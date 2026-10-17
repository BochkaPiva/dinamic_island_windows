# Cloud Hub 0.4 · desktop tools

The previous UI had two concrete problems: nested outlines and gradients made
the launcher look like an inset control, while constant full-width group headers
spent most of their width on empty space. The groups also disappeared and were
shown again on a foreground poll, introducing latency and native Windows fly-in
animations. Visual styling alone could not solve that behavior.

## References and decisions

- [Raycast for Windows](https://www.raycast.com/windows): use a direct search field,
  consistent result density, recognizable icons and secondary metadata. Our
  implementation and vector icons are original; no Raycast assets or code.
- [Fluent layout](https://fluent2.microsoft.design/layout): use a coherent spacing
  grid instead of accumulating unrelated margins. The palette has one surface,
  one input, one results region and a quiet keyboard footer.
- [Microsoft Acrylic](https://learn.microsoft.com/windows/apps/design/style/acrylic):
  avoid multiple material layers. Its rendering also carries a power cost. The
  current Qt renderer uses simple translucency, with an opaque option, and no
  runtime screen capture or simulated live blur.
- [Fences roll-up behavior](https://www.stardock.com/blog/508751/fences-4--a-guided-tour):
  retain a clear compact header with content available on hover. This is an
  interaction reference; no dependency on Fences, file migration or shell patch.

## Shared visual values

| Role | Value |
| --- | --- |
| Surface | `#202227`, one tint |
| Primary text | `#f4f4f6` |
| Secondary text | `#989ca6` |
| Typeface | Bundled Golos Text, OFL |
| Search input / result / metadata | 18 / 14 / 11 logical px |
| Group header / icon label | 15 / 11 logical px |
| Corners | 10 px compact groups, 14 px open surfaces |
| Search footprint | 600×96 px empty; up to six 54 px rows |
| Group header footprint | 216–264 px, limited by configured expanded width |
| Motion | Critically damped, same geometry for width and reveal, no idle animation |

## Native behavior and verification

Groups use documented [top-level window ownership](https://learn.microsoft.com/windows/win32/api/winuser/nf-winuser-setwindowlongptrw)
and [window ordering](https://learn.microsoft.com/windows/win32/api/winuser/nf-winuser-setwindowpos).
Only our HWNDs are modified. Owning them by the shell keeps them above the
desktop; placing them at the bottom leaves ordinary applications above them.
They are already composed when an application minimizes. The two-second clock
checks shell recovery, not foreground visibility. Destroyed native windows can
be recreated from the retained Qt widget/data after the shell owner changes.

Windows transitions are disabled per tile with `DWMWA_TRANSITIONS_FORCEDISABLED`;
Peek exclusion remains per window. No global animation setting is changed.

`DWMSBT_TRANSIENTWINDOW` returned success but painted a rectangular native plate
behind the alpha-enabled Qt palette on the tested Windows 11 system. It is now
explicitly removed, together with DWM's extra border. Our single alpha surface
supplies smooth corners. This is translucency, not a claim of native Acrylic.

`tools/check_surfaces.py` verifies our own real windows: ordering under an
ordinary app, visibility before another poll after minimize, stable coordinates,
menu order, destruction/recovery of an owned surface and native composition over
an isolated backing window. It creates screenshots of actual UI. It does not
control or capture other applications. `tools/check_motion_groups.py` retains
reveal/reversal tests; unit tests cover ownership arguments, no foreground-driven
show/hide, clipping, appearance and existing data/keyboard behavior.
