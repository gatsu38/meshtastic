import re, time

in_block = False
pkt = {}

def show(p):
    if "from" not in p:
        return
    t = time.strftime("%H:%M:%S", time.localtime(int(p["rx_time"]))) if "rx_time" in p else "--:--:--"
    port = p.get("portnum", "ENCRYPTED")
    if "hop_start" in p and "hop_limit" in p:
        taken = int(p["hop_start"]) - int(p["hop_limit"])
        hops = "direct" if taken == 0 else f"{taken} hop{'s' if taken != 1 else ''}"
        hops += f" (start {p['hop_start']}, left {p['hop_limit']})"
    else:
        hops = "hops unknown"
    print(f"{t}  !{int(p['from']):08x}  {port:<16} {hops}")

for line in open("mesh", errors="replace"):
    if "Received from radio: packet {" in line:
        in_block, pkt = True, {}
        continue
    if not in_block:
        continue
    if line.rstrip() == "}":          # closing brace of the packet block
        show(pkt)
        in_block = False
        continue
    m = re.match(r"\s+(from|rx_time|portnum|hop_start|hop_limit): (\w+)", line)
    if m:
        pkt[m.group(1)] = m.group(2)
