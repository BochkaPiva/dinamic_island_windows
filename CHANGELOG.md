## v0.10.2

- Исправлен выбор медиасессии: активное воспроизведение имеет приоритет перед старой текущей сессией Windows. Stopped и Closed больше не выдаются за Paused.
- Остановленная вкладка браузера с тем же ID не вытесняет играющую. Автовыбор не показывает давно забытые сессии на паузе.
- Ошибка чтения и отсутствие активного источника сбрасывают старую обложку и команды управления. Обложки без изменения названия перепроверяются.
- Если слышен системный звук без медиаданных, отображается «Звук Windows», без чужой обложки и недействующих кнопок.
- Убрана кнопка-инструкция «Видео поверх окон» и её неработающий сценарий. Автоматический вывод браузерного видеопотока внутри острова не реализован; локальные видео и камера остаются отдельно в настройках.

## v0.10.1

- Исправлена ошибка повторного обновления статуса Telegram: карточки больше не удаляются при проверке подписки.
- Постоянные живые предпросмотры, отдельный статус подключения и понятные действия в каждом состоянии.
- На странице объяснены бесплатные и расширенные возможности, офлайн-доступ и сохранность групп.
- Основная кнопка видео работает со встроенным PiP браузера: без захвата страницы, выбора окон и привязки к смене аудиоисточника. Включение PiP выполняется в самом браузере.
- Видеофайлы и камера перенесены в свёрнутый блок настроек; аудиоменю оформлено под чёрный остров.
- Добавлена проверка повторных уведомлений и полного локального цикла доступа: подтверждение, льготный период, ограничение, повторная подписка и отключение.


## v0.10.0

- Added a movable video state in the same island window: local file playback, explicit native window preview, and an opt-in camera mirror for channel subscribers. Drag the header; pause/close returns continuously to the selected screen's notch/island. Esc returns too.
- Snapshot-based content/geometry transitions, reversible entry/return, screen work-area clamping, device/source loss handling and capability expiry cleanup. Camera and decoding stop on close; DWM relationships release at the end of the short return.
- Video/camera frames are pulled from the native sink at a bounded 30 fps without Python callbacks on decoder threads or per-frame queued slots. The preview retains one image capped at 1280×720; no microphone, recording or upload.
- Swipe the compact island horizontally or use horizontal touchpad scrolling to select media, clock or a running/paused timer. Vertical scrolling retains volume control. Subscriber pinning retains a chosen activity; disappearing sources release the pin.
- Audio menu selects actual SMTC sessions; the local video player offers its own output-device selector. Global Windows audio configuration opens the native sound settings. Fixed source-list refresh overwriting a preferred session.
- Rebuilt community comparison using the shared resting silhouette and centered live spectrum; added concrete benefits, connected state and access explanation. Prominent cursor-avoidance toggle, calmer settings headers/type hierarchy, and an actionable empty file shelf.
- QtMultimedia is packaged with matched PySide6 Addons and external FFmpeg 7.1.5 libraries. Dependency notices/build flags are recorded; unrelated Qt modules remain excluded by the bundle audit.

## v0.9.3

- Floating avoidance morphs into an opaque six-pixel bezel tab instead of disappearing. The complete live artwork/spectrum texture travels upward inside the contracting silhouette.
- Hovering the visible tab opens controls; the physical top-edge gesture still works. Browser tabs below retain click-through input.
- Fullscreen visibility remains independent; avoidance does not cancel the fullscreen fade or move the native window onto another monitor.
- Added a staged media/activity proposal with explicit video capture limitations and acceptance criteria in docs/island-media-roadmap.md.

## v0.9.2

- Floating cursor avoidance now lifts and fades the intact capsule; artwork and spectrum move together without dents or strip warping.
- Screen-edge clipping prevents bleed onto a display above, and the native window remains associated with its selected monitor.
- Cursor retreat composes with fullscreen visibility rather than overriding its opacity. Global top-edge activation remains alive when the capsule is transparent.
- Holding the cursor on the physical top edge keeps the floating panel open instead of starting its collapse timer across the gap.

## v0.9.1

- Isolate window-placement Win32 prototypes from the island's APIs. Opening the window page no longer causes incompatible RECT/Monitor pointer errors in cursor/fullscreen checks.
- Added a regression check using the actual native APIs sequentially, rather than mocking their shared function signatures.

## v0.9.0

- Visual section headers, concise grouped settings and animated disclosures; removed Windows/HONOR page.
- Smooth settings scrolling; native touchpad pixel deltas preserved and reduced-motion preference respected.
- Floating island with adjustable gap for channel subscribers; free notch and saved data remain available on access expiry.
- Reversible opacity/position appearance for both forms. Foreground and foreground-geometry events replace waiting for the slow fullscreen poll; no premature content collapse during exit.
- Community capability comparison, prominent navigation and connected state show actual benefits.
- Direct native window placement in halves, thirds and 60/40 with size verification and minimum-size checks. PowerToys Shift zones and workspace sets remain separate optional tools.

## v0.8.0

- Nelviro identity: original N mark, Glacier accent, shared dark/light palette and calmer native controls.
- Two-column module overview with live cover/audio, saved groups, direct search and editable focus timer.
- Preview audio updates coalesced to 30 fps while visible; no additional capture service.
- Search and desktop groups follow the selected theme. Keyboard controls and reduced motion retained.
- Existing installation identity, updater protocol, Telegram pairing and user data paths preserved.

## v0.7.1

- Public Telegram service on Vercel with PostgreSQL on Neon Free; no Yandex login or payments.
- Public membership API embedded in Windows; public GitHub update channel restored.
- Preserve groups on read failure, retry loading, retain the last valid file before changes.
- Fixed a PostgreSQL table/index name collision in the original community migration.
- PostgreSQL tests now run, including concurrent ledger checks; added safe readiness endpoint.

# v0.7.0 (community preview)

- Free base: current island, search, local utilities and two active desktop groups.
- Telegram directly opens additional groups; no Yandex ID or checkout in the active flow.
- Background membership checks, offline allowance and safe downgrade without deleting groups.
- Community page and explicit selection of which saved groups are active.
- GPL v3 project licensing restored by owner request. Public service is not deployed yet.

# Changelog

## Unreleased — private account foundation

- Отдельный сервер Django/PostgreSQL, Яндекс ID через браузер и PKCE-клиент для Windows.
- Нативный аккаунт, устройства, история платежей, адаптер ЮKassa, журнал доступа,
  отмена продления, очередь повторов/сверки, возвраты и учёт задач на чеки НПД.
- Подписанные разрешения для установки и защищённые токены. Реальные сервисы не
  подключены; продажи выключены. Установленная версия 0.6.0 не заменяется этим коммитом.
- Инструкция подключения с нуля и частный CI PostgreSQL. Две проверки конкурентности
  требуют реального PostgreSQL; локальная SQLite их не подтверждает.

## v0.6.0

- Частная основа будущей коммерческой линии: Python и Qt сохранены, интерфейс переведён с PyQt6 на PySide6 Essentials 6.11.2. Существующие функции доступны в предварительной сборке.
- Чистое окружение с закреплёнными зависимостями, внешние заменяемые Qt DLL, установщик и переносимая папка приложения. EXE требует соседнюю папку `_internal`.
- Помощник обновления переносит свой runtime за пределы установки; резервная копия и восстановление учитывают весь runtime предыдущей версии.
- Общие возможности и числовые ограничения, Ed25519-проверка разрешений, раздельные назначения подписей лицензий/обновлений, идентификатор установки в защищённом хранилище Windows. Платёжный сервис пока не подключён.
- Предварительная линия отделена от публичного канала GPL-обновлений. Нет автоматической публичной публикации и выгрузки source ZIP. Продажа требует отдельной проверки конфигурации, прав, зависимостей и платёжного цикла.

## v0.5.1

- Обновления используют файл канала стабильного релиза `update.json` на GitHub. Проверка больше не расходует общий анонимный лимит GitHub API; при недоступном файле канала используется прежний API. Адреса, версия, установщик, размер и контрольные суммы проверяются теми же правилами.
- Сохраняет новый интерфейс 0.5: светлая и тёмная темы, карточки модулей, поиск настроек и короткие плавные переходы. Полный цикл обновления: фоновая загрузка, проверка, резервная копия, установка и автоматический перезапуск с прежними группами, ярлыками, заметками, настройками и таймером.

## v0.5.0

- Новый Cloud Hub: компактная боковая навигация с поиском по настройкам, карточки модулей с быстрыми переключателями, живое превью острова, единая типографика и спокойные светлая, тёмная и системная темы.
- Плавные короткие переходы между страницами и переключатели. Кадры переходов освобождаются после анимации, скрытый интерфейс не поддерживает анимационные таймеры. Движение можно отключить в настройках приложения.
- Полноценное обновление из приложения: список изменений, фоновая загрузка с прогрессом и отменой, проверка размера и SHA-256, установка и автоматический перезапуск. Загружается только точный установщик стабильного релиза этого репозитория по HTTPS; сторонние адреса и переход на предыдущую версию отклоняются.
- Отдельный помощник завершает приложение, создаёт резервную копию данных и предыдущего EXE, запускает установщик для текущего пользователя, проверяет новую версию и открывает результат. Ошибка установки не удаляет данные; помощник пытается вернуть предыдущий EXE и запуск. Доступна повторная установка текущей версии.
- Группы, сохранённые ярлыки, заметки, настройки и автозапуск сохраняются. Активный таймер учитывает время установки, таймер на паузе сохраняет оставшееся время. Обновление не создаёт заново собранный с рабочего стола ярлык.
- Исправлены сброс готового обновления фоновой проверкой, гонка отмены и повторной загрузки, замена незавершённого ввода при обновлении настроек и обработка повреждённого результата предыдущей установки. Добавлены проверки загрузки, восстановления, таймера, тем и управления с клавиатуры.

## v0.4.2

- Keep independent, byte-for-byte copies of imported `.lnk` and `.url` shortcuts in Cloud Hub's local library. Commit the group before removing a matching desktop shortcut, verify both copies again before collection, preserve original documents/folders, and retain library files when removing a group. Offer an opt-out from desktop collection and a per-item Copy to desktop action.
- Migrate existing accessible shortcuts with a before-migration backup. Preserve IDs, titles, positions and order; never remove source shortcuts if copying, library metadata or the group commit fails. Keep unavailable references for recovery instead of silently deleting them.
- Load native icons from the system image list without shortcut overlays, on a bounded background worker with an LRU cache. Keep custom shortcut icons, arguments, launch targets and Steam URLs; change no Explorer icon settings.
- Add critically damped scrolling for wheel notches while applying touchpad pixel input directly. Preserve velocity when retargeting, stop on manual scrollbar input/hide/range changes and stop animation clocks at rest. Retain scroll position when reloading the grid.
- Remove patterned scrollbar tracks, hide `.url` suffixes in desktop groups and wrap/elide long captions inside their own cells. Add migration, rollback, desktop restore, wheel/touchpad and native shortcut/grid acceptance checks.

## v0.4.1

- Replace the concealed group picker with a persistent, numbered list of all groups and item counts. Bind editing to stable IDs, including collections containing identical titles; retain selection and unfinished names when other surfaces update.
- Add a dedicated group editor with a named creation dialog, editable title, explicit save/Enter/focus-out behavior, file and folder links, an instructive empty state and confirmed deletion. Separate global appearance and behavior into their own tab; keep controls accessible in smaller windows.
- Add Rename, Settings for this group, Create and Delete to every desktop group's own menu. Open the corresponding editor directly and dispatch actions after the popup closes to safely delete its owning panel.
- Localize and style group dialogs, reject blank names, cap names at 60 characters and propose distinct default names. Roll back group mutations on failed writes; keep file-dialog results bound to their original group. Removing groups or links never deletes source files.
- Add regression and native Windows checks covering five duplicate titles, keyboard editing, popup actions, cancellation, deletion, empty collections, file preservation and reload persistence.

## v0.4.0

- Replace foreground-driven desktop group hide/show with a persistent desktop layer. Assign only our own tool HWNDs to the shell owner using documented Win32 ownership, place them below ordinary applications without activation, and retain their position while other windows minimize. Keep the two-second timer solely for shell recovery.
- Disable Windows fly-in/minimize transitions on desktop tiles. Recreate our native surface after a shell-owner restart; no Explorer patching, injected DLLs, child-window reparenting or global animation changes.
- Introduce compact, content-aware group headers, a unified original line-icon family, larger typography, unobtrusive counts, hover menus and synchronized width/height reveal. Preserve expanded dimensions, normalized positions, data and settings.
- Paint stable desktop icon cells with native file/application icons and readable labels. Hide shortcut extensions and redundant folder prefixes; retain original paths and references.
- Redesign search as one continuous neutral surface, a frameless input, denser result rows, quiet keyboard hints and recognizable icons. Remove stacked gradients, the nested input frame and the artificial bevel/shadow.
- Remove Windows 11's incompatible native transient backplate from the layered Qt window: a successful API call still rendered an unwanted square/grey frame. Offer adjustable translucency through the existing appearance toggle, without claiming background blur.
- Add native acceptance checks for immediate group visibility before the next poll, desktop/app z-order, menu ordering, owner destruction/recovery and actual compositor output over an isolated backing window. Preserve single-instance startup, the island compositor, real loopback audio and timer behavior.

## v0.3.2

- Synchronize island content with the expanding black silhouette: scale a cached content layer from actual window geometry, clip it to the same bezel path, then hand back live controls. Preserve spring velocity on rapid reversals; remove the separate late content fade.
- Rebuild desktop group reveal around a stable final layout and one critically damped height clock. Avoid reflowing icons every frame, retain velocity when reversing and stop animation clocks at rest. Keep empty groups compact.
- Fix menus appearing behind their group: use ordinary desktop tools instead of topmost panels, recognize popup ancestry and explicitly retain groups during native file/folder dialogs. Repair desktop z-order only when needed, without activation; retain Peek exclusion.
- Repair coincident group headers on load and creation, preserving IDs, titles and original file references with a before-arrange backup. Add an explicit Arrange action and refresh live grids when settings change their references.
- Refine group styling, spacing, controls and scrollbars. Keep ordinary foreground applications unobstructed and preserve normalized positions across display changes.
- Make repeated background/login launches idempotent: acknowledge the existing process without opening settings. Retain the per-user Windows startup entry and add group/animation state to local runtime diagnostics.
- Add pixel-level clipping, reversal, overlap, popup/dialog and persistence regressions plus native checks for menu z-order, Show Desktop recovery without focus, Peek API acceptance and idle clocks.

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
