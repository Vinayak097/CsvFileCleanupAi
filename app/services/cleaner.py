import re
from datetime import datetime

import pandas as pd


def _parse_date(val: str) -> str:
    """Normalise DD-MM-YYYY and YYYY/MM/DD → ISO 8601 (YYYY-MM-DD)."""
    if pd.isna(val) or not str(val).strip():
        return None
    val = str(val).strip()
    for fmt in ("%d-%m-%Y", "%Y/%m/%d", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(val, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return val  # return as-is if no format matched


def _strip_currency_symbol(val) -> float:
    """Remove leading $ (or other symbols) and convert to float."""
    if pd.isna(val):
        return None
    cleaned = re.sub(r"[^\d.]", "", str(val))
    try:
        return float(cleaned)
    except ValueError:
        return None


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    raw_count = len(df)

    # --- 1. Remove exact duplicate rows ---
    df = df.drop_duplicates()

    # --- 2. Normalise date formats ---
    df["date"] = df["date"].apply(_parse_date)

    # --- 3. Strip currency symbols from amount ---
    df["amount"] = df["amount"].apply(_strip_currency_symbol)

    # --- 4. Uppercase status ---
    df["status"] = df["status"].str.upper().str.strip()

    # --- 5. Uppercase currency ---
    df["currency"] = df["currency"].str.upper().str.strip()

    # --- 6. Fill missing category ---
    df["category"] = df["category"].fillna("").str.strip()
    df["category"] = df["category"].replace("", "Uncategorised")

    # --- 7. Strip whitespace from string columns ---
    for col in ["txn_id", "merchant", "account_id", "notes"]:
        df[col] = df[col].astype(str).str.strip().replace("nan", None).replace("", None)

    clean_count = len(df)
    return df, raw_count, clean_count
