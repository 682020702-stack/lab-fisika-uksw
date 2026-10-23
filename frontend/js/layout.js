(() => {
  const api = window.LabAPI;
  const icons = {
    dashboard: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="3" width="8" height="8" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="11" width="7" height="10" rx="1.5"/><rect x="3" y="14" width="8" height="7" rx="1.5"/></svg>',
    users: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="9" cy="8" r="3.2"/><path d="M3 20v-1.5a6 6 0 0 1 12 0V20M16 5.2a3.2 3.2 0 0 1 0 6.2m2 3.1a5.1 5.1 0 0 1 3 4.7V20"/></svg>',
    items: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="m4 7 8-4 8 4-8 4-8-4Z"/><path d="m4 12 8 4 8-4M4 17l8 4 8-4"/></svg>',
    loans: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 5h16v15H4zM8 3v4m8-4v4M4 10h16"/><path d="m8 15 2 2 5-5"/></svg>',
    reports: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M5 3h14v18H5zM8 8h8M8 12h8M8 16h4"/><path d="M8 3v2m8-2v2"/></svg>',
    activity: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M3 12h4l3-8 4 16 3-8h4"/><path d="M4 4h2m12 16h2"/></svg>',
    notifications: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9m-8 12h4"/></svg>',
    profile: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></svg>',
    logout: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M10 17l5-5-5-5m5 5H3"/><path d="M12 3h7a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-7"/></svg>',
    logo: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="12" r="2" fill="currentColor"/><ellipse cx="12" cy="12" rx="9" ry="4.2"/><ellipse cx="12" cy="12" rx="9" ry="4.2" transform="rotate(60 12 12)"/><ellipse cx="12" cy="12" rx="9" ry="4.2" transform="rotate(120 12 12)"/></svg>',
  };
  const pages = [
    ["dashboard", "Dashboard", "dashboard.html", "dashboard"],
    ["users", "Pengguna", "users.html", "users"],
    ["items", "Data Barang", "items.html", "items"],
    ["loans", "Peminjaman", "loans.html", "loans"],
    ["activity", "Log Aktivitas", "activity.html", "activity"],
    ["reports", "Laporan", "reports.html", "reports"],
    ["notifications", "Notifikasi", "notifications.html", "notifications"],
  ];
  const active = document.body.dataset.page;
  const current = pages.find((entry) => entry[0] === active) || pages[0];
  const sidebar = document.getElementById("sidebar");
  const topbar = document.getElementById("topbar");
  if (!sidebar || !topbar) return;
  let sidebarBackdrop = document.querySelector("[data-sidebar-backdrop]");
  if (!sidebarBackdrop) {
    sidebarBackdrop = document.createElement("button");
    sidebarBackdrop.className = "sidebar-backdrop";
    sidebarBackdrop.type = "button";
    sidebarBackdrop.setAttribute("aria-label", "Tutup menu");
    sidebarBackdrop.setAttribute("data-sidebar-backdrop", "");
    sidebar.insertAdjacentElement("afterend", sidebarBackdrop);
  }

  function setSidebarOpen(isOpen) {
    sidebar.classList.toggle("open", isOpen);
    document.body.classList.toggle("sidebar-open", isOpen);
    document.querySelector("[data-menu-toggle]")?.setAttribute("aria-expanded", String(isOpen));
    sidebar.setAttribute("aria-hidden", String(!isOpen && window.matchMedia("(max-width: 767px)").matches));
  }

  window.toggleSidebar = () => {
    setSidebarOpen(!sidebar.classList.contains("open"));
  };

  sidebarBackdrop.addEventListener("click", () => setSidebarOpen(false));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") setSidebarOpen(false);
  });

  window.showToast = (message, kind = "success") => {
    let host = document.querySelector(".toast-host");
    if (!host) {
      host = document.createElement("div");
      host.className = "toast-host";
      host.setAttribute("aria-live", "polite");
      document.body.append(host);
    }
    const toast = document.createElement("div");
    toast.className = `toast ${kind === "error" ? "error" : ""}`;
    toast.textContent = message;
    host.append(toast);
    window.setTimeout(() => toast.remove(), 3600);
  };

  function renderLayout(user) {
    const isAdmin = user?.role?.toLowerCase() === "admin";
    const visiblePages = isAdmin ? pages : pages.filter(([key]) => !["users", "reports", "activity"].includes(key));
    const currentTitle = active === "profile" ? "Profil" : current[1];
    sidebar.innerHTML = `
      <!-- Logo lokal: simpan gambar di frontend/assets/FSM_UKSW.png. -->
      <a class="lab-brand" href="dashboard.html" aria-label="Laboratorium Fisika, beranda">
        <img
          class="lab-brand-image"
          src="/assets/FSM_UKSW.png"
          width="950" height="500"
          alt="Logo FSM dan UKSW">

        <span class="lab-brand-text">
          <span class="brand-title block">LABORATORIUM FISIKA DAN PEMBELAJARAN FISIKA</span>
          <span class="brand-subtitle block">Sistem Inventaris</span>
        </span>
      </a>
      <div class="side-caption">Menu Utama</div>
      <nav class="side-nav" aria-label="Navigasi utama">${visiblePages.map(([key, label, href, icon]) => `
        <a class="side-link ${key === active ? "active" : ""}" href="${href}" ${key === active ? 'aria-current="page"' : ""}>${icons[icon]}<span>${label}</span></a>
      `).join("")}</nav>
      <div class="sidebar-foot">
        <a class="profile-link" href="profile.html"><span class="avatar" data-avatar>A</span><span class="profile-meta"><span class="profile-name block" data-sidebar-name>Pengguna</span><span class="profile-role block" data-sidebar-role>Laboratorium Fisika</span></span>${icons.profile}</a>
        <button class="logout-button" type="button" data-logout>${icons.logout}<span>Keluar</span></button>
      </div>`;

    topbar.innerHTML = `
      <div class="topbar-left">
        <button class="mobile-menu" type="button" aria-label="Buka menu" aria-controls="sidebar" aria-expanded="false" data-menu-toggle><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 6h16M4 12h16M4 18h16"/></svg></button>
        <div><div class="topbar-title">${currentTitle}</div><div class="topbar-kicker">Sistem Manajemen Laboratorium Fisika</div></div>
      </div>
      <div class="topbar-right"><div class="text-right"><div class="font-semibold text-[#34433a]" data-header-name>Memuat pengguna…</div><div class="mt-1 flex justify-end gap-1.5"><span class="role-badge" data-header-role></span><span class="role-badge role-badge-user hidden" data-header-type></span></div></div><span class="avatar" data-avatar>A</span></div>`;

    const pageContent = document.querySelector(".page-content");
    if (pageContent && !pageContent.querySelector(".page-date")) {
      const pageDate = document.createElement("div");
      pageDate.className = "page-date";
      pageDate.textContent = new Intl.DateTimeFormat("id-ID", {
        weekday: "long",
        day: "numeric",
        month: "long",
        year: "numeric",
      }).format(new Date());
      pageContent.append(pageDate);
    }

    document.querySelectorAll("[data-admin-only]").forEach((node) => node.classList.toggle("hidden", !isAdmin));
    document.querySelectorAll("[data-user-only]").forEach((node) => node.classList.toggle("hidden", isAdmin));
    const name = user?.nama_lengkap || user?.username || "Pengguna";
    const role = user?.role || "";
    document.querySelectorAll("[data-sidebar-name], [data-header-name]").forEach((node) => { node.textContent = name; });
    const roleBadge = document.querySelector("[data-header-role]");
    if (roleBadge) {
      roleBadge.textContent = role;
      roleBadge.className = `role-badge ${isAdmin ? "role-badge-admin" : "role-badge-user"}`;
    }
    const typeBadge = document.querySelector("[data-header-type]");
    if (typeBadge) {
      typeBadge.textContent = user?.tipe_user || "";
      typeBadge.classList.toggle("hidden", !user?.tipe_user);
    }
    document.querySelectorAll("[data-sidebar-role]").forEach((node) => { node.textContent = role; });
    document.querySelectorAll("[data-avatar]").forEach((node) => { node.textContent = (name.trim()[0] || "P").toUpperCase(); });

    document.querySelectorAll("[data-logout]").forEach((button) => button.addEventListener("click", window.LabAuth.logout));
    document.querySelector("[data-menu-toggle]")?.addEventListener("click", window.toggleSidebar);
    document.querySelectorAll(".side-link").forEach((link) => link.addEventListener("click", () => setSidebarOpen(false)));
    setSidebarOpen(false);

    if (user?.role && !isAdmin && ["users", "reports", "activity"].includes(active)) {
      location.replace("dashboard.html");
    }
  }

  renderLayout(api.getUser());
  if (!api.getUser() && api.getToken()) {
    api.apiFetch("/users/me")
      .then((user) => renderLayout(api.saveUser(user)))
      .catch((error) => window.showToast(error.message || "Gagal memuat informasi pengguna.", "error"));
  }
})();
