# -*- coding: utf-8 -*-
# Python 3

import sys
import xbmc
import xbmcgui
import os
import time
import json
import concurrent.futures
from resources.lib.handler.ParameterHandler import ParameterHandler
from resources.lib.handler.requestHandler import cRequestHandler
from resources.lib.handler.pluginHandler import cPluginHandler
from xbmc import executebuiltin
from resources.lib.gui.guiElement import cGuiElement
from resources.lib.gui.gui import cGui
from resources.lib.config import cConfig
from resources.lib.logger import logger
from resources.lib.tools import cParser
from resources.lib.cache import cCache
from xbmcvfs import translatePath

try:
    import resolveurl as resolver
except ImportError:
    # Resolver Fehlermeldung (bei defekten oder nicht installierten Resolver)
    xbmcgui.Dialog().ok(cConfig().getLocalizedString(30119), cConfig().getLocalizedString(30120))


def viewInfo(params):
    from resources.lib.tmdbinfo import WindowsBoxes
    parms = ParameterHandler()
    sCleanTitle = params.getValue('searchTitle')
    sMeta = parms.getValue('sMeta')
    sYear = parms.getValue('sYear')
    WindowsBoxes(sCleanTitle, sCleanTitle, sMeta, sYear)


def parseUrl():
    if xbmc.getInfoLabel('Container.PluginName') == 'plugin.video.osmosis':
        sys.exit()

    params = ParameterHandler()
    logger.info(params.getAllParameters())

    # If no function is set, we set it to the default "load" function
    if params.exist('function'):
        sFunction = params.getValue('function')
        if sFunction == 'spacer':
            return True
        elif sFunction == 'clearCache':
            cCache().clearCache()
            return
        elif sFunction == 'viewInfo':
            viewInfo(params)
            return
        elif sFunction == 'playTrailer':
            from resources.lib.trailer import playTrailer
            try:
                # Map prefLanguage setting to language code
                _pref = cConfig().getSetting('prefLanguage') or '0'
                _kodi_lang = xbmc.getLanguage(xbmc.ISO_639_1) or 'de'
                _lang_map = {'0': _kodi_lang, '1': 'de', '2': 'en', '3': 'ja'}
                _pref_lang = _lang_map.get(_pref, _kodi_lang)
                playTrailer(
                    tmdb_id=params.getValue('tmdb_id') or '',
                    mediatype=params.getValue('mediatype') or 'movie',
                    title=params.getValue('title') or '',
                    year=params.getValue('year') or '',
                    poster=params.getValue('poster') or '',
                    pref_lang=_pref_lang,
                )
            except Exception:
                import traceback
                logger.error('Trailer error: %s' % traceback.format_exc())
                cGui.showError('Trailer', 'Trailer-Suche fehlgeschlagen')
            return
        elif sFunction == 'searchAlter':
            searchAlter(params)
            return
        elif sFunction == 'searchTMDB':
            searchTMDB(params)
            return
        elif sFunction == 'manualResolverUpdate':
            from resources.lib import updateManager
            updateManager.manualResolverUpdate()
            return
        elif sFunction == 'pluginInfo':
            cPluginHandler().pluginInfo()
            return
        elif sFunction == 'changelog':
            changelog_path = os.path.join(translatePath('special://home/addons/%s/' % cConfig().getAddonInfo('id')), 'changelog.txt')
            if not os.path.isfile(changelog_path):
                xbmcgui.Dialog().notification(cConfig().getAddonInfo('name'), cConfig().getLocalizedString(30822), xbmcgui.NOTIFICATION_INFO, 5000)
                return
            with open(changelog_path, 'r', encoding='utf-8') as f:
                text = f.read()
            if not text.strip():
                xbmcgui.Dialog().notification(cConfig().getAddonInfo('name'), cConfig().getLocalizedString(30821), xbmcgui.NOTIFICATION_INFO, 5000)
            else:
                xbmcgui.Dialog().textviewer('Changelog', text)
            return
        elif sFunction == 'domainCheck':
            manualDomainCheck()
            return
            
    elif params.exist('remoteplayurl'):
        try:
            remotePlayUrl = params.getValue('remoteplayurl')
            sLink = resolver.resolve(remotePlayUrl)
            if sLink:
                xbmc.executebuiltin('PlayMedia(' + sLink + ')')
            else:
                logger.debug('Could not play remote url %s' % sLink)
        except resolver.resolver.ResolverError as e:
            logger.error('ResolverError: %s' % e)
        return
    else:
        sFunction = 'load'

    # Test if we should run a function on a special site
    if not params.exist('site'):
        # As a default if no site was specified, we run the default starting gui with all plugins
        showMainMenu(sFunction)
        return
    sSiteName = params.getValue('site')
    if params.exist('playMode'):
        from resources.lib.gui.hoster import cHosterGui
        url = False
        playMode = params.getValue('playMode')
        isHoster = params.getValue('isHoster')
        url = params.getValue('url')
        manual = params.exist('manual')

        hosterSelect = cConfig().getSetting('hosterSelect')
        if hosterSelect == 'Auto' and playMode != 'jd' and playMode != 'jd2' and not manual:
            cHosterGui().streamAuto(playMode, sSiteName, sFunction)
        else:
            cHosterGui().stream(playMode, sSiteName, sFunction, url)
        return

    logger.debug("Call function '%s' from '%s'" % (sFunction, sSiteName))
    # If the hoster gui is called, run the function on it and return
    if sSiteName == 'cHosterGui':
        showHosterGui(sFunction)
    # If global search is called
    elif sSiteName == 'globalSearch':
        searchterm = False
        if params.exist('searchterm'):
            searchterm = params.getValue('searchterm')
            logger.debug('found searchTermin')
        searchGlobal(searchterm)
    elif sSiteName == 'xStream':
        oGui = cGui()
        oGui.openSettings()
        # resolves strange errors in the logfile
        #oGui.updateDirectory()
        oGui.setEndOfDirectory()
        xbmc.executebuiltin('Action(ParentDir)')
    # Resolver Einstellungen im Hauptmenü
    elif sSiteName == 'resolver':
        oGui = cGui()
        resolver.display_settings()
        # resolves strange errors in the logfile
        oGui.setEndOfDirectory()
        xbmc.executebuiltin('Action(ParentDir)')
    # Manuelles Update im Hauptmenü
    elif sSiteName == 'manualResolverUpdate':
        from resources.lib import updateManager
        updateManager.manualResolverUpdate()
    # Plugin Infos    
    elif sSiteName == 'pluginInfo':
        cPluginHandler().pluginInfo()
    # Changelog anzeigen    
    elif sSiteName == 'changelog':
        from resources.lib import tools
        tools.changelog()
    # Manueller Domain Check
    elif sSiteName == 'domainCheck':
        manualDomainCheck()
    # Unterordner der Einstellungen   
    elif sSiteName == 'settings':
        oGui = cGui()
        for folder in settingsGuiElements():
            oGui.addFolder(folder)
        oGui.setEndOfDirectory()
    else:
        # Else load any other site as plugin and run the function
        plugin = __import__(sSiteName, globals(), locals())
        function = getattr(plugin, sFunction)
        function()


def showMainMenu(sFunction):
    ART = os.path.join(cConfig().getAddonInfo('path'), 'resources', 'art')
    addon_id = cConfig().getAddonInfo('id')
    start_time = time.time()
    # timeout for the startup status check  to make sure all is done
    startupFlag = cConfig().getSetting(cConfig().getAddonInfo('id') + '_main')
    logger.debug(f'cache get init {startupFlag}')
    
    while (startupStatus := cConfig().getSetting(cConfig().getAddonInfo('id') + '_main')) != 'finished' and time.time() - start_time <= 25:
        time.sleep(0.2)
    
    # Clear cached search texts so next search opens fresh keyboard
    xbmcgui.Window(10000).clearProperty('xstream.globalSearchText')
    xbmcgui.Window(10000).clearProperty('xstream.globalSearchResults')
    xbmcgui.Window(10000).clearProperty('xstream.alterSearchTitle')
    xbmcgui.Window(10000).clearProperty('xstream.alterSearchResults')

    oGui = cGui()

    # Setzte die globale Suche an erste Stelle
    if cConfig().getSetting('GlobalSearchPosition') == 'true':
        oGui.addFolder(globalSearchGuiElement())

    oPluginHandler = cPluginHandler()
    aPlugins = oPluginHandler.getAvailablePlugins()
    if not aPlugins:
        logger.debug('No activated Plugins found')
        # Open the settings dialog to choose a plugin that could be enabled
        oGui.openSettings()
        oGui.updateDirectory()
    else:
        # Create a gui element for every plugin found
        for aPlugin in sorted(aPlugins, key=lambda k: k['id']):
            oGuiElement = cGuiElement()
            oGuiElement.setTitle(aPlugin['name'])
            oGuiElement.setSiteName(aPlugin['id'])
            oGuiElement.setFunction(sFunction)
            if 'icon' in aPlugin and aPlugin['icon']:
                oGuiElement.setThumbnail(aPlugin['icon'])
            oGui.addFolder(oGuiElement)
        if cConfig().getSetting('GlobalSearchPosition') == 'false':
            oGui.addFolder(globalSearchGuiElement())

    if cConfig().getSetting('SettingsFolder') == 'true':
        # Einstellung im Menü mit Untereinstellungen
        oGuiElement = cGuiElement()
        oGuiElement.setTitle(cConfig().getLocalizedString(30041))
        oGuiElement.setSiteName('settings')
        oGuiElement.setFunction('showSettingsFolder')
        oGuiElement.setThumbnail(os.path.join(ART, 'settings.png'))
        oGui.addFolder(oGuiElement)
    else:
        for folder in settingsGuiElements():
            oGui.addFolder(folder)
    oGui.setEndOfDirectory(pCacheToDisc=False) # caching will brake global search!
def settingsGuiElements():
    ART = os.path.join(cConfig().getAddonInfo('path'), 'resources', 'art')

    # GUI Plugin Informationen
    oGuiElement = cGuiElement()
    oGuiElement.setTitle(cConfig().getLocalizedString(30267))
    oGuiElement.setSiteName('pluginInfo')
    oGuiElement.setFunction('pluginInfo')
    oGuiElement.setThumbnail(os.path.join(ART, 'plugin_info.png'))
    PluginInfo = oGuiElement


    # GUI xStream Einstellungen
    oGuiElement = cGuiElement()
    oGuiElement.setTitle(cConfig().getLocalizedString(30042))
    oGuiElement.setSiteName('xStream')
    oGuiElement.setFunction('display_settings')
    oGuiElement.setThumbnail(os.path.join(ART, 'xstream_settings.png'))
    xStreamSettings = oGuiElement

    # GUI Resolver Einstellungen
    oGuiElement = cGuiElement()
    oGuiElement.setTitle(cConfig().getLocalizedString(30043))
    oGuiElement.setSiteName('resolver')
    oGuiElement.setFunction('display_settings')
    oGuiElement.setThumbnail(os.path.join(ART, 'resolveurl_settings.png'))
    resolveurlSettings = oGuiElement
    
    # GUI Manueller Domain Check
    oGuiElement = cGuiElement()
    oGuiElement.setTitle(cConfig().getLocalizedString(30818))
    oGuiElement.setSiteName('domainCheck')
    oGuiElement.setFunction('domainCheck')
    oGuiElement.setThumbnail(os.path.join(ART, 'domain_check.png'))
    DomainCheck = oGuiElement

    # GUI ResolveURL Update
    oGuiElement = cGuiElement()
    oGuiElement.setTitle(cConfig().getLocalizedString(30121))
    oGuiElement.setSiteName('manualResolverUpdate')
    oGuiElement.setFunction('manualResolverUpdate')
    oGuiElement.setThumbnail(os.path.join(ART, 'resolveurl_update.png'))
    DevUpdateMan = oGuiElement

    return PluginInfo, xStreamSettings, resolveurlSettings, DomainCheck, DevUpdateMan


def manualDomainCheck():
    cPluginHandler().checkDomain()
    # Plugin-Daten aktualisieren mit neuen Domains
    cPluginHandler().getAvailablePlugins()


def globalSearchGuiElement():
    ART = os.path.join(cConfig().getAddonInfo('path'), 'resources', 'art')

    # Create a gui element for global search
    oGuiElement = cGuiElement()
    oGuiElement.setTitle(cConfig().getLocalizedString(30040))
    oGuiElement.setSiteName('globalSearch')
    oGuiElement.setFunction('globalSearch')
    oGuiElement.setThumbnail(os.path.join(ART, 'search.png'))
    return oGuiElement


def showHosterGui(sFunction):
    from resources.lib.gui.hoster import cHosterGui
    oHosterGui = cHosterGui()
    function = getattr(oHosterGui, sFunction)
    function()
    return True


def _serializeSearchResults(results):
    """Serialize search results list to a JSON string for Window property caching."""
    serialized = []
    for result in results:
        serialized.append({
            'guiElement': result['guiElement'].to_dict(),
            'params': result['params'].to_dict() if hasattr(result['params'], 'to_dict') else {},
            'isFolder': result['isFolder'],
        })
    return json.dumps(serialized, ensure_ascii=False)


def _deserializeSearchResults(data):
    """Reconstruct search results list from a cached JSON string."""
    results = []
    for entry in json.loads(data):
        results.append({
            'guiElement': cGuiElement.from_dict(entry['guiElement']),
            'params': ParameterHandler.from_dict(entry['params']),
            'isFolder': entry['isFolder'],
        })
    return results


def searchGlobal(sSearchText=False):
    oGui = cGui()
    oGui.globalSearch = True
    win = xbmcgui.Window(10000)

    if not sSearchText:
        # Check if we have a cached search text (e.g. coming back from playback)
        sSearchText = win.getProperty('xstream.globalSearchText')

        if sSearchText:
            # We have a cached search term — try to load cached results
            cachedResults = win.getProperty('xstream.globalSearchResults')
            if cachedResults:
                try:
                    results = _deserializeSearchResults(cachedResults)
                    total = len(results)
                    for result in sorted(results, key=lambda k: k['guiElement'].getSiteName()):
                        oGui.addFolder(result['guiElement'], result['params'], bIsFolder=result['isFolder'], iTotal=total)
                    oGui.setView()
                    oGui.setEndOfDirectory()
                    return True
                except Exception:
                    import traceback
                    logger.error('Search cache restore failed: %s' % traceback.format_exc())
                    # Cache broken — fall through to fresh search
                    win.clearProperty('xstream.globalSearchResults')

        if not sSearchText:
            sSearchText = oGui.showKeyBoard(sHeading=cConfig().getLocalizedString(30280))
        if not sSearchText:
            oGui.setEndOfDirectory()
            return True

    # New search — clear old cached results
    win.clearProperty('xstream.globalSearchResults')
    win.setProperty('xstream.globalSearchText', sSearchText)

    oGui._collectMode = True

    aPlugins = cPluginHandler().getAvailablePlugins()
    dialog = xbmcgui.DialogProgress()
    dialog.create(cConfig().getLocalizedString(30122), cConfig().getLocalizedString(30123))

    numPlugins = len(aPlugins)
    searchablePlugins = [pluginEntry for pluginEntry in aPlugins if pluginEntry['globalsearch'] not in ['false', '']]

    def worker(pluginEntry):
        logger.debug('Searching for %s at %s' % (sSearchText, pluginEntry['id']))
        _pluginSearch(pluginEntry, sSearchText, oGui)
        return pluginEntry['name']

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_plugin = {executor.submit(worker, pluginEntry): pluginEntry for pluginEntry in searchablePlugins}

        for count, future in enumerate(concurrent.futures.as_completed(future_to_plugin)):
            pluginEntry = future_to_plugin[future]
            if dialog.iscanceled():
                oGui.setEndOfDirectory()
                return
            try: pluginName = future.result()
            except Exception as e:
                pluginName = pluginEntry['name']
                logger.error(f"Fehler bei Plugin {pluginName}: {str(e)}")
            progress = (count + 1) * 50 // len(searchablePlugins)
            dialog.update(progress, pluginName + cConfig().getLocalizedString(30125))
    dialog.close()

    # Cache the results for re-use when navigating back
    try:
        win.setProperty('xstream.globalSearchResults', _serializeSearchResults(oGui.searchResults))
    except Exception:
        import traceback
        logger.error('Search cache save failed: %s' % traceback.format_exc())

    # Ergebnisse anzeigen
    oGui._collectMode = False
    total = len(oGui.searchResults)
    dialog = xbmcgui.DialogProgress()
    dialog.create(cConfig().getLocalizedString(30126), cConfig().getLocalizedString(30127))

    for count, result in enumerate(sorted(oGui.searchResults, key=lambda k: k['guiElement'].getSiteName()), 1):
        if dialog.iscanceled():
            oGui.setEndOfDirectory()
            return
        oGui.addFolder(result['guiElement'], result['params'], bIsFolder=result['isFolder'], iTotal=total)
        dialog.update(count * 100 // total, str(count) + cConfig().getLocalizedString(30128) + str(total) + ': ' + result['guiElement'].getTitle())

    dialog.close()
    oGui.setView()
    oGui.setEndOfDirectory()
    return True

def searchAlter(params):
    searchTitle = params.getValue('searchTitle')
    searchImdbId = params.getValue('searchImdbID')
    searchYear = params.getValue('searchYear')

    # Jahr aus dem Titel extrahieren
    if ' (19' in searchTitle or ' (20' in searchTitle:
        isMatch, aYear = cParser.parse(searchTitle, r'(.*?) \((\d{4})\)')
        if isMatch:
            searchTitle = aYear[0][0]
            if not searchYear:
                searchYear = str(aYear[0][1])

    # Staffel oder Episodenkennung abschneiden
    for token in [' S0', ' E0', ' - Staffel', ' Staffel']:
        if token in searchTitle:
            searchTitle = searchTitle.split(token)[0].strip()
            break

    oGui = cGui()
    oGui.globalSearch = True
    win = xbmcgui.Window(10000)

    # Cache prüfen: gleicher Titel wie letztes Mal?
    cachedTitle = win.getProperty('xstream.alterSearchTitle')
    if cachedTitle == searchTitle:
        cachedResults = win.getProperty('xstream.alterSearchResults')
        if cachedResults:
            try:
                results = _deserializeSearchResults(cachedResults)
                total = len(results)
                for result in sorted(results, key=lambda k: k['guiElement'].getSiteName()):
                    oGui.addFolder(result['guiElement'], result['params'], bIsFolder=result['isFolder'], iTotal=total)
                oGui.setView()
                oGui.setEndOfDirectory()
                return True
            except Exception:
                import traceback
                logger.error('Alter search cache restore failed: %s' % traceback.format_exc())
                win.clearProperty('xstream.alterSearchResults')

    # Neuer Titel oder kein Cache — neue Suche starten
    win.clearProperty('xstream.alterSearchResults')
    win.setProperty('xstream.alterSearchTitle', searchTitle)

    oGui._collectMode = True
    aPlugins = cPluginHandler().getAvailablePlugins()

    dialog = xbmcgui.DialogProgress()
    dialog.create(cConfig().getLocalizedString(30122), cConfig().getLocalizedString(30123))

    searchablePlugins = [
        pluginEntry for pluginEntry in aPlugins
        if pluginEntry['globalsearch'] not in ['false', '']
    ]

    def worker(pluginEntry):
        logger.debug('Searching for ' + searchTitle + pluginEntry['id'])
        _pluginSearch(pluginEntry, searchTitle, oGui)
        return pluginEntry['name']

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_plugin = {executor.submit(worker, plugin): plugin for plugin in searchablePlugins}

        for count, future in enumerate(concurrent.futures.as_completed(future_to_plugin)):
            plugin = future_to_plugin[future]
            if dialog.iscanceled():
                oGui.setEndOfDirectory()
                return
            try:
                name = future.result()
            except Exception as e:
                name = plugin['name']
                logger.error(f"Fehler bei Plugin {name}: {str(e)}")
            dialog.update((count + 1) * 50 // len(searchablePlugins) + 50, name + cConfig().getLocalizedString(30125))

    dialog.close()

    # Ergebnisse filtern
    filteredResults = []
    for result in oGui.searchResults:
        guiElement = result['guiElement']
        logger.debug('Site: %s Titel: %s' % (guiElement.getSiteName(), guiElement.getTitle()))
        if searchTitle not in guiElement.getTitle():
            continue
        if guiElement._sYear and searchYear and guiElement._sYear != searchYear:
            continue
        if searchImdbId and guiElement.getItemProperties().get('imdbID') != searchImdbId:
            continue
        filteredResults.append(result)

    # Gefilterte Ergebnisse cachen
    try:
        win.setProperty('xstream.alterSearchResults', _serializeSearchResults(filteredResults))
    except Exception:
        import traceback
        logger.error('Alter search cache save failed: %s' % traceback.format_exc())

    oGui._collectMode = False
    total = len(filteredResults)
    for result in sorted(filteredResults, key=lambda k: k['guiElement'].getSiteName()):
        oGui.addFolder(result['guiElement'], result['params'], bIsFolder=result['isFolder'], iTotal=total)

    oGui.setView()
    oGui.setEndOfDirectory()
    xbmc.executebuiltin('Container.Update')
    return True

def searchTMDB(params):
    sSearchText = params.getValue('searchTitle')
    oGui = cGui()
    oGui.globalSearch = True
    oGui._collectMode = True

    if not sSearchText:
        oGui.setEndOfDirectory()
        return True

    aPlugins = cPluginHandler().getAvailablePlugins()

    dialog = xbmcgui.DialogProgress()
    dialog.create(cConfig().getLocalizedString(30122), cConfig().getLocalizedString(30123))

    searchablePlugins = [
        pluginEntry for pluginEntry in aPlugins
        if pluginEntry['globalsearch'] != 'false'
    ]

    def worker(pluginEntry):
        logger.debug('Searching for %s at %s' % (sSearchText, pluginEntry['id']))
        _pluginSearch(pluginEntry, sSearchText, oGui)
        return pluginEntry['name']

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_plugin = {executor.submit(worker, plugin): plugin for plugin in searchablePlugins}

        for count, future in enumerate(concurrent.futures.as_completed(future_to_plugin)):
            plugin = future_to_plugin[future]
            if dialog.iscanceled():
                oGui.setEndOfDirectory()
                return
            try:
                name = future.result()
            except Exception as e:
                name = plugin['name']
                logger.error(f"Fehler bei Plugin {name}: {str(e)}")
            dialog.update((count + 1) * 50 // len(searchablePlugins) + 50, name + cConfig().getLocalizedString(30125))

    dialog.close()

    oGui._collectMode = False
    total = len(oGui.searchResults)

    dialog = xbmcgui.DialogProgress()
    dialog.create(cConfig().getLocalizedString(30126), cConfig().getLocalizedString(30127))

    for count, result in enumerate(sorted(oGui.searchResults, key=lambda k: k['guiElement'].getSiteName()), 1):
        if dialog.iscanceled():
            oGui.setEndOfDirectory()
            return
        oGui.addFolder(result['guiElement'], result['params'], bIsFolder=result['isFolder'], iTotal=total)
        dialog.update(count * 100 // total, str(count) + cConfig().getLocalizedString(30128) + str(total) + ': ' + result['guiElement'].getTitle())

    dialog.close()
    oGui.setView()
    oGui.setEndOfDirectory()
    return True


def _pluginSearch(pluginEntry, sSearchText, oGui):
    try:
        plugin = __import__(pluginEntry['id'], globals(), locals())
        function = getattr(plugin, '_search')
        function(oGui, sSearchText)
    except Exception:
        logger.error(pluginEntry['name'] + ': search failed')
        import traceback
        logger.error(traceback.format_exc())
