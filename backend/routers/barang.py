from io import BytesIO
from pathlib import Path
import re
from zipfile import BadZipFile

import pandas as pd
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from openpyxl.utils.exceptions import InvalidFileException
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.auth import get_admin_user, get_current_user
from backend.database import get_db
from backend.models import Barang, KategoriBarang, Peminjaman, User
from backend.schemas import BarangCreate, BarangResponse, BarangUpdate
from backend.utils import log_aktivitas

router = APIRouter(prefix="/barang", tags=["Barang"])

EXCEL_COLUMNS = [
    "kode_barang",
    "nama_barang",
    "kategori",
    "laboratorium",
    "stok",
    "kondisi",
    "tahun_pengadaan",
]
EXCEL_HEADER_ALIASES = {
    "kode_barang": {"kode", "kodebarang"},
    "nama_barang": {"nama", "namabarang"},
    "kategori": {"kategori", "category", "kategoribarang", "namakategori"},
    "laboratorium": {"laboratorium", "lab", "namalab", "ruanglab"},
    "stok": {"stok", "stock", "jumlahstok", "quantity"},
    "kondisi": {"kondisi", "condition", "kondisibarang", "statuskondisi"},
    "tahun_pengadaan": {"tahun", "tahunpengadaan", "thn"},
}
REQUIRED_EXCEL_COLUMNS = set(EXCEL_HEADER_ALIASES) - {"tahun_pengadaan"}


def _cell_text(value: object) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _normalize_excel_header(value: object) -> str:
    return re.sub(r"[\W_]+", "", str(value).casefold())


def _normalize_condition(value: str) -> str:
    normalized = value.strip().casefold()
    if normalized == "perlu perbaikan":
        return "Perawatan"
    known_conditions = {
        "baik": "Baik",
        "perawatan": "Perawatan",
        "rusak": "Rusak",
    }
    return known_conditions.get(normalized, "Baik")


def _cell_integer(
    value: object,
    column: str,
    row_number: int,
    *,
    optional: bool = False,
) -> int | None:
    if pd.isna(value) or (isinstance(value, str) and not value.strip()):
        if optional:
            return None
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Baris {row_number}: kolom {column} wajib diisi dengan angka bulat.",
        )
    try:
        numeric_value = float(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Baris {row_number}: kolom {column} harus berupa angka bulat.",
        ) from exc
    if not numeric_value.is_integer():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Baris {row_number}: kolom {column} harus berupa angka bulat.",
        )
    result = int(numeric_value)
    minimum = 1 if column == "tahun_pengadaan" else 0
    if result < minimum or (column == "tahun_pengadaan" and result > 9999):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Baris {row_number}: kolom {column} di luar rentang yang valid.",
        )
    return result


@router.get("", response_model=list[BarangResponse])
def list_barang(
    kategori_id: int | None = Query(default=None, gt=0),
    laboratorium: str | None = Query(default=None, min_length=1),
    search: str | None = Query(default=None, min_length=1),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> list[Barang]:
    query = db.query(Barang)
    if kategori_id is not None:
        query = query.filter(Barang.kategori_id == kategori_id)
    if laboratorium:
        query = query.filter(Barang.laboratorium.ilike(f"%{laboratorium.strip()}%"))
    if search:
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(Barang.kode_barang.ilike(term), Barang.nama_barang.ilike(term))
        )
    return query.order_by(Barang.id).all()


@router.get("/template-excel")
def download_template_excel(
    _admin: User = Depends(get_admin_user),
) -> StreamingResponse:
    output = BytesIO()
    pd.DataFrame(columns=EXCEL_COLUMNS).to_excel(
        output,
        index=False,
        engine="openpyxl",
    )
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="template-barang.xlsx"'},
    )


@router.get("/{barang_id}", response_model=BarangResponse)
def get_barang(
    barang_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> Barang:
    barang = db.get(Barang, barang_id)
    if barang is None:
        raise HTTPException(status_code=404, detail="Barang tidak ditemukan")
    return barang


@router.post("/upload-excel", status_code=status.HTTP_200_OK)
def upload_barang_excel(
    file: UploadFile,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
) -> dict[str, int | str | list[dict[str, int | str]]]:
    if not file.filename or Path(file.filename).suffix.lower() != ".xlsx":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File harus berformat .xlsx.",
        )
    try:
        dataframe = pd.read_excel(
            BytesIO(file.file.read()),
            dtype=object,
            engine="openpyxl",
        )
    except (BadZipFile, InvalidFileException, ImportError, OSError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File Excel tidak dapat dibaca. Gunakan template .xlsx yang disediakan.",
        ) from exc
    finally:
        file.file.close()

    header_mapping: dict[str, str] = {}
    for column in dataframe.columns:
        normalized_header = _normalize_excel_header(column)
        matches = [
            field
            for field, aliases in EXCEL_HEADER_ALIASES.items()
            if normalized_header in aliases
        ]
        if not matches:
            continue
        field = matches[0]
        if field in header_mapping.values():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Header Excel memiliki lebih dari satu kolom untuk {field}.",
            )
        header_mapping[str(column)] = field

    mapped_fields = set(header_mapping.values())
    missing_fields = sorted(REQUIRED_EXCEL_COLUMNS - mapped_fields)
    if missing_fields:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "Kolom wajib tidak ditemukan: "
                f"{', '.join(missing_fields)}. Gunakan header seperti "
                "Kode Barang, Nama Barang, Kategori, Laboratorium, Stok, dan Kondisi."
            ),
        )
    if dataframe.empty:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="File Excel tidak berisi baris barang.",
        )

    dataframe = dataframe.rename(columns=header_mapping)
    seen_codes: set[str] = set()
    berhasil = 0
    gagal: list[dict[str, str | int]] = []
    for index, row in dataframe.iterrows():
        row_number = int(index) + 2
        values = {column: row.get(column) for column in EXCEL_COLUMNS}
        if all(
            pd.isna(value) or (isinstance(value, str) and not value.strip())
            for value in values.values()
        ):
            continue

        try:
            text_columns = (
                "kode_barang",
                "nama_barang",
                "kategori",
                "laboratorium",
            )
            text_values = {
                column: _cell_text(values[column]) for column in text_columns
            }
            for column, maximum in (
                ("kode_barang", 50),
                ("nama_barang", 150),
                ("kategori", 100),
                ("laboratorium", 100),
            ):
                value = text_values[column]
                if not value or len(value) > maximum:
                    raise ValueError(
                        f"kolom {column} wajib diisi dan maksimal {maximum} karakter"
                    )
            code = text_values["kode_barang"]
            if code in seen_codes or db.query(Barang.id).filter(
                Barang.kode_barang == code
            ).first():
                raise ValueError(f"kode_barang {code} sudah digunakan")
            stock = _cell_integer(values["stok"], "stok", row_number)
            year = _cell_integer(
                values["tahun_pengadaan"],
                "tahun_pengadaan",
                row_number,
                optional=True,
            )

            category = (
                db.query(KategoriBarang)
                .filter(KategoriBarang.nama_kategori.ilike(text_values["kategori"]))
                .first()
            )
            if category is None:
                category = KategoriBarang(nama_kategori=text_values["kategori"])
                db.add(category)
                db.flush()

            db.add(
                Barang(
                    kode_barang=code,
                    nama_barang=text_values["nama_barang"],
                    kategori_id=category.id,
                    laboratorium=text_values["laboratorium"],
                    stok=stock,
                    kondisi=_normalize_condition(_cell_text(values["kondisi"])),
                    tahun_pengadaan=year,
                )
            )
            db.commit()
            seen_codes.add(code)
            berhasil += 1
        except (ValueError, HTTPException) as exc:
            db.rollback()
            detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
            row_prefix = f"Baris {row_number}: "
            if isinstance(detail, str) and detail.startswith(row_prefix):
                detail = detail[len(row_prefix):]
            gagal.append({"baris": row_number, "alasan": str(detail)})
        except IntegrityError:
            db.rollback()
            gagal.append(
                {
                    "baris": row_number,
                    "alasan": "kode_barang atau kategori bertabrakan dengan data yang sudah ada",
                }
            )

    if berhasil == 0 and not gagal:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="File Excel tidak berisi baris barang yang valid.",
        )

    if berhasil:
        log_aktivitas(
            db,
            admin,
            "Upload Excel",
            "Barang",
            None,
            f"Berhasil mengimpor {berhasil} barang; {len(gagal)} baris gagal.",
            request.client.host if request.client else None,
        )
        db.commit()
    return {
        "jumlah_berhasil": berhasil,
        "jumlah_gagal": len(gagal),
        "gagal": gagal,
        "message": f"Berhasil mengunggah {berhasil} barang, {len(gagal)} gagal.",
    }


@router.post("", response_model=BarangResponse, status_code=status.HTTP_201_CREATED)
def create_barang(
    payload: BarangCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
) -> Barang:
    if db.get(KategoriBarang, payload.kategori_id) is None:
        raise HTTPException(status_code=404, detail="Kategori tidak ditemukan")

    barang = Barang(**payload.model_dump())
    db.add(barang)
    log_aktivitas(
        db,
        admin,
        "Tambah Barang",
        "Barang",
        f"{barang.kode_barang} / {barang.nama_barang}",
        f"Stok awal: {barang.stok}; kondisi: {barang.kondisi}.",
        request.client.host if request.client else None,
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Kode barang sudah digunakan",
        ) from exc
    db.refresh(barang)
    return barang


@router.put("/{barang_id}", response_model=BarangResponse)
def update_barang(
    barang_id: int,
    payload: BarangUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
) -> Barang:
    barang = db.get(Barang, barang_id)
    if barang is None:
        raise HTTPException(status_code=404, detail="Barang tidak ditemukan")

    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    if "tahun_pengadaan" in payload.model_fields_set:
        changes["tahun_pengadaan"] = payload.tahun_pengadaan
    previous_values = {field: getattr(barang, field) for field in changes}
    kategori_id = changes.get("kategori_id")
    if kategori_id is not None and db.get(KategoriBarang, kategori_id) is None:
        raise HTTPException(status_code=404, detail="Kategori tidak ditemukan")
    for field, value in changes.items():
        setattr(barang, field, value)
    detail = "; ".join(
        f"{field}: {previous_values[field]} → {value}"
        for field, value in changes.items()
        if previous_values[field] != value
    ) or "Tidak ada perubahan."
    log_aktivitas(
        db,
        admin,
        "Edit Barang",
        "Barang",
        f"{barang.kode_barang} / {barang.nama_barang}",
        detail,
        request.client.host if request.client else None,
    )

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Kode barang sudah digunakan atau data tidak valid",
        ) from exc
    db.refresh(barang)
    return barang


@router.delete("/{barang_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_barang(
    barang_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
) -> Response:
    barang = db.get(Barang, barang_id)
    if barang is None:
        raise HTTPException(status_code=404, detail="Barang tidak ditemukan")
    if db.query(Peminjaman.id).filter(Peminjaman.barang_id == barang_id).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Barang memiliki riwayat peminjaman dan tidak dapat dihapus",
        )

    log_aktivitas(
        db,
        admin,
        "Hapus Barang",
        "Barang",
        f"{barang.kode_barang} / {barang.nama_barang}",
        f"Stok terakhir: {barang.stok}; kondisi: {barang.kondisi}.",
        request.client.host if request.client else None,
    )
    db.delete(barang)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
