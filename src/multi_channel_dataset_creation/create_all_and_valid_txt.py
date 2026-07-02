import os
from PIL import Image
import numpy as np
import pandas as pd
import argparse
import pathlib
import create_train_txt
import time
import shutil
import overlap
import random



def verify_all_files_exists(file_name,folder_path,other_data_folders =[]):
    all_files_exists = True


    for other_data_folder in  other_data_folders:
        if not (other_data_folder/file_name).is_file():
            all_files_exists = False
            #print("this file does not exist:"+str((other_data_folder/file_name)))
    #if no other data folders are used its enough that the initial file exists
    if not (pathlib.Path(folder_path)/file_name).is_file():
        all_files_exists = False
    #print("all_files_exists:"+str(all_files_exists))

    return all_files_exists



def remove_files_with_missing_labels_or_datasources(files_in_folder,other_data_folders,label_folder,remove_images_without_label):
    print("removing the files that are missing input data")
    if remove_images_without_label:
        print("removing the files that are missing input data or label data")
    images_that_have_all_datasources = []
    # keep track of how many images where missing label or were missing a datatype
    nr_of_images_missing_data = {label_folder: 0}
    for datatype_folder in other_data_folders:
        nr_of_images_missing_data[datatype_folder] = 0

    images_that_where_missing_datasource = []

    images_to_check = len(files_in_folder)
    images_checked = 0

    for x in files_in_folder:
        all_files_exists = True
        if remove_images_without_label:
            if not (pathlib.Path(label_folder) / x).is_file():
                nr_of_images_missing_data[label_folder] += 1
                all_files_exists = False
            elif np.array(Image.open((pathlib.Path(label_folder) / x))).sum() ==0:
                #if there are only zeros in the label we treat this as if the label is missing
                nr_of_images_missing_data[label_folder] += 1
                all_files_exists = False

        #we should always verify that all datasources are there
        for datasource_folder_to_check in other_data_folders:
            if not (pathlib.Path(datasource_folder_to_check) / x).is_file():
                nr_of_images_missing_data[datasource_folder_to_check] += 1
                all_files_exists = False

        if all_files_exists:
            images_that_have_all_datasources.append(x)
        else:
            images_that_where_missing_datasource.append(x)
        images_checked += 1
        create_train_txt.print_overwrite("checked " + str(images_checked) + " files out of " + str(images_to_check) + ", images_checked/images_to_check : " + str(images_checked / images_to_check))
    print()
    print("all files checked for missing label or datasource:")
    print("nr_of_images_missing_data : "+str(nr_of_images_missing_data))


    return images_that_have_all_datasources


def create_all_txt(folder_path,datatype,all_txt_filename,other_data_folders,label_folder,remove_images_without_label,text_file_listing_images_to_consider=None):
    """
    Create all.txt file with all image files included in the folder_path

    """
    #make sure the folder we want to save the txt file in exists
    pathlib.Path(all_txt_filename).parent.mkdir(parents=True, exist_ok=True)



 
    #folder_path=folder_path.replace("//","/")
    folder_path = pathlib.Path(folder_path)


    if text_file_listing_images_to_consider:
        with open(text_file_listing_images_to_consider, "r") as files_listed_in_txt_file:
            files_in_folder = [line.strip() for line in files_listed_in_txt_file.readlines()]
    else:
        #crate a list of image files
        files_in_folder =os.listdir(folder_path)

    files_in_folder = [x for x in files_in_folder if ((datatype in x )and (".xml" not in x ))]

    print("files in folder :"+str(len(files_in_folder)))

    #filter away files that are missing lables or datasources
    files= remove_files_with_missing_labels_or_datasources(files_in_folder,other_data_folders,label_folder,remove_images_without_label)

    print("files in folder that have labels and  also exists in "+str(other_data_folders)+" :" + str(len(files)))
    print("removed "+str(len(files_in_folder)-len(files)) +" nr of files")

    print("number of image files in all: " + str(len(files)))
    print("first image: "+str(files[0]))

    
    with open(all_txt_filename, 'w') as f:
        f.write('\n'.join(files))
    print("printed the filenames to the file : " + all_txt_filename)


def create_valid_txt(all_txt_filename,valid_txt_filename,pick_every):
    with open(all_txt_filename, 'r') as f:
        all_list = f.readlines()
        valid_list=[]
        for i in range(0,len(all_list),pick_every):
            valid_list.append(all_list[i].split("/")[-1])
        with open(valid_txt_filename, 'w') as f:
            f.write(''.join(valid_list))
            print("number of files in valid: " + str(len(valid_list)) + "  == "+str(100*len(valid_list)/len(all_list)) +" % of images in all_txt_file")

            print("first elements in valid_list : " + str(valid_list[0]))
            print("printed the valid filenames to the file : " + valid_txt_filename)


def remove_overlap_from_all_txt(path_to_all_txt,path_to_valid_txt,folder_path,images_must_be_crops_of_these_images_path):
    """
    create a all_without_overlap.txt file based on all_including_overlap.txt.txt and valid.txt
    files present in valid.txt should also be present in all.txt
    files(geotifs) in all_including_overlap.txt only partly overlapping with the files(geotifs) in valid.txt ,should not be present in all.txt
    @returns: all_without_operlap.txt

    1. find all files in all.txt that dont overlap with valid.txt
    2. combine those files with the files in valid.txt in all_without_overlap.txt
    """
    print("files where only parts of the image overlap with images in valid.txt are removed from all.txt , for a list of all files , look at all_including_overlap.txt ")

    create_all_without_overlap_txt_start = time.time()

    #save the old all.txt file in a new name so we can overwrite the old file
    path_to_all_including_overlap = pathlib.Path(str(path_to_all_txt).replace(".txt","including_overlap.txt"))
    shutil.copyfile(path_to_all_txt, path_to_all_including_overlap)

    path_to_all_txt = pathlib.Path(path_to_all_txt)
    path_to_valid_txt = pathlib.Path(path_to_valid_txt)

    train_files = []  # all files not present in valid.txt
    images_overlapping_with_images_in_validationset = []

    with open(path_to_all_including_overlap, "r") as all_files:
        all_lines = [line.strip() for line in all_files.readlines()]
        random.shuffle(all_lines)
    with open(path_to_valid_txt, "r") as valid_file:
        valid_lines = [line.strip() for line in valid_file.readlines()]

    if images_must_be_crops_of_these_images_path:
        #if we have .txt file that lists all large unsplitted .tif files that the crops must come from.
        #such a list can be created by listng all large files that intersect with the .shp
        with open(images_must_be_crops_of_these_images_path, 'r') as file:
            # Read all lines into a list, stripping any trailing newline characters
            large_tiff_files = [line.strip() for line in file]
            #remove the .tif in order to get the part of the filename that also occurs in the crop
            #also remove the parent folders

            large_tiff_files =[os.path.splitext(large_tiff_file)[0].split("/")[-1] for large_tiff_file in large_tiff_files]

    # for all files in the dataset (all.txt)
    nr_of_files = len(all_lines)
    finnished_file = 0
    for filename in all_lines:
        found_file = False
        found_overlapping_file = False
        search_for_overlap = True

        if images_must_be_crops_of_these_images_path:
            #e.g: remove the "_7000_2880.tif" part of "O2021_82_24_1_0020_00004289_7000_2880.tif"
            # if the trainingset set file is a croped version of any of the large tiff images that intersect with the validationset
            #then we should check for actuall overlaps

            #input("_".join(filename.split("_")[0:-2]))
            #input(large_tiff_files[0])
            if not ("_".join(filename.split("_")[0:-2]) in large_tiff_files):
                search_for_overlap = False
                print("dont search for overlap")
            else:
                search_for_overlap = True
                print("search for overlap")

        if search_for_overlap:
            # compare it to each file in valid.txt
            for validset_filename in valid_lines:
                # file in all.txt is present in valid.txt and should therfore not be present in train.txt
                if validset_filename in filename:
                    found_file = True
                    break

                # file in all.txt is overlapping with file in valid.txt and should therfore not be present in train.txt
                if overlap.geotiff_overlap(str(pathlib.Path(folder_path) / validset_filename),
                                           str(pathlib.Path(folder_path) / filename)):
                    found_overlapping_file = True
                    images_overlapping_with_images_in_validationset.append(filename)
                    break

        if (not found_file) and (not found_overlapping_file):
            train_files.append(filename)

        finnished_file += 1
        time_per_image = (time.time() - create_all_without_overlap_txt_start) / finnished_file
        create_train_txt.print_overwrite("create all_without_overlap.txt processed :" + str(finnished_file) + " out of :" + str(
            nr_of_files) + " estimated time left : " + str(
            (time_per_image * (nr_of_files - finnished_file)) / 60) + " minutes")

    print()  # go to a new line since the last print did not do this
    print("found : " + str(len(
        images_overlapping_with_images_in_validationset)) + " files that not were present in valid.txt but overlapped with files in valid.txt")

    # write the files with overlap with valid.txt to "tmp_debug_overlapping_files.txt in same folder as all.txt in order to be able to check them manually"
    with open(pathlib.Path(path_to_all_txt).parent/"tmp_debug_overlapping_files.txt", "w") as overlap_file:
        overlap_file.write.write("\n".join(images_overlapping_with_images_in_validationset))


    # write the files without overlap with valid.txt and the files in valid.txt to path_to_all_wihout_overlap
    with open(path_to_all_txt, "w") as no_overlap_file:
        no_overlap_file.write("\n".join(train_files))
        no_overlap_file.write("\n")
        no_overlap_file.write("\n".join(valid_lines))

    print("creating " + str(path_to_all_txt) + " took: " + str(
        (time.time() - create_all_without_overlap_txt_start) / 60) + ", minutes")
    return path_to_all_txt

def create_all_and_valid(all_txt_filename,valid_txt_filename,path_to_training_images,datatype,nr_of_images_between_validation_samples,other_data_folders,label_folder,remove_images_without_label ,remove_overlap,use_fixed_validation_set,images_must_be_crops_of_these_images_path,text_file_listing_images_to_consider):
    if images_must_be_crops_of_these_images_path in ["False","None","false"]:
        images_must_be_crops_of_these_images_path = False

    create_all_txt(folder_path=path_to_training_images,datatype=datatype,all_txt_filename=all_txt_filename,other_data_folders=other_data_folders,label_folder=label_folder,remove_images_without_label=remove_images_without_label,text_file_listing_images_to_consider=text_file_listing_images_to_consider)
    #we use a fixed validation set in order to easier be able to compare results between runs
    if not use_fixed_validation_set:
        create_valid_txt(all_txt_filename=all_txt_filename,valid_txt_filename=valid_txt_filename,pick_every=nr_of_images_between_validation_samples)
    if remove_overlap:
        print("removing the geotifs in "+str(all_txt_filename)+" that partly overlap with those in :"+str(valid_txt_filename))
        remove_overlap_from_all_txt(path_to_all_txt=all_txt_filename,path_to_valid_txt=valid_txt_filename,folder_path=path_to_training_images,images_must_be_crops_of_these_images_path=images_must_be_crops_of_these_images_path)
    else:
        print(str(all_txt_filename)+ " contains all images")
if __name__ == "__main__":
    usage_example="example usage: \n "+r"python create_all_and_valid_txt.py -f /mnt/trainingdata-disk/trainingdata/RoofTopOrto/path/to/splitted/rgb -a /mnt/trainingdata-disk/trainingdata//RoofTopOrto/esbjergplusplus/all.txt  -v  /mnt/trainingdata-disk/trainingdata//RoofTopOrto/esbjergplusplus/valid.txt -p 17 -d .tif --other_data_folders path/to/splitted/cir path/to/splitted/DSM path/to/splitted/DTM path/to/splitted/OrtoCIR path/to/splitted/OrtoRGB"
    # Initialize parser
    parser = argparse.ArgumentParser(
                                    epilog=usage_example,
                                    formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument("-f", "--Folder_path", help="path to dataset folder",required=True)
    parser.add_argument("-l", "--label_folder", help="path to labelfolder", required=True)

    parser.add_argument("-a", "--All_filename", help="all.txt filename .eg 'esbjerg++_all.txt'  -> esbjer++_all.txt and 'esbjerg++_all.xlsx'",required=True)
    parser.add_argument("-v", "--Valid_filename", help=".eg -v valid.txt",required=True)
    parser.add_argument("-d", "--Datatype", help=".eg -d .tif",required=True)
    parser.add_argument("-p", "--nr_of_images_between_validation_samples",type = int,default = 17, help=".eg pick every 17 when creating a validation set: -p 17",required=False)
    parser.add_argument("--other_data_folders", help="e.g T:\trainingdata\befastelse\ten_channels_1\data\splitted\cir T:\trainingdata\befastelse\ten_channels_1\data\splitted\DSM T:\trainingdata\befastelse\ten_channels_1\data\splitted\DTM T:\trainingdata\befastelse\ten_channels_1\data\splitted\OrtoCIR T:\trainingdata\befastelse\ten_channels_1\data\splitted\OrtoRGB", nargs='+', default=[],required=False)
    parser.add_argument("--remove_images_without_label", action='store_true',help= "use this if you want to remove images  without labels from the all.txt and valid.txt files")
    parser.add_argument("--use_fixed_validation_set", action='store_true',
                        help="use this if you want to use an existing text file as valid.txt instead of creating one dynamically")
    parser.add_argument("--remove_overlap", action='store_true',
                        help="use this if you want to remove images  from all.txt and train.txt that partly overlap with images in valid.txt")
    #quickly filter away all images that not are crops of the images listed in this txt file
    parser.add_argument('--images_must_be_crops_of_these_images_path', help='Path to a .txt file listing all unsplitted images that overlap with the .shp file. only images that are crops of these images can overlap with the .shp file')

    parser.add_argument("--text_file_listing_images_to_consider", default = None,
                        help="e.g subset_all.txt, use this if you want to use a txt file listing images to consider instead of listing the files that exists in one of the inputdata folders")






    
    
    args = parser.parse_args()

    create_all_and_valid(all_txt_filename =args.All_filename,valid_txt_filename=args.Valid_filename,path_to_training_images=args.Folder_path,datatype=args.Datatype,nr_of_images_between_validation_samples=args.nr_of_images_between_validation_samples,other_data_folders=[pathlib.Path(folder_path) for folder_path in args.other_data_folders],remove_images_without_label=args.remove_images_without_label,use_fixed_validation_set=args.use_fixed_validation_set,label_folder =args.label_folder,remove_overlap=args.remove_overlap,images_must_be_crops_of_these_images_path=args.images_must_be_crops_of_these_images_path,text_file_listing_images_to_consider=args.text_file_listing_images_to_consider)

