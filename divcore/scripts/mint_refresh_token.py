"""One-time helper to mint a Google OAuth refresh token for the public calendar.

Run this ONCE, locally, signed in as the account that OWNS the shared public
calendar. It prints a refresh token you paste into `.env` as
GOOGLE_OAUTH_REFRESH_TOKEN. See followup.md (Part E) for the full context.

Usage:
    pip install google-auth-oauthlib
    # fill CLIENT_ID / CLIENT_SECRET below (from GCP Credentials, Part C), then:
    python scripts/mint_refresh_token.py

A browser opens -> sign in as the calendar owner -> grant access ->
the terminal prints REFRESH TOKEN.
"""

import os
import sys
from pathlib import Path

# Running this as a script puts scripts/ (not the project root) on sys.path, so make
# the project importable for the `app.config` fallback below.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google_auth_oauthlib.flow import InstalledAppFlow

try:
    # Prefer the app's settings (which load `.env`) so we don't need to export vars.
    from app.config import get_settings_singleton

    _s = get_settings_singleton()
    _cfg_id, _cfg_secret = _s.GOOGLE_OAUTH_CLIENT_ID, _s.GOOGLE_OAUTH_CLIENT_SECRET
except Exception:  # running outside the project / import failure — fall back to env
    _cfg_id = _cfg_secret = None

# Precedence: explicit env var > .env via settings > placeholder.
CLIENT_ID = os.getenv("GOOGLE_OAUTH_CLIENT_ID") or _cfg_id or "YOUR_CLIENT_ID"
CLIENT_SECRET = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET") or _cfg_secret or "YOUR_CLIENT_SECRET"

# Redirect URI must be registered on the OAuth client (Part C): http://localhost:8765/
REDIRECT_PORT = 8765

# Only the scope needed to create/update events on a calendar we own.
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]

CLIENT_CONFIG = {
    "web": {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": [f"http://localhost:{REDIRECT_PORT}/"],
    }
}


def main() -> None:
    if CLIENT_ID == "YOUR_CLIENT_ID" or CLIENT_SECRET == "YOUR_CLIENT_SECRET":
        raise SystemExit(
            "Set CLIENT_ID / CLIENT_SECRET (edit this file or export "
            "GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET) first."
        )

    flow = InstalledAppFlow.from_client_config(CLIENT_CONFIG, scopes=SCOPES)
    # access_type=offline + prompt=consent forces Google to return a refresh_token.
    creds = flow.run_local_server(
        port=REDIRECT_PORT,
        access_type="offline",
        prompt="consent",
    )

    if not creds.refresh_token:
        raise SystemExit(
            "No refresh token returned. Re-run; ensure prompt=consent and that this "
            "is a fresh grant (revoke prior access at myaccount.google.com/permissions)."
        )

    print("\n" + "=" * 60)
    print("REFRESH TOKEN (paste into .env as GOOGLE_OAUTH_REFRESH_TOKEN):\n")
    print(creds.refresh_token)
    print("=" * 60)


if __name__ == "__main__":
    main()
