import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import async_session
from .migrations import run_migrations
from .routers import admin, ai, auth, billing, connections, me, system, telegram, webhooks, workflows
from .seed import run_seed
from .services.maintenance import scheduler_loop
from .services.telegram_service import poller

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("flowmind")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Миграции и seed не должны убивать весь процесс: на Render free Postgres
    # иногда недоступна при cold start — лучше отдать 503 на /health, чем 502 на всё.
    for attempt in range(1, 6):
        try:
            if settings.auto_migrate:
                await run_migrations()
            async with async_session() as db:
                await run_seed(db)
            break
        except Exception as exc:
            log.exception("startup DB init failed (attempt %s/5): %s", attempt, exc)
            if attempt == 5:
                log.error("Продолжаю без успешной инициализации БД — /api/health вернёт 503")
            else:
                await asyncio.sleep(min(2 ** attempt, 15))
    if not settings.secret_key or not settings.secret_key.strip():
        log.error("SECRET_KEY пуст — вход и JWT работать не будут. Задайте SECRET_KEY в .env")
    elif settings.secret_key == "dev-insecure-change-me":
        if settings.is_cloud:
            log.warning("SECRET_KEY не задан — используется небезопасное значение по умолчанию!")
        else:
            log.info("SECRET_KEY не задан — локальный dev-ключ. Для облака задайте длинную случайную строку.")
    scheduler = asyncio.create_task(scheduler_loop())
    if settings.effective_telegram_mode == "polling":
        poller.start()
    log.info("FlowMind AI запущен: режим=%s, авторизация=%s, оплата=%s, telegram=%s",
             settings.deployment_mode, settings.auth_required, settings.payment_provider, settings.effective_telegram_mode)
    yield
    scheduler.cancel()
    await poller.stop()


show_docs = settings.is_local or settings.demo_mode
app = FastAPI(
    title="FlowMind AI", version="1.0.0", lifespan=lifespan,
    docs_url="/api/docs" if show_docs else None, redoc_url=None,
    openapi_url="/api/openapi.json" if show_docs else None,
)

app.add_middleware(
    CORSMiddleware, allow_origins=settings.cors_list, allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    if settings.secure_cookies:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


for module in (system, auth, me, workflows, webhooks, connections, billing, telegram, admin, ai):
    app.include_router(module.router, prefix="/api")


# ───── раздача собранного фронтенда (один образ — и API, и сайт) ─────
if settings.static_dir and Path(settings.static_dir).is_dir():
    STATIC = Path(settings.static_dir).resolve()
    if (STATIC / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(404, "Not found")
        candidate = (STATIC / full_path).resolve()
        if full_path and candidate.is_file() and STATIC in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(STATIC / "index.html")
