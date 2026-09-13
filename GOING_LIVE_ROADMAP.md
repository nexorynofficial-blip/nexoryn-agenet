# Going Live — Roadmap

Who does what, in order. **(ME)** = this Claude session, working in
the `nexoryn-agent` folder. **(YOU)** = you, the account owner —
things that need your money, your accounts, or your judgment call.
**(DEV CLAUDE)** = the developer's separate Claude Code session,
working in the dashboard's `admin`/`backend` repo.

---

### Phase 1 — Backend deployment prep

1. **(ME, done)** Added CORS support (`config.py`/`main.py`) so the
   deployed backend accepts requests from the dashboard's real
   domain, and a `Procfile` so standard Python hosts know how to run
   it (`uvicorn main:app --host 0.0.0.0 --port $PORT`).

### Phase 2 — Get this code somewhere deployable

2. **(YOU)** Decide where this code should live for deployment: a
   new GitHub repo, or a folder inside an existing one. Either is
   fine — just tell me which.
3. **(ME, once you answer #2)** Initialize git in this folder, commit
   everything (the real `.env` stays out of it — it's already
   gitignored), and get it ready to push.
4. **(YOU)** Create the GitHub repo (if new) and authorize the push
   — I can run `git push` once a remote is set up and you're logged
   in via `gh auth login` or similar, but creating the actual GitHub
   account/repo and granting access is yours to do.

### Phase 3 — Choose & deploy hosting for the backend

5. **(YOU)** Pick a host. Given this is one lightweight FastAPI
   endpoint with no database, any of Railway, Render, or Fly.io work
   well and have generous free/cheap tiers — Railway is probably the
   least fiddly to start with. This needs your account + your
   payment method, so it has to be you.
6. **(YOU)** Connect the GitHub repo to that platform via their web
   dashboard and deploy. I can give you exact click-by-click
   instructions once you pick a platform — say the word and I'll
   write them out for whichever one you choose.
7. **(YOU)** In that platform's dashboard (not in git), set the
   environment variables: `ANTHROPIC_API_KEY`, `LLM_MODEL`, and
   `CORS_ALLOWED_ORIGINS` (include your production dashboard's real
   domain here).
8. **(YOU)** Once deployed, copy the public URL the platform gives
   you (e.g. `https://nexoryn-agent.up.railway.app`) — you'll hand
   this to the developer next.

### Phase 4 — Wire up production frontend

9. **(YOU)** Give the developer (or their Claude Code) the deployed
   backend URL from step 8, and confirm the widget integration
   report they already sent is what actually gets deployed.
10. **(DEV CLAUDE)** Set the production `VITE_NEXORYN_AGENT_URL` env
    var (in Vercel's project settings for the `admin` app, or
    wherever that app's production env vars live) to the URL from
    step 8.
11. **(DEV CLAUDE)** Commit and deploy the `ProjectForm.tsx` widget
    integration to production — push to whatever branch triggers
    their Vercel deploy for the `admin` app.
12. **(YOU)** Confirm the Vercel deployment actually went out (check
    the deploy log / visit the live admin URL).

### Phase 5 — Test for real

13. **(YOU)** Log into the real production dashboard, open New
    Project, click the widget, paste a real summary, pick images,
    click "Fill Form." This is the point where a real Anthropic API
    call happens (a cent or two) and real images get uploaded to
    Cloudinary — same rule as always, I won't trigger this, you do.
14. **(YOU)** Review what got filled in. If anything looks wrong,
    send me what happened (screenshots, the review report, any
    console errors) and I'll help fix it.
15. **(YOU)** Click Save Project yourself, whenever you're satisfied
    — never automated, by design.

---

## Right now, the next unblocking action is step 2

Tell me: new GitHub repo, or an existing one? Once I know that, I can
do step 3 immediately.
