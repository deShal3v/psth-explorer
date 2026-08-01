#!/usr/bin/env bash
# Serve the Neural Spiking Explorer and expose it via a Cloudflare quick tunnel.
# Prints the public https URL (reachable from anywhere). Ctrl-C stops both.
# Note: quick-tunnel URLs are ephemeral. For an always-up service see deploy/.
set -euo pipefail
SITE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${1:-8099}"
CF="${CLOUDFLARED:-$HOME/.local/bin/cloudflared}"

[ -f "$SITE/data/manifest.json" ] || { echo "no data/ yet — run ./setup.sh first" >&2; exit 1; }

# refresh the servable copy from the design source of truth
cp "$SITE/index.dc.html" "$SITE/index.html"

# static file server (threaded, gzip sidecars) in background
python3 "$SITE/tools/serve_gz.py" "$PORT" "$SITE" >/tmp/nse_httpd.log 2>&1 &
HTTPD=$!
trap 'kill $HTTPD 2>/dev/null || true' EXIT

echo "Local:  http://127.0.0.1:$PORT/"
[ -x "$CF" ] || { echo "cloudflared not found at $CF — serving locally only."; wait $HTTPD; }

echo "Opening Cloudflare tunnel (public URL below, may take ~10s)..."
"$CF" tunnel --url "http://127.0.0.1:$PORT" --no-autoupdate 2>&1 \
  | grep --line-buffered -E 'trycloudflare\.com|ERR|Registered tunnel'
