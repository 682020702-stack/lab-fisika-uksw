(() => {
  const api = window.LabAPI;
  const { apiFetch, currentUserId, token } = api;
  const page = document.body.dataset.page;
  let editingItemId = null;
  let editingUserId = null;
  let editingCategoryId = null;
  let itemCategories = [];
  let loanRequestForm = null;
  let itemLoanRequestForm = null;
  const escapeHTML = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
  const dateText = (value) => value ? new Intl.DateTimeFormat("id-ID", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "—";
  const dateOnly = (value) => value ? new Intl.DateTimeFormat("id-ID", { dateStyle: "medium" }).format(new Date(value)) : "—";
  const statusClass = (value) => {
    const status = String(value || "").toLowerCase();
    if (status === "selesai - rusak") return "status-completed-damaged";
    if (status === "disetujui") return "status-approved";
    if (status.includes("menunggu")) return "status-wait";
    if (status.includes("tolak") || status.includes("nonaktif") || status.includes("rusak")) return "status-bad";
    if (["aktif", "baik", "selesai"].includes(status)) return "";
    if (status.includes("perbaikan") || status.includes("perawatan")) return "status-wait";
    return "status-neutral";
  };
  const statusTag = (value) => `<span class="status-pill ${statusClass(value)}">${String(value) === "Selesai - Rusak" ? '<span class="status-warning-icon" aria-hidden="true">!</span>' : ""}${escapeHTML(value || "—")}</span>`;
  const localDateKey = (value = new Date()) => `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
  const lateDaysFor = (dueDate, now = new Date()) => {
    if (!dueDate) return 0;
    const due = String(dueDate).slice(0, 10);
    const today = localDateKey(now);
    const [dueYear, dueMonth, dueDay] = due.split("-").map(Number);
    const [todayYear, todayMonth, todayDay] = today.split("-").map(Number);
    return Math.max(0, Math.floor((Date.UTC(todayYear, todayMonth - 1, todayDay) - Date.UTC(dueYear, dueMonth - 1, dueDay)) / 86400000));
  };
  const showFailure = (error) => window.showToast?.(error.message || "Terjadi kesalahan. Coba lagi.", "error");
  const formValues = (form) => Object.fromEntries(new FormData(form).entries());
  const emptyRow = (columnCount, message, title = "Belum ada data") => `<tr><td colspan="${columnCount}"><div class="empty-state"><strong>${escapeHTML(title)}</strong>${escapeHTML(message)}</div></td></tr>`;
  const addMobileCardLabels = (tbody) => {
    const labels = [...tbody.closest("table").querySelectorAll("thead th")].map((cell) => cell.textContent.trim());
    [...tbody.rows].forEach((row) => {
      if (row.cells.length === 1 && row.cells[0].hasAttribute("colspan")) {
        row.classList.add("table-empty-row");
        return;
      }
      [...row.cells].forEach((cell, index) => {
        if (labels[index]) cell.dataset.label = labels[index];
      });
    });
  };

  function setupLoanRequestForm(onSuccess) {
    const modal = document.getElementById("loan-create-modal");
    const form = document.getElementById("loan-create-form");
    const itemsContainer = document.getElementById("loan-items-container");
    const submitButton = document.getElementById("submit-loan");
    const addItemButton = document.getElementById("add-loan-item");
    let availableItems = [];

    const setItems = (items) => {
      availableItems = items.filter((item) => item.stok > 0);
      refreshItemRows();
    };

    const refreshItemRows = () => {
      const rows = [...itemsContainer.querySelectorAll(".loan-item-row")];
      rows.forEach((row) => {
        const select = row.querySelector("[data-loan-item]");
        const quantity = row.querySelector("[data-loan-quantity]");
        const selectedId = Number(select.value) || null;
        const usedByOtherRows = new Set(
          rows
            .filter((otherRow) => otherRow !== row)
            .map((otherRow) => Number(otherRow.querySelector("[data-loan-item]").value))
            .filter(Boolean),
        );
        const options = availableItems.filter(
          (item) => item.id === selectedId || !usedByOtherRows.has(item.id),
        );
        select.innerHTML = `<option value="">Pilih barang</option>${options.map((item) =>
          `<option value="${item.id}">${escapeHTML(item.nama_barang)}</option>`
        ).join("")}`;
        select.value = selectedId && options.some((item) => item.id === selectedId)
          ? String(selectedId)
          : "";
        const selected = availableItems.find((item) => String(item.id) === select.value);
        quantity.max = selected ? String(selected.stok) : "";
        quantity.value = selected
          ? String(Math.min(Number(quantity.value) || 1, selected.stok))
          : "";
        row.querySelector("[data-item-stock-hint]").textContent = selected
          ? `Stok tersedia: ${selected.stok}`
          : "Pilih barang yang tersedia.";
        row.querySelector("[data-remove-loan-item]").disabled = rows.length === 1;
      });
      addItemButton.disabled = availableItems.length <= rows.length;
    };

    const addItemRow = (itemId = null) => {
      const row = document.createElement("div");
      row.className = "loan-item-row";
      row.innerHTML = `
        <div class="form-field"><label class="field-label">Barang</label><select class="input-control" data-loan-item required><option value="">Pilih barang</option></select><div class="field-hint" data-item-stock-hint>Pilih barang yang tersedia.</div></div>
        <div class="form-field"><label class="field-label">Jumlah</label><input class="input-control" data-loan-quantity type="number" min="1" required></div>
        <button class="btn btn-danger" data-remove-loan-item type="button" aria-label="Hapus barang">Hapus</button>
      `;
      itemsContainer.append(row);
      const select = row.querySelector("[data-loan-item]");
      select.value = itemId ? String(itemId) : "";
      select.addEventListener("change", refreshItemRows);
      row.querySelector("[data-loan-quantity]").addEventListener("input", refreshItemRows);
      row.querySelector("[data-remove-loan-item]").addEventListener("click", () => {
        row.remove();
        refreshItemRows();
      });
      refreshItemRows();
    };

    const setDefaultLoanDates = () => {
      const today = new Date();
      const returnDate = new Date(today);
      returnDate.setDate(today.getDate() + 3);
      const localDate = (date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
      document.getElementById("loan-date").value = localDate(today);
      document.getElementById("loan-return-date").value = localDate(returnDate);
    };

    const open = (itemId = null) => {
      form.reset();
      itemsContainer.replaceChildren();
      setDefaultLoanDates();
      if (itemId !== null && !availableItems.some((item) => item.id === itemId)) {
        showFailure(new Error("Barang sudah tidak tersedia. Muat ulang data barang dan coba lagi."));
        return;
      }
      if (!availableItems.length) {
        showFailure(new Error("Tidak ada barang yang tersedia untuk dipinjam."));
        return;
      }
      addItemRow(itemId);
      modal.showModal();
    };

    addItemButton.addEventListener("click", () => addItemRow());
    document.getElementById("open-loan-modal")?.addEventListener("click", () => open());
    document.getElementById("cancel-loan").addEventListener("click", () => modal.close());
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const items = [...itemsContainer.querySelectorAll(".loan-item-row")].map((row) => {
        const barangId = Number(row.querySelector("[data-loan-item]").value);
        const jumlah = Number(row.querySelector("[data-loan-quantity]").value);
        return { barang_id: barangId, jumlah };
      });
      const invalidItem = items.some((requestedItem) => {
        const item = availableItems.find((available) => available.id === requestedItem.barang_id);
        return !item || requestedItem.jumlah < 1 || requestedItem.jumlah > item.stok;
      });
      if (invalidItem || new Set(items.map((item) => item.barang_id)).size !== items.length) {
        showFailure(new Error("Pilih barang yang berbeda dan jumlah yang tidak melebihi stok."));
        return;
      }
      const tanggalPinjam = document.getElementById("loan-date").value;
      const tanggalKembali = document.getElementById("loan-return-date").value;
      if (tanggalKembali < tanggalPinjam) {
        showFailure(new Error("Tanggal kembali harus sama atau setelah tanggal pinjam."));
        return;
      }

      submitButton.disabled = true;
      try {
        const createdLoan = await apiFetch("/peminjaman", {
          method: "POST",
          body: {
            items,
            tanggal_pinjam: `${tanggalPinjam}T00:00:00`,
            tanggal_kembali_rencana: `${tanggalKembali}T00:00:00`,
            keterangan: document.getElementById("loan-note").value.trim() || null,
          },
        });
        modal.close();
        form.reset();
        itemsContainer.replaceChildren();
        await onSuccess();
        window.showToast(`Pengajuan peminjaman berhasil dikirim dengan kode ${createdLoan.kode_peminjaman}.`);
      } catch (error) {
        showFailure(error);
      } finally {
        submitButton.disabled = false;
      }
    });

    return { open, setItems };
  }

  if (!token()) {
    location.replace("index.html");
    return;
  }

  async function loadDashboard() {
    const currentUser = await apiFetch("/users/me");
    api.saveUser(currentUser);
    const isAdmin = currentUser.role?.toLowerCase() === "admin";
    const [stats, items, loans] = await Promise.all([
      isAdmin ? apiFetch("/laporan/statistik") : Promise.resolve(null),
      isAdmin ? Promise.resolve(null) : apiFetch("/barang"),
      apiFetch("/peminjaman"),
    ]);
    const values = isAdmin ? {
      "admin-users": stats.total_pengguna,
      "admin-items": stats.total_barang,
      "admin-loans": stats.total_transaksi,
      "admin-pending": stats.transaksi_per_status?.Menunggu || 0,
    } : {
      "user-available": items.filter((item) => item.stok > 0).length,
      "user-loans": loans.length,
      "user-pending": loans.filter((loan) => loan.status === "Menunggu").length,
      "user-completed": loans.filter((loan) => loan.status === "Selesai" || loan.status === "Selesai - Rusak").length,
    };
    Object.entries(values).forEach(([key, value]) => {
      const node = document.querySelector(`[data-stat="${key}"]`);
      if (node) node.textContent = new Intl.NumberFormat("id-ID").format(value ?? 0);
    });
    const activityBody = document.getElementById("activity-body");
    const recent = [...loans].sort((a, b) => new Date(b.tanggal_pinjam) - new Date(a.tanggal_pinjam)).slice(0, 7);
    activityBody.innerHTML = recent.length ? recent.map((loan) => `
      <tr><td class="whitespace-nowrap">${dateText(loan.tanggal_pinjam)}</td><td>${isAdmin ? `Pengguna #${escapeHTML(loan.user_id)}` : escapeHTML(currentUser.nama_lengkap)}</td><td>Pengajuan ${escapeHTML(loan.kode_peminjaman)}</td><td>${statusTag(loan.status)}</td></tr>
    `).join("") : emptyRow(4, "Transaksi akan muncul di sini.");
    addMobileCardLabels(activityBody);
  }

  async function loadUsers() {
    const [users, query, role] = await Promise.all([
      apiFetch("/users"),
      Promise.resolve(document.getElementById("user-search")?.value.trim().toLowerCase() || ""),
      Promise.resolve(document.getElementById("user-role-filter")?.value || ""),
    ]);
    const status = document.getElementById("user-status-filter")?.value || "";
    const filtered = users.filter((user) => {
      const matchesText = !query || [user.nama_lengkap, user.username, user.email].some((value) => String(value).toLowerCase().includes(query));
      return matchesText && (!role || user.role === role) && (!status || user.status === status);
    });
    document.getElementById("user-count").textContent = `${filtered.length} pengguna`;
    document.getElementById("users-body").innerHTML = filtered.length ? filtered.map((user) => `
      <tr><td class="font-semibold">${user.id}</td><td class="font-semibold text-[#26372c]">${escapeHTML(user.nama_lengkap)}</td><td>${escapeHTML(user.role)}</td><td><div class="font-semibold">${escapeHTML(user.username)}</div><div class="mt-1 text-[11px] text-[#728078]">${escapeHTML(user.email)}</div></td><td><span class="text-[11px] tracking-widest text-[#76837a]" title="Password tidak dikirim oleh API">••••••••</span></td><td>${statusTag(user.status)}</td><td><div class="flex gap-1.5"><button class="btn-icon btn-icon-edit" type="button" data-edit-user="${user.id}" aria-label="Edit pengguna ${escapeHTML(user.nama_lengkap)}" title="Edit pengguna"><svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4Z"/></svg></button><button class="btn-icon" type="button" data-delete-user="${user.id}" aria-label="Hapus pengguna ${escapeHTML(user.nama_lengkap)}" title="Hapus pengguna"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 7h16M10 11v6m4-6v6M6 7l1 14h10l1-14M9 7V4h6v3"/></svg></button></div></td></tr>
    `).join("") : emptyRow(8, "Coba ubah filter atau kata pencarian.");
    if (filtered.length) {
      document.querySelectorAll("#users-body tr").forEach((row, index) => {
        row.insertCell(3).textContent = filtered[index].tipe_user || "—";
      });
    }
    addMobileCardLabels(document.getElementById("users-body"));
  }

  async function loadItems(selectedCategoryId = null) {
    const [items, categories, currentUser] = await Promise.all([
      apiFetch("/barang"),
      apiFetch("/kategori"),
      apiFetch("/users/me"),
    ]);
    itemCategories = categories;
    const isAdmin = currentUser.role?.toLowerCase() === "admin";
    api.saveUser(currentUser);
    const categoryNames = new Map(categories.map((category) => [category.id, category.nama_kategori]));
    const fillOptions = (select) => {
      if (!select) return;
      const selected = select.value;
      const first = select.id === "category-filter" ? '<option value="">Semua kategori</option>' : '<option value="">Pilih kategori</option>';
      select.innerHTML = first + categories.map((category) => `<option value="${category.id}">${escapeHTML(category.nama_kategori)}</option>`).join("");
      select.value = selected;
    };
    fillOptions(document.getElementById("category-filter"));
    fillOptions(document.getElementById("item-category"));
    if (selectedCategoryId !== null) {
      document.getElementById("item-category").value = String(selectedCategoryId);
    }
    const categoryList = document.getElementById("category-list");
    categoryList.innerHTML = categories.length ? categories.map((category) => `
      <span class="category-chip">${escapeHTML(category.nama_kategori)}${isAdmin ? `<button class="category-edit" type="button" data-edit-category="${category.id}" aria-label="Edit kategori ${escapeHTML(category.nama_kategori)}" title="Edit kategori"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4Z"/></svg></button><button class="category-delete" type="button" data-delete-category="${category.id}" aria-label="Hapus kategori ${escapeHTML(category.nama_kategori)}" title="Hapus kategori"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 7h16M10 11v6m4-6v6M6 7l1 14h10l1-14M9 7V4h6v3"/></svg></button>` : ""}</span>
    `).join("") : '<div class="panel-note">Belum ada kategori.</div>';
    const query = document.getElementById("item-search")?.value.trim().toLowerCase() || "";
    const categoryId = document.getElementById("category-filter")?.value || "";
    const filtered = items.filter((item) => {
      const matchesText = !query || `${item.kode_barang} ${item.nama_barang}`.toLowerCase().includes(query);
      return matchesText && (!categoryId || String(item.kategori_id) === categoryId);
    });
    document.getElementById("item-count").textContent = `${filtered.length} barang`;
    itemLoanRequestForm?.setItems(items);
    document.getElementById("items-body").innerHTML = filtered.length ? filtered.map((item) => `
      <tr><td class="font-semibold">${escapeHTML(item.kode_barang)}</td><td class="font-semibold text-[#26372c]">${escapeHTML(item.nama_barang)}</td><td>${escapeHTML(categoryNames.get(item.kategori_id) || `Kategori #${item.kategori_id}`)}</td><td>${escapeHTML(item.laboratorium)}</td><td><span class="font-display text-sm font-extrabold">${item.stok}</span></td><td>${statusTag(item.kondisi)}</td><td>${item.tahun_pengadaan ?? "—"}</td><td>${isAdmin ? `
        <div class="flex gap-1.5"><button class="btn-icon btn-icon-edit" type="button" data-edit-item="${item.id}" aria-label="Edit ${escapeHTML(item.nama_barang)}" title="Edit barang"><svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4Z"/></svg></button><button class="btn-icon" type="button" data-delete-item="${item.id}" aria-label="Hapus ${escapeHTML(item.nama_barang)}" title="Hapus barang"><svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 7h16M10 11v6m4-6v6M6 7l1 14h10l1-14M9 7V4h6v3"/></svg></button></div>
      ` : `<button class="btn btn-primary item-borrow-button" type="button" data-borrow-item="${item.id}" ${item.stok < 1 ? 'disabled title="Stok habis"' : `aria-label="Pinjam ${escapeHTML(item.nama_barang)}"`}><svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M5 12h14"/><path d="m13 6 6 6-6 6"/></svg>Pinjam</button>`}</td></tr>
      `).join("") : emptyRow(8, "Belum ada barang yang sesuai dengan pencarian.");
    addMobileCardLabels(document.getElementById("items-body"));
  }

  async function loadItemsSafely(selectedCategoryId = null) {
    try {
      await loadItems(selectedCategoryId);
    } catch (error) {
      const itemsBody = document.getElementById("items-body");
      if (itemsBody) {
        itemsBody.innerHTML = emptyRow(
          8,
          "Periksa koneksi dan akses akun, lalu coba muat ulang halaman.",
          "Inventaris gagal dimuat",
        );
      }
      throw error;
    }
  }

  async function exportLoanReceipt(button) {
    const label = button.textContent;
    button.disabled = true;
    button.textContent = "Menyiapkan PDF…";
    try {
      const blob = await apiFetch(`/peminjaman/${encodeURIComponent(button.dataset.loanReceipt)}/struk`, { responseType: "blob" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      const code = String(button.dataset.loanCode || button.dataset.loanReceipt).replace(/[^A-Za-z0-9_-]/g, "_");
      link.href = url;
      link.download = `bukti-${code}.pdf`;
      document.body.append(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 30000);
      window.showToast("Bukti PDF berhasil diekspor. Buka PDF, lalu pilih Cetak untuk mencetaknya.");
    } finally {
      button.disabled = false;
      button.textContent = label;
    }
  }

  async function loadLoans() {
    const [currentUser, items] = await Promise.all([
      apiFetch("/users/me"),
      apiFetch("/barang"),
    ]);
    const isAdmin = currentUser.role?.toLowerCase() === "admin";
    api.saveUser(currentUser);
    const users = isAdmin ? await apiFetch("/users") : [currentUser];
    const userNames = new Map(users.map((user) => [user.id, user.nama_lengkap]));
    const itemNames = new Map(items.map((item) => [item.id, item.nama_barang]));
    window.loanPageState = { currentUser, isAdmin, userNames, itemNames };
    const createButton = document.getElementById("open-loan-modal");
    if (createButton) {
      createButton.classList.toggle(
        "hidden",
        currentUser.role?.toLowerCase() !== "user",
      );
    }

    loanRequestForm?.setItems(items);

    const selectedStatus = document.getElementById("loan-status-filter")?.value || "";
    const query = selectedStatus ? `?status=${encodeURIComponent(selectedStatus)}` : "";
    const loans = await apiFetch(`/peminjaman${query}`);
    const period = document.getElementById("loan-month-filter")?.value || "all";
    const customMonth = document.getElementById("loan-custom-month")?.value || "";
    const now = new Date();
    const currentMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
    const previousDate = new Date(now.getFullYear(), now.getMonth() - 1, 1);
    const previousMonth = `${previousDate.getFullYear()}-${String(previousDate.getMonth() + 1).padStart(2, "0")}`;
    const filteredLoans = loans.filter((loan) => {
      const month = String(loan.tanggal_pinjam || "").slice(0, 7);
      if (period === "current") return month === currentMonth;
      if (period === "previous") return month === previousMonth;
      if (period === "custom") return !customMonth || month === customMonth;
      return true;
    });
    document.getElementById("loan-count").textContent = `${filteredLoans.length} transaksi`;
    document.getElementById("loans-body").innerHTML = filteredLoans.length ? filteredLoans.map((loan) => {
      const actions = [];
      if (isAdmin && loan.status === "Menunggu") {
        actions.push(`<button class="btn btn-primary" type="button" data-loan-action="approve" data-loan-id="${loan.id}">Setujui</button>`);
        actions.push(`<button class="btn btn-danger" type="button" data-loan-action="reject" data-loan-id="${loan.id}">Tolak</button>`);
      } else if (isAdmin && loan.status === "Disetujui") {
        actions.push(`<button class="btn btn-return" type="button" data-loan-action="return" data-loan-id="${loan.id}">Proses Pengembalian</button>`);
      }
      actions.push(`<button class="btn btn-quiet" type="button" data-loan-detail="${loan.id}">Lihat Detail</button>`);
      if (loan.status === "Disetujui") {
        actions.push(`<button class="btn btn-quiet" type="button" data-loan-receipt="${loan.id}" data-loan-code="${escapeHTML(loan.kode_peminjaman)}" aria-label="Cetak struk ${escapeHTML(loan.kode_peminjaman)}">Cetak Struk PDF</button>`);
      }
      const borrowerName = userNames.get(loan.user_id) || (isAdmin ? `Pengguna #${loan.user_id}` : currentUser.nama_lengkap);
      const loanItems = loan.items || [];
      const itemNamesInLoan = loanItems.map((detail) =>
        itemNames.get(detail.barang_id) || detail.barang?.nama_barang || `Barang #${detail.barang_id}`,
      );
      const itemSummary = itemNamesInLoan.length > 1
        ? `${itemNamesInLoan.length} Barang (${itemNamesInLoan.join(", ")})`
        : itemNamesInLoan[0]
          ? `${itemNamesInLoan[0]} × ${loanItems[0].jumlah}`
          : "—";
      const totalQuantity = loanItems.reduce((total, detail) => total + detail.jumlah, 0);
      const lateDays = loan.status === "Disetujui" ? lateDaysFor(loan.tanggal_kembali) : 0;
      const lateTag = lateDays ? `<span class="late-pill">Terlambat ${lateDays} hari</span>` : "";
      return `<tr><td class="font-semibold">${escapeHTML(loan.kode_peminjaman)}</td><td>${escapeHTML(borrowerName)}</td><td>${escapeHTML(itemSummary || "—")}</td><td>${totalQuantity}</td><td class="whitespace-nowrap">${dateText(loan.tanggal_pinjam)}</td><td class="whitespace-nowrap">${dateOnly(loan.tanggal_kembali)}${lateTag}</td><td>${statusTag(loan.status)}</td><td><div class="loan-action-buttons">${actions.join("")}</div></td></tr>`;
    }).join("") : emptyRow(8, "Belum ada transaksi pada filter ini.");
    addMobileCardLabels(document.getElementById("loans-body"));
  }

  let reportDates = { dari: "", sampai: "" };
  function reportQuery() {
    const params = new URLSearchParams();
    if (reportDates.dari) params.set("dari", `${reportDates.dari}T00:00:00`);
    if (reportDates.sampai) params.set("sampai", `${reportDates.sampai}T23:59:59`);
    return params.toString();
  }
  async function loadReports() {
    const suffix = reportQuery();
    const rows = await apiFetch(`/laporan/transaksi${suffix ? `?${suffix}` : ""}`);
    document.getElementById("report-count").textContent = `${rows.length} transaksi`;
    document.getElementById("reports-body").innerHTML = rows.length ? rows.map((row) => `
      <tr><td class="font-semibold">${escapeHTML(row.kode_peminjaman)}</td><td>${row.user_id}</td><td>${escapeHTML((row.items || []).map((detail) => `${detail.barang.kode_barang} / ${detail.barang.nama_barang} × ${detail.jumlah}`).join(", "))}</td><td class="whitespace-nowrap">${dateText(row.tanggal_pinjam)}</td><td class="whitespace-nowrap">${dateOnly(row.tanggal_kembali)}</td><td>${statusTag(row.status)}</td></tr>
    `).join("") : emptyRow(6, "Tidak ada transaksi pada rentang tanggal ini.");
    addMobileCardLabels(document.getElementById("reports-body"));
  }
  async function exportReport(kind) {
    const suffix = reportQuery();
    const blob = await apiFetch(`/laporan/export/${kind}${suffix ? `?${suffix}` : ""}`, { responseType: "blob" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `laporan-transaksi.${kind === "excel" ? "xlsx" : "pdf"}`;
    document.body.append(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  async function loadNotifications() {
    const notifications = await apiFetch("/notifikasi");
    const unread = notifications.filter((item) => !item.dibaca).length;
    document.getElementById("notification-count").textContent = `${notifications.length} notifikasi · ${unread} belum dibaca`;
    const list = document.getElementById("notifications-list");
    list.innerHTML = notifications.length ? notifications.map((item) => `
      <article class="flex flex-wrap items-center gap-4 border-t border-[#edf1ed] px-5 py-4 ${item.dibaca ? "bg-white" : "bg-[#fbfdf8]"}">
        <span class="grid h-10 w-10 flex-none place-items-center rounded-full ${item.dibaca ? "bg-[#eff2f0] text-[#6c7971]" : "bg-[#edf5e3] text-[#527526]"}"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9m-8 12h4"/></svg></span>
        <div class="min-w-[180px] flex-1"><div class="text-xs font-semibold text-[#34433a]">${escapeHTML(item.pesan)}</div><div class="mt-1 text-[11px] text-[#87928a]">${dateText(item.timestamp)}</div></div>
        ${item.dibaca ? '<span class="text-[11px] font-semibold text-[#87928a]">Sudah dibaca</span>' : `<button class="btn btn-quiet" type="button" data-read-notification="${item.id}">Tandai dibaca</button>`}
      </article>
    `).join("") : '<div class="empty-state"><strong>Belum ada notifikasi</strong>Pembaruan transaksi akan tampil di sini.</div>';
  }

  async function loadActivityLogs() {
    const activities = await apiFetch("/log-aktivitas");
    const category = document.getElementById("activity-category-filter").value;
    const search = document.getElementById("activity-search").value.trim().toLocaleLowerCase("id");
    const filtered = activities.filter((activity) => {
      if (category && activity.kategori !== category) return false;
      const searchable = [
        activity.admin_nama,
        activity.aksi,
        activity.kategori,
        activity.target,
        activity.detail,
        activity.ip_address,
      ].join(" ").toLocaleLowerCase("id");
      return !search || searchable.includes(search);
    });
    document.getElementById("activity-count").textContent = `${filtered.length} aktivitas`;
    document.getElementById("activity-body").innerHTML = filtered.length ? filtered.map((activity) => `
      <tr><td class="whitespace-nowrap">${dateText(activity.timestamp)}</td><td class="font-semibold">${escapeHTML(activity.admin_nama)}</td><td>${escapeHTML(activity.aksi)}</td><td>${statusTag(activity.kategori)}</td><td>${escapeHTML(activity.target || "—")}</td><td>${escapeHTML(activity.detail || "—")}</td><td>${escapeHTML(activity.ip_address || "—")}</td></tr>
    `).join("") : emptyRow(7, "Tidak ada aktivitas yang sesuai dengan filter.");
    addMobileCardLabels(document.getElementById("activity-body"));
  }

  async function loadProfile() {
    const id = currentUserId();
    if (!id) throw new Error("Sesi tidak valid. Silakan masuk kembali.");
    const user = await apiFetch("/users/me");
    api.saveUser(user);
    document.getElementById("profile-name").value = user.nama_lengkap;
    document.getElementById("profile-username").value = user.username;
    document.getElementById("profile-email").value = user.email;
    document.getElementById("profile-role").value = user.role;
    document.getElementById("profile-gender").value = user.jenis_kelamin || "Belum diisi";
    document.getElementById("profile-status").textContent = user.status;
    document.querySelectorAll("[data-profile-name]").forEach((node) => { node.textContent = user.nama_lengkap; });
    document.querySelectorAll("[data-profile-avatar]").forEach((node) => { node.textContent = (user.nama_lengkap[0] || "A").toUpperCase(); });
    document.querySelectorAll("[data-header-name], [data-sidebar-name]").forEach((node) => { node.textContent = user.nama_lengkap; });
    document.querySelectorAll("[data-sidebar-role], [data-header-role]").forEach((node) => { node.textContent = user.role; });
    document.querySelectorAll("[data-avatar]").forEach((node) => { node.textContent = (user.nama_lengkap[0] || "A").toUpperCase(); });
  }

  const initializers = {
    dashboard: () => loadDashboard().catch(showFailure),
    users: () => {
      const panel = document.getElementById("user-form-panel");
      const form = document.getElementById("user-form");
      const usernameInput = document.getElementById("user-username");
      const passwordInput = document.getElementById("user-password");
      const userRoleInput = document.getElementById("user-role");
      const userTypeInput = document.getElementById("user-type");
      const syncUserTypeInput = () => {
        if (userRoleInput.value === "Admin") userTypeInput.value = "";
        userTypeInput.disabled = userRoleInput.value === "Admin";
      };
      const resetUserForm = () => {
        editingUserId = null;
        form.reset();
        usernameInput.disabled = false;
        passwordInput.disabled = false;
        passwordInput.required = true;
        document.getElementById("user-password-label").textContent = "Password awal";
        document.getElementById("user-form-title").textContent = "Pengguna Baru";
        document.getElementById("user-submit").textContent = "Simpan Pengguna";
        syncUserTypeInput();
      };
      userRoleInput.addEventListener("change", syncUserTypeInput);
      document.querySelectorAll("[data-toggle-user-form]").forEach((button) => button.addEventListener("click", () => {
        if (!panel.classList.contains("hidden")) {
          resetUserForm();
          panel.classList.add("hidden");
        } else {
          resetUserForm();
          panel.classList.remove("hidden");
        }
      }));
      document.getElementById("user-search").addEventListener("input", () => loadUsers().catch(showFailure));
      document.getElementById("user-role-filter").addEventListener("change", () => loadUsers().catch(showFailure));
      document.getElementById("user-status-filter").addEventListener("change", () => loadUsers().catch(showFailure));
      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const wasEditing = editingUserId !== null;
        try {
          if (wasEditing) {
            await apiFetch(`/users/${editingUserId}`, {
              method: "PUT",
              body: {
                nama_lengkap: document.getElementById("user-name").value.trim(),
                email: document.getElementById("user-email").value.trim(),
                role: document.getElementById("user-role").value,
                tipe_user: document.getElementById("user-type").value || null,
                status: document.getElementById("user-status").value,
              },
            });
          } else {
            const data = formValues(form);
            data.tipe_user = data.tipe_user || null;
            await apiFetch("/users", { method: "POST", body: data });
          }
          resetUserForm();
          panel.classList.add("hidden");
          window.showToast(wasEditing ? "Data pengguna berhasil diperbarui." : "Pengguna berhasil ditambahkan.");
          await loadUsers();
        } catch (error) { showFailure(error); }
      });
      document.getElementById("users-body").addEventListener("click", async (event) => {
        const editButton = event.target.closest("[data-edit-user]");
        if (editButton) {
          try {
            const user = await apiFetch(`/users/${editButton.dataset.editUser}`);
            editingUserId = user.id;
            document.getElementById("user-name").value = user.nama_lengkap;
            usernameInput.value = user.username;
            document.getElementById("user-email").value = user.email;
            document.getElementById("user-role").value = user.role;
            document.getElementById("user-type").value = user.tipe_user || "";
            syncUserTypeInput();
            document.getElementById("user-status").value = user.status;
            usernameInput.disabled = true;
            passwordInput.value = "";
            passwordInput.required = false;
            passwordInput.disabled = true;
            document.getElementById("user-password-label").textContent = "Password (tidak dapat diubah di sini)";
            document.getElementById("user-form-title").textContent = "Edit Pengguna";
            document.getElementById("user-submit").textContent = "Update Pengguna";
            panel.classList.remove("hidden");
            panel.scrollIntoView({ behavior: "smooth", block: "start" });
          } catch (error) { showFailure(error); }
          return;
        }
        const button = event.target.closest("[data-delete-user]");
        if (!button || !window.confirm("Hapus pengguna ini?")) return;
        try {
          await apiFetch(`/users/${button.dataset.deleteUser}`, { method: "DELETE" });
          window.showToast("Pengguna berhasil dihapus.");
          await loadUsers();
        } catch (error) { showFailure(error); }
      });
      loadUsers().catch(showFailure);
    },
    items: () => {
      const panel = document.getElementById("item-form-panel");
      const form = document.getElementById("item-form");
      const excelFileInput = document.getElementById("items-excel-file");
      const uploadExcelButton = document.getElementById("upload-excel-button");
      itemLoanRequestForm = setupLoanRequestForm(() => loadItemsSafely());
      const resetItemForm = () => {
        editingItemId = null;
        form.reset();
        document.getElementById("item-form-title").textContent = "Barang Baru";
        document.getElementById("item-submit").textContent = "Simpan Barang";
      };
      const categoryModal = document.getElementById("category-modal");
      document.querySelectorAll("[data-toggle-item-form]").forEach((button) => button.addEventListener("click", () => {
        if (api.getUser()?.role?.toLowerCase() !== "admin") return;
        if (!panel.classList.contains("hidden")) {
          resetItemForm();
          panel.classList.add("hidden");
        } else {
          resetItemForm();
          panel.classList.remove("hidden");
        }
      }));
      if (location.hash === "#new-item" && api.getUser()?.role?.toLowerCase() === "admin") { panel.classList.remove("hidden"); panel.scrollIntoView({ behavior: "smooth" }); }
      document.getElementById("item-search").addEventListener("input", () => loadItemsSafely().catch(showFailure));
      document.getElementById("category-filter").addEventListener("change", () => loadItemsSafely().catch(showFailure));
      uploadExcelButton.addEventListener("click", () => {
        if (api.getUser()?.role?.toLowerCase() === "admin") excelFileInput.click();
      });
      excelFileInput.addEventListener("change", async () => {
        const file = excelFileInput.files?.[0];
        excelFileInput.value = "";
        if (!file) return;
        if (!file.name.toLowerCase().endsWith(".xlsx")) {
          showFailure(new Error("Pilih file Excel berformat .xlsx."));
          return;
        }
        const formData = new FormData();
        formData.append("file", file);
        uploadExcelButton.disabled = true;
        try {
          const result = await apiFetch("/barang/upload-excel", {
            method: "POST",
            body: formData,
          });
          await loadItemsSafely();
          const resultPanel = document.getElementById("excel-upload-result");
          const resultSummary = document.getElementById("excel-upload-summary");
          const errorList = document.getElementById("excel-upload-errors");
          resultSummary.textContent = result.message;
          errorList.replaceChildren();
          result.gagal.forEach((failure) => {
            const listItem = document.createElement("li");
            listItem.textContent = `Baris ${failure.baris}: ${failure.alasan}`;
            errorList.append(listItem);
          });
          resultPanel.classList.remove("hidden");
          window.showToast(result.message, result.jumlah_gagal ? "error" : "success");
        } catch (error) {
          showFailure(error);
        } finally {
          uploadExcelButton.disabled = false;
        }
      });
      document.getElementById("download-excel-template").addEventListener("click", async (event) => {
        if (api.getUser()?.role?.toLowerCase() !== "admin") return;
        const button = event.currentTarget;
        button.disabled = true;
        try {
          const blob = await apiFetch("/barang/template-excel", { responseType: "blob" });
          const url = URL.createObjectURL(blob);
          const link = document.createElement("a");
          link.href = url;
          link.download = "template-barang.xlsx";
          document.body.append(link);
          link.click();
          link.remove();
          window.setTimeout(() => URL.revokeObjectURL(url), 1000);
        } catch (error) {
          showFailure(error);
        } finally {
          button.disabled = false;
        }
      });
      document.getElementById("open-category-modal").addEventListener("click", () => {
        if (api.getUser()?.role?.toLowerCase() !== "admin") return;
        editingCategoryId = null;
        document.getElementById("category-form").reset();
        document.getElementById("category-modal-title").textContent = "Kategori Baru";
        document.querySelector("#category-form button[type='submit']").textContent = "Simpan";
        categoryModal.showModal();
        document.getElementById("category-name").focus();
      });
      document.getElementById("cancel-category").addEventListener("click", () => {
        editingCategoryId = null;
        categoryModal.close();
      });
      document.getElementById("category-form").addEventListener("submit", async (event) => {
        event.preventDefault();
        if (api.getUser()?.role?.toLowerCase() !== "admin") return;
        const namaKategori = document.getElementById("category-name").value.trim();
        if (!namaKategori) return;
        try {
          const wasEditing = editingCategoryId !== null;
          const category = await apiFetch(
            wasEditing ? `/kategori/${editingCategoryId}` : "/kategori",
            { method: wasEditing ? "PUT" : "POST", body: { nama_kategori: namaKategori } },
          );
          editingCategoryId = null;
          categoryModal.close();
          document.getElementById("category-modal-title").textContent = "Kategori Baru";
          document.querySelector("#category-form button[type='submit']").textContent = "Simpan";
          await loadItemsSafely(wasEditing ? null : category.id);
          window.showToast(wasEditing ? "Kategori berhasil diperbarui." : "Kategori berhasil ditambahkan.");
        } catch (error) { showFailure(error); }
      });
      document.getElementById("category-list").addEventListener("click", async (event) => {
        if (api.getUser()?.role?.toLowerCase() !== "admin") return;
        const editButton = event.target.closest("[data-edit-category]");
        if (editButton) {
          const category = itemCategories.find((item) => item.id === Number(editButton.dataset.editCategory));
          if (!category) return;
          editingCategoryId = category.id;
          document.getElementById("category-name").value = category.nama_kategori;
          document.getElementById("category-modal-title").textContent = "Edit Kategori";
          document.querySelector("#category-form button[type='submit']").textContent = "Update";
          categoryModal.showModal();
          document.getElementById("category-name").focus();
          return;
        }
        const button = event.target.closest("[data-delete-category]");
        if (!button || !window.confirm("Hapus kategori ini?")) return;
        try {
          await apiFetch(`/kategori/${button.dataset.deleteCategory}`, { method: "DELETE" });
          window.showToast("Kategori berhasil dihapus.");
          await loadItemsSafely();
        } catch (error) { showFailure(error); }
      });
      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        if (api.getUser()?.role?.toLowerCase() !== "admin") return;
        const data = formValues(event.currentTarget);
        data.kategori_id = Number(data.kategori_id);
        data.stok = Number(data.stok);
        data.tahun_pengadaan = data.tahun_pengadaan ? Number(data.tahun_pengadaan) : null;
        try {
          const wasEditing = editingItemId !== null;
          await apiFetch(wasEditing ? `/barang/${editingItemId}` : "/barang", {
            method: wasEditing ? "PUT" : "POST",
            body: data,
          });
          resetItemForm();
          panel.classList.add("hidden");
          window.showToast(wasEditing ? "Barang berhasil diperbarui." : "Barang berhasil ditambahkan.");
          await loadItemsSafely();
        } catch (error) { showFailure(error); }
      });
      document.getElementById("items-body").addEventListener("click", async (event) => {
        const borrowButton = event.target.closest("[data-borrow-item]");
        if (borrowButton) {
          if (api.getUser()?.role?.toLowerCase() !== "admin") {
            itemLoanRequestForm.open(Number(borrowButton.dataset.borrowItem));
          }
          return;
        }
        if (api.getUser()?.role?.toLowerCase() !== "admin") return;
        const editButton = event.target.closest("[data-edit-item]");
        if (editButton) {
          try {
            const item = await apiFetch(`/barang/${editButton.dataset.editItem}`);
            editingItemId = item.id;
            document.getElementById("item-code").value = item.kode_barang;
            document.getElementById("item-name").value = item.nama_barang;
            document.getElementById("item-category").value = String(item.kategori_id);
            document.getElementById("item-lab").value = item.laboratorium;
            document.getElementById("item-stock").value = item.stok;
            document.getElementById("item-condition").value = item.kondisi;
            document.getElementById("item-year").value = item.tahun_pengadaan ?? "";
            document.getElementById("item-form-title").textContent = "Edit Barang";
            document.getElementById("item-submit").textContent = "Update Barang";
            panel.classList.remove("hidden");
            panel.scrollIntoView({ behavior: "smooth", block: "start" });
          } catch (error) { showFailure(error); }
          return;
        }
        const button = event.target.closest("[data-delete-item]");
        if (!button || !window.confirm("Hapus barang ini? Barang dengan riwayat peminjaman tidak dapat dihapus.")) return;
        try {
          await apiFetch(`/barang/${button.dataset.deleteItem}`, { method: "DELETE" });
          window.showToast("Barang berhasil dihapus.");
          await loadItemsSafely();
        } catch (error) { showFailure(error); }
      });
      loadItemsSafely().catch(showFailure);
    },
    loans: () => {
      const detailModal = document.getElementById("loan-detail-modal");
      const receiptButton = document.getElementById("export-loan-receipt");
      receiptButton.addEventListener("click", () => {
        if (receiptButton.classList.contains("hidden")) return;
        exportLoanReceipt(receiptButton).catch(showFailure);
      });
      const returnModal = document.getElementById("loan-return-modal");
      const returnForm = document.getElementById("loan-return-form");
      const returnCondition = document.getElementById("loan-return-condition");
      const returnNote = document.getElementById("loan-return-note");
      const returnQuantity = document.getElementById("loan-return-quantity");
      let returnLoanId = null;
      let returnMaxQuantity = 0;
      let returnMultiItem = false;
      loanRequestForm = setupLoanRequestForm(() => loadLoans());
      const syncReturnNoteRequirement = () => {
        const required = returnCondition.value !== "Baik";
        returnNote.required = required;
        document.getElementById("loan-return-note-required").textContent = required
          ? "(wajib)"
          : "(opsional)";
      };
      const openReturnModal = async (loanId) => {
        const loan = await apiFetch(`/peminjaman/${loanId}`);
        const state = window.loanPageState;
        if (!state?.isAdmin || loan.status !== "Disetujui") {
          throw new Error("Hanya Admin yang dapat memproses transaksi yang disetujui.");
        }
        returnLoanId = loan.id;
        const loanItems = loan.items || [];
        returnMaxQuantity = loanItems.reduce((total, item) => total + item.jumlah, 0);
        returnMultiItem = loanItems.length > 1;
        returnQuantity.max = String(returnMaxQuantity);
        returnQuantity.value = String(returnMaxQuantity);
        returnCondition.value = "Baik";
        returnNote.value = "";
        syncReturnNoteRequirement();
        const borrowerName = state.userNames.get(loan.user_id) || `Pengguna #${loan.user_id}`;
        const itemSummary = loanItems.map((detail) => {
          const itemName = state.itemNames.get(detail.barang_id) || detail.barang?.nama_barang || `Barang #${detail.barang_id}`;
          return `${itemName} × ${detail.jumlah}`;
        }).join(", ");
        const summary = [
          ["Nama Peminjam", borrowerName],
          ["Barang dan jumlah", itemSummary],
          ["Jumlah total dipinjam", returnMaxQuantity],
          ["Tanggal Pinjam", dateText(loan.tanggal_pinjam)],
          ["Jatuh Tempo", dateOnly(loan.tanggal_kembali)],
        ];
        document.getElementById("loan-return-summary").innerHTML = summary.map(([label, value]) => `
          <div class="loan-detail-item"><dt>${escapeHTML(label)}</dt><dd>${escapeHTML(value)}</dd></div>
        `).join("");
        const lateDays = lateDaysFor(loan.tanggal_kembali);
        const lateInfo = document.getElementById("loan-return-late");
        lateInfo.textContent = lateDays > 0
          ? `Terlambat ${lateDays} hari`
          : "Tidak terlambat";
        lateInfo.classList.toggle("is-late", lateDays > 0);
        returnModal.showModal();
      };
      document.getElementById("loan-status-filter").addEventListener("change", () => loadLoans().catch(showFailure));
      document.getElementById("loan-month-filter").addEventListener("change", (event) => {
        document.getElementById("custom-month-wrap").classList.toggle("hidden", event.currentTarget.value !== "custom");
        loadLoans().catch(showFailure);
      });
      document.getElementById("loan-custom-month").addEventListener("input", () => loadLoans().catch(showFailure));
      document.getElementById("loans-body").addEventListener("click", async (event) => {
        const exportButton = event.target.closest("[data-loan-receipt]");
        if (exportButton) {
          try { await exportLoanReceipt(exportButton); }
          catch (error) { showFailure(error); }
          return;
        }
        const detailButton = event.target.closest("[data-loan-detail]");
        if (detailButton) {
          try {
            const loan = await apiFetch(`/peminjaman/${detailButton.dataset.loanDetail}`);
            const state = window.loanPageState;
            const loanItems = loan.items || [];
            const itemSummary = loanItems.map((detail) => {
              const itemName = state.itemNames.get(detail.barang_id) || detail.barang?.nama_barang || `Barang #${detail.barang_id}`;
              return `${itemName} × ${detail.jumlah} (${detail.kondisi_saat_pinjam})`;
            }).join("; ");
            const fields = [
              ["Kode Transaksi", loan.kode_peminjaman],
              ["Peminjam", state.userNames.get(loan.user_id) || state.currentUser.nama_lengkap || `Pengguna #${loan.user_id}`],
              ["Barang dan jumlah", itemSummary, true],
              ["Jumlah total", loanItems.reduce((total, item) => total + item.jumlah, 0)],
              ["Tanggal Pinjam", dateText(loan.tanggal_pinjam)],
              ["Tanggal Kembali", dateText(loan.tanggal_kembali)],
              ["Status", loan.status],
              ["Keterangan", loan.keterangan || "Tidak ada keterangan", true],
            ];
            if (loan.jumlah_kembali !== null) {
              fields.push(
                ["Kondisi Kembali", loan.kondisi_kembali],
                ["Jumlah Diterima", loan.jumlah_kembali],
                ["Tanggal Kembali Aktual", dateText(loan.tanggal_kembali_aktual)],
                ["Terlambat", `${loan.terlambat_hari} hari`],
                ["Denda", new Intl.NumberFormat("id-ID").format(loan.denda || 0)],
                ["Catatan Admin", loan.catatan_admin || "Tidak ada catatan", true],
              );
            }
            document.getElementById("loan-detail-content").innerHTML = fields.map(([label, value, full]) => `
              <div class="loan-detail-item ${full ? "full" : ""}"><dt>${escapeHTML(label)}</dt><dd>${escapeHTML(value)}</dd></div>
            `).join("");
            receiptButton.dataset.loanReceipt = String(loan.id);
            receiptButton.dataset.loanCode = loan.kode_peminjaman;
            const canPrintReceipt = loan.status === "Disetujui";
            receiptButton.hidden = !canPrintReceipt;
            receiptButton.classList.toggle("hidden", !canPrintReceipt);
            detailModal.showModal();
          } catch (error) { showFailure(error); }
          return;
        }
        const button = event.target.closest("[data-loan-action]");
        if (!button) return;
        const action = button.dataset.loanAction;
        if (!window.loanPageState?.isAdmin) return;
        if (action === "return") {
          try { await openReturnModal(button.dataset.loanId); }
          catch (error) { showFailure(error); }
          return;
        }
        const labels = { approve: "setujui", reject: "tolak" };
        if (!window.confirm(`Yakin ingin ${labels[action]}?`)) return;
        button.disabled = true;
        try {
          await apiFetch(`/peminjaman/${button.dataset.loanId}/${action}`, { method: "PUT" });
          window.showToast("Status transaksi berhasil diperbarui.");
          await loadLoans();
        } catch (error) { showFailure(error); button.disabled = false; }
      });
      returnCondition.addEventListener("change", syncReturnNoteRequirement);
      document.getElementById("cancel-loan-return").addEventListener("click", () => returnModal.close());
      returnForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        const jumlahKembali = Number(returnQuantity.value);
        if (!returnLoanId || jumlahKembali < 0 || jumlahKembali > Number(returnQuantity.max)) {
          showFailure(new Error("Jumlah diterima tidak valid."));
          return;
        }
        if (returnCondition.value !== "Hilang" && jumlahKembali === 0) {
          showFailure(new Error("Jumlah diterima harus lebih dari 0 kecuali barang hilang."));
          return;
        }
        if (returnCondition.value === "Hilang" && jumlahKembali !== 0) {
          showFailure(new Error("Jumlah diterima harus 0 jika semua barang ditandai hilang."));
          return;
        }
        if (returnMultiItem && returnCondition.value !== "Hilang" && jumlahKembali !== returnMaxQuantity) {
          showFailure(new Error("Semua barang dalam transaksi multi-item harus dikembalikan sekaligus."));
          return;
        }
        if (returnNote.required && !returnNote.value.trim()) {
          showFailure(new Error("Catatan wajib diisi jika kondisi bukan Baik."));
          return;
        }
        const submitButton = document.getElementById("confirm-loan-return");
        submitButton.disabled = true;
        try {
          await apiFetch(`/peminjaman/${returnLoanId}/return`, {
            method: "PUT",
            body: {
              jumlah_kembali: jumlahKembali,
              kondisi_kembali: returnCondition.value,
              catatan_admin: returnNote.value.trim() || null,
            },
          });
          returnModal.close();
          returnLoanId = null;
          window.showToast("Pengembalian berhasil dicatat.");
          await loadLoans();
        } catch (error) {
          showFailure(error);
        } finally {
          submitButton.disabled = false;
        }
      });
      document.getElementById("close-loan-detail").addEventListener("click", () => detailModal.close());
      loadLoans().catch(showFailure);
    },
    reports: () => {
      document.getElementById("report-filter").addEventListener("submit", (event) => {
        event.preventDefault();
        reportDates = { dari: document.getElementById("report-from").value, sampai: document.getElementById("report-to").value };
        if (reportDates.dari && reportDates.sampai && reportDates.dari > reportDates.sampai) {
          window.showToast("Tanggal awal harus sebelum tanggal akhir.", "error");
          return;
        }
        loadReports().catch(showFailure);
      });
      document.querySelectorAll("[data-export]").forEach((button) => button.addEventListener("click", async () => {
        try { await exportReport(button.dataset.export); }
        catch (error) { showFailure(error); }
      }));
      loadReports().catch(showFailure);
    },
    notifications: () => {
      document.getElementById("refresh-notifications").addEventListener("click", () => loadNotifications().catch(showFailure));
      document.getElementById("notifications-list").addEventListener("click", async (event) => {
        const button = event.target.closest("[data-read-notification]");
        if (!button) return;
        try {
          await apiFetch(`/notifikasi/${button.dataset.readNotification}/read`, { method: "PUT" });
          await loadNotifications();
        } catch (error) { showFailure(error); }
      });
      loadNotifications().catch(showFailure);
    },
    activity: () => {
      document.getElementById("activity-category-filter").addEventListener("change", () => loadActivityLogs().catch(showFailure));
      document.getElementById("activity-search").addEventListener("input", () => loadActivityLogs().catch(showFailure));
      loadActivityLogs().catch(showFailure);
    },
    profile: () => {
      loadProfile().catch(showFailure);
      document.getElementById("profile-form").addEventListener("submit", async (event) => {
        event.preventDefault();
        try {
          await apiFetch("/users/me/username", {
            method: "PUT",
            body: {
              new_username: document.getElementById("profile-username").value.trim(),
            },
          });
          await loadProfile();
          window.showToast("Username berhasil diperbarui.");
        } catch (error) { showFailure(error); }
      });
      const passwordModal = document.getElementById("change-password-modal");
      const passwordForm = document.getElementById("change-password-form");
      document.getElementById("open-password-modal").addEventListener("click", () => {
        passwordModal.showModal();
        document.getElementById("password-current").focus();
      });
      document.getElementById("cancel-password-change").addEventListener("click", () => passwordModal.close());
      passwordModal.addEventListener("close", () => passwordForm.reset());
      passwordForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        const passwordBaru = document.getElementById("password-new").value;
        const konfirmasi = document.getElementById("password-confirm").value;
        if (passwordBaru !== konfirmasi) {
          window.showToast("Konfirmasi password baru tidak cocok.", "error");
          document.getElementById("password-confirm").focus();
          return;
        }
        const submitButton = document.getElementById("submit-password-change");
        submitButton.disabled = true;
        try {
          await apiFetch("/users/me/password", {
            method: "PUT",
            body: {
              password_lama: document.getElementById("password-current").value,
              password_baru: passwordBaru,
            },
          });
          passwordModal.close();
          window.showToast("Password berhasil diperbarui.");
        } catch (error) {
          showFailure(error);
        } finally {
          submitButton.disabled = false;
        }
      });
    },
  };

  initializers[page]?.();
})();
