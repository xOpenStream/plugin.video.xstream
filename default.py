# -*- coding: utf-8 -*-
# Python 3

def main():
    from xstream import parseUrl
    from os.path import join
    import sys
    import platform
    import os

    from resources.lib.config import cConfig
    from xbmc import LOGINFO as LOGNOTICE, log
    from xbmcvfs import translatePath

    _addonPath_ = translatePath(cConfig().getAddonInfo('path'))
    sys.path.append(join(_addonPath_, 'resources', 'lib'))
    sys.path.append(join(_addonPath_, 'resources', 'lib', 'gui'))
    sys.path.append(join(_addonPath_, 'resources', 'lib', 'handler'))
    sys.path.append(join(_addonPath_, 'resources', 'art', 'sites'))
    sys.path.append(join(_addonPath_, 'resources', 'art'))
    sys.path.append(join(_addonPath_, 'sites'))    
    
    LOGMESSAGE = cConfig().getLocalizedString(30166)
    log('-----------------------------------------------------------------------', LOGNOTICE)
    log(LOGMESSAGE + ' -> [default]: Start xStream Log, Version %s ' % cConfig().getAddonInfo('version'), LOGNOTICE)
    log(LOGMESSAGE + ' -> [default]: Python-Version: %s' % platform.python_version(), LOGNOTICE)

    # RunScript handler for changelog button in settings
    if len(sys.argv) > 1 and sys.argv[1] == 'changelog':
        import xbmcgui
        changelog_path = os.path.join(_addonPath_, 'changelog.txt')
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

    try:
        parseUrl()
    except Exception as e:
        if str(e) == 'UserAborted':
            log(LOGMESSAGE + ' -> [default]: User aborted list creation', LOGNOTICE)
        else:
            import traceback
            import xbmcgui
            log(traceback.format_exc(), LOGNOTICE)
            value = (str(e.__class__.__name__) + ' : ' + str(e), str(traceback.format_exc().splitlines()[-3].split('addons')[-1]))
            dialog = xbmcgui.Dialog().ok(cConfig().getLocalizedString(257), str(value)) # Error

if __name__ == "__main__":
    main()
