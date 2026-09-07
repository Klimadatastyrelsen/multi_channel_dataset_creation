"""Fast bbox overlap checks: one GeoTIFF read per file + STRtree spatial index."""

from __future__ import annotations

import hashlib
import json
import pathlib
import time
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from osgeo import gdal
from shapely.geometry import box
from shapely.strtree import STRtree

gdal.UseExceptions()

ProgressCallback = Optional[Callable[[str, int, int, str], None]]


def geotiff_bbox_polygon(tif_path: pathlib.Path):
    """Return a shapely box for the GeoTIFF footprint (same logic as overlap.geotiff_overlap)."""
    dataset = gdal.Open(str(tif_path), gdal.GA_ReadOnly)
    if dataset is None:
        raise RuntimeError(f"Failed to open GeoTIFF: {tif_path}")

    geo_transform = dataset.GetGeoTransform()
    min_x = geo_transform[0]
    max_x = min_x + geo_transform[1] * dataset.RasterXSize
    min_y = geo_transform[3] + geo_transform[5] * dataset.RasterYSize
    max_y = geo_transform[3]
    dataset = None
    return box(min_x, min_y, max_x, max_y)


def _cache_key(folder_path: pathlib.Path, filenames: Sequence[str]) -> str:
    payload = f"{folder_path}\n" + "\n".join(sorted(filenames))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _load_footprint_cache(cache_path: pathlib.Path, cache_key: str) -> Optional[Dict[str, list]]:
    if not cache_path.is_file():
        return None
    try:
        with open(cache_path, "r", encoding="utf-8") as cache_file:
            payload = json.load(cache_file)
    except (OSError, json.JSONDecodeError):
        return None
    if payload.get("cache_key") != cache_key:
        return None
    return payload.get("footprints")


def _save_footprint_cache(
    cache_path: pathlib.Path,
    cache_key: str,
    footprints: Dict[str, list],
) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as cache_file:
        json.dump({"cache_key": cache_key, "footprints": footprints}, cache_file)


def build_footprints(
    filenames: Sequence[str],
    folder_path: pathlib.Path,
    cache_path: Optional[pathlib.Path] = None,
    progress_callback: ProgressCallback = None,
) -> Dict[str, object]:
    """Read each GeoTIFF once and return filename -> shapely box."""
    folder_path = pathlib.Path(folder_path)
    unique_filenames = list(dict.fromkeys(filenames))
    cache_key = _cache_key(folder_path, unique_filenames)

    if cache_path is not None:
        cached = _load_footprint_cache(cache_path, cache_key)
        if cached is not None:
            return {name: box(*bounds) for name, bounds in cached.items()}

    footprints: Dict[str, object] = {}
    serialized: Dict[str, list] = {}
    total = len(unique_filenames)
    for index, filename in enumerate(unique_filenames, start=1):
        geom = geotiff_bbox_polygon(folder_path / filename)
        footprints[filename] = geom
        serialized[filename] = list(geom.bounds)
        if progress_callback is not None:
            progress_callback("footprints", index, total, filename)

    if cache_path is not None:
        _save_footprint_cache(cache_path, cache_key, serialized)

    return footprints


def build_valid_spatial_index(
    valid_filenames: Sequence[str],
    footprints: Dict[str, object],
) -> Tuple[STRtree, List[str], List[object]]:
    """Build an STRtree over validation footprints."""
    ordered_valid = list(dict.fromkeys(valid_filenames))
    valid_geometries = [footprints[name] for name in ordered_valid]
    return STRtree(valid_geometries), ordered_valid, valid_geometries


def filename_matches_valid_entry(filename: str, valid_filenames: Sequence[str]) -> bool:
    """Mirror legacy substring check: validset_filename in filename."""
    return any(valid_name in filename for valid_name in valid_filenames)


def overlaps_any_valid(
    train_geom,
    valid_tree: STRtree,
    valid_geometries: Sequence[object],
) -> bool:
    """Return True when train footprint intersects any validation footprint."""
    candidate_indices = valid_tree.query(train_geom, predicate="intersects")
    for candidate_index in candidate_indices:
        if train_geom.intersects(valid_geometries[candidate_index]):
            return True
    return False


def crop_prefix(filename: str) -> str:
    """Prefix shared by splitted crop filenames (drops last two _ segments)."""
    return "_".join(filename.split("_")[0:-2])


def remove_overlap_fast(
    all_filenames: Sequence[str],
    valid_filenames: Sequence[str],
    folder_path: pathlib.Path,
    images_must_be_crops_of_these_images_path: Optional[str] = None,
    cache_path: Optional[pathlib.Path] = None,
    progress_callback: ProgressCallback = None,
) -> Tuple[List[str], List[str]]:
    """
    Return (train_filenames, overlapping_filenames) using bbox overlap only.

    Preserves the legacy semantics of remove_overlap_from_all_txt:
    - shuffle order of all_filenames is handled by the caller
    - valid entries are excluded from train via substring match
    - partial bbox overlap with valid excludes a file from train
    """
    folder_path = pathlib.Path(folder_path)
    large_tiff_files: Optional[List[str]] = None
    if images_must_be_crops_of_these_images_path:
        with open(images_must_be_crops_of_these_images_path, "r", encoding="utf-8") as crop_file:
            large_tiff_files = [
                pathlib.Path(line.strip()).stem.split("/")[-1]
                for line in crop_file
                if line.strip()
            ]

    unique_names = list(dict.fromkeys(list(all_filenames) + list(valid_filenames)))
    footprint_cache = cache_path
    if footprint_cache is None:
        footprint_cache = folder_path.parent / ".overlap_footprints_cache.json"

    print(f"Reading GeoTIFF footprints for {len(unique_names)} files (one open per file)...")
    footprint_start = time.time()
    footprints = build_footprints(
        unique_names,
        folder_path,
        cache_path=footprint_cache,
        progress_callback=progress_callback,
    )
    print(
        f"Footprints loaded in {(time.time() - footprint_start) / 60:.2f} minutes "
        f"(cache: {footprint_cache})"
    )

    valid_tree, ordered_valid, valid_geometries = build_valid_spatial_index(
        valid_filenames,
        footprints,
    )

    train_files: List[str] = []
    overlapping_files: List[str] = []
    total = len(all_filenames)
    loop_start = time.time()

    for index, filename in enumerate(all_filenames, start=1):
        search_for_overlap = True
        if large_tiff_files is not None:
            search_for_overlap = crop_prefix(filename) in large_tiff_files

        found_in_valid = False
        found_overlapping = False

        if search_for_overlap:
            if filename_matches_valid_entry(filename, valid_filenames):
                found_in_valid = True
            elif overlaps_any_valid(footprints[filename], valid_tree, valid_geometries):
                found_overlapping = True
                overlapping_files.append(filename)

        if not found_in_valid and not found_overlapping:
            train_files.append(filename)

        if progress_callback is not None:
            progress_callback("filter", index, total, filename)

    print(
        f"Overlap filtering finished in {(time.time() - loop_start) / 60:.2f} minutes "
        f"(total {(time.time() - footprint_start) / 60:.2f} minutes)"
    )
    return train_files, overlapping_files
