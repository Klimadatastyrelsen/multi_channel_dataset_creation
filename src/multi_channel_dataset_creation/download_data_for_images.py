#!/usr/bin/env python3
"""
Download Dataforsyningen products for each footprint.

Footprints come from a folder of GeoTIFFs, or from the bounding box of each
feature in a shapefile. For every footprint and every name in ``--datatypes``,
writes::

    output_folder/DATATYPE/<name>.tif

Example (images)::

  python download_data_for_images.py \\
    --token TOKEN \\
    --images_or_shapefile_defining_footprints /path/to/images \\
    --datatypes OrtoRGB OrtoCIR DSM DTM \\
    --output_folder /path/to/out \\
    --skip_existing

Example (shapefile; --resolution is required)::

  python download_data_for_images.py \\
    --token TOKEN \\
    --images_or_shapefile_defining_footprints /path/to/areas.shp \\
    --resolution 0.125 \\
    --datatypes OrtoRGB OrtoCIR DSM DTM \\
    --output_folder /path/to/out \\
    --skip_existing
"""
from __future__ import annotations

import argparse
import logging
import math
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

import geopandas as gpd
import pandas as pd
import rasterio
from rasterio.errors import NotGeoreferencedWarning
from rasterio.transform import from_bounds
from rasterio.warp import transform_bounds
from rasterio.windows import Window
from tqdm import tqdm

log = logging.getLogger("download_data_for_images")

TARGET_CRS = "EPSG:25832"
WMS_FORMAT = "image/jpeg"
# Dataforsyningen WMS rejects WIDTH or HEIGHT above 10000. Pieces are kept
# at 1000 so a single request is small enough to avoid gateway timeouts.
MAX_REQUEST_PIXELS = 1000
RETRYABLE_HTTP_CODES = frozenset({408, 429, 500, 502, 503, 504})
Bbox = Tuple[float, float, float, float]

# Friendly name -> Dataforsyningen service.
DATATYPES: Dict[str, dict] = {
    "OrtoRGB": {
        "service": "wms",
        "base": "https://api.dataforsyningen.dk/orto_foraar_DAF",
        "name": "geodanmark_2025_12_5cm",
    },
    "OrtoCIR": {
        "service": "wms",
        "base": "https://api.dataforsyningen.dk/orto_foraar_DAF",
        "name": "geodanmark_2025_12_5cm_cir",
    },
    "DSM": {
        "service": "wcs",
        "base": "https://api.dataforsyningen.dk/dhm_wcs_DAF",
        "name": "dhm_overflade",
    },
    "DTM": {
        "service": "wcs",
        "base": "https://api.dataforsyningen.dk/dhm_wcs_DAF",
        "name": "dhm_terraen",
    },
}


def setup_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    log.setLevel(logging.INFO)
    log.handlers.clear()
    log.addHandler(handler)


def hide_token(text: str, token: str) -> str:
    """Remove the API token from a message before it is logged."""
    if token:
        text = text.replace(token, "***")
        text = text.replace(urllib.parse.quote(token, safe=""), "***")
    return text


def list_geotiffs(folder: Path) -> List[Path]:
    paths = sorted(folder.rglob("*.tif")) + sorted(folder.rglob("*.tiff"))
    unique: List[Path] = []
    seen = set()
    for path in paths:
        if path.is_file() and path not in seen:
            seen.add(path)
            unique.append(path)
    return unique


def image_footprint(path: Path) -> dict:
    """Read bbox, resolution, and size. Bounds are reprojected to EPSG:25832."""
    with rasterio.open(path) as src:
        if src.crs is None:
            raise ValueError(f"{path} has no CRS")
        left, bottom, right, top = src.bounds
        if str(src.crs) != TARGET_CRS:
            left, bottom, right, top = transform_bounds(
                src.crs, TARGET_CRS, left, bottom, right, top, densify_pts=21
            )
        res_x = float(abs(src.res[0]))
        res_y = float(abs(src.res[1]))
        if abs(res_x - res_y) > 1e-6 * max(res_x, res_y):
            log.warning(
                "%s has non-square pixels (%.6f x %.6f); using x-resolution",
                path.name,
                res_x,
                res_y,
            )
        return {
            "name": path.name,
            "bbox": (float(left), float(bottom), float(right), float(top)),
            "resolution": res_x,
            "width": int(src.width),
            "height": int(src.height),
        }


def usable_attribute(value) -> Optional[str]:
    """Return a non-empty attribute value, or None when it cannot name a file."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "nat", "<na>"}:
        return None
    return text


def safe_stem(text: str) -> str:
    cleaned = []
    for char in text:
        if char.isalnum() or char in "._-":
            cleaned.append(char)
        else:
            cleaned.append("_")
    return "".join(cleaned).strip("._")


def unique_tif_name(stem: str, used: Set[str]) -> str:
    base = stem[:-4] if stem.lower().endswith(".tif") else stem
    name = f"{base}.tif"
    if name not in used:
        used.add(name)
        return name
    number = 2
    while f"{base}_{number}.tif" in used:
        number += 1
    name = f"{base}_{number}.tif"
    used.add(name)
    return name


def feature_filename(row, columns: Sequence[str], index: int, used: Set[str]) -> str:
    """First non-empty attribute, or the 1-based feature index when none exist."""
    for column in columns:
        text = usable_attribute(row[column])
        if text is None:
            continue
        stem = safe_stem(text)
        if stem:
            return unique_tif_name(stem, used)
    return unique_tif_name(str(index), used)


def shapefile_footprints(path: Path, resolution: float) -> List[dict]:
    """One footprint per feature bounding box, reprojected to EPSG:25832."""
    gdf = gpd.read_file(path)
    if gdf.crs is None:
        raise ValueError(f"{path} has no CRS")
    if gdf.empty:
        return []

    columns = [column for column in gdf.columns if column != gdf.geometry.name]
    used: Set[str] = set()
    footprints: List[dict] = []
    for feature_index, (_, row) in enumerate(gdf.iterrows(), start=1):
        geom = row.geometry
        if geom is None or geom.is_empty or not geom.is_valid:
            log.warning("Skipping feature %s: empty or invalid geometry", feature_index)
            continue
        left, bottom, right, top = geom.bounds
        if str(gdf.crs) != TARGET_CRS:
            left, bottom, right, top = transform_bounds(
                gdf.crs, TARGET_CRS, left, bottom, right, top, densify_pts=21
            )
        width = int(round((right - left) / resolution))
        height = int(round((top - bottom) / resolution))
        if width < 1 or height < 1 or not all(map(math.isfinite, (left, bottom, right, top))):
            log.warning("Skipping feature %s: bounding box is empty", feature_index)
            continue
        footprints.append(
            {
                "name": feature_filename(row, columns, feature_index, used),
                "bbox": (float(left), float(bottom), float(right), float(top)),
                "resolution": resolution,
                "width": width,
                "height": height,
            }
        )
    return footprints


def load_footprints(source: Path, resolution: Optional[float]) -> List[dict]:
    """Load footprints from a GeoTIFF folder or a shapefile."""
    if source.is_dir():
        if resolution is not None:
            log.info("Ignoring --resolution; each GeoTIFF supplies its own resolution")
        tif_paths = list_geotiffs(source)
        if not tif_paths:
            raise ValueError(f"No GeoTIFFs found under {source}")
        log.info("Reading footprints for %d images", len(tif_paths))
        return [image_footprint(path) for path in tif_paths]

    if source.is_file() and source.suffix.lower() == ".shp":
        if resolution is None:
            raise ValueError("--resolution is required when the input is a shapefile")
        if resolution <= 0:
            raise ValueError("--resolution must be > 0")
        log.info("Reading footprints from %s at %.4f m", source, resolution)
        return shapefile_footprints(source, resolution)

    raise ValueError(f"Expected a folder of GeoTIFFs or a .shp file, got: {source}")


def resolve_datatypes(names: Sequence[str]) -> List[Tuple[str, dict]]:
    resolved: List[Tuple[str, dict]] = []
    unknown: List[str] = []
    for raw in names:
        key = raw.strip()
        if not key:
            continue
        if key not in DATATYPES:
            unknown.append(key)
            continue
        resolved.append((key, DATATYPES[key]))
    if unknown:
        valid = ", ".join(sorted(DATATYPES))
        raise ValueError(f"Unknown --datatypes: {unknown}. Valid choices: {valid}")
    if not resolved:
        raise ValueError("Provide at least one --datatypes entry.")
    return resolved


def getmap_url(token: str, base: str, layer: str, bbox: Bbox, width: int, height: int) -> str:
    xmin, ymin, xmax, ymax = bbox
    return (
        f"{base}?token={token}"
        f"&SERVICE=WMS&VERSION=1.1.1&REQUEST=GetMap"
        f"&LAYERS={layer}&STYLES=&SRS={TARGET_CRS}"
        f"&BBOX={xmin},{ymin},{xmax},{ymax}"
        f"&WIDTH={width}&HEIGHT={height}"
        f"&FORMAT={WMS_FORMAT}"
    )


def pixel_edges(size: int, max_pixels: int = MAX_REQUEST_PIXELS) -> List[int]:
    """Split a pixel axis into pieces no larger than max_pixels."""
    if size < 1:
        raise ValueError(f"image size must be >= 1, got {size}")
    edges = list(range(0, size, max_pixels))
    if edges[-1] != size:
        edges.append(size)
    return edges


def pixel_windows(width: int, height: int, max_pixels: int = MAX_REQUEST_PIXELS) -> List[Tuple[int, int, int, int]]:
    """Return (col0, row0, col1, row1) windows covering width x height."""
    cols = pixel_edges(width, max_pixels)
    rows = pixel_edges(height, max_pixels)
    windows = []
    for row_index in range(len(rows) - 1):
        for col_index in range(len(cols) - 1):
            windows.append((cols[col_index], rows[row_index], cols[col_index + 1], rows[row_index + 1]))
    return windows


def sub_bbox(bbox: Bbox, width: int, height: int, col0: int, row0: int, col1: int, row1: int) -> Bbox:
    """Map a pixel window onto the footprint. Row 0 is the northern edge."""
    xmin, ymin, xmax, ymax = bbox
    x0 = xmin + (xmax - xmin) * col0 / width
    x1 = xmin + (xmax - xmin) * col1 / width
    y1 = ymax - (ymax - ymin) * row0 / height
    y0 = ymax - (ymax - ymin) * row1 / height
    return (x0, y0, x1, y1)


def coverage_size(bbox: Bbox, resolution: float) -> Tuple[int, int]:
    xmin, ymin, xmax, ymax = bbox
    width = max(1, int(round((xmax - xmin) / resolution)))
    height = max(1, int(round((ymax - ymin) / resolution)))
    return width, height


def getcoverage_url(token: str, base: str, coverage: str, bbox: Bbox, width: int, height: int) -> str:
    xmin, ymin, xmax, ymax = bbox
    return (
        f"{base}?token={token}"
        f"&SERVICE=WCS&VERSION=1.0.0&REQUEST=GetCoverage"
        f"&COVERAGE={coverage}&CRS={TARGET_CRS}&RESPONSE_CRS={TARGET_CRS}"
        f"&BBOX={xmin},{ymin},{xmax},{ymax}"
        f"&WIDTH={width}&HEIGHT={height}"
        f"&FORMAT=GTiff"
    )


def looks_like_image(data: bytes) -> bool:
    if len(data) < 4:
        return False
    return (
        data[:3] == b"\xff\xd8\xff"
        or data[:8] == b"\x89PNG\r\n\x1a\n"
        or data[:4] in (b"II*\x00", b"MM\x00*")
    )


def http_get(url: str, token: str, timeout: float, retries: int) -> Tuple[bytes, str]:
    """GET url. Retry timeouts and transient HTTP codes."""
    last_exc: Optional[BaseException] = None
    attempts = max(1, retries)
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                payload = resp.read()
                content_type = (resp.headers.get("Content-Type") or "").lower()
                return payload, content_type
        except urllib.error.HTTPError as exc:
            last_exc = exc
            if exc.code not in RETRYABLE_HTTP_CODES or attempt == attempts:
                raise
            sleep_s = 2.0 * (2 ** (attempt - 1))
            log.warning("HTTP %s (attempt %d/%d); retrying in %.1fs", exc.code, attempt, attempts, sleep_s)
            time.sleep(sleep_s)
        except urllib.error.URLError as exc:
            last_exc = exc
            if attempt == attempts:
                raise
            sleep_s = 2.0 * (2 ** (attempt - 1))
            reason = hide_token(str(exc.reason if hasattr(exc, "reason") else exc), token)
            log.warning(
                "Request failed (attempt %d/%d): %s; retrying in %.1fs",
                attempt,
                attempts,
                reason,
                sleep_s,
            )
            time.sleep(sleep_s)
    assert last_exc is not None
    raise last_exc


def write_bytes(path: Path, payload: bytes) -> None:
    """Write via a local tempfile, then copy. Safer on network drives."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="download_tile_") as tmp:
        local_out = Path(tmp) / path.name
        local_out.write_bytes(payload)
        path.write_bytes(local_out.read_bytes())


def geotiff_profile(width: int, height: int, bbox: Bbox, count: int, dtype: str) -> dict:
    xmin, ymin, xmax, ymax = bbox
    profile = {
        "driver": "GTiff",
        "height": height,
        "width": width,
        "count": count,
        "dtype": dtype,
        "crs": TARGET_CRS,
        "transform": from_bounds(xmin, ymin, xmax, ymax, width, height),
        "compress": "lzw",
    }
    # TIFF tiles must be multiples of 16 and no larger than the image.
    if width >= 16 and height >= 16:
        profile["tiled"] = True
        profile["blockxsize"] = max(16, (min(256, width) // 16) * 16)
        profile["blockysize"] = max(16, (min(256, height) // 16) * 16)
    return profile


def reject_service_error(payload: bytes, content_type: str, folder: str, service_name: str) -> None:
    if (not looks_like_image(payload)) or "xml" in content_type or "text" in content_type:
        snippet = payload[:300].decode("utf-8", errors="replace")
        raise RuntimeError(
            f"{service_name} did not return an image for {folder} "
            f"(content-type={content_type!r}). Response starts with:\n{snippet}"
        )


def read_wms_array(job: dict, bbox: Bbox, width: int, height: int):
    url = getmap_url(job["token"], job["base"], job["layer"], bbox, width, height)
    try:
        payload, content_type = http_get(url, job["token"], timeout=120, retries=job["retries"])
    except urllib.error.URLError as exc:
        raise RuntimeError(f"WMS GetMap failed: {hide_token(str(exc), job['token'])}") from exc
    reject_service_error(payload, content_type, job["folder"], "WMS")
    with tempfile.TemporaryDirectory(prefix="orto_piece_") as tmp:
        raw_path = Path(tmp) / "tile.jpg"
        raw_path.write_bytes(payload)
        # The JPEG has no georeferencing; the caller sets the GeoTIFF transform.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", NotGeoreferencedWarning)
            with rasterio.open(raw_path) as src:
                data = src.read()
                count = src.count
                dtype = src.dtypes[0]
    if data.shape[1] != height or data.shape[2] != width:
        raise RuntimeError(f"WMS returned {data.shape[2]}x{data.shape[1]} for {job['folder']}, expected {width}x{height}")
    return data, count, dtype


def download_wms(job: dict) -> None:
    bbox = job["bbox"]
    width = job["width"]
    height = job["height"]
    windows = pixel_windows(width, height)
    #if we try to download to large an area, we need to download it in several patches and patch them together
    if len(windows) > 1:
        log.info(
            "%s is %d x %d pixels; downloading %d WMS pieces (max %d)",
            job["out_path"].name,
            width,
            height,
            len(windows),
            MAX_REQUEST_PIXELS,
        )
    with tempfile.TemporaryDirectory(prefix="orto_tile_") as tmp:
        local_out = Path(tmp) / job["out_path"].name
        destination = None
        try:
            for col0, row0, col1, row1 in windows:
                piece_bbox = sub_bbox(bbox, width, height, col0, row0, col1, row1)
                data, count, dtype = read_wms_array(job, piece_bbox, col1 - col0, row1 - row0)
                if destination is None:
                    destination = rasterio.open(
                        local_out, "w", **geotiff_profile(width, height, bbox, count, dtype)
                    )
                elif data.shape[0] != destination.count or data.dtype != destination.dtypes[0]:
                    raise RuntimeError(f"WMS piece for {job['folder']} does not match the first piece")
                destination.write(data, window=Window(col0, row0, col1 - col0, row1 - row0))
        finally:
            if destination is not None:
                destination.close()
        write_bytes(job["out_path"], local_out.read_bytes())


def read_wcs_bytes(job: dict, bbox: Bbox, width: int, height: int) -> bytes:
    url = getcoverage_url(job["token"], job["base"], job["layer"], bbox, width, height)
    try:
        payload, content_type = http_get(url, job["token"], timeout=180, retries=job["retries"])
    except urllib.error.URLError as exc:
        raise RuntimeError(f"WCS GetCoverage failed: {hide_token(str(exc), job['token'])}") from exc
    reject_service_error(payload, content_type, job["folder"], "WCS")
    return payload


def download_wcs(job: dict) -> None:
    bbox = job["bbox"]
    width, height = coverage_size(bbox, job["resolution"])
    windows = pixel_windows(width, height)
    if len(windows) == 1:
        write_bytes(job["out_path"], read_wcs_bytes(job, bbox, width, height))
        return
    log.info(
        "%s is %d x %d pixels; downloading %d WCS pieces (max %d)",
        job["out_path"].name,
        width,
        height,
        len(windows),
        MAX_REQUEST_PIXELS,
    )
    with tempfile.TemporaryDirectory(prefix="wcs_tile_") as tmp:
        local_out = Path(tmp) / job["out_path"].name
        destination = None
        try:
            for col0, row0, col1, row1 in windows:
                piece_bbox = sub_bbox(bbox, width, height, col0, row0, col1, row1)
                payload = read_wcs_bytes(job, piece_bbox, col1 - col0, row1 - row0)
                piece_path = Path(tmp) / f"piece_{col0}_{row0}.tif"
                piece_path.write_bytes(payload)
                with rasterio.open(piece_path) as src:
                    data = src.read()
                    count = src.count
                    dtype = src.dtypes[0]
                if data.shape[1] != row1 - row0 or data.shape[2] != col1 - col0:
                    raise RuntimeError(
                        f"WCS returned {data.shape[2]}x{data.shape[1]} for {job['folder']}, "
                        f"expected {col1 - col0}x{row1 - row0}"
                    )
                if destination is None:
                    destination = rasterio.open(
                        local_out, "w", **geotiff_profile(width, height, bbox, count, dtype)
                    )
                elif count != destination.count or dtype != destination.dtypes[0]:
                    raise RuntimeError(f"WCS piece for {job['folder']} does not match the first piece")
                destination.write(data, window=Window(col0, row0, col1 - col0, row1 - row0))
        finally:
            if destination is not None:
                destination.close()
        write_bytes(job["out_path"], local_out.read_bytes())


def download_one(job: dict) -> None:
    if job["service"] == "wms":
        download_wms(job)
    else:
        download_wcs(job)


def build_jobs(
    footprints: List[dict],
    datatypes: List[Tuple[str, dict]],
    output_folder: Path,
    token: str,
    skip_existing: bool,
    retries: int,
) -> Tuple[List[dict], int]:
    pending: List[dict] = []
    n_skip = 0
    for folder_key, cfg in datatypes:
        layer_dir = output_folder / folder_key
        for footprint in footprints:
            out_path = layer_dir / footprint["name"]
            if skip_existing and out_path.exists():
                n_skip += 1
                continue
            pending.append(
                {
                    "service": cfg["service"],
                    "folder": folder_key,
                    "layer": cfg["name"],
                    "base": cfg["base"],
                    "bbox": footprint["bbox"],
                    "resolution": footprint["resolution"],
                    "width": footprint["width"],
                    "height": footprint["height"],
                    "out_path": out_path,
                    "token": token,
                    "retries": retries,
                }
            )
    return pending, n_skip


def run_downloads(pending: List[dict], workers: int) -> List[str]:
    """Download every job. Return error lines for the ones that failed."""
    failed: List[str] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(download_one, job): job for job in pending}
        with tqdm(total=len(pending), desc="Downloading", unit="tile") as pbar:
            for fut in as_completed(futures):
                job = futures[fut]
                try:
                    fut.result()
                except Exception as exc:  # noqa: BLE001
                    message = hide_token(str(exc), job["token"])
                    log.error("%s: %s", job["out_path"], message)
                    failed.append(f"{job['out_path']}: {message}")
                pbar.update(1)
    return failed


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--token", required=True, help="Dataforsyningen API token")
    parser.add_argument(
        "--images_or_shapefile_defining_footprints",
        type=Path,
        required=True,
        help="Folder of GeoTIFFs, or a .shp whose feature bounding boxes define the download windows",
    )
    parser.add_argument(
        "--resolution",
        type=float,
        default=None,
        help="Ground resolution in metres. Required for a shapefile; ignored for GeoTIFF folders",
    )
    parser.add_argument(
        "--datatypes",
        nargs="+",
        required=True,
        metavar="NAME",
        help="Products to download: " + ", ".join(sorted(DATATYPES)),
    )
    parser.add_argument(
        "--output_folder",
        type=Path,
        required=True,
        help="Root output folder; each datatype gets a subfolder",
    )
    parser.add_argument("--skip_existing", action="store_true", help="Skip outputs that already exist")
    parser.add_argument("--workers", type=int, default=1, help="Parallel downloads (default: 1)")
    parser.add_argument("--retries", type=int, default=5, help="HTTP retries per tile (default: 5)")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    setup_logging()

    source = args.images_or_shapefile_defining_footprints
    output_folder = args.output_folder
    if args.workers < 1:
        log.error("--workers must be >= 1")
        return 1
    if args.retries < 1:
        log.error("--retries must be >= 1")
        return 1
    if not args.token.strip():
        log.error("--token is empty")
        return 1

    try:
        datatypes = resolve_datatypes(args.datatypes)
    except ValueError as exc:
        log.error("%s", exc)
        return 1

    try:
        footprints = load_footprints(source, args.resolution)
    except Exception as exc:  # noqa: BLE001
        log.error("%s", exc)
        return 1
    if not footprints:
        log.error("No footprints found in %s", source)
        return 1

    output_folder.mkdir(parents=True, exist_ok=True)
    pending, n_skip = build_jobs(
        footprints, datatypes, output_folder, args.token.strip(), args.skip_existing, args.retries
    )
    log.info("Jobs: %d pending, %d skipped existing", len(pending), n_skip)
    if not pending:
        log.info("Nothing to download.")
        return 0

    failed = run_downloads(pending, args.workers)
    log.info("Finished: wrote=%d, skipped_existing=%d, failed=%d", len(pending) - len(failed), n_skip, len(failed))
    if failed:
        log.error("Failed downloads:")
        for line in failed:
            log.error("  %s", line)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
