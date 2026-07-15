# Real End-to-End Validation Status

**Last updated:** July 15, 2026
**Branch:** `feat/omi-live-football`

## Summary

The application is implemented and its component tests pass, but the complete Omi user flow has
not been validated without mocks, fakes, or fixed provider match identifiers.

Completed real-environment evidence:

- the production Docker image starts and serves the health and manifest endpoints;
- the manifest was reached through a real public HTTPS tunnel;
- EasySoccerData dynamically discovered matches live at test time;
- the opt-in provider smoke test reached EasySoccerData over the network.

The remaining blocker is Omi app registration. The Windows Electron client can install
Marketplace apps but does not expose Create App. Omi's official documentation currently requires
the mobile app to create and publish an app. No mobile client, Flutter toolchain, Android SDK,
ADB, or Android emulator was available on the test computer.

## Implemented Surface

- One Omi Chat Tool named `football_match`.
- `query`, `start_commentary`, and `stop_commentary` actions.
- EasySoccerData lookup and optional detail retrieval.
- Popular-match classification and partial non-popular responses.
- Per-user in-memory commentary polling and update deduplication.
- Omi Direct Notification API client with rate-limit handling.
- FastAPI health, manifest, and tool endpoints.
- A single-worker Docker runtime.

## Automated Test Evidence

The complete local suite produced `34 passed, 1 skipped`. The opt-in provider test produced
`1 passed` with `RUN_LIVE_SOCCER_TESTS=1`.

That provider test uses the fixed historical match ID `13_511_924`. It is a live provider
integration smoke test, not a complete end-to-end test or a no-hardcoding acceptance test.

Most component tests intentionally use test doubles. Tool tests use fake soccer and commentary
services, commentary tests use fake clients and a dummy task, Omi notification tests intercept
HTTP with `respx`, and route tests inject a fake tool with in-process ASGI transport. These tests
remain useful, but they do not count as real end-to-end evidence.

## Real Environment Checks

EasySoccerData was queried for live matches at runtime without a fixed match ID. It returned
three live matches during the test window:

- Samoa U16 vs Fiji U16;
- Dilkusha SC vs Victoria SC;
- Zenit-Izhevsk U17 vs OSSh-Chelyabinsk U17.

All three were non-popular under the configured policy. The provider's non-live events request
for the same day returned an HTTP error. Future tests must report this neutrally without claiming
that a requested match does not exist.

The `omi-live-football:dev` Docker image started with one worker. Real HTTP requests to
`/healthz` and `/.well-known/omi-tools.json` succeeded. The manifest contained exactly one
`football_match` tool and the three expected actions.

Cloudflare Tunnel temporarily exposed the container. QUIC was blocked by the current network,
so transport was changed to HTTP/2. The tunnel registered successfully, and both endpoints were
retrieved through its public HTTPS URL. The ephemeral URL is intentionally not recorded.

## Security and Cleanup

- No Omi App ID or App Secret was available or stored.
- No `.env` file was created.
- No credentials or access tokens are included in this repository.
- The temporary tunnel and application container were stopped after confirming the blocker.
- Cloudflare Tunnel remains installed for a future test session.

## Remaining No-Mock End-to-End Scenarios

All scenarios must use the installed Omi desktop client, Omi's production cloud service, the
deployed FastAPI app, and the real EasySoccerData and Omi APIs. They must not inject handlers,
replace network clients, intercept HTTP, or use fixed match IDs.

1. Register the public manifest in a real private Omi app and install it for the test account.
2. Dynamically query a non-popular live match by team names; verify partial data and commentary
   rejection.
3. Query a uniquely generated impossible fixture; verify the neutral unavailable response.
4. Dynamically query a covered popular match and compare details with fresh provider responses.
5. Start commentary; verify real polling, notification delivery, update deduplication, and an
   idempotent repeated start.
6. Stop commentary; verify no later update and a harmless repeated stop.
7. Let a match finish; verify the final update and automatic session termination.
8. With a dedicated private test app, verify real HTTP 429 and `Retry-After` behavior.
9. Restart the service during commentary and verify the documented loss of the in-memory session.

## Completion Criteria

The app is ready for Marketplace review only after scenarios 1 through 7 pass through the real
Omi desktop experience. Scenarios 8 and 9 must also pass before claiming full behavior coverage.
