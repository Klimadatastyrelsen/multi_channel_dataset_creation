# import cv2
from configparser import ConfigParser
import logging
import os
from osgeo import gdal
import numpy as np
from PIL import Image
import argparse
import multiprocessing as mp
import time
_all__ = ["split"]

_logger = logging.getLogger(__name__)


def _split_one_file_worker(pair):
    """Module-level worker so multiprocessing spawn can pickle it."""
    start_time = time.time()
    (nr_of_files, index, in_path, out_path, filename, tile_size_x, tile_size_y, cutdatatype, kun_ok_pic, ignore_id, overlap) = pair
    print(f"Processing file : {filename} , nr: {index} , out of: {nr_of_files}")
    try:
        os.environ.setdefault("GDAL_NUM_THREADS", "1")
        Split().splitfile(
            in_path, out_path, filename, tile_size_x, tile_size_y, cutdatatype,
            kun_ok_pic=kun_ok_pic, nodata=ignore_id, overlap=overlap,
        )
        elapsed_min = (time.time() - start_time) / 60.0
        print(f"Done Processing file : {filename} ,took {elapsed_min} , minutes ")
        return {"ok": True, "filename": filename, "elapsed_min": elapsed_min, "index": index}
    except Exception as e:
        print(f"FAILED Processing file : {filename} : {e}")
        return {"ok": False, "filename": filename, "error": str(e), "index": index}


class Split():
    def __init__(self):
        pass
    def helper_function(self,pair):
        return _split_one_file_worker(pair)
    '''
    dont use this !!
    def split(in_path, out_path, tile_size_x, tile_size_y, kun_ok_pic=False, centrer_opklip=False,
              cutdatatype="oldstyle", srs="EPSG:25832", nodata=255,nr_of_processes=8):
        """splittgin files with gdal on """+str(nr_of_processes)+""" worker threads in paralell"""

        print("Proceeding: {}".format(in_path))
        # TODO: check path exist
        print("Out path  : {}".format(out_path))
        filelist = self.getfiles(in_path)
        filelist.sort()
        print("{} files (all types)".format(len(filelist)))



        # Create a pool of worker processes
        print("creating pool of : " +str(int(nr_of_processes))+ " nr of processes")
        pool = mp.Pool(processes=int(nr_of_processes))

        # Use pool.map to parallelize the loop
        pool.map(self.helper_function, [(in_path, out_path,filename,tile_size_x, tile_size_y, kun_ok_pic, centrer_opklip,
                           cutdatatype, srs, nodata) for filename in filelist])

        # Close and join the pool to free up resources
        pool.close()
        pool.join()
    '''


    def split(self, in_path, out_path, tile_size_x, tile_size_y, kun_ok_pic=False, centrer_opklip=False,
              cutdatatype="oldstyle", srs="EPSG:25832", nodata=255):
        print("Proceeding: {}".format(in_path))
        # TODO: check path exist
        print("Out path  : {}".format(out_path))
        filelist = self.getfiles(in_path)
        filelist.sort()
        print("{} files (all types)".format(len(filelist)))
        for filename in filelist:
            # if filename < '2021_85_50_04_0287.tif':
            #    continue
            self.splitfile(in_path, out_path, filename, tile_size_x, tile_size_y, kun_ok_pic, centrer_opklip,
                           cutdatatype, srs, nodata)

    '''
    def splitdst(self, in_path, out_path, tile_size_x, tile_size_y,cutdatatype,kun_ok_pic=False,ignore_id=0,stop_on_error=True,overlap=0):
        filelist = self.getfiles(in_path)
        filelist.sort()
        failed_files = []
        for (index,filename) in enumerate(filelist):
            print("working on image nr: "+str(index) + " out of : "+str(len(filelist)))

            if stop_on_error:
                self.splitfile(in_path, out_path, filename, tile_size_x, tile_size_y,cutdatatype,kun_ok_pic=kun_ok_pic,nodata=ignore_id,overlap=overlap)
            else:
                try:
                    self.splitfile(in_path, out_path, filename, tile_size_x, tile_size_y, cutdatatype,
                                   kun_ok_pic=kun_ok_pic, nodata=ignore_id,overlap=overlap)
                except:
                    failed_files.append(in_path)
        return failed_files
    '''


    def splitdst(self, in_path, out_path, tile_size_x, tile_size_y,cutdatatype,kun_ok_pic=False,ignore_id=0,stop_on_error=True,overlap=0,nr_of_processes=1):
        filelist = self.getfiles(in_path)
        nr_of_files = len(filelist)
        filelist.sort()
        failed_files = []
        if nr_of_processes>1:

            # Create a pool of worker processes
            print("creating pool of : " +str(int(nr_of_processes))+ " nr of processes")
            jobs = [[nr_of_files,index,in_path, out_path, filename, tile_size_x, tile_size_y,cutdatatype,kun_ok_pic,ignore_id,overlap] for (index,filename) in enumerate(filelist)]
            # fork on Linux: spawn re-imports __main__ and breaks runpy/stdin runners
            ctx = mp.get_context("fork")
            with ctx.Pool(processes=int(nr_of_processes), maxtasksperchild=8) as pool:
                results = pool.map(_split_one_file_worker, jobs, 1)
            failed_files = [r["filename"] for r in results if not r.get("ok")]
        else:
            for (index,filename) in enumerate(filelist):
                print("working on image nr: "+str(index) + " out of : "+str(len(filelist)))
                result = _split_one_file_worker(
                    [nr_of_files, index, in_path, out_path, filename, tile_size_x, tile_size_y, cutdatatype, kun_ok_pic, ignore_id, overlap]
                )
                if not result.get("ok"):
                    if stop_on_error:
                        raise RuntimeError(result.get("error", "splitfile failed"))
                    failed_files.append(filename)
        return failed_files


    def splitfile(self, in_path, out_path, filename, tile_size_x, tile_size_y,cutdatatype, kun_ok_pic=False, centrer_opklip=False,srs="EPSG:25832", nodata=255,overlap =0,debug=False):
        """
        @ arg kun_ok_pic: Hvis True undgå masker/pic,  der ikke bliver fuld dækket af det oprindelige billede.
        @ arg centrer_opklip: Hvis True center opklippene om omkring midten af det oprindelige billede/mask.
        parm: cutdatatype: setup to type of data/type cut u  (i.e. photo or mask_NaN)
        parm: srs: Geo. ref. system
        parm: nodata: Value for nodata (NaN etc.)
        """
        sub_tiles = 0
        if filename.upper().endswith('.PNG') or filename.upper().endswith('.JPG') or filename.upper().endswith('.TIF'):
            print('File to be splitted: ', filename)
            basename = os.path.splitext(filename)[0]
            extension = os.path.splitext(filename)[1]
            inputfilepath = os.path.join(in_path, filename)
            ds = gdal.Open(inputfilepath)
            band = ds.GetRasterBand(1)
            xsize = band.XSize
            ysize = band.YSize
            ds = None
            if debug:
                print("Xsize={} Ysize={}".format(xsize, ysize))
            """
            for i in range(0, xsize, tile_size_x):
                for j in range(0, ysize, tile_size_y):
                    com_string = "gdal_translate -srcwin " + str(i) + ", " + str(j) + ", " + str(
                        tile_size_x) + ", " + str(tile_size_y) + " " + str(inputfilepath) + " " + str(
                        outputfilepath) + str(i) + "_" + str(j) + ".png"
                    #print(com_string)
                    os.system(com_string)
            """
            if debug:
                print("kun_ok_pic={}  centrer_opklip={}".format(kun_ok_pic, centrer_opklip))
            # Juster opklipningen så den ligger i centrum af billede
            if centrer_opklip:
                #TODO: skal testes og prøves af
                xdelta = xsize % tile_size_x // 2
                ydelta = ysize % tile_size_y // 2
            else:
                xdelta, ydelta = 0, 0
            # Udregn hvornår opklipningen stopper
            if kun_ok_pic:
                # drop de sidste tiles der mangler fulde data
                xstop = xsize + 1 - tile_size_x
                ystop = ysize + 1 - tile_size_y
            else:
                xstop, ystop = xsize, ysize

            # Controlling extra gdal options
            gdal_old_style = ' -a_srs EPSG:25832 -co TILED=YES -co PHOTOMETRIC=RGB -co COMPRESS=LZW '
            gdal_opt = ""


            if cutdatatype == "photo":
                # Standar arial photo
                gdal_opt = " -a_srs {} -co TILED=YES -co PHOTOMETRIC=RGB -co COMPRESS=LZW ".format(srs)
            elif cutdatatype == "single_channel":
                # float 32 single channel data (DTM or DSM)
                gdal_opt = " -a_srs {} -co TILED=YES -co PHOTOMETRIC=MINISBLACK -co COMPRESS=LZW ".format(srs)


            elif cutdatatype == "mask_NaN":
                # Standart mask with cut up at edge with missing data(from in photo)
                if kun_ok_pic: print("Warning: Not correct cutdatatype when kun_ok_pic=True")
                gdal_opt = " -a_srs {} -co TILED=YES -co PHOTOMETRIC=MINISBLACK -co COMPRESS=LZW".format(srs) + \
                               " -a_offset {} -a_nodata {}".format(nodata, nodata)
                # print(' -a_srs EPSG:25832 -co TILED=YES -co PHOTOMETRIC=MINISBLACK -co COMPRESS=LZW -a_offset 255 -a_nodata 255 ') #  move to test assert!

            elif cutdatatype == "mask":
                # Standart mask - ALl data not cut at edge (not NaN)
                if not kun_ok_pic: print("Warning: Not correct cutdatatype when kun_ok_pic=False")
                gdal_opt = " -a_srs {} -co TILED=YES -co PHOTOMETRIC=MINISBLACK -co COMPRESS=LZW ".format(srs)
                # print(' -a_srs EPSG:25832 -co TILED=YES -co PHOTOMETRIC=MINISBLACK -co COMPRESS=LZW ')  # move to test assert!

            elif cutdatatype == "mask_binary":
                # old style for adding mask later
                if not kun_ok_pic: print("Warning: Not correct cutdatatype when kun_ok_pic=False")
                gdal_opt = " -a_srs {} -co TILED=YES -co PHOTOMETRIC=MINISBLACK -co COMPRESS=LZW ".format(srs) + \
                               " -a_offset {} -a_nodata {}".format(3, 3)
                # print(' -a_srs EPSG:25832 -co TILED=YES -co PHOTOMETRIC=MINISBLACK -co COMPRESS=LZW ')  # move to test assert!

            elif cutdatatype == "oldstyle":
                # as before :-)
                gdal_opt = gdal_old_style
                print("Warning: You are running oure old style gdal extra parameters!")
            else:
                print("Warning: Missing/unknown  par: cutdatatype ")
                return
            if debug:
                print("Extra gdal options (cutdatatype={}): \n{}".format(cutdatatype, gdal_opt))

            #in order to get overlap between the images we only step with tile_size -overlap
            for i in range(0 + xdelta, xstop, (tile_size_x-overlap)):
                for j in range(0 + ydelta, ystop, (tile_size_y-overlap)):
                    #com_string = "gdal_translate -srcwin " + str(i) + ", " + str(j) + ", " + str(
                    #    tile_size_x) + ", " + str(tile_size_y) + " " + str(inputfilepath) + " " + str(
                    #    out_path) + basename + "_" + str(i) + "_" + str(j) + extension
                    #print(com_string)
                    # os.system(com_string)
                    outputfilename = basename + "_" + str(i) + "_" + str(j) + extension
                    outputfilepath = os.path.join(out_path, outputfilename)

                    #When the crop goes outside of the image we move it to fit inside (this way we avoid classifying pixels outside of image)
                    adjusted_i = min(i,(xstop-(tile_size_x)))
                    if adjusted_i != i:
                        pass #print("adjusted i from :"+str(i )+ " to :"+str(adjusted_i))
                    i= adjusted_i
                    adjusted_j = min(j,(ystop-(tile_size_y)))
                    if adjusted_j != j:
                        pass #print("adjusted j from :"+str(j )+ " to :"+str(adjusted_j))
                    j= adjusted_j


                    # outfile = str(out_path) + basename + "_" + str(i) + "_" + str(j) + extension
                    options = "-srcwin " + str(i) + ", " + str(j) + ", " + str(tile_size_x) + ", " + str(tile_size_y) +  \
                        gdal_opt
                        # ' -a_srs EPSG:25832 -co TILED=YES -co PHOTOMETRIC=RGB -co COMPRESS=LZW ' # old style
                    # ' -a_srs EPSG:25832 -co TILED=YES -co PHOTOMETRIC=RGB -co COMPRESS=LZW -a_offset 3 -a_nodata 3 '  # fix nodata problem monochrome mask (old style)
                    ds = gdal.Translate(outputfilepath, inputfilepath, options=options)
                    ds = None
                    sub_tiles += 1
            if debug:
                print("Cut into {} sub tiles".format(sub_tiles))


    def splitfiles(self, in_path, tile_size_x, tile_size_y, correctpixels = 'False'):
        out_path = os.path.join(in_path, 'split')
        self.split(in_path, out_path, tile_size_x, tile_size_y)
        if correctpixels == 'True':
            self.correctpixelvalues(out_path, 0, 1)


    def getfiles(self, path):
        filelist = []
        if os.path.isdir(path):
            for file in os.listdir(path):
                if os.path.isfile(os.path.join(path, file)):
                    filelist.append(file)
        return filelist

    def checkpixelvalues(self, path, min, max):
        filelist = self.getfiles(path)
        filelist.sort()
        for filename in filelist:
            if filename.endswith('.tif'):
                filepath = os.path.join(path, filename)
                im = Image.open(filepath)
                arr = np.asarray(im)
                x = np.argwhere(arr is None)
                if x.size > 0:
                    print(filename + ' contains null pixelvalues')
                    print(x)
                x = np.argwhere(arr > 1)
                if x.size > 0:
                    print(filename + ' contains values > 1')
                    print(len(x))
                    print(x)
                x = np.where(arr > 1)
                if x.size > 0:
                    print(filename + ' contains values > 1')
                    print(len(x))
                    print(x)
                x = np.argwhere(arr < 0)
                if x.size > 0:
                    print(filename + ' contains values < 0')
                    print(x)

    # Null values are converted to 0
    def correctpixelvalues(self, path, min, max):
        filelist = self.getfiles(path)
        filelist.sort()
        for filename in filelist:
            if filename.endswith('.tif'):
                filepath = os.path.join(path, filename)
                im = Image.open(filepath)
                arr = np.asarray(im)
                np.nan_to_num(arr)
                arr = np.where(arr<2, arr, 0)
                im = Image.fromarray(arr)
                arrcheck = np.asarray(im)
                im.save(filepath)


    # Finder hvor meget, der skal paddes, så højde og bredde bliver delelige med tile_sizes
    def getBorders(self, height, width, tile_size_x, tile_size_y):
        i = 0
        j = 0
        while i < height:
            i = i + tile_size_y
        bottom = i - height
        while j < width:
            j = j + tile_size_x
        right = j - width
        return bottom, right, i, j

    def config(self, filename='settings.ini', section='Paths_Per'):
        # create a parser
        parser = ConfigParser()
        # read config file
        parser.read(filename)

        if parser.has_section(section):
            split_this_dir = parser[section]['split_this_dir']
            tile_size_x = parser[section]['tile_size_x']
            tile_size_y = parser[section]['tile_size_y']
            return split_this_dir, tile_size_x, tile_size_y
        else:
            raise Exception('Section {0} not found in the {1} file'.format(section, filename))


    def exec(self, section='Paths_Per'):
        split_this_dir, tile_size_x, tile_size_y = self.config(section=section)
        self.splitfiles(split_this_dir, int(tile_size_x), int(tile_size_y), 'True')

if __name__ == "__main__":
    usage_example= "python split.py --input_folder /path/to/folder --output_folder /path/to/folder --tile_size_x 1000 --tile_size_y 1000"
    # Initialize parser
    parser = argparse.ArgumentParser(
        epilog=usage_example,
        formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument("--input_folder",help ="path to folder containing images to be splitted",required=True)
    parser.add_argument("--output_folder",  help="path to folder where splitted images should be saved",required=True)
    parser.add_argument("--tile_size_x",  help="e.g 1000",required=True)
    parser.add_argument("--tile_size_y",  help="e.g 1000",required=True)
    parser.add_argument("--kun_ok_pic",  help="should we skip the croped parts that includes areas outside of the image",required=False,type=bool,default =False)

    args = parser.parse_args()


    splitf = Split()

    splitf.splitdst(in_path=args.input_folder, out_path=args.output_folder, tile_size_x=int(args.tile_size_x), tile_size_y=int(args.tile_size_x),kun_ok_pic=args.kun_ok_pic,overlap=args.overlap)

# Null values are converted to 0 for files in file filelist
"""
def cv2splitfile(in_path, out_path, filename, tile_size_x, tile_size_y):
    print('File to be splitted: ', filename)
    if filename.upper().endswith('.PNG') or filename.upper().endswith('.JPG') or filename.upper().endswith('.TIF'):
        basename = os.path.splitext(filename)[0]
        extension = os.path.splitext(filename)[1]
        inputfilepath  = os.path.join(in_path, filename)
        # read image
        img = cv2.imread(inputfilepath, cv2.IMREAD_UNCHANGED)
        # get dimensions of image
        dimensions = img.shape
        # height, width, number of channels in image
        height = img.shape[0]
        width = img.shape[1]
        #channels = img.shape[2]

        #print('Image Dimension    : ',dimensions)
        #print('Image Height       : ',height)
        #print('Image Width        : ',width)
        #print('Number of Channels : ',channels)

        bottom, right, paddedheight, paddedwidth = getBorders(height, width, tile_size_x, tile_size_y)

        window_name = 'Image_padded'
        imgpadded = cv2.copyMakeBorder(img, 0, bottom, 0, right, cv2.BORDER_CONSTANT, 0)
        imgpaddedname = os.path.join(in_path, 'padded_'+filename)
        # cv2.imwrite(imgpaddedname, imgpadded)
        # cv2.imshow(window_name, imgpadded)

        # y1 = 0

        for y in range(0, paddedheight, tile_size_y):
            for x in range(0, paddedwidth, tile_size_x):
                y1 = y + tile_size_y
                x1 = x + tile_size_y
                tiles = imgpadded[y:y1,x:x1]
                outfile = basename + '_' + str(x) + '_' + str(y) + extension
                outputfilepath  = os.path.join(out_path, outfile)
                #cv2.rectangle(img, (x, y), (x1, y1), (0, 255, 0))
                cv2.imwrite(outputfilepath,tiles)
"""


"""
splitfiles()
srcpath = r'F:\TEMP\PEMAC\server\Vector2Image\EsbjergPlus\src\split'
correctpixelvalues(srcpath, 0, 1)

maskpath = r'F:\TEMP\PEMAC\server\Vector2Image\EsbjergPlus\dest\reclass\split'
checkpixelvalues(maskpath, 0, 1)
correctpixelvalues(maskpath, 0, 1)
print("Done correcting pixelvalues!")
"""
