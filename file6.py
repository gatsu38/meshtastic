import re
import ast
import time
from collections import defaultdict

LOGFILE = "/tmp/mesh"

packets = []

def get_field(line, name):
    m = re.search(rf"'{name}':\s*(-?\d+(?:\.\d+)?)", line)
    return m.group(1) if m else None


# Read Meshtastic DEBUG log
with open(LOGFILE, errors="replace") as f:
    for line in f:

        if "Publishing meshtastic.receive.text: packet=" not in line:
            continue

        # Extract decoded dictionary
        m = re.search(r"'decoded': (\{.*?\}), 'id':", line)
        if not m:
            continue

        try:
            decoded = ast.literal_eval(m.group(1))
        except (ValueError, SyntaxError):
            continue

        p = {
            "from": get_field(line, "from"),
            "to": get_field(line, "to"),
            "id": get_field(line, "id"),
            "rx_time": get_field(line, "rxTime"),
            "rx_rssi": get_field(line, "rxRssi"),
            "rx_snr": get_field(line, "rxSnr"),
            "hop_start": get_field(line, "hopStart"),
            "hop_limit": get_field(line, "hopLimit"),
            "relay_node": get_field(line, "relayNode"),
            "portnum": decoded.get("portnum", "UNKNOWN"),
            "text": decoded.get("text", ""),
        }

        if p["from"]:
            packets.append(p)


# Build node lookup using last byte of node ID
by_byte = defaultdict(set)

for p in packets:
    n = int(p["from"])
    by_byte[n & 0xFF].add(n)


# Display packets
for p in packets:

    sender = int(p["from"])

    t = (
        time.strftime(
            "%H:%M:%S",
            time.localtime(int(float(p["rx_time"])))
        )
        if p["rx_time"] else "--:--:--"
    )

    # Recipient
    recipient = (
        f"!{int(p['to']):08x}"
        if p["to"] and int(p["to"]) != 0xFFFFFFFF
        else "BROADCAST"
    )

    # Packet type
    port = p["portnum"]

    # Signal
    rssi = p["rx_rssi"] or "N/A"
    snr = p["rx_snr"] or "N/A"

    # Hops
    if p["hop_start"] and p["hop_limit"]:
        taken = int(p["hop_start"]) - int(p["hop_limit"])

        hops = (
            "direct" if taken == 0
            else f"{taken} hop{'s' if taken != 1 else ''}"
        )

        hops += f" (start {p['hop_start']}, left {p['hop_limit']})"

    else:
        taken = None
        hops = "hops ?"

    # Forwarder identification
    if p["relay_node"] is None:
        relay = "relay ?"

    else:
        b = int(p["relay_node"])

        if taken == 0:
            relay = f"direct / sender (..{b:02x})"

        else:
            cands = sorted(by_byte.get(b, set()) - {sender})

            if len(cands) == 1:
                relay = f"!{cands[0]:08x}"

            elif cands:
                relay = "relay ..{:02x} = {}".format(
                    b,
                    " or ".join(f"!{c:08x}" for c in cands)
                )

            else:
                relay = f"relay ..{b:02x} (not found)"

    # Message text
    message = p["text"]

    # Output
    print(
        f"{t}  "
        f"!{sender:08x} -> {recipient:<12} "
        f"{port:<16} "
        f"RSSI: {rssi:>6} dBm  "
        f"SNR: {snr:>6} dB  "
        f"{hops:<27} "
        f"Forwarder: {relay}"
    )

    if message:
        print(f"         MESSAGE: {message}")

    print()
