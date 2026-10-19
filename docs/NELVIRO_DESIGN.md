# Nelviro interface · 0.11

## Approved direction

The latest user clarification takes precedence over Brandbook v1.0's Glacier UI
accent: settings, search and desktop groups use neutral black/gray surfaces and
selection, visually guided by the supplied Raycast screenshots. Preserve the
original N identity and licensed Golos Text. Do not copy Raycast assets or code.
Reference: https://manual.raycast.com/settings .

`island/brand.py` owns semantic colors. Dark: background #161616, sidebar #1C1C1C,
settings sections #242424, raised controls #303030, selection #343434, text #F2F2F2.
The light palette is neutral too. No blue/teal selection, gradients, glow or fake blur. The original logo may retain
its color. The later shortcut-sheet reference adds real acrylic on transient
panels and the settings chrome; reading surfaces stay opaque.

## Composition

- A quiet, thin title bar. Integrated sidebar with 36 px navigation rows; a separate
  Parameters group for shortcuts, application, updates and community.
- The sidebar folds to icons. Every icon retains a tooltip and accessible name.
  Ctrl+F unfolds it and focuses settings search. Page IDs remain stable.
- The shell names the current section once. Descriptions are short and subordinate.
- Modules form one compact catalog, with a single selected inspector. Only the
  selected preview is visible; no grid of simultaneously animated cards.
- Settings group related rows on one charcoal surface. Label left, control right.
  Additional settings use the common disclosure. No cards nested in cards.
- Useful previews use real existing models. Do not invent illustrations for ordinary
  application settings, hotkeys, notes or window management. The group editor comes
  before its optional preview. Focus keeps its editable, live timer.
- Community shows real connection status, one primary action, a literal feature
  comparison and one selectable form preview. Keep its widget tree persistent on
  controller/access notifications; never rebuild the UI on each refresh.

## Components and tokens

Reuse `hub_ui.py`: Navigation/NavDelegate, CatalogRow, ToggleSwitch,
SettingsSection, WindowHeader, ContentTransition, icon and stylesheet.
shortcut_ui.py provides ShortcutButton, ShortcutCapture and ShortcutDialog.
SettingsPages
card/number and ControlCenter._module build consistent groups and setting rows.
Use existing vector glyphs from ui_tokens.py; no emoji or new icon package.

Body text 13 px, supporting text 11–12 px, group title 14 px, page title 19 px.
Rows ~56 px for a two-line catalog; 36 px navigation. Settings/controls use 6–8 px
radii. Use 4/8 px spacing increments; no giant promotional hero.
`brand.MOTION`: response 120 ms, toggle 180 ms, groups 320 ms, island 380 ms.
Respect hub_animations; do not poll a second media source to animate a preview.
No hidden preview clocks or permanent decorative motion.

## Compatibility

Keep CloudIsland.exe, installer AppId, Cloud Island data/autostart/IPC identities,
DPAPI context, installation binding, stored keys/data formats and Telegram protocol.
The membership model remains free plus channel-member capabilities, without payment.
The video feature is local files and camera, not a promised browser video stream.
Search has one optionally translucent rounded surface; native blur is not claimed.

## Verification and maintenance

Run desktop unittest discovery, `tools/check_hub_design.py`, and
`tools/check_raycast_ui.py OUTPUT` in fresh Windows processes at actual DPR 1/1.5/2.
Inspect every page in dark/light at logical widths 900/1120, keyboard actions,
empty/long text, reduced motion and hidden timers. A scale factor multiplies Windows
native scale: record devicePixelRatioF, not only QT_SCALE_FACTOR.
Run packaging/build.ps1 for packaged self-test and dependency/license audit.
The complete function/access map and verification limits are in
[NELVIRO_RAYCAST_UI.md](NELVIRO_RAYCAST_UI.md).
New pages must reuse these components. Do not reintroduce blue selection, giant
preview grids, decorative headers or duplicate labels as features are added.

## Shortcut interaction and materials

The latest cropped Raycast reference is a behavior reference too: clicking a
keycap opens a 474 px floating recorder, with large separate keys and a quiet
footer containing the action, Save/Return and Cancel/Escape. No row of native
text input + Apply + Manual + Disable buttons. Advanced manual/disable actions
remain in the row menu. Validation and conflicts stay inside the sheet.
Suspend only Nelviro's registered hotkeys while capturing; restore them on cancel,
close or deactivation. Restore before atomic rebind so existing conflict/rollback
logic remains authoritative. Support Cyrillic layouts via native virtual letter keys.

native_material.py isolates the optional Windows 11 composition accent API in a
private WinDLL. It is undocumented and may be unavailable: the interface must work
with a fully opaque fallback. Respect Windows transparency and high-contrast
preferences. Native blur is used, never captured pixels/blurred wallpaper assets.
Main content is opaque; only title/sidebar chrome and the shortcut sheet expose
the material. Rounded native masks clip the accent to the actual window contour.
A positive DWM HRESULT alone is insufficient proof: the layered-window transient
backdrop was visually opaque in the checker/band fixture and is not used.
Inspect the composed native sheet over an owned fixture, because QWidget.grab()
does not include compositor blur. tools/check_shortcut_ui.py checks cancel, save,
duplicate preservation and records native composition. The opaque fallback is
covered by offscreen GUI tests; no global keyboard hook is installed.
