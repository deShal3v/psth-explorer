# Neural Spiking Explorer

A browser tool for looking at intracortical microelectrode-array recordings: array
heatmaps that play as movies, stacked PSTHs, per-sweep cue-to-cue timing,
session-order playback, rest periods, z-scoring, an array-mean trace, and a 3-10 s
band-pass for slow waves.

Live at **<https://psth.io>**.

## Which participants and sessions

Five participants, switchable from the avatar in the top bar. One session per
participant, named exactly as it is in the source dataset.

| participant | source | session | task | channels | arrays | conditions | sweeps | bins |
|---|---|---|---|---|---|---|---|---|
| T5 | Willett 2021 | `t5.2019.05.08` | handwriting, single letters | 192 | 2 | 32 characters | 27 | 10 ms |
| T12 | Kunz 2025 | `t12.2023.08.15` | attempted speech | 128 | 2 | 7 words + `DO_NOTHING` | 21 | 20 ms |
| T15 | Kunz 2025 | `t15.2024.04.07` | attempted speech | 256 | 4 | 7 words + `DO_NOTHING` | 20 | 10 ms |
| T16 | Kunz 2025 | `t16.2024.03.04` | attempted speech | 256 | 4 | 7 words + `DO_NOTHING` | 14 | 10 ms |
| T17 | Kunz 2025 | `t17.2024.12.09` | attempted speech | 256 | 4 | 7 words + `DO_NOTHING` | 20 | 10 ms |

The seven words are ban, choice, day, feel, kite, though and were, plus a do-nothing
rest condition.

T5 is the first session of the Willett handwriting dataset. The four speech
participants come from the Kunz isolated verbal behaviors task, which recorded seven
behaviors per participant; the `attempted` blocks are the ones shown here. The other
six (mouthed, imagined motoric, imagined auditory, imagined listening, passive
listening, silent reading) are a one-word change in `tools/build_site_data.py`.

## Run it

```bash
git clone https://github.com/deShal3v/neural-spiking-explorer.git
cd neural-spiking-explorer
./setup.sh
```

This downloads the prebuilt data (about 25 MB for all five participants) and serves on
<http://127.0.0.1:8099>. The data lives in a GitHub Release rather than in git history.
`./setup.sh --help` lists the other flags: `--no-serve`, `--port`, `--from-raw`.

## Hosting

The public site runs on Cloudflare Pages, so nothing is served from a personal
machine. Deploying is a direct upload of the site directory after `setup.sh` has
populated `data/`:

```bash
export CLOUDFLARE_API_TOKEN=...  CLOUDFLARE_ACCOUNT_ID=...
npx wrangler pages deploy . --project-name=psth --commit-dirty=true
```

`_headers` sets the caching rules Pages applies: the cubes are immutable and cache for
a year, while `index.html` and `support.js` must not cache or a deploy appears to do
nothing. Because Pages has no `serve_gz.py`, the app requests the `.u8.gz` file
directly and inflates it with `DecompressionStream`, falling back to the plain `.u8`
if a host has already decompressed it.

To run a public URL off your own machine instead, `bash tools/serve_site.sh` adds a
Cloudflare quick tunnel, though the URL it prints changes on every restart. The
systemd user units in `deploy/` are the always-up version of that:

```bash
cp deploy/nse-web.service deploy/nse-tunnel.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now nse-web.service nse-tunnel.service
cat ~/nse_tunnel_url.txt           # current public URL
```

## Analytics

Traffic (pageviews, referrers, countries, devices) comes from Cloudflare Web
Analytics, which is enabled on the Pages project in the dashboard and needs no code
in this repo.

In-app behavior is separate, because Web Analytics only counts pageviews. `track()`
in `index.dc.html` emits an event when someone loads the page, switches participant,
switches array, picks a condition, changes view mode, or hits play.
`deploy/analytics-worker.js` is a Cloudflare Worker that receives those and writes to
Analytics Engine, which you then query with SQL. It is off until you set the
collector URL:

```bash
cd deploy && npx wrangler deploy       # prints the workers.dev URL
# then in index.dc.html: window.NSE_ANALYTICS_URL = "https://nse-analytics.<sub>.workers.dev"
```

No cookies and no stored IP addresses. Events carry a random per-tab id that is lost
when the tab closes, which distinguishes one visit's actions without identifying a
person. Country is added at the Cloudflare edge. If you need to attribute activity to
named individuals, that is a different system and a different privacy conversation.

## How it works

It is a static site with no backend. The browser fetches `data/manifest.json`, then
one uint8 cube per participant, keeps it in memory as a single `Uint8Array`, and
computes every PSTH, z-score and band-pass client-side. `tools/serve_gz.py` serves
`data/*.u8` from a gzipped sidecar, which takes the T5 cube from 83 MB to 12 MB on
the wire, so only the `.gz` is ever distributed.

`AGENTS.md` documents the binary layout and the manifest fields, along with the
places this repo behaves unexpectedly. Read it before changing anything.

## Data and provenance

Both source datasets are on Dryad under CC0-1.0:

| participant | dataset | DOI |
|---|---|---|
| T5 | Willett et al. 2021, *High-performance brain-to-text communication via handwriting* | [10.5061/dryad.wh70rxwmv](https://doi.org/10.5061/dryad.wh70rxwmv) |
| T12 | Kunz et al. 2025, *Inner speech in motor cortex and implications for speech neuroprostheses* | [10.5061/dryad.gf1vhhn1j](https://doi.org/10.5061/dryad.gf1vhhn1j) |

What ships here is derived, not raw: threshold-crossing counts quantized to one byte
per electrode per bin, cut into go-aligned windows. If you use this data in your own
work, cite the papers above rather than this repo. The sha256 of the release tarball
is in `data.sha256` and `setup.sh` checks it, so you can confirm you have the same
bytes the site was built from.

## Rebuilding from raw

You only need this to add sessions or to switch which Kunz behavior is shown. The
builder reads five files:

```
handwritingBCIData/Datasets/t5.2019.05.08/singleLetters.mat                            (13.7 MB)
kunz/isolatedVerbalBehaviors/isolatedVerbalBehaviors/t12.2023.08.15_attempted_raw.mat  (24.2 MB)
kunz/isolatedVerbalBehaviors/isolatedVerbalBehaviors/t15.2024.04.07_attempted_raw.mat  (89.7 MB)
kunz/isolatedVerbalBehaviors/isolatedVerbalBehaviors/t16.2024.03.04_attempted_raw.mat  (72.7 MB)
kunz/isolatedVerbalBehaviors/isolatedVerbalBehaviors/t17.2024.12.09_attempted_raw.mat  (85.0 MB)
```

None of them is separately downloadable. Dryad ships the handwriting data as a single
1.41 GB `handwritingBCIData.tar.gz`, and all four speech files live inside a 3.53 GB
`isolatedVerbalBehaviors.zip`, so reproducing the cubes means pulling about 4.9 GB by
hand from the two DOIs above. Downloads go through a browser check, which is why
`setup.sh` does not try to automate them.

Once both archives are unpacked under one directory:

```bash
export NSE_RAW=/path/to/datasets     # containing handwritingBCIData/ and kunz/
pip install numpy scipy
./setup.sh --from-raw
```

## Files

| path | what |
|---|---|
| `setup.sh` | fetch data and serve; `--from-raw` rebuilds instead |
| `AGENTS.md` | data format, architecture, gotchas (`CLAUDE.md` imports it) |
| `index.dc.html` | the app: markup and logic; `support.js` is the runtime it boots |
| `index.html` | generated copy that the server serves (gitignored) |
| `data/manifest.json` | geometry, conditions, acquisition order, per-trial cue bins, z params |
| `data/sess_*.u8.gz` | trial cube `(nCond, nTrials, nBins, nCh)` of uint8 counts |
| `data/rest_*.u8.gz` | continuous no-cue rest segment from the raw time series |
| `tools/build_site_data.py` | rebuilds `data/` from the raw `.mat` sources |
| `tools/serve_gz.py` | threaded static server with gzip sidecars |
| `tools/verify_users.js` | headless check that every participant loads and draws |
| `_headers` | Cloudflare Pages caching and security headers |
| `deploy/analytics-worker.js` | Worker collecting in-app events into Analytics Engine |
| `deploy/wrangler.toml` | Worker config and the Analytics Engine binding |
| `deploy/*.service` | systemd user units for self-hosting |
