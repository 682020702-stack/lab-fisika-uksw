"""Printable borrowing receipts; all displayed values come from the database."""

from datetime import datetime
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

import reportlab
from reportlab.lib import colors
from reportlab.lib.pagesizes import A5
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)


def _date(value: datetime | None) -> str:
    if value is None:
        return "-"
    months = ("Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des")
    return f"{value.day:02d}-{months[value.month - 1]}-{value.year} {value:%H:%M}"


def build_loan_receipt(loan) -> BytesIO:
    """A5 PDF Build"""
    output = BytesIO()
    forest = colors.HexColor("#005024")
    line = colors.HexColor("#dce5dd")
    fonts = Path(reportlab.__file__).parent / "fonts"
    regular, bold = "Helvetica", "Helvetica-Bold"
    if (fonts / "Vera.ttf").is_file() and (fonts / "VeraBd.ttf").is_file():
        regular, bold = "LabReceiptRegular", "LabReceiptBold"
        if regular not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(regular, str(fonts / "Vera.ttf")))
            pdfmetrics.registerFont(TTFont(bold, str(fonts / "VeraBd.ttf")))
    body = ParagraphStyle("ReceiptBody", fontName=regular, fontSize=9,
                          leading=12, textColor=colors.HexColor("#18231d"),
                          splitLongWords=True)
    small = ParagraphStyle("ReceiptSmall", parent=body, fontSize=8, leading=11,
                           textColor=colors.HexColor("#53645a"))
    heading = ParagraphStyle("ReceiptHeading", parent=body, fontName=bold,
                             fontSize=10, leading=13, textColor=forest)
    title = ParagraphStyle("ReceiptTitle", parent=heading, fontSize=14, leading=17)
    document = SimpleDocTemplate(output, pagesize=A5, rightMargin=12*mm,
                                 leftMargin=12*mm, topMargin=10*mm,
                                 bottomMargin=13*mm,
                                 title=f"Bukti Peminjaman {loan.kode_peminjaman}",
                                 author="Laboratorium Fisika dan Pembelajaran Fisika UKSW")
    width = A5[0] - 24*mm

    def p(value, style=body):
        text = "-" if value is None or value == "" else str(value)
        return Paragraph(escape(text).replace("\n", "<br/>"), style)

    def section(label, rows):
        story.extend([Spacer(1, 8), p(label, heading), Spacer(1, 4)])
        table = Table([[p(key, small), p(value)] for key, value in rows],
                      colWidths=[40*mm, width - 40*mm], hAlign="LEFT")
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LINEBELOW", (0, 0), (-1, -1), .3, line),
        ]))
        story.append(table)

    logo_path = Path(__file__).resolve().parents[1] / "frontend/assets/FSM_UKSW.png"
    header = [p("BUKTI PEMINJAMAN", title), p("Laboratorium Fisika UKSW", heading),
              p("Sistem Inventaris Laboratorium", small)]
    if logo_path.is_file():
        logo = Image(str(logo_path))
        logo.drawHeight = 30*mm * logo.imageHeight / logo.imageWidth
        logo.drawWidth = 30*mm
        header_table = Table([[header, logo]], colWidths=[width - 32*mm, 32*mm])
        header_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]))
        story = [header_table]
    else:
        story = header

    section("TRANSAKSI", [("Kode peminjaman", loan.kode_peminjaman),
                           ("Status saat ekspor", loan.status)])
    user = loan.user
    section("PEMINJAM", [("Nama", user.nama_lengkap),
                         ("Username / Email", user.username),
                         ("Tipe pengguna", user.tipe_user or user.role)])
    item_rows = [[p("Kode / Nama barang", small), p("Jumlah / Kondisi", small)]]
    item_rows.extend(
        [
            p(f"{detail.barang.kode_barang} / {detail.barang.nama_barang}"),
            p(
                f"{detail.jumlah} unit / "
                f"{detail.kondisi_saat_pinjam}"
            ),
        ]
        for detail in loan.items
    )
    items_table = Table(
        item_rows,
        colWidths=[width * 0.68, width * 0.32],
        repeatRows=1,
        hAlign="LEFT",
    )
    items_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#edf5e3")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("GRID", (0, 0), (-1, -1), .3, line),
            ]
        )
    )
    section(
        "BARANG DAN JADWAL",
        [
            ("Tanggal pinjam", _date(loan.tanggal_pinjam)),
            ("Batas pengembalian", _date(loan.tanggal_kembali)),
        ],
    )
    story.extend([Spacer(1, 4), items_table])
    if loan.keterangan:
        section("KEPERLUAN / KETERANGAN", [("Keterangan", loan.keterangan)])
    if loan.jumlah_kembali is not None:
        section("PENGEMBALIAN", [("Tanggal aktual", _date(loan.tanggal_kembali_aktual)),
                                 ("Jumlah total / Kondisi", f"{loan.jumlah_kembali} unit / {loan.kondisi_kembali}"),
                                 ("Keterlambatan", f"{loan.terlambat_hari or 0} hari"),
                                 ("Denda tercatat", "Rp " + f"{loan.denda or 0:,}".replace(",", "."))])
        if loan.catatan_admin:
            section("CATATAN PETUGAS", [("Catatan", loan.catatan_admin)])

    notes = {
        "Menunggu": "Pengajuan masih menunggu persetujuan. Bukti ini belum menjadi izin pengambilan barang.",
        "Ditolak": "Pengajuan ditolak. Bukti ini bukan izin pengambilan barang.",
        "Disetujui": "Pengajuan disetujui. Tunjukkan bukti ini kepada petugas saat pengambilan barang dan kembalikan sesuai jadwal.",
    }
    note = notes.get(loan.status, "Pengembalian sudah dicatat. Simpan bukti ini sebagai arsip transaksi Anda.")
    story.extend([Spacer(1, 10), p(note, small)])
    if loan.status == "Disetujui":
        signatures = Table([[p("Peminjam", small), p("Petugas laboratorium", small)],
                            [Spacer(1, 18*mm), ""],
                            [p("(_____________________)", small), p("(_____________________)", small)]],
                           colWidths=[width/2, width/2])
        story.append(KeepTogether([Spacer(1, 8), signatures]))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(line)
        canvas.line(12*mm, 10*mm, A5[0]-12*mm, 10*mm)
        canvas.setFont(regular, 6.5)
        canvas.setFillColor(colors.HexColor("#53645a"))
        canvas.drawString(12*mm, 6*mm, f"{loan.kode_peminjaman} | Diekspor {_date(exported_at)}")
        canvas.drawRightString(A5[0]-12*mm, 6*mm, f"Hal. {doc.page}")
        canvas.restoreState()

    exported_at = datetime.now()
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    output.seek(0)
    return output
