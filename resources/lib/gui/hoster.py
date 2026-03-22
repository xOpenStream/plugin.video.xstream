# -*- coding: utf-8 -*-
# Python 3
#
# 24.01.23 - Heptamer: Korrektur getpriorities (nun werden alle Hoster gelesen und sortiert)
# 22.12.24 - Heptamer: m3u8 und mpd Files - MimeType für native Kodi Wiedergabe

import xbmc
import xbmcgui 
import xbmcplugin
from resources.lib.handler.ParameterHandler import ParameterHandler
from resources.lib.gui.guiElement import cGuiElement
from resources.lib.gui.gui import cGui
from resources.lib.config import cConfig
from resources.lib.player import cPlayer
from resources.lib.tools import logger


class cHosterGui:
    SITE_NAME = 'cHosterGui'

    def __init__(self):
        self.maxHoster = int(cConfig().getSetting('maxHoster', 100))
        self.dialog = False

    # TODO: unify parts of play, download etc.
    def _getInfoAndResolve(self, siteResult):
        oGui = cGui()
        params = ParameterHandler()
        # get data
        mediaUrl = params.getValue('sMediaUrl')
        fileName = params.getValue('MovieTitle')
        try:
            try:
                import resolveurl as resolver
            except:
                import urlresolver as resolver
            # resolve
            if siteResult:
                mediaUrl = siteResult.get('streamUrl', False)
                mediaId = siteResult.get('streamID', False)
                if mediaUrl:
                    logger.info('-> [hoster]: resolve: ' + mediaUrl)
                    link = mediaUrl if siteResult['resolved'] else resolver.resolve(mediaUrl)
                elif mediaId:
                    logger.info('-> [hoster]: resolve: hoster: %s - mediaID: %s' % (siteResult['host'], mediaId))
                    link = resolver.HostedMediaFile(host=siteResult['host'].lower(), media_id=mediaId).resolve()
                else:
                    oGui.showError('xStream', cConfig().getLocalizedString(30134), 5)
                    return False
            elif mediaUrl:
                logger.info('-> [hoster]: resolve: ' + mediaUrl)
                link = resolver.resolve(mediaUrl)
            else:
                oGui.showError('xStream', cConfig().getLocalizedString(30134), 5)
                return False
        except resolver.resolver.ResolverError as e:
            logger.error('-> [hoster]: ResolverError: %s' % e)
            oGui.showError('xStream', cConfig().getLocalizedString(30135), 7)
            return False
        # resolver response
        if link is not False:
            data = {'title': fileName, 'season': params.getValue('season'), 'episode': params.getValue('episode'), 'showTitle': params.getValue('TVShowTitle'), 'thumb': params.getValue('thumb'), 'link': link, 'imdb_id': params.getValue('imdb_id'), 'year': params.getValue('year'), 'mediaType': params.getValue('mediaType')}
            return data
        return False

    def play(self, siteResult=False):
        logger.info('-> [hoster]: attempt to play file')
        data = self._getInfoAndResolve(siteResult)
        if not data:
            return False
        if self.dialog:
            try:
                self.dialog.close()
            except:
                pass

        logger.info('-> [hoster]: play file link: ' + str(data['link']))
        list_item = xbmcgui.ListItem(path=data['link'])
        # MimeType setzen damit Kodi das Format nativ erkennt
        if '.mpd' in data['link']:
            list_item.setMimeType('application/dash+xml')
            list_item.setContentLookup(False)
        elif '.m3u8' in data['link']:
            list_item.setMimeType('application/vnd.apple.mpegurl')
            list_item.setContentLookup(False)

        if 'youtube' in data['link']:
            import time
            time.sleep(1)
        if data['thumb']:
            list_item.setArt(data['thumb'])

        vtag = list_item.getVideoInfoTag()
        # Korrekten MediaType setzen (für Trakt.TV Scrobbling)
        if data.get('showTitle') and data.get('episode'):
            vtag.setMediaType('episode')
        elif data.get('mediaType') in ('movie', 'episode', 'tvshow', 'season'):
            vtag.setMediaType(data['mediaType'])
        else:
            vtag.setMediaType('video')
        if data.get('title'):
            try:
                vtag.setTitle(str(data['title']))
            except: pass
        if data.get('showTitle'):
            try:
                vtag.setTvShowTitle(data['showTitle'])
            except: pass
            if data.get('season'):
                try:
                    vtag.setSeason(int(data['season']))
                except: pass
            if data.get('episode'):
                try:
                    vtag.setEpisode(int(data['episode']))
                except: pass
        # Jahr und IMDb ID setzen (für Trakt.TV Scrobbling)
        if data.get('year'):
            try:
                vtag.setYear(int(data['year']))
            except: pass
        if data.get('imdb_id'):
            try:
                vtag.setUniqueID(str(data['imdb_id']), 'imdb', True)
            except: pass

        list_item.setProperty('IsPlayable', 'true')
        if cGui().pluginHandle > 0:
            xbmcplugin.setResolvedUrl(cGui().pluginHandle, True, list_item)
        else:
            xbmc.Player().play(data['link'], list_item)
        return cPlayer().startPlayer()

    def addToPlaylist(self, siteResult=False):
        oGui = cGui()
        logger.info('-> [hoster]: attempt addToPlaylist')
        data = self._getInfoAndResolve(siteResult)
        if not data: return False
        logger.info('-> [hoster]: addToPlaylist file link: ' + str(data['link']))
        oGuiElement = cGuiElement()
        oGuiElement.setSiteName(self.SITE_NAME)
        oGuiElement.setMediaUrl(data['link'])
        oGuiElement.setTitle(data['title'])
        if data['thumb']:
            oGuiElement.setThumbnail(data['thumb'])
        if data['showTitle']:
            oGuiElement.setEpisode(data['episode'])
            oGuiElement.setSeason(data['season'])
            oGuiElement.setTVShowTitle(data['showTitle'])
        if self.dialog:
            self.dialog.close()
        oPlayer = cPlayer()
        oPlayer.addItemToPlaylist(oGuiElement)
        oGui.showInfo(cConfig().getLocalizedString(30136), cConfig().getLocalizedString(30137), 5)
        return True

    def download(self, siteResult=False):
        logger.info('-> [hoster]: attempt download')
        data = self._getInfoAndResolve(siteResult)
        if not data: return False
        logger.info('-> [hoster]: download file link: ' + data['link'])
        if self.dialog:
            self.dialog.close()

        # Check which download managers are configured
        downloadOptions = []
        downloadModes = []
        if cConfig().getSetting('jd2_enabled') == 'true':
            downloadOptions.append('JDownloader 2')
            downloadModes.append('jd2')
        if cConfig().getSetting('myjd_enabled') == 'true':
            downloadOptions.append('My.JDownloader')
            downloadModes.append('myjd')


        selectedMode = 'direct'
        if downloadOptions:
            # Add direct download as last option
            downloadOptions.append(cConfig().getLocalizedString(30245))  # "Download"
            downloadModes.append('direct')
            dialog = xbmcgui.Dialog()
            idx = dialog.select('Download', downloadOptions)
            if idx < 0:
                return False  # User cancelled
            selectedMode = downloadModes[idx]

        if selectedMode == 'jd2':
            self.sendToJDownloader2(siteResult['streamUrl'] if siteResult and 'streamUrl' in siteResult else data['link'])
        elif selectedMode == 'myjd':
            self.sendToMyJDownloader(siteResult['streamUrl'] if siteResult and 'streamUrl' in siteResult else data['link'], data['title'])
        else:
            from resources.lib.download import cDownload
            oDownload = cDownload()
            oDownload.download(data['link'], data['title'])
        return True

    def sendToJDownloader2(self, sMediaUrl=False):
        from resources.lib.handler.jdownloader2Handler import cJDownloader2Handler
        params = ParameterHandler()
        if not sMediaUrl:
            sMediaUrl = params.getValue('sMediaUrl')
        if self.dialog:
            self.dialog.close()
        logger.info('-> [hoster]: call send to JDownloader2: ' + sMediaUrl)
        cJDownloader2Handler().sendToJDownloader2(sMediaUrl)

    def sendToMyJDownloader(self, sMediaUrl=False, sMovieTitle='xStream'):
        from resources.lib.handler.myjdownloaderHandler import cMyJDownloaderHandler
        params = ParameterHandler()
        if not sMediaUrl:
            sMediaUrl = params.getValue('sMediaUrl')
        sMovieTitle = params.getValue('MovieTitle')
        if not sMovieTitle:
            sMovieTitle = params.getValue('Title')
        if not sMovieTitle:  # only temporary
            sMovieTitle = params.getValue('sMovieTitle')
        if not sMovieTitle:
            sMovieTitle = params.getValue('title')
        if self.dialog:
            self.dialog.close()
        logger.info('-> [hoster]: call send to My.JDownloader: ' + sMediaUrl)
        cMyJDownloaderHandler().sendToMyJDownloader(sMediaUrl, sMovieTitle)

    def __getPriorities(self, hosterList, filter=True):
        # Sort hosters based on their resolvers priority.
        ranking = []

        # Import resolver module once (Python caches modules, re-importing in loop has no effect)
        try:
            import resolveurl as resolver_module
        except:
            import urlresolver as resolver_module

        for hoster in hosterList:
            # accept hoster which is marked as resolveable by sitePlugin
            if hoster.get('resolveable', False):
                ranking.append([0, hoster])
                continue

            try:
                # serienstream VOE hoster = {'link': [sUrl, sName], aus array "[0]" True bzw. False
                link = hoster['link'][0] if isinstance(hoster['link'], list) else hoster['link']
                hmf = resolver_module.HostedMediaFile(url=link)
            except Exception as e:
                logger.error('-> [hoster]: getPriorities HostedMediaFile error: %s' % e)
                continue

            if not hmf.valid_url():
                hmf = resolver_module.HostedMediaFile(host=hoster['name'].lower(), media_id='dummy')

            resolvers = hmf.get_resolvers()
            if resolvers:
                priority = None
                for res in resolvers:
                    # prefer individual hoster priority over universal (debrid) priority
                    if not res.isUniversal():
                        priority = res._get_priority()
                        break
                    if priority is None:
                        priority = res._get_priority()
                if priority is not None:
                    ranking.append([priority, hoster])
            elif not filter:
                ranking.append([999, hoster])

        # Combined sort: Language (asc) -> Quality (desc) -> Resolver Priority (asc)
        pref_quali = cConfig().getSetting('preferedQuality')
        has_language = any('languageCode' in hoster[1] for hoster in ranking)

        def sort_key(item):
            priority, hoster = item

            # 1) Language: ascending (lower code = preferred). Default 999 if no languageCode.
            lang = hoster.get('languageCode', 999) if has_language else 0

            # 2) Quality: hosters with quality info ranked higher than those without.
            #    If preferedQuality is a specific resolution (not '5'/Best),
            #    exact matches get top priority (0), others sorted descending by quality.
            #    If preferedQuality is '5' (Best), sort descending by quality value.
            has_qual = 'quality' in hoster
            if has_qual:
                qual = int(hoster['quality'])
                if pref_quali != '5':
                    # Exact match = 0 (best), non-match = 1, then within non-matches higher quality first
                    qual_match = 0 if qual == int(pref_quali) else 1
                    qual_value = -qual  # negative for descending sort
                else:
                    qual_match = 0
                    qual_value = -qual  # negative for descending sort (higher quality first)
            else:
                # No quality info: sort after hosters with known quality
                qual_match = 2
                qual_value = 0

            # 3) Resolver priority: ascending (lower = better)
            res_prio = priority

            return (lang, qual_match, qual_value, res_prio)

        try:
            ranking = sorted(ranking, key=sort_key)
        except Exception as e:
            logger.error('-> [hoster]: getPriorities sort error: %s' % e)

        return [hoster for _, hoster in ranking]

    def stream(self, playMode, siteName, function, url):
        self.dialog = xbmcgui.DialogProgress()
        self.dialog.create('xStream', cConfig().getLocalizedString(30138))
        # load site as plugin and run the function
        self.dialog.update(5, cConfig().getLocalizedString(30139))
        plugin = __import__(siteName, globals(), locals())
        function = getattr(plugin, function)
        self.dialog.update(10, cConfig().getLocalizedString(30140))
        if url:
            siteResult = function(url)
        else:
            siteResult = function()
        self.dialog.update(40)
        if not siteResult:
            self.dialog.close()
            cGui().showInfo('xStream', cConfig().getLocalizedString(30141))
            return
        # if result is not a list, make in one
        if not type(siteResult) is list:
            temp = [siteResult]
            siteResult = temp
        # field "name" marks hosters
        if 'name' in siteResult[0]:
            functionName = siteResult[-1]
            del siteResult[-1]
            if not siteResult:
                self.dialog.close()
                cGui().showInfo('xStream', cConfig().getLocalizedString(30142))
                return

            self.dialog.update(60, cConfig().getLocalizedString(30143))
            if (playMode != 'jd2') and (cConfig().getSetting('presortHoster') == 'true') and (playMode != 'myjd'):
                siteResult = self.__getPriorities(siteResult)
            if not siteResult:
                self.dialog.close()
                cGui().showInfo('xStream', cConfig().getLocalizedString(30144))
                return False
            self.dialog.update(90)
            # self.dialog.close()
            if len(siteResult) > self.maxHoster:
                siteResult = siteResult[:self.maxHoster - 1]
            if cConfig().getSetting('hosterSelect') == 'List':
                self.showHosterFolder(siteResult, siteName, functionName)
                return
            if len(siteResult) > 1:
                # choose hoster
                siteResult = self._chooseHoster(siteResult)
                if not siteResult:
                    return
            else:
                siteResult = siteResult[0]
            # get stream links
            logger.info(siteResult['link'])
            function = getattr(plugin, functionName)
            siteResult = function(siteResult['link'])
            # if result is not a list, make in one
            if not type(siteResult) is list:
                temp = [siteResult]
                siteResult = temp
        # choose part
        if len(siteResult) > 1:
            siteResult = self._choosePart(siteResult)
            if not siteResult:
                logger.info('-> [hoster]: no part selected')
                return
        else:
            siteResult = siteResult[0]

        self.dialog = xbmcgui.DialogProgress()
        self.dialog.create('xStream', cConfig().getLocalizedString(30145))
        self.dialog.update(95, cConfig().getLocalizedString(30146))
        if playMode == 'play':
            self.play(siteResult)
        elif playMode == 'download':
            self.download(siteResult)
        elif playMode == 'enqueue':
            self.addToPlaylist(siteResult)
        elif playMode == 'jd2':
            self.sendToJDownloader2(siteResult['streamUrl'])
        elif playMode == 'myjd':
            self.sendToMyJDownloader(siteResult['streamUrl'])

    def streamAuto(self, playMode, siteName, function):
        logger.info('-> [hoster]: auto stream initiated')
        self.dialog = xbmcgui.DialogProgress()
        self.dialog.create('xStream', cConfig().getLocalizedString(30138))
        # load site as plugin and run the function
        self.dialog.update(5, cConfig().getLocalizedString(30139))
        plugin = __import__(siteName, globals(), locals())
        function = getattr(plugin, function)
        self.dialog.update(10, cConfig().getLocalizedString(30140))
        siteResult = function()
        if not siteResult:
            self.dialog.close()
            cGui().showInfo('xStream', cConfig().getLocalizedString(30141))
            return False
        # if result is not a list, make in one
        if not type(siteResult) is list:
            temp = [siteResult]
            siteResult = temp
        # field "name" marks hosters
        if 'name' in siteResult[0]:
            self.dialog.update(90, cConfig().getLocalizedString(30143))
            functionName = siteResult[-1]
            del siteResult[-1]
            if siteName.startswith('dummy'):
                hosters = siteResult
            else:
                hosters = self.__getPriorities(siteResult)
            if not hosters:
                self.dialog.close()
                cGui().showInfo('xStream', cConfig().getLocalizedString(30144))
                return False
            if len(siteResult) > self.maxHoster:
                siteResult = siteResult[:self.maxHoster - 1]
            check = False
            self.dialog.create('xStream', cConfig().getLocalizedString(30147))
            total = len(hosters)
            for count, hoster in enumerate(hosters):
                if self.dialog.iscanceled() or xbmc.Monitor().abortRequested() or check: return
                percent = (count + 1) * 100 // total
                try:
                    logger.info('-> [hoster]: try hoster %s' % hoster['name'])
                    self.dialog.create('xStream', cConfig().getLocalizedString(30147))
                    self.dialog.update(percent, cConfig().getLocalizedString(30147) + ' %s' % hoster['name'])
                    # get stream links
                    function = getattr(plugin, functionName)
                    siteResult = function(hoster['link'])
                    check = self.__autoEnqueue(siteResult, playMode)
                    if check:
                        return True
                except:
                    self.dialog.update(percent, cConfig().getLocalizedString(30148) % hoster['name'])
                    logger.error('-> [hoster]: playback with hoster %s failed' % hoster['name'])
        # field "resolved" marks streamlinks
        elif 'resolved' in siteResult[0]:
            for stream in siteResult:
                try:
                    if self.__autoEnqueue(siteResult, playMode):
                        self.dialog.close()
                        return True
                except:
                    pass

    def _chooseHoster(self, siteResult):
        dialog = xbmcgui.Dialog()
        titles = []
        for result in siteResult:
            if 'displayedName' in result:
                titles.append(str(result['displayedName']))
            else:
                titles.append(str(result['name']))
        index = dialog.select(cConfig().getLocalizedString(30149), titles)
        if index > -1:
            siteResult = siteResult[index]
            return siteResult
        else:
            logger.info('-> [hoster]: no hoster selected')
            return False

    def _choosePart(self, siteResult):
        self.dialog = xbmcgui.Dialog()
        titles = []
        for result in siteResult:
            titles.append(str(result['title']))
        index = self.dialog.select(cConfig().getLocalizedString(30150), titles)
        if index > -1:
            siteResult = siteResult[index]
            return siteResult
        else:
            return False

    def showHosterFolder(self, siteResult, siteName, functionName):
        oGui = cGui()
        total = len(siteResult)
        params = ParameterHandler()
        for hoster in siteResult:
            if 'displayedName' in hoster:
                name = hoster['displayedName']
            else:
                name = hoster['name']
            oGuiElement = cGuiElement(name, siteName, functionName)
            oGuiElement.setThumbnail(str(params.getValue('thumb')))
            params.setParam('url', hoster['link'])
            params.setParam('isHoster', 'true')
            oGui.addFolder(oGuiElement, params, iTotal=total, isHoster=True)
        oGui.setEndOfDirectory()

    def __autoEnqueue(self, partList, playMode):
        # choose part
        if not partList:
            return False
        for i in range(len(partList) - 1, -1, -1):
            try:
                if playMode == 'play' and i == 0:
                    if not self.play(partList[i]):
                        return False
                elif playMode == 'download':
                    self.download(partList[i])
                elif playMode == 'enqueue' or (playMode == 'play' and i > 0):
                    self.addToPlaylist(partList[i])
            except:
                return False
        logger.info('-> [hoster]: autoEnqueue successful')
        return True


class Hoster:
    def __init__(self, name, link):
        self.name = name
        self.link = link