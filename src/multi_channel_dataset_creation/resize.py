"""Resample GeoTIFFs to a target ground resolution (meters per pixel)."""

from __future__ import annotations

import argparse
import glob
import logging
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from tqdm import tqdm

log = logging.getLogger("resize")


def setup_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    log.setLevel(logging.INFO)
    log.handlers.clear()
    log.addHandler(handler)


def output_dimensions(bounds, resolution: float) -> Tuple[int, int]:
    """Pixel size from geographic extent (avoids int(width*scale) truncation)."""
    left, bottom, right, top = bounds
    width = int(round((right - left) / resolution))
    height = int(round((top - bottom) / resolution))
    return max(1, width), max(1, height)


def compression_profile(src_meta: dict, compress: Optional[str]) -> dict:
    """Build optional GeoTIFF compression keys for the output profile."""
    if not compress:
        return {}
    dtype = src_meta.get("dtype", "")
    is_float = np.issubdtype(np.dtype(dtype), np.floating)
    return {
        "compress": compress,
        "predictor": 3 if is_float else 2,
        "tiled": True,
        "blockxsize": 256,
        "blockysize": 256,
        "BIGTIFF": "IF_SAFER",
    }


def resample_geotiff(
    input_path: Path,
    output_path: Path,
    resolution: float,
    compress: Optional[str] = "deflate",
    dry_run: bool = False,
    temp_dir: Optional[Path] = None,
) -> None:
    with rasterio.open(input_path) as src:
        left, bottom, right, top = src.bounds
        new_width, new_height = output_dimensions(src.bounds, resolution)
        new_transform = from_origin(left, top, resolution, resolution)

        profile = src.meta.copy()
        profile.update(
            {
                "height": new_height,
                "width": new_width,
                "transform": new_transform,
                **compression_profile(profile, compress),
            }
        )

        if dry_run:
            return

        output_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_root = temp_dir or output_path.parent
        tmp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="resize_", dir=str(tmp_root)) as tmp:
            local_out = Path(tmp) / output_path.name
            with rasterio.open(local_out, "w", **profile) as dst:
                for band in range(1, src.count + 1):
                    data = src.read(
                        band,
                        out_shape=(new_height, new_width),
                        resampling=Resampling.bilinear,
                    )
                    dst.write(data, band)
            output_path.write_bytes(local_out.read_bytes())


def process_one(
    input_path: Path,
    output_path: Path,
    resolution: float,
    compress: Optional[str],
    skip_existing: bool,
    dry_run: bool,
    temp_dir: Optional[Path],
) -> str:
    if skip_existing and output_path.exists() and not dry_run:
        return "skip"
    resample_geotiff(
        input_path,
        output_path,
        resolution,
        compress=compress,
        dry_run=dry_run,
        temp_dir=temp_dir,
    )
    return "ok"


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", required=True, help="Folder containing input GeoTIFFs")
    parser.add_argument("--output_folder", required=True, help="Folder to save resampled GeoTIFFs")
    parser.add_argument(
        "--resolution",
        type=float,
        default=0.1,
        help="Target resolution in meters per pixel (default: 0.1 = 10 cm)",
    )
    parser.add_argument(
        "--compress",
        default="deflate",
        help="GeoTIFF compression (default: deflate). Use '' or 'none' for uncompressed.",
    )
    parser.add_argument("--workers", type=int, default=4, help="Parallel workers (default: 4)")
    parser.add_argument(
        "--temp_dir",
        type=Path,
        default=None,
        help="Directory for temporary files during write (default: output_folder)",
    )
    parser.add_argument("--skip_existing", action="store_true", help="Skip existing outputs")
    parser.add_argument("--dry_run", action="store_true", help="Count jobs only, do not write")
    args = parser.parse_args(argv)
    setup_logging()

    compress = args.compress.strip().lower()
    if compress in ("", "none", "false"):
        compress = None

    in_folder = Path(args.folder)
    out_folder = Path(args.output_folder)
    tiffs = sorted(glob.glob(str(in_folder / "*.tif"))) + sorted(
        glob.glob(str(in_folder / "*.tiff"))
    )
    if not tiffs:
        log.error("No GeoTIFFs found in %s", in_folder)
        return 1

    log.info(
        "Resampling %d files: %s -> %s @ %.3f m/px compress=%s workers=%d",
        len(tiffs),
        in_folder,
        out_folder,
        args.resolution,
        compress,
        args.workers,
    )

    if not args.dry_run:
        out_folder.mkdir(parents=True, exist_ok=True)

    temp_dir = Path(args.temp_dir) if args.temp_dir else out_folder
    temp_dir.mkdir(parents=True, exist_ok=True)
    log.info("Using temp_dir=%s", temp_dir)

    jobs = [(Path(tif), out_folder / Path(tif).name) for tif in tiffs]

    n_ok = n_skip = n_fail = 0
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {
            pool.submit(
                process_one,
                inp,
                outp,
                args.resolution,
                compress,
                args.skip_existing,
                args.dry_run,
                temp_dir,
            ): inp
            for inp, outp in jobs
        }
        with tqdm(total=len(futures), desc="Resampling", unit="file") as pbar:
            for fut in as_completed(futures):
                inp = futures[fut]
                try:
                    status = fut.result()
                    if status == "skip":
                        n_skip += 1
                    else:
                        n_ok += 1
                except Exception as exc:  # noqa: BLE001
                    log.error("Failed %s: %s", inp.name, exc)
                    n_fail += 1
                pbar.update(1)

    log.info("Done: wrote=%d skipped=%d failed=%d", n_ok, n_skip, n_fail)
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
