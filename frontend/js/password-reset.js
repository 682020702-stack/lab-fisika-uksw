(() => {
  const api = window.LabAPI;
  const form = document.querySelector("form");
  const message = document.getElementById("reset-message");
  const submit = form?.querySelector('button[type="submit"]');

  function showMessage(text, isSuccess = false) {
    message.textContent = text;
    message.classList.add("visible");
    message.classList.toggle("success", isSuccess);
  }

  if (!form || !message || !submit) return;

  if (document.body.dataset.page === "forgot-password") {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      message.classList.remove("visible", "success");
      submit.disabled = true;
      try {
        const email = new FormData(form).get("email");
        const result = await api.apiFetch("/forgot-password", {
          method: "POST",
          body: { email },
        });
        showMessage(result.message, true);
        form.reset();
      } catch (error) {
        showMessage(error.message || "Permintaan gagal. Silakan coba kembali.");
      } finally {
        submit.disabled = false;
      }
    });
    return;
  }

  if (document.body.dataset.page === "reset-password") {
    const token = new URLSearchParams(location.search).get("token");
    if (!token) {
      showMessage("Token reset tidak valid atau tidak tersedia.");
      submit.disabled = true;
      return;
    }

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      message.classList.remove("visible", "success");
      const values = new FormData(form);
      const newPassword = values.get("new_password");
      if (newPassword !== values.get("confirm_password")) {
        showMessage("Konfirmasi password baru tidak cocok.");
        return;
      }

      submit.disabled = true;
      try {
        const result = await api.apiFetch("/reset-password", {
          method: "POST",
          body: { token, new_password: newPassword },
        });
        showMessage(result.message, true);
        form.reset();
        submit.disabled = true;
      } catch (error) {
        showMessage(error.message || "Password gagal diubah. Silakan coba kembali.");
        submit.disabled = false;
      }
    });
  }
})();
