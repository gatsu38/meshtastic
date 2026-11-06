import re, time

sender = None
port = "ENCRYPTED"

for line in open("mesh", errors="replace"):
    m = re.match(r"\s+from: (\d+)", line)
    if m:
        sender = int(m.group(1))
        port = "ENCRYPTED"   # reset for each new packet
        continue

    m = re.match(r"\s+portnum: (\w+)", line)
    if m:
        port = m.group(1)
        continue

    m = re.match(r"\s+rx_time: (\d+)", line)
    if m and sender is not None:
        t = time.strftime("%H:%M:%S", time.localtime(int(m.group(1))))
        print(f"{t}  !{sender:08x}  {port}")
        sender = None
