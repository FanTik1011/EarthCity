'use strict';

/* ================== helpers ================== */
function getCityIdFromPath(){
  const p = location.pathname.split('/').filter(Boolean); // ["city","123"]
  const i = p.indexOf('city');
  if(i === -1 || !p[i+1]) return null;
  const id = Number(p[i+1]);
  return Number.isFinite(id) ? id : null;
}
const CITY_ID = getCityIdFromPath();
const LS_KEY = `earthcity_buildings_city_${CITY_ID}`;

/* ================== UI ================== */
const statusEl = document.getElementById('status');

const btnModePlace = document.getElementById('btnModePlace');
const btnModeSelect = document.getElementById('btnModeSelect');

const btnTypeHouse = document.getElementById('btnTypeHouse');
const btnTypeFactory = document.getElementById('btnTypeFactory');
const btnTypeShop = document.getElementById('btnTypeShop');

const btnReplace = document.getElementById('btnReplace');
const btnUpgrade = document.getElementById('btnUpgrade');
const btnRotate = document.getElementById('btnRotate');
const btnDelete = document.getElementById('btnDelete');

/* ================== State ================== */
let city = null;

let mode = 'select';            // 'place' | 'select'
let currentType = 'house';      // що ставимо в place режимі
let selectedId = null;          // вибрана будівля

// Grid settings
const CELL = 2;                 // розмір клітинки (в world units)
const GRID_HALF = 15;           // піврозмір поля в клітинках (15 => 30x30 клітин)
const GROUND_SIZE = GRID_HALF * 2 * CELL; // реальний розмір площини

// buildings store
// id -> { id, kind, level, x, z, rot }
const buildings = new Map();

/* ================== storage (temporary) ================== */
function saveToLocal(){
  const arr = Array.from(buildings.values());
  localStorage.setItem(LS_KEY, JSON.stringify(arr));
}
function loadFromLocal(){
  buildings.clear();
  const raw = localStorage.getItem(LS_KEY);
  if(!raw) return;
  try{
    const arr = JSON.parse(raw);
    if(Array.isArray(arr)){
      for(const b of arr){
        if(!b || b.id == null) continue;
        buildings.set(b.id, b);
      }
    }
  }catch{}
}

/* ================== Three.js base ================== */
const canvas = document.getElementById('c');
const renderer = new THREE.WebGLRenderer({ canvas, antialias:true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0b0f14);

const camera = new THREE.PerspectiveCamera(55, 2, 0.1, 2000);
camera.position.set(18, 18, 18);

const controls = new THREE.OrbitControls(camera, canvas);
controls.enableDamping = true;
controls.target.set(0, 0, 0);

scene.add(new THREE.AmbientLight(0xffffff, 0.55));
const dir = new THREE.DirectionalLight(0xffffff, 0.85);
dir.position.set(30, 40, 10);
scene.add(dir);

// ground (clickable)
const groundMat = new THREE.MeshStandardMaterial({ color: 0x0f1622, roughness: 1, metalness: 0 });
const ground = new THREE.Mesh(new THREE.PlaneGeometry(GROUND_SIZE, GROUND_SIZE), groundMat);
ground.rotation.x = -Math.PI / 2;
ground.name = 'GROUND';
scene.add(ground);

// grid helper
scene.add(new THREE.GridHelper(GROUND_SIZE, GRID_HALF * 2, 0x2a3a55, 0x1b2738));

// highlight square (cursor / selected cell)
const highlight = new THREE.Mesh(
  new THREE.PlaneGeometry(CELL, CELL),
  new THREE.MeshBasicMaterial({ transparent:true, opacity:0.25 })
);
highlight.rotation.x = -Math.PI / 2;
highlight.visible = false;
scene.add(highlight);

// raycasting
const raycaster = new THREE.Raycaster();
const mouse = new THREE.Vector2();

/* ================== mesh registry ================== */
// Тут головне: в майбутньому заміниш на завантаження GLB моделей, а логіка лишиться.
function createBuildingMesh(kind, level = 1){
  // базові розміри/висоти
  const baseH = 1.1 + (level - 1) * 0.6;

  let geom;
  let mat;

  if(kind === 'house'){
    geom = new THREE.BoxGeometry(1.2, baseH, 1.2);
    mat = new THREE.MeshStandardMaterial({ color: 0x4da3ff });
  } else if(kind === 'factory'){
    geom = new THREE.BoxGeometry(1.6, baseH + 0.8, 1.6);
    mat = new THREE.MeshStandardMaterial({ color: 0x3ccf91 });
  } else if(kind === 'shop'){
    geom = new THREE.BoxGeometry(1.4, baseH, 1.4);
    mat = new THREE.MeshStandardMaterial({ color: 0xffc24d });
  } else {
    geom = new THREE.BoxGeometry(1.2, baseH, 1.2);
    mat = new THREE.MeshStandardMaterial({ color: 0x9aa4b2 });
  }

  const mesh = new THREE.Mesh(geom, mat);
  mesh.castShadow = false;
  mesh.receiveShadow = false;
  return mesh;
}

/* ================== placement math ================== */
function snapToGrid(x, z){
  const gx = Math.round(x / CELL) * CELL;
  const gz = Math.round(z / CELL) * CELL;
  // clamp inside ground
  const limit = (GROUND_SIZE / 2) - CELL/2;
  return {
    x: Math.max(-limit, Math.min(limit, gx)),
    z: Math.max(-limit, Math.min(limit, gz)),
  };
}
function keyFromXZ(x, z){
  // ключ клітинки
  return `${x.toFixed(3)}:${z.toFixed(3)}`;
}

/* ================== scene objects for buildings ================== */
const buildingGroup = new THREE.Group();
scene.add(buildingGroup);

// id -> mesh
const buildingMeshes = new Map();

function upsertBuildingMesh(b){
  // remove old
  const old = buildingMeshes.get(b.id);
  if(old){
    buildingGroup.remove(old);
    old.geometry?.dispose?.();
    old.material?.dispose?.();
    buildingMeshes.delete(b.id);
  }

  const mesh = createBuildingMesh(b.kind, b.level);
  mesh.position.set(b.x, (mesh.geometry.parameters.height ?? 1)/2, b.z);
  mesh.rotation.y = b.rot || 0;

  mesh.userData.buildingId = b.id;
  buildingGroup.add(mesh);
  buildingMeshes.set(b.id, mesh);
}

function removeBuildingMesh(id){
  const old = buildingMeshes.get(id);
  if(!old) return;
  buildingGroup.remove(old);
  old.geometry?.dispose?.();
  old.material?.dispose?.();
  buildingMeshes.delete(id);
}

/* ================== logic ================== */
function setMode(next){
  mode = next;
  statusEl.textContent = `Mode: ${mode} | Type: ${currentType}` + (selectedId ? ` | Selected: #${selectedId}` : '');
}

function setCurrentType(t){
  currentType = t;
  setMode(mode);
}

function setSelected(id){
  selectedId = id;
  setMode(mode);
}

function newId(){
  return Math.floor(Date.now() + Math.random()*1000);
}

function canPlaceAt(x, z){
  const cellKey = keyFromXZ(x, z);
  for(const b of buildings.values()){
    if(keyFromXZ(b.x, b.z) === cellKey) return false;
  }
  return true;
}

function placeBuildingAt(x, z, kind){
  if(!canPlaceAt(x, z)){
    statusEl.textContent = 'Cell is occupied. Choose another.';
    return;
  }
  const id = newId();
  const b = { id, kind, level: 1, x, z, rot: 0 };
  buildings.set(id, b);
  upsertBuildingMesh(b);
  saveToLocal();
  setSelected(id);
}

function replaceSelected(newKind){
  if(!selectedId || !buildings.has(selectedId)) return;
  const b = buildings.get(selectedId);
  b.kind = newKind;
  upsertBuildingMesh(b);
  saveToLocal();
}

function upgradeSelected(){
  if(!selectedId || !buildings.has(selectedId)) return;
  const b = buildings.get(selectedId);
  b.level = Math.min(10, (b.level || 1) + 1);
  upsertBuildingMesh(b);
  saveToLocal();
}

function rotateSelected(){
  if(!selectedId || !buildings.has(selectedId)) return;
  const b = buildings.get(selectedId);
  b.rot = (b.rot || 0) + Math.PI / 2;
  upsertBuildingMesh(b);
  saveToLocal();
}

function deleteSelected(){
  if(!selectedId || !buildings.has(selectedId)) return;
  buildings.delete(selectedId);
  removeBuildingMesh(selectedId);
  saveToLocal();
  setSelected(null);
}

/* ================== clicking / selection ================== */
function setMouseFromEvent(ev){
  const rect = canvas.getBoundingClientRect();
  mouse.x = ((ev.clientX - rect.left) / rect.width) * 2 - 1;
  mouse.y = -(((ev.clientY - rect.top) / rect.height) * 2 - 1);
}

function pick(ev){
  setMouseFromEvent(ev);
  raycaster.setFromCamera(mouse, camera);

  // 1) try building hit
  const bHits = raycaster.intersectObjects(Array.from(buildingMeshes.values()), true);
  if(bHits.length){
    const id = bHits[0].object.userData.buildingId;
    if(id != null){
      setSelected(id);
      return { type:'building', id };
    }
  }

  // 2) ground hit
  const hits = raycaster.intersectObject(ground, false);
  if(!hits.length) return null;
  const p = hits[0].point;
  const snapped = snapToGrid(p.x, p.z);
  return { type:'ground', ...snapped };
}

canvas.addEventListener('mousemove', (ev)=>{
  const hit = pick(ev);
  if(hit && hit.type === 'ground'){
    highlight.visible = true;
    highlight.position.set(hit.x, 0.01, hit.z);
  } else {
    highlight.visible = false;
  }
});

canvas.addEventListener('click', (ev)=>{
  const hit = pick(ev);
  if(!hit) return;

  if(mode === 'place' && hit.type === 'ground'){
    placeBuildingAt(hit.x, hit.z, currentType);
  } else if(mode === 'select' && hit.type === 'ground'){
    // клік по землі — зняти виділення
    setSelected(null);
  }
});

/* ================== buttons ================== */
btnModePlace?.addEventListener('click', ()=>setMode('place'));
btnModeSelect?.addEventListener('click', ()=>setMode('select'));

btnTypeHouse?.addEventListener('click', ()=>setCurrentType('house'));
btnTypeFactory?.addEventListener('click', ()=>setCurrentType('factory'));
btnTypeShop?.addEventListener('click', ()=>setCurrentType('shop'));

// Replace: замінити вибрану будівлю на поточний тип
btnReplace?.addEventListener('click', ()=>{
  if(!selectedId){ statusEl.textContent = 'Select building first.'; return; }
  replaceSelected(currentType);
});

// Upgrade / Rotate / Delete
btnUpgrade?.addEventListener('click', ()=>{
  if(!selectedId){ statusEl.textContent = 'Select building first.'; return; }
  upgradeSelected();
});
btnRotate?.addEventListener('click', ()=>{
  if(!selectedId){ statusEl.textContent = 'Select building first.'; return; }
  rotateSelected();
});
btnDelete?.addEventListener('click', ()=>{
  if(!selectedId){ statusEl.textContent = 'Select building first.'; return; }
  deleteSelected();
});

/* ================== init ================== */
async function loadCity(){
  const r = await fetch(`/api/cities/${CITY_ID}`);
  const data = await r.json().catch(()=>({}));
  if(!r.ok){
    statusEl.textContent = data.error || 'Failed to load city';
    return null;
  }
  return data;
}

function renderAllBuildingsFromStore(){
  for(const b of buildings.values()){
    upsertBuildingMesh(b);
  }
}

function resize(){
  const w = canvas.clientWidth;
  const h = canvas.clientHeight;
  if(canvas.width !== w || canvas.height !== h){
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }
}

function animate(){
  resize();
  controls.update();
  renderer.render(scene, camera);
  requestAnimationFrame(animate);
}

(async ()=>{
  if(!CITY_ID){
    statusEl.textContent = 'City ID not found in URL';
    return;
  }

  city = await loadCity();
  if(city){
    statusEl.textContent = `${city.name} • radius ${city.radius_km} km • tax ${city.tax}%`;
  }

  loadFromLocal();
  renderAllBuildingsFromStore();

  setMode('select');
  animate();
})();
