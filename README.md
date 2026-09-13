# Nexoryn AI Portfolio Agent

Lets a Nexoryn Dashboard admin paste a project summary + pick images
on the **New Project** page, and have the real form's fields filled
in automatically for review — the admin always clicks **Save
Project** themselves.

## Architecture

```
Admin, already on the New Project page in the dashboard
   -> Floating widget (widget/FloatingAgentWidget.tsx, rendered inside ProjectForm.tsx)
        -> POST /extract  (this repo's Python backend — the ONLY network call that costs anything)
             -> agent/extractor.py   summary -> structured data matching the real schema, no hallucination
             -> agent/validator.py   review report: what's filled, what's missing, what's blocking
        -> POST /api/v1/admin/assets  (the dashboard's OWN API — image uploads, using the
             admin's existing session cookie; this repo never touches it)
        -> onAutofill(payload)  applies everything to ProjectForm.tsx's own React state
   <- Admin sees the real fields filled in, reviews, edits anything, clicks Save Project themselves
```

This backend does **one job**: turn text into structured data. It
never logs into the dashboard, never opens a browser, and has no
code path that calls `POST`/`PUT /api/v1/admin/projects` — that
capability doesn't exist anywhere in this repo, on purpose. See
`PORTFOLIO_FORM_REFERENCE.md` for why: the real project record has no
draft/status field at all, so creating one always publishes
immediately — meaning the only place a safety checkpoint can live is
before that call ever happens, in the human's own hands.

## Decisions locked in for this build

- **No browser automation, no Playwright.** The real form has no
  stable selectors to target externally anyway (see
  `PORTFOLIO_FORM_REFERENCE.md` §7.3) — the widget instead runs
  inside the dashboard's own React tree and calls its state directly.
- **Extraction uses the Anthropic API** (pay-as-you-go), currently
  Haiku 4.5 — chosen for cost, with a code-enforced backstop (not
  just prompting) that strips any of the four "never invent" fields
  (`results.before`, `results.after`, `results.proof`,
  `livePreview`) unless the model explicitly confirms they were
  genuinely stated in the summary.
- **Cover image is always the admin's manual choice** — uploaded
  images are added to the pool the same way a manual "+Add photo"
  click would; the dashboard's own default-thumbnail behavior and
  star-toggle UI are left alone.
- **Category-aware**: Automation/Web Development ("standard" shape)
  and Brand & Graphic Design ("design" shape) have genuinely
  different Case Study tabs and fields — see `PORTFOLIO_FORM_REFERENCE.md`
  §2-3 for the exact per-category structure this mirrors.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate      # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env           # then add your ANTHROPIC_API_KEY
python main.py                 # serves on http://localhost:8000
```

Visit `http://localhost:8000/health` to confirm it's running, or
`http://localhost:8000/docs` to try `POST /extract` directly.

## Testing

```bash
pip install -r requirements-dev.txt
pytest tests/test_extraction.py -v
```

Pure offline tests against hand-built extraction output — no network
or API calls. Covers the standard/design schema shaping and,
critically, the no-hallucination backstop for the four sensitive
fields (both "correctly discarded" and "correctly kept" cases).

## Progress

- [x] Extraction engine, schema-accurate to the real dashboard
- [x] Validator / review report
- [x] FastAPI backend (`POST /extract`)
- [x] Floating widget (`widget/FloatingAgentWidget.tsx`) — client-side
      image upload + real-form autofill via `onAutofill`
- [ ] Wiring `onAutofill` into the real `ProjectForm.tsx` — needs the
      dashboard developer to adapt the example in `widget/README.md`
      to the component's actual state setter names
- [ ] End-to-end test against the real dashboard, with real API key

## Project layout

```
nexoryn-agent/
├── agent/
│   ├── extractor.py       # LLM extraction, schema-accurate, no-hallucination backstop
│   └── validator.py       # review report (ok / warnings / blocking)
├── widget/
│   ├── FloatingAgentWidget.tsx  # drop-in widget, rendered inside ProjectForm.tsx
│   ├── assets/nexoryn-logo.png  # button icon (256x256)
│   └── README.md                # integration instructions + onAutofill example
├── tests/
│   └── test_extraction.py       # offline regression suite
├── PORTFOLIO_FORM_REFERENCE.md  # ground-truth reference for the real dashboard's schema
├── config.py
├── main.py                # FastAPI app (POST /extract)
├── requirements.txt
├── requirements-dev.txt   # adds pytest
├── .env.example
└── README.md
```
