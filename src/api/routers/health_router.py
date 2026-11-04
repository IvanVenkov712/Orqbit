from fastapi import APIRouter
from fastapi.responses import JSONResponse

from health import database_is_ready

health_router = APIRouter(prefix="/health", tags=["health"])


@health_router.get("")
@health_router.get("/live")
def liveness() -> dict[str, str]:
    """Report that the API responds, independently of PostgreSQL."""
    return {"status": "ok"}


@health_router.get("/ready", responses={503: {"description": "Not ready"}})
def readiness() -> JSONResponse:
    ready = database_is_ready()
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"status": "ready" if ready else "not_ready"},
        headers={"Cache-Control": "no-store"},
    )
