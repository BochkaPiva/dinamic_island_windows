# SPDX-License-Identifier: GPL-3.0-only
"""Nelviro identity. Product styling is independent of persisted installation IDs."""
import winreg

DARK = dict(bg='#101216', side='#15181D', surface='#1C2026', raised='#262C34',
    line='#343C47', text='#F5F6F8', muted='#AFB7C3', accent='#B4DFF2',
    onAccent='#11232D', selection='#233C49', field='#15181D', danger='#FFB4B4')
LIGHT = dict(bg='#F2F3F5', side='#E9ECF0', surface='#FFFFFF', raised='#E8EDF1',
    line='#D1D8E0', text='#171A1F', muted='#596574', accent='#25647F',
    onAccent='#FFFFFF', selection='#DCEEF5', field='#F2F3F5', danger='#A62835')


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
