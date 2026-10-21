import faulthandler
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from island.failure_log import failure_logging


class FailureLogTests(unittest.TestCase):
    def test_callback_exception_is_recorded_and_hook_restored(self):
        with tempfile.TemporaryDirectory() as temp:
            old = Mock()
            with patch.object(sys, 'excepthook', old):
                with failure_logging(temp):
                    try:
                        raise ValueError('callback fixture')
                    except ValueError:
                        sys.excepthook(*sys.exc_info())
                self.assertIs(sys.excepthook, old)
            old.assert_called_once()
            text = (Path(temp)/'crash.log').read_text(encoding='utf-8')
            self.assertIn('callback fixture', text)
            self.assertIn('pid=', text)

    def test_application_exception_is_logged_and_still_propagates(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(RuntimeError, 'startup fixture'):
                with failure_logging(temp):
                    raise RuntimeError('startup fixture')
            self.assertIn('startup fixture', (Path(temp)/'crash.log').read_text(encoding='utf-8'))

    def test_native_handler_stream_stays_open_until_exit(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(faulthandler, 'is_enabled', return_value=False), \
                 patch.object(faulthandler, 'enable') as enable, \
                 patch.object(faulthandler, 'disable') as disable:
                with failure_logging(temp):
                    stream = enable.call_args.kwargs['file']
                    self.assertFalse(stream.closed)
                self.assertTrue(stream.closed)
                disable.assert_called_once()
            self.assertIn('clean exit', (Path(temp)/'native-crash.log').read_text(encoding='utf-8'))

    def test_unwritable_log_never_prevents_startup_or_masks_error(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(Path, 'open', side_effect=PermissionError('fixture')):
                with failure_logging(temp):
                    pass
                with self.assertRaisesRegex(RuntimeError, 'original'):
                    with failure_logging(temp):
                        raise RuntimeError('original')
