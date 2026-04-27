import urllib.parse
from datetime import datetime


def _fmt_display_date(iso_date: str) -> str:
    try:
        return datetime.strptime(iso_date, "%Y-%m-%d").strftime("%-d %b %Y")
    except Exception:
        return iso_date


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
        q = f"flights from {origin} to {destination} on {departure_date}"
    return f"https://www.google.com/travel/flights?q={urllib.parse.quote(q)}"


def skyscanner_url(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str = "",
    adults: int = 1,
) -> str:
    dep = departure_date.replace("-", "")
    if return_date:
        ret = return_date.replace("-", "")
        path = f"{origin.upper()}/{destination.upper()}/{dep}/{ret}/{adults}"
    else:
        path = f"{origin.upper()}/{destination.upper()}/{dep}/{adults}"
    return f"https://www.skyscanner.com/transport/flights/{path}/?adultsv2={adults}"


def build_message(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str = "",
    adults: int = 1,
) -> str:
    trip_type = "Return trip" if return_date else "One-way"
    dep_display = _fmt_display_date(departure_date)
    lines = [
        f"✈️ {trip_type}: {origin.upper()} → {destination.upper()}",
        f"Departure: {dep_display}",
    ]
    if return_date:
        lines.append(f"Return: {_fmt_display_date(return_date)}")
    if adults > 1:
        lines.append(f"Passengers: {adults}")
    lines.append("")
    lines.append("Tap a button below to see live prices and book:")
    return "\n".join(lines)
