from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


def _default_tipe_user(context) -> str | None:
    if context.get_current_parameters().get("role") == "Admin":
        return None
    return "Umum"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('Admin', 'User')", name="ck_users_role"),
        CheckConstraint(
            "tipe_user IS NULL OR tipe_user IN ('Mahasiswa', 'Dosen', 'Umum')",
            name="ck_users_tipe_user",
        ),
        CheckConstraint(
            "role = 'User' OR tipe_user IS NULL",
            name="ck_users_admin_without_tipe_user",
        ),
        CheckConstraint("status IN ('Aktif', 'Pending')", name="ck_users_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    nama_lengkap: Mapped[str] = mapped_column(String(150))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    jenis_kelamin: Mapped[str | None] = mapped_column(String(20), nullable=True)
    role: Mapped[str] = mapped_column(String(30), default="User")
    tipe_user: Mapped[str | None] = mapped_column(
        String(30), default=_default_tipe_user, nullable=True
    )
    status: Mapped[str] = mapped_column(String(30), default="Aktif")
    is_verified: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )
    verification_token: Mapped[str | None] = mapped_column(
        String(255), unique=True, index=True, nullable=True
    )
    verification_token_expires: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    reset_token: Mapped[str | None] = mapped_column(
        String(255), unique=True, index=True, nullable=True
    )
    reset_token_expires: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )

    peminjaman: Mapped[list["Peminjaman"]] = relationship(
        back_populates="user", foreign_keys="Peminjaman.user_id"
    )
    peminjaman_diproses: Mapped[list["Peminjaman"]] = relationship(
        back_populates="pemroses", foreign_keys="Peminjaman.diproses_oleh"
    )
    log_aktivitas: Mapped[list["LogAktivitas"]] = relationship(
        back_populates="admin", foreign_keys="LogAktivitas.admin_id"
    )
    notifikasi: Mapped[list["Notifikasi"]] = relationship(back_populates="user")


class KategoriBarang(Base):
    __tablename__ = "kategori_barang"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    nama_kategori: Mapped[str] = mapped_column(String(100), unique=True, index=True)

    barang: Mapped[list["Barang"]] = relationship(back_populates="kategori")


class Barang(Base):
    __tablename__ = "barang"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    kode_barang: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    nama_barang: Mapped[str] = mapped_column(String(150), index=True)
    kategori_id: Mapped[int] = mapped_column(ForeignKey("kategori_barang.id"))
    laboratorium: Mapped[str] = mapped_column(String(100))
    stok: Mapped[int] = mapped_column(Integer, default=0)
    kondisi: Mapped[str] = mapped_column(String(50), default="Baik")
    tahun_pengadaan: Mapped[int | None] = mapped_column(Integer, nullable=True)

    kategori: Mapped["KategoriBarang"] = relationship(back_populates="barang")
    detail_peminjaman: Mapped[list["DetailPeminjaman"]] = relationship(
        back_populates="barang"
    )


class Peminjaman(Base):
    __tablename__ = "peminjaman"
    __table_args__ = (
        CheckConstraint(
            "status IN ('Menunggu', 'Disetujui', 'Ditolak', 'Selesai', 'Selesai - Rusak')",
            name="ck_peminjaman_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    kode_peminjaman: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    tanggal_pinjam: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    tanggal_kembali: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="Menunggu")
    keterangan: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    kondisi_kembali: Mapped[str | None] = mapped_column(String(50), nullable=True)
    jumlah_kembali: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tanggal_kembali_aktual: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    catatan_admin: Mapped[str | None] = mapped_column(Text, nullable=True)
    terlambat_hari: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    denda: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    diproses_oleh: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    user: Mapped["User"] = relationship(
        back_populates="peminjaman", foreign_keys=[user_id]
    )
    pemroses: Mapped["User | None"] = relationship(
        back_populates="peminjaman_diproses", foreign_keys=[diproses_oleh]
    )
    items: Mapped[list["DetailPeminjaman"]] = relationship(
        back_populates="peminjaman", cascade="all, delete-orphan"
    )


class DetailPeminjaman(Base):
    __tablename__ = "detail_peminjaman"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    peminjaman_id: Mapped[int] = mapped_column(
        ForeignKey("peminjaman.id", ondelete="CASCADE")
    )
    barang_id: Mapped[int] = mapped_column(ForeignKey("barang.id"))
    jumlah: Mapped[int] = mapped_column(Integer)
    kondisi_saat_pinjam: Mapped[str] = mapped_column(String(50))

    peminjaman: Mapped["Peminjaman"] = relationship(back_populates="items")
    barang: Mapped["Barang"] = relationship(back_populates="detail_peminjaman")


class LogAktivitas(Base):
    __tablename__ = "log_aktivitas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    admin_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    admin_nama: Mapped[str] = mapped_column(String(150))
    aksi: Mapped[str] = mapped_column(String(100))
    kategori: Mapped[str] = mapped_column(String(50))
    target: Mapped[str | None] = mapped_column(String(255), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    admin: Mapped["User"] = relationship(
        back_populates="log_aktivitas", foreign_keys=[admin_id]
    )


class Notifikasi(Base):
    __tablename__ = "notifikasi"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    pesan: Mapped[str] = mapped_column(String(500))
    dibaca: Mapped[bool] = mapped_column(default=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="notifikasi")
