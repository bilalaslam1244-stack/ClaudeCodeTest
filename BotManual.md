# Telegram Personal Assistant Bot — Complete Manual

> Built for busy executives. Powered by Claude AI, Gmail, Google Calendar, OpenAI Whisper, and Zoom.

---

## Table of Contents

1. [What This Bot Does](#1-what-this-bot-does)
2. [All Features & Example Commands](#2-all-features--example-commands)
3. [Setup Guide (First-Time Installation)](#3-setup-guide-first-time-installation)
4. [Environment Variables Reference](#4-environment-variables-reference)
5. [API Keys — Where to Get Them](#5-api-keys--where-to-get-them)
6. [Zoom Integration Setup](#6-zoom-integration-setup)
7. [Google OAuth Setup (Gmail & Calendar)](#7-google-oauth-setup-gmail--calendar)
8. [Starting, Stopping & Auto-Start](#8-starting-stopping--auto-start)
9. [Transferring the Bot to a New Machine](#9-transferring-the-bot-to-a-new-machine)
10. [Costs Breakdown](#10-costs-breakdown)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. What This Bot Does

This is a private Telegram bot that acts as a fully capable personal assistant. It connects to Gmail, Google Calendar, Zoom, and uses Claude AI for intelligence and OpenAI Whisper for voice transcription.

Only authorised Telegram users can interact with it. All data stays local — nothing is stored on third-party servers beyond what is necessary to call the APIs (Google, Anthropic, OpenAI, Zoom).

**Core capabilities:**

- Manage reminders — set, list, cancel
- Manage calendar events — create, reschedule, cancel, view by day/week
- Auto-create Zoom meeting links when scheduling events
- Read, summarize, and send emails via Gmail
- Mute noisy senders (e.g. tender emails)
- Daily morning briefing at 7 AM — schedule + inbox highlights
- Save and retrieve personal notes
- Upload documents (PDF, Word, images) — ask questions about them
- Transcribe voice messages and execute commands
- Convert long voice recordings into formatted meeting minutes
- Scan business cards → save contact to iPhone
- Summarize images, screenshots, resumes, and document photos
- Summarize web URLs
- Natural conversation with memory of past messages

---

## 2. All Features & Example Commands

### Reminders

| Command | What it does |
|---|---|
| Remind me to call Ahmed at 3pm tomorrow | Sets a reminder; bot pings you at that time |
| What are my reminders? | Lists all pending reminders |
| Cancel the 3pm reminder | Cancels a specific reminder |

### Calendar

| Command | What it does |
|---|---|
| Schedule a meeting with Eddie on Friday at 10:30am | Creates calendar event + Zoom link (if configured) |
| What's on my calendar today? | Shows today's events only |
| What do I have this week? | Shows the full week |
| Reschedule the board meeting to Monday 2pm | Moves an existing event |
| Cancel the Friday meeting | Deletes event (with confirmation button) |

### Email

| Command | What it does |
|---|---|
| Check my emails | Fetches and summarizes latest inbox emails |
| Give me the last 5 emails | Fetches exactly 5 emails with AI summaries |
| Any emails from Ahmed? | Filters emails by sender name |
| Summarize my emails | AI digest of important emails |
| Send an email to sarah@company.com — Re: Meeting — body: see you at 3pm | Sends an email |
| Mute tender emails | Blocks emails matching "tender" from appearing |
| Unmute tender | Removes the mute filter |

### Daily Overview (Auto at 7 AM)

| Command | What it does |
|---|---|
| *(automatic every morning)* | Bot sends today's calendar + inbox highlights at 7 AM |
| Give me today's overview | Trigger manually anytime |

### Notes

| Command | What it does |
|---|---|
| Note: follow up with the legal team on Monday | Saves a note |
| What notes do I have about legal? | Searches and retrieves notes by topic |

### Documents

| Command | What it does |
|---|---|
| *(attach any PDF, Word, or image file)* | Bot reads it and asks what you'd like to do |
| Summarize this document | After uploading, summarize it |
| What are the key risks in this report? | Ask questions about an uploaded document |
| Generate a report based on this audit | Generates a new Word/PDF doc from uploaded content |

### Voice Messages

| Command | What it does |
|---|---|
| *(send any short voice note)* | Transcribed and executed as a command |
| *(send voice recording over 60 seconds)* | Auto-converted to formatted meeting minutes (.docx) |

### Business Cards

| Command | What it does |
|---|---|
| *(send a photo of a business card)* | Extracts name, phone, email, company → sends .vcf file → tap to add to iPhone contacts |

### Image / Screenshot Summarizer

| Command | What it does |
|---|---|
| *(send any photo — resume, screenshot, document)* | Claude reads and summarizes key content |
| *(send photo with caption: "who is this person?")* | Caption used as the question; answered against the image |

### URL Summarizer

| Command | What it does |
|---|---|
| https://some-article.com — summarize this | Fetches the page and summarizes it |

### General Chat

| Command | What it does |
|---|---|
| Draft a polite follow-up email to a client | General AI assistant request |
| Clear memory | Resets conversation history |

---

## 3. Setup Guide (First-Time Installation)

### Prerequisites

- Windows 10/11 PC (the "server" machine — must stay on)
- Python 3.11 or 3.12 — [python.org](https://python.org)
- Git — [git-scm.com](https://git-scm.com)
- Tesseract OCR — [github.com/UB-Mannheim/tesseract/wiki](https://github.com/UB-Mannheim/tesseract/wiki)
- ffmpeg on PATH — [ffmpeg.org](https://ffmpeg.org) (required for audio processing)

### Step 1 — Clone the Repository

```
git clone https://github.com/bilalaslam1244-stack/ClaudeCodeTest.git
cd ClaudeCodeTest\telegram-pa
```

### Step 2 — Create Virtual Environment

```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### Step 3 — Create .env File

Copy `.env.example` to `.env` and fill in all values:

```
copy .env.example .env
```

Edit `.env` with your actual keys (see Sections 4 and 5).

### Step 4 — Create the data folder

```
mkdir data
```

Place `credentials.json` (Google OAuth) inside the `data` folder.

### Step 5 — Run the Bot

```
python -m bot.main
```

On first run you will be redirected to a Google login page in your browser. Log in with the boss's Google account and grant permissions. A `token.json` file will be saved in the `data` folder — this keeps you logged in permanently.

---

## 4. Environment Variables Reference

All variables go in the `.env` file inside the `telegram-pa` folder.

| Variable | Required | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Yes | Bot token from @BotFather |
| `ANTHROPIC_API_KEY` | Yes | Claude AI key from console.anthropic.com |
| `OPENAI_API_KEY` | Yes | OpenAI key for Whisper transcription |
| `ALLOWED_USER_ID` | Yes | Boss's Telegram numeric ID. For multiple users: `123456,789012` |
| `BOSS_TIMEZONE` | Yes | e.g. `Asia/Kuala_Lumpur` — used for all time calculations |
| `GOOGLE_CREDENTIALS_PATH` | Yes | Path to OAuth credentials JSON (default: `data/credentials.json`) |
| `GOOGLE_TOKEN_PATH` | Yes | Where to store the OAuth token (default: `data/token.json`) |
| `DB_PATH` | Yes | SQLite database path (default: `data/pa.db`) |
| `CLAUDE_HAIKU_MODEL` | No | Claude Haiku model ID (default: `claude-haiku-4-5-20251001`) |
| `CLAUDE_SONNET_MODEL` | No | Claude Sonnet model ID (default: `claude-sonnet-4-6`) |
| `ZOOM_ACCOUNT_ID` | No | Zoom Server-to-Server OAuth account ID |
| `ZOOM_CLIENT_ID` | No | Zoom app client ID |
| `ZOOM_CLIENT_SECRET` | No | Zoom app client secret |
| `TELEGRAM_LOCAL_API_URL` | No | Local Bot API URL to remove 20MB file limit (e.g. `http://localhost:8081/bot`) |

---

## 5. API Keys — Where to Get Them

| Key | Where to get it |
|---|---|
| **Telegram Bot Token** | Message @BotFather on Telegram → `/newbot` → follow prompts → copy token |
| **Boss's Telegram ID** | Message @userinfobot on Telegram — it replies with the numeric ID |
| **Anthropic API Key** | [console.anthropic.com](https://console.anthropic.com) → API Keys → Create Key |
| **OpenAI API Key** | [platform.openai.com](https://platform.openai.com) → API Keys → Create new secret key |
| **Google OAuth credentials** | [console.cloud.google.com](https://console.cloud.google.com) → New project → Enable Gmail + Calendar APIs → Credentials → OAuth 2.0 Client → Desktop App → Download JSON → save as `data/credentials.json` |
| **Zoom credentials** | [marketplace.zoom.us](https://marketplace.zoom.us) → Develop → Build App → Server-to-Server OAuth → note Account ID, Client ID, Client Secret |

---

## 6. Zoom Integration Setup

When configured, every calendar event the bot creates automatically includes a Zoom meeting link — in both the Telegram reply and the Google Calendar invite.

**Steps:**

1. Go to [marketplace.zoom.us](https://marketplace.zoom.us) and sign in with the boss's Zoom account
2. Click **Develop → Build App**
3. Choose **Server-to-Server OAuth**
4. Give it any name (e.g. "PA Bot")
5. Copy the **Account ID**, **Client ID**, and **Client Secret**
6. Under **Scopes**, add: `meeting:write` or `meeting:write:admin`
7. Click **Activate App**
8. Add the three values to `.env`:

```
ZOOM_ACCOUNT_ID=your_account_id
ZOOM_CLIENT_ID=your_client_id
ZOOM_CLIENT_SECRET=your_client_secret
```

9. Restart the bot

> If Zoom credentials are not in `.env`, calendar events are still created normally — just without a Zoom link. No errors.

---

## 7. Google OAuth Setup (Gmail & Calendar)

The bot needs OAuth2 access to the boss's Gmail and Google Calendar. This is a one-time setup per Google account.

### Step 1 — Create a Google Cloud Project

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Click **Select a project → New Project** → give it any name → **Create**

### Step 2 — Enable APIs

1. Go to **APIs & Services → Library**
2. Search for **Gmail API** → Enable
3. Search for **Google Calendar API** → Enable

### Step 3 — Create OAuth Credentials

1. Go to **APIs & Services → Credentials → Create Credentials → OAuth 2.0 Client ID**
2. Application type: **Desktop App**
3. Download the JSON file → rename to `credentials.json` → place in `data/` folder

### Step 4 — OAuth Consent Screen

1. Go to **APIs & Services → OAuth consent screen**
2. User type: **External**
3. Fill in App name (any name) and support email
4. Under **Test users** — add the boss's Gmail address
5. Publishing status: leave as **Testing** (no need to publish)

### Step 5 — First Run Authorization

1. Start the bot: `python -m bot.main`
2. A browser window opens asking to sign into Google
3. Sign in with the boss's Google account
4. Click **Allow** for Gmail and Calendar permissions
5. A `token.json` is saved — bot stays logged in permanently

> Keep `token.json` safe. If deleted, just restart the bot and log in again via the browser.

---

## 8. Starting, Stopping & Auto-Start

### Start Manually

```
cd C:\path\to\ClaudeCodeTest\telegram-pa
venv\Scripts\activate
python -m bot.main
```

### Stop the Bot

Press **Ctrl + C** in the terminal. A traceback may appear — this is normal.

### Auto-Start with Windows Task Scheduler

1. Open **Task Scheduler** (search in Start menu)
2. Click **Create Basic Task** → give it a name (e.g. "PA Bot")
3. Trigger: **When the computer starts**
4. Action: **Start a program**
5. Program: `C:\path\to\telegram-pa\venv\Scripts\python.exe`
6. Arguments: `-m bot.main`
7. Start in: `C:\path\to\telegram-pa`
8. Check: **Run whether user is logged on or not**
9. Finish

> The PC must stay on for the bot to work. Sleep/hibernate stops the bot.

---

## 9. Transferring the Bot to a New Machine

1. Install Python 3.11+, Git, Tesseract OCR, and ffmpeg on the new machine
2. Clone: `git clone https://github.com/bilalaslam1244-stack/ClaudeCodeTest.git`
3. `cd ClaudeCodeTest\telegram-pa`
4. `python -m venv venv && venv\Scripts\activate && pip install -r requirements.txt`
5. Copy the `.env` file from the old machine
6. Copy the entire `data/` folder (contains `credentials.json` and `token.json` — no Google login needed again)
7. Run: `python -m bot.main`
8. Set up Task Scheduler again (see Section 8)

---

## 10. Costs Breakdown

All costs are pay-as-you-go. No monthly subscription.

| Service | Estimated Cost |
|---|---|
| **Anthropic (Claude AI)** | ~$5–15/month depending on usage. Intent classification uses Haiku (cheap). Doc generation uses Sonnet. |
| **OpenAI (Whisper)** | ~$0.006 per minute of audio. A 30-min meeting ≈ $0.18. Light use = under $2/month. |
| **Google APIs** | Free within generous quota limits. |
| **Zoom API** | Free — included in all Zoom plans. |
| **Telegram Bot API** | Free. |
| **Electricity (PC)** | ~$10–20/month running 24/7 on a modern desktop. |
| **Internet** | Minimal — API calls only, no streaming. |

**Estimated total API cost for typical executive use: USD $10–25/month.**

---

## 11. Troubleshooting

| Problem | Solution |
|---|---|
| **Bot not responding** | Check terminal for errors. Ensure venv is active and `.env` has correct keys. Restart: Ctrl+C then `python -m bot.main` |
| **"Access Required" or "no access" messages** | Type `clear memory` in the bot. Old cached messages caused this. Bot has full Gmail + Calendar access. |
| **Bot says file is too big (audio)** | File exceeds Telegram's 20MB limit. Set up the local Telegram Bot API server to remove this limit. |
| **Google auth expired** | Delete `data/token.json` and restart the bot. Browser login appears again. |
| **Zoom link not appearing** | Check `ZOOM_ACCOUNT_ID`, `ZOOM_CLIENT_ID`, `ZOOM_CLIENT_SECRET` are in `.env`. Restart bot. |
| **Business card scan sends no .vcf** | Ensure the photo is clear and well-lit. Blurry cards may fail detection. |
| **Daily overview not arriving at 7 AM** | Check `BOSS_TIMEZONE` in `.env` is correct. PC must be on and bot running. |
| **Email mute not working** | Say `mute [keyword]` exactly. Verify with "what are my muted senders". |
| **Bot not reading PDF fully** | Large/scanned PDFs use Tesseract OCR. Ensure Tesseract is installed and on PATH. |
| **KeyboardInterrupt traceback on stop** | Normal — not an error. Just press Ctrl+C to stop. |
| **Photos not being processed** | Ensure bot is restarted after latest update. PHOTO filter was added in a recent fix. |

---

*Manual generated April 2026 — covers all features as of the latest bot version.*
