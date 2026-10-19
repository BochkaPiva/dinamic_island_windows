# Commercial foundation 0.6.0 (private preview)

Development directory: this repository. It has no public push remote. Do not push
these changes to the legacy public repository. The legacy 0.5.1 line and update
channel are unchanged.

## Build and run

Use a clean Python 3.14 x64 virtual environment. Install requirements-dev.txt
with --only-binary=:all:. Run tests with `python -m unittest discover -s tests -v`.
Run `./packaging/build.ps1` from PowerShell using that environment's Python on
PATH. The output is an onedir portable ZIP and Inno Setup installer. EXE alone
is not portable: `_internal` and notices must accompany it.

build_config.py selects preview at build time. All existing functionality remains
available; no payment or artificial trial expiry is active. The island carries
no commercial badge. The commercial update channel is empty and no legacy API
fallback occurs. Before publishing a commercial client, configure a separate
signed channel, trusted release host, production public keys, and license API.
The commercial verifier accepts purpose-separated signed update envelopes.

## License foundation

FeatureAccess supplies feature decisions and numeric capacity decisions, separate
from battery/game runtime policy. GroupStore checks group creation centrally.
Signed licenses are installation-bound, validated by Ed25519, version/product/
purpose separated, expire at offline_until, and fall back to Free without
deleting data. The installation ID is random, not derived from hardware serials.
Edition strings in settings cannot grant Pro. Keys are empty until a real issuer
is configured. Ephemeral test keys are generated inside tests and never installed.

This is NOT a running subscription service. Account login, activation/refresh,
payment-provider webhooks, receipts, cancellation/refunds, device management and
end-user licensing UI remain to be integrated after seller/service decisions.
No private issuer key belongs in the client or its repository. Future refresh
credentials must use Windows protected storage; no such credentials exist yet.
Clock rollback/long-outage policy must be finalized before paid offline grants.

active_ids is a pure selection helper; expiry never removes records. The final
choose-two/activate/archive UI is deferred until the Free/Pro split is approved.
Preview never hides existing groups. Do not change distribution to commercial
and distribute until activation/expiry UX and all module entry points are wired.

## Update compatibility

The app identifier, data directory, executable name, local IPC and autostart
entry remain compatible. The helper is staged with its matching `_internal`
outside the installed directory, preventing Qt DLL locks during installation.
Backups include notes, groups, owned shortcuts and the complete previous runtime.
Installer removes the previous `_internal` before copying the next runtime.
Rollback restores matching libraries and executable together.

Legacy 0.5.1 uses a self-contained helper and can install the onedir candidate
when explicitly chosen by its owner. It must not be silently redirected to this
line. A future public migration needs an explicit opt-in flow and clear terms.

## Sales release checks

`python tools/release_readiness.py --sales` intentionally fails in this preview.
See legal/release-approvals.json and legal/PROVENANCE.md. Missing production keys,
payment lifecycle, dependency-source delivery, signed installer and seller/rights
approvals are explicit release requirements, not fictitious completed features.
The CI is private-only and has no tag-triggered public publishing job or source
ZIP generation. Runtime notices are preserved independently of app licensing.
