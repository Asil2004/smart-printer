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
  // Gemini AI API kaliti
  getGeminiApiKey() {
    return atob("QVEuQWI4Uk42TFNiWGt4X2JMV1Z6S2tRbk5HTnBGaTN1OTBYY2FpWFhScV83S2xfaHlKc2c=");
  },

  // Raspberry Pi Cloudflare / Ngrok doimiy URL
  DEFAULT_API_URL: "https://relation-heated-ladder-mpg.trycloudflare.com",

  // To'lov tizimi sozlamalari
  // ⚠️ cardNumber ni TO'LIQ kiriting: "8600 1234 5678 9012"
  //    Yulduzcha (*) bo'lsa Click/Payme havolasi ishlamaydi!
  PAYMENT: {
    enabled: true,
    cardNumber: "",          // ← TO'LIQ karta raqami: "8600 XXXX XXXX XXXX"
    cardHolder: "",          // ← Karta egasi: "FAMILIYA ISM"
    cardBank: "Uzcard / Humo",
    // Click P2P (MerchantId bo'lmasa karta orqali ishlaydi)
    clickPhone: "",          // ← "+998XXXXXXXXX"
    clickMerchantId: "",     // ← Click merchant bo'lmasa bo'sh qoldiring
    clickServiceId: "",      // ← Click service bo'lmasa bo'sh qoldiring
    // Payme (MerchantId bo'lmasa karta orqali ishlaydi)
    paymeMerchantId: "",     // ← Payme merchant bo'lmasa bo'sh qoldiring
    paymePhone: ""           // ← "+998XXXXXXXXX"
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

  getApiUrl() {
    const saved = localStorage.getItem("PRINTCHI_API_URL");
    if (saved && saved.trim()) {
      return saved.trim().replace(/\/+$/, "");
    }
    if (this.DEFAULT_API_URL && this.DEFAULT_API_URL.trim()) {
      return this.DEFAULT_API_URL.trim().replace(/\/+$/, "");
    }
    if (window.location.hostname !== "localhost" && !window.location.hostname.includes("netlify.app")) {
      return window.location.origin;
    }
    return "";
  },

  setApiUrl(url) {
    if (url) {
      localStorage.setItem("PRINTCHI_API_URL", url.trim().replace(/\/+$/, ""));
    } else {
      localStorage.removeItem("PRINTCHI_API_URL");
    }
  }
};

