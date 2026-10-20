# Nelviro — agent guidance

Nelviro is an existing Windows desktop application built with Python, PySide6,
and Qt Widgets. Read the current README and `island/brand.py` before UI work.
Keep the Nelviro N mark and Golos Text. Use the current neutral semantic palette
in brand.py and the latest approved direction below.

## UI UX Pro Max

The project-local skill is `.agents/skills/ui-ux-pro-max/SKILL.md`.
Use it as an advisory resource for composition, typography, interaction,
accessibility, and UX review. User instructions and project-specific constraints
take priority over the skill's general recommendations and defaults.

- Implement interfaces using the existing PySide6 / Qt Widgets architecture.
  A suggested web stack is not permission to migrate to React, Electron, or QML.
- Translate useful web/mobile guidance into appropriate Qt behavior and units;
  do not install web UI packages or change brand typography to match a search result.
- Preserve working features, settings, user data, Telegram access rules,
  executable/installer identities, and update/backup compatibility during UI work.
- Applying a skill is not itself authorization for a broader redesign, new
  backend, telemetry, or additional product features.

The skill is a local development tool, not an application runtime dependency.

## Approved desktop interface direction (0.11)
Read docs/NELVIRO_DESIGN.md and docs/NELVIRO_RAYCAST_UI.md before UI edits.
The latest user instruction replaces Glacier/teal UI accents with neutral black
and gray, guided visually by the three Raycast screenshots. Preserve the N mark
and Golos Text. Use brand.py semantic palette and hub_ui.py components; no colored
selection, promotional heroes, giant module grids or duplicate decorative previews.
Keep one active preview, keyboard access, dark/light and reduced-motion support.
The feature/access map is a preservation checklist; never drop functions/data or
change install identities/protocols for styling. Verify rendered Windows widgets
at actual DPR 1/1.5/2 and widths 900/1120, then run tests and packaged self-test.

The later shortcut-sheet reference explicitly requires a keycap recorder and real
material, not native text fields and rows of Apply buttons. Reuse shortcut_ui.py.
Use optional native acrylic for transient sheets/chrome with opaque fallback;
reading surfaces remain opaque. Respect Windows transparency/high contrast, clip
native material, and restore registered hotkeys on cancellation/deactivation.
Never fake blur with screenshots. Compare native composition, not only API return codes.

## Latest reference correction (0.11.1)
The user rejected permanent explanatory copy and the previous composition. Follow
current docs/NELVIRO_DESIGN.md: short task-oriented roots, separate persistent detail
screens, one-line setting rows, on-demand help, and search that opens actual parameters.
Do not restore broad button bars, duplicated title/name fields, technical paragraphs,
or piles of expanding settings. Use settings_navigation.py, preserve all control/data
and access contracts, and render root AND detail screens before declaring a design pass done.

## Latest user correction (0.11.2)
The user explicitly superseded the earlier one-preview/catalog rule: restore six
interactive home tiles and a glass material with visible edge refraction. Follow
current docs/NELVIRO_DESIGN.md. Keep shared live models, direct actions and neutral
colors. Native DWM acrylic blurs the external desktop; optics.py refracts only the
app-owned internal light field. Never call that external-desktop refraction, warp
labels, or capture the screen as a product backdrop. Preserve opaque fallback.

## Island material (0.12)
Classic black remains the default and free. Glass and color are separate member
capabilities; preserve saved appearance across expiry and render black until renewal.
Use island_material.py and color_ui.py. Rounded islands use per-pixel translucency
and softly shaded curved reflections; accent Acrylic is rectangular and must not be enabled on this
shape. Do not describe this as desktop refraction or blur. Respect system transparency
and high contrast with an opaque fallback. Keep shortcut/install/data identities.

## Frosted material correction (0.12.1)
The user rejected painted lighting as plastic. Do not restore fake specular spots,
white frames or the reflected_light implementation. glass_backend.py hosts a clipped
Windows Composition host backdrop in an input-transparent, nonactivating native
surface below the Qt content. No screen capture is allowed. Respect system policy;
use an opaque matte fallback where native host backdrop is unavailable. Color is
member-only and applies to BOTH solid and glass materials; solid uses exact RGB
and adaptive foreground contrast. Keep all backdrop lifecycle and focus tests.
