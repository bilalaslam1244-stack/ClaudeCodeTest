import time
import httpx
from bot.config import AMADEUS_API_KEY, AMADEUS_API_SECRET, AMADEUS_BASE_URL

_token: str = ""
_token_expiry: float = 0.0


async def _get_token() -> str:
    global _token, _token_expiry
    if _token and time.time() < _token_expiry - 60:
        return _token
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{AMADEUS_BASE_URL}/v1/security/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": AMADEUS_API_KEY,
                "client_secret": AMADEUS_API_SECRET,
            },
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
    _token = data["access_token"]
    _token_expiry = time.time() + data["expires_in"]
    return _token


async def search_flights(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str = "",
    adults: int = 1,
    currency: str = "MYR",
    max_results: int = 5,
) -> list[dict]:
    token = await _get_token()
    params: dict = {
        "originLocationCode": origin.upper(),
        "destinationLocationCode": destination.upper(),
        "departureDate": departure_date,
        "adults": adults,
        "max": max_results,
        "currencyCode": currency,
    }
    if return_date:
        params["returnDate"] = return_date

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{AMADEUS_BASE_URL}/v2/shopping/flight-offers",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
            timeout=20.0,
        )
        resp.raise_for_status()
        data = resp.json()

    carriers = data.get("dictionaries", {}).get("carriers", {})
    return [_parse_offer(o, carriers) for o in data.get("data", [])[:max_results]]


def _parse_duration(iso: str) -> str:
    iso = iso.replace("PT", "")
    h = m = 0
    if "H" in iso:
        parts = iso.split("H")
        h = int(parts[0])
        iso = parts[1]
    if "M" in iso:
        m = int(iso.replace("M", ""))
    return f"{h}h {m}m" if h else f"{m}m"


def _fmt_time(dt_str: str) -> str:
    if not dt_str:
        return "?"
    return dt_str[11:16]


def _fmt_date(dt_str: str) -> str:
    if not dt_str:
        return "?"
    return dt_str[:10]


def _parse_offer(offer: dict, carriers: dict) -> dict:
    price = offer.get("price", {})
    total = price.get("grandTotal", "?")
    currency = price.get("currency", "")

    itineraries = offer.get("itineraries", [])
    outbound = itineraries[0] if itineraries else {}
    inbound = itineraries[1] if len(itineraries) > 1 else None

    segments = outbound.get("segments", [])
    stops = len(segments) - 1
    duration = _parse_duration(outbound.get("duration", "PT0H"))

    first = segments[0] if segments else {}
    last = segments[-1] if segments else {}

    dep_dt = first.get("departure", {}).get("at", "")
    arr_dt = last.get("arrival", {}).get("at", "")
    carrier_code = first.get("carrierCode", "")
    carrier_name = carriers.get(carrier_code, carrier_code)

    result = {
        "airline": carrier_name,
        "price": f"{currency} {total}",
        "dep_date": _fmt_date(dep_dt),
        "dep_time": _fmt_time(dep_dt),
        "arr_time": _fmt_time(arr_dt),
        "duration": duration,
        "stops": stops,
    }

    if inbound:
        in_segs = inbound.get("segments", [])
        in_first = in_segs[0] if in_segs else {}
        in_last = in_segs[-1] if in_segs else {}
        result["return_dep"] = _fmt_time(in_first.get("departure", {}).get("at", ""))
        result["return_arr"] = _fmt_time(in_last.get("arrival", {}).get("at", ""))
        result["return_duration"] = _parse_duration(inbound.get("duration", "PT0H"))
        result["return_stops"] = len(in_segs) - 1

    return result


def format_results(
    offers: list[dict],
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str = "",
) -> str:
    if not offers:
        return f"No flights found from {origin} to {destination} on {departure_date}."

    trip = "Return" if return_date else "One-way"
    lines = [f"✈️ {trip}: {origin.upper()} → {destination.upper()} | {departure_date}"]
    if return_date:
        lines[0] += f" → {return_date}"
    lines.append("")

    for i, o in enumerate(offers, 1):
        stops_label = "Direct" if o["stops"] == 0 else f"{o['stops']} stop(s)"
        lines.append(
            f"{i}. {o['airline']}\n"
            f"   {o['dep_time']} → {o['arr_time']} ({o['duration']}, {stops_label})\n"
            f"   💰 {o['price']}"
        )
        if o.get("return_dep"):
            ret_stops = "Direct" if o["return_stops"] == 0 else f"{o['return_stops']} stop(s)"
            lines.append(
                f"   ↩️ Return: {o['return_dep']} → {o['return_arr']} ({o['return_duration']}, {ret_stops})"
            )
        lines.append("")

    return "\n".join(lines).strip()


def google_flights_url(origin: str, destination: str, departure_date: str, return_date: str = "") -> str:
    date_str = departure_date.replace("-", "")
    if return_date:
        ret_str = return_date.replace("-", "")
        return (
            f"https://www.google.com/travel/flights/search?"
            f"tfs=CBwQAhoeEgoyMDI2LTA1LTE1agcIARIDREFZcgcIARIDQ01C"
        )
    q = f"flights from {origin} to {destination} on {departure_date}"
    import urllib.parse
    return f"https://www.google.com/travel/flights?q={urllib.parse.quote(q)}"
