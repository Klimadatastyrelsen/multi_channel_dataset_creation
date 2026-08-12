import split
from pathlib import Path
import configparser
import argparse
import shutil
import json
import time
import sys



def clear_folder(folder_path):
    # remove the destination folder and create it anew
    print("emptying the folder: "+str(folder_path) + ",start")
    try:
        if Path(folder_path).exists() and Path(folder_path).is_dir():
            shutil.rmtree(Path(folder_path))
    except:
        sys.exit("failed to clear the folder :"+str(folder_path)+ " , the folder ,a subfolder or a file in the folder might be open by a program of file browser!")
    time.sleep(2)
    Path(folder_path).mkdir(parents=True, exist_ok=True)
    print("emptying the folder: " + str(folder_path)+ " ,done")


def main(config,skip):
    ini_parser = configparser.ConfigParser()
    ini_parser.read(config)
    section = "SETTINGS"





    tile_size_y = ini_parser[section]["tile_size_y"]
    tile_size_x = ini_parser[section]["tile_size_x"]
    overlap = ini_parser[section]["overlap"]

    ignore_id = int(ini_parser[section]["ignore_id"])


    #handle label masks
    if "mask_folder" in ini_parser[section] and not "split_labels" in skip:
        print("########################################################")
        print("dataset includes label masks that should be splitted")
        large_masks_folder = ini_parser[section]["mask_folder"]
        splitted_mask_folder = ini_parser[section]["splitted_mask_folder"]
        print("splitting the labels in "+str(large_masks_folder)+"and string them in folder :"+str(splitted_mask_folder))


        #remove the destination folder and create it anew
        clear_folder(splitted_mask_folder)


        splitf = split.Split()
        splitf.splitdst(in_path=large_masks_folder, out_path=splitted_mask_folder, tile_size_x=int(ini_parser[section]["tile_size_x"]),tile_size_y=int(ini_parser[section]["tile_size_y"]),kun_ok_pic=False,ignore_id=ignore_id,cutdatatype="mask_NaN",overlap=int(overlap))
    elif "split_labels" in skip:
        print("skipping 'split_labels'")
    else:
        print("dataset does NOT include any label masks")

    if not "create_patches" in skip:

        # handle input data
        datatypes =json.loads(ini_parser[section]["datatypes"])
        data_folders_parent_directory =Path(ini_parser[section]["data_folder"])
        data_folders = [data_folders_parent_directory / datatype for datatype in datatypes]
        splitted_data_folders_parent_directory = Path(ini_parser[section]["splitted_data_parent_folder"])
        for data_folder in data_folders:
            splitted_folder = splitted_data_folders_parent_directory/data_folder.name
            print("########################################################")
            print("splitting the data in "+str(data_folder)+", and storing them in folder :"+str(splitted_folder))

            # remove the destination folder and create it anew
            clear_folder(splitted_folder)


            splitf = split.Split()
            if data_folder.name  in ["OrtoRGB","rgb","OrtoCIR","cir"]:
                cutdatatype = "photo"
            elif ["DSM","DTM"]:
                cutdatatype = "single_channel"
            else:
                sys.exit("dont know how to splitt data of type :"+str(data_folder.name))
            failed_files = splitf.splitdst(in_path=data_folder, out_path=splitted_folder, tile_size_x=int(tile_size_x), tile_size_y=int(tile_size_y),kun_ok_pic=False,ignore_id=ignore_id,cutdatatype=cutdatatype,stop_on_error=False,overlap=int(overlap))
            if len(failed_files)>0:
                print("###############################################################")
                print("failed to split the following files: "+str(failed_files))
                print("###############################################################")




if __name__ == "__main__":
    usage_example="example usage: \n "+r"python create_patches.py --config path\to\file.ini"
    # Initialize parser
    parser = argparse.ArgumentParser(
        epilog=usage_example,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-c", "--config", help="one or more paths to config file",required=True)
    args = parser.parse_args()
    main(args.config,skip={})



