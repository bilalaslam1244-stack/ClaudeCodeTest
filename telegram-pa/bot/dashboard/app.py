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

app = FastAPI(docs_url=None, redoc_url=None)

DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "8080"))


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


@app.get("/api/status")
async def get_status() -> JSONResponse:
    reminders = []
    muted = []
    recent_emails = []
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT description, remind_at FROM reminders WHERE status='pending' ORDER BY remind_at LIMIT 20"
            ) as cur:
                rows = await cur.fetchall()
                reminders = [{"description": r["description"], "remind_at": r["remind_at"]} for r in rows]
            async with db.execute(
                "SELECT pattern, created_at FROM muted_senders ORDER BY created_at"
            ) as cur:
                rows = await cur.fetchall()
                muted = [{"pattern": r["pattern"], "added": r["created_at"][:10]} for r in rows]
            async with db.execute(
                "SELECT sender, subject, received_at FROM email_cache ORDER BY received_at DESC LIMIT 10"
            ) as cur:
                rows = await cur.fetchall()
                recent_emails = [
                    {"sender": r["sender"], "subject": r["subject"], "received": r["received_at"][:16]}
                    for r in rows
                ]
    except Exception:
        pass

    api_keys = {
        "Telegram": bool(TELEGRAM_BOT_TOKEN),
        "Anthropic (Claude)": bool(ANTHROPIC_API_KEY),
        "OpenAI (Whisper)": bool(OPENAI_API_KEY),
        "SerpApi (Flights)": bool(SERPAPI_KEY),
        "Zoom": bool(ZOOM_ACCOUNT_ID),
    }

    return JSONResponse({
        "status": "online",
        "uptime": _uptime_str(get_start_time()),
        "started_at": get_start_time().strftime("%Y-%m-%d %H:%M UTC"),
        "error_count": get_error_count(),
        "reminders": reminders,
        "muted_senders": muted,
        "recent_emails": recent_emails,
        "api_keys": api_keys,
        "logs": get_logs()[:150],
    })


@app.get("/", response_class=HTMLResponse)
async def dashboard() -> HTMLResponse:
    return HTMLResponse(_HTML)


_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AKFA PA Bot Dashboard</title>
<style>
  :root {
    --bg: #0f1117;
    --surface: #1a1d27;
    --border: #2a2d3a;
    --text: #e2e8f0;
    --muted: #8892a4;
    --green: #22c55e;
    --red: #ef4444;
    --yellow: #f59e0b;
    --blue: #3b82f6;
    --purple: #8b5cf6;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; font-size: 14px; }
  header { background: var(--surface); border-bottom: 1px solid var(--border); padding: 16px 24px; display: flex; align-items: center; justify-content: space-between; }
  header h1 { font-size: 18px; font-weight: 600; letter-spacing: 0.02em; }
  header .subtitle { color: var(--muted); font-size: 12px; margin-top: 2px; }
  .refresh-info { color: var(--muted); font-size: 12px; text-align: right; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; padding: 20px 24px; }
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 18px; }
  .card h2 { font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); margin-bottom: 14px; }
  .stat-row { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
  .dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
  .dot.green { background: var(--green); box-shadow: 0 0 6px var(--green); }
  .dot.red { background: var(--red); }
  .stat-label { color: var(--muted); min-width: 100px; }
  .stat-value { font-weight: 500; }
  .stat-value.big { font-size: 28px; font-weight: 700; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 600; }
  .badge.green { background: rgba(34,197,94,0.15); color: var(--green); }
  .badge.red { background: rgba(239,68,68,0.15); color: var(--red); }
  .badge.yellow { background: rgba(245,158,11,0.15); color: var(--yellow); }
  .key-row { display: flex; align-items: center; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid var(--border); }
  .key-row:last-child { border-bottom: none; }
  table { width: 100%; border-collapse: collapse; }
  th { text-align: left; font-size: 11px; color: var(--muted); font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; padding: 0 0 8px; }
  td { padding: 6px 0; border-bottom: 1px solid var(--border); font-size: 13px; vertical-align: top; }
  tr:last-child td { border-bottom: none; }
  .td-small { color: var(--muted); font-size: 11px; }
  .log-wrap { max-height: 380px; overflow-y: auto; }
  .log-entry { display: flex; gap: 10px; padding: 4px 0; border-bottom: 1px solid rgba(255,255,255,0.04); font-family: 'SF Mono', 'Consolas', monospace; font-size: 12px; }
  .log-entry:last-child { border-bottom: none; }
  .log-time { color: var(--muted); flex-shrink: 0; }
  .log-level { flex-shrink: 0; width: 54px; font-weight: 600; }
  .log-level.INFO { color: var(--blue); }
  .log-level.WARNING { color: var(--yellow); }
  .log-level.ERROR, .log-level.CRITICAL { color: var(--red); }
  .log-level.DEBUG { color: var(--muted); }
  .log-msg { color: var(--text); word-break: break-all; }
  .empty { color: var(--muted); font-style: italic; padding: 8px 0; }
  .full-width { grid-column: 1 / -1; }
  .error-num { color: var(--red); font-weight: 700; }
  .spinner { display: inline-block; width: 10px; height: 10px; border: 2px solid var(--border); border-top-color: var(--blue); border-radius: 50%; animation: spin 0.8s linear infinite; margin-right: 6px; }
  @keyframes spin { to { transform: rotate(360deg); } }
  ::-webkit-scrollbar { width: 4px; } ::-webkit-scrollbar-track { background: transparent; } ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
</style>
</head>
<body>
<header>
  <div>
    <h1>&#x1F916; AKFA PA Bot Dashboard</h1>
    <div class="subtitle" id="started-at">Loading...</div>
  </div>
  <div class="refresh-info">
    <span id="refresh-spinner" class="spinner"></span>
    Auto-refreshes every 30s &nbsp;|&nbsp; <span id="last-updated">—</span>
  </div>
</header>

<div class="grid">

  <!-- Status card -->
  <div class="card">
    <h2>Bot Status</h2>
    <div class="stat-row">
      <div class="dot green" id="status-dot"></div>
      <span class="stat-value" id="status-text">Online</span>
    </div>
    <div class="stat-row">
      <span class="stat-label">Uptime</span>
      <span class="stat-value" id="uptime">—</span>
    </div>
    <div class="stat-row">
      <span class="stat-label">Errors logged</span>
      <span class="stat-value" id="error-count">—</span>
    </div>
  </div>

  <!-- API Keys card -->
  <div class="card">
    <h2>Services &amp; API Keys</h2>
    <div id="api-keys-list"></div>
  </div>

  <!-- Muted senders -->
  <div class="card">
    <h2>Muted Email Senders</h2>
    <div id="muted-list"></div>
  </div>

  <!-- Pending reminders -->
  <div class="card">
    <h2>Pending Reminders</h2>
    <div id="reminders-list"></div>
  </div>

  <!-- Recent emails -->
  <div class="card">
    <h2>Recent Emails (Cache)</h2>
    <div id="emails-list"></div>
  </div>

  <!-- Logs — full width -->
  <div class="card full-width">
    <h2>Activity Log (latest 150 entries)</h2>
    <div class="log-wrap" id="log-entries"></div>
  </div>

</div>

<script>
async function refresh() {
  const spinner = document.getElementById('refresh-spinner');
  spinner.style.display = 'inline-block';
  try {
    const res = await fetch('/api/status');
    const d = await res.json();

    document.getElementById('started-at').textContent = 'Started: ' + d.started_at;
    document.getElementById('uptime').textContent = d.uptime;

    const ec = d.error_count;
    const ecEl = document.getElementById('error-count');
    ecEl.textContent = ec;
    ecEl.className = 'stat-value' + (ec > 0 ? ' error-num' : '');

    document.getElementById('last-updated').textContent = 'Updated ' + new Date().toLocaleTimeString();

    // API keys
    const keysList = document.getElementById('api-keys-list');
    keysList.innerHTML = '';
    for (const [name, ok] of Object.entries(d.api_keys)) {
      const row = document.createElement('div');
      row.className = 'key-row';
      row.innerHTML = '<span>' + name + '</span>' +
        '<span class="badge ' + (ok ? 'green' : 'red') + '">' + (ok ? 'Configured' : 'Missing') + '</span>';
      keysList.appendChild(row);
    }

    // Muted senders
    const mutedList = document.getElementById('muted-list');
    if (!d.muted_senders.length) {
      mutedList.innerHTML = '<div class="empty">No senders muted</div>';
    } else {
      let html = '<table><thead><tr><th>Pattern</th><th>Added</th></tr></thead><tbody>';
      for (const m of d.muted_senders) {
        html += '<tr><td>' + esc(m.pattern) + '</td><td class="td-small">' + esc(m.added) + '</td></tr>';
      }
      mutedList.innerHTML = html + '</tbody></table>';
    }

    // Reminders
    const remindersList = document.getElementById('reminders-list');
    if (!d.reminders.length) {
      remindersList.innerHTML = '<div class="empty">No pending reminders</div>';
    } else {
      let html = '<table><thead><tr><th>Description</th><th>Due</th></tr></thead><tbody>';
      for (const r of d.reminders) {
        const due = r.remind_at.replace('T', ' ').replace('Z', '').slice(0, 16);
        html += '<tr><td>' + esc(r.description) + '</td><td class="td-small">' + esc(due) + '</td></tr>';
      }
      remindersList.innerHTML = html + '</tbody></table>';
    }

    // Recent emails
    const emailsList = document.getElementById('emails-list');
    if (!d.recent_emails.length) {
      emailsList.innerHTML = '<div class="empty">No cached emails</div>';
    } else {
      let html = '<table><thead><tr><th>From</th><th>Subject</th></tr></thead><tbody>';
      for (const e of d.recent_emails) {
        html += '<tr><td class="td-small">' + esc(e.sender.replace(/<.*>/, '').trim()) + '</td><td>' + esc(e.subject) + '</td></tr>';
      }
      emailsList.innerHTML = html + '</tbody></table>';
    }

    // Logs
    const logEntries = document.getElementById('log-entries');
    if (!d.logs.length) {
      logEntries.innerHTML = '<div class="empty">No log entries yet</div>';
    } else {
      let html = '';
      for (const l of d.logs) {
        html += '<div class="log-entry">' +
          '<span class="log-time">' + l.time.slice(11) + '</span>' +
          '<span class="log-level ' + l.level + '">' + l.level + '</span>' +
          '<span class="log-msg">[' + esc(l.name) + '] ' + esc(l.message) + '</span>' +
          '</div>';
      }
      logEntries.innerHTML = html;
    }

  } catch (err) {
    document.getElementById('status-dot').className = 'dot red';
    document.getElementById('status-text').textContent = 'Unreachable';
  } finally {
    spinner.style.display = 'none';
  }
}

function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

refresh();
setInterval(refresh, 30000);
</script>
</body>
</html>"""
