// static/js/auth.js
document.addEventListener("DOMContentLoaded", () => {
  const $ = (id) => document.getElementById(id);

  // overlay + tabs
  const overlay = $("overlay");
  const tabLogin = $("tabLogin");
  const tabRegister = $("tabRegister");

  const panelLogin = $("panelLogin");
  const panelRegister = $("panelRegister");
  const panelUnconfirmed = $("panelUnconfirmed");

  // msg + dev link
  const msg = $("msg");
  const devLink = $("devLink");

  // inputs
  const loginEmail = $("loginEmail");
  const loginPassword = $("loginPassword");
  const regUsername = $("regUsername");
  const regEmail = $("regEmail");
  const regPassword = $("regPassword");

  // buttons
  const btnLogin = $("btnLogin");
  const btnRegister = $("btnRegister");
  const btnResend = $("btnResend");
  const btnLogout = $("btnLogout");
  const btnGoogle = $("btnGoogle");

  // hud
  const userLabel = $("userLabel");

  let confirmPollTimer = null;

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  function show(el, on = true) {
    if (!el) return;
    el.style.display = on ? "" : "none";
  }

  function setOverlayOpen(open) {
    if (!overlay) return;
    overlay.style.display = open ? "" : "none";
    overlay.setAttribute("aria-hidden", open ? "false" : "true");
  }

  function setMsg(text, kind = "info") {
    if (!msg) return;
    if (!text) {
      msg.style.display = "none";
      msg.textContent = "";
      msg.classList.remove("ok", "err");
      return;
    }
    msg.style.display = "";
    msg.textContent = text;
    msg.classList.remove("ok", "err");
    if (kind === "ok") msg.classList.add("ok");
    if (kind === "err") msg.classList.add("err");
  }

  function setDevLink(url) {
    if (!devLink) return;
    if (!url) {
      devLink.style.display = "none";
      devLink.innerHTML = "";
      return;
    }
    devLink.style.display = "";
    devLink.innerHTML = `Dev link: <a href="${url}" target="_blank" rel="noreferrer noopener">${url}</a>`;
  }

  function selectTab(which) {
    const isLogin = which === "login";

    tabLogin?.classList.toggle("active", isLogin);
    tabRegister?.classList.toggle("active", !isLogin);

    show(panelLogin, isLogin);
    show(panelRegister, !isLogin);
    show(panelUnconfirmed, false);

    setMsg("");
    setDevLink(null);
  }

  function stopConfirmPolling() {
    if (confirmPollTimer) {
      clearInterval(confirmPollTimer);
      confirmPollTimer = null;
    }
  }

  async function getMe() {
    const res = await fetch("/api/me", { credentials: "include" });
    return await res.json();
  }

  function applyMeToUI(me) {
    const authed = !!me?.authenticated;

    if (btnLogout) btnLogout.style.display = authed ? "" : "none";
    if (userLabel) userLabel.textContent = authed ? (me.username || "User") : "Guest";

    // call coin updater if page provided it
    if (typeof window.updateCoins === "function") {
      window.updateCoins();
    }
  }

  async function refreshAuthState({ openOverlayIfGuest = true } = {}) {
    const me = await getMe().catch(() => null);
    if (!me) return;

    applyMeToUI(me);

    if (!me.authenticated) {
      stopConfirmPolling();
      if (openOverlayIfGuest) {
        selectTab("login");
        setOverlayOpen(true);
      }
      return;
    }

    // authenticated
    if (me.is_blocked) {
      setOverlayOpen(true);
      selectTab("login");
      setMsg("Акаунт заблоковано адміністратором.", "err");
      return;
    }

    if (!me.is_confirmed) {
      // show unconfirmed panel
      setOverlayOpen(true);
      show(panelLogin, false);
      show(panelRegister, false);
      show(panelUnconfirmed, true);
      setMsg("Підтверди email, щоб будувати країни та фабрики.", "err");
      startConfirmPolling();
      return;
    }

    // confirmed authed: close overlay
    setOverlayOpen(false);
    stopConfirmPolling();
  }

  function startConfirmPolling() {
    stopConfirmPolling();
    confirmPollTimer = setInterval(async () => {
      const me = await getMe().catch(() => null);
      if (!me) return;

      applyMeToUI(me);

      if (!me.authenticated) {
        stopConfirmPolling();
        return;
      }
      if (me.is_blocked) {
        stopConfirmPolling();
        setMsg("Акаунт заблоковано адміністратором.", "err");
        return;
      }
      if (me.is_confirmed) {
        stopConfirmPolling();
        setMsg("✅ Email підтверджено! Можеш грати.", "ok");
        await sleep(600);
        setOverlayOpen(false);
      }
    }, 3000);
  }

  async function postJSON(url, body) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify(body || {}),
    });

    let data = null;
    try { data = await res.json(); } catch (e) {}
    return { ok: res.ok, status: res.status, data };
  }

  // -------- Events --------

  tabLogin?.addEventListener("click", () => selectTab("login"));
  tabRegister?.addEventListener("click", () => selectTab("register"));

  btnLogin?.addEventListener("click", async () => {
    setMsg("");
    setDevLink(null);

    const email = (loginEmail?.value || "").trim().toLowerCase();
    const password = loginPassword?.value || "";

    if (!email || !email.includes("@")) return setMsg("Введи коректний email.", "err");
    if (!password || password.length < 6) return setMsg("Пароль мінімум 6 символів.", "err");

    btnLogin.disabled = true;
    try {
      const r = await postJSON("/api/login", { email, password });

      if (!r.ok || !r.data?.ok) {
        const err = r.data?.error || "Login failed.";
        setMsg(err, "err");
        return;
      }

      await refreshAuthState({ openOverlayIfGuest: false });
    } finally {
      btnLogin.disabled = false;
    }
  });

  btnRegister?.addEventListener("click", async () => {
    setMsg("");
    setDevLink(null);

    const username = (regUsername?.value || "").trim();
    const email = (regEmail?.value || "").trim().toLowerCase();
    const password = regPassword?.value || "";

    if (username.length < 3) return setMsg("Username мінімум 3 символи.", "err");
    if (!email || !email.includes("@") || !email.includes(".")) return setMsg("Некоректний email.", "err");
    if (password.length < 6) return setMsg("Пароль мінімум 6 символів.", "err");

    btnRegister.disabled = true;
    try {
      const r = await postJSON("/api/register", { username, email, password });

      if (!r.ok || !r.data?.ok) {
        const err = r.data?.error || "Register failed.";
        setMsg(err, "err");
        return;
      }

      // show unconfirmed panel right away
      show(panelLogin, false);
      show(panelRegister, false);
      show(panelUnconfirmed, true);

      setMsg("✅ Зареєстровано! Тепер підтверди email (Inbox/Spam).", "ok");
      setDevLink(r.data?.dev_link || null);
      startConfirmPolling();

      // update HUD
      await refreshAuthState({ openOverlayIfGuest: false });
    } finally {
      btnRegister.disabled = false;
    }
  });

  btnResend?.addEventListener("click", async () => {
    setMsg("");
    setDevLink(null);

    btnResend.disabled = true;
    try {
      const res = await fetch("/api/resend-confirmation", {
        method: "POST",
        credentials: "include",
      });

      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data.ok) {
        setMsg(data.error || "Не вдалося надіслати лист.", "err");
        return;
      }

      setMsg("📩 Лист відправлено ще раз. Перевір Inbox/Spam.", "ok");
      setDevLink(data.dev_link || null);
    } finally {
      btnResend.disabled = false;
    }
  });

  btnLogout?.addEventListener("click", async () => {
    setMsg("");
    setDevLink(null);

    btnLogout.disabled = true;
    try {
      await fetch("/api/logout", { method: "POST", credentials: "include" });
      stopConfirmPolling();
      await refreshAuthState({ openOverlayIfGuest: true });
    } finally {
      btnLogout.disabled = false;
    }
  });

  btnGoogle?.addEventListener("click", () => {
    // return back here after OAuth
    const next = encodeURIComponent(window.location.pathname + window.location.search);
    window.location.href = "/auth/google?next=" + next;
  });

  // show useful messages from URL (?blocked=1 / ?google_error=1)
  function handleUrlFlags() {
    const p = new URLSearchParams(window.location.search);
    if (p.get("blocked") === "1") {
      setOverlayOpen(true);
      selectTab("login");
      setMsg("Акаунт заблоковано адміністратором.", "err");
    }
    if (p.get("google_error")) {
      setOverlayOpen(true);
      selectTab("login");
      setMsg("Google-вхід не вдався. Перевір налаштування Redirect URI.", "err");
    }
  }

  // initial
  handleUrlFlags();
  refreshAuthState({ openOverlayIfGuest: true });
});
