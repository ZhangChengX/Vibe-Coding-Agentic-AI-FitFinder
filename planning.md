# FitFinder — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->
Searches over the mock secondhand listings dataset (`load_listings()`) for items that match the user's
keywords, with optional size and price filters. It scores each listing by how well it overlaps the
description and returns the best matches first, so the agent has concrete items to style.

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `description` (str): Free-text keywords describing what the user wants (e.g., "vintage graphic tee"). Used for keyword/relevance matching against each listing's title, description, and style tags.
- `size` (str | None): Size string to filter by (e.g., "M"). Matched case-insensitively and allowed to match compound sizes like "S/M". `None` skips size filtering.
- `max_price` (float | None): Inclusive price ceiling. Listings above this are dropped. `None` skips price filtering.

**What it returns:**
<!-- Describe the return value — what fields does a result contain? -->
A `list[dict]` of matching listings, sorted by relevance score (best match first). Each listing dict
contains: `id`, `title`, `description`, `category`, `style_tags` (list), `size`, `condition`,
`price` (float), `colors` (list), `brand` (str or None), and `platform` (depop / thredUp / poshmark).
Listings scoring 0 on keyword overlap are excluded.

**What happens if it fails or returns nothing:**
<!-- What should the agent do if no listings match? -->
It returns an empty list rather than raising an exception. The agent should detect the empty result,
tell the user nothing matched their criteria, and suggest broadening the search — e.g., raising
`max_price`, dropping the size filter, or using more general keywords — before re-running the search.
Because no item was found, the agent should NOT proceed to `suggest_outfit` / `create_fit_card`.

---

### Tool 2: suggest_outfit

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->
Takes a thrifted item the user is considering and their existing wardrobe, then calls the LLM to
suggest 1–2 complete outfits that pair the new item with specific pieces the user already owns. If the
wardrobe is empty, it falls back to general styling advice for the item instead.

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `new_item` (dict): A single listing dict (typically one result from `search_listings`) representing the item being styled. Relevant fields: `title`, `category`, `style_tags` (list), `colors` (list), `size`, `price`, `platform`.
- `wardrobe` (dict): The user's wardrobe, shaped as `{"items": [...]}`. Each item dict has `id` (str), `name` (str), `category` (str: tops/bottoms/outerwear/shoes/accessories), `colors` (list[str]), `style_tags` (list[str]), and an optional `notes` (str). May be empty (`items == []`), which must be handled gracefully.

**What it returns:**
<!-- Describe the return value -->
A non-empty `str` of human-readable outfit suggestions. When the wardrobe has items, the text names
1–2 outfits that combine the new item with specific owned pieces (referenced by their `name`). When the
wardrobe is empty, the string instead gives general styling guidance (what categories/colors/vibes pair
well with the item). It is plain prose meant to be shown to the user and passed into `create_fit_card`.

**What happens if it fails or returns nothing:**
<!-- What should the agent do if the wardrobe is empty or no outfit can be suggested? -->
The tool never returns an empty string: an empty wardrobe triggers the general-advice fallback rather
than an error. If the LLM call itself fails (e.g., API/network error), the agent should catch it,
inform the user that styling couldn't be generated, and either retry or skip `create_fit_card` for that
item rather than crashing. The agent should not pass an empty/blank outfit string downstream.

---

### Tool 3: create_fit_card

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->
Generates a short, shareable social-media caption (an "OOTD"/fit card) for the thrifted find, based on
the outfit suggestion and the item details. It uses a higher LLM temperature so captions feel casual,
authentic, and varied rather than like a product description.

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `outfit` (str): The outfit suggestion text produced by `suggest_outfit()`. Provides the styling context the caption should capture.
- `new_item` (dict): The listing dict for the thrifted item being featured. The caption naturally mentions its `title` (item name), `price` (float), and `platform` (str) once each, and draws on `style_tags`/`colors` for vibe.

**What it returns:**
<!-- Describe the return value -->
A `str` of 2–4 sentences usable directly as an Instagram/TikTok caption. It reads casually (not like a
product listing), names the item, its price, and the platform once each, captures the outfit's vibe in
specific terms, and varies between different inputs/runs.

**What happens if it fails or returns nothing:**
<!-- What should the agent do if the outfit data is incomplete? -->
If `outfit` is missing, empty, or whitespace-only, the tool returns a descriptive error-message string
(it does NOT raise). The agent should treat that as a signal that styling is incomplete — typically
re-run or skip `suggest_outfit` first — and avoid showing the placeholder/error text to the user as a
finished caption. If the underlying LLM call fails, the agent should report that the caption couldn't be
generated rather than crashing.

---

### Additional Tools (if any)

<!-- Copy the block above for any tools beyond the required three -->

---

## Planning Loop

**How does your agent decide which tool to call next?**
<!-- Describe the logic your planning loop uses. What does it look at? What conditions change its behavior? How does it know when it's done? -->
The loop is a fixed sequence of stages driven by the `session` dict. At each stage it inspects the
state produced by the previous tool and branches: on a bad/empty result it writes a message to
`session["error"]` and returns the session early; otherwise it stores the result in `session` and
advances. The agent is "done" when either `session["fit_card"]` is set (success) or `session["error"]`
is set (early exit). The specific branches:

1. **Initialize.** Call `_new_session(query, wardrobe)` to create `session`. `session["error"]` starts as `None`.

2. **Parse the query.** Extract `description`, `size`, and `max_price` from `session["query"]` and store them in `session["parsed"]`. (Parsing method: simple regex/string rules — e.g., a `$NN` or "under NN" pattern for `max_price`, a "size X" pattern for `size`, and the remaining text as `description`; `size`/`max_price` default to `None` when absent.) `description` should never be empty — if parsing yields no usable keywords, fall back to using the raw query string as `description`.

3. **Search.** Call `search_listings(description, size, max_price)` and store the return in `session["search_results"]`.
   - **If `search_results` is empty:** set `session["error"]` to a helpful message (e.g., "No listings matched 'description' under $max_price in size X — try raising the price, dropping the size, or using broader keywords.") and `return session` immediately. Do NOT call `suggest_outfit`.
   - **If `search_results` is non-empty:** continue.

4. **Select item.** Set `session["selected_item"] = session["search_results"][0]` (the top-scored result) and proceed.

5. **Suggest outfit.** Call `suggest_outfit(session["selected_item"], session["wardrobe"])` and store the return in `session["outfit_suggestion"]`. (`suggest_outfit` handles an empty wardrobe internally by returning general advice, so no extra branch is needed for an empty wardrobe here.)
   - **If the call raises or returns an empty/blank string:** set `session["error"]` to a message that styling could not be generated and `return session` without calling `create_fit_card`.
   - **Otherwise:** continue.

6. **Create fit card.** Call `create_fit_card(session["outfit_suggestion"], session["selected_item"])` and store the return in `session["fit_card"]`.

7. **Return.** `return session`. The caller checks `session["error"]` first: if `None`, the interaction succeeded and `selected_item`, `outfit_suggestion`, and `fit_card` are all populated; if not `None`, the run ended early at one of the branches above and those fields may be `None`.

---

## State Management

**How does information from one tool get passed to the next?**
<!-- Describe how your agent stores and accesses state within a session. What data is tracked? How is it passed between tool calls? -->

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | |
| suggest_outfit | Wardrobe is empty | |
| create_fit_card | Outfit input is missing or incomplete | |

---

## Architecture

<!-- Draw a diagram of your agent showing how the components connect:
     User input → Planning Loop → Tools (search_listings, suggest_outfit, create_fit_card)
  
     State / Session
     Show what triggers each tool, how state flows between them, and where error paths branch off.
     ASCII art, a Mermaid diagram (https://mermaid.js.org/syntax/flowchart.html), or an embedded
     sketch are all fine. You'll share this diagram with an AI tool when asking it to implement
     the planning loop and each individual tool. -->

```
                         ┌────────────────────────────────────────────┐
                         │  SESSION STATE (dict, run_agent)           │
                         │  query · parsed{description,size,max_price}│
                         │  search_results · selected_item · wardrobe │
                         │  outfit_suggestion · fit_card · error      │
                         └────────────────────────────────────────────┘
                              ▲ read/write at every stage   ▲
                              │                             │
  User query + wardrobe       │                             │
        │                     │                             │
        ▼                     │                             │
  ┌───────────────┐  query    │                             │
  │ Planning Loop │───────────┘                             │
  │  (run_agent)  │                                         │  ERROR PATH
  └───────────────┘                                         │  (return session
        │                                                   │   early; outfit &
        │  parse query → parsed{description,size,max_price} │   fit_card stay None)
        ▼                                                   │
  ┌───────────────────────────────────────────────┐         │
  │ search_listings(description, size, max_price) │         │
  └───────────────────────────────────────────────┘         │
        │ returns list[dict]                                │
        │                                                   │
        ├── results == []  ──► error = "No listings found…" ┤
        │                                                   │
        │ results = [item, …]                               │
        ▼                                                   │
   Session: selected_item = search_results[0]               │
        │                                                   │
        ▼                                                   │
  ┌────────────────────────────────────────────────┐        │
  │ suggest_outfit(selected_item, wardrobe)        │  ◄── wardrobe (from session)
  │   empty wardrobe → general advice (no error)   │        │
  └────────────────────────────────────────────────┘        │
        │ returns str                                       │
        │                                                   │
        ├── raised / blank string ──► error = "Couldn't style…" ┤
        │                                                   │
        │ outfit_suggestion = "…"                           │
        ▼                                                   │
  ┌────────────────────────────────────────────────┐        │
  │ create_fit_card(outfit_suggestion, selected_item) │     │
  └────────────────────────────────────────────────┘        │
        │ returns str                                       │
        ▼                                                   │
   Session: fit_card = "…"                                  │
        │                                                   │
        ▼                                                   ▼
  ┌────────────────────────────────────────────────────────────┐
  │  return session   →  caller checks session["error"]:       │
  │    error is None  → success (selected_item/outfit/fit_card)│
  │    error set      → early exit message shown to user       │
  └────────────────────────────────────────────────────────────┘
```

**How to read it:** the Planning Loop is the only component that calls tools; each tool reads its
inputs from the session and writes its result back. Solid downward arrows are the happy path; the
right-hand rail is the **error branch** — any stage that produces an empty/failed result sets
`session["error"]` and jumps straight to `return session`, skipping the remaining tools. `suggest_outfit`
handles an empty wardrobe internally (general advice) and so does not branch to the error rail for that
case.

---

## AI Tool Plan

<!-- For each part of the implementation below, describe:
     - Which AI tool you plan to use (Claude, Copilot, ChatGPT, etc.)
     - What you'll give it as input (which sections of this planning.md, your agent diagram)
     - What you expect it to produce
     - How you'll verify the output matches your spec before moving on

     "I'll use AI to help me code" is not a plan.
     "I'll give Claude my Tool 1 spec (inputs, return value, failure mode) and ask it to implement
     search_listings() using load_listings() from the data loader — then test it against 3 queries
     before trusting it" is a plan. -->

**Milestone 3 — Individual tool implementations:**

I'll use **Claude** to implement the three tool function bodies in `tools.py`, one tool at a time with unit test cases so
each can be verified in isolation before moving on.

- **search_listings** — *Input to Claude:* the **Tool 1: search_listings** block of this planning.md
  (inputs, return-value field list, empty-result failure mode), the existing stub + docstring in
  `tools.py`, and the `load_listings()` signature/field list from `utils/data_loader.py`. *Ask for:* a
  pure-Python implementation (no LLM call) that loads listings, filters by `size` (case-insensitive,
  matching compound sizes) and `max_price` (inclusive) when provided, scores remaining listings by
  keyword overlap of `description` against title/description/style_tags, drops score-0 listings, and
  returns the dicts sorted best-first. *Verify before use:* read the code and confirm it (1) filters by
  all three params, (2) skips a filter when its arg is `None`, (3) returns `[]` (never raises) on no
  match. Then run it with 3 queries — a normal one ("vintage graphic tee", `max_price=30`), a
  size-filtered one, and a deliberately impossible one ("designer ballgown size XXS under $5") — and
  check the impossible one returns `[]`.

- **suggest_outfit** — *Input to Claude:* the **Tool 2** block (inputs incl. the wardrobe item schema,
  return value, empty-wardrobe fallback), the stub in `tools.py`, the `_get_groq_client()` helper, and
  the example/empty wardrobe shape from `utils/data_loader.py`. *Ask for:* a function that branches on
  `wardrobe["items"]` — empty → LLM prompt for general styling advice; non-empty → LLM prompt that
  references owned pieces by `name` — and returns the response string. *Verify before use:* confirm the
  empty-wardrobe branch exists and that no branch returns `""`. Run it with `get_example_wardrobe()`
  (output should name specific owned pieces) and with `get_empty_wardrobe()` (output should still be
  non-empty general advice).

- **create_fit_card** — *Input to Claude:* the **Tool 3** block (inputs, caption style rules, empty-
  outfit failure mode) and the stub in `tools.py`. *Ask for:* a function that guards against an
  empty/whitespace `outfit` by returning a descriptive error string (no raise), otherwise builds a
  higher-temperature prompt and returns a 2–4 sentence caption mentioning the item name, price, and
  platform once each. *Verify before use:* check the empty-`outfit` guard returns a string; then call it
  twice with the same real outfit and confirm the caption mentions name/price/platform and that two runs
  produce different text (temperature working).

**Milestone 4 — Planning loop and state management:**

I'll use **Claude** to implement `run_agent()` (and the query parser) in `agent.py`.

- *Input to Claude:* the **Planning Loop** section (the 7-stage branch logic), the **State Management**
  section, and the **Architecture** diagram from this planning.md, plus the `_new_session()` definition
  and `run_agent()` docstring/TODO in `agent.py`, and the now-implemented tool signatures in `tools.py`.
- *Ask for:* a `run_agent(query, wardrobe)` that initializes the session via `_new_session()`, parses
  the query into `session["parsed"]`, then calls the three tools in order, writing each result back to
  the matching session key and taking the error branch (set `session["error"]`, `return session` early)
  exactly where the diagram shows it — on empty `search_results`, and on a raised/blank
  `outfit_suggestion`.
- *Expect it to produce:* a function that returns the completed `session` dict, with `error=None` and
  all output fields populated on success, or `error` set and downstream fields `None` on early exit.
- *Verify before use:* trace the code against the diagram to confirm the error branch returns before the
  next tool runs and that state flows through the session (not local variables). Then run the two
  scenarios already in `agent.py`'s `__main__`: the happy path ("vintage graphic tee under $30" with the
  example wardrobe) should fill `selected_item`, `outfit_suggestion`, and `fit_card` with `error=None`;
  the no-results path ("designer ballgown size XXS under $5") should set a helpful `error` and leave
  `outfit_suggestion`/`fit_card` as `None`.

---

## A Complete Interaction (Step by Step)

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1 — Initialize + parse (no tool yet).**
The agent calls `_new_session(query, wardrobe)` to create the session, then parses the query. The
parser extracts `max_price = 30.0` (from "under $30"), finds no explicit "size X" so `size = None`, and
takes the descriptive keywords as `description = "vintage graphic tee"` (the "baggy jeans / chunky
sneakers" part describes the user's existing style, not the item to search for). It stores
`session["parsed"] = {"description": "vintage graphic tee", "size": None, "max_price": 30.0}`.

**Step 2 — Call `search_listings`.**
The agent calls `search_listings(description="vintage graphic tee", size=None, max_price=30.0)`. The
tool drops listings over $30, scores the rest by keyword overlap, and returns a non-empty `list[dict]`
sorted best-first. The top hit is **`lst_006` — "Graphic Tee — 2003 Tour Bootleg Style"**, `$24.0`,
size `L`, `platform="depop"`, `style_tags=["graphic tee", "vintage", "grunge", "streetwear", "band
tee"]` (it matches all three of "vintage", "graphic", "tee"). The agent stores the list in
`session["search_results"]`. Since the list is non-empty, it does **not** take the error branch.

**Step 3 — Select item.**
The agent sets `session["selected_item"] = session["search_results"][0]` — the `lst_006` dict above.

**Step 4 — Call `suggest_outfit`.**
The agent calls `suggest_outfit(new_item=session["selected_item"], wardrobe=session["wardrobe"])`. The
example wardrobe is non-empty (it contains pieces like "Baggy straight-leg jeans, dark wash" and chunky
sneakers), so the tool's LLM returns a string naming 1–2 concrete outfits — e.g., the bootleg tee tucked
into the baggy dark-wash jeans with chunky sneakers and a layered flannel for a grunge/streetwear look.
The agent stores it in `session["outfit_suggestion"]`. It's a non-empty string, so no error branch.

**Step 5 — Call `create_fit_card`.**
The agent calls `create_fit_card(outfit=session["outfit_suggestion"], new_item=session["selected_item"])`.
Using a higher temperature, the LLM returns a 2–4 sentence caption that mentions the item name, its $24
price, and depop once each and captures the grunge/streetwear vibe. The agent stores it in
`session["fit_card"]`.

**Step 6 — Return.**
`run_agent` returns the session with `error = None` and `selected_item`, `outfit_suggestion`, and
`fit_card` all populated.

**Final output to user:**
<!-- What does the user actually see at the end? -->
The user sees the found item and how to wear it, assembled from the session — roughly:

- **Found:** "Graphic Tee — 2003 Tour Bootleg Style" — $24 on depop (size L)
- **Style it:** the `outfit_suggestion` text (tee + baggy dark-wash jeans + chunky sneakers + flannel layer)
- **Fit card:** the `create_fit_card` caption, ready to copy-paste to Instagram/TikTok

(Contrast: had the query been "designer ballgown size XXS under $5", Step 2's `search_listings` would
return `[]`, the agent would set `session["error"]` to a "no listings matched — try broadening your
search" message and return early, and the user would see only that message — no outfit or fit card.)
