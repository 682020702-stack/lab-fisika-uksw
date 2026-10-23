from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from backend.database import (
    Base,
    engine,
    migrate_legacy_activity_logs,
    migrate_legacy_schema,
)
from backend.rate_limiter import limiter
from backend.seed import seed_categories, seed_test_users
from backend.routers.aktivitas import router as aktivitas_router
from backend.routers.auth import router as auth_router
from backend.routers.barang import router as barang_router
from backend.routers.kategori import router as kategori_router
from backend.routers.laporan import router as laporan_router
from backend.routers.notifikasi import router as notifikasi_router
from backend.routers.peminjaman import router as peminjaman_router
from backend.routers.users import router as users_router

FRONTEND_DIRECTORY = Path(__file__).resolve().parents[1] / "frontend"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    migrate_legacy_schema()
    Base.metadata.create_all(bind=engine)
    seed_test_users()
    seed_categories()
    migrate_legacy_activity_logs()
    yield


app = FastAPI(
    title="Sistem Laboratorium Fisika UKSW API",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(
    RateLimitExceeded,
    lambda _request, _exc: JSONResponse(
        status_code=429,
        content={
            "detail": "Terlalu banyak percobaan. Silakan coba lagi dalam 1 menit."
        },
    ),
)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def revalidate_frontend_files(request: Request, call_next):
    """Always check the latest HTML/JS/CSS when navigating between pages."""
    response = await call_next(request)
    path = request.url.path.lower()
    if request.method in {"GET", "HEAD"} and (
        path == "/" or path.endswith((".html", ".js", ".css"))
    ):
        is_html = path == "/" or path.endswith(".html")
        response.headers["Cache-Control"] = (
            "no-store, no-cache, max-age=0, must-revalidate" if is_html
            else "no-cache, max-age=0, must-revalidate"
        )
        if is_html:
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
    return response


app.include_router(auth_router)
app.include_router(users_router)
app.include_router(barang_router)
app.include_router(kategori_router)
app.include_router(peminjaman_router)
app.include_router(laporan_router)
app.include_router(notifikasi_router)
app.include_router(aktivitas_router)


@app.get("/api/health", tags=["Health"])
def health_check() -> dict[str, str]:
    return {"status": "ok", "message": "Sistem Laboratorium Fisika UKSW API"}


@app.api_route("/loans.html", methods=["GET", "HEAD"], include_in_schema=False)
def loans_page() -> FileResponse:
    return FileResponse(FRONTEND_DIRECTORY / "loans.html", media_type="text/html")


app.mount("/", StaticFiles(directory=str(FRONTEND_DIRECTORY), html=True), name="frontend")
