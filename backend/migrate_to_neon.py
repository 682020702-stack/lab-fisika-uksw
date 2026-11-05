from pathlib import Path
import os

from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from backend.database import Base, engine as target_engine
from backend.models import (
    Barang,
    DetailPeminjaman,
    KategoriBarang,
    LogAktivitas,
    Notifikasi,
    Peminjaman,
    User,
)

SOURCE_DATABASE_PATH = Path(__file__).resolve().parent / "laboratorium.db"
MIGRATION_MODELS = (
    User,
    KategoriBarang,
    Barang,
    Peminjaman,
    DetailPeminjaman,
    LogAktivitas,
    Notifikasi,
)


def _column_values(model: type, row: object) -> dict[str, object]:
    return {
        column.key: getattr(row, column.key)
        for column in model.__mapper__.column_attrs
    }


def _same_values(existing: object, values: dict[str, object]) -> bool:
    return all(getattr(existing, key) == value for key, value in values.items())


def _transfer_table(
    source: Session, target: Session, model: type
) -> tuple[int, int, int]:
    inserted = skipped = errors = 0
    rows = source.scalars(select(model).order_by(model.id)).yield_per(100)

    for source_row in rows:
        values = _column_values(model, source_row)
        row_id = values["id"]
        existing = target.get(model, row_id)
        if existing is not None:
            if _same_values(existing, values):
                skipped += 1
                continue
            print(
                f"CONFLICT {model.__tablename__} id={row_id}: "
                "target already contains different data; row not changed."
            )
            errors += 1
            continue

        target.add(model(**values))
        try:
            target.commit()
            inserted += 1
        except SQLAlchemyError as error:
            target.rollback()
            reason = (
                "duplicate or foreign-key constraint"
                if isinstance(error, IntegrityError)
                else "database error"
            )
            print(
                f"ERROR {model.__tablename__} id={row_id}: "
                f"{type(error).__name__} ({reason}); row not migrated."
            )
            errors += 1

    return inserted, skipped, errors


def _synchronize_postgresql_sequences(connection) -> None:
    for model in MIGRATION_MODELS:
        table_name = model.__tablename__
        quoted_table = connection.dialect.identifier_preparer.quote(table_name)
        connection.execute(
            text(
                "SELECT setval(pg_get_serial_sequence(:table_name, 'id'), "
                f"COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) FROM {quoted_table}"
            ),
            {"table_name": table_name},
        )


def main() -> int:
    if not os.getenv("DATABASE_URL"):
        raise SystemExit(
            "DATABASE_URL belum diatur. Isi connection string Neon di .env "
            "atau environment sebelum menjalankan migrasi."
        )
    if target_engine.dialect.name != "postgresql":
        raise SystemExit("DATABASE_URL harus menunjuk ke database PostgreSQL Neon.")
    if not SOURCE_DATABASE_PATH.is_file():
        raise SystemExit(f"Database SQLite sumber tidak ditemukan: {SOURCE_DATABASE_PATH}")

    source_engine = create_engine(
        URL.create("sqlite", database=str(SOURCE_DATABASE_PATH))
    )
    try:
        Base.metadata.create_all(bind=target_engine)
        total_errors = 0
        with Session(source_engine) as source, Session(target_engine) as target:
            for model in MIGRATION_MODELS:
                inserted, skipped, errors = _transfer_table(source, target, model)
                total_errors += errors
                print(
                    f"{model.__tablename__}: "
                    f"{inserted} inserted, {skipped} already present, {errors} errors"
                )

        with target_engine.begin() as connection:
            _synchronize_postgresql_sequences(connection)

        if total_errors:
            print(
                f"Migration finished with {total_errors} row error(s). "
                "Resolve the reported conflicts and rerun; SQLite was not modified."
            )
            return 1

        print("Migration completed successfully. SQLite source was not modified.")
        return 0
    finally:
        source_engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
