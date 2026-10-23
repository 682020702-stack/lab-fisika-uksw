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

   Untuk Gmail, gunakan App Password, bukan password akun utama. Jika variabel
   SMTP belum diatur, pendaftaran akan ditolak dan backend melaporkan bahwa
   konfigurasi email belum siap.

   Pada halaman login, pilih "Lupa Password?" dan masukkan email akun. Buka link
   reset yang dikirim ke inbox; token berlaku 15 menit dan hanya dapat digunakan
   sekali. Untuk pengujian lokal, gunakan inbox Mailtrap dan pastikan URL reset
   di atas mengarah ke frontend yang sedang dijalankan. Ganti nilai placeholder
   SMTP di file `.env` dengan kredensial inbox Mailtrap sebelum tes.

   Skema database lama akan ditambah kolom verifikasi otomatis saat backend
   dijalankan. File database tidak perlu dihapus.

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
