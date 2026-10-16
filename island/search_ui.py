# SPDX-License-Identifier: GPL-3.0-only
"""Compact search chrome and result painting, independent of search providers."""
from PyQt6.QtCore import Qt, QSize, QRectF, QVariantAnimation, QEasingCurve
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen, QLinearGradient
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QFrame, QStyledItemDelegate, QStyle)
from .style import font


class Magnifier(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(26,26)

    def paintEvent(self,event):
        p=QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor("#d9dfeb"),1.8))
        p.drawEllipse(QRectF(4,3,13,13))
        p.drawLine(16,16,22,22)


class ResultDelegate(QStyledItemDelegate):
    def sizeHint(self,option,index):
        return QSize(300,58)

    def paint(self,painter,option,index):
        result=index.data(Qt.ItemDataRole.UserRole)
        if result is None:
            return
        p=painter
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect=QRectF(option.rect).adjusted(2,2,-2,-2)
        selected=bool(option.state & QStyle.StateFlag.State_Selected)
        hovered=bool(option.state & QStyle.StateFlag.State_MouseOver)
        p.setPen(QPen(QColor(190,210,255,44 if selected else 0),1))
        p.setBrush(QColor(190,210,255,28 if selected else 12 if hovered else 0))
        p.drawRoundedRect(rect,11,11)
        icon_rect=QRectF(rect.left()+11,rect.top()+10,32,32)
        p.setPen(Qt.PenStyle.NoPen)
        gradient=QLinearGradient(icon_rect.topLeft(),icon_rect.bottomRight())
        gradient.setColorAt(0,QColor(208,224,255,35))
        gradient.setColorAt(1,QColor(138,158,195,12))
        p.setBrush(gradient)
        p.drawRoundedRect(icon_rect,8,8)
        icon=index.data(Qt.ItemDataRole.DecorationRole)
        if icon and not icon.isNull():
            icon.paint(p,icon_rect.adjusted(5,5,-5,-5).toRect())
        else:
            p.setPen(QPen(QColor("#b9c9e4"),1.3))
            p.setBrush(Qt.BrushStyle.NoBrush)
            if result.kind=="command":
                for dx,dy in ((0,0),(9,0),(0,9),(9,9)):
                    p.drawRoundedRect(QRectF(icon_rect.left()+8+dx,icon_rect.top()+8+dy,5,5),1,1)
            else:
                p.drawRoundedRect(icon_rect.adjusted(8,6,-8,-6),2,2)
        left=icon_rect.right()+12
        category={"app":"Приложение","store":"Приложение","command":"Команда"}.get(result.kind,"Файл")
        p.setFont(font(9,400))
        category_width=p.fontMetrics().horizontalAdvance(category)+12
        p.setPen(QColor("#77859a"))
        p.drawText(QRectF(rect.right()-category_width-10,rect.top()+12,category_width,17),
                   Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter,category)
        width=max(40,round(rect.right()-left-category_width-24))
        p.setFont(font(13,500))
        p.setPen(QColor("#f3f5fb"))
        p.drawText(QRectF(left,rect.top()+9,width,20),Qt.AlignmentFlag.AlignVCenter,
                   p.fontMetrics().elidedText(result.title,Qt.TextElideMode.ElideRight,width))
        p.setFont(font(10,400))
        p.setPen(QColor("#a1adbf" if selected else "#7f8da2"))
        width=max(40,round(rect.right()-left-16))
        p.drawText(QRectF(left,rect.top()+31,width,16),Qt.AlignmentFlag.AlignVCenter,
                   p.fontMetrics().elidedText(result.detail,Qt.TextElideMode.ElideMiddle,width))
        p.restore()


class SearchPresentation:
    def build_presentation(self):
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(640,132)
        self.setStyleSheet("""
            QWidget {background:transparent;color:#edf1f8;font-family:'Segoe UI';}
            QFrame#searchHeader {background:rgba(225,236,255,6);border:1px solid rgba(225,236,255,16);border-radius:14px;}
            QLineEdit {background:transparent;color:#f4f6fb;border:0;padding:0;font-size:20px;selection-background-color:#536985;}
            QLabel#escape {color:#8995a9;border:1px solid rgba(220,230,255,28);border-radius:5px;font-size:10px;padding:3px 5px;}
            QLabel#searchStatus {color:#8d9ab0;font-size:10px;background:transparent;}
            QLabel#searchKeys {color:#76849a;font-size:10px;}
            QListWidget {background:transparent;border:0;outline:0;padding:0;}
        """)
        root=QVBoxLayout(self)
        root.setContentsMargins(24,23,24,20)
        root.setSpacing(8)
        header=QFrame()
        header.setObjectName("searchHeader")
        header.setFixedHeight(59)
        bar=QHBoxLayout(header)
        bar.setContentsMargins(16,0,13,0)
        bar.setSpacing(13)
        bar.addWidget(Magnifier())
        self.input=QLineEdit()
        self.input.setPlaceholderText("Найти что-нибудь…")
        self.input.setAccessibleName("Поиск приложений, файлов и команд")
        self.input.setClearButtonEnabled(True)
        self.input.installEventFilter(self)
        bar.addWidget(self.input,1)
        badge=QLabel("esc")
        badge.setObjectName("escape")
        badge.setFixedSize(32,22)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bar.addWidget(badge,0,Qt.AlignmentFlag.AlignVCenter)
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
        footer.setContentsMargins(6,0,6,0)
        self.status=QLabel("Приложения · файлы · команды")
        self.status.setObjectName("searchStatus")
        self.status.setMinimumWidth(0)
        self.status.setWordWrap(False)
        footer.addWidget(self.status,1)
        keys=QLabel("↑ ↓  выбрать     ↵  открыть")
        keys.setObjectName("searchKeys")
        footer.addWidget(keys)
        root.addLayout(footer)
        self.height_animation=QVariantAnimation(self)
        self.height_animation.setDuration(170)
        self.height_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.height_animation.valueChanged.connect(lambda v:self.resize(self.width(),round(v)))
        self.backdrop_applied=False

    def update_presentation(self):
        count=min(6,self.results.count())
        self.results.setVisible(bool(count))
        available=self.owner.screen().availableGeometry()
        height=min(available.height()-100,132+58*count+(4 if count else 0))
        self.height_animation.stop()
        if self.isVisible():
            self.height_animation.setStartValue(float(self.height()))
            self.height_animation.setEndValue(float(height))
            self.height_animation.start()
        else:
            self.resize(min(640,available.width()-40),height)

    def paintEvent(self,event):
        p=QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect=QRectF(self.rect()).adjusted(10,9,-10,-10)
        # Local vector shading only; no screen capture or continuous background rendering.
        for spread in range(10,0,-1):
            p.setPen(QPen(QColor(0,0,0,round((11-spread)*1.6)),spread*2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect,21,21)
        fill=QLinearGradient(rect.topLeft(),rect.bottomRight())
        glass=self.backdrop_applied
        fill.setColorAt(0,QColor(39,46,59,225 if glass else 247))
        fill.setColorAt(.52,QColor(24,31,43,220 if glass else 241))
        fill.setColorAt(1,QColor(19,25,35,232 if glass else 248))
        p.setBrush(fill)
        p.setPen(QPen(QColor(211,226,255,49),1))
        p.drawRoundedRect(rect,21,21)
        shine=QLinearGradient(rect.topLeft(),rect.bottomLeft())
        shine.setColorAt(0,QColor(220,236,255,23))
        shine.setColorAt(.28,QColor(220,236,255,0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(shine)
        p.drawRoundedRect(rect.adjusted(1,1,-1,-1),20,20)

    def showEvent(self,event):
        super().showEvent(event)
        from .platform_win import apply_search_backdrop
        self.backdrop_applied=apply_search_backdrop(self)
