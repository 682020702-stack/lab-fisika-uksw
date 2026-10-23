import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from smtplib import SMTPException

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, or_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.email_utils import (
    SMTPConfigurationError,
    send_password_reset_email,
    send_verification_email,
)
from backend.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from backend.database import get_db
from backend.models import User
from backend.rate_limiter import limiter
from backend.schemas import (
    LoginRequest,
    ForgotPasswordRequest,
    RegisterRequest,
    ResetPasswordRequest,
    Token,
    UserRegisterPublic,
    UserResponse,
)
from backend.utils import log_aktivitas

router = APIRouter(tags=["Authentication"])
logger = logging.getLogger(__name__)


@router.post("/login", response_model=Token)
@limiter.limit("5/minute")
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> Token:
    user = db.query(User).filter(User.username == payload.username).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Username atau password salah",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Akun belum diverifikasi. Silakan cek email Anda.",
        )
    if user.status != "Aktif":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Akun Anda sedang menunggu verifikasi admin.",
        )

    if user.role.casefold() == "admin":
        log_aktivitas(
            db,
            user,
            "Login",
            "Auth",
            f"{user.username} / {user.nama_lengkap}",
            "Admin berhasil masuk.",
            request.client.host if request.client else None,
        )
        db.commit()

    return Token(
        access_token=create_access_token(user.id),
        user={
            "id": user.id,
            "username": user.username,
            "nama_lengkap": user.nama_lengkap,
            "role": user.role,
            "tipe_user": user.tipe_user,
        },
    )


@router.post("/forgot-password")
@limiter.limit("3/minute")
def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    user = (
        db.query(User)
        .filter(func.lower(User.email) == payload.email.lower())
        .first()
    )
    if user is not None:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        user.reset_token = token_hash
        user.reset_token_expires = now + timedelta(minutes=15)
        db.commit()

        try:
            send_password_reset_email(user.email, user.nama_lengkap, token)
        except (OSError, SMTPException, SMTPConfigurationError, ValueError):
            db.execute(
                update(User)
                .where(User.id == user.id, User.reset_token == token_hash)
                .values(reset_token=None, reset_token_expires=None)
            )
            db.commit()
            logger.exception("Gagal mengirim email reset password")

    return {"message": "Jika email terdaftar, link reset telah dikirim"}


@router.post("/reset-password")
@limiter.limit("5/minute")
def reset_password(
    payload: ResetPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    token_hash = hashlib.sha256(payload.token.encode("utf-8")).hexdigest()
    user = db.query(User).filter(User.reset_token == token_hash).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token reset tidak valid",
        )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if user.reset_token_expires is None or user.reset_token_expires < now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token sudah kedaluwarsa",
        )

    result = db.execute(
        update(User)
        .where(
            User.id == user.id,
            User.reset_token == token_hash,
            User.reset_token_expires >= now,
        )
        .values(
            password_hash=hash_password(payload.new_password),
            reset_token=None,
            reset_token_expires=None,
        )
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token sudah kedaluwarsa atau telah digunakan",
        )
    db.commit()
    return {"message": "Password berhasil diubah. Silakan masuk dengan password baru."}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    if current_user.role.casefold() == "admin":
        log_aktivitas(
            db,
            current_user,
            "Logout",
            "Auth",
            f"{current_user.username} / {current_user.nama_lengkap}",
            "Admin berhasil keluar.",
            request.client.host if request.client else None,
        )
        db.commit()


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    payload: RegisterRequest,
    db: Session = Depends(get_db),
) -> User:
    existing_user = (
        db.query(User)
        .filter(or_(User.username == payload.username, User.email == payload.email))
        .first()
    )
    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username atau email sudah digunakan",
        )

    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        nama_lengkap=payload.nama_lengkap,
        email=payload.email,
        jenis_kelamin=payload.jenis_kelamin,
        role="User",
        tipe_user=payload.tipe_user,
        status="Pending",
        is_verified=True,
    )
    db.add(user)
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


@router.post("/register-public", status_code=status.HTTP_201_CREATED)
def register_public(
    payload: UserRegisterPublic,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    existing_user = (
        db.query(User)
        .filter(or_(User.username == payload.username, User.email == payload.email))
        .first()
    )
    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username atau email sudah terdaftar",
        )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    token = secrets.token_urlsafe(32)
    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        nama_lengkap=payload.nama_lengkap,
        email=payload.email,
        jenis_kelamin=payload.jenis_kelamin,
        role="User",
        tipe_user=payload.tipe_user,
        status="Aktif",
        is_verified=False,
        verification_token=token,
        verification_token_expires=now + timedelta(hours=24),
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username atau email sudah terdaftar",
        ) from exc

    try:
        send_verification_email(user.email, user.nama_lengkap, token)
    except (OSError, SMTPException, SMTPConfigurationError) as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email verifikasi gagal dikirim. Periksa konfigurasi SMTP dan coba lagi.",
        ) from exc

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username atau email sudah terdaftar",
        ) from exc
    return {"message": "Registrasi berhasil. Silakan cek email untuk verifikasi."}


@router.get("/verify-email")
def verify_email(
    token: str,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    user = db.query(User).filter(User.verification_token == token).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token tidak valid",
        )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if user.verification_token_expires is None or user.verification_token_expires < now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token sudah kadaluarsa",
        )

    user.is_verified = True
    user.verification_token = None
    user.verification_token_expires = None
    db.commit()
    return {"message": "Email berhasil diverifikasi. Silakan login."}
