"""
Unit tests for tools.search_listings.

Run with:  pytest
"""

import os
import re
import sys

# Make the project root importable when pytest is run from anywhere.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import search_listings
from utils.data_loader import load_listings


# ── basic behaviour ────────────────────────────────────────────────────────────

def test_returns_list_of_dicts():
    results = search_listings("vintage graphic tee")
    assert isinstance(results, list)
    assert all(isinstance(item, dict) for item in results)


def test_relevant_query_returns_matches():
    results = search_listings("vintage graphic tee")
    assert len(results) > 0
    # Every returned listing should genuinely overlap the query keywords.
    for item in results:
        haystack = (
            item["title"]
            + " "
            + item["description"]
            + " "
            + " ".join(item["style_tags"])
        ).lower()
        assert any(word in haystack for word in ("vintage", "graphic", "tee"))


def test_results_contain_expected_fields():
    results = search_listings("vintage graphic tee")
    expected = {
        "id",
        "title",
        "description",
        "category",
        "style_tags",
        "size",
        "condition",
        "price",
        "colors",
        "brand",
        "platform",
    }
    assert expected.issubset(results[0].keys())


# ── empty / no-match behaviour ──────────────────────────────────────────────────

def test_no_match_returns_empty_list_not_exception():
    # Nonsense keywords that overlap nothing in the dataset.
    results = search_listings("xyzzy quux frobnicate")
    assert results == []


def test_impossible_combo_returns_empty_list():
    # A real-ish query that the dataset cannot satisfy.
    results = search_listings("designer ballgown", size="XXS", max_price=5.0)
    assert results == []


# ── price filtering ─────────────────────────────────────────────────────────────

def test_max_price_is_inclusive_and_filters():
    results = search_listings("vintage", max_price=20.0)
    assert len(results) > 0
    assert all(item["price"] <= 20.0 for item in results)


def test_no_max_price_includes_pricier_items():
    cheap = search_listings("vintage", max_price=20.0)
    all_priced = search_listings("vintage")
    assert len(all_priced) >= len(cheap)


# ── size filtering ──────────────────────────────────────────────────────────────

def test_size_filter_matches_exact_and_compound():
    results = search_listings("vintage", size="M")
    assert len(results) > 0
    for item in results:
        tokens = item["size"].lower().replace("/", " ").split()
        assert "m" in tokens  # matches "M", "S/M", "M/L"


def test_size_filter_is_case_insensitive():
    upper = search_listings("vintage", size="M")
    lower = search_listings("vintage", size="m")
    assert {i["id"] for i in upper} == {i["id"] for i in lower}


# ── ranking ─────────────────────────────────────────────────────────────────────

def test_results_sorted_by_relevance_desc():
    # "vintage graphic tee band" gives varied overlap counts across listings.
    results = search_listings("vintage graphic tee band")

    def score(item):
        words = {"vintage", "graphic", "tee", "band"}
        haystack = (
            item["title"]
            + " "
            + item["description"]
            + " "
            + " ".join(item["style_tags"])
        ).lower()
        # Word-token overlap, matching the implementation (not substring matching).
        tokens = set(re.split(r"[^a-z0-9]+", haystack))
        return len(words & tokens)

    scores = [score(item) for item in results]
    assert scores == sorted(scores, reverse=True)


# ── sanity: the dataset is what the tests assume ────────────────────────────────

def test_dataset_loads():
    assert len(load_listings()) > 0
