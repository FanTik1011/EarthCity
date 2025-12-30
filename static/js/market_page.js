// static/js/market_page.js
// NPC Market only (no P2P)
// - Inventory stickers (Sell) + NPC Buy + Harvest
// - Confirm modal via window.MarketUI.openConfirm()

(function () {
  const $ = (id) => document.getElementById(id);

  // Header
  const pillUser = $("pillUser");
  const pillCoins = $("pillCoins");
  const countryLine = $("countryLine");
  const btnHarvest = $("btnHarvest");

  // Toast
  const msg = $("msg");

  // Inventory
  const invGrid = $("invGrid");

  // NPC
  const buyRes = $("buyRes");
  const buyAmt = $("buyAmt");
  const buyInfo = $("buyInfo");
  const btnBuy = $("btnBuy");

  // Scroll buttons (optional)
  $("btnGoInv")?.addEventListener("click", () => $("secInventory")?.scrollIntoView({ behavior: "smooth" }));
  $("btnGoMarket")?.addEventListener("click", () => $("secMarket")?.scrollIntoView({ behavior: "smooth" }));
  $("btnScrollInv")?.addEventListener("click", () => $("secInventory")?.scrollIntoView({ behavior: "smooth" }));
  $("btnScrollMarket")?.addEventListener("click", () => $("secMarket")?.scrollIntoView({ behavior: "smooth" }));
  $("fabTop")?.addEventListener("click", () => window.scrollTo({ top: 0, behavior: "smooth" }));
  $("fabInv")?.addEventListener("click", () => $("secInventory")?.scrollIntoView({ behavior: "smooth" }));
  $("fabMk")?.addEventListener("click", () => $("secMarket")?.scrollIntoView({ behavior: "smooth" }));

  // ---------- Meta ----------
  const RESOURCE_META = {
    oil: { icon: "🛢️", name: "Oil" },
    gas: { icon: "🔥", name: "Gas" },
    iron: { icon: "⛏️", name: "Iron" },
    gold: { icon: "🪙", name: "Gold" },
    coal: { icon: "🪨", name: "Coal" },
    uranium: { icon: "☢️", name: "Uranium" },
    rare: { icon: "💎", name: "Rare" },
    water: { icon: "💧", name: "Water" },
    farmland: { icon: "🌾", name: "Farmland" },
    fish: { icon: "🐟", name: "Fish" },
    wind: { icon: "🌬️", name: "Wind" },
    solar: { icon: "☀️", name: "Solar" },
    hydro: { icon: "🌊", name: "Hydro" },
    geo: { icon: "🌋", name: "Geo" },
  };

  function meta(r) {
    return RESOURCE_META[r] || { icon: "✨", name: r };
  }
  function resLabel(r) {
    const m = meta(r);
    return `${m.icon} ${m.name}`;
  }

  // ---------- State ----------
  let ME = null;
  let MY_COUNTRY = null;
  let COUNTRY_ID = null;

  let INVENTORY = {};
  let PRICES = {};
  let PRICE_ORDER = [];

  // ---------- UI helpers ----------
  function toast(text, kind = "info") {
    if (!msg) return;
    msg.style.display = "block";
    msg.classList.remove("ok", "err");
    if (kind === "ok") msg.classList.add("ok");
    if (kind === "err") msg.classList.add("err");
    msg.textContent = text || "";
  }
  function clearToast() {
    if (!msg) return;
    msg.style.display = "none";
    msg.classList.remove("ok", "err");
    msg.textContent = "";
  }

  function fmt(n) {
    const v = Number(n || 0);
    if (!isFinite(v)) return "0";
    if (Math.abs(v) >= 1000) return Math.round(v).toLocaleString("en-US");
    return (Math.round(v * 10) / 10).toString();
  }
  function clamp(n, a, b) {
    const v = Number(n);
    if (!isFinite(v)) return a;
    return Math.max(a, Math.min(b, v));
  }

  // ---------- Fetch helpers ----------
  async function getJSON(url) {
    const r = await fetch(url, { credentials: "include" });
    let j = {};
    try { j = await r.json(); } catch { j = {}; }
    if (!r.ok) throw new Error(j.error || j.message || `HTTP ${r.status}`);
    return j;
  }

  async function postJSON(url, body) {
    const r = await fetch(url, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    let j = {};
    try { j = await r.json(); } catch { j = {}; }
    if (!r.ok) throw new Error(j.error || j.message || `HTTP ${r.status}`);
    return j;
  }

  // ---------- Prices ----------
  const priceSell = (r) => Number(PRICES?.[r]?.sell || 0);
  const priceBuy = (r) => Number(PRICES?.[r]?.buy || 0);
  const basePrice = (r) => Number(PRICES?.[r]?.base || 0);

  async function loadPrices() {
    const j = await getJSON("/api/market/prices");
    PRICES = j.data || {};
    PRICE_ORDER = j.order || Object.keys(PRICES);
    if (!PRICE_ORDER.length) PRICE_ORDER = Object.keys(PRICES);

    // fill NPC select
    buyRes.innerHTML = "";
    for (const r of PRICE_ORDER) {
      const opt = document.createElement("option");
      opt.value = r;
      opt.textContent = `${resLabel(r)} • Buy ${priceBuy(r)} EC`;
      buyRes.appendChild(opt);
    }

    updateBuyInfo();
  }

  function updateBuyInfo() {
    const r = buyRes.value;
    const amt = Math.max(0, Number(buyAmt.value || 0));
    const p = priceBuy(r);
    const total = Math.round(p * amt);
    buyInfo.textContent = `Price: ${p || "—"} EC each • Total: ${isFinite(total) ? total : "—"} EC`;
  }

  // ---------- Me / country / inventory ----------
  async function loadMe() {
    const j = await getJSON("/api/me");
    ME = j;

    if (!ME?.authenticated) throw new Error("Спочатку увійди (login).");

    pillUser.textContent = `👤 ${ME.username || "User"}`;
    pillCoins.textContent = `💰 ${(ME.coins ?? 0)} EC`;

    if (ME.is_confirmed === false) {
      toast("Підтверди email, щоб користуватись HARVEST/Market.", "err");
    }
  }

  async function loadMyCountry() {
    const j = await getJSON("/api/my/country");
    MY_COUNTRY = j.data;

    if (!MY_COUNTRY) throw new Error("Спочатку створи свою країну на карті.");

    COUNTRY_ID = Number(MY_COUNTRY.properties?.id || MY_COUNTRY.id || 0);
    const nm = MY_COUNTRY.properties?.name || MY_COUNTRY.name || "My Country";

    countryLine.textContent = `Країна: ${nm} • id=${COUNTRY_ID}`;
    if (!COUNTRY_ID) throw new Error("Не знайшов id країни.");
  }

  async function loadInventory() {
    const j = await getJSON(`/api/countries/${COUNTRY_ID}/inventory`);
    INVENTORY = j.data || {};
    renderInventory();
  }

  // ---------- Inventory render ----------
  function sortedResources() {
    const keysInv = Object.keys(INVENTORY || {});
    const all = new Set([...Object.keys(PRICES || {}), ...keysInv]);
    const list = Array.from(all);

    list.sort((a, b) => {
      const da = Number(INVENTORY[a] || 0);
      const db = Number(INVENTORY[b] || 0);
      if (db !== da) return db - da;
      return basePrice(b) - basePrice(a);
    });

    return list;
  }

  function renderInventory() {
    const list = sortedResources();
    invGrid.innerHTML = "";

    // show empty state nicely
    const totalHave = list.reduce((s, r) => s + (Number(INVENTORY[r] || 0) || 0), 0);
    if (!list.length || totalHave <= 0) {
      invGrid.innerHTML = `
        <div class="mkSticker" style="grid-column:1/-1;">
          <div class="mkStkHead">
            <div class="mkStkName">
              <div class="mkIconBox">📦</div>
              <div>
                Empty inventory
                <div class="mkKey">Press HARVEST</div>
              </div>
            </div>
            <div class="mkPriceTag">⛏️ try HARVEST</div>
          </div>
          <div class="mkNote" style="margin-top:10px;">
            Якщо HARVEST нічого не дає — перевір чи є resource nodes в межах кордону.
          </div>
        </div>
      `;
      return;
    }

    let mx = 1;
    for (const r of list) mx = Math.max(mx, Number(INVENTORY[r] || 0) || 0);
    mx = Math.max(mx, 1);

    for (const r of list) {
      const have = Number(INVENTORY[r] || 0);
      if (have <= 0) continue;

      const sp = priceSell(r);
      const bp = priceBuy(r);
      const m = meta(r);
      const frac = clamp(have / mx, 0, 1);

      const el = document.createElement("div");
      el.className = "mkSticker";

      el.innerHTML = `
        <div class="mkStkHead">
          <div class="mkStkName">
            <div class="mkIconBox">${m.icon}</div>
            <div>
              ${m.name}
              <div class="mkKey">${r}</div>
            </div>
          </div>
          <div class="mkPriceTag">💸 Sell ${sp > 0 ? sp : "—"} EC</div>
        </div>

        <div class="mkBar"><div style="width:${Math.round(frac * 100)}%"></div></div>

        <div class="mkStkStats">
          <div class="mkStat">
            <div class="l">ON STOCK</div>
            <div class="v">${fmt(have)}</div>
          </div>
          <div class="mkStat">
            <div class="l">NPC BUY</div>
            <div class="v">${bp > 0 ? bp : "—"} EC</div>
          </div>
        </div>

        <div class="mkStkActions">
          <div>
            <div class="mkKey">Qty to sell</div>
            <input class="mkInput mkQty" type="number" min="1" step="1"
                   value="${Math.min(10, Math.floor(have))}"
                   data-sell-amt="${r}">
          </div>

          <button class="mkBtn mkBtn--primary"
                  data-sell-btn="${r}">
            Sell
          </button>
        </div>
      `;

      invGrid.appendChild(el);
    }

    // bind sell
    invGrid.querySelectorAll("[data-sell-btn]").forEach((btn) => {
      btn.addEventListener("click", () => openSellConfirm(btn));
    });
  }

  // ---------- SELL / BUY with Confirm modal ----------
  function openSellConfirm(btn) {
    const r = btn.getAttribute("data-sell-btn");
    const input = invGrid.querySelector(`[data-sell-amt="${CSS.escape(r)}"]`);

    let amt = Math.max(0, Number(input?.value || 0));
    const have = Number(INVENTORY[r] || 0);
    amt = clamp(Math.floor(amt), 0, have);

    if (!r || amt <= 0) return toast("Введи кількість > 0.", "err");

    const p = priceSell(r);
    const total = Math.round(p * amt);

    window.MarketUI?.openConfirm({
      title: "Confirm Sell",
      action: "Sell to NPC",
      res: resLabel(r),
      amt: fmt(amt),
      price: `${p} EC`,
      total: `${total} EC`,
      hint: "Продаж миттєвий: ресурс - зі складу, монети +.",
      onConfirm: async () => {
        clearToast();
        const res = await postJSON("/api/market/sell", {
          country_id: COUNTRY_ID,
          resource: r,
          amount: amt,
          qty: amt,
        });

        if (typeof res.coins === "number") pillCoins.textContent = `💰 ${res.coins} EC`;
        toast(`✅ Sold ${fmt(amt)} ${r} (+${res.sold?.coins_add ?? 0} EC)`, "ok");
        await loadInventory();
      },
    });
  }

  function openBuyConfirm() {
    const r = buyRes.value;
    let amt = Math.max(0, Number(buyAmt.value || 0));
    if (!r) return toast("Вибери ресурс.", "err");
    if (amt <= 0) return toast("Amount має бути > 0.", "err");

    amt = Math.floor(amt);

    const p = priceBuy(r);
    const total = Math.round(p * amt);

    window.MarketUI?.openConfirm({
      title: "Confirm Buy",
      action: "Buy from NPC",
      res: resLabel(r),
      amt: fmt(amt),
      price: `${p} EC`,
      total: `${total} EC`,
      hint: "Покупка миттєва: ресурс + у склад, монети -.",
      onConfirm: async () => {
        clearToast();
        const res = await postJSON("/api/market/buy", {
          country_id: COUNTRY_ID,
          resource: r,
          amount: amt,
          qty: amt,
        });

        if (typeof res.coins === "number") pillCoins.textContent = `💰 ${res.coins} EC`;
        toast(`✅ Bought ${fmt(amt)} ${r} (-${res.bought?.cost ?? 0} EC)`, "ok");
        await loadInventory();
      },
    });
  }

  // ---------- HARVEST ----------
  async function doHarvest() {
    btnHarvest.disabled = true;
    try {
      clearToast();
      const res = await postJSON(`/api/countries/${COUNTRY_ID}/harvest`, {});
      const gained = res.gained || {};

      const parts = Object.keys(gained)
        .sort((a, b) => (gained[b] || 0) - (gained[a] || 0))
        .slice(0, 12)
        .map((k) => `+${fmt(gained[k])} ${k}`);

      toast(
        parts.length
          ? `✅ HARVEST OK • nodes inside: ${res.nodes_inside || 0}\n${parts.join(", ")}`
          : `✅ HARVEST OK • nodes inside: ${res.nodes_inside || 0}\n(нічого не зібралося)`,
        "ok"
      );

      await loadInventory();
    } catch (e) {
      toast(e.message || "Harvest failed", "err");
    } finally {
      btnHarvest.disabled = false;
    }
  }

  // ---------- Init ----------
  async function init() {
    try {
      btnHarvest?.addEventListener("click", doHarvest);

      buyRes?.addEventListener("change", updateBuyInfo);
      buyAmt?.addEventListener("input", updateBuyInfo);
      btnBuy?.addEventListener("click", openBuyConfirm);

      await loadMe();
      await loadMyCountry();
      await loadPrices();
      await loadInventory();

    } catch (e) {
      toast(e.message || "Init error", "err");
      if (btnHarvest) btnHarvest.disabled = true;
      if (btnBuy) btnBuy.disabled = true;
    }
  }

  init();
})();