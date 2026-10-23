from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.auth import get_admin_user, get_current_user
from backend.database import get_db
from backend.models import Barang, KategoriBarang, User
from backend.schemas import (
    KategoriBarangCreate,
    KategoriBarangResponse,
    KategoriBarangUpdate,
)
from backend.utils import log_aktivitas

router = APIRouter(prefix="/kategori", tags=["Kategori"])


@router.get("", response_model=list[KategoriBarangResponse])
def list_kategori(
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> list[KategoriBarang]:
    return db.query(KategoriBarang).order_by(KategoriBarang.nama_kategori).all()


@router.post(
    "",
    response_model=KategoriBarangResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_kategori(
    payload: KategoriBarangCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
) -> KategoriBarang:
    kategori = KategoriBarang(nama_kategori=payload.nama_kategori.strip())
    if not kategori.nama_kategori:
        raise HTTPException(status_code=422, detail="Nama kategori tidak boleh kosong")

    db.add(kategori)
    log_aktivitas(
        db,
        admin,
        "Tambah Kategori",
        "Kategori",
        kategori.nama_kategori,
        "Kategori barang ditambahkan.",
        request.client.host if request.client else None,
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Nama kategori sudah digunakan",
        ) from exc
    db.refresh(kategori)
    return kategori


@router.put("/{kategori_id}", response_model=KategoriBarangResponse)
def update_kategori(
    kategori_id: int,
    payload: KategoriBarangUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
) -> KategoriBarang:
    kategori = db.get(KategoriBarang, kategori_id)
    if kategori is None:
        raise HTTPException(status_code=404, detail="Kategori tidak ditemukan")

    old_name = kategori.nama_kategori
    kategori.nama_kategori = payload.nama_kategori.strip()
    if not kategori.nama_kategori:
        raise HTTPException(status_code=422, detail="Nama kategori tidak boleh kosong")
    log_aktivitas(
        db,
        admin,
        "Edit Kategori",
        "Kategori",
        kategori.nama_kategori,
        f"Nama kategori: {old_name} → {kategori.nama_kategori}.",
        request.client.host if request.client else None,
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Nama kategori sudah digunakan",
        ) from exc
    db.refresh(kategori)
    return kategori


@router.delete("/{kategori_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_kategori(
    kategori_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
) -> Response:
    kategori = db.get(KategoriBarang, kategori_id)
    if kategori is None:
        raise HTTPException(status_code=404, detail="Kategori tidak ditemukan")
    if db.query(Barang.id).filter(Barang.kategori_id == kategori_id).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Kategori masih digunakan oleh barang",
        )

    log_aktivitas(
        db,
        admin,
        "Hapus Kategori",
        "Kategori",
        kategori.nama_kategori,
        "Kategori barang dihapus.",
        request.client.host if request.client else None,
    )
    db.delete(kategori)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
