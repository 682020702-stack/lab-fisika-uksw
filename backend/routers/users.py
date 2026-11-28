from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.auth import (
    get_admin_user,
    get_current_user,
    hash_password,
    verify_password,
)
from backend.database import get_db
from backend.models import LogAktivitas, Peminjaman, User
from backend.schemas import (
    ChangePasswordRequest,
    UserBulkDeleteRequest,
    UsernameUpdate,
    UserCreate,
    UserResponse,
    UserUpdate,
)
from backend.utils import log_aktivitas

router = APIRouter(prefix="/users", tags=["Users"])


# BULK DELETE: gunakan aturan hapus yang sama untuk aksi tunggal dan massal.
def _ensure_user_deletable(db: Session, user: User, admin: User) -> None:
    if user.id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Admin tidak dapat menghapus akunnya sendiri",
        )
    if db.query(Peminjaman.id).filter(Peminjaman.user_id == user.id).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Pengguna memiliki riwayat peminjaman dan tidak dapat dihapus",
        )
    if (
        user.role.casefold() == "admin"
        and db.query(LogAktivitas.id).filter(LogAktivitas.admin_id == user.id).first()
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Admin dengan riwayat aktivitas tidak dapat dihapus",
        )


@router.get("/export/excel")
def export_users_excel(
    db: Session = Depends(get_db),
    _admin: User = Depends(get_admin_user),
) -> StreamingResponse:
    users = db.query(User).order_by(User.id).all()
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Pengguna"
    sheet.append(["Nama", "Role", "Tipe Pengguna", "Email", "Status"])
    for user in users:
        sheet.append(
            [
                user.nama_lengkap,
                user.role,
                user.tipe_user or "",
                user.email,
                user.status,
            ]
        )
        for cell in sheet[sheet.max_row]:
            if isinstance(cell.value, str):
                cell.data_type = "s"
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions

    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="data-pengguna.xlsx"'},
    )


@router.delete("/bulk")  # BULK DELETE: endpoint massal khusus Admin.
def bulk_delete_users(
    payload: UserBulkDeleteRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
) -> dict[str, int]:
    user_ids = payload.user_ids
    users = db.query(User).filter(User.id.in_(user_ids)).all()
    found_ids = {user.id for user in users}
    missing_ids = sorted(set(user_ids) - found_ids)
    if missing_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pengguna tidak ditemukan: {', '.join(map(str, missing_ids))}",
        )

    for user in users:
        _ensure_user_deletable(
            db, user, admin
        )  # BULK DELETE: pertahankan batasan hapus yang sama.

    log_aktivitas(
        db,
        admin,
        "Hapus Pengguna Massal",
        "Pengguna",
        f"{len(users)} pengguna",
        f"ID pengguna: {', '.join(map(str, sorted(user_ids)))}",
        request.client.host if request.client else None,
    )
    try:
        deleted_count = (
            db.query(User)
            .filter(User.id.in_(user_ids))
            .delete(synchronize_session=False)
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Pengguna terpilih memiliki data terkait dan tidak dapat dihapus",
        ) from exc
    return {"deleted_count": deleted_count}


@router.get("", response_model=list[UserResponse])
def list_users(
    role: str | None = Query(default=None, min_length=1),
    search: str | None = Query(default=None, min_length=1),
    db: Session = Depends(get_db),
    _admin: User = Depends(get_admin_user),
) -> list[User]:
    query = db.query(User)
    if role:
        query = query.filter(User.role == role)
    if search:
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                User.username.ilike(term),
                User.nama_lengkap.ilike(term),
                User.email.ilike(term),
            )
        )
    return query.order_by(User.id).all()


@router.get("/me", response_model=UserResponse)
def get_current_user_profile(
    current_user: User = Depends(get_current_user),
) -> User:
    return current_user


@router.put("/me/password", status_code=status.HTTP_204_NO_CONTENT)
def change_current_user_password(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    if not verify_password(payload.password_lama, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password lama tidak sesuai",
        )

    current_user.password_hash = hash_password(payload.password_baru)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/me/username")
def update_current_user_username(
    payload: UsernameUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    existing_user = (
        db.query(User)
        .filter(
            User.username == payload.new_username,
            User.id != current_user.id,
        )
        .first()
    )
    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username sudah digunakan",
        )

    current_user.username = payload.new_username
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username sudah digunakan",
        ) from exc
    db.refresh(current_user)
    return {"username": current_user.username}


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_admin_user),
) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Pengguna tidak ditemukan")
    return user


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
) -> User:
    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        nama_lengkap=payload.nama_lengkap,
        email=payload.email,
        jenis_kelamin=payload.jenis_kelamin,
        role=payload.role,
        tipe_user=payload.tipe_user,
        status=payload.status,
        is_verified=True,
    )
    db.add(user)
    log_aktivitas(
        db,
        admin,
        "Tambah User",
        "Pengguna",
        f"{user.username} / {user.nama_lengkap}",
        f"Role: {user.role}; status: {user.status}.",
        request.client.host if request.client else None,
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username atau email sudah digunakan",
        ) from exc
    db.refresh(user)
    return user


@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    payload: UserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Pengguna tidak ditemukan")

    changes = payload.model_dump(exclude_unset=True)
    if "tipe_user" in payload.model_fields_set:
        changes["tipe_user"] = payload.tipe_user
    if changes.get("role", user.role) == "Admin":
        if changes.get("tipe_user") is not None:
            if "tipe_user" in payload.model_fields_set:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Admin tidak boleh memiliki tipe_user",
                )
        changes["tipe_user"] = None
    changed_values = {
        field: (getattr(user, field), value)
        for field, value in changes.items()
        if getattr(user, field) != value
    }
    for field, value in changes.items():
        if value is not None or field == "tipe_user":
            setattr(user, field, value)
    status_verified = changed_values.get("status") == ("Pending", "Aktif")
    detail = (
        "; ".join(
            f"{field}: {old_value} → {new_value}"
            for field, (old_value, new_value) in changed_values.items()
        )
        or "Tidak ada perubahan."
    )
    log_aktivitas(
        db,
        admin,
        "Verifikasi User" if status_verified else "Edit User",
        "Pengguna",
        f"{user.username} / {user.nama_lengkap}",
        detail,
        request.client.host if request.client else None,
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email sudah digunakan",
        ) from exc
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
) -> Response:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Pengguna tidak ditemukan")
    _ensure_user_deletable(db, user, admin)

    log_aktivitas(
        db,
        admin,
        "Hapus User",
        "Pengguna",
        f"{user.username} / {user.nama_lengkap}",
        f"Role: {user.role}; status: {user.status}.",
        request.client.host if request.client else None,
    )
    db.delete(user)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
