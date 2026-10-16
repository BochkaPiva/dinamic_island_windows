# Changelog

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
