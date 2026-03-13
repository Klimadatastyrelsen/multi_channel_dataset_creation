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

```bash
git clone https://github.com/rasmuspjohansson/multi_channel_dataset_creation.git
cd multi_channel_dataset_creation

conda env create -f environment.yml
conda activate multi-channel-env

# Install in editable mode so changes in the source code are reflected immediately
pip install -e .
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

