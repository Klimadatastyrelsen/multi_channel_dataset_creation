#when splitting a trainingset into train and validation partitions it is important to be able to verify that the images in the two sets dont overlap
#this module provide this functionality

from osgeo import gdal, ogr, osr
import argparse
import sys
import numpy as np

# Enable exceptions so that failures (e.g. a file that cannot be opened) raise a
# clear error instead of silently returning None. This also silences GDAL's
# FutureWarning about the default changing in GDAL 4.0.
gdal.UseExceptions()
ogr.UseExceptions()



def geotiff_overlap(file1_path, file2_path):
    """
    :param file1_path:
    :param file2_path:
    :return: do the geotiff files overlap?
    """
    try:
        # Open the first GeoTIFF file
        dataset1 = gdal.Open(file1_path, gdal.GA_ReadOnly)

        # Open the second GeoTIFF file
        dataset2 = gdal.Open(file2_path, gdal.GA_ReadOnly)

        # Get the extent (bounding box) for the first dataset
        geo_transform1 = dataset1.GetGeoTransform()
        min_x1 = geo_transform1[0]
        max_x1 = min_x1 + geo_transform1[1] * dataset1.RasterXSize
        min_y1 = geo_transform1[3] + geo_transform1[5] * dataset1.RasterYSize
        max_y1 = geo_transform1[3]

        # Get the extent (bounding box) for the second dataset
        geo_transform2 = dataset2.GetGeoTransform()
        min_x2 = geo_transform2[0]
        max_x2 = min_x2 + geo_transform2[1] * dataset2.RasterXSize
        min_y2 = geo_transform2[3] + geo_transform2[5] * dataset2.RasterYSize
        max_y2 = geo_transform2[3]

        # Check if the extents overlap
        overlap = not (max_x1 < min_x2 or max_x2 < min_x1 or max_y1 < min_y2 or max_y2 < min_y1)

        return overlap

    except Exception as e:
        print(f"An error occurred: {str(e)}")
        sys.exit()



def shp_geotif_overlap(shp_layer, tiff_path):
    """
    :param shp_layer: an OGR layer (obtained from an already-opened shapefile
        data source, e.g. ``ogr.Open(path).GetLayer()``). Opening the shapefile
        once and reusing the layer avoids leaking a file handle on every call,
        which previously exhausted the OS file-descriptor limit part-way through
        a large folder.
    :param tiff_path: path to a GeoTIFF file.
    :return: do any of the envelopes of the polygons in the shapefile overlap
        with the geotiff (and does the overlap contain any non-zero pixels)?
    """
    # Open GeoTIFF file
    tiff_ds = gdal.Open(tiff_path)
    if tiff_ds is None:
        raise RuntimeError(f"Failed to open GeoTIFF: {tiff_path}")

    try:
        tiff_gt = tiff_ds.GetGeoTransform()
        tiff_band = tiff_ds.GetRasterBand(1)

        # Get extent of GeoTIFF
        tiff_cols = tiff_ds.RasterXSize
        tiff_rows = tiff_ds.RasterYSize
        tiff_extent = (
            tiff_gt[0],
            tiff_gt[0] + tiff_cols * tiff_gt[1],
            tiff_gt[3] + tiff_rows * tiff_gt[5],
            tiff_gt[3]
        )

        # Get spatial reference of GeoTIFF dataset
        tiff_srs = osr.SpatialReference()
        tiff_srs.ImportFromWkt(tiff_ds.GetProjectionRef())

        # Iterate the shapefile features fresh on every call
        shp_layer.ResetReading()

        # Check overlap
        for feature in shp_layer:
            shp_geom = feature.GetGeometryRef()
            shp_extent = shp_geom.GetEnvelope()

            # Check if the bounding boxes overlap
            if (
                    shp_extent[0] < tiff_extent[1] and
                    shp_extent[1] > tiff_extent[0] and
                    shp_extent[2] < tiff_extent[3] and
                    shp_extent[3] > tiff_extent[2]
            ):
                # Create a coordinate transformation
                coord_transform = osr.CoordinateTransformation(shp_geom.GetSpatialReference(), tiff_srs)

                # Transform a clone so we never mutate the layer's geometry
                shp_geom = shp_geom.Clone()
                shp_geom.Transform(coord_transform)

                # Get the transformed extent
                shp_geom_extent = shp_geom.GetEnvelope()

                # Ensure the transformed extent is within the valid range of the GeoTIFF
                min_x, max_x = max(shp_geom_extent[0], tiff_extent[0]), min(shp_geom_extent[1], tiff_extent[1])
                min_y, max_y = max(shp_geom_extent[2], tiff_extent[2]), min(shp_geom_extent[3], tiff_extent[3])

                if min_x < max_x and min_y < max_y:
                    # Read raster data for the overlapping area
                    tiff_window = tiff_band.ReadAsArray(
                        int((min_x - tiff_gt[0]) / tiff_gt[1]),
                        int((tiff_gt[3] - max_y) / -tiff_gt[5]),
                        int((max_x - min_x) / tiff_gt[1]),
                        int((max_y - min_y) / -tiff_gt[5])
                    )

                    # Check if there is any overlap in the pixel values
                    if np.any(tiff_window):
                        return True

        return False

    finally:
        # Release the raster handles so we don't leak file descriptors.
        tiff_band = None
        tiff_ds = None


if __name__ == "__main__":
    usage_example= "python overlap.py --image_1 images/a_geotif.image.tif --image_2 images/another_geotif.image.tif"
    # Initialize parser
    parser = argparse.ArgumentParser(
        epilog=usage_example,
        formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument("--image_1",help ="path to a geotif image ",required=True)
    parser.add_argument("--image_2",help ="path to a geotif image ",required=True)
    args = parser.parse_args()


    #### RUN ####
    if geotiff_overlap(file1_path=args.image_1, file2_path=args.image_2):
        print("The two GeoTIFF files overlap.")
    else:
        print("The two GeoTIFF files do not overlap.")
