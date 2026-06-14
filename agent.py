"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import re

from tools import search_listings, suggest_outfit, create_fit_card


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.

    You may add fields to this dict as needed for your implementation.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "search_results": [],        # list of matching listing dicts
        "selected_item": None,       # top result, passed into suggest_outfit
        "wardrobe": wardrobe,        # user's wardrobe dict
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "error": None,               # set if the interaction ended early
    }


# ── query parsing ───────────────────────────────────────────────────────────────

# Recognized size tokens (checked as standalone words, case-insensitive).
_SIZE_TOKENS = ["xxs", "xs", "s", "m", "l", "xl", "xxl"]


def _parse_query(query: str) -> dict:
    """
    Extract a search description, size, and max_price from a free-text query.

    Uses simple regex/string rules (per the Planning Loop spec):
      - max_price: a "$NN" or "under/below/less than NN" pattern.
      - size:      a "size X" pattern, or a standalone size token (S, M, XL…).
      - description: the remaining text, with the matched price/size removed.
                     Falls back to the raw query if nothing usable is left.

    Returns:
        {"description": str, "size": str | None, "max_price": float | None}
    """
    remaining = query

    # max_price — "under $30", "below 40", "$25", "less than 20"
    max_price = None
    price_match = re.search(
        r"(?:under|below|less than|max|<=?)?\s*\$\s*(\d+(?:\.\d+)?)"
        r"|(?:under|below|less than|max)\s+(\d+(?:\.\d+)?)",
        query,
        flags=re.IGNORECASE,
    )
    if price_match:
        amount = price_match.group(1) or price_match.group(2)
        max_price = float(amount)
        remaining = remaining.replace(price_match.group(0), " ")

    # size — explicit "size X" first, then a standalone size token.
    size = None
    size_match = re.search(r"\bsize\s+([\w./]+)", remaining, flags=re.IGNORECASE)
    if size_match:
        size = size_match.group(1).upper()
        remaining = remaining.replace(size_match.group(0), " ")
    else:
        for token in _SIZE_TOKENS:
            token_match = re.search(rf"\b{token}\b", remaining, flags=re.IGNORECASE)
            if token_match:
                size = token.upper()
                remaining = remaining[: token_match.start()] + " " + remaining[token_match.end():]
                break

    # description — leftover keywords; fall back to the raw query if empty.
    # (Price digits were already removed above; keep other digits like "90s"/"2003".)
    description = remaining.replace("$", " ")
    description = re.sub(r"\s+", " ", description).strip(" ,.")
    if not description:
        description = query.strip()

    return {"description": description, "size": size, "max_price": max_price}


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFinder planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and the other
        output fields (outfit_suggestion, fit_card) will be None.

    TODO — implement this function using the planning loop you designed in planning.md:

        Step 1: Initialize the session with _new_session().

        Step 2: Parse the user's query to extract a description, size, and
                max_price. You can use regex, string splitting, or ask the LLM
                to parse it — document your choice in planning.md.
                Store the result in session["parsed"].

        Step 3: Call search_listings() with the parsed parameters.
                Store results in session["search_results"].
                If no results: set session["error"] to a helpful message and
                return the session early. Do NOT proceed to suggest_outfit
                with empty input.

        Step 4: Select the item to use (e.g., the top result).
                Store it in session["selected_item"].

        Step 5: Call suggest_outfit() with the selected item and wardrobe.
                Store the result in session["outfit_suggestion"].

        Step 6: Call create_fit_card() with the outfit suggestion and selected item.
                Store the result in session["fit_card"].

        Step 7: Return the session.

    Before writing code, complete the Planning Loop and State Management sections
    of planning.md — your implementation should match what you described there.
    """
    # Step 1: Initialize the session.
    session = _new_session(query, wardrobe)

    # Step 2: Parse the query into description / size / max_price.
    session["parsed"] = _parse_query(query)
    parsed = session["parsed"]

    # Step 3: Search. Branch on the result — do NOT proceed on an empty list.
    session["search_results"] = search_listings(
        parsed["description"], parsed["size"], parsed["max_price"]
    )
    if not session["search_results"]:
        size_note = f" in size {parsed['size']}" if parsed["size"] else ""
        price_note = f" under ${parsed['max_price']:g}" if parsed["max_price"] is not None else ""
        session["error"] = (
            f"No listings matched '{parsed['description']}'{price_note}{size_note}. "
            "Try raising the price, dropping the size, or using broader keywords."
        )
        return session  # early exit — suggest_outfit / create_fit_card not called

    # Step 4: Select the top-ranked item.
    session["selected_item"] = session["search_results"][0]

    # Step 5: Suggest an outfit. Guard against a failed/blank result.
    try:
        outfit = suggest_outfit(session["selected_item"], session["wardrobe"])
    except Exception as exc:  # LLM/API failure — don't crash the agent
        session["error"] = f"Couldn't generate an outfit suggestion: {exc}"
        return session
    if not outfit or not outfit.strip():
        session["error"] = "Couldn't generate an outfit suggestion for this item."
        return session  # early exit — create_fit_card not called
    session["outfit_suggestion"] = outfit

    # Step 6: Create the fit card from the outfit + selected item.
    session["fit_card"] = create_fit_card(
        session["outfit_suggestion"], session["selected_item"]
    )

    # Step 7: Return the completed session (error stays None on success).
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")
