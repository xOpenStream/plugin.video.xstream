# -*- coding: utf-8 -*-
# Python 3

import os
import shutil
import json
import requests
import zipfile

from requests.auth import HTTPBasicAuth
from resources.lib.config import cConfig
from resources.lib.tools import infoDialog
from xbmc import executebuiltin
from xbmcvfs import translatePath
from resources.lib.logger import Logger as logger

# Resolver
def resolverUpdate():
    # Release Branch https://github.com/Gujal00/ResolveURL
    username = 'Gujal00'
    resolve_dir = 'ResolveURL'
    resolve_id = 'script.module.resolveurl'
    branch = 'master'
    token = ''

    try:
        return UpdateResolve(username, resolve_dir, resolve_id, branch, token)
    except Exception as e:
        logger.error('-> [updateManager]: Exception Raised: %s' % str(e))
        return False


# Update Resolver
def UpdateResolve(username, resolve_dir, resolve_id, branch, token):
    REMOTE_PLUGIN_COMMITS = "https://api.github.com/repos/%s/%s/commits/%s" % (username, resolve_dir, branch)   # Github Commits
    REMOTE_PLUGIN_DOWNLOADS = "https://api.github.com/repos/%s/%s/zipball/%s" % (username, resolve_dir, branch) # Github Downloads
    PACKAGES_PATH = translatePath(os.path.join('special://home/addons/packages/'))  # Packages Ordner für Downloads
    ADDON_PATH = translatePath(os.path.join('special://home/addons/packages/', '%s') % resolve_id)  # Addon Ordner in Packages
    INSTALL_PATH = translatePath(os.path.join('special://home/addons/', '%s') % resolve_id) # Installation Ordner
    
    auth = HTTPBasicAuth(username, token)
    logger.debug('-> [updateManager]: %s: - Search for updates.' % resolve_id)
    try:
        ADDON_DIR = translatePath(os.path.join('special://userdata/addon_data/', '%s') % resolve_id) # Pfad von ResolveURL Daten
        LOCAL_PLUGIN_VERSION = os.path.join(ADDON_DIR, "update_sha")    # Pfad der update.sha in den ResolveURL Daten
        LOCAL_FILE_NAME_PLUGIN = os.path.join(ADDON_DIR, 'update-' + resolve_id + '.zip')
        if not os.path.exists(ADDON_DIR): os.mkdir(ADDON_DIR)
        
        if cConfig().getSetting('enforceUpdate') == 'true':
            if os.path.exists(LOCAL_PLUGIN_VERSION): os.remove(LOCAL_PLUGIN_VERSION)
            
        commitXML = _getXmlString(REMOTE_PLUGIN_COMMITS, auth)  # Commit Update
        if commitXML:
            isTrue = commitUpdate(commitXML, LOCAL_PLUGIN_VERSION, REMOTE_PLUGIN_DOWNLOADS, PACKAGES_PATH, resolve_dir, LOCAL_FILE_NAME_PLUGIN, auth)
            
            if isTrue is True:
                logger.debug('-> [updateManager]: %s: - download new update.' % resolve_id)
                shutil.make_archive(ADDON_PATH, 'zip', ADDON_PATH)
                shutil.unpack_archive(ADDON_PATH + '.zip', INSTALL_PATH)
                logger.debug('-> [updateManager]: %s: - install new update.' % resolve_id)
                if os.path.exists(ADDON_PATH + '.zip'): os.remove(ADDON_PATH + '.zip')
                logger.debug('-> [updateManager]: %s: - update completed.' % resolve_id)
                return True
            elif isTrue is None:
                logger.debug('-> [updateManager]: %s: - no update available.' % resolve_id)
                return None

        logger.error('-> [updateManager]: %s: - Error updating!' % resolve_id)
        return False
    except:
        logger.error('-> [updateManager]: %s: - Error updating!' % resolve_id)
        return False

def commitUpdate(onlineFile, offlineFile, downloadLink, LocalDir, plugin_id, localFileName, auth):
    try:
        jsData = json.loads(onlineFile)
        if not os.path.exists(offlineFile) or open(offlineFile).read() != jsData['sha']:
            logger.debug('-> [updateManager]: %s: - Start updating!' % plugin_id)
            isTrue = doUpdate(LocalDir, downloadLink, plugin_id, localFileName, auth)
            if isTrue is True:
                try:
                    open(offlineFile, 'w').write(jsData['sha'])
                    return True
                except:
                    return False
            else:
                return False
        else:
            return None
    except Exception:
        os.remove(offlineFile)
        logger.error('-> [updateManager]: RateLimit reached')
        return False


def doUpdate(LocalDir, REMOTE_PATH, Title, localFileName, auth):
    try:
        response = requests.get(REMOTE_PATH, auth=auth, timeout=10)  # verify=False,
        if response.status_code == 200:
            open(localFileName, "wb").write(response.content)
        else:
            return False
        updateFile = zipfile.ZipFile(localFileName)
        removeFilesNotInRepo(updateFile, LocalDir)
        for index, n in enumerate(updateFile.namelist()):
            if n[-1] != "/":
                dest = os.path.join(LocalDir, "/".join(n.split("/")[1:]))
                if not os.path.abspath(dest).startswith(os.path.abspath(LocalDir)):
                    continue  # skip entries that escape target directory
                destdir = os.path.dirname(dest)
                if not os.path.isdir(destdir):
                    os.makedirs(destdir)
                data = updateFile.read(n)
                if os.path.exists(dest):
                    os.remove(dest)
                f = open(dest, 'wb')
                f.write(data)
                f.close()
        updateFile.close()
        os.remove(localFileName)
        executebuiltin("UpdateLocalAddons()")
        return True
    except:
        logger.error('-> [updateManager]: doUpdate not possible due download error')
        return False


def removeFilesNotInRepo(updateFile, LocalDir):
    ignored_files = ['settings.xml', 'aniworld.py', 'aniworld.png']
    updateFileNameList = [i.split("/")[-1] for i in updateFile.namelist()]

    for root, dirs, files in os.walk(LocalDir):
        if ".git" in root or ".idea" in root:
            continue
        else:
            for file in files:
                if file in ignored_files:
                    continue
                if file not in updateFileNameList:
                    os.remove(os.path.join(root, file))


def _getXmlString(xml_url, auth):
    try:
        xmlString = requests.get(xml_url, auth=auth, timeout=10).content  # verify=False,
        if "sha" in json.loads(xmlString):
            return xmlString
        else:
            logger.error('-> [updateManager]: Update-URL incorrect or bad credentials')
    except Exception as e:
        logger.error(e)


# todo Verzeichnis packen -für zukünftige Erweiterung "Backup"
def zipfolder(foldername, target_dir):
    zipobj = zipfile.ZipFile(foldername + '.zip', 'w', zipfile.ZIP_DEFLATED)
    rootlen = len(target_dir) + 1
    for base, dirs, files in os.walk(target_dir):
        for file in files:
            fn = os.path.join(base, file)
            zipobj.write(fn, fn[rootlen:])
    zipobj.close()


def devUpdates():  # für manuelles Updates vorgesehen
    try:
        cConfig().setSetting('resolver.branch', 'release')
        status = resolverUpdate()
        if status == True:  infoDialog(cConfig().getLocalizedString(30116), sound=False, icon='INFO', time=6000)
        if status == False: infoDialog(cConfig().getLocalizedString(30117), sound=True, icon='ERROR')
        if status == None:  infoDialog(cConfig().getLocalizedString(30118), sound=False, icon='INFO', time=6000)
        if cConfig().getSetting('enforceUpdate') == 'true': cConfig().setSetting('enforceUpdate', 'false')
    except Exception as e:
        logger.error(e)