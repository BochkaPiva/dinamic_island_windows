# Cloud Hub modules

Cloud Hub is a local Qt application. `IslandWindow` owns the process lifecycle,
tray, preferences and power/profile policy. Closing the settings window hides it;
explicit Exit performs cleanup and flushes notes.

`modules.py` defines immutable `ModuleSpec` entries for the module catalog and
`ModuleRuntime` for native module lifecycle. A new native service implements
`set_enabled(bool)` and `shutdown()`; its coordinator derives effective state from
saved user preferences plus the current profile. Disabling a service must stop
its timers and close its resources, without overwriting user preferences.
The island's existing media/audio threads use their own blocking enabled events.

`settings_pages.py` provides the settings page registry and factories. Page IDs
are stable navigation targets, independent of their order. The window shell and
PowerToys adapter remain separate from page construction. Settings have strict
types and numeric ranges in `storage.py`; writes replace a temporary file and
update in-memory state only after success. Unknown fields are not executable
plugins; this release supports built-in modules only.

## Boundaries

- `search.py`: on-demand app catalog and asynchronous Windows Search SQL. No
  private disk index, content indexing, telemetry or command evaluation. Queries
  use sanitized filename tokens. PowerShell receives encoded constant scripts,
  never raw query text. An executor has at most two workers and one pending latest
  indexed request. Query generations prevent late results replacing current ones.
  Shell application identifiers come from Windows `Get-StartApps`; launching
  requires an explicit selection, with separate process arguments and no shell.
- `desktop_groups.py`: versioned `desktop-groups.json` contains group IDs,
  titles, references and normalized monitor positions. Independent tool windows
  appear only in desktop/group context; no Explorer injection, shell replacement
  or movement/deletion of the user's original files. One 300 ms visibility timer
  runs only while the module is enabled; animations run only during interaction.
- `notebook.py`: named notes in versioned `notes.json`. The quick note shares
  the island document and preserves `notch-notes.txt`. Debounced atomic saves and
  flush-on-close prevent losing a last edit. An unreadable store is copied to a
  recovery file before replacement.
- `hub.py`: compact overview and persistent island pages. The calendar is a
  seven-day local date strip, not an account calendar. Qt animation runs on
  interaction only. The timer uses a monotonic deadline; it is not persisted
  across full application exits. The file shelf contains references, not copies.
- `timer.py`: editable/wheel-adjustable readouts share the Hub's monotonic timer.
  Completion uses an original generated WAV with asynchronous WinMM playback,
  bounded repetition and an explicit dismiss action. The waveform generator is
  in `tools/generate_timer_chime.py`; no recorded audio is bundled.
- `search_ui.py`: search appearance is separate from providers. Result delegates
  paint selected text explicitly, elide paths, and never need horizontal scrolling.
  Windows 11 backdrop attributes are best effort; layered-window composition and
  Windows transparency settings may affect the material. Vector tint/highlights
  remain available without desktop capture or animation running in the background.
- `hotkey.py`: native `RegisterHotKey`, no keyboard hooks. A candidate binding
  must register before the old ID is released. Failed changes retain the old key.
- `integrations.py`: optional PowerToys bridge. Complete configuration snapshots,
  verified graceful host exit, exact native-field retention and restore-on-exit
  protect unrelated utilities. Only the connected module flags are managed.

## Checks

Run `python -m unittest discover -s tests -v` for domain and Qt regressions.
`tools/check_instance.py` checks a real isolated process and graceful IPC exit.
`tools/check_native.py` checks own-window click-through, edge dwell, rendering,
volume event routing, desktop recovery and DWM Peek exclusion.
`tools/check_hub.py` checks real WASAPI/media suspension and profiles.
`tools/check_audio_timer.py` checks compact battery capture, direct/wheel timer
entry and actual alarm playback/dismissal with an isolated window. It plays one
short chime to verify output, without modifying system volume.
`tools/check_workspace.py` captures all settings pages and exercises new native
flows with isolated data. It queries the existing Windows Search index read-only.
Native UI checks should run sequentially because they intentionally change focus
between their own fixture windows. Physical touchpad/mouse testing remains useful
for driver-specific behavior; simulated input isn't a substitute for all hardware.
