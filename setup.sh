#!/usr/bin/env bash
# Neural Spiking Explorer — one-command setup.
#
#   ./setup.sh              fetch the prebuilt cubes (~15 MB) and serve on :8099
#   ./setup.sh --no-serve   fetch only
#   ./setup.sh --from-raw   rebuild the cubes from the source .mat files instead
#   ./setup.sh --port 9000  serve on another port
#
# The app is a static site with no backend: the browser downloads one uint8 cube
# per participant and does every PSTH / z-score / band-pass in JS. All this script
# has to do is put that cube in data/ and start a file server.
set -euo pipefail

SITE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="${NSE_REPO:-deShal3v/psth-explorer}"
TAG="${NSE_DATA_TAG:-data-v1}"
ASSET="nse-data.tar.gz"
PORT=8099
SERVE=1
FROM_RAW=0

while [ $# -gt 0 ]; do
  case "$1" in
    --no-serve) SERVE=0 ;;
    --from-raw) FROM_RAW=1 ;;
    --port) PORT="$2"; shift ;;
    -h|--help) sed -n '2,9p' "$0" | sed 's/^# \?//'; exit 0 ;;
    *) echo "unknown option: $1 (try --help)" >&2; exit 2 ;;
  esac
  shift
done

say() { printf '\033[36m==>\033[0m %s\n' "$*"; }

# ---------- data ----------
if [ "$FROM_RAW" = 1 ]; then
  say "rebuilding cubes from raw .mat files"
  if [ -z "${NSE_RAW:-}" ]; then
    cat >&2 <<'MSG'
NSE_RAW is not set. Point it at a directory holding both unpacked datasets:

  handwritingBCIData/Datasets/t5.2019.05.08/singleLetters.mat
  kunz/isolatedVerbalBehaviors/isolatedVerbalBehaviors/t12.2023.08.15_attempted_raw.mat

Both are CC0 on Dryad, but neither file is separately downloadable -- the first
ships inside a 1.41 GB tar.gz and the second inside a 3.53 GB zip, and Dryad puts a
browser check in front of downloads, so fetch them by hand:

  T5   https://doi.org/10.5061/dryad.wh70rxwmv   handwritingBCIData.tar.gz
  T12  https://doi.org/10.5061/dryad.gf1vhhn1j   isolatedVerbalBehaviors.zip

Unless you are adding sessions, plain ./setup.sh downloads the same cubes as a
15 MB checksummed tarball.
MSG
    exit 1
  fi
  python3 -c 'import numpy, scipy' 2>/dev/null \
    || { echo "--from-raw needs numpy and scipy: pip install numpy scipy" >&2; exit 1; }
  NSE_RAW="$NSE_RAW" NSE_OUT="$SITE/data" python3 "$SITE/tools/build_site_data.py"
elif [ -f "$SITE/data/manifest.json" ]; then
  say "data/ already populated — skipping download (delete data/ to refetch)"
else
  say "fetching prebuilt data $TAG/$ASSET (~25 MB, 5 participants)"
  mkdir -p "$SITE/data"
  tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
  # The repo is private, so the release asset needs an authenticated fetch; gh handles
  # that. Plain curl is the fallback for when/if the repo is made public.
  if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
    gh release download "$TAG" --repo "$REPO" --pattern "$ASSET" --dir "$tmp"
  else
    say "gh not available/authed — trying unauthenticated download"
    curl -fL --progress-bar -o "$tmp/$ASSET" \
      "https://github.com/$REPO/releases/download/$TAG/$ASSET" \
      || { echo "download failed. This repo is private: install the GitHub CLI and run 'gh auth login', or build with --from-raw." >&2; exit 1; }
  fi
  if [ -f "$SITE/data.sha256" ]; then
    (cd "$tmp" && sha256sum -c <(grep "$ASSET" "$SITE/data.sha256")) \
      || { echo "checksum mismatch — refusing to unpack" >&2; exit 1; }
    say "checksum ok"
  fi
  tar -xzf "$tmp/$ASSET" -C "$SITE/data"
fi

# sanity: the app fetches data/<dataFile> for each user in the manifest
python3 - "$SITE" <<'PY'
import json, os, sys
site = sys.argv[1]
mf = json.load(open(os.path.join(site, "data", "manifest.json")))
missing = []
for u in mf["users"]:
    for f in [u["dataFile"]] + ([u["rest"]["file"]] if u.get("rest") else []):
        # serve_gz.py ships the .gz sidecar as Content-Encoding: gzip, so only it need exist
        if not os.path.isfile(os.path.join(site, "data", f + ".gz")):
            missing.append(f + ".gz")
    print(f"  {u['id']:5} {u['label']:22} {u['nCh']:3} ch  {len(u['conditions']):2} conditions  {u['binMs']} ms bins")
if missing:
    sys.exit("missing data files: " + ", ".join(missing))
PY

# ---------- the served copy of the app ----------
# index.html is generated from the design source and is gitignored, so a fresh
# clone has none until this runs.
cp "$SITE/index.dc.html" "$SITE/index.html"

say "ready"
[ "$SERVE" = 1 ] || exit 0

say "serving http://127.0.0.1:$PORT/  (Ctrl-C to stop)"
exec python3 "$SITE/tools/serve_gz.py" "$PORT" "$SITE"
