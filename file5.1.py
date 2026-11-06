import re
import ast
import time
from collections import defaultdict

LOG_FILE = "/tmp/mesh_usb"

packets = []


def get_field(line, name):
    pattern = rf"'{re.escape(name)}':\s*(-?\d+(?:\.\d+)?)"
    match = re.search(pattern, line)
    return match.group(1) if match else None


# Read Meshtastic decoded text-message events
with open(LOG_FILE, errors="replace") as f:
    for line in f:

        if "Publishing meshtastic.receive.text: packet=" not in line:
            continue

        # Extract the decoded dictionary
        match = re.search(
            r"'decoded': (\{.*?\}), 'id':",
            line
        )

        if not match:
            continue

        try:
            decoded = ast.literal_eval(match.group(1))
        except (ValueError, SyntaxError):
            continue

        sender = get_field(line, "from")
        recipient = get_field(line, "to")
        rx_time = get_field(line, "rxTime")
        rssi = get_field(line, "rxRssi")
        snr = get_field(line, "rxSnr")
        hop_start = get_field(line, "hopStart")
        hop_limit = get_field(line, "hopLimit")
        relay = get_field(line, "relayNode")

        if not sender:
            continue

        packets.append({
            "sender": int(sender),
            "recipient": int(recipient) if recipient else 0xFFFFFFFF,
            "time": int(rx_time) if rx_time else None,
            "rssi": rssi,
            "snr": snr,
            "hop_start": hop_start,
            "hop_limit": hop_limit,
            "relay": relay,
            "port": decoded.get("portnum", "UNKNOWN"),
            "text": decoded.get("text", "")
        })


# Build relay lookup
by_byte = defaultdict(set)

for p in packets:
    by_byte[p["sender"] & 0xFF].add(p["sender"])


# Print packets
print()
print("=" * 150)
print(
    f"{'TIME':<10} "
    f"{'SENDER':<12} "
    f"{'RECIPIENT':<12} "
    f"{'PORT':<18} "
    f"{'RSSI':>7} "
    f"{'SNR':>7} "
    f"{'HOPS':<12} "
    f"{'FORWARDER':<22} "
    f"MESSAGE"
)
print("=" * 150)


for p in packets:

    sender = p["sender"]
    recipient = p["recipient"]

    timestamp = (
        time.strftime("%H:%M:%S", time.localtime(p["time"]))
        if p["time"] else "--:--:--"
    )

    recipient_name = (
        "BROADCAST"
        if recipient == 0xFFFFFFFF
        else f"!{recipient:08x}"
    )

    # Hop count
    if p["hop_start"] is not None and p["hop_limit"] is not None:
        hops_taken = int(p["hop_start"]) - int(p["hop_limit"])
        hops = str(hops_taken)
    else:
        hops_taken = None
        hops = "?"

    # Forwarder
    if p["relay"] is None:
        forwarder = "UNKNOWN"
    else:
        relay_byte = int(p["relay"])

        candidates = sorted(
            by_byte.get(relay_byte, set()) - {sender}
        )

        if hops_taken == 0:
            forwarder = "DIRECT"
        elif len(candidates) == 1:
            forwarder = f"!{candidates[0]:08x}"
        elif candidates:
            forwarder = f"..{relay_byte:02x} (ambiguous)"
        else:
            forwarder = f"..{relay_byte:02x} (unknown)"

    message = p["text"].replace("\n", " ").strip()

    print(
        f"{timestamp:<10} "
        f"!{sender:08x} "
        f"{recipient_name:<12} "
        f"{p['port']:<18} "
        f"{p['rssi'] or 'N/A':>7} "
        f"{p['snr'] or 'N/A':>7} "
        f"{hops:<12} "
        f"{forwarder:<22} "
        f"{message}"
    )


print("=" * 150)
print(f"Total text packets: {len(packets)}")

