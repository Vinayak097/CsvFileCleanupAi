import pandas as pd

DOMESTIC_MERCHANTS = {
    "swiggy", "ola", "irctc", "zomato", "jio recharge", "jio",
    "airtel", "blinkit", "bigbasket", "myntra", "nykaa", "rapido",
    "flipkart", "phonepe transfer", "phonepe",
}


def detect_anomalies(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["is_anomaly"] = False
    df["anomaly_reason"] = ""

    # --- Statistical outlier: amount > 3x account median ---
    medians = (
        df.groupby("account_id")["amount"]
        .median()
        .rename("acct_median")
    )
    df = df.join(medians, on="account_id")

    outlier_mask = df["amount"] > (3 * df["acct_median"])
    df.loc[outlier_mask, "is_anomaly"] = True
    df.loc[outlier_mask, "anomaly_reason"] = (
        df.loc[outlier_mask].apply(
            lambda r: f"Amount {r['amount']:.2f} exceeds 3× account median ({r['acct_median']:.2f})",
            axis=1,
        )
    )

    # --- USD with domestic-only merchant ---
    def _is_domestic_usd(row):
        merchant_lower = str(row.get("merchant", "")).lower().strip()
        currency = str(row.get("currency", "")).upper().strip()
        return currency == "USD" and any(
            dm in merchant_lower for dm in DOMESTIC_MERCHANTS
        )

    domestic_usd_mask = df.apply(_is_domestic_usd, axis=1)
    df.loc[domestic_usd_mask, "is_anomaly"] = True

    def _append_reason(existing, new_part):
        return f"{existing}; {new_part}" if existing else new_part

    df.loc[domestic_usd_mask, "anomaly_reason"] = df.loc[domestic_usd_mask].apply(
        lambda r: _append_reason(
            r["anomaly_reason"],
            f"USD charged to domestic-only merchant '{r['merchant']}'",
        ),
        axis=1,
    )

    df = df.drop(columns=["acct_median"])
    return df
