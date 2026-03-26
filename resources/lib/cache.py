# -*- coding: utf-8 -*-
# resources/lib/cache.py

import xbmc
import xbmcvfs
import xbmcaddon
import xbmcgui
import time
import ast
import hashlib
import os
from resources.lib.config import cConfig
from resources.lib.logger import Logger


class CacheStrategy:

    def get(self, key, cache_time=-1):
        raise NotImplementedError

    def set(self, key, content):
        raise NotImplementedError

    def clear(self, key):
        raise NotImplementedError

    def clearAll(self):
        raise NotImplementedError


class MemoryCacheStrategy(CacheStrategy):

    def __init__(self):
        self._win = xbmcgui.Window(10000)
        self.prefix = xbmcaddon.Addon().getAddonInfo('name') + "."

    def _get_full_key(self, key):
        key_str = str(key).strip()
        if not key_str:
            key_str = "empty"
        return self.prefix + hashlib.md5(key_str.encode('utf-8')).hexdigest()

    def get(self, key, cache_time=-1):
        full_key = self._get_full_key(key)
        try:
            data_str = self._win.getProperty(full_key)
            if not data_str:
                return None

            cached_time, content = ast.literal_eval(data_str)

            if cache_time < 0 or (time.time() - cached_time) < cache_time:
                return content
            else:
                self._win.clearProperty(full_key)
                return None
        except:
            self._win.clearProperty(full_key)
            return None

    def set(self, key, content):
        full_key = self._get_full_key(key)
        try:
            entry = (time.time(), content)
            self._win.setProperty(full_key, repr(entry))
        except:
            pass

    def clear(self, key):
        full_key = self._get_full_key(key)
        self._win.clearProperty(full_key)

    def clearAll(self):
        self._win.clearProperties()


class FileCacheStrategy(CacheStrategy):

    def __init__(self):
        addon = xbmcaddon.Addon()
        self.cache_dir = xbmcvfs.translatePath(addon.getAddonInfo('profile')) + "cache/"
        if not xbmcvfs.exists(self.cache_dir):
            xbmcvfs.mkdirs(self.cache_dir)

    def _get_filename(self, key):
        key_str = str(key).strip()
        if not key_str:
            key_str = "empty"
        hash_name = hashlib.md5(key_str.encode('utf-8')).hexdigest()
        return os.path.join(self.cache_dir, hash_name + ".cache")

    def get(self, key, cache_time=-1):
        filename = self._get_filename(key)
        try:
            if not xbmcvfs.exists(filename):
                return None

            with xbmcvfs.File(filename, 'r') as f:
                data_str = f.read()

            if not data_str:
                return None

            cached_time, content = ast.literal_eval(data_str)

            if cache_time < 0 or (time.time() - cached_time) < cache_time:
                return content
            else:
                xbmcvfs.delete(filename)
                return None
        except Exception:
            try:
                xbmcvfs.delete(filename)
            except:
                pass
            return None

    def set(self, key, content):
        filename = self._get_filename(key)
        try:
            entry = (time.time(), content)
            with xbmcvfs.File(filename, 'w') as f:
                f.write(repr(entry))
        except Exception as e:
            Logger.error(f"[FileCache] Schreibfehler für Key {str(key)[:80]}...: {e}")

    def clear(self, key):
        filename = self._get_filename(key)
        try:
            if xbmcvfs.exists(filename):
                xbmcvfs.delete(filename)
        except:
            pass

    def clearAll(self):
        try:
            _, files = xbmcvfs.listdir(self.cache_dir)
            for file in files:
                try:
                    xbmcvfs.delete(os.path.join(self.cache_dir, file))
                except:
                    pass
        except Exception as e:
            Logger.error(f"[FileCache] Fehler bei clearAll: {e}")


# ====================== Factory ======================

class cCache:

    def __init__(self, use_memory=None, cache_time=None):
        self._is_memory_active = use_memory if use_memory is not None else (cConfig().getSetting('volatileHtmlCache', 'false') == 'true')
        self._cache_time = int(cache_time) if cache_time is not None else int(cConfig().getSetting('cacheTime', 360)) * 60
        self._strategy = None
        if self._is_memory_active:
            self._strategy = MemoryCacheStrategy()
        else:
            self._strategy = FileCacheStrategy()

    def get(self, key, cacheTime = None):
        cacheTime = cacheTime if cacheTime is not None else self._cache_time
        return self._strategy.get(key, cacheTime)

    def set(self, key, content):
        self._strategy.set(key, content)

    def clear(self, key):
        self._strategy.clear(key)

    def clearAll(self):
        self._strategy.clearAll()
