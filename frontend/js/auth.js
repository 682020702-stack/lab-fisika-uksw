(() => {
  const api = window.LabAPI;

  function getToken() {
    return api.getToken();
  }

  async function logout() {
    try {
      await api.apiFetch("/logout", { method: "POST" });
    } catch (error) {
      console.error("Gagal mencatat logout:", error);
    } finally {
      api.clearToken();
      location.replace("index.html");
    }
  }

  window.LabAuth = { getToken, logout };

  if (document.body.dataset.page === "register") {
    const form = document.getElementById("register-form");
    const messageBox = document.getElementById("register-message");
    const submit = document.getElementById("register-submit");
    form?.addEventListener("submit", async (event) => {
      event.preventDefault();
      messageBox.classList.remove("visible");
      messageBox.classList.remove("success");
      submit.disabled = true;
      submit.textContent = "Mengirim pendaftaran…";
      try {
        const data = Object.fromEntries(new FormData(form).entries());
        await api.apiFetch("/register-public", { method: "POST", body: data });
        window.alert("Registrasi berhasil! Cek email Anda untuk verifikasi.");
        form.reset();
        location.replace("index.html");
      } catch (error) {
        messageBox.textContent = error.message || "Pendaftaran gagal. Silakan coba kembali.";
        messageBox.classList.add("visible");
      } finally {
        submit.disabled = false;
        submit.textContent = "Daftar";
      }
    });
    return;
  }

  if (document.body.dataset.page !== "login") return;
  if (getToken()) {
    location.replace("dashboard.html");
    return;
  }

  const form = document.getElementById("login-form");
  const errorBox = document.getElementById("login-error");
  const submit = document.getElementById("login-submit");

  document.querySelector("[data-password-toggle]")?.addEventListener("click", (event) => {
    const input = document.getElementById("password");
    input.type = input.type === "password" ? "text" : "password";
    event.currentTarget.setAttribute("aria-label", input.type === "password" ? "Tampilkan password" : "Sembunyikan password");
  });

  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    errorBox.classList.remove("visible");
    submit.disabled = true;
    submit.textContent = "Memeriksa akun…";
    try {
      const credentials = Object.fromEntries(new FormData(form).entries());
      const result = await api.apiFetch("/login", { method: "POST", body: credentials });
      if (!result.access_token) throw new Error("Token tidak diterima dari server.");
      api.saveToken(result.access_token);
      api.saveUser(result.user);
      location.href = "dashboard.html";
    } catch (error) {
      api.clearToken();
      errorBox.textContent = error.message || "Username atau password tidak sesuai.";
      errorBox.classList.add("visible");
    } finally {
      submit.disabled = false;
      submit.innerHTML = 'Masuk ke Dashboard <span aria-hidden="true">→</span>';
    }
  });
})();
