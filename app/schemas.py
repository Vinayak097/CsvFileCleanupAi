from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel


class JobCreateResponse(BaseModel):
    job_id: UUID
    status: str
    filename: str
    message: str


class JobStatusSummary(BaseModel):
    row_count_raw: Optional[int] = None
    row_count_clean: Optional[int] = None
    anomaly_count: Optional[int] = None
    risk_level: Optional[str] = None


class JobStatusResponse(BaseModel):
    job_id: UUID
    status: str
    filename: str
    created_at: datetime
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    summary: Optional[JobStatusSummary] = None

    class Config:
        from_attributes = True


class TransactionOut(BaseModel):
    id: UUID
    txn_id: Optional[str] = None
    date: Optional[str] = None
    merchant: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    status: Optional[str] = None
    category: Optional[str] = None
    account_id: Optional[str] = None
    notes: Optional[str] = None
    is_anomaly: bool
    anomaly_reason: Optional[str] = None
    llm_category: Optional[str] = None
    llm_failed: bool

    class Config:
        from_attributes = True


class MerchantStat(BaseModel):
    name: str
    total_spend: float


class SummaryOut(BaseModel):
    total_spend_inr: Optional[float] = None
    total_spend_usd: Optional[float] = None
    top_merchants: Optional[List[Dict[str, Any]]] = None
    anomaly_count: int
    narrative: Optional[str] = None
    risk_level: Optional[str] = None
    category_breakdown: Optional[Dict[str, float]] = None


class JobResultsResponse(BaseModel):
    job_id: UUID
    status: str
    filename: str
    row_count_raw: Optional[int] = None
    row_count_clean: Optional[int] = None
    transactions: List[TransactionOut]
    anomalies: List[TransactionOut]
    summary: Optional[SummaryOut] = None

    class Config:
        from_attributes = True


class JobListItem(BaseModel):
    job_id: UUID
    status: str
    filename: str
    row_count_raw: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True
