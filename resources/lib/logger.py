# -*- coding: utf-8 -*-
# Python 3
# xStream interner Log
import sys
import xbmc
import xbmcaddon
from urllib.parse import parse_qsl, urlsplit


class logger:
    ADDON_NAME = xbmcaddon.Addon().getAddonInfo('name')

    @staticmethod
    def info(sInfo):
        logger.__writeLog(sInfo, cLogLevel=xbmc.LOGINFO)

    @staticmethod
    def debug(sInfo):
        logger.__writeLog(sInfo, cLogLevel=xbmc.LOGDEBUG)

    @staticmethod
    def warning(sInfo):
        logger.__writeLog(sInfo, cLogLevel=xbmc.LOGWARNING)

    @staticmethod
    def error(sInfo):
        logger.__writeLog(sInfo, cLogLevel=xbmc.LOGERROR)

    @staticmethod
    def fatal(sInfo):
        logger.__writeLog(sInfo, cLogLevel=xbmc.LOGFATAL)

    @staticmethod
    def __writeLog(sLog, cLogLevel=xbmc.LOGDEBUG):
        try:
            params = dict()
            if len(sys.argv) >= 3 and len(sys.argv[2]) > 0:
                params = dict(parse_qsl(urlsplit(sys.argv[2]).query))
            if 'site' in params:
                sLog = "[%s] -> [%s]: %s" % (logger.ADDON_NAME, params['site'], sLog)
            else:
                sLog = "[%s] %s" % (logger.ADDON_NAME, sLog)
            xbmc.log(sLog, cLogLevel)
        except Exception as e:
            xbmc.log('Logging Failure: %s' % e, cLogLevel)
