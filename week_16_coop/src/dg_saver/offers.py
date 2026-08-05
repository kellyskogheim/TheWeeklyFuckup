from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright
from pydantic import BaseModel, ConfigDict

from dg_saver.probe import (
    COUPONS_URL,
    WEEKLY_ADS_URL,
    _load_all_coupons,
    _wait_for_advertised_coupon_count,
)


class OfferType(StrEnum):
    DIGITAL_COUPON = "digital_coupon"
    CASH_BACK = "cash_back"
    WEEKLY_AD = "weekly_ad"
    UNKNOWN = "unknown"


class Issuer(StrEnum):
    DG_STORE = "dg_store"
    MANUFACTURER = "manufacturer"
    UNKNOWN = "unknown"


class CouponOffer(BaseModel):
    model_config = ConfigDict(frozen=True)

    offer_id: str
    ordinal: int
    offer_type: OfferType
    brand: str
    savings_text: str
    savings_cents: int | None
    description: str
    expiration_date: date | None
    minimum_quantity: int | None
    redemption_limit: int | None
    issuer: Issuer
    badges: list[str]
    image_alt: str | None
    visible_fields_complete: bool
    full_terms_review_required: bool = True
    review_reasons: list[str]


class WeeklyAdOffer(BaseModel):
    model_config = ConfigDict(frozen=True)

    offer_id: str
    ordinal: int
    text: str
    price_text: str | None
    full_terms_review_required: bool = True


class OfferReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    generated_at: datetime
    source_urls: list[str]
    advertised_coupon_count: int
    coupon_count: int
    weekly_ad_offer_count: int
    all_coupons_loaded: bool
    load_more_clicks: int
    authenticated: bool = False
    mutations_attempted: bool = False
    store_label: str | None = None
    coupons: list[CouponOffer]
    weekly_ad_offers: list[WeeklyAdOffer]

    @property
    def review_required_count(self) -> int:
        return sum(offer.full_terms_review_required for offer in self.coupons) + sum(
            offer.full_terms_review_required for offer in self.weekly_ad_offers
        )

    def write_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=2), encoding="utf-8")


def _fingerprint(*parts: str) -> str:
    normalized = "\x1f".join(" ".join(part.split()).casefold() for part in parts)
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def _money_to_cents(text: str) -> int | None:
    match = re.search(r"\$\s*(\d+(?:\.\d{1,2})?)", text)
    if match:
        return round(float(match.group(1)) * 100)
    cents = re.search(r"(\d+)\s*¢", text)
    return int(cents.group(1)) if cents else None


def _number_badge(badges: list[str], prefix: str) -> int | None:
    for badge in badges:
        match = re.fullmatch(rf"{prefix}\s+(\d+)", badge, flags=re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def _expiration(badges: list[str]) -> date | None:
    for badge in badges:
        try:
            return datetime.strptime(badge.strip(), "%m/%d/%y").date()
        except ValueError:
            continue
    return None


def normalize_coupon(raw: dict[str, Any], ordinal: int) -> CouponOffer:
    tag = str(raw.get("tag", "")).strip().upper()
    offer_type = {
        "DIGITAL COUPON": OfferType.DIGITAL_COUPON,
        "CASH BACK": OfferType.CASH_BACK,
    }.get(tag, OfferType.UNKNOWN)
    brand = str(raw.get("brand", "")).strip()
    savings = str(raw.get("summary", "")).strip()
    description = str(raw.get("description", "")).strip()
    badges = [str(value).strip() for value in raw.get("badges", []) if str(value).strip()]
    issuer = Issuer.UNKNOWN
    if any(value.upper() == "DG STORE" for value in badges):
        issuer = Issuer.DG_STORE
    elif any(value.upper() == "MANUFACTURER" for value in badges):
        issuer = Issuer.MANUFACTURER
    expiration = _expiration(badges)
    review_reasons: list[str] = ["full terms are available only on the detail page"]
    if not brand or not savings or not description:
        review_reasons.append("one or more visible fields are missing")
    if _money_to_cents(savings) is None:
        review_reasons.append("savings amount could not be normalized")
    if offer_type is OfferType.DIGITAL_COUPON and expiration is None:
        review_reasons.append("digital coupon expiration is missing")
    if offer_type is OfferType.UNKNOWN:
        review_reasons.append("offer type is unknown")
    visible_complete = len(review_reasons) == 1
    return CouponOffer(
        offer_id=_fingerprint(tag, brand, savings, description, "|".join(badges)),
        ordinal=ordinal,
        offer_type=offer_type,
        brand=brand,
        savings_text=savings,
        savings_cents=_money_to_cents(savings),
        description=description,
        expiration_date=expiration,
        minimum_quantity=_number_badge(badges, "MUST BUY"),
        redemption_limit=_number_badge(badges, "LIMIT"),
        issuer=issuer,
        badges=badges,
        image_alt=str(raw.get("image_alt") or "").strip() or None,
        visible_fields_complete=visible_complete,
        review_reasons=review_reasons,
    )


def normalize_weekly_offer(text: str, ordinal: int) -> WeeklyAdOffer:
    cleaned = " ".join(text.split())
    price_match = re.search(
        r"(?:SALE|Everyday|Reg\.|Final Price With Coupon)?\s*"
        r"(?:\d+\s+for\s+)?\$\d+(?:\.\d{1,2})?",
        cleaned,
        flags=re.IGNORECASE,
    )
    return WeeklyAdOffer(
        offer_id=_fingerprint(cleaned),
        ordinal=ordinal,
        text=cleaned,
        price_text=price_match.group(0).strip() if price_match else None,
    )


def report_from_raw(
    raw_coupons: list[dict[str, Any]],
    weekly_texts: list[str],
    *,
    advertised_count: int,
    load_more_clicks: int,
    all_loaded: bool,
    store_label: str | None = None,
) -> OfferReport:
    coupons = [normalize_coupon(raw, index) for index, raw in enumerate(raw_coupons, 1)]
    weekly = [
        normalize_weekly_offer(text, index)
        for index, text in enumerate(weekly_texts, 1)
        if text.strip()
    ]
    return OfferReport(
        generated_at=datetime.now().astimezone(),
        source_urls=[COUPONS_URL, WEEKLY_ADS_URL],
        advertised_coupon_count=advertised_count,
        coupon_count=len(coupons),
        weekly_ad_offer_count=len(weekly),
        all_coupons_loaded=all_loaded,
        load_more_clicks=load_more_clicks,
        store_label=store_label,
        coupons=coupons,
        weekly_ad_offers=weekly,
    )


def extract_fixture_offers(directory: Path) -> OfferReport:
    raw_coupons = json.loads((directory / "coupon-cards.json").read_text(encoding="utf-8"))
    weekly = json.loads((directory / "weekly-offers.json").read_text(encoding="utf-8"))
    return report_from_raw(
        raw_coupons,
        weekly,
        advertised_count=len(raw_coupons),
        load_more_clicks=0,
        all_loaded=True,
    )


def extract_live_offers(
    *, timeout_ms: int = 30_000, select_store: Callable[[Any], str] | None = None
) -> OfferReport:
    """Extract every public offer from headed ephemeral Chrome without account activity."""
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=False)
            context = browser.new_context()
            page = context.new_page()
            page.goto(COUPONS_URL, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(2_000)
            store_label = select_store(page) if select_store else None
            advertised = _wait_for_advertised_coupon_count(page)
            loaded, clicks, complete = _load_all_coupons(page, advertised)
            if not complete or loaded != advertised:
                raise RuntimeError(f"coupon pagination incomplete: {loaded} of {advertised}")
            raw_coupons = page.locator(".coupon-tile").evaluate_all(
                """elements => elements.map(element => ({
                    tag: element.querySelector('[class*="couponTag_"]')?.innerText || '',
                    brand: element.querySelector('[class*="tile_brandName__"]')?.innerText || '',
                    summary:
                      element.querySelector('[class*="tile_offerSummary__"]')?.innerText || '',
                    description:
                      element.querySelector('[class*="tile_offerDescription__"]')?.innerText || '',
                    badges: Array.from(element.querySelectorAll('[class*="pill_root__"]'))
                      .map(node => node.innerText.trim()).filter(Boolean),
                    image_alt: element.querySelector('img')?.getAttribute('alt') || null
                }))"""
            )
            if len(raw_coupons) != advertised:
                raise RuntimeError("coupon extraction count does not match advertised total")

            page.close()
            page = context.new_page()
            page.goto(WEEKLY_ADS_URL, wait_until="domcontentloaded", timeout=timeout_ms)
            weekly_texts = _wait_for_weekly_offers(page)
            if not weekly_texts:
                raise RuntimeError("weekly-ad viewer loaded without readable offers")
            report = report_from_raw(
                raw_coupons,
                weekly_texts,
                advertised_count=advertised,
                load_more_clicks=clicks,
                all_loaded=complete,
                store_label=store_label,
            )
            context.close()
            browser.close()
            return report
    except PlaywrightError as error:
        raise RuntimeError(
            f"public offer extraction was blocked or the page changed: {error}"
        ) from error


def _wait_for_weekly_offers(page: Any) -> list[str]:
    """Wait for the cross-origin ad viewer and return only its item-level offer labels."""
    for _ in range(40):
        offers: list[str] = []
        for frame in page.frames:
            if frame == page.main_frame:
                continue
            try:
                offers.extend(
                    frame.locator('button[aria-label*="Select for details."]').evaluate_all(
                        "buttons => buttons.map(button => button.getAttribute('aria-label') || '')"
                    )
                )
            except PlaywrightError:
                # The ad vendor replaces loading frames; use a fresh frame list next poll.
                continue
        if offers:
            return [
                re.sub(r"\s*\. Select for details\.\s*$", "", text).strip()
                for text in offers
                if text.strip()
            ]
        page.wait_for_timeout(250)
    return []
