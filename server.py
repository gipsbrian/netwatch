"""
netwatch — live LAN device dashboard.

Run:   sudo python server.py            (real ARP scanning, needs root/admin)
       python server.py --demo          (simulated devices, no privileges)
Then open http://localhost:8008
"""
import argparse
import asyncio
import ipaddress
import json
import os
import random
import re
import socket
import sys
import time
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

HERE = Path(__file__).parent
SCAN_INTERVAL = 10          # seconds between ARP sweeps
STALE_AFTER = 45            # seconds without a reply → "stale"
GONE_AFTER = 180            # seconds without a reply → removed

# ---------------------------------------------------------------- vendor lookup
# Small built-in table so common vendors resolve offline. On first run the full
# IEEE registry (~35k vendors) is downloaded once and cached; see ensure_vendor_db().
OUI_MINI = {
    "A4:83:E7": "Apple", "F0:18:98": "Apple", "3C:22:FB": "Apple", "DC:A9:04": "Apple",
    "F4:F5:D8": "Google", "3C:5A:B4": "Google", "54:60:09": "Google",
    "94:65:2D": "OnePlus", "F8:2F:A8": "Samsung", "8C:F5:A3": "Samsung", "00:12:FB": "Samsung",
    "B8:27:EB": "Raspberry Pi", "DC:A6:32": "Raspberry Pi", "E4:5F:01": "Raspberry Pi",
    "24:6F:28": "Espressif", "A4:CF:12": "Espressif", "30:AE:A4": "Espressif",
    "00:11:32": "Synology", "F0:81:73": "Amazon", "FC:65:DE": "Amazon", "74:C2:46": "Amazon",
    "00:17:88": "Philips Hue", "70:4F:57": "TP-Link", "50:C7:BF": "TP-Link", "C0:25:E9": "TP-Link",
    "B0:BE:76": "TP-Link", "18:E8:29": "Ubiquiti", "F0:9F:C2": "Ubiquiti", "74:AC:B9": "Ubiquiti",
    "3C:52:82": "HP", "00:1E:0B": "HP", "00:80:92": "Silex (printer)", "00:50:56": "VMware",
    "08:00:27": "VirtualBox", "00:1A:11": "Google", "00:0C:29": "VMware", "AC:DE:48": "Private",
    "D8:3A:DD": "Raspberry Pi", "28:CD:C1": "Raspberry Pi", "9C:8E:CD": "Amcrest", "00:E0:4C": "Realtek",
    "04:D3:B0": "Intel", "48:51:C5": "Intel", "A0:36:9F": "Intel", "FC:AA:14": "Gigabyte",
    "00:D8:61": "Micro-Star", "2C:F0:5D": "Micro-Star", "00:1B:21": "Intel", "8C:EC:4B": "Dell",
}

VENDOR_CACHE = Path(os.environ.get("NETWATCH_CACHE_DIR", Path.home() / ".cache" / "netwatch")) / "oui.tsv"
VENDOR_SOURCES = (
    "https://standards-oui.ieee.org/oui/oui.txt",                    # IEEE, authoritative
    "https://www.wireshark.org/download/automated/data/manuf",       # Wireshark mirror, fallback
)
_VENDORS: dict[str, str] = {}
_SUFFIXES = re.compile(
    r"[ ,.]*(co\.?,? ?ltd\.?|corp(oration)?\.?|inc\.?|incorporated|llc|ltd\.?|limited|gmbh|s\.?a\.?|b\.?v\.?|ag|plc|oy|pte\.?)$",
    re.I,
)


def _tidy(name: str) -> str:
    """'Samsung Electronics Co.,Ltd' -> 'Samsung Electronics'."""
    name = name.strip().strip('"')
    for _ in range(3):
        trimmed = _SUFFIXES.sub("", name).strip(" ,.")
        if trimmed == name:
            break
        name = trimmed
    return name


def _parse_registry(text: str) -> dict[str, str]:
    out = {}
    ieee = re.compile(r"^([0-9A-F]{2})-([0-9A-F]{2})-([0-9A-F]{2})\s+\(hex\)\s+(.+)$", re.M)
    for a, b, c, name in ieee.findall(text):
        out[a + b + c] = _tidy(name)
    if not out:  # Wireshark "manuf" format: 00:00:0C<TAB>Cisco<TAB>Cisco Systems, Inc
        for line in text.splitlines():
            parts = line.split("\t")
            if len(parts) >= 2 and re.fullmatch(r"[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}", parts[0]):
                out[parts[0].replace(":", "").upper()] = _tidy(parts[2] if len(parts) > 2 and parts[2] else parts[1])
    return out


def _load_cache() -> bool:
    try:
        for line in VENDOR_CACHE.read_text(encoding="utf-8").splitlines():
            prefix, _, name = line.partition("\t")
            if name:
                _VENDORS[prefix] = name
        return bool(_VENDORS)
    except OSError:
        return False


def ensure_vendor_db() -> bool:
    """Load the vendor registry, downloading it once if needed. Returns True if newly loaded."""
    if _VENDORS:
        return False
    if _load_cache():
        print(f"netwatch: vendor database loaded ({len(_VENDORS):,} vendors)")
        return True
    import urllib.request
    for url in VENDOR_SOURCES:
        try:
            print(f"netwatch: downloading vendor database (one-time) from {url.split('/')[2]}…")
            req = urllib.request.Request(url, headers={"User-Agent": "netwatch/1.0 (+https://github.com/gipsbrian/netwatch)"})
            with urllib.request.urlopen(req, timeout=30) as r:
                parsed = _parse_registry(r.read().decode("utf-8", "replace"))
            if len(parsed) < 1000:
                raise ValueError(f"only {len(parsed)} entries parsed")
            VENDOR_CACHE.parent.mkdir(parents=True, exist_ok=True)
            VENDOR_CACHE.write_text("\n".join(f"{k}\t{v}" for k, v in sorted(parsed.items())), encoding="utf-8")
            _VENDORS.update(parsed)
            print(f"netwatch: vendor database ready ({len(_VENDORS):,} vendors)")
            return True
        except Exception as e:
            print(f"netwatch: couldn't fetch {url.split('/')[2]}: {e}", file=sys.stderr)
    print("netwatch: using built-in vendor table; will retry next start", file=sys.stderr)
    return False


def vendor_for(mac: str) -> str:
    mac = mac.upper()
    first_octet = int(mac[:2], 16)
    if first_octet & 0x02:  # locally administered bit: randomised "private" address (iOS, Android, Windows)
        return "Private address"
    key = mac.replace(":", "").replace("-", "")[:6]
    return _VENDORS.get(key) or OUI_MINI.get(mac[:8], "Unknown")


# ---------------------------------------------------------------- state
class DeviceTable:
    def __init__(self):
        self.devices: dict[str, dict] = {}   # key: MAC
        self.listeners: set[asyncio.Queue] = set()
        self.scan_count = 0
        self.gateway_ip = None
        self.network_name = None

    def snapshot(self):
        return {
            "type": "snapshot",
            "gateway": self.gateway_ip,
            "network": self.network_name,
            "scan": self.scan_count,
            "devices": list(self.devices.values()),
        }

    async def broadcast(self, msg: dict):
        dead = []
        for q in self.listeners:
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            self.listeners.discard(q)

    async def observe(self, mac: str, ip: str, latency_ms=None, hostname=None):
        now = time.time()
        d = self.devices.get(mac)
        if d is None:
            d = {
                "mac": mac,
                "ip": ip,
                "hostname": hostname or resolve_host(ip),
                "vendor": vendor_for(mac),
                "first_seen": now,
                "last_seen": now,
                "latency": latency_ms,
                "status": "active",
                "is_gateway": ip == self.gateway_ip,
                "history": [latency_ms] if latency_ms is not None else [],
            }
            self.devices[mac] = d
            await self.broadcast({"type": "joined", "device": d})
        else:
            was = d["status"]
            d.update(ip=ip, last_seen=now, status="active")
            if latency_ms is not None:
                d["latency"] = latency_ms
                d["history"] = (d["history"] + [latency_ms])[-30:]
            if hostname:
                d["hostname"] = hostname
            await self.broadcast({"type": "updated", "device": d, "returned": was != "active"})

    async def age(self):
        now = time.time()
        for mac, d in list(self.devices.items()):
            gap = now - d["last_seen"]
            if gap > GONE_AFTER:
                del self.devices[mac]
                await self.broadcast({"type": "left", "mac": mac})
            elif gap > STALE_AFTER and d["status"] != "stale":
                d["status"] = "stale"
                await self.broadcast({"type": "updated", "device": d, "returned": False})


table = DeviceTable()


def detect_network_name(iface: str | None = None) -> str | None:
    """Best-effort Wi-Fi SSID (or interface name when wired). Never raises."""
    import platform
    import re
    import subprocess

    def run(cmd):
        try:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=3).stdout
        except Exception:
            return ""

    sysname = platform.system()
    if sysname == "Darwin":
        # macOS 14+: the airport tool is gone; ipconfig still reports the SSID.
        for dev in ([iface] if iface else []) + ["en0", "en1"]:
            out = run(["ipconfig", "getsummary", dev])
            m = re.search(r"^\s*SSID\s*:\s*(.+)$", out, re.M)
            if m:
                return m.group(1).strip()
        out = run(["networksetup", "-getairportnetwork", iface or "en0"])
        m = re.search(r"Network:\s*(.+)$", out, re.M)
        if m:
            return m.group(1).strip()
        out = run(["system_profiler", "SPAirPortDataType"])
        m = re.search(r"Current Network Information:\s*\n\s*(.+?):", out)
        if m:
            return m.group(1).strip()
    elif sysname == "Linux":
        out = run(["iwgetid", "-r"]).strip()
        if out:
            return out
        out = run(["nmcli", "-t", "-f", "active,ssid", "dev", "wifi"])
        for line in out.splitlines():
            if line.startswith("yes:"):
                return line[4:]
    elif sysname == "Windows":
        out = run(["netsh", "wlan", "show", "interfaces"])
        m = re.search(r"^\s*SSID\s*:\s*(.+)$", out, re.M)
        if m:
            return m.group(1).strip()
    # Wired or unknown: fall back to the interface name scapy routes through.
    try:
        from scapy.all import conf  # type: ignore
        return f"wired ({iface or conf.route.route('0.0.0.0')[0]})"
    except Exception:
        return None


def resolve_host(ip: str) -> str | None:
    try:
        socket.setdefaulttimeout(0.4)
        return socket.gethostbyaddr(ip)[0].split(".")[0]
    except Exception:
        return None


# ---------------------------------------------------------------- real scanning
TUNNEL_PREFIXES = ("utun", "tun", "tap", "ppp", "ipsec", "wg", "tailscale", "zt")
VIRTUAL_PREFIXES = ("lo", "docker", "br-", "veth", "virbr", "vmnet", "vboxnet", "cni", "flannel", "cali", "awdl", "llw", "bridge", "anpi", "ap1")


def _sh(cmd):
    import subprocess
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=3).stdout
    except Exception:
        return ""


def detect_subnet(iface: str | None = None) -> tuple[str, str, str]:
    """Return (cidr, gateway_ip, iface) for the physical LAN, skipping VPN tunnels."""
    import platform
    import re

    if platform.system() == "Darwin":
        candidates = [iface] if iface else []
        if not iface:
            # Hardware ports in order: Wi-Fi first, then wired.
            ports = _sh(["networksetup", "-listallhardwareports"])
            devs = re.findall(r"Device:\s*(\S+)", ports)
            candidates = [d for d in devs if not d.startswith(TUNNEL_PREFIXES + VIRTUAL_PREFIXES)] or ["en0"]
        for dev in candidates:
            ip = _sh(["ipconfig", "getifaddr", dev]).strip()
            if not ip:
                continue
            mask = _sh(["ipconfig", "getoption", dev, "subnet_mask"]).strip() or "255.255.255.0"
            gw = _sh(["ipconfig", "getoption", dev, "router"]).strip()
            net = ipaddress.ip_interface(f"{ip}/{mask}").network
            if net.prefixlen < 22:  # don't sweep a huge range; narrow to the /24 around us
                net = ipaddress.ip_interface(ip + "/24").network
            return str(net), gw or str(net[1]), dev

    # Generic path (Linux/Windows): follow scapy's routing table to the physical LAN.
    try:
        from scapy.all import conf  # type: ignore
        skip = TUNNEL_PREFIXES + VIRTUAL_PREFIXES
        usable = lambda dev: dev and (dev == iface if iface else not str(dev).startswith(skip))
        routes = [r for r in conf.route.routes if usable(r[3])]
        defaults = [r for r in routes if r[0] == 0 and r[1] == 0]
        dev = iface or (defaults[0][3] if defaults else None)
        connected = []
        for net, mask, _gw, d, addr, *_ in routes:
            prefix = bin(mask).count("1")
            if d != dev and dev is not None:
                continue
            if not (8 <= prefix <= 30) or addr in ("0.0.0.0", "127.0.0.1"):
                continue
            network = ipaddress.ip_network(f"{ipaddress.IPv4Address(net)}/{prefix}", strict=False)
            if network.is_multicast or network.is_link_local:
                continue
            connected.append((prefix, network, d, addr))
        if connected:
            prefix, network, dev, addr = max(connected, key=lambda c: c[0])
            if prefix < 22:  # don't sweep a huge range; narrow to the /24 around us
                network = ipaddress.ip_interface(addr + "/24").network
            gw = next((r[2] for r in defaults if r[3] == dev), None)
            if not gw or ipaddress.ip_address(gw) not in network:
                gw = str(network[1])
            return str(network), gw, dev
    except Exception as e:
        print("netwatch: route detection failed, falling back:", e, file=sys.stderr)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    local_ip = s.getsockname()[0]
    s.close()
    net = ipaddress.ip_interface(local_ip + "/24").network
    return str(net), str(net[1]), iface or ""


async def refresh_vendors():
    loop = asyncio.get_running_loop()
    updated = await loop.run_in_executor(None, ensure_vendor_db)
    if not updated:
        return
    for d in table.devices.values():
        if d["vendor"] in ("Unknown", None) or d["vendor"] in OUI_MINI.values():
            v = vendor_for(d["mac"])
            if v != d["vendor"]:
                d["vendor"] = v
                await table.broadcast({"type": "updated", "device": d, "returned": False})


async def arp_scan_loop(cidr: str, iface: str | None = None):
    from scapy.all import ARP, Ether, srp  # type: ignore
    loop = asyncio.get_running_loop()
    asyncio.create_task(refresh_vendors())
    while True:
        t0 = time.time()
        try:
            ans, _ = await loop.run_in_executor(
                None,
                lambda: srp(Ether(dst="ff:ff:ff:ff:ff:ff") / ARP(pdst=cidr), timeout=2, verbose=0, iface=iface or None),
            )
            for sent, rcv in ans:
                latency = round((rcv.time - sent.sent_time) * 1000, 1) if getattr(sent, "sent_time", None) else None
                await table.observe(rcv.hwsrc.upper(), rcv.psrc, latency)
        except PermissionError:
            print("Need root/admin for raw sockets. Re-run with sudo, or use --demo.", file=sys.stderr)
            os._exit(1)
        except Exception as e:  # keep looping on transient errors
            print("scan error:", e, file=sys.stderr)
        table.scan_count += 1
        await table.age()
        await table.broadcast({"type": "scan", "n": table.scan_count, "took": round(time.time() - t0, 2)})
        await asyncio.sleep(SCAN_INTERVAL)


# ---------------------------------------------------------------- demo mode
DEMO = [
    ("A4:83:E7:11:22:01", "192.168.1.14", "macbook-pro"),
    ("F4:F5:D8:AA:BB:02", "192.168.1.22", "pixel-8"),
    ("F8:2F:A8:33:44:03", "192.168.1.30", "living-room-tv"),
    ("00:11:32:55:66:04", "192.168.1.10", "nas"),
    ("3C:52:82:77:88:05", "192.168.1.41", "printer"),
    ("F0:81:73:99:AA:06", "192.168.1.63", "echo-dot"),
    ("B8:27:EB:BB:CC:07", "192.168.1.70", "raspberrypi"),
    ("00:17:88:DD:EE:08", "192.168.1.80", "hue-bridge"),
    ("DC:A9:04:FF:00:09", "192.168.1.19", "iphone"),
    ("18:E8:29:12:34:0A", "192.168.1.2", "unifi-ap"),
    ("04:D3:B0:56:78:0B", "192.168.1.51", "thinkpad"),
]
DEMO_TRANSIENT = [
    ("24:6F:28:A1:C4:0C", "192.168.1.57", "esp32-a1c4"),
    ("3C:5A:B4:9F:00:0D", "192.168.1.88", "chromecast"),
    ("94:65:2D:00:11:0E", "192.168.1.93", None),
]


async def demo_loop():
    table.gateway_ip = "192.168.1.1"
    table.network_name = "Demo Wi-Fi"
    await table.observe("70:4F:57:00:00:01", "192.168.1.1", 1.2, "router")
    t = 0
    while True:
        for mac, ip, host in DEMO:
            if random.random() < 0.93:
                await table.observe(mac, ip, round(random.uniform(1, 18), 1), host)
        for mac, ip, host in DEMO_TRANSIENT:
            if random.random() < 0.35:
                await table.observe(mac, ip, round(random.uniform(3, 40), 1), host)
        table.scan_count += 1
        await table.age()
        await table.broadcast({"type": "scan", "n": table.scan_count, "took": round(random.uniform(1.1, 2.2), 2)})
        t += 1
        await asyncio.sleep(4)


# ---------------------------------------------------------------- web
app = FastAPI(title="netwatch")
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")


@app.get("/")
async def index():
    return FileResponse(HERE / "static" / "index.html")


@app.get("/api/devices")
async def api_devices():
    return table.snapshot()


@app.websocket("/ws")
async def ws(sock: WebSocket):
    await sock.accept()
    q: asyncio.Queue = asyncio.Queue(maxsize=200)
    table.listeners.add(q)
    try:
        await sock.send_text(json.dumps(table.snapshot()))
        while True:
            msg = await q.get()
            await sock.send_text(json.dumps(msg))
    except WebSocketDisconnect:
        pass
    finally:
        table.listeners.discard(q)


def main():
    ap = argparse.ArgumentParser()
    env = os.environ.get
    ap.add_argument("--demo", action="store_true", default=env("NETWATCH_DEMO", "").lower() in ("1", "true", "yes"),
                    help="simulate devices (no root needed)  [env NETWATCH_DEMO]")
    ap.add_argument("--host", default=env("NETWATCH_HOST", "127.0.0.1"),
                    help="address to serve on; 0.0.0.0 to reach it from other devices  [env NETWATCH_HOST]")
    ap.add_argument("--port", type=int, default=int(env("NETWATCH_PORT", "8008")),
                    help="dashboard port  [env NETWATCH_PORT]")
    ap.add_argument("--subnet", default=env("NETWATCH_SUBNET") or None,
                    help="CIDR to scan, e.g. 192.168.0.0/24 (auto-detected if omitted)  [env NETWATCH_SUBNET]")
    ap.add_argument("--iface", default=env("NETWATCH_IFACE") or None,
                    help="interface to scan on, e.g. en0 (auto-detected; skips VPN tunnels)  [env NETWATCH_IFACE]")
    args = ap.parse_args()

    import uvicorn
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(_app):
        if args.demo:
            print("netwatch: DEMO mode — simulated devices")
            task = asyncio.create_task(demo_loop())
        else:
            cidr, gw, iface = detect_subnet(args.iface)
            if args.subnet:
                cidr = args.subnet
            table.gateway_ip = gw
            table.network_name = detect_network_name(iface)
            print(f"netwatch: network {table.network_name or '?'} on {iface or 'default'} · scanning {cidr} (gateway {gw}) every {SCAN_INTERVAL}s")
            task = asyncio.create_task(arp_scan_loop(cidr, iface))
        yield
        task.cancel()

    app.router.lifespan_context = lifespan

    shown = "localhost" if args.host in ("127.0.0.1", "0.0.0.0") else args.host
    print(f"netwatch: open http://{shown}:{args.port}")
    if args.host == "0.0.0.0":
        print("netwatch: listening on all interfaces — reachable from other devices on this network")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
