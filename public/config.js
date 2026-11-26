/**
 * Smart Web-Printchi - Netlify Konfiguratsiyasi
 *
 * ⚠️ SOZLASH KERAK:
 *  1. DEFAULT_API_URL — Raspberry Pi Ngrok manzili
 *  2. PAYMENT — Haqiqiy karta raqami va egasi
 *
 * Yoki saytdagi ⚙️ tugma orqali sozlash mumkin (localStorage ga saqlanadi)
 */
const AppConfig = {
  // Render.com doimiy tezkor bulutli server URL
  DEFAULT_API_URL: "https://smart-printer-mo1g.onrender.com",

  // Yagona printer: Canon LBP3010 (A4, oq-qora). To'lov: faqat kartaga o'tkazma.
  PAY_METHODS: ["card"],     // "qr", "click", "payme", "card" — saytda shu tartibda ko'rsatiladi

  // To'lov tizimi sozlamalari
  PAYMENT: {
    enabled: true,
    cardNumber: "5614681290252570",          // Ipoteka bank (…2570) — CardXabar kuzatadi, avtomatik tasdiq
    cardHolder: "Ravshanov Asilbek",
    cardBank: "Ipoteka bank",
    // Click P2P
    clickPhone: "+998944737627",
    clickMerchantId: "",     // Click merchant bo'lmasa bo'sh qoladi
    clickServiceId: "",
    // Payme
    paymeMerchantId: "",     // Payme merchant bo'lmasa bo'sh qoladi
    paymePhone: "+998944737627"
  },

  getPaymentConfig() {
    const saved = localStorage.getItem("PRINTCHI_PAYMENT_CONFIG");
    if (saved) {
      try {
        return { ...this.PAYMENT, ...JSON.parse(saved) };
      } catch (e) {
        console.error("Payment config parse xatosi:", e);
      }
    }
    return this.PAYMENT;
  },

  setPaymentConfig(cfg) {
    if (cfg) {
      localStorage.setItem("PRINTCHI_PAYMENT_CONFIG", JSON.stringify(cfg));
    }
  },

  _activeUrl: "",

  // Sayt statik xostingdami (Netlify / GitHub Pages)? Unda backend manzili tunnel orqali olinadi.
  isStaticHost() {
    const h = window.location.hostname;
    return window.location.protocol === "file:" || h.includes("netlify.app") || h.includes("github.io");
  },

  shouldDiscoverUrl() {
    return this.isStaticHost();
  },

  getApiUrl() {
    // Sahifani Flask serverining o'zi bergan bo'lsa (localhost:5000, Pi IP, trycloudflare) — o'sha manzil
    if (!this.isStaticHost()) {
      return window.location.origin;
    }
    if (this._activeUrl) {
      return this._activeUrl.replace(/\/+$/, "");
    }
    const saved = localStorage.getItem("PRINTCHI_API_URL");
    if (saved && saved.trim()) {
      return saved.trim().replace(/\/+$/, "");
    }
    if (this.DEFAULT_API_URL && this.DEFAULT_API_URL.trim()) {
      return this.DEFAULT_API_URL.trim().replace(/\/+$/, "");
    }
    return window.location.origin;
  },

  async fetchLatestLiveUrl() {
    try {
      const res = await fetch("https://ntfy.sh/smart_printer_asil2004_tunnel_url/json?poll=1&since=all", { cache: "no-store" });
      const text = await res.text();
      const msgs = text.trim().split("\n")
        .map(line => { try { return JSON.parse(line); } catch(e) { return null; } })
        .filter(m => m && m.event === "message" && m.message && m.message.startsWith("http"));
      if (msgs.length > 0) {
        const liveUrl = msgs[msgs.length - 1].message.trim().replace(/\/+$/, "");
        this._activeUrl = liveUrl;
        this.DEFAULT_API_URL = liveUrl;
        return liveUrl;
      }
    } catch (e) {
      console.warn("Dinamik URL olishda xatolik:", e);
    }
    return this.getApiUrl();
  },

  setApiUrl(url) {
    if (url) {
      this._activeUrl = url.trim().replace(/\/+$/, "");
      localStorage.setItem("PRINTCHI_API_URL", this._activeUrl);
    } else {
      this._activeUrl = "";
      localStorage.removeItem("PRINTCHI_API_URL");
    }
  }
};


