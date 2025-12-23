// static/js/expand.js
// EarthCity — Country Expansion (separate module, does NOT break map.js)
// Adds:
//  - Topbar button near Factories
//  - "Expand" button inside country panel when selected country is yours
//  - Expansion drawing mode (points/line/fill) with nicer radius/LOD
// Calls backend endpoint: POST /api/countries/<cid>/expand

(function () {
  const map = window.__earthMap; // from map.js
  if (!map) return console.warn("[expand.js] map not found (window.__earthMap). Load after map.js");

  const $ = (id) => document.getElementById(id);

  // UI we can reuse if exists
  const fbMsg = $("fbMsg");

  function toast(msg) {
    // Prefer fbMsg if exists, else alert-like fallback (soft)
    if (fbMsg) {
      fbMsg.style.display = "block";
      fbMsg.textContent = msg;
      setTimeout(() => {
        // don't hide if user changed it
        if (fbMsg.textContent === msg) {
          fbMsg.style.display = "none";
          fbMsg.textContent = "";
        }
      }, 4500);
      return;
    }
    console.log("[Expand]", msg);
  }

  async function getJSON(url) {
    const r = await fetch(url, { credentials: "include" });
    const j = await r.json().catch(() => ({}));
    return { ok: r.ok, data: j };
  }

  async function postJSON(url, body) {
    const r = await fetch(url, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {})
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
    return j;
  }

  // ---------------------------
  // Helpers (geometry)
  // ---------------------------
  function rad(d) { return d * Math.PI / 180; }

  function pointInRing(lng, lat, ring) {
    if (!ring || ring.length < 4) return false;
    let inside = false;
    const n = ring.length - 1;
    let j = n - 1;
    for (let i = 0; i < n; i++) {
      const xi = ring[i][0], yi = ring[i][1];
      const xj = ring[j][0], yj = ring[j][1];
      const intersect = ((yi > lat) !== (yj > lat)) &&
        (lng < (xj - xi) * (lat - yi) / ((yj - yi) || 1e-12) + xi);
      if (intersect) inside = !inside;
      j = i;
    }
    return inside;
  }

  // quick "touch/overlap" check (edge intersect + contains)
  function orient(a, b, c) {
    return (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0]);
  }
  function onSegment(a, b, c) {
    return (Math.min(a[0], b[0]) <= c[0] && c[0] <= Math.max(a[0], b[0]) &&
            Math.min(a[1], b[1]) <= c[1] && c[1] <= Math.max(a[1], b[1]));
  }
  function segmentsIntersect(p1, p2, q1, q2) {
    const o1 = orient(p1, p2, q1);
    const o2 = orient(p1, p2, q2);
    const o3 = orient(q1, q2, p1);
    const o4 = orient(q1, q2, p2);

    if ((o1 > 0) !== (o2 > 0) && (o3 > 0) !== (o4 > 0)) return true;

    const eps = 1e-12;
    if (Math.abs(o1) < eps && onSegment(p1, p2, q1)) return true;
    if (Math.abs(o2) < eps && onSegment(p1, p2, q2)) return true;
    if (Math.abs(o3) < eps && onSegment(q1, q2, p1)) return true;
    if (Math.abs(o4) < eps && onSegment(q1, q2, p2)) return true;

    return false;
  }

  function ringsIntersect(ringAClosed, ringBClosed) {
    if (!ringAClosed || !ringBClosed) return false;
    const A = ringAClosed.slice(0, -1);
    const B = ringBClosed.slice(0, -1);
    if (A.length < 3 || B.length < 3) return false;

    for (let i = 0; i < A.length; i++) {
      const p1 = A[i], p2 = A[(i + 1) % A.length];
      for (let j = 0; j < B.length; j++) {
        const q1 = B[j], q2 = B[(j + 1) % B.length];
        if (segmentsIntersect(p1, p2, q1, q2)) return true;
      }
    }

    if (pointInRing(B[0][0], B[0][1], ringAClosed)) return true;
    if (pointInRing(A[0][0], A[0][1], ringBClosed)) return true;

    return false;
  }

  function polygonAreaKm2(pointsLngLatClosed) {
    const ring = pointsLngLatClosed.slice(0, -1);
    if (ring.length < 3) return 0;

    const R = 6371.0088;
    let lat0 = 0;
    for (const p of ring) lat0 += p[1];
    lat0 /= ring.length;
    const lat0r = rad(lat0);

    const xy = ring.map(([lng, lat]) => {
      const x = R * rad(lng) * Math.cos(lat0r);
      const y = R * rad(lat);
      return [x, y];
    });

    let s = 0;
    for (let i = 0; i < xy.length; i++) {
      const [x1, y1] = xy[i];
      const [x2, y2] = xy[(i + 1) % xy.length];
      s += x1 * y2 - x2 * y1;
    }
    return Math.abs(s) / 2;
  }

  // ---------------------------
  // State
  // ---------------------------
  let mode = "idle"; // idle | expand
  let expandCountryId = null;
  let points = []; // {lng,lat}

  // cached
  let ME = null;
  let countriesFC = null;

  async function refreshMe() {
    const { ok, data } = await getJSON("/api/me");
    if (!ok) ME = null;
    else ME = data;
    return ME;
  }

  async function refreshCountries() {
    const { ok, data } = await getJSON("/api/countries");
    if (!ok || !data.ok) countriesFC = { type: "FeatureCollection", features: [] };
    else countriesFC = data.data || { type: "FeatureCollection", features: [] };

    if (map.getSource("countries") && countriesFC) {
      try { map.getSource("countries").setData(countriesFC); } catch {}
    }
    return countriesFC;
  }

  function findMyCountryFeature() {
    if (!ME?.authenticated || !countriesFC?.features) return null;
    return countriesFC.features.find(f => (f?.properties?.owner === ME.username)) || null;
  }

  function getCountryFeatureById(cid) {
    return (countriesFC?.features || []).find(f => Number(f?.properties?.id) === Number(cid)) || null;
  }

  function myCountryId() {
    const f = findMyCountryFeature();
    return f ? Number(f.properties.id) : null;
  }

  // ---------------------------
  // Layers for expansion draft
  // ---------------------------
  const SRC = "expandDraft";
  const FC = { type: "FeatureCollection", features: [] };

  function ensureLayers() {
    if (map.getSource(SRC)) return;

    map.addSource(SRC, { type: "geojson", data: FC });

    // Fill (soft)
    map.addLayer({
      id: "expand-fill",
      type: "fill",
      source: SRC,
      filter: ["==", ["get", "kind"], "poly"],
      paint: {
        "fill-color": "rgba(34,197,94,0.55)",
        "fill-opacity": ["interpolate", ["linear"], ["zoom"], 1.2, 0.10, 3.0, 0.16, 6.0, 0.22]
      }
    });

    // Line (glow-ish)
    map.addLayer({
      id: "expand-line",
      type: "line",
      source: SRC,
      filter: ["==", ["get", "kind"], "line"],
      paint: {
        "line-color": "rgba(255,255,255,0.95)",
        "line-width": ["interpolate", ["linear"], ["zoom"], 1.0, 1.8, 2.6, 3.2, 4.0, 4.6, 6.0, 6.2],
        "line-opacity": 0.96
      }
    });

    // Points — красивіший “радіус” на зумі + обводка
    map.addLayer({
      id: "expand-points",
      type: "circle",
      source: SRC,
      filter: ["==", ["get", "kind"], "pts"],
      paint: {
        "circle-radius": [
          "interpolate", ["exponential", 1.25], ["zoom"],
          1.0, 4.0,
          2.0, 5.5,
          3.0, 7.5,
          4.0, 10.5,
          6.0, 14.0
        ],
        "circle-color": "rgba(34,197,94,1)",
        "circle-opacity": 0.95,
        "circle-stroke-width": [
          "interpolate", ["linear"], ["zoom"],
          1.0, 1.2,
          4.0, 1.6,
          6.0, 2.0
        ],
        "circle-stroke-color": "rgba(0,0,0,0.55)"
      }
    });
  }

  function setData() {
    const coords = points.map(p => [p.lng, p.lat]);
    FC.features = [];

    if (coords.length) {
      FC.features.push({
        type: "Feature",
        properties: { kind: "pts" },
        geometry: { type: "MultiPoint", coordinates: coords }
      });
    }
    if (coords.length >= 2) {
      FC.features.push({
        type: "Feature",
        properties: { kind: "line" },
        geometry: { type: "LineString", coordinates: coords }
      });
    }
    if (coords.length >= 3) {
      const closed = coords.concat([coords[0]]);
      FC.features.push({
        type: "Feature",
        properties: { kind: "poly" },
        geometry: { type: "Polygon", coordinates: [closed] }
      });
    }

    const s = map.getSource(SRC);
    if (s) s.setData(FC);
  }

  function clearDraft() {
    points = [];
    FC.features = [];
    const s = map.getSource(SRC);
    if (s) s.setData(FC);
  }

  // ---------------------------
  // Validation (client-side hints)
  // Backend must validate strictly.
  // ---------------------------
  function draftClosedRing() {
    if (points.length < 3) return null;
    const ring = points.map(p => [p.lng, p.lat]);
    ring.push([points[0].lng, points[0].lat]);
    return ring;
  }

  function intersectsOtherCountries(myCid, draftRingClosed) {
    const feats = (countriesFC?.features || []).filter(f => Number(f?.properties?.id) !== Number(myCid));
    for (const f of feats) {
      const ring2 = f?.geometry?.coordinates?.[0];
      if (!ring2 || ring2.length < 4) continue;
      if (ringsIntersect(draftRingClosed, ring2)) return true;
    }
    return false;
  }

  function touchesMyCountry(myCid, draftRingClosed) {
    const mine = getCountryFeatureById(myCid);
    const myRing = mine?.geometry?.coordinates?.[0];
    if (!myRing || myRing.length < 4) return false;

    // touch/overlap (simple)
    if (ringsIntersect(draftRingClosed, myRing)) return true;

    // or at least one vertex inside my polygon
    const pts = draftRingClosed.slice(0, -1);
    for (const p of pts) {
      if (pointInRing(p[0], p[1], myRing)) return true;
    }
    return false;
  }

  // ---------------------------
  // UI controls
  // ---------------------------
  let topBtn = null;

  function ensureTopButton() {
    if (topBtn) return;

    const factoriesBtn = $("btnOpenFactories");
    if (!factoriesBtn) return;

    topBtn = document.createElement("button");
    topBtn.type = "button";
    topBtn.className = "btn-ghost";
    topBtn.id = "btnExpand";
    topBtn.textContent = "🧩 Expand";
    topBtn.title = "Expand your country";

    factoriesBtn.insertAdjacentElement("afterend", topBtn);

    topBtn.addEventListener("click", async () => {
      await refreshMe();
      await refreshCountries();

      if (!ME?.authenticated) return toast("🔒 Спочатку Login.");
      if (!ME?.is_confirmed) return toast("📩 Підтверди email, щоб розширювати країну.");
      const cid = myCountryId();
      if (!cid) return toast("🏳️ Спочатку створи країну.");

      startExpand(cid);
    });
  }

  // Country panel button (only if yours)
  const countryPanel = $("countryPanel");
  const cpRow = countryPanel ? countryPanel.querySelector(".cp-row") : null;
  let cpExpandBtn = null;

  function setCountryPanelExpandButton(visible, cid) {
    if (!cpRow) return;

    if (!cpExpandBtn) {
      cpExpandBtn = document.createElement("button");
      cpExpandBtn.type = "button";
      cpExpandBtn.className = "btn-ghost";
      cpExpandBtn.id = "cpExpand";
      cpExpandBtn.textContent = "🧩 Expand";
      cpExpandBtn.title = "Expand this country";
      cpExpandBtn.style.display = "none";
      cpRow.appendChild(cpExpandBtn);

      cpExpandBtn.addEventListener("click", async () => {
        if (!cid) return;
        await refreshMe();
        await refreshCountries();

        if (!ME?.authenticated) return toast("🔒 Спочатку Login.");
        if (!ME?.is_confirmed) return toast("📩 Підтверди email, щоб розширювати країну.");
        startExpand(cid);
      });
    }

    cpExpandBtn.style.display = visible ? "inline-flex" : "none";
  }

  async function detectCountryPanelMineAndToggle() {
    // map.js already fills cpId and cpSub; we read cpId and ask backend for is_mine
    const cpId = $("cpId");
    const cid = Number(cpId?.textContent || 0);
    if (!cid) return setCountryPanelExpandButton(false, null);

    try {
      const { ok, data } = await getJSON(`/api/countries/${cid}`);
      if (!ok || !data.ok) return setCountryPanelExpandButton(false, null);
      const isMine = !!data.data?.is_mine;
      setCountryPanelExpandButton(isMine, cid);
    } catch {
      setCountryPanelExpandButton(false, null);
    }
  }

  function observeCountryPanel() {
    if (!countryPanel) return;

    const obs = new MutationObserver(() => {
      const open = countryPanel.classList.contains("open");
      if (!open) return setCountryPanelExpandButton(false, null);
      detectCountryPanelMineAndToggle();
    });

    obs.observe(countryPanel, { attributes: true, attributeFilter: ["class"] });
  }

  // ---------------------------
  // Expand mode
  // ---------------------------
  function startExpand(cid) {
    expandCountryId = Number(cid);
    mode = "expand";
    clearDraft();
    ensureLayers();

    map.getCanvas().style.cursor = "crosshair";
    toast("🧩 Expand mode: клікай точки навколо/біля своєї країни → подвійний клік або Enter щоб Finish. Esc щоб Cancel.");
  }

  async function finishExpand() {
    const cid = expandCountryId;
    const ring = draftClosedRing();
    if (!cid || !ring) return;

    // simple client-side checks
    if (!touchesMyCountry(cid, ring)) {
      return toast("⚠️ Полігон має торкатись твоєї країни (або частково заходити на неї).");
    }
    if (intersectsOtherCountries(cid, ring)) {
      return toast("⛔ Полігон перетинає іншу країну — так не можна.");
    }

    const area = polygonAreaKm2(ring);
    const prettyArea = Math.round(area).toLocaleString("en-US");
    toast(`⏳ Надсилаю розширення… (+${prettyArea} км²)`);

    try {
      // backend endpoint should handle:
      // - land check
      // - overlap check
      // - merge geometry (union)
      // - coin cost + deduction
      const res = await postJSON(`/api/countries/${cid}/expand`, {
        geometry: { type: "Polygon", coordinates: [ring] }
      });

      // refresh world
      await refreshCountries();
      await refreshMe();

      toast(`✅ Готово! Розширення збережено. Монети: ${res.coins ?? "?"} EC`);

      stopExpand();
    } catch (e) {
      // If endpoint doesn't exist yet, show friendly hint
      const msg = (e && e.message) ? e.message : "Failed";
      toast(`❌ ${msg} (бекенд /expand ще треба додати в app.py)`);
    }
  }

  function stopExpand() {
    mode = "idle";
    expandCountryId = null;
    clearDraft();
    map.getCanvas().style.cursor = "";
  }

  function undoPoint() {
    if (!points.length) return;
    points.pop();
    setData();
  }

  // ---------------------------
  // Events
  // ---------------------------
  map.on("style.load", () => {
    ensureTopButton();
    observeCountryPanel();
  });

  // click to add points
  map.on("click", (e) => {
    if (mode !== "expand") return;

    points.push({ lng: e.lngLat.lng, lat: e.lngLat.lat });
    setData();
  });

  // dblclick to finish
  map.on("dblclick", (e) => {
    if (mode !== "expand") return;
    e.preventDefault();
    finishExpand();
  });

  // keyboard shortcuts
  window.addEventListener("keydown", (ev) => {
    if (mode !== "expand") return;

    if (ev.key === "Escape") {
      ev.preventDefault();
      toast("✖ Expand cancelled.");
      stopExpand();
    } else if (ev.key === "Backspace") {
      ev.preventDefault();
      undoPoint();
    } else if (ev.key === "Enter") {
      ev.preventDefault();
      if (points.length >= 3) finishExpand();
      else toast("Ще замало точок (мінімум 3).");
    }
  }, { passive: false });

})();
