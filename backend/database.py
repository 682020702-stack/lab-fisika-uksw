from collections.abc import Generator
from pathlib import Path

from sqlalchemy import URL, create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DATABASE_PATH = Path(__file__).resolve().parent / "laboratorium.db"
DATABASE_URL = URL.create("sqlite", database=str(DATABASE_PATH))

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def enable_sqlite_foreign_keys(connection, _record):
    connection.execute("PRAGMA foreign_keys=ON")


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def migrate_legacy_schema() -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    if "users" in table_names:
        user_columns = {column["name"] for column in inspector.get_columns("users")}
        new_user_columns = {
            # Existing accounts predate email verification and must remain usable.
            "is_verified": "BOOLEAN NOT NULL DEFAULT 1",
            "verification_token": "VARCHAR(255)",
            "verification_token_expires": "DATETIME",
            "jenis_kelamin": "VARCHAR(20)",
            "reset_token": "VARCHAR(255)",
            "reset_token_expires": "DATETIME",
        }
        with engine.begin() as connection:
            for column, definition in new_user_columns.items():
                if column not in user_columns:
                    connection.execute(
                        text(f"ALTER TABLE users ADD COLUMN {column} {definition}")
                    )
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS "
                    "ix_users_verification_token ON users (verification_token)"
                )
            )
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS "
                    "ix_users_reset_token ON users (reset_token)"
                )
            )

    if "peminjaman" in table_names:
        loan_columns = {column["name"] for column in inspector.get_columns("peminjaman")}
        new_columns = {
            "kondisi_kembali": "VARCHAR(50)",
            "jumlah_kembali": "INTEGER",
            "tanggal_kembali_aktual": "DATETIME",
            "catatan_admin": "TEXT",
            "terlambat_hari": "INTEGER NOT NULL DEFAULT 0",
            "denda": "INTEGER NOT NULL DEFAULT 0",
            "diproses_oleh": "INTEGER REFERENCES users(id) ON DELETE SET NULL",
        }
        with engine.begin() as connection:
            for column, definition in new_columns.items():
                if column not in loan_columns:
                    connection.execute(
                        text(f"ALTER TABLE peminjaman ADD COLUMN {column} {definition}")
                    )
            connection.execute(
                text(
                    "UPDATE peminjaman SET status = CASE status "
                    "WHEN 'Menunggu ACC' THEN 'Menunggu' "
                    "WHEN 'Dipinjam' THEN 'Disetujui' "
                    "WHEN 'Dikembalikan' THEN 'Selesai' ELSE status END"
                )
            )

    if "barang" in table_names:
        barang_columns = {column["name"] for column in inspector.get_columns("barang")}
        if "tahun_pengadaan" not in barang_columns:
            with engine.begin() as connection:
                connection.execute(
            text("ALTER TABLE barang ADD COLUMN tahun_pengadaan INTEGER")
                )

    if "log_aktivitas" not in table_names:
        return

    log_columns = {column["name"] for column in inspector.get_columns("log_aktivitas")}
    if {"user_id", "status"} <= log_columns and "admin_nama" not in log_columns:
        if "log_aktivitas_legacy" not in table_names:
            legacy_indexes = inspector.get_indexes("log_aktivitas")
            with engine.begin() as connection:
                connection.execute(
                    text("ALTER TABLE log_aktivitas RENAME TO log_aktivitas_legacy")
                )
                for index in legacy_indexes:
                    quoted_name = connection.dialect.identifier_preparer.quote(
                        index["name"]
                    )
                    connection.execute(text(f"DROP INDEX IF EXISTS {quoted_name}"))


def migrate_legacy_activity_logs() -> None:
    if "log_aktivitas_legacy" not in inspect(engine).get_table_names():
        return

    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO log_aktivitas "
                "(admin_id, admin_nama, aksi, kategori, target, detail, timestamp) "
                "SELECT users.id, users.nama_lengkap, 'Aktivitas Legacy', "
                "'Sistem', NULL, legacy.aksi || ': ' || legacy.status, "
                "legacy.timestamp FROM log_aktivitas_legacy AS legacy "
                "JOIN users ON users.id = legacy.user_id "
                "WHERE users.role = 'Admin'"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE log_aktivitas_legacy "
                "RENAME TO log_aktivitas_legacy_migrated"
            )
        )


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
