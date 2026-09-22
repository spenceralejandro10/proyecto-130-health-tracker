from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .config import ensure_runtime_dirs, settings
from .db import Base, engine
from .routers.api import router as api_router
from .web import router as web_router

ensure_runtime_dirs()
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Seguimiento longitudinal, auditoría de datos y soporte de decisiones para Proyecto 130.",
)

app.include_router(api_router)
app.include_router(web_router)
app.mount("/static", StaticFiles(directory=str(Path(__file__).resolve().parent / "static")), name="static")
