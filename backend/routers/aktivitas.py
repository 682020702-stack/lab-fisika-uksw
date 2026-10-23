from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.auth import get_admin_user
from backend.database import get_db
from backend.models import LogAktivitas, User
from backend.schemas import LogAktivitasResponse

router = APIRouter(prefix="/log-aktivitas", tags=["Log Aktivitas"])


@router.get("", response_model=list[LogAktivitasResponse])
def list_log_aktivitas(
    db: Session = Depends(get_db),
    _admin: User = Depends(get_admin_user),
) -> list[LogAktivitas]:
    return (
        db.query(LogAktivitas)
        .order_by(LogAktivitas.timestamp.desc(), LogAktivitas.id.desc())
        .all()
    )
