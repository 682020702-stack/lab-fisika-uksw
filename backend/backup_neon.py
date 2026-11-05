from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.database import engine
from backend.models import (
    Barang,
    DetailPeminjaman,
    KategoriBarang,
    LogAktivitas,
    Notifikasi,
    Peminjaman,
    User,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKUP_DIRECTORY = PROJECT_ROOT / "backup"
BACKUP_MODELS = (
    User,
    KategoriBarang,
    Barang,
    Peminjaman,
    DetailPeminjaman,
    LogAktivitas,
    Notifikasi,
)


def _insert_statement(model: type, row: object) -> str:
    values = {
        column.key: getattr(row, column.key) for column in model.__mapper__.column_attrs
    }
    statement = model.__table__.insert().values(values)
    compiled = statement.compile(
        dialect=engine.dialect,
        compile_kwargs={"literal_binds": True},
    )
    return f"{compiled};"


def main() -> int:
    if engine.dialect.name != "postgresql":
        raise SystemExit(
            "DATABASE_URL harus menunjuk ke database PostgreSQL Neon, bukan SQLite."
        )

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_path = BACKUP_DIRECTORY / f"backup_neon_{timestamp}.sql"
    backup_created = False

    try:
        BACKUP_DIRECTORY.mkdir(parents=True, exist_ok=True)
        with backup_path.open("x", encoding="utf-8", newline="\n") as backup_file:
            backup_created = True
            backup_file.write("-- Data-only backup of the Neon database.\n")
            backup_file.write(
                "-- Restore into a database with the application schema.\n\n"
            )
            backup_file.write("SET standard_conforming_strings = on;\n\n")
            backup_file.write("BEGIN;\n\n")
            total_rows = 0

            with Session(engine) as session:
                for model in BACKUP_MODELS:
                    table_name = model.__tablename__
                    table_rows = 0
                    rows = session.scalars(
                        select(model)
                        .order_by(model.id)
                        .execution_options(yield_per=100)
                    )
                    for row in rows:
                        backup_file.write(_insert_statement(model, row))
                        backup_file.write("\n")
                        table_rows += 1
                    total_rows += table_rows
                    backup_file.write(f"\n-- {table_name}: {table_rows} row(s)\n\n")

            if total_rows == 0:
                raise RuntimeError(
                    "Tidak ada data pada tabel backup; file SQL kosong tidak disimpan."
                )

            for model in BACKUP_MODELS:
                table_name = model.__tablename__
                backup_file.write(
                    "SELECT setval(pg_get_serial_sequence("
                    f"'{table_name}', 'id'), COALESCE(MAX(id), 1), "
                    f"MAX(id) IS NOT NULL) FROM {table_name};\n"
                )
            backup_file.write("\nCOMMIT;\n")

        if backup_path.stat().st_size == 0:
            raise RuntimeError("Backup selesai tetapi file yang dihasilkan kosong.")
    except (OSError, SQLAlchemyError, RuntimeError) as error:
        if backup_created:
            backup_path.unlink(missing_ok=True)
        raise SystemExit(f"Backup gagal: {error}") from error

    print(f"Backup berhasil dibuat: {backup_path}")
    print(f"Jumlah baris: {total_rows}")
    print(f"Ukuran file: {backup_path.stat().st_size:,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
