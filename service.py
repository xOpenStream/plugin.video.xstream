# -*- coding: utf-8 -*-
# Python 3

import os
import xbmc
import time

from resources.lib.config import cConfig
from resources.lib import tools
from xbmc import LOGERROR,  LOGDEBUG, log
from resources.lib.handler.requestHandler import cRequestHandler
from resources.lib.handler.pluginHandler import cPluginHandler
from resources.lib import updateManager
from resources.lib.utils import translatePath
from resources.lib.tools import cCache
from resources.lib.tools import infoDialog


# ResolverUrl Addon Data
RESOLVE_ADDON_DATA_PATH = translatePath(os.path.join('special://home/userdata/addon_data/script.module.resolveurl'))

# Pfad der update.sha
RESOLVE_SHA = os.path.join(translatePath(RESOLVE_ADDON_DATA_PATH), "update_sha")

# xStream Installationspfad
ADDON_PATH = translatePath(os.path.join('special://home/addons/', '%s'))

def delHtmlCache():
    # Html Cache beim KodiStart nach (X) Tage löschen
    deltaDay = int(cConfig().getSetting('cacheDeltaDay', 2))
    deltaTime = 60*60*24*deltaDay # Tage
    currentTime = int(time.time())
    # alle x Tage
    if currentTime >= int(cConfig().getSetting('lastdelhtml', 0)) + deltaTime:
        cRequestHandler('').clearCache() # Cache löschen
        cConfig().setSetting('lastdelhtml', str(currentTime))


def main():
    cCache().set(cConfig().getAddonInfo('id') + '_main', 'running')

    # Starte Resolver Update wenn auf Github verfügbar
    if os.path.isfile(RESOLVE_SHA) == False or cConfig().getSetting('githubUpdateResolver') == 'true'  or cConfig().getSetting('enforceUpdate') == 'true':
        status2 = updateManager.resolverUpdate(True)
        if status2 == True: infoDialog(cConfig().getLocalizedString(30116), sound=False, icon='INFO', time=6000)
        if status2 == False: infoDialog(cConfig().getLocalizedString(30117), sound=True, icon='ERROR')
        if status2 == None: infoDialog(cConfig().getLocalizedString(30118), sound=False, icon='INFO', time=6000)
        if cConfig().getSetting('enforceUpdate') == 'true': cConfig().setSetting('enforceUpdate', 'false')

    # Startet Domain Überprüfung und schreibt diese in die settings.xml
    cPluginHandler().checkDomain()

    # Wenn neue settings vorhanden oder geändert in addon_data dann starte Pluginhandler und aktualisiere die PluginDB um Daten von checkDomain mit aufzunehmen
    try:
        if cConfig().getSetting('newSetting') == 'true':
            cPluginHandler().getAvailablePlugins()
    except Exception:
        pass

    # getAvailablePlugins must be finished before the main menu can be started!
    cCache().set(cConfig().getAddonInfo('id') + '_main', 'finished')

    # Changelog Popup in den "settings.xml" ein bzw. aus schaltbar
    if cConfig().getSetting('popup.update.notification') == 'true':
        tools.changelog()

    # Html Cache beim KodiStart nach (X) Tage löschen
    delHtmlCache()

if __name__ == "__main__":
    main()