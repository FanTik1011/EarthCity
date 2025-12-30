document.addEventListener("DOMContentLoaded", () => {
  const $ = (id) => document.getElementById(id);

  // =====================
  // CONFIG (change if needed)
  // =====================
  const GOOGLE_AUTH_URL = "/api/auth/google"; // <- якщо інший шлях, зміни тут
  const COUNTRIES_URL = "/api/countries";     // <- якщо інший шлях, зміни тут

  // =====================
  // UI refs
  // =====================
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
  const btnCreateCountry = $("btnCreateCountry");
  const btnGoogle = $("btnGoogle");

  // Toast
  const toastEl = $("toast");
  const toastTitle = $("toastTitle");
  const toastText = $("toastText");
  const toastClose = $("toastClose");

  if (btnGoogle) btnGoogle.setAttribute("href", GOOGLE_AUTH_URL);

  // =====================
  // Toast helpers
  // =====================
  function toast(title, text) {
    if (!toastEl) return;
    toastTitle.textContent = title || "Done";
    toastText.textContent = text || "";
    toastEl.style.display = "flex";
    clearTimeout(toast._t);
    toast._t = setTimeout(() => {
      toastEl.style.display = "none";
    }, 3600);
  }
  if (toastClose) {
    toastClose.addEventListener("click", () => {
      if (toastEl) toastEl.style.display = "none";
    });
  }

  // =====================
  // ---- NEW: polling when unconfirmed ----
  // =====================
  let confirmPollTimer = null;

  function startConfirmPolling() {
    stopConfirmPolling();
    confirmPollTimer = setInterval(async () => {
      const me = await getMe().catch(() => null);
      if (!me) return;

      // if logged out - stop
      if (!me.authenticated) {
        stopConfirmPolling();
        return;
      }

      // once confirmed -> refresh UI and stop
      if (me.is_confirmed) {
        stopConfirmPolling();
        await refreshMe({ showWelcome: false });
      }
    }, 2000);
  }

  function stopConfirmPolling() {
    if (confirmPollTimer) {
      clearInterval(confirmPollTimer);
      confirmPollTimer = null;
    }
  }

  // =====================
  // Messages
  // =====================
  function showMsg(text) {
    if (!msg) return;
    msg.style.display = "block";
    msg.textContent = text;
  }
  function clearMsg() {
    if (!msg) return;
    msg.style.display = "none";
    msg.textContent = "";
  }
  function showDevLink(link) {
    if (!devLink) return;
    if (!link) {
      devLink.style.display = "none";
      devLink.textContent = "";
      return;
    }
    devLink.style.display = "block";
    devLink.textContent = `DEV link: ${link}`;
  }

  function switchTab(which) {
    clearMsg();
    showDevLink(null);

    tabLogin.classList.toggle("active", which === "login");
    tabRegister.classList.toggle("active", which === "register");

    panelLogin.style.display = which === "login" ? "block" : "none";
    panelRegister.style.display = which === "register" ? "block" : "none";
    panelUnconfirmed.style.display = "none";

    stopConfirmPolling();
  }

  function showUnconfirmed() {
    clearMsg();
    showDevLink(null);

    panelLogin.style.display = "none";
    panelRegister.style.display = "none";
    panelUnconfirmed.style.display = "block";

    // while user is unconfirmed, keep checking confirmation status
    startConfirmPolling();
  }

  // =====================
  // Fetch helpers
  // =====================
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

  async function getJSON(path) {
    const res = await fetch(path, { credentials: "include" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    return data;
  }

  async function getMe() {
    const res = await fetch("/api/me", { credentials: "include" });
    return await res.json();
  }

  // =====================
  // Hide "Create Country" if already has a country
  // =====================
  function setCreateVisible(visible) {
    if (!btnCreateCountry) return;
    btnCreateCountry.style.display = visible ? "" : "none";
  }

  async function userHasCountry(me) {
    // If backend gives has_country -> use it
    if (me && typeof me.has_country === "boolean") return me.has_country;

    // Otherwise try to detect from countries list
    // NOTE: adjust COUNTRIES_URL if needed
    const list = await getJSON(COUNTRIES_URL);
    const countries = Array.isArray(list) ? list : (list.countries || []);

    const uname = (me && me.username) ? String(me.username) : "";
    const uid = me && (me.id || me.user_id);

    return countries.some(c => {
      const ownerU = c.owner || c.owner_username || c.username;
      const ownerId = c.owner_id || c.user_id;

      if (uid != null && ownerId != null) return String(ownerId) === String(uid);
      if (uname) return String(ownerU || "").toLowerCase() === uname.toLowerCase();
      return false;
    });
  }

  // =====================
  // Main state refresh
  // =====================
  async function refreshMe({ showWelcome = true } = {}) {
    const me = await getMe().catch(() => null);
    if (!me) return;

    if (me.authenticated) {
      const uname = me.username || "User";
      userLabel.textContent = uname;
      btnLogout.style.display = "inline-flex";

      // confirmed?
      if (me.is_confirmed) {
        stopConfirmPolling();
        overlay.style.display = "none";
        setTimeout(() => window.__earthMap && window.__earthMap.resize(), 60);

        // show username (especially after Google login redirect)
        if (showWelcome) {
          toast("Welcome back", `Logged in as @${uname}`);
        }

        // hide Create Country if already exists
        try {
          const has = await userHasCountry(me);
          setCreateVisible(!has);
          if (has) {
            // optional: small info
            // toast("Country detected", "Create button hidden because you already own a country.");
          }
        } catch (e) {
          // if cannot check -> keep button visible
          setCreateVisible(true);
        }

      } else {
        overlay.style.display = "flex";
        showUnconfirmed();
        setCreateVisible(true);
      }
    } else {
      stopConfirmPolling();
      userLabel.textContent = "Guest";
      btnLogout.style.display = "none";
      overlay.style.display = "flex";
      switchTab("login");
      setCreateVisible(true);
    }
  }

  // =====================
  // Events
  // =====================
  // refresh on tab focus (useful after clicking confirm link)
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) refreshMe({ showWelcome: false });
  });

  tabLogin.addEventListener("click", (e) => { e.preventDefault(); switchTab("login"); });
  tabRegister.addEventListener("click", (e) => { e.preventDefault(); switchTab("register"); });

  btnLogin.addEventListener("click", async (e) => {
    e.preventDefault();
    clearMsg(); showDevLink(null);

    const email = ($("loginEmail").value || "").trim().toLowerCase();
    const password = $("loginPassword").value || "";

    try {
      const data = await postJSON("/api/login", { email, password });
      if (!data.is_confirmed) {
        showUnconfirmed();
        showMsg("Підтверди email, щоб отримати доступ. Після підтвердження повернись на вкладку — ми перевіримо автоматично ✅");
      }
      await refreshMe({ showWelcome: true });
    } catch (err) {
      showMsg(err.message);
    }
  });

  btnRegister.addEventListener("click", async (e) => {
    e.preventDefault();
    clearMsg(); showDevLink(null);

    const username = ($("regUsername").value || "").trim();
    const email = ($("regEmail").value || "").trim().toLowerCase();
    const password = $("regPassword").value || "";

    try {
      const data = await postJSON("/api/register", { username, email, password });
      showUnconfirmed();
      showMsg("Ми надіслали лист ✅ Перевір Inbox/Spam. Після кліку по лінку просто повернись на вкладку — підтягнеться автоматично.");
      if (data.sent === false && data.dev_link) showDevLink(data.dev_link);
      await refreshMe({ showWelcome: false });
    } catch (err) {
      showMsg(err.message);
    }
  });

  btnResend.addEventListener("click", async (e) => {
    e.preventDefault();
    clearMsg(); showDevLink(null);

    try {
      const data = await postJSON("/api/resend-confirmation", {});
      showMsg("Лист відправлено ще раз ✅");
      if (data.sent === false && data.dev_link) showDevLink(data.dev_link);
    } catch (err) {
      showMsg(err.message);
    }
  });

  btnLogout.addEventListener("click", async (e) => {
    e.preventDefault();
    clearMsg(); showDevLink(null);

    try {
      await postJSON("/api/logout", {});
      overlay.style.display = "flex";
      switchTab("login");
      toast("Logged out", "See you soon 👋");
      await refreshMe({ showWelcome: false });
    } catch (err) {
      showMsg(err.message);
    }
  });

  // init
  refreshMe({ showWelcome: true });
});
