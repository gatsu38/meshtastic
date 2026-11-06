
import re
import time
from collections import defaultdict

KEYS = (
    "from|to|rx_time|portnum|hop_start|hop_limit|"
    "relay_node|rx_rssi|rx_snr|payload"
)

packets = []
in_block = False
pkt = {}


def readable_payload(value):
    if not value:
        return None

    try:
        # Handle Python bytes representation, if present
        if value.startswith("b'") or value.startswith('b"'):
            import ast
            data = ast.literal_eval(value)
        else:
            data = bytes.fromhex(value)

        text = data.decode("utf-8").rstrip("\x00")

        # Require mostly printable characters
        if not text or sum(c.isprintable() or c in "\r\n\t" for c in text) / len(text) < 0.90:
            return None

        return text

    except (ValueError, UnicodeDecodeError, SyntaxError):
        return None


# Read packet log
for line in open("/tmp/mesh_usb", errors="replace"):
    if "Received from radio: packet {" in line:
        in_block, pkt = True, {}
        continue

    if not in_block:
        continue

    if line.rstrip() == "}":
        if "from" in pkt:
            packets.append(pkt)
        in_block = False
        continue

    m = re.match(rf"\s+({KEYS}):\s*(.*)", line)
    if m:
         pkt[m.group(1)] = m.group(2).strip()

    if "payload" in line or "text:" in line:
        print("DEBUG:", repr(line))

#    m = re.match(rf"\s+({KEYS}): (\S+)", line)
#    if m:
#        pkt[m.group(1)] = m.group(2)


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
            time.localtime(int(p["rx_time"]))
        )
        if "rx_time" in p else "--:--:--"
    )

    # Recipient
    recipient = (
        f"!{int(p['to']):08x}"
        if "to" in p and int(p["to"]) != 0xFFFFFFFF
        else "BROADCAST"
    )

    # Port
    port = p.get("portnum", "ENCRYPTED")

    # Hop count
    if "hop_start" in p and "hop_limit" in p:
        taken = int(p["hop_start"]) - int(p["hop_limit"])
        hops = (
            "direct" if taken == 0
            else f"{taken} hop{'s' if taken != 1 else ''}"
        )
        hops += f" (start {p['hop_start']}, left {p['hop_limit']})"
    else:
        taken = None
        hops = "hops ?"

    # RSSI and SNR
    rssi = p.get("rx_rssi", "N/A")
    snr = p.get("rx_snr", "N/A")

    # Relay identification
    if "relay_node" not in p:
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

    # Payload decoding
    payload = readable_payload(p.get("payload", ""))

    if payload:
        payload = repr(payload)
    else:
        payload = ""

    print(
        f"{t}  "
        f"!{sender:08x} -> {recipient:<12} "
        f"{port:<16} "
        f"RSSI: {rssi:>5} dBm  "
        f"SNR: {snr:>5} dB  "
        f"{hops:<30} "
        f"Forwarder: {relay}"
        f"{' | MSG: ' + payload if payload else ''}"

    )
