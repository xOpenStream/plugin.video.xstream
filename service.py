# -*- coding: utf-8 -*-
# Python 3

import os
import xbmc
import time
from concurrent.futures import ThreadPoolExecutor

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


def _resolverUpdate():
    """Resolver Update im Hintergrund - gibt Status zurück für Notification."""
    try:
        if not os.path.isfile(RESOLVE_SHA) or cConfig().getSetting('githubUpdateResolver') == 'true' or cConfig().getSetting('enforceUpdate') == 'true':
            status = updateManager.resolverUpdate()
            if cConfig().getSetting('enforceUpdate') == 'true':
                cConfig().setSetting('enforceUpdate', 'false')
            return status
    except Exception:
        import traceback
        log(cConfig().getLocalizedString(30166) + ' -> [xstream]: Resolver update error: %s' % traceback.format_exc(), LOGERROR)
        return False
    return 'skipped'


def main():
    cCache().set(cConfig().getAddonInfo('id') + '_main', 'running')

    # Resolver Update und Domain Check parallel starten
    with ThreadPoolExecutor(max_workers=1) as executor:
        # Resolver läuft im Hintergrund
        resolver_future = executor.submit(_resolverUpdate)

        # Domain Check läuft gleichzeitig im Main Thread
        cPluginHandler().checkDomain()

        # Warte auf Resolver (falls noch nicht fertig, max 10 Sek)
        try:
            resolver_status = resolver_future.result(timeout=10)
        except Exception:
            resolver_status = False

    # Wenn neue settings vorhanden oder geändert in addon_data dann starte Pluginhandler und aktualisiere die PluginDB um Daten von checkDomain mit aufzunehmen
    try:
        if cConfig().getSetting('newSetting') == 'true':
            cPluginHandler().getAvailablePlugins()
    except Exception:
        pass

    # getAvailablePlugins must be finished before the main menu can be started!
    cCache().set(cConfig().getAddonInfo('id') + '_main', 'finished')

    # Resolver Notification (nach Domain Check damit sich Notifications nicht überschneiden)
    # Nur anzeigen wenn ein Update Check tatsächlich stattfand (nicht 'skipped')
    if resolver_status != 'skipped':
        if resolver_status == True: infoDialog(cConfig().getLocalizedString(30116), sound=False, icon='INFO', time=6000)
        if resolver_status == False: infoDialog(cConfig().getLocalizedString(30117), sound=True, icon='ERROR')
        if resolver_status == None: infoDialog(cConfig().getLocalizedString(30118), sound=False, icon='INFO', time=6000)

    # Changelog Popup in den "settings.xml" ein bzw. aus schaltbar
    if cConfig().getSetting('popup.update.notification') == 'true':
        tools.changelog()

    # Html Cache beim KodiStart nach (X) Tage löschen
    delHtmlCache()

if __name__ == "__main__":
    main()
