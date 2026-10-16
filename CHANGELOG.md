# Changelog

## v0.3.1

- Fix the apparent frozen equalizer on battery: Auto/Battery now retain real loopback capture in the compact island. Process at 20 Hz instead of 40 Hz while compact on battery; expose complete suspension as an explicit opt-in setting.
- Make the timer numbers directly editable and wheel-adjustable in the overview, Focus tab and control center. Accumulate precision-wheel deltas, validate 1–1440 minutes, preserve edits during ticks and support Enter/Escape.
- Add an original local timer chime, bounded repetition (3–30 seconds), a visible completion state, automatic Focus reveal and a Stop action. Respect hidden/fullscreen/Game contexts and stop audio on dismissal, reset or exit.
- Redesign search with a compact empty state, adaptive height, translucent rounded chrome, subtle highlights and custom high-contrast result painting. Elide long titles/paths and hide scrollbars while retaining scrolling and keyboard navigation.
- Request the documented Windows 11 transient backdrop where supported; retain a painted fallback and an appearance toggle. No background screen capture or shell injection.
- Add on-demand same-user runtime diagnostics (`--diagnostics REPORT`) without track titles, file paths or audio samples, plus regressions and a real loopback/alarm integration check.

## v0.3.0

- Rebuild Cloud Hub around ten separate settings pages, a module catalog and explicit start/stop lifecycles for native modules.
- Redesign the expanded island as a compact three-part overview: mini player and album cover on the left, seven-day calendar centered on today, focus timer on the right. Default expanded size is 560×170 logical pixels.
- Animate calendar wheel/touchpad navigation, horizontal dragging and return-to-today; keep it free of scrollbars. Animate tab changes without nesting Qt graphics effects.
- Add live compact/expanded dimensions, opacity, monitor selection, hover/collapse delays and optional overview blocks. Preserve centered geometry, cursor avoidance, real spectrum and Windows Peek recovery.
- Replace the PowerToys search dependency with a native keyboard launcher for Start Menu/Store applications, local commands, explicit paths and Windows-indexed filenames. Query only on demand off the UI thread; discard stale results and cancel pending obsolete requests.
- Make search, island and Hub hotkeys configurable. Reserve replacements before releasing working bindings; reject conflicts and duplicates. Defaults: Alt+Space, Ctrl+Alt+I and Ctrl+Alt+H.
- Add independent hover-expanding desktop groups with animated height, shortcut/file/folder links, filtering, icons, drag/drop, repositioning, locking and configurable appearance. Groups hide when ordinary applications have focus; originals remain untouched.
- Support any timer duration from 1 to 1440 minutes, pause/resume, reset and completion notification. Share the timer between Hub and island.
- Add named searchable notes alongside the existing shared quick note, automatic local saves, clipboard copy and text export. Improve the file shelf with explicit add/open/location/remove actions; retain unavailable links.
- Keep the island file shelf optional and off by default. Existing quick notes, file links, profiles and installation identity survive upgrades.
- Continue optional FancyZones/Workspaces integration; keep Command Palette disabled while Cloud Hub manages the connection and restore original module preferences on exit.
- Add regression tests and an isolated native workspace check for calendar gestures, custom timer, notes, groups and Windows Search.

## v0.2.1

- Preserve the exact native PowerToys configuration across DSC serialization and host restart. PowerToys 0.101's managed serializer renames the File Explorer enable key and can otherwise enable that unrelated module again.
- Back up the native configuration and atomically retain all unrelated fields while the verified PowerToys host is closed; change only the three connected module flags.
- Add a regression covering the File Explorer key mismatch and unknown future settings.

## v0.2.0

- Introduce Cloud Hub: a native control center for Cloud Island, profiles, module switches and Windows/HONOR shortcuts.
- Add Auto, Work, Battery and Game profiles plus a global pause. Individual module preferences survive profile changes.
- Auto selects Work on AC and Battery when unplugged. Battery opens WASAPI only while the island is expanded; Game/pause/disabled island stop capture and media polling.
- Add optional PowerToys integration for Command Palette, FancyZones and Workspaces through its DSC/CLI interfaces. Round-trip complete settings, preserve unrelated utilities, back up and restore the original three enable flags.
- Gracefully restart the verified PowerToys host when its module states change; 0.101 does not reload DSC enable flags live. Restore the original connection when Cloud Hub exits.
- Discover saved PowerToys workspaces and launch a selected local workspace; open the official editors to create layouts and application sets.
- Open Cloud Hub through the tray, desktop shortcut or Ctrl+Alt+H. Keep the existing installer identity, executable and local data location for upgrades.
- Stop hidden control-center refresh, suspend unused media/pointer clocks and avoid relaying out compact content for each FFT packet.
- Preserve natural scrolling, click-through wave, centered geometry, desktop recovery and Windows Peek exclusion.

## v0.1.4

- Exclude the island from Windows Peek fading when previewing another application's taskbar thumbnail.
- Apply the native DWM setting whenever the island is shown, including after restoring or recreating its window.
- Keep other applications' previews enabled and preserve intentional tray/full-screen hiding.
- Verify Windows accepts the DWM exclusion on a real overlay and after HWND recreation, alongside desktop recovery and focus preservation.

## v0.1.3

- Keep the island visible after activating the desktop or using Show Desktop.
- Recognize custom desktop child/owned windows through their shell ancestry; do not mistake desktop organizer surfaces for full-screen apps or browser tabs.
- Recover a lowered/minimized island above the desktop without activating it or changing its bounds.
- Preserve intentional tray hiding and hiding over real full-screen applications.
- Add desktop ancestry/visibility regression tests and a native restore/focus-preservation check.

## v0.1.2

- Fix volume direction for natural touchpad scrolling without reversing ordinary mouse wheels.
- Respect Qt's inversion flag and identify Windows Precision Touchpad wheel messages before Qt loses their device metadata.
- Accumulate high-resolution wheel/pixel packets, avoiding a volume key press for every tiny touchpad movement.
- Add an optional scroll-direction override for older drivers that do not identify their input source.
- Regression tests cover both devices, Windows scrolling preferences, Qt inversion, fine deltas and Windows volume key dispatch.

## v0.1.1

First public release of Cloud Island for Windows x64. Includes all v0.1.0 features below.

- Graceful same-user local shutdown before installer upgrades and uninstallation.
- Opening a second instance activates the existing panel.
- The v0.1.0 preview build was held back after the live upgrade test exposed a slow Windows Restart Manager shutdown.

## v0.1.0

First independent Cloud Island release for Windows x64.

- Centered, bezel-attached island with a soft, motion-dependent cursor wave.
- Native mouse passthrough over other applications; top-edge dwell opens the panel.
- Persistent content layers and smooth, cancellable geometry transitions.
- Real five-band WASAPI output spectrum with silence decay and output-device reconnect.
- Windows media sessions: artwork, source selection, transport and seeking where supported.
- Calendar, timer, local notes and file-reference shelf.
- Tray controls, monitor selection, fullscreen hiding and optional user-level autostart.
- Daily stable-release check against this repository; explicit download and installer upgrade.
- Per-user installer, portable EXE/ZIP, source ZIP and SHA-256 checksums.
- GPL-3.0-only source, dependency notices, pinned builds and Windows CI.
