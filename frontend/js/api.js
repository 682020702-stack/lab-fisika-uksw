(() => {
  const API_BASE = window.location.port === "5500"
    ? `${window.location.protocol}//${window.location.hostname}:8000`
    : window.location.origin;
  const TOKEN_KEY = "laboratorium_access_token";
  const USER_KEY = "laboratorium_user";

  function getToken() {
    return localStorage.getItem(TOKEN_KEY);
  }

  function token() {
    return getToken();
  }

  function saveToken(value) {
    localStorage.setItem(TOKEN_KEY, value);
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

    const response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers,
      body,
    });
    if (!response.ok) {
      let message = `Permintaan gagal (${response.status})`;
      try {
        const result = await response.json();
        message = Array.isArray(result.detail)
          ? result.detail.map((entry) => entry.msg).join(", ")
          : (result.detail || result.message || message);
      } catch {
        // Keep the HTTP status message when the response is not JSON.
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
