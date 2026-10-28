"""Rasterize geopackage polygons directly onto already splitted image patches.

The normal route is geopackage_to_label_v2.py (one label per large image) followed by
create_patches.py (split into patches). This script skips the large labels, which for the
befaestelse dataset are 90 GB, and writes the patches straight away. The rasterization
itself is geopackage_to_label_v2.process_single_raster_labels, so the result is the same.
"""

import argparse
import multiprocessing as mp
import os
import sys
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from shapely.geometry import box

from geopackage_to_label_v2 import process_single_raster_labels

# set in each worker by _init_worker, inherited through fork in the parent
_GDF = None
_SETTINGS = None


def _init_worker(gdf, settings):
    global _GDF, _SETTINGS
    _GDF = gdf
    _SETTINGS = settings


def _create_one_label(job):
    index, nr_of_files, tile_path, output_path = job
    settings = _SETTINGS
    try:
        if settings["skip_existing"] and Path(output_path).exists():
            return {"ok": True, "filename": Path(tile_path).name, "skipped": True}

        with rasterio.open(tile_path) as src:
            bounds = src.bounds
            output_shape = (src.height, src.width)
            out_transform = src.transform
            crs = src.crs

        # the elementwise gdf.geometry.intersects() of process_label_generation_main is
        # nr_of_polygons x nr_of_patches comparisons, which is too slow for >20000 patches
        candidates = _GDF.iloc[sorted(_GDF.sindex.query(box(*bounds), predicate="intersects"))]

        label_array = process_single_raster_labels(
            gdf=candidates,
            bounds=bounds,
            output_shape=output_shape,
            out_transform=out_transform,
            unknown_border_size=settings["unknown_border_size"],
            background_value=settings["background_value"],
            ignore_value=settings["ignore_value"],
            attr_column=settings["attribute"],
            value_used_for_all_polygons=settings["value_used_for_all_polygons"],
        )

        profile = dict(
            driver="GTiff",
            height=output_shape[0],
            width=output_shape[1],
            count=1,
            dtype=rasterio.uint8,
            crs=crs,
            transform=out_transform,
            nodata=settings["ignore_value"],
            compress="lzw",
            tiled=True,
            blockxsize=256,
            blockysize=256,
        )
        with rasterio.open(output_path, "w", **profile) as dst:
            dst.write(label_array, 1)

        if index % 500 == 0:
            print(f"created label {index} out of {nr_of_files}", flush=True)
        return {"ok": True, "filename": Path(tile_path).name, "skipped": False}
    except Exception as e:
        print(f"FAILED creating label for: {tile_path} : {e}", flush=True)
        return {"ok": False, "filename": Path(tile_path).name, "error": str(e)}


def load_geopackage(geopackage, attribute=None, value_used_for_all_polygons=None):
    """Load and preprocess the polygons the same way geopackage_to_label_v2 does."""
    if value_used_for_all_polygons is not None and attribute is not None:
        raise ValueError(
            "Cannot specify both 'value_used_for_all_polygons' and 'attribute'. Use one or the other."
        )
    if value_used_for_all_polygons is None and attribute is None:
        raise ValueError("Must specify either 'value_used_for_all_polygons' or 'attribute'.")

    print("Loading geopackage...")
    reading_geopkg_start = time.time()
    gdf = gpd.read_file(geopackage)
    print(f"Reading geopackage took: {(time.time()-reading_geopkg_start)/60:.2f} minutes")
    print(f"polygons: {len(gdf)}, crs: {gdf.crs}")

    if attribute is not None:
        if attribute not in gdf.columns:
            print("Available columns:", list(gdf.columns))
            raise ValueError(f"Attribute column '{attribute}' not found in the GeoPackage.")
        original_count = len(gdf)
        gdf = gdf.dropna(subset=[attribute])
        if original_count - len(gdf) > 0:
            print(f"Removed {original_count - len(gdf)} polygons missing '{attribute}' values.")
        gdf[attribute] = gdf[attribute].astype(np.uint8)

    if "area" not in gdf.columns:
        gdf["area"] = gdf.geometry.area

    gdf.sindex  # build the spatial index before forking so the workers share it
    return gdf


def main(
    geopackage,
    tile_folder,
    output_folder,
    file_list=None,
    attribute=None,
    value_used_for_all_polygons=None,
    background_value=0,
    ignore_value=0,
    unknown_border_size=0.1,
    nr_of_processes=1,
    skip_existing=False,
):
    tile_folder = Path(tile_folder)
    output_folder = Path(output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)

    if file_list:
        filenames = [line.strip() for line in open(file_list) if line.strip()]
        missing = [name for name in filenames if not (tile_folder / name).exists()]
        if missing:
            sys.exit(
                f"{len(missing)} of the {len(filenames)} files in {file_list} are missing from "
                f"{tile_folder}, first ones: {missing[:5]}"
            )
    else:
        filenames = sorted(p.name for p in tile_folder.glob("*.tif"))

    if not filenames:
        sys.exit(f"No patches to create labels for in: {tile_folder}")
    print(f"creating {len(filenames)} labels in {output_folder}")

    gdf = load_geopackage(geopackage, attribute, value_used_for_all_polygons)
    settings = {
        "attribute": attribute,
        "value_used_for_all_polygons": value_used_for_all_polygons,
        "background_value": background_value,
        "ignore_value": ignore_value,
        "unknown_border_size": unknown_border_size,
        "skip_existing": skip_existing,
    }

    jobs = [
        (index, len(filenames), str(tile_folder / name), str(output_folder / name))
        for index, name in enumerate(filenames)
    ]

    start_time = time.time()
    if nr_of_processes > 1:
        print(f"creating pool of : {nr_of_processes} nr of processes")
        # fork on Linux: spawn would reload the geopackage in every worker
        ctx = mp.get_context("fork")
        with ctx.Pool(
            processes=nr_of_processes, initializer=_init_worker, initargs=(gdf, settings)
        ) as pool:
            results = pool.map(_create_one_label, jobs, 32)
    else:
        _init_worker(gdf, settings)
        results = [_create_one_label(job) for job in jobs]

    failed = [r["filename"] for r in results if not r.get("ok")]
    skipped = [r["filename"] for r in results if r.get("skipped")]
    print(f"creating labels took: {(time.time()-start_time)/60:.2f} minutes")
    print(f"created: {len(results)-len(failed)-len(skipped)}, skipped: {len(skipped)}, failed: {len(failed)}")
    if failed:
        print("failed files: " + str(failed))
        sys.exit(1)


if __name__ == "__main__":
    usage_example = (
        "example usage:\n"
        "python geopackage_to_splitted_labels.py --geopackage labels/20261023_labels.gpkg "
        "--tile_folder data/splitted/OrtoRGB --file_list data/all.txt "
        "--output_folder labels/splitted_labels --attribute ML_CATEGORY "
        "--background_value 0 --ignore_value 0 --nr_of_processes 12"
    )
    parser = argparse.ArgumentParser(
        epilog=usage_example, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--geopackage", required=True, help="path to the geopackage holding the polygons")
    parser.add_argument("--tile_folder", required=True, help="folder with the splitted images defining the label grid")
    parser.add_argument("--output_folder", required=True, help="folder the label patches are written to")
    parser.add_argument("--file_list", required=False, help="txt file listing the patches to create, one name per line. Default: every .tif in --tile_folder")
    parser.add_argument("--attribute", required=False, help="polygon attribute holding the class, e.g ML_CATEGORY. Mutually exclusive with --value_used_for_all_polygons")
    parser.add_argument("--value_used_for_all_polygons", required=False, type=int, help="class given to every polygon. Mutually exclusive with --attribute")
    parser.add_argument("--background_value", required=False, type=int, default=0, help="value for areas not covered by a polygon. Default: 0")
    parser.add_argument("--ignore_value", required=False, type=int, default=0, help="value for the border between classes. Default: 0")
    parser.add_argument("--unknown_border_size", required=False, type=float, default=0.1, help="width in ground units of the ignored border between classes. Default: 0.1")
    parser.add_argument("--nr_of_processes", required=False, type=int, default=1, help="nr of parallel worker processes. Default: 1")
    parser.add_argument("--skip_existing", action="store_true", help="leave already existing label patches untouched")
    args = parser.parse_args()

    os.environ.setdefault("GDAL_NUM_THREADS", "1")
    main(
        geopackage=args.geopackage,
        tile_folder=args.tile_folder,
        output_folder=args.output_folder,
        file_list=args.file_list,
        attribute=args.attribute,
        value_used_for_all_polygons=args.value_used_for_all_polygons,
        background_value=args.background_value,
        ignore_value=args.ignore_value,
        unknown_border_size=args.unknown_border_size,
        nr_of_processes=args.nr_of_processes,
        skip_existing=args.skip_existing,
    )
