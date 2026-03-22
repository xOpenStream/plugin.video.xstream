# -*- coding: utf-8 -*-
# Python 3
# YouTube API Key Registration via api_keys.json (no YouTube addon file modifications)

import json
import os
import sys
import xbmc
import xbmcvfs

from resources.lib.config import cConfig

# Pfad zur api_keys.json im YouTube Addon Userdata
storedb = xbmcvfs.translatePath('special://home/userdata/addon_data/plugin.video.youtube/api_keys.json')


def YT():
    try:
        apikey = cConfig('plugin.video.youtube').getSetting('youtube.api.key')
    except:
        xbmc.executebuiltin('InstallAddon(%s)' % 'plugin.video.youtube')
        sys.exit()

    api_key = 'AIzaSyDnlJ0e_CZlLoZm7CMNnO41xInZgVFyObo'
    client_id = '869922081769-d392du3vu6c8cpmtll11rpd7f09deu1n.apps.googleusercontent.com'
    client_secret = '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'

    if apikey == '' or apikey is None:
        # Nicht überschreiben wenn der User bereits eigene Daten konfiguriert hat
        if os.path.exists(storedb):
            return

        data = {
            "keys": {
                "developer": {},
                "personal": {
                    "api_key": api_key,
                    "client_id": client_id,
                    "client_secret": client_secret
                }
            }
        }

        try:
            os.makedirs(os.path.dirname(storedb), exist_ok=True)
            with open(storedb, 'w') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            xbmc.log('[xStream] youtube_fix: Fehler beim Schreiben der api_keys.json: %s' % str(e), xbmc.LOGERROR)