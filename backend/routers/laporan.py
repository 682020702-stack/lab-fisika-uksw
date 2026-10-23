from datetime import datetime
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.auth import get_admin_user
from backend.database import get_db
from backend.models import Barang, Peminjaman, User
from backend.schemas import PeminjamanResponse

router = APIRouter(prefix="/laporan", tags=["Laporan"])


def _query_transaksi(db: Session, dari: datetime | None, sampai: datetime | None):
    query = db.query(Peminjaman)
    if dari is not None:
        query = query.filter(Peminjaman.tanggal_pinjam >= dari)
    if sampai is not None:
        query = query.filter(Peminjaman.tanggal_pinjam <= sampai)
    return query.order_by(Peminjaman.tanggal_pinjam.desc()).all()


def _validate_dates(dari: datetime | None, sampai: datetime | None) -> None:
    if dari is not None and sampai is not None and dari > sampai:
        raise HTTPException(
            status_code=422, detail="Tanggal awal harus sebelum tanggal akhir"
        )


def _rows(transaksi: list[Peminjaman]) -> list[list[str | int]]:
    return [
        [
            item.kode_peminjaman,
            item.user_id,
            item.barang_id,
            item.jumlah,
            item.tanggal_pinjam.isoformat(sep=" "),
            item.tanggal_kembali.isoformat(sep=" ") if item.tanggal_kembali else "",
            item.status,
        ]
        for item in transaksi
    ]


@router.get("/transaksi", response_model=list[PeminjamanResponse])
def laporan_transaksi(
    dari: datetime | None = Query(default=None),
    sampai: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
    _admin: User = Depends(get_admin_user),
) -> list[Peminjaman]:
    _validate_dates(dari, sampai)
    return _query_transaksi(db, dari, sampai)


@router.get("/statistik")
def laporan_statistik(
    db: Session = Depends(get_db),
    _admin: User = Depends(get_admin_user),
) -> dict[str, int | dict[str, int]]:
    per_status = dict(
        db.query(Peminjaman.status, func.count(Peminjaman.id))
        .group_by(Peminjaman.status)
        .all()
    )
    return {
        "total_transaksi": db.query(func.count(Peminjaman.id)).scalar() or 0,
        "total_barang": db.query(func.count(Barang.id)).scalar() or 0,
        "total_pengguna": db.query(func.count(User.id)).scalar() or 0,
        "stok_barang": db.query(func.coalesce(func.sum(Barang.stok), 0)).scalar() or 0,
        "transaksi_per_status": per_status,
    }


@router.get("/export/pdf")
def export_pdf(
    dari: datetime | None = Query(default=None),
    sampai: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
    _admin: User = Depends(get_admin_user),
) -> StreamingResponse:
    _validate_dates(dari, sampai)
    rows = _rows(_query_transaksi(db, dari, sampai))
    output = BytesIO()
    document = SimpleDocTemplate(output, pagesize=landscape(letter))
    table = Table(
        [
            [
                "Kode",
                "User ID",
                "Barang ID",
                "Jumlah",
                "Tanggal Pinjam",
                "Tanggal Kembali",
                "Status",
            ],
            *rows,
        ],
        repeatRows=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#245b4a")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#b8c7c1")),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    document.build([table])
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="laporan-transaksi.pdf"'},
    )


@router.get("/export/excel")
def export_excel(
    dari: datetime | None = Query(default=None),
    sampai: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
    _admin: User = Depends(get_admin_user),
) -> StreamingResponse:
    _validate_dates(dari, sampai)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Transaksi"
    sheet.append(
        [
            "Kode",
            "User ID",
            "Barang ID",
            "Jumlah",
            "Tanggal Pinjam",
            "Tanggal Kembali",
            "Status",
        ]
    )
    for row in _rows(_query_transaksi(db, dari, sampai)):
        sheet.append(row)
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="laporan-transaksi.xlsx"'
        },
    )
