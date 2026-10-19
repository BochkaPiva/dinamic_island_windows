# Security and privacy

The optional community service receives Telegram ID, random installation ID and
membership status. User files, groups, notes, audio and camera images remain local.
Device credentials use Windows DPAPI; only their hashes are stored server-side.
The bot token and signing private key must never be distributed with an installer.

Report a vulnerability through the repository's private vulnerability reporting
feature if available; otherwise contact the maintainer through their GitHub
profile before posting exploit details publicly.

Normal operation stores settings, notes and file references only on this PC.
The spectrum reads Windows output loopback into memory and discards PCM buffers;
it never opens a microphone or writes audio files. The calendar is local and
does not access online accounts.

The optional update check contacts the GitHub Releases API for this repository,
sending a normal application user agent. No notes, file lists or audio are sent.
Updating requires the user to download and run an installer. Published checksums
detect file corruption; they are not a substitute for a trusted download source.

Release EXEs are currently unsigned. CI uses pinned dependency versions and
Actions commit SHAs. Builds from pull requests have read-only repository access;
only a successful tag build can publish a release.
