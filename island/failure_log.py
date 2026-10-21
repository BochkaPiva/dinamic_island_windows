# SPDX-License-Identifier: GPL-3.0-only
"""Local crash evidence, including native faults that bypass sys.excepthook."""
from contextlib import contextmanager
from datetime import datetime, timezone
import faulthandler
import os
from pathlib import Path
import sys
import traceback
from . import __version__


@contextmanager
def failure_logging(directory):
    directory = Path(directory)
    previous = sys.excepthook
    native = None
    owned_handler = False

    def record(message, error=None):
        try:
            with (directory/'crash.log').open('a', encoding='utf-8') as stream:
                stream.write(f'\n{datetime.now(timezone.utc).isoformat()} Nelviro {__version__} pid={os.getpid()} {message}\n')
                if error:
                    traceback.print_exception(*error, file=stream)
        except OSError:
            pass  # Logging must never turn an unavailable data folder into a crash.

    def failure(kind, value, trace):
        record('Python exception', (kind, value, trace))
        previous(kind, value, trace)

    try:
        if not faulthandler.is_enabled():
            try:
                native = (directory/'native-crash.log').open('a', encoding='utf-8')
                native.write(f'\n{datetime.now(timezone.utc).isoformat()} Nelviro {__version__} pid={os.getpid()} started\n')
                native.flush()
                faulthandler.enable(file=native, all_threads=True)
                owned_handler = True
            except (OSError, RuntimeError):
                if native:
                    try:
                        native.close()
                    except OSError:
                        pass
                native = None
        sys.excepthook = failure
        try:
            yield
        except BaseException:
            record('Application exception', sys.exc_info())
            raise
        else:
            if native:
                try:
                    native.write(f'{datetime.now(timezone.utc).isoformat()} pid={os.getpid()} clean exit\n')
                    native.flush()
                except OSError:
                    pass
    finally:
        sys.excepthook = previous
        if owned_handler:
            faulthandler.disable()
        if native:
            try:
                native.close()
            except OSError:
                pass
