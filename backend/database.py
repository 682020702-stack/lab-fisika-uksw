from collections.abc import Generator
import os
from pathlib import Path

from sqlalchemy import URL, create_engine, event, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DATABASE_PATH = Path(__file__).resolve().parent / "laboratorium.db"
configured_database_url = os.getenv("DATABASE_URL")
if configured_database_url:
    DATABASE_URL = make_url(configured_database_url)
    if DATABASE_URL.drivername in {"postgres", "postgresql"}:
        DATABASE_URL = DATABASE_URL.set(drivername="postgresql+psycopg")
else:
    DATABASE_URL = URL.create("sqlite", database=str(DATABASE_PATH))

engine_options = {}
if DATABASE_URL.get_backend_name() == "sqlite":
    engine_options["connect_args"] = {"check_same_thread": False}
engine = create_engine(DATABASE_URL, **engine_options)


if engine.dialect.name == "sqlite":
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
        verified_default = (
            "BOOLEAN NOT NULL DEFAULT TRUE"
            if engine.dialect.name == "postgresql"
            else "BOOLEAN NOT NULL DEFAULT 1"
        )
        new_user_columns = {
            # Existing accounts predate email verification and must remain usable.
            "is_verified": verified_default,
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
        legacy_item_columns = {"barang_id", "jumlah"} & loan_columns
        if legacy_item_columns and legacy_item_columns != {"barang_id", "jumlah"}:
            raise RuntimeError(
                "Skema peminjaman lama tidak lengkap; migrasi barang/jumlah "
                "dihentikan agar data tidak berubah."
            )
        known_loan_columns = {
            "id",
            "kode_peminjaman",
            "user_id",
            "barang_id",
            "jumlah",
            "tanggal_pinjam",
            "tanggal_kembali",
            "status",
            "keterangan",
            "kondisi_kembali",
            "jumlah_kembali",
            "tanggal_kembali_aktual",
            "catatan_admin",
            "terlambat_hari",
            "denda",
            "diproses_oleh",
        }
        unknown_columns = loan_columns - known_loan_columns
        if unknown_columns:
            raise RuntimeError(
                "Kolom peminjaman yang tidak dikenal ditemukan; migrasi "
                f"dihentikan agar data tidak berubah: {', '.join(sorted(unknown_columns))}"
            )
        has_detail_table = "detail_peminjaman" in table_names
        if not legacy_item_columns and not has_detail_table:
            with engine.connect() as connection:
                loan_count = connection.scalar(text("SELECT COUNT(*) FROM peminjaman"))
            if loan_count:
                raise RuntimeError(
                    "Data detail peminjaman tidak ditemukan; migrasi dihentikan "
                    "agar riwayat transaksi tidak kehilangan barang."
                )
        new_columns = {
            "kondisi_kembali": "VARCHAR(50)",
            "jumlah_kembali": "INTEGER",
            "tanggal_kembali_aktual": "DATETIME",
            "catatan_admin": "TEXT",
            "terlambat_hari": "INTEGER NOT NULL DEFAULT 0",
            "denda": "INTEGER NOT NULL DEFAULT 0",
            "diproses_oleh": "INTEGER REFERENCES users(id) ON DELETE SET NULL",
        }
        dependent_tables = [
            table
            for table in table_names
            if table != "detail_peminjaman"
            and any(
                foreign_key.get("referred_table") == "peminjaman"
                for foreign_key in inspector.get_foreign_keys(table)
            )
        ]
        if dependent_tables:
            raise RuntimeError(
                "Tabel lain bergantung pada peminjaman; migrasi dihentikan: "
                + ", ".join(sorted(dependent_tables))
            )
        detail_id_definition = (
            "INTEGER NOT NULL PRIMARY KEY"
            if engine.dialect.name == "sqlite"
            else "INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY"
        )
        detail_table_ddl = (
            "CREATE TABLE IF NOT EXISTS detail_peminjaman ("
            f"id {detail_id_definition}, "
            "peminjaman_id INTEGER NOT NULL "
            "REFERENCES peminjaman(id) ON DELETE CASCADE, "
            "barang_id INTEGER NOT NULL REFERENCES barang(id), "
            "jumlah INTEGER NOT NULL, "
            "kondisi_saat_pinjam VARCHAR(50) NOT NULL)"
        )
        with engine.begin() as connection:
            if engine.dialect.name == "sqlite":
                # Ensure SQLite rolls DDL back if validation later aborts migration.
                connection.exec_driver_sql("BEGIN IMMEDIATE")
            for column, definition in new_columns.items():
                if column not in loan_columns:
                    connection.execute(
                        text(f"ALTER TABLE peminjaman ADD COLUMN {column} {definition}")
                    )
            connection.execute(text(detail_table_ddl))
            if legacy_item_columns:
                missing_barang = connection.scalar(
                    text(
                        "SELECT COUNT(*) FROM peminjaman AS p "
                        "LEFT JOIN barang AS b ON b.id = p.barang_id "
                        "WHERE b.id IS NULL"
                    )
                )
                if missing_barang:
                    raise RuntimeError(
                        "Ada peminjaman dengan barang yang tidak ditemukan; "
                        "migrasi dihentikan agar data tidak berubah."
                    )
                connection.execute(
                    text(
                        "INSERT INTO detail_peminjaman "
                        "(peminjaman_id, barang_id, jumlah, kondisi_saat_pinjam) "
                        "SELECT p.id, p.barang_id, p.jumlah, "
                        "COALESCE(b.kondisi, 'Baik') "
                        "FROM peminjaman AS p "
                        "JOIN barang AS b ON b.id = p.barang_id "
                        "WHERE NOT EXISTS ("
                        "SELECT 1 FROM detail_peminjaman AS d "
                        "WHERE d.peminjaman_id = p.id)"
                    )
                )
                incomplete_loans = connection.scalar(
                    text(
                        "SELECT COUNT(*) FROM peminjaman AS p "
                        "WHERE NOT EXISTS ("
                        "SELECT 1 FROM detail_peminjaman AS d "
                        "WHERE d.peminjaman_id = p.id)"
                    )
                )
                if incomplete_loans:
                    raise RuntimeError(
                        "Migrasi detail peminjaman tidak lengkap; "
                        "kolom lama tidak dihapus."
                    )
            connection.execute(
                text(
                    "UPDATE peminjaman SET status = CASE status "
                    "WHEN 'Menunggu ACC' THEN 'Menunggu' "
                    "WHEN 'Dipinjam' THEN 'Disetujui' "
                    "WHEN 'Dikembalikan' THEN 'Selesai' ELSE status END"
                )
            )
            if legacy_item_columns and engine.dialect.name != "sqlite":
                connection.execute(
                    text("ALTER TABLE peminjaman DROP COLUMN barang_id")
                )
                connection.execute(text("ALTER TABLE peminjaman DROP COLUMN jumlah"))
            if legacy_item_columns and engine.dialect.name == "sqlite":
                indexes = connection.execute(
                    text(
                        "SELECT sql FROM sqlite_master "
                        "WHERE type = 'index' AND tbl_name = 'peminjaman' "
                        "AND sql IS NOT NULL"
                    )
                ).scalars().all()
                triggers = connection.execute(
                    text(
                        "SELECT sql FROM sqlite_master "
                        "WHERE type = 'trigger' AND tbl_name = 'peminjaman' "
                        "AND sql IS NOT NULL"
                    )
                ).scalars().all()
                connection.execute(
                    text(
                        "CREATE TEMP TABLE _detail_peminjaman_migration_backup "
                        "AS SELECT * FROM detail_peminjaman"
                    )
                )
                connection.execute(text("DROP TABLE detail_peminjaman"))
                connection.execute(
                    text(
                        "CREATE TABLE peminjaman_new ("
                        "id INTEGER NOT NULL PRIMARY KEY, "
                        "kode_peminjaman VARCHAR(50) NOT NULL, "
                        "user_id INTEGER NOT NULL REFERENCES users(id), "
                        "tanggal_pinjam DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                        "tanggal_kembali DATETIME, "
                        "status VARCHAR(50) NOT NULL CHECK (status IN "
                        "('Menunggu', 'Disetujui', 'Ditolak', 'Selesai', "
                        "'Selesai - Rusak')), "
                        "keterangan VARCHAR(1000), "
                        "kondisi_kembali VARCHAR(50), "
                        "jumlah_kembali INTEGER, "
                        "tanggal_kembali_aktual DATETIME, "
                        "catatan_admin TEXT, "
                        "terlambat_hari INTEGER NOT NULL DEFAULT 0, "
                        "denda INTEGER NOT NULL DEFAULT 0, "
                        "diproses_oleh INTEGER REFERENCES users(id) ON DELETE SET NULL)"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO peminjaman_new "
                        "(id, kode_peminjaman, user_id, tanggal_pinjam, "
                        "tanggal_kembali, status, keterangan, kondisi_kembali, "
                        "jumlah_kembali, tanggal_kembali_aktual, catatan_admin, "
                        "terlambat_hari, denda, diproses_oleh) "
                        "SELECT id, kode_peminjaman, user_id, tanggal_pinjam, "
                        "tanggal_kembali, status, keterangan, kondisi_kembali, "
                        "jumlah_kembali, tanggal_kembali_aktual, catatan_admin, "
                        "terlambat_hari, denda, diproses_oleh FROM peminjaman"
                    )
                )
                connection.execute(text("DROP TABLE peminjaman"))
                connection.execute(
                    text("ALTER TABLE peminjaman_new RENAME TO peminjaman")
                )
                connection.execute(
                    text(detail_table_ddl.replace(" IF NOT EXISTS", ""))
                )
                connection.execute(
                    text(
                        "INSERT INTO detail_peminjaman "
                        "(id, peminjaman_id, barang_id, jumlah, kondisi_saat_pinjam) "
                        "SELECT id, peminjaman_id, barang_id, jumlah, "
                        "kondisi_saat_pinjam "
                        "FROM _detail_peminjaman_migration_backup"
                    )
                )
                connection.execute(
                    text("DROP TABLE _detail_peminjaman_migration_backup")
                )
                for index_sql in indexes:
                    connection.execute(text(index_sql))
                connection.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS "
                        "ix_detail_peminjaman_id ON detail_peminjaman (id)"
                    )
                )
                for trigger_sql in triggers:
                    connection.execute(text(trigger_sql))
                foreign_key_errors = connection.execute(
                    text("PRAGMA foreign_key_check")
                ).all()
                if foreign_key_errors:
                    raise RuntimeError(
                        "Pemeriksaan foreign key gagal setelah migrasi; "
                        "perubahan dibatalkan."
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
