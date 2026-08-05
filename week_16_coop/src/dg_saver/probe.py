from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright
from pydantic import BaseModel, ConfigDict

COUPONS_URL = "https://www.dollargeneral.com/deals/coupons"
WEEKLY_ADS_URL = "https://www.dollargeneral.com/deals/weekly-ads"


class ProbeStatus(StrEnum):
    SUPPORTED = "supported"
    CHANGED = "changed"
    BLOCKED = "blocked"


class PageProbe(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    url: str
    status: ProbeStatus
    signals: dict[str, int | str | bool]
    limitations: list[str] = []


class FeasibilityReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    mode: str
    pages: list[PageProbe]
    stored_browser_state: bool = False
    authenticated: bool = False
    mutations_attempted: bool = False
    store_label: str | None = None

    @property
    def supported(self) -> bool:
        return bool(self.pages) and all(page.status is ProbeStatus.SUPPORTED for page in self.pages)

    def write_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=2), encoding="utf-8")


@dataclass
class _HtmlSignals:
    title: str = ""
    text: str = ""
    coupon_cards: int = 0
    advertised_coupon_count: int = 0
    clip_controls: int = 0
    weekly_offer_controls: int = 0
    iframes: int = 0


class _FixtureParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.signals = _HtmlSignals()
        self._in_title = False
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        self._in_title = tag == "title"
        test_id = attributes.get("data-testid")
        if test_id == "coupon-card":
            self.signals.coupon_cards += 1
        if attributes.get("data-total-coupons", "").isdigit():
            self.signals.advertised_coupon_count = int(attributes["data-total-coupons"])
        if test_id == "clip-control":
            self.signals.clip_controls += 1
        if test_id == "weekly-offer":
            self.signals.weekly_offer_controls += 1
        if tag == "iframe":
            self.signals.iframes += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        value = data.strip()
        if not value:
            return
        self._text.append(value)
        if self._in_title:
            self.signals.title += value

    def close(self) -> None:
        super().close()
        self.signals.text = " ".join(self._text)


def _parse_fixture(path: Path) -> _HtmlSignals:
    parser = _FixtureParser()
    parser.feed(path.read_text(encoding="utf-8"))
    parser.close()
    return parser.signals


def probe_fixtures(directory: Path) -> FeasibilityReport:
    coupons = _parse_fixture(directory / "coupons.html")
    weekly = _parse_fixture(directory / "weekly-ads.html")
    return FeasibilityReport(
        mode="fixture",
        pages=[
            _coupon_result(COUPONS_URL, coupons.title, coupons.text, coupons.coupon_cards,
                           coupons.clip_controls, coupons.advertised_coupon_count, 0,
                           coupons.coupon_cards == coupons.advertised_coupon_count),
            _weekly_result(WEEKLY_ADS_URL, weekly.title, weekly.text, weekly.iframes,
                           weekly.weekly_offer_controls),
        ],
    )


def _coupon_result(
    url: str,
    title: str,
    text: str,
    coupon_cards: int,
    clip_controls: int,
    advertised_count: int,
    load_more_clicks: int,
    all_coupons_loaded: bool,
) -> PageProbe:
    contract_ok = (
        "Explore Deals" in text
        and "Coupons & Cash Back" in text
        and advertised_count > 0
        and coupon_cards == advertised_count
        and all_coupons_loaded
    )
    return PageProbe(
        name="public coupons",
        url=url,
        status=ProbeStatus.SUPPORTED if contract_ok else ProbeStatus.CHANGED,
        signals={
            "title": title,
            "explore_deals_heading": "Explore Deals" in text,
            "coupon_cards": coupon_cards,
            "clip_controls_visible": clip_controls,
            "advertised_coupon_count": advertised_count,
            "load_more_clicks": load_more_clicks,
            "all_coupons_loaded": all_coupons_loaded,
        },
        limitations=["Coupon details and eligibility are not normalized in Phase 1."],
    )


def _weekly_result(
    url: str, title: str, text: str, iframes: int, weekly_offer_controls: int
) -> PageProbe:
    contract_ok = "Weekly Ads" in text and iframes > 0 and weekly_offer_controls > 0
    return PageProbe(
        name="public weekly ads",
        url=url,
        status=ProbeStatus.SUPPORTED if contract_ok else ProbeStatus.CHANGED,
        signals={
            "title": title,
            "weekly_ads_label": "Weekly Ads" in text,
            "iframes": iframes,
            "visible_offer_controls": weekly_offer_controls,
        },
        limitations=[
            "Store-specific availability and complete fine print are not parsed in Phase 1."
        ],
    )


def probe_live(
    *, timeout_ms: int = 30_000, select_store: Callable[[Any], str] | None = None
) -> FeasibilityReport:
    """Probe public pages in a headed, ephemeral Chrome context without account activity."""
    pages: list[PageProbe] = []
    store_label: str | None = None
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=False)
            context = browser.new_context()
            page = context.new_page()

            page.goto(COUPONS_URL, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(2_000)
            store_label = select_store(page) if select_store else None
            coupon_contract_text = " ".join(
                [
                    "Explore Deals"
                    if page.get_by_role("heading", name="Explore Deals").count()
                    else "",
                    "Coupons & Cash Back"
                    if page.get_by_role("tab", name="Coupons & Cash Back").count()
                    else "",
                ]
            )
            advertised_count = _wait_for_advertised_coupon_count(page)
            coupon_cards, load_more_clicks, all_loaded = _load_all_coupons(
                page, advertised_count
            )
            pages.append(
                _coupon_result(
                    page.url,
                    page.title(),
                    coupon_contract_text,
                    coupon_cards,
                    coupon_cards,
                    advertised_count,
                    load_more_clicks,
                    all_loaded,
                )
            )

            page.goto(WEEKLY_ADS_URL, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(2_000)
            weekly_contract_text = (
                "Weekly Ads" if page.get_by_role("tab", name="Weekly Ads").count() else ""
            )
            iframe_count = page.locator("iframe").count()
            offer_count = sum(
                frame.get_by_role("button").count()
                for frame in page.frames
                if frame != page.main_frame
            )
            pages.append(
                _weekly_result(
                    page.url,
                    page.title(),
                    weekly_contract_text,
                    iframe_count,
                    offer_count,
                )
            )
            context.close()
            browser.close()
    except PlaywrightError as error:
        pages.append(
            PageProbe(
                name="live browser access",
                url=COUPONS_URL,
                status=ProbeStatus.BLOCKED,
                signals={"error_type": type(error).__name__},
                limitations=["Dollar General or the local browser blocked the read-only probe."],
            )
        )
    return FeasibilityReport(mode="live", pages=pages, store_label=store_label)


def _load_all_coupons(page: Any, advertised_count: int) -> tuple[int, int, bool]:
    """Expand every coupon batch, rejecting missing, stalled, or inconsistent pagination."""
    coupon_controls = page.get_by_role("button", name="Clip this deal")
    loaded = coupon_controls.count()
    clicks = 0
    while loaded < advertised_count:
        load_more = page.get_by_role("button", name="Load more")
        if load_more.count() != 1:
            return loaded, clicks, False
        # DG sometimes leaves a global error/footer overlay above the still-functional public
        # pagination control. Target the exact visible Load more button and invoke it directly.
        load_more.click(force=True)
        clicks += 1
        previous = loaded
        for _ in range(40):
            page.wait_for_timeout(250)
            loaded = coupon_controls.count()
            if loaded > previous:
                break
        if loaded <= previous or clicks > advertised_count:
            return loaded, clicks, False
    load_more_remaining = page.get_by_role("button", name="Load more").count()
    return loaded, clicks, loaded == advertised_count and load_more_remaining == 0


def _wait_for_advertised_coupon_count(page: Any) -> int:
    """Wait for the store-aligned coupon request to replace its temporary zero count."""
    panel = page.get_by_role("tabpanel", name="Coupons & Cash Back")
    for _ in range(40):
        match = re.search(r"Coupons & Cash Back\s*\((\d+)\)", panel.inner_text())
        count = int(match.group(1)) if match else 0
        if count > 0 and page.get_by_role("button", name="Clip this deal").count() > 0:
            return count
        page.wait_for_timeout(250)
    raise RuntimeError("advertised coupon count did not become positive")


def report_as_dict(report: FeasibilityReport) -> dict[str, Any]:
    return json.loads(report.model_dump_json())
