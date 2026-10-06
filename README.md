# Multi-Channel Dataset Creation

Combine imagery, elevation data and labels (rgb, cir, OrtoRGB, OrtoCIR, DSM, DTM) into multi-channel patch datasets for semantic segmentation. Data and labels are cut into patches, and the split into train and valid takes geographical overlap into account. The datasets are used with [ML_sdfi_fastai2](https://github.com/SDFIdk/ML_sdfi_fastai2).

Related repos (same `ML_sdfi` environment): [ML_Production](https://github.com/SDFIdk/ML_Production), [ML_geo_production](https://github.com/SDFIdk/ML_geo_production), [ML_sdfi_fastai2](https://github.com/SDFIdk/ML_sdfi_fastai2).

## Installation

Clone the four repos as siblings and run from this repo root:

```sh
conda env create --file environment.yml   # once
conda activate ML_sdfi
bash install_pytorch.sh                   # picks the CUDA build; override with PYTORCH_CUDA=cu121
pip install --pre --no-build-isolation -r requirements_pip.txt
bash install_local_repos.sh
pip install -r requirements_extra.txt
```

On Windows, also run `pip install --force-reinstall pillow rasterio` once.

Docker alternative:

```sh
docker pull rasmuspjohansson/kds_cuda_pytorch:latest
docker run --gpus all --shm-size=100g -it -v /path/to/projects:/home/projects \
  -w /home/projects/multi_channel_dataset_creation rasmuspjohansson/kds_cuda_pytorch:latest bash
```

## Quickstart

Create a dataset from the included example data (no GPU needed):

```sh
python src/multi_channel_dataset_creation/create_dataset.py --dataset_config configs/create_dataset_example_dataset.ini
```

Check that it ran without errors:

```sh
python verify_functionality.py
python check_logs.py
```

## Download data for images

`download_data_for_images.py` creates OrtoRGB, OrtoCIR, DSM and DTM with the same extent and resolution as each input image. Each product has two sources:

- `*_datafordeler` downloads from the Datafordeler WMS/WCS. It needs an API key, read from `~/datafordelar_key.txt` by default (or passed with `--apikey` / `--apikey_file`).
- `*_vrt` cuts from local VRTs in `--vrt_dir`, with bilinear resampling. No key is needed.

Both sources write to the same subfolder (`OrtoRGB/`, `OrtoCIR/`, `DSM/`, `DTM/`), so only one source per product can be requested in a run.

```sh
python src/multi_channel_dataset_creation/download_data_for_images.py \
  --images_or_shapefile_defining_footprints example_dataset/data/rgb \
  --datatypes OrtoRGB_datafordeler OrtoCIR_datafordeler DSM_datafordeler DTM_datafordeler \
  --output_folder /tmp/downloads --skip_existing

python src/multi_channel_dataset_creation/download_data_for_images.py \
  --images_or_shapefile_defining_footprints example_dataset/data/rgb \
  --datatypes OrtoRGB_vrt OrtoCIR_vrt DSM_vrt DTM_vrt \
  --vrt_dir /mnt/T/mnt/trainingdata/test_data --output_folder /tmp/downloads
```

A shapefile can be used instead of an image folder; then `--resolution` is required. See `--help` for all options.

## Dataset layout

```
data/
  original_data/   image-X_rgb.tif, image-X_cir.tif, image-X_OrtoRGB.tif, image-X_DSM.tif, ...
  rgb/ cir/ OrtoRGB/ OrtoCIR/ DSM/ DTM/   image-X.tif
labels/
  large_labels/    image-X.tif
```

Files in `original_data/` are renamed and moved into the per-channel folders. If `original_data/` is empty, the existing per-channel folders are used. All channels must be georeferenced and aligned in the same coordinate system.

## Labels

Labels are polygons in a GeoPackage. `geopackage_to_label_v2.py` rasterizes them onto the grid of each image:

```sh
# Class from the ML_CATEGORY attribute; unlabeled areas become 0 (ignore)
python src/multi_channel_dataset_creation/geopackage_to_label_v2.py \
  --geopackage example_dataset/labels/example_dataset_ground_surface.gpkg \
  --input_folder example_dataset/data/rgb/ --output_folder example_dataset/labels/large_labels/ \
  --attribute ML_CATEGORY --background_value 0

# Every polygon becomes class 2 (building); unlabeled areas become class 1 (background)
python src/multi_channel_dataset_creation/geopackage_to_label_v2.py \
  --geopackage example_dataset/labels/example_dataset_buildings.gpkg \
  --input_folder example_dataset/data/rgb/ --output_folder example_dataset/labels/large_labels/ \
  --background_value 1 --value_used_for_all_polygons 2
```

For training, ML_sdfi_fastai2 needs a `codes.txt` with one class name per line, where line N (0-based) names pixel value N.

### Cleaning labels with newer ground truth

Labels for areas that changed between two GeoPackage versions can't be trusted. To mask them out, create one label set from the older GeoPackage and one from the newer, then compare them. Changed pixels are set to the ignore value (0):

```sh
python src/multi_channel_dataset_creation/data_cleaning_based_on_newer_ground_truth.py \
  --old_labels old_labels/ --new_labels new_labels/ --output cleaned_labels/ --output_csv changed_pixels.csv
```

## Data sources

- Orthophoto: [GeoDanmark Ortofoto](https://datafordeler.dk/dataoversigt/geodanmark-ortofoto/)
- Oblique images (ortho version): [LOD images](https://dataforsyningen.dk/data/1036)
- DSM and DTM: [Danmarks Højdemodel](https://datafordeler.dk/dataoversigt/danmarks-hoejdemodel-dhm/dhm-fildownload-raster/)
