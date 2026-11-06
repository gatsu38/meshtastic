import re, time
from collections import defaultdict

KEYS = "from|rx_time|portnum|hop_start|hop_limit|relay_node"
packets, in_block, pkt = [], False, {}

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
    m = re.match(rf"\s+({KEYS}): (\w+)", line)
    if m:
        pkt[m.group(1)] = m.group(2)

# Every node heard as a sender, grouped by the last byte of its ID
by_byte = defaultdict(set)
for p in packets:
    n = int(p["from"])
    by_byte[n & 0xFF].add(n)

for p in packets:
    sender = int(p["from"])
    t = time.strftime("%H:%M:%S", time.localtime(int(p["rx_time"]))) if "rx_time" in p else "--:--:--"
    port = p.get("portnum", "ENCRYPTED")

    if "hop_start" in p and "hop_limit" in p:
        taken = int(p["hop_start"]) - int(p["hop_limit"])
        hops = "direct" if taken == 0 else f"{taken} hop{'s' if taken != 1 else ''}"
    else:
        taken, hops = None, "hops ?"

    if "relay_node" not in p:
        relay = "relay ?"
    else:
        b = int(p["relay_node"])
        if taken == 0:
            relay = f"relayed by sender itself (..{b:02x})"
        else:
            cands = sorted(by_byte.get(b, []) - {sender})
            if cands:
                relay = f"relay ..{b:02x} = " + " or ".join(f"!{c:08x}" for c in cands)
            else:
                relay = f"relay ..{b:02x} (no matching node in log)"

    print(f"{t}  !{sender:08x}  {port:<16} {hops:<8} {relay}")
