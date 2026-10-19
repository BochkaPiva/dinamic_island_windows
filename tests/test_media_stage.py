# SPDX-License-Identifier: GPL-3.0-only
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
import struct
import tempfile
import time
import unittest
from unittest.mock import Mock,patch
from PySide6.QtCore import Qt,QPoint,QPointF,QRect,QBuffer,QIODevice
from PySide6.QtGui import QImage,QColor,QWheelEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from island.app import IslandWindow
from island.storage import Settings
from island.entitlements import Grant,PRO_FEATURES,PRO_LIMITS,COMMUNITY_BASE_FEATURES,FREE_LIMITS
from island.media import Snapshot
from island.media_stage import fit_to_screen


def video_fixture(path):
    """Small real Motion-JPEG AVI, no network, camera, encoder executable or audio."""
    def chunk(tag,data):return tag+struct.pack('<I',len(data))+data+(b'\0' if len(data)%2 else b'')
    def listing(tag,data):return chunk(b'LIST',tag+data)
    frames=[];width,height=160,90
    for i in range(30):
        image=QImage(width,height,QImage.Format.Format_RGB32);image.fill(QColor.fromHsv(i*10,170,210))
        buf=QBuffer();buf.open(QIODevice.OpenModeFlag.WriteOnly);image.save(buf,'JPEG');frames.append(bytes(buf.data()))
    largest=max(map(len,frames));fps=10
    avih=struct.pack('<14I',1000000//fps,largest*fps,0,16,len(frames),0,1,largest,width,height,0,0,0,0)
    strh=struct.pack('<4s4sIHHIIIIIIIIhhhh',b'vids',b'MJPG',0,0,0,0,1,fps,0,len(frames),largest,0xffffffff,0,0,0,width,height)
    strf=struct.pack('<IiiHH4sIiiII',40,width,height,1,24,b'MJPG',width*height*3,0,0,0,0)
    headers=listing(b'hdrl',chunk(b'avih',avih)+listing(b'strl',chunk(b'strh',strh)+chunk(b'strf',strf)))
    data=b'';index=b'';offset=4
    for frame in frames:
        packed=chunk(b'00dc',frame);index+=struct.pack('<4sIII',b'00dc',16,offset,len(frame));data+=packed;offset+=len(packed)
    body=b'AVI '+headers+listing(b'movi',data)+chunk(b'idx1',index)
    Path(path).write_bytes(b'RIFF'+struct.pack('<I',len(body))+body)


class MediaStageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.w=IslandWindow(Settings(self.temp.name),services=False)
        self.w._system_timer.stop();self.w._notch_pointer_timer.stop();self.w._notch_pointer.enabled=False
        self.w.show();self.stage=self.w.media_stage

    def supporter(self):self.w.access.grant=Grant('supporter',PRO_FEATURES,dict(PRO_LIMITS))

    def tearDown(self):
        self.w.cleanup()
        if self.w.control_center:self.w.control_center.hide();self.w.control_center.deleteLater()
        self.w.hide();self.w.deleteLater();QTest.qWait(15);self.temp.cleanup()

    def test_free_user_cannot_start_resource_or_pin(self):
        self.w.show_hub=Mock();self.w.control_center=Mock()
        with patch('island.media_stage.QFileDialog.getOpenFileName') as dialog:
            self.stage.choose_file();dialog.assert_not_called()
        self.assertFalse(self.stage.engaged);self.assertIsNone(self.stage.camera);self.assertIsNone(self.stage.player)
        self.w.activities.toggle_pin();self.assertFalse(self.w.activities.pinned)
        self.w.control_center=None

    def test_browser_action_uses_inline_guide_not_window_capture_or_a_menu(self):
        with patch('island.browser_video.existing_pip',return_value=None),patch.object(self.stage,'choose_window') as capture:
            self.stage.browser_video()
            hub=self.w.notch_hub
            self.assertIs(hub.stack.currentWidget(),hub.browser_page)
            self.assertTrue(self.w._island_expanded)
            self.assertFalse(self.stage.engaged)
            capture.assert_not_called()
            # Changing audio sources has no ownership of the browser PiP.
            self.w.snapshot=Snapshot(aumid='Telegram',title='Voice message',status='Playing')
            self.stage.check_source()
            self.assertFalse(self.stage.engaged)

    def test_existing_browser_pip_is_activated_without_creating_a_duplicate_player(self):
        window=object()
        with patch('island.browser_video.existing_pip',return_value=window),patch('island.browser_video.activate',return_value=True) as activate:
            self.stage.browser_video()
            activate.assert_called_once_with(window)
            self.assertFalse(self.stage.engaged)
            self.assertIsNone(self.stage.player)

    def test_dragged_media_returns_continuously_in_same_native_window(self):
        self.supporter();w=self.w;native=int(w.winId());home=QRect(w.geometry())
        self.stage.begin('file','Fixture');QTest.qWait(420)
        self.assertEqual(self.stage.state,'active')
        target=fit_to_screen(QRect(w.x()+130,w.y()+180,w.width(),w.height()),w.screen())
        w.setGeometry(target);start=QRect(w.geometry())
        self.stage.close_media()
        self.assertEqual(w.geometry(),start)  # no instant placement at home
        QTest.qWait(120);middle=QRect(w.geometry())
        self.assertNotEqual(middle,start);self.assertNotEqual(middle,home)
        self.assertEqual(int(w.winId()),native)
        QTest.qWait(500)
        self.assertEqual(self.stage.state,'idle');self.assertEqual(w.geometry(),home)
        self.assertFalse(self.stage.panel.isVisible());self.assertTrue(w._notch_stage.surface.isVisible())

    def test_close_interrupts_entering_animation_without_jump(self):
        self.supporter();self.stage.begin('file','Fixture');QTest.qWait(90)
        before=QRect(self.w.geometry());self.stage.close_media()
        self.assertEqual(self.w.geometry(),before);QTest.qWait(600)
        self.assertEqual(self.stage.state,'idle');self.assertFalse(self.stage.animation.state().value)

    def test_fullscreen_does_not_move_explicit_media_but_pause_closes_it(self):
        self.supporter();self.w.settings.set('hub_animations',False);self.stage.begin('file','Fixture')
        moved=QRect(self.w.geometry()).translated(20,100);self.w.setGeometry(moved)
        with patch('island.app.is_fullscreen',return_value=True):self.w._sync_visibility()
        self.assertEqual(self.w.geometry(),moved);self.assertTrue(self.w.isVisible())
        self.w._hidden_by_user=True;self.w._sync_visibility()
        self.assertFalse(self.stage.engaged);self.assertFalse(self.w.isVisible())

    def test_expiry_releases_camera_and_preserves_groups(self):
        self.supporter();self.w.settings.set('hub_animations',False);before=self.w.modules.desktop.store.path.read_bytes()
        self.stage.begin('camera','Fixture');camera=Mock();capture=Mock();self.stage.camera=camera;self.stage.capture=capture
        self.w.access.grant=Grant('free',COMMUNITY_BASE_FEATURES,dict(FREE_LIMITS));self.w.access.changed.emit()
        camera.stop.assert_called_once();capture.setCamera.assert_called_with(None)
        self.assertFalse(self.stage.engaged);self.assertEqual(before,self.w.modules.desktop.store.path.read_bytes())

    def test_unlinked_window_never_controls_a_media_session(self):
        self.supporter();self.w.settings.set('hub_animations',False);self.stage.begin('window','Fixture')
        thumbnail=Mock();thumbnail.valid.return_value=True;thumbnail.minimized.return_value=False
        self.stage.thumbnail=thumbnail
        self.w._handle_snapshot(Snapshot(has_session=True,aumid='browser',status='Paused'))
        self.stage.check_source();self.assertTrue(self.stage.engaged)
        thumbnail.valid.return_value=False;self.stage.check_source();self.assertFalse(self.stage.engaged)
        thumbnail.close.assert_called_once()

    def test_linked_window_observes_its_own_session_not_selected_music(self):
        self.supporter();self.w.settings.set('hub_animations',False);self.stage.begin('window','Fixture')
        thumbnail=Mock();thumbnail.valid.return_value=True;thumbnail.minimized.return_value=False
        self.stage.thumbnail=thumbnail;self.stage.source_session='video';self.stage.source_was_playing=True
        self.w._handle_snapshot(Snapshot(has_session=True,aumid='music',status='Playing',sources=('music','video'),source_states=(('music','Playing'),('video','Paused'))))
        self.stage.check_source();self.assertFalse(self.stage.engaged);thumbnail.close.assert_called_once()

    def test_real_video_decodes_and_pause_returns_then_can_resume(self):
        self.supporter();self.w.settings.set('hub_animations',False)
        path=Path(self.temp.name)/'fixture.avi';video_fixture(path)
        self.assertTrue(self.stage.open_file(path));self.stage.audio_output.setMuted(True)
        for _ in range(40):
            QTest.qWait(50)
            if not self.stage.canvas.image.isNull():break
        self.assertFalse(self.stage.canvas.image.isNull(),'Qt multimedia must actually decode frames')
        self.assertGreater(self.stage.player.duration(),0)
        self.stage.pause();QTest.qWait(30)
        self.assertEqual(self.stage.state,'idle');self.assertFalse(self.stage.player.source().isEmpty())
        self.stage.resume();QTest.qWait(100);self.assertEqual(self.stage.state,'active')
        self.stage.close_media();self.assertTrue(self.stage.player.source().isEmpty())

    def test_activity_swipe_does_not_control_playback_or_volume(self):
        self.w._handle_snapshot(Snapshot(has_session=True,title='Fixture',aumid='app',sources=('app',)))
        self.w.worker.command=Mock();a=self.w.activities
        self.assertEqual(a.current(),'media');a.step(1);self.assertEqual(a.current(),'clock')
        self.w.worker.command.assert_not_called()
        event=QWheelEvent(QPointF(10,10),QPointF(10,10),QPoint(),QPoint(0,120),Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier,Qt.ScrollPhase.NoScrollPhase,False)
        self.assertFalse(a.eventFilter(self.w,event));self.assertEqual(a.current(),'clock')

    def test_pin_is_removed_when_its_activity_disappears(self):
        self.supporter();a=self.w.activities
        self.w._handle_snapshot(Snapshot(has_session=True,title='Fixture'));a.toggle_pin();self.assertTrue(a.pinned)
        self.w._handle_snapshot(Snapshot());self.assertEqual(a.current(),'clock');self.assertFalse(a.pinned)

    def test_source_list_refresh_does_not_overwrite_saved_choice(self):
        self.w._select_source('chosen')
        self.w._handle_snapshot(Snapshot(has_session=True,aumid='chosen',sources=('other','chosen')))
        self.assertEqual(self.w.worker.preferred_source,'chosen');self.assertEqual(self.w.settings.get('source'),'chosen')

    def test_preview_is_clamped_to_work_area(self):
        rect=fit_to_screen(QRect(-10000,-10000,10000,10000),self.w.screen())
        self.assertTrue(self.w.screen().availableGeometry().contains(rect))

    def test_camera_stall_releases_device_and_returns(self):
        self.supporter();self.w.settings.set('hub_animations',False);self.stage.begin('camera','Fixture')
        camera=Mock();camera.isActive.return_value=False
        self.stage.camera=camera;self.stage.capture=Mock();self.stage.started_at=time.monotonic()-11
        self.stage.check_source();camera.stop.assert_called_once();self.assertFalse(self.stage.engaged)

    def test_media_input_is_not_made_transparent_by_pointer_controller(self):
        self.supporter();self.w.settings.set('hub_animations',False);self.stage.begin('file','Fixture')
        self.w._notch_pointer.enabled=True
        with patch('island.motion.set_mouse_passthrough',side_effect=lambda h,v:v):
            self.w._notch_pointer.route_input(True);self.w._notch_pointer.tick()
            self.assertFalse(self.w._notch_pointer.passthrough)

    def test_display_change_during_entry_does_not_leave_tiny_player(self):
        self.supporter();self.stage.begin('file','Fixture');QTest.qWait(50)
        self.stage.screens_changed();QTest.qWait(320)
        self.assertEqual(self.stage.state,'active');self.assertEqual(self.w.width(),480)

    def test_horizontal_wheel_switches_once_and_leaves_transport_untouched(self):
        self.w._handle_snapshot(Snapshot(has_session=True,title='Fixture'))
        self.w.worker.command=Mock();a=self.w.activities
        event=QWheelEvent(QPointF(10,10),QPointF(10,10),QPoint(-80,0),QPoint(),Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier,Qt.ScrollPhase.ScrollUpdate,False)
        for _ in range(10):self.assertTrue(a.eventFilter(self.w,event))
        self.assertEqual(a.current(),'clock');self.w.worker.command.assert_not_called()
