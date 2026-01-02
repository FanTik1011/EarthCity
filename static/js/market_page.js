// static/js/market_page.js
// NPC Market only (no P2P)
// - Country Stock (Sell) + NPC Buy + Harvest
// - Confirm modal via window.MarketUI.openConfirm()
// UI upgrades: search/sort, Max/All, affordability hints, loading states
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
  const invSearch = $("invSearch");
  const invSort = $("invSort");

  // NPC
  const buyRes = $("buyRes");
  const buyAmt = $("buyAmt");
  const buyInfo = $("buyInfo");
  const buyHint = $("buyHint");
  const btnBuy = $("btnBuy");
  const buyMinus = $("buyMinus");
  const buyPlus = $("buyPlus");
  const buyMax = $("buyMax");

  // ---------- Meta ----------
  const RESOURCE_META = {
    oil: { icon: "🛢️", name: "Oil" },
    gas: { icon: "🔥", name: "Gas" },
    iron: { icon: "⛏️", name: "Iron" },
    gold: { icon: "🪙", name: "Gold" },
    coal: { icon: "🪨", name: "Coal" },
    uranium: { icon: "☢️", name: "Uranium" },
    rare: { icon: "💎", name: "Rare Minerals" },
    water: { icon: "💧", name: "Water" },
    farmland: { icon: "🌾", name: "Farmland" },
    fish: { icon: "🐟", name: "Fish" },
    wind: { icon: "🌬️", name: "Wind Energy" },
    solar: { icon: "☀️", name: "Solar Energy" },
    hydro: { icon: "🌊", name: "Hydro Energy" },
    geo: { icon: "🌋", name: "Geothermal Energy" },
  };

  function meta(r) {
    return RESOURCE_META[r] || { icon: "✨", name: niceName(r) };
  }
  function niceName(r) {
    if (!r) return "Resource";
    const s = String(r).replace(/_/g, " ");
    return s.charAt(0).toUpperCase() + s.slice(1);
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

  let CURRENT_COINS = 0;

  // ---------- UI helpers ----------
  let toastTimer = null;

  function toast(text, kind = "info") {
    if (!msg) return;
    msg.style.display = "block";
    msg.classList.remove("ok", "err");
    if (kind === "ok") msg.classList.add("ok");
    if (kind === "err") msg.classList.add("err");
    msg.textContent = text || "";

    // auto-hide success/info after a bit (keep errors visible longer)
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      if (kind !== "err") clearToast();
    }, kind === "err" ? 8000 : 4500);
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

  function setBusy(el, busy, labelWhileBusy = "Working…") {
    if (!el) return;
    if (busy) {
      el.dataset._old = el.textContent;
      el.disabled = true;
      el.textContent = labelWhileBusy;
    } else {
      el.disabled = false;
      if (el.dataset._old) el.textContent = el.dataset._old;
      delete el.dataset._old;
    }
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

  // ---------- Me / country / inventory ----------
  async function loadMe() {
    const j = await getJSON("/api/me");
    ME = j;

    if (!ME?.authenticated) throw new Error("Please log in first.");

    pillUser.textContent = `👤 ${ME.username || "User"}`;
    CURRENT_COINS = Number(ME.coins ?? 0) || 0;
    pillCoins.textContent = `💰 ${CURRENT_COINS} EC`;

    if (ME.is_confirmed === false) {
      toast("Please confirm your email to use Harvest/Market.", "err");
    }
  }

  async function loadMyCountry() {
    const j = await getJSON("/api/my/country");
    MY_COUNTRY = j.data;

    if (!MY_COUNTRY) throw new Error("Create your country on the map first.");

    COUNTRY_ID = Number(MY_COUNTRY.properties?.id || MY_COUNTRY.id || 0);
    const nm = MY_COUNTRY.properties?.name || MY_COUNTRY.name || "My Country";

    countryLine.textContent = `Country: ${nm} • id=${COUNTRY_ID}`;
    if (!COUNTRY_ID) throw new Error("Country id not found.");
  }

  async function loadInventory() {
    const j = await getJSON(`/api/countries/${COUNTRY_ID}/inventory`);
    INVENTORY = j.data || {};
    renderInventory();
  }

  // ---------- Inventory render ----------
  function normalizedSearch(s) {
    return String(s || "").trim().toLowerCase();
  }

  function inventoryValue(r) {
    const have = Number(INVENTORY[r] || 0) || 0;
    const sp = priceSell(r) || 0;
    return have * sp;
  }

  function sortedResourcesFiltered() {
    const keysInv = Object.keys(INVENTORY || {});
    const all = new Set([...Object.keys(PRICES || {}), ...keysInv]);
    let list = Array.from(all);

    const q = normalizedSearch(invSearch?.value);
    if (q) {
      list = list.filter((r) => {
        const m = meta(r);
        return (
          r.toLowerCase().includes(q) ||
          m.name.toLowerCase().includes(q)
        );
      });
    }

    const mode = invSort?.value || "have_desc";

    list.sort((a, b) => {
      const ha = Number(INVENTORY[a] || 0) || 0;
      const hb = Number(INVENTORY[b] || 0) || 0;

      if (mode === "name_asc") {
        return meta(a).name.localeCompare(meta(b).name);
      }

      if (mode === "value_desc") {
        const va = inventoryValue(a);
        const vb = inventoryValue(b);
        if (vb !== va) return vb - va;
        if (hb !== ha) return hb - ha;
        return basePrice(b) - basePrice(a);
      }

      // have_desc default
      if (hb !== ha) return hb - ha;
      return basePrice(b) - basePrice(a);
    });

    return list;
  }

  function renderInventory() {
    const list = sortedResourcesFiltered();
    invGrid.innerHTML = "";

    const totalHave = Object.values(INVENTORY || {}).reduce((s, v) => s + (Number(v || 0) || 0), 0);

    // Empty state
    if (!Object.keys(INVENTORY || {}).length || totalHave <= 0) {
      invGrid.innerHTML = `
        <div class="mkSticker" style="grid-column:1/-1;">
          <div class="mkStkHead">
            <div class="mkStkName">
              <div class="mkIconBox">📦</div>
              <div>
                Stock is empty
                <div class="mkKey">Press Harvest to collect nodes</div>
              </div>
            </div>
            <div class="mkPriceTag">⛏️ Try Harvest</div>
          </div>
          <div class="mkNote" style="margin-top:10px;">
            If Harvest gives nothing, make sure resource nodes are inside your borders.
          </div>
        </div>
      `;
      return;
    }

    // If search filters everything out
    if (!list.length) {
      invGrid.innerHTML = `
        <div class="mkSticker" style="grid-column:1/-1;">
          <div class="mkStkHead">
            <div class="mkStkName">
              <div class="mkIconBox">🔎</div>
              <div>
                Nothing found
                <div class="mkKey">Try a different search query</div>
              </div>
            </div>
            <div class="mkPriceTag">Search</div>
          </div>
          <div class="mkNote" style="margin-top:10px;">
            Tip: search by key (iron) or by name (Oil).
          </div>
        </div>
      `;
      return;
    }

    // For progress bars
    let mx = 1;
    for (const r of Object.keys(INVENTORY || {})) mx = Math.max(mx, Number(INVENTORY[r] || 0) || 0);
    mx = Math.max(mx, 1);

    for (const r of list) {
      const have = Number(INVENTORY[r] || 0) || 0;
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
            <div class="mkKey">Amount to sell</div>
            <input class="mkInput mkQty" type="number" min="1" step="1"
                   value="${Math.min(10, Math.floor(have))}"
                   data-sell-amt="${escapeAttr(r)}">
            <div class="mkSmallRow">
              <button class="mkPillBtn" type="button" data-sell-max="${escapeAttr(r)}">Max</button>
              <button class="mkPillBtn" type="button" data-sell-all="${escapeAttr(r)}">All</button>
            </div>
          </div>

          <button class="mkBtn mkBtn--primary"
                  data-sell-btn="${escapeAttr(r)}">
            Sell
          </button>
        </div>
      `;

      invGrid.appendChild(el);
    }

    // bind sell buttons
    invGrid.querySelectorAll("[data-sell-btn]").forEach((btn) => {
      btn.addEventListener("click", () => openSellConfirm(btn));
    });

    // bind Max/All quick buttons
    invGrid.querySelectorAll("[data-sell-max]").forEach((b) => {
      b.addEventListener("click", () => {
        const r = b.getAttribute("data-sell-max");
        const input = invGrid.querySelector(`[data-sell-amt="${CSS.escape(r)}"]`);
        const have = Number(INVENTORY[r] || 0) || 0;
        if (input) input.value = Math.max(1, Math.floor(have));
      });
    });
    invGrid.querySelectorAll("[data-sell-all]").forEach((b) => {
      b.addEventListener("click", () => {
        const r = b.getAttribute("data-sell-all");
        const input = invGrid.querySelector(`[data-sell-amt="${CSS.escape(r)}"]`);
        const have = Number(INVENTORY[r] || 0) || 0;
        if (input) input.value = Math.max(1, Math.floor(have));
      });
    });
  }

  function escapeAttr(s) {
    return String(s || "").replace(/"/g, "&quot;");
  }

  // ---------- BUY info + affordability ----------
  function updateBuyInfo() {
    if (!buyRes) return;
    const r = buyRes.value;
    let amt = Math.max(1, Number(buyAmt?.value || 1));
    amt = Math.floor(amt);

    const p = priceBuy(r);
    const total = Math.round(p * amt);

    const canAfford = p > 0 ? Math.floor(CURRENT_COINS / p) : 0;
    const ok = total <= CURRENT_COINS;

    buyInfo.textContent =
      `Unit price: ${p || "—"} EC • Total: ${isFinite(total) ? total : "—"} EC • You can afford: ${fmt(canAfford)}`;

    if (buyHint) {
      buyHint.textContent = ok
        ? "Looks good. Press Buy to confirm."
        : "Not enough coins for this amount — try Max or lower the amount.";
    }

    // UI warning (still allow click; backend will validate too)
    if (btnBuy) btnBuy.disabled = !r || amt <= 0 || p <= 0;
  }

  function setBuyAmount(v) {
    const x = Math.max(1, Math.floor(Number(v || 1)));
    if (buyAmt) buyAmt.value = String(x);
    updateBuyInfo();
  }

  function maxAffordableAmount() {
    const r = buyRes.value;
    const p = priceBuy(r);
    if (!p || p <= 0) return 1;
    return Math.max(1, Math.floor(CURRENT_COINS / p));
  }

  // ---------- SELL / BUY with Confirm modal ----------
  function openSellConfirm(btn) {
    const r = btn.getAttribute("data-sell-btn");
    const input = invGrid.querySelector(`[data-sell-amt="${CSS.escape(r)}"]`);

    let amt = Math.max(0, Number(input?.value || 0));
    const have = Number(INVENTORY[r] || 0) || 0;
    amt = clamp(Math.floor(amt), 0, have);

    if (!r || amt <= 0) return toast("Enter an amount greater than 0.", "err");

    const p = priceSell(r);
    const total = Math.round(p * amt);

    window.MarketUI?.openConfirm({
      title: "Confirm Sell",
      action: "Sell to NPC (instant)",
      res: resLabel(r),
      amt: fmt(amt),
      price: `${p} EC`,
      total: `${total} EC`,
      hint: "Instant trade: stock decreases, coins increase.",
      onConfirm: async () => {
        clearToast();
        setBusy(btn, true, "Selling…");

        try {
          const res = await postJSON("/api/market/sell", {
            country_id: COUNTRY_ID,
            resource: r,
            amount: amt,
            qty: amt,
          });

          if (typeof res.coins === "number") {
            CURRENT_COINS = res.coins;
            pillCoins.textContent = `💰 ${CURRENT_COINS} EC`;
          }

          toast(`✅ Sold ${fmt(amt)} ${r} (+${res.sold?.coins_add ?? 0} EC)`, "ok");
          await loadInventory();
          updateBuyInfo();
        } finally {
          setBusy(btn, false);
        }
      },
    });
  }

  function openBuyConfirm() {
    const r = buyRes.value;
    let amt = Math.max(1, Number(buyAmt.value || 1));
    if (!r) return toast("Select a resource.", "err");
    if (amt <= 0) return toast("Amount must be > 0.", "err");

    amt = Math.floor(amt);

    const p = priceBuy(r);
    const total = Math.round(p * amt);

    window.MarketUI?.openConfirm({
      title: "Confirm Buy",
      action: "Buy from NPC (instant)",
      res: resLabel(r),
      amt: fmt(amt),
      price: `${p} EC`,
      total: `${total} EC`,
      hint: "Instant trade: coins decrease, stock increases.",
      onConfirm: async () => {
        clearToast();
        setBusy(btnBuy, true, "Buying…");

        try {
          const res = await postJSON("/api/market/buy", {
            country_id: COUNTRY_ID,
            resource: r,
            amount: amt,
            qty: amt,
          });

          if (typeof res.coins === "number") {
            CURRENT_COINS = res.coins;
            pillCoins.textContent = `💰 ${CURRENT_COINS} EC`;
          }

          toast(`✅ Bought ${fmt(amt)} ${r} (-${res.bought?.cost ?? 0} EC)`, "ok");
          await loadInventory();
          updateBuyInfo();
        } finally {
          setBusy(btnBuy, false);
        }
      },
    });
  }

  // ---------- HARVEST ----------
  async function doHarvest() {
    setBusy(btnHarvest, true, "Harvesting…");
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
          ? `✅ Harvest complete • Nodes inside: ${res.nodes_inside || 0}\n${parts.join(", ")}`
          : `✅ Harvest complete • Nodes inside: ${res.nodes_inside || 0}\n(No resources collected)`,
        "ok"
      );

      await loadInventory();
      updateBuyInfo();
    } catch (e) {
      toast(e.message || "Harvest failed", "err");
    } finally {
      setBusy(btnHarvest, false);
    }
  }

  // ---------- Init ----------
  async function init() {
    try {
      btnHarvest?.addEventListener("click", doHarvest);

      buyRes?.addEventListener("change", updateBuyInfo);
      buyAmt?.addEventListener("input", updateBuyInfo);
      btnBuy?.addEventListener("click", openBuyConfirm);

      buyMinus?.addEventListener("click", () => setBuyAmount((Number(buyAmt.value || 1) || 1) - 1));
      buyPlus?.addEventListener("click", () => setBuyAmount((Number(buyAmt.value || 1) || 1) + 1));
      buyMax?.addEventListener("click", () => setBuyAmount(maxAffordableAmount()));

      invSearch?.addEventListener("input", () => renderInventory());
      invSort?.addEventListener("change", () => renderInventory());

      toast("Loading market…", "info");

      await loadMe();
      await loadMyCountry();
      await loadPrices();
      await loadInventory();

      clearToast();
    } catch (e) {
      toast(e.message || "Init error", "err");
      if (btnHarvest) btnHarvest.disabled = true;
      if (btnBuy) btnBuy.disabled = true;
    }
  }

  init();
})();
