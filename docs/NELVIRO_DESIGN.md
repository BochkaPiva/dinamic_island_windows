# Nelviro settings · 0.11.2

## Brief

The user rejected the preceding recoloring/catalog passes. The new baseline is the
supplied Raycast Settings screenshots: quiet neutral surfaces, readable grouped rows,
clear hierarchy, and direct navigation. Persistent explanation paragraphs, repeated
labels, broad action bars and expanding piles of controls are removed.

Preserve the N mark and Golos Text; stay in Python/PySide6/Qt Widgets. Frontend Design
(Anthropic) and UI UX Pro Max are advisory. Their web-stack defaults do not apply.
The reference and the user's explicit black/gray direction take priority.

## Tokens and composition

- Background #111111; sidebar #202020; group #1C1C1C; raised #303030;
  text #F2F2F2; secondary #A6A6A6. Light mode uses the neutral LIGHT palette.
- Golos Text: 15 px body/navigation, 20 px section title, 14 px group title,
  12–13 px subordinate status. No tracked uppercase eyebrows.
- Sidebar 218 px, collapsible to 54 px; 42 px navigation rows. Content has a
  shared header with history, help, launch action and the module master switch.
- Related controls share one rounded surface, with subtle internal separators.
  A setting is normally one 52 px row: name left, control right.
- No permanent help paragraph under each label. Tooltips and the header information
  action explain settings on demand. Keep actionable error, pairing, download and
  recovery instructions visible when that state actually needs them.
- A detail screen is a task, not another simultaneous column. Back/Escape returns
  to the parent; forward restores the previous detail. No destruction/recreation
  of forms when navigating.

```
[sidebar]  [back / forward] Section              [help] [launch] [on]
           Group
           ┌─────────────────────────────────────────────┐
           │ Name                                control │
           │ Next task                         summary › │
           └─────────────────────────────────────────────┘
```

## Navigation and scenarios

Keep the 11 stable root page IDs. There are 9 detail screens:
Island: size/opacity, behavior, sound, content, video/camera;
Desktop: group appearance; Windows: workspaces and drag zones;
Application: PowerToys. Each detail has a persistent body in one shared scroll viewport.

Settings search indexes actual parameter names and help, not only section labels.
An exact page name/alias wins; a parameter match opens its containing detail, scrolls
to its control and focuses it. Ctrl+F, Ctrl+K, Alt+Left/Right and Escape remain available.
History includes detail routes and replaces its forward branch on new navigation.
The active sidebar item returns to its root. Home now has six interactive tiles:
island, groups, search, focus, notes and windows. These use the actual shared models;
no independent audio/video service or idle animation is added. The visible home
focus readout updates once per second, regardless of which tile is hovered.
Shortcuts and Updates keep stable root IDs but are entered through Application or
settings search, reducing the sidebar. Bottom Ctrl+F / Ctrl+K hints remain visible.
Island forms are direct buttons beside a live preview, rather than a hidden menu.

Groups: select an ID-bound record, edit its name in place, add/drop files. The `…`
menu contains Rename, Show on desktop and Delete. No duplicate title/name/Save rows.
Appearance is a separate screen. Existing collection/save/restore semantics stay intact.

Focus: ring and timer aligned; presets in a wrapping grid, start/reset alongside; completion settings are a second group on the same screen.
Files and notes: two clear tabs, compact actions, persistent local models.
Community: connection state/action and a short real comparison. Preserve its widget
objects across controller notifications; never rebuild the panel on refresh.

## Native material and implementation

`brand.py` owns colors, `hub_ui.py` the shell and shared controls.
`settings_navigation.py` provides SettingsLink, SettingsSubpage, SettingsSurface and
SettingsCombo. `settings_pages.py` composes screens; ControlCenter routes them.
Use the existing glyph system; no emoji or borrowed Raycast assets.

Optional native acrylic is used for chrome/transient surfaces with opaque fallback,
Windows transparency/high contrast respected, and rounded native masks. Product
backgrounds never use screenshots. Text editors remain opaque. Native
composition captures must be made over owned fixtures; QWidget.grab omits DWM blur.
The shared glass surfaces sample the app-owned neutral light field and displace its
pixels in a narrow 12 px edge band. Their centers and child controls remain sharp.
The optical images cache by geometry/theme/DPR, not a free-running animation timer;
the full-window light-field cache holds at most two images. Edge maps reuse their
geometry when scrolling. Only the broad backdrop samples use logical resolution;
rims and labels remain at native DPR. The owned-window CPU scroll check measured
about 16 ms median / 18 ms p95 at DPR 2 (not a compositor FPS measurement). This is internal scene
refraction, not refraction of external windows. Windows acrylic itself only blurs.
No wallpaper/screenshot background, desktop capture or browser shader dependency.
Use palette lightness to select dark/light material, never a hardcoded background equality.

Motion follows brand.MOTION and hub_animations. Hidden previews and scroll timers stop.
Forms retain controls/drafts; settings keep atomic persistence and validation. Never
change installation identities, data formats, membership protocol or access limits for design.

## Checks

Run desktop tests, tools/check_raycast_ui.py (root AND detail screens), native group
management and launcher/shortcut checks. Test dark/light, widths 900/1120, actual
DPR 1/1.5/2, long titles, search routing, back/forward and reduced motion. Complete
packaging/build.ps1 including packaged self-test and dependency/license audit.
See NELVIRO_RAYCAST_UI.md for the preservation map, actual captures and results.


### Оформление острова · 0.12
Чёрный материал бесплатный и стандартный. Подписчики выбирают стекло и оттенок
в разделе «Остров». Цветовой круг, яркость, RGB и HEX синхронизированы; до
«Применить» меняется только предпросмотр. Потеря доступа не стирает настройки.
Стекло острова — альфа-прозрачность, тёмная читаемая сердцевина и световая кромка.
Системный Acrylic не используется на острове: его прямоугольная область выходит
за форму. Внешнее размытие и преломление не заявляются. Это ограничение не
относится к существующему акрилу прямоугольных панелей настроек.
