# -*- coding: utf-8 -*-
# Python 3

import myjdapi

from resources.lib.config import cConfig
from resources.lib.gui.gui import cGui
from resources.lib.logger import logger

class cMyJDownloaderHandler:

    def sendToMyJDownloader(self, sUrl, sMovieTitle):
        if self.__checkConfig() == False:
            cGui().showError(cConfig().getLocalizedString(30090), cConfig().getLocalizedString(30254), 5)
            return False

        try:
            jd = myjdapi.Myjdapi()
            jd.connect(self.__getUser(), self.__getPass())
        except Exception as e:
            logger.error('-> [myjdownloaderHandler]: connect failed: %s' % str(e))
            cGui().showError(cConfig().getLocalizedString(30090), cConfig().getLocalizedString(30255), 5)
            return False

        try:
            jd.update_devices()
        except Exception as e:
            logger.error('-> [myjdownloaderHandler]: update_devices failed: %s' % str(e))
            cGui().showError(cConfig().getLocalizedString(30090), cConfig().getLocalizedString(30256), 5)
            return False

        try:
            device = jd.get_device(self.__getDevice())
            result = device.linkgrabber.add_links([{"autostart": False, "links": sUrl, "packageName": sMovieTitle}])
            if result and result.get('id', 0) > 0:
                cGui().showInfo(cConfig().getLocalizedString(30090), cConfig().getLocalizedString(30256), 5)
                return True
        except Exception as e:
            logger.error('-> [myjdownloaderHandler]: send failed: %s' % str(e))
            cGui().showError(cConfig().getLocalizedString(30090), cConfig().getLocalizedString(30256), 5)
        return False

    def __checkConfig(self):
        logger.debug('-> [myjdownloaderHandler]: check MYJD Addon setings')
        if cConfig().getSetting('myjd_enabled') == 'true':
            return True
        return False

    def __getDevice(self):
        return cConfig().getSetting('myjd_device')

    def __getUser(self):
        return cConfig().getSetting('myjd_user')

    def __getPass(self):
        return cConfig().getSetting('myjd_pass')
