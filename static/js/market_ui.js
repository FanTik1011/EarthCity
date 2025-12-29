// static/js/market_ui.js
(function(){
  const $ = (id)=>document.getElementById(id);

  function scrollToId(id){
    const el = $(id);
    if (!el) return;
    el.scrollIntoView({behavior:"smooth", block:"start"});
  }

  // top mini nav
  $("btnGoInv")?.addEventListener("click", ()=>scrollToId("secInventory"));
  $("btnGoMarket")?.addEventListener("click", ()=>scrollToId("secMarket"));
  $("btnGoOffers")?.addEventListener("click", ()=>scrollToId("secOffers"));

  // hero quick
  $("btnScrollInv")?.addEventListener("click", ()=>scrollToId("secInventory"));
  $("btnScrollMarket")?.addEventListener("click", ()=>scrollToId("secMarket"));
  $("btnScrollOffers2")?.addEventListener("click", ()=>scrollToId("secOffers"));

  // floating
  $("fabTop")?.addEventListener("click", ()=>window.scrollTo({top:0, behavior:"smooth"}));
  $("fabInv")?.addEventListener("click", ()=>scrollToId("secInventory"));
  $("fabMk")?.addEventListener("click", ()=>scrollToId("secMarket"));
  $("fabP2P")?.addEventListener("click", ()=>scrollToId("secOffers"));

  // modal helpers
  function openModal(modal){
    if (!modal) return;
    modal.classList.add("open");
    modal.setAttribute("aria-hidden","false");
  }
  function closeModal(modal){
    if (!modal) return;
    modal.classList.remove("open");
    modal.setAttribute("aria-hidden","true");
  }

  // help modal
  const help = $("helpModal");
  $("btnHelp")?.addEventListener("click", ()=>openModal(help));
  help?.addEventListener("click", (e)=>{
    const t = e.target;
    if (t?.getAttribute?.("data-close") === "1") closeModal(help);
  });

  // global close any modal by ESC
  document.addEventListener("keydown", (e)=>{
    if (e.key !== "Escape") return;
    document.querySelectorAll(".mkModal.open").forEach(m => closeModal(m));
  });

  // expose confirm modal controller to market_page.js
  const confirm = $("confirmModal");
  const confirmTitle = $("confirmTitle");
  const confirmAction = $("confirmAction");
  const confirmRes = $("confirmRes");
  const confirmAmt = $("confirmAmt");
  const confirmPrice = $("confirmPrice");
  const confirmTotal = $("confirmTotal");
  const confirmHint = $("confirmHint");
  const confirmDo = $("confirmDo");

  confirm?.addEventListener("click", (e)=>{
    const t = e.target;
    if (t?.getAttribute?.("data-close") === "1") closeModal(confirm);
  });

  window.MarketUI = {
    openConfirm(payload){
      // payload: { title, action, res, amt, price, total, hint, onConfirm }
      if (!confirm) return;
      confirmTitle.textContent = payload.title || "Confirm";
      confirmAction.textContent = payload.action || "—";
      confirmRes.textContent = payload.res || "—";
      confirmAmt.textContent = payload.amt ?? "—";
      confirmPrice.textContent = payload.price ?? "—";
      confirmTotal.textContent = payload.total ?? "—";
      confirmHint.textContent = payload.hint || "";
      confirmDo.onclick = async () => {
        confirmDo.disabled = true;
        try {
          await (payload.onConfirm?.());
          closeModal(confirm);
        } finally {
          confirmDo.disabled = false;
        }
      };
      openModal(confirm);
    }
  };
})();