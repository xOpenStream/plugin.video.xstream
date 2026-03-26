# -*- coding: utf-8 -*-
# Python 3

import os
import zipfile
import xbmcgui, xbmcvfs
from xbmcvfs import translatePath
from urllib.request import urlretrieve
from resources.lib.config import cConfig
from resources.lib.logger import Logger as logger

progressDialog = xbmcgui.DialogProgress()


def download_url(url, dest, dp=None):
    # download_url(url, src, dp=[None / True / False / Dialog])
    if dp == None or dp == True:
        dp = progressDialog
        dp.create("URL Downloader", " \n  Downloading  File:  [B]%s[/B]" % url.split('/')[-1])
    elif dp == False:
        return urlretrieve(url, dest)
    try:
        dp.update(0)
        urlretrieve(url, dest, lambda nb, bs, fs, url=url: _pbhook(nb, bs, fs, dp))
        dp.close()
    except:
        urlretrieve(url, dest)

def _pbhook(numblocks, blocksize, filesize, dp):
    try:
        percent = min((numblocks * blocksize * 100) / filesize, 100)
        dp.update(int(percent))
    except:
        percent = 100
        dp.update(percent)
    if dp.iscanceled():
        dp.close()
        raise Exception("Canceled")


def unzip_recursive(path, dirs, dest):
    for directory in dirs:
        dirs_dir = os.path.join(path, directory)
        dest_dir = os.path.join(dest, directory)
        xbmcvfs.mkdir(dest_dir)
        dirs2, files = xbmcvfs.listdir(dirs_dir)
        if dirs2:
            unzip_recursive(dirs_dir, dirs2, dest_dir)
        for file in files:
            unzip_file(os.path.join(dirs_dir, file), os.path.join(dest_dir, file))

def unzip_file(path, dest):
    ''' Unzip specific file. Path should start with zip:// '''
    xbmcvfs.copy(path, dest)

def unzip(path, dest, folder=None):
    try:
        with zipfile.ZipFile(path, 'r') as zip:
            zip.extractall(dest)
    except:
        pass

def get_zip_directory(path, folder):
    dirs, files = xbmcvfs.listdir(path)
    if folder in dirs:
        return os.path.join(path, folder)
    for directory in dirs:
        result = get_zip_directory(os.path.join(path, directory), folder)
        if result:
            return result


# # Todo - soll mal Hilfefunktion werden
def help():
    return 'OK' # Platzhalter

