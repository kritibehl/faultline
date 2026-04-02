from fastapi import FastAPI
from common.observability.tracing import configure_tracing
from api.routes.jobs import router as jobs_router

configure_tracing()

app = FastAPI(title="Faultline")
app.include_router(jobs_router)
