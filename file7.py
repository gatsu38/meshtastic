import re
import time
from collections import defaultdict

from google.protobuf.json_format import MessageToDict

try:
    from meshtastic.protobuf import mesh_pb2, telemetry_pb2
except ImportError:  # older meshtastic versions
    from meshtastic import mesh_pb2, telemetry_pb2

KEYS = (
    "from|to|rx_time|portnum|hop_start|hop_limit|"
    "relay_node|rx_rssi|rx_snr|payload|encrypted"
)

# Which protobuf message class decodes which port
PORT_TYPES = {
    "NODEINFO_APP":     getattr(mesh_pb2, "User", None),
    "POSITION_APP":     getattr(mesh_pb2, "Position", None),
    "TELEMETRY_APP":    getattr(telemetry_pb2, "Telemetry", None),
    "ROUTING_APP":      getattr(mesh_pb2, "Routing", None),
    "NEIGHBORINFO_APP": getattr(mesh_pb2, "NeighborInfo", None),
    "TRACEROUTE_APP":   getattr(mesh_pb2, "RouteDiscovery", None),
    "WAYPOINT_APP":     getattr(mesh_pb2, "Waypoint", None),
    "MAP_REPORT_APP":   getattr(mesh_pb2, "MapReport", None),
}

# Fields that are just noise or unreadable bytes
HIDE = {"macaddr", "public_key", "time"}

packets = []
in_block = False
pkt = {}

SIMPLE_ESCAPES = {
    "n": 10, "r": 13, "t": 9,
    '"': 34, "'": 39, "\\": 92,
}


def unescape_proto(value):
    """Decode a protobuf text-format string like "\\rD\\275j" into bytes."""
    value = value.strip()
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        value = value[1:-1]

    out = bytearray()
    i = 0
    while i < len(value):
        c = value[i]
        if c != "\\":
            out += c.encode("utf-8")
            i += 1
            continue

        i += 1
        if i >= len(value):
            break
        c = value[i]

        if c in "01234567":                      # octal escape, up to 3 digits
            j = i
            while j < len(value) and j < i + 3 and value[j] in "01234567":
                j += 1
            out.append(int(value[i:j], 8) & 0xFF)
            i = j
        elif c == "x":                           # hex escape
            j = i + 1
            while j < len(value) and j < i + 3 and value[j] in "0123456789abcdefABCDEF":
                j += 1
            out.append(int(value[i + 1:j], 16))
            i = j
        else:
            out.append(SIMPLE_ESCAPES.get(c, ord(c)))
            i += 1

    return bytes(out)


def flatten(d):
    """Turn a nested dict into a compact 'key=value key[sub=value]' string."""
    parts = []
    for k, v in d.items():
        if k in HIDE:
            continue
        if isinstance(v, dict):
            parts.append(f"{k}[{flatten(v)}]")
        elif isinstance(v, list):
            items = ", ".join(
                f"({flatten(x)})" if isinstance(x, dict) else str(x) for x in v
            )
            parts.append(f"{k}=[{items}]")
        elif isinstance(v, float):
            parts.append(f"{k}={round(v, 3)}")
        else:
            parts.append(f"{k}={v}")
    return " ".join(parts)


def describe(msg):
    d = MessageToDict(msg, preserving_proto_field_name=True)

    # Position: convert the integer degrees (1e-7) into normal coordinates
    lat_i = d.pop("latitude_i", None)
    lon_i = d.pop("longitude_i", None)
    if lat_i is not None or lon_i is not None:
        d = {
            "lat": round(int(lat_i or 0) / 1e7, 5),
            "lon": round(int(lon_i or 0) / 1e7, 5),
            **d,
        }

    return flatten(d)


def format_payload(port, value, max_hex=48):
    """Return (label, text) for display under the packet line."""
    if not value:
        return None

    data = unescape_proto(value)
    if not data:
        return None

    # Plain text messages
    if port == "TEXT_MESSAGE_APP":
        return "MSG", repr(data.decode("utf-8", errors="replace"))

    # Known protobuf payloads
    cls = PORT_TYPES.get(port)
    if cls is not None:
        try:
            msg = cls()
            msg.ParseFromString(data)
            text = describe(msg)
            if text:
                return port.replace("_APP", ""), text
        except Exception:
            pass  # fall through to the generic display

    # Generic fallback: printable text, otherwise hex
    try:
        text = data.decode("utf-8").rstrip("\x00")
        if text and sum(c.isprintable() or c in "\r\n\t" for c in text) / len(text) >= 0.90:
            return "TEXT", repr(text)
    except UnicodeDecodeError:
        pass

    hexstr = " ".join(f"{b:02x}" for b in data[:max_hex])
    if len(data) > max_hex:
        hexstr += " ..."
    return "HEX", f"{len(data)} bytes: {hexstr}"


# Read packet log
for line in open("/tmp/mesh", errors="replace"):
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

    print(
        f"{t}  "
        f"!{sender:08x} -> {recipient:<12} "
        f"{port:<16} "
        f"RSSI: {rssi:>5} dBm  "
        f"SNR: {snr:>5} dB  "
        f"{hops:<30} "
        f"Forwarder: {relay}"
    )

    # Payload, indented under its packet
    payload = format_payload(port, p.get("payload", ""))
    if payload:
        label, text = payload
        print(f"           {label}: {text}")
    elif "encrypted" in p:
        size = len(unescape_proto(p["encrypted"]))
        print(f"           ENCRYPTED: {size} bytes (channel key unknown)")

    print()
