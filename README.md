# Omi Live Football

Omi Live Football is a lightweight external-integration app with one Chat Tool. It uses
EasySoccerData to answer match questions and can send per-user live text commentary until
the user stops it or the match ends.

## Tool contract

The manifest exposes one tool named `football_match` with three actions:

- `query`: return the latest available match information;
- `start_commentary`: start an in-memory polling loop for a popular match;
- `stop_commentary`: stop the current user's polling loop.

The service intentionally has no Redis, separate worker, shared match cache, or cross-user
request merging. Run exactly one application worker. Active commentary sessions are lost if
the process restarts.

## Local setup

1. Create and activate a Python 3.12 or newer virtual environment.
2. Install the project with development dependencies: `python -m pip install -e ".[dev]"`.
3. Copy `.env.example` to `.env` and set `OMI_APP_ID` and `OMI_APP_SECRET`.
4. Run tests with `python -m pytest -q`.
5. Start the app with `uvicorn omi_live_football.main:app --host 0.0.0.0 --port 8080 --workers 1`.

The service provides:

- `GET /healthz`
- `GET /.well-known/omi-tools.json`
- `POST /tools/football-match`

## Omi app setup

1. Deploy the service at a public HTTPS URL.
2. Create an Omi app with the `external_integration` capability.
3. Set the App Home URL to the deployed service URL.
4. Set the Chat Tools Manifest URL to
   `https://your-host.example/.well-known/omi-tools.json`.
5. Configure the deployed service with the Omi App ID and App Secret.
6. Install the app privately and test query, start, notification, stop, partial-data, and
   unavailable-data paths before submitting it to the Marketplace.

## Live provider smoke test

Normal tests do not access the network. To verify the pinned EasySoccerData integration:

```powershell
$env:RUN_LIVE_SOCCER_TESTS = "1"
python -m pytest tests/live/test_easy_soccer_data.py -q
```

The smoke test verifies that a known match can still be loaded. Optional detail endpoints
may be unavailable without failing the base match lookup.
