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
from openpyxl import Workbook
from openpyxl.utils.exceptions import InvalidFileException
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from backend.auth import get_admin_user, get_current_user
from backend.database import get_db
from backend.models import Barang, DetailPeminjaman, KategoriBarang, User
from backend.schemas import (
    BarangBulkDeleteRequest,
    BarangCreate,
    BarangResponse,
    BarangUpdate,
)
from backend.utils import log_aktivitas

router = APIRouter(prefix="/barang", tags=["Barang"])

EXCEL_COLUMNS = [
    "kode_barang",
    "nama_barang",
    "kategori",
    "laboratorium",
    "stok",
    "satuan",  # UPDATE BARANG: satuan disertakan pada template dan ekspor.
    "kondisi",
    "tahun_pengadaan",
]
EXCEL_HEADER_ALIASES = {
    "kode_barang": {"kode", "kodebarang"},
    "nama_barang": {"nama", "namabarang"},
    "kategori": {"kategori", "category", "kategoribarang", "namakategori"},
    "laboratorium": {"laboratorium", "lokasi", "lab", "namalab", "ruanglab"},  # UPDATE BARANG: impor juga menerima header Lokasi.
    "stok": {"stok", "stock", "jumlahstok", "quantity"},
    "satuan": {"satuan", "unit"},
    "kondisi": {"kondisi", "condition", "kondisibarang", "statuskondisi"},
    "tahun_pengadaan": {"tahun", "tahunpengadaan", "thn"},
}
REQUIRED_EXCEL_COLUMNS = set(EXCEL_HEADER_ALIASES) - {"tahun_pengadaan", "satuan"}  # UPDATE BARANG: satuan opsional untuk template Excel lama.


def _query_barang(
    db: Session,
    kategori_id: int | None = None,
    laboratorium: str | None = None,
    search: str | None = None,
) -> list[Barang]:
    query = db.query(Barang).options(joinedload(Barang.kategori))
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
    return _query_barang(db, kategori_id, laboratorium, search)


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


@router.get("/export/excel")
def export_barang_excel(
    db: Session = Depends(get_db),
    _admin: User = Depends(get_admin_user),
) -> StreamingResponse:
    items = _query_barang(db)
    if not items:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Data tidak ditemukan.",
        )

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Barang"
    sheet.append(EXCEL_COLUMNS)
    for item in items:
        sheet.append(
            [
                item.kode_barang,
                item.nama_barang,
                item.kategori.nama_kategori,
                item.laboratorium,
                item.stok,
                item.kondisi,
                item.tahun_pengadaan,
            ]
        )
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions

    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="data-barang.xlsx"'},
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
) -> dict[str, object]:
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
    # VALIDASI UPLOAD: nama barang yang ada di database menjadi acuan deteksi duplikat case-insensitive.
    seen_names = {
        nama.strip().casefold() for (nama,) in db.query(Barang.nama_barang).all()
    }
    seen_codes = {kode for (kode,) in db.query(Barang.kode_barang).all()}
    prepared_rows: list[dict[str, object]] = []
    gagal: list[dict[str, str | int]] = []
    category_by_name = {
        category.nama_kategori.strip().casefold(): category
        for category in db.query(KategoriBarang).all()
    }

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
                "satuan",
            )
            text_values = {
                column: _cell_text(values[column]) for column in text_columns
            }
            for column, maximum in (
                ("kode_barang", 50),
                ("nama_barang", 150),
                ("kategori", 100),
                ("laboratorium", 100),
                ("satuan", 50),
            ):
                value = text_values[column]
                if column == "satuan" and not value:
                    text_values[column] = "unit"
                    continue
                if not value or len(value) > maximum:
                    raise ValueError(
                        f"kolom {column} wajib diisi dan maksimal {maximum} karakter"
                    )

            # VALIDASI UPLOAD: tandai nama database/file sebagai duplikat sebelum menyimpan baris.
            item_name = text_values["nama_barang"]
            normalized_name = item_name.casefold()
            if normalized_name in seen_names:
                gagal.append(
                    {
                        "baris": row_number,
                        "nama_barang": item_name,
                        "alasan": "nama barang sudah ada (duplikat)",
                    }
                )
                continue
            seen_names.add(normalized_name)

            code = text_values["kode_barang"]
            if code in seen_codes:
                raise ValueError(f"kode_barang {code} sudah digunakan")
            stock = _cell_integer(values["stok"], "stok", row_number)
            year = _cell_integer(
                values["tahun_pengadaan"],
                "tahun_pengadaan",
                row_number,
                optional=True,
            )

            prepared_rows.append(
                {
                    "baris": row_number,
                    "kode_barang": code,
                    "nama_barang": item_name,
                    "kategori": text_values["kategori"],
                    "laboratorium": text_values["laboratorium"],
                    "stok": stock,
                    "satuan": text_values["satuan"],
                    "kondisi": _normalize_condition(_cell_text(values["kondisi"])),
                    "tahun_pengadaan": year,
                }
            )
            seen_codes.add(code)
        except (ValueError, HTTPException) as exc:
            detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
            row_prefix = f"Baris {row_number}: "
            if isinstance(detail, str) and detail.startswith(row_prefix):
                detail = detail[len(row_prefix):]
            gagal.append({"baris": row_number, "alasan": str(detail)})

    if not prepared_rows and not gagal:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="File Excel tidak berisi baris barang yang valid.",
        )

    berhasil = 0
    # VALIDASI UPLOAD: simpan seluruh baris valid dan log dalam satu transaksi atomik.
    try:
        for values in prepared_rows:
            category_name = str(values["kategori"])
            category_key = category_name.casefold()
            category = category_by_name.get(category_key)
            if category is None:
                category = KategoriBarang(nama_kategori=category_name)
                db.add(category)
                db.flush()
                category_by_name[category_key] = category

            db.add(
                Barang(
                    kode_barang=str(values["kode_barang"]),
                    nama_barang=str(values["nama_barang"]),
                    kategori_id=category.id,
                    laboratorium=str(values["laboratorium"]),
                    stok=values["stok"],
                    satuan=str(values["satuan"]),  # UPDATE BARANG: pertahankan satuan dari Excel.
                    kondisi=str(values["kondisi"]),
                    tahun_pengadaan=values["tahun_pengadaan"],
                )
            )
            berhasil += 1

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
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Impor dibatalkan karena kode barang atau kategori bertabrakan dengan data yang ada.",
        ) from exc
    except Exception:
        db.rollback()
        raise

    duplicate_failures = [
        item
        for item in gagal
        if item.get("alasan") == "nama barang sudah ada (duplikat)"
    ]
    nama_duplikat = list(
        dict.fromkeys(
            str(item["nama_barang"])
            for item in duplicate_failures
        )
    )
    message = (
        f"Berhasil mengimpor {berhasil} barang. Gagal mengimpor "
        f"{len(duplicate_failures)} "
        "barang karena duplikat "
        f"(daftar nama barang: {', '.join(nama_duplikat) if nama_duplikat else 'tidak ada'})."
    )
    if len(gagal) > len(duplicate_failures):
        message += f" Total baris gagal: {len(gagal)}."
    return {
        "jumlah_berhasil": berhasil,
        "jumlah_gagal": len(gagal),
        "nama_duplikat": nama_duplikat,
        "gagal": gagal,
        "message": message,
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
    new_code = changes.get("kode_barang")
    if new_code is not None and (
        db.query(Barang.id)
        .filter(Barang.kode_barang == new_code, Barang.id != barang_id)
        .first()
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Kode Barang sudah digunakan",  # UPDATE BARANG: tolak kode unik yang sudah terpakai.
        )
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
        duplicate_code = (
            db.query(Barang.id)
            .filter(
                Barang.kode_barang == new_code,
                Barang.id != barang_id,
            )
            .first()
            if new_code is not None
            else None
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Kode Barang sudah digunakan"
                if duplicate_code
                else "Perubahan barang tidak dapat disimpan karena konflik data"
            ),  # UPDATE BARANG: sampaikan pesan spesifik bila terjadi benturan kode saat commit.
        ) from exc
    db.refresh(barang)
    return barang


# BULK BARANG: penghapusan massal Admin berjalan atomik dan mempertahankan batasan riwayat.
@router.delete("/bulk")
def bulk_delete_barang(
    payload: BarangBulkDeleteRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
) -> dict[str, int]:
    barang_ids = payload.barang_ids
    items = db.query(Barang).filter(Barang.id.in_(barang_ids)).all()
    found_ids = {item.id for item in items}
    missing_ids = sorted(set(barang_ids) - found_ids)
    if missing_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Barang tidak ditemukan: {', '.join(map(str, missing_ids))}",
        )

    blocked_ids = sorted(
        barang_id
        for (barang_id,) in db.query(DetailPeminjaman.barang_id)
        .filter(DetailPeminjaman.barang_id.in_(barang_ids))
        .distinct()
        .all()
    )
    if blocked_ids:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Barang dengan riwayat peminjaman tidak dapat dihapus: "
                f"{', '.join(map(str, blocked_ids))}"
            ),
        )

    log_aktivitas(
        db,
        admin,
        "Hapus Barang Massal",
        "Barang",
        f"{len(items)} barang",
        f"ID barang: {', '.join(map(str, sorted(barang_ids)))}",
        request.client.host if request.client else None,
    )
    try:
        for item in items:
            db.delete(item)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Barang terpilih memiliki data terkait dan tidak dapat dihapus",
        ) from exc
    return {"deleted_count": len(items)}


# BERSIH DUPLIKAT: pertahankan barang dengan ID terkecil dan alihkan riwayatnya sebelum menghapus sisanya.
@router.delete("/bersihkan-duplikat")
def clean_duplicate_barang(
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
) -> dict[str, int]:
    items = db.query(Barang).order_by(Barang.id).all()
    grouped_items: dict[str, list[Barang]] = {}
    for item in items:
        normalized_name = item.nama_barang.strip().casefold()
        grouped_items.setdefault(normalized_name, []).append(item)

    duplicate_groups = [
        group for group in grouped_items.values() if len(group) > 1
    ]
    deleted_count = sum(len(group) - 1 for group in duplicate_groups)
    for group in duplicate_groups:
        keeper = group[0]
        for duplicate in group[1:]:
            db.query(DetailPeminjaman).filter(
                DetailPeminjaman.barang_id == duplicate.id
            ).update(
                {DetailPeminjaman.barang_id: keeper.id},
                synchronize_session=False,
            )
            db.delete(duplicate)

    log_aktivitas(
        db,
        admin,
        "Bersihkan Duplikat Barang",
        "Barang",
        None,
        f"Barang duplikat yang dihapus: {deleted_count}.",
        request.client.host if request.client else None,
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Pembersihan dibatalkan karena barang duplikat memiliki relasi data yang tidak dapat dipindahkan.",
        ) from exc
    return {"deleted_count": deleted_count}


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
    if (
        db.query(DetailPeminjaman.id)
        .filter(DetailPeminjaman.barang_id == barang_id)
        .first()
    ):
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
