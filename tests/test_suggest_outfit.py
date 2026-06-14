"""
Unit tests for tools.suggest_outfit.

The tool calls Groq's LLM, so these tests mock the Groq client — they verify the
tool's branching, prompt construction, and return handling WITHOUT making a real
API call (no GROQ_API_KEY needed to run them).

Run with:  pytest
"""

import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

# Make the project root importable when pytest is run from anywhere.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tools
from tools import suggest_outfit


# ── fakes ───────────────────────────────────────────────────────────────────────

class _FakeChat:
    """Records the kwargs of the last create() call and returns a canned reply."""

    def __init__(self, reply="  Pair it with your dark jeans and white sneakers.  "):
        self.reply = reply
        self.last_kwargs = None
        self.call_count = 0
        self.completions = self

    def create(self, **kwargs):
        self.call_count += 1
        self.last_kwargs = kwargs
        message = SimpleNamespace(content=self.reply)
        choice = SimpleNamespace(message=message)
        return SimpleNamespace(choices=[choice])


class _FakeClient:
    def __init__(self, chat):
        self.chat = chat


def _patched_client(reply="Pair it with your dark jeans and white sneakers."):
    """Return (patch_context, fake_chat) so a test can inspect the recorded call."""
    fake_chat = _FakeChat(reply=reply)
    fake_client = _FakeClient(fake_chat)
    return patch.object(tools, "_get_groq_client", return_value=fake_client), fake_chat


NEW_ITEM = {
    "id": "lst_006",
    "title": "Graphic Tee — 2003 Tour Bootleg Style",
    "category": "tops",
    "style_tags": ["graphic tee", "vintage", "grunge"],
    "size": "L",
    "price": 24.0,
    "colors": ["black"],
    "brand": None,
    "platform": "depop",
}

WARDROBE_WITH_ITEMS = {
    "items": [
        {
            "id": "w_001",
            "name": "Baggy straight-leg jeans, dark wash",
            "category": "bottoms",
            "colors": ["dark blue"],
            "style_tags": ["denim", "baggy"],
        },
        {
            "id": "w_002",
            "name": "Chunky white sneakers",
            "category": "shoes",
            "colors": ["white"],
            "style_tags": ["streetwear"],
        },
    ]
}

EMPTY_WARDROBE = {"items": []}


# ── populated-wardrobe behaviour ─────────────────────────────────────────────────

def test_returns_nonempty_string_with_wardrobe():
    ctx, _ = _patched_client()
    with ctx:
        result = suggest_outfit(NEW_ITEM, WARDROBE_WITH_ITEMS)
    assert isinstance(result, str)
    assert result.strip() != ""


def test_strips_whitespace_from_llm_reply():
    ctx, _ = _patched_client(reply="   styled look   ")
    with ctx:
        result = suggest_outfit(NEW_ITEM, WARDROBE_WITH_ITEMS)
    assert result == "styled look"


def test_uses_correct_model():
    ctx, fake_chat = _patched_client()
    with ctx:
        suggest_outfit(NEW_ITEM, WARDROBE_WITH_ITEMS)
    assert fake_chat.last_kwargs["model"] == "llama-3.3-70b-versatile"


def test_prompt_includes_wardrobe_item_names():
    ctx, fake_chat = _patched_client()
    with ctx:
        suggest_outfit(NEW_ITEM, WARDROBE_WITH_ITEMS)
    prompt = _last_user_prompt(fake_chat)
    assert "Baggy straight-leg jeans, dark wash" in prompt
    assert "Chunky white sneakers" in prompt


def test_prompt_includes_new_item_title():
    ctx, fake_chat = _patched_client()
    with ctx:
        suggest_outfit(NEW_ITEM, WARDROBE_WITH_ITEMS)
    assert NEW_ITEM["title"] in _last_user_prompt(fake_chat)


# ── empty-wardrobe behaviour ─────────────────────────────────────────────────────

def test_empty_wardrobe_does_not_crash_and_returns_nonempty():
    ctx, _ = _patched_client(reply="Here is some general styling advice.")
    with ctx:
        result = suggest_outfit(NEW_ITEM, EMPTY_WARDROBE)
    assert isinstance(result, str)
    assert result.strip() != ""


def test_empty_wardrobe_still_calls_llm_once():
    ctx, fake_chat = _patched_client(reply="general advice")
    with ctx:
        suggest_outfit(NEW_ITEM, EMPTY_WARDROBE)
    assert fake_chat.call_count == 1


def test_empty_wardrobe_prompt_has_no_wardrobe_items():
    ctx, fake_chat = _patched_client(reply="general advice")
    with ctx:
        suggest_outfit(NEW_ITEM, EMPTY_WARDROBE)
    prompt = _last_user_prompt(fake_chat)
    # No named wardrobe pieces should leak into the general-advice prompt.
    assert "Baggy straight-leg jeans" not in prompt
    # But the item being styled should still be present.
    assert NEW_ITEM["title"] in prompt


def test_missing_items_key_is_treated_as_empty():
    # A wardrobe dict without an 'items' key should not raise a KeyError.
    ctx, _ = _patched_client(reply="general advice")
    with ctx:
        result = suggest_outfit(NEW_ITEM, {})
    assert result.strip() != ""


# ── helpers ─────────────────────────────────────────────────────────────────────

def _last_user_prompt(fake_chat):
    messages = fake_chat.last_kwargs["messages"]
    user_msgs = [m["content"] for m in messages if m["role"] == "user"]
    return "\n".join(user_msgs)
