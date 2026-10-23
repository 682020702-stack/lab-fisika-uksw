import re
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.auth import get_admin_user, get_current_user
from backend.database import get_db
from backend.models import Barang, Notifikasi, Peminjaman, User
from backend.receipts import build_loan_receipt
from backend.schemas import PeminjamanCreate, PeminjamanResponse, PeminjamanReturn
from backend.utils import log_aktivitas

router = APIRouter(prefix="/peminjaman", tags=["Peminjaman"])


def _generate_kode_peminjaman(db: Session, tanggal_pinjam: datetime) -> str:
    date_prefix = f"PJM-{tanggal_pinjam:%Y%m%d}-"
    existing_codes = (
        db.query(Peminjaman.kode_peminjaman)
        .filter(Peminjaman.kode_peminjaman.like(f"{date_prefix}%"))
        .all()
    )
    sequences = (
        int(match.group(1))
        for (code,) in existing_codes
        if (match := re.fullmatch(r"PJM-\d{8}-(\d+)", code))
    )
    next_sequence = max(sequences, default=0) + 1
    return f"{date_prefix}{next_sequence:04d}"


def _buat_notifikasi(db: Session, user_id: int, pesan: str) -> None:
    db.add(Notifikasi(user_id=user_id, pesan=pesan))


def _get_peminjaman(db: Session, peminjaman_id: int) -> Peminjaman:
    peminjaman = db.get(Peminjaman, peminjaman_id)
    if peminjaman is None:
        raise HTTPException(status_code=404, detail="Transaksi tidak ditemukan")
    return peminjaman


@router.get("", response_model=list[PeminjamanResponse])
def list_peminjaman(
    status_transaksi: str | None = Query(default=None, alias="status", min_length=1),
    user_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Peminjaman]:
    query = db.query(Peminjaman)
    if current_user.role.casefold() != "admin":
        query = query.filter(Peminjaman.user_id == current_user.id)
    elif user_id is not None:
        query = query.filter(Peminjaman.user_id == user_id)
    if status_transaksi:
        query = query.filter(Peminjaman.status == status_transaksi)
    return query.order_by(Peminjaman.tanggal_pinjam.desc(), Peminjaman.id.desc()).all()


@router.get("/{peminjaman_id}", response_model=PeminjamanResponse)
def get_peminjaman(
    peminjaman_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Peminjaman:
    peminjaman = _get_peminjaman(db, peminjaman_id)
    if (
        current_user.role.casefold() != "admin"
        and peminjaman.user_id != current_user.id
    ):
        raise HTTPException(status_code=403, detail="Akses transaksi ditolak")
    return peminjaman


@router.get("/{peminjaman_id}/bukti")
def export_bukti_peminjaman(
    peminjaman_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    loan = get_peminjaman(peminjaman_id, db, current_user)
    filename_code = re.sub(r"[^A-Za-z0-9_-]", "_", loan.kode_peminjaman)
    return StreamingResponse(
        build_loan_receipt(loan),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="bukti-{filename_code}.pdf"',
            "Cache-Control": "no-store",
        },
    )


@router.post("", response_model=PeminjamanResponse, status_code=status.HTTP_201_CREATED)
def create_peminjaman(
    payload: PeminjamanCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Peminjaman:
    barang = db.get(Barang, payload.barang_id)
    if barang is None:
        raise HTTPException(status_code=404, detail="Barang tidak ditemukan")
    if barang.stok < payload.jumlah:
        raise HTTPException(status_code=409, detail="Stok barang tidak mencukupi")

    tanggal_pinjam = payload.tanggal_pinjam or datetime.now()
    for _ in range(10):
        kode_peminjaman = _generate_kode_peminjaman(db, tanggal_pinjam)
        peminjaman = Peminjaman(
            kode_peminjaman=kode_peminjaman,
            user_id=current_user.id,
            barang_id=payload.barang_id,
            jumlah=payload.jumlah,
            tanggal_pinjam=tanggal_pinjam,
            tanggal_kembali=payload.tanggal_kembali,
            keterangan=payload.keterangan,
            status="Menunggu",
        )
        db.add(peminjaman)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            if (
                db.query(Peminjaman.id)
                .filter(Peminjaman.kode_peminjaman == kode_peminjaman)
                .first()
            ):
                continue
            raise
        db.refresh(peminjaman)
        return peminjaman

    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Tidak dapat membuat kode transaksi unik. Silakan coba lagi.",
    )


@router.put("/{peminjaman_id}/approve", response_model=PeminjamanResponse)
def approve_peminjaman(
    peminjaman_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
) -> Peminjaman:
    peminjaman = _get_peminjaman(db, peminjaman_id)
    if peminjaman.status != "Menunggu":
        raise HTTPException(status_code=409, detail="Transaksi bukan pengajuan aktif")
    barang = (
        db.query(Barang)
        .filter(Barang.id == peminjaman.barang_id)
        .with_for_update()
        .first()
    )
    if barang is None:
        raise HTTPException(status_code=404, detail="Barang tidak ditemukan")
    if barang.stok < peminjaman.jumlah:
        raise HTTPException(status_code=409, detail="Stok barang tidak mencukupi")

    barang.stok -= peminjaman.jumlah
    peminjaman.status = "Disetujui"
    log_aktivitas(
        db,
        admin,
        "Setujui Peminjaman",
        "Peminjaman",
        f"{peminjaman.kode_peminjaman} / {barang.nama_barang}",
        f"Jumlah disetujui: {peminjaman.jumlah}; stok {barang.stok + peminjaman.jumlah} → {barang.stok}",
        request.client.host if request.client else None,
    )
    _buat_notifikasi(
        db,
        peminjaman.user_id,
        f"Peminjaman {peminjaman.kode_peminjaman} disetujui.",
    )
    db.commit()
    db.refresh(peminjaman)
    return peminjaman


@router.put("/{peminjaman_id}/reject", response_model=PeminjamanResponse)
def reject_peminjaman(
    peminjaman_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
) -> Peminjaman:
    peminjaman = _get_peminjaman(db, peminjaman_id)
    if peminjaman.status != "Menunggu":
        raise HTTPException(status_code=409, detail="Transaksi bukan pengajuan aktif")

    peminjaman.status = "Ditolak"
    barang = db.get(Barang, peminjaman.barang_id)
    log_aktivitas(
        db,
        admin,
        "Tolak Peminjaman",
        "Peminjaman",
        f"{peminjaman.kode_peminjaman} / {barang.nama_barang if barang else 'Barang'}",
        "Pengajuan peminjaman ditolak.",
        request.client.host if request.client else None,
    )
    _buat_notifikasi(
        db,
        peminjaman.user_id,
        f"Peminjaman {peminjaman.kode_peminjaman} ditolak.",
    )
    db.commit()
    db.refresh(peminjaman)
    return peminjaman


@router.put("/{peminjaman_id}/return", response_model=PeminjamanResponse)
def return_peminjaman(
    peminjaman_id: int,
    payload: PeminjamanReturn,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
) -> Peminjaman:
    peminjaman = _get_peminjaman(db, peminjaman_id)
    if peminjaman.status != "Disetujui":
        raise HTTPException(
            status_code=409, detail="Transaksi tidak dalam status disetujui"
        )
    if payload.jumlah_kembali > peminjaman.jumlah:
        raise HTTPException(
            status_code=422,
            detail="Jumlah kembali tidak boleh melebihi jumlah yang dipinjam",
        )
    catatan_admin = payload.catatan_admin.strip() if payload.catatan_admin else None
    if payload.kondisi_kembali != "Baik" and not catatan_admin:
        raise HTTPException(
            status_code=422,
            detail="Catatan admin wajib diisi jika kondisi bukan Baik",
        )
    if payload.kondisi_kembali != "Hilang" and payload.jumlah_kembali == 0:
        raise HTTPException(
            status_code=422,
            detail="Jumlah diterima harus lebih dari 0 kecuali barang hilang",
        )
    barang = (
        db.query(Barang)
        .filter(Barang.id == peminjaman.barang_id)
        .with_for_update()
        .first()
    )
    if barang is None:
        raise HTTPException(status_code=404, detail="Barang tidak ditemukan")

    planned_date = peminjaman.tanggal_kembali.date() if peminjaman.tanggal_kembali else None
    late_days = max(0, (date.today() - planned_date).days) if planned_date else 0
    previous_stock = barang.stok
    if payload.kondisi_kembali != "Hilang":
        barang.stok += payload.jumlah_kembali
    if payload.kondisi_kembali == "Rusak Berat":
        barang.kondisi = "Perawatan"

    peminjaman.kondisi_kembali = payload.kondisi_kembali
    peminjaman.jumlah_kembali = payload.jumlah_kembali
    peminjaman.tanggal_kembali_aktual = datetime.now()
    peminjaman.catatan_admin = catatan_admin
    peminjaman.terlambat_hari = late_days
    peminjaman.denda = 0
    peminjaman.diproses_oleh = admin.id
    peminjaman.status = (
        "Selesai" if payload.kondisi_kembali == "Baik" else "Selesai - Rusak"
    )
    log_aktivitas(
        db,
        admin,
        "Proses Pengembalian",
        "Peminjaman",
        f"{peminjaman.kode_peminjaman} / {barang.nama_barang}",
        (
            f"Kondisi {payload.kondisi_kembali}; jumlah diterima "
            f"{payload.jumlah_kembali}/{peminjaman.jumlah}; stok "
            f"{previous_stock} → {barang.stok}; terlambat {late_days} hari."
        ),
        request.client.host if request.client else None,
    )
    _buat_notifikasi(
        db,
        peminjaman.user_id,
        f"Pengembalian peminjaman {peminjaman.kode_peminjaman} telah dicatat "
        f"dengan kondisi {payload.kondisi_kembali}.",
    )
    db.commit()
    db.refresh(peminjaman)
    return peminjaman
