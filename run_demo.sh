#!/usr/bin/env bash
# Run heatbot's live demo on Linux or macOS: both villages, the read-only public
# gateway, and (if available) a temporary public Cloudflare Quick Tunnel.
#
#   ./run_demo.sh            # local only:  http://127.0.0.1:8780
#   ./run_demo.sh --public   # also prints a public https://….trycloudflare.com link
#
# Ctrl+C stops everything. The public link changes every time it's started.
set -u
cd "$(dirname "$0")"
mkdir -p tools
PY=${PYTHON:-python3}
pids=()
for port in 8765 8766 8780; do
  if "$PY" -c "import socket,sys; s=socket.socket(); sys.exit(0 if s.connect_ex(('127.0.0.1',$port)) else 1)"; then :; else
    echo "Port $port is already in use: an earlier demo may still be running."
    echo "Stop it first:  pkill -f 'live_server|demo_server|cloudflared'"
    exit 1
  fi
done
stop() { echo; echo "Stopping…"; kill "${pids[@]}" 2>/dev/null; wait 2>/dev/null; exit 0; }
trap stop INT TERM

"$PY" live_server.py              > tools/main.log      2>&1 & pids+=($!)
"$PY" live_server.py --open-chat  > tools/open-chat.log 2>&1 & pids+=($!)
"$PY" demo_server.py              > tools/demo.log      2>&1 & pids+=($!)
sleep 2
echo "Main village viewer (private):  http://127.0.0.1:8765"
echo "Open Chat viewer   (private):   http://127.0.0.1:8766"
echo "Read-only demo     (shareable): http://127.0.0.1:8780   (Open Chat at /open-chat/)"
echo "First data appears after the first poll (a minute or two). Logs: tools/*.log"

if [[ "${1:-}" == "--public" ]]; then
  CF=$(command -v cloudflared || true)
  [[ -z "$CF" && -x tools/cloudflared ]] && CF=tools/cloudflared
  if [[ -z "$CF" ]]; then
    case "$(uname -s)-$(uname -m)" in
      Linux-x86_64)  asset=cloudflared-linux-amd64 ;;
      Linux-aarch64) asset=cloudflared-linux-arm64 ;;
      *) echo "Install cloudflared (https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/) and rerun."; asset="" ;;
    esac
    if [[ -n "$asset" ]]; then
      echo "Downloading cloudflared (official Cloudflare release) into tools/…"
      curl -fsSL -o tools/cloudflared "https://github.com/cloudflare/cloudflared/releases/latest/download/$asset" \
        && chmod +x tools/cloudflared && CF=tools/cloudflared
    fi
  fi
  if [[ -n "$CF" ]]; then
    "$CF" tunnel --no-autoupdate --url http://127.0.0.1:8780 > tools/tunnel.log 2>&1 & pids+=($!)
    for _ in $(seq 1 30); do
      url=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' tools/tunnel.log | head -1)
      [[ -n "$url" ]] && break; sleep 1
    done
    if [[ -n "${url:-}" ]]; then
      echo "$url" > tools/demo-url.txt
      echo; echo "PUBLIC read-only demo: $url"
      echo "Anyone with this link can view the dashboard (no setup pages, no writes)."
    else
      echo "Tunnel didn't report an address; see tools/tunnel.log"
    fi
  fi
fi
echo; echo "Running. Press Ctrl+C to stop."
wait
