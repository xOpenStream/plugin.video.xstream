# -*- coding: utf-8 -*-
# Python 3
# xStream interner Log
import sys
import xbmc
import xbmcaddon
from urllib.parse import parse_qsl, urlsplit

class Logger:
    ADDON_NAME = xbmcaddon.Addon().getAddonInfo('name')

    @staticmethod
    def info(sInfo):
        Logger.__writeLog(sInfo, cLogLevel=xbmc.LOGINFO)

    @staticmethod
    def debug(sInfo):
        Logger.__writeLog(sInfo, cLogLevel=xbmc.LOGDEBUG)

    @staticmethod
    def warning(sInfo):
        Logger.__writeLog(sInfo, cLogLevel=xbmc.LOGWARNING)

    @staticmethod
    def error(sInfo):
        Logger.__writeLog(sInfo, cLogLevel=xbmc.LOGERROR)

    @staticmethod
    def fatal(sInfo):
        Logger.__writeLog(sInfo, cLogLevel=xbmc.LOGFATAL)

    @staticmethod
    def __writeLog(sLog, cLogLevel=xbmc.LOGDEBUG):
        params = dict()
        if len(sys.argv) >= 3 and len(sys.argv[2]) > 0:
            params = dict(parse_qsl(urlsplit(sys.argv[2]).query))
        try:
            if 'site' in params:
                site = params['site']
                sLog = f"[{Logger.ADDON_NAME}] -> [{site}] {sLog}"
            else:
                sLog = f"[{Logger.ADDON_NAME}] {sLog}"
            xbmc.log(sLog, cLogLevel)
        except Exception as e:
            xbmc.log(f'Logging Failure: {e}', cLogLevel)
            pass