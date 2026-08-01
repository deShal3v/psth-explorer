#!/usr/bin/env bash
# Wait for cloudflared to print its quick-tunnel URL, then write it where the user can find it.
LOG=/tmp/nse_cf.log
OUT="$HOME/nse_tunnel_url.txt"
for _ in $(seq 1 40); do
  url=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG" 2>/dev/null | tail -1)
  if [ -n "$url" ]; then echo "$url" > "$OUT"; exit 0; fi
  sleep 1
done
exit 0
