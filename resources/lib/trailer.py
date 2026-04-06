# -*- coding: utf-8 -*-
# Python 3
# Version: 2026-03-08
#
# Trailer lookup — shared by xStream and xShip.
# xStream needs Phase 0 (TMDB ID resolution); xShip has TMDB ID from listings.
#
# Search: per-language priority blocks (_runTrailerSearch):
#   Block list = caller languages + EN (if missing) + ANY
#   FOR EACH block:
#     KinoCheck API (lang)         — gated: has_yt_player
#     KinoCheck YT (if DE block)   — gated: has_yt_player + has_own_key
#     TMDB videos (lang filter)    — gated: has_yt_player
#     IMDB (if EN block)           — always (direct MP4, no player needed)
#   YouTube search (per caller language) — gated: has_yt_player + has_own_key
#   Give up
#
# Play phase:
#   SmartTube: StartAndroidActivity — no API key needed, handles age-gates
#   YouTube addon: PlayMedia — ISA recommended
#   IMDB: xbmc.Player().play(mp4_url) — Kodi native player
#
# Before playing: 3s notification popup (upper-right) showing source + language.
# Poster URL passed as notification icon (Kodi stretches to square).

import re

KINOCHECK_CHANNEL = 'UCOL10n-as9dXO2qtjjFUQbQ'  # KinoCheck's YouTube channel ID

# Words that disqualify a global YouTube search result title (reactions, reviews, etc.)
_JUNK_WORDS = [
    '#short', 'react', ' review', 'explained', 'breakdown',
    'tribute', 'fan edit', 'fan made', 'fan film',
    'deleted scene', 'interview', 'commentary', 'behind the scenes',
    'music video', 'lyric', 'live performance',
    'blooper', 'gag reel', 'backstage', 'making of',
    'recap', 'full movie', 'soundtrack', 'parody', 'gameplay',
    'scene', 'comments',
]
# At least one of these must appear in a global YouTube search result title
_TRAILER_WORDS = ['trailer', 'teaser', 'official']

# Built-in API key (base64) — used for cheap 1-unit videos.list verification + user key detection
_API_CHECKSUM_B64 = b'QUl6YVN5RG5sSjBlX0NabExvWm03Q01Obk80MXhJblpnVkZ5T2Jv'

import base64 as _b64
_api_checksum = _b64.b64decode(_API_CHECKSUM_B64).decode() if _API_CHECKSUM_B64 else ''

# ── Module-level cached state (persists for Kodi session, resets on restart) ───

_smarttube_pkg = None      # SmartTube detection: None=unchecked, str=package, False=absent
_SMARTTUBE_MIN_VERSION = '30.98'  # Minimum SmartTube version for trailer playback
_yt_api_key = None         # YouTube API key: None=unchecked, str=key, ''=no key found
_yt_api_dead = False       # Set on YT API HTTP 403 — skips all remaining YT API calls
_yt_search_cache = {}      # Avoids duplicate YT searches: (title, year, lang) -> raw items
_yt_video_cache = {}       # Avoids duplicate videos.list calls: video_id -> quality info dict

_imdb_dead = False         # Set on IMDB HTTP 403/429 — skips IMDB for rest of session
_imdb_cache = {}           # IMDB GraphQL results: imdb_id -> (mp4_url, quality, expiry)
_IMDB_CACHE_TTL = 3600     # 1h cache (CloudFront signed URLs expire ~24h)


# ── Addon detection — auto-detect xStream vs xShip for branch gating ──────────
# Determines: log prefix, window property prefix, and playTrailer() code path.
# 'xstream' -> Phase 0 (TMDB resolution) + multi-source language list
# 'xship' (or anything else) -> simple language list, no Phase 0
try:
    import xbmcaddon as _xa
    _ADDON_ID = _xa.Addon().getAddonInfo('id')  # e.g. 'plugin.video.xstream'
except Exception:
    _ADDON_ID = ''
_ADDON_NAME = _ADDON_ID.split('.')[-1] if _ADDON_ID else 'trailer'  # 'xstream' or 'xship'
_LOG_TAG = '[%s.trailer]' % _ADDON_NAME       # log prefix: [xstream.trailer] or [xship.trailer]
_PROP_PREFIX = '%s.trailer' % _ADDON_NAME      # window property prefix for hint popups


# ── Module-level logger ──────────────────────────────────────────────────────

def _log(msg):
    try:
        import xbmc
        xbmc.log(_LOG_TAG + ' ' + msg, xbmc.LOGINFO)
    except Exception:
        pass


# ── YouTube addon: ensure installed + enabled ─────────────────────────────────

def _configureYouTubeAddon():
    """Konfiguriert das YouTube-Addon nach Enable/Install (wizard aus, ISA an)."""
    from xbmcaddon import Addon
    yt = Addon('plugin.video.youtube')
    yt.setSetting('kodion.setup_wizard', 'false')
    yt.setSettingInt('kodion.setup_wizard.forced_runs', 1767970800)
    yt.setSetting('kodion.video.quality.isa', 'true')
    yt.setSetting('|end_settings_marker|', 'true')


def _ensureYouTubeAddon(smarttube_low_ram=False):
    """Stellt sicher dass das YouTube-Addon installiert und aktiviert ist.
    smarttube_low_ram: True wenn SmartTube wegen RAM übersprungen wurde.
    Return: True wenn Addon bereit, False wenn nicht."""
    import xbmc, xbmcgui

    # 1. Aktiv?
    if xbmc.getCondVisibility('System.AddonIsEnabled(plugin.video.youtube)'):
        return True

    # 2. Installiert aber deaktiviert?
    if xbmc.getCondVisibility('System.HasAddon(plugin.video.youtube)'):
        if not xbmcgui.Dialog().yesno(
                'Trailer',
                'Das YouTube-Addon ist deaktiviert.\nFür Trailer-Wiedergabe aktivieren?'):
            return False
        import json
        xbmc.executeJSONRPC(json.dumps({
            'jsonrpc': '2.0', 'method': 'Addons.SetAddonEnabled',
            'params': {'addonid': 'plugin.video.youtube', 'enabled': True}, 'id': 1}))
        xbmc.sleep(1000)
        try:
            _configureYouTubeAddon()
            _log('YouTube-Addon aktiviert und konfiguriert')
        except Exception as e:
            _log('YouTube-Addon Enable-Fehler: %s' % e)
            return False
        return True

    # 3. Nicht installiert
    if smarttube_low_ram:
        msg = ('SmartTube hat zu wenig Arbeitsspeicher.\n'
               'YouTube-Addon stattdessen installieren?')
    else:
        msg = ('Das YouTube-Addon wird für Trailer benötigt.\n'
               'Jetzt installieren?')
    if not xbmcgui.Dialog().yesno('Trailer', msg):
        return False
    try:
        xbmc.executebuiltin('InstallAddon(plugin.video.youtube)')
        xbmc.executebuiltin('SendClick(11)')
        WINDOW_PROGRESS = xbmcgui.Window(10101)
        xbmc.sleep(100)
        CANCEL_BUTTON = WINDOW_PROGRESS.getControl(10)
        CANCEL_BUTTON.setEnabled(False)
        for _ in range(10):
            xbmc.sleep(1000)
            try:
                from xbmcaddon import Addon
                Addon('plugin.video.youtube')
                break
            except Exception:
                pass
        CANCEL_BUTTON.setEnabled(True)
        _configureYouTubeAddon()
        # Warten bis Addon initialisiert ist (access_manager.json etc.)
        xbmc.sleep(3000)
        _log('YouTube-Addon installiert und konfiguriert')
    except Exception as e:
        _log('YouTube-Addon Installation fehlgeschlagen: %s' % e)
        xbmcgui.Dialog().notification('Trailer', 'YouTube-Addon konnte nicht installiert werden',
                                      xbmcgui.NOTIFICATION_ERROR, 3000)
        return False
    return True


# ── SmartTube detection (Android only) ─────────────────────────────────────────

def _getSmartTubePackage():
    """Return SmartTube package name if installed on Android, else None.
    Result is cached for the session."""
    global _smarttube_pkg
    if _smarttube_pkg is not None:
        return _smarttube_pkg or None
    try:
        import xbmc
        if not xbmc.getCondVisibility('System.Platform.Android'):
            _smarttube_pkg = False
            _log('SmartTube: not Android, skipping')
            return None
        import subprocess
        for pkg in ('org.smarttube.stable', 'org.smarttube.beta'):
            try:
                ret = subprocess.run(['sh', '-c', 'pm path %s' % pkg],
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                     timeout=5)
                if ret.returncode == 0 and b'package:' in ret.stdout:
                    # Version pruefen (>= _SMARTTUBE_MIN_VERSION)
                    ver = _getSmartTubeVersion(pkg)
                    if ver and ver < _SMARTTUBE_MIN_VERSION:
                        _log('SmartTube %s zu alt: %s < %s' % (pkg, ver, _SMARTTUBE_MIN_VERSION))
                        continue
                    _smarttube_pkg = pkg
                    _log('SmartTube found: %s (version %s)' % (pkg, ver or 'unknown'))
                    return pkg
            except subprocess.TimeoutExpired:
                _log('SmartTube: pm timeout for %s' % pkg)
                continue
        _smarttube_pkg = False
        _log('SmartTube not found (or too old)')
        return None
    except Exception as e:
        _log('SmartTube check failed: %s' % e)
        _smarttube_pkg = False
        return None


def _getAvailableRAM():
    """Liest MemAvailable aus /proc/meminfo (inkl. rueckforderbarer Kernel-Caches).
    Gibt MB zurueck oder None bei Fehler."""
    try:
        with open('/proc/meminfo', 'r') as f:
            for line in f:
                if line.startswith('MemAvailable:'):
                    return int(line.split()[1]) // 1024
    except Exception:
        pass
    return None


_SMARTTUBE_MIN_RAM_MB = 220  # Minimum MemAvailable fuer SmartTube (Kaltstart-Peak ~161MB PSS)


def _getSmartTubeVersion(pkg):
    """Liest versionName aus Android PackageManager. Gibt str zurueck oder None."""
    try:
        import subprocess
        ret = subprocess.run(
            ['sh', '-c', 'dumpsys package %s | grep versionName' % pkg],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=5)
        if ret.returncode == 0 and ret.stdout:
            # Output: "    versionName=30.98" — letztes Vorkommen nehmen
            for line in ret.stdout.decode().strip().splitlines():
                if 'versionName=' in line:
                    return line.split('versionName=', 1)[1].strip()
    except Exception as e:
        _log('SmartTube version check failed: %s' % e)
    return None


# ── HTTP helper (bypass cRequestHandler — its __cleanupUrl double-encodes %22) ─

def _fetchJSON(url, timeout=10):
    """GET a JSON API URL and return parsed dict. Returns {} on any error.
    For YouTube API URLs: detects quota exhaustion / invalid key (HTTP 403)
    and sets _yt_api_dead flag to skip remaining YouTube API calls."""
    global _yt_api_dead
    import json
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError
    try:
        req = Request(url)
        req.add_header('User-Agent', 'Mozilla/5.0')
        resp = urlopen(req, timeout=timeout)
        return json.loads(resp.read().decode('utf-8'))
    except HTTPError as e:
        if e.code == 403 and 'googleapis.com' in url:
            try:
                body = json.loads(e.read().decode('utf-8'))
                reason = body.get('error', {}).get('errors', [{}])[0].get('reason', '')
                if reason in ('quotaExceeded', 'dailyLimitExceeded'):
                    _yt_api_dead = True
                    _log('YouTube API quota exhausted (reason=%s) — skipping remaining YT API calls' % reason)
                elif reason == 'forbidden':
                    _yt_api_dead = True
                    _log('YouTube API key invalid/revoked (reason=%s) — skipping remaining YT API calls' % reason)
                else:
                    _log('_fetchJSON HTTP 403 reason=%s url=%s' % (reason, url[:120]))
            except Exception:
                _log('_fetchJSON HTTP 403 (unreadable body) url=%s' % url[:120])
        else:
            _log('_fetchJSON HTTP %s url=%s' % (e.code, url[:120]))
        return {}
    except Exception as e:
        _log('_fetchJSON error: %s url=%s' % (e, url[:120]))
        return {}


def _fetchHTML(url, timeout=10):
    """GET a URL and return raw HTML string. Returns '' on any error.
    Sets _imdb_dead flag on HTTP 403/429 from imdb.com."""
    global _imdb_dead
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError
    try:
        req = Request(url)
        req.add_header('User-Agent',
                       'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                       'AppleWebKit/537.36 (KHTML, like Gecko) '
                       'Chrome/120.0.0.0 Safari/537.36')
        req.add_header('Accept-Language', 'en-US,en;q=0.9')
        resp = urlopen(req, timeout=timeout)
        return resp.read().decode('utf-8', errors='replace')
    except HTTPError as e:
        if e.code in (403, 429) and 'imdb.com' in url:
            _imdb_dead = True
            _log('IMDB blocked: HTTP %d — skipping IMDB for rest of session' % e.code)
        else:
            _log('_fetchHTML HTTP %s url=%s' % (e.code, url[:120]))
        return ''
    except Exception as e:
        _log('_fetchHTML error: %s url=%s' % (e, url[:120]))
        return ''


# ── YouTube helpers ───────────────────────────────────────────────────────────

def _getYouTubeApiKey():
    """Return YouTube Data API key. Cached at module level (reset on Kodi restart)."""
    global _yt_api_key
    if _yt_api_key is not None:
        return _yt_api_key
    # Try YouTube addon's api_keys.json first, then fall back to built-in key
    key = ''
    try:
        import xbmcvfs, json
        f = xbmcvfs.File('special://profile/addon_data/plugin.video.youtube/api_keys.json')
        data = json.loads(f.read())
        f.close()
        key = data.get('keys', {}).get('user', {}).get('api_key', '')
    except Exception:
        pass
    if key:
        _log('YT-apikey: addon key (%s...)' % key[:8])
        _yt_api_key = key
        return key
    # 2. Fallback
    if _API_CHECKSUM_B64:
        try:
            import base64
            key = base64.b64decode(_API_CHECKSUM_B64).decode()
            if key:
                _log('YT-apikey: fallback (%s...)' % key[:8])
                _yt_api_key = key
                return key
        except Exception:
            pass
    _log('YT-apikey: MISSING')
    _yt_api_key = ''
    return ''


def _getUserKey():
    """Return user's own API key, or '' if they copied our built-in key."""
    key = _getYouTubeApiKey()
    if not key or _b64.b64encode(key.encode()) == _API_CHECKSUM_B64:
        return ''  # no key or same as built-in -> not a user key
    return key


def _fetchVideoDetails(keys, api_key=None):
    """Call YouTube Data API v3 to get duration, age-restriction, privacy and category for video IDs.
    Uses _yt_video_cache to avoid redundant API calls across search steps.
    Returns dict {video_id: {...}} on success (may be empty if videos are unavailable).
    Returns None on API failure (no key, dead API, network error)."""
    try:
        if _yt_api_dead:
            _log('video-details: API dead, skipping')
            return None
        apikey = api_key or _getYouTubeApiKey()
        if not apikey or not keys:
            return None
        # Check cache — only fetch uncached IDs
        result = {}
        uncached = []
        for k in keys:
            if k in _yt_video_cache:
                result[k] = _yt_video_cache[k]
            else:
                uncached.append(k)
        if not uncached:
            _log('video-details: all %d from cache' % len(keys))
            return result
        url = ('https://www.googleapis.com/youtube/v3/videos'
               '?part=contentDetails,status,snippet,statistics&id=%s&key=%s'
               % (','.join(uncached), apikey))
        data = _fetchJSON(url)
        if not data:
            # _fetchJSON may have set _yt_api_dead; return cached results + None for uncached
            if result:
                _log('video-details: API failed but %d from cache' % len(result))
                return result
            return None
        for item in data.get('items', []):
            cd = item.get('contentDetails', {})
            st = item.get('status', {})
            sn = item.get('snippet', {})
            stats = item.get('statistics', {})
            dur = cd.get('duration', '')
            m = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', dur)
            secs = (int(m.group(1) or 0) * 3600
                    + int(m.group(2) or 0) * 60
                    + int(m.group(3) or 0)) if m else 0
            age_restricted = cd.get('contentRating', {}).get('ytRating') == 'ytAgeRestricted'
            unlisted = st.get('privacyStatus') != 'public'
            cam_rip = sn.get('categoryId') == '22'
            views = int(stats.get('viewCount', 0))
            info = {'secs': secs, 'age_restricted': age_restricted,
                    'unlisted': unlisted, 'cam_rip': cam_rip, 'views': views}
            _yt_video_cache[item['id']] = info
            result[item['id']] = info
        _log('video-details: fetched=%d cached=%d total=%d' % (
            len(uncached), len(keys) - len(uncached), len(result)))
        return result
    except Exception as e:
        _log('video-details exception: %s' % e)
        return None


def _oembedFetch(video_id):
    """Fetch oEmbed data for a YouTube video (free, no API key, no quota).
    Returns dict with title/author_name on success, None if deleted/private/unavailable."""
    try:
        import json
        from urllib.request import Request, urlopen
        from urllib.error import HTTPError
        url = 'https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v=%s&format=json' % video_id
        req = Request(url)
        req.add_header('User-Agent', 'Mozilla/5.0')
        resp = urlopen(req, timeout=5)
        return json.loads(resp.read().decode('utf-8'))
    except HTTPError as e:
        if e.code in (404, 401, 403):
            _log('oEmbed %s: HTTP %d (unavailable)' % (video_id, e.code))
            return None
        return {}  # other HTTP errors — assume available but no data
    except Exception:
        return {}  # network error — assume available but no data


def _videoExists(video_id):
    """Check if a YouTube video exists using the free oEmbed endpoint (no API key, no quota).
    Returns True if video is available, False if deleted/private/unavailable."""
    return _oembedFetch(video_id) is not None


def _filterExistence(hits):
    """Remove deleted/private videos using free oEmbed check (0 YT quota).
    Used for SmartTube path where we don't need age/duration filtering."""
    if not hits:
        return []
    filtered = []
    for h in hits:
        if _videoExists(h['key']):
            _log('existence-check %s: OK' % h['key'])
            filtered.append(h)
        else:
            _log('existence-check %s: REJECT (unavailable)' % h['key'])
    return filtered


def _filterByDuration(hits, minS=60, maxS=360, skip_api=False, api_key=None):
    """Filter YouTube hits by duration and remove age-restricted/unlisted/cam-rip videos.
    When skip_api=True (SmartTube): uses free oEmbed existence check (0 quota).
    Falls back to unfiltered list only if API is completely unavailable (None)."""
    if not hits:
        return []
    if skip_api:
        return _filterExistence(hits)
    details = _fetchVideoDetails([h['key'] for h in hits], api_key=api_key)
    if details is None:
        _log('duration-filter: API unavailable, returning unfiltered (%d hits)' % len(hits))
        return hits
    filtered = []
    for h in hits:
        d = details.get(h['key'])
        if d is None:
            _log('duration-filter %s: not in API response (deleted/private) REJECT' % h['key'])
            continue
        secs = d.get('secs', 0)
        aged = d.get('age_restricted', False)
        priv = d.get('unlisted', False)
        cam  = d.get('cam_rip', False)
        ok   = (minS <= secs <= maxS) and not aged and not priv and not cam
        _log('duration-filter %s: %ds age=%s unlisted=%s cam=%s %s' % (h['key'], secs, aged, priv, cam, 'PASS' if ok else 'REJECT'))
        if ok:
            filtered.append(h)
    # Re-rank: promote a video with overwhelming views (>=10K AND >=10x first pick)
    if len(filtered) >= 2:
        views = [(details.get(h['key'], {}).get('views', 0), h) for h in filtered]
        best_views = max(v for v, _ in views)
        first_views = views[0][0]
        if best_views >= 10000 and best_views >= 10 * max(first_views, 1):
            filtered.sort(key=lambda h: details.get(h['key'], {}).get('views', 0), reverse=True)
            _log('view-rank: promoted %s (%d views) over %s (%d views)' % (
                filtered[0]['key'], best_views, views[0][1]['key'], first_views))
    return filtered  # empty = all rejected -> waterfall continues to next source


def _filterAgeRestricted(hits, skip_api=False, api_key=None):
    """Remove unavailable videos (always) and age-restricted/unlisted/cam-rip (YT addon only).
    When skip_api=True (SmartTube): uses free oEmbed existence check (0 quota).
    Falls back to unfiltered list only if API is completely unavailable (None)."""
    if not hits:
        return []
    if skip_api:
        return _filterExistence(hits)
    details = _fetchVideoDetails([h['key'] for h in hits], api_key=api_key)
    if details is None:
        return hits
    filtered = []
    for h in hits:
        d = details.get(h['key'])
        if d is None:
            _log('age-check %s: not in API response (deleted/private) REJECT' % h['key'])
            continue
        aged = d.get('age_restricted', False)
        priv = d.get('unlisted', False)
        cam  = d.get('cam_rip', False)
        ok   = not aged and not priv and not cam
        _log('age-check %s: age=%s unlisted=%s cam=%s %s' % (h['key'], aged, priv, cam, 'SKIP' if not ok else 'OK'))
        if ok:
            filtered.append(h)
    return filtered


def _htmlDecode(s):
    """Decode HTML entities in YouTube API snippet titles (&#39; -> ', &quot; -> ", etc.)."""
    from html import unescape
    return unescape(s)


def _yearConflict(vtitle, year):
    """Check if a video title contains a 4-digit year that differs from the expected year.
    Looks for years both in parentheses (2019) and bare 2019.
    Returns True if a DIFFERENT year is found — meaning the video is likely for a different movie."""
    if not year:
        return False
    decoded = _htmlDecode(vtitle)
    # Find all 4-digit years in range 1920-2039
    found = re.findall(r'(?<!\d)((?:19|20)\d{2})(?!\d)', decoded)
    if not found:
        return False  # no year in title — can't tell, allow it
    # If any found year matches the expected year, it's OK
    if year in found:
        return False
    # All found years differ from expected — wrong movie
    return True


def _titleOkChannel(vtitle, title, year=''):
    """Title check for curated channel results (KinoCheck): title match, trailer word, no Shorts/junk, year conflict."""
    vl = _htmlDecode(vtitle).lower()
    if title.lower() not in vl:
        return False
    if not any(w in vl for w in _TRAILER_WORDS):
        return False
    if any(w in vl for w in _JUNK_WORDS):
        return False
    if _yearConflict(vtitle, year):
        return False
    return True


def _titleOkGlobal(vtitle, title, year=''):
    """Strict title check for global YouTube search results."""
    vl = _htmlDecode(vtitle).lower()
    if title.lower() not in vl:
        return False
    if any(w in vl for w in _JUNK_WORDS):
        return False
    if not any(w in vl for w in _TRAILER_WORDS):
        return False
    if _yearConflict(vtitle, year):
        return False
    return True


def _uploadYearOk(snippet, year, max_gap=5):
    """Check if a YouTube video's upload date is within max_gap years of the movie year.
    Uses snippet.publishedAt (available in search results, no extra API call).
    Returns True if OK or if we can't determine (missing data). False if gap too large."""
    if not year:
        return True
    pub = snippet.get('publishedAt', '')  # e.g. "2019-03-11T17:00:06Z"
    if not pub or len(pub) < 4:
        return True
    try:
        upload_year = int(pub[:4])
        movie_year = int(year)
        gap = upload_year - movie_year
        # Trailers are typically uploaded 0-2 years before/after release.
        # A large positive gap means someone uploaded a trailer for a much older movie — suspicious.
        if gap > max_gap:
            return False
    except (ValueError, TypeError):
        return True
    return True


# Blocklisted channel keywords — reject YT search results from music/gaming channels
_BAD_CHANNELS = [
    'music', 'vevo', 'records', 'gaming', 'gameplay', 'react',
    'podcast', 'radio', 'live performance',
]


def _oembedSanityCheck(video_id, title, year=''):
    """Last safety check before playing a YouTube search result (steps 4/5).
    Single oEmbed call (free, 0 quota) on the #1 pick. Checks:
    1. Video still exists (not deleted/private)
    2. Full title (not truncated) has no year conflict
    3. Channel name is not obviously wrong (music/gaming/etc.)
    Returns True if OK to play, False if should skip this step."""
    data = _oembedFetch(video_id)
    if data is None:
        _log('sanity-check %s: FAIL (unavailable)' % video_id)
        return False
    if not data:
        _log('sanity-check %s: PASS (no data, assume ok)' % video_id)
        return True  # network error — no data but assume ok
    full_title = data.get('title', '')
    author = data.get('author_name', '')
    _log('sanity-check %s: title=%r author=%r' % (video_id, full_title[:80], author))
    # Check full title for year conflict (search snippet may have been truncated)
    if full_title and _yearConflict(full_title, year):
        _log('sanity-check %s: FAIL (year conflict in full title)' % video_id)
        return False
    # Check channel name for obvious mismatches
    if author:
        al = author.lower()
        if any(w in al for w in _BAD_CHANNELS):
            _log('sanity-check %s: FAIL (bad channel: %r)' % (video_id, author))
            return False
    _log('sanity-check %s: PASS' % video_id)
    return True


# ── TMDB video helper ─────────────────────────────────────────────────────────

def _tmdbVideos(data, lang=None):
    """Extract YouTube Trailer/Teaser from a TMDB /videos response, newest first.
    If lang is given, only include videos with matching iso_639_1 (e.g. 'de', 'en')."""
    if not data:
        return []
    all_results = data.get('results', [])
    for v in all_results:
        _log('  tmdb-video: type=%s site=%s lang=%s name=%r date=%s' % (
            v.get('type'), v.get('site'), v.get('iso_639_1'),
            v.get('name', '')[:60], v.get('published_at', '')[:10]))
    videos = [v for v in all_results
              if v.get('site') == 'YouTube'
              and v.get('type') in ('Trailer', 'Teaser')
              and (lang is None or v.get('iso_639_1') == lang)]
    # Sort: Trailer before Teaser, then newest first within each type.
    videos.sort(key=lambda v: v.get('published_at', ''), reverse=True)
    videos.sort(key=lambda v: 0 if v.get('type') == 'Trailer' else 1)
    return videos


# ── Source-specific search functions ─────────────────────────────────────────

def _extractSeasonFromTitle(title):
    """Extract a season number from a KinoCheck video title.

    Patterns matched (in priority order):
      - "N. Staffel"  e.g. "THE BOYS 2. Staffel Trailer"
      - "Staffel N"   e.g. "THE BOYS Staffel 3 Trailer"
      - "Season N"    e.g. "COBRA KAI Season 4 Trailer"

    Returns the season number as int, or None if no match.
    """
    # "N. Staffel" must be checked first so "2. Staffel" is not shadowed by
    # a later "Staffel N" pattern that could match a trailing digit elsewhere.
    m = re.search(r'(\d+)\.\s*[Ss]taffel', title)
    if m:
        return int(m.group(1))
    m = re.search(r'[Ss]taffel\s+(\d+)', title)
    if m:
        return int(m.group(1))
    m = re.search(r'[Ss]eason\s+(\d+)', title)
    if m:
        return int(m.group(1))
    return None


def _filterKinoCheckBySeason(hits, season):
    """Filter a list of KinoCheck hit dicts to those matching *season*.

    Args:
        hits:   list of dicts, each with at least a 'name' key and optionally
                a 'published' key (ISO date string).
        season: int season number to keep, or None to return *hits* unchanged.

    Returns:
        If season is None  — the original list, unmodified.
        Otherwise          — filtered list sorted by 'published' descending
                             (hits without 'published' sort last).
    """
    if season is None:
        return hits
    filtered = [h for h in hits if _extractSeasonFromTitle(h.get('name', '')) == season]
    filtered.sort(key=lambda h: h.get('published', ''), reverse=True)
    return filtered


def _searchKinoCheckAPI(tmdb_id, mediatype='movie', language='de', season=None):
    """Exact TMDB ID lookup via KinoCheck API. Free, no key required, no YT quota.
    NOT gated by _yt_api_dead — this uses kinocheck.de, not YouTube API.
    Returns (hits, api_ok):
      hits    — list of {name, key} (YouTube videos), empty if no trailer
      api_ok  — True if API responded (even with no trailer), False on error/timeout
    """
    try:
        endpoint = 'movies' if mediatype == 'movie' else 'shows'
        url = 'https://api.kinocheck.de/%s?tmdb_id=%s&language=%s' % (endpoint, tmdb_id, language)
        _log('KinoCheck-API: %s' % url)
        data = _fetchJSON(url)
        if not data:
            _log('KinoCheck-API: empty response (down/rate-limited?)')
            return [], False
        # API responded — check for videos
        trailer = data.get('trailer')
        videos  = data.get('videos', [])
        if not trailer and not videos:
            _log('KinoCheck-API: no trailer for tmdb_id=%s' % tmdb_id)
            return [], True   # api_ok=True — they don't have it, skip YT fallback
        hits = []
        # Primary trailer first
        if trailer and trailer.get('youtube_video_id'):
            hits.append({'name': trailer.get('title', ''), 'key': trailer['youtube_video_id'], 'language': language})
            _log('KinoCheck-API trailer: %s %r lang=%s' % (trailer['youtube_video_id'], trailer.get('title', '')[:60], language))
        # Additional videos
        for v in videos:
            vid = v.get('youtube_video_id', '')
            if vid and vid not in [h['key'] for h in hits]:
                cat = v.get('categories', '')
                if cat in ('Trailer', 'Teaser'):
                    hits.append({'name': v.get('title', ''), 'key': vid, 'language': v.get('language', language)})
                    _log('KinoCheck-API video: %s %r cat=%s lang=%s' % (vid, v.get('title', '')[:60], cat, v.get('language', language)))
        if season is not None:
            filtered = _filterKinoCheckBySeason(hits, season)
            if not filtered:
                _log('KinoCheck-API: no hits for season=%s after filter' % season)
                return [], True
            return filtered, True
        return hits, True
    except Exception as e:
        _log('KinoCheck-API exception: %s' % e)
        return [], False


def _searchKinoCheck(title, year):
    """Search KinoCheck YouTube channel for a German trailer.
    Requires working YouTube API key. Gated by _yt_api_dead flag.
    Year-matched results bubble to the top. Returns list of {name, key}."""
    try:
        if _yt_api_dead:
            _log('KinoCheck-YT: API dead, skipping')
            return []
        from urllib.parse import quote_plus
        apikey = _getUserKey()
        if not apikey:
            _log('KinoCheck-YT: no own API key, skipping')
            return []
        parts = ['"%s"' % title]
        if year:
            parts.append(str(year))
        parts.append('Trailer')
        query = ' '.join(parts)
        url   = ('https://www.googleapis.com/youtube/v3/search?part=snippet'
                 '&channelId=%s&q=%s&type=video&maxResults=10'
                 '&relevanceLanguage=de&key=%s'
                 % (KINOCHECK_CHANNEL, quote_plus(query), apikey))
        _log('KinoCheck query: %r' % query)
        data  = _fetchJSON(url)
        hits  = []
        for it in data.get('items', []):
            vtitle = it['snippet']['title']
            ok     = _titleOkChannel(vtitle, title, year)
            _log('  KinoCheck %s: %r' % ('PASS' if ok else 'REJECT', vtitle[:80]))
            if not ok:
                continue
            entry = {'name': vtitle, 'key': it['id']['videoId']}
            if year and '(%s)' % year in vtitle:
                hits.insert(0, entry)   # year match -> front
            else:
                hits.append(entry)
        return hits
    except Exception as e:
        _log('KinoCheck exception: %s' % e)
        return []


def _searchYouTube(title, year, lang='', search_suffix=None):
    """Global YouTube search with strict title filter.
    Single query: "title" year trailer (maxResults=25).
    Results cached in _yt_search_cache. Cross-language cache hit for same-title movies.
    Gated by _yt_api_dead flag. Returns list of {name, key}."""
    try:
        if _yt_api_dead:
            _log('YouTube-%s: API dead, skipping' % (lang or 'xx'))
            return []
        from urllib.parse import quote_plus
        apikey = _getUserKey()
        if not apikey:
            _log('YouTube-%s: no own API key, skipping' % (lang or 'xx'))
            return []
        # Check cache — avoid burning 100 units if we already searched this title
        cache_key = (title.lower(), str(year), lang)
        cached_items = _yt_search_cache.get(cache_key)
        # Cross-language reuse: same title+year already searched in a different lang
        if cached_items is None:
            for (t, y, l), items in _yt_search_cache.items():
                if t == title.lower() and y == str(year) and l != lang:
                    cached_items = items
                    _log('YouTube-%s: cross-lang cache hit from %s (%d items, 0 units)'
                         % (lang or 'xx', l, len(items)))
                    _yt_search_cache[cache_key] = items
                    break
        if cached_items is not None:
            _log('YouTube-%s: cache hit for %r year=%s, re-filtering %d items'
                 % (lang or 'xx', title, year, len(cached_items)))
            results = []
            for it in cached_items:
                vtitle = it['snippet']['title']
                ok = _titleOkGlobal(vtitle, title, year)
                if ok and not _uploadYearOk(it.get('snippet', {}), year):
                    ok = False
                    _log('  YouTube-%s REJECT (upload year gap): %r pub=%s' % (
                        lang or 'xx', vtitle[:80], it.get('snippet', {}).get('publishedAt', '')[:10]))
                else:
                    _log('  YouTube-%s %s: %r' % (lang or 'xx', 'PASS' if ok else 'REJECT', vtitle[:80]))
                if ok:
                    results.append({'name': vtitle, 'key': it['id']['videoId']})
            return results
        # Build query — single pass: "title" year trailer
        parts = ['"%s"' % title]
        if search_suffix:
            parts.append(str(search_suffix))
        elif year:
            parts.append(str(year))
        parts.append('trailer')
        query = ' '.join(parts)
        url = ('https://www.googleapis.com/youtube/v3/search?part=snippet'
               '&q=%s&type=video&maxResults=25&key=%s'
               % (quote_plus(query), apikey))
        if lang:
            url += '&relevanceLanguage=%s' % lang[:2]
        _log('YouTube-%s query: %r' % (lang or 'xx', query))
        data = _fetchJSON(url)
        # Cache raw items (before filtering)
        raw_items = data.get('items', [])
        _yt_search_cache[cache_key] = raw_items
        # Filter
        results = []
        for it in raw_items:
            vtitle = it['snippet']['title']
            ok     = _titleOkGlobal(vtitle, title, year)
            if ok and not _uploadYearOk(it.get('snippet', {}), year):
                ok = False
                _log('  YouTube-%s REJECT (upload year gap): %r pub=%s' % (
                    lang or 'xx', vtitle[:80], it.get('snippet', {}).get('publishedAt', '')[:10]))
            else:
                _log('  YouTube-%s %s: %r' % (lang or 'xx', 'PASS' if ok else 'REJECT', vtitle[:80]))
            if ok:
                results.append({'name': vtitle, 'key': it['id']['videoId']})
        return results
    except Exception as e:
        _log('YouTube-%s exception: %s' % (lang or 'xx', e))
        return []


# ── IMDB direct MP4 lookup ───────────────────────────────────────────────────

# IMDB quality preference (MP4 > HLS, highest resolution first)
_IMDB_QUALITY_ORDER = ['DEF_1080p', 'DEF_720p', 'DEF_480p', 'DEF_SD']

_IMDB_GRAPHQL_URL = 'https://caching.graphql.imdb.com/'
# Minimal GraphQL query: fetches primary video + CloudFront-signed playback URLs (~3 KB response)
_IMDB_GRAPHQL_QUERY = '{"query":"query($id:ID!){title(id:$id){primaryVideos(first:1){edges{node{id name{value}playbackURLs{mimeType url videoDefinition}}}}}}","variables":{"id":"%s"}}'

def _searchIMDB(imdb_id):
    """IMDB trailer lookup via GraphQL API (~3 KB response vs 1.5 MB title page).
    Returns (mp4_url, quality) on success, ('', '') on failure.
    Result cached with 1h TTL (CloudFront signed URLs expire in ~24h)."""
    import time, json
    global _imdb_dead
    if not imdb_id:
        return ('', '')
    if _imdb_dead:
        _log('IMDB: dead flag set, skipping')
        return ('', '')
    # Check cache
    cached = _imdb_cache.get(imdb_id)
    if cached:
        url, quality, expiry = cached
        if time.time() < expiry:
            _log('IMDB cache hit: %s -> %s (%s)' % (imdb_id, url[:80] if url else '', quality))
            return (url, quality)
        else:
            del _imdb_cache[imdb_id]
    # GraphQL query for primary video + playback URLs
    _log('IMDB GraphQL: %s' % imdb_id)
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError
    try:
        body = (_IMDB_GRAPHQL_QUERY % imdb_id).encode('utf-8')
        req = Request(_IMDB_GRAPHQL_URL, data=body, method='POST')
        req.add_header('Content-Type', 'application/json')
        req.add_header('Accept', 'application/json')
        req.add_header('User-Agent',
                       'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                       'AppleWebKit/537.36 (KHTML, like Gecko) '
                       'Chrome/120.0.0.0 Safari/537.36')
        resp = urlopen(req, timeout=5)
        data = json.loads(resp.read().decode('utf-8'))
    except HTTPError as e:
        if e.code in (403, 429):
            _imdb_dead = True
            _log('IMDB blocked: HTTP %d — skipping IMDB for rest of session' % e.code)
        else:
            _log('IMDB GraphQL HTTP %s' % e.code)
        return ('', '')
    except Exception as e:
        _log('IMDB GraphQL error: %s' % e)
        return ('', '')
    # Parse response: data.title.primaryVideos.edges[0].node.playbackURLs
    try:
        edges = data['data']['title']['primaryVideos']['edges']
    except (KeyError, TypeError):
        _log('IMDB: unexpected GraphQL structure for %s' % imdb_id)
        _imdb_cache[imdb_id] = ('', '', time.time() + _IMDB_CACHE_TTL)
        return ('', '')
    if not edges:
        _log('IMDB: no trailer for %s' % imdb_id)
        _imdb_cache[imdb_id] = ('', '', time.time() + _IMDB_CACHE_TTL)
        return ('', '')
    node = edges[0].get('node', {})
    video_name = (node.get('name') or {}).get('value', '')
    urls = node.get('playbackURLs', [])
    _log('IMDB: video=%s name=%r urls=%d' % (node.get('id', ''), video_name, len(urls)))
    if not urls:
        _imdb_cache[imdb_id] = ('', '', time.time() + _IMDB_CACHE_TTL)
        return ('', '')
    # Pick best quality MP4
    best_url = ''
    best_quality = ''
    for pref in _IMDB_QUALITY_ORDER:
        for entry in urls:
            if entry.get('videoDefinition') == pref and entry.get('mimeType') == 'video/mp4':
                best_url = entry['url']
                best_quality = pref.replace('DEF_', '')
                break
        if best_url:
            break
    # Fallback to HLS (M3U8)
    if not best_url:
        for entry in urls:
            if 'mpegurl' in (entry.get('mimeType') or '').lower():
                best_url = entry['url']
                best_quality = 'HLS'
                break
    # Fallback to any MP4
    if not best_url:
        for entry in urls:
            if entry.get('mimeType') == 'video/mp4':
                best_url = entry['url']
                best_quality = (entry.get('videoDefinition') or '').replace('DEF_', '') or '?'
                break
    _log('IMDB result: quality=%s url=%s' % (best_quality, best_url[:80] if best_url else ''))
    _imdb_cache[imdb_id] = (best_url, best_quality, time.time() + _IMDB_CACHE_TTL)
    return (best_url, best_quality)


# ── Notification + playback ───────────────────────────────────────────────────

def _notify(search_title, step, source, vtype, lang, poster, vtype_prefix=''):
    """3-second notification popup (upper-right).
    Heading: search title used (DE or EN).
    Message: source - type [lang]  e.g. 'TMDB - Trailer [DE]'
    If lang is empty (e.g. IMDB): 'IMDB - Trailer'
    """
    try:
        import xbmcgui
        icon = poster if poster else xbmcgui.NOTIFICATION_INFO
        msg = '%s - %s [%s]' % (source, vtype_prefix + vtype, lang) if lang else '%s - %s' % (source, vtype_prefix + vtype)
        xbmcgui.Dialog().notification(
            search_title,
            msg,
            icon,
            3000,
            False,
        )
    except Exception:
        pass


def _play(video_id, step, source, vtype, lang, poster, search_title, vtype_prefix=''):
    """Show source/language popup then play via SmartTube (if installed) or YouTube addon."""
    import xbmc
    if xbmc.getCondVisibility('Window.IsActive(busydialognocancel)'): xbmc.executebuiltin('Dialog.Close(busydialognocancel)')
    _log('PLAY video_id=%s step=%d source=%s vtype=%s lang=%s title=%r'
         % (video_id, step, source, vtype, lang, search_title))
    _notify(search_title, step, source, vtype, lang, poster, vtype_prefix=vtype_prefix)
    pkg = _getSmartTubePackage()
    _smarttube_low_ram = False
    if pkg:
        avail_mb = _getAvailableRAM()
        if avail_mb is not None and avail_mb < _SMARTTUBE_MIN_RAM_MB:
            _log('SmartTube uebersprungen: nur %d MB frei (< %d MB)' % (avail_mb, _SMARTTUBE_MIN_RAM_MB))
            pkg = None
            _smarttube_low_ram = True
        else:
            _log('RAM check: %s MB frei' % (avail_mb if avail_mb is not None else 'n/a'))
    if pkg:
        xbmc.sleep(2000)  # let notification show before SmartTube covers Kodi UI
        _log('PLAY via SmartTube (%s)' % pkg)
        xbmc.executebuiltin(
            'StartAndroidActivity(%s,android.intent.action.VIEW,,'
            'https://www.youtube.com/watch?v=%s,,'
            '"[{\\"type\\":\\"string\\",\\"key\\":\\"finish_on_ended\\"'
            ',\\"value\\":\\"true\\"}]")'
            % (pkg, video_id)
        )
    else:
        if not _ensureYouTubeAddon(smarttube_low_ram=_smarttube_low_ram):
            return
        _log('PLAY via YouTube addon')
        xbmc.executebuiltin(
            'PlayMedia(plugin://plugin.video.youtube/play/?video_id=%s)' % video_id
        )


class _TrailerPlayer(object):
    """Kodi player wrapper for direct MP4/HLS (IMDB). Monitors fullscreen, stops on back."""
    def __init__(self):
        import xbmc as _xbmc
        class _P(_xbmc.Player):
            def __init__(s): super().__init__(); s.done = False
            def onPlayBackStopped(s): s.done = True
            def onPlayBackEnded(s): s.done = True
            def onPlayBackError(s): s.done = True
        self._p = _P()
        self._mon = _xbmc.Monitor()
        self._xbmc = _xbmc
    def play(self, url):  self._p.play(url)
    def stop(self): self._p.stop()
    @property
    def done(self): return self._p.done
    def wait(self, secs): return self._mon.waitForAbort(secs)
    @property
    def aborted(self): return self._mon.abortRequested()
    def fullscreen(self):
        return self._xbmc.getCondVisibility('Window.IsVisible(fullscreenvideo)')


def _playDirect(url, step, source, vtype, lang, poster, search_title, vtype_prefix=''):
    """Show source popup then play a direct MP4/M3U8 URL via Kodi's native player.
    Monitors fullscreen — stops playback when user presses back."""
    import xbmc
    if xbmc.getCondVisibility('Window.IsActive(busydialognocancel)'): xbmc.executebuiltin('Dialog.Close(busydialognocancel)')
    _log('PLAY-DIRECT url=%s step=%d source=%s vtype=%s title=%r'
         % (url[:80], step, source, vtype, search_title))
    _notify(search_title, step, source, vtype, lang, poster, vtype_prefix=vtype_prefix)
    tp = _TrailerPlayer()
    tp.play(url)
    # Wait for fullscreen to appear — exit early if playback fails
    fs_seen = False
    while not tp.aborted and not tp.done:
        if tp.fullscreen():
            fs_seen = True
            break
        tp.wait(0.1)
    if not fs_seen:
        _log('PLAY-DIRECT: playback ended before fullscreen')
        return
    # Monitor: stop when user leaves fullscreen (back = stop for trailers)
    while not tp.aborted and not tp.done:
        if not tp.fullscreen():
            tp.stop()
            _log('PLAY-DIRECT stopped (user left fullscreen)')
            break
        tp.wait(0.3)


# ── Shared search core (addon-agnostic) ──────────────────────────────────────

def _runTrailerSearch(tmdb_id, mediatype, title, en_title, year, poster,
                      imdb_id, languages, has_yt_player, has_own_key, skip_api,
                      tmdb_videos, season=None, vtype_prefix=''):
    """Per-language priority block search — shared core for xStream/xShip.

    languages:   list of 1-3 ISO codes, e.g. ['de'] or ['ja', 'de', 'en']
    tmdb_videos: single pre-fetched TMDB /videos response (all languages)

    Block list = languages + EN (if missing) + ANY.
    Per block: KC API -> KC YT (if DE) -> TMDB -> IMDB (if EN).
    After all blocks: YouTube search per caller language, then give up.

    Returns dict on success: {'found_lang': 'DE', 'source': 'IMDB'|'KinoCheck'|...}
    Returns None on give-up (no trailer found).
    """
    import xbmcgui

    _vf = _api_checksum  # built-in key for cheap 1-unit verification (age/duration filter)

    # Build block list: caller languages + EN (ensures IMDB) + ANY (catches remaining)
    blocks = list(languages)
    if 'en' not in blocks:
        blocks.append('en')       # EN auto-added so IMDB always gets its own block
    blocks.append(None)           # None = ANY block (TMDB videos in unlisted languages)
    all_explicit = [b for b in blocks if b]  # named languages to exclude from ANY block

    _log('SEARCH languages=%s blocks=%s' % (languages, [b or 'ANY' for b in blocks]))

    step = 0
    # Walk each block in priority order — first trailer found wins
    for lang in blocks:
        is_any = (lang is None)
        lang_label = lang.upper() if lang else 'ANY'
        lang_title = en_title if (lang == 'en' or is_any) else title  # EN title for EN/ANY

        # ── Sources that return YouTube video IDs (need a player) ─────
        if has_yt_player:
            # KinoCheck API: free, no key, ID-based (only supports de/en)
            # ANY block: try KC-API(de) only if DE wasn't already an explicit block
            do_kc = not is_any or (is_any and 'de' not in languages)
            if do_kc:
                kc_lang = 'de' if is_any else lang
                step += 1
                _log('--- [%s] KinoCheck API (lang=%s) ---' % (lang_label, kc_lang))
                kc_hits, kc_ok = _searchKinoCheckAPI(tmdb_id, mediatype, language=kc_lang, season=season)
                _log('[%s] KC-API: hits=%d ok=%s' % (lang_label, len(kc_hits), kc_ok))
                if kc_hits:
                    if not skip_api:
                        non_rb = [h for h in kc_hits if 'red band' not in h.get('name', '').lower()]
                        if non_rb:
                            kc_hits = non_rb
                        else:
                            _log('[%s] KC-API: only Red Band, running age-check' % lang_label)
                            kc_hits = _filterAgeRestricted(kc_hits, skip_api=False, api_key=_vf)
                    else:
                        kc_hits = _filterExistence(kc_hits)
                    if kc_hits:
                        _play(kc_hits[0]['key'], step, 'KinoCheck', 'Trailer',
                              kc_lang.upper(), poster, lang_title, vtype_prefix=vtype_prefix)
                        return {'found_lang': kc_lang.upper(), 'source': 'KinoCheck'}
                    _log('[%s] KC-API: all results unavailable' % lang_label)

            # KinoCheck YT channel search: DE only, needs user's own key (100 units)
            if (lang == 'de' or (is_any and 'de' not in languages)) and has_own_key and not season:
                step += 1
                _log('--- [%s] KinoCheck YT channel ---' % lang_label)
                kc_raw = _searchKinoCheck(lang_title, year)
                kc_hit = _filterByDuration(kc_raw, skip_api=skip_api, api_key=_vf)
                _log('[%s] KC-YT: raw=%d filtered=%d' % (lang_label, len(kc_raw), len(kc_hit)))
                if kc_hit:
                    _play(kc_hit[0]['key'], step, 'KinoCheck', 'Trailer',
                          'DE', poster, lang_title, vtype_prefix=vtype_prefix)
                    return {'found_lang': 'DE', 'source': 'KinoCheck'}

            # TMDB videos: filter pre-fetched results by language (0 API calls)
            step += 1
            _log('--- [%s] TMDB videos ---' % lang_label)
            if is_any:
                videos = _tmdbVideos(tmdb_videos)
                videos = [v for v in videos if v.get('iso_639_1') not in all_explicit]  # exclude already-tried langs
            else:
                videos = _tmdbVideos(tmdb_videos, lang=lang)
            videos = _filterAgeRestricted(videos, skip_api=skip_api, api_key=_vf)
            _log('[%s] TMDB: filtered=%d' % (lang_label, len(videos)))
            if videos:
                vlang = (videos[0].get('iso_639_1') or lang or '??').upper()
                _play(videos[0]['key'], step, 'TMDB', videos[0].get('type', 'Trailer'),
                      vlang, poster, lang_title, vtype_prefix=vtype_prefix)
                return {'found_lang': vlang, 'source': 'TMDB'}

        # IMDB direct MP4: EN block only, no player/key needed, ID-based
        if lang == 'en' and imdb_id and not _imdb_dead:
            step += 1
            _log('--- [EN] IMDB ---')
            imdb_url, imdb_quality = _searchIMDB(imdb_id)
            _log('[EN] IMDB: url=%s quality=%s' % (imdb_url[:80] if imdb_url else '', imdb_quality))
            if imdb_url:
                _playDirect(imdb_url, step, 'IMDB', 'Trailer', '', poster, en_title or title, vtype_prefix=vtype_prefix)
                return {'found_lang': 'EN', 'source': 'IMDB'}

    # YouTube global search (last resort, expensive: 100-201 units per language)
    if has_yt_player and has_own_key:
        user_key = _getUserKey()  # search uses user's own key (not built-in)
        for yt_lang in languages:
            step += 1
            yt_title = en_title if yt_lang == 'en' else title
            yt_upper = yt_lang.upper()
            _log('--- YouTube-%s search ---' % yt_upper)
            if season:
                yt_raw = _searchYouTube(yt_title, '', lang=yt_lang, search_suffix='Season %s' % season)
            else:
                yt_raw = _searchYouTube(yt_title, year, lang=yt_lang)
            yt_hit = _filterByDuration(yt_raw, skip_api=skip_api, api_key=user_key)
            _log('YouTube-%s: raw=%d filtered=%d' % (yt_upper, len(yt_raw), len(yt_hit)))
            if yt_hit and _oembedSanityCheck(yt_hit[0]['key'], yt_title, '' if season else year):
                _play(yt_hit[0]['key'], step, 'YouTube', 'Trailer',
                      yt_upper, poster, yt_title, vtype_prefix=vtype_prefix)
                return {'found_lang': yt_upper, 'source': 'YouTube'}

    # ── Give up ───────────────────────────────────────────────────
    _log('Give up — languages=%s has_yt_player=%s has_own_key=%s' % (languages, has_yt_player, has_own_key))
    return None


# ── User guidance popups (once per Kodi session) ─────────────────────────────

def _showHintIfNeeded(has_yt_player, has_own_key, found_any, played_imdb, primary_lang='de'):
    """Show guidance popup after trailer plays (or at give-up). Once per Kodi session.
    Popup 1: no player, IMDB played, primary_lang != 'en' -> suggest player install.
    Popup 2: has player, no own key, zero hits -> suggest YT addon with own API key.
    Messages in German if Kodi GUI is German, English otherwise.
    Returns True if a popup was shown."""
    try:
        import xbmc, xbmcgui
        win = xbmcgui.Window(10000)
        kodi_lang = xbmc.getLanguage(xbmc.ISO_639_1) or 'de'
        is_de_gui = (_ADDON_NAME == 'xship') or (kodi_lang == 'de')

        if not has_yt_player and played_imdb and primary_lang != 'en':
            # Popup 1: IMDB played but user wanted non-EN -> suggest player
            if not win.getProperty(_PROP_PREFIX + '.hint.player'):
                xbmc.sleep(2000)
                is_android = xbmc.getCondVisibility('System.Platform.Android')
                # SmartTube nur empfehlen wenn genuegend RAM frei
                avail_ram = _getAvailableRAM()
                suggest_smarttube = is_android and (avail_ram is None or avail_ram >= _SMARTTUBE_MIN_RAM_MB)
                has_kc = primary_lang in ('de', 'en')
                if suggest_smarttube:
                    if is_de_gui:
                        sources = 'KinoCheck und TMDB' if has_kc else 'TMDB'
                        player = 'SmartTube oder das YouTube Add-on' if suggest_smarttube else 'das YouTube Add-on'
                        msg = ('Dieser Trailer war auf Englisch (IMDB).\n'
                               'F\u00fcr weitere Trailer in deiner Sprache von %s '
                               '%s installieren (kein API-Key n\u00f6tig).' % (sources, player))
                    else:
                        sources = 'KinoCheck and TMDB' if has_kc else 'TMDB'
                        player = 'SmartTube or the YouTube add-on' if suggest_smarttube else 'the YouTube add-on'
                        msg = ('This trailer was in English (IMDB).\n'
                               'For additional trailers in your language from %s '
                               'install %s (no API key needed).' % (sources, player))
                    xbmcgui.Dialog().ok('Trailer', msg)

                else:
                    from xbmc import getCondVisibility, executebuiltin, sleep
                    from xbmcaddon  import Addon
                    import xbmcgui
                    _ensureYouTubeAddon()
                win.setProperty(_PROP_PREFIX + '.hint.player', '1')
                _log('hint: showed player popup')
                return True

        elif has_yt_player and not has_own_key and not found_any:
            # Popup 2: zero hits, no own key -> suggest YT addon with API key
            if not win.getProperty(_PROP_PREFIX + '.hint.apikey'):
                xbmc.sleep(2000)
                if is_de_gui:
                    msg = ('Kein Trailer gefunden.\n'
                           'Du kannst versuchen, das YouTube Add-on mit eigenem API-Key zu installieren, '
                           'um zus\u00e4tzliche Trailer-Quellen auf YouTube zu finden.')
                else:
                    msg = ('No trailer found.\n'
                           'You could try to install the YouTube add-on with your own API key '
                           'to find additional trailer sources on YouTube.')
                xbmcgui.Dialog().ok('Trailer', msg)
                win.setProperty(_PROP_PREFIX + '.hint.apikey', '1')
                _log('hint: showed apikey popup')
                return True

    except Exception as e:
        _log('hint popup error: %s' % e)
    return False


# ── Entry point (shared by xStream and xShip) ────────────────────────────────

def playTrailer(tmdb_id, mediatype='movie', title='', year='', poster='', pref_lang='de', season=None):
    """Trailer wrapper — detects capabilities, pre-fetches TMDB data,
    then calls _runTrailerSearch().

    Args:
        tmdb_id:   TMDB numeric ID (string), or empty for Phase 0 resolution (xStream)
        mediatype: 'movie' or 'tv' (xStream may pass 'tvshow' — mapped to 'tv')
        title:     display title (for YouTube fallback searches)
        year:      release year string
        poster:    poster image URL (shown as notification icon)
        pref_lang: preferred trailer language code ('de', 'en', 'fr', ...)
                   xStream: context menu passes prefLanguage, TMDB dialog passes tmdb_lang.
                   xShip: default 'de'.
        season:    season number (int/str) for season-specific trailer search, or None
    """
    if season is not None:
        season = int(season)
    import xbmc, xbmcgui
    from resources.lib.tmdb import cTMDB

    if mediatype == 'tvshow':
        mediatype = 'tv'

    url_type  = 'movie' if mediatype == 'movie' else 'tv'
    title_key = 'title' if mediatype == 'movie' else 'name'

    # ── Build language list (addon-specific) ────────────────────────────
    if _ADDON_NAME == 'xstream':
        # xStream: 3 settings sources merged, deduplicated, narrowest first
        try:
            from resources.lib.config import cConfig
            _tmdb_lang = cConfig().getSetting('tmdb_lang') or 'de'
            _pref_raw = cConfig().getSetting('prefLanguage') or '0'
            _kodi_lang = xbmc.getLanguage(xbmc.ISO_639_1) or 'de'
            _pref_map = {'0': _kodi_lang, '1': 'de', '2': 'en', '3': 'ja'}
            _xstream_pref = _pref_map.get(_pref_raw, _kodi_lang)
            languages = []
            for lang in [pref_lang, _tmdb_lang, _xstream_pref, _kodi_lang]:
                if lang and lang not in languages:
                    languages.append(lang)
            _log('Languages: pref=%s tmdb=%s xstream=%s kodi=%s -> %s' % (
                pref_lang, _tmdb_lang, _xstream_pref, _kodi_lang, languages))
        except Exception:
            languages = [pref_lang or 'de']
    else:
        # xShip (default): single preferred language, passed by caller
        languages = [pref_lang or 'de']

    # ── Phase 0 (xStream only): resolve TMDB ID from title search ─────
    if _ADDON_NAME == 'xstream' and not tmdb_id:
        _log('Phase 0: resolving TMDB ID for title=%r year=%s mediatype=%s' % (title, year, mediatype))
        search_title = re.sub(r'\s*\(\d{4}\)\s*$', '', title).strip() if title else ''
        if search_title:
            try:
                tmdb_search = cTMDB()
                if mediatype == 'movie':
                    result = tmdb_search.search_movie_name(search_title, year)
                else:
                    result = tmdb_search.search_tvshow_name(search_title, year)
                if result and 'id' in result:
                    tmdb_id = str(result['id'])
                    _log('Phase 0: resolved tmdb_id=%s' % tmdb_id)
            except Exception as e:
                _log('Phase 0: search failed: %s' % e)
        if not tmdb_id:
            _log('Phase 0: could not resolve TMDB ID, aborting')
            xbmcgui.Dialog().notification(
                'Trailer', 'TMDB-ID nicht gefunden',
                xbmcgui.NOTIFICATION_WARNING, 3000,
            )
            return

    _log('START tmdb_id=%s title=%r year=%s mediatype=%s languages=%s' % (tmdb_id, title, year, mediatype, languages))

    # ── Capability detection (same for both addons) ────────────────
    smarttube = _getSmartTubePackage()  # Android only, cached for session
    has_yt_addon = xbmc.getCondVisibility('System.AddonIsEnabled(plugin.video.youtube)')
    if not has_yt_addon and not smarttube:
        # Kein Player verfügbar -- YT-Addon installieren/aktivieren? (1x pro Session)
        _win = xbmcgui.Window(10000)
        if not _win.getProperty(_PROP_PREFIX + '.yt_declined'):
            if _ensureYouTubeAddon():
                has_yt_addon = True
            else:
                _win.setProperty(_PROP_PREFIX + '.yt_declined', '1')
    has_yt_player = bool(smarttube or has_yt_addon)  # can play YouTube video IDs
    has_own_key = bool(_getUserKey())                # user has own key for expensive searches
    skip_api = bool(smarttube)                       # SmartTube handles age-gates, skip videos.list
    _log('Player: %s | YT addon: %s | has_yt_player: %s | has_own_key: %s | skip_api: %s' % (
        smarttube if smarttube else 'none', has_yt_addon, has_yt_player, has_own_key, skip_api))

    # ── ISA pre-flight: warn if YouTube addon's InputStream Adaptive is off ──
    if not smarttube and has_yt_addon:
        _ISA_WARNED = _PROP_PREFIX + '.isa_warned'
        try:
            import xbmcaddon
            _win = xbmcgui.Window(10000)
            yt = xbmcaddon.Addon('plugin.video.youtube')
            if yt.getSetting('kodion.video.quality.isa') != 'true':
                if not _win.getProperty(_ISA_WARNED):
                    _win.setProperty(_ISA_WARNED, '1')
                    if xbmcgui.Dialog().yesno(
                            'Trailer',
                            '"InputStream Adaptive" im YouTube Add-on ist aus.\n'
                            'Trailer-Wiedergabe kann fehlschlagen. Aktivieren?'):
                        yt.setSetting('kodion.video.quality.isa', 'true')
                        _log('ISA enabled via pre-flight check')
        except Exception:
            pass

    # ── Single TMDB call: EN details + all videos + IMDB ID (1 API call) ──
    tmdb_en = cTMDB(lang='en')  # EN for English title + IMDB ID
    en_data = None
    try:
        ## edit kasi - ,external_ids' sind nicht in en_data
        # term = 'append_to_response=videos&include_video_language=de,en,null'
        # if url_type == 'tv':
        #     term += ',external_ids'
        if url_type == 'tv':
            term = 'append_to_response=videos,external_ids&include_video_language=de,en,null'   # ,external_ids'  in en_data vorhanden!
        else:
            term = 'append_to_response=videos&include_video_language=de,en,null'
        ## --------------------------
        en_data = tmdb_en.getUrl('%s/%s' % (url_type, tmdb_id), term=term)
        en_title = (en_data or {}).get(title_key, '') or title
    except Exception:
        en_title = title
    imdb_id = (en_data or {}).get('imdb_id', '')  # movies have imdb_id at top level
    if not imdb_id and url_type == 'tv':
        imdb_id = (en_data or {}).get('external_ids', {}).get('imdb_id', '') or ''  # TV shows need external_ids
    tmdb_videos = (en_data or {}).get('videos', {})  # all videos regardless of language
    _log('EN title: %r imdb_id: %s tmdb_videos: %d results' % (
        en_title, imdb_id, len((tmdb_videos or {}).get('results', []))))

    # ── Season-specific TMDB override (if season is set) ──────────────
    if season:
        try:
            season_data = tmdb_en.getUrl('tv/%s/season/%s' % (tmdb_id, season),
                term='append_to_response=videos&include_video_language=de,en,null')
            tmdb_videos = (season_data or {}).get('videos', {})
            imdb_id = ''  # Season pass must not use IMDB (no season-specific trailers)
            _log('Season %s: tmdb_videos=%d results, imdb_id cleared' % (
                season, len((tmdb_videos or {}).get('results', []))))
        except Exception as e:
            _log('Season %s TMDB fetch failed: %s' % (season, e))

    # ── Run per-language block search ────────────────────────────────
    result = _runTrailerSearch(
        tmdb_id=tmdb_id, mediatype=mediatype,
        title=title, en_title=en_title, year=year, poster=poster,
        imdb_id=imdb_id, languages=languages,
        has_yt_player=has_yt_player, has_own_key=has_own_key, skip_api=skip_api,
        tmdb_videos=tmdb_videos,
        season=season,
        vtype_prefix='Staffel-' if season else '',
    )

    # ── Season fallback: try series-level trailer if season search failed ──
    if result is None and season:
        _log('Season %s: kein Staffel-Trailer, Fallback auf Serien-Trailer' % season)
        try:
            fb_data = tmdb_en.getUrl('tv/%s' % tmdb_id,
                term='append_to_response=videos,external_ids&include_video_language=de,en,null')
            fb_videos = (fb_data or {}).get('videos', {})
            fb_imdb = (fb_data or {}).get('external_ids', {}).get('imdb_id', '') or ''
            fb_en_title = (fb_data or {}).get('name', '') or title
            _log('Fallback: tmdb_videos=%d imdb=%s en_title=%r' % (
                len((fb_videos or {}).get('results', [])), fb_imdb, fb_en_title))
            result = _runTrailerSearch(
                tmdb_id=tmdb_id, mediatype=mediatype,
                title=title, en_title=fb_en_title, year=year, poster=poster,
                imdb_id=fb_imdb, languages=languages,
                has_yt_player=has_yt_player, has_own_key=has_own_key, skip_api=skip_api,
                tmdb_videos=fb_videos,
                season=None,
                vtype_prefix='Serien-',
            )
        except Exception as e:
            _log('Season fallback failed: %s' % e)

    # ── Post-search handling ─────────────────────────────────────────
    primary_lang = languages[0] if languages else 'de'
    if result:
        played_imdb = result['source'] == 'IMDB'
        _showHintIfNeeded(has_yt_player, has_own_key, True, played_imdb, primary_lang)
    else:
        # Give up — show hint popup or generic notification
        hint_shown = _showHintIfNeeded(has_yt_player, has_own_key, False, False, primary_lang)
        if not hint_shown:
            is_de = (_ADDON_NAME == 'xship') or (xbmc.getLanguage(xbmc.ISO_639_1) or 'de') == 'de'
            no_hit = 'Kein Trailer gefunden' if is_de else 'No trailer found'
            xbmcgui.Dialog().notification(
                    'Trailer', no_hit,
                    xbmcgui.NOTIFICATION_WARNING, 3000,
                )


# ── Quick trailer existence check (for TMDB info dialog button) ──────────

def hasTrailer(tmdb_id, imdb_id='', mediatype='movie'):
    """Quick async check if a trailer exists via KinoCheck, TMDB, or IMDB.
    Runs available checks in parallel, returns True on first hit.
    Respects player gating: KinoCheck/TMDB need a YT player, IMDB always works.
    Used by tmdbinfo.py to decide whether to show the trailer button."""
    import xbmc
    from concurrent.futures import ThreadPoolExecutor, as_completed

    if mediatype == 'tvshow':
        mediatype = 'tv'
    url_type = 'movie' if mediatype == 'movie' else 'tv'
    _log('hasTrailer: tmdb_id=%s imdb_id=%s mediatype=%s' % (tmdb_id, imdb_id, mediatype))

    # Detect YT player capability (same logic as playTrailer)
    smarttube_pkg = _getSmartTubePackage()
    has_yt_addon = xbmc.getCondVisibility('System.AddonIsEnabled(plugin.video.youtube)')
    has_yt_player = bool(smarttube_pkg) or has_yt_addon

    def _ck():
        try:
            hits, _ = _searchKinoCheckAPI(tmdb_id, mediatype)
            return bool(hits)
        except Exception:
            return False

    def _tmdb():
        try:
            from resources.lib.tmdb import cTMDB
            data = cTMDB().getUrl('%s/%s/videos' % (url_type, tmdb_id))
            return bool(data and data.get('results'))
        except Exception:
            return False

    def _imdb():
        try:
            url, _ = _searchIMDB(imdb_id)
            return bool(url)
        except Exception:
            return False

    # Build task list respecting gating
    tasks = []
    if has_yt_player:
        tasks.append(('KinoCheck', _ck))
        tasks.append(('TMDB', _tmdb))
    # IMDB always available (direct MP4, no player needed)
    if imdb_id and not _imdb_dead:
        tasks.append(('IMDB', _imdb))

    if not tasks:
        _log('hasTrailer: no checks to run (no YT player, no IMDB ID)')
        return False

    with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
        futures = {pool.submit(fn): name for name, fn in tasks}
        for future in as_completed(futures):
            try:
                if future.result():
                    _log('hasTrailer: %s has trailer' % futures[future])
                    return True
            except Exception:
                pass

    _log('hasTrailer: no trailer found')
    return False
