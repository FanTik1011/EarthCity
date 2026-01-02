// static/js/auth.js
// EarthCity — Auth UI + "Hide Create Country if user already has a country"
// ✅ No backend changes required. Uses safe multi-endpoint detection.

document.addEventListener("DOMContentLoaded", () => {
  const $ = (id) => document.getElementById(id);

  const overlay = $("overlay");
  const tabLogin = $("tabLogin");
  const tabRegister = $("tabRegister");

  const panelLogin = $("panelLogin");
  const panelRegister = $("panelRegister");
  const panelUnconfirmed = $("panelUnconfirmed");

  const msg = $("msg");
  const devLink = $("devLink");

  const btnLogin = $("btnLogin");
  const btnRegister = $("btnRegister");
  const btnResend = $("btnResend");
  const btnLogout = $("btnLogout");

  const userLabel = $("userLabel");

  // Country create UI (only UI toggles — logic remains in map.js)
  const btnCreateCountry = $("btnCreateCountry");
  const buildbarNote = $("buildbarNote");

  // fields
  const loginEmail = $("loginEmail");
  const loginPassword = $("loginPassword");
  const regUsername = $("regUsername");
  const regEmail = $("regEmail");
  const regPassword = $("regPassword");

  // ---- Helpers ----
  function show(el, on = true) {
    if (!el) return;
    el.style.display = on ? "" : "none";
  }

  function setOverlayVisible(on) {
    if (!overlay) return;
    overlay.setAttribute("aria-hidden", on ? "false" : "true");
    // CSS overlay uses pointer-events:none by default; we only show/hide visually
    overlay.style.display = on ? "flex" : "none";
  }

  function setMsg(text, tone = "info") {
    if (!msg) return;
    msg.textContent = text;
    msg.style.display = "block";

    // small tone styling (no CSS dependency)
    if (tone === "ok") {
      msg.style.borderColor = "rgba(34,197,94,.35)";
      msg.style.background = "rgba(34,197,94,.10)";
    } else if (tone === "warn") {
      msg.style.borderColor = "rgba(245,158,11,.40)";
      msg.style.background = "rgba(245,158,11,.10)";
    } else if (tone === "err") {
      msg.style.borderColor = "rgba(239,68,68,.40)";
      msg.style.background = "rgba(239,68,68,.10)";
    } else {
      msg.style.borderColor = "rgba(255,255,255,.16)";
      msg.style.background = "rgba(0,0,0,.22)";
    }
  }

  function clearMsg() {
    if (!msg) return;
    msg.style.display = "none";
    msg.textContent = "";
  }

  async function safeJson(res) {
    try { return await res.json(); } catch { return null; }
  }

  async function getMe() {
    const res = await fetch("/api/me", { credentials: "same-origin" });
    const data = await safeJson(res);
    return data || { authenticated: false };
  }

  async function detectHasCountry(me) {
    // 1) if backend already gives it in /api/me
    if (me && me.authenticated) {
      if (me.has_country === true) return true;
      if (me.country_id) return true;
      if (me.country && (me.country.id || me.country.name)) return true;
    }

    // 2) try common endpoints (NO backend change; just probing)
    const candidates = [
      "/api/countries/mine",
      "/api/countries/my",
      "/api/countries/me",
    ];

    for (const url of candidates) {
      try {
        const r = await fetch(url, { credentials: "same-origin" });
        if (!r.ok) continue;
        const j = await safeJson(r);
        if (!j) continue;

        // Accept either {id,...} or {country:{id}} or {items:[...]}
        if (j.id) return true;
        if (j.country && (j.country.id || j.country.name)) return true;
        if (Array.isArray(j.items) && j.items.length > 0) return true;
        if (Array.isArray(j) && j.length > 0) return true;
      } catch {}
    }

    return false;
  }

  async function applyCountryCreateVisibility(me) {
    const authed = !!(me && me.authenticated);
    if (!authed) {
      // guest: show create button (or keep your intended UX)
      show(btnCreateCountry, true);
      show(buildbarNote, false);
      return;
    }

    const hasCountry = await detectHasCountry(me);

    // ✅ Requirement: if user has a country -> button must not appear
    show(btnCreateCountry, !hasCountry);
    show(buildbarNote, hasCountry);
  }

  function setTab(which) {
    const isLogin = which === "login";
    tabLogin?.classList.toggle("active", isLogin);
    tabRegister?.classList.toggle("active", !isLogin);
    show(panelLogin, isLogin);
    show(panelRegister, !isLogin);
    show(panelUnconfirmed, false);
    clearMsg();
  }

  // ---- Auth actions ----
  async function doLogin() {
    clearMsg();
    const email = (loginEmail?.value || "").trim();
    const password = (loginPassword?.value || "").trim();

    if (!email || !password) {
      setMsg("Please enter email and password.", "warn");
      return;
    }

    try {
      const res = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ email, password })
      });

      const data = await safeJson(res);

      if (res.ok) {
        setMsg("Logged in успешно. Loading…", "ok");
        await refreshAuthUI();
        return;
      }

      // common pattern: unconfirmed email
      if (res.status === 403 && data && (data.reason === "unconfirmed" || data.code === "UNCONFIRMED")) {
        show(panelLogin, false);
        show(panelRegister, false);
        show(panelUnconfirmed, true);
        setMsg("Please confirm your email first.", "warn");
        return;
      }

      setMsg((data && (data.error || data.message)) || "Login failed.", "err");
    } catch (e) {
      setMsg("Network error while logging in.", "err");
    }
  }

  async function doRegister() {
    clearMsg();
    const username = (regUsername?.value || "").trim();
    const email = (regEmail?.value || "").trim();
    const password = (regPassword?.value || "").trim();

    if (!username || !email || !password) {
      setMsg("Please fill all fields.", "warn");
      return;
    }

    try {
      const res = await fetch("/api/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ username, email, password })
      });

      const data = await safeJson(res);

      if (res.ok) {
        setMsg("Account created. Check your email to confirm (Inbox/Spam).", "ok");
        show(panelLogin, false);
        show(panelRegister, false);
        show(panelUnconfirmed, true);
        return;
      }

      setMsg((data && (data.error || data.message)) || "Register failed.", "err");
    } catch (e) {
      setMsg("Network error while registering.", "err");
    }
  }

  async function doResend() {
    clearMsg();
    try {
      const res = await fetch("/api/resend-confirmation", {
        method: "POST",
        credentials: "same-origin"
      });
      const data = await safeJson(res);

      if (res.ok) {
        setMsg("Confirmation email resent. Check Inbox/Spam.", "ok");
        if (data && data.dev_link && devLink) {
          devLink.style.display = "block";
          devLink.textContent = data.dev_link;
        }
        return;
      }

      setMsg((data && (data.error || data.message)) || "Resend failed.", "err");
    } catch {
      setMsg("Network error while resending.", "err");
    }
  }

  async function doLogout() {
    clearMsg();
    try {
      await fetch("/api/logout", { method: "POST", credentials: "same-origin" }).catch(() => null);
      await refreshAuthUI();
    } catch {
      await refreshAuthUI();
    }
  }

  // ---- UI refresh ----
  async function refreshAuthUI() {
    const me = await getMe().catch(() => ({ authenticated: false }));
    const authed = !!(me && me.authenticated);

    // show/hide overlay
    setOverlayVisible(!authed);

    // logout button
    show(btnLogout, authed);

    // label
    if (userLabel) userLabel.textContent = authed ? (me.username || "User") : "Guest";

    // ✅ apply Create Country visibility rule
    await applyCountryCreateVisibility(me);

    return me;
  }

  // ---- Events ----
  tabLogin?.addEventListener("click", () => setTab("login"));
  tabRegister?.addEventListener("click", () => setTab("register"));

  btnLogin?.addEventListener("click", doLogin);
  btnRegister?.addEventListener("click", doRegister);
  btnResend?.addEventListener("click", doResend);
  btnLogout?.addEventListener("click", doLogout);

  // Enter key
  [loginEmail, loginPassword].forEach((el) => el?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") doLogin();
  }));
  [regUsername, regEmail, regPassword].forEach((el) => el?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") doRegister();
  }));

  // extra close button in factory sidebar (if you have duplicated id, we used fbClose2 in HTML)
  $("fbClose2")?.addEventListener("click", () => $("fbClose")?.click?.());

  // ---- Init ----
  setTab("login");
  refreshAuthUI();

  // Optional: re-check periodically (if user creates country during session)
  setInterval(() => {
    refreshAuthUI().catch(() => null);
  }, 15000);
});
