/**
 * Smart Web-Printchi - Netlify Konfiguratsiyasi
 */
const AppConfig = {
  // Doimiy bir umrlik Ngrok domeni
  DEFAULT_API_URL: "https://snazzy-chosen-lyricism.ngrok-free.dev",

  // To'lov tizimi sozlamalari
  PAYMENT: {
    enabled: true,
    cardNumber: "8600 5304 **** ****", // Default ko'rsatiladigan karta raqami
    cardHolder: "PRINT MARKAZ EGASI",
    cardBank: "Uzcard / Humo",
    // Click sozlamalari
    clickPhone: "+998901234567",
    clickMerchantId: "",
    clickServiceId: "",
    // Payme sozlamalari
    paymeMerchantId: "",
    paymePhone: "+998901234567"
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

