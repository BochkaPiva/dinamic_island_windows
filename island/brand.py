# SPDX-License-Identifier: GPL-3.0-only
"""Nelviro identity. Product styling is independent of persisted installation IDs."""
import winreg

# Neutral interface palette approved against the user's Raycast references.
# Glacier remains in the original brand assets, not in UI selection surfaces.
DARK = dict(bg='#111111', side='#202020', surface='#1C1C1C', raised='#303030',
    line='#303030', text='#F2F2F2', muted='#A6A6A6', accent='#E5E5E5',
    onAccent='#181818', selection='#343434', field='#191919', danger='#FFB4B4')
LIGHT = dict(bg='#F5F5F5', side='#EDEDED', surface='#FFFFFF', raised='#E5E5E5',
    line='#D4D4D4', text='#1B1B1B', muted='#646464', accent='#444444',
    onAccent='#FFFFFF', selection='#DDDDDD', field='#FAFAFA', danger='#A62835')



def palette(theme='dark'):
    return dict(LIGHT if theme == 'light' else DARK)


def resolved_palette(settings):
    theme = settings.get('hub_theme')
    if theme == 'system':
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                    r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize') as key:
                theme = 'light' if winreg.QueryValueEx(key, 'AppsUseLightTheme')[0] else 'dark'
        except OSError:
            theme = 'dark'
    return palette(theme)

# Shared native UI timing in milliseconds; no independent decorative clocks.
MOTION = dict(response=120, toggle=180, groups=320, island=380)
