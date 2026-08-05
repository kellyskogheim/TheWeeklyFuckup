from pathlib import Path

from dg_saver.store import (
    StorePreference,
    clear_store_preference,
    find_directory_match,
    load_store_preference,
    parse_store_address,
    save_store_preference,
    store_matches,
)


def test_store_preference_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "dg-saver.preferences.json"
    preference = StorePreference(display_name="Westland, MI")

    save_store_preference(path, preference)

    assert load_store_preference(path) == preference
    assert clear_store_preference(path) is True
    assert load_store_preference(path) is None


def test_store_match_is_case_insensitive_and_whitespace_tolerant() -> None:
    assert store_matches("Westland, MI", "Shopping in store at  Westland, MI")
    assert not store_matches("Westland, MI", "Shopping in store at Livonia, MI")


def test_full_address_builds_official_city_directory_url() -> None:
    address = parse_store_address("2712 S Cedar St, Lansing, MI 48910-3029")

    assert address.street == "2712 S Cedar St"
    assert address.directory_url.endswith("/store-directory/mi/lansing")


def test_directory_match_requires_exact_full_address() -> None:
    address = parse_store_address("2712 S Cedar St, Lansing, MI 48910-3029")
    listings = [
        {
            "href": "/store-directory/mi/lansing/18481",
            "text": "2712 S Cedar St\nLansing, MI 48910-3029\n(517) 721-7529\nView Store Details",
        },
        {
            "href": "/store-directory/mi/lansing/10748",
            "text": "1700 E Cavanaugh Rd\nLansing, MI 48910-3680\nView Store Details",
        },
    ]

    match = find_directory_match(address, listings)

    assert match["href"].endswith("/18481")
