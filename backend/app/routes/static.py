from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse

from app.config import resolve_static_dir

router = APIRouter()

STATIC_DIR = resolve_static_dir()

FALLBACK_HTML = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>PM MVP</title>
    <style>
      body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 40px; color: #032147; }
      h1 { margin-bottom: 8px; }
      p { color: #888888; }
      code { background: #f7f8fb; padding: 2px 6px; border-radius: 6px; }
    </style>
  </head>
  <body>
    <h1>Project Management MVP</h1>
    <p>FastAPI backend is running.</p>
    <p>Try <code>/api/hello</code> or <code>/health</code>.</p>
  </body>
</html>"""


@router.get("/", response_class=HTMLResponse)
def root():
    if STATIC_DIR:
        index_path = STATIC_DIR / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
    return FALLBACK_HTML


@router.get("/{full_path:path}", include_in_schema=False)
def static_fallback(full_path: str):
    if not STATIC_DIR:
        return HTMLResponse("Not found", status_code=404)

    resolved_static_dir = STATIC_DIR.resolve()
    requested_path = (STATIC_DIR / full_path).resolve()
    if not requested_path.is_relative_to(resolved_static_dir):
        return HTMLResponse("Not found", status_code=404)

    if requested_path.is_dir():
        index_path = requested_path / "index.html"
        if index_path.exists():
            return FileResponse(index_path)

    if requested_path.exists():
        return FileResponse(requested_path)

    index_path = resolved_static_dir / "index.html"
    if index_path.exists():
        return FileResponse(index_path)

    return HTMLResponse("Not found", status_code=404)


def get_static_dir() -> Path | None:
    return STATIC_DIR
