import os

from backend.auth import hash_password
from backend.database import SessionLocal
from backend.models import KategoriBarang, User

INITIAL_CATEGORIES = ("Elektronika", "Alat Ukur", "Sensor", "Kabel & Konektor")
TEST_USERS = (
    {
        "username": "admin",
        "password": "admin123",
        "nama_lengkap": "Administrator Laboratorium Fisika",
        "email": "admin@uksw.edu",
        "role": "Admin",
        "tipe_user": None,
    },
    {
        "username": "mahasiswa1",
        "password": "mhs12345",
        "nama_lengkap": "Mahasiswa Testing",
        "email": "mahasiswa1@uksw.edu",
        "role": "User",
        "tipe_user": "Mahasiswa",
    },
    {
        "username": "dosen1",
        "password": "dosen123",
        "nama_lengkap": "Dosen Testing",
        "email": "dosen1@uksw.edu",
        "role": "User",
        "tipe_user": "Dosen",
    },
)


def seed_test_users() -> None:
    if os.getenv("ENVIRONMENT", "").strip().casefold() == "production":
        return

    with SessionLocal() as db:
        for account in TEST_USERS:
            user = db.query(User).filter(User.username == account["username"]).first()
            if user is None:
                user = User(username=account["username"])
                db.add(user)
            user.password_hash = hash_password(account["password"])
            user.nama_lengkap = account["nama_lengkap"]
            user.email = account["email"]
            user.role = account["role"]
            user.tipe_user = account["tipe_user"]
            user.status = "Aktif"
            user.is_verified = True
            user.verification_token = None
            user.verification_token_expires = None

        db.commit()


def seed_categories() -> None:
    with SessionLocal() as db:
        existing = {name for (name,) in db.query(KategoriBarang.nama_kategori).all()}
        missing = [
            KategoriBarang(nama_kategori=name)
            for name in INITIAL_CATEGORIES
            if name not in existing
        ]
        if missing:
            db.add_all(missing)
            db.commit()
