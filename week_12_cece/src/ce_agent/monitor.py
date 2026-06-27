from __future__ import annotations

import hashlib
import html
import re
import urllib.request
from datetime import date
from pathlib import Path

from .db import connect

USER_AGENT = "CAS-CE-Agent/0.1 (personal policy monitor)"


def _plain_text(payload: bytes, content_type: str) -> str:
    if "pdf" in content_type.lower() or payload.startswith(b"%PDF"):
        return f"PDF binary SHA256: {hashlib.sha256(payload).hexdigest()}"
    text = payload.decode("utf-8", errors="replace")
    text = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def check_sources(db_path: str | Path) -> list[dict]:
    changes: list[dict] = []
    with connect(db_path) as db:
        sources = db.execute(
            "SELECT * FROM monitored_sources WHERE enabled=1 ORDER BY id"
        ).fetchall()
        for source in sources:
            try:
                request = urllib.request.Request(
                    source["url"], headers={"User-Agent": USER_AGENT}
                )
                with urllib.request.urlopen(request, timeout=30) as response:
                    payload = response.read()
                    content_type = response.headers.get("Content-Type", "")
                text = _plain_text(payload, content_type)
                digest = hashlib.sha256(payload).hexdigest()
                changed = bool(source["last_hash"] and source["last_hash"] != digest)
                db.execute(
                    """
                    INSERT INTO source_snapshots(source_id, content_hash, content_text)
                    VALUES (?, ?, ?)
                    """,
                    (source["id"], digest, text[:200_000]),
                )
                db.execute(
                    """
                    UPDATE monitored_sources
                    SET last_checked_at=CURRENT_TIMESTAMP, last_hash=?, last_error=NULL
                    WHERE id=?
                    """,
                    (digest, source["id"]),
                )
                if changed:
                    severity = "urgent" if source["source_type"] == "policy" else "info"
                    title = f'{source["name"]} changed'
                    body = (
                        "The monitored official source differs from the prior snapshot. "
                        "Review the source before changing CE classifications or requirements."
                    )
                    db.execute(
                        """
                        INSERT INTO alerts(alert_type, severity, title, body, source_url)
                        VALUES ('source_change', ?, ?, ?, ?)
                        """,
                        (severity, title, body, source["url"]),
                    )
                    changes.append(
                        {"name": source["name"], "url": source["url"], "severity": severity}
                    )
            except Exception as exc:
                db.execute(
                    """
                    UPDATE monitored_sources
                    SET last_checked_at=CURRENT_TIMESTAMP, last_error=?
                    WHERE id=?
                    """,
                    (str(exc), source["id"]),
                )
    return changes


def suggested_topics(gaps: dict[str, float]) -> list[str]:
    suggestions: list[str] = []
    if gaps.get("bias", 0):
        suggestions.append(
            "Bias: CAS Unconscious Bias Microlearning Series (on demand, about 60 minutes)."
        )
    if gaps.get("professionalism", 0):
        suggestions.append(
            "Professionalism: review the Code of Professional Conduct, relevant ASOPs, "
            "or attend a CAS professionalism webinar."
        )
    if gaps.get("organized", 0):
        suggestions.append(
            "Organized: choose a live CAS webinar where participants can ask questions."
        )
    if gaps.get("total", 0):
        suggestions.append(
            "Other relevant: read a paper directly relevant to your current actuarial practice "
            "and log actual study time."
        )
    return suggestions

