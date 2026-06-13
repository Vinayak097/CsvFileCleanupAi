import os
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Job, JobSummary, Transaction
from app.schemas import (
    JobCreateResponse,
    JobListItem,
    JobResultsResponse,
    JobStatusResponse,
    JobStatusSummary,
    SummaryOut,
    TransactionOut,
)
from app.tasks.processing import process_job

router = APIRouter()

REQUIRED_COLUMNS = {
    "txn_id", "date", "merchant", "amount",
    "currency", "status", "category", "account_id", "notes",
}


@router.post("/upload", response_model=JobCreateResponse, status_code=202)
async def upload_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are accepted.")

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # Quick column validation
    first_line = contents.split(b"\n")[0].decode("utf-8", errors="replace").strip()
    headers = {h.strip().lower() for h in first_line.split(",")}
    missing = REQUIRED_COLUMNS - headers
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"CSV is missing required columns: {missing}",
        )

    job_id = uuid.uuid4()
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    file_path = os.path.join(settings.UPLOAD_DIR, f"{job_id}.csv")

    with open(file_path, "wb") as f:
        f.write(contents)

    job = Job(
        id=job_id,
        filename=file.filename,
        status="pending",
        file_path=file_path,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    process_job.delay(str(job_id))

    return JobCreateResponse(
        job_id=job_id,
        status="pending",
        filename=file.filename,
        message="Job enqueued. Poll /jobs/{job_id}/status for progress.",
    )


@router.get("/{job_id}/status", response_model=JobStatusResponse)
def get_job_status(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    summary_data = None
    if job.status == "completed" and job.summary:
        summary_data = JobStatusSummary(
            row_count_raw=job.row_count_raw,
            row_count_clean=job.row_count_clean,
            anomaly_count=job.summary.anomaly_count,
            risk_level=job.summary.risk_level,
        )

    return JobStatusResponse(
        job_id=job.id,
        status=job.status,
        filename=job.filename,
        created_at=job.created_at,
        completed_at=job.completed_at,
        error_message=job.error_message,
        summary=summary_data,
    )


@router.get("/{job_id}/results", response_model=JobResultsResponse)
def get_job_results(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job.status not in ("completed", "failed"):
        raise HTTPException(
            status_code=202,
            detail=f"Job is still {job.status}. Try again later.",
        )

    transactions = db.query(Transaction).filter(Transaction.job_id == job_id).all()
    anomalies = [t for t in transactions if t.is_anomaly]

    summary_out = None
    if job.summary:
        s = job.summary
        summary_out = SummaryOut(
            total_spend_inr=float(s.total_spend_inr) if s.total_spend_inr else None,
            total_spend_usd=float(s.total_spend_usd) if s.total_spend_usd else None,
            top_merchants=s.top_merchants,
            anomaly_count=s.anomaly_count,
            narrative=s.narrative,
            risk_level=s.risk_level,
            category_breakdown=s.category_breakdown,
        )

    txn_out = [
        TransactionOut(
            id=t.id,
            txn_id=t.txn_id,
            date=t.date,
            merchant=t.merchant,
            amount=float(t.amount) if t.amount is not None else None,
            currency=t.currency,
            status=t.status,
            category=t.category,
            account_id=t.account_id,
            notes=t.notes,
            is_anomaly=t.is_anomaly,
            anomaly_reason=t.anomaly_reason,
            llm_category=t.llm_category,
            llm_failed=t.llm_failed,
        )
        for t in transactions
    ]

    anomaly_out = [t for t in txn_out if t.is_anomaly]

    return JobResultsResponse(
        job_id=job.id,
        status=job.status,
        filename=job.filename,
        row_count_raw=job.row_count_raw,
        row_count_clean=job.row_count_clean,
        transactions=txn_out,
        anomalies=anomaly_out,
        summary=summary_out,
    )


@router.get("", response_model=List[JobListItem])
def list_jobs(
    status: Optional[str] = Query(None, description="Filter by status"),
    db: Session = Depends(get_db),
):
    query = db.query(Job)
    if status:
        query = query.filter(Job.status == status)
    jobs = query.order_by(Job.created_at.desc()).all()
    return [
        JobListItem(
            job_id=j.id,
            status=j.status,
            filename=j.filename,
            row_count_raw=j.row_count_raw,
            created_at=j.created_at,
        )
        for j in jobs
    ]
