#!/usr/bin/env python3
"""Web UI for the video metadata spoofer."""

from __future__ import annotations

import os
import secrets
import shutil
import time
import zipfile
from datetime import timedelta
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
from geocode import resolve_place
from cameras import camera_defaults, get_camera
from spoof import MEDIA_EXTS, IMAGE_EXTS, parse_when, read_metadata, spoof_file

ROOT = Path(__file__).resolve().parent
WORK = ROOT / ".work"
UPLOADS = WORK / "uploads"
OUTPUTS = WORK / "outputs"
MAX_BATCH = int(os.environ.get("MAX_BATCH", "30"))

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


def _apple_filename(suffix: str, used: set[str] | None = None) -> str:
    """iPhone Camera Roll style: IMG_4521.MOV / IMG_4521.HEIC / IMG_4521.JPG"""
    import random as _rnd

    ext = suffix.lower()
    if ext in {".jpg", ".jpeg"}:
        out = ".JPG"
    elif ext in {".heic", ".heif"}:
        out = ".HEIC"
    elif ext == ".png":
        out = ".PNG"
    elif ext in {".tif", ".tiff"}:
        out = ".TIFF"
    elif ext == ".dng":
        out = ".DNG"
    elif ext == ".webp":
        out = ".WEBP"
    elif ext == ".mov":
        out = ".MOV"
    elif ext == ".m4v":
        out = ".M4V"
    else:
        out = ext.upper() if ext else ".MOV"

    used = used if used is not None else set()
    for _ in range(50):
        name = f"IMG_{_rnd.randint(1, 9999):04d}{out}"
        if name not in used:
            used.add(name)
            return name
    name = f"IMG_{secrets.token_hex(2).upper()}{out}"
    used.add(name)
    return name


def _download_mimetype(name: str) -> str:
    ext = Path(name).suffix.lower()
    return {
        ".mov": "video/quicktime",
        ".m4v": "video/x-m4v",
        ".mp4": "video/mp4",
        ".3gp": "video/3gpp",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".heic": "image/heic",
        ".heif": "image/heif",
        ".png": "image/png",
        ".webp": "image/webp",
        ".tif": "image/tiff",
        ".tiff": "image/tiff",
        ".dng": "image/x-adobe-dng",
        ".zip": "application/zip",
    }.get(ext, "application/octet-stream")


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


def _collect_uploads():
    files = request.files.getlist("file")
    if not files:
        legacy = request.files.get("video")
        if legacy:
            files = [legacy]
    return [f for f in files if f and f.filename]


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/presets")
def api_presets():
    phones = []
    for key, label in list_phones():
        phone = PHONES[key]
        cam = camera_defaults(key, phone)
        phones.append(
            {
                "id": key,
                "label": label,
                "make": phone["make"],
                "model": phone["model"],
                "software": phone["software"],
                "camera": cam,
            }
        )
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


@app.get("/api/camera/<phone_id>")
def api_camera(phone_id: str):
    if phone_id not in PHONES:
        return jsonify({"error": f"Neznámy telefón: {phone_id}"}), 404
    sample = request.args.get("sample") in {"1", "true", "yes"}
    phone = PHONES[phone_id]
    cam = get_camera(phone_id, phone, randomize=sample)
    return jsonify(cam)


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
    place = resolve_place(lat, lon)
    return jsonify(place)


@app.post("/api/spoof")
def api_spoof():
    _cleanup_old()

    uploads = _collect_uploads()
    if not uploads:
        return jsonify({"error": "Vyber aspoň jednu fotku alebo video."}), 400
    if len(uploads) > MAX_BATCH:
        return jsonify({"error": f"Maximum je {MAX_BATCH} súborov naraz."}), 400

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

    camera_override = None
    cam_fields = {
        "focal_mm": request.form.get("focal_mm"),
        "fnumber": request.form.get("fnumber"),
        "focal_35": request.form.get("focal_35"),
        "iso": request.form.get("iso"),
        "exposure_num": request.form.get("exposure_num"),
        "exposure_den": request.form.get("exposure_den"),
        "lens_make": request.form.get("lens_make"),
        "lens_model": request.form.get("lens_model"),
    }
    if any(v is not None and str(v).strip() != "" for v in cam_fields.values()):
        camera_override = cam_fields

    location_override = None
    if not no_gps and lat is not None and lon is not None:
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return jsonify({"error": "GPS mimo rozsahu (lat ±90, lon ±180)."}), 400
        place = resolve_place(
            lat,
            lon,
            city=(request.form.get("city") or "").strip(),
            country=(request.form.get("country") or "").strip(),
            country_code=(request.form.get("country_code") or "").strip(),
            location_key=location,
        )
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

    sid = _session_id()
    job = f"{sid}_{int(time.time())}_{secrets.token_hex(4)}"
    out_dir = OUTPUTS / job
    out_dir.mkdir(parents=True, exist_ok=True)

    used_names: set[str] = set()
    items = []
    errors = []
    last_meta = {}

    for index, file in enumerate(uploads):
        original_name = Path(file.filename).name
        suffix = Path(original_name).suffix.lower()
        if suffix not in MEDIA_EXTS:
            errors.append(
                {
                    "original": original_name,
                    "error": f"Nepodporovaný formát {suffix or '(bez prípony)'}",
                }
            )
            continue

        kind = "image" if suffix in IMAGE_EXTS else "video"
        # Slightly different capture time per file (looks more natural in batch)
        file_when = when + timedelta(seconds=index)
        src = UPLOADS / f"{job}_{index}{suffix}"
        file.save(src)

        try:
            # Per-file mild camera jitter when batching (ISO/shutter) unless user locked values
            cam_for_file = camera_override
            if camera_override and len(uploads) > 1:
                import random as _rnd
                from copy import deepcopy

                cam_for_file = deepcopy(camera_override)
                try:
                    base_iso = int(float(cam_for_file.get("iso") or 100))
                    cam_for_file["iso"] = str(
                        max(25, base_iso + _rnd.choice([-50, -25, 0, 25, 50, 100]))
                    )
                    den = int(float(cam_for_file.get("exposure_den") or 125))
                    cam_for_file["exposure_den"] = str(
                        max(30, den + _rnd.choice([-40, -20, 0, 20, 40, 80]))
                    )
                except (TypeError, ValueError):
                    pass

            target = spoof_file(
                src,
                phone,
                None if (no_gps or location_override) else location,
                file_when,
                inplace=False,
                out_dir=out_dir,
                no_gps=no_gps,
                quiet=True,
                location_override=None if no_gps else location_override,
                wipe=wipe,
                camera_override=cam_for_file,
            )
            meta = read_metadata(target)
            download_name = _apple_filename(suffix, used_names)
            apple_path = target.with_name(download_name)
            if apple_path != target:
                target.replace(apple_path)
                target = apple_path

            items.append(
                {
                    "original": original_name,
                    "filename": download_name,
                    "kind": kind,
                    "when": file_when.strftime("%Y-%m-%d %H:%M:%S"),
                    "path": str(target),
                }
            )
            last_meta = meta
        except Exception as exc:  # noqa: BLE001
            errors.append({"original": original_name, "error": str(exc)})
        finally:
            src.unlink(missing_ok=True)

    if not items:
        return jsonify(
            {
                "error": "Žiaden súbor sa nepodarilo spoofnúť.",
                "errors": errors,
            }
        ), 500

    if len(items) == 1:
        download_name = items[0]["filename"]
        download_path = Path(items[0]["path"])
        batch = False
    else:
        download_name = f"IMG_batch_{when.strftime('%Y%m%d_%H%M%S')}.zip"
        download_path = out_dir / download_name
        with zipfile.ZipFile(download_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for item in items:
                zf.write(item["path"], arcname=item["filename"])
        batch = True

    session["last_job"] = {
        "path": str(download_path),
        "download_name": download_name,
    }

    return jsonify(
        {
            "ok": True,
            "batch": batch,
            "count": len(items),
            "download_url": "/api/download",
            "download_name": download_name,
            "summary": {
                "phone": label,
                "location": loc_name,
                "city": location_override["city"] if location_override else None,
                "country": location_override["country"] if location_override else None,
                "country_code": location_override["country_code"] if location_override else None,
                "when": when.strftime("%Y-%m-%d %H:%M:%S"),
                "original": items[0]["original"]
                if len(items) == 1
                else f"{len(items)} súborov",
                "filename": download_name,
                "kind": items[0]["kind"] if len(items) == 1 else "batch",
                "wipe": wipe,
                "count": len(items),
            },
            "items": [
                {
                    "original": i["original"],
                    "filename": i["filename"],
                    "kind": i["kind"],
                    "when": i["when"],
                }
                for i in items
            ],
            "errors": errors,
            "metadata": last_meta,
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
