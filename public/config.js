/**
 * Smart Web-Printchi - Netlify Konfiguratsiyasi
 */
const AppConfig = {
  // Doimiy bir umrlik Ngrok domeni
  DEFAULT_API_URL: "https://snazzy-chosen-lyricism.ngrok-free.dev",

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
