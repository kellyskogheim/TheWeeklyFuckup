from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Iterable, Mapping


@dataclass(frozen=True)
class Requirements:
    total: float = 30.0
    organized: float = 6.0
    professionalism: float = 3.0
    bias: float = 1.0
    general_business_max: float = 3.0
    specific: float = 15.0
    specific_organized: float = 6.0


@dataclass
class Progress:
    year: int
    total: float
    organized: float
    professionalism: float
    bias: float
    general_business: float
    specific: float
    specific_organized: float
    requirements: Requirements

    def gaps(self, include_specific: bool = False) -> dict[str, float]:
        req = self.requirements
        gaps = {
            "total": max(0.0, req.total - self.total),
            "organized": max(0.0, req.organized - self.organized),
            "professionalism": max(0.0, req.professionalism - self.professionalism),
            "bias": max(0.0, req.bias - self.bias),
        }
        if include_specific:
            gaps["specific"] = max(0.0, req.specific - self.specific)
            gaps["specific_organized"] = max(
                0.0, req.specific_organized - self.specific_organized
            )
        return gaps

    def to_dict(self, include_specific: bool = False) -> dict:
        return {
            **asdict(self),
            "requirements": asdict(self.requirements),
            "gaps": self.gaps(include_specific),
        }


def _hours(row: Mapping) -> float:
    return round(int(row["minutes"]) / 50.0, 2)


def calculate_progress(
    rows: Iterable[Mapping], year: int, requirements: Requirements | None = None
) -> Progress:
    req = requirements or Requirements()
    completed = [
        row
        for row in rows
        if row["status"] == "completed"
        and str(row["completed_on"]).startswith(f"{year}-")
        and row["ce_type"] != "Unclassified"
        and row["activity_kind"] != "Unclassified"
    ]
    general_business_raw = sum(
        _hours(row) for row in completed if row["ce_type"] == "General Business"
    )
    countable_general_business = min(req.general_business_max, general_business_raw)
    non_business = sum(
        _hours(row) for row in completed if row["ce_type"] != "General Business"
    )
    return Progress(
        year=year,
        total=round(non_business + countable_general_business, 2),
        organized=round(
            sum(_hours(row) for row in completed if row["activity_kind"] == "Organized"),
            2,
        ),
        professionalism=round(
            sum(_hours(row) for row in completed if row["ce_type"] == "Professionalism"),
            2,
        ),
        bias=round(sum(_hours(row) for row in completed if row["bias_topic"]), 2),
        general_business=round(general_business_raw, 2),
        specific=round(sum(_hours(row) for row in completed if row["specific_education"]), 2),
        specific_organized=round(
            sum(
                _hours(row)
                for row in completed
                if row["specific_education"] and row["activity_kind"] == "Organized"
            ),
            2,
        ),
        requirements=req,
    )


def risk_level(progress: Progress, as_of: date | None = None, include_specific: bool = False) -> str:
    today = as_of or date.today()
    gaps = progress.gaps(include_specific)
    if not any(gaps.values()):
        return "on_track"
    days_left = max(0, (date(progress.year, 12, 31) - today).days)
    if days_left <= 45 or gaps.get("organized", 0) > 3 or gaps.get("professionalism", 0) > 2:
        return "urgent"
    elapsed_fraction = min(1.0, max(0.0, (today.timetuple().tm_yday - 1) / 365))
    expected = progress.requirements.total * elapsed_fraction
    return "warning" if progress.total + 5 < expected else "watch"

