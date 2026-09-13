Prompt to hand to the Nexoryn Dashboard developer (or paste into an
AI coding assistant that has access to the `admin/` app). Copy
everything below the line.

---

I need you to wire a small AI assistant widget into the "New
Project" form (`admin/src/pages/ProjectForm.tsx`). It lets an admin
paste a project summary + pick images, and it fills in the real form
fields automatically for review — **it never saves or submits
anything itself**. The admin always reviews what's filled in and
clicks "Save Project" themselves, same as today.

## Files I'm sending you

1. `FloatingAgentWidget.tsx` — the widget component, already built
   and type-checked. Copy it to `admin/src/components/FloatingAgentWidget.tsx`.
2. `nexoryn-logo.png` — the button's icon (256×256). Copy it to
   `admin/public/nexoryn-logo.png` (Vite serves anything in `public/`
   at the root path, which is why the component references it as
   `/nexoryn-logo.png`).
3. `README.md` (the one from the `widget/` folder — rename it to
   something like `WIDGET_README.md` if it'd otherwise clash with
   this repo's own README) — full integration instructions and an
   example `onAutofill` implementation. Read this in full before
   starting — it explains exactly what the widget hands you and why
   it's structured this way.
4. `PORTFOLIO_FORM_REFERENCE.md` — the reference document you wrote
   for me describing the real project schema. The widget's output is
   shaped to match `caseStudy` in this document's §4.2 exactly.

## What you need to do

1. Copy the two files into place as described above.
2. In `ProjectForm.tsx`, render `<FloatingAgentWidget />` and write
   an `onAutofill` handler that applies the data it receives to this
   component's **actual** state setters. `WIDGET_README.md` has an
   example, but the setter names in it are illustrative — use this
   file's real ones.
   - Text/structural fields (`title`, `industry`, `service`,
     `description`, `tags`, `caseStudy`) map straightforwardly to
     whatever state/setters already populate those fields today.
   - Images (`uploadedAssets`) are **already-created Asset rows** —
     the widget uploads them itself via `POST /api/v1/admin/assets`
     using the admin's existing session. Apply them exactly the way
     a manual "+Add photo" / "Choose photo" click already does in
     this file today (for Web Development: the single `photo`; for
     Automation/Design: append to `mediaItems`). Don't re-upload
     them — they already exist as real Asset records.
3. Add `VITE_NEXORYN_AGENT_URL=http://localhost:8000` (or wherever
   the Python backend actually runs) to `admin/.env`.

## Constraints — please don't change these

- **Do not** add any code path that calls `POST` or `PUT
  /api/v1/admin/projects` from this widget or its handler. The whole
  point is that filling the form and saving it stay separate steps —
  the admin always clicks Save Project themselves. Since there's no
  draft state on `Project` at all (per your own §4 in the reference
  doc), this is the only place a safety checkpoint can exist.
- Don't add a role/permission check specific to this widget — it
  should behave the same for any admin who could already use this
  form.
- Leave the existing thumbnail-selection UI (the star toggle in
  `MultiImageUploader`) untouched — don't have the widget or its
  handler auto-pick a thumbnail. Whatever this component's current
  default behavior is when an image is added (per §5.2, the first
  one added becomes the thumbnail) can stay exactly as-is.

## When you're done

Please fill in `WIDGET_INTEGRATION_REPORT_TEMPLATE.md` (also
attached) and send it back — that's what I'll hand back to the AI
that built this, so it can help debug anything that doesn't work on
the first real test.
