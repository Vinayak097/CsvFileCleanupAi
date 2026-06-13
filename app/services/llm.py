import json
import logging
import re

import google.generativeai as genai
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings

logger = logging.getLogger(__name__)

VALID_CATEGORIES = {
    "Food", "Shopping", "Travel", "Transport",
    "Utilities", "Cash Withdrawal", "Entertainment", "Other",
}

genai.configure(api_key=settings.GEMINI_API_KEY)
_model = genai.GenerativeModel("gemini-1.5-flash")


def _extract_json(text: str):
    """Pull the first JSON object or array from a text blob."""
    match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", text)
    if match:
        return json.loads(match.group(1))
    return json.loads(text)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
def _call_gemini(prompt: str) -> str:
    response = _model.generate_content(prompt)
    return response.text


def classify_transactions_batch(transactions: list[dict]) -> list[str]:
    """
    Given a list of transaction dicts (merchant, amount, currency, notes),
    return a list of category strings in the same order.
    Falls back to 'Other' for any item that can't be classified.
    """
    if not transactions:
        return []

    items_json = json.dumps(
        [
            {
                "index": i,
                "merchant": t.get("merchant", ""),
                "amount": t.get("amount"),
                "currency": t.get("currency", ""),
                "notes": t.get("notes", ""),
            }
            for i, t in enumerate(transactions)
        ],
        indent=2,
    )

    prompt = f"""You are a financial transaction classifier.
Classify each transaction into exactly one of these categories:
Food, Shopping, Travel, Transport, Utilities, Cash Withdrawal, Entertainment, Other

Transactions (JSON array):
{items_json}

Return ONLY a JSON array of strings with one category per transaction, in the same order as the input.
Example for 3 transactions: ["Food", "Shopping", "Transport"]
Do not include any explanation. Return only the JSON array."""

    try:
        raw = _call_gemini(prompt)
        parsed = _extract_json(raw)
        if isinstance(parsed, list) and len(parsed) == len(transactions):
            return [
                cat if cat in VALID_CATEGORIES else "Other"
                for cat in parsed
            ]
    except Exception as e:
        logger.warning("LLM classification failed: %s", e)

    return ["Other"] * len(transactions)


def generate_narrative_summary(stats: dict) -> dict:
    """
    Call the LLM to produce a structured narrative summary.
    Returns a dict with keys: total_spend_inr, total_spend_usd,
    top_merchants, anomaly_count, narrative, risk_level.
    """
    prompt = f"""You are a financial analyst. Analyze the following transaction statistics and return a JSON summary.

Statistics:
{json.dumps(stats, indent=2)}

Return ONLY valid JSON with exactly these fields:
{{
  "total_spend_inr": <number>,
  "total_spend_usd": <number>,
  "top_merchants": [{{"name": "<string>", "total_spend": <number>}}],
  "anomaly_count": <integer>,
  "narrative": "<2-3 sentence spending narrative>",
  "risk_level": "<low|medium|high>"
}}

risk_level rules:
- high: anomaly_count > 5 or any transaction exceeds 10× the account median
- medium: anomaly_count 2-5
- low: anomaly_count 0-1

Return only the JSON object, no markdown fences."""

    try:
        raw = _call_gemini(prompt)
        return _extract_json(raw)
    except Exception as e:
        logger.warning("LLM narrative summary failed: %s", e)
        return {
            "total_spend_inr": stats.get("total_spend_inr", 0),
            "total_spend_usd": stats.get("total_spend_usd", 0),
            "top_merchants": stats.get("top_merchants", []),
            "anomaly_count": stats.get("anomaly_count", 0),
            "narrative": "LLM narrative generation failed.",
            "risk_level": "unknown",
        }
