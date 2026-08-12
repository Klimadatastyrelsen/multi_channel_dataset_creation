import os
import sys
import inspect
currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))

sys.path.insert(0, currentdir)


import parse_ini
import create_patches
import create_txt_files
import move_data_to_separate_folders
import argparse
import time
import configparser
import geopackage_to_label_v2

def main(args):
    create_dataset_start_time = time.time()
    if not "move_data_to_separate_folders" in args.skip:
        print("#######################################")
        print("move_data_to_separate_folders")
        print("#######################################")
        #going from folder/a_name_DSM.tif , folder/a_name_OrtoCIR.tif ... to  DSM/a_name.tif , OrtoCIR/a_name.tif ..
        move_data_to_separate_folders.main(args = args)
    

    if (not "create_labels" in args.skip):
        print("#######################################")
        print("create_labels")
        print("#######################################")
        #convert the geopackage polygons to label images of same shape as the 'lod-images'
        parsed_ini_file = parse_ini.parse(args.dataset_config) # aprse the .ini file
        label_kwargs = dict(
            geopackage=parsed_ini_file["geopackage"],
            input_folder=parsed_ini_file["images_that_define_areas_to_create_labels_for"],
            output_folder=parsed_ini_file["mask_folder"],
            unknown_border_size=0.1,
            background_value=parsed_ini_file["background_value"],
            ignore_value=parsed_ini_file["ignore_id"],
        )
        if "value_used_for_all_polygons" in parsed_ini_file:
            label_kwargs["value_used_for_all_polygons"] = int(parsed_ini_file["value_used_for_all_polygons"])
        else:
            label_kwargs["attribute"] = parsed_ini_file["attribute"]
        geopackage_to_label_v2.process_label_generation_main(**label_kwargs)




    print("#######################################")
    print("create_patches") #splitting input data and label data can be stopped by including create_patches and split_labels in args.skip
    print("#######################################")
    #split the data and label-images up into smaler pathces e.g 1000x1000
    create_patches.main(config=args.dataset_config,skip = args.skip)

    if not "create_text_files" in args.skip:
        print("#######################################")
        print("create_text_files")
        print("#######################################")
        #divide the dataset into trainingset and validationset and save the split as all.txt, train.txt and valid.txt
        create_txt_files.main(config=args.dataset_config)

    create_dataset_end_time = time.time()
    print("################################################################################")
    print("create_dataset took: "+str(create_dataset_end_time-create_dataset_start_time ))
    print("################################################################################")
    print()
    print()

if __name__ == "__main__":
    usage_example= "python src\multi_channel_dataset_creation\create_dataset.py --dataset_config configs\create_dataset_example_dataset.ini --skip move_data_to_separate_folders create_labels create_patches split_labels create_text_files"
    # Initialize parser
    parser = argparse.ArgumentParser(
        epilog=usage_example,
        formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument("--dataset_config",help ="path to config.ini file e.g ..\..\configs\template_create_dataset.ini",required=True)
    parser.add_argument("--skip",help ="steps in the process to be skipped: move_data_to_separate_folders create_labels create_patches split_labels create_text_files",nargs ='+',default =[],required=False)
    args = parser.parse_args()
    main(args)
