from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.database import init_db
from app.routes import api_router, static_router
from app.routes.static import get_static_dir


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(lifespan=lifespan)

# Allows `npm run dev` (port 3000) to call this backend directly during local
# development. Production serves the built frontend from this same origin, so
# these headers are simply unused there.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _mount_static_assets(static_dir) -> None:
    next_assets = static_dir / "_next"
    if next_assets.exists():
        app.mount("/_next", StaticFiles(directory=next_assets), name="next-assets")
    static_assets = static_dir / "static"
    if static_assets.exists():
        app.mount("/static", StaticFiles(directory=static_assets), name="static-assets")


STATIC_DIR = get_static_dir()
if STATIC_DIR:
    _mount_static_assets(STATIC_DIR)


@app.get("/health")
def health_check() -> dict:
    return {"status": "ok"}


@app.get("/api/hello")
def hello() -> dict:
    return {"message": "Hello from FastAPI"}


app.include_router(api_router)
app.include_router(static_router)
