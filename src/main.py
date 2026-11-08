
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from api.routers.auth_router import auth_router
from api.routers.claim_router import claim_router
from api.routers.health_router import health_router
from api.routers.job_router import job_router
from api.routers.user_router import user_router
from api.routers.worker_router import worker_router

app = FastAPI()

app.include_router(job_router)
app.include_router(claim_router)
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(user_router)
app.include_router(worker_router)


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, exc: RequestValidationError):
    """Keep field locations/messages without echoing non-JSON numeric inputs."""
    # NaN and Infinity can be parsed from request JSON, but cannot be serialized
    # by the default validation response when it echoes the rejected input.
    return JSONResponse(status_code=422, content={
        "detail": [
            {key: error[key] for key in ("type", "loc", "msg")}
            for error in exc.errors()
        ],
    })
