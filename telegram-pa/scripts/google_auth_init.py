"""
One-time Google OAuth2 consent flow.

Run on the VPS via SSH tunnel:
  Local machine:  ssh -L 8080:localhost:8080 user@your-vps-ip
  On VPS:         python scripts/google_auth_init.py

Then open the URL printed in your local browser.
Token is saved to data/token.json.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google_auth_oauthlib.flow import InstalledAppFlow
from bot.config import GOOGLE_CREDENTIALS_PATH, GOOGLE_TOKEN_PATH, GOOGLE_SCOPES


def main() -> None:
    if not os.path.exists(GOOGLE_CREDENTIALS_PATH):
        print(f"ERROR: {GOOGLE_CREDENTIALS_PATH} not found.")
        print("Download OAuth2 credentials from Google Cloud Console")
        print("(APIs & Services → Credentials → Create OAuth client ID → Desktop App)")
        sys.exit(1)

    flow = InstalledAppFlow.from_client_secrets_file(
        GOOGLE_CREDENTIALS_PATH, GOOGLE_SCOPES
    )
    creds = flow.run_local_server(port=8080, open_browser=False)

    os.makedirs(os.path.dirname(GOOGLE_TOKEN_PATH), exist_ok=True)
    with open(GOOGLE_TOKEN_PATH, "w") as f:
        f.write(creds.to_json())
    try:
        os.chmod(GOOGLE_TOKEN_PATH, 0o600)
    except OSError:
        pass

    print(f"\nSuccess! Token saved to {GOOGLE_TOKEN_PATH}")
    print("You can now start the bot.")


if __name__ == "__main__":
    main()
