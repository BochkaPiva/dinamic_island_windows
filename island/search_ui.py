# SPDX-License-Identifier: GPL-3.0-only
"""One continuous launcher surface; no nested frames or painted bevels."""
from PySide6.QtCore import Qt, QSize, QRectF, QVariantAnimation, QEasingCurve
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QRegion
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QStyledItemDelegate, QStyle)
from .hub_ui import ActionFooter
from .style import font
from .brand import resolved_palette
from .ui_tokens import LineIcon, glyph, TEXT, MUTED, SURFACE


class ResultDelegate(QStyledItemDelegate):
    def sizeHint(self,option,index):
        return QSize(300,80 if index.data(Qt.ItemDataRole.UserRole+1) else 52)

    def paint(self,painter,option,index):
        result=index.data(Qt.ItemDataRole.UserRole)
        if result is None:
            return
        p=painter
        c=resolved_palette(self.parent().window().owner.settings)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect=QRectF(option.rect).adjusted(0,1,0,-1)
        group=index.data(Qt.ItemDataRole.UserRole+1)
        if group:
            p.setFont(font(12,500));p.setPen(QColor(c['muted']))
            p.drawText(rect.adjusted(12,0,-12,0),Qt.AlignmentFlag.AlignTop,group)
            rect.setTop(rect.top()+28)
        selected=bool(option.state & QStyle.StateFlag.State_Selected)
        hovered=bool(option.state & QStyle.StateFlag.State_MouseOver)
        p.setPen(Qt.PenStyle.NoPen)
        fill=QColor(c['selection'] if selected else c['raised']); fill.setAlpha(255 if selected or hovered else 0)
        p.setBrush(fill)
        p.drawRoundedRect(rect,8,8)
        icon_rect=QRectF(rect.left()+12,rect.top()+11,28,28)
        icon=index.data(Qt.ItemDataRole.DecorationRole)
        if icon and not icon.isNull():
            icon.paint(p,icon_rect.toRect())
        else:
            glyph(p,result.target if result.kind=="command" else result.kind,icon_rect,c['muted'])
        left=rect.left()+54
        width=max(20,round(rect.right()-left-110))
        p.setFont(font(15,500))
        p.setPen(QColor(c['text']))
        p.drawText(QRectF(left,rect.top()+7,width,21),Qt.AlignmentFlag.AlignVCenter,
            p.fontMetrics().elidedText(result.title,Qt.TextElideMode.ElideRight,width))
        p.setFont(font(12,400))
        p.setPen(QColor(c['muted']))
        detail="Приложение" if result.kind=="app" else result.detail
        p.drawText(QRectF(left,rect.top()+29,width,17),Qt.AlignmentFlag.AlignVCenter,
            p.fontMetrics().elidedText(detail,Qt.TextElideMode.ElideMiddle,width))
        p.setFont(font(12));p.setPen(QColor(c['muted']))
        kind={'command':'Команда','app':'Приложение','store':'Приложение'}.get(result.kind,'Файл')
        p.drawText(QRectF(rect.right()-104,rect.top(),92,rect.height()),Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter,kind)

        p.restore()


class SearchPresentation:
    def build_presentation(self):
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(720,122)
        self.apply_brand_theme()
        # Styling is refreshed on every launch to follow the settings window.
        root=QVBoxLayout(self)
        root.setContentsMargins(10,4,10,4)
        root.setSpacing(0)
        header=QWidget()
        header.setObjectName("searchHeader")
        header.setFixedHeight(74)
        bar=QHBoxLayout(header)
        bar.setContentsMargins(10,0,10,0)
        bar.setSpacing(14)
        bar.addWidget(LineIcon("search",22))
        self.input=QLineEdit()
        self.input.setFont(font(21))
        self.input.setPlaceholderText("Найти приложение, файл или команду…")
        self.input.setAccessibleName("Поиск приложений, файлов и команд")
        self.input.setClearButtonEnabled(True)
        self.input.installEventFilter(self)
        bar.addWidget(self.input,1)
        badge=QLabel("esc")
        badge.setObjectName("keyHint")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFixedHeight(24)
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
        self.footer=ActionFooter()
        self.status=self.footer.context
        self.status.setText('Приложения · файлы · команды')
        self.open_action=self.footer.add_action('Открыть',('↵',),self.activate)
        self.footer.add_action('Действия',('Ctrl','K'),self.show_actions)
        root.addWidget(self.footer)
        self.height_animation=QVariantAnimation(self)
        self.height_animation.setDuration(180)
        self.height_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.height_animation.valueChanged.connect(lambda v:self.resize(self.width(),round(v)))
        self.backdrop_applied=False
        self._height_target=122

    def apply_brand_theme(self):
        c=resolved_palette(self.owner.settings)
        self.setStyleSheet(f"""
            QWidget {{background:transparent;color:{c['text']};font-family:'Golos Text';}}
            QLineEdit {{background:transparent;color:{c['text']};border:0;padding:0;font-size:21px;selection-background-color:{c['selection']};}}
            QLabel#escape,QLabel#searchStatus,QLabel#searchKeys {{color:{c['muted']};font-size:11px;}}
            QLabel#keyHint {{background:{c['raised']};border:1px solid {c['line']};border-radius:4px;padding:2px 5px;font-size:11px;color:{c['muted']};}}
            QLabel#secondary {{color:{c['muted']};font-size:11px;}}
            QFrame#actionFooter {{border:0;border-top:1px solid {c['line']};}}
            QPushButton#hintAction {{background:transparent;border:0;border-radius:5px;}}
            QPushButton#hintAction:hover,QPushButton#hintAction:focus {{background:{c['selection']};}}
            QMenu {{background:{c['raised']};color:{c['text']};border:1px solid {c['line']};border-radius:8px;padding:6px;font-size:13px;}}
            QMenu::item {{padding:8px 16px;border-radius:4px;}}
            QMenu::item:selected {{background:{c['selection']};}}
            QListWidget {{background:transparent;border:0;outline:0;padding:6px 0;}}
        """)

    def update_presentation(self):
        count=min(7,self.results.count())
        self.results.setVisible(bool(count))
        available=self.owner.screen().availableGeometry()
        height=max(122,min(available.height()-100,134+sum(80 if self.results.item(i).data(Qt.ItemDataRole.UserRole+1) else 52 for i in range(count))))
        if height==self._height_target:
            return
        self._height_target=height
        self.height_animation.stop()
        if self.isVisible() and self.owner.settings.get("hub_animations"):
            self.height_animation.setStartValue(float(self.height()))
            self.height_animation.setEndValue(float(height))
            self.height_animation.start()
        else:
            self.resize(min(720,available.width()-40),height)

    def shape(self):
        path=QPainterPath()
        path.addRoundedRect(QRectF(self.rect()),12,12)
        return path

    def paintEvent(self,event):
        p=QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path=self.shape()
        c=resolved_palette(self.owner.settings)
        color=QColor(c['surface'])
        color.setAlpha(210 if self.backdrop_applied else 255)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.fillPath(path,color)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        p.setPen(QPen(QColor(c['line']),1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(self.rect()).adjusted(.5,.5,-.5,-.5),12,12)
        if self.results.isVisible():
            p.setPen(QPen(QColor(c['line']),1))
            p.drawLine(1,78,self.width()-1,78)

    def showEvent(self,event):
        self.apply_brand_theme()
        super().showEvent(event)
        from .native_material import apply_acrylic
        self.backdrop_applied=apply_acrylic(self,light=resolved_palette(self.owner.settings)['bg']!='#161616',enabled=bool(self.owner.settings.get('search_glass')))
        self.clip_surface()

    def clip_surface(self):
        if self.backdrop_applied:self.setMask(QRegion(self.shape().toFillPolygon().toPolygon()))
        else:self.clearMask()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'backdrop_applied'):self.clip_surface()
