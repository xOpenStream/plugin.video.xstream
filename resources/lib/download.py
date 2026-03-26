# -*- coding: utf-8 -*-
# Python 3

import os
import time
import xbmcgui
import requests

from resources.lib import utils
from resources.lib.config import cConfig
from resources.lib.gui.gui import cGui
from resources.lib.logger import logger
from xbmcvfs import translatePath

# Default User-Agent to avoid CDN blocks
_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36'


class cDownload:
    def __createProcessDialog(self, downloadDialogTitle):
        if cConfig().getSetting('backgrounddownload') == 'true':
            oDialog = xbmcgui.DialogProgressBG()
        else:
            oDialog = xbmcgui.DialogProgress()
        oDialog.create(downloadDialogTitle)
        self.__oDialog = oDialog


    def __createDownloadFilename(self, filename):
        filename = filename.replace(' ', '_')
        return filename


    def download(self, url, sTitle, showDialog=True, downloadDialogTitle=cConfig().getLocalizedString(30245)):
        sTitle = '%s' % sTitle
        self.__processIsCanceled = False
        try:
            header = dict([item.split('=') for item in (url.split('|')[1]).split('&')])
        except Exception:
            header = {}
        logger.debug('-> [download]: Header for download: %s' % header)
        url = url.split('|')[0]
        sTitle = self.__createTitle(url, sTitle)
        self.__sTitle = self.__createDownloadFilename(sTitle)
        if showDialog:
            self.__sTitle = cGui().showKeyBoard(self.__sTitle, sHeading=cConfig().getLocalizedString(30290))
            if self.__sTitle != False and len(self.__sTitle) > 0:
                sPath = cConfig().getSetting('download-folder')
                if sPath == '':
                    dialog = xbmcgui.Dialog()
                    sPath = dialog.browse(3, 'Downloadfolder', 'files', '')
                if sPath != '':
                    sDownloadPath = translatePath(sPath + '%s' % (self.__sTitle,))
                    self.__prepareDownload(url, header, sDownloadPath, downloadDialogTitle)
        elif self.__sTitle != False:
            temp_dir = os.path.join(translatePath(cConfig().getAddonInfo('profile')))
            if not os.path.isdir(temp_dir):
                os.makedirs(os.path.join(temp_dir))
            self.__prepareDownload(url, header, os.path.join(temp_dir, sTitle), downloadDialogTitle)
            logger.debug('-> [download]: download completed')


    def __prepareDownload(self, url, header, sDownloadPath, downloadDialogTitle):
        try:
            logger.debug(-> [download]: download file: ' + str(url) + ' to ' + str(sDownloadPath))
            self.__createProcessDialog(downloadDialogTitle)
            # Set User-Agent if not provided
            if 'User-Agent' not in header and 'user-agent' not in header:
                header['User-Agent'] = _UA
            self.__download(url, header, sDownloadPath)
        except Exception as e:
            logger.error('-> [download]: download error: %s' % str(e))
            try:
                cGui().showError('xStream', 'Download fehlgeschlagen: %s' % str(e), 5)
            except:
                pass
        try:
            self.__oDialog.close()
        except:
            pass


    def __download(self, url, header, fpath):
        # Use requests with stream=True for reliable large file downloads
        response = requests.get(url, headers=header, stream=True, timeout=(15, 60))
        response.raise_for_status()

        iTotalSize = int(response.headers.get('Content-Length', 0))
        if iTotalSize == 0:
            iTotalSize = -1
        chunk_size = 1024 * 1024  # 1MB chunks for reliable fast downloads

        logger.debug('-> [download]: start download (size: %s)' %
            (self.__formatFileSize(iTotalSize) if iTotalSize > 0 else 'unbekannt'))

        f = None
        iBytesLoaded = 0
        try:
            f = open(fpath, 'wb')
            self._startTime = time.time()

            for data in response.iter_content(chunk_size=chunk_size):
                if self.__processIsCanceled:
                    logger.debug('-> [download]: download cancelled by user')
                    break
                if not data:
                    continue
                f.write(data)
                iBytesLoaded += len(data)
                self.__stateCallBackFunction(iBytesLoaded, iTotalSize)

            f.close()
            f = None

            if not self.__processIsCanceled:
                logger.debug('-> [download]: download complete (%s)' %
                    self.__formatFileSize(iBytesLoaded))

        except Exception as e:
            logger.error('-> [download]: download failed at %s: %s' %
                (self.__formatFileSize(iBytesLoaded), str(e)))
            if f:
                f.close()
            raise


    def __createTitle(self, sUrl, sTitle):
        if '.' in sTitle:
            return sTitle

        video_exts = ('mp4', 'mkv', 'avi', 'mov', 'flv', 'wmv', 'webm', 'mpeg', 'mpg')
        sUrl_clean = sUrl.split('?', 1)[0]
        parts = sUrl_clean.rsplit('.', 1)
        if len(parts) > 1:
            ext = parts[-1].lower()
            if ext in video_exts:
                return f"{sTitle}.{ext}"
        return sTitle


    def __stateCallBackFunction(self, iBytesLoaded, iTotalSize):
        timedif = time.time() - self._startTime
        if iTotalSize > 0:
            iPercent = int(iBytesLoaded * 100 / iTotalSize)
        else:
            iPercent = 0
        if timedif > 0.0:
            avgSpd = iBytesLoaded / timedif / 1024.0
        else:
            avgSpd = 0
        sTotal = self.__formatFileSize(iTotalSize) if iTotalSize > 0 else '???'
        value = '%s: %s/%s @ %d KB/s' % (self.__sTitle, self.__formatFileSize(iBytesLoaded), sTotal, int(avgSpd))
        try:
            self.__oDialog.update(iPercent, value)
            if cConfig().getSetting('backgrounddownload') == 'false' and self.__oDialog.iscanceled():
                self.__processIsCanceled = True
                self.__oDialog.close()
        except:
            pass


    def __formatFileSize(self, iBytes):
        iBytes = int(iBytes)
        if iBytes <= 0:
            return '0.00 MB'
        if iBytes >= 1024 * 1024 * 1024:
            return '%.2f GB' % (iBytes / (1024.0 * 1024.0 * 1024.0))
        return '%.2f MB' % (iBytes / (1024.0 * 1024.0))
