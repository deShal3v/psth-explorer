# Notes for coding agents

Two things about this repo are easy to get wrong: the app has no backend, and the
data is a headerless binary blob that only makes sense next to `data/manifest.json`.

## Getting it running

```bash
./setup.sh
```

That downloads the prebuilt cubes (about 15 MB) and serves on port 8099.

A fresh clone has no `data/` and no `index.html`. Both are generated and both are
gitignored, so the page stays blank until `setup.sh` has run.

## No backend

There is no API and no database. `tools/serve_gz.py` is a 40-line static file
server. The app itself is `index.dc.html`, which holds the markup and all of the
logic in a `<script type="text/x-dc">` block, plus `support.js`, the runtime it
boots from a React CDN.

On load it makes two fetches per participant:

```js
fetch('data/manifest.json')            // ~28 KB of metadata
fetch('data/' + user.dataFile)         // the whole cube, e.g. sess_t5.u8
  .then(r => r.arrayBuffer())
  .then(buf => { this.CUBE = new Uint8Array(buf) })
```

The cube then sits in browser memory as one flat `Uint8Array`. Every PSTH, gaussian
smooth, z-score, integral, differential, band-pass and array heatmap is computed in
JS by indexing into it. Nothing is fetched per trial or per electrode, so adding an
analysis means writing more JS rather than adding an endpoint.

## The .u8 format

`data/sess_<uid>.u8` is a `(nCond, nTrials, nBins, nCh)` uint8 array in C order.
The file has no header or magic bytes, and the values are unscaled: each byte is the
threshold-crossing count for one electrode in one time bin, which fits in a uint8 at
these bin widths.

```
offset(cond, trial, bin, ch) = ((cond * nTrials + trial) * nBins + bin) * nCh + ch
rate_Hz                      = count * 1000 / binMs
```

Every one of those dimensions comes from the manifest, so the file is unreadable
without it. The five participants differ in all of them:

| field | T5 | T12 | T15 | T16 | T17 |
|---|---|---|---|---|---|
| `nCond` x `nTrials` | 32 x 27 | 8 x 21 | 8 x 20 | 8 x 14 | 8 x 20 |
| `nBins`, `binMs` | 500, 10 | 350, 20 | 700, 10 | 700, 10 | 700, 10 |
| `goBin` | 300 | 150 | 300 | 300 | 300 |
| `nCh` | 192 | 128 | 256 | 256 | 256 |
| arrays | 2 | 2 | 4 | 4 | 4 |
| `geoRows/Cols` | 10x10 | 8x8 | 8x8 | 8x8 | 8x8 |

As a check: 32 * 27 * 500 * 192 = 82,944,000 bytes, the exact size of `sess_t5.u8`.
Never assume T5's numbers; read them from the manifest for the user you are on.

The manifest also carries `delayBins` and `nextCueBins` (per-trial cue onsets, which
drive the per-sweep cue-to-cue epochs), `zMean` and `zStd` (per channel, precomputed
over the whole session), `order` (acquisition order, for session playback), `rest`
(a continuous no-cue segment stored in its own `rest_<uid>.u8`), and `conditions[]`.

## Things that will bite you

Serve with `tools/serve_gz.py`, not `python3 -m http.server`. Only the `.u8.gz`
sidecars are distributed; the raw `.u8` is gitignored and absent from the release
tarball. `serve_gz.py` answers a request for `foo.u8` with the contents of
`foo.u8.gz` under a `Content-Encoding: gzip` header, and the browser inflates it
transparently (83 MB becomes 12 MB on the wire). A generic static server returns 404
for `.u8` and the app renders blank.

`index.html` is generated. It is a copy of `index.dc.html` made by `setup.sh` and
`tools/serve_site.sh`, so edit `index.dc.html`; anything written to `index.html` is
overwritten on the next start.

In `.gitignore`, keep comments on their own lines. An inline `# ...` after a pattern
becomes part of the pattern and the rule silently stops matching.

Kunz electrode geometry is 8x8 row-major and spatially approximate. That dataset ships
no wiring map, so the heatmap layout is not true cortical adjacency.

Every array panel is 64 channels, which is a display convention rather than something
the source data states. The app gives all arrays one shared `geo` and computes
channels-per-array as `nCh / arrays.length`, so arrays have to be equal sized. Most
`chanSets` in the Kunz files are already 64 wide, but T16's `6d` and T17's `55b` are
128, and `kunz_arrays()` in the builder splits those into `6d-1` / `6d-2` and
`55b-1` / `55b-2`. The split point is arbitrary within the anatomical set. Supporting
genuinely unequal arrays would mean making `geo` per-array in the manifest and
dropping the `nCh / arrays.length` shortcut.

Participant switching tears down state: `loadUser` sets `CUBE`, `gridData` and the
caches to null while the new cube downloads, and channel indices do not survive the
switch (256-channel participants to a 128-channel one). Anything reading `gridData`
or indexing by channel during a render needs a null and range guard; `drawFrame` and
the hover tooltip both have one.

`tools/build_site_data.py` needs the raw `.mat` files, which are not in the repo or
the release. You only need it to add sessions; `setup.sh` covers everything else.
Point `NSE_RAW` at the unpacked datasets and `NSE_OUT` at the output directory.

## Layout

| path | what |
|---|---|
| `setup.sh` | fetch data and serve; `--from-raw` rebuilds instead of downloading |
| `index.dc.html` | the app: markup and logic |
| `support.js` | runtime the app boots itself from |
| `data/` | generated; manifest and `.u8.gz` cubes, from the release tarball |
| `tools/build_site_data.py` | rebuilds `data/` from the raw `.mat` sources |
| `tools/serve_gz.py` | static server with gzip sidecar support |
| `tools/verify_users.js` | headless check that every participant loads and draws |
| `tools/serve_site.sh` | local server plus a Cloudflare quick tunnel (ephemeral URL) |
| `deploy/*.service` | systemd user units for an always-up deployment |
