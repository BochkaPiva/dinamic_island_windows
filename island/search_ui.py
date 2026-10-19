# SPDX-License-Identifier: GPL-3.0-only
"""One continuous launcher surface; no nested frames or painted bevels."""
from PySide6.QtCore import Qt, QSize, QRectF, QVariantAnimation, QEasingCurve
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QStyledItemDelegate, QStyle)
from .style import font
from .brand import resolved_palette
from .ui_tokens import LineIcon, glyph, TEXT, MUTED, SURFACE


class ResultDelegate(QStyledItemDelegate):
    def sizeHint(self,option,index):
        return QSize(300,54)

    def paint(self,painter,option,index):
        result=index.data(Qt.ItemDataRole.UserRole)
        if result is None:
            return
        p=painter
        c=resolved_palette(self.parent().window().owner.settings)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect=QRectF(option.rect).adjusted(0,1,0,-1)
        selected=bool(option.state & QStyle.StateFlag.State_Selected)
        hovered=bool(option.state & QStyle.StateFlag.State_MouseOver)
        p.setPen(Qt.PenStyle.NoPen)
        fill=QColor(c['selection'] if selected else c['raised']); fill.setAlpha(255 if selected or hovered else 0)
        p.setBrush(fill)
        p.drawRoundedRect(rect,8,8)
        icon_rect=QRectF(rect.left()+12,rect.top()+14,24,24)
        icon=index.data(Qt.ItemDataRole.DecorationRole)
        if icon and not icon.isNull():
            icon.paint(p,icon_rect.toRect())
        else:
            glyph(p,result.target if result.kind=="command" else result.kind,icon_rect,c['muted'])
        left=rect.left()+50
        width=max(20,round(rect.right()-left-42))
        p.setFont(font(14,500))
        p.setPen(QColor(c['text']))
        p.drawText(QRectF(left,rect.top()+7,width,21),Qt.AlignmentFlag.AlignVCenter,
            p.fontMetrics().elidedText(result.title,Qt.TextElideMode.ElideRight,width))
        p.setFont(font(11,400))
        p.setPen(QColor(c['muted']))
        detail="Приложение" if result.kind=="app" else result.detail
        p.drawText(QRectF(left,rect.top()+29,width,17),Qt.AlignmentFlag.AlignVCenter,
            p.fontMetrics().elidedText(detail,Qt.TextElideMode.ElideMiddle,width))
        if selected:
            p.setFont(font(15,400)); p.setPen(QColor(c['muted']))
            p.drawText(QRectF(rect.right()-30,rect.top(),20,rect.height()),Qt.AlignmentFlag.AlignCenter,"↵")
        p.restore()


class SearchPresentation:
    def build_presentation(self):
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(600,96)
        self.apply_brand_theme()
        # Styling is refreshed on every launch to follow the settings window.
        root=QVBoxLayout(self)
        root.setContentsMargins(12,4,12,4)
        root.setSpacing(0)
        header=QWidget()
        header.setObjectName("searchHeader")
        header.setFixedHeight(64)
        bar=QHBoxLayout(header)
        bar.setContentsMargins(10,0,10,0)
        bar.setSpacing(14)
        bar.addWidget(LineIcon("search",22))
        self.input=QLineEdit()
        self.input.setFont(font(18))
        self.input.setPlaceholderText("Что открыть?")
        self.input.setAccessibleName("Поиск приложений, файлов и команд")
        self.input.setClearButtonEnabled(True)
        self.input.installEventFilter(self)
        bar.addWidget(self.input,1)
        badge=QLabel("esc")
        badge.setObjectName("escape")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bar.addWidget(badge)
        root.addWidget(header)
        self.results=QListWidget()
        self.results.installEventFilter(self)
        self.results.setItemDelegate(ResultDelegate(self.results))
        self.results.setMouseTracking(True)
        self.results.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.results.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.results.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.results.setSpacing(0)
        self.results.setMinimumHeight(0)
        self.results.hide()
        self.results.itemActivated.connect(lambda _:self.activate())
        root.addWidget(self.results,1)
        footer=QHBoxLayout()
        footer.setContentsMargins(10,0,10,0)
        self.status=QLabel("Приложения · файлы · команды")
        self.status.setObjectName("searchStatus")
        self.status.setMinimumWidth(0)
        self.status.setFixedHeight(24)
        footer.addWidget(self.status,1)
        keys=QLabel("↑ ↓  выбрать     ↵  открыть")
        keys.setObjectName("searchKeys")
        footer.addWidget(keys)
        root.addLayout(footer)
        self.height_animation=QVariantAnimation(self)
        self.height_animation.setDuration(180)
        self.height_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.height_animation.valueChanged.connect(lambda v:self.resize(self.width(),round(v)))
        self.backdrop_applied=False
        self._height_target=96

    def apply_brand_theme(self):
        c=resolved_palette(self.owner.settings)
        self.setStyleSheet(f"""
            QWidget {{background:transparent;color:{c['text']};font-family:'Golos Text';}}
            QLineEdit {{background:transparent;color:{c['text']};border:0;padding:0;font-size:18px;selection-background-color:{c['selection']};}}
            QLabel#escape,QLabel#searchStatus,QLabel#searchKeys {{color:{c['muted']};font-size:11px;}}
            QListWidget {{background:transparent;border:0;outline:0;padding:0;}}
        """)

    def update_presentation(self):
        count=min(6,self.results.count())
        self.results.setVisible(bool(count))
        available=self.owner.screen().availableGeometry()
        height=max(96,min(available.height()-100,96+54*count))
        if height==self._height_target:
            return
        self._height_target=height
        self.height_animation.stop()
        if self.isVisible():
            self.height_animation.setStartValue(float(self.height()))
            self.height_animation.setEndValue(float(height))
            self.height_animation.start()
        else:
            self.resize(min(600,available.width()-40),height)

    def shape(self):
        path=QPainterPath()
        path.addRoundedRect(QRectF(self.rect()),24,24)
        return path

    def paintEvent(self,event):
        p=QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path=self.shape()
        c=resolved_palette(self.owner.settings)
        color=QColor(c['surface'])
        color.setAlpha(244 if self.owner.settings.get("search_glass") else 255)
        p.fillPath(path,color)
        p.setPen(QPen(QColor(c['line']),1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(self.rect()).adjusted(.5,.5,-.5,-.5),24,24)
        if self.results.isVisible():
            p.setPen(QPen(QColor(c['line']),1))
            p.drawLine(22,67,self.width()-22,67)

    def showEvent(self,event):
        self.apply_brand_theme()
        super().showEvent(event)
        from .platform_win import apply_search_backdrop
        self.backdrop_applied=apply_search_backdrop(self)
