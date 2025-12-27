// static/js/auth.js
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

  // Optional: close factories sidebar close buttons duplication fix
  const fbClose = $("fbClose");
  const fbClose2 = $("fbClose2");
  if (fbClose2 && fbClose) fbClose2.addEventListener("click", () => fbClose.click());

  // ---- polling when unconfirmed ----
  let confirmPollTimer = null;

  function startConfirmPolling() {
    stopConfirmPolling();
    confirmPollTimer = setInterval(async () => {
      const me = await getMe().catch(() => null);
      if (!me) return;

      if (!me.authenticated) {
        stopConfirmPolling();
        return;
      }

      if (me.is_confirmed) {
        stopConfirmPolling();
        await refreshMe();
      }
    }, 2000);
  }

  function stopConfirmPolling() {
    if (confirmPollTimer) {
      clearInterval(confirmPollTimer);
      confirmPollTimer = null;
    }
  }
  // ---------------------------------

  // ✅ Critical fix: overlay must NOT be aria-hidden=true while user interacts with it
  function overlayOpen(focusEl) {
    overlay.style.display = "flex";
    overlay.setAttribute("aria-hidden", "false");
    // safe focus (avoid aria-hidden/focus warnings)
    if (focusEl) setTimeout(() => focusEl.focus(), 0);
  }

  function overlayClose() {
    // remove focus from inside overlay before hiding
    if (overlay.contains(document.activeElement)) document.activeElement.blur();
    overlay.style.display = "none";
    overlay.setAttribute("aria-hidden", "true");
  }

  function showMsg(text) {
    msg.style.display = "block";
    msg.textContent = text;
  }

  function clearMsg() {
    msg.style.display = "none";
    msg.textContent = "";
  }

  function showDevLink(link, mailError) {
    if (!link) {
      devLink.style.display = "none";
      devLink.textContent = "";
      return;
    }
    devLink.style.display = "block";
    // покажемо й причину, якщо сервер вернув mail_error (дуже корисно на Heroku)
    devLink.textContent = mailError ? `DEV link: ${link}\nMAIL: ${mailError}` : `DEV link: ${link}`;
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

    // фокус на перше поле
    if (which === "login") {
      overlayOpen($("loginEmail"));
    } else {
      overlayOpen($("regUsername"));
    }
  }

  function showUnconfirmed() {
    clearMsg();
    showDevLink(null);

    panelLogin.style.display = "none";
    panelRegister.style.display = "none";
    panelUnconfirmed.style.display = "block";

    startConfirmPolling();
    overlayOpen(btnResend);
  }

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

  async function getMe() {
    const res = await fetch("/api/me", { credentials: "include" });
    return await res.json();
  }

  async function refreshMe() {
    const me = await getMe().catch(() => null);
    if (!me) return;

    if (me.authenticated) {
      userLabel.textContent = me.username || "User";
      btnLogout.style.display = "inline-flex";

      if (me.is_confirmed) {
        stopConfirmPolling();
        overlayClose();
        setTimeout(() => window.__earthMap && window.__earthMap.resize(), 60);
      } else {
        showUnconfirmed();
      }
    } else {
      stopConfirmPolling();
      userLabel.textContent = "Guest";
      btnLogout.style.display = "none";
      switchTab("login");
    }
  }

  // Extra: if user returns to tab (after clicking confirm link), refresh state
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) refreshMe();
  });

  tabLogin.addEventListener("click", (e) => {
    e.preventDefault();
    switchTab("login");
  });

  tabRegister.addEventListener("click", (e) => {
    e.preventDefault();
    switchTab("register");
  });

  btnLogin.addEventListener("click", async (e) => {
    e.preventDefault();
    clearMsg();
    showDevLink(null);

    const email = ($("loginEmail").value || "").trim().toLowerCase();
    const password = $("loginPassword").value || "";

    try {
      const data = await postJSON("/api/login", { email, password });
      if (!data.is_confirmed) {
        showUnconfirmed();
        showMsg("Підтверди email, щоб отримати доступ. Після підтвердження повернись на вкладку — ми перевіримо автоматично ✅");
      }
      await refreshMe();
    } catch (err) {
      showMsg(err.message);
    }
  });

  btnRegister.addEventListener("click", async (e) => {
    e.preventDefault();
    clearMsg();
    showDevLink(null);

    const username = ($("regUsername").value || "").trim();
    const email = ($("regEmail").value || "").trim().toLowerCase();
    const password = $("regPassword").value || "";

    try {
      const data = await postJSON("/api/register", { username, email, password });

      showUnconfirmed();

      if (data.sent) {
        showMsg("Ми надіслали лист ✅ Перевір Inbox/Spam. Після кліку по лінку просто повернись на вкладку — підтягнеться автоматично.");
        showDevLink(null);
      } else {
        showMsg("Не вдалося надіслати лист 😕 Я покажу dev-link (і причину), щоб ти все одно міг підтвердити.");
        if (data.dev_link) showDevLink(data.dev_link, data.mail_error);
      }

      await refreshMe();
    } catch (err) {
      showMsg(err.message);
    }
  });

  btnResend.addEventListener("click", async (e) => {
    e.preventDefault();
    clearMsg();
    showDevLink(null);

    try {
      const data = await postJSON("/api/resend-confirmation", {});
      if (data.sent) {
        showMsg("Лист відправлено ще раз ✅ Перевір Inbox/Spam.");
      } else {
        showMsg("Не вдалося надіслати лист 😕 Я покажу dev-link (і причину).");
        if (data.dev_link) showDevLink(data.dev_link, data.mail_error);
      }
    } catch (err) {
      showMsg(err.message);
    }
  });

  btnLogout.addEventListener("click", async (e) => {
    e.preventDefault();
    clearMsg();
    showDevLink(null);

    try {
      await postJSON("/api/logout", {});
      overlayOpen($("loginEmail"));
      switchTab("login");
      await refreshMe();
    } catch (err) {
      showMsg(err.message);
    }
  });

  // init
  refreshMe();
});
