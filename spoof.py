#!/usr/bin/env python3
"""
Simple video metadata spoofer.

Rewrites QuickTime/MP4 tags so a video looks like it was shot on a real phone
(device, OS, GPS/country, creation time). Uses ExifTool under the hood.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from presets import LOCATIONS, PHONES, list_locations, list_phones

VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".3gp", ".3g2"}


def require_exiftool() -> str:
    path = shutil.which("exiftool")
    if not path:
        raise RuntimeError(
            "ExifTool nie je nainštalovaný. "
            "macOS: brew install exiftool | Linux: sudo apt install libimage-exiftool-perl"
        )
    return path


def run_exiftool(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    et = require_exiftool()
    cmd = [et, "-overwrite_original", "-charset", "utf8", *args]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        err = (result.stderr or result.stdout or "unknown error").strip()
        raise RuntimeError(f"exiftool failed: {err}")
    return result


def iso6709(lat: float, lon: float, alt: float | None = None) -> str:
    """Apple QuickTime location string, e.g. +48.1486+17.1077+152.000/."""
    lat_s = f"{lat:+.4f}"
    lon_s = f"{lon:+.4f}"
    if alt is None:
        return f"{lat_s}{lon_s}/"
    return f"{lat_s}{lon_s}{alt:+.3f}/"


def parse_when(value: str | None) -> datetime:
    if not value:
        days_ago = random.randint(1, 90)
        hour = random.randint(8, 21)
        minute = random.randint(0, 59)
        second = random.randint(0, 59)
        base = datetime.now().replace(microsecond=0) - timedelta(days=days_ago)
        return base.replace(hour=hour, minute=minute, second=second)

    value = value.strip()
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%d.%m.%Y %H:%M:%S",
        "%d.%m.%Y %H:%M",
        "%d.%m.%Y",
    ):
        try:
            dt = datetime.strptime(value, fmt)
            if fmt in ("%Y-%m-%d", "%d.%m.%Y"):
                dt = dt.replace(
                    hour=random.randint(10, 18),
                    minute=random.randint(0, 59),
                    second=random.randint(0, 59),
                )
            return dt
        except ValueError:
            continue
    raise ValueError(
        f"Neplatný dátum: {value!r}. "
        "Použi napr. '2024-06-15 14:30:00' alebo '15.06.2024 14:30'"
    )


def jitter_coords(lat: float, lon: float, meters: float = 80.0) -> tuple[float, float]:
    """Small random offset so GPS isn't always the exact city pin."""
    dlat = random.uniform(-meters, meters) / 111_111
    cos_lat = max(0.2, abs(math.cos(math.radians(lat))))
    dlon = random.uniform(-meters, meters) / (111_111 * cos_lat)
    return lat + dlat, lon + dlon


def tz_offset_hours(location: dict | None) -> int:
    if not location:
        return 1
    cc = location.get("country_code")
    if cc == "US":
        return random.choice([-5, -8, -7])
    if cc == "GB":
        return 0
    if cc in {"SK", "CZ", "AT", "HU", "PL", "DE", "IT", "FR", "ES"}:
        return random.choice([1, 2])
    # Fallback from longitude
    lon = float(location.get("lon", 0.0))
    return max(-12, min(14, int(round(lon / 15.0))))


def build_tags(
    phone: dict,
    location: dict | None,
    when: datetime,
    *,
    no_gps: bool = False,
) -> list[str]:
    stamp = when.strftime("%Y:%m:%d %H:%M:%S")
    offset_hours = tz_offset_hours(location)
    tz = f"{offset_hours:+03d}:00"
    apple_stamp = when.strftime("%Y-%m-%dT%H:%M:%S") + tz

    make = phone["make"]
    model = phone["model"]
    software = phone["software"]
    is_apple = make.lower() == "apple"

    tags = [
        f"-CreateDate={stamp}",
        f"-ModifyDate={stamp}",
        f"-TrackCreateDate={stamp}",
        f"-TrackModifyDate={stamp}",
        f"-MediaCreateDate={stamp}",
        f"-MediaModifyDate={stamp}",
        f"-Make={make}",
        f"-Model={model}",
        f"-Software={software}",
        f"-HandlerDescription=Core Media Video",
    ]

    if is_apple:
        tags.extend(
            [
                f"-Keys:Make={make}",
                f"-Keys:Model={model}",
                f"-Keys:Software={software}",
                f"-Keys:CreationDate={apple_stamp}",
                f"-QuickTime:CreateDate={stamp}",
                f"-QuickTime:ModifyDate={stamp}",
            ]
        )
        if phone.get("lens"):
            tags.append(f"-Keys:LensModel={phone['lens']}")
    else:
        tags.extend(
            [
                f"-AndroidMake={make}",
                f"-AndroidModel={model}",
                f"-CompressorName={make} {model}",
            ]
        )

    if location and not no_gps:
        lat = float(location["lat"])
        lon = float(location["lon"])
        # Exact map pin stays exact; city presets get slight jitter
        if not location.get("exact"):
            lat, lon = jitter_coords(lat, lon)
        alt = float(location.get("alt", 0.0))
        if not location.get("exact"):
            alt += random.uniform(-5, 5)
        loc_str = iso6709(lat, lon, alt)
        city = location.get("city") or "Unknown"
        country = location.get("country") or "Unknown"
        country_code = location.get("country_code") or ""
        tags.extend(
            [
                f"-GPSLatitude={abs(lat)}",
                f"-GPSLongitude={abs(lon)}",
                f"-GPSLatitudeRef={'N' if lat >= 0 else 'S'}",
                f"-GPSLongitudeRef={'E' if lon >= 0 else 'W'}",
                f"-GPSAltitude={abs(alt)}",
                f"-GPSAltitudeRef={'above' if alt >= 0 else 'below'}",
                f"-Keys:GPSCoordinates={loc_str}",
                f"-UserData:GPSCoordinates={loc_str}",
                f"-Location={city}",
                f"-LocationName={city}, {country}",
                f"-Country={country}",
            ]
        )
        if country_code:
            tags.append(f"-CountryCode={country_code}")
        if is_apple:
            tags.append(f"-Keys:LocationISO6709={loc_str}")

    return tags


def strip_all_metadata(path: Path) -> None:
    """Wipe existing container/tag metadata before writing a clean fingerprint."""
    # ExifTool: remove all writable tags
    run_exiftool(["-all=", str(path)], check=False)

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return

    # Remux without metadata streams / global headers (no re-encode)
    tmp = path.with_suffix(path.suffix + ".clean.tmp" + path.suffix)
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(path),
        "-map_metadata",
        "-1",
        "-c",
        "copy",
        str(tmp),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0 and tmp.is_file():
        tmp.replace(path)
    else:
        tmp.unlink(missing_ok=True)


INSPECT_TAGS = [
    "Make",
    "Model",
    "Software",
    "CreateDate",
    "ModifyDate",
    "TrackCreateDate",
    "MediaCreateDate",
    "GPSLatitude",
    "GPSLongitude",
    "GPSAltitude",
    "Keys:Make",
    "Keys:Model",
    "Keys:Software",
    "Keys:CreationDate",
    "Keys:GPSCoordinates",
    "Keys:LocationISO6709",
    "Location",
    "Country",
    "CountryCode",
    "AndroidMake",
    "AndroidModel",
]


def read_metadata(path: Path) -> dict:
    result = run_exiftool(
        ["-json", "-G1", *[f"-{t}" for t in INSPECT_TAGS], str(path)],
        check=False,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "unknown error").strip()
        raise RuntimeError(f"Nepodarilo sa čítať metadata: {err}")
    data = json.loads(result.stdout)[0]
    data.pop("SourceFile", None)
    return data


def inspect_file(path: Path) -> None:
    data = read_metadata(path)
    print(f"\n=== {path.name} ===")
    if len(data) <= 1:
        print("(žiadne relevantné metadata)")
        return
    width = max(len(k) for k in data)
    for key, value in data.items():
        print(f"  {key:<{width}}  {value}")


def spoof_file(
    path: Path,
    phone_key: str,
    location_key: str | None,
    when: datetime,
    *,
    inplace: bool,
    out_dir: Path | None,
    no_gps: bool,
    quiet: bool = False,
    location_override: dict | None = None,
    wipe: bool = True,
) -> Path:
    if path.suffix.lower() not in VIDEO_EXTS:
        raise ValueError(
            f"Nepodporovaný formát: {path.suffix} "
            f"(podporované: {', '.join(sorted(VIDEO_EXTS))})"
        )
    if phone_key not in PHONES:
        raise ValueError(f"Neznámy telefón: {phone_key}")
    if location_key and location_key not in LOCATIONS and not location_override:
        raise ValueError(f"Neznáma lokalita: {location_key}")

    phone = PHONES[phone_key]
    if location_override:
        location = location_override
    elif location_key:
        location = LOCATIONS[location_key]
    else:
        location = None

    if inplace:
        target = path
    else:
        dest_dir = out_dir or path.parent / "spoofed"
        dest_dir.mkdir(parents=True, exist_ok=True)
        stamp = when.strftime("%Y%m%d_%H%M%S")
        target = dest_dir / f"{path.stem}_spoofed_{stamp}{path.suffix.lower()}"
        shutil.copy2(path, target)

    if wipe:
        strip_all_metadata(target)

    tags = build_tags(phone, location, when, no_gps=no_gps)
    run_exiftool([*tags, str(target)])

    if not quiet:
        label = phone.get("display_name") or f"{phone['make']} {phone['model']}"
        if no_gps or not location:
            where = "(bez GPS)"
        else:
            where = location.get("name") or f"{location.get('lat')}, {location.get('lon')}"
        print(f"✓ {path.name}")
        print(f"  → {target}")
        print(f"  telefón : {label}")
        print(f"  miesto  : {where}")
        print(f"  čas     : {when.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  wipe    : {'áno' if wipe else 'nie'}")
    return target


def cmd_list(_: argparse.Namespace) -> None:
    print("Telefóny:")
    for key, label in list_phones():
        print(f"  {key:<18}  {label}")
    print("\nLokality:")
    for key, label in list_locations():
        print(f"  {key:<18}  {label}")


def cmd_inspect(args: argparse.Namespace) -> None:
    try:
        require_exiftool()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    for p in args.files:
        path = Path(p).expanduser().resolve()
        if not path.is_file():
            print(f"Súbor neexistuje: {path}", file=sys.stderr)
            continue
        inspect_file(path)


def cmd_spoof(args: argparse.Namespace) -> None:
    try:
        require_exiftool()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

    phone_key = args.phone
    location_key = args.location
    if args.random:
        phone_key = phone_key or random.choice(list(PHONES))
        location_key = location_key or random.choice(list(LOCATIONS))
    if not phone_key:
        raise SystemExit("Zadaj --phone alebo použi --random")
    if phone_key not in PHONES:
        raise SystemExit(f"Neznámy telefón: {phone_key}\nSpusti: python3 spoof.py list")
    if location_key and location_key not in LOCATIONS:
        raise SystemExit(f"Neznáma lokalita: {location_key}\nSpusti: python3 spoof.py list")

    out_dir = Path(args.out).expanduser().resolve() if args.out else None

    for p in args.files:
        path = Path(p).expanduser().resolve()
        if not path.is_file():
            print(f"Súbor neexistuje: {path}", file=sys.stderr)
            continue
        when = parse_when(args.when)
        try:
            target = spoof_file(
                path,
                phone_key,
                location_key,
                when,
                inplace=args.inplace,
                out_dir=out_dir,
                no_gps=args.no_gps,
            )
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            continue
        if args.show:
            inspect_file(target)
        print()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="spoof",
        description=(
            "Fake video metadata (telefón, krajina/GPS, dátum) "
            "aby to vyzeralo ako reálne nahraté video."
        ),
    )
    sub = p.add_subparsers(dest="command", required=True)

    list_p = sub.add_parser("list", help="Zoznam telefónov a lokalít")
    list_p.set_defaults(func=cmd_list)

    insp = sub.add_parser("inspect", help="Ukáž aktuálne metadata videa")
    insp.add_argument("files", nargs="+", help="Video súbory")
    insp.set_defaults(func=cmd_inspect)

    sp = sub.add_parser("spoof", help="Prepíš metadata videa")
    sp.add_argument("files", nargs="+", help="Video súbory (.mp4 / .mov)")
    sp.add_argument("--phone", "-p", help="Preset telefónu (pozri: list)")
    sp.add_argument("--location", "-l", help="Preset lokality / krajiny (pozri: list)")
    sp.add_argument(
        "--when",
        "-w",
        help="Dátum/čas nahratia, napr. '2024-06-15 14:30:00' (default: náhodný)",
    )
    sp.add_argument("--random", "-r", action="store_true", help="Náhodný telefón + lokalita")
    sp.add_argument("--no-gps", action="store_true", help="Bez GPS / krajiny")
    sp.add_argument(
        "--inplace",
        action="store_true",
        help="Prepíš pôvodný súbor (default: kópia do spoofed/)",
    )
    sp.add_argument("--out", "-o", help="Výstupný priečinok pre kópie")
    sp.add_argument("--show", action="store_true", help="Po spoofe ukáž nové metadata")
    sp.set_defaults(func=cmd_spoof)

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
