"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()

MODEL_NAME = "llama-3.3-70b-versatile"

# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform

    TODO:
        1. Load all listings with load_listings().
        2. Filter by max_price and size (if provided).
        3. Score each remaining listing by keyword overlap with `description`.
        4. Drop any listings with a score of 0 (no relevant matches).
        5. Sort by score, highest first, and return the listing dicts.

    Before writing code, fill in the Tool 1 section of planning.md.
    """
    listings = load_listings()

    # 1. Filter by price ceiling and size, when those filters are provided.
    candidates = []
    for listing in listings:
        if max_price is not None and listing.get("price", 0) > max_price:
            continue
        if size is not None and not _size_matches(size, listing.get("size", "")):
            continue
        candidates.append(listing)

    # 2. Score each candidate by keyword overlap with the description.
    query_words = _tokenize(description)
    scored = []
    for listing in candidates:
        haystack = " ".join(
            [
                listing.get("title", ""),
                listing.get("description", ""),
                " ".join(listing.get("style_tags", [])),
            ]
        )
        listing_words = _tokenize(haystack)
        score = len(query_words & listing_words)
        if score > 0:  # 3. Drop listings with no relevant overlap.
            scored.append((score, listing))

    # 4. Sort by score, highest first, and return just the listing dicts.
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [listing for _, listing in scored]


def _tokenize(text: str) -> set[str]:
    """Lowercase `text` and split it into a set of alphanumeric word tokens."""
    return {token for token in re.split(r"[^a-z0-9]+", text.lower()) if token}


def _size_matches(requested: str, listing_size: str) -> bool:
    """
    Case-insensitive size match that handles compound sizes.

    e.g. requested "M" matches listing sizes "M", "m", "S/M", and "M/L".
    """
    requested = requested.strip().lower()
    if not requested:
        return True
    listing_tokens = {
        token for token in re.split(r"[^a-z0-9]+", listing_size.lower()) if token
    }
    return requested in listing_tokens


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    TODO:
        1. Check whether wardrobe['items'] is empty.
        2. If empty: call the LLM with a prompt for general styling ideas
           (what kinds of items pair well, what vibe it suits, etc.).
        3. If not empty: format the wardrobe items into a prompt and ask
           the LLM to suggest specific outfit combinations using the new item
           and named pieces from the wardrobe.
        4. Return the LLM's response as a string.

    Before writing code, fill in the Tool 2 section of planning.md.
    """
    item_summary = _format_item(new_item)
    items = (wardrobe or {}).get("items", [])

    if not items:
        # Empty wardrobe → general styling advice, never crash or return "".
        prompt = (
            f"A shopper is considering this secondhand item:\n{item_summary}\n\n"
            "They have not told us anything about their existing wardrobe. "
            "Give friendly, general styling advice for this piece in 3-5 sentences: "
            "what kinds of items pair well with it, what colors and vibe it suits, "
            "and one or two occasions to wear it. Do not invent specific items they own."
        )
    else:
        wardrobe_text = "\n".join(f"- {_format_wardrobe_item(i)}" for i in items)
        prompt = (
            f"A shopper is considering this secondhand item:\n{item_summary}\n\n"
            f"Here is their existing wardrobe:\n{wardrobe_text}\n\n"
            "Suggest 1-2 complete outfits that combine the new item with specific "
            "pieces from their wardrobe. Refer to wardrobe pieces by name. Keep it "
            "concise and practical."
        )

    client = _get_groq_client()
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {
                "role": "system",
                "content": "You are a thoughtful personal stylist for secondhand fashion.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
    )
    return response.choices[0].message.content.strip()


def _format_item(item: dict) -> str:
    """Render a listing dict as a short human-readable summary for a prompt."""
    parts = [item.get("title", "Unknown item")]
    if item.get("category"):
        parts.append(f"category: {item['category']}")
    if item.get("colors"):
        parts.append(f"colors: {', '.join(item['colors'])}")
    if item.get("style_tags"):
        parts.append(f"style: {', '.join(item['style_tags'])}")
    if item.get("size"):
        parts.append(f"size: {item['size']}")
    if item.get("price") is not None:
        parts.append(f"${item['price']}")
    return " | ".join(parts)


def _format_wardrobe_item(item: dict) -> str:
    """Render a wardrobe item dict as a short line for a prompt."""
    parts = [item.get("name", "Unnamed piece")]
    if item.get("category"):
        parts.append(f"({item['category']})")
    if item.get("colors"):
        parts.append(f"colors: {', '.join(item['colors'])}")
    if item.get("style_tags"):
        parts.append(f"style: {', '.join(item['style_tags'])}")
    return " ".join(parts)


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    TODO:
        1. Guard against an empty or whitespace-only outfit string.
        2. Build a prompt that gives the LLM the item details and the outfit,
           and asks for a caption matching the style guidelines above.
        3. Call the LLM and return the response.

    Before writing code, fill in the Tool 3 section of planning.md.
    """
    # 1. Guard against an empty / whitespace-only outfit — return a string, never raise.
    if not outfit or not outfit.strip():
        return (
            "Couldn't create a fit card — no outfit suggestion was provided. "
            "Generate an outfit first, then try again."
        )

    item_summary = _format_item(new_item)
    title = new_item.get("title", "this piece")
    price = new_item.get("price")
    price_text = f"${price}" if price is not None else "a great price"
    platform = new_item.get("platform", "secondhand")

    prompt = (
        f"Write a short, shareable Instagram/TikTok-style outfit caption for this "
        f"thrifted find.\n\n"
        f"Item: {item_summary}\n"
        f"Outfit: {outfit.strip()}\n\n"
        "Guidelines:\n"
        "- 2-4 sentences, casual and authentic — like a real OOTD post, NOT a product description.\n"
        f"- Mention the item name ({title}), its price ({price_text}), and where it's from "
        f"({platform}) naturally, once each.\n"
        "- Capture the outfit's specific vibe.\n"
        "- Add a couple of fitting hashtags at the end.\n"
        "Return only the caption text."
    )

    # 3. Higher temperature so captions read fresh and vary between runs.
    client = _get_groq_client()
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {
                "role": "system",
                "content": "You write fun, authentic secondhand-fashion captions for social media.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=1.0,
    )
    return response.choices[0].message.content.strip()



if __name__ == "__main__":
    # Simple end-to-end workflow

    from utils.data_loader import get_example_wardrobe

    # Step 1: find listings that match a query.
    query = "vintage graphic tee"
    print(f"🔎 Searching for: {query!r} (max $30)\n")
    results = search_listings(query, size=None, max_price=30.0)

    if not results:
        print("No listings matched — try broadening the search.")
    else:
        item = results[0]  # top-ranked match
        print(f"🛍️  Top match: {item['title']} — ${item['price']} on {item['platform']}\n")

        # Step 2: suggest an outfit using the example wardrobe.
        wardrobe = get_example_wardrobe()
        outfit = suggest_outfit(item, wardrobe)
        print("👗 Outfit suggestion:")
        print(outfit, "\n")

        # Step 3: turn the outfit into a shareable fit card.
        fit_card = create_fit_card(outfit, item)
        print("✨ Fit card:")
        print(fit_card)
