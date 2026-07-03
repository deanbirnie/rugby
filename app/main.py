from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app import config
from app.database import init_db
from app.routers import admin, predict, public
from app.security import NotAuthenticated, ensure_crypto_ready


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_crypto_ready()
    init_db()
    yield


app = FastAPI(title=config.APP_NAME, lifespan=lifespan)

app.add_middleware(SessionMiddleware, secret_key=config.SESSION_SECRET, same_site="lax")

static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.exception_handler(NotAuthenticated)
async def not_authenticated_handler(request: Request, exc: NotAuthenticated):
    return RedirectResponse(url="/admin/login", status_code=303)


app.include_router(public.router)
app.include_router(predict.router)
app.include_router(admin.router)
