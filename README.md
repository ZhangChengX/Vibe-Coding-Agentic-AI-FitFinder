# Vibe-Coding-Agentic-AI-FitFinder

FitFinder is a thrift-shopping assistant that takes a user's request for a secondhand item and returns a real listing plus a styled outfit. The agent first calls search_listings to filter the dataset by the user's description, size, and max price; if matches come back, it passes the top result and the user's wardrobe to suggest_outfit to generate a styling idea, then feeds that outfit into create_fit_card to produce the final shareable caption. If search_listings returns nothing, the agent stops and tells the user what to loosen (broaden the description, raise the price, or change the size) rather than calling suggest_outfit with empty input, and likewise if the wardrobe is empty, it suggests the item solo instead of inventing pairings.

## What's Included

```
.
├── agent.py                   # The planning loop (run_agent) + query parser
├── tools.py                   # The three tools (search_listings, suggest_outfit, create_fit_card)
├── app.py                     # Gradio web UI
├── data/
│   ├── listings.json          # 40 mock secondhand listings
│   └── wardrobe_schema.json   # Wardrobe format + example wardrobe
├── utils/
│   └── data_loader.py         # Helper functions for loading the data
├── tests/                     # pytest unit tests for the tools
├── planning.md                # Design doc (tools, loop, diagram)
└── requirements.txt           # Python dependencies
```

## Setup

```bash
pip install -r requirements.txt
```

Set your Groq API key in a `.env` file (get a free key at [console.groq.com](https://console.groq.com)):
```
GROQ_API_KEY=your_key_here
```

## How to Run

```bash
python agent.py              # run the agent from the command line
python app.py                # launch the web UI, then open the localhost URL it prints
python -m pytest tests/ -q   # run the unit tests
```

## Tool Inventory

The agent uses three tools. Each one does a single job and can be tested on its own.

### 1. `search_listings(description, size, max_price)`

- **Purpose:** Find listings in the dataset that match what the user asked for.
- **Inputs:**
  - `description` (`str`) — keywords to search for, e.g. `"vintage graphic tee"`.
  - `size` (`str | None`) — size to filter by, e.g. `"M"`. `None` means "any size". Matching ignores case and handles combined sizes (so `"M"` matches `"S/M"`).
  - `max_price` (`float | None`) — highest price allowed (inclusive). `None` means "any price".
- **Output:** a `list[dict]` of matching listings, best match first. Each dict has `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, `platform`. Returns an empty list `[]` when nothing matches (it never crashes).

### 2. `suggest_outfit(new_item, wardrobe)`

- **Purpose:** Suggest one or two outfits that mix the found item with clothes the user already owns.
- **Inputs:**
  - `new_item` (`dict`) — one listing (usually the top result from `search_listings`).
  - `wardrobe` (`dict`) — the user's clothes, shaped like `{"items": [...]}`. Can be empty.
- **Output:** a non-empty `str` of styling ideas. If the wardrobe has items, it names them. If the wardrobe is empty, it gives general advice instead. (Uses the Groq LLM.)

### 3. `create_fit_card(outfit, new_item)`

- **Purpose:** Turn the outfit idea into a short, casual social-media caption.
- **Inputs:**
  - `outfit` (`str`) — the text from `suggest_outfit`.
  - `new_item` (`dict`) — the same listing, so the caption can name the item, price, and platform.
- **Output:** a `str` of 2–4 sentences. If `outfit` is empty, it returns a short error message instead (it never crashes). (Uses the Groq LLM with a higher temperature so captions vary.)

## How the Planning Loop Works

The loop lives in `run_agent(query, wardrobe)` in `agent.py`. It is a fixed order of steps, but **at each step it looks at the result and decides whether to keep going or stop.** It is not "call all three tools no matter what."

The order and the decisions:

1. **Make a session.** A `session` dict is created to hold everything for this run.
2. **Read the query.** A small parser pulls out the `description`, `size`, and `max_price` from the user's sentence (for example, `"under $30"` becomes `max_price = 30.0`).
3. **Search.** Call `search_listings`.
   - **Decision:** *Is the result empty?*
     - **Yes →** write a helpful message into `session["error"]` and **stop right here**. The agent does **not** call `suggest_outfit` or `create_fit_card`, because there is nothing to style.
     - **No →** keep going.
4. **Pick the top item** (`search_results[0]`) and save it as `selected_item`.
5. **Suggest an outfit** using the selected item and the wardrobe.
   - **Decision:** *Did it fail or come back blank?*
     - **Yes →** set `session["error"]` and **stop** before making a fit card.
     - **No →** keep going.
6. **Make the fit card** from the outfit and the item.
7. **Return the session.**

**How does the agent know it is done?** It is done when either `fit_card` is filled in (success) or `error` is filled in (it stopped early). The caller just checks `session["error"]`: if it is `None`, everything worked.

So the two decisions that change the agent's behavior are: *did the search find anything?* and *did the outfit come back okay?* Each "no" ends the run early with a clear message.

## State Management

There is one source of truth: a **`session` dict**, created by `_new_session()` at the start of each run. Every step reads what it needs from the session and writes its result back into the session. Nothing important is kept in loose variables, and the user is never asked again mid-run.

The fields it tracks:

| Field | What it holds |
|---|---|
| `query` | the original user text |
| `parsed` | the extracted `description`, `size`, `max_price` |
| `search_results` | the list from `search_listings` |
| `selected_item` | the top listing (the input to the next two tools) |
| `wardrobe` | the user's wardrobe |
| `outfit_suggestion` | the text from `suggest_outfit` |
| `fit_card` | the text from `create_fit_card` |
| `error` | a message if the run stopped early, else `None` |

This is how data flows from one tool to the next: the listing saved in `selected_item` is the exact object passed into `suggest_outfit` and then into `create_fit_card`, and the text saved in `outfit_suggestion` is the exact text passed into `create_fit_card`. (Verified by identity checks — see Error Handling and testing below.)

## Error Handling (per tool)

| Tool | What can go wrong | What the agent does |
|---|---|---|
| `search_listings` | No listing matches the query | Returns `[]`. The loop sees the empty list, sets `session["error"]`, and stops — it does **not** call the other tools. |
| `suggest_outfit` | Wardrobe is empty | The tool itself handles this: instead of inventing pairings, it returns general styling advice. No error. |
| `suggest_outfit` | LLM/API call fails or returns blank | The loop catches it, sets `session["error"]`, and stops before the fit card. |
| `create_fit_card` | `outfit` text is missing or blank | The tool returns a short error message string instead of crashing. |

**Concrete example from testing.** Running the no-results query from `agent.py`:

```
query = "designer ballgown size XXS under $5"
```

gave this session state:

```
search_results : []
error          : "No listings matched 'designer ballgown' under $5 in size XXS.
                  Try raising the price, dropping the size, or using broader keywords."
selected_item  : None
outfit_suggestion : None
fit_card       : None
tools called   : []      # suggest_outfit and create_fit_card were never called
```

We confirmed this by wrapping both LLM tools to record any call — neither fired. So the agent really does stop at the empty search instead of passing empty input forward.

## Spec Reflection

What matched the plan, and what we learned while building it:

- **The loop matched the plan.** The branches in `run_agent` line up with the Planning Loop and the diagram in `planning.md`: stop on empty search, stop on a bad outfit, otherwise finish with a fit card.
- **One extra guard.** The spec said `suggest_outfit` could fail by raising *or* by returning blank. In practice the tool never returns blank, but we kept both checks (a `try/except` and a blank check) so the loop stays safe even if the tool changes later.
- **A parser bug we found by testing.** The first query parser stripped all digits from the description to clean up price numbers. That also destroyed real keywords like `"90s"` and `"2003"`. A parse test caught it, and we changed the parser to remove only the matched price, keeping other digits.
- **Tie-breaking is simple.** Search ranks by keyword overlap only. When two items tie (for example a `"vintage graphic tee"` matches both a Y2K baby tee and a bootleg tour tee equally), the first one in the dataset wins. This is fine for the demo but could be made smarter (e.g. break ties by lowest price).

## AI Usage

We used **Claude** to help write the code. Two specific examples:

**1. The planning loop (`run_agent`).**
- *What we gave it:* the **Planning Loop** section, the **State Management** notes, and the **Architecture diagram** from `planning.md`, plus the `_new_session()` function and the tool signatures.
- *What it produced:* a `run_agent` that created the session, parsed the query, called the three tools in order, and stored each result in the session.
- *What we changed:* the first version had the digit-stripping parser bug above (it dropped `"90s"`/`"2003"`); we fixed the parser after a test caught it. We also kept the extra `try/except` around `suggest_outfit` to match the diagram's error path.

**2. `create_fit_card`.**
- *What we gave it:* the **Tool 3** spec block (inputs, the "casual, mention name/price/platform once each" rules, and the empty-outfit failure mode).
- *What it produced:* a function that guards against empty input and calls the LLM for a caption.
- *What we changed:* we set the temperature to `1.0` and added a live test that runs the tool a few times on the same input to confirm the captions actually differ. We also kept the empty-`outfit` guard returning a plain string so the agent never crashes.

## The Mock Listings Dataset

`data/listings.json` contains 40 mock secondhand listings across categories (tops, bottoms, outerwear, shoes, accessories) and styles (vintage, y2k, grunge, cottagecore, streetwear, and more).

Each listing has: `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, and `platform`.

Load it with:
```python
from utils.data_loader import load_listings
listings = load_listings()
```

## The Wardrobe Schema

`data/wardrobe_schema.json` defines the format the agent uses to represent a user's existing wardrobe. It includes:

- `schema`: field definitions for a wardrobe item
- `example_wardrobe`: a sample wardrobe with 10 items you can use for testing
- `empty_wardrobe`: a starting template for a new user

Load an example wardrobe with:
```python
from utils.data_loader import get_example_wardrobe
wardrobe = get_example_wardrobe()
```
