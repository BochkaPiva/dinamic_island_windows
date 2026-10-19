# Development and releases

> Current policy (0.7): free GPL v3 community project. The optional community API
> is documented in server/COMMUNITY.md; old account/payment code is archived and
> excluded from the active routes and desktop build. CI builds on public or private
> repositories but never publishes a release automatically. Historical commercial
> instructions below are superseded by docs/community-release-0.7.md.

Cloud Island is a Windows x64 desktop application. Keep the UI thread free of
blocking media, network and audio work. Personal notes, file references, logs,
credentials, settings and build outputs must never be committed.

## Modules

- `island/app.py`: window, tray, services and lifecycle.
- `island/motion.py`: cursor policy, cloud wake, input routing and persistent layers.
- `island/style.py`: independent vector drawing and artwork.
- `island/media.py`: SMTC session polling and commands bound to the displayed source.
- `island/audio.py`: real WASAPI loopback and FFT; never use the microphone.
- `island/hub.py`: calendar, timer, notes and file-reference shelf.
- `island/update_manager.py`: signed commercial channel, no fallback to legacy GPL latest.
- `island/entitlements.py`: central features/limits and signed offline license leases.
- `island/protected_storage.py`: current-user Windows DPAPI boundary.
- `island/storage.py`: per-user atomic settings persistence.
- `island/instance.py`: same-user local activation and graceful installer shutdown.

## Validation

Run `python -m unittest discover -s tests -v` for every substantive change.
For motion/input changes run `python tools/check_native.py build/native-check`
on a Windows desktop. Inspect its PNG/GIF. For audio changes also run
`CloudIsland.exe --audio-self-test build/audio.json` while output audio is playing,
then check silence and an output-device change. Do not capture microphone input.
Check browser tab usability manually on the target setup before claiming a
specific browser has been verified. Native tests use only their own fixture.

Build with `packaging/build.ps1`; it checks that the packaged runtime imports Qt,
the spectrum dependencies and WinRT. Installer and portable archive must contain
notices, replaceable LGPL libraries and checksums. Proprietary application source
must not be automatically published; required dependency sources are a separate
distribution responsibility.
For lifecycle/installer changes run `python tools/check_instance.py` and test
installing over a running packaged app; notes and settings must survive.

## Private candidates and eventual sales releases

1. Make and test the change, update `CHANGELOG.md` with `## vX.Y.Z`.
2. Set `__version__` in `island/__init__.py` to `X.Y.Z`.
3. Commit in the private successor only. This local repository has no public push remote.
4. Run packaging/build.ps1 and the isolated packaged lifecycle verification.
5. CI is private-repository-only, manually dispatched/PR based, and produces private
   candidate artifacts. It has no public publishing job or tag-triggered release.
6. Before any sales publication, run `python tools/release_readiness.py --sales`,
   resolve its actual requirements, configure production services/keys, complete
   source/rights and seller review, and review the exact binary payload.

The installer AppId and the settings directory are stable upgrade identities;
do not change them between releases. The private preview has no live update
channel. Configure a separate signed channel for commercial binaries, preserving
the legacy public release channel and explicit migration choice.
If a release is broken, publish a corrected higher version and explain the issue;
do not replace a version's binaries without changing the version.

Dependabot opens grouped dependency and Actions update PRs weekly. Review them
and wait for CI; it does not merge or publish updates automatically.
