import urllib.parse
from datetime import datetime

import httpx

from bot.config import SERPAPI_KEY


def _fmt_display_date(iso_date: str) -> str:
    try:
        return datetime.strptime(iso_date, "%Y-%m-%d").strftime("%d %b %Y")
    except Exception:
        return iso_date


def _yymmdd(iso_date: str) -> str:
    """Convert YYYY-MM-DD to YYMMDD for Skyscanner URLs."""
    return iso_date[2:4] + iso_date[5:7] + iso_date[8:10]


def google_flights_url(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str = "",
    adults: int = 1,
) -> str:
    if return_date:
        q = f"flights from {origin} to {destination} on {departure_date} returning {return_date}"
    else:
        q = f"one way flights from {origin} to {destination} on {departure_date}"
    return f"https://www.google.com/travel/flights?q={urllib.parse.quote(q)}"


def skyscanner_url(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str = "",
    adults: int = 1,
) -> str:
    dep = _yymmdd(departure_date)
    o = origin.upper()
    d = destination.upper()
    if return_date:
        ret = _yymmdd(return_date)
        return f"https://www.skyscanner.com/transport/flights/{o}/{d}/{dep}/{ret}/?adults={adults}&rtn=1"
    return f"https://www.skyscanner.com/transport/flights/{o}/{d}/{dep}/?adults={adults}&rtn=0"


async def search_prices(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str = "",
    adults: int = 1,
    currency: str = "MYR",
) -> list[dict]:
    if not SERPAPI_KEY:
        return []
    params = {
        "engine": "google_flights",
        "departure_id": origin.upper(),
        "arrival_id": destination.upper(),
        "outbound_date": departure_date,
        "currency": currency,
        "hl": "en",
        "adults": adults,
        "api_key": SERPAPI_KEY,
        "type": "1" if return_date else "2",
    }
    if return_date:
        params["return_date"] = return_date

    async with httpx.AsyncClient() as client:
        resp = await client.get("https://serpapi.com/search", params=params, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()

    results = []
    for offer in data.get("best_flights", []) + data.get("other_flights", []):
        flights = offer.get("flights", [])
        if not flights:
            continue
        first = flights[0]
        last = flights[-1]
        price = offer.get("price")
        airline = first.get("airline", "")
        dep_time = first.get("departure_airport", {}).get("time", "")[-5:]
        arr_time = last.get("arrival_airport", {}).get("time", "")[-5:]
        stops = len(flights) - 1
        duration_min = offer.get("total_duration", 0)
        hours, mins = divmod(duration_min, 60)
        duration = f"{hours}h {mins}m"
        results.append({
            "airline": airline,
            "price": price,
            "dep_time": dep_time,
            "arr_time": arr_time,
            "stops": stops,
            "duration": duration,
        })

    results.sort(key=lambda x: x["price"] or 99999)
    return results[:5]


def build_message(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str = "",
    adults: int = 1,
    price_results: list[dict] | None = None,
    currency: str = "MYR",
) -> str:
    trip_type = "Return" if return_date else "One-way"
    lines = [
        f"✈️ {trip_type}: {origin.upper()} → {destination.upper()}",
        f"Departure: {_fmt_display_date(departure_date)}",
    ]
    if return_date:
        lines.append(f"Return: {_fmt_display_date(return_date)}")
    if adults > 1:
        lines.append(f"Passengers: {adults}")

    if price_results:
        lines.append("")
        lines.append("Cheapest options:")
        for i, r in enumerate(price_results, 1):
            stops_label = "Direct" if r["stops"] == 0 else f"{r['stops']} stop(s)"
            price_str = f"{currency} {r['price']:,}" if r["price"] else "—"
            lines.append(
                f"{i}. {r['airline']} — {price_str}\n"
                f"   {r['dep_time']} → {r['arr_time']} ({r['duration']}, {stops_label})"
            )
    else:
        lines.append("")
        lines.append("Tap below to see live prices and book:")

    return "\n".join(lines)
