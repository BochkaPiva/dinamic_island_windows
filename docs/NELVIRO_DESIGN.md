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
