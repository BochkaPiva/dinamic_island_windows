# SPDX-License-Identifier: GPL-3.0-only
"""Windows entry point. Diagnostic modes never open the desktop widget."""
import argparse
import json
from pathlib import Path
import sys


def self_test(report, audio=False):
    from PyQt6.QtCore import QCoreApplication, QTimer
    from island.audio import AudioSpectrum
    from island import __version__
    from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager
    app = QCoreApplication([])
    result = {"version": __version__, "qt": True, "winrt": True, "frozen": bool(getattr(sys, "frozen", False))}
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", metavar="REPORT")
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
        from PyQt6.QtCore import QCoreApplication
        from island.instance import query_status
        app=QCoreApplication([])
        result=query_status()
        Path(args.diagnostics).write_text(json.dumps(result,indent=2),encoding="utf-8")
        return 0 if result.get("running") else 1
    if args.self_test or args.audio_self_test:
        return self_test(args.self_test or args.audio_self_test, bool(args.audio_self_test))
    if args.quit:
        from PyQt6.QtCore import QCoreApplication
        from island.instance import notify_existing
        app = QCoreApplication([])
        notify_existing("quit")
        return 0
    from island.app import run
    from island.storage import data_dir
    import traceback
    def failure(kind, value, trace):
        with (data_dir()/"crash.log").open("a", encoding="utf-8") as stream:
            traceback.print_exception(kind, value, trace, file=stream)
        sys.__excepthook__(kind, value, trace)
    sys.excepthook = failure
    return run(background=args.background, island=args.island, updated=args.updated)


if __name__ == "__main__":
    sys.exit(main())
