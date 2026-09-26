const form = document.getElementById("spoof-form");
const dropzone = document.getElementById("dropzone");
const videoInput = document.getElementById("video");
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
const latInput = document.getElementById("lat");
const lonInput = document.getElementById("lon");
const altInput = document.getElementById("alt");
const cityInput = document.getElementById("city");
const countryInput = document.getElementById("country");
const countryCodeInput = document.getElementById("country_code");

let locationsById = {};
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

function lookupPlace(lat, lon) {
  clearTimeout(reverseTimer);
  reverseTimer = setTimeout(async () => {
    placeLabel.textContent = "Hľadám miesto…";
    try {
      const url = `/api/reverse?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error("reverse failed");
      const data = await res.json();
      cityInput.value = data.city || "Unknown";
      countryInput.value = data.country || "Unknown";
      countryCodeInput.value = data.country_code || "";
      placeLabel.textContent = `${data.city}, ${data.country}`;
    } catch {
      placeLabel.textContent = `${Number(lat).toFixed(5)}, ${Number(lon).toFixed(5)}`;
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
  latInput.value = Number(lat).toFixed(6);
  lonInput.value = Number(lon).toFixed(6);
  if (alt != null && alt !== "") altInput.value = Number(alt).toFixed(1);

  const ll = [Number(lat), Number(lon)];
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

async function loadPresets() {
  const res = await fetch("/api/presets");
  if (!res.ok) throw new Error("Nepodarilo sa načítať presety.");
  const data = await res.json();
  fillSelect(phoneSelect, data.phones, "Vyber telefón…");
  fillSelect(locationSelect, data.locations, "Preset mesta…");
  phoneSelect.value = "iphone-15-pro";

  locationsById = Object.fromEntries(data.locations.map((l) => [l.id, l]));
  const def = locationsById["sk-bratislava"] || data.locations[0];
  locationSelect.value = def.id;
  initMap(def);
}

function updateFileLabel() {
  const file = videoInput.files?.[0];
  if (file) {
    dropTitle.textContent = file.name;
    dropzone.classList.add("has-file");
  } else {
    dropTitle.textContent = "Presuň video sem";
    dropzone.classList.remove("has-file");
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
  const file = e.dataTransfer?.files?.[0];
  if (!file) return;
  const dt = new DataTransfer();
  dt.items.add(file);
  videoInput.files = dt.files;
  updateFileLabel();
});

videoInput.addEventListener("change", updateFileLabel);
randomCheck.addEventListener("change", syncRandomUi);
noGpsCheck.addEventListener("change", syncGpsUi);

locationSelect.addEventListener("change", () => {
  const loc = locationsById[locationSelect.value];
  if (!loc) return;
  setCoords(loc.lat, loc.lon, loc.alt, { fly: true, reverse: true });
});

function applyManualCoords() {
  const lat = parseFloat(latInput.value);
  const lon = parseFloat(lonInput.value);
  if (Number.isFinite(lat) && Number.isFinite(lon)) {
    setCoords(lat, lon, altInput.value, { fly: true, reverse: true });
  }
}

latInput.addEventListener("change", applyManualCoords);
lonInput.addEventListener("change", applyManualCoords);

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  resultEl.hidden = true;
  setStatus("");

  if (!videoInput.files?.length) {
    setStatus("Najprv vyber video.", "error");
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
  fd.append("video", videoInput.files[0]);
  if (phoneSelect.value) fd.append("phone", phoneSelect.value);
  if (locationSelect.value) fd.append("location", locationSelect.value);
  if (whenInput.value) {
    fd.append("when", whenInput.value.length === 16 ? `${whenInput.value}:00` : whenInput.value);
  }
  if (randomCheck.checked) fd.append("random", "1");
  if (noGpsCheck.checked) fd.append("no_gps", "1");
  fd.append("wipe", wipeCheck.checked ? "1" : "0");

  if (!noGpsCheck.checked) {
    fd.append("lat", latInput.value);
    fd.append("lon", lonInput.value);
    fd.append("alt", altInput.value || "0");
    fd.append("city", cityInput.value || "");
    fd.append("country", countryInput.value || "");
    fd.append("country_code", countryCodeInput.value || "");
  }

  submitBtn.disabled = true;
  setStatus(wipeCheck.checked ? "Mažem staré metadata a zapisujem nové…" : "Zapisujem metadata…");

  try {
    const res = await fetch("/api/spoof", { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Spoof zlyhal.");

    const s = data.summary;
    summaryEl.innerHTML = `
      <dt>súbor</dt><dd>${escapeHtml(s.original)} → <strong>${escapeHtml(s.filename || data.download_name || "—")}</strong></dd>
      <dt>telefón</dt><dd>${escapeHtml(s.phone)}</dd>
      <dt>miesto</dt><dd>${escapeHtml(s.location)}</dd>
      <dt>mesto</dt><dd>${escapeHtml(s.city || "—")}</dd>
      <dt>krajina</dt><dd>${escapeHtml(s.country || "—")}${s.country_code ? ` (${escapeHtml(s.country_code)})` : ""}</dd>
      <dt>čas</dt><dd>${escapeHtml(s.when)}</dd>
      <dt>wipe</dt><dd>${s.wipe ? "áno — staré tagy premazané" : "nie"}</dd>
    `;
    metaEl.textContent = formatMeta(data.metadata);
    downloadBtn.href = data.download_url;
    downloadBtn.setAttribute("download", data.download_name || "IMG_0001.MOV");
    downloadBtn.textContent = `Stiahnuť ${data.download_name || "video"}`;
    resultEl.hidden = false;
    setStatus("Hotovo — môžeš stiahnuť video.", "ok");
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
