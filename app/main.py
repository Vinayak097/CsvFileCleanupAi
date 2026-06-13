from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, engine
from app.routers import jobs

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="AI Transaction Processing Pipeline",
    description="Async CSV ingestion → cleaning → anomaly detection → LLM classification",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs.router, prefix="/jobs", tags=["jobs"])


@app.get("/health")
def health():
    return {"status": "ok"}
