"""Start a real isolated process, activate it, then verify graceful shutdown."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from PyQt6.QtCore import QCoreApplication
from island.instance import notify_existing, query_status
app = QCoreApplication([])
with tempfile.TemporaryDirectory() as folder:
    os.environ["CLOUD_ISLAND_DATA_DIR"] = folder
    store = Path(folder)
    (store/"settings.json").write_text(json.dumps({"updates": False}), encoding="utf-8")
    note = "IPC test: сохранить заметку при обновлении"
    (store/"notch-notes.txt").write_text(note, encoding="utf-8")
    process = subprocess.Popen([sys.executable, str(root/"main.py"),"--background"], cwd=root,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        ready = False
        for _ in range(30):
            if query_status().get("running"):
                ready = True
                break
            if process.poll() is not None:
                raise RuntimeError("App exited before creating its local command server")
            time.sleep(.1)
        assert ready, "Local command server did not appear"
        status=query_status()
        assert status["running"] and "spectrum_levels" in status
        assert not status["hub_visible"]
        assert "title" not in status and "path" not in status
        second = subprocess.run([sys.executable, str(root/"main.py"),"--background"], cwd=root,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        assert second.returncode == 0 and process.poll() is None
        assert not query_status()["hub_visible"], "A repeated login/background launch opened settings"
        assert notify_existing("hub") and query_status()["hub_visible"]
        start = time.monotonic()
        assert notify_existing("quit"), "Shutdown was not acknowledged"
        assert process.wait(timeout=15) == 0
        assert (store/"notch-notes.txt").read_text(encoding="utf-8") == note
        assert not (store/"crash.log").exists()
        print(json.dumps({"single_instance": True,"background_launch_idempotent":True,"graceful_quit": True,
                          "notes_preserved": True, "shutdown_seconds": round(time.monotonic()-start, 3)}))
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
