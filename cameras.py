"""Per-phone camera EXIF fingerprints (main wide camera)."""

from __future__ import annotations

import random
import re
from typing import Any

# Typical main rear camera values for spoofed stills
# focal_mm = actual focal length, focal_35 = 35mm equivalent
_CAMERAS: dict[str, dict[str, Any]] = {
    # Apple — Pro models ~24mm eq, f/1.78; non-pro f/1.6 or f/1.5
    "iphone-16-pro-max": {"focal_mm": 6.86, "fnumber": 1.78, "focal_35": 24, "iso": (32, 1600)},
    "iphone-16-pro": {"focal_mm": 6.86, "fnumber": 1.78, "focal_35": 24, "iso": (32, 1600)},
    "iphone-16": {"focal_mm": 6.86, "fnumber": 1.6, "focal_35": 26, "iso": (32, 2000)},
    "iphone-16-plus": {"focal_mm": 6.86, "fnumber": 1.6, "focal_35": 26, "iso": (32, 2000)},
    "iphone-15-pro-max": {"focal_mm": 6.86, "fnumber": 1.78, "focal_35": 24, "iso": (32, 1600)},
    "iphone-15-pro": {"focal_mm": 6.86, "fnumber": 1.78, "focal_35": 24, "iso": (32, 1600)},
    "iphone-15": {"focal_mm": 6.86, "fnumber": 1.6, "focal_35": 26, "iso": (32, 2000)},
    "iphone-15-plus": {"focal_mm": 6.86, "fnumber": 1.6, "focal_35": 26, "iso": (32, 2000)},
    "iphone-14-pro-max": {"focal_mm": 6.86, "fnumber": 1.78, "focal_35": 24, "iso": (40, 1600)},
    "iphone-14-pro": {"focal_mm": 6.86, "fnumber": 1.78, "focal_35": 24, "iso": (40, 1600)},
    "iphone-14": {"focal_mm": 5.7, "fnumber": 1.5, "focal_35": 26, "iso": (40, 2000)},
    "iphone-13-pro": {"focal_mm": 5.7, "fnumber": 1.5, "focal_35": 26, "iso": (40, 2000)},
    "iphone-13": {"focal_mm": 5.1, "fnumber": 1.6, "focal_35": 26, "iso": (40, 2000)},
    "iphone-13-mini": {"focal_mm": 5.1, "fnumber": 1.6, "focal_35": 26, "iso": (40, 2000)},
    "iphone-12-pro": {"focal_mm": 4.2, "fnumber": 1.6, "focal_35": 26, "iso": (40, 2500)},
    "iphone-12": {"focal_mm": 4.2, "fnumber": 1.6, "focal_35": 26, "iso": (40, 2500)},
    "iphone-11-pro": {"focal_mm": 4.25, "fnumber": 1.8, "focal_35": 26, "iso": (40, 2500)},
    "iphone-11": {"focal_mm": 4.25, "fnumber": 1.8, "focal_35": 26, "iso": (40, 2500)},
    "iphone-se-3": {"focal_mm": 3.99, "fnumber": 1.8, "focal_35": 28, "iso": (40, 2000)},
    # Samsung
    "samsung-s25-ultra": {"focal_mm": 6.3, "fnumber": 1.7, "focal_35": 23, "iso": (50, 3200)},
    "samsung-s25": {"focal_mm": 5.54, "fnumber": 1.8, "focal_35": 24, "iso": (50, 3200)},
    "samsung-s24-ultra": {"focal_mm": 6.3, "fnumber": 1.7, "focal_35": 23, "iso": (50, 3200)},
    "samsung-s24": {"focal_mm": 5.4, "fnumber": 1.8, "focal_35": 24, "iso": (50, 3200)},
    "samsung-s23-ultra": {"focal_mm": 6.3, "fnumber": 1.7, "focal_35": 23, "iso": (50, 3200)},
    "samsung-s23": {"focal_mm": 5.4, "fnumber": 1.8, "focal_35": 24, "iso": (50, 3200)},
    "samsung-s22": {"focal_mm": 5.4, "fnumber": 1.8, "focal_35": 24, "iso": (50, 3200)},
    "samsung-zflip6": {"focal_mm": 5.4, "fnumber": 1.8, "focal_35": 24, "iso": (50, 3200)},
    "samsung-a55": {"focal_mm": 5.4, "fnumber": 1.8, "focal_35": 26, "iso": (50, 3200)},
    "samsung-a54": {"focal_mm": 5.4, "fnumber": 1.8, "focal_35": 26, "iso": (50, 3200)},
    # Google
    "pixel-9-pro": {"focal_mm": 6.9, "fnumber": 1.68, "focal_35": 24, "iso": (40, 3200)},
    "pixel-9": {"focal_mm": 6.9, "fnumber": 1.68, "focal_35": 24, "iso": (40, 3200)},
    "pixel-8-pro": {"focal_mm": 6.9, "fnumber": 1.68, "focal_35": 24, "iso": (40, 3200)},
    "pixel-8": {"focal_mm": 6.9, "fnumber": 1.68, "focal_35": 24, "iso": (40, 3200)},
    "pixel-7-pro": {"focal_mm": 6.81, "fnumber": 1.85, "focal_35": 24, "iso": (40, 3200)},
    "pixel-7": {"focal_mm": 6.81, "fnumber": 1.85, "focal_35": 24, "iso": (40, 3200)},
    "pixel-6a": {"focal_mm": 4.38, "fnumber": 1.7, "focal_35": 27, "iso": (50, 3200)},
    # Xiaomi / others
    "xiaomi-14-ultra": {"focal_mm": 6.9, "fnumber": 1.63, "focal_35": 23, "iso": (50, 3200)},
    "xiaomi-14": {"focal_mm": 6.9, "fnumber": 1.63, "focal_35": 23, "iso": (50, 3200)},
    "xiaomi-13": {"focal_mm": 6.9, "fnumber": 1.8, "focal_35": 23, "iso": (50, 3200)},
    "redmi-note-13": {"focal_mm": 4.74, "fnumber": 1.9, "focal_35": 26, "iso": (50, 3200)},
    "oneplus-12": {"focal_mm": 6.81, "fnumber": 1.6, "focal_35": 23, "iso": (50, 3200)},
    "oneplus-11": {"focal_mm": 6.41, "fnumber": 1.8, "focal_35": 24, "iso": (50, 3200)},
    "nothing-phone-2": {"focal_mm": 6.34, "fnumber": 1.9, "focal_35": 24, "iso": (50, 3200)},
    "nothing-phone-2a": {"focal_mm": 6.34, "fnumber": 1.9, "focal_35": 24, "iso": (50, 3200)},
    "huawei-p60-pro": {"focal_mm": 6.3, "fnumber": 1.4, "focal_35": 24, "iso": (50, 3200)},
    "oppo-find-x7": {"focal_mm": 6.7, "fnumber": 1.8, "focal_35": 23, "iso": (50, 3200)},
    "sony-xperia-1-v": {"focal_mm": 6.9, "fnumber": 1.9, "focal_35": 24, "iso": (50, 3200)},
}

_DEFAULT = {"focal_mm": 5.0, "fnumber": 1.8, "focal_35": 26, "iso": (50, 3200)}


def _parse_lens(lens: str | None) -> dict[str, float]:
    out: dict[str, float] = {}
    if not lens:
        return out
    mm = re.search(r"([\d.]+)\s*mm", lens, re.I)
    fn = re.search(r"f\s*/\s*([\d.]+)", lens, re.I)
    if mm:
        out["focal_mm"] = float(mm.group(1))
    if fn:
        out["fnumber"] = float(fn.group(1))
    return out


def get_camera(
    phone_key: str,
    phone: dict,
    *,
    randomize: bool = True,
    overrides: dict | None = None,
) -> dict[str, Any]:
    base = dict(_CAMERAS.get(phone_key, _DEFAULT))
    base.update(_parse_lens(phone.get("lens")))
    iso_lo, iso_hi = base.get("iso", (50, 3200))

    shutters = [
        (1, 60),
        (1, 80),
        (1, 100),
        (1, 125),
        (1, 160),
        (1, 200),
        (1, 250),
        (1, 320),
        (1, 400),
        (1, 500),
    ]
    if randomize:
        num, den = random.choice(shutters)
        iso = random.choice(
            [
                x
                for x in (
                    50, 64, 80, 100, 125, 160, 200, 250, 320, 400, 500, 640, 800, 1000, 1250, 1600,
                )
                if iso_lo <= x <= iso_hi
            ]
            or [100]
        )
    else:
        num, den = 1, 125
        iso = min(max(100, iso_lo), iso_hi)

    cam = {
        "focal_mm": float(base["focal_mm"]),
        "fnumber": float(base["fnumber"]),
        "focal_35": int(base["focal_35"]),
        "iso": int(iso),
        "exposure_num": int(num),
        "exposure_den": int(den),
        "lens_make": phone.get("make")
        if str(phone.get("make", "")).lower() == "apple"
        else phone.get("vendor") or phone.get("make"),
        "lens_model": phone.get("lens"),
    }

    if overrides:
        for key in (
            "focal_mm",
            "fnumber",
            "focal_35",
            "iso",
            "exposure_num",
            "exposure_den",
            "lens_make",
            "lens_model",
        ):
            if key not in overrides or overrides[key] is None or overrides[key] == "":
                continue
            if key in {"lens_make", "lens_model"}:
                cam[key] = str(overrides[key])
            elif key == "focal_35":
                cam[key] = int(float(overrides[key]))
            elif key in {"iso", "exposure_num", "exposure_den"}:
                cam[key] = int(float(overrides[key]))
            else:
                cam[key] = float(overrides[key])

    return cam


def camera_defaults(phone_key: str, phone: dict) -> dict[str, Any]:
    """Stable defaults for UI (no random shutter/ISO each request)."""
    return get_camera(phone_key, phone, randomize=False)
