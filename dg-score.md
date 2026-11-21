# dg-score: building course packs with `dg_course_pack.py`

[`dg-score.html`](dg-score.html) is an offline disc golf scoring app with a flat map and a 3D view. It draws a course from a **course pack**, a single `.dgpack` file. [`python/dg_course_pack.py`](python/dg_course_pack.py) builds that file. Run it once on a computer with internet access. After that the app works with no signal.

## What a pack contains

| Layer | Contents | Source |
|-------|----------|--------|
| `dem` | Terrain heightmap (Terrarium-encoded PNG, 0.05 m vertical quantisation) | USGS 3DEP lidar (US, ~1 m). Falls back to AWS Terrain Tiles (global, ~5–30 m). |
| `imagery` | Aerial photo (JPEG, same bounding box as the DEM). Optional. | USGS NAIP (US, 0.6–1 m), or your own image. |
| `osm` | Vector features: woods, water, paths, roads, buildings, fences, OB, tees, baskets and others | OpenStreetMap via the Overpass API |
| `layout` | Hole list (tee, basket, par), if OSM has `disc_golf=hole` data | Derived from OSM |

The pack header also stores the bounding box, the sources, and attribution text (including the OSM ODbL credit).

## Requirements

- Python 3.9+
- `numpy` and `Pillow`:

  ```bash
  pip install numpy pillow
  ```

- Internet access while building. Nothing is needed afterwards.

## Quick start

From the repo root:

```bash
python3 python/dg_course_pack.py \
    --center 32.7335,-117.1437 --size 1000 \
    --name "Morley Field" --out packs/morley.dgpack
```

Or give an explicit bounding box (`W,S,E,N` in degrees) and skip imagery:

```bash
python3 python/dg_course_pack.py --bbox -117.150,32.728,-117.140,32.737 \
    --name Test --imagery none
```

Progress and the sources used are printed to stderr. The last line is `wrote <path> (<size> KB)`.

## Choosing the area

Give exactly one of these:

| Option | Meaning |
|--------|---------|
| `--center LAT,LON` | Course centre. Use it with `--size`. |
| `--bbox W,S,E,N` | Explicit bounding box in degrees. |
| `--size N` or `--size W,H` | With `--center`: square side, or width and height, in metres. Default `1000`. |

The area is limited to **6 km** per side. A larger area exits with an error. Cover the whole course with a little margin, but don't make the box much bigger than needed. The file size and the time to build both grow with the area.

To get coordinates, right-click the course centre in Google Maps or OpenStreetMap and copy the lat/lon.

## Options

| Option | Default | Description |
|--------|---------|-------------|
| `--name NAME` | required | Course name, shown in the app. |
| `--out PATH` | `<name>.dgpack` (lowercased, spaces become `_`) | Output file. Parent directories are created. |
| `--dem-res M` | `1.0` | Terrain resolution in metres per pixel (the DEM is capped at 4000 px). |
| `--dem-source {3dep,aws}` | `3dep` | Terrain source. `3dep` automatically falls back to `aws` if 3DEP fails or has more than 20% no-data. Use `aws` outside the US. |
| `--imagery {naip,none}` | `naip` | Aerial imagery source. Use `none` to omit it. |
| `--imagery-file FILE` | – | Use your own image instead of NAIP, for example a drone orthomosaic. It **must cover exactly the same bounding box**. |
| `--imagery-res M` | `0.6` | Imagery metres per pixel. |
| `--imagery-max-px N` | `3072` | Maximum imagery width or height. Larger images are downscaled. |
| `--jpeg-quality Q` | `80` | JPEG quality. Lower it for smaller packs. |
| `--no-osm` | off | Skip the OpenStreetMap vectors and layout. |
| `--unpack` | off | Also write `dem.png`, `imagery.jpg`, `osm.json` and `manifest.json` into a folder named after the pack. It is useful for debugging. |

## Using the pack in the app

1. Put the pack where the app can reach it, for example `packs/morley.dgpack`. The repo already includes `packs/morley.dgpack`.
2. Open `dg-score.html` and tap **Course ▾**. Then do one of the following:
   - **Choose a file** under *Add a course pack* and pick the `.dgpack` file from your device.
   - Enter a URL or relative path such as `packs/morley.dgpack`, and tap **Download**.
3. The app stores the pack in IndexedDB, so it works offline from then on.

Deep link: `dg-score.html?pack=packs/morley.dgpack`. The app also accepts `?view=3d|flat`, `?base=sat|map` and `?hole=3`.

To try the app without a pack, tap **Load synthetic demo course** or open `?demo=1`.

## How it falls back

- **Terrain:** 3DEP first, then AWS Terrain Tiles. Small holes in the 3DEP data are filled automatically.
- **Imagery:** NAIP tries two USGS services. If both fail, for example outside the US, the pack is built **without imagery**, with a warning. Use `--imagery-file` to supply your own.
- **OSM:** The script tries three Overpass servers. If all fail, the pack is built with no vector data. Re-run later if this happens.

Check the log output for `skipped` or `falling back` messages before you rely on a pack.

## Holes, tees and baskets

The hole list comes only from OSM. The script reads ways tagged `disc_golf=hole` (drawn tee to basket), with optional `ref` (hole number) and `par` tags. It snaps each end to a nearby `disc_golf=tee` or `disc_golf=basket` node within 40 m. If your course isn't mapped in OSM, the pack has an empty hole list. Add the data to OpenStreetMap and rebuild the pack.

## Playing without a pack

If you arrive at a course before anyone has built a pack, the app can build one on the spot. It uses free sources that need no key: OpenStreetMap vectors via Overpass, AWS Terrain Tiles (about 5 m terrain), and USGS NAIP aerial photos (US only).

- **Banner:** When your GPS fix is outside the open map, a banner offers **Play without pack**. If a saved map already covers your spot, it offers **Open it** instead.
- **Course dialog:** Tap **Course ▾**, then **Play without pack (use my location)**. You can type `lat,lon` instead, and pick an area of 1, 1.6 or 2.5 km.
- **Deep link:** `dg-score.html?live=1` uses your GPS. `dg-score.html?live=LAT,LON` uses the coordinates you give.

The map is built once, then saved on the device as a normal `.dgpack`. It works offline afterwards. Tees and baskets are learned as you mark throws. If OpenStreetMap has `disc_golf=hole` data, the hole list is pre-filled.

It needs a data connection once. With no connection at all you get a flat blank map, so GPS marking still works. Entries marked "no-pack (partial)" in the Course dialog are missing terrain or map data. Tap **↻** next to one when you have signal to refresh it in place. Your round is kept.

Start near the first tee. A no-pack map has no lidar terrain, and imagery is available only in the US. For the best result, build a real pack later with `dg_course_pack.py`.

## Pack file format

Little endian:

```
b"DGPK" | u8 version (=1) | u32 header_len | header JSON (utf-8) | blob0 | blob1 ...
```

`header.layers.<name>` holds `{offset, length, mime, ...}`. Offsets are relative to the end of the header.

## Troubleshooting

- **`area ... is too large`:** Reduce `--size`, or use a smaller `--bbox`. The limit is 6 km per side.
- **`3DEP has no data here`:** The area is outside US lidar coverage. The script already falls back to AWS. You can also pass `--dem-source aws`.
- **Imagery skipped or blank:** The area is outside NAIP coverage, or the service is down. Retry, or use `--imagery-file`.
- **Overpass failures or timeouts:** Wait and retry. The public servers are rate-limited.
- **Large file:** Lower `--imagery-max-px` or `--jpeg-quality`, raise `--dem-res` (for example `2`), or use `--imagery none`.

## Licensing and attribution

OpenStreetMap data is ODbL. Credit "© OpenStreetMap contributors". The pack records attribution strings for every source it used.
