# macOS launchd Service

This project includes launchd automation for running the app on boot and exposing it to your local LAN.

## Files
- `launchd/control.sh`
- `launchd/com.jay.bs-user-summary.plist.template`

## Install
```bash
./launchd/control.sh install
```

What install does:
1. Renders plist from template to `~/Library/LaunchAgents/com.jay.bs-user-summary.plist`
2. Creates log files under `logs/`
3. Bootstraps and starts the launchd service

Default command run by launchd:
```bash
python3 -m backend.server --host 0.0.0.0 --port 8080
```

The install command enforces Python 3.11+.

## Control Commands
```bash
./launchd/control.sh start
./launchd/control.sh stop
./launchd/control.sh restart
./launchd/control.sh status
./launchd/control.sh logs
./launchd/control.sh uninstall
```

## Environment Overrides
Set these before running `install`:
- `BS_APP_HOST` default `0.0.0.0`
- `BS_APP_PORT` default `8080`
- `PYTHON_BIN` default current `python3` from shell `PATH` (must be 3.11+)

Example:
```bash
BS_APP_PORT=8090 ./launchd/control.sh install
```

## LAN Access
After service starts, open from another device on your network:
- `http://<your-mac-lan-ip>:<port>`

Find IP on macOS:
```bash
ipconfig getifaddr en0
```
