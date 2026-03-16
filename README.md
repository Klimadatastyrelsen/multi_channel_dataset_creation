# Multi-Channel Dataset Creation for Semantic Segmentation

Use this repository to create semantic segmentation datasets made up of multiple different modalities into a unified multi-channel datasets.
E.g by combining imagery and LiDAR data.

Data and labels are cut into patches and dataset is divided into train and test/valid subsets while taking geographical overlap into consideration.
Code supports conversion of labeled polygons stored in GeoPackage files into GeoTIFF label images.  

The resulting datasets can be used for training and inference with [ML_sdfi_fastai2](https://github.com/SDFIdk/ML_sdfi_fastai2).

---

## Data Sources

The accompanying "example_dataset" combines the following georeferenced layers:

- **Orthophoto:** [GeoDanmark Orthophoto](https://datafordeler.dk/dataoversigt/geodanmark-ortofoto/)  
- **Oblique Camera (Ortho Version):** [LOD Images](https://dataforsyningen.dk/data/1036)  
- **Digital Terrain Model (DTM):** [Danmarks Højdemodel – DHM Raster Download](https://datafordeler.dk/dataoversigt/danmarks-hoejdemodel-dhm/dhm-fildownload-raster/)  
- **Digital Surface Model (DSM):** [Danmarks Højdemodel – DHM Raster Download](https://datafordeler.dk/dataoversigt/danmarks-hoejdemodel-dhm/dhm-fildownload-raster/)  

---

## Example Folder Structure

```
training_dataset/
  labels/
    large_labels/
      image-x.tif
  data/
    original_data/
      image-X_rgb.tif
      image-X_cir.tif
      image-X_OrtoRGB.tif
      image-X_OrtoCIR.tif
      image-X_DSM.tif
      image-X_DTM.tif
    rgb/
      image-X.tif
    cir/
      image-X.tif
    OrtoRGB/
      image-X.tif
    OrtoCIR/
      image-X.tif
    DSM/
      image-X.tif
    DTM/
      image-X.tif
```

Images located in the `original_data` folder will be renamed and distributed into the appropriate subfolders (`rgb`, `cir`, `OrtoRGB`, `OrtoCIR`, `DSM`, `DTM`).  
If `original_data` is empty, the tool will use existing images from these subfolders.

---

## Labels

Labels should be provided as **GeoPackages** containing polygon features marking different semantic areas.  
These will be rasterized into GeoTIFF label images during dataset creation.

---

## Installation

### Conda version

Use **conda** or **mamba** (Miniforge includes conda; mamba is optional). From this repository root (or from a parent folder where all four shared-env repos are cloned as siblings):

```sh
conda env create --file environment.yml
conda activate ML_sdfi
pip install --pre --no-build-isolation -r requirements_pip.txt
```

This installs PyTorch nightly with CUDA 12.8 (for NVIDIA Blackwell / RTX 50-series / sm_120 GPUs), fastai, git-based deps, and this package in editable mode.

To install the other shared-env repos and extra deps, from the **project root** (parent of all four repos):

```sh
cd ML_Production && bash install_local_repos.sh && pip install -r requirements_extra.txt && cd ..
```

**Other GPUs:** To use stable PyTorch instead of nightly (e.g. cu121), after the steps above run:

```sh
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

(Adjust `cu121` to your CUDA version; see [pytorch.org/get-started/locally](https://pytorch.org/get-started/locally).)

**Use conda's libstdc++ (Linux):** On some Linux systems, set this before running Python:

```sh
export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$LD_LIBRARY_PATH
```

**Verify CUDA support:**

```sh
python -c "import torch; print('CUDA available:', torch.cuda.is_available()); print('Device:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'N/A')"
```

**Windows:** After the steps above, run once: `pip install --force-reinstall pillow rasterio` so PIL and rasterio use pip's Windows wheels.

### Docker version

Pull the prebuilt shared image and run with this repo as working directory:

```bash
docker pull rasmuspjohansson/kds_cuda_pytorch:latest

docker run --gpus all --shm-size=100g -it \
  -v /path/to/your/projects:/home/projects \
  -w /home/projects/multi_channel_dataset_creation \
  rasmuspjohansson/kds_cuda_pytorch:20260302 \
  bash
```

To have all four shared-env repos installed in the container, run once from ML_Production (e.g. with `-w /home/projects/ML_Production` and `sh install_local_repos.sh && pip install -r requirements_extra.txt`). Then use `-w /home/projects/multi_channel_dataset_creation` for this repo.

Example after setup:

```bash
python src/multi_channel_dataset_creation/create_dataset.py --dataset_config configs/create_dataset_example_dataset.ini
```

---

## Usage

A small example dataset is included with this repository.  
You can generate a dataset using the example configuration:

```bash
python src/multi_channel_dataset_creation/create_dataset.py   --dataset_config configs/create_dataset_example_dataset.ini
```

To see all available options:

```bash
python src/multi_channel_dataset_creation/create_dataset.py -h
```

Creating label Images from a GeoPackage can be done with

```bash
Example with not labeled areas marked up as ignore_label (background_value == 0)
python src/multi_channel_dataset_creation/geopackage_to_label_v2.py   --geopackage example_dataset/labels/example_dataset_ground_surface.gpkg   --input_folder example_dataset/data/rgb/   --output_folder example_dataset/labels/large_labels/   --attribute ML_CATEGORY --background_value 0

Example with all polygons interpreted as label 2 (value_used_for_all_polygons == 2) and unlabeled areas interprted as background class 1 (background_value == 1)

python src/multi_channel_dataset_creation/geopackage_to_label_v2.py   --geopackage example_dataset/labels/example_dataset_buildings.gpkg   --input_folder example_dataset/data/rgb/   --output_folder example_dataset/labels/large_labels   --background_value 1 --value_used_for_all_polygons 2
```

Cleaning labels can be done by 

1. create labels based on geopackage older than the data
2. create labels based on geopackage newer than the data
3. create cleaned labels based on the old and new labels
python src/multi_channel_dataset_creation/data_cleaning_based_on_newer_ground_truth.py --old_labels dir_with_olod_labels --new_labels dir_with_new_labels --output dir_with_cleaned_labels
Labels that have changed in this time interval should not be trrusted and are set to ingore value (0)

## Verify that everything works

Do the installation acording to instructions above
run 

python src/multi_channel_dataset_creation/create_dataset.py   --dataset_config configs/create_dataset_example_dataset.ini

There should be no error messages in output

---

## 📘 Notes

- The tool is designed for geospatial datasets with consistent coordinate systems.  
- Each channel (RGB, CIR, OrthoRGB, OrthoCIR, DSM, DTM) should be aligned and georeferenced properly before processing.

---

