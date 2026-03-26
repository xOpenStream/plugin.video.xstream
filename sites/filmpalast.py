# -*- coding: utf-8 -*-
# Python 3

# Always pay attention to the translations in the menu!
# Sprachauswahl für Filme
# HTML LangzeitCache hinzugefügt
# showValue:     24 Stunden
# showEntries:    6 Stunden
# showEpisodes:   4 Stunden

import re
import xbmcgui
from resources.lib.handler.ParameterHandler import ParameterHandler
from resources.lib.handler.requestHandler import cRequestHandler
from resources.lib.logger import logger
from resources.lib.tools import cParser
from resources.lib.gui.guiElement import cGuiElement
from resources.lib.config import cConfig
from resources.lib.gui.gui import cGui


SITE_IDENTIFIER = 'filmpalast'
SITE_NAME = 'FilmPalast'
SITE_ICON = 'filmpalast.png'

# Global search function is thus deactivated!
if cConfig().getSetting('global_search_' + SITE_IDENTIFIER) == 'false':
    SITE_GLOBAL_SEARCH = False
    logger.info('-> [SitePlugin]: globalSearch for %s is deactivated.' % SITE_NAME)

# Domain Abfrage
DOMAIN = cConfig().getSetting('plugin_' + SITE_IDENTIFIER + '.domain', 'filmpalast.to') # Domain Auswahl über die Einstellungen möglich
STATUS = cConfig().getSetting('plugin_' + SITE_IDENTIFIER + '_status') # Status Code Abfrage der Domain
ACTIVE = cConfig().getSetting('plugin_' + SITE_IDENTIFIER) # Ob Plugin aktiviert ist oder nicht

URL_MAIN = 'https://' + DOMAIN
URL_MOVIES = URL_MAIN + '/movies/%s'
URL_ENGLISH = URL_MAIN + '/search/genre/Englisch'
URL_SEARCH = URL_MAIN + '/search/title/%s'
URL_SERIES = URL_MAIN + '/serien/view'


def load(): # Menu structure of the site plugin
    logger.info('Load %s' % SITE_NAME)
    xbmcgui.Window(10000).clearProperty('xstream.filmpalast.lastSearchText')
    params = ParameterHandler()
    sLanguage = cConfig().getSetting('prefLanguage')

    # English ganz oben wenn Sprache "Alle" oder "English"
    if sLanguage == '0' or sLanguage == '2':    # Alle Sprachen oder English
        params.setParam('sUrl', URL_ENGLISH)
        cGui().addFolder(cGuiElement(cConfig().getLocalizedString(30104), SITE_IDENTIFIER, 'showEntries'), params) # English

    # Neu
    params.setParam('sUrl', URL_MAIN)
    cGui().addFolder(cGuiElement(cConfig().getLocalizedString(30500), SITE_IDENTIFIER, 'showEntries'), params)  # Neu

    # Deutsche Kategorien (bei Alle oder Deutsch)
    if sLanguage == '0' or sLanguage == '1':    # Alle Sprachen oder Deutsch
        params.setParam('sUrl', URL_MOVIES % 'new')
        cGui().addFolder(cGuiElement(cConfig().getLocalizedString(30502), SITE_IDENTIFIER, 'showEntries'), params)   # Filme
        params.setParam('sUrl', URL_MOVIES % 'top')
        cGui().addFolder(cGuiElement(cConfig().getLocalizedString(30509), SITE_IDENTIFIER, 'showEntries'), params)  # Top movies
        params.setParam('sUrl', URL_MOVIES % 'imdb')
        cGui().addFolder(cGuiElement(cConfig().getLocalizedString(30510), SITE_IDENTIFIER, 'showEntries'), params) # IMDB rating
        params.setParam('sUrl', URL_MOVIES % 'new')
        params.setParam('value', 'genre')
        cGui().addFolder(cGuiElement(cConfig().getLocalizedString(30506), SITE_IDENTIFIER, 'showValue'), params)    # Genre
        params.setParam('value', 'movietitle')
        cGui().addFolder(cGuiElement(cConfig().getLocalizedString(30517), SITE_IDENTIFIER, 'showValue'), params)  # From A-Z

    if sLanguage == '3':    # Japanisch
        cGui().showLanguage()

    # Add Serien entry above search
    cGui().addFolder(cGuiElement(cConfig().getLocalizedString(30511), SITE_IDENTIFIER, 'showSeriesMenu'))  # Serien

    # Search added at the bottom
    cGui().addFolder(cGuiElement(cConfig().getLocalizedString(30520), SITE_IDENTIFIER, 'showSearch'), params)   # Search
    cGui().setEndOfDirectory()


def showValue():
    params = ParameterHandler()
    value = params.getValue("value")
    oRequest = cRequestHandler(params.getValue('sUrl'), bypass_dns=True)
    if cConfig().getSetting('global_search_' + SITE_IDENTIFIER) == 'true':
        oRequest.cacheTime = 60 * 60 * 24 # HTML Cache Zeit 1 Tag
    sHtmlContent = oRequest.request()
    pattern = '<section[^>]id="%s">(.*?)</section>' % value # Suche in der Section Einträge
    isMatch, sContainer = cParser.parseSingleResult(sHtmlContent, pattern)
    if isMatch:
        isMatch, aResult = cParser.parse(sContainer, 'href="([^"]+)">([^<]+)')
        aResult = sorted(aResult, key=lambda x: x[1].lower())  # Sort alphabetically by name (case-insensitive)
        for sUrl, sName in aResult:
            params.setParam('sUrl', sUrl)
            cGui().addFolder(cGuiElement(sName, SITE_IDENTIFIER, 'showEntries'), params)
    if not isMatch:
        cGui().showInfo()
        return
    cGui().setEndOfDirectory()


def _parsePage(sHtmlContent):
    """Parst eine einzelne Seite und gibt (isMatch, aResult) zurück."""
    pattern = r'<article[^>]*>\s*<a href="([^"]+)" title="([^"]+)">\s*<img src=["\']([^"\']+)["\'][^>]*>(.*?)</article>'
    isMatch, aResult = cParser.parse(sHtmlContent, pattern)
    if not isMatch:
        pattern = r'<a[^>]*href="([^"]*)"[^>]*title="([^"]*)"[^>]*>[^<]*<img[^>]*src=["\']([^"\']*)["\'][^>]*>\s*</a>(\s*)</article>'
        isMatch, aResult = cParser.parse(sHtmlContent, pattern)
    return isMatch, aResult if isMatch else []


def _getNextPageUrl(sHtmlContent):
    """Extrahiert die nächste Seiten-URL oder gibt False zurück."""
    pattern = r'<a class="pageing[^"]*"\s*href=([^>]+)>[^\+]+\+</a>\s*</div>'
    isMatch, sNextUrl = cParser.parseSingleResult(sHtmlContent, pattern)
    if isMatch:
        sNextUrl = sNextUrl.replace("'", "").replace('"', '')
        if sNextUrl.startswith('/'):
            sNextUrl = URL_MAIN + sNextUrl
        return sNextUrl
    return False


def _fetchAllSearchPages(startUrl, sGui=False):
    """Holt ALLE Seiten einer Suche und gibt kombinierte Ergebnisse zurück."""
    allResults = []
    currentUrl = startUrl
    maxPages = 10  # Sicherheitslimit

    for page in range(maxPages):
        currentUrl = currentUrl.replace(' ', '%20')
        oRequest = cRequestHandler(currentUrl, ignoreErrors=(sGui is not False), bypass_dns=True)
        if cConfig().getSetting('global_search_' + SITE_IDENTIFIER) == 'true':
            oRequest.cacheTime = 60 * 60 * 6
        sHtmlContent = oRequest.request()
        if not sHtmlContent:
            break

        isMatch, aResult = _parsePage(sHtmlContent)
        if isMatch:
            allResults.extend(aResult)

        nextUrl = _getNextPageUrl(sHtmlContent)
        if not nextUrl:
            break
        currentUrl = nextUrl

    return allResults


def showEntries(entryUrl=False, sGui=False, sSearchText=False):
    oGui = sGui if sGui else cGui()
    params = ParameterHandler()
    if not entryUrl: entryUrl = params.getValue('sUrl')
    entryUrl = entryUrl.replace(' ', '%20')  # Leerzeichen in URL encoden
    isTvshow = False

    # Bei Suche: ALLE Seiten auf einmal holen
    if sSearchText:
        aResult = _fetchAllSearchPages(entryUrl, sGui)
        isMatch = len(aResult) > 0
        sHtmlContent = None  # Nicht mehr nötig für Pagination
    else:
        oRequest = cRequestHandler(entryUrl, ignoreErrors=(sGui is not False), bypass_dns=True)
        if cConfig().getSetting('global_search_' + SITE_IDENTIFIER) == 'true':
            oRequest.cacheTime = 60 * 60 * 6  # 6 Stunden
        sHtmlContent = oRequest.request()
        isMatch, aResult = _parsePage(sHtmlContent)

    if not isMatch:
        if not sGui: oGui.showInfo()
        return

    total = len(aResult)
    seen_tv_shows = set()
    
    # Sortierung (alphabetisch)
    aResult = sorted(aResult, key=lambda x: x[1].lower())
    
    for sUrl, sName, sThumbnail, sDummy in aResult:
        isTvshow, _ = cParser.parse(sName, r'S\d\dE\d\d')
        
        # Lockerer Suchfilter (ignoriert Sonderzeichen/Case)
        if sSearchText:
            search_clean = re.sub(r'\W+', '', sSearchText).lower()
            name_clean = re.sub(r'\W+', '', sName).lower()
            if search_clean not in name_clean:
                continue

        # Dedupe Logik für Serien (beibehalten)
        if isTvshow:
            cleanNameMatch = re.search(r'(.*?)\s*S\d+E\d+', sName, re.IGNORECASE)
            if cleanNameMatch:
                cleanName = cleanNameMatch.group(1).strip()
                if cleanName in seen_tv_shows:
                    continue
                seen_tv_shows.add(cleanName)
                sName = cleanName

        if sThumbnail.startswith('/'):
            sThumbnail = URL_MAIN + sThumbnail

        isYear, sYear = cParser.parseSingleResult(sDummy, r'Jahr:[^>]([\d]+)')
        isDuration, sDuration = cParser.parseSingleResult(sDummy, r'(?:Laufzeit|Spielzeit):[^>]([\d]+)')
        isRating, sRating = cParser.parseSingleResult(sDummy, 'Imdb:[^>]([^/]+)')

        oGuiElement = cGuiElement(sName, SITE_IDENTIFIER, 'showSeasons' if isTvshow else 'showHosters')
        oGuiElement.setMediaType('tvshow' if isTvshow else 'movie')
        oGuiElement.setThumbnail(sThumbnail)
        if isYear: oGuiElement.setYear(sYear)
        if isDuration: oGuiElement.addItemValue('duration', sDuration)
        if isRating: oGuiElement.addItemValue('rating', sRating.replace(',', '.'))

        if sUrl.startswith('//'):
            params.setParam('entryUrl', 'https:' + sUrl)
        else:
            params.setParam('entryUrl', sUrl)
        
        params.setParam('sName', sName)
        params.setParam('sThumbnail', sThumbnail)
        oGui.addFolder(oGuiElement, params, isTvshow, total)

    # --- PAGINATION nur für Kategorien (nicht für Suche, da schon alle Seiten geholt) ---
    if not sGui and not sSearchText and sHtmlContent:
        nextUrl = _getNextPageUrl(sHtmlContent)
        if nextUrl:
            params.setParam('sUrl', nextUrl)
            oGui.addNextPage(SITE_IDENTIFIER, 'showEntries', params)
    if not sGui:
        oGui.setView('tvshows' if isTvshow else 'movies')
        if not sSearchText:
            oGui.setEndOfDirectory()

def showSeasons():
    params = ParameterHandler()
    # Parameter laden
    sUrl = params.getValue('entryUrl')
    sThumbnail = params.getValue("sThumbnail")
    sName = params.getValue('sName')
    oRequest = cRequestHandler(sUrl, bypass_dns=True)
    if cConfig().getSetting('global_search_' + SITE_IDENTIFIER) == 'true':
        oRequest.cacheTime = 60 * 60 * 6  # HTML Cache Zeit 6 Stunden
    sHtmlContent = oRequest.request()
    pattern = r'<a[^>]*class="staffTab"[^>]*data-sid="(\d+)"[^>]*>'
    isMatch, aResult = cParser.parse(sHtmlContent, pattern)
    if not isMatch:
        cGui().showInfo()
        return
    isDesc, sDesc = cParser.parseSingleResult(sHtmlContent, '"description">([^<]+)')
    total = len(aResult)
    for sSeason in aResult:
        oGuiElement = cGuiElement(cConfig().getLocalizedString(30512) + ' ' + str(sSeason), SITE_IDENTIFIER, 'showEpisodes')
        oGuiElement.setTVShowTitle(sName)
        oGuiElement.setSeason(sSeason)
        oGuiElement.setMediaType('season')
        oGuiElement.setThumbnail(sThumbnail)
        if isDesc:
            oGuiElement.setDescription(sDesc)
        cGui().addFolder(oGuiElement, params, True, total)
    cGui().setView('seasons')
    cGui().setEndOfDirectory()


def showEpisodes():
    params = ParameterHandler()
    # Parameter laden
    sUrl = params.getValue('entryUrl')
    sThumbnail = params.getValue("sThumbnail")
    sSeason = params.getValue('season')
    sShowName = params.getValue('TVShowTitle')
    oRequest = cRequestHandler(sUrl, bypass_dns=True)
    if cConfig().getSetting('global_search_' + SITE_IDENTIFIER) == 'true':
        oRequest.cacheTime = 60 * 60 * 4  # HTML Cache Zeit 4 Stunden
    sHtmlContent = oRequest.request()
    pattern = r'<div[^>]*class="staffelWrapperLoop[^"]*"[^>]*data-sid="%s">(.*?)</ul></div>' % sSeason
    isMatch, sContainer = cParser.parseSingleResult(sHtmlContent, pattern)
    if not isMatch:
        cGui().showInfo()
        return

    pattern = 'href="([^"]+)'
    isMatch, aResult = cParser.parse(sContainer, pattern)
    isDesc, sDesc = cParser.parseSingleResult(sHtmlContent, '"description">([^<]+)')
    total = len(aResult)
    for sUrl in aResult:
        isMatch, sName = cParser.parseSingleResult(sUrl, r'e(\d+)')
        oGuiElement = cGuiElement(cConfig().getLocalizedString(30513) + ' ' + str(sName), SITE_IDENTIFIER, 'showHosters')
        oGuiElement.setThumbnail(sThumbnail)
        oGuiElement.setTVShowTitle(sShowName)
        oGuiElement.setSeason(sSeason)
        oGuiElement.setEpisode(sName)
        oGuiElement.setMediaType('episode')
        if sUrl.startswith('//'):
            params.setParam('entryUrl', 'https:' + sUrl)
        else:
            params.setParam('entryUrl', sUrl)
        if isDesc:
            oGuiElement.setDescription(sDesc)
        cGui().addFolder(oGuiElement, params, False, total)
    cGui().setView('episodes')
    cGui().setEndOfDirectory()


def showHosters():
    params = ParameterHandler()
    sUrl = params.getValue('entryUrl')
    if '-english' in sUrl: sLang = '(EN)'
    else: sLang = ''
    sHtmlContent = cRequestHandler(sUrl, caching=False, bypass_dns=True).request()
    pattern = 'hostName">([^<]+).*?(http[^"]+)' # Hoster Link
    releaseQuality = r'class="rb">.*?(\d\d\d+)p\.' # Release Qualität
    isMatch, aResult = cParser.parse(sHtmlContent, pattern)
    isQuality, sQuality = cParser.parseSingleResult(sHtmlContent, releaseQuality)  # sReleaseQuality auslesen z.B. 1080
    if not isQuality: sQuality = '720'
    hosters = []
    if isMatch:
        for sName, sUrl in aResult:
            sName = sName.split(' HD')[0].strip()
            if 'Filemoon' in sName or 'Swiftload' in sName or 'Vidhide' in sName:
                sUrl = sUrl + '$$https://filmpalast.to/' # Referer hinzugefügt
                if cConfig().isBlockedHoster(sName)[0]: continue  # Hoster aus settings.xml oder deaktivierten Resolver ausschließen
                hoster = {'link': sUrl, 'name': sName, 'displayedName': '%s [I]%s [%sp][/I]' % (sName, sLang, sQuality), 'languageCode': sLang, 'quality': sQuality}  # Qualität Anzeige aus Release Eintrag
                hosters.append(hoster)
            else:
                if cConfig().isBlockedHoster(sName)[0]: continue # Hoster aus settings.xml oder deaktivierten Resolver ausschließen
                hoster = {'link': sUrl, 'name': sName, 'displayedName': '%s [I]%s [%sp][/I]' % (sName, sLang, sQuality), 'languageCode': sLang, 'quality': sQuality} # Qualität Anzeige aus Release Eintrag
                hosters.append(hoster)
    if hosters:
        hosters.append('getHosterUrl')
    return hosters

def getHosterUrl(sUrl=False):
    return [{'streamUrl': sUrl, 'resolved': False}]


def showSearch():
    # Check if we have a cached search text (e.g. coming back from playback)
    win = xbmcgui.Window(10000)
    sSearchText = win.getProperty('xstream.filmpalast.lastSearchText')
    if not sSearchText:
        sSearchText = cGui().showKeyBoard(sHeading=cConfig().getLocalizedString(30281))
        if not sSearchText: return
        win.setProperty('xstream.filmpalast.lastSearchText', sSearchText)
    _search(False, sSearchText)
    cGui().setEndOfDirectory()


def _search(oGui, sSearchText):
    # Quote nutzen statt quotePlus, damit Leerzeichen als %20 übergeben werden
    showEntries(URL_SEARCH % cParser.quote(sSearchText), oGui, sSearchText)


def showSeriesMenu(): # Menu structure of series menu
    params = ParameterHandler()
    params.setParam('sUrl', URL_SERIES)
    cGui().addFolder(cGuiElement(cConfig().getLocalizedString(30518), SITE_IDENTIFIER, 'showEntries'), params) # All Series
    params.setParam('value', 'movietitle')
    cGui().addFolder(cGuiElement(cConfig().getLocalizedString(30517), SITE_IDENTIFIER, 'showValue'), params) # Von A bis Z
    cGui().setEndOfDirectory()
