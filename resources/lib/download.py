# -*- coding: utf-8 -*-
# Python 3

import os
import time
import xbmcgui
import requests

from resources.lib import utils
from resources.lib.config import cConfig
from resources.lib.gui.gui import cGui
from xbmc import LOGINFO as LOGNOTICE, LOGERROR, log
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
        log(cConfig().getLocalizedString(30166) + ' -> [download]: Header for download: %s' % header, LOGNOTICE)
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
            log(cConfig().getLocalizedString(30166) + ' -> [download]: download completed', LOGNOTICE)


    def __prepareDownload(self, url, header, sDownloadPath, downloadDialogTitle):
        try:
            log(cConfig().getLocalizedString(30166) + ' -> [download]: download file: ' + str(url) + ' to ' + str(sDownloadPath), LOGNOTICE)
            self.__createProcessDialog(downloadDialogTitle)
            # Set User-Agent if not provided
            if 'User-Agent' not in header and 'user-agent' not in header:
                header['User-Agent'] = _UA
            self.__download(url, header, sDownloadPath)
        except Exception as e:
            log(cConfig().getLocalizedString(30166) + ' -> [download]: download error: %s' % str(e), LOGERROR)
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

        log(cConfig().getLocalizedString(30166) + ' -> [download]: start download (size: %s)' %
            (self.__formatFileSize(iTotalSize) if iTotalSize > 0 else 'unbekannt'), LOGNOTICE)

        f = None
        iBytesLoaded = 0
        try:
            f = open(fpath, 'wb')
            self._startTime = time.time()

            for data in response.iter_content(chunk_size=chunk_size):
                if self.__processIsCanceled:
                    log(cConfig().getLocalizedString(30166) + ' -> [download]: download cancelled by user', LOGNOTICE)
                    break
                if not data:
                    continue
                f.write(data)
                iBytesLoaded += len(data)
                self.__stateCallBackFunction(iBytesLoaded, iTotalSize)

            f.close()
            f = None

            if not self.__processIsCanceled:
                log(cConfig().getLocalizedString(30166) + ' -> [download]: download complete (%s)' %
                    self.__formatFileSize(iBytesLoaded), LOGNOTICE)

        except Exception as e:
            log(cConfig().getLocalizedString(30166) + ' -> [download]: download failed at %s: %s' %
                (self.__formatFileSize(iBytesLoaded), str(e)), LOGERROR)
            if f:
                f.close()
            raise


    def __createTitle(self, sUrl, sTitle):
        aTitle = sTitle.rsplit('.')
        if len(aTitle) > 1:
            return sTitle
        aUrl = sUrl.rsplit('.')
        if len(aUrl) > 1:
            sSuffix = aUrl[-1]
            sTitle = sTitle + '.' + sSuffix
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
