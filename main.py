# SPDX-License-Identifier: GPL-3.0-only
"""Windows entry point. Diagnostic modes never open the desktop widget."""
import argparse
import json
from pathlib import Path
import sys


def self_test(report, audio=False):
    from PySide6.QtCore import QCoreApplication, QTimer
    from island.audio import AudioSpectrum
    from island import __version__
    from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager
    app = QCoreApplication([])
    from PySide6.QtMultimedia import QMediaPlayer,QVideoSink,QCamera
    player=QMediaPlayer();sink=QVideoSink();player.setVideoSink(sink)
    if not player.isAvailable(): raise RuntimeError('Qt multimedia backend unavailable')
    from PySide6.QtCore import qVersion
    import PySide6
    from island.build_config import DISTRIBUTION
    result = {"version": __version__, "qt": True, "winrt": True, "frozen": bool(getattr(sys, "frozen", False)),
              "binding": "PySide6", "binding_version": PySide6.__version__, "qt_version": qVersion(),
              "distribution": DISTRIBUTION,"multimedia":True}
    if audio:
        capture = AudioSpectrum()
        available, levels = [], []
        capture.availability_changed.connect(available.append)
        capture.levels_changed.connect(levels.append)
        capture.start()
        QTimer.singleShot(3500, app.quit)
        app.exec()
        capture.stop()
        capture.wait(10000)
        result.update(loopback=any(available), updates=len(levels),
                      peak=max((max(frame) for frame in levels), default=0), microphone=False, pcm_saved=False)
    Path(report).write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0 if not audio or result["loopback"] else 2


def material_self_test(report):
    from PySide6.QtWidgets import QApplication,QWidget
    from winrt.windows.ui.composition import Compositor
    from winrt.windows.ui.composition.interop import create_desktop_window_target
    from winrt.windows.system.interop import create_dispatcher_queue_controller
    from winrt.windows.system import DispatcherQueue
    from winrt.windows.foundation.numerics import Vector2
    from island.glass_backend import GlassBackdrop
    app=QApplication([]);owner=QWidget();backend=None
    result={'composition_imports':True,'native_available':False,'window_shown':False,'data_accessed':False}
    try:
        backend=GlassBackdrop(owner);result['native_available']=True
    except (OSError,RuntimeError):pass
    finally:
        if backend:backend.close()
        owner.close();app.processEvents()
    Path(report).write_text(json.dumps(result,indent=2),encoding='utf-8')
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", metavar="REPORT")
    parser.add_argument("--material-self-test", metavar="REPORT")
    parser.add_argument("--audio-self-test", metavar="REPORT")
    parser.add_argument("--diagnostics", metavar="REPORT", help="Read runtime state from the current same-user instance")
    parser.add_argument("--quit", action="store_true", help="Gracefully close the current user's running instance")
    parser.add_argument("--background", action="store_true", help="Start tray and enabled modules without opening Cloud Hub")
    parser.add_argument("--apply-update", metavar="MANIFEST", help=argparse.SUPPRESS)
    parser.add_argument("--updated", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--island", action="store_true", help="Open the island instead of Cloud Hub")
    args = parser.parse_args()
    if args.apply_update:
        from island.update_helper import apply_update
        return apply_update(args.apply_update)
    if args.diagnostics:
        from PySide6.QtCore import QCoreApplication
        from island.instance import query_status
        app=QCoreApplication([])
        result=query_status()
        Path(args.diagnostics).write_text(json.dumps(result,indent=2),encoding="utf-8")
        return 0 if result.get("running") else 1
    if args.material_self_test:return material_self_test(args.material_self_test)
    if args.self_test or args.audio_self_test:
        return self_test(args.self_test or args.audio_self_test, bool(args.audio_self_test))
    if args.quit:
        from PySide6.QtCore import QCoreApplication
        from island.instance import notify_existing
        app = QCoreApplication([])
        notify_existing("quit")
        return 0
    from island.storage import data_dir
    from island.failure_log import failure_logging
    with failure_logging(data_dir()):
        from island.app import run
        return run(background=args.background, island=args.island, updated=args.updated)


if __name__ == "__main__":
    sys.exit(main())
