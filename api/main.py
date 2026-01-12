from fastapi import FastAPI
from api.routes.jobs import router as jobs_router

app = FastAPI(title="Faultline")
app.include_router(jobs_router)
