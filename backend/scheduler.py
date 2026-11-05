import logging
import os
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import joinedload, selectinload

from backend.database import SessionLocal
from backend.email_utils import send_return_reminder_email
from backend.models import DetailPeminjaman, Notifikasi, Peminjaman

logger = logging.getLogger(__name__)
SCHEDULER_TIMEZONE = os.getenv("SCHEDULER_TIMEZONE", "Asia/Jakarta")


def send_return_reminders(today: date | None = None) -> int:
    reminder_date = today or datetime.now(ZoneInfo(SCHEDULER_TIMEZONE)).date()
    local_timezone = ZoneInfo(SCHEDULER_TIMEZONE)
    day_start = datetime.combine(
        reminder_date, time.min, tzinfo=local_timezone
    ).astimezone(timezone.utc).replace(tzinfo=None)
    next_day = datetime.combine(
        reminder_date + timedelta(days=1), time.min, tzinfo=local_timezone
    ).astimezone(timezone.utc).replace(tzinfo=None)
    sent_count = 0

    with SessionLocal() as db:
        loans = (
            db.query(Peminjaman)
            .options(
                joinedload(Peminjaman.user),
                selectinload(Peminjaman.items).joinedload(DetailPeminjaman.barang),
            )
            .filter(Peminjaman.status == "Disetujui")
            .all()
        )

        for loan in loans:
            if loan.tanggal_kembali is None:
                continue

            due_date = loan.tanggal_kembali.date()
            late_days = (reminder_date - due_date).days
            item_names = ", ".join(
                sorted({item.barang.nama_barang for item in loan.items})
            )
            if not item_names:
                logger.warning(
                    "Peminjaman %s tidak memiliki detail barang; pengingat dilewati",
                    loan.kode_peminjaman,
                )
                continue
            if due_date == reminder_date + timedelta(days=1):
                message = (
                    f"Pengingat: Besok adalah batas akhir pengembalian barang "
                    f"{item_names}. Harap segera kembalikan ke laboran."
                )
                subject = "Pengingat Batas Pengembalian Barang"
            elif late_days > 0:
                message = (
                    f"Peringatan: Anda telah terlambat {late_days} hari dalam "
                    f"mengembalikan {item_names}. Harap segera kembalikan."
                )
                subject = "Peringatan Keterlambatan Pengembalian Barang"
            else:
                continue

            existing_reminder = (
                db.query(Notifikasi.id)
                .filter(
                    Notifikasi.user_id == loan.user_id,
                    Notifikasi.pesan == message,
                    Notifikasi.timestamp >= day_start,
                    Notifikasi.timestamp < next_day,
                )
                .first()
            )
            if existing_reminder is not None:
                continue

            db.add(Notifikasi(user_id=loan.user_id, pesan=message))
            db.commit()
            sent_count += 1

            try:
                send_return_reminder_email(
                    loan.user.email,
                    loan.user.nama_lengkap,
                    message,
                    subject,
                )
            except Exception:
                logger.exception(
                    "Gagal mengirim email pengingat untuk peminjaman %s",
                    loan.kode_peminjaman,
                )

    return sent_count


def start_return_reminder_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=ZoneInfo(SCHEDULER_TIMEZONE))
    scheduler.add_job(
        send_return_reminders,
        trigger=CronTrigger(hour=8, minute=0, timezone=ZoneInfo(SCHEDULER_TIMEZONE)),
        id="return-reminders",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    scheduler.start()
    logger.info(
        "Scheduler pengingat pengembalian berjalan setiap hari pukul 08:00 %s",
        SCHEDULER_TIMEZONE,
    )
    return scheduler


if __name__ == "__main__":
    print(f"Pengingat diproses: {send_return_reminders()}")
