// static/js/map.js
// EarthCity — Globe + Resources(server) + Countries + Create Country + Factories(server)

(function () {
  const $ = (id) => document.getElementById(id);

  // ---- UI refs ----
  const starsEl = $("stars");
  const coordsEl = $("coords");
  const zoomEl = $("zoom");

  // Country build UI
  const btnCreateCountry = $("btnCreateCountry");
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
  const myCoinsEl = $("myCoins");           // sidebar pill
  const myCoinsModalEl = $("myCoinsModal"); // modal coins

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




  // ---- Stars background ----
  if (starsEl) {
    const N = 220;
    for (let i = 0; i < N; i++) {
      const s = document.createElement("div");
      s.className = "star";
      s.style.left = (Math.random() * 100) + "%";
      s.style.top = (Math.random() * 100) + "%";
      const size = 1 + Math.random() * 2.3;
      s.style.width = size + "px";
      s.style.height = size + "px";
      s.style.animationDelay = (Math.random() * 4) + "s";
      s.style.opacity = String(0.22 + Math.random() * 0.78);
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

  // ---- Math helpers ----
  function rad(d) { return d * Math.PI / 180; }

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

  function showFbMsg(text) {
    if (!fbMsg) return;
    fbMsg.style.display = "block";
    fbMsg.textContent = text;
  }
  function hideFbMsg() {
    if (!fbMsg) return;
    fbMsg.style.display = "none";
    fbMsg.textContent = "";
  }

  // ---- Rules + coins ----
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
    ME = j || { authenticated:false };
    MY_COINS = (j && typeof j.coins === "number") ? j.coins : 0;

    if (myCoinsEl) myCoinsEl.textContent = `${MY_COINS} EC`;
    if (myCoinsModalEl) myCoinsModalEl.textContent = `${MY_COINS} EC`;
  }

  function computeCountryCost(areaKm2) {
    return Math.round(RULES.country_base_cost + (areaKm2 / 1000) * RULES.country_cost_per_1000_km2);
  }

  // ---- Map style ----
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

  // ---- Resources (server) ----
  let RESOURCES = { type:"FeatureCollection", features: [] };
  const RESOURCE_META = {
    oil:      { icon: "🛢️", color: "rgba(250, 204, 21, 1)" },
    gas:      { icon: "🔥",  color: "rgba(251, 146, 60, 1)" },
    iron:     { icon: "⛏️",  color: "rgba(226, 232, 240, 1)" },
    gold:     { icon: "🪙",  color: "rgba(251, 191, 36, 1)" },
    coal:     { icon: "🪨",  color: "rgba(148, 163, 184, 1)" },
    uranium:  { icon: "☢️",  color: "rgba(74, 222, 128, 1)" },
    rare:     { icon: "💎",  color: "rgba(196, 181, 253, 1)" },
    water:    { icon: "💧",  color: "rgba(96, 165, 250, 1)" },
    farmland: { icon: "🌾",  color: "rgba(74, 222, 128, 1)" },
    fish:     { icon: "🐟",  color: "rgba(56, 189, 248, 1)" },
    wind:     { icon: "🌬️",  color: "rgba(196, 181, 253, 1)" },
    solar:    { icon: "☀️",  color: "rgba(253, 164, 175, 1)" },
    hydro:    { icon: "🌊",  color: "rgba(96, 165, 250, 1)" },
    geo:      { icon: "🌋",  color: "rgba(244, 63, 94, 1)" }
  };

  const resourceMarkers = []; // { marker, el }

  function makeResourceElement(type, name, strength) {
    const meta = RESOURCE_META[type] || { icon: "✨", color: "rgba(255,255,255,1)" };

    const wrap = document.createElement("div");
    wrap.className = "resource-marker";

    const dot = document.createElement("div");
    dot.className = "resource-dot";
    dot.style.background = meta.color;
    dot.style.boxShadow = `0 0 18px ${meta.color.replace("1)", "0.35)")}`;

    const ico = document.createElement("div");
    ico.className = "resource-ico";
    ico.textContent = meta.icon;

    const label = document.createElement("div");
    label.className = "resource-name";
    label.textContent = name || type;

    const st = document.createElement("div");
    st.className = "resource-strength";
    st.textContent = `${Math.round((Number(strength) || 0) * 100)}%`;

    wrap.appendChild(dot);
    wrap.appendChild(ico);
    wrap.appendChild(label);
    wrap.appendChild(st);

    wrap.title = `${name || type} • ${Math.round((Number(strength) || 0) * 100)}%`;
    return wrap;
  }

  function addResourceLayers() {
    if (map.getSource("resources")) return;

    map.addSource("resources", { type: "geojson", data: RESOURCES });

    map.addLayer({
      id: "resources-glow",
      type: "circle",
      source: "resources",
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 1, 6, 3, 16, 6, 36],
        "circle-color": ["match", ["get", "type"],
          "oil", "rgba(250,204,21,0.95)",
          "gas", "rgba(251,146,60,0.95)",
          "iron", "rgba(148,163,184,0.95)",
          "gold", "rgba(251,191,36,0.98)",
          "coal", "rgba(148,163,184,0.92)",
          "uranium", "rgba(34,197,94,0.95)",
          "rare", "rgba(167,139,250,0.98)",
          "water", "rgba(59,130,246,0.98)",
          "farmland", "rgba(34,197,94,0.92)",
          "fish", "rgba(56,189,248,0.96)",
          "wind", "rgba(196,181,253,0.96)",
          "solar", "rgba(253,164,175,0.96)",
          "hydro", "rgba(59,130,246,0.96)",
          "geo", "rgba(244,63,94,0.96)",
          "rgba(34,197,94,0.95)"
        ],
        "circle-opacity": ["interpolate", ["linear"], ["get", "strength"], 0.5, 0.10, 1.0, 0.24],
        "circle-blur": 1
      }
    });

    map.addLayer({
      id: "resources-core",
      type: "circle",
      source: "resources",
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 1, 2.2, 3, 4.2, 6, 7.2],
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
        "circle-opacity": 0.92,
        "circle-stroke-color": "rgba(0,0,0,0.42)",
        "circle-stroke-width": 1
      }
    });
  }

  function addResourceMarkers() {
    for (const rm of resourceMarkers) rm.marker.remove();
    resourceMarkers.length = 0;

    for (const f of RESOURCES.features) {
      const [lng, lat] = f.geometry.coordinates;
      const el = makeResourceElement(f.properties.type, f.properties.name, f.properties.strength);
      const marker = new maplibregl.Marker({ element: el, anchor: "center" })
        .setLngLat([lng, lat])
        .addTo(map);
      resourceMarkers.push({ marker, el });
    }
    updateMarkerDetail();
    updateBacksideResourcesVisibility();
  }

  function updateMarkerDetail() {
    const z = map.getZoom();
    for (const rm of resourceMarkers) {
      if (z < 1.6) {
        rm.el.classList.add("tiny"); rm.el.classList.remove("small");
      } else if (z < 2.6) {
        rm.el.classList.add("small"); rm.el.classList.remove("tiny");
      } else {
        rm.el.classList.remove("small"); rm.el.classList.remove("tiny");
      }
    }
  }

  function updateBacksideResourcesVisibility() {
    const z = map.getZoom();
    const shouldCull = z >= 2.2;

    const center = map.getCenter();
    const clng = center.lng, clat = center.lat;

    for (const rm of resourceMarkers) {
      const ll = rm.marker.getLngLat();
      let visible = true;
      if (shouldCull) {
        const ang = angularDistanceRad(clng, clat, ll.lng, ll.lat);
        visible = ang <= (Math.PI / 2);
      }
      rm.el.style.display = visible ? "" : "none";
    }
  }

  async function loadResources() {
    const r = await fetch("/api/resources");
    const j = await r.json().catch(() => ({}));
    if (j.ok && j.data) RESOURCES = j.data;
    if (map.getSource("resources")) map.getSource("resources").setData(RESOURCES);
  }

  // ---- Countries (MMO) ----
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
      paint: {
        "fill-color": ["get", "color"],
        "fill-opacity": 0.22
      }
    });

    map.addLayer({
      id: "countries-line",
      type: "line",
      source: "countries",
      paint: {
        "line-color": ["get", "color"],
        "line-width": ["interpolate", ["linear"], ["zoom"], 1.2, 1.2, 6, 3.2],
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
        "line-width": ["interpolate", ["linear"], ["zoom"], 1.2, 2.2, 6, 4.8],
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

  // ---- Draft (Create Country) ----
  let mode = "explore"; // explore | create_country | factory_build
  let draftPoints = [];

  const DRAFT = { type: "FeatureCollection", features: [] };

  function setMode(m) {
    mode = m;

    // country build UI
    if (btnCreateCountry && buildActions) {
      if (mode === "create_country") {
        buildActions.style.display = "flex";
        btnCreateCountry.style.display = "none";
        map.getCanvas().style.cursor = "crosshair";
        selectedCountryId = null;
        if (map.getLayer("countries-selected")) map.setFilter("countries-selected", ["==", ["get", "id"], -1]);
        updateDraftEconomyUI();
      } else {
        buildActions.style.display = "none";
        btnCreateCountry.style.display = "inline-flex";
        map.getCanvas().style.cursor = "";
        clearDraft();
        updateDraftEconomyUI(true);
      }
    }

    // factories UI
    if (fbSub) {
      fbSub.textContent =
        (mode === "factory_build") ? "Build mode: ON (click inside your country)" : "Build mode: off";
    }
    if (btnCancelFactoryMode) btnCancelFactoryMode.style.display = (mode === "factory_build") ? "inline-flex" : "none";
    if (btnTipFactory) btnTipFactory.style.display = (mode === "factory_build") ? "inline-flex" : "none";

    if (mode !== "factory_build") {
      selectedBlueprint = null;
      renderSelectedBlueprint();
      hideFbMsg();
    }
  }

  function clearDraft() {
    draftPoints = [];
    DRAFT.features = [];
    if (map.getSource("draft")) map.getSource("draft").setData(DRAFT);
  }

  function addDraftLayers() {
    if (map.getSource("draft")) return;

    map.addSource("draft", { type: "geojson", data: DRAFT });

    map.addLayer({
      id: "draft-fill",
      type: "fill",
      source: "draft",
      filter: ["==", ["get", "kind"], "poly"],
      paint: {
        "fill-color": "rgba(124,58,237,0.65)",
        "fill-opacity": 0.18
      }
    });

    map.addLayer({
      id: "draft-line",
      type: "line",
      source: "draft",
      filter: ["==", ["get", "kind"], "line"],
      paint: {
        "line-color": "rgba(255,255,255,0.92)",
        "line-width": ["interpolate", ["linear"], ["zoom"], 1.2, 2.0, 6, 4.0],
        "line-opacity": 0.96
      }
    });

    map.addLayer({
      id: "draft-points",
      type: "circle",
      source: "draft",
      filter: ["==", ["get", "kind"], "pts"],
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 1.2, 3.2, 6, 6.4],
        "circle-color": "rgba(124,58,237,1)",
        "circle-opacity": 0.95,
        "circle-stroke-color": "rgba(0,0,0,0.45)",
        "circle-stroke-width": 1
      }
    });
  }

  function refreshDraftSource() {
    const coords = draftPoints.map(p => [p.lng, p.lat]);
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
        geometry: { type: "LineString", coordinates: coords }
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

    map.getSource("draft").setData(DRAFT);
    updateDraftEconomyUI();
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

    const coords = draftPoints.map(p => [p.lng, p.lat]);
    const closed = coords.concat([coords[0]]);
    const area = polygonAreaKm2(closed);
    const cost = computeCountryCost(area);

    if (draftAreaEl) draftAreaEl.textContent = formatKm2(area);
    if (draftCostEl) draftCostEl.textContent = `${cost} EC`;

    const tooBig = area > RULES.country_max_area_km2;
    const tooMany = draftPoints.length > RULES.country_max_points;
    const tooPoor = MY_COINS < cost;

    if (btnFinish) {
      btnFinish.disabled = tooBig || tooMany || tooPoor;
      btnFinish.style.opacity = btnFinish.disabled ? "0.6" : "1";
      btnFinish.title = btnFinish.disabled
        ? (tooBig ? `Too big (max ${RULES.country_max_area_km2.toLocaleString("en-US")} km²)` :
           tooMany ? `Too many points (max ${RULES.country_max_points})` :
           `Not enough coins`)
        : "";
    }
  }

  // ---- Modal helpers ----
  function openCountrySaveModal() {
    if (!countryOverlay) return;
    if (countryMsg) { countryMsg.style.display = "none"; countryMsg.textContent = ""; }
    if (countryName) countryName.value = "";
    if (countryColor) countryColor.value = "#7c3aed";
    countryOverlay.style.display = "flex";
    setTimeout(() => countryName && countryName.focus(), 50);
    updateDraftEconomyUI();
  }

  function closeCountrySaveModal() {
    if (!countryOverlay) return;
    countryOverlay.style.display = "none";
    setTimeout(() => map.resize(), 50);
  }

  // ---- Networking helpers ----
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

  async function saveCountry() {
    if (draftPoints.length < 3) return;

    const name = (countryName?.value || "").trim();
    const color = (countryColor?.value || "#7c3aed").trim();

    if (name.length < 2) {
      if (countryMsg) { countryMsg.style.display = "block"; countryMsg.textContent = "Назва мінімум 2 символи."; }
      return;
    }

    const coords = draftPoints.map(p => [p.lng, p.lat]);
    const closed = coords.concat([coords[0]]);
    const area = polygonAreaKm2(closed);
    const cost = computeCountryCost(area);

    if (area > RULES.country_max_area_km2) {
      if (countryMsg) { countryMsg.style.display = "block"; countryMsg.textContent = "Країна завелика. Зменш полігон."; }
      return;
    }
    if (draftPoints.length > RULES.country_max_points) {
      if (countryMsg) { countryMsg.style.display = "block"; countryMsg.textContent = "Забагато точок. Зменш."; }
      return;
    }
    if (MY_COINS < cost) {
      if (countryMsg) { countryMsg.style.display = "block"; countryMsg.textContent = "Недостатньо монет."; }
      return;
    }

    const payload = { name, color, geometry: { type: "Polygon", coordinates: [closed] } };

    if (btnSaveCountry) btnSaveCountry.disabled = true;

    try {
      const res = await postJSON("/api/countries", payload);
      if (res && typeof res.coins === "number") MY_COINS = res.coins;

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

  // ---- FACTORIES ----
  let BLUEPRINTS = [];
  let selectedBlueprint = null;

  let factoriesFC = { type:"FeatureCollection", features:[] };
  const factoryMarkers = []; // { marker, el }

  function factoryIconEl(icon, name, level) {
    const el = document.createElement("div");
    el.className = "resource-marker"; // reuse nice style
    el.style.padding = "7px 11px";
    el.style.gap = "10px";

    const dot = document.createElement("div");
    dot.className = "resource-dot";
    dot.style.background = "rgba(124,58,237,1)";
    dot.style.boxShadow = "0 0 18px rgba(124,58,237,.35)";

    const ico = document.createElement("div");
    ico.className = "resource-ico";
    ico.textContent = icon || "🏭";

    const label = document.createElement("div");
    label.className = "resource-name";
    label.textContent = name || "Factory";

    const st = document.createElement("div");
    st.className = "resource-strength";
    st.textContent = `Lv ${level || 1}`;

    el.appendChild(dot);
    el.appendChild(ico);
    el.appendChild(label);
    el.appendChild(st);
    return el;
  }

  async function loadBlueprints() {
    const r = await fetch("/api/blueprints", { credentials:"include" });
    const j = await r.json().catch(() => ({}));
    BLUEPRINTS = (j.ok && Array.isArray(j.data)) ? j.data : [];
    renderBlueprints();
  }

  function reqToText(req) {
    const parts = [];
    for (const k of Object.keys(req || {})) {
      parts.push(`${k}×${req[k]}`);
    }
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

  async function loadFactories() {
    const r = await fetch("/api/factories", { credentials:"include" });
    const j = await r.json().catch(() => ({}));
    factoriesFC = (j.ok && j.data) ? j.data : { type:"FeatureCollection", features:[] };
    drawFactoryMarkers();
  }

  function drawFactoryMarkers() {
    for (const m of factoryMarkers) m.marker.remove();
    factoryMarkers.length = 0;

    for (const f of (factoriesFC.features || [])) {
      const [lng, lat] = f.geometry.coordinates;
      const p = f.properties || {};
      const el = factoryIconEl(p.icon, p.name, p.level);

      const marker = new maplibregl.Marker({ element: el, anchor: "center" })
        .setLngLat([lng, lat])
        .addTo(map);

      factoryMarkers.push({ marker, el });
    }
    updateMarkerDetail(); // uses same class logic
    updateBacksideFactoriesVisibility();
  }

  function updateBacksideFactoriesVisibility() {
    const z = map.getZoom();
    const shouldCull = z >= 2.2;
    const center = map.getCenter();
    const clng = center.lng, clat = center.lat;

    for (const fm of factoryMarkers) {
      const ll = fm.marker.getLngLat();
      let visible = true;
      if (shouldCull) {
        const ang = angularDistanceRad(clng, clat, ll.lng, ll.lat);
        visible = ang <= (Math.PI / 2);
      }
      fm.el.style.display = visible ? "" : "none";
    }
  }

  async function refreshMyFactories() {
    if (!fbMyFactories) return;

    if (!ME.authenticated) {
      fbMyFactories.innerHTML = `<div class="fb-muted">Login to see your factories.</div>`;
      return;
    }

    const r = await fetch("/api/my/factories", { credentials:"include" });
    const j = await r.json().catch(() => ({}));
    if (!j.ok) {
      fbMyFactories.innerHTML = `<div class="fb-muted">Failed to load.</div>`;
      return;
    }

    if (typeof j.coins === "number") MY_COINS = j.coins;
    if (myCoinsEl) myCoinsEl.textContent = `${MY_COINS} EC`;

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

      row.querySelector('[data-act="fly"]').addEventListener("click", () => {
        map.flyTo({ center: [f.lng, f.lat], zoom: Math.max(map.getZoom(), 3.0), speed: 1.2 });
      });

      row.querySelector('[data-act="collect"]').addEventListener("click", async () => {
        try {
          const res = await postJSON(`/api/factories/${f.id}/collect`, {});
          if (typeof res.coins === "number") MY_COINS = res.coins;
          if (myCoinsEl) myCoinsEl.textContent = `${MY_COINS} EC`;
          showFbMsg(`✅ Collected: ${res.collected || 0} EC`);
          await refreshMyFactories();
        } catch (e) {
          showFbMsg(e.message);
        }
      });

      row.querySelector('[data-act="upgrade"]').addEventListener("click", async () => {
        try {
          const res = await postJSON(`/api/factories/${f.id}/upgrade`, {});
          if (typeof res.coins === "number") MY_COINS = res.coins;
          if (myCoinsEl) myCoinsEl.textContent = `${MY_COINS} EC`;
          showFbMsg(`✅ Upgraded to Lv ${res.level}`);
          await refreshMyFactories();
          await loadFactories();
        } catch (e) {
          showFbMsg(e.message);
        }
      });

      fbMyFactories.appendChild(row);
    }
  }

  // helper: pick my country id (since 1 user = 1 country)
  function myCountryIdFromCountriesFC() {
    if (!ME.authenticated) return null;
    const meId = null; // we don't have id on /api/me, so detect by owner_user_id==? not possible
    // We'll infer by "owner_user_id" comparison only if backend includes user_id.
    // For MVP: fetch /api/countries and pick the one with owner_user_id == window.__ME_ID if you add it.
    // Simple workaround: call /api/my/factories and store country_id there later.
    // BUT we do better: use /api/countries and compare "owner" == ME.username
    const feats = countriesFC.features || [];
    const mine = feats.find(f => (f.properties && (f.properties.owner === ME.username)));
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
      if (myCoinsEl) myCoinsEl.textContent = `${MY_COINS} EC`;

      showFbMsg(`✅ Built ${selectedBlueprint.name}!`);
      await loadFactories();
      await refreshMyFactories();
    } catch (e) {
      showFbMsg(e.message);
    }
  }

  // ---- INIT ----
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

    await loadResources();
    addResourceLayers();
    addResourceMarkers();

    await loadCountries();
    addCountriesLayers();

    addDraftLayers();

    await loadBlueprints();
    renderSelectedBlueprint();

    await loadFactories();
    await refreshMyFactories();

    map.resize();
    updateStarsVisibility(map);
    updateMarkerDetail();
    updateBacksideResourcesVisibility();
    updateBacksideFactoriesVisibility();
    updateDraftEconomyUI(true);
  });

  // ---- HUD updates ----
  function fmt(n) { return (Math.round(n * 1000) / 1000).toFixed(3); }

  function updateHUD(e) {
    if (coordsEl && e && e.lngLat) coordsEl.textContent = `${fmt(e.lngLat.lng)}, ${fmt(e.lngLat.lat)}`;
    if (zoomEl) zoomEl.textContent = `Zoom ${map.getZoom().toFixed(2)}`;

    updateStarsVisibility(map);
    updateMarkerDetail();
    updateBacksideResourcesVisibility();
    updateBacksideFactoriesVisibility();
  }

  map.on("mousemove", updateHUD);
  map.on("move", updateHUD);
  map.on("zoom", updateHUD);

  map.scrollZoom.enable();
  map.dragRotate.enable();
  map.dragPan.enable();
  map.touchZoomRotate.enable();

  // Map click
  map.on("click", async (e) => {
    // Build factory mode
    if (mode === "factory_build") {
      // don't build when clicking over existing polygons
      const feats = map.queryRenderedFeatures(e.point, { layers: ["countries-fill"] });
      if (!feats || !feats.length) {
        // You may allow building only if inside your country - server will check anyway
      }
      return buildFactoryAt(e.lngLat.lng, e.lngLat.lat);
    }

    // Create country mode
    if (mode !== "create_country") return;

    const feats = map.queryRenderedFeatures(e.point, { layers: ["countries-fill"] });
    if (feats && feats.length) return;

    if (draftPoints.length >= RULES.country_max_points) return;

    draftPoints.push({ lng: e.lngLat.lng, lat: e.lngLat.lat });
    refreshDraftSource();
  });

  // ---- UI handlers (country) ----
  if (btnCreateCountry) btnCreateCountry.addEventListener("click", () => setMode("create_country"));

  if (btnUndo) btnUndo.addEventListener("click", () => {
    if (draftPoints.length) {
      draftPoints.pop();
      refreshDraftSource();
    }
  });

  if (btnCancel) btnCancel.addEventListener("click", () => setMode("explore"));

  if (btnFinish) btnFinish.addEventListener("click", () => {
    if (draftPoints.length < 3) return;
    openCountrySaveModal();
  });

  if (btnCloseCountry) btnCloseCountry.addEventListener("click", closeCountrySaveModal);
  if (btnSaveCountry) btnSaveCountry.addEventListener("click", saveCountry);

  // ---- UI handlers (factory sidebar) ----
  if (fbToggle && factorybar) {
    fbToggle.addEventListener("click", () => {
      factorybar.classList.toggle("collapsed");
    });
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
        }
      }
    });
  }

  if (btnCancelFactoryMode) {
    btnCancelFactoryMode.addEventListener("click", () => setMode("explore"));
  }

  if (btnTipFactory && fbTip) {
    btnTipFactory.addEventListener("click", () => {
      fbTip.style.display = (fbTip.style.display === "none" || !fbTip.style.display) ? "block" : "none";
    });
  }
  /* =========================================================
   COUNTRY PANEL + FACTORIES PANEL (ADD-ON BLOCK)
   Paste this at the VERY END of map.js
   ========================================================= */

// ---------- UI refs ----------
  

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

  

  // ---------- STATE ----------
  let factoriesPanelOpen = false;
  let currentCountryPanelId = null;

  // ---------- FACTORIES PANEL ----------
  function setFactoriesPanel(open) {
    factoriesPanelOpen = !!open;
    if (!factorybar) return;

    if (factoriesPanelOpen) {
      factorybar.classList.add("open");
    } else {
      factorybar.classList.remove("open");
    }
  }

  function toggleFactoriesPanel() {
    setFactoriesPanel(!factoriesPanelOpen);
  }

  if (btnOpenFactories) {
    btnOpenFactories.addEventListener("click", toggleFactoriesPanel);
  }

  // ---------- COUNTRY PANEL ----------
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
      const j = await r.json();
      if (!j.ok) return;

      const d = j.data || {};
      if (cpFactories) cpFactories.textContent = d.factories ?? "0";
      if (cpOwner) cpOwner.textContent = d.owner_username || "—";
      if (cpSub) {
        cpSub.textContent = d.is_mine ? "Your country ✅" : "Foreign country";
      }
    } catch (e) {
      console.warn("Failed to load country details", e);
    }
  }

  // ---------- MAP CLICK → OPEN COUNTRY PANEL ----------
  if (window.__earthMap) {
    window.__earthMap.on("click", "countries-fill", async (e) => {
      const f = e.features?.[0];
      if (!f) return;

      const id = Number(f.properties?.id || -1);
      if (id < 0) return;

      // highlight
      window.__earthMap.setFilter(
        "countries-selected",
        ["==", ["get", "id"], id]
      );

      openCountryPanelBasic(f.properties);
      await loadCountryDetailsToPanel(id);
    });
  }

  // ---------- PANEL BUTTONS ----------
  if (cpClose) cpClose.addEventListener("click", closeCountryPanel);

  if (cpFly && window.__earthMap) {
    cpFly.addEventListener("click", () => {
      if (!currentCountryPanelId) return;

      const feat = (window.countriesFC?.features || []).find(
        f => Number(f.properties?.id) === Number(currentCountryPanelId)
      );
      if (!feat) return;

      const ring = feat.geometry?.coordinates?.[0];
      if (!ring || ring.length < 3) return;

      let lng = 0, lat = 0;
      const pts = ring.slice(0, -1);
      for (const p of pts) {
        lng += p[0];
        lat += p[1];
      }
      lng /= pts.length;
      lat /= pts.length;

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

  // ---------- INIT ----------
  setFactoriesPanel(false);

})();