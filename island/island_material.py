# SPDX-License-Identifier: GPL-3.0-only
"""Shared island material: classical black or membership-gated smoked glass.

The background uses per-pixel translucency. Curved surface normals shade a cached studio reflection;
there is no desktop capture, synthetic wallpaper or claim of desktop refraction.
"""
from dataclasses import dataclass
import re
from functools import lru_cache
import numpy as np
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor,QPainterPath,QLinearGradient,QPen,QBrush,QTransform,QImage,QPainter

HEX_COLOR=re.compile(r'#[0-9a-fA-F]{6}\Z')


def valid_color(value):
    return isinstance(value,str) and bool(HEX_COLOR.fullmatch(value))


@dataclass(frozen=True)
class Appearance:
    glass: bool=False
    color: str='#000000'


def effective_appearance(owner):
    if not owner or owner.settings.get('island_material')!='glass':return Appearance()
    if not owner.access.feature('island.glass').allowed:return Appearance()
    color=owner.settings.get('island_color') if owner.access.feature('island.color').allowed else '#000000'
    preview=getattr(owner,'_island_color_preview',None)
    if preview is not None and owner.access.feature('island.color').allowed:color=preview
    return Appearance(True,color if valid_color(color) else '#000000')


def smoke_color(value):
    """A dye, not a flat RGB fill: preserve readable white controls for every hue."""
    color=QColor(value);h,s,v,_=color.getHsvF()
    return QColor.fromHsvF(max(0.,h),s*.75,.055+v*.115)


@lru_cache(maxsize=12)
def reflected_light(width,height):
    """A fixed studio reflection shaped by curved normals, not a desktop image.

    Cache only the low-frequency illumination. Text and the silhouette stay vector
    at native DPR; this works through the software painter without a GPU backend.
    """
    width=max(2,width);height=max(2,height)
    y,x=np.mgrid[:height,:width].astype(np.float32)
    radius=min(24.,height/2)
    qx=np.abs(x-(width-1)/2)-(width/2-radius)
    qy=np.abs(y-(height-1)/2)-(height/2-radius)
    distance=-(np.hypot(np.maximum(qx,0),np.maximum(qy,0))+np.minimum(np.maximum(qx,qy),0)-radius)
    gy,gx=np.gradient(distance)
    band=min(14.,height*.29)
    slope=np.exp(-np.maximum(distance,0)/max(1.,band))*1.7
    nx=-gx*slope;ny=-gy*slope;nz=np.ones_like(nx)
    norm=np.sqrt(nx*nx+ny*ny+nz*nz);nx/=norm;ny/=norm;nz/=norm
    # The lip catches a broad upper-left softbox, with a much weaker lower return.
    upper=np.exp(-((nx+.42)**2+(ny+.6)**2+(nz-.68)**2)/.13)
    lower=np.exp(-((nx-.5)**2+(ny-.65)**2+(nz-.55)**2)/.09)
    # The reflected light bends with the normals instead of tracing a white border.
    reflected_x=x/width+nx*.16
    reflected_y=y/height+ny*.22
    softbox=np.exp(-((reflected_x-.23)/.5)**2-((reflected_y+.18)/.32)**2)
    diagonal=np.exp(-((reflected_x*.65+reflected_y-.21)/.16)**2)
    alpha=np.clip(upper*69+lower*29+softbox*35+diagonal*8,0,90)
    rgba=np.empty((height,width,4),dtype=np.uint8);rgba[:,:,:3]=255;rgba[:,:,3]=alpha.astype(np.uint8)
    return QImage(rgba.data,width,height,width*4,QImage.Format.Format_RGBA8888).copy()


def paint_island(p,path,appearance=Appearance(),*,native=False):
    if not appearance.glass:
        p.fillPath(path,QColor('black'));return
    box=path.boundingRect()
    if box.isEmpty():return
    p.save()
    smoke=smoke_color(appearance.color)
    body=QLinearGradient(box.topLeft(),box.bottomLeft())
    top=QColor(smoke.lighter(180));top.setAlpha(204 if native else 255)
    bottom=QColor(smoke);bottom.setAlpha(232 if native else 255)
    body.setColorAt(0,top);body.setColorAt(.5,bottom);body.setColorAt(1,top.darker(150))
    p.fillPath(path,body)
    # SourceAtop preserves the antialiased alpha silhouette. No integer region,
    # clipped white pen, or nested border can stair-step the rounded corners.
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    p.drawImage(box,reflected_light(min(768,max(2,round(box.width()))),min(256,max(2,round(box.height())))))
    p.restore()
