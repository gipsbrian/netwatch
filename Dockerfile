# Netwatch — live LAN device dashboard
#
# Linux hosts only for real scanning: the container must share the host's
# network stack (--network host) and hold the NET_RAW capability to send ARP.
# On macOS/Windows Docker Desktop, only --demo mode is useful; see README.

FROM python:3.12-slim

LABEL org.opencontainers.image.title="netwatch" \
      org.opencontainers.image.description="Real-time radar-style dashboard of every device on your local network" \
      org.opencontainers.image.source="https://github.com/gipsbrian/netwatch" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    NETWATCH_HOST=0.0.0.0 \
    NETWATCH_PORT=8008

WORKDIR /app

# iproute2 lets scapy read the routing table; wireless-tools provides iwgetid for the Wi-Fi name.
RUN apt-get update \
 && apt-get install -y --no-install-recommends iproute2 wireless-tools \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY server.py .
COPY static ./static

# Vendor database (~2 MB) is downloaded on first run and cached here; mount a volume to keep it.
VOLUME ["/root/.cache"]

EXPOSE 8008

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"NETWATCH_PORT\",\"8008\")}/api/devices', timeout=2)" || exit 1

ENTRYPOINT ["python", "server.py"]
