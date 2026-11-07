import logging
import sys

logging.basicConfig(
    filename="/tmp/mesh",
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    force=True
)

# Redirect stderr too, so library diagnostics don't pollute the CLI
sys.stderr = open("/tmp/mesh", "a", buffering=1)


import meshtastic
import meshtastic.ble_interface
from pubsub import pub
import threading


if len(sys.argv) != 2:
    print(f"Usage: {sys.argv[0]} <BLE_ADDRESS>")
    print(f"Example: {sys.argv[0]} B8:1F:3F:D9:0C:CD")
    sys.exit(1)

BLE_ADDRESS = sys.argv[1]

print_lock = threading.Lock()

pending = {}   # packet id -> (destination number or None, text)
pending_lock = threading.Lock()


def node_id(value):
    if isinstance(value, int):
        return f"!{value:08x}"
    return str(value)


def find_nodes_by_last_byte(interface, b, exclude=()):
    """Meshtastic packets only carry the last byte of the relay's node number,
    so look through the radio's node database for nodes ending in that byte."""
    matches = []
    for n in list((interface.nodes or {}).values()):
        num = n.get("num")
        if num is None or num in exclude:
            continue
        if num & 0xFF == b:
            user = n.get("user", {})
            matches.append((num, user.get("shortName", ""), user.get("longName", ""), n.get("snr")))
    return matches


def describe_relay(packet, interface, my_num):
    b = packet.get("relayNode")
    if b is None:
        return "relay: not reported in this packet"

    exclude = (my_num,) if my_num is not None else ()
    matches = find_nodes_by_last_byte(interface, b, exclude)

    if not matches:
        text = f"relay: ..{b:02x} (not in node database)"
    else:
        names = " or ".join(
            f"!{num:08x} [{short}] {long_}".rstrip() for num, short, long_, _ in matches
        )
        text = f"relay: ..{b:02x} = {names}"
        if len(matches) > 1:
            text += "  (ambiguous: several nodes share that last byte)"

    if my_num is not None and b == (my_num & 0xFF):
        text += "  (same last byte as your own node)"

    extra = []
    if "rxRssi" in packet:
        extra.append(f"RSSI {packet['rxRssi']} dBm")
    if "rxSnr" in packet:
        extra.append(f"SNR {packet['rxSnr']} dB")
    if "hopStart" in packet and "hopLimit" in packet:
        extra.append(f"{packet['hopStart'] - packet['hopLimit']} hops")
    if extra:
        text += "\n      " + ", ".join(extra)

    return text

def on_receive(packet, interface):
    sender_num = packet.get("from", 0)
    sender = node_id(sender_num)
    decoded = packet.get("decoded", {})
    message = decoded.get("text", "")

    # Delivery report for something we sent
    if decoded.get("portnum") == "ROUTING_APP" and "requestId" in decoded:
        req_id = decoded["requestId"]
        reason = decoded.get("routing", {}).get("errorReason", "NONE")

        with pending_lock:
            info = pending.pop(req_id, None)

        if info is not None:
            dest_num, text = info
            try:
                my_num = interface.myInfo.my_node_num
            except Exception:
                my_num = None

            if reason != "NONE":
                status = f"FAILED ({reason})"
            elif dest_num is not None and sender_num == dest_num:
                status = "DELIVERED (confirmed by destination)"
            elif sender_num == my_num:
                status = "SENT OK (heard a neighbour rebroadcast, destination not confirmed)"
            else:
                status = f"ACK from {sender}"

            relay_text = describe_relay(packet, interface, my_num)

            with print_lock:
                print(f"\n[ACK] {status}")
                print(f"      Packet ID: {req_id}  Message: {text!r}")
                print(f"      {relay_text}")
                print("\nmesh> ", end="", flush=True)


    with print_lock:
        with open("/tmp/mesh", "a", buffering=1) as log:
            if message:
                log.write(f"[RECEIVED] {sender}: {message}\n")
            else:
                log.write(
                    f"[PACKET] {sender}: "
                    f"{decoded.get('portnum', 'UNKNOWN')}\n"
                )


# Subscribe to incoming packets
pub.subscribe(on_receive, "meshtastic.receive")

print("Connecting to Meshtastic over BLE...")

iface = meshtastic.ble_interface.BLEInterface(BLE_ADDRESS)

print("Connected!")
print("-----------------------------------")
print("Send messages using:")
print("  !aabbccdd Hello there")
print("  ^all Hello everyone")
print("Type 'quit' to exit.")
print("-----------------------------------")

try:
    while True:
        try:
            line = input("\nmesh> ").strip()

            if line.lower() == "quit":
                break

            if not line:
                continue

            parts = line.split(maxsplit=1)

            if len(parts) != 2:
                print("Usage: !nodeid message")
                continue

            destination, message = parts

            if not (destination.startswith("!") or destination == "^all"):
                print("Destination must look like !aabbccdd or ^all")
                continue

            try:
                dest_num = int(destination[1:], 16) if destination.startswith("!") else None
            except ValueError:
                print("Invalid node id")
                continue

            packet = iface.sendText(
                message,
                destinationId=destination,
                wantAck=True
            )

            # Register before the ACK can arrive
            with pending_lock:
                pending[packet.id] = (dest_num, message)

            print(f"[SENT] To {destination}: {message}")
            print(f"      Packet ID: {packet.id}")

        except EOFError:
            break
        except Exception as e:
            logging.exception("send failed")
            print(f"Error: {e}")

except KeyboardInterrupt:
    print("\nExiting...")

finally:
    iface.close()
    print("Disconnected.")
