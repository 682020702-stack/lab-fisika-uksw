from sqlalchemy.orm import Session

from backend.models import LogAktivitas, User


def log_aktivitas(
    db: Session,
    admin: User,
    aksi: str,
    kategori: str,
    target: str | None = None,
    detail: str | None = None,
    ip: str | None = None,
) -> None:
    db.add(
        LogAktivitas(
            admin_id=admin.id,
            admin_nama=admin.nama_lengkap or admin.username,
            aksi=aksi,
            kategori=kategori,
            target=target,
            detail=detail,
            ip_address=ip,
        )
    )
