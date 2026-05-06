import os
from datetime import datetime, timezone

import aiosqlite
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from bot.config import (
    ANTHROPIC_API_KEY,
    DB_PATH,
    OPENAI_API_KEY,
    SERPAPI_KEY,
    TELEGRAM_BOT_TOKEN,
    ZOOM_ACCOUNT_ID,
)
from bot.dashboard.log_buffer import get_error_count, get_logs, get_start_time

DASHBOARD_PORT: int = int(os.getenv("DASHBOARD_PORT", "8080"))

app = FastAPI(docs_url=None, redoc_url=None)

# ── HTML template ──────────────────────────────────────────────────────────────

_HTML = (
    "<!DOCTYPE html>"
    '<html lang="en">'
    "<head>"
    '<meta charset="UTF-8">'
    '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
    "<title>AKFA PA Bot Dashboard</title>"
    "<style>"
    ":root{"
    "--bg:#0f1117;--surface:#1a1d27;--border:#2a2d3a;--text:#e2e8f0;--muted:#8892a4;"
    "--green:#22c55e;--red:#ef4444;--yellow:#f59e0b;--blue:#3b82f6;"
    "}"
    "*{box-sizing:border-box;margin:0;padding:0}"
    "body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:14px}"
    "header{background:var(--surface);border-bottom:1px solid var(--border);padding:16px 24px;display:flex;align-items:center;justify-content:space-between}"
    "header h1{font-size:18px;font-weight:600}"
    ".sub{color:var(--muted);font-size:12px;margin-top:2px}"
    ".rinfo{color:var(--muted);font-size:12px;text-align:right}"
    ".grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px;padding:20px 24px}"
    ".card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:18px}"
    ".card h2{font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin-bottom:14px}"
    ".srow{display:flex;align-items:center;gap:10px;margin-bottom:10px}"
    ".dot{width:10px;height:10px;border-radius:50%;flex-shrink:0}"
    ".dot.g{background:var(--green);box-shadow:0 0 6px var(--green)}"
    ".dot.r{background:var(--red)}"
    ".sl{color:var(--muted);min-width:100px}"
    ".sv{font-weight:500}"
    ".badge{display:inline-block;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600}"
    ".badge.g{background:rgba(34,197,94,.15);color:var(--green)}"
    ".badge.r{background:rgba(239,68,68,.15);color:var(--red)}"
    ".badge.yellow{background:rgba(245,158,11,.15);color:var(--yellow)}"
    ".krow{display:flex;align-items:center;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border)}"
    ".krow:last-child{border-bottom:none}"
    "table{width:100%;border-collapse:collapse}"
    "th{text-align:left;font-size:11px;color:var(--muted);font-weight:600;text-transform:uppercase;letter-spacing:.06em;padding:0 0 8px}"
    "td{padding:6px 0;border-bottom:1px solid var(--border);font-size:13px;vertical-align:top}"
    "tr:last-child td{border-bottom:none}"
    ".ts{color:var(--muted);font-size:11px}"
    ".lw{max-height:380px;overflow-y:auto}"
    ".le{display:flex;gap:10px;padding:4px 0;border-bottom:1px solid rgba(255,255,255,.04);font-family:Consolas,monospace;font-size:12px}"
    ".le:last-child{border-bottom:none}"
    ".lt{color:var(--muted);flex-shrink:0}"
    ".ll{flex-shrink:0;width:54px;font-weight:600}"
    ".ll.INFO{color:var(--blue)}"
    ".ll.WARNING{color:var(--yellow)}"
    ".ll.ERROR,.ll.CRITICAL{color:var(--red)}"
    ".ll.DEBUG{color:var(--muted)}"
    ".lm{color:var(--text);word-break:break-all}"
    ".empty{color:var(--muted);font-style:italic;padding:8px 0}"
    ".fw{grid-column:1/-1}"
    ".err{color:var(--red);font-weight:700}"
    ".sp{display:inline-block;width:10px;height:10px;border:2px solid var(--border);border-top-color:var(--blue);border-radius:50%;animation:spin .8s linear infinite;margin-right:6px}"
    "@keyframes spin{to{transform:rotate(360deg)}}"
    "::-webkit-scrollbar{width:4px}"
    "::-webkit-scrollbar-thumb{background:var(--border);border-radius:2px}"
    "</style>"
    "</head>"
    "<body>"
    "<header>"
    "<div><h1>&#x1F916; AKFA PA Bot Dashboard</h1>"
    '<div class="sub" id="started-at">Loading...</div></div>'
    '<div class="rinfo"><span id="sp" class="sp"></span>Auto-refreshes every 30s &nbsp;|&nbsp; <span id="lu">-</span></div>'
    "</header>"
    '<div class="grid">'
    '<div class="card"><h2>Bot Status</h2>'
    '<div class="srow"><div class="dot g" id="sdot"></div><span class="sv" id="stxt">Online</span></div>'
    '<div class="srow"><span class="sl">Uptime</span><span class="sv" id="up">-</span></div>'
    '<div class="srow"><span class="sl">Errors logged</span><span class="sv" id="ec">-</span></div>'
    "</div>"
    '<div class="card"><h2>Services &amp; API Keys</h2><div id="keys"></div></div>'
    '<div class="card"><h2>Muted Email Senders</h2><div id="muted"></div></div>'
    '<div class="card"><h2>Pending Reminders</h2><div id="reminders"></div></div>'
    '<div class="card"><h2>Recent Emails (Cache)</h2><div id="emails"></div></div>'
    '<div class="card fw"><h2>User Activity (Last 100 Tasks)</h2><div class="lw" id="activity"></div></div>'
    '<div class="card fw"><h2>System Log</h2><div class="lw" id="logs"></div></div>'
    "</div>"
    "<script>"
    "function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}"
    "async function refresh(){"
    "document.getElementById('sp').style.display='inline-block';"
    "try{"
    "const d=await fetch('/api/status').then(r=>r.json());"
    "document.getElementById('started-at').textContent='Started: '+d.started_at;"
    "document.getElementById('up').textContent=d.uptime;"
    "const ec=d.error_count;"
    "const el=document.getElementById('ec');"
    "el.textContent=ec;el.className='sv'+(ec>0?' err':'');"
    "document.getElementById('lu').textContent='Updated '+new Date().toLocaleTimeString();"
    "const kd=document.getElementById('keys');kd.innerHTML='';"
    "for(const[n,ok]of Object.entries(d.api_keys)){"
    "const r=document.createElement('div');r.className='krow';"
    "r.innerHTML='<span>'+esc(n)+'</span><span class=\"badge '+(ok?'g':'r')+'\">'+(ok?'Configured':'Missing')+'</span>';"
    "kd.appendChild(r)}"
    "const md=document.getElementById('muted');"
    "if(!d.muted_senders.length){md.innerHTML='<div class=\"empty\">No senders muted</div>'}"
    "else{let h='<table><thead><tr><th>Pattern</th><th>Added</th></tr></thead><tbody>';"
    "for(const m of d.muted_senders)h+='<tr><td>'+esc(m.pattern)+'</td><td class=\"ts\">'+esc(m.added)+'</td></tr>';"
    "md.innerHTML=h+'</tbody></table>'}"
    "const rd=document.getElementById('reminders');"
    "if(!d.reminders.length){rd.innerHTML='<div class=\"empty\">No pending reminders</div>'}"
    "else{let h='<table><thead><tr><th>Description</th><th>Due (UTC)</th></tr></thead><tbody>';"
    "for(const r of d.reminders)h+='<tr><td>'+esc(r.description)+'</td><td class=\"ts\">'+esc(r.remind_at.slice(0,16).replace('T',' '))+'</td></tr>';"
    "rd.innerHTML=h+'</tbody></table>'}"
    "const ed=document.getElementById('emails');"
    "if(!d.recent_emails.length){ed.innerHTML='<div class=\"empty\">No cached emails</div>'}"
    "else{let h='<table><thead><tr><th>From</th><th>Subject</th></tr></thead><tbody>';"
    "for(const e of d.recent_emails)h+='<tr><td class=\"ts\">'+esc(e.sender.replace(/<.*>/,'').trim())+'</td><td>'+esc(e.subject)+'</td></tr>';"
    "ed.innerHTML=h+'</tbody></table>'}"
    "const ad=document.getElementById('activity');"
    "if(!d.activity||!d.activity.length){ad.innerHTML='<div class=\"empty\">No activity yet — send a message to the bot</div>'}"
    "else{let h='<table><thead><tr><th>Time (UTC)</th><th>Intent</th><th>Confidence</th><th>Status</th><th>Message</th></tr></thead><tbody>';"
    "for(const a of d.activity){"
    "const sc=a.status==='ok'?'g':a.status==='low_confidence'?'yellow':'r';"
    "h+='<tr><td class=\"ts\">'+esc(a.timestamp.slice(0,16).replace('T',' '))+'</td>';"
    "h+='<td><b>'+esc(a.intent)+'</b></td>';"
    "h+='<td class=\"ts\">'+(a.confidence*100).toFixed(0)+'%</td>';"
    "h+='<td><span class=\"badge '+sc+'\">'+esc(a.status)+'</span></td>';"
    "h+='<td class=\"ts\">'+esc(a.message)+'</td></tr>';}"
    "ad.innerHTML=h+'</tbody></table>'}"
    "const ld=document.getElementById('logs');"
    "if(!d.logs.length){ld.innerHTML='<div class=\"empty\">No log entries yet</div>'}"
    "else{let h='';"
    "for(const l of d.logs)h+='<div class=\"le\"><span class=\"lt\">'+esc(l.time.slice(11))+'</span><span class=\"ll '+l.level+'\">'+l.level+'</span><span class=\"lm\">['+esc(l.name)+'] '+esc(l.message)+'</span></div>';"
    "ld.innerHTML=h}"
    "}catch(e){"
    "document.getElementById('sdot').className='dot r';"
    "document.getElementById('stxt').textContent='Unreachable';"
    "}finally{document.getElementById('sp').style.display='none'}"
    "}"
    "refresh();setInterval(refresh,30000);"
    "</script>"
    "</body></html>"
)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/ping")
async def ping() -> dict:
    return {"status": "ok"}


@app.get("/api/status")
async def get_status() -> dict:
    reminders: list[dict] = []
    muted: list[dict] = []
    recent_emails: list[dict] = []
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT description, remind_at FROM reminders WHERE status='pending' ORDER BY remind_at LIMIT 20"
            ) as cur:
                reminders = [{"description": r["description"], "remind_at": r["remind_at"]} for r in await cur.fetchall()]
            async with db.execute(
                "SELECT pattern, created_at FROM muted_senders ORDER BY created_at"
            ) as cur:
                muted = [{"pattern": r["pattern"], "added": r["created_at"][:10]} for r in await cur.fetchall()]
            async with db.execute(
                "SELECT sender, subject, received_at FROM email_cache ORDER BY received_at DESC LIMIT 10"
            ) as cur:
                recent_emails = [
                    {"sender": r["sender"], "subject": r["subject"], "received": r["received_at"][:16]}
                    for r in await cur.fetchall()
                ]
    except Exception:
        pass

    activity: list[dict] = []
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT timestamp, intent, confidence, message, status FROM activity_log ORDER BY id DESC LIMIT 100"
            ) as cur:
                activity = [dict(r) for r in await cur.fetchall()]
    except Exception:
        pass

    api_keys = {
        "Telegram": bool(TELEGRAM_BOT_TOKEN),
        "Anthropic (Claude)": bool(ANTHROPIC_API_KEY),
        "OpenAI (Whisper)": bool(OPENAI_API_KEY),
        "SerpApi (Flights)": bool(SERPAPI_KEY),
        "Zoom": bool(ZOOM_ACCOUNT_ID),
    }

    return {
        "status": "online",
        "uptime": _uptime_str(get_start_time()),
        "started_at": get_start_time().strftime("%Y-%m-%d %H:%M UTC"),
        "error_count": get_error_count(),
        "reminders": reminders,
        "muted_senders": muted,
        "recent_emails": recent_emails,
        "api_keys": api_keys,
        "activity": activity,
        "logs": get_logs()[:150],
    }


@app.get("/", response_class=HTMLResponse)
async def dashboard() -> HTMLResponse:
    return HTMLResponse(content=_HTML)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _uptime_str(start: datetime) -> str:
    delta = datetime.now(timezone.utc) - start
    days = delta.days
    hours, rem = divmod(delta.seconds, 3600)
    minutes, _ = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)
