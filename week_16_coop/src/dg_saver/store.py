from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StorePreference(BaseModel):
    model_config = ConfigDict(frozen=True)

    display_name: str = Field(min_length=1)


@dataclass(frozen=True)
class ParsedStoreAddress:
    street: str
    city: str
    state: str
    postal_code: str

    @property
    def directory_url(self) -> str:
        city_slug = re.sub(r"[^a-z0-9]+", "-", self.city.casefold()).strip("-")
        return f"https://www.dollargeneral.com/store-directory/{self.state.lower()}/{city_slug}"

    @property
    def display_name(self) -> str:
        return f"{self.street}, {self.city}, {self.state} {self.postal_code}"


def load_store_preference(path: Path) -> StorePreference | None:
    if not path.exists():
        return None
    return StorePreference.model_validate_json(path.read_text(encoding="utf-8"))


def save_store_preference(path: Path, preference: StorePreference) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(preference.model_dump_json(indent=2), encoding="utf-8")


def clear_store_preference(path: Path) -> bool:
    if not path.exists():
        return False
    path.unlink()
    return True


def normalized_store_label(value: str) -> str:
    return " ".join(value.split())


def store_matches(expected: str, actual: str) -> bool:
    return normalized_store_label(expected).casefold() in normalized_store_label(actual).casefold()


def parse_store_address(value: str) -> ParsedStoreAddress:
    match = re.fullmatch(
        r"\s*(?P<street>.+?)\s*,\s*(?P<city>.+?)\s*,\s*"
        r"(?P<state>[A-Za-z]{2})\s+(?P<postal>\d{5}(?:-\d{4})?)\s*",
        value,
    )
    if not match:
        raise ValueError(
            "preferred store must be 'Street, City, ST ZIP' with an optional ZIP+4 suffix"
        )
    return ParsedStoreAddress(
        street=normalized_store_label(match.group("street")),
        city=normalized_store_label(match.group("city")),
        state=match.group("state").upper(),
        postal_code=match.group("postal"),
    )


def find_directory_match(
    expected: ParsedStoreAddress, listings: list[dict[str, str]]
) -> dict[str, str]:
    matches = []
    for listing in listings:
        lines = [
            normalized_store_label(line)
            for line in listing["text"].splitlines()
            if line.strip()
        ]
        if len(lines) < 2:
            continue
        displayed = f"{lines[0]}, {lines[1]}"
        if normalized_store_label(displayed).casefold() == expected.display_name.casefold():
            matches.append(listing)
    if len(matches) != 1:
        raise RuntimeError(
            f"expected exactly one official directory match for {expected.display_name!r}; "
            f"found {len(matches)}"
        )
    return matches[0]


def _wait_for_store_header(page: Any, expected: str, timeout_ms: int) -> str | None:
    order_button = page.get_by_role("button", name="Order type", exact=True)
    deadline = timeout_ms // 250
    for _ in range(deadline):
        if order_button.count() == 1:
            actual = normalized_store_label(order_button.inner_text())
            if store_matches(expected, actual):
                return actual
        page.wait_for_timeout(250)
    return None


def apply_configured_store(page: Any, display_name: str) -> str:
    """Resolve an exact official directory entry and apply it as an ephemeral guest store."""
    address = parse_store_address(display_name)
    page.goto(address.directory_url, wait_until="domcontentloaded")
    links = page.locator('a[href*="/store-directory/"]').evaluate_all(
        r"""links => links
          .filter(link => /\/\d+$/.test(link.getAttribute('href') || ''))
          .map(link => ({
            href: link.getAttribute('href') || '',
            text: link.parentElement?.innerText || ''
          }))"""
    )
    match = find_directory_match(address, links)
    store_number_match = re.search(r"/(\d+)$", match["href"])
    if not store_number_match:
        raise RuntimeError("official directory match has no store number")
    store_number = int(store_number_match.group(1))
    selector_url = (
        f"https://www.dollargeneral.com/deals/coupons?storeNumber={store_number}"
    )
    detail_selector_url = (
        f"https://www.dollargeneral.com{match['href']}?storeNumber={store_number}"
    )
    clean_url = "https://www.dollargeneral.com/deals/coupons"
    displayed = ""
    for _ in range(3):
        # The official store-detail page owns DG's URL-based store-selection bootstrap.
        page.goto(detail_selector_url, wait_until="domcontentloaded")
        page.wait_for_timeout(3_000)
        page.goto(selector_url, wait_until="domcontentloaded")
        page.get_by_role("heading", name="Explore Deals", exact=True).wait_for(
            state="visible", timeout=10_000
        )
        selected = _wait_for_store_header(page, address.display_name, timeout_ms=15_000)
        if not selected:
            continue

        # The selector writes guest-store state asynchronously. A clean URL proves that the
        # selected store will also govern the coupon and weekly-ad scans that follow.
        page.goto(clean_url, wait_until="domcontentloaded")
        page.get_by_role("heading", name="Explore Deals", exact=True).wait_for(
            state="visible", timeout=10_000
        )
        persisted = _wait_for_store_header(page, address.display_name, timeout_ms=10_000)
        if persisted:
            return persisted
        order_button = page.get_by_role("button", name="Order type", exact=True)
        if order_button.count() == 1:
            displayed = normalized_store_label(order_button.inner_text())

    raise RuntimeError(
        f"Dollar General selected a different store: expected {address.display_name!r}, "
        f"displayed {displayed!r}"
    )


def read_preferences_json(path: Path) -> dict[str, str]:
    """Return a non-secret representation for diagnostics and tests."""
    preference = load_store_preference(path)
    return json.loads(preference.model_dump_json()) if preference else {}
