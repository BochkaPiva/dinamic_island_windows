# Future license-service contract

This document defines the boundary; it is not a deployed payment or activation
backend. Current preview does not contact an account or payment service.

Authentication opens the system browser. The client must not embed a payment
form or store card details. Use a standard browser-to-native flow with PKCE and
state, exact redirect validation and short-lived codes. User credentials/tokens
belong in Windows protected storage. No shared secret or signing private key is
distributed with the app.

## Operations

- Activate an installation: authenticated account + installation UUID + product;
  enforce device limits atomically, return a signed license lease.
- Refresh a lease: authenticate the installation/session; re-evaluate payment,
  cancellation, revocation, device slots and server time. Return a new bounded
  lease or explicit revoked/expired state. Retry transient errors with backoff.
- List/deactivate devices: authenticated account ownership required. Support
  reinstall/replacement without permanent hardware blacklisting.
- Start checkout: server resolves an allowed price/product, creates a provider
  payment and returns an HTTPS checkout URL. Never trust a client amount/edition.
- Provider notification: verify via the provider's supported method and/or fetch
  payment status server-to-server, deduplicate by provider event/payment ID, and
  commit the payment ledger and entitlement change transactionally.
- Cancel renewal, refund and history: authorize account ownership; cancellation
  stops future renewals and does not discard the already paid interval. Refund
  and lease revocation policies must be explicit and tested.

## Signed client lease v1

Envelope: key_id, base64 payload, base64 Ed25519 signature. Sign the exact payload
bytes prefixed with `cloud-hub/license/v1` and a NUL separator. A key ID is accepted
only from the client's compiled trusted key map; it cannot supply a new public key.

Payload: integer schema=1, product=cloud-hub, installation_id, edition=pro,
issued_at, not_before, offline_until, paid_until (UTC Unix seconds), explicit
feature IDs and numeric limits. None for a known limit means no tariff cap;
missing fields never imply unlimited rights. Offline validity ends at
offline_until, no later than paid_until in v1. New outage/grace behavior needs
an explicit versioned policy, not ignoring expiry.

Renewal must complete before lease expiry with jitter/backoff; no requests in the
rendering loop. Re-evaluate access on a timer and resume/unlock, not only when a
button is clicked. Final module/activation UI and clock rollback policy are sales
requirements; they are not enabled by switching a flag in this preview.

## Signed updates

Use a separate trusted key map and the prefix `cloud-hub/update/v1` followed by
NUL. Never reuse a license as update metadata. The inner payload follows the
existing bounded release schema (version, exact repository/asset names, size,
digest). Final commercial binary-host identity must differ from the public GPL
latest channel. Publish neither private keys nor proprietary application source.

Before sales test duplicate/out-of-order provider events, failed renewal,
refunds, revoked devices, unavailable service, moved/corrupt credentials, clock
changes, version/key rotation and restoration of existing local user materials.
