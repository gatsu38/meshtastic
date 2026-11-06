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


def node_id(value):
    if isinstance(value, int):
        return f"!{value:08x}"
    return str(value)


def on_receive(packet, interface):
    sender = node_id(packet.get("from", 0))
    decoded = packet.get("decoded", {})
    message = decoded.get("text", "")

    with print_lock:
        with open("/tmp/mesh", "a", buffering=1) as log:
            if message:
                log.write(f"[RECEIVED] {sender}: {message}\n")
            else:
                log.write(
                    f"[PACKET] {sender}: "
                    f"{decoded.get('portnum', 'UNKNOWN')}\n"
                )

def on_ack(p):
    print(f"\n[ACK] {p['decoded']['routing']['errorReason']} for {p['decoded']['requestId']}")


# Subscribe to incoming packets
pub.subscribe(on_receive, "meshtastic.receive")

print("Connecting to Meshtastic over BLE...")

iface = meshtastic.ble_interface.BLEInterface(BLE_ADDRESS)

print("Connected!")
print("-----------------------------------")
print("Send messages using:")
print("  !aabbccdd Hello there")
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
                print("Destination must look like !aabbccdd")
                continue

            packet = iface.sendText(
                message,
                destinationId=destination,
                wantAck=True,
                onResponse=on_ack
            )

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
