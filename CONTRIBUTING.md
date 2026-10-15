# Development and releases

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
- `island/updates.py`: stable releases from this repository, no silent execution.
- `island/storage.py`: per-user atomic settings persistence.

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
notices, and the release must include matching source and checksums.

## Publish a release

1. Make and test the change, update `CHANGELOG.md` with `## vX.Y.Z`.
2. Set `__version__` in `island/__init__.py` to `X.Y.Z`.
3. Commit and push to `main`; inspect the Windows build in Actions.
4. Tag that verified commit: `git tag vX.Y.Z`, then `git push origin vX.Y.Z`.
5. The tag workflow builds, tests and publishes installer, EXE, portable ZIP,
   source ZIP and `SHA256SUMS.txt` to GitHub Releases.
6. Inspect the published assets and release notes before recommending the update.

The installer AppId and the settings directory are stable upgrade identities;
do not change them between releases. The tag must match `__version__`; the build
rejects a mismatch. The application checks only stable releases in this repository.
If a release is broken, publish a corrected higher version and explain the issue;
do not replace a version's binaries without changing the version.

Dependabot opens grouped dependency and Actions update PRs weekly. Review them
and wait for CI; it does not merge or publish updates automatically.
