import logging
import uuid
from datetime import datetime, timezone

import pandas as pd

from app.celery_app import celery_app
from app.config import settings
from app.database import SessionLocal
from app.models import Job, JobSummary, Transaction
from app.services.anomaly import detect_anomalies
from app.services.cleaner import clean_dataframe
from app.services.llm import classify_transactions_batch, generate_narrative_summary

logger = logging.getLogger(__name__)

BATCH_SIZE = 20  # LLM classification batch size


def _update_job_status(db, job_id: str, status: str, error: str = None):
    job = db.query(Job).filter(Job.id == job_id).first()
    if job:
        job.status = status
        if error:
            job.error_message = error
        if status in ("completed", "failed"):
            job.completed_at = datetime.now(timezone.utc)
        db.commit()


@celery_app.task(bind=True, max_retries=0)
def process_job(self, job_id: str):
    db = SessionLocal()
    try:
        _update_job_status(db, job_id, "processing")

        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            logger.error("Job %s not found in DB", job_id)
            return

        # ── Step 1: Load CSV ──────────────────────────────────────────────────
        df = pd.read_csv(job.file_path, dtype=str, keep_default_na=False)
        df = df.rename(columns=lambda c: c.strip().lower())

        # ── Step 2: Clean ─────────────────────────────────────────────────────
        df, raw_count, clean_count = clean_dataframe(df)

        job.row_count_raw = raw_count
        job.row_count_clean = clean_count
        db.commit()

        # ── Step 3: Anomaly Detection ─────────────────────────────────────────
        df = detect_anomalies(df)

        # ── Step 4: LLM Classification (batched) ──────────────────────────────
        needs_llm = df["category"] == "Uncategorised"
        llm_indices = df.index[needs_llm].tolist()

        df["llm_category"] = None
        df["llm_raw_response"] = None
        df["llm_failed"] = False

        for i in range(0, len(llm_indices), BATCH_SIZE):
            batch_indices = llm_indices[i : i + BATCH_SIZE]
            batch_rows = df.loc[batch_indices].to_dict("records")

            try:
                categories = classify_transactions_batch(batch_rows)
                for idx, cat in zip(batch_indices, categories):
                    df.at[idx, "llm_category"] = cat
                    df.at[idx, "category"] = cat
            except Exception as e:
                logger.warning(
                    "LLM batch %d failed after retries: %s", i // BATCH_SIZE, e
                )
                for idx in batch_indices:
                    df.at[idx, "llm_failed"] = True
                    df.at[idx, "category"] = "Uncategorised"

        # ── Step 5: Persist Transactions ──────────────────────────────────────
        db.query(Transaction).filter(Transaction.job_id == job_id).delete()
        records = []
        for _, row in df.iterrows():
            records.append(
                Transaction(
                    id=uuid.uuid4(),
                    job_id=job_id,
                    txn_id=row.get("txn_id") or None,
                    date=row.get("date"),
                    merchant=row.get("merchant"),
                    amount=float(row["amount"]) if row.get("amount") not in (None, "") else None,
                    currency=row.get("currency"),
                    status=row.get("status"),
                    category=row.get("category"),
                    account_id=row.get("account_id"),
                    notes=row.get("notes"),
                    is_anomaly=bool(row.get("is_anomaly", False)),
                    anomaly_reason=row.get("anomaly_reason") or None,
                    llm_category=row.get("llm_category"),
                    llm_failed=bool(row.get("llm_failed", False)),
                )
            )
        db.bulk_save_objects(records)
        db.commit()

        # ── Step 6: LLM Narrative Summary ─────────────────────────────────────
        inr_df = df[df["currency"] == "INR"]
        usd_df = df[df["currency"] == "USD"]
        total_inr = float(inr_df["amount"].sum()) if not inr_df.empty else 0.0
        total_usd = float(usd_df["amount"].sum()) if not usd_df.empty else 0.0

        merchant_spend = (
            df.groupby("merchant")["amount"]
            .sum()
            .sort_values(ascending=False)
            .head(3)
        )
        top_merchants = [
            {"name": m, "total_spend": round(float(v), 2)}
            for m, v in merchant_spend.items()
        ]

        category_spend = (
            df.groupby("category")["amount"]
            .sum()
            .round(2)
            .to_dict()
        )

        anomaly_count = int(df["is_anomaly"].sum())

        stats = {
            "total_spend_inr": round(total_inr, 2),
            "total_spend_usd": round(total_usd, 2),
            "top_merchants": top_merchants,
            "anomaly_count": anomaly_count,
            "category_breakdown": {k: round(float(v), 2) for k, v in category_spend.items()},
            "total_transactions": len(df),
        }

        llm_summary = generate_narrative_summary(stats)

        db.query(JobSummary).filter(JobSummary.job_id == job_id).delete()
        summary = JobSummary(
            id=uuid.uuid4(),
            job_id=job_id,
            total_spend_inr=llm_summary.get("total_spend_inr", total_inr),
            total_spend_usd=llm_summary.get("total_spend_usd", total_usd),
            top_merchants=llm_summary.get("top_merchants", top_merchants),
            anomaly_count=llm_summary.get("anomaly_count", anomaly_count),
            narrative=llm_summary.get("narrative", ""),
            risk_level=llm_summary.get("risk_level", "unknown"),
            category_breakdown=category_spend,
        )
        db.add(summary)
        db.commit()

        _update_job_status(db, job_id, "completed")
        logger.info("Job %s completed. %d rows cleaned, %d anomalies.", job_id, clean_count, anomaly_count)

    except Exception as exc:
        logger.exception("Job %s failed: %s", job_id, exc)
        try:
            _update_job_status(db, job_id, "failed", str(exc))
        except Exception:
            pass
    finally:
        db.close()
