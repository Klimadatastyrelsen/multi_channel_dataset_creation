#usage .    first create a .txt file containing all file_names of the files you want to copy. e.g with create_txt_file_with_images_that_overlap_with_shapefile.py
#           then use this script to copy all files with those names from a folder to another
#           .eg 1. create txt_file copy from rgb folder to another rgb folder , copy from one cir folder to anotehr , copy from one label folder to another
#           the fileformat can optioally be changed (if we for instance need to change from .tif to .jpg)
import os
import pathlib
import shutil
from PIL import Image
def copy_files_to_folder(text_file,origin_folder,destination_folder,new_image_format):
    """
    :param text_file:
    :param origin_folder:
    :param destination_folder:
    :return:
    """
    origin_folder = pathlib.Path(origin_folder)
    destination_folder = pathlib.Path(destination_folder)
    os.makedirs(destination_folder, exist_ok = True)
    with open(text_file) as f:
        #in order to make sure we only have the name of the file and not a complete filepath ,we do: pathlib.Path(line.rstrip()).name
        listed_names = [pathlib.Path(line.rstrip()).name for line in f if line.rstrip()]

    nr_listed = len(listed_names)
    print("copying the images noted in " +str(text_file)+ " from :"+str(origin_folder) +" to "+str(destination_folder) +"...")

    nr_copied = 0
    for name in listed_names:
        source_file = origin_folder / name
        # Only copy files that actually exist in the source folder, so files
        # listed in the .txt but living in another folder are skipped instead
        # of crashing the run.
        if not source_file.is_file():
            continue
        if new_image_format:
            im = Image.open(source_file)
            im.save(destination_folder/source_file.with_suffix(new_image_format).name)
        else:
            # Copy the file
            shutil.copyfile(source_file, destination_folder/source_file.name)
        nr_copied += 1

    print("done copying the images noted in " +str(text_file)+ " from :"+str(origin_folder) +" to "+str(destination_folder) )
    print(f"copied {nr_copied} out of {nr_listed} files listed in {text_file}")



if __name__ == "__main__":
    example_usage= r"python copy_files_listed_in_txt_file.py --text_file --folder --new_folder"
    print("########################EXAMPLE USAGE########################")
    print(example_usage)
    print("#############################################################")
    import argparse

    # Initialize parser
    parser = argparse.ArgumentParser()

    parser.add_argument("-t", "--text_file", help="path/to/text_file.txt ",required=True, type=pathlib.Path)

    parser.add_argument("-f", "--folder", help="path/to/folder  e.g path/to/images",required=True,type=pathlib.Path)
    parser.add_argument("-n", "--new_folder", help="path/to/folder  e.g path/to/new_folder",required=True,type=pathlib.Path)

    parser.add_argument("--New_Image_format", help="e.g .jpg",default=None,required=False)


    args = parser.parse_args()

    print("copying images")
    copy_files_to_folder(text_file=args.text_file,origin_folder=args.folder,destination_folder= args.new_folder,new_image_format =args.New_Image_format )
