/**
 * Smart Web-Printchi - Netlify Konfiguratsiyasi
 * 
 * Agar veb-sayt Netlify da ishlasa, so'rovlar Raspberry Pi dagi
 * Cloudflare Tunnel yoki IP manzilga yo'naltiriladi.
 */
const AppConfig = {
  // Standart Backend API URL (Agar bo'sh bo'lsa, localStorage yoki avtomatik aniqlanadi)
  DEFAULT_API_URL: "",

  // Backend API manzilini olish
  getApiUrl() {
    const saved = localStorage.getItem("PRINTCHI_API_URL");
    if (saved && saved.trim()) {
      return saved.trim().replace(/\/+$/, "");
    }
    if (this.DEFAULT_API_URL && this.DEFAULT_API_URL.trim()) {
      return this.DEFAULT_API_URL.trim().replace(/\/+$/, "");
    }
    // Agar Netlify da bo'lmasa (lokal ochilgan bo'lsa):
    if (window.location.hostname !== "localhost" && !window.location.hostname.includes("netlify.app")) {
      return window.location.origin;
    }
    return "";
  },

  // Backend manzilini saqlash
  setApiUrl(url) {
    if (url) {
      localStorage.setItem("PRINTCHI_API_URL", url.trim().replace(/\/+$/, ""));
    } else {
      localStorage.removeItem("PRINTCHI_API_URL");
    }
  }
};
