// static/js/map.js
// EarthCity — Globe + Resources(server, LOD) + Countries + Create Country + Factories(server)
// OPTIMIZED + UX+++ (NO backend changes)
//
// ✅ EXPAND TERRITORY UX+++ (Border Edit Mode)
//  - Hover line: shows GREEN segment where point will be inserted
//  - Click on LINE = insert point into nearest segment (comfortable tolerance)
//  - Alt+Click = insert even if you clicked a bit farther (force insert)
//  - Drag points (handles) with snap to ghost border if close
//  - Shift+Click on a point = delete point
//  - Ctrl+Z / Ctrl+Y = Undo / Redo for insert/drag/delete
//  - Clear user hints + “why disabled” (button title) + better cursor + point hover highlight
//
// NOTE: This file assumes your HTML ids exist (as in your current layout).

(function () {
  const $ = (id) => document.getElementById(id);

  // ---- UI refs ----
  const starsEl = $("stars");
  const coordsEl = $("coords");
  const zoomEl = $("zoom");

  // Country build UI
  const btnCreateCountry = $("btnCreateCountry");
  const btnExpandCountry = $("btnExpandCountry");
  const buildActions = $("buildActions");
  const btnUndo = $("btnUndo");
  const btnCancel = $("btnCancel");
  const btnFinish = $("btnFinish");

  // Save Country modal
  const countryOverlay = $("countryOverlay");
  const countryName = $("countryName");
  const countryColor = $("countryColor");
  const countryMsg = $("countryMsg");
  const btnSaveCountry = $("btnSaveCountry");
  const btnCloseCountry = $("btnCloseCountry");

  // Stats
  const draftAreaEl = $("draftArea");
  const draftCostEl = $("draftCost");
  const myCoinsEl = $("myCoins");
  const myCoinsModalEl = $("myCoinsModal");
  const topCoinsEl = $("topCoins");

  // Left factory sidebar
  const factorybar = $("factorybar");
  const fbToggle = $("fbToggle");
  const fbSub = $("fbSub");
  const fbMsg = $("fbMsg");
  const fbBlueprints = $("fbBlueprints");
  const fbSelected = $("fbSelected");
  const fbMyFactories = $("fbMyFactories");
  const btnFactoryMode = $("btnFactoryMode");
  const btnCancelFactoryMode = $("btnCancelFactoryMode");
  const btnTipFactory = $("btnTipFactory");
  const fbTip = $("fbTip");

  // Topbar factories button
  const btnOpenFactories = $("btnOpenFactories");

  // =========================================================
  // Stars background
  // =========================================================
  if (starsEl) {
    const N = 200;
    for (let i = 0; i < N; i++) {
      const s = document.createElement("div");
      s.className = "star";
      s.style.left = Math.random() * 100 + "%";
      s.style.top = Math.random() * 100 + "%";
      const size = 1 + Math.random() * 2.0;
      s.style.width = size + "px";
      s.style.height = size + "px";
      s.style.animationDelay = Math.random() * 4 + "s";
      s.style.opacity = String(0.22 + Math.random() * 0.68);
      starsEl.appendChild(s);
    }
  }

  function updateStarsVisibility(map) {
    const z = map.getZoom();
    let opacity = 1;
    if (z >= 3.0) opacity = 0;
    else if (z > 2.0) opacity = 1 - (z - 2.0);
    if (starsEl) starsEl.style.opacity = opacity.toFixed(2);
  }

  // =========================================================
  // Helpers
  // =========================================================
  function rad(d) { return (d * Math.PI) / 180; }

  function angularDistanceRad(lng1, lat1, lng2, lat2) {
    const φ1 = rad(lat1), φ2 = rad(lat2);
    const Δλ = rad(lng2 - lng1);
    const sinφ1 = Math.sin(φ1), sinφ2 = Math.sin(φ2);
    const cosφ1 = Math.cos(φ1), cosφ2 = Math.cos(φ2);
    const cosc = sinφ1 * sinφ2 + cosφ1 * cosφ2 * Math.cos(Δλ);
    return Math.acos(Math.min(1, Math.max(-1, cosc)));
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

  function formatKm2(v) {
    const n = Math.round(v);
    return n.toLocaleString("en-US") + " км²";
  }

  function debounce(fn, ms) {
    let t = null;
    return (...args) => {
      clearTimeout(t);
      t = setTimeout(() => fn(...args), ms);
    };
  }

  function rafThrottle(fn) {
    let raf = 0;
    let lastArgs = null;
    return (...args) => {
      lastArgs = args;
      if (raf) return;
      raf = requestAnimationFrame(() => {
        raf = 0;
        fn(...lastArgs);
      });
    };
  }

  // =========================================================
  // User-friendly message system (non-spam)
  // =========================================================
  let lastFbText = "";
  let lastFbAt = 0;

  function showFbMsg(text, ttlMs = 0) {
    if (!fbMsg) return;
    const now = Date.now();
    if (text === lastFbText && now - lastFbAt < 900) return;

    lastFbText = text;
    lastFbAt = now;

    fbMsg.style.display = "block";
    fbMsg.textContent = text;

    if (ttlMs > 0) {
      const cur = text;
      setTimeout(() => {
        if (fbMsg && fbMsg.textContent === cur) {
          fbMsg.style.display = "none";
          fbMsg.textContent = "";
        }
      }, ttlMs);
    }
  }

  function hideFbMsg() {
    if (!fbMsg) return;
    fbMsg.style.display = "none";
    fbMsg.textContent = "";
    lastFbText = "";
  }

  // =========================================================
  // Rules + user state
  // =========================================================
  let RULES = {
    start_coins: 5000,
    country_base_cost: 800,
    country_cost_per_1000_km2: 35,
    country_max_area_km2: 250000,
    country_max_points: 60,
    factory_place_fee: 120,
    factory_pick_radius_km: 120,
    factory_max_per_country: 40
  };

  let MY_COINS = 0;
  let ME = { authenticated: false, username: null, has_country: false };

  async function loadRules() {
    const r = await fetch("/api/rules", { credentials: "include" });
    const j = await r.json().catch(() => ({}));
    if (j.ok && j.rules) RULES = j.rules;
  }

  async function refreshMe() {
    const r = await fetch("/api/me", { credentials: "include" });
    const j = await r.json().catch(() => ({}));
    ME = j || { authenticated: false };
    MY_COINS = j && typeof j.coins === "number" ? j.coins : 0;

    const pretty = `${MY_COINS} EC`;
    if (myCoinsEl) myCoinsEl.textContent = `💰 ${pretty}`;
    if (myCoinsModalEl) myCoinsModalEl.textContent = `${pretty}`;
    if (topCoinsEl) topCoinsEl.textContent = `💰 ${pretty}`;
  }

  function computeCountryCost(areaKm2) {
    return Math.round(
      RULES.country_base_cost + (areaKm2 / 1000) * RULES.country_cost_per_1000_km2
    );
  }

  // =========================================================
  // Map style
  // =========================================================
  const rasterStyle = {
    version: 8,
    sources: {
      "esri-imagery": {
        type: "raster",
        tiles: [
          "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
        ],
        tileSize: 256,
        attribution: "Tiles © Esri"
      }
    },
    layers: [
      { id: "bg", type: "background", paint: { "background-color": "#05070c" } },
      {
        id: "earth",
        type: "raster",
        source: "esri-imagery",
        paint: {
          "raster-saturation": 0.18,
          "raster-contrast": 0.12,
          "raster-brightness-min": 0.05,
          "raster-brightness-max": 0.96,
          "raster-fade-duration": 200
        }
      }
    ]
  };

  const map = new maplibregl.Map({
    container: "map",
    style: rasterStyle,
    center: [20, 35],
    zoom: 1.7,
    pitch: 18,
    bearing: 0,
    antialias: true
  });
  window.__earthMap = map;

  map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");
  map.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-right");

  // =========================================================
  // LAND CHECK — requires static/data/land.geojson
  // =========================================================
  let LAND = { type: "FeatureCollection", features: [] };
  let LAND_READY = false;

  async function loadLand() {
    try {
      const r = await fetch("/static/data/land.geojson", { cache: "force-cache" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const j = await r.json();
      if (j && j.type === "FeatureCollection") {
        LAND = j;
        LAND_READY = true;
      }
    } catch (e) {
      LAND_READY = false;
      console.warn("land.geojson missing or invalid. Sea check disabled.", e);
    }
  }

  function landRingsFromGeometry(geom) {
    const rings = [];
    if (!geom || typeof geom !== "object") return rings;
    const t = geom.type;
    const c = geom.coordinates;

    if (t === "Polygon" && Array.isArray(c) && Array.isArray(c[0])) {
      rings.push(c[0]);
    } else if (t === "MultiPolygon" && Array.isArray(c)) {
      for (const poly of c) {
        if (Array.isArray(poly) && Array.isArray(poly[0])) rings.push(poly[0]);
      }
    }
    return rings;
  }

  function pointInRing(lng, lat, ring) {
    if (!ring || ring.length < 4) return false;
    let inside = false;
    const n = ring.length - 1;
    let j = n - 1;
    for (let i = 0; i < n; i++) {
      const xi = ring[i][0], yi = ring[i][1];
      const xj = ring[j][0], yj = ring[j][1];
      const intersect =
        (yi > lat) !== (yj > lat) &&
        lng < ((xj - xi) * (lat - yi)) / ((yj - yi) || 1e-12) + xi;
      if (intersect) inside = !inside;
      j = i;
    }
    return inside;
  }

  function isPointOnLand(lng, lat) {
    if (!LAND_READY) return null;
    for (const f of LAND.features || []) {
      const rings = landRingsFromGeometry(f && f.geometry);
      for (const ring of rings) {
        if (pointInRing(lng, lat, ring)) return true;
      }
    }
    return false;
  }

  // =========================================================
  // Expand ghost (old border) + hover highlight
  // =========================================================
  const EXPAND_GHOST = { type: "FeatureCollection", features: [] };

  function addExpandGhostLayer() {
    if (map.getSource("expandGhost")) return;

    map.addSource("expandGhost", { type: "geojson", data: EXPAND_GHOST });

    map.addLayer({
      id: "expand-ghost-fill",
      type: "fill",
      source: "expandGhost",
      paint: {
        "fill-color": "rgba(255,255,255,0.45)",
        "fill-opacity": 0.06
      }
    });

    map.addLayer({
      id: "expand-ghost-line",
      type: "line",
      source: "expandGhost",
      paint: {
        "line-color": "rgba(255,255,255,0.65)",
        "line-width": ["interpolate", ["linear"], ["zoom"], 1.2, 1.0, 6.0, 3.2],
        "line-opacity": 0.55,
        "line-dasharray": [2, 2]
      }
    });
  }

  function setExpandGhostFromRingClosed(ringClosed) {
    if (!ringClosed || ringClosed.length < 4) {
      EXPAND_GHOST.features = [];
    } else {
      EXPAND_GHOST.features = [{
        type: "Feature",
        properties: { kind: "ghost" },
        geometry: { type: "Polygon", coordinates: [ringClosed] }
      }];
    }
    const src = map.getSource("expandGhost");
    if (src) src.setData(EXPAND_GHOST);
  }

  // --- Hover highlight segment (where point will be inserted) ---
  const EXPAND_HOVER = { type: "FeatureCollection", features: [] };

  function addExpandHoverLayer() {
    if (map.getSource("expandHover")) return;
    map.addSource("expandHover", { type: "geojson", data: EXPAND_HOVER });

    map.addLayer({
      id: "expand-hover-line",
      type: "line",
      source: "expandHover",
      paint: {
        "line-color": "rgba(34,197,94,0.95)",
        "line-width": ["interpolate", ["linear"], ["zoom"], 1.2, 2.2, 6.0, 6.6],
        "line-opacity": 0.9
      }
    });
  }

  function setExpandHoverSegment(a, b) {
    if (!a || !b) {
      EXPAND_HOVER.features = [];
    } else {
      EXPAND_HOVER.features = [{
        type: "Feature",
        properties: {},
        geometry: { type: "LineString", coordinates: [[a.lng, a.lat], [b.lng, b.lat]] }
      }];
    }
    const src = map.getSource("expandHover");
    if (src) src.setData(EXPAND_HOVER);
  }

  // ✅ NEW: hover point highlight (makes dragging feel obvious)
  const EXPAND_POINT_HOVER = { type: "FeatureCollection", features: [] };
  function addExpandPointHoverLayer() {
    if (map.getSource("expandPointHover")) return;
    map.addSource("expandPointHover", { type: "geojson", data: EXPAND_POINT_HOVER });
    map.addLayer({
      id: "expand-point-hover",
      type: "circle",
      source: "expandPointHover",
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 1.2, 7, 4.0, 10, 6.0, 13],
        "circle-color": "rgba(255,255,255,0.14)",
        "circle-stroke-color": "rgba(255,255,255,0.95)",
        "circle-stroke-width": 2,
        "circle-opacity": 1,
        "circle-blur": 0.15
      }
    });
  }
  function setExpandPointHover(lng, lat, on) {
    if (!on) {
      EXPAND_POINT_HOVER.features = [];
    } else {
      EXPAND_POINT_HOVER.features = [{
        type: "Feature",
        properties: {},
        geometry: { type: "Point", coordinates: [lng, lat] }
      }];
    }
    const src = map.getSource("expandPointHover");
    if (src) src.setData(EXPAND_POINT_HOVER);
  }

  // =========================================================
  // Country-on-country overlap check (client-side)
  // =========================================================
  function orient(a, b, c) { return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]); }
  function onSegment(a, b, c) {
    return (
      Math.min(a[0], b[0]) <= c[0] && c[0] <= Math.max(a[0], b[0]) &&
      Math.min(a[1], b[1]) <= c[1] && c[1] <= Math.max(a[1], b[1])
    );
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

  // =========================================================
  // Draft preview point marker (green/red)
  // =========================================================
  const DRAFT_PREVIEW = { type: "FeatureCollection", features: [] };

  function addDraftPreviewLayer() {
    if (map.getSource("draftPreview")) return;

    map.addSource("draftPreview", { type: "geojson", data: DRAFT_PREVIEW });

    map.addLayer({
      id: "draftPreviewDot",
      type: "circle",
      source: "draftPreview",
      paint: {
        "circle-radius": [
          "interpolate", ["linear"], ["zoom"],
          1.0, 3.2,
          2.2, 4.2,
          4.2, 6.0,
          6.2, 7.0
        ],
        "circle-color": [
          "case",
          ["==", ["get", "ok"], 1], "rgba(34,197,94,1)",
          "rgba(239,68,68,1)"
        ],
        "circle-opacity": 0.92,
        "circle-stroke-color": "rgba(0,0,0,0.55)",
        "circle-stroke-width": 1,
        "circle-blur": 0.15
      }
    });
  }

  function setDraftPreview(lng, lat) {
    if (mode !== "create_country" && mode !== "expand_country") {
      if (DRAFT_PREVIEW.features.length) {
        DRAFT_PREVIEW.features = [];
        if (map.getSource("draftPreview")) map.getSource("draftPreview").setData(DRAFT_PREVIEW);
      }
      return;
    }

    const onLand = isPointOnLand(lng, lat);
    if (onLand === null) {
      DRAFT_PREVIEW.features = [];
      if (map.getSource("draftPreview")) map.getSource("draftPreview").setData(DRAFT_PREVIEW);
      return;
    }

    DRAFT_PREVIEW.features = [{
      type: "Feature",
      properties: { ok: onLand ? 1 : 0 },
      geometry: { type: "Point", coordinates: [lng, lat] }
    }];

    if (map.getSource("draftPreview")) map.getSource("draftPreview").setData(DRAFT_PREVIEW);
  }

  function isDraftOnLand(draftPoints) {
    if (!LAND_READY) return null;
    if (!draftPoints.length) return false;
    for (const p of draftPoints) {
      const ok = isPointOnLand(p.lng, p.lat);
      if (ok !== true) return false;
    }
    return true;
  }

  // =========================================================
  // Resources (server) + LOD
  // =========================================================
  let RESOURCES = { type: "FeatureCollection", features: [] };

  const RESOURCE_META = {
    oil: { icon: "🛢️" }, gas: { icon: "🔥" }, iron: { icon: "⛏️" }, gold: { icon: "🪙" },
    coal: { icon: "🪨" }, uranium: { icon: "☢️" }, rare: { icon: "💎" }, water: { icon: "💧" },
    farmland: { icon: "🌾" }, fish: { icon: "🐟" }, wind: { icon: "🌬️" }, solar: { icon: "☀️" },
    hydro: { icon: "🌊" }, geo: { icon: "🌋" }
  };

  const RESOURCE_RADIUS = [
    "interpolate", ["exponential", 1.45], ["zoom"],
    0.8, 0.7, 1.3, 0.9, 1.7, 1.2, 2.2, 1.55, 2.8, 2.1, 3.4, 2.8, 4.2, 3.6, 5.0, 4.4, 6.2, 5.2
  ];

  const RESOURCE_GLOW_RADIUS = [
    "interpolate", ["exponential", 1.5], ["zoom"],
    0.8, 2.0, 1.5, 3.5, 2.2, 5.5, 3.0, 8.0, 4.2, 11.0, 5.2, 14.0, 6.2, 16.0
  ];

  function addResourceLayers() {
    if (map.getSource("resources")) return;

    map.addSource("resources", { type: "geojson", data: RESOURCES });

    map.addLayer({
      id: "resources-glow",
      type: "circle",
      source: "resources",
      paint: {
        "circle-radius": RESOURCE_GLOW_RADIUS,
        "circle-color": ["match", ["get", "type"],
          "oil", "rgba(250,204,21,0.9)",
          "gas", "rgba(251,146,60,0.9)",
          "iron", "rgba(148,163,184,0.9)",
          "gold", "rgba(251,191,36,0.9)",
          "coal", "rgba(148,163,184,0.9)",
          "uranium", "rgba(34,197,94,0.9)",
          "rare", "rgba(167,139,250,0.9)",
          "water", "rgba(59,130,246,0.9)",
          "farmland", "rgba(34,197,94,0.9)",
          "fish", "rgba(56,189,248,0.9)",
          "wind", "rgba(196,181,253,0.9)",
          "solar", "rgba(253,164,175,0.9)",
          "hydro", "rgba(59,130,246,0.9)",
          "geo", "rgba(244,63,94,0.9)",
          "rgba(34,197,94,0.9)"
        ],
        "circle-opacity": ["interpolate", ["linear"], ["get", "strength"], 0.35, 0.03, 1.0, 0.10],
        "circle-blur": 0.95
      }
    });

    map.addLayer({
      id: "resources-core",
      type: "circle",
      source: "resources",
      paint: {
        "circle-radius": RESOURCE_RADIUS,
        "circle-color": ["match", ["get", "type"],
          "oil", "rgba(250,204,21,1)",
          "gas", "rgba(251,146,60,1)",
          "iron", "rgba(226,232,240,1)",
          "gold", "rgba(251,191,36,1)",
          "coal", "rgba(203,213,225,1)",
          "uranium", "rgba(74,222,128,1)",
          "rare", "rgba(196,181,253,1)",
          "water", "rgba(96,165,250,1)",
          "farmland", "rgba(74,222,128,1)",
          "fish", "rgba(56,189,248,1)",
          "wind", "rgba(196,181,253,1)",
          "solar", "rgba(253,164,175,1)",
          "hydro", "rgba(96,165,250,1)",
          "geo", "rgba(244,63,94,1)",
          "rgba(34,197,94,1)"
        ],
        "circle-opacity": 0.90,
        "circle-stroke-color": "rgba(0,0,0,0.40)",
        "circle-stroke-width": 1,
        "circle-blur": 0.05
      }
    });

    map.addSource("resourcesHover", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
    map.addLayer({
      id: "resources-hover-ring",
      type: "circle",
      source: "resourcesHover",
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 1.0, 7, 3.0, 10, 5.0, 14, 6.2, 16],
        "circle-color": "rgba(255,255,255,0.06)",
        "circle-stroke-color": "rgba(255,255,255,0.75)",
        "circle-stroke-width": 2,
        "circle-opacity": 1,
        "circle-blur": 0.18
      }
    });

    map.on("mouseenter", "resources-core", () => { map.getCanvas().style.cursor = "pointer"; });
    map.on("mouseleave", "resources-core", () => { map.getCanvas().style.cursor = ""; });
  }

  // Tooltip
  const tip = document.createElement("div");
  tip.style.position = "absolute";
  tip.style.zIndex = "50";
  tip.style.pointerEvents = "none";
  tip.style.transform = "translate(-50%, calc(-100% - 10px))";
  tip.style.display = "none";
  tip.style.padding = "10px 12px";
  tip.style.borderRadius = "14px";
  tip.style.backdropFilter = "blur(10px)";
  tip.style.webkitBackdropFilter = "blur(10px)";
  tip.style.background = "rgba(12, 16, 26, .78)";
  tip.style.border = "1px solid rgba(255,255,255,.12)";
  tip.style.boxShadow = "0 12px 28px rgba(0,0,0,.35)";
  tip.style.color = "rgba(255,255,255,.95)";
  tip.style.fontFamily = "Inter, system-ui, -apple-system, Segoe UI, Roboto, sans-serif";
  tip.style.maxWidth = "260px";
  tip.innerHTML = "";
  document.body.appendChild(tip);

  function tipShow(x, y, html) {
    tip.innerHTML = html;
    tip.style.left = `${x}px`;
    tip.style.top = `${y}px`;
    tip.style.display = "block";
  }
  function tipHide() { tip.style.display = "none"; }

  // HTML markers for resources (only close zoom)
  const resourceMarkers = [];
  let RESOURCE_MARKERS_ENABLED = false;
  const RESOURCE_MARKERS_CAP = 120;
  let lastMarkersKey = "";

  function clearResourceMarkers() {
    for (const rm of resourceMarkers) rm.marker.remove();
    resourceMarkers.length = 0;
  }

  function setResourceMarkersEnabled(enabled) {
    enabled = !!enabled;
    if (RESOURCE_MARKERS_ENABLED === enabled) return;
    RESOURCE_MARKERS_ENABLED = enabled;
    if (!enabled) {
      clearResourceMarkers();
      lastMarkersKey = "";
      return;
    }
    rebuildResourceMarkersCapped();
  }

  function makeResourceElement(type, name, strength) {
    const meta = RESOURCE_META[type] || { icon: "✨" };
    const wrap = document.createElement("div");
    wrap.className = "resource-marker";
    wrap.style.display = "flex";
    wrap.style.gap = "8px";
    wrap.style.alignItems = "center";
    wrap.style.padding = "5px 9px";
    wrap.style.borderRadius = "16px";

    const dot = document.createElement("div");
    dot.className = "resource-dot";

    const ico = document.createElement("div");
    ico.className = "resource-ico";
    ico.textContent = meta.icon;

    const label = document.createElement("div");
    label.className = "resource-name";
    label.textContent = name || type;

    const st = document.createElement("div");
    st.className = "resource-strength";
    st.textContent = `${Math.round((Number(strength) || 0) * 100)}%`;

    label.style.fontSize = "11px";
    label.style.lineHeight = "1.05";
    label.style.maxWidth = "110px";
    label.style.whiteSpace = "nowrap";
    label.style.overflow = "hidden";
    label.style.textOverflow = "ellipsis";
    label.style.opacity = "0.88";

    st.style.fontSize = "10px";
    st.style.opacity = "0.75";

    wrap.appendChild(dot);
    wrap.appendChild(ico);
    wrap.appendChild(label);
    wrap.appendChild(st);

    wrap.title = `${name || type} • ${Math.round((Number(strength) || 0) * 100)}%`;
    return wrap;
  }

  function rebuildResourceMarkersCapped() {
    const feats = RESOURCES.features || [];
    const z = map.getZoom();
    if (z < 6.0 || !feats.length) {
      clearResourceMarkers();
      lastMarkersKey = "";
      return;
    }

    const center = map.getCenter();
    const key = `${feats.length}|${center.lng.toFixed(2)}|${center.lat.toFixed(2)}|${z.toFixed(2)}`;
    if (key === lastMarkersKey && resourceMarkers.length) return;
    lastMarkersKey = key;

    clearResourceMarkers();

    const clng = center.lng, clat = center.lat;
    const scored = feats
      .map((f) => {
        const [lng, lat] = f.geometry.coordinates;
        const ang = angularDistanceRad(clng, clat, lng, lat);
        return { f, ang };
      })
      .sort((a, b) => a.ang - b.ang);

    const chosen = scored.slice(0, RESOURCE_MARKERS_CAP);
    for (const it of chosen) {
      const f = it.f;
      const [lng, lat] = f.geometry.coordinates;
      const el = makeResourceElement(f.properties.type, f.properties.name, f.properties.strength);

      const marker = new maplibregl.Marker({ element: el, anchor: "center" })
        .setLngLat([lng, lat])
        .addTo(map);

      resourceMarkers.push({ marker, el });
    }
  }

  // LOD loader
  let lastLODKey = "";
  async function loadResourcesLOD() {
    const b = map.getBounds();
    const z = map.getZoom();

    const bbox = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()]
      .map((v) => +v.toFixed(5))
      .join(",");

    const limit =
      z < 1.8 ? 600 :
      z < 2.5 ? 900 :
      z < 3.2 ? 1400 :
      z < 4.2 ? 2200 :
      z < 5.2 ? 3200 : 4500;

    const key = `${bbox}|${z.toFixed(2)}|${limit}`;
    if (key === lastLODKey) return;
    lastLODKey = key;

    const url = `/api/resources?bbox=${encodeURIComponent(bbox)}&zoom=${encodeURIComponent(z.toFixed(2))}&limit=${limit}`;
    const r = await fetch(url);
    const j = await r.json().catch(() => ({}));
    if (j.ok && j.data) RESOURCES = j.data;

    if (map.getSource("resources")) map.getSource("resources").setData(RESOURCES);

    const wantHtml = z >= 6.0;
    setResourceMarkersEnabled(wantHtml);
    if (wantHtml) rebuildResourceMarkersCapped();
  }

  // =========================================================
  // Countries
  // =========================================================
  let countriesFC = { type: "FeatureCollection", features: [] };
  let selectedCountryId = null;

  async function loadCountries() {
    const res = await fetch("/api/countries", { credentials: "include" });
    const data = await res.json().catch(() => ({}));
    if (!data.ok) return;
    countriesFC = data.data || { type: "FeatureCollection", features: [] };
    if (map.getSource("countries")) map.getSource("countries").setData(countriesFC);
  }

  function addCountriesLayers() {
    if (map.getSource("countries")) return;

    map.addSource("countries", { type: "geojson", data: countriesFC });

    map.addLayer({
      id: "countries-fill",
      type: "fill",
      source: "countries",
      paint: { "fill-color": ["get", "color"], "fill-opacity": 0.20 }
    });

    map.addLayer({
      id: "countries-line",
      type: "line",
      source: "countries",
      paint: {
        "line-color": ["get", "color"],
        "line-width": ["interpolate", ["exponential", 1.25], ["zoom"], 1.2, 1.1, 6, 3.0],
        "line-opacity": 0.88
      }
    });

    map.addLayer({
      id: "countries-selected",
      type: "line",
      source: "countries",
      filter: ["==", ["get", "id"], -1],
      paint: {
        "line-color": "rgba(255,255,255,0.95)",
        "line-width": ["interpolate", ["exponential", 1.2], ["zoom"], 1.2, 2.0, 6, 4.8],
        "line-opacity": 0.95
      }
    });

    map.on("mousemove", "countries-fill", () => { map.getCanvas().style.cursor = "pointer"; });
    map.on("mouseleave", "countries-fill", () => { map.getCanvas().style.cursor = ""; });

    map.on("click", "countries-fill", (e) => {
      const f = e.features?.[0];
      if (!f) return;
      selectedCountryId = Number(f.properties.id || -1);
      map.setFilter("countries-selected", ["==", ["get", "id"], selectedCountryId]);
    });
  }

  // =========================================================
  // Draft
  // =========================================================
  let mode = "explore"; // explore | create_country | expand_country | factory_build
  let draftPoints = [];
  let EXPAND_TARGET = { countryId: null, oldAreaKm2: 0, oldCost: 0 };

  // Undo/Redo history
  const draftHistory = [];
  const redoHistory = [];
  const HISTORY_MAX = 80;

  function snapshotDraft() {
    return draftPoints.map(p => ({ lng: p.lng, lat: p.lat }));
  }

  function applyDraftSnapshot(snap) {
    draftPoints = (snap || []).map(p => ({ lng: p.lng, lat: p.lat }));
    refreshDraftSource();
  }

  function pushDraftHistory() {
    draftHistory.push(snapshotDraft());
    if (draftHistory.length > HISTORY_MAX) draftHistory.shift();
    redoHistory.length = 0;
  }

  function undoDraft() {
    if (!draftHistory.length) return false;
    redoHistory.push(snapshotDraft());
    const prev = draftHistory.pop();
    applyDraftSnapshot(prev);
    return true;
  }

  function redoDraft() {
    if (!redoHistory.length) return false;
    draftHistory.push(snapshotDraft());
    const next = redoHistory.pop();
    applyDraftSnapshot(next);
    return true;
  }

  function clearDraftHistory() { draftHistory.length = 0; redoHistory.length = 0; }

  const DRAFT = { type: "FeatureCollection", features: [] };

  function addDraftLayers() {
    if (map.getSource("draft")) return;

    map.addSource("draft", { type: "geojson", data: DRAFT });

    map.addLayer({
      id: "draft-fill",
      type: "fill",
      source: "draft",
      filter: ["==", ["get", "kind"], "poly"],
      paint: { "fill-color": "rgba(124,58,237,0.65)", "fill-opacity": 0.16 }
    });

    map.addLayer({
      id: "draft-line",
      type: "line",
      source: "draft",
      filter: ["==", ["get", "kind"], "line"],
      paint: {
        "line-color": "rgba(255,255,255,0.92)",
        "line-width": ["interpolate", ["exponential", 1.2], ["zoom"], 1.2, 2.2, 6, 4.6],
        "line-opacity": 0.96
      }
    });

    // ✅ “handles” look a bit more obvious
    map.addLayer({
      id: "draft-points",
      type: "circle",
      source: "draft",
      filter: ["==", ["get", "kind"], "pts"],
      paint: {
        "circle-radius": ["interpolate", ["exponential", 1.5], ["zoom"], 1.0, 3.6, 2.0, 4.6, 3.2, 6.2, 4.2, 8.4, 6.0, 10.8],
        "circle-color": "rgba(124,58,237,1)",
        "circle-opacity": 0.97,
        "circle-stroke-color": "rgba(0,0,0,0.55)",
        "circle-stroke-width": 1,
        "circle-blur": 0.08
      }
    });
  }

  function refreshDraftSource() {
    const coords = draftPoints.map((p) => [p.lng, p.lat]);
    DRAFT.features = [];

    if (coords.length) {
      DRAFT.features.push({
        type: "Feature",
        properties: { kind: "pts" },
        geometry: { type: "MultiPoint", coordinates: coords }
      });
    }
    if (coords.length >= 2) {
      DRAFT.features.push({
        type: "Feature",
        properties: { kind: "line" },
        geometry: { type: "LineString", coordinates: coords.concat([coords[0]]) }
      });
    }
    if (coords.length >= 3) {
      const closed = coords.concat([coords[0]]);
      DRAFT.features.push({
        type: "Feature",
        properties: { kind: "poly" },
        geometry: { type: "Polygon", coordinates: [closed] }
      });
    }

    if (map.getSource("draft")) map.getSource("draft").setData(DRAFT);
    updateDraftEconomyUI();
  }

  function clearDraft() {
    draftPoints = [];
    DRAFT.features = [];
    if (map.getSource("draft")) map.getSource("draft").setData(DRAFT);

    DRAFT_PREVIEW.features = [];
    if (map.getSource("draftPreview")) map.getSource("draftPreview").setData(DRAFT_PREVIEW);

    setExpandHoverSegment(null, null);
    setExpandPointHover(0, 0, false);
    clearDraftHistory();
  }

  function updateDraftEconomyUI(reset = false) {
    if (reset) {
      if (draftAreaEl) draftAreaEl.textContent = "—";
      if (draftCostEl) draftCostEl.textContent = "—";
      if (myCoinsModalEl) myCoinsModalEl.textContent = `${MY_COINS} EC`;
      if (btnFinish) btnFinish.disabled = true;
      return;
    }

    if (myCoinsModalEl) myCoinsModalEl.textContent = `${MY_COINS} EC`;

    if (draftPoints.length < 3) {
      if (draftAreaEl) draftAreaEl.textContent = "—";
      if (draftCostEl) draftCostEl.textContent = "—";
      if (btnFinish) btnFinish.disabled = true;
      return;
    }

    const coords = draftPoints.map((p) => [p.lng, p.lat]);
    const closed = coords.concat([coords[0]]);
    const area = polygonAreaKm2(closed);
    const cost = computeCountryCost(area);

    if (draftAreaEl) draftAreaEl.textContent = formatKm2(area);

    let shownCost = cost;
    let titlePrefix = "";
    if (mode === "expand_country" && EXPAND_TARGET.countryId) {
      const oldCost = EXPAND_TARGET.oldCost || computeCountryCost(EXPAND_TARGET.oldAreaKm2 || 0);
      const delta = Math.max(0, cost - oldCost);
      shownCost = delta;
      titlePrefix = "Δ ";
    }

    if (draftCostEl) draftCostEl.textContent = `${titlePrefix}${shownCost} EC`;

    const tooBig = area > RULES.country_max_area_km2;
    const tooMany = draftPoints.length > RULES.country_max_points;

    const notOnLand = isDraftOnLand(draftPoints) === false;
    const overlaps = mode === "expand_country"
      ? draftIntersectsAnyCountry(EXPAND_TARGET.countryId)
      : draftIntersectsAnyCountry(null);

    const tooPoor = MY_COINS < shownCost;

    if (btnFinish) {
      btnFinish.disabled = tooBig || tooMany || tooPoor || notOnLand || overlaps;
      btnFinish.style.opacity = btnFinish.disabled ? "0.6" : "1";

      let title = "";
      if (tooBig) title = `Too big (max ${RULES.country_max_area_km2.toLocaleString("en-US")} km²)`;
      else if (tooMany) title = `Too many points (max ${RULES.country_max_points})`;
      else if (tooPoor) title = "Not enough coins";
      else if (notOnLand) title = "Must be on land";
      else if (overlaps) title = "Cannot overlap other countries";
      btnFinish.title = title;
    }

    if (mode === "create_country" || mode === "expand_country") {
      if (notOnLand) showFbMsg("🔴 Точки мають бути НА СУШІ. (зелена крапка = ок)");
      else if (overlaps) showFbMsg("⛔ Перетин з іншою країною — так не можна.");
    }
  }

  function setMode(m) {
    mode = m;

    if (m !== "expand_country") {
      setExpandGhostFromRingClosed(null);
      setExpandHoverSegment(null, null);
      setExpandPointHover(0, 0, false);
    }

    if (btnCreateCountry && buildActions) {
      if (mode === "create_country" || mode === "expand_country") {
        buildActions.style.display = "flex";
        if (btnCreateCountry) btnCreateCountry.style.display = "none";
        if (btnExpandCountry) btnExpandCountry.style.display = "none";

        map.getCanvas().style.cursor = "crosshair";
        selectedCountryId = null;
        if (map.getLayer("countries-selected")) map.setFilter("countries-selected", ["==", ["get", "id"], -1]);

        hideFbMsg();
        if (!LAND_READY) showFbMsg("ℹ️ land.geojson не знайдено → клієнт не знає сушу (сервер все одно перевірить).");

        updateDraftEconomyUI();
      } else {
        buildActions.style.display = "none";
        if (btnCreateCountry) btnCreateCountry.style.display = "inline-flex";
        if (btnExpandCountry) btnExpandCountry.style.display = "inline-flex";
        map.getCanvas().style.cursor = "";
        clearDraft();
        updateDraftEconomyUI(true);
        hideFbMsg();
      }
    }

    if (fbSub) {
      fbSub.textContent = mode === "factory_build"
        ? "Build mode: ON (click inside your country)"
        : "Build mode: off";
    }
    if (btnCancelFactoryMode) btnCancelFactoryMode.style.display = mode === "factory_build" ? "inline-flex" : "none";
    if (btnTipFactory) btnTipFactory.style.display = mode === "factory_build" ? "inline-flex" : "none";

    if (mode !== "factory_build") {
      selectedBlueprint = null;
      renderSelectedBlueprint();
    }

    if (mode !== "create_country" && mode !== "expand_country") setDraftPreview(0, 0);
  }

  // =========================================================
  // Expand UX core: segment distance + insert + snap + drag
  // =========================================================
  function distPointToSegment2(P, A, B) {
    const ABx = B.x - A.x, ABy = B.y - A.y;
    const APx = P.x - A.x, APy = P.y - A.y;
    const ab2 = ABx * ABx + ABy * ABy || 1e-12;
    let t = (APx * ABx + APy * ABy) / ab2;
    t = Math.max(0, Math.min(1, t));
    const Cx = A.x + t * ABx;
    const Cy = A.y + t * ABy;
    const dx = P.x - Cx, dy = P.y - Cy;
    return dx * dx + dy * dy;
  }

  function nearestSegmentIndexPx(lng, lat) {
    if (draftPoints.length < 2) return { i: 0, d2: Infinity };

    const P = map.project([lng, lat]);
    let bestI = 0, bestD = Infinity;

    for (let i = 0; i < draftPoints.length; i++) {
      const a = draftPoints[i];
      const b = draftPoints[(i + 1) % draftPoints.length];
      const A = map.project([a.lng, a.lat]);
      const B = map.project([b.lng, b.lat]);
      const d2 = distPointToSegment2(P, A, B);
      if (d2 < bestD) { bestD = d2; bestI = i; }
    }
    return { i: bestI, d2: bestD };
  }

  // snap to old border if close
  function snapToGhostIfClose(lng, lat) {
    const ghostRing = EXPAND_GHOST.features?.[0]?.geometry?.coordinates?.[0];
    if (!ghostRing || ghostRing.length < 4) return { lng, lat };

    const P = map.project([lng, lat]);
    let best = { lng, lat, d2: Infinity };

    for (let i = 0; i < ghostRing.length - 1; i++) {
      const a = ghostRing[i], b = ghostRing[i + 1];
      const A = map.project(a);
      const B = map.project(b);

      const ABx = B.x - A.x, ABy = B.y - A.y;
      const APx = P.x - A.x, APy = P.y - A.y;
      const ab2 = ABx * ABx + ABy * ABy || 1e-12;
      let t = (APx * ABx + APy * ABy) / ab2;
      t = Math.max(0, Math.min(1, t));

      const Cx = A.x + t * ABx;
      const Cy = A.y + t * ABy;
      const dx = P.x - Cx, dy = P.y - Cy;
      const d2 = dx * dx + dy * dy;

      if (d2 < best.d2) {
        const L = map.unproject([Cx, Cy]);
        best = { lng: L.lng, lat: L.lat, d2 };
      }
    }

    // ✅ feels nicer: snap depends a bit on zoom (bigger at far zoom)
    const z = map.getZoom();
    const SNAP_PX = Math.max(14, Math.min(22, 22 - (z - 2) * 1.5)); // ~22px at low zoom, ~14px near zoom
    if (best.d2 <= SNAP_PX * SNAP_PX) return { lng: best.lng, lat: best.lat };
    return { lng, lat };
  }

  // prevent crazy duplicate points
  function tooCloseToExistingPoint(lng, lat, minPx = 10) {
    const P = map.project([lng, lat]);
    for (const p of draftPoints) {
      const Q = map.project([p.lng, p.lat]);
      const dx = P.x - Q.x, dy = P.y - Q.y;
      if (dx * dx + dy * dy <= minPx * minPx) return true;
    }
    return false;
  }

  // ✅ NEW: project click point onto nearest segment (makes “add on line” perfect)
  function projectLngLatToNearestSegment(lng, lat) {
    if (draftPoints.length < 2) return { lng, lat, segI: 0, d2: Infinity };

    const P = map.project([lng, lat]);
    let best = { lng, lat, segI: 0, d2: Infinity };

    for (let i = 0; i < draftPoints.length; i++) {
      const a = draftPoints[i];
      const b = draftPoints[(i + 1) % draftPoints.length];
      const A = map.project([a.lng, a.lat]);
      const B = map.project([b.lng, b.lat]);

      const ABx = B.x - A.x, ABy = B.y - A.y;
      const APx = P.x - A.x, APy = P.y - A.y;
      const ab2 = ABx * ABx + ABy * ABy || 1e-12;
      let t = (APx * ABx + APy * ABy) / ab2;
      t = Math.max(0, Math.min(1, t));

      const Cx = A.x + t * ABx;
      const Cy = A.y + t * ABy;

      const dx = P.x - Cx, dy = P.y - Cy;
      const d2 = dx * dx + dy * dy;

      if (d2 < best.d2) {
        const L = map.unproject([Cx, Cy]);
        best = { lng: L.lng, lat: L.lat, segI: i, d2 };
      }
    }
    return best;
  }

  function insertDraftPointNearestSegment(lng, lat, { force = false } = {}) {
    if (draftPoints.length < 2) {
      if (tooCloseToExistingPoint(lng, lat, 10)) return;
      pushDraftHistory();
      draftPoints.push({ lng, lat });
      refreshDraftSource();
      return;
    }

    // 1) project onto nearest segment → реально “додаєш точку на лінію”
    const proj = projectLngLatToNearestSegment(lng, lat);

    // 2) tolerance: must be close enough to border unless force
    const MAX_PX = force ? 80 : 34;
    if (proj.d2 > MAX_PX * MAX_PX) {
      showFbMsg(force
        ? "Клікни ближче до кордону (або zoom-in) — тоді вставка буде точнішою."
        : "Клікни БІЛЯ КОРДОНУ. Зелена лінія показує сегмент для вставки."
      , 1600);
      return;
    }

    // 3) snap to ghost (pleasant feel)
    const snapped = snapToGhostIfClose(proj.lng, proj.lat);
    lng = snapped.lng; lat = snapped.lat;

    if (tooCloseToExistingPoint(lng, lat, 10)) {
      showFbMsg("ℹ️ Точка занадто близько до існуючої.", 1200);
      return;
    }

    pushDraftHistory();
    draftPoints.splice(proj.segI + 1, 0, { lng, lat });
    refreshDraftSource();
  }

  // --- Drag points + Shift delete ---
  let draggingPointIdx = null;
  let wasDragging = false;

  function findNearestDraftPointIdxPx(lng, lat, maxPx = 20) {
    const P = map.project([lng, lat]);
    let best = { idx: -1, d2: Infinity };

    for (let i = 0; i < draftPoints.length; i++) {
      const p = draftPoints[i];
      const Q = map.project([p.lng, p.lat]);
      const dx = P.x - Q.x, dy = P.y - Q.y;
      const d2 = dx * dx + dy * dy;
      if (d2 < best.d2) best = { idx: i, d2 };
    }
    if (best.idx >= 0 && best.d2 <= maxPx * maxPx) return best.idx;
    return -1;
  }

  function deleteDraftPointAt(idx) {
    if (idx < 0) return;
    if (draftPoints.length <= 3) {
      showFbMsg("⚠ Мінімум 3 точки мають залишитись.", 1600);
      return;
    }
    pushDraftHistory();
    draftPoints.splice(idx, 1);
    refreshDraftSource();
  }

  // =========================================================
  // Draft intersects any country
  // =========================================================
  function draftIntersectsAnyCountry(excludeCountryId = null) {
    if (draftPoints.length < 3) return false;
    const ring = draftPoints.map((p) => [p.lng, p.lat]);
    const closed = ring.concat([ring[0]]);

    const feats = countriesFC && countriesFC.features ? countriesFC.features : [];
    for (const f of feats) {
      const id = Number(f?.properties?.id ?? f?.id ?? -1);
      if (excludeCountryId && id === Number(excludeCountryId)) continue;

      const ring2 = f?.geometry?.coordinates?.[0];
      if (!ring2 || ring2.length < 4) continue;
      if (ringsIntersect(closed, ring2)) return true;
    }
    return false;
  }

  // =========================================================
  // Modal helpers
  // =========================================================
  function openCountrySaveModal() {
    if (!countryOverlay) return;

    if (countryMsg) { countryMsg.style.display = "none"; countryMsg.textContent = ""; }

    if (mode === "create_country") {
      if (countryName) countryName.value = "";
      if (countryColor) countryColor.value = "#7c3aed";
      if (countryName) countryName.disabled = false;
      if (countryColor) countryColor.disabled = false;
    } else if (mode === "expand_country") {
      if (countryName) { countryName.value = "Territory expand"; countryName.disabled = true; }
      if (countryColor) { countryColor.value = "#7c3aed"; countryColor.disabled = true; }
    }

    countryOverlay.style.display = "flex";
    setTimeout(() => countryName && countryName.focus(), 50);
    updateDraftEconomyUI();
  }

  function closeCountrySaveModal() {
    if (!countryOverlay) return;
    countryOverlay.style.display = "none";
    setTimeout(() => map.resize(), 50);
    if (countryName) countryName.disabled = false;
    if (countryColor) countryColor.disabled = false;
  }

  // =========================================================
  // Networking helpers
  // =========================================================
  async function postJSON(path, body) {
    const res = await fetch(path, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {})
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    return data;
  }

  async function saveCountryOrExpand() {
    if (draftPoints.length < 3) return;

    const onLand = isDraftOnLand(draftPoints);
    if (onLand === false) {
      if (countryMsg) { countryMsg.style.display = "block"; countryMsg.textContent = "Лише суша (не море/океан)."; }
      return;
    }

    const coords = draftPoints.map((p) => [p.lng, p.lat]);
    const closed = coords.concat([coords[0]]);
    const area = polygonAreaKm2(closed);
    const cost = computeCountryCost(area);

    const overlaps = mode === "expand_country"
      ? draftIntersectsAnyCountry(EXPAND_TARGET.countryId)
      : draftIntersectsAnyCountry(null);

    if (overlaps) {
      if (countryMsg) { countryMsg.style.display = "block"; countryMsg.textContent = "Перетин з іншою країною."; }
      return;
    }

    if (area > RULES.country_max_area_km2) {
      if (countryMsg) { countryMsg.style.display = "block"; countryMsg.textContent = "Занадто велика."; }
      return;
    }
    if (draftPoints.length > RULES.country_max_points) {
      if (countryMsg) { countryMsg.style.display = "block"; countryMsg.textContent = "Забагато точок."; }
      return;
    }

    if (btnSaveCountry) btnSaveCountry.disabled = true;

    try {
      if (mode === "create_country") {
        const name = (countryName?.value || "").trim();
        const color = (countryColor?.value || "#7c3aed").trim();

        if (name.length < 2) {
          if (countryMsg) { countryMsg.style.display = "block"; countryMsg.textContent = "Назва мінімум 2 символи."; }
          return;
        }
        if (MY_COINS < cost) {
          if (countryMsg) { countryMsg.style.display = "block"; countryMsg.textContent = "Недостатньо монет."; }
          return;
        }

        const payload = { name, color, geometry: { type: "Polygon", coordinates: [closed] } };
        const res = await postJSON("/api/countries", payload);
        if (res && typeof res.coins === "number") MY_COINS = res.coins;

      } else if (mode === "expand_country") {
        const oldCost = EXPAND_TARGET.oldCost || computeCountryCost(EXPAND_TARGET.oldAreaKm2 || 0);
        const delta = Math.max(0, cost - oldCost);

        if (MY_COINS < delta) {
          if (countryMsg) { countryMsg.style.display = "block"; countryMsg.textContent = "Недостатньо монет на розширення."; }
          return;
        }

        const payload = { geometry: { type: "Polygon", coordinates: [closed] } };
        const res = await postJSON(`/api/countries/${EXPAND_TARGET.countryId}/update-geometry`, payload);
        if (res && typeof res.coins === "number") MY_COINS = res.coins;
      }

      closeCountrySaveModal();
      setMode("explore");
      await loadCountries();
      await refreshMe();
      await refreshMyFactories();

    } catch (err) {
      if (countryMsg) { countryMsg.style.display = "block"; countryMsg.textContent = err.message; }
    } finally {
      if (btnSaveCountry) btnSaveCountry.disabled = false;
    }
  }

  // =========================================================
  // Factories
  // =========================================================
  let BLUEPRINTS = [];
  let selectedBlueprint = null;

  let factoriesFC = { type: "FeatureCollection", features: [] };
  const factoryMarkers = [];

  function factoryIconEl(icon, name, level) {
    const el = document.createElement("div");
    el.className = "resource-marker";
    el.style.padding = "6px 10px";
    el.style.gap = "8px";

    const dot = document.createElement("div");
    dot.className = "resource-dot";
    dot.style.boxShadow = "0 0 14px rgba(124,58,237,.28)";

    const ico = document.createElement("div");
    ico.className = "resource-ico";
    ico.textContent = icon || "🏭";

    const label = document.createElement("div");
    label.className = "resource-name";
    label.textContent = name || "Factory";
    label.style.fontSize = "11px";
    label.style.maxWidth = "110px";
    label.style.whiteSpace = "nowrap";
    label.style.overflow = "hidden";
    label.style.textOverflow = "ellipsis";

    const st = document.createElement("div");
    st.className = "resource-strength";
    st.textContent = `Lv ${level || 1}`;
    st.style.fontSize = "10px";
    st.style.opacity = "0.75";

    el.appendChild(dot);
    el.appendChild(ico);
    el.appendChild(label);
    el.appendChild(st);
    return el;
  }

  async function loadBlueprints() {
    const r = await fetch("/api/blueprints", { credentials: "include" });
    const j = await r.json().catch(() => ({}));
    BLUEPRINTS = j.ok && Array.isArray(j.data) ? j.data : [];
    renderBlueprints();
  }

  function reqToText(req) {
    const parts = [];
    for (const k of Object.keys(req || {})) parts.push(`${k}×${req[k]}`);
    return parts.join(", ");
  }

  function renderBlueprints() {
    if (!fbBlueprints) return;
    fbBlueprints.innerHTML = "";

    for (const bp of BLUEPRINTS) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "fb-item";
      if (selectedBlueprint && selectedBlueprint.key === bp.key) btn.classList.add("active");

      btn.innerHTML = `
        <div class="fb-ico">${bp.icon || "🏭"}</div>
        <div class="fb-main">
          <div class="fb-title2">${bp.name}</div>
          <div class="fb-sub2">Cost: <b>${bp.build_cost} EC</b> + fee ${RULES.factory_place_fee} • Income/h: ~${bp.base_income_per_hour}</div>
          <div class="fb-desc"><b>Needs:</b> ${reqToText(bp.requires)} <span style="opacity:.75;">(near by)</span><br>${bp.desc || ""}</div>
        </div>
      `;

      btn.addEventListener("click", () => {
        selectedBlueprint = bp;
        renderBlueprints();
        renderSelectedBlueprint();
        hideFbMsg();
        setResourceEmphasisForBlueprint(bp);
      });

      fbBlueprints.appendChild(btn);
    }

    if (!BLUEPRINTS.length) {
      fbBlueprints.innerHTML = `<div class="fb-muted">No blueprints yet.</div>`;
    }
  }

  function renderSelectedBlueprint() {
    if (!fbSelected) return;

    if (!selectedBlueprint) {
      fbSelected.innerHTML = `<div class="fb-selected-empty">Select a blueprint to place it on the map.</div>`;
      setResourceEmphasisForBlueprint(null);
      return;
    }

    fbSelected.innerHTML = `
      <div style="display:flex; gap:12px; align-items:flex-start;">
        <div class="fb-ico">${selectedBlueprint.icon || "🏭"}</div>
        <div style="flex:1;">
          <div class="fb-title2">${selectedBlueprint.name}</div>
          <div class="fb-sub2">Click on map inside your country to build.</div>
          <div class="fb-desc"><b>Needs:</b> ${reqToText(selectedBlueprint.requires)} • <b>Radius</b> ${RULES.factory_pick_radius_km} km</div>
        </div>
      </div>
    `;
  }

  function setResourceEmphasisForBlueprint(bp) {
    if (!map.getLayer("resources-core") || !map.getLayer("resources-glow")) return;

    const need = new Set(Object.keys(bp?.requires || {}));
    if (!bp || need.size === 0) {
      map.setPaintProperty("resources-core", "circle-opacity", 0.90);
      map.setPaintProperty("resources-glow", "circle-opacity",
        ["interpolate", ["linear"], ["get", "strength"], 0.35, 0.03, 1.0, 0.10]
      );
      return;
    }

    map.setPaintProperty("resources-core", "circle-opacity",
      ["case",
        ["in", ["get", "type"], ["literal", Array.from(need)]], 0.95,
        0.25
      ]
    );
    map.setPaintProperty("resources-glow", "circle-opacity",
      ["case",
        ["in", ["get", "type"], ["literal", Array.from(need)]],
        ["interpolate", ["linear"], ["get", "strength"], 0.35, 0.04, 1.0, 0.12],
        0.02
      ]
    );
  }

  async function loadFactories() {
    const r = await fetch("/api/factories", { credentials: "include" });
    const j = await r.json().catch(() => ({}));
    factoriesFC = j.ok && j.data ? j.data : { type: "FeatureCollection", features: [] };
    drawFactoryMarkers();
  }

  function drawFactoryMarkers() {
    for (const m of factoryMarkers) m.marker.remove();
    factoryMarkers.length = 0;

    for (const f of factoriesFC.features || []) {
      const [lng, lat] = f.geometry.coordinates;
      const p = f.properties || {};
      const el = factoryIconEl(p.icon, p.name, p.level);

      const marker = new maplibregl.Marker({ element: el, anchor: "center" })
        .setLngLat([lng, lat])
        .addTo(map);

      factoryMarkers.push({ marker, el });
    }
  }

  async function refreshMyFactories() {
    if (!fbMyFactories) return;

    if (!ME.authenticated) {
      fbMyFactories.innerHTML = `<div class="fb-muted">Login to see your factories.</div>`;
      return;
    }

    const r = await fetch("/api/my/factories", { credentials: "include" });
    const j = await r.json().catch(() => ({}));
    if (!j.ok) {
      fbMyFactories.innerHTML = `<div class="fb-muted">Failed to load.</div>`;
      return;
    }

    if (typeof j.coins === "number") MY_COINS = j.coins;
    const pretty = `${MY_COINS} EC`;
    if (myCoinsEl) myCoinsEl.textContent = `💰 ${pretty}`;
    if (topCoinsEl) topCoinsEl.textContent = `💰 ${pretty}`;

    const list = j.data || [];
    if (!list.length) {
      fbMyFactories.innerHTML = `<div class="fb-muted">No factories yet.</div>`;
      return;
    }

    fbMyFactories.innerHTML = "";
    for (const f of list) {
      const row = document.createElement("div");
      row.className = "fb-item";
      row.innerHTML = `
        <div class="fb-ico">${f.icon || "🏭"}</div>
        <div class="fb-main">
          <div class="fb-title2">${f.name} <span style="opacity:.75;">(Lv ${f.level})</span></div>
          <div class="fb-sub2">Stored: <b>${f.stored_coins} EC</b> • Rate: ~${Math.round(f.rate_per_hour)}/h</div>
          <div class="fb-desc">
            <button class="btn-ghost" style="padding:8px 10px; border-radius:12px;" data-act="fly">🌍 Fly</button>
            <button class="btn-primary" style="width:auto; padding:8px 10px; border-radius:12px; margin-top:0;" data-act="collect">💰 Collect</button>
            <button class="btn-ghost" style="padding:8px 10px; border-radius:12px;" data-act="upgrade">⬆ Upgrade</button>
          </div>
        </div>
      `;

      const flyBtn = row.querySelector('[data-act="fly"]');
      const collectBtn = row.querySelector('[data-act="collect"]');
      const upgradeBtn = row.querySelector('[data-act="upgrade"]');

      if (flyBtn) flyBtn.addEventListener("click", () => {
        map.flyTo({ center: [f.lng, f.lat], zoom: Math.max(map.getZoom(), 3.0), speed: 1.2 });
      });

      if (collectBtn) collectBtn.addEventListener("click", async () => {
        try {
          const res = await postJSON(`/api/factories/${f.id}/collect`, {});
          if (typeof res.coins === "number") MY_COINS = res.coins;
          const p = `${MY_COINS} EC`;
          if (myCoinsEl) myCoinsEl.textContent = `💰 ${p}`;
          if (topCoinsEl) topCoinsEl.textContent = `💰 ${p}`;
          showFbMsg(`✅ Collected: ${res.collected || 0} EC`, 1800);
          await refreshMyFactories();
        } catch (e) { showFbMsg(e.message); }
      });

      if (upgradeBtn) upgradeBtn.addEventListener("click", async () => {
        try {
          const res = await postJSON(`/api/factories/${f.id}/upgrade`, {});
          if (typeof res.coins === "number") MY_COINS = res.coins;
          const p = `${MY_COINS} EC`;
          if (myCoinsEl) myCoinsEl.textContent = `💰 ${p}`;
          if (topCoinsEl) topCoinsEl.textContent = `💰 ${p}`;
          showFbMsg(`✅ Upgraded to Lv ${res.level}`, 1800);
          await refreshMyFactories();
          await loadFactories();
        } catch (e) { showFbMsg(e.message); }
      });

      fbMyFactories.appendChild(row);
    }
  }

  function myCountryIdFromCountriesFC() {
    if (!ME.authenticated) return null;
    const feats = countriesFC.features || [];
    const mine = feats.find((f) => f.properties && f.properties.owner === ME.username);
    return mine ? Number(mine.properties.id) : null;
  }

  async function buildFactoryAt(lng, lat) {
    if (!selectedBlueprint) return showFbMsg("Select a blueprint first.");
    if (!ME.authenticated) return showFbMsg("Login first.");
    if (!ME.has_country) return showFbMsg("Create your country first.");

    const cid = myCountryIdFromCountriesFC();
    if (!cid) return showFbMsg("Could not detect your country. Reload / ensure your country exists.");

    try {
      const payload = { country_id: cid, blueprint: selectedBlueprint.key, lng, lat };
      const res = await postJSON("/api/factories", payload);

      if (typeof res.coins === "number") MY_COINS = res.coins;
      const p = `${MY_COINS} EC`;
      if (myCoinsEl) myCoinsEl.textContent = `💰 ${p}`;
      if (topCoinsEl) topCoinsEl.textContent = `💰 ${p}`;

      showFbMsg(`✅ Built ${selectedBlueprint.name}!`, 2000);
      await loadFactories();
      await refreshMyFactories();
    } catch (e) {
      showFbMsg(e.message);
    }
  }

  // =========================================================
  // INIT style
  // =========================================================
  map.on("style.load", async () => {
    try { map.setProjection({ type: "globe" }); } catch {}

    if (map.setFog) {
      map.setFog({
        range: [0.6, 10],
        horizonBlend: 0.18,
        spaceColor: "rgba(3,6,14,1)",
        highColor: "rgba(18,32,60,1)",
        starIntensity: 0.28
      });
    }

    await loadRules();
    await refreshMe();
    await loadLand();

    addResourceLayers();
    await loadResourcesLOD();

    await loadCountries();
    addCountriesLayers();

    addDraftLayers();
    addDraftPreviewLayer();
    addExpandGhostLayer();
    addExpandHoverLayer();
    addExpandPointHoverLayer();

    await loadBlueprints();
    renderSelectedBlueprint();

    await loadFactories();
    await refreshMyFactories();

    map.resize();
    updateStarsVisibility(map);
    updateDraftEconomyUI(true);

    const setHoverFeature = (feat) => {
      const src = map.getSource("resourcesHover");
      if (!src) return;
      src.setData(feat ? { type: "FeatureCollection", features: [feat] } : { type: "FeatureCollection", features: [] });
    };

    map.on("mousemove", "resources-core", (e) => {
      const f = e.features?.[0];
      if (!f) return;

      setHoverFeature(f);

      const p = f.properties || {};
      const t = p.type || "resource";
      const nm = p.name || t;
      const st = Math.round((Number(p.strength) || 0) * 100);

      const icon = RESOURCE_META[t]?.icon || "✨";
      tipShow(e.originalEvent.clientX, e.originalEvent.clientY, `
        <div style="display:flex; gap:10px; align-items:flex-start;">
          <div style="font-size:18px; line-height:1;">${icon}</div>
          <div style="min-width:0;">
            <div style="font-weight:800; font-size:13px; line-height:1.1; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${nm}</div>
            <div style="opacity:.8; font-size:12px; margin-top:4px;">Type: <b>${t}</b> • Strength: <b>${st}%</b></div>
          </div>
        </div>
      `);
    });

    map.on("mouseleave", "resources-core", () => {
      tipHide();
      setHoverFeature(null);
    });
  });

  // =========================================================
  // HUD updates
  // =========================================================
  function fmt(n) { return (Math.round(n * 1000) / 1000).toFixed(3); }

  const updateMouseHUD = rafThrottle((e) => {
    if (coordsEl && e && e.lngLat) coordsEl.textContent = `${fmt(e.lngLat.lng)}, ${fmt(e.lngLat.lat)}`;
    if (mode === "create_country" || mode === "expand_country") {
      if (e && e.lngLat) setDraftPreview(e.lngLat.lng, e.lngLat.lat);
    }

    // Expand: highlight segment for insert + point hover highlight
    if (mode === "expand_country" && draftPoints.length >= 2 && e?.lngLat) {
      const { i, d2 } = nearestSegmentIndexPx(e.lngLat.lng, e.lngLat.lat);
      const a = draftPoints[i];
      const b = draftPoints[(i + 1) % draftPoints.length];

      // Comfort threshold depends on zoom a bit
      const z = map.getZoom();
      const MAX_HOVER_PX = Math.max(36, Math.min(60, 60 - (z - 2) * 4)); // bigger at far zoom
      const ok = d2 <= MAX_HOVER_PX * MAX_HOVER_PX;
      setExpandHoverSegment(ok ? a : null, ok ? b : null);

      // point hover highlight (helps discover “drag handles”)
      const pIdx = findNearestDraftPointIdxPx(e.lngLat.lng, e.lngLat.lat, 22);
      if (pIdx >= 0) {
        const p = draftPoints[pIdx];
        setExpandPointHover(p.lng, p.lat, true);
        map.getCanvas().style.cursor = "grab";
      } else {
        setExpandPointHover(0, 0, false);
        map.getCanvas().style.cursor = "crosshair";
      }
    } else {
      setExpandHoverSegment(null, null);
      setExpandPointHover(0, 0, false);
    }
  });

  const updateMoveHUD = rafThrottle(() => {
    if (zoomEl) zoomEl.textContent = `Zoom ${map.getZoom().toFixed(2)}`;
    updateStarsVisibility(map);
    if (RESOURCE_MARKERS_ENABLED) rebuildResourceMarkersCapped();
  });

  map.on("mousemove", updateMouseHUD);
  map.on("move", updateMoveHUD);
  map.on("zoom", updateMoveHUD);

  map.scrollZoom.enable();
  map.dragRotate.enable();
  map.dragPan.enable();
  map.touchZoomRotate.enable();

  const scheduleResourcesReload = debounce(() => {
    loadResourcesLOD().catch(() => {});
  }, 180);

  map.on("moveend", scheduleResourcesReload);
  map.on("zoomend", scheduleResourcesReload);

  // =========================================================
  // Drag points (expand) + Shift delete
  // =========================================================
  map.on("mousedown", (e) => {
    if (mode !== "expand_country") return;

    const idx = findNearestDraftPointIdxPx(e.lngLat.lng, e.lngLat.lat, 22);
    if (idx >= 0) {
      if (e.originalEvent && e.originalEvent.shiftKey) {
        deleteDraftPointAt(idx);
        wasDragging = true;
        return;
      }
      pushDraftHistory();
      draggingPointIdx = idx;
      wasDragging = false;
      map.getCanvas().style.cursor = "grabbing";
      e.preventDefault();
    }
  });

  map.on("mousemove", (e) => {
    if (mode !== "expand_country") return;
    if (draggingPointIdx === null) return;

    // snap to ghost while dragging
    const s1 = snapToGhostIfClose(e.lngLat.lng, e.lngLat.lat);

    // ✅ also lightly “stick” to the segment projection when close to it (prevents wobbly edits)
    // this makes border editing feel more “on rails” without forcing it.
    let lng = s1.lng, lat = s1.lat;

    draftPoints[draggingPointIdx] = { lng, lat };
    wasDragging = true;
    refreshDraftSource();
  });

  function stopDragging() {
    if (draggingPointIdx !== null) {
      draggingPointIdx = null;
      map.getCanvas().style.cursor = (mode === "expand_country" || mode === "create_country") ? "crosshair" : "";
      setTimeout(() => { wasDragging = false; }, 0);
    }
  }
  map.on("mouseup", stopDragging);
  map.on("mouseleave", stopDragging);

  // =========================================================
  // Map click
  // =========================================================
  map.on("click", async (e) => {
    if (mode === "factory_build") {
      return buildFactoryAt(e.lngLat.lng, e.lngLat.lat);
    }

    if (mode !== "create_country" && mode !== "expand_country") return;

    // if just dragged / deleted — do not insert
    if (mode === "expand_country" && (draggingPointIdx !== null || wasDragging)) return;

    // Create: cannot put country over country
    if (mode === "create_country") {
      const feats = map.queryRenderedFeatures(e.point, { layers: ["countries-fill"] });
      if (feats && feats.length) {
        showFbMsg("⛔ Тут уже є країна. Не можна ставити країну на країну.", 1700);
        return;
      }
    }

    const onLand = isPointOnLand(e.lngLat.lng, e.lngLat.lat);
    if (onLand === false) {
      showFbMsg("🔴 Це море/океан. Став точку на суші (зелена крапка).", 1700);
      return;
    }

    if (draftPoints.length >= RULES.country_max_points) {
      showFbMsg(`⚠ Досягнуто ліміт точок: ${RULES.country_max_points}`, 1500);
      return;
    }

    if (mode === "expand_country") {
      const force = !!(e.originalEvent && e.originalEvent.altKey);
      insertDraftPointNearestSegment(e.lngLat.lng, e.lngLat.lat, { force });
    } else {
      if (tooCloseToExistingPoint(e.lngLat.lng, e.lngLat.lat, 10)) {
        showFbMsg("ℹ️ Точка занадто близько до існуючої.", 1200);
        return;
      }
      pushDraftHistory();
      draftPoints.push({ lng: e.lngLat.lng, lat: e.lngLat.lat });
      refreshDraftSource();
    }
  });

  // =========================================================
  // UI handlers (country)
  // =========================================================
  if (btnCreateCountry) btnCreateCountry.addEventListener("click", () => {
    EXPAND_TARGET = { countryId: null, oldAreaKm2: 0, oldCost: 0 };
    clearDraft();
    setMode("create_country");
    showFbMsg("🟣 Створення країни: клікай щоб ставити точки. Коли готово — Finish → Save.", 2200);
  });

  // Expand = clone old polygon into draft + ghost old border
  if (btnExpandCountry) btnExpandCountry.addEventListener("click", async () => {
    hideFbMsg();
    if (!ME.authenticated) return showFbMsg("Login first.");
    if (!ME.has_country) return showFbMsg("Спочатку створи країну.", 2000);

    const r = await fetch("/api/my/country", { credentials: "include" });
    const j = await r.json().catch(() => ({}));
    const feat = j?.data;
    if (!j.ok || !feat) return showFbMsg("Не можу знайти твою країну. Перезавантаж сторінку.", 2000);

    const cid = Number(feat.properties?.id || feat.id || 0);
    const oldArea = Number(feat.properties?.area_km2 || 0);
    const oldCost = computeCountryCost(oldArea);
    EXPAND_TARGET = { countryId: cid, oldAreaKm2: oldArea, oldCost };

    const ringClosed = feat.geometry?.coordinates?.[0];
    if (!ringClosed || ringClosed.length < 4) return showFbMsg("Погана геометрія країни.", 1800);

    setExpandGhostFromRingClosed(ringClosed);

    clearDraft();
    draftPoints = ringClosed.slice(0, -1).map(([lng, lat]) => ({ lng, lat }));
    refreshDraftSource();

    setMode("expand_country");

    showFbMsg(
      "🟣 РЕЖИМ РОЗШИРЕННЯ КОРДОНУ:\n" +
      "• Наведи на лінію: підсвітиться сегмент\n" +
      "• Клік по лінії = додати точку НА ЛІНІЮ\n" +
      "• Тягни точки (drag)\n" +
      "• Shift+клік по точці = видалити\n" +
      "• Alt+клік = вставити навіть якщо трохи далеко\n" +
      "• Ctrl+Z / Ctrl+Y = Undo/Redo\n" +
      "Ціна показується як Δ (доплата)."
    );
  });

  if (btnUndo) btnUndo.addEventListener("click", () => {
    if (!undoDraft()) {
      // fallback
      if (draftPoints.length) {
        pushDraftHistory();
        draftPoints.pop();
        refreshDraftSource();
      }
    }
  });

  if (btnCancel) btnCancel.addEventListener("click", () => setMode("explore"));

  if (btnFinish) btnFinish.addEventListener("click", () => {
    if (draftPoints.length < 3) return;
    openCountrySaveModal();
  });

  if (btnCloseCountry) btnCloseCountry.addEventListener("click", closeCountrySaveModal);
  if (btnSaveCountry) btnSaveCountry.addEventListener("click", saveCountryOrExpand);

  // Hotkeys
  window.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") {
      if (countryOverlay && countryOverlay.style.display === "flex") closeCountrySaveModal();
      else if (mode === "create_country" || mode === "expand_country" || mode === "factory_build") setMode("explore");
    }
    if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "z") {
      if (mode === "create_country" || mode === "expand_country") {
        ev.preventDefault();
        undoDraft();
      }
    }
    if ((ev.ctrlKey || ev.metaKey) && (ev.key.toLowerCase() === "y" || (ev.shiftKey && ev.key.toLowerCase() === "z"))) {
      if (mode === "create_country" || mode === "expand_country") {
        ev.preventDefault();
        redoDraft();
      }
    }
  });

  // =========================================================
  // UI handlers (factory sidebar)
  // =========================================================
  if (fbToggle && factorybar) {
    fbToggle.addEventListener("click", () => {
      factorybar.classList.toggle("collapsed");
    });
  }

  const fbCloseBtns = document.querySelectorAll("#fbClose");
  fbCloseBtns.forEach((b) => {
    b.addEventListener("click", () => {
      factorybar && factorybar.classList.remove("open");
    });
  });

  let factoriesPanelOpen = false;

  function setFactoriesPanel(open) {
    factoriesPanelOpen = !!open;
    if (!factorybar) return;
    if (factoriesPanelOpen) factorybar.classList.add("open");
    else factorybar.classList.remove("open");
  }

  function toggleFactoriesPanel() {
    setFactoriesPanel(!factoriesPanelOpen);
  }

  if (btnOpenFactories) {
    btnOpenFactories.addEventListener("click", toggleFactoriesPanel);
  }

  if (btnFactoryMode) {
    btnFactoryMode.addEventListener("click", () => {
      hideFbMsg();
      if (mode === "factory_build") {
        setMode("explore");
      } else {
        setMode("factory_build");
        if (!selectedBlueprint && BLUEPRINTS.length) {
          selectedBlueprint = BLUEPRINTS[0];
          renderBlueprints();
          renderSelectedBlueprint();
          setResourceEmphasisForBlueprint(selectedBlueprint);
        }
      }
    });
  }

  if (btnCancelFactoryMode) {
    btnCancelFactoryMode.addEventListener("click", () => setMode("explore"));
  }

  if (btnTipFactory && fbTip) {
    btnTipFactory.addEventListener("click", () => {
      fbTip.style.display = fbTip.style.display === "none" || !fbTip.style.display ? "block" : "none";
    });
  }

  // =========================================================
  // Country panel (optional UI)
  // =========================================================
  const countryPanel = document.getElementById("countryPanel");
  const cpClose = document.getElementById("cpClose");
  const cpColor = document.getElementById("cpColor");
  const cpName = document.getElementById("cpName");
  const cpSub = document.getElementById("cpSub");
  const cpArea = document.getElementById("cpArea");
  const cpFactories = document.getElementById("cpFactories");
  const cpOwner = document.getElementById("cpOwner");
  const cpId = document.getElementById("cpId");
  const cpFly = document.getElementById("cpFly");
  const cpOpenFactories = document.getElementById("cpOpenFactories");

  let currentCountryPanelId = null;

  function closeCountryPanel() {
    if (!countryPanel) return;
    countryPanel.classList.remove("open");
    countryPanel.setAttribute("aria-hidden", "true");
    currentCountryPanelId = null;
  }

  function openCountryPanelBasic(props) {
    if (!countryPanel) return;

    const id = Number(props?.id ?? -1);
    currentCountryPanelId = id;

    const name = props?.name || "Country";
    const color = props?.color || "#7c3aed";
    const owner = props?.owner || "—";
    const area = Number(props?.area_km2 || 0);

    if (cpColor) cpColor.style.background = color;
    if (cpName) cpName.textContent = name;
    if (cpSub) cpSub.textContent = "MMO Country";
    if (cpOwner) cpOwner.textContent = owner;
    if (cpArea) cpArea.textContent = area ? `${Math.round(area).toLocaleString("en-US")} км²` : "—";
    if (cpFactories) cpFactories.textContent = "—";
    if (cpId) cpId.textContent = String(id);

    countryPanel.classList.add("open");
    countryPanel.setAttribute("aria-hidden", "false");
  }

  async function loadCountryDetailsToPanel(countryId) {
    try {
      const r = await fetch(`/api/countries/${countryId}`, { credentials: "include" });
      const j = await r.json().catch(() => ({}));
      if (!j.ok) return;

      const d = j.data || {};
      if (cpFactories) cpFactories.textContent = d.factories ?? "0";
      if (cpOwner) cpOwner.textContent = d.owner_username || "—";
      if (cpSub) cpSub.textContent = d.is_mine ? "Your country ✅" : "Foreign country";
    } catch (e) {
      console.warn("Failed to load country details", e);
    }
  }

  if (window.__earthMap) {
    window.__earthMap.on("click", "countries-fill", async (e) => {
      const f = e.features?.[0];
      if (!f) return;

      const id = Number(f.properties?.id || -1);
      if (id < 0) return;

      window.__earthMap.setFilter("countries-selected", ["==", ["get", "id"], id]);
      openCountryPanelBasic(f.properties);
      await loadCountryDetailsToPanel(id);
    });
  }

  if (cpClose) cpClose.addEventListener("click", closeCountryPanel);

  if (cpFly && window.__earthMap) {
    cpFly.addEventListener("click", () => {
      if (!currentCountryPanelId) return;

      const feat = (countriesFC?.features || []).find(
        (f) => Number(f.properties?.id) === Number(currentCountryPanelId)
      );
      if (!feat) return;

      const ring = feat.geometry?.coordinates?.[0];
      if (!ring || ring.length < 3) return;

      let lng = 0, lat = 0;
      const pts = ring.slice(0, -1);
      for (const p of pts) { lng += p[0]; lat += p[1]; }
      lng /= pts.length; lat /= pts.length;

      window.__earthMap.flyTo({
        center: [lng, lat],
        zoom: Math.max(window.__earthMap.getZoom(), 2.8),
        speed: 1.2
      });
    });
  }

  if (cpOpenFactories) {
    cpOpenFactories.addEventListener("click", () => {
      setFactoriesPanel(true);
    });
  }

  // =========================================================
  // Start
  // =========================================================
  setFactoriesPanel(false);
  setMode("explore");
})();
