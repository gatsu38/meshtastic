import logging
import sys
import threading
import traceback

import meshtastic
import meshtastic.ble_interface
from pubsub import pub

BLE_ADDRESS = "B8:1F:3F:D9:0C:CD"

logging.basicConfig(
    filename="/tmp/mesh",
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    force=True
)

sys.stderr = open("/tmp/mesh", "a", buffering=1)

print_lock = threading.Lock()


def log(message):
    with print_lock:
        print(message, flush=True)
        with open("/tmp/mesh", "a", buffering=1) as f:
            f.write(message + "\n")


def node_id(value):
    if isinstance(value, int):
        return f"!{value:08x}"
    return str(value)


def on_receive(packet, interface):
    try:
        sender = node_id(packet.get("from", 0))
        decoded = packet.get("decoded", {})
        message = decoded.get("text", "")

        if message:
            log(f"[RECEIVED] {sender}: {message}")
        else:
            log(
                f"[PACKET] {sender}: "
                f"{decoded.get('portnum', 'UNKNOWN')}"
            )

    except Exception:
        logging.exception("Receive callback error")


pub.subscribe(on_receive, "meshtastic.receive")

log("Connecting to Meshtastic over BLE...")

iface = None

try:
    iface = meshtastic.ble_interface.BLEInterface(BLE_ADDRESS)

    log("Connected!")
    log("-----------------------------------")
    log("Send messages using:")
    log("  !aabbccdd Hello there")
    log("Type 'quit' to exit.")
    log("-----------------------------------")

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

            if not destination.startswith("!"):
                print("Destination must look like !aabbccdd")
                continue

            try:
                packet = iface.sendText(
                    message,
                    destinationId=destination,
                    wantAck=True
                )

                log(f"[SENT] To {destination}: {message}")
                log(f"[PACKET ID] {packet.get('id', 'unknown')}")

            except Exception:
                logging.exception("Message sending failed")
                log("[ERROR] Failed to send message. Check /tmp/mesh")

        except EOFError:
            break

except KeyboardInterrupt:
    log("Interrupted by user")

except Exception:
    logging.exception("BLE connection error")
    log("[ERROR] BLE connection failed")

finally:
    if iface is not None:
        try:
            iface.close()
        except Exception:
            logging.exception("Error closing BLE connection")

    log("Disconnected.")
