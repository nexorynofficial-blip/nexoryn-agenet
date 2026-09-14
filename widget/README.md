# Floating AI Assistant Widget

Drop-in React component for the Nexoryn Dashboard's **New Project**
page. Renders the floating circular button, and fills in the real
form's text fields for the admin to review — it never saves or
publishes anything itself, and it doesn't touch photos at all (those
stay a fully manual step, same as always).

## Visual design

Matches the site's dark "forge" theme — near-black surfaces,
glassmorphism panel (28px backdrop blur, film grain overlay),
Montserrat ExtraBold uppercase headings, Chakra Petch for technical
labels, and the signature orange-to-gold gradient on the primary
action. All CSS is scoped under `.nxai-` classes and injected via a
`<style>` tag in the component itself — no global CSS changes
needed, and nothing here should collide with the rest of the app's
styles.

Fonts (Manrope, Montserrat, Chakra Petch) are pulled via an `@import`
inside that same injected stylesheet, so it renders correctly with
zero setup. If these fonts are already loaded site-wide elsewhere in
`admin/`, it'd be slightly more efficient to add proper `<link>` tags
to `admin/index.html` instead and let the browser load them once in
parallel — optional, not required for correctness.

The button icon path uses `import.meta.env.BASE_URL` (not a
hardcoded `/nexoryn-logo.png`), so it resolves correctly whether the
admin app is served at the site root or under a sub-path like
`/admin/` — a real bug in an earlier version, now fixed.

## Why this lives inside ProjectForm.tsx, not the generic layout

Earlier versions of this widget assumed a separate backend would
drive a headless browser to fill the form from outside. That's gone.
Per `PORTFOLIO_FORM_REFERENCE.md`, the real form has no stable
`id`/`name`/`data-testid` attributes to target externally (§7.3), and
there's no draft state to save to anyway (§4) — so the only robust
way to "fill in the fields" is for this widget to call directly into
`ProjectForm.tsx`'s own React state, from inside the same component
tree. That means it must be rendered **inside `ProjectForm.tsx`**,
not just somewhere in the dashboard's outer layout.

## Integration

1. Copy `FloatingAgentWidget.tsx` into `admin/src/components/`.
2. Copy `assets/nexoryn-logo.png` (256×256, already sized for a
   button icon — not `assets/nexoryn-logo-original.png`, a 13MB
   reference file, not for shipping) into `admin/public/` as
   `admin/public/nexoryn-logo.png`.
3. In `ProjectForm.tsx`, render it and wire `onAutofill` to your own
   state setters. **The setter names below are illustrative** — swap
   in whatever this file's actual state variables are called:

   ```tsx
   import FloatingAgentWidget, { type AutofillPayload } from "@/components/FloatingAgentWidget";

   function handleAutofill(data: AutofillPayload) {
     setTitle(data.title);
     setIndustry(data.industry);
     setService(data.service);
     setDescription(data.description);
     setTags(data.tags);

     // Case study content: however this component currently applies
     // a full case-study object (e.g. the CaseStudyEditor's onChange
     // prop, or a single setCaseStudy(...) call) — feed it
     // `data.caseStudy` there. It's shaped exactly like
     // standardCaseStudySchema / designCaseStudySchema minus
     // gallery/photoId — photos aren't part of this payload at all.
     setCaseStudy((prev) => ({ ...prev, ...data.caseStudy }));
   }

   // Inside the component's JSX, alongside the rest of the form:
   <FloatingAgentWidget
     backendApiBaseUrl={import.meta.env.VITE_NEXORYN_AGENT_URL}
     onAutofill={handleAutofill}
   />
   ```

   Since this no longer touches `photo`/`mediaItems`/`thumbnailId` at
   all, the service-switch race condition earlier versions of this
   doc warned about doesn't apply here — there's nothing image-related
   left for `handleAutofill` to set.

4. Set `VITE_NEXORYN_AGENT_URL` in `admin/.env` to wherever the
   Python backend is running (e.g. `http://localhost:8000` in dev).
   This is a Vite app, so the env var must be prefixed `VITE_` and
   read via `import.meta.env`, not `process.env`. **Set it by typing
   the value directly** rather than pasting from another source if
   you can — a pasted value carrying an invisible leading character
   (e.g. a UTF-8 BOM) will silently break every request the widget
   makes, and it won't look like an error, it'll look like a broken
   URL.

## What it does / doesn't do

- Calls the Python backend's `POST /extract` (the **only** network
  call this makes, and the only one that costs anything — one
  Anthropic API call per click) to turn the summary into structured
  data shaped like the real project schema.
- Calls `onAutofill` with the result. From there, it's ordinary React
  state in `ProjectForm.tsx` — visible, editable, and entirely under
  the admin's control.
- **Does not touch photos at all.** No file picker, no upload call,
  nothing in the payload related to images. The admin adds photos the
  same way they always have, through the dashboard's existing photo
  picker.
- **Never calls `POST`/`PUT /api/v1/admin/projects`.** There is no
  code path in this widget, or in the Python backend, that creates
  or saves a project. That capability simply doesn't exist here —
  the admin always clicks Save Project themselves, in the dashboard's
  own UI, after reviewing. (There's no draft state to fall back to
  either — see `PORTFOLIO_FORM_REFERENCE.md` §4 — so this is the only
  place a safety checkpoint can live.)
- Every field except a live project URL (`caseStudy.livePreview`) is
  always filled with a reasonable derived value rather than left
  blank — including `caseStudy.results.before/after/proof` — since
  the admin reviews everything before saving anyway. Only a URL is
  held to "must be explicitly stated," since a wrong guess there is
  an actively broken link, not just cautious editorial content.

## Not included here

Zero dependencies beyond React. Assumes it's dropped into an existing
Vite + React + TypeScript app (which `admin/` already is).
