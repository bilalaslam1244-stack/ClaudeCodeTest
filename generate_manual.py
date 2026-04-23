"""Generate BotManual.pdf — run from project root with venv active."""
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak,
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT

OUTPUT = "BotManual.pdf"

W, H = A4
MARGIN = 2 * cm

styles = getSampleStyleSheet()

def style(name, **kwargs):
    s = ParagraphStyle(name, parent=styles["Normal"], **kwargs)
    return s

TITLE   = style("Title",    fontSize=26, textColor=colors.HexColor("#1a1a2e"), spaceAfter=6, alignment=TA_CENTER, fontName="Helvetica-Bold")
SUB     = style("Sub",      fontSize=13, textColor=colors.HexColor("#16213e"), spaceAfter=14, alignment=TA_CENTER, fontName="Helvetica")
H1      = style("H1",       fontSize=16, textColor=colors.HexColor("#0f3460"), spaceBefore=18, spaceAfter=6, fontName="Helvetica-Bold")
H2      = style("H2",       fontSize=13, textColor=colors.HexColor("#533483"), spaceBefore=12, spaceAfter=4, fontName="Helvetica-Bold")
BODY    = style("Body",     fontSize=10, leading=15, spaceAfter=4)
BULLET  = style("Bullet",   fontSize=10, leading=15, leftIndent=16, spaceAfter=3, bulletIndent=6)
CODE    = style("Code",     fontSize=9,  leading=13, fontName="Courier", backColor=colors.HexColor("#f4f4f4"), leftIndent=12, spaceBefore=4, spaceAfter=4)
NOTE    = style("Note",     fontSize=9,  leading=13, textColor=colors.HexColor("#555555"), leftIndent=12, spaceAfter=4)
CAPTION = style("Caption",  fontSize=8,  textColor=colors.grey, alignment=TA_CENTER)

ACCENT = colors.HexColor("#0f3460")
LIGHT  = colors.HexColor("#e8f0fe")
MID    = colors.HexColor("#c5d8f7")

def hr():
    return HRFlowable(width="100%", thickness=1, color=MID, spaceAfter=8, spaceBefore=4)

def h1(t): return Paragraph(t, H1)
def h2(t): return Paragraph(t, H2)
def p(t):  return Paragraph(t, BODY)
def b(t):  return Paragraph(f"• {t}", BULLET)
def sp(n=6): return Spacer(1, n)
def code(t): return Paragraph(t.replace(" ", "&nbsp;"), CODE)
def note(t): return Paragraph(f"<i>{t}</i>", NOTE)

def cmd_table(rows):
    data = [["Command / Example", "What it does"]] + rows
    col_w = [(W - 2*MARGIN) * x for x in (0.45, 0.55)]
    t = Table(data, colWidths=col_w, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND",   (0,0), (-1,0), ACCENT),
        ("TEXTCOLOR",    (0,0), (-1,0), colors.white),
        ("FONTNAME",     (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",     (0,0), (-1,0), 9),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, LIGHT]),
        ("FONTSIZE",     (0,1), (-1,-1), 9),
        ("VALIGN",       (0,0), (-1,-1), "TOP"),
        ("GRID",         (0,0), (-1,-1), 0.4, MID),
        ("LEFTPADDING",  (0,0), (-1,-1), 6),
        ("RIGHTPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING",   (0,0), (-1,-1), 5),
        ("BOTTOMPADDING",(0,0), (-1,-1), 5),
    ]))
    return t

def key_table(rows):
    data = [["Key / Variable", "Where to get it"]] + rows
    col_w = [(W - 2*MARGIN) * x for x in (0.35, 0.65)]
    t = Table(data, colWidths=col_w, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND",   (0,0), (-1,0), ACCENT),
        ("TEXTCOLOR",    (0,0), (-1,0), colors.white),
        ("FONTNAME",     (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",     (0,0), (-1,0), 9),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, LIGHT]),
        ("FONTSIZE",     (0,1), (-1,-1), 9),
        ("VALIGN",       (0,0), (-1,-1), "TOP"),
        ("GRID",         (0,0), (-1,-1), 0.4, MID),
        ("LEFTPADDING",  (0,0), (-1,-1), 6),
        ("RIGHTPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING",   (0,0), (-1,-1), 5),
        ("BOTTOMPADDING",(0,0), (-1,-1), 5),
    ]))
    return t

def env_table(rows):
    data = [["Variable", "Required", "Description"]] + rows
    col_w = [(W - 2*MARGIN) * x for x in (0.32, 0.12, 0.56)]
    t = Table(data, colWidths=col_w, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND",   (0,0), (-1,0), ACCENT),
        ("TEXTCOLOR",    (0,0), (-1,0), colors.white),
        ("FONTNAME",     (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",     (0,0), (-1,0), 9),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, LIGHT]),
        ("FONTSIZE",     (0,1), (-1,-1), 9),
        ("FONTNAME",     (0,1), (0,-1), "Courier"),
        ("VALIGN",       (0,0), (-1,-1), "TOP"),
        ("GRID",         (0,0), (-1,-1), 0.4, MID),
        ("LEFTPADDING",  (0,0), (-1,-1), 6),
        ("RIGHTPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING",   (0,0), (-1,-1), 5),
        ("BOTTOMPADDING",(0,0), (-1,-1), 5),
    ]))
    return t

story = []

# ── COVER ──────────────────────────────────────────────────────────────────────
story += [
    sp(60),
    Paragraph("Telegram Personal Assistant Bot", TITLE),
    sp(8),
    Paragraph("Complete User &amp; Setup Manual", SUB),
    sp(4),
    hr(),
    sp(4),
    Paragraph("Built for busy executives — powered by Claude AI, Gmail, Google Calendar, Whisper &amp; Zoom", NOTE),
    sp(4),
    note("Version 1.0  ·  April 2026"),
    PageBreak(),
]

# ── TABLE OF CONTENTS ──────────────────────────────────────────────────────────
story += [
    h1("Table of Contents"),
    hr(),
    p("1. What This Bot Does"),
    p("2. All Features &amp; Example Commands"),
    p("3. Setup Guide (First-Time Installation)"),
    p("4. Environment Variables Reference"),
    p("5. API Keys — Where to Get Them"),
    p("6. Zoom Integration Setup"),
    p("7. Google OAuth Setup (Gmail &amp; Calendar)"),
    p("8. Starting, Stopping &amp; Auto-Start"),
    p("9. Transferring the Bot to a New Machine"),
    p("10. Costs Breakdown"),
    p("11. Troubleshooting"),
    PageBreak(),
]

# ── SECTION 1 ──────────────────────────────────────────────────────────────────
story += [
    h1("1. What This Bot Does"),
    hr(),
    p("This is a private Telegram bot that acts as a fully capable personal assistant. "
      "It connects to Gmail, Google Calendar, Zoom, and uses Claude AI for intelligence "
      "and OpenAI Whisper for voice transcription."),
    sp(),
    p("Only authorised Telegram users can interact with it. All data stays local — "
      "nothing is stored on third-party servers except what is necessary to call the APIs "
      "(Google, Anthropic, OpenAI, Zoom)."),
    sp(),
    p("<b>Core capabilities at a glance:</b>"),
    b("Manage reminders — set, list, cancel"),
    b("Manage calendar events — create, reschedule, cancel, view"),
    b("Auto-create Zoom meeting links when scheduling events"),
    b("Read, summarize, and send emails via Gmail"),
    b("Mute noisy senders (e.g. tender emails)"),
    b("Daily morning briefing at 7 AM — schedule + inbox highlights"),
    b("Save and retrieve personal notes"),
    b("Upload documents (PDF, Word, images) — ask questions about them"),
    b("Transcribe voice messages and execute commands"),
    b("Convert long voice recordings into formatted meeting minutes"),
    b("Scan business cards → save contact to iPhone"),
    b("Summarize images, screenshots, resumes, and document photos"),
    b("Summarize web URLs"),
    b("Natural conversation with memory of past messages"),
    PageBreak(),
]

# ── SECTION 2 ──────────────────────────────────────────────────────────────────
story += [
    h1("2. All Features &amp; Example Commands"),
    hr(),
]

story += [
    h2("Reminders"),
    cmd_table([
        ["Remind me to call Ahmed at 3pm tomorrow", "Sets a reminder; bot pings you at that time"],
        ["What are my reminders?", "Lists all pending reminders"],
        ["Cancel the 3pm reminder", "Cancels a specific reminder"],
    ]),
    sp(),

    h2("Calendar"),
    cmd_table([
        ["Schedule a meeting with Eddie on Friday at 10:30am", "Creates calendar event + Zoom link (if configured)"],
        ["What's on my calendar today?", "Shows today's events only"],
        ["What do I have this week?", "Shows the full week"],
        ["Reschedule the board meeting to Monday 2pm", "Moves an existing event"],
        ["Cancel the Friday meeting", "Deletes event (with confirmation button)"],
    ]),
    sp(),

    h2("Email"),
    cmd_table([
        ["Check my emails", "Fetches and summarizes latest inbox emails"],
        ["Give me the last 5 emails", "Fetches exactly 5 emails with summaries"],
        ["Any emails from Ahmed?", "Filters emails by sender name"],
        ["Summarize my emails", "AI digest of important emails"],
        ["Send an email to sarah@company.com — Re: Meeting — body: see you at 3pm", "Sends email"],
        ["Mute tender emails", "Blocks emails matching 'tender' from appearing"],
        ["Unmute tender", "Removes the mute filter"],
    ]),
    sp(),

    h2("Daily Overview (Auto at 7 AM)"),
    cmd_table([
        ["(automatic every morning)", "Bot sends today's calendar + inbox highlights at 7 AM"],
        ["Give me today's overview", "Trigger manually anytime"],
    ]),
    sp(),

    h2("Notes"),
    cmd_table([
        ["Note: follow up with the legal team on Monday", "Saves a note"],
        ["What notes do I have about legal?", "Searches and retrieves notes by topic"],
    ]),
    sp(),

    h2("Documents"),
    cmd_table([
        ["(attach any PDF, Word, or image file)", "Bot reads it and asks what you'd like to do"],
        ["Summarize this document", "After uploading, summarize it"],
        ["What are the key risks in this report?", "Ask questions about an uploaded doc"],
        ["Generate a report based on this audit", "Generate a new Word/PDF doc from uploaded content"],
    ]),
    sp(),

    h2("Voice Messages"),
    cmd_table([
        ["(send any short voice note)", "Transcribed and executed as a command"],
        ["(send voice recording over 60 seconds)", "Auto-converted to formatted meeting minutes (.docx)"],
    ]),
    sp(),

    h2("Business Cards"),
    cmd_table([
        ["(send a photo of a business card)", "Extracts name, phone, email, company → sends .vcf file → tap to add to iPhone contacts"],
    ]),
    sp(),

    h2("Image / Screenshot Summarizer"),
    cmd_table([
        ["(send any photo — resume, screenshot, doc)", "Claude reads it and summarizes key content"],
        ["(send photo with caption: 'who is this person?')", "Caption used as the question; answered against the image"],
    ]),
    sp(),

    h2("URL Summarizer"),
    cmd_table([
        ["https://some-article.com — summarize this", "Fetches the page and summarizes it"],
    ]),
    sp(),

    h2("General Chat"),
    cmd_table([
        ["Draft a polite follow-up email to a client who hasn't responded", "General AI assistant request"],
        ["Clear memory", "Resets conversation history"],
    ]),
    PageBreak(),
]

# ── SECTION 3 ──────────────────────────────────────────────────────────────────
story += [
    h1("3. Setup Guide (First-Time Installation)"),
    hr(),
    h2("Prerequisites"),
    b("Windows 10/11 PC (the 'server' machine — must stay on)"),
    b("Python 3.11 or 3.12 installed — python.org"),
    b("Git installed — git-scm.com"),
    b("Tesseract OCR installed — github.com/UB-Mannheim/tesseract/wiki"),
    b("ffmpeg installed and on PATH — ffmpeg.org (needed for audio)"),
    sp(),

    h2("Step 1 — Clone the Repository"),
    code("git clone https://github.com/bilalaslam1244-stack/ClaudeCodeTest.git"),
    code("cd ClaudeCodeTest\\telegram-pa"),
    sp(),

    h2("Step 2 — Create Virtual Environment"),
    code("python -m venv venv"),
    code("venv\\Scripts\\activate"),
    code("pip install -r requirements.txt"),
    sp(),

    h2("Step 3 — Create .env File"),
    p("Copy <b>.env.example</b> to <b>.env</b> and fill in all values:"),
    code("copy .env.example .env"),
    p("Edit <b>.env</b> with your actual keys (see Section 4 and 5)."),
    sp(),

    h2("Step 4 — Set Up Google OAuth"),
    p("See Section 7 for the full Google OAuth walkthrough."),
    sp(),

    h2("Step 5 — Create the data folder"),
    code("mkdir data"),
    sp(),

    h2("Step 6 — Run the Bot"),
    code("python -m bot.main"),
    p("On first run you will be redirected to a Google login page in your browser. "
      "Log in with the boss's Google account and grant permissions. "
      "A <b>token.json</b> file will be saved in the data folder — this keeps you logged in."),
    sp(),
    note("Tip: Once running, set up Task Scheduler to auto-start the bot when the PC turns on (see Section 8)."),
    PageBreak(),
]

# ── SECTION 4 ──────────────────────────────────────────────────────────────────
story += [
    h1("4. Environment Variables Reference"),
    hr(),
    p("All variables go in the <b>.env</b> file inside the <b>telegram-pa</b> folder."),
    sp(),
    env_table([
        ["TELEGRAM_BOT_TOKEN",     "Yes",      "Bot token from @BotFather"],
        ["ANTHROPIC_API_KEY",      "Yes",      "Claude AI key from console.anthropic.com"],
        ["OPENAI_API_KEY",         "Yes",      "OpenAI key for Whisper transcription"],
        ["ALLOWED_USER_ID",        "Yes",      "Boss's Telegram numeric ID. For multiple users: 123,456"],
        ["BOSS_TIMEZONE",          "Yes",      "e.g. Asia/Kuala_Lumpur — used for all time calculations"],
        ["GOOGLE_CREDENTIALS_PATH","Yes",      "Path to Google OAuth credentials JSON (default: data/credentials.json)"],
        ["GOOGLE_TOKEN_PATH",      "Yes",      "Where to store the OAuth token (default: data/token.json)"],
        ["DB_PATH",                "Yes",      "SQLite database path (default: data/pa.db)"],
        ["CLAUDE_HAIKU_MODEL",     "No",       "Claude Haiku model ID (default: claude-haiku-4-5-20251001)"],
        ["CLAUDE_SONNET_MODEL",    "No",       "Claude Sonnet model ID (default: claude-sonnet-4-6)"],
        ["ZOOM_ACCOUNT_ID",        "No",       "Zoom Server-to-Server OAuth account ID"],
        ["ZOOM_CLIENT_ID",         "No",       "Zoom app client ID"],
        ["ZOOM_CLIENT_SECRET",     "No",       "Zoom app client secret"],
        ["TELEGRAM_LOCAL_API_URL", "No",       "Local Bot API URL to remove 20MB file limit (e.g. http://localhost:8081/bot)"],
    ]),
    PageBreak(),
]

# ── SECTION 5 ──────────────────────────────────────────────────────────────────
story += [
    h1("5. API Keys — Where to Get Them"),
    hr(),
    key_table([
        ["Telegram Bot Token",    "@BotFather on Telegram → /newbot → follow prompts → copy token"],
        ["Boss's Telegram ID",    "Message @userinfobot on Telegram — it replies with your numeric ID"],
        ["Anthropic API Key",     "console.anthropic.com → API Keys → Create Key"],
        ["OpenAI API Key",        "platform.openai.com → API Keys → Create new secret key"],
        ["Google OAuth creds",    "console.cloud.google.com → New project → Enable Gmail + Calendar APIs → Credentials → OAuth 2.0 Client → Desktop App → Download JSON → save as data/credentials.json"],
        ["Zoom Account ID",       "marketplace.zoom.us → Develop → Build App → Server-to-Server OAuth → note Account ID, Client ID, Client Secret"],
    ]),
    PageBreak(),
]

# ── SECTION 6 ──────────────────────────────────────────────────────────────────
story += [
    h1("6. Zoom Integration Setup"),
    hr(),
    p("When Zoom is configured, every calendar event the bot creates will automatically "
      "include a Zoom meeting link — in both the Telegram reply and the Google Calendar invite."),
    sp(),
    p("<b>Steps:</b>"),
    b("Go to marketplace.zoom.us and sign in with the boss's Zoom account"),
    b("Click Develop → Build App"),
    b("Choose Server-to-Server OAuth"),
    b("Give it any name (e.g. 'PA Bot')"),
    b("Copy the Account ID, Client ID, and Client Secret"),
    b("Under Scopes, add: meeting:write or meeting:write:admin"),
    b("Click Activate App"),
    b("Add the three values to .env as ZOOM_ACCOUNT_ID, ZOOM_CLIENT_ID, ZOOM_CLIENT_SECRET"),
    b("Restart the bot"),
    sp(),
    note("If Zoom credentials are not in .env, calendar events are created normally without a Zoom link. No errors."),
    PageBreak(),
]

# ── SECTION 7 ──────────────────────────────────────────────────────────────────
story += [
    h1("7. Google OAuth Setup (Gmail &amp; Calendar)"),
    hr(),
    p("The bot needs OAuth2 access to the boss's Gmail and Google Calendar. "
      "This is a one-time setup per Google account."),
    sp(),
    h2("Step 1 — Create a Google Cloud Project"),
    b("Go to console.cloud.google.com"),
    b("Click Select a project → New Project → give it any name → Create"),
    sp(),

    h2("Step 2 — Enable APIs"),
    b("In the project, go to APIs &amp; Services → Library"),
    b("Search for Gmail API → Enable"),
    b("Search for Google Calendar API → Enable"),
    sp(),

    h2("Step 3 — Create OAuth Credentials"),
    b("Go to APIs &amp; Services → Credentials → Create Credentials → OAuth 2.0 Client ID"),
    b("Application type: Desktop App"),
    b("Download the JSON file → rename it credentials.json → put in data/ folder"),
    sp(),

    h2("Step 4 — OAuth Consent Screen"),
    b("Go to APIs &amp; Services → OAuth consent screen"),
    b("User type: External"),
    b("Fill in App name (any name), support email"),
    b("Under Test users — add the boss's Gmail address"),
    b("Publishing status: leave as Testing (no need to publish)"),
    sp(),

    h2("Step 5 — First Run Authorization"),
    b("Start the bot: python -m bot.main"),
    b("A browser window opens asking to sign into Google"),
    b("Sign in with the boss's Google account"),
    b("Click Allow for Gmail and Calendar permissions"),
    b("A token.json is saved — bot stays logged in permanently"),
    sp(),
    note("token.json must be kept safe. If deleted, re-run the bot and go through the browser login again."),
    PageBreak(),
]

# ── SECTION 8 ──────────────────────────────────────────────────────────────────
story += [
    h1("8. Starting, Stopping &amp; Auto-Start"),
    hr(),

    h2("Start the Bot Manually"),
    code("cd C:\\path\\to\\ClaudeCodeTest\\telegram-pa"),
    code("venv\\Scripts\\activate"),
    code("python -m bot.main"),
    sp(),

    h2("Stop the Bot"),
    p("Press <b>Ctrl + C</b> in the terminal window. You may see a traceback — this is normal."),
    sp(),

    h2("Auto-Start with Windows Task Scheduler"),
    p("To have the bot start automatically when the PC turns on:"),
    b("Open Task Scheduler (search in Start menu)"),
    b("Click Create Basic Task → give it a name (e.g. 'PA Bot')"),
    b("Trigger: When the computer starts"),
    b("Action: Start a program"),
    b("Program: C:\\path\\to\\telegram-pa\\venv\\Scripts\\python.exe"),
    b("Arguments: -m bot.main"),
    b("Start in: C:\\path\\to\\telegram-pa"),
    b("Check: Run whether user is logged on or not"),
    b("Finish"),
    sp(),
    note("The PC must remain on for the bot to work. Putting it to sleep stops the bot."),
    PageBreak(),
]

# ── SECTION 9 ──────────────────────────────────────────────────────────────────
story += [
    h1("9. Transferring the Bot to a New Machine"),
    hr(),
    p("To move the bot to a different PC (e.g. the boss's dedicated desktop):"),
    sp(),
    b("Install Python 3.11+, Git, Tesseract OCR, and ffmpeg on the new machine"),
    b("Clone the repo: git clone https://github.com/bilalaslam1244-stack/ClaudeCodeTest.git"),
    b("cd ClaudeCodeTest\\telegram-pa"),
    b("python -m venv venv && venv\\Scripts\\activate && pip install -r requirements.txt"),
    b("Copy the .env file from the old machine"),
    b("Copy the data/ folder (contains credentials.json and token.json — keeps Google auth)"),
    b("Run: python -m bot.main"),
    b("Set up Task Scheduler again on the new machine (see Section 8)"),
    sp(),
    note("If you copy the data/ folder, Google login will NOT be needed again on the new machine."),
    PageBreak(),
]

# ── SECTION 10 ──────────────────────────────────────────────────────────────────
story += [
    h1("10. Costs Breakdown"),
    hr(),
    p("All costs are pay-as-you-go. There is no monthly subscription."),
    sp(),
    cmd_table([
        ["Anthropic (Claude AI)",  "~$5–15/month depending on usage. Intent classification uses cheap Haiku model. Doc generation uses Sonnet."],
        ["OpenAI (Whisper)",       "~$0.006 per minute of audio. A 30-min meeting = ~$0.18. Light use = under $2/month."],
        ["Google APIs",            "Gmail and Calendar APIs are free within generous quota limits."],
        ["Zoom API",               "Free — Server-to-Server OAuth is included in all Zoom plans."],
        ["Telegram Bot API",       "Free."],
        ["Electricity (PC)",       "Depends on PC. A modern desktop = ~$10–20/month running 24/7."],
        ["Internet",               "Minimal data usage — API calls only, no video/streaming."],
    ]),
    sp(),
    note("Estimated total API cost for a busy executive: USD $10–25/month."),
    PageBreak(),
]

# ── SECTION 11 ──────────────────────────────────────────────────────────────────
story += [
    h1("11. Troubleshooting"),
    hr(),
    cmd_table([
        ["Bot not responding",              "Check the terminal for errors. Ensure venv is active and .env has correct keys. Restart: Ctrl+C then python -m bot.main"],
        ["'Access Required' or 'no access' messages", "Type 'clear memory' in the bot. Old messages were cached. Bot has full Gmail + Calendar access."],
        ["Bot crashes on large audio files", "File exceeds Telegram's 20MB limit. Set up the local Telegram Bot API server to remove this limit."],
        ["Google auth expired",             "Delete data/token.json and restart the bot. Browser login will appear again."],
        ["Zoom link not appearing",         "Check ZOOM_ACCOUNT_ID, ZOOM_CLIENT_ID, ZOOM_CLIENT_SECRET are in .env. Restart bot."],
        ["Business card scan sends no .vcf","Ensure the photo is clear and well-lit. Blurry cards may not be detected."],
        ["Daily overview not arriving at 7 AM", "Check BOSS_TIMEZONE in .env is correct. PC must be on and bot running."],
        ["Email mute not working",          "Say 'mute [keyword]' exactly. Check with 'what are my muted senders'."],
        ["Bot not reading PDF correctly",   "Large/scanned PDFs use OCR (Tesseract). Ensure Tesseract is installed and on PATH."],
        ["KeyboardInterrupt traceback on stop", "Normal behaviour when pressing Ctrl+C. Not an error."],
    ]),
]

# ── BUILD ───────────────────────────────────────────────────────────────────────
doc = SimpleDocTemplate(
    OUTPUT,
    pagesize=A4,
    leftMargin=MARGIN,
    rightMargin=MARGIN,
    topMargin=MARGIN,
    bottomMargin=MARGIN,
    title="Telegram PA Bot Manual",
    author="PA Bot",
)
doc.build(story)
print(f"Generated: {OUTPUT}")
