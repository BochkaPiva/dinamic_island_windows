# SPDX-License-Identifier: GPL-3.0-only
"""One continuous launcher surface; no nested frames or painted bevels."""
from PySide6.QtCore import Qt, QSize, QRectF, QVariantAnimation, QEasingCurve
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QStyledItemDelegate, QStyle)
from .style import font
from .ui_tokens import LineIcon, glyph, TEXT, MUTED, SURFACE


class ResultDelegate(QStyledItemDelegate):
    def sizeHint(self,option,index):
        return QSize(300,54)

    def paint(self,painter,option,index):
        result=index.data(Qt.ItemDataRole.UserRole)
        if result is None:
            return
        p=painter
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect=QRectF(option.rect).adjusted(0,1,0,-1)
        selected=bool(option.state & QStyle.StateFlag.State_Selected)
        hovered=bool(option.state & QStyle.StateFlag.State_MouseOver)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255,255,255,19 if selected else 9 if hovered else 0))
        p.drawRoundedRect(rect,8,8)
        icon_rect=QRectF(rect.left()+12,rect.top()+14,24,24)
        icon=index.data(Qt.ItemDataRole.DecorationRole)
        if icon and not icon.isNull():
            icon.paint(p,icon_rect.toRect())
        else:
            glyph(p,result.target if result.kind=="command" else result.kind,icon_rect,MUTED)
        left=rect.left()+50
        width=max(20,round(rect.right()-left-42))
        p.setFont(font(14,500))
        p.setPen(QColor(TEXT))
        p.drawText(QRectF(left,rect.top()+7,width,21),Qt.AlignmentFlag.AlignVCenter,
            p.fontMetrics().elidedText(result.title,Qt.TextElideMode.ElideRight,width))
        p.setFont(font(11,400))
        p.setPen(QColor(MUTED))
        detail="Приложение" if result.kind=="app" else result.detail
        p.drawText(QRectF(left,rect.top()+29,width,17),Qt.AlignmentFlag.AlignVCenter,
            p.fontMetrics().elidedText(detail,Qt.TextElideMode.ElideMiddle,width))
        if selected:
            p.setFont(font(15,400)); p.setPen(QColor(MUTED))
            p.drawText(QRectF(rect.right()-30,rect.top(),20,rect.height()),Qt.AlignmentFlag.AlignCenter,"↵")
        p.restore()


class SearchPresentation:
    def build_presentation(self):
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(600,96)
        self.setStyleSheet("""
            QWidget {background:transparent;color:#f4f4f6;font-family:'Golos Text';}
            QLineEdit {background:transparent;color:#f4f4f6;border:0;padding:0;font-size:18px;selection-background-color:#526582;}
            QLabel#escape {color:#858993;font-size:10px;}
            QLabel#searchStatus {color:#9296a0;font-size:10px;}
            QLabel#searchKeys {color:#858993;font-size:10px;}
            QListWidget {background:transparent;border:0;outline:0;padding:0;}
        """)
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
        self.input.setPlaceholderText("Поиск приложений, файлов, команд")
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
        path.addRoundedRect(QRectF(self.rect()),14,14)
        return path

    def paintEvent(self,event):
        p=QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path=self.shape()
        color=QColor(SURFACE)
        color.setAlpha(235 if self.owner.settings.get("search_glass") else 255)
        p.fillPath(path,color)
        p.setPen(QPen(QColor(255,255,255,26),1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(self.rect()).adjusted(.5,.5,-.5,-.5),14,14)
        if self.results.isVisible():
            p.setPen(QPen(QColor(255,255,255,14),1))
            p.drawLine(22,67,self.width()-22,67)

    def showEvent(self,event):
        super().showEvent(event)
        from .platform_win import apply_search_backdrop
        self.backdrop_applied=apply_search_backdrop(self)
