# Netwatch

**A real-time, radar-style dashboard of every device on your local network.**

Netwatch sweeps your LAN with ARP every few seconds, streams the results to your browser over a WebSocket, and draws each device as a glowing node orbiting your router. Devices light up when they answer, fade to amber when they go quiet, and drop off when they leave. It runs entirely on your own machine; nothing is sent anywhere.

![Netwatch dashboard](docs/screenshot.png)

[![License: MIT](https://img.shields.io/badge/License-MIT-36f1ff.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-0fa6b8.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Windows-0c1526.svg)](#platform-notes)
[![Docker](https://img.shields.io/badge/docker-ghcr.io%2Fgipsbrian%2Fnetwatch-0fa6b8.svg)](#run-with-docker)

## Contents

- [Features](#features)
- [Quick start](#quick-start)
- [Which way should I run it?](#which-way-should-i-run-it)
- [Run natively](#run-natively)
- [Run with Docker](#run-with-docker)
- [Configuration](#configuration)
- [Platform notes](#platform-notes)
- [How it works](#how-it-works)
- [Troubleshooting](#troubleshooting)
- [Security](#security)
- [Roadmap](#roadmap) · [Contributing](#contributing) · [License](#license)

## Features

- **Live topology** — your gateway at the centre, every device on a ring around it. Each ARP reply sends a particle down the link and brightens the node.
- **Join / leave / return events** — a ticker logs every change with a timestamp; new devices flash in the table and carry a `NEW` badge for a minute.
- **Device detail** — IP, MAC, vendor (from the IEEE registry of ~35,000 manufacturers), hostname when available, round-trip latency, and last-seen time. Hover a node for a tooltip; click to pin it.
- **Status at a glance** — active, new-this-session, stale and median-latency tiles, plus your Wi-Fi name and subnet in the header.
- **VPN-aware** — scans your physical Wi-Fi or Ethernet interface and ignores VPN tunnels and Docker bridges, so it sees the room you're in, not the office you're tunnelled into.
- **Small and dependency-light** — one Python file, one HTML file, three Python packages. No Node, no bundler, no database.
- **Runs your way** — natively on macOS, Linux and Windows, or as a Docker container on a Raspberry Pi or home server. One-word `make` commands for both.
- **Demo mode** — simulated devices, so you can see it working before granting scan privileges.

## Quick start

You need Python 3.10+ and `make` (built into macOS and Linux).

```bash
git clone https://github.com/gipsbrian/netwatch.git
cd netwatch

make demo     # simulated devices, no password needed
make run      # scan your real network (asks for your password)
```

Open **http://localhost:8008**. The first `make` command sets up a virtual environment and installs the dependencies automatically; later runs start instantly.

When scanning for real, the terminal prints the network it picked, for example:

```
netwatch: network HomeWiFi on en0 · scanning 192.168.1.0/24 (gateway 192.168.1.1) every 10s
```

Devices appear after the first sweep, about 10 seconds in. Stop with **Ctrl+C**. Run `make help` to see every command.

## Which way should I run it?

| You want to… | On | Use |
|---|---|---|
| Check your network from your laptop | macOS, Linux, Windows | [Native](#run-natively): `make run` |
| Watch your network 24/7 from an always-on box | Raspberry Pi, Linux server, NAS | [Docker](#run-with-docker): `make up` |
| Just see what it looks like | anything | `make demo` or `make docker-demo` |

> **Docker on macOS or Windows can't scan your network.** Docker Desktop runs containers inside a hidden Linux virtual machine with its own private network, so ARP requests from the container never reach your real Wi-Fi. No setting changes this. On a Mac or Windows PC, run Netwatch natively. Docker is the right choice on Linux, where the container can share the host's network directly.

## Run natively

### With make

| Command | What it does |
|---|---|
| `make demo` | Run with simulated devices. No password needed |
| `make run` | Scan your real network. Uses `sudo`, so it asks for your password |
| `make run-lan` | Same as `run`, but the dashboard is reachable from other devices, e.g. your phone at `http://<your-computer's-IP>:8008` |
| `make open` | Open the dashboard in your browser |
| `make install` | Set up `.venv` and install dependencies (runs automatically before `demo` and `run`) |
| `make clean` | Delete the virtual environment |
| `make help` | List all commands |

Any [setting](#configuration) can be passed on the command line:

```bash
make run IFACE=en0                    # force a specific interface
make run SUBNET=192.168.0.0/24        # force the range to sweep
make demo PORT=9000                   # use a different port
```

### Without make

If you don't have `make` (for example on Windows without WSL), the equivalent commands are:

```bash
python3 -m venv .venv
source .venv/bin/activate             # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python server.py --demo               # simulated devices
sudo .venv/bin/python server.py       # real scan, macOS / Linux
python server.py                      # real scan, Windows (Administrator terminal, Npcap installed)
```

## Run with Docker

Docker is the best way to run Netwatch permanently on a **Linux** machine such as a Raspberry Pi, a home server or a NAS. It restarts automatically, survives reboots, and you can check it from any device on your network. (On macOS and Windows, [run natively](#run-natively) instead; see [why](#which-way-should-i-run-it).)

The container needs two things to see your network, both already set in `docker-compose.yml`:

- **`network_mode: host`** — shares the host's network card, so ARP broadcasts reach your LAN. Without it, the container is on Docker's private bridge network and finds nothing.
- **`cap_add: NET_RAW`** — permission to send raw ARP packets. (`NET_ADMIN` is also added so the interface can be read reliably.)

### With Docker Compose (recommended)

You need Docker Engine with the Compose plugin. On a Raspberry Pi: `curl -fsSL https://get.docker.com | sh`.

```bash
git clone https://github.com/gipsbrian/netwatch.git
cd netwatch
make up
```

That builds the image and starts it in the background. Open **http://localhost:8008** on the machine itself, or **http://\<machine-IP\>:8008** from your laptop or phone.

| Command | What it does |
|---|---|
| `make up` | Build the image and start Netwatch in the background |
| `make logs` | Follow the logs (Ctrl+C to stop following; Netwatch keeps running) |
| `make status` | Show whether it's running and healthy |
| `make restart` | Restart the container |
| `make down` | Stop and remove the container |
| `make docker-demo` | Run the image in the foreground with simulated devices. Works on any OS, including macOS |
| `make docker-clean` | Remove the container, the image and the cached vendor data |

Without `make`, the same thing is `docker compose up -d --build`, `docker compose logs -f`, `docker compose down`.

**To change settings**, copy the example file and edit it:

```bash
cp .env.example .env
nano .env          # e.g. set NETWATCH_IFACE=wlan0
make up            # recreates the container with the new settings
```

**To update** to the latest version:

```bash
git pull
make up
```

### With plain `docker run`

A ready-built image for both PCs (amd64) and Raspberry Pi (arm64) is published to GitHub's container registry, so you can run it without cloning the repository:

```bash
docker run -d \
  --name netwatch \
  --restart unless-stopped \
  --network host \
  --cap-add NET_RAW --cap-add NET_ADMIN \
  -v netwatch-cache:/root/.cache \
  ghcr.io/gipsbrian/netwatch:latest
```

Pass settings with `-e`, e.g. `-e NETWATCH_IFACE=wlan0 -e NETWATCH_PORT=9000`. Arguments after the image name go straight to the server, so `ghcr.io/gipsbrian/netwatch --demo` works too.

To build the image yourself instead: `make docker-build` (or `docker build -t netwatch .`).

### Notes for Docker

- **Port mapping is ignored with host networking.** The dashboard binds directly to the host on `NETWATCH_PORT` (default 8008). Change the port with that setting, not with `-p`.
- **Health check.** The image checks `/api/devices` every 30 seconds; `make status` shows `healthy` once the server is up.
- **Vendor data** is downloaded on first start and cached in the `netwatch-cache` volume, so restarts and updates don't download it again.
- **Wi-Fi name.** The container reads it with `iwgetid` when the host's Wi-Fi is managed by the kernel. On some systems it shows `wired (eth0)` or the interface name instead; scanning works either way.

## Configuration

Every setting can be given as a command-line flag (native), a `make` variable, or an environment variable (Docker, `.env`). Leave a setting out to use the default.

| Flag | `make` variable | Environment variable | Default | Purpose |
|---|---|---|---|---|
| `--demo` | — (`make demo`) | `NETWATCH_DEMO=1` | off | Simulated devices, no root needed |
| `--host ADDR` | `HOST` | `NETWATCH_HOST` | `127.0.0.1` natively, `0.0.0.0` in Docker | Address the dashboard listens on. `0.0.0.0` makes it reachable from other devices |
| `--port N` | `PORT` | `NETWATCH_PORT` | `8008` | Dashboard port |
| `--iface NAME` | `IFACE` | `NETWATCH_IFACE` | auto | Interface to scan on, e.g. `en0`, `eth0`, `wlan0` |
| `--subnet CIDR` | `SUBNET` | `NETWATCH_SUBNET` | auto | Range to sweep, e.g. `192.168.0.0/24` |
| — | — | `NETWATCH_CACHE_DIR` | `~/.cache/netwatch` | Where the vendor database is cached |

**Auto-detection** picks the interface your internet traffic normally leaves through, skipping VPN tunnels (`utun`, `tun`, `wg`, Tailscale…) and virtual bridges (`docker0`, `br-…`, `veth…`). It sweeps that interface's subnet, narrowed to a /24 if the network is larger, so a sweep stays fast.

**Timing** constants live at the top of `server.py`:

| Constant | Default | Meaning |
|---|---|---|
| `SCAN_INTERVAL` | 10 s | Seconds between ARP sweeps |
| `STALE_AFTER` | 45 s | No reply for this long → shown as stale (amber, outer ring) |
| `GONE_AFTER` | 180 s | No reply for this long → removed |

**Vendor names.** On first start Netwatch downloads the IEEE manufacturer registry (falling back to Wireshark's copy), tidies the names ("Samsung Electronics Co.,Ltd" → "Samsung Electronics") and caches the result. If neither source is reachable it uses a small built-in table and tries again on the next start. Modern phones and laptops often use a **randomised MAC address** for privacy; these can't be traced to a manufacturer, so Netwatch labels them "Private address" and shows the device by its IP.

## Platform notes

**macOS** — Works on macOS 12 and later. `make run` uses `sudo`. The Wi-Fi name is read with `ipconfig getsummary` (the old `airport` tool was removed in macOS 14). Interface detection reads macOS's own hardware-port list, so it finds Wi-Fi even while a VPN is connected.

**Linux** — `make run` uses `sudo`. To avoid `sudo`, you can grant raw-packet permission to the Python interpreter once with `sudo setcap cap_net_raw,cap_net_admin+eip "$(readlink -f .venv/bin/python)"` and then start Netwatch with `.venv/bin/python server.py`. This applies to every program using that Python binary, so only do it on a machine you control. The Wi-Fi name comes from `iwgetid` or `nmcli` if installed.

**Windows** — Install [Npcap](https://npcap.com) and tick *WinPcap API-compatible mode*. Run from an Administrator terminal with `python server.py`, or use WSL2 with `make`. Note that WSL2 has its own virtual network, like Docker Desktop, so a scan from inside WSL2 sees only WSL; run natively on Windows for real results. The Wi-Fi name comes from `netsh wlan show interfaces`.

## How it works

```
┌────────────┐   ARP who-has     ┌────────────┐
│ server.py  │ ───────────────▶  │   LAN      │
│  scapy     │ ◀───────────────  │  devices   │
└─────┬──────┘   ARP is-at       └────────────┘
      │ joined / updated / left (JSON over WebSocket)
      ▼
┌────────────┐
│ index.html │  canvas topology · device table · event ticker
└────────────┘
```

1. **Discovery** — `arp_scan_loop` broadcasts an ARP request to every address in the subnet using [scapy](https://scapy.net) and records each reply: MAC, IP and round-trip time. ARP works below IP, so it finds devices that ignore ping.
2. **Enrichment** — each new MAC is matched against the cached IEEE registry and reverse DNS is tried for a hostname.
3. **State** — `DeviceTable` keeps every device in memory, ages them into *stale* and then *gone*, and broadcasts each change (`joined`, `updated`, `left`, `scan`) to every connected browser. Nothing is stored between runs.
4. **Rendering** — `static/index.html` mirrors the table, places nodes on a ring ordered by IP so they never jostle, and animates the glow, particles and radar sweep on a `<canvas>`. If the page can't reach a server it falls back to a built-in simulation.

### Project layout

```
netwatch/
├── server.py              discovery, device state, web server
├── static/index.html      the dashboard (HTML, CSS and JS in one file)
├── requirements.txt       fastapi, uvicorn, scapy
├── Makefile               make demo / run / up / down / …
├── Dockerfile             container image
├── docker-compose.yml     host networking + NET_RAW, ready to `make up`
├── .env.example           settings for Docker
└── .github/workflows/     builds and publishes the Docker image
```

### API

| Endpoint | Description |
|---|---|
| `GET /` | The dashboard |
| `GET /api/devices` | JSON snapshot: `{gateway, network, scan, devices: [...]}` |
| `WS /ws` | Snapshot on connect, then a stream of `joined` / `updated` / `left` / `scan` events |

A device looks like:

```json
{
  "mac": "A4:83:E7:11:22:01",
  "ip": "192.168.1.14",
  "hostname": "macbook-pro",
  "vendor": "Apple",
  "first_seen": 1792525595.98,
  "last_seen": 1792525599.98,
  "latency": 10.3,
  "status": "active",
  "is_gateway": false,
  "history": [11.8, 10.3]
}
```

## Troubleshooting

**Nothing appears and the subnet shown is `10.8.x.x`, `100.x.x.x` or similar** — that's a VPN or Tailscale range. Auto-detection should skip it; if it doesn't, name your interface: `make run IFACE=en0` (macOS Wi-Fi) or `make run IFACE=wlan0` (Linux). `networksetup -listallhardwareports` (macOS) or `ip -br addr` (Linux) lists your interfaces.

**Only the router shows up** — your network has *client isolation* on, which is common on guest, hotel and office Wi-Fi. Devices can't see each other, so there's nothing to discover. Or, if you're using Docker on macOS or Windows, see [why that can't work](#which-way-should-i-run-it).

**Docker: no devices on Linux** — check the container is on the host network: `docker inspect netwatch --format '{{.HostConfig.NetworkMode}}'` should print `host`. Then check `make logs` for the interface and subnet it chose, and set `NETWATCH_IFACE` in `.env` if it's wrong.

**Docker: "Operation not permitted"** — the container is missing `NET_RAW`. Use `make up` or add `--cap-add NET_RAW --cap-add NET_ADMIN` to `docker run`.

**Phones keep flickering to stale** — phones sleep their Wi-Fi radio and sometimes miss a sweep. Raise `STALE_AFTER` to 90 in `server.py`.

**Many devices say "Private address"** — those devices use randomised MAC addresses (the default on iPhone, Android and Windows 11). That's expected; the manufacturer can't be known. You can turn it off per network on the device if you want it identifiable.

**Vendors stay "Unknown" for real manufacturers** — the registry download failed on first start. Check the startup log for `couldn't fetch`, make sure the machine has internet access, and restart; it retries every time.

**`PermissionError` / "Operation not permitted" (native)** — ARP needs raw sockets. Use `make run`, which uses `sudo`, or see the `setcap` tip under [Platform notes](#platform-notes).

**Port 8008 is already in use** — pick another: `make run PORT=9000`, or `NETWATCH_PORT=9000` in `.env`.

## Security

- Netwatch only **sends ARP requests and reverse-DNS lookups** on your local network. It doesn't probe ports, log in to anything, or send data outside your network, apart from the one-time vendor download.
- The dashboard has **no login**. By default it listens only on `127.0.0.1`, so only your own computer can open it. `make run-lan` and the Docker setup listen on all interfaces so your other devices can reach it; anyone on the same network can then view the device list. Don't expose port 8008 to the internet.
- Scanning needs elevated privileges. Natively that's `sudo`; in Docker it's the `NET_RAW` capability and host networking. Only scan networks you own or have permission to monitor.

## Roadmap

- Passive mode: listen for ARP, DHCP and mDNS so devices appear the instant they connect
- mDNS/Bonjour hostnames ("Brian's iPhone" instead of an IP address)
- History in SQLite with a "seen in the last 24 hours" view
- Notifications or a webhook when an unknown device joins
- Per-device nicknames and icons
- Optional password for the dashboard when it's shared on the network

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, how to report bugs, and pull request guidelines.

## License

[MIT](LICENSE) © 2026 gipsbrian
