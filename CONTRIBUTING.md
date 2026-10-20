# Contributing to Netwatch

Thanks for your interest. Netwatch is deliberately small: one Python file for discovery and one HTML file for the dashboard, with no build step. Please keep it that way where you can.

## Getting set up

```bash
git clone https://github.com/gipsbrian/netwatch.git
cd netwatch
make demo        # sets up .venv and runs with simulated devices
```

Demo mode feeds the dashboard simulated devices on a 4-second cycle, including devices that join, go stale and leave, so most front-end work needs no privileges. Test discovery changes with `make run` on a real network before opening a pull request. If you touch the `Dockerfile` or `docker-compose.yml`, also check `make docker-demo` and, on a Linux machine, `make up`.

`make help` lists every command.

## Reporting bugs

Open an issue with:

- your OS and version, and Python version
- the full startup line Netwatch prints (`netwatch: network … · scanning …`)
- whether you ran it natively or in Docker, and whether you were on a VPN
- what you expected vs. what you saw

For discovery problems, the output of `networksetup -listallhardwareports` (macOS), `ip addr` (Linux) or `ipconfig /all` (Windows) helps a lot.

## Pull requests

- One change per PR, with a short description of *why*.
- Keep the two-file layout: discovery and API in `server.py`, UI in `static/index.html`. New settings should work as a flag, a `make` variable and a `NETWATCH_*` environment variable, and be added to the configuration table in the README. New back-end modules are fine if they're clearly a separate concern (e.g. a passive sniffer).
- No new runtime dependencies without discussion. The front end stays dependency-free.
- Anything that touches the dark theme should still be readable at phone width; resize your browser before you push.
- Match the existing style: 4-space Python, no type-checking strictness required, short functions.

## Ideas that would be welcome

See the roadmap in the README. Passive discovery (ARP/mDNS sniffing) and mDNS hostnames are the two most useful next steps.

## License

By contributing you agree that your contributions are licensed under the MIT License.
