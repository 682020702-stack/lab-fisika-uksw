(() => {
  const API_BASE = window.location.port === "5500"
    ? `${window.location.protocol}//${window.location.hostname}:8000`
    : window.location.origin;
  const TOKEN_KEY = "laboratorium_access_token";
  const USER_KEY = "laboratorium_user";

  // SECURITY FIX: Keep bearer tokens only for the current tab session, not across browser sessions.
  const legacyToken = localStorage.getItem(TOKEN_KEY);
  if (legacyToken) {
    if (!sessionStorage.getItem(TOKEN_KEY)) sessionStorage.setItem(TOKEN_KEY, legacyToken);
    localStorage.removeItem(TOKEN_KEY);
  }

  function getToken() {
    return sessionStorage.getItem(TOKEN_KEY);
  }

  function token() {
    return getToken();
  }

  function saveToken(value) {
    sessionStorage.setItem(TOKEN_KEY, value);
  }

  function getUser() {
    try {
      const user = JSON.parse(localStorage.getItem(USER_KEY) || "null");
      return user && typeof user === "object" ? user : null;
    } catch {
      localStorage.removeItem(USER_KEY);
      return null;
    }
  }

  function saveUser(user) {
    const savedUser = {
      id: user.id,
      username: user.username,
      nama_lengkap: user.nama_lengkap || user.nama || user.username,
      role: user.role,
      tipe_user: user.tipe_user ?? null,
    };
    localStorage.setItem(USER_KEY, JSON.stringify(savedUser));
    return savedUser;
  }

  function clearToken() {
    sessionStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  }

  function currentUserId() {
    const value = token();
    if (!value) return null;
    try {
      const payload = JSON.parse(atob(value.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
      return Number(payload.sub) || null;
    } catch {
      return null;
    }
  }

  async function apiFetch(path, options = {}) {
    const headers = new Headers(options.headers || {});
    const accessToken = token();
    if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);

    let body = options.body;
    if (body && typeof body === "object" && !(body instanceof FormData) && !(body instanceof Blob)) {
      headers.set("Content-Type", "application/json");
      body = JSON.stringify(body);
    }

    let response;
    try {
      response = await fetch(`${API_BASE}${path}`, {
        ...options,
        headers,
        body,
      });
    } catch (error) {
      if (error?.name === "AbortError") throw error;
      // SECURITY FIX: Do not expose raw browser/network exception details in the UI.
      throw new Error("Tidak dapat terhubung ke server. Periksa koneksi Anda.");
    }
    if (!response.ok) {
      // SECURITY FIX: Map status codes to safe messages instead of displaying API details.
      let message = "Permintaan gagal. Silakan coba kembali.";
      if (response.status === 401) {
        message = path === "/login"
          ? "Username atau password tidak sesuai."
          : "Sesi Anda telah berakhir, silakan login kembali.";
      } else if (response.status === 403) {
        message = path === "/login"
          ? "Akun belum dapat digunakan. Periksa status verifikasi atau hubungi administrator."
          : "Anda tidak memiliki izin untuk melakukan tindakan ini.";
      } else if (response.status === 404) {
        message = "Data yang diminta tidak ditemukan.";
      } else if (response.status === 422) {
        message = "Periksa kembali data yang Anda masukkan.";
      } else if (response.status === 429) {
        message = "Terlalu banyak percobaan. Silakan tunggu sebelum mencoba kembali.";
      } else if (response.status >= 500) {
        message = "Terjadi kesalahan pada server. Silakan coba kembali.";
      }
      if (response.status === 401 && document.body.dataset.page !== "login") {
        clearToken();
        location.replace("index.html");
      }
      throw new Error(message);
    }
    if (response.status === 204) return null;
    if (options.responseType === "blob") return response.blob();
    return response.json();
  }

  function logout() {
    clearToken();
    location.href = "index.html";
  }

  window.LabAPI = { API_BASE, TOKEN_KEY, USER_KEY, apiFetch, clearToken, currentUserId, getToken, getUser, logout, saveToken, saveUser, token };
})();
