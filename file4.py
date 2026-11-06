
import re
import time

in_block = False
pkt = {}

def show(p):
    if "from" not in p:
        return

    t = (
        time.strftime("%H:%M:%S", time.localtime(int(p["rx_time"])))
        if "rx_time" in p else "--:--:--"
    )

    sender = f"!{int(p['from']):08x}"

    recipient = (
        f"!{int(p['to']):08x}"
        if "to" in p and p["to"] != "0"
        else "BROADCAST"
    )

    port = p.get("portnum", "ENCRYPTED")

    if "hop_start" in p and "hop_limit" in p:
        taken = int(p["hop_start"]) - int(p["hop_limit"])
        hops = "direct" if taken == 0 else f"{taken} hop{'s' if taken != 1 else ''}"
        hops += f" (start {p['hop_start']}, left {p['hop_limit']})"
    else:
        hops = "hops unknown"

    rssi = p.get("rx_rssi", "N/A")
    snr = p.get("rx_snr", "N/A")

    print(
        f"{t}  "
        f"{sender:<12} -> {recipient:<12} "
        f"{port:<16} "
        f"RSSI: {rssi:>5} dBm  "
        f"SNR: {snr:>5} dB  "
        f"{hops}"
    )


for line in open("/tmp/mesh", errors="replace"):
    if "Received from radio: packet {" in line:
        in_block, pkt = True, {}
        continue

    if not in_block:
        continue

    if line.rstrip() == "}":
        show(pkt)
        in_block = False
        continue

    m = re.match(
        r"\s+(from|to|rx_time|portnum|hop_start|hop_limit|rx_rssi|rx_snr): (\S+)",
        line
    )

    if m:
        pkt[m.group(1)] = m.group(2)
