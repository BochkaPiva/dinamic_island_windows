# SPDX-License-Identifier: GPL-3.0-only
"""One island HWND: docked → movable media → animated return. Lazy resources."""
from pathlib import Path
import time
from PySide6.QtCore import (Qt,QObject,QRect,QRectF,QPoint,QUrl,QTimer,QVariantAnimation,
    QEasingCurve,QCameraPermission)
from PySide6.QtGui import QColor,QPainter,QPainterPath,QDesktopServices,QImage
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QPushButton,QLabel,QSlider,
    QFileDialog,QDialog,QListWidget,QComboBox,QDialogButtonBox,QApplication,QLineEdit)


def fit_to_screen(rect,screen):
    bounds=screen.availableGeometry()
    width=min(rect.width(),bounds.width());height=min(rect.height(),bounds.height())
    return QRect(max(bounds.left(),min(rect.x(),bounds.right()-width+1)),
        max(bounds.top(),min(rect.y(),bounds.bottom()-height+1)),width,height)


class VideoCanvas(QWidget):
    """Keep only the last frame; QVideoSink's owning backend supplies pacing."""
    def __init__(self,parent):
        super().__init__(parent);self.image=QImage();self.message='';self.mirror=False
        self.setMinimumHeight(80)

    def frame(self,frame):
        image=frame.toImage()
        if not image.isNull():
            if image.width()>1280 or image.height()>720:image=image.scaled(1280,720,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.FastTransformation)
            self.image=image;self.message='';self.update()

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if not self.image.isNull():
            size=self.image.size().scaled(self.size(),Qt.AspectRatioMode.KeepAspectRatio)
            rect=QRect((self.width()-size.width())//2,(self.height()-size.height())//2,size.width(),size.height())
            if self.mirror:p.translate(self.width(),0);p.scale(-1,1)
            p.drawImage(rect,self.image)
        if self.message:
            p.resetTransform();p.fillRect(self.rect(),QColor('#101216'))
            p.setPen(QColor('#AFB7C3'))
            p.drawText(QRectF(self.rect()).adjusted(18,8,-18,-8),Qt.AlignmentFlag.AlignCenter|Qt.TextFlag.TextWordWrap,self.message)


class DragHeader(QWidget):
    def __init__(self,controller):
        super().__init__();self.controller=controller;self.offset=None
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.setToolTip('Перетащи, чтобы переместить. Esc — вернуть остров наверх.')

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and self.controller.state=='active':
            self.offset=event.globalPosition().toPoint()-self.controller.owner.pos();event.accept()

    def mouseMoveEvent(self,event):
        if self.offset is None:return
        point=event.globalPosition().toPoint()
        screen=QApplication.screenAt(point) or self.controller.owner.screen()
        target=QRect(point-self.offset,self.controller.owner.size())
        self.controller.owner.setGeometry(fit_to_screen(target,screen))
        self.controller.refresh_thumbnail()

    def mouseReleaseEvent(self,event):self.offset=None


class MediaMorph(QWidget):
    def __init__(self,stage):
        super().__init__(stage.owner.card);self.stage=stage;self.texture=None
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents);self.hide()

    def capture(self):self.texture=self.stage.panel.grab()

    def paintEvent(self,event):
        if self.texture is None:return
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setClipPath(self.stage.owner.card.notch_path())
        p.setOpacity(min(1,max(0,(self.height()-38)/64)))
        p.drawPixmap(self.rect(),self.texture)


class MediaStage(QObject):
    def __init__(self,owner):
        super().__init__(owner)
        self.owner=owner;self.state='idle';self.kind=None;self.player=None;self.camera=None
        self.capture=None;self.sink=None;self.player_sink=None;self.audio_output=None;self.thumbnail=None
        self.source_session='';self.source_was_playing=False;self.generation=0
        self.started_at=0.;self.camera_was_active=False
        self.missing_since=None
        self.frame_clock=QTimer(self);self.frame_clock.setInterval(34)
        self.frame_clock.timeout.connect(self.show_latest_frame)
        self.animation=QVariantAnimation(self);self.animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.animation.valueChanged.connect(self.frame);self.animation.finished.connect(self.finished)
        self.monitor=QTimer(self);self.monitor.setInterval(500);self.monitor.timeout.connect(self.check_source)
        self.panel=QWidget(owner.card);self.panel.setObjectName('mediaStage')
        self.panel.setStyleSheet('''QWidget#mediaStage {background:transparent;color:#F5F6F8;}
            QLabel {color:#AFB7C3;background:transparent;} QPushButton {color:#F5F6F8;background:#20252C;border:0;border-radius:8px;padding:5px 10px;}
            QPushButton:hover {background:#343C47;} QSlider::groove:horizontal {height:3px;background:#343C47;}
            QSlider::sub-page:horizontal {background:#B4DFF2;} QSlider::handle:horizontal {width:9px;margin:-3px 0;background:#F5F6F8;border-radius:4px;}''')
        root=QVBoxLayout(self.panel);root.setContentsMargins(14,8,14,12);root.setSpacing(7)
        self.header=DragHeader(self);bar=QHBoxLayout(self.header);bar.setContentsMargins(8,0,0,0)
        self.header.setFixedHeight(30)
        self.title=QLabel('Видео');self.title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        bar.addWidget(self.title,1)
        self.output_button=self.button('♫','Источник и устройство звука',self.audio_menu)
        self.output_button.setFixedSize(30,28)
        bar.addWidget(self.output_button)
        close=self.button('×','Закрыть и вернуть остров наверх',self.close_media);close.setFixedSize(30,28);bar.addWidget(close)
        root.addWidget(self.header)
        self.alarm_bar=QWidget();alarm_row=QHBoxLayout(self.alarm_bar);alarm_row.setContentsMargins(8,0,0,0)
        alarm_row.addWidget(QLabel('Таймер завершён'),1)
        alarm_row.addWidget(self.button('Остановить сигнал','Остановить сигнал таймера',owner.notch_hub.alarm.dismiss))
        self.alarm_bar.hide();root.addWidget(self.alarm_bar)
        owner.notch_hub.alarm.changed.connect(lambda:self.alarm_bar.setVisible(owner.notch_hub.alarm.active))
        self.canvas=VideoCanvas(self.panel);root.addWidget(self.canvas,1)
        self.seek=QSlider(Qt.Orientation.Horizontal);self.seek.setRange(0,1000)
        self.seek.sliderReleased.connect(self.seek_to);root.addWidget(self.seek)
        self.controls=QWidget();controls=QHBoxLayout(self.controls);controls.setContentsMargins(0,0,0,0)
        self.play_button=self.button('Пауза','Пауза и возврат острова наверх',self.pause)
        controls.addWidget(self.play_button)
        self.resume_button=self.button('К источнику','Открыть исходное окно',self.activate_source)
        controls.addWidget(self.resume_button)
        self.time_label=QLabel('');controls.addWidget(self.time_label,1)
        self.volume=QSlider(Qt.Orientation.Horizontal);self.volume.setRange(0,100);self.volume.setValue(60)
        self.volume.setFixedWidth(80);self.volume.setToolTip('Громкость этого видео')
        self.volume.valueChanged.connect(lambda value:self.audio_output.setVolume(value/100) if self.audio_output else None)
        controls.addWidget(self.volume);root.addWidget(self.controls)
        self.panel.hide()
        self.morph=MediaMorph(self)
        owner.access.changed.connect(self.access_changed)

    @property
    def engaged(self):return self.state!='idle'

    def button(self,text,tip,callback):
        from .style import font
        b=QPushButton(text);b.setFont(font(10));b.setToolTip(tip);b.setAccessibleName(tip);b.clicked.connect(callback);return b

    def allowed(self,feature):
        if self.owner.access.feature(feature).allowed:
            if self.owner._policy.island:return True
            self.owner.show_hub();self.owner.control_center._message('Сначала включи остров или выбери профиль «Работа».');return False
        self.owner.show_hub();self.owner.control_center.navigate('account');return False

    def access_changed(self):
        if self.engaged and not self.owner.access.feature('island.mirror' if self.kind=='camera' else 'island.video').allowed:self.close_media()

    def choose_file(self):
        if not self.allowed('island.video'):return
        self.owner._island_auto_timer.stop()
        filename,_=QFileDialog.getOpenFileName(self.owner,'Открыть видео',filter='Видео (*.mp4 *.mkv *.webm *.mov *.avi);;Все файлы (*)')
        if filename:self.open_file(filename)

    def ensure_player(self):
        if self.player:return
        from PySide6.QtMultimedia import QMediaPlayer,QAudioOutput,QVideoSink
        self.player=QMediaPlayer(self);self.audio_output=QAudioOutput(self);self.audio_output.setVolume(self.volume.value()/100)
        self.player.setAudioOutput(self.audio_output);self.sink=QVideoSink(self)
        self.player_sink=self.sink;self.player.setVideoSink(self.player_sink)
        self.player.positionChanged.connect(self.position_changed)
        self.player.playbackStateChanged.connect(self.playback_changed)
        self.player.mediaStatusChanged.connect(self.status_changed)
        self.player.errorOccurred.connect(lambda *_:self.failure('Не удалось воспроизвести файл. Проверь формат и доступ к файлу.') if self.kind=='file' and self.state in ('entering','active') else None)

    def show_latest_frame(self):
        # Pull the native sink's newest frame at most 30 times/sec. Connecting
        # every decoder signal queues frames; Python callbacks on its native
        # thread can deadlock pause/stop. Neither is needed for a preview.
        sink=self.player_sink if self.kind=='file' else self.sink
        if sink and self.state in ('entering','active'):
            frame=sink.videoFrame()
            if frame.isValid():self.canvas.frame(frame)

    def open_file(self,filename):
        if not self.allowed('island.video'):return False
        if not Path(filename).is_file():self.owner.notice('Видеофайл не найден');return False
        self.release_resources(clear_player=True)
        self.ensure_player();self.canvas.image=QImage();self.canvas.mirror=False
        self.canvas.message='Открываем видео…';self.begin('file',Path(filename).name)
        self.player.setSource(QUrl.fromLocalFile(str(Path(filename).resolve())));self.player.play();return True

    def resume(self):
        if not self.allowed('island.video') or not self.player or self.player.source().isEmpty():return
        self.canvas.message='';self.begin('file',Path(self.player.source().toLocalFile()).name);self.player.play()

    def pause(self):
        if self.kind=='file' and self.player:
            self.player.pause()  # state signal starts the return; retain file/position for Resume
        elif self.kind=='window' and self.source_session:
            snap=self.owner.snapshot
            if snap.aumid==self.source_session and snap.can_pause:self.owner.worker.command(self.source_session,'play_pause')
            self.close_media()

    def playback_changed(self,state):
        from PySide6.QtMultimedia import QMediaPlayer
        if self.kind=='file' and self.state in ('active','entering') and state==QMediaPlayer.PlaybackState.PausedState:self.return_home()

    def status_changed(self,status):
        from PySide6.QtMultimedia import QMediaPlayer
        if self.kind=='file' and status==QMediaPlayer.MediaStatus.EndOfMedia:self.close_media()

    def seek_to(self):
        if self.player and self.kind=='file':self.player.setPosition(round(self.player.duration()*self.seek.value()/1000))

    def position_changed(self,value):
        if not self.player or self.kind!='file':return
        duration=self.player.duration()
        if not self.seek.isSliderDown():self.seek.setValue(round(1000*value/max(1,duration)))
        from .hub import fmt
        self.time_label.setText(f'{fmt(value/1000)} / {fmt(duration/1000)}')

    def choose_window(self):
        if not self.allowed('island.video'):return
        from .window_layouts import list_windows
        windows=list_windows();dialog=QDialog(self.owner);dialog.setWindowTitle('Показать окно в острове');dialog.resize(500,400)
        from .hub_ui import stylesheet
        from .brand import palette
        dialog.setStyleSheet(stylesheet(getattr(self.owner.control_center,'colors',palette())))
        layout=QVBoxLayout(dialog)
        hint=QLabel('Выбери окно. Свёрнутые окна могут приостанавливать превью; защищённое видео может быть недоступно.');hint.setWordWrap(True);layout.addWidget(hint)
        search=QLineEdit();search.setPlaceholderText('Найти окно…');search.setClearButtonEnabled(True);layout.addWidget(search)
        listing=QListWidget();listing.addItems([w.title for w in windows]);layout.addWidget(listing,1)
        def filter_windows(value):
            for i,window in enumerate(windows):listing.item(i).setHidden(value.casefold() not in window.title.casefold())
            listing.setCurrentRow(-1)
        search.textChanged.connect(filter_windows)
        sources=QComboBox();sources.addItem('Без управления плеером','')
        for source in self.owner.snapshot.sources:sources.addItem(self.owner._notch_source_name(source),source)
        sources.setToolTip('Связывай с плеером только если он воспроизводит выбранное окно')
        layout.addWidget(QLabel('Связать с медиаплеером (необязательно)'));layout.addWidget(sources)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        listing.currentRowChanged.connect(lambda i:buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(i>=0))
        buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons)
        if dialog.exec()==QDialog.DialogCode.Accepted:self.open_window(windows[listing.currentRow()],sources.currentData())

    def open_window(self,window,source=''):
        if not self.allowed('island.video'):return False
        from .window_preview import Thumbnail
        self.release_resources(clear_player=True);self.canvas.image=QImage();self.canvas.message='';self.canvas.mirror=False
        self.begin('window',window.title)
        try:self.thumbnail=Thumbnail(int(self.owner.winId()),window)
        except OSError as exc:self.failure(str(exc));return False
        self.source_session=source
        state=dict(self.owner.snapshot.source_states).get(source)
        self.source_was_playing=state=='Playing' or self.owner.snapshot.aumid==source and self.owner.snapshot.status=='Playing'
        self.missing_since=None
        self.monitor.start();self.check_source();return True

    def choose_camera(self):
        if not self.allowed('island.mirror'):return
        app=QApplication.instance();permission=QCameraPermission()
        status=app.checkPermission(permission)
        if status==Qt.PermissionStatus.Denied:
            self.owner.notice('Разреши доступ к камере в настройках Windows')
            QDesktopServices.openUrl(QUrl('ms-settings:privacy-webcam'));return
        self.generation+=1;generation=self.generation
        if status==Qt.PermissionStatus.Undetermined:
            app.requestPermission(permission,self,lambda p:self.open_camera() if generation==self.generation and p.status()==Qt.PermissionStatus.Granted else None)
        else:self.open_camera()

    def open_camera(self,device=None):
        if not self.allowed('island.mirror'):return False
        from PySide6.QtMultimedia import QMediaDevices,QCamera,QMediaCaptureSession,QVideoSink
        devices=QMediaDevices.videoInputs()
        if not devices:self.owner.notice('Камера не найдена');return False
        if device is None and len(devices)>1:
            from PySide6.QtWidgets import QInputDialog
            name,ok=QInputDialog.getItem(self.owner,'Камера','Выбери устройство',[d.description() for d in devices],0,False)
            if not ok:return False
            device=devices[[d.description() for d in devices].index(name)]
        device=device or devices[0]
        self.release_resources(clear_player=True);self.canvas.image=QImage();self.canvas.mirror=True;self.canvas.message='Включаем камеру…'
        self.begin('camera','Зеркало · камера включена')
        self.capture=QMediaCaptureSession(self);self.camera=QCamera(device,self)
        formats=[f for f in device.videoFormats() if f.resolution().width()<=1280 and f.resolution().height()<=720 and 24<=f.maxFrameRate()<=30]
        if formats:self.camera.setCameraFormat(max(formats,key=lambda f:f.resolution().width()*f.resolution().height()))
        self.camera.errorOccurred.connect(lambda *_:self.failure('Камера недоступна. Возможно, она занята другим приложением или запрещена в Windows.') if self.kind=='camera' and self.state in ('entering','active') else None)
        self.sink=QVideoSink(self)
        self.capture.setVideoSink(self.sink);self.capture.setCamera(self.camera);self.camera.start();return True

    def audio_menu(self):
        from PySide6.QtWidgets import QMenu
        from PySide6.QtGui import QCursor
        from PySide6.QtMultimedia import QMediaDevices
        menu=QMenu(self.owner)
        menu.setStyleSheet('''QMenu {background:#111114;color:#eeeef2;border:1px solid #29292f;border-radius:12px;padding:6px;}
            QMenu::item {padding:9px 16px;border-radius:7px;} QMenu::item:selected {background:#25252c;}
            QMenu::separator {height:1px;background:#29292f;margin:5px 10px;}''')
        menu.addSection('Медиаприложения')
        menu.addAction('Автоматический выбор',lambda:self.owner._select_source(''))
        for source in self.owner.snapshot.sources:
            a=menu.addAction(self.owner._notch_source_name(source));a.setCheckable(True);a.setChecked(source==self.owner.snapshot.aumid)
            a.triggered.connect(lambda _,s=source:self.owner._select_source(s))
        if self.kind=='file' and self.audio_output:
            menu.addSection('Звук этого видео')
            for device in QMediaDevices.audioOutputs():
                a=menu.addAction(device.description());a.setCheckable(True);a.setChecked(device.id()==self.audio_output.device().id())
                a.triggered.connect(lambda _,d=device:self.audio_output.setDevice(d))
        menu.addSeparator();menu.addAction('Устройства и громкость Windows ↗',lambda:QDesktopServices.openUrl(QUrl('ms-settings:sound')))
        menu.exec(QCursor.pos())

    def begin(self,kind,title):
        w=self.owner;self.generation+=1;self.kind=kind
        self.started_at=time.monotonic();self.camera_was_active=False
        if kind in ('file','camera'):self.frame_clock.start()
        self.monitor.start()
        self.animation.stop();w._geometry.stop();w._island_auto_timer.stop();w._notch_hover_timer.stop()
        pointer=w._notch_pointer
        pointer.spring.value=pointer.spring.velocity=0.;pointer.edge_since=None;pointer.edge_blocked=False
        w.activities.press=None
        w._visibility.animation.stop();w._visibility.fraction=1.;w._visibility.desired=True
        w._notch_pointer.route_input(False);w.card.set_retreat(0,.5);w._notch_stage.retreat=0
        w._island_expanded=False;w._fs_hidden=False
        self.full_title=title;self.title.setText(title);self.title.setMaximumWidth(280);self.title.setToolTip(title)
        self.seek.setVisible(kind=='file');self.volume.setVisible(kind=='file')
        self.play_button.setVisible(kind=='file');self.resume_button.setVisible(kind=='window')
        self.time_label.setText('Камера работает только пока открыто зеркало' if kind=='camera' else '')
        self.canvas.setMinimumHeight(1)
        self.state='entering';w.clearMask()
        self.panel.setGeometry(0,0,480,320);self.panel.ensurePolished();self.panel.layout().activate()
        self.morph.capture();self.layout()
        screen=QApplication.screenAt(w.geometry().center()) or w.screen()
        target=QRect(w.x()+(w.width()-480)//2,w.y(),480,320)
        self.animate(fit_to_screen(target,screen),360)
        w.show();w.setWindowOpacity(w.settings.get('island_opacity')/100)

    def animate(self,target,duration):
        self.animation.stop();self.start_rect=QRect(self.owner.geometry());self.target_rect=QRect(target)
        self.animation.blockSignals(True);self.animation.setDuration(duration)
        self.animation.setStartValue(0.);self.animation.setEndValue(1.);self.animation.setCurrentTime(0);self.animation.blockSignals(False)
        if not self.owner.settings.get('hub_animations'):self.frame(1.);self.finished()
        else:self.animation.start()

    def frame(self,value):
        t=float(value);a,b=self.start_rect,self.target_rect
        self.owner.setGeometry(QRect(*[round(x+(y-x)*t) for x,y in zip((a.x(),a.y(),a.width(),a.height()),(b.x(),b.y(),b.width(),b.height()))]))
        self.layout()

    def finished(self):
        if self.state=='returning':
            if self.thumbnail:self.thumbnail.close();self.thumbnail=None
            self.state='idle';self.panel.hide();self.morph.hide();self.kind=None
            self.owner._notch_stage._signature=None;self.owner._notch_stage.sync()
            self.owner._place();self.owner._sync_visibility();self.owner._update_services()
        elif self.state=='entering':self.state='active';self.layout()

    def layout(self):
        if not self.engaged:return
        stage=self.owner._notch_stage
        stage.surface.hide();stage.reveal.hide();self.owner.notch_hub.hide()
        if self.state=='active':
            self.morph.hide();self.panel.setGeometry(self.owner.card.rect());self.panel.show();self.panel.raise_();self.panel.layout().activate()
        else:
            self.panel.hide();self.morph.setGeometry(self.owner.card.rect());self.morph.show();self.morph.raise_();self.morph.update()
        self.title.setText(self.title.fontMetrics().elidedText(self.full_title,Qt.TextElideMode.ElideRight,max(40,self.panel.width()-120)))
        self.refresh_thumbnail()

    def refresh_thumbnail(self):
        if not self.thumbnail:return
        local=self.canvas.mapTo(self.owner,QPoint())
        dpr=self.owner.devicePixelRatioF()
        sx=self.owner.width()/self.panel.width();sy=self.owner.height()/self.panel.height()
        rect=tuple(round(value*dpr) for value in (local.x()*sx,local.y()*sy,self.canvas.width()*sx,self.canvas.height()*sy))
        try:self.thumbnail.update(rect,opacity=round(255*min(1,max(0,(self.owner.height()-38)/64))),visible=self.owner.height()>65 and not self.thumbnail.minimized())
        except OSError:self.failure('Предпросмотр недоступен')

    def check_source(self):
        if self.state not in ('active','entering'):return
        if self.kind=='camera' and self.camera:
            active=self.camera.isActive()
            if active:self.camera_was_active=True
            if (self.camera_was_active and not active) or (time.monotonic()-self.started_at>10 and (not active or self.canvas.image.isNull())):
                self.failure('Камера перестала передавать изображение. Проверь устройство и разрешения Windows.')
            return
        if self.kind=='file' and self.player:
            if time.monotonic()-self.started_at>10 and self.canvas.image.isNull():self.failure('Видеодорожка недоступна. Попробуй другой файл.')
            return
        if not self.thumbnail:return
        if not self.thumbnail.valid():self.close_media();return
        minimized=self.thumbnail.minimized()
        self.canvas.message='Окно свёрнуто. Открой источник, чтобы продолжить.' if minimized else ''
        self.canvas.update();self.refresh_thumbnail()
        snap=self.owner.snapshot
        if self.source_session:
            status=dict(snap.source_states).get(self.source_session)
            if status is None and snap.aumid==self.source_session:status=snap.status
            if status=='Playing':self.source_was_playing=True
            elif self.source_was_playing and status in ('Paused','Stopped'):self.close_media()
            if self.source_session and self.source_session not in snap.sources:
                self.missing_since=self.missing_since or time.monotonic()
                if time.monotonic()-self.missing_since>2:self.close_media()
            else:self.missing_since=None

    def activate_source(self):
        if self.thumbnail:self.thumbnail.activate()

    def release_resources(self,clear_player=False):
        self.frame_clock.stop()
        self.monitor.stop()
        if self.thumbnail:self.thumbnail.close();self.thumbnail=None
        self.source_session='';self.source_was_playing=False
        if self.camera:
            self.camera.stop()
            self.capture.setCamera(None);self.capture.setVideoSink(None)
            self.camera.deleteLater();self.capture.deleteLater();self.camera=self.capture=None
            if self.sink:self.sink.deleteLater();self.sink=None
        if self.player:
            self.player.blockSignals(True);self.player.pause()
            if clear_player:self.player.stop();self.player.setSource(QUrl())
            self.player.blockSignals(False)

    def return_home(self):
        if not self.engaged or self.state=='returning':return
        self.header.offset=None
        self.monitor.stop()
        self.frame_clock.stop()
        self.morph.capture();self.state='returning';self.generation+=1
        w=self.owner;screen=next((s for s in QApplication.screens() if s.name()==w.settings.get('monitor')),QApplication.primaryScreen())
        width,height=w._scale_window_size(50)
        target=QRect(screen.geometry().x()+(screen.geometry().width()-width)//2,screen.geometry().top()+(w.settings.get('island_gap') if w.floating_mode() else 0),width,height)
        self.animate(target,520)

    def close_media(self):
        # Keep a DWM relationship through the half-second return, then release
        # it at the destination. Camera and decoder stop immediately.
        thumbnail=self.thumbnail;self.thumbnail=None
        self.release_resources(clear_player=True);self.thumbnail=thumbnail
        self.return_home()

    def failure(self,message):
        self.release_resources(clear_player=True);self.canvas.message=message;self.canvas.update()
        self.owner.notice(message)
        if self.engaged:self.return_home()

    def screens_changed(self):
        if self.state=='returning':self.state='active';self.return_home()
        elif self.engaged:
            screen=QApplication.screenAt(self.owner.geometry().center()) or QApplication.primaryScreen()
            if self.state=='entering':self.animate(fit_to_screen(QRect(self.owner.pos(),self.target_rect.size()),screen),240)
            else:self.owner.setGeometry(fit_to_screen(self.owner.geometry(),screen));self.layout()

    def close(self):
        self.generation+=1;self.animation.stop();self.release_resources(clear_player=True);self.state='idle';self.panel.hide();self.morph.hide()
