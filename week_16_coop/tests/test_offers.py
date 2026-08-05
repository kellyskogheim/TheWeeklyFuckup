from pathlib import Path

from dg_saver.offers import (
    Issuer,
    OfferType,
    extract_fixture_offers,
    normalize_coupon,
    normalize_weekly_offer,
    report_from_raw,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_fixture_extraction_normalizes_coupon_fields() -> None:
    report = extract_fixture_offers(FIXTURES)
    coupon = report.coupons[0]

    assert report.coupon_count == report.advertised_coupon_count == 2
    assert coupon.offer_type is OfferType.DIGITAL_COUPON
    assert coupon.savings_cents == 150
    assert coupon.minimum_quantity == 2
    assert coupon.expiration_date.isoformat() == "2049-12-31"
    assert coupon.issuer is Issuer.MANUFACTURER
    assert coupon.visible_fields_complete is True
    assert coupon.full_terms_review_required is True


def test_cash_back_limit_and_issuer_are_normalized() -> None:
    offer = extract_fixture_offers(FIXTURES).coupons[1]

    assert offer.offer_type is OfferType.CASH_BACK
    assert offer.redemption_limit == 5
    assert offer.issuer is Issuer.DG_STORE


def test_weekly_offer_preserves_text_and_extracts_price_phrase() -> None:
    offer = normalize_weekly_offer("Example Soap, SALE 2 for $4.00", 1)

    assert offer.text == "Example Soap, SALE 2 for $4.00"
    assert offer.price_text == "SALE 2 for $4.00"


def test_offer_ids_are_deterministic() -> None:
    first = extract_fixture_offers(FIXTURES)
    second = extract_fixture_offers(FIXTURES)

    first_ids = [offer.offer_id for offer in first.coupons]
    second_ids = [offer.offer_id for offer in second.coupons]
    assert first_ids == second_ids


def test_unparseable_savings_are_flagged_instead_of_guessed() -> None:
    offer = normalize_coupon(
        {
            "tag": "DIGITAL COUPON",
            "brand": "Example",
            "summary": "BUY ONE GET ONE FREE",
            "description": "on qualifying products",
            "badges": ["12/31/49", "DG STORE"],
        },
        1,
    )

    assert offer.savings_cents is None
    assert offer.visible_fields_complete is False
    assert "savings amount could not be normalized" in offer.review_reasons


def test_report_records_verified_store_label() -> None:
    report = report_from_raw(
        [], [], advertised_count=0, load_more_clicks=0, all_loaded=True,
        store_label="Shopping in store at Westland, MI",
    )

    assert report.store_label == "Shopping in store at Westland, MI"
