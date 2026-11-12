#!/usr/bin/env python3
"""
dg_course_pack.py - build an offline "course pack" for dg-score.html

A course pack is ONE file (.dgpack) holding everything the browser needs to draw a
flat map and a 3D view of a disc golf course with no network:

  dem      terrain heightmap  (Terrarium-encoded PNG, uniform lon/lat grid)
  imagery  aerial photo       (JPEG, same bbox as the DEM)          [optional]
  osm      vector features    (JSON: woods, water, paths, OB, tees, baskets...)
  layout   hole list          (tee/basket/par if OSM has them)

Sources (all free to cache for offline use):
  * Terrain : USGS 3DEP lidar DEM (US, ~1 m)  -> falls back to AWS Terrain Tiles (global, ~5-30 m)
  * Imagery : USGS NAIP (US, 0.6-1 m)         -> or --imagery-file for your own drone/ortho image
  * Vectors : OpenStreetMap via Overpass API  (ODbL - attribution is recorded in the pack)

Usage examples
  python3 dg_course_pack.py --center 32.7335,-117.1437 --size 1000 --name "Morley Field" \
          --out ../packs/morley.dgpack
  python3 dg_course_pack.py --bbox -117.150,32.728,-117.140,32.737 --name Test --imagery none

Requires: Python 3.9+, numpy, Pillow   (pip install numpy pillow)

Container layout (little endian):
  b"DGPK" | u8 version(=1) | u32 header_len | header JSON (utf-8) | blob0 | blob1 ...
  header.layers.<name> = {offset, length, mime, ...}; offsets are relative to the end of the header.
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import math
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

UA = "dg-course-pack/0.1 (disc golf scoring prototype; https://github.com/gever/explorations)"
EARTH_R = 6371008.8
M_PER_DEG = math.pi / 180.0 * EARTH_R  # ~111195 m per degree of latitude (and of lon at the equator)

DEM_3DEP = "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage"
NAIP_SERVICES = [
    "https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPPlus/ImageServer/exportImage",
    "https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer/exportImage",
]
AWS_TERRARIUM = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
OVERPASS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]

DEM_QUANT_M = 0.05  # vertical quantisation of the stored heightmap (lidar is ~0.1 m accurate)


# --------------------------------------------------------------------------- helpers
def log(*a):
    print(*a, file=sys.stderr, flush=True)


def http_get(url: str, data: bytes | None = None, timeout: int = 120, retries: int = 3) -> bytes:
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = e
            wait = 2 ** attempt * 2
            log(f"    request failed ({e}); retry in {wait}s")
            time.sleep(wait)
    raise RuntimeError(f"giving up on {url[:100]}...: {last}")


def bbox_from_center(lat: float, lon: float, w_m: float, h_m: float):
    dlat = h_m / 2 / M_PER_DEG
    dlon = w_m / 2 / (M_PER_DEG * math.cos(math.radians(lat)))
    return (lon - dlon, lat - dlat, lon + dlon, lat + dlat)


def bbox_size_m(bbox):
    w, s, e, n = bbox
    lat0 = (s + n) / 2
    return ((e - w) * M_PER_DEG * math.cos(math.radians(lat0)), (n - s) * M_PER_DEG)


def grid_size(bbox, res_m: float, max_px: int):
    """Pixel dimensions giving ~square pixels of `res_m` metres, capped at max_px."""
    w_m, h_m = bbox_size_m(bbox)
    scale = min(1.0, max_px / max(w_m / res_m, h_m / res_m))
    return max(2, round(w_m / res_m * scale)), max(2, round(h_m / res_m * scale))


# --------------------------------------------------------------------------- terrain
def fill_nodata(a: np.ndarray) -> np.ndarray:
    """Replace NaNs by iteratively averaging valid neighbours."""
    mask = np.isnan(a)
    if not mask.any():
        return a
    if mask.all():
        raise RuntimeError("DEM is entirely no-data")
    a = a.copy()
    for _ in range(500):
        mask = np.isnan(a)
        if not mask.any():
            break
        p = np.pad(a, 1, constant_values=np.nan)
        stack = np.stack([p[:-2, 1:-1], p[2:, 1:-1], p[1:-1, :-2], p[1:-1, 2:]])
        with np.errstate(all="ignore"):
            avg = np.nanmean(stack, axis=0)
        a[mask] = avg[mask]
    return a


def fetch_dem_3dep(bbox, res_m: float, max_px: int):
    w, h = grid_size(bbox, res_m, min(max_px, 4000))
    q = urllib.parse.urlencode({
        "bbox": ",".join(f"{v:.8f}" for v in bbox), "bboxSR": 4326, "imageSR": 4326,
        "size": f"{w},{h}", "format": "tiff", "pixelType": "F32",
        "interpolation": "RSP_BilinearInterpolation", "f": "image",
    })
    raw = http_get(f"{DEM_3DEP}?{q}")
    im = Image.open(io.BytesIO(raw))
    if im.mode != "F":
        raise RuntimeError(f"unexpected 3DEP response (mode {im.mode}); body starts {raw[:80]!r}")
    a = np.array(im, dtype=np.float32)
    a[(a < -500) | (a > 9000) | ~np.isfinite(a)] = np.nan
    return a, "USGS 3DEP"


def decode_terrarium(rgb: np.ndarray) -> np.ndarray:
    r, g, b = (rgb[..., i].astype(np.float32) for i in range(3))
    return r * 256.0 + g + b / 256.0 - 32768.0


def fetch_dem_aws(bbox, res_m: float, max_px: int):
    w_deg, s, e, n = bbox[0], bbox[1], bbox[2], bbox[3]
    lat0 = (s + n) / 2
    # choose zoom: tile pixel size must be <= ~res_m but terrain tiles stop at z15
    z = 15
    for zz in range(8, 16):
        mpp = 156543.03392 * math.cos(math.radians(lat0)) / (2 ** zz)
        if mpp <= max(res_m, 1.0):
            z = zz
            break
    native = 156543.03392 * math.cos(math.radians(lat0)) / (2 ** z)

    def merc(lon, lat):  # -> fractional tile coords
        x = (lon + 180) / 360 * 2 ** z
        y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * 2 ** z
        return x, y

    x0, y1 = merc(w_deg, s)
    x1, y0 = merc(e, n)
    tx0, tx1, ty0, ty1 = int(x0), int(x1), int(y0), int(y1)
    mosaic = np.zeros(((ty1 - ty0 + 1) * 256, (tx1 - tx0 + 1) * 256), dtype=np.float32)
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            png = http_get(AWS_TERRARIUM.format(z=z, x=tx, y=ty))
            rgb = np.array(Image.open(io.BytesIO(png)).convert("RGB"))
            mosaic[(ty - ty0) * 256:(ty - ty0 + 1) * 256, (tx - tx0) * 256:(tx - tx0 + 1) * 256] = decode_terrarium(rgb)
    box = ((x0 - tx0) * 256, (y0 - ty0) * 256, (x1 - tx0) * 256, (y1 - ty0) * 256)
    w, h = grid_size(bbox, max(res_m, native), max_px)
    out = Image.fromarray(mosaic, mode="F").resize((w, h), Image.BILINEAR, box=box)
    return np.array(out, dtype=np.float32), f"AWS Terrain Tiles z{z} (~{native:.0f} m native)"


def get_dem(bbox, res_m, max_px, prefer="3dep"):
    if prefer == "3dep":
        try:
            a, src = fetch_dem_3dep(bbox, res_m, max_px)
            bad = np.isnan(a).mean()
            if bad < 0.2:
                if bad:
                    log(f"    filling {bad:.1%} no-data cells")
                return fill_nodata(a), src
            log(f"    3DEP has no data here ({bad:.0%} empty) - falling back to AWS terrain tiles")
        except Exception as e:  # network / outside coverage
            log(f"    3DEP failed ({e}) - falling back to AWS terrain tiles")
    return fetch_dem_aws(bbox, res_m, max_px)


def encode_terrarium_png(elev: np.ndarray) -> bytes:
    q = np.round(elev / DEM_QUANT_M) * DEM_QUANT_M
    v = q + 32768.0
    ip = np.floor(v)
    r = (ip // 256).astype(np.uint8)
    g = (ip % 256).astype(np.uint8)
    b = np.clip(np.floor((v - ip) * 256), 0, 255).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(np.dstack([r, g, b]), "RGB").save(buf, "PNG", optimize=True)
    return buf.getvalue()


# --------------------------------------------------------------------------- imagery
def fetch_naip(bbox, res_m: float, max_px: int):
    w, h = grid_size(bbox, res_m, min(max_px, 4096))
    q = urllib.parse.urlencode({
        "bbox": ",".join(f"{v:.8f}" for v in bbox), "bboxSR": 4326, "imageSR": 4326,
        "size": f"{w},{h}", "format": "jpg", "interpolation": "RSP_BilinearInterpolation", "f": "image",
    })
    last = None
    for svc in NAIP_SERVICES:
        try:
            raw = http_get(f"{svc}?{q}", timeout=180, retries=2)
            im = Image.open(io.BytesIO(raw)).convert("RGB")
            if np.asarray(im).std() < 3:
                raise RuntimeError("imagery is blank (outside NAIP coverage?)")
            return im, "USGS NAIP"
        except Exception as e:
            last = e
            log(f"    {svc.split('/')[-3]} failed: {e}")
    raise RuntimeError(f"no NAIP imagery: {last}")


def jpeg_bytes(im: Image.Image, quality: int) -> bytes:
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
    return buf.getvalue()


# --------------------------------------------------------------------------- OSM
def overpass_query(bbox) -> str:
    w, s, e, n = bbox
    b = f"{s:.6f},{w:.6f},{n:.6f},{e:.6f}"
    return f"""[out:json][timeout:90];
(
  way["natural"~"^(wood|scrub|water|wetland|grassland|heath|bare_rock|sand|scree)$"]({b});
  way["landuse"~"^(forest|grass|meadow|recreation_ground|residential|retail|commercial|industrial|farmland|cemetery)$"]({b});
  way["waterway"]({b});
  way["highway"]({b});
  way["building"]({b});
  way["barrier"~"^(fence|wall|hedge|retaining_wall)$"]({b});
  way["leisure"~"^(park|pitch|playground|disc_golf_course|golf_course|garden|nature_reserve)$"]({b});
  way["disc_golf"]({b});
  relation["natural"~"^(wood|water|wetland)$"]({b});
  relation["landuse"="forest"]({b});
  relation["disc_golf"]({b});
  relation["leisure"="disc_golf_course"]({b});
  node["natural"="tree"]({b});
  node["disc_golf"]({b});
  node["leisure"="disc_golf_course"]({b});
);
out geom tags;"""


def classify(tags: dict) -> tuple[str, str] | None:
    """-> (kind, geometry-hint) where hint is 'area' | 'line' | 'point'."""
    dg = tags.get("disc_golf")
    if dg:
        kind = {"hole": "dg_hole", "tee": "dg_tee", "basket": "dg_basket", "out_of_bounds": "ob", "ob": "ob",
                "drop_zone": "dg_drop"}.get(dg)
        if kind:
            return kind, "area" if kind == "ob" else ("line" if kind == "dg_hole" else "any")
    if tags.get("leisure") == "disc_golf_course":
        return "course", "area"
    nat, lu, lei = tags.get("natural"), tags.get("landuse"), tags.get("leisure")
    if nat == "tree":
        return "tree", "point"
    if nat == "wood" or lu == "forest":
        return "wood", "area"
    if nat in ("scrub", "heath"):
        return "scrub", "area"
    if nat == "water":
        return "water", "area"
    if nat == "wetland":
        return "wetland", "area"
    if "waterway" in tags:
        return "waterway", "line"
    if "building" in tags:
        return "building", "area"
    if "highway" in tags:
        return ("path" if tags["highway"] in ("path", "footway", "track", "bridleway", "cycleway", "steps", "pedestrian")
                else "road"), "line"
    if tags.get("barrier") in ("fence", "wall", "hedge", "retaining_wall"):
        return "fence", "line"
    if lu in ("residential", "retail", "commercial", "industrial", "cemetery"):
        return "developed", "area"
    if nat in ("grassland", "bare_rock", "sand", "scree") or lu in ("grass", "meadow", "recreation_ground", "farmland"):
        return "open", "area"
    if lei in ("park", "pitch", "playground", "garden", "golf_course", "nature_reserve"):
        return "park", "area"
    return None


def stitch_rings(segments: list[list[tuple[float, float]]]):
    """Join open way fragments (a multipolygon member role) into closed rings."""
    rings, segs = [], [list(s) for s in segments if len(s) >= 2]
    while segs:
        ring = segs.pop(0)
        progressed = True
        while ring[0] != ring[-1] and progressed:
            progressed = False
            for i, s in enumerate(segs):
                if s[0] == ring[-1]:
                    ring += s[1:]
                elif s[-1] == ring[-1]:
                    ring += s[::-1][1:]
                elif s[-1] == ring[0]:
                    ring = s[:-1] + ring
                elif s[0] == ring[0]:
                    ring = s[::-1][:-1] + ring
                else:
                    continue
                segs.pop(i)
                progressed = True
                break
        if ring[0] == ring[-1] and len(ring) >= 4:
            rings.append(ring)
    return rings


def simplify(pts, tol_deg: float):
    """Douglas-Peucker on lon/lat (tolerance in degrees; fine for sub-metre tolerances)."""
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i0, i1 = stack.pop()
        (x0, y0), (x1, y1) = pts[i0], pts[i1]
        dx, dy = x1 - x0, y1 - y0
        den = dx * dx + dy * dy
        best, bi = -1.0, -1
        for i in range(i0 + 1, i1):
            px, py = pts[i]
            if den == 0:
                d = math.hypot(px - x0, py - y0)
            else:
                t = max(0, min(1, ((px - x0) * dx + (py - y0) * dy) / den))
                d = math.hypot(px - (x0 + t * dx), py - (y0 + t * dy))
            if d > best:
                best, bi = d, i
        if best > tol_deg:
            keep[bi] = True
            stack += [(i0, bi), (bi, i1)]
    return [p for p, k in zip(pts, keep) if k]


def fetch_osm(bbox):
    body = urllib.parse.urlencode({"data": overpass_query(bbox)}).encode()
    last = None
    for url in OVERPASS:
        try:
            return json.loads(http_get(url, data=body, timeout=150, retries=2))
        except Exception as e:
            last = e
            log(f"    {url.split('/')[2]} failed: {e}")
    raise RuntimeError(f"all Overpass servers failed: {last}")


def convert_osm(raw: dict):
    """Overpass JSON -> compact feature list. Coordinates are [lon, lat] rounded to 1e-6 deg (~0.1 m)."""
    tol = 0.5 / M_PER_DEG
    rd = lambda p: [round(p[0], 6), round(p[1], 6)]
    feats = []
    for el in raw.get("elements", []):
        tags = el.get("tags", {})
        cl = classify(tags)
        if not cl:
            continue
        kind, hint = cl
        props = {k: tags[k] for k in ("name", "ref", "par", "dist", "highway", "surface") if k in tags}
        if el["type"] == "node":
            feats.append({"k": kind, "t": "n", "c": rd((el["lon"], el["lat"])), "p": props})
        elif el["type"] == "way" and el.get("geometry"):
            pts = [(g["lon"], g["lat"]) for g in el["geometry"]]
            closed = len(pts) >= 4 and pts[0] == pts[-1]
            if hint == "area" or (hint == "any" and closed):
                if not closed:
                    continue
                feats.append({"k": kind, "t": "a", "c": [[rd(p) for p in simplify(pts, tol)]], "p": props})
            else:
                feats.append({"k": kind, "t": "l", "c": [rd(p) for p in simplify(pts, tol)], "p": props})
        elif el["type"] == "relation":
            outer, inner = [], []
            for m in el.get("members", []):
                if m.get("type") == "way" and m.get("geometry"):
                    seg = [(g["lon"], g["lat"]) for g in m["geometry"]]
                    (inner if m.get("role") == "inner" else outer).append(seg)
            rings = stitch_rings(outer) + stitch_rings(inner)
            if rings and hint in ("area", "any"):
                feats.append({"k": kind, "t": "a", "c": [[rd(p) for p in simplify(r, tol)] for r in rings], "p": props})
    return feats


def derive_layout(feats):
    """Best-effort holes from OSM disc_golf=hole ways (tee -> basket order) + nearby tee/basket nodes."""
    def centroid(f):
        if f["t"] == "n":
            return f["c"]
        ring = f["c"][0] if f["t"] == "a" else f["c"]
        return [sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring)]

    def dist(a, b):
        lat = (a[1] + b[1]) / 2
        return math.hypot((a[0] - b[0]) * math.cos(math.radians(lat)), a[1] - b[1]) * M_PER_DEG

    tees = [centroid(f) for f in feats if f["k"] == "dg_tee"]
    baskets = [centroid(f) for f in feats if f["k"] == "dg_basket"]
    holes = []
    for f in feats:
        if f["k"] != "dg_hole" or f["t"] != "l" or len(f["c"]) < 2:
            continue
        tee, basket = f["c"][0], f["c"][-1]
        near = lambda pt, pool: min(pool, key=lambda q: dist(pt, q)) if pool and min(dist(pt, q) for q in pool) < 40 else pt
        p = f["p"]
        try:
            par = int(p.get("par")) if p.get("par") else None
        except ValueError:
            par = None
        holes.append({"ref": p.get("ref"), "par": par, "tee": near(tee, tees), "basket": near(basket, baskets),
                      "source": "osm"})

    def key(h):
        try:
            return (0, int(h["ref"]))
        except (TypeError, ValueError):
            return (1, 0)

    holes.sort(key=key)
    return holes


# --------------------------------------------------------------------------- container
def write_pack(path: Path, header: dict, blobs: list[tuple[str, bytes, dict]]):
    layers, data, off = {}, bytearray(), 0
    for name, blob, meta in blobs:
        layers[name] = {**meta, "offset": off, "length": len(blob)}
        data += blob
        off += len(blob)
    header = {**header, "layers": layers}
    hb = json.dumps(header, separators=(",", ":")).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"DGPK" + struct.pack("<BI", 1, len(hb)) + hb + data)
    return header


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--center", help="LAT,LON of the course centre")
    g.add_argument("--bbox", help="W,S,E,N in degrees")
    ap.add_argument("--size", default="1000", help="with --center: square side in metres, or W,H (default 1000)")
    ap.add_argument("--name", required=True, help="course name")
    ap.add_argument("--out", help="output file (default: <name>.dgpack)")
    ap.add_argument("--dem-res", type=float, default=1.0, help="terrain resolution in metres/pixel (default 1)")
    ap.add_argument("--dem-source", choices=["3dep", "aws"], default="3dep")
    ap.add_argument("--imagery", choices=["naip", "none"], default="naip")
    ap.add_argument("--imagery-file", help="use this image (must cover exactly the bbox) instead of NAIP")
    ap.add_argument("--imagery-res", type=float, default=0.6, help="imagery metres/pixel (default 0.6)")
    ap.add_argument("--imagery-max-px", type=int, default=3072, help="cap for imagery width/height")
    ap.add_argument("--jpeg-quality", type=int, default=80)
    ap.add_argument("--no-osm", action="store_true")
    ap.add_argument("--unpack", action="store_true", help="also write dem.png/imagery.jpg/osm.json/manifest.json beside the pack")
    a = ap.parse_args()

    if a.center:
        lat, lon = (float(v) for v in a.center.split(","))
        sz = [float(v) for v in a.size.split(",")]
        bbox = bbox_from_center(lat, lon, sz[0], sz[-1])
    else:
        bbox = tuple(float(v) for v in a.bbox.split(","))
    w_m, h_m = bbox_size_m(bbox)
    if w_m > 6000 or h_m > 6000:
        sys.exit(f"area {w_m:.0f} x {h_m:.0f} m is too large for a course pack (limit 6 km)")
    log(f"bbox W,S,E,N = {', '.join(f'{v:.6f}' for v in bbox)}  ({w_m:.0f} x {h_m:.0f} m)")

    out = Path(a.out or (a.name.lower().replace(" ", "_") + ".dgpack"))
    blobs, sources, attribution = [], [], []

    log("terrain ...")
    elev, dem_src = get_dem(bbox, a.dem_res, 4000, a.dem_source)
    sources.append(dem_src)
    attribution.append("Terrain: " + dem_src)
    log(f"    {dem_src}: {elev.shape[1]}x{elev.shape[0]} px, elevation {elev.min():.1f}..{elev.max():.1f} m")
    dem_png = encode_terrarium_png(elev)
    blobs.append(("dem", dem_png, {"mime": "image/png", "encoding": "terrarium", "quant_m": DEM_QUANT_M,
                                   "width": int(elev.shape[1]), "height": int(elev.shape[0]),
                                   "min": float(elev.min()), "max": float(elev.max()), "source": dem_src}))

    img_bytes = None
    if a.imagery_file:
        log("imagery (user file) ...")
        im = Image.open(a.imagery_file).convert("RGB")
        if max(im.size) > a.imagery_max_px:
            im.thumbnail((a.imagery_max_px, a.imagery_max_px), Image.LANCZOS)
        img_src = f"user imagery: {Path(a.imagery_file).name}"
    elif a.imagery == "naip":
        log("imagery (NAIP) ...")
        try:
            im, img_src = fetch_naip(bbox, a.imagery_res, a.imagery_max_px)
        except Exception as e:
            log(f"    imagery skipped: {e}")
            im = None
    else:
        im = None
    if im is not None:
        img_bytes = jpeg_bytes(im, a.jpeg_quality)
        blobs.append(("imagery", img_bytes, {"mime": "image/jpeg", "width": im.width, "height": im.height, "source": img_src}))
        sources.append(img_src)
        attribution.append("Imagery: " + img_src)
        log(f"    {im.width}x{im.height} px, {len(img_bytes) / 1024:.0f} KB")

    feats, holes = [], []
    if not a.no_osm:
        log("OpenStreetMap ...")
        try:
            feats = convert_osm(fetch_osm(bbox))
            holes = derive_layout(feats)
            counts = {}
            for f in feats:
                counts[f["k"]] = counts.get(f["k"], 0) + 1
            log(f"    {len(feats)} features: {counts}; {len(holes)} holes derived from OSM")
            attribution.append("Map data: OpenStreetMap contributors (ODbL)")
        except Exception as e:
            log(f"    OSM skipped: {e}")
    osm_bytes = json.dumps(feats, separators=(",", ":")).encode()
    blobs.append(("osm", osm_bytes, {"mime": "application/json", "count": len(feats)}))

    header = {
        "format": "dgpack", "version": 1, "name": a.name,
        "created": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "bbox": list(bbox), "center": [(bbox[1] + bbox[3]) / 2, (bbox[0] + bbox[2]) / 2],
        "size_m": [round(w_m, 1), round(h_m, 1)],
        "sources": sources, "attribution": attribution,
        "layout": {"holes": holes},
    }
    header = write_pack(out, header, blobs)
    log(f"wrote {out}  ({out.stat().st_size / 1024:.0f} KB)")

    if a.unpack:
        d = out.with_suffix("")
        d.mkdir(exist_ok=True)
        (d / "dem.png").write_bytes(dem_png)
        if img_bytes:
            (d / "imagery.jpg").write_bytes(img_bytes)
        (d / "osm.json").write_bytes(osm_bytes)
        (d / "manifest.json").write_text(json.dumps(header, indent=2))
        log(f"unpacked to {d}/")


if __name__ == "__main__":
    main()
