const form = document.getElementById("spoof-form");
const dropzone = document.getElementById("dropzone");
const mediaInput = document.getElementById("media");
const dropTitle = document.getElementById("drop-title");
const phoneSelect = document.getElementById("phone");
const locationSelect = document.getElementById("location");
const whenInput = document.getElementById("when");
const randomCheck = document.getElementById("random");
const noGpsCheck = document.getElementById("no_gps");
const wipeCheck = document.getElementById("wipe");
const submitBtn = document.getElementById("submit-btn");
const statusEl = document.getElementById("status");
const resultEl = document.getElementById("result");
const summaryEl = document.getElementById("summary");
const metaEl = document.getElementById("meta");
const downloadBtn = document.getElementById("download-btn");
const mapBlock = document.getElementById("map-block");
const placeLabel = document.getElementById("place-label");
const fileListEl = document.getElementById("file-list");
const latInput = document.getElementById("lat");
const lonInput = document.getElementById("lon");
const altInput = document.getElementById("alt");
const cityInput = document.getElementById("city");
const countryInput = document.getElementById("country");
const countryCodeInput = document.getElementById("country_code");
const resampleCamBtn = document.getElementById("resample-cam");
const camFocalMm = document.getElementById("focal_mm");
const camFnumber = document.getElementById("fnumber");
const camFocal35 = document.getElementById("focal_35");
const camIso = document.getElementById("iso");
const camExpNum = document.getElementById("exposure_num");
const camExpDen = document.getElementById("exposure_den");
const camLensMake = document.getElementById("lens_make");
const camLensModel = document.getElementById("lens_model");

let locationsById = {};
let phonesById = {};
let map;
let marker;
let reverseTimer = null;

function setStatus(text, kind = "") {
  statusEl.textContent = text || "";
  statusEl.className = `status${kind ? ` ${kind}` : ""}`;
}

function fillSelect(select, items, placeholder) {
  select.innerHTML = "";
  const opt0 = document.createElement("option");
  opt0.value = "";
  opt0.textContent = placeholder;
  select.appendChild(opt0);
  for (const item of items) {
    const opt = document.createElement("option");
    opt.value = item.id;
    opt.textContent = item.label;
    select.appendChild(opt);
  }
}

function parseCoord(raw) {
  if (raw == null || raw === "") return NaN;
  let text = String(raw).trim().replace(/\s|\u00a0/g, "");
  if (text.includes(",") && text.includes(".")) {
    text = text.replace(/\./g, "").replace(",", ".");
  } else if (text.includes(",")) {
    text = text.replace(",", ".");
  }
  return Number(text);
}

function lookupPlace(lat, lon) {
  clearTimeout(reverseTimer);
  reverseTimer = setTimeout(async () => {
    placeLabel.textContent = "Hľadám miesto…";
    // Pin moved → don't keep stale "Rýchla lokalita" city
    if (locationSelect) locationSelect.value = "";
    try {
      const url = `/api/reverse?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}`;
      const res = await fetch(url);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "reverse failed");
      const city = data.city && data.city !== "Unknown" ? data.city : "";
      const country = data.country && data.country !== "Unknown" ? data.country : "";
      if (!city || !country) throw new Error("empty place");
      // Reject raw-coordinate fake cities like "43.6850"
      if (/^-?\d+(\.\d+)?$/.test(city) || /^-?\d+(\.\d+)?$/.test(country)) {
        throw new Error("coord fallback");
      }
      cityInput.value = city;
      countryInput.value = country;
      countryCodeInput.value = data.country_code || "";
      placeLabel.textContent = `${city}, ${country}`;
    } catch {
      placeLabel.textContent = `${Number(lat).toFixed(5)}, ${Number(lon).toFixed(5)}`;
      cityInput.value = "";
      countryInput.value = "";
      countryCodeInput.value = "";
    }
  }, 280);
}

function syncRandomUi() {
  const on = randomCheck.checked;
  phoneSelect.disabled = on;
  whenInput.disabled = on;
  if (on) {
    phoneSelect.value = "";
    whenInput.value = "";
  }
}

function syncGpsUi() {
  const off = noGpsCheck.checked;
  mapBlock.classList.toggle("disabled", off);
  locationSelect.disabled = off;
  latInput.disabled = off;
  lonInput.disabled = off;
  altInput.disabled = off;
}

function setCoords(lat, lon, alt, { fly = true, reverse = true } = {}) {
  const la = parseCoord(lat);
  const lo = parseCoord(lon);
  if (!Number.isFinite(la) || !Number.isFinite(lo)) return;

  latInput.value = la.toFixed(6);
  lonInput.value = lo.toFixed(6);
  const altN = parseCoord(alt);
  if (Number.isFinite(altN)) altInput.value = altN.toFixed(1);

  const ll = [la, lo];
  if (marker) marker.setLatLng(ll);
  if (fly && map) map.flyTo(ll, Math.max(map.getZoom(), 13), { duration: 0.55 });
  if (reverse) lookupPlace(ll[0], ll[1]);
}

function initMap(defaultLoc) {
  map = L.map("map", { zoomControl: true }).setView(
    [defaultLoc.lat, defaultLoc.lon],
    13
  );
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap",
  }).addTo(map);

  marker = L.marker([defaultLoc.lat, defaultLoc.lon], { draggable: true }).addTo(map);

  map.on("click", (e) => {
    setCoords(e.latlng.lat, e.latlng.lng, altInput.value || defaultLoc.alt, {
      fly: false,
      reverse: true,
    });
  });

  marker.on("dragend", () => {
    const p = marker.getLatLng();
    setCoords(p.lat, p.lng, altInput.value, { fly: false, reverse: true });
  });

  setCoords(defaultLoc.lat, defaultLoc.lon, defaultLoc.alt, { fly: false, reverse: true });
  setTimeout(() => map.invalidateSize(), 50);
}

function applyCamera(cam) {
  if (!cam) return;
  camFocalMm.value = cam.focal_mm ?? "";
  camFnumber.value = cam.fnumber ?? "";
  camFocal35.value = cam.focal_35 ?? "";
  camIso.value = cam.iso ?? "";
  camExpNum.value = cam.exposure_num ?? 1;
  camExpDen.value = cam.exposure_den ?? "";
  camLensMake.value = cam.lens_make ?? "";
  camLensModel.value = cam.lens_model ?? "";
}

function fillCameraFromPhone() {
  const phone = phonesById[phoneSelect.value];
  if (phone?.camera) applyCamera(phone.camera);
}

async function sampleCamera() {
  const id = phoneSelect.value;
  if (!id) return;
  const res = await fetch(`/api/camera/${encodeURIComponent(id)}?sample=1`);
  if (!res.ok) throw new Error("Nepodarilo sa načítať kameru.");
  applyCamera(await res.json());
}

async function loadPresets() {
  const res = await fetch("/api/presets");
  if (!res.ok) throw new Error("Nepodarilo sa načítať presety.");
  const data = await res.json();
  fillSelect(phoneSelect, data.phones, "Vyber telefón…");
  fillSelect(locationSelect, data.locations, "Preset mesta…");
  phonesById = Object.fromEntries(data.phones.map((p) => [p.id, p]));
  phoneSelect.value = "iphone-15-pro";
  fillCameraFromPhone();

  locationsById = Object.fromEntries(data.locations.map((l) => [l.id, l]));
  const def = locationsById["sk-bratislava"] || data.locations[0];
  locationSelect.value = def.id;
  initMap(def);
}

function updateFileLabel() {
  const files = [...(mediaInput.files || [])];
  if (files.length === 1) {
    dropTitle.textContent = files[0].name;
    dropzone.classList.add("has-file");
    fileListEl.hidden = true;
    fileListEl.innerHTML = "";
  } else if (files.length > 1) {
    dropTitle.textContent = `${files.length} súborov vybraných`;
    dropzone.classList.add("has-file");
    fileListEl.hidden = false;
    fileListEl.innerHTML = files
      .map((f) => `<li>${escapeHtml(f.name)} <span style="opacity:.6">(${Math.round(f.size / 1024)} KB)</span></li>`)
      .join("");
  } else {
    dropTitle.textContent = "Presuň fotky alebo video sem";
    dropzone.classList.remove("has-file");
    fileListEl.hidden = true;
    fileListEl.innerHTML = "";
  }
}

["dragenter", "dragover"].forEach((evt) => {
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.classList.add("dragover");
  });
});

["dragleave", "drop"].forEach((evt) => {
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
  });
});

dropzone.addEventListener("drop", (e) => {
  const files = [...(e.dataTransfer?.files || [])];
  if (!files.length) return;
  const dt = new DataTransfer();
  files.forEach((f) => dt.items.add(f));
  mediaInput.files = dt.files;
  updateFileLabel();
});

mediaInput.addEventListener("change", updateFileLabel);
randomCheck.addEventListener("change", syncRandomUi);
noGpsCheck.addEventListener("change", syncGpsUi);
phoneSelect.addEventListener("change", fillCameraFromPhone);
resampleCamBtn.addEventListener("click", () => {
  sampleCamera().catch((err) => setStatus(err.message, "error"));
});

locationSelect.addEventListener("change", () => {
  const loc = locationsById[locationSelect.value];
  if (!loc) return;
  setCoords(loc.lat, loc.lon, loc.alt, { fly: true, reverse: true });
});

function applyManualCoords() {
  const lat = parseCoord(latInput.value);
  const lon = parseCoord(lonInput.value);
  if (Number.isFinite(lat) && Number.isFinite(lon)) {
    setCoords(lat, lon, altInput.value, { fly: true, reverse: true });
  }
}

latInput.addEventListener("change", applyManualCoords);
lonInput.addEventListener("change", applyManualCoords);
altInput.addEventListener("change", () => {
  const a = parseCoord(altInput.value);
  if (Number.isFinite(a)) altInput.value = a.toFixed(1);
});

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  resultEl.hidden = true;
  setStatus("");

  if (!mediaInput.files?.length) {
    setStatus("Najprv vyber foto alebo video.", "error");
    return;
  }
  if (!randomCheck.checked && !phoneSelect.value) {
    setStatus("Vyber telefón alebo zapni Random.", "error");
    return;
  }
  if (!noGpsCheck.checked && (!latInput.value || !lonInput.value)) {
    setStatus("Klikni na mapu alebo zadaj lat/lon.", "error");
    return;
  }

  const fd = new FormData();
  [...mediaInput.files].forEach((f) => fd.append("file", f));
  if (phoneSelect.value) fd.append("phone", phoneSelect.value);
  if (locationSelect.value) fd.append("location", locationSelect.value);
  if (whenInput.value) {
    fd.append("when", whenInput.value.length === 16 ? `${whenInput.value}:00` : whenInput.value);
  }
  if (randomCheck.checked) fd.append("random", "1");
  if (noGpsCheck.checked) fd.append("no_gps", "1");
  fd.append("wipe", wipeCheck.checked ? "1" : "0");

  if (!noGpsCheck.checked) {
    const la = parseCoord(latInput.value);
    const lo = parseCoord(lonInput.value);
    const al = parseCoord(altInput.value);
    if (!Number.isFinite(la) || !Number.isFinite(lo)) {
      setStatus("Neplatné GPS súradnice (použi bodku alebo čiarku).", "error");
      return;
    }
    fd.append("lat", String(la));
    fd.append("lon", String(lo));
    fd.append("alt", Number.isFinite(al) ? String(al) : "0");
    fd.append("city", cityInput.value || "");
    fd.append("country", countryInput.value || "");
    fd.append("country_code", countryCodeInput.value || "");
  }

  // Editable camera EXIF
  fd.append("focal_mm", camFocalMm.value);
  fd.append("fnumber", camFnumber.value);
  fd.append("focal_35", camFocal35.value);
  fd.append("iso", camIso.value);
  fd.append("exposure_num", camExpNum.value || "1");
  fd.append("exposure_den", camExpDen.value);
  fd.append("lens_make", camLensMake.value);
  fd.append("lens_model", camLensModel.value);

  submitBtn.disabled = true;
  const n = mediaInput.files.length;
  setStatus(
    wipeCheck.checked
      ? `Mažem metadata a zapisujem nové (${n})…`
      : `Zapisujem metadata (${n})…`
  );

  try {
    const res = await fetch("/api/spoof", { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Spoof zlyhal.");

    const s = data.summary;
    const kindLabel =
      s.kind === "image" ? "foto" : s.kind === "batch" ? `batch (${s.count})` : "video";
    let itemsHtml = "";
    if (data.items && data.items.length > 1) {
      itemsHtml = `<ul class="batch-list">${data.items
        .map(
          (it) =>
            `<li><span>${escapeHtml(it.original)}</span><strong>${escapeHtml(it.filename)}</strong></li>`
        )
        .join("")}</ul>`;
    }
    let errHtml = "";
    if (data.errors && data.errors.length) {
      errHtml = `<p class="status error">${data.errors.length} súbor(ov) zlyhalo</p>`;
    }
    summaryEl.innerHTML = `
      <dt>súbor</dt><dd>${escapeHtml(s.original)} → <strong>${escapeHtml(s.filename || data.download_name || "—")}</strong></dd>
      <dt>typ</dt><dd>${escapeHtml(kindLabel)}</dd>
      <dt>telefón</dt><dd>${escapeHtml(s.phone)}</dd>
      <dt>miesto</dt><dd>${escapeHtml(s.location)}</dd>
      <dt>mesto</dt><dd>${escapeHtml(s.city || "—")}</dd>
      <dt>krajina</dt><dd>${escapeHtml(s.country || "—")}${s.country_code ? ` (${escapeHtml(s.country_code)})` : ""}</dd>
      <dt>čas</dt><dd>${escapeHtml(s.when)}</dd>
      <dt>wipe</dt><dd>${s.wipe ? "áno — staré tagy premazané" : "nie"}</dd>
    `;
    metaEl.textContent = formatMeta(data.metadata);
    const resultHead = resultEl.querySelector(".result-head");
    let listHost = resultEl.querySelector(".batch-host");
    if (!listHost) {
      listHost = document.createElement("div");
      listHost.className = "batch-host";
      resultHead.insertAdjacentElement("afterend", listHost);
    }
    listHost.innerHTML = itemsHtml + errHtml;

    downloadBtn.href = data.download_url;
    downloadBtn.setAttribute("download", data.download_name || "IMG_0001.JPG");
    downloadBtn.textContent = data.batch
      ? `Stiahnuť ZIP (${data.count})`
      : `Stiahnuť ${data.download_name || "súbor"}`;
    resultEl.hidden = false;
    setStatus(
      data.batch
        ? `Hotovo — ${data.count} súborov v ZIP.`
        : "Hotovo — môžeš stiahnuť súbor.",
      "ok"
    );
  } catch (err) {
    setStatus(err.message || "Chyba", "error");
  } finally {
    submitBtn.disabled = false;
  }
});

function escapeHtml(str) {
  return String(str)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function formatMeta(meta) {
  if (!meta || !Object.keys(meta).length) return "(žiadne tagy)";
  const width = Math.max(...Object.keys(meta).map((k) => k.length));
  return Object.entries(meta)
    .map(([k, v]) => `${k.padEnd(width)}  ${v}`)
    .join("\n");
}

loadPresets().catch((err) => setStatus(err.message, "error"));
