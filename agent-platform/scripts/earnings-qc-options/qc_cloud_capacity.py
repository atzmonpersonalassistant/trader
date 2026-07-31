from __future__ import annotations

QC_CLOUD_RATE_LIMIT_STATUS = "BLOCKED_QC_CLOUD_RATE_LIMITED"
QC_CLOUD_NO_SPARE_NODES_STATUS = "BLOCKED_QC_CLOUD_NO_SPARE_NODES"
QC_CLOUD_CAPACITY_STATUSES = {
    QC_CLOUD_RATE_LIMIT_STATUS,
    QC_CLOUD_NO_SPARE_NODES_STATUS,
}


def classify_qc_cloud_capacity(text: str | None) -> dict | None:
    lowered = str(text or "").lower()
    if "too many backtest requests" in lowered:
        return {
            "status": QC_CLOUD_RATE_LIMIT_STATUS,
            "rate_limited": True,
            "error": "QuantConnect Cloud rejected the request as too many backtest requests; retry later/slower.",
            "error_class": "qc_cloud_rate_limit",
        }
    if "no spare nodes available" in lowered:
        return {
            "status": QC_CLOUD_NO_SPARE_NODES_STATUS,
            "capacity_blocked": True,
            "error": "QuantConnect Cloud has no spare nodes available for a new backtest.",
            "error_class": "qc_cloud_capacity",
        }
    return None


def is_qc_cloud_capacity_status(status: str | None) -> bool:
    return str(status or "") in QC_CLOUD_CAPACITY_STATUSES
