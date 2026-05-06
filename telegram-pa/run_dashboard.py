"""Standalone dashboard runner — works even when the bot is offline."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import uvicorn
from bot.dashboard.app import app, DASHBOARD_PORT

if __name__ == "__main__":
    print(f"Dashboard running at http://0.0.0.0:{DASHBOARD_PORT}")
    print("Open http://localhost:{} in your browser".format(DASHBOARD_PORT))
    uvicorn.run(app, host="0.0.0.0", port=DASHBOARD_PORT, log_level="info")
