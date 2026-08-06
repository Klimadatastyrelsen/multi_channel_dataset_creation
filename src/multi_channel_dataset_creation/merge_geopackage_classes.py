import geopandas as gpd
import argparse


def merge_classes_in_geopackage(src: str, dst: str, column_name: str = "ML_CATEGORY", merge_ids: str = "1,2,3,4,5,6,7,8", layer: str = "VindmoelleLabelTjek - bef"):
    """
    Args:
        src (str): Path to the source GeoPackage file.
        dst (str): Path to the destination GeoPackage file.
        column_name (str): Name of the column to merge classes in. Default is "ML_CATEGORY".
        merge_ids (str): Comma-separated list of merge IDs to merge into a single class
        layer (str): Name of the layer in the GeoPackage file.
    """

    # Read the GeoPackage file into a GeoDataFrame and drop rows with NaN values in the specified column
    gdf = gpd.read_file(src, layer = layer)
    gdf = gdf.dropna(subset=[column_name])
    gdf[column_name] = gdf[column_name].astype(int)

    merge_ids = {int(x) for x in merge_ids.split(",")}

    unique_values = gdf[column_name].unique()
    # ceck what values are present in the column
    num_unique_values = len(unique_values)
    print(f"Unique values in column '{column_name}': {num_unique_values}")
    print(f"Unique values: {sorted(unique_values)}")

    # Get the IDs not in merge_ids 
    other_ids = sorted(gdf[gdf[column_name].isin(merge_ids) == False][column_name].unique())
    print(f"Other IDs not in merge_ids: {other_ids}")

    # Merge the specified merge IDs into a single class (1) and remap the rest to fit     
    if 1 in merge_ids:
        # Merge the specified merge IDs into a single class (1) and remap the rest
        gdf.loc[gdf[column_name].isin(merge_ids), column_name] = 1
        if len(other_ids) > 0:
            print(f"Other IDs not in merge_ids: {other_ids}")
            n = 2
            # Remap the other IDs to a new class (e.g., 2)
            for other_id in other_ids:
                gdf.loc[gdf[column_name] == other_id, column_name] = n  # remap to new class
                print(f"Remapped ID {other_id} to {n}")
                n += 1
    else: 
        # if 1 is not in merge_ids, we can merge the specified merge IDs into a single class and remap the rest
        new_class_id = sorted(merge_ids)[0]
        gdf.loc[gdf[column_name].isin(merge_ids), column_name] = new_class_id
        if len(other_ids) > 0:
            print(f"Other IDs not in merge_ids: {other_ids}")
            n = 1
            # Remap the other IDs to a new class (e.g., 2)
            for other_id in other_ids:
                if new_class_id == n:
                    n += 1  # Skip the new class ID
                gdf.loc[gdf[column_name] == other_id, column_name] = n  # remap to new class
                print(f"Remapped ID {other_id} to {n}")
                n += 1

    # Save the modified GeoDataFrame to a new GeoPackage file
    gdf.to_file(dst, driver="GPKG")
    print(gdf[column_name].value_counts().sort_index())

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Merge classes from column into single class and remap the rest in a GeoPackage file.", 
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument("--geopackage_input", type=str, required=True, help="Path to the source GeoPackage file.")
    parser.add_argument("--geopackage_output", type=str, required=True, help="Path to the destination GeoPackage file.")
    parser.add_argument("--column_name", type=str, default="ML_CATEGORY", help="Name of the column to merge classes in.")
    parser.add_argument("--merge_ids", type=str, default="1,2,3,4,5,6,7,8", help="Comma-separated list of merge IDs to merge into a single class.")
    parser.add_argument("--layer", type=str, default="VindmoelleLabelTjek - bef", help="Name of the layer in the GeoPackage file.")

    args = parser.parse_args()

    merge_classes_in_geopackage(args.geopackage_input, args.geopackage_output, args.column_name, args.merge_ids, args.layer)