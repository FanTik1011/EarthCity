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

  // ---- NEW: polling when unconfirmed ----
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
  // --------------------------------------

  function showMsg(text) {
    msg.style.display = "block";
    msg.textContent = text;
  }
  function clearMsg() {
    msg.style.display = "none";
    msg.textContent = "";
  }
  function showDevLink(link) {
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

    // NEW: while user is unconfirmed, keep checking confirmation status
    startConfirmPolling();
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
        stopConfirmPolling(); // NEW
        overlay.style.display = "none";
        setTimeout(() => window.__earthMap && window.__earthMap.resize(), 60);
      } else {
        overlay.style.display = "flex";
        showUnconfirmed();
      }
    } else {
      stopConfirmPolling(); // NEW
      userLabel.textContent = "Guest";
      btnLogout.style.display = "none";
      overlay.style.display = "flex";
      switchTab("login");
    }
  }

  // Extra: if user returns to tab, refresh state (very useful after clicking confirm link)
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) refreshMe();
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
      await refreshMe();
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
      await refreshMe();
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
      await refreshMe();
    } catch (err) {
      showMsg(err.message);
    }
  });
  const btnAdmin = document.getElementById("btnAdmin");

async function refreshMeUI(){
  const r = await fetch("/api/me", { credentials: "same-origin" });
  const me = await r.json();

  // existing your UI code...

  // ✅ Admin button
  if (btnAdmin) {
    btnAdmin.style.display = (me.authenticated && me.is_admin) ? "" : "none";
  }
}

if (btnAdmin) {
  btnAdmin.addEventListener("click", () => {
    window.location.href = "/admin";
  });
}


  refreshMe();
});
