"""DataChat — FastAPI Hauptanwendung."""
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from routes.upload import router as upload_router
from routes.query import router as query_router

app = FastAPI(title="DataChat", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload_router)
app.include_router(query_router)

# Serve frontend build if it exists (production)
_dist = Path(__file__).parent.parent / "frontend" / "dist"
if _dist.exists():
    app.mount("/assets", StaticFiles(directory=str(_dist / "assets")), name="assets")

    @app.get("/")
    def serve_index():
        return FileResponse(str(_dist / "index.html"))

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        file_path = _dist / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(_dist / "index.html"))
else:
    @app.get("/")
    def root():
        return {"status": "ok", "service": "DataChat"}
