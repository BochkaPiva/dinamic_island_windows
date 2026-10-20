# SPDX-License-Identifier: GPL-3.0-only
"""Shared island material: classical black or membership-gated smoked glass.

The background uses per-pixel translucency. Native backdrop supplies blur when supported;
there is no desktop capture, synthetic wallpaper or claim of desktop refraction.
"""
from dataclasses import dataclass
import re
from PySide6.QtGui import QColor

HEX_COLOR=re.compile(r'#[0-9a-fA-F]{6}\Z')


def valid_color(value):
    return isinstance(value,str) and bool(HEX_COLOR.fullmatch(value))


@dataclass(frozen=True)
class Appearance:
    glass: bool=False
    color: str='#000000'


def effective_appearance(owner):
    if not owner or not hasattr(owner,"settings") or not hasattr(owner,"access"):return Appearance()
    color=owner.settings.get('island_color') if owner.access.feature('island.color').allowed else '#000000'
    preview=getattr(owner,'_island_color_preview',None)
    if preview is not None and owner.access.feature('island.color').allowed:color=preview
    glass=owner.settings.get('island_material')=='glass' and owner.access.feature('island.glass').allowed
    return Appearance(glass,color if valid_color(color) else '#000000')


def island_ink(owner):
    return appearance_ink(effective_appearance(owner))


def appearance_ink(appearance):
    color=QColor(appearance.color)
    def linear(value):return value/12.92 if value<=.04045 else ((value+.055)/1.055)**2.4
    luminance=sum(k*linear(v) for k,v in zip((.2126,.7152,.0722),(color.redF(),color.greenF(),color.blueF())))
    return QColor('#171717' if not appearance.glass and luminance>.179 else '#F2F2F2')


def smoke_color(value):
    """A dye, not a flat RGB fill: preserve readable white controls for every hue."""
    color=QColor(value);h,s,v,_=color.getHsvF()
    return QColor.fromHsvF(max(0.,h),s*.75,.055+v*.115)



def paint_island(p,path,appearance=Appearance(),*,native=False):
    if not appearance.glass:
        p.fillPath(path,QColor(appearance.color));return
    box=path.boundingRect()
    if box.isEmpty():return
    p.save()
    smoke=smoke_color(appearance.color)
    body=QColor(smoke);body.setAlpha(155 if native else 255)
    p.fillPath(path,body)
    p.restore()
