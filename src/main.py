from fastapi import FastAPI

from api.routers.claim_router import claim_router
from api.routers.job_router import job_router

app = FastAPI()

app.include_router(job_router)
app.include_router(claim_router)

