from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.auth import get_current_user
from backend.database import get_db
from backend.models import Notifikasi, User
from backend.schemas import NotifikasiResponse

router = APIRouter(prefix="/notifikasi", tags=["Notifikasi"])


@router.get("", response_model=list[NotifikasiResponse])
def list_notifikasi(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Notifikasi]:
    return (
        db.query(Notifikasi)
        .filter(Notifikasi.user_id == current_user.id)
        .order_by(Notifikasi.timestamp.desc(), Notifikasi.id.desc())
        .all()
    )


@router.put("/{notifikasi_id}/read", response_model=NotifikasiResponse)
def read_notifikasi(
    notifikasi_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Notifikasi:
    notifikasi = db.get(Notifikasi, notifikasi_id)
    if notifikasi is None or notifikasi.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Notifikasi tidak ditemukan")
    notifikasi.dibaca = True
    db.commit()
    db.refresh(notifikasi)
    return notifikasi
