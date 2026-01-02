document.addEventListener("DOMContentLoaded", () => {
  const $ = (id) => document.getElementById(id);

  // ----- UI refs (must exist) -----
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

  const langUK = $("langUK");
  const langEN = $("langEN");

  // Optional labels that exist in your layout
  const modeLabel = $("modeLabel");
  const buildHint = $("buildHint");

  // ----- i18n -----
  const I18N = {
    uk: {
      earlyAccess: "РАННІЙ ДОСТУП",
      subtitle: "Створюй королівства • збирай ресурси • будуй економіку",
      vault: "Скарбниця",
      factories: "Фабрики",
      claimRealm: "Створити країну",
      expand: "Розширити",
      market: "Маркет",
      logout: "Вийти",
      mode: "Режим",
      hintExplore: "Досліджуй планету. Наблизься, щоб бачити ресурси.",
      undo: "Назад",
      cancel: "Скасувати",
      finish: "Готово",
      factoryBay: "Фабричний відсік",
      factorySub: "Вибери схему і постав на своїй території",
      blueprints: "Схеми",
      beta: "BETA",
      selected: "Обране",
      noneSelected: "Нічого не вибрано",
      placeMode: "Режим встановлення",
      exit: "Вийти",
      tip: "Порада:",
      myFactories: "Мої фабрики",
      countrySub: "Вибери країну, щоб подивитися деталі",
      territory: "Територія",
      ruler: "Правитель",
      realmId: "ID країни",
      quickActions: "Швидкі дії",
      focus: "Фокус",
      openFactoryBay: "Відкрити фабрики",
      betaNote: "Механіки, ціни та вигляд можуть змінюватися.",
      coordinates: "Координати",
      pilot: "Гравець",
      hudLine1: "Drag — обертання • Wheel/Pinch — zoom • Shift+Drag — нахил",
      hudLine2: "Створити країну: постав точки → Завершити",
      hudBeta: "EarthCity Beta — ранній доступ.",
      signIn: "Вхід",
      join: "Реєстрація",
      google: "Увійти через Google",
      email: "Email",
      password: "Пароль",
      launch: "Увійти",
      betaFoot: "Продовжуючи, ти підтверджуєш, що це Beta-версія.",
      username: "Username",
      createPilot: "Створити акаунт",
      confirmNote: "Після реєстрації підтверди email, щоб відкрити гру.",
      notConfirmed: "Email ще не підтверджено. Перевір Inbox/Spam.",
      resend: "Надіслати ще раз",
      spamNote: "Якщо не приходить — перевір спам або спробуй інший email.",
      claimTitle: "Створи свою країну",
      claimSub: "Назва + колір → збережеться у світі (Beta)",
      realmName: "Назва країни",
      realmColor: "Колір країни",
      claimCost: "Вартість",
      yourVault: "Твоя скарбниця",
      finalize: "Зберегти",
      close: "Закрити",

      errors: {
        fillAll: "Заповни всі поля.",
        badEmail: "Некоректний email.",
        shortPass: "Пароль має бути мінімум 6 символів.",
        usernameRule: "Username: 3-20 символів, латиниця/цифри/_",
        loginFirst: "Спершу увійди.",
        unknown: "Щось пішло не так. Спробуй ще раз."
      },
      ok: {
        sent: "Лист відправлено. Перевір пошту.",
        loggedIn: "Успішний вхід."
      }
    },

    en: {
      earlyAccess: "EARLY ACCESS",
      subtitle: "Forge realms • harvest resources • build an economy",
      vault: "Vault",
      factories: "Factories",
      claimRealm: "Claim Realm",
      expand: "Expand",
      market: "Market",
      logout: "Logout",
      mode: "Mode",
      hintExplore: "Explore the planet. Zoom in to see resources.",
      undo: "Undo",
      cancel: "Cancel",
      finish: "Finish",
      factoryBay: "Factory Bay",
      factorySub: "Pick a blueprint and place it on your territory",
      blueprints: "Blueprints",
      beta: "BETA",
      selected: "Selected",
      noneSelected: "Nothing selected",
      placeMode: "Place mode",
      exit: "Exit",
      tip: "Tip:",
      myFactories: "My factories",
      countrySub: "Select a realm to see details",
      territory: "Territory",
      ruler: "Ruler",
      realmId: "Realm ID",
      quickActions: "Quick actions",
      focus: "Focus",
      openFactoryBay: "Open Factory Bay",
      betaNote: "Gameplay, costs and visuals may change at any time.",
      coordinates: "Coordinates",
      pilot: "Pilot",
      hudLine1: "Drag — rotate • Wheel/Pinch — zoom • Shift+Drag — tilt",
      hudLine2: "Claim Realm: click points → Finish",
      hudBeta: "EarthCity Beta — early access build.",
      signIn: "Sign in",
      join: "Join",
      google: "Warp in with Google",
      email: "Email",
      password: "Password",
      launch: "Launch Session",
      betaFoot: "By continuing, you acknowledge this is a Beta version.",
      username: "Username",
      createPilot: "Create Pilot ID",
      confirmNote: "After joining, confirm email to unlock the game.",
      notConfirmed: "Email not confirmed yet. Check Inbox/Spam.",
      resend: "Resend Beacon",
      spamNote: "Still nothing? Check spam or try another email.",
      claimTitle: "Claim your realm",
      claimSub: "Name + color → saved into the world (Beta)",
      realmName: "Realm name",
      realmColor: "Realm color",
      claimCost: "Claim cost",
      yourVault: "Your vault",
      finalize: "Finalize",
      close: "Close",

      errors: {
        fillAll: "Please fill all fields.",
        badEmail: "Invalid email.",
        shortPass: "Password must be at least 6 characters.",
        usernameRule: "Username: 3-20 chars, latin/numbers/_",
        loginFirst: "Login first.",
        unknown: "Something went wrong. Try again."
      },
      ok: {
        sent: "Email sent. Check your inbox.",
        loggedIn: "Logged in successfully."
      }
    }
  };

  let LANG = localStorage.getItem("ec_lang") || "uk";

  function t(key) {
    const pack = I18N[LANG] || I18N.uk;
    return key.split(".").reduce((acc, k) => (acc && acc[k] != null ? acc[k] : null), pack) ?? key;
  }

  function applyLang(newLang) {
    LANG = newLang;
    localStorage.setItem("ec_lang", LANG);

    document.documentElement.lang = (LANG === "uk" ? "uk" : "en");

    document.querySelectorAll("[data-i18n]").forEach((el) => {
      const k = el.getAttribute("data-i18n");
      el.textContent = t(k);
    });

    if (langUK) langUK.classList.toggle("active", LANG === "uk");
    if (langEN) langEN.classList.toggle("active", LANG === "en");
  }

  if (langUK) langUK.addEventListener("click", () => applyLang("uk"));
  if (langEN) langEN.addEventListener("click", () => applyLang("en"));
  applyLang(LANG);

  // ----- helpers -----
  function showMsg(text, kind = "info") {
    if (!msg) return;
    msg.style.display = "block";
    msg.textContent = text;
    msg.style.borderColor =
      kind === "warn" ? "rgba(245,158,11,.35)" :
      kind === "ok" ? "rgba(34,197,94,.35)" :
      "rgba(255,255,255,.14)";
  }
  function hideMsg() {
    if (!msg) return;
    msg.style.display = "none";
    msg.textContent = "";
  }

  function showPanel(which) {
    if (panelLogin) panelLogin.style.display = (which === "login") ? "" : "none";
    if (panelRegister) panelRegister.style.display = (which === "register") ? "" : "none";
    if (panelUnconfirmed) panelUnconfirmed.style.display = (which === "unconfirmed") ? "" : "none";

    if (tabLogin) tabLogin.classList.toggle("active", which === "login");
    if (tabRegister) tabRegister.classList.toggle("active", which === "register");
  }

  function setOverlay(open) {
    if (!overlay) return;
    overlay.style.display = open ? "flex" : "none";
    overlay.setAttribute("aria-hidden", open ? "false" : "true");
  }

  async function apiJSON(url, data) {
    const res = await fetch(url, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data || {})
    });
    const j = await res.json().catch(() => ({}));
    return { res, j };
  }

  async function getMe() {
    const r = await fetch("/api/me", { credentials: "include" });
    const j = await r.json().catch(() => ({}));
    return j || { authenticated: false };
  }

  function isConfirmed(me) {
    // supports different backend shapes: confirmed / email_confirmed / needs_confirmation
    if (me == null) return false;
    if (typeof me.confirmed === "boolean") return me.confirmed;
    if (typeof me.email_confirmed === "boolean") return me.email_confirmed;
    if (typeof me.needs_confirmation === "boolean") return !me.needs_confirmation;
    // if backend doesn't have field – assume confirmed when authenticated
    return !!me.authenticated;
  }

  function updateHeader(me) {
    const coins = (me && typeof me.coins === "number") ? me.coins : 0;
    const pretty = coins.toLocaleString("en-US") + " EC";

    const topCoins = document.getElementById("topCoins");
    const myCoins = document.getElementById("myCoins");
    const myCoinsModal = document.getElementById("myCoinsModal");

    if (topCoins) topCoins.textContent = pretty;
    if (myCoins) myCoins.textContent = "💰 " + pretty;
    if (myCoinsModal) myCoinsModal.textContent = pretty;

    if (userLabel) {
      userLabel.textContent = me && me.authenticated
        ? ((me.username || "Pilot") + " • " + pretty)
        : "Guest";
    }

    // show logout only if logged in
    if (btnLogout) btnLogout.style.display = (me && me.authenticated) ? "" : "none";
  }

  // ----- confirmation polling -----
  let confirmPollTimer = null;
  function stopConfirmPolling() {
    if (confirmPollTimer) clearInterval(confirmPollTimer);
    confirmPollTimer = null;
  }
  function startConfirmPolling() {
    stopConfirmPolling();
    confirmPollTimer = setInterval(async () => {
      const me = await getMe().catch(() => null);
      if (!me) return;

      updateHeader(me);

      if (!me.authenticated) {
        stopConfirmPolling();
        setOverlay(true);
        showPanel("login");
        return;
      }

      if (isConfirmed(me)) {
        stopConfirmPolling();
        setOverlay(false);
      } else {
        setOverlay(true);
        showPanel("unconfirmed");
      }
    }, 2500);
  }

  // ----- tabs -----
  if (tabLogin) tabLogin.addEventListener("click", () => { hideMsg(); showPanel("login"); });
  if (tabRegister) tabRegister.addEventListener("click", () => { hideMsg(); showPanel("register"); });

  // ----- actions -----
  if (btnLogin) {
    btnLogin.addEventListener("click", async () => {
      hideMsg();
      const email = ($("loginEmail")?.value || "").trim();
      const password = ($("loginPassword")?.value || "");

      if (!email || !password) return showMsg(t("errors.fillAll"), "warn");
      if (!email.includes("@")) return showMsg(t("errors.badEmail"), "warn");

      const { res, j } = await apiJSON("/api/login", { email, password }).catch(() => ({ res:null, j:{} }));
      if (!res) return showMsg(t("errors.unknown"), "warn");

      if (j.ok) {
        const me = await getMe().catch(() => ({ authenticated: true }));
        updateHeader(me);

        if (me.authenticated && !isConfirmed(me)) {
          setOverlay(true);
          showPanel("unconfirmed");
          startConfirmPolling();
          return;
        }

        showMsg(t("ok.loggedIn"), "ok");
        setOverlay(false);
        stopConfirmPolling();
      } else {
        showMsg(j.error || j.message || t("errors.unknown"), "warn");
      }
    });
  }

  if (btnRegister) {
    btnRegister.addEventListener("click", async () => {
      hideMsg();
      const username = ($("regUsername")?.value || "").trim();
      const email = ($("regEmail")?.value || "").trim();
      const password = ($("regPassword")?.value || "");

      if (!username || !email || !password) return showMsg(t("errors.fillAll"), "warn");
      if (!email.includes("@")) return showMsg(t("errors.badEmail"), "warn");
      if (password.length < 6) return showMsg(t("errors.shortPass"), "warn");
      if (!/^[a-zA-Z0-9_]{3,20}$/.test(username)) return showMsg(t("errors.usernameRule"), "warn");

      const { res, j } = await apiJSON("/api/register", { username, email, password }).catch(() => ({ res:null, j:{} }));
      if (!res) return showMsg(t("errors.unknown"), "warn");

      if (j.ok) {
        // most backends auto-login OR not; we handle both
        showMsg(t("confirmNote"), "ok");
        showPanel("unconfirmed");
        startConfirmPolling();
      } else {
        showMsg(j.error || j.message || t("errors.unknown"), "warn");
      }
    });
  }

  async function tryResend() {
    const candidates = ["/api/resend", "/api/resend-confirm", "/api/resend_confirmation", "/api/confirm/resend"];
    for (const url of candidates) {
      const out = await apiJSON(url, {}).catch(() => null);
      if (out && out.res && (out.j?.ok || out.res.ok)) return out;
    }
    return null;
  }

  if (btnResend) {
    btnResend.addEventListener("click", async () => {
      hideMsg();
      const out = await tryResend();
      if (out) {
        showMsg(t("ok.sent"), "ok");
        return;
      }
      showMsg(t("errors.unknown"), "warn");
    });
  }

  if (btnLogout) {
    btnLogout.addEventListener("click", async () => {
      hideMsg();
      await fetch("/api/logout", { method: "POST", credentials: "include" }).catch(() => {});
      stopConfirmPolling();
      updateHeader({ authenticated:false, coins:0 });
      setOverlay(true);
      showPanel("login");
    });
  }

  // ----- bootstrap -----
  (async () => {
    const me = await getMe().catch(() => ({ authenticated: false }));
    updateHeader(me);

    if (!me.authenticated) {
      setOverlay(true);
      showPanel("login");
      return;
    }

    if (!isConfirmed(me)) {
      setOverlay(true);
      showPanel("unconfirmed");
      startConfirmPolling();
      return;
    }

    setOverlay(false);
  })();
});
