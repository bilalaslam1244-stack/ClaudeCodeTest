# Telegram PA Bot

A 24/7 personal assistant bot for Telegram. Handles reminders, Google Calendar, Gmail, notes, document generation, and meeting transcription.

**Estimated API cost: ~$6/month** (Whisper + Claude Haiku + Sonnet)

---

## Prerequisites

- Python 3.11+
- A Linux VPS (Ubuntu 22.04 recommended)
- `ffmpeg` installed: `sudo apt install ffmpeg libsndfile1`
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- Anthropic API key
- OpenAI API key (Whisper only)
- Google Workspace account with Calendar + Gmail

---

## Setup

### 1. Clone & install

```bash
git clone <repo-url> telegram-pa
cd telegram-pa
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
nano .env   # fill in all values
```

Get your Telegram user ID by messaging [@userinfobot](https://t.me/userinfobot).

### 3. Google OAuth2 setup

**In Google Cloud Console:**
1. Create a project
2. Enable Calendar API and Gmail API
3. Create OAuth2 credentials → Desktop App → download as `data/credentials.json`

**Run the one-time auth flow** (SSH tunnel from your local machine):

```bash
# On your local machine:
ssh -L 8080:localhost:8080 ubuntu@YOUR_VPS_IP

# On the VPS (in the SSH session):
source .venv/bin/activate
python scripts/google_auth_init.py
```

Open the printed URL in your local browser, grant access. Token saved to `data/token.json`.

### 4. Download CJK font (required for Chinese PDF support)

```bash
mkdir -p bot/assets/fonts
wget -O bot/assets/fonts/NotoSansSC-Regular.ttf \
  "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf"
```

Or download `NotoSansSC-Regular.ttf` from [Google Fonts](https://fonts.google.com/noto/specimen/Noto+Sans+SC) and place it in `bot/assets/fonts/`.

### 5. Run manually (test)

```bash
source .venv/bin/activate
python -m bot.main
```

### 6. Deploy as systemd service

```bash
sudo cp systemd/telegram-pa.service /etc/systemd/system/
# Edit the service file if your username is not 'ubuntu':
sudo nano /etc/systemd/system/telegram-pa.service

sudo systemctl daemon-reload
sudo systemctl enable --now telegram-pa
sudo systemctl status telegram-pa
```

View logs:
```bash
journalctl -u telegram-pa -f
```

---

## Usage

Send any message to the bot — voice note or text. Examples:

| Input | Action |
|---|---|
| "Remind me tomorrow at 3pm to review the contract" | Sets reminder |
| "What's on my calendar this week?" | Lists upcoming events |
| "Schedule a meeting with John on Friday at 10am" | Creates calendar event |
| "Cancel the board meeting" | Cancels calendar event |
| "Note: discussed Q3 budget targets with finance team" | Saves note |
| "Any important emails?" | Checks Gmail now |
| "Write a one-page report on Q3 sales performance" | Generates .docx |
| Upload a voice recording | Meeting minutes as .docx |
| Upload a .txt or .csv file | Report generated from file |

**Languages supported:** English, Chinese (Simplified), Malay — auto-detected.

---

## Architecture

```
Voice/Text input
    → Allowlist check (your Telegram user ID only)
    → Language detection (langdetect)
    → Claude Haiku intent classification (temp=0, JSON)
    → Dispatcher:
        reminders    → APScheduler + SQLite
        calendar     → Google Calendar API
        email        → Gmail API + Haiku scoring + Sonnet summary
        notes        → SQLite
        documents    → Claude Sonnet + python-docx / reportlab
        minutes      → Whisper transcription + Claude Sonnet + python-docx
        chat         → Claude Haiku
```

---

## File Structure

```
telegram-pa/
├── bot/
│   ├── main.py              # Entry point
│   ├── config.py            # Environment variables
│   ├── handlers/            # Telegram message handlers
│   ├── services/            # AI, Google, document services
│   ├── db/                  # SQLite models and database
│   ├── auth/                # Google OAuth2
│   ├── scheduler/           # APScheduler jobs
│   ├── utils/               # Language, formatting helpers
│   └── assets/fonts/        # NotoSansSC-Regular.ttf (CJK PDF)
├── data/                    # Runtime data (git-ignored)
│   ├── pa.db                # SQLite database
│   ├── token.json           # Google OAuth2 token
│   └── credentials.json     # Google client secrets
├── output/                  # Temp generated files
├── scripts/
│   └── google_auth_init.py  # One-time OAuth2 setup
├── systemd/
│   └── telegram-pa.service  # systemd unit
├── .env.example
└── requirements.txt
```

---

## Security Notes

- Only your Telegram user ID (`ALLOWED_USER_ID`) can interact with the bot
- `data/token.json` and `data/credentials.json` are git-ignored; keep them secure
- Gmail scope is read-only (`gmail.readonly`) — bot cannot send or delete emails
- All API keys stored in `.env` (git-ignored), loaded at runtime
