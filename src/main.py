from fastapi import FastAPI

from api.routers.claim_router import claim_router
from api.routers.job_router import job_router
from database import engine
from models import Base

app = FastAPI()

Base.metadata.create_all(engine)

app.include_router(job_router)
app.include_router(claim_router)

