from pathlib import Path

from dg_saver.probe import ProbeStatus, _load_all_coupons, probe_fixtures

FIXTURES = Path(__file__).parent / "fixtures"


def test_sanitized_public_fixtures_satisfy_phase_one_contract() -> None:
    report = probe_fixtures(FIXTURES)

    assert report.supported
    assert report.authenticated is False
    assert report.stored_browser_state is False
    assert report.mutations_attempted is False
    assert all(page.status is ProbeStatus.SUPPORTED for page in report.pages)


def test_coupon_fixture_exposes_read_only_signals() -> None:
    report = probe_fixtures(FIXTURES)
    coupons = report.pages[0]

    assert coupons.signals["coupon_cards"] == 2
    assert coupons.signals["clip_controls_visible"] == 2
    assert coupons.signals["advertised_coupon_count"] == 2
    assert coupons.signals["all_coupons_loaded"] is True


def test_fixture_probe_fails_closed_when_contract_changes(tmp_path: Path) -> None:
    (tmp_path / "coupons.html").write_text("<title>Changed</title>", encoding="utf-8")
    (tmp_path / "weekly-ads.html").write_text("<title>Changed</title>", encoding="utf-8")

    report = probe_fixtures(tmp_path)

    assert report.supported is False
    assert all(page.status is ProbeStatus.CHANGED for page in report.pages)


class _FakeCouponPage:
    def __init__(self, batches: list[int], *, keep_load_more: bool = False) -> None:
        self.batches = batches
        self.loaded = batches[0]
        self.batch_index = 0
        self.keep_load_more = keep_load_more

    def get_by_role(self, role: str, name: str):  # noqa: ANN201
        assert role == "button"
        return _FakeLocator(self, name)

    def wait_for_timeout(self, _milliseconds: int) -> None:
        return None


class _FakeLocator:
    def __init__(self, page: _FakeCouponPage, name: str) -> None:
        self.page = page
        self.name = name

    def count(self) -> int:
        if self.name == "Clip this deal":
            return self.page.loaded
        has_next = self.page.batch_index < len(self.page.batches) - 1
        return int(has_next or self.page.keep_load_more)

    def click(self, *, force: bool = False) -> None:
        assert force is True
        if self.page.batch_index < len(self.page.batches) - 1:
            self.page.batch_index += 1
            self.page.loaded = self.page.batches[self.page.batch_index]


def test_load_all_coupons_expands_every_increasing_batch() -> None:
    page = _FakeCouponPage([21, 41, 61, 75])

    loaded, clicks, complete = _load_all_coupons(page, advertised_count=75)

    assert (loaded, clicks, complete) == (75, 3, True)


def test_load_all_coupons_fails_closed_on_stalled_batch() -> None:
    page = _FakeCouponPage([21], keep_load_more=True)

    loaded, clicks, complete = _load_all_coupons(page, advertised_count=40)

    assert (loaded, clicks, complete) == (21, 1, False)


def test_load_all_coupons_requires_load_more_to_disappear() -> None:
    page = _FakeCouponPage([21, 40], keep_load_more=True)

    loaded, clicks, complete = _load_all_coupons(page, advertised_count=40)

    assert (loaded, clicks, complete) == (40, 1, False)
