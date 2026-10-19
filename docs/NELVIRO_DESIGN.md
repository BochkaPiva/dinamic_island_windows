# Nelviro interface

The original continuous N mark and Glacier/Graphite palette come from the
approved Nelviro brandbook v1.0. Brand assets live in `island/assets/brand`;
`island/brand.py` is the shared desktop color source. Golos Text remains the
bundled, licensed font. The installer and running application use the same ICO.

## Interface rules

- One quiet application title; no Pro labels, promotional hero or permanent load counters.
- Two columns of actionable modules. The island, groups and search have previews;
  focus uses the existing editable timer and its real remaining-time ring.
- Use existing models. Never create a second audio capture, file index or timer
  just to animate a preview. Audio repaint requests are coalesced to 30 fps and
  cancelled when the preview page hides. No synthetic equalizer activity.
- All settings remain reachable through navigation and setting search. Existing
  keyboard activation, animation preference and native timer editing remain available.
- Dark and light palettes share semantic roles. Floating search uses one rounded
  translucent surface, with an opaque option. Native blur is not claimed: the
  existing Windows layered-window fallback intentionally disables DWM material
  because it draws an unwanted rectangular backplate.
- Small preview widths show media only rather than squeezing seven calendar dates.

## Compatibility boundary

Nelviro is the visible product name. Keep the legacy `CloudIsland.exe`, installer
AppId, `%LOCALAPPDATA%/Cloud Island`, autostart registry value, IPC identity,
DPAPI context and subscription installation ID. Renaming these is a separate
data migration, not a visual change. This update does not change the Telegram
service, permissions or membership policy.

## Validation

Run `python -m unittest discover -s tests -q` in the desktop environment and
`packaging/build.ps1` for the packaged self-test, license collection and bundle
audit. Visually inspect the module screen in dark/light modes at 1120 px and
the minimum 900 px width, plus search and desktop groups. Use the update helper
for an installation test so rollback and data snapshots remain active.

## Layout and island update (0.9)

Section headers carry live or explanatory previews. Secondary controls use
collapsible sections; settings pages share inertial wheel scrolling and native
pixel touchpad input. The Windows/HONOR page is removed. Community navigation
is prominent and the comparison shows only implemented capabilities.

The free notch remains available. Channel members can choose a floating shape
and gap. A saved floating choice is retained when access expires, but the
renderer safely uses the free notch. No group data is removed.

Visibility has a separate, reversible opacity/position timeline. Foreground,
move/size-end, minimize-end and foreground-location WinEvents trigger state
checks. Location events are coalesced, and a polling fallback remains. Runtime
services stop in fullscreen; expanded content is not collapsed halfway through
its exit. Interrupted timelines preserve their current rendered fraction.

Window placement is an explicit action against a chosen local HWND/PID, with
monitor work-area/DPI, minimum-size checks and post-placement size verification.
It does not install global snap/keyboard hooks or replace the separate optional
PowerToys Shift-drag behavior. Windows with larger minimum sizes cannot fit a
narrow zone; elevated/nonresponsive windows may reject placement.

Validation: 175 desktop tests, three native fixture placements (halves, thirds,
60/40), four registered/unregistered native event hooks, packaged Qt/WinRT
self-test and bundle audit. Dark/light pages were rendered and inspected. An
attempted live fullscreen fixture could not obtain foreground under Windows'
focus policy; real browser Alt-Tab is not claimed as manually verified. Reversal,
hide/show and reduced-motion behavior are covered by GUI tests.

The final 0.9.1 packaging isolates window-placement Win32 function signatures
in a private DLL interface. A real-API regression test now opens the window
catalog before invoking cursor/fullscreen geometry, covering shared ctypes
signature conflicts that separate mocked tests missed in 0.9.0.
