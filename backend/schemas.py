from datetime import datetime
from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=128)


class ChangePasswordRequest(BaseModel):
    password_lama: str = Field(min_length=1, max_length=128)
    password_baru: str = Field(min_length=8, max_length=128)


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=8, max_length=128)
    nama_lengkap: str = Field(min_length=1, max_length=150)
    email: str = Field(
        min_length=3,
        max_length=255,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    )
    tipe_user: Literal["Mahasiswa", "Dosen", "Umum"] = "Umum"
    jenis_kelamin: Literal["Laki-laki", "Perempuan"] | None = None


class UserRegisterPublic(RegisterRequest):
    pass


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=1)


class ForgotPasswordRequest(BaseModel):
    email: str = Field(
        min_length=3,
        max_length=255,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    )


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=1, max_length=255)
    new_password: str = Field(min_length=8, max_length=128)


class LoginUserResponse(BaseModel):
    id: int
    username: str
    nama_lengkap: str
    role: Literal["Admin", "User"]
    tipe_user: Literal["Mahasiswa", "Dosen", "Umum"] | None
    jenis_kelamin: Literal["Laki-laki", "Perempuan"] | None = None


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: LoginUserResponse


class UserCreate(RegisterRequest):
    role: Literal["Admin", "User"] = "User"
    tipe_user: Literal["Mahasiswa", "Dosen", "Umum"] | None = None
    status: Literal["Aktif", "Pending"] = "Aktif"

    @model_validator(mode="after")
    def validate_user_type(self):
        if self.role == "Admin" and self.tipe_user is not None:
            raise ValueError("Admin tidak boleh memiliki tipe_user")
        return self


class UserUpdate(BaseModel):
    nama_lengkap: str | None = Field(default=None, min_length=1, max_length=150)
    email: str | None = Field(default=None, min_length=3, max_length=255)
    role: Literal["Admin", "User"] | None = None
    tipe_user: Literal["Mahasiswa", "Dosen", "Umum"] | None = None
    status: Literal["Aktif", "Pending"] | None = None


class UserResponse(ORMModel):
    id: int
    username: str
    nama_lengkap: str
    email: str
    jenis_kelamin: Literal["Laki-laki", "Perempuan"] | None = None
    role: Literal["Admin", "User"]
    tipe_user: Literal["Mahasiswa", "Dosen", "Umum"] | None
    status: Literal["Aktif", "Pending"]


class UsernameUpdate(BaseModel):
    new_username: str = Field(min_length=3, max_length=100)


class KategoriBarangCreate(BaseModel):
    nama_kategori: str = Field(min_length=1, max_length=100)


class KategoriBarangUpdate(BaseModel):
    nama_kategori: str = Field(min_length=1, max_length=100)


class KategoriBarangResponse(ORMModel):
    id: int
    nama_kategori: str


class BarangCreate(BaseModel):
    kode_barang: str = Field(min_length=1, max_length=50)
    nama_barang: str = Field(min_length=1, max_length=150)
    kategori_id: int = Field(gt=0)
    laboratorium: str = Field(min_length=1, max_length=100)
    stok: int = Field(default=0, ge=0)
    kondisi: str = Field(default="Baik", max_length=50)
    tahun_pengadaan: int | None = Field(default=None, ge=1, le=9999)


class BarangUpdate(BaseModel):
    kode_barang: str | None = Field(default=None, min_length=1, max_length=50)
    nama_barang: str | None = Field(default=None, min_length=1, max_length=150)
    kategori_id: int | None = Field(default=None, gt=0)
    laboratorium: str | None = Field(default=None, min_length=1, max_length=100)
    stok: int | None = Field(default=None, ge=0)
    kondisi: str | None = Field(default=None, max_length=50)
    tahun_pengadaan: int | None = Field(default=None, ge=1, le=9999)


class BarangResponse(ORMModel):
    id: int
    kode_barang: str
    nama_barang: str
    kategori_id: int
    laboratorium: str
    stok: int
    kondisi: str
    tahun_pengadaan: int | None


class PeminjamanItemCreate(BaseModel):
    barang_id: int = Field(gt=0)
    jumlah: int = Field(gt=0)


class PeminjamanCreate(BaseModel):
    items: list[PeminjamanItemCreate] = Field(min_length=1)
    tanggal_pinjam: datetime | None = None
    tanggal_kembali: datetime | None = Field(
        default=None,
        validation_alias=AliasChoices("tanggal_kembali_rencana", "tanggal_kembali"),
    )
    keterangan: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_unique_items(self):
        barang_ids = [item.barang_id for item in self.items]
        if len(barang_ids) != len(set(barang_ids)):
            raise ValueError("Barang yang sama tidak boleh dicantumkan lebih dari sekali")
        return self


class PeminjamanReturn(BaseModel):
    jumlah_kembali: int = Field(ge=0)
    kondisi_kembali: Literal["Baik", "Rusak Ringan", "Rusak Berat", "Hilang"]
    catatan_admin: str | None = Field(default=None, max_length=2000)


class DetailPeminjamanResponse(ORMModel):
    id: int
    barang_id: int
    jumlah: int
    kondisi_saat_pinjam: str
    barang: BarangResponse


class PeminjamanResponse(ORMModel):
    id: int
    kode_peminjaman: str
    user_id: int
    items: list[DetailPeminjamanResponse]
    tanggal_pinjam: datetime
    tanggal_kembali: datetime | None
    status: Literal["Menunggu", "Disetujui", "Ditolak", "Selesai", "Selesai - Rusak"]
    keterangan: str | None
    kondisi_kembali: str | None
    jumlah_kembali: int | None
    tanggal_kembali_aktual: datetime | None
    catatan_admin: str | None
    terlambat_hari: int
    denda: int
    diproses_oleh: int | None


class LogAktivitasResponse(ORMModel):
    id: int
    admin_id: int
    admin_nama: str
    aksi: str
    kategori: str
    target: str | None
    detail: str | None
    ip_address: str | None
    timestamp: datetime


class NotifikasiResponse(ORMModel):
    id: int
    user_id: int
    pesan: str
    dibaca: bool
    timestamp: datetime
