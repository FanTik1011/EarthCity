'use strict';

/* ================= CONFIG ================= */
const API_BASE = "";
const STYLE_URL = "https://demotiles.maplibre.org/style.json";

/* ================= I18N ================= */
const I18N = {
  en: {
    subtitle: "Globe-based world simulation",
    Balance: "Balance",
    City: "City",
    Loading: "Loading cities",
    SelectCity: "Select a city",
    ClickDot: "Click a dot on the globe",
    World: "World",
    Active: "Active",
    CityRating: "City rating",
    Players: "Players",
    Safety: "Safety",
    Tax: "Tax",
    Tip: "<strong>Tip:</strong> Click city dot to open dashboard. Create city → pick point on globe → confirm.",
    SignIn: "Sign in to EarthCity",
    CreateCity: "Create a city",
    CreateSteps: "1) Press “Pick on map”, 2) click on globe, 3) confirm create.",
    PickModeFeed: "📍 Pick mode: click on globe to set city location",
    Picked: "Picked",
    NeedLogin: "Please login first.",
  },
  uk: {
    subtitle: "Симуляція світу на глобусі",
    Balance: "Баланс",
    City: "Місто",
    Loading: "Завантаження міст",
    SelectCity: "Обери місто",
    ClickDot: "Натисни на точку на глобусі",
    World: "Світ",
    Active: "Активне",
    CityRating: "Рейтинг міста",
    Players: "Гравці",
    Safety: "Безпека",
    Tax: "Податок",
    Tip: "<strong>Порада:</strong> Клік по місту відкриває панель. Створення: Pick on map → клік по глобусу → Create.",
    SignIn: "Вхід в EarthCity",
    CreateCity: "Створити місто",
    CreateSteps: "1) Натисни “Pick on map”, 2) клікни по глобусу, 3) підтверди створення.",
    PickModeFeed: "📍 Режим вибору: клікни по глобусу щоб вибрати точку",
    Picked: "Вибрано",
    NeedLogin: "Спочатку увійди.",
  }
};

function getLang(){ return localStorage.getItem('lang') || 'en'; }
function setLang(lang){ localStorage.setItem('lang', lang); applyLang(); }
function T(key){
  const lang = getLang();
  return (I18N[lang] && I18N[lang][key]) ? I18N[lang][key] : (I18N.en[key] || key);
}

/* ================= STATE ================= */
let me = null;
let activeCity = null;
let createMode = false;
let pickedPoint = null;

/* ================= UI ================= */
const ui = {
  panel: document.getElementById('cityPanel'),
  currentCity: document.getElementById('currentCity'),
  cityName: document.getElementById('cityName'),
  cityCountry: document.getElementById('cityCountry'),
  cityRating: document.getElementById('cityRating'),
  cityPlayers: document.getElementById('cityPlayers'),
  citySafety: document.getElementById('citySafety'),
  cityTax: document.getElementById('cityTax'),
  cityStatus: document.getElementById('cityStatus'),
  loadingChip: document.getElementById('loadingChip'),
  feed: document.getElementById('feed'),
  authArea: document.getElementById('authArea'),
  balance: document.getElementById('balance'),

  subtitle: document.getElementById('subtitle'),
  tBalance: document.getElementById('tBalance'),
  tCity: document.getElementById('tCity'),
  tLoading: document.getElementById('tLoading'),
  kRating: document.getElementById('kRating'),
  kPlayers: document.getElementById('kPlayers'),
  kSafety: document.getElementById('kSafety'),
  kTax: document.getElementById('kTax'),
  hintText: document.getElementById('hintText'),
  langSelect: document.getElementById('langSelect'),

  loginModal: document.getElementById('loginModal'),
  btnLogin: document.getElementById('btnLogin'),
  btnCloseLogin: document.getElementById('btnCloseLogin'),

  createCityModal: document.getElementById('createCityModal'),
  btnCreateCity: document.getElementById('btnCreateCity'),
  btnCloseCreate: document.getElementById('btnCloseCreate'),
  btnPickOnMap: document.getElementById('btnPickOnMap'),
  btnCreateConfirm: document.getElementById('btnCreateConfirm'),
  newCityName: document.getElementById('newCityName'),
  newCityRadius: document.getElementById('newCityRadius'),
  createCityError: document.getElementById('createCityError'),
  tCreateTitle: document.getElementById('tCreateTitle'),
  tCreateStep: document.getElementById('tCreateStep'),

  btnExpand: document.getElementById('btnExpand'),
  btnOpen3D: document.getElementById('btnOpen3D'),
};

function applyLang(){
  const lang = getLang();
  ui.langSelect.value = lang;

  ui.subtitle.textContent = T('subtitle');
  ui.tBalance.textContent = T('Balance');
  ui.tCity.textContent = T('City');
  ui.tLoading.textContent = T('Loading');

  ui.kRating.textContent = T('CityRating');
  ui.kPlayers.textContent = T('Players');
  ui.kSafety.textContent = T('Safety');
  ui.kTax.textContent = T('Tax');

  ui.hintText.innerHTML = T('Tip');
  document.getElementById('authTitle').textContent = T('SignIn');
  ui.tCreateTitle.textContent = T('CreateCity');
  ui.tCreateStep.textContent = T('CreateSteps');

  if(ui.currentCity.textContent === '—') setPanelCity(null);
}
ui.langSelect.addEventListener('change', (e)=>setLang(e.target.value));

function setLoading(on){ ui.loadingChip.style.display = on ? 'flex' : 'none'; }
function panelUpdating(on){ ui.panel.classList.toggle('updating', !!on); }

function pushFeed(text){
  const item = document.createElement('div');
  item.className = 'feed-item';
  item.textContent = text;
  ui.feed.prepend(item);
}

function showCreateError(msg){
  ui.createCityError.textContent = msg || '';
  ui.createCityError.style.display = msg ? 'block' : 'none';
}

function clearCityRadius(){
  // прибрати коло
  if(map.getLayer('city-radius-outline')) map.removeLayer('city-radius-outline');
  if(map.getLayer('city-radius')) map.removeLayer('city-radius');
  if(map.getSource('city-radius')) map.removeSource('city-radius');
}

function setPanelCity(city){
  ui.currentCity.textContent = city?.name ?? '—';
  ui.cityName.textContent = city?.name ?? T('SelectCity');
  ui.cityCountry.textContent = city?.name ? '' : T('ClickDot');

  ui.cityRating.textContent = (city?.rating ?? '—') + (city?.rating != null ? '%' : '');
  ui.cityPlayers.textContent = city?.players != null ? Number(city.players).toLocaleString() : '—';
  ui.citySafety.textContent = city?.safety ?? '—';
  ui.cityTax.textContent = (city?.tax ?? '—') + (city?.tax != null ? '%' : '');

  ui.cityStatus.textContent = city?.name ? T('Active') : T('World');

  if(!city) clearCityRadius();
}

/* ================= AUTH ================= */
function openLogin(){ ui.loginModal.style.display = 'flex'; }
function closeLogin(){ ui.loginModal.style.display = 'none'; }
ui.btnLogin?.addEventListener('click', openLogin);
ui.btnCloseLogin?.addEventListener('click', closeLogin);
ui.loginModal?.addEventListener('click', (e)=>{ if(e.target===ui.loginModal) closeLogin(); });

let authMode = "login";
const auth = {
  tabLogin: document.getElementById('tabLogin'),
  tabRegister: document.getElementById('tabRegister'),
  username: document.getElementById('authUsername'),
  email: document.getElementById('authEmail'),
  password: document.getElementById('authPassword'),
  submit: document.getElementById('btnAuthSubmit'),
  hint: document.getElementById('authHint'),
  error: document.getElementById('authError'),
};

function showAuthError(msg){
  auth.error.textContent = msg || '';
  auth.error.style.display = msg ? 'block' : 'none';
}

function setAuthMode(mode){
  authMode = mode;
  showAuthError('');

  auth.tabLogin.classList.toggle('active', mode === 'login');
  auth.tabRegister.classList.toggle('active', mode === 'register');

  if(mode === 'register'){
    auth.submit.textContent = 'Register';
    auth.email.style.display = 'block';
    auth.hint.textContent = 'Create account (email optional).';
    auth.password.autocomplete = 'new-password';
  } else {
    auth.submit.textContent = 'Login';
    auth.email.style.display = 'none';
    auth.hint.textContent = 'Login with your username & password.';
    auth.password.autocomplete = 'current-password';
  }
}
auth.tabLogin.addEventListener('click', ()=>setAuthMode('login'));
auth.tabRegister.addEventListener('click', ()=>setAuthMode('register'));

auth.submit.addEventListener('click', async ()=>{
  showAuthError('');
  const username = (auth.username.value || '').trim();
  const email = (auth.email.value || '').trim();
  const password = auth.password.value || '';

  if(!username || !password){
    showAuthError('Username and password are required.');
    return;
  }

  const url = (authMode === 'register')
    ? `${API_BASE}/api/auth/register`
    : `${API_BASE}/api/auth/login`;

  const payload = (authMode === 'register')
    ? { username, email, password }
    : { username, password };

  const res = await fetch(url, {
    method:'POST',
    headers:{ 'Content-Type':'application/json' },
    body: JSON.stringify(payload)
  });

  if(res.ok){
    location.reload();
  } else {
    const data = await res.json().catch(()=> ({}));
    showAuthError(data.error || 'Auth failed.');
  }
});

[auth.username, auth.email, auth.password].forEach(el=>{
  el.addEventListener('keydown', (e)=>{ if(e.key==='Enter') auth.submit.click(); });
});

async function checkAuth(){
  const res = await fetch(`${API_BASE}/api/me`);
  const data = await res.json().catch(()=>({ authenticated:false }));
  me = data;

  if(!data.authenticated){
    ui.authArea.innerHTML = `<button class="login-btn" id="btnLogin2">Login</button>`;
    document.getElementById('btnLogin2').onclick = openLogin;
    ui.balance.textContent = '$—';
    return;
  }

  ui.balance.textContent = '$' + Number(data.user.balance).toLocaleString();

  ui.authArea.innerHTML = `
    <div class="user-pill">
      👤 ${data.user.username}
      <span class="muted">(${data.user.role})</span>
      <span style="cursor:pointer" id="btnLogout" title="Logout">⎋</span>
    </div>
  `;
  document.getElementById('btnLogout').onclick = async ()=>{
    await fetch(`${API_BASE}/api/auth/logout`, { method:'POST' });
    location.reload();
  };
}

/* ================= MAP ================= */
const map = new maplibregl.Map({
  container: 'map',
  style: STYLE_URL,
  center: [24.0297, 49.8397],
  zoom: 3.2,
  pitch: 35,
  bearing: -20,
  projection: 'globe'
});

map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'top-left');

const SOURCE_ID = 'cities';
const LAYER_ID = 'cities-layer';
const LAYER_ACTIVE = 'cities-layer-active';

function toGeoJSON(cities){
  return {
    type: "FeatureCollection",
    features: cities.map(c => ({
      type: "Feature",
      properties: {
        id: c.id,
        name: c.name,
        rating: c.rating,
        players: c.players,
        safety: c.safety,
        tax: c.tax,
        radius_km: c.radius_km,
        mayor_user_id: c.mayor_user_id
      },
      geometry: { type: "Point", coordinates: [c.lng, c.lat] }
    }))
  };
}

async function fetchCitiesForViewport(){
  setLoading(true);
  try{
    const b = map.getBounds();
    const bbox = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].join(',');

    const res = await fetch(`${API_BASE}/api/cities?bbox=${encodeURIComponent(bbox)}`);
    if(!res.ok){
      pushFeed('⚠️ Failed to load cities (/api/cities)');
      return;
    }

    const data = await res.json().catch(()=>({ cities:[] }));
    const cities = data.cities || [];
    const geo = toGeoJSON(cities);

    if(map.getSource(SOURCE_ID)){
      map.getSource(SOURCE_ID).setData(geo);
      return;
    }

    map.addSource(SOURCE_ID, { type: 'geojson', data: geo });

    map.addLayer({
      id: LAYER_ID,
      type: 'circle',
      source: SOURCE_ID,
      paint: {
        'circle-radius': 4.5,
        'circle-color': '#4da3ff',
        'circle-opacity': 0.9,
        'circle-stroke-color': '#0b0f14',
        'circle-stroke-width': 1.2
      }
    });

    map.addLayer({
      id: LAYER_ACTIVE,
      type: 'circle',
      source: SOURCE_ID,
      filter: ['==', ['get', 'id'], -1],
      paint: {
        'circle-radius': 7.5,
        'circle-color': '#4da3ff',
        'circle-opacity': 1,
        'circle-stroke-color': '#ffffff',
        'circle-stroke-width': 2.2
      }
    });

    map.on('mouseenter', LAYER_ID, () => map.getCanvas().style.cursor = 'pointer');
    map.on('mouseleave', LAYER_ID, () => map.getCanvas().style.cursor = '');

    map.on('click', LAYER_ID, async (e) => {
      const f = e.features?.[0];
      if(!f) return;

      const id = Number(f.properties.id);
      panelUpdating(true);
      try{
        const r = await fetch(`${API_BASE}/api/cities/${id}`);
        if(!r.ok) return;
        const detail = await r.json();

        activeCity = detail;
        map.setFilter(LAYER_ACTIVE, ['==', ['get', 'id'], id]);

        map.easeTo({
          center: [detail.lng, detail.lat],
          zoom: Math.max(map.getZoom(), 6),
          duration: 900
        });

        setPanelCity(detail);
        drawCityRadius(detail);
        pushFeed(`📍 Selected: ${detail.name}`);
      } finally {
        setTimeout(()=>panelUpdating(false), 140);
      }
    });

  } finally {
    setLoading(false);
  }
}

/* ================= CREATE CITY FLOW ================= */
function openCreateModal(){
  showCreateError('');
  ui.createCityModal.style.display = 'flex';
  ui.tCreateStep.textContent = T('CreateSteps');
  pickedPoint = null;
  createMode = false;
  ui.panel.classList.remove('pickmode');
}
function closeCreateModal(){
  ui.createCityModal.style.display = 'none';
  createMode = false;
  pickedPoint = null;
  ui.panel.classList.remove('pickmode');
}

ui.btnCreateCity.addEventListener('click', ()=>{
  if(!me?.authenticated){ openLogin(); return; }
  openCreateModal();
});

ui.btnCloseCreate.addEventListener('click', closeCreateModal);
ui.createCityModal.addEventListener('click', (e)=>{ if(e.target===ui.createCityModal) closeCreateModal(); });

ui.btnPickOnMap.addEventListener('click', ()=>{
  showCreateError('');
  if(!me?.authenticated){ showCreateError(T('NeedLogin')); return; }
  createMode = true;
  ui.createCityModal.style.display = 'none';
  ui.panel.classList.add('pickmode');
  pushFeed(T('PickModeFeed'));
});

// pick point on globe
map.on('click', (e)=>{
  if(!createMode) return;

  // ignore click on city dot
  if(map.getLayer(LAYER_ID)){
    const hit = map.queryRenderedFeatures(e.point, { layers:[LAYER_ID] });
    if(hit && hit.length) return;
  }

  pickedPoint = { lng: e.lngLat.lng, lat: e.lngLat.lat };
  createMode = false;

  ui.panel.classList.remove('pickmode');
  ui.createCityModal.style.display = 'flex';

  ui.tCreateStep.textContent = `${T('Picked')}: ${pickedPoint.lat.toFixed(4)}, ${pickedPoint.lng.toFixed(4)}`;
  pushFeed(`📌 ${T('Picked')}: ${pickedPoint.lat.toFixed(4)}, ${pickedPoint.lng.toFixed(4)}`);
});

ui.btnCreateConfirm.addEventListener('click', async ()=>{
  showCreateError('');
  if(!me?.authenticated){ showCreateError(T('NeedLogin')); return; }

  const name = (ui.newCityName.value || '').trim();
  const radius_km = Number(ui.newCityRadius.value || 15);

  if(name.length < 3 || name.length > 32){
    showCreateError('City name must be 3..32 chars.');
    return;
  }
  if(!pickedPoint){
    showCreateError('Pick location: click “Pick on map” and choose point.');
    return;
  }
  if(!(radius_km >= 5 && radius_km <= 200)){
    showCreateError('radius_km must be 5..200');
    return;
  }

  const res = await fetch(`${API_BASE}/api/cities/create`, {
    method: 'POST',
    headers: { 'Content-Type':'application/json' },
    body: JSON.stringify({
      name,
      lat: pickedPoint.lat,
      lng: pickedPoint.lng,
      radius_km
    })
  });

  const data = await res.json().catch(()=>({}));
  if(!res.ok){
    showCreateError(data.error || 'Create failed.');
    return;
  }

  pushFeed(`✅ City created: ${data.city?.name || name}`);
  closeCreateModal();

  await checkAuth();
  await fetchCitiesForViewport();

  // auto select created city
  if(data.city?.id){
    const r = await fetch(`${API_BASE}/api/cities/${data.city.id}`);
    if(r.ok){
      const detail = await r.json();
      activeCity = detail;
      map.setFilter(LAYER_ACTIVE, ['==', ['get','id'], detail.id]);
      setPanelCity(detail);
      drawCityRadius(detail);
      map.easeTo({ center:[detail.lng, detail.lat], zoom: Math.max(map.getZoom(), 6), duration: 900 });
    }
  }
});

/* ================= EXPAND ================= */
ui.btnExpand.addEventListener('click', async ()=>{
  if(!me?.authenticated){ openLogin(); return; }
  if(!activeCity?.id){
    pushFeed('ℹ️ Select a city first');
    return;
  }

  const addKmRaw = prompt('How many km to add? (1..25)', '5');
  if(addKmRaw == null) return;
  const add_km = Number(addKmRaw);

  if(!(add_km > 0 && add_km <= 25)){
    pushFeed('⚠️ add_km must be 1..25');
    return;
  }

  const res = await fetch(`${API_BASE}/api/cities/${activeCity.id}/expand`, {
    method:'POST',
    headers:{ 'Content-Type':'application/json' },
    body: JSON.stringify({ add_km })
  });

  const data = await res.json().catch(()=>({}));
  if(!res.ok){
    pushFeed(`⚠️ ${data.error || 'Expand failed'}`);
    return;
  }

  pushFeed(`✅ Expanded. Cost: ${data.cost}$, New radius: ${data.new_radius_km} km`);

  const r = await fetch(`${API_BASE}/api/cities/${activeCity.id}`);
  if(r.ok){
    const detail = await r.json();
    activeCity = detail;
    setPanelCity(detail);
    drawCityRadius(detail);
  }

  await checkAuth();
  await fetchCitiesForViewport();
});

/* ================= OPEN 3D ================= */
ui.btnOpen3D.addEventListener('click', () => {
  if(!activeCity?.id){
    pushFeed('ℹ️ Select a city first');
    return;
  }
  if(!me?.authenticated){
    openLogin();
    return;
  }
  window.open(`/city/${activeCity.id}`, '_blank');
});

/* ================= CITY RADIUS VISUAL ================= */
// геодезичне коло (реальний км)
function makeCircle(lng, lat, radiusKm, steps = 64){
  const coords = [];
  const r = radiusKm / 6371;
  const latRad = lat * Math.PI / 180;
  const lngRad = lng * Math.PI / 180;

  for(let i=0;i<=steps;i++){
    const brng = i * 2 * Math.PI / steps;
    const lat2 = Math.asin(
      Math.sin(latRad) * Math.cos(r) +
      Math.cos(latRad) * Math.sin(r) * Math.cos(brng)
    );
    const lng2 = lngRad + Math.atan2(
      Math.sin(brng) * Math.sin(r) * Math.cos(latRad),
      Math.cos(r) - Math.sin(latRad) * Math.sin(lat2)
    );
    coords.push([lng2 * 180/Math.PI, lat2 * 180/Math.PI]);
  }
  return coords;
}

function drawCityRadius(city){
  if(!city?.radius_km) { clearCityRadius(); return; }

  clearCityRadius();

  map.addSource('city-radius',{
    type:'geojson',
    data:{
      type:'Feature',
      geometry:{
        type:'Polygon',
        coordinates:[ makeCircle(city.lng, city.lat, city.radius_km) ]
      }
    }
  });

  map.addLayer({
    id:'city-radius',
    type:'fill',
    source:'city-radius',
    paint:{
      'fill-color':'#4da3ff',
      'fill-opacity':0.18
    }
  });

  map.addLayer({
    id:'city-radius-outline',
    type:'line',
    source:'city-radius',
    paint:{
      'line-color':'#4da3ff',
      'line-width':2,
      'line-opacity':0.95
    }
  });
}

/* ================= INIT ================= */
applyLang();
setAuthMode('login');

map.on('load', ()=>{
  setPanelCity(null);

  if(map.setFog){
    map.setFog({ range:[0.8,8], color:'rgba(18,22,30,0.75)', 'horizon-blend':0.15 });
  }

  fetchCitiesForViewport();

  let t=null;
  map.on('moveend', ()=>{ clearTimeout(t); t=setTimeout(fetchCitiesForViewport, 180); });
  map.on('zoomend', ()=>{ clearTimeout(t); t=setTimeout(fetchCitiesForViewport, 180); });
});

checkAuth();
