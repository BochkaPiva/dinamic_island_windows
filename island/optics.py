# SPDX-License-Identifier: GPL-3.0-only
"""Optical edge sampling of the app's own light field, never desktop capture.

DWM acrylic supplies external blur. This layer refracts only the internal light
field; labels and child controls are painted afterwards and stay sharp.
"""
from functools import lru_cache
import numpy as np
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QImage,QPainter,QPainterPath,QColor,QPen,QLinearGradient


def lens_map(width,height,scale=1.,radius=18.):
    if width<2 or height<2:raise ValueError('Lens dimensions must be at least two pixels')
    y,x=np.mgrid[:height,:width].astype(np.float32)
    radius=min(radius*scale,width/2,height/2)
    qx=np.abs(x-(width-1)/2)-(width/2-radius)
    qy=np.abs(y-(height-1)/2)-(height/2-radius)
    sdf=np.hypot(np.maximum(qx,0),np.maximum(qy,0))+np.minimum(np.maximum(qx,qy),0)-radius
    gy,gx=np.gradient(sdf);norm=np.maximum(.001,np.hypot(gx,gy))
    band=min(12*scale,min(width,height)*.2)
    depth=np.clip(-sdf/band,0,1)
    amount=np.where(sdf<0,np.sin(depth*np.pi)*4*scale,0)
    sx=np.clip(np.rint(x+gx/norm*amount),0,width-1).astype(np.int32)
    sy=np.clip(np.rint(y+gy/norm*amount),0,height-1).astype(np.int32)
    return sx,sy


def refract(image,mapping):
    source=image.convertToFormat(QImage.Format.Format_RGBA8888)
    width,height=source.width(),source.height()
    sx,sy=mapping
    if sx.shape!=(height,width) or sy.shape!=(height,width):raise ValueError('Lens map does not match image')
    a=np.frombuffer(source.constBits(),dtype=np.uint8,count=source.sizeInBytes()).reshape(height,source.bytesPerLine())[:,:width*4].reshape(height,width,4)
    pixels=np.ascontiguousarray(a[sy,sx])
    result=QImage(pixels.data,width,height,width*4,QImage.Format.Format_RGBA8888).copy()
    result.setDevicePixelRatio(image.devicePixelRatio())
    return result


@lru_cache(maxsize=2)
def light_field(width,height,scale,light):
    """Stationary, neutral studio illumination owned by the app, not wallpaper."""
    image=QImage(width,height,QImage.Format.Format_RGBA8888);image.fill(QColor('#EEEEEE' if light else '#181818'))
    p=QPainter(image);p.setRenderHint(QPainter.RenderHint.Antialiasing)
    # Broad reflected arcs, with a narrow luminous contour visible through rims.
    for x,y,w,h in ((-.4,-.8,1.5,1.7),(.35,.15,1.4,1.8)):
        box=QRectF(x*width,y*height,w*width,h*height)
        gradient=QLinearGradient(box.topLeft(),box.bottomRight())
        gradient.setColorAt(0,QColor(255,255,255,0));gradient.setColorAt(.5,QColor(255,255,255,23 if not light else 65));gradient.setColorAt(1,QColor(255,255,255,0))
        p.setBrush(gradient);p.setPen(QPen(QColor(255,255,255,14 if not light else 60),2*scale));p.drawEllipse(box)
    p.end();image.setDevicePixelRatio(scale);return image


def paint_surface(painter,widget,colors):
    """Render the sampled internal backdrop inside the rim, below all controls."""
    window=widget.window()
    # Only the broad reflected backdrop is sampled at logical resolution. The
    # rim and every child stay at native DPR; this is not a text raster cache.
    scale=1.
    material=getattr(window,'material',False)
    rect=QRectF(widget.rect()).adjusted(.7,.7,-.7,-.7)
    light=QColor(colors['bg']).lightness()>128
    painter.save()
    path=QPainterPath();path.addRoundedRect(rect,18,18);painter.setClipPath(path)
    if material:
        point=widget.mapTo(window,widget.rect().topLeft())
        key=(widget.width(),widget.height(),window.width(),window.height(),point.x(),point.y(),scale,light)
        if getattr(widget,'_optical_key',None)!=key:
            scene=light_field(round(window.width()*scale),round(window.height()*scale),scale,light)
            crop=scene.copy(round(point.x()*scale),round(point.y()*scale),max(2,round(widget.width()*scale)),max(2,round(widget.height()*scale)))
            crop.setDevicePixelRatio(scale)
            map_key=(crop.width(),crop.height(),scale)
            if getattr(widget,'_optical_map_key',None)!=map_key:
                widget._optical_map=lens_map(*map_key);widget._optical_map_key=map_key
            widget._optical_image=refract(crop,widget._optical_map)
            widget._optical_key=key
        painter.setOpacity(.72);painter.drawImage(0,0,widget._optical_image);painter.setOpacity(1)
    gradient=QLinearGradient(rect.topLeft(),rect.bottomRight())
    top=QColor(colors['raised']);top.setAlpha(75 if material else 255)
    bottom=QColor(colors['surface']);bottom.setAlpha(135 if material else 255)
    gradient.setColorAt(0,top);gradient.setColorAt(1,bottom)
    painter.fillPath(path,gradient);painter.restore()
    # Asymmetric illumination gives the edge thickness without a second frame.
    rim=QLinearGradient(rect.topLeft(),rect.bottomRight())
    rim.setColorAt(0,QColor(255,255,255,52 if material else 12))
    rim.setColorAt(.35,QColor(255,255,255,12 if material else 6))
    rim.setColorAt(1,QColor(255,255,255,25 if material else 8))
    painter.setBrush(Qt.BrushStyle.NoBrush);painter.setPen(QPen(rim,1));painter.drawRoundedRect(rect,18,18)
