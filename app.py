#!/usr/bin/env python3
"""Web UI for the video metadata spoofer."""

from __future__ import annotations

import os
import secrets
import shutil
import time
from pathlib import Path

from flask import (
    Flask,
    jsonify,
    render_template,
    request,
    send_file,
    session,
)

from presets import LOCATIONS, PHONES, list_locations, list_phones
from geocode import reverse_geocode
from spoof import VIDEO_EXTS, parse_when, read_metadata, spoof_file

ROOT = Path(__file__).resolve().parent
WORK = ROOT / ".work"
UPLOADS = WORK / "uploads"
OUTPUTS = WORK / "outputs"

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config["MAX_CONTENT_LENGTH"] = int(
    os.environ.get("MAX_UPLOAD_MB", "200")
) * 1024 * 1024

for d in (UPLOADS, OUTPUTS):
    d.mkdir(parents=True, exist_ok=True)


def _session_id() -> str:
    if "sid" not in session:
        session["sid"] = secrets.token_hex(8)
    return session["sid"]


def _apple_video_filename() -> str:
    """iPhone Camera Roll style: IMG_4521.MOV"""
    import random as _rnd

    return f"IMG_{_rnd.randint(1, 9999):04d}.MOV"


def _download_mimetype(name: str) -> str:
    ext = Path(name).suffix.lower()
    if ext == ".mov":
        return "video/quicktime"
    if ext == ".m4v":
        return "video/x-m4v"
    return "video/mp4"


def _cleanup_old(max_age_sec: int = 3600) -> None:
    now = time.time()
    for folder in (UPLOADS, OUTPUTS):
        for path in folder.glob("*"):
            try:
                if now - path.stat().st_mtime > max_age_sec:
                    if path.is_file():
                        path.unlink(missing_ok=True)
                    elif path.is_dir():
                        shutil.rmtree(path, ignore_errors=True)
            except OSError:
                pass


def _parse_float(raw: str | None, name: str) -> float | None:
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return float(str(raw).strip())
    except ValueError as exc:
        raise ValueError(f"Neplatné {name}: {raw!r}") from exc


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/presets")
def api_presets():
    phones = [
        {
            "id": key,
            "label": label,
            "make": PHONES[key]["make"],
            "model": PHONES[key]["model"],
            "software": PHONES[key]["software"],
        }
        for key, label in list_phones()
    ]
    locations = [
        {
            "id": key,
            "label": label,
            "city": LOCATIONS[key]["city"],
            "country": LOCATIONS[key]["country"],
            "country_code": LOCATIONS[key]["country_code"],
            "lat": LOCATIONS[key]["lat"],
            "lon": LOCATIONS[key]["lon"],
            "alt": LOCATIONS[key]["alt"],
        }
        for key, label in list_locations()
    ]
    return jsonify({"phones": phones, "locations": locations})


@app.get("/api/reverse")
def api_reverse():
    try:
        lat = _parse_float(request.args.get("lat"), "lat")
        lon = _parse_float(request.args.get("lon"), "lon")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    if lat is None or lon is None:
        return jsonify({"error": "Chýba lat/lon."}), 400
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return jsonify({"error": "GPS mimo rozsahu."}), 400
    place = reverse_geocode(lat, lon)
    return jsonify(place)


@app.post("/api/spoof")
def api_spoof():
    _cleanup_old()

    if "video" not in request.files:
        return jsonify({"error": "Chýba video súbor."}), 400

    file = request.files["video"]
    if not file or not file.filename:
        return jsonify({"error": "Vyber video súbor."}), 400

    original_name = Path(file.filename).name
    suffix = Path(original_name).suffix.lower()
    if suffix not in VIDEO_EXTS:
        return jsonify(
            {
                "error": f"Nepodporovaný formát {suffix or '(bez prípony)'}. "
                f"Použi: {', '.join(sorted(VIDEO_EXTS))}"
            }
        ), 400

    phone = (request.form.get("phone") or "").strip()
    location = (request.form.get("location") or "").strip() or None
    when_raw = (request.form.get("when") or "").strip() or None
    random_mode = request.form.get("random") in {"1", "true", "on", "yes"}
    no_gps = request.form.get("no_gps") in {"1", "true", "on", "yes"}
    wipe = request.form.get("wipe", "1") in {"1", "true", "on", "yes"}

    try:
        lat = _parse_float(request.form.get("lat"), "lat")
        lon = _parse_float(request.form.get("lon"), "lon")
        alt = _parse_float(request.form.get("alt"), "alt")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    if random_mode:
        import random as _rnd

        phone = phone or _rnd.choice(list(PHONES))
        if not no_gps and lat is None:
            location = location or _rnd.choice(list(LOCATIONS))
            preset = LOCATIONS[location]
            lat = preset["lat"]
            lon = preset["lon"]
            if alt is None:
                alt = preset["alt"]

    if not phone:
        return jsonify({"error": "Vyber telefón alebo zapni Random."}), 400
    if phone not in PHONES:
        return jsonify({"error": f"Neznámy telefón: {phone}"}), 400
    if location and location not in LOCATIONS:
        return jsonify({"error": f"Neznáma lokalita: {location}"}), 400

    try:
        when = parse_when(when_raw)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    location_override = None
    if not no_gps and lat is not None and lon is not None:
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return jsonify({"error": "GPS mimo rozsahu (lat ±90, lon ±180)."}), 400
        # Always resolve city/country from map coordinates
        place = reverse_geocode(lat, lon)
        location_override = {
            "lat": lat,
            "lon": lon,
            "alt": 0.0 if alt is None else alt,
            "city": place["city"],
            "country": place["country"],
            "country_code": place["country_code"],
            "name": f"{place['city']}, {place['country']}",
            "exact": True,
        }

    sid = _session_id()
    job = f"{sid}_{int(time.time())}_{secrets.token_hex(4)}"
    src = UPLOADS / f"{job}{suffix}"
    out_dir = OUTPUTS / job
    out_dir.mkdir(parents=True, exist_ok=True)

    file.save(src)

    try:
        target = spoof_file(
            src,
            phone,
            None if (no_gps or location_override) else location,
            when,
            inplace=False,
            out_dir=out_dir,
            no_gps=no_gps,
            quiet=True,
            location_override=None if no_gps else location_override,
            wipe=wipe,
        )
        meta = read_metadata(target)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500
    finally:
        src.unlink(missing_ok=True)

    phone_info = PHONES[phone]
    label = phone_info.get("display_name") or f"{phone_info['make']} {phone_info['model']}"

    if no_gps:
        loc_name = "(bez GPS)"
    elif location_override:
        loc_name = (
            f"{location_override['city']}, {location_override['country']} "
            f"({location_override['lat']:.6f}, {location_override['lon']:.6f})"
        )
    elif location:
        loc_name = LOCATIONS[location]["name"]
    else:
        loc_name = "(bez GPS)"

    download_name = _apple_video_filename()
    # Rename on disk so the file itself looks like Camera Roll output
    apple_path = target.with_name(download_name)
    if apple_path != target:
        target.replace(apple_path)
        target = apple_path

    session["last_job"] = {
        "path": str(target),
        "download_name": download_name,
    }

    return jsonify(
        {
            "ok": True,
            "download_url": "/api/download",
            "download_name": download_name,
            "summary": {
                "phone": label,
                "location": loc_name,
                "city": location_override["city"] if location_override else None,
                "country": location_override["country"] if location_override else None,
                "country_code": location_override["country_code"] if location_override else None,
                "when": when.strftime("%Y-%m-%d %H:%M:%S"),
                "original": original_name,
                "filename": download_name,
                "wipe": wipe,
            },
            "metadata": meta,
        }
    )


@app.get("/api/download")
def api_download():
    job = session.get("last_job")
    if not job:
        return jsonify({"error": "Žiadny hotový súbor. Najprv spusti spoof."}), 404
    path = Path(job["path"])
    if not path.is_file():
        return jsonify({"error": "Súbor už vypršal. Spoofni znova."}), 404
    name = job.get("download_name") or path.name
    return send_file(
        path,
        as_attachment=True,
        download_name=name,
        mimetype=_download_mimetype(name),
    )


def main() -> None:
    port = int(os.environ.get("PORT", "5050"))
    host = os.environ.get("HOST", "127.0.0.1")
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    print(f"Data Spoofer → http://{host}:{port}")
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
