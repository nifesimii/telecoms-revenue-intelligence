# Onboarding — Getting Productive on the FBB Trade Partner Intelligence Codebase

For new team members joining the platform. Work through the steps in order,
at your own pace. Each step names concrete files to read, actions to take,
and a "done when" checkpoint so you know you've absorbed the material
before moving on.

Pair this with the slide deck at [`docs/FBB_Onboarding.pptx`](FBB_Onboarding.pptx)
— the deck is the map, this file is the walkthrough.

---

## Before you start — access checklist

- GitHub access to `nifesimii/telecoms-revenue-intelligence`
- Anthropic API key (for the chat features — dev key from Nifesimi)
- Read access to the deployed preview at
  [fbb-preview.onrender.com](https://fbb-preview.onrender.com)
  (credentials from Nifesimi)
- Local dev tools installed: **Python 3.12+**, **Node 20+/22+**, **Docker Desktop**
- Slack workspace + join the FBB engineering channel

Skip anything you already have.

---

## Step 1 — Business context + get it running

Get the code running locally and get the vocabulary in your head before
touching anything.

**Read**

- Slides 2, 3, 16, 17 of [`docs/FBB_Onboarding.pptx`](FBB_Onboarding.pptx) —
  business context + goals
- [`ARCHITECTURE.md`](../ARCHITECTURE.md) sections 1-3 (overview, tech stack,
  directory tour)
- [`CLAUDE.md`](../CLAUDE.md) end-to-end — it's short and it's the rulebook

**Do**

- Clone the repo, follow the five commands on slide 13 to run backend +
  frontend locally (skip Docker for now — the next step covers it)
- Open `http://localhost:5173`, click through every tab
- Read [`docs/GM_DEMO.md`](GM_DEMO.md) while browsing so the vocabulary maps
  to what you're seeing on screen
- Write down the acronyms that come up (ORSC, USP, IFS, dev_act, FBB, EB) —
  they appear everywhere

**Done when**

You can explain in one sentence what each of the six tabs answers, without
opening the deck.

---

## Step 2 — Data + tests

Learn where the numbers come from and prove the code works on your machine.

**Read**

- Every file in `data/samples/` — actually open them and look at the columns
- [`backend/db/queries.py`](../backend/db/queries.py) top to bottom. This
  is where **all** data access lives.
- [`backend/db/connection.py`](../backend/db/connection.py) — the
  `execute_query` choke point

**Do**

- Bring up the audit Postgres: `docker compose up -d` (runs on port 5544
  plus a backup sidecar)
- Run the full test suite: `.venv/bin/python -m pytest backend/tests -q`
  — ~208 tests, ~7 minutes. Read what runs.
- Open the **Audit Trails** tab, click **Run** for each of the four
  modules, then expand a couple of trails and read the step chains
- Read [`backend/audit/base.py`](../backend/audit/base.py) +
  [`backend/audit/trail.py`](../backend/audit/trail.py) — the registry
  and the trail primitive

**Done when**

You can point to the exact CSV file + handler function + query name that
produces a specific number in the UI.

---

## Step 3 — Deep-dive one audit module + one intelligence tab

Now trace live data through the layers, end to end.

**Read one audit module (pilot: `zero_commission_audit.py`)**

- Read the module front-to-back with `data/samples/fbb_comm_dev_act_202602.csv`
  open beside you
- Trace one partner's trail: pick a `partner_code` from the UI, follow it
  through `run_period` → `gather_inputs` → `build_trail` → the six steps →
  conclusion
- Read [`backend/tests/test_zero_commission_audit.py`](../backend/tests/test_zero_commission_audit.py) —
  this is the test-shape template for every future audit module

**Read one intelligence tab (pilot: Activation Intelligence)**

- Read `frontend/src/components/activation/*.jsx`
- Read [`frontend/src/api/client.js`](../frontend/src/api/client.js) —
  every backend call is centralised here
- Find each endpoint's route in `backend/api/routes.py` and its handler in
  `backend/db/queries.py`
- Trace one dealer's "Total Activations" number from screen → CSV cell

**Done when**

You can walk any teammate through (a) one partner's audit trail step-by-step
and (b) one activation number's full provenance.

---

## Step 4 — The agent + knowledge base (the AI layer)

Understand how the chat side works, because it drives every future prompt
you'll design.

**Read**

- `backend/agent/agent.py` — the 5-iteration bounded tool-use loop
- `backend/agent/tools.py` — the ~13 tool definitions in Anthropic format
- `backend/agent/tool_executor.py` — how tool calls route to `execute_query`
- `backend/agent/prompts.py` — how the KB gets injected into every system
  prompt
- `backend/knowledge_base/fbb_commission_kb.md` end-to-end, slowly. This is
  the domain.
- Skim `backend/knowledge_base/addenda/` — what gets pulled in on demand
  vs baked into every prompt

**Do**

- Open the Commission Intelligence chat, ask five questions, watch the
  "tools called" list on every reply
- Ask one question the agent shouldn't be able to answer from its tools —
  see how it declines

**Done when**

You can predict which tool(s) Claude will call for a given natural-language
question, before you send it.

---

## Step 5 — Ship a first PR

Pick something small and get through the full ship cycle so you touch
every layer once.

**Pick from these, roughly easiest-first**

1. A doc fix you noticed while reading (typo, stale reference, unclear
   paragraph)
2. A missing test case — any `build_trail` edge case you thought of that
   isn't covered
3. A UI polish — a label that reads awkwardly, a missing empty state, a
   truncation issue
4. Something small from the "Next" section of [`PROGRESS.md`](../PROGRESS.md)
   that you have context for
5. A new sub-section for [`GM_DEMO.md`](GM_DEMO.md) based on something you
   found confusing that a first-time viewer would too

**Do**

- Branch → change → `pytest backend/tests -q` green → commit with a
  written message → PR
- Add a session note to [`PROGRESS.md`](../PROGRESS.md) at the top
- Read `PROGRESS.md` again at end of day — that's the tempo of this
  project, remember it

**Done when**

You've merged one PR, however small, and `PROGRESS.md` has your note in it.

---

## Standing rules for week one (and after)

- **Note what surprised you and what confused you every day.** Bring both
  to the next standup.
- **Ask for context, not answers.** "Which pattern does X follow?" beats
  "how do I do X?".
- **Investigate before deleting or 'fixing'.** If something looks weird,
  assume it's deliberate until proven otherwise. `ARCHITECTURE.md § 7`
  lists the deliberately-weird things.
- **Read the whole file before editing part of it.** Especially
  `backend/db/queries.py` and any `*_audit.py`.
- **When you finish reading a doc, update it if you saw something stale.**
  Docs decay if nobody touches them.

---

## When you're stuck

Slack DM Nifesimi, or bring it to the daily standup. Read the relevant doc
first, then ask with a concrete question — it saves everyone's time and
usually surfaces the answer while you're writing the question out.
