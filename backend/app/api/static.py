from pathlib import Path

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

log = structlog.get_logger()


def mount_frontend(app: FastAPI, dist_dir: Path) -> None:
    index = dist_dir / "index.html"
    if not index.is_file():
        log.warning("frontend dist not found, serving API only", dist=str(dist_dir))
        return
    assets = dist_dir / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404)
        candidate = dist_dir / full_path
        is_within_dist = candidate.resolve().is_relative_to(dist_dir.resolve())
        if full_path and candidate.is_file() and is_within_dist:
            return FileResponse(candidate)
        # The index names the hashed bundles, so a stale page runs the old app.
        # no-cache revalidates it on every load; the assets themselves are
        # content-hashed and cache fine.
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
