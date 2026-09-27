"""Reverse geocode lat/lon → city, country (Nominatim / OpenStreetMap)."""

from __future__ import annotations

import json
import math
import urllib.error
import urllib.parse
import urllib.request
from functools import lru_cache

from presets import LOCATIONS

NOMINATIM = "https://nominatim.openstreetmap.org/reverse"
USER_AGENT = "DataSpoofer/1.1 (https://github.com/OtoMihalik296/data-spoofer; local metadata tool)"


def _pick_city(address: dict) -> str:
    for key in (
        "city",
        "town",
        "village",
        "municipality",
        "city_district",
        "suburb",
        "borough",
        "quarter",
        "neighbourhood",
        "hamlet",
        "county",
        "state_district",
        "state",
    ):
        val = address.get(key)
        if val:
            return str(val)
    return ""


def nearest_preset(lat: float, lon: float, *, max_km: float = 75.0) -> dict | None:
    """Closest LOCATIONS preset only if within max_km (avoid NYC for Toronto)."""
    best = None
    best_d = float("inf")
    for loc in LOCATIONS.values():
        dlat = math.radians(lat - loc["lat"])
        dlon = math.radians(lon - loc["lon"])
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(lat))
            * math.cos(math.radians(loc["lat"]))
            * math.sin(dlon / 2) ** 2
        )
        d = 2 * 6371 * math.asin(min(1.0, math.sqrt(a)))
        if d < best_d:
            best_d = d
            best = loc
    if best is None or best_d > max_km:
        return None
    return {
        "city": best["city"],
        "country": best["country"],
        "country_code": best["country_code"],
        "display_name": best["name"],
        "ok": True,
        "source": "preset",
        "distance_km": round(best_d, 1),
    }


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return 2 * 6371 * math.asin(min(1.0, math.sqrt(a)))


@lru_cache(maxsize=256)
def reverse_geocode(lat: float, lon: float) -> dict:
    """
    Resolve coordinates to place info.
    Returns: city, country, country_code, display_name, ok
    """
    lat_r = round(float(lat), 5)
    lon_r = round(float(lon), 5)
    params = urllib.parse.urlencode(
        {
            "lat": f"{lat_r:.5f}",
            "lon": f"{lon_r:.5f}",
            "format": "jsonv2",
            "zoom": 14,
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
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        fallback = nearest_preset(lat_r, lon_r)
        if fallback:
            fallback["ok"] = False
            return fallback
        return {
            "city": f"{lat_r:.4f}",
            "country": f"{lon_r:.4f}",
            "country_code": "",
            "display_name": f"{lat_r:.5f}, {lon_r:.5f}",
            "ok": False,
            "source": "coords",
        }

    address = data.get("address") or {}
    city = _pick_city(address)
    country = str(address.get("country") or "")
    cc = str(address.get("country_code") or "").upper()

    if not city or not country:
        fallback = nearest_preset(lat_r, lon_r)
        if fallback:
            city = city or fallback["city"]
            country = country or fallback["country"]
            cc = cc or fallback["country_code"]

    # Last resort: don't invent a faraway city
    if not city:
        city = f"{lat_r:.4f}"
    if not country:
        country = cc or f"{lon_r:.4f}"

    display = data.get("display_name") or f"{city}, {country}"
    return {
        "city": city,
        "country": country,
        "country_code": cc,
        "display_name": display,
        "ok": True,
        "source": "nominatim",
    }


def resolve_place(
    lat: float,
    lon: float,
    *,
    city: str | None = None,
    country: str | None = None,
    country_code: str | None = None,
    location_key: str | None = None,
) -> dict:
    """
    Prefer client city/country from map reverse, then Nominatim.
    location_key preset only if pin is near that city (prevents NYC label on Toronto).
    """
    city = (city or "").strip()
    country = (country or "").strip()
    country_code = (country_code or "").strip().upper()
    if city.lower() in {"unknown", "—", "-", "n/a"}:
        city = ""
    if country.lower() in {"unknown", "—", "-", "n/a"}:
        country = ""

    # Only trust dropdown preset when coordinates match that city
    if location_key and location_key in LOCATIONS:
        preset = LOCATIONS[location_key]
        if _haversine_km(lat, lon, preset["lat"], preset["lon"]) <= 75:
            city = city or preset["city"]
            country = country or preset["country"]
            country_code = country_code or preset["country_code"]

    if city and country and not city.replace(".", "").replace("-", "").isdigit():
        return {
            "city": city,
            "country": country,
            "country_code": country_code,
            "display_name": f"{city}, {country}",
            "ok": True,
            "source": "client",
        }

    place = reverse_geocode(lat, lon)
    out_city = city or place["city"]
    out_country = country or place["country"]
    # If place fell back to raw coords as city, keep trying preset nearby
    if out_city.replace(".", "").replace("-", "").isdigit() or place.get("source") == "coords":
        near = nearest_preset(lat, lon)
        if near:
            out_city = near["city"]
            out_country = near["country"]
            country_code = country_code or near["country_code"]
            place = near

    return {
        "city": out_city,
        "country": out_country,
        "country_code": country_code or place.get("country_code") or "",
        "display_name": place.get("display_name") or f"{out_city}, {out_country}",
        "ok": place.get("ok", False),
        "source": place.get("source", "nominatim"),
    }
