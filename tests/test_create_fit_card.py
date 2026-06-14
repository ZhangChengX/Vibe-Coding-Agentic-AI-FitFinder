"""
Unit tests for tools.create_fit_card.

The tool calls Groq's LLM, so most tests mock the client — they verify the empty
outfit guard, prompt construction, model, and a high temperature WITHOUT a real
API call. One optional live test (skipped unless GROQ_API_KEY is set) confirms
that repeated calls actually produce varied captions.

Run with:  pytest
"""

import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

# Make the project root importable when pytest is run from anywhere.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tools
from tools import create_fit_card


# ── fakes ───────────────────────────────────────────────────────────────────────

class _FakeChat:
    """Records the kwargs of the last create() call and returns a canned reply."""

    def __init__(self, reply="  Thrifted gold. #ootd  "):
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


def _patched_client(reply="Thrifted gold. #ootd"):
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

OUTFIT = "Tuck the bootleg tee into baggy dark-wash jeans and finish with chunky white sneakers."


# ── empty-outfit guard ───────────────────────────────────────────────────────────

def test_empty_outfit_returns_error_string_not_exception():
    # No client should be needed — guard returns before any LLM call.
    result = create_fit_card("", NEW_ITEM)
    assert isinstance(result, str)
    assert result.strip() != ""


def test_whitespace_outfit_returns_error_string():
    result = create_fit_card("   \n  ", NEW_ITEM)
    assert isinstance(result, str)
    assert result.strip() != ""


def test_empty_outfit_does_not_call_llm():
    ctx, fake_chat = _patched_client()
    with ctx:
        create_fit_card("", NEW_ITEM)
    assert fake_chat.call_count == 0


# ── happy path ───────────────────────────────────────────────────────────────────

def test_returns_nonempty_string():
    ctx, _ = _patched_client()
    with ctx:
        result = create_fit_card(OUTFIT, NEW_ITEM)
    assert isinstance(result, str)
    assert result.strip() != ""


def test_strips_whitespace_from_reply():
    ctx, _ = _patched_client(reply="   caption text   ")
    with ctx:
        result = create_fit_card(OUTFIT, NEW_ITEM)
    assert result == "caption text"


def test_uses_correct_model():
    ctx, fake_chat = _patched_client()
    with ctx:
        create_fit_card(OUTFIT, NEW_ITEM)
    assert fake_chat.last_kwargs["model"] == "llama-3.3-70b-versatile"


def test_uses_high_temperature_for_variety():
    ctx, fake_chat = _patched_client()
    with ctx:
        create_fit_card(OUTFIT, NEW_ITEM)
    # High temperature is what makes repeated captions differ.
    assert fake_chat.last_kwargs["temperature"] >= 0.8


def test_prompt_includes_item_details_and_outfit():
    ctx, fake_chat = _patched_client()
    with ctx:
        create_fit_card(OUTFIT, NEW_ITEM)
    prompt = _last_user_prompt(fake_chat)
    assert NEW_ITEM["title"] in prompt
    assert "24" in prompt          # price surfaced
    assert "depop" in prompt       # platform surfaced
    assert OUTFIT in prompt        # the outfit context is passed through


# ── optional live variation check ────────────────────────────────────────────────

@pytest.mark.skipif(
    not os.environ.get("GROQ_API_KEY"),
    reason="GROQ_API_KEY not set — skipping live LLM variation test",
)
def test_live_outputs_vary():
    # Calls the real LLM a few times; high temperature should yield variety.
    captions = {create_fit_card(OUTFIT, NEW_ITEM) for _ in range(3)}
    assert len(captions) > 1, "Captions were identical — increase the temperature"


# ── helpers ─────────────────────────────────────────────────────────────────────

def _last_user_prompt(fake_chat):
    messages = fake_chat.last_kwargs["messages"]
    user_msgs = [m["content"] for m in messages if m["role"] == "user"]
    return "\n".join(user_msgs)
