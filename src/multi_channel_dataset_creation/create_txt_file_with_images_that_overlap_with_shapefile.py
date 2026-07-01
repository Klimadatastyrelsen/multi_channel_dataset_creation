from osgeo import gdal
import argparse
import sys
import os
from multi_channel_dataset_creation import overlap
import pathlib
import geopandas as gpd
from rasterio.features import bounds
from shapely.geometry import box
from shapely.ops import unary_union
import rasterio
def get_extent_from_shapefile(shapefile):
    """Get the bounding box extent of a shapefile."""
    gdf = gpd.read_file(shapefile)
    return gdf.total_bounds  # [minx, miny, maxx, maxy]

def calculate_distance_to_extent_center(extent, geotiff_path):
    """Calculate the distance of a GeoTIFF's center to the center of the extent."""
    center_x = (extent[0] + extent[2]) / 2
    center_y = (extent[1] + extent[3]) / 2
    extent_center = (center_x, center_y)

    with rasterio.open(geotiff_path) as src:
        geotiff_center = ((src.bounds.left + src.bounds.right) / 2,
                          (src.bounds.top + src.bounds.bottom) / 2)
        return ((extent_center[0] - geotiff_center[0]) ** 2 +
                (extent_center[1] - geotiff_center[1]) ** 2) ** 0.5
def prune(extent, geotiffs):
    """
    Iteratively prune the list of GeoTIFFs. removes geotifs untill the merged extent not covers the extetn anymore .
    @arg extent crated with  gpd.read_file(shapefile).total_bounds  # [minx, miny, maxx, maxy]
    @arg geotifs a list with paths to geotiffs

    @return a new list with the pruned list of geotiffs


    """
    # Sort GeoTIFFs by distance to the center of the extent
    geotiffs = sorted(geotiffs, key=lambda path: calculate_distance_to_extent_center(extent, path), reverse=True)

    index = 0  # Start with the first GeoTIFF
    while index < len(geotiffs):
        # Create a new list by excluding the current GeoTIFF
        remaining_geotiffs = geotiffs[:index] + geotiffs[index+1:]
        # Merge remaining GeoTIFF extents
        merged_extent = unary_union([box(*rasterio.open(gt).bounds) for gt in remaining_geotiffs])

        # Check if the shapefile extent fits within the merged polygon
        if box(*extent).within(merged_extent):
            # Update the list to the pruned version and reset index to restart
            geotiffs = remaining_geotiffs
            index = 0  # Restart the pruning process
        else:
            # Move to the next GeoTIFF
            index += 1

    return geotiffs

def create_txt_file_with_files_overlapping_with_shp_file(shape_file,folder,output_txt,images_must_be_crops_of_these_images_path,prune_to_fewer_images):
    folder_path = pathlib.Path(folder)
    print(f"Listing all .tif/.tiff files under {folder} (recursive)...")
    tiff_files = [str(p) for p in folder_path.rglob("*.tif")]
    tiff_files.extend(str(p) for p in folder_path.rglob("*.tiff"))

    if images_must_be_crops_of_these_images_path:
        print("filtering away files that not are crops of the files listed in 'images_must_be_crops_of_these_images_path'")
        with open(images_must_be_crops_of_these_images_path, 'r') as file:
            # Read all lines into a list, stripping any trailing newline characters
            large_tiff_files = [line.strip() for line in file]
            #remove the .tif in order to get the part of the filename that also occurs in the crop
            large_tiff_files =[large_tiff_file.strip(".tif").split("/")[-1] for large_tiff_file in large_tiff_files]

            tiff_files_that_are_crops_of_set_of_larger_tiff_files = []
            for tiff_file in tiff_files:
                #e.g: remove the "_7000_2880.tif" part of "O2021_82_24_1_0020_00004289_7000_2880.tif"
                search_string = "_".join(tiff_file.split("_")[0:-2]).split("/")[-1]
                #input("search_string:"+str(search_string))
                #input("large_tiff_files[0]:"+str(large_tiff_files[0]))
                if search_string in large_tiff_files:
                    tiff_files_that_are_crops_of_set_of_larger_tiff_files.append(tiff_file)
        tiff_files = tiff_files_that_are_crops_of_set_of_larger_tiff_files




    print("filtering away geotiff files that dont overlap with .shp file...")
    nr_of_files = len(tiff_files)
    overlapping_tif_files = []
    checked_files=0
    for filepath in tiff_files:
        if overlap.shp_geotif_overlap(shp_path=shape_file,tiff_path=filepath):
             overlapping_tif_files.append(filepath)
        checked_files+=1
        print(f"\rPercent ready: {100*(checked_files/nr_of_files)}%", end="")
    if prune_to_fewer_images:
        print("pruning")
        extent= get_extent_from_shapefile(shape_file)
        overlapping_tif_files = prune(extent= extent, geotiffs=overlapping_tif_files)
    overlapping_tif_files = [file.split("/")[-1] for file in overlapping_tif_files]
    print("saving the filenames of all overlapping geotiffs to : "+str(output_txt)+ " ...")
    pathlib.Path(pathlib.Path(output_txt).parent).mkdir(parents=True, exist_ok=True)
    with open(output_txt, 'w') as f:
        f.write('\n'.join(overlapping_tif_files))








if __name__ == "__main__":
    usage_example= "python create_txt_file_with_images_that_overlap_with_shapefile.py --shapefile path/to/file.shp --folder path/to/images/ --output_txt path/to/filenames.txt"
    # Initialize parser
    parser = argparse.ArgumentParser(
        epilog=usage_example,
        formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument("--shapefile", required=True, help="Path to the shapefile.")
    parser.add_argument('--folder', help='Path to the root folder of the TIFF files.')
    parser.add_argument('--output_txt', help='Path to the txt were we should save all filenames')
    parser.add_argument('--images_must_be_crops_of_these_images_path',default = None, help='Path to a .txt file listing all unsplitted images that overlap with the .shp file. only images that are crops of these images can overlap with the .shp file')
    args = parser.parse_args()


    #### RUN ####
    create_txt_file_with_files_overlapping_with_shp_file(shape_file=args.shapefile,folder=args.folder,output_txt=args.output_txt,images_must_be_crops_of_these_images_path=args.images_must_be_crops_of_these_images_path,prune_to_fewer_images=False)
