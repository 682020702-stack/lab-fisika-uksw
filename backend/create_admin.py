import argparse
import getpass
import os
import sys
from collections.abc import Sequence

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from backend.auth import hash_password
from backend.database import Base, SessionLocal, engine, migrate_legacy_schema
from backend.models import User
from backend.schemas import UserCreate


def create_admin(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Buat akun Admin.")
    parser.add_argument("--username", required=True)
    parser.add_argument("--nama-lengkap", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument(
        "--password",
        help="Password akun (lebih aman jika tidak diberikan agar diminta tersembunyi).",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Lewati konfirmasi pembuatan akun.",
    )
    args = parser.parse_args(argv)

    if (
        os.getenv("ENVIRONMENT", "").casefold() == "production"
        and engine.dialect.name == "sqlite"
    ):
        raise RuntimeError(
            "DATABASE_URL must point to the production database; refusing to "
            "create an Admin in the local SQLite database."
        )

    print(f"Target database: {engine.dialect.name}")
    password = args.password
    if password is None:
        password = getpass.getpass("Password (minimal 8 karakter): ")
        password_confirmation = getpass.getpass("Ulangi password: ")
        if password != password_confirmation:
            raise ValueError("Password tidak sama.")

    try:
        payload = UserCreate(
            username=args.username.strip(),
            password=password,
            nama_lengkap=args.nama_lengkap.strip(),
            email=args.email.strip(),
            role="Admin",
            tipe_user=None,
            status="Aktif",
        )
    except ValidationError as exc:
        raise ValueError(
            "Data tidak valid. Periksa username, nama lengkap, email, "
            "dan panjang password."
        ) from exc

    if not args.yes:
        confirmation = input(
            f"Ketik 'buat' untuk membuat akun Admin '{payload.username}': "
        ).strip()
        if confirmation.casefold() != "buat":
            print("Pembuatan Admin dibatalkan.")
            return

    migrate_legacy_schema()
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        if (
            db.query(User)
            .filter(
                (User.username == payload.username) | (User.email == payload.email)
            )
            .first()
        ):
            raise ValueError("Username atau email sudah digunakan.")

        db.add(
            User(
                username=payload.username,
                password_hash=hash_password(payload.password),
                nama_lengkap=payload.nama_lengkap,
                email=payload.email,
                role="Admin",
                tipe_user=None,
                status="Aktif",
                is_verified=True,
            )
        )
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise RuntimeError(
                "Akun tidak dibuat karena username atau email sudah digunakan."
            ) from None

    print(f"Akun Admin '{payload.username}' berhasil dibuat.")


if __name__ == "__main__":
    try:
        create_admin()
    except (ValueError, RuntimeError) as exc:
        print(f"Gagal membuat Admin: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
