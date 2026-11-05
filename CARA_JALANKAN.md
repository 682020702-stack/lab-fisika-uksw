============================================================
  CARA JALANKAN SISTEM LABORATORIUM FISIKA UKSW
============================================================

PRASYARAT:
- Python 3.10 atau lebih baru sudah terinstal di komputer
- Koneksi internet (untuk install library pertama kali)

LANGKAH-LANGKAH:

1. EKSTRAK FILE ZIP
   Ekstrak file lab-fisika-uksw.zip ke folder pilihanmu.
   Misalnya: C:\Users\Namamu\Documents\lab-fisika-uksw

2. BUKA TERMINAL DI FOLDER ITU
   - Buka File Explorer, masuk ke folder lab-fisika-uksw
   - Klik kanan di area kosong -> "Open in Terminal"
     (Atau: Shift + Klik Kanan -> "Open PowerShell window here")

3. BUAT VIRTUAL ENVIRONMENT
   Ketik perintah ini, lalu Enter:

   python -m venv .venv

4. AKTIFKAN VIRTUAL ENVIRONMENT

   .venv\Scripts\Activate.ps1

5. INSTALL LIBRARY

   pip install -r requirements.txt

   Tunggu sampai selesai (~2-3 menit).

6. JALANKAN BACKEND

   python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8081 --no-use-colors

   Tunggu sampai muncul pesan:
   INFO:     Application startup complete.
   
   BIARKAN TERMINAL INI TETAP TERBUKA.

7. BUKA APLIKASI DI BROWSER
   Buka browser, akses:

   http://127.0.0.1:8081/

   Halaman login akan muncul.

   Pengguna baru dapat mendaftar melalui tautan "Daftar di sini". Untuk
   mengirim email verifikasi, atur variabel lingkungan berikut sebelum
   menjalankan backend:

   - SMTP_HOST (contoh: smtp.gmail.com atau sandbox.smtp.mailtrap.io)
   - SMTP_PORT (default: 587)
   - SMTP_USERNAME
   - SMTP_PASSWORD
   - SMTP_FROM_EMAIL (alamat pengirim)
   - VERIFICATION_BASE_URL (default: http://127.0.0.1:8081/verify.html)
   - RESET_PASSWORD_BASE_URL (default: http://127.0.0.1:8081/reset-password.html)
   - SCHEDULER_TIMEZONE (default: Asia/Jakarta)

   Untuk Gmail, gunakan App Password, bukan password akun utama. Jika variabel
   SMTP belum diatur, pendaftaran akan ditolak dan backend melaporkan bahwa
   konfigurasi email belum siap.

   Pada halaman login, pilih "Lupa Password?" dan masukkan email akun. Buka link
   reset yang dikirim ke inbox; token berlaku 15 menit dan hanya dapat digunakan
   sekali. Untuk pengujian lokal, gunakan inbox Mailtrap dan pastikan URL reset
   di atas mengarah ke frontend yang sedang dijalankan. Ganti nilai placeholder
   SMTP di file `.env` dengan kredensial inbox Mailtrap sebelum tes.

   Scheduler pengingat berjalan setiap hari pukul 08:00 pada zona waktu di
   `SCHEDULER_TIMEZONE`, kecuali `ENVIRONMENT=development`. Untuk menjalankan
   pemeriksaan secara manual dari folder proyek, gunakan:

   `python -m backend.scheduler`

   Perintah tersebut memproses tanggal hari ini, menyimpan notifikasi in-app,
   dan mencoba mengirim email sungguhan. Pastikan SMTP telah dikonfigurasi dan
   gunakan data peminjaman uji dengan status `Disetujui`, tanggal kembali besok
   atau yang sudah lewat. Pengingat yang sama tidak dikirim ulang pada hari
   yang sama. Email yang gagal dicatat di log; notifikasi in-app tetap tersimpan.

   Skema database lama akan dimigrasikan otomatis saat backend dijalankan.
   Riwayat peminjaman lama disalin ke detail barang sebelum kolom barang dan
   jumlah lama dihapus dari header transaksi. Sebelum peningkatan pertama,
   cadangkan file `backend\laboratorium.db`; file database tidak perlu dihapus.
   Karena skema lama tidak menyimpan kondisi historis barang, detail migrasi
   memakai kondisi barang yang tercatat saat migrasi sebagai snapshot awal.

   Satu transaksi dapat mencakup beberapa barang. Pengembalian untuk transaksi
   multi-item harus dilakukan sekaligus; pengembalian sebagian tetap didukung
   untuk transaksi yang hanya berisi satu barang.

   Secara default, aplikasi lokal menggunakan SQLite di
   `backend\laboratorium.db`. Untuk production, atur `DATABASE_URL` pada
   environment service Render ke connection string PostgreSQL Neon. Aplikasi
   dan script admin akan menggunakan database tersebut; script menolak berjalan
   pada SQLite jika `ENVIRONMENT=production`.

   Untuk menyalin data SQLite lokal ke Neon:
   - Simpan connection string Neon sebagai `DATABASE_URL` di file `.env` pada
     folder proyek, atau atur environment variable tersebut di terminal.
   - Pastikan `.env` tidak dibagikan atau dimasukkan ke Git.
   - Dari folder proyek, jalankan `python backend\migrate_to_neon.py`.
   - Script membuat tabel yang belum ada dan menyalin data secara berurutan.
     Baris identik yang sudah ada dilewati; konflik dan pelanggaran foreign key
     dilaporkan dan menyebabkan exit code gagal agar dapat diperbaiki sebelum
     script dijalankan kembali.
   - File `backend\laboratorium.db` tidak diubah atau dihapus. Simpan file itu
     sampai hasil migrasi dan aplikasi di Neon sudah diverifikasi.

   Untuk membuat backup SQL mandiri dari Neon:
   - Pastikan `DATABASE_URL` di `.env` menunjuk ke Neon.
   - Dari folder proyek, jalankan `python backend\backup_neon.py`.
   - Script memakai engine SQLAlchemy aplikasi untuk membaca data, jadi tidak
     memerlukan `pg_dump` atau instalasi PostgreSQL Client.
   - Script menulis `INSERT` untuk tabel users, kategori_barang, barang,
     peminjaman, detail_peminjaman, log_aktivitas, dan notifikasi. File dibuat
     di folder `backup\` dengan nama `backup_neon_YYYY-MM-DD_HH-MM-SS.sql`;
     hasil backup tanpa baris data tidak akan disimpan.
   - Untuk memulihkan backup, jalankan file SQL pada database dengan skema
     aplikasi yang sama. Jalankan pada database kosong agar tidak terjadi
     konflik primary key.
   - Upload file tersebut ke Google Drive setelah memastikan pesan backup
     berhasil dan jumlah baris lebih dari nol.

   Untuk membuat Admin pertama secara manual di Render:
   - Pastikan `DATABASE_URL` service Render sudah menunjuk ke database Neon
     production dan `ENVIRONMENT=production`.
   - Buka Shell service Render, lalu jalankan dari folder proyek (yang berisi
     folder `backend`): `python -m backend.create_admin`
   - Isi username, nama lengkap, email, dan password pada prompt. Password
     diminta secara tersembunyi; konfirmasi pembuatan dengan mengetik `buat`.
   - Script hanya membuat Admin pertama. Jika Admin sudah ada, script akan
     berhenti tanpa membuat akun tambahan. Jangan menaruh password di source
     code atau command line.

8. LOGIN
   - Admin:      username=admin       password=admin123
   - Mahasiswa:  username=mahasiswa1  password=mhs12345
   - Dosen:      username=dosen1      password=dosen123

============================================================
  TROUBLESHOOTING
============================================================

Q: "python is not recognized"
A: Python belum terinstal atau belum masuk PATH.
   Download dari python.org/downloads
   Saat install, CENTANG "Add Python to PATH".

Q: "cannot be loaded because running scripts is disabled"
A: Jalankan dulu:
   Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
   Ketik Y, lalu Enter.

Q: "port 8000 already in use"
A: Tutup aplikasi lain yang pakai port 8000. Atau jalankan:
   uvicorn backend.main:app --reload --port 8001

Q: Halaman putih / tidak bisa dibuka
A: Pastikan backend masih jalan. Cek terminal, harus ada 
   "Application startup complete".

============================================================
  SELESAI
============================================================
