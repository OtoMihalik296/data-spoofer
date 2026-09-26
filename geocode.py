"""Reverse geocode lat/lon → city, country (Nominatim / OpenStreetMap)."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from functools import lru_cache

NOMINATIM = "https://nominatim.openstreetmap.org/reverse"
USER_AGENT = "DataSpoofer/1.0 (local metadata tool)"


def _pick_city(address: dict) -> str:
    for key in (
        "city",
        "town",
        "village",
        "municipality",
        "city_district",
        "suburb",
        "hamlet",
        "county",
        "state",
    ):
        val = address.get(key)
        if val:
            return str(val)
    return "Unknown"


@lru_cache(maxsize=256)
def reverse_geocode(lat: float, lon: float) -> dict:
    """
    Resolve coordinates to place info.
    Returns: city, country, country_code, display_name
    """
    lat_r = round(float(lat), 5)
    lon_r = round(float(lon), 5)
    params = urllib.parse.urlencode(
        {
            "lat": f"{lat_r:.5f}",
            "lon": f"{lon_r:.5f}",
            "format": "jsonv2",
            "zoom": 16,
            "addressdetails": 1,
        }
    )
    req = urllib.request.Request(
        f"{NOMINATIM}?{params}",
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Accept-Language": "en",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return {
            "city": "Unknown",
            "country": "Unknown",
            "country_code": "",
            "display_name": f"{lat_r:.5f}, {lon_r:.5f}",
            "ok": False,
        }

    address = data.get("address") or {}
    city = _pick_city(address)
    country = str(address.get("country") or "Unknown")
    cc = str(address.get("country_code") or "").upper()
    display = data.get("display_name") or f"{city}, {country}"
    return {
        "city": city,
        "country": country,
        "country_code": cc,
        "display_name": display,
        "ok": True,
    }
