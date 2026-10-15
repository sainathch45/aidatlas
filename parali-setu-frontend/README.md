# Parali Setu — Frontend

Plain HTML/CSS/JS, no build step, no framework — deliberately, to match
`aidatlas-api`'s sibling frontend's simplicity. Two pages:

- `index.html` + `app.js` — farmer view. Text or voice listing submission
  (real microphone via `MediaRecorder`, WebM/Opus), optional photo
  attachment, match result with a spoken reply, and a negotiation box.
- `company.html` + `company.js` — company dashboard. Four read-only zones
  (Incoming Supply, Recommendation, Active Matches, Standing Demand form),
  polling `GET /companies/{id}/dashboard`.

`config.js` holds the one thing that changes per environment —
`API_BASE`, the deployed backend URL. Edit that file, not the HTML/JS, to
point at a different backend.

Theme: committed light-only (see the comment at the top of `styles.css`)
— a deliberate choice for this product, not a missing dark-mode variant.

## Running locally

Any static file server works, e.g.:

```bash
python -m http.server 8000
```

Then open `http://localhost:8000`. Update `config.js` to point at a
locally-running backend (`http://localhost:8000` for `uvicorn`, a
different port than the frontend's own) if testing both together.

## Deploying

```bash
firebase deploy --only hosting:parali-setu --project ai-builder-cup-aidatlas
```

Live: https://parali-setu.web.app

(The backend's `main.py` CORS config already allows all origins, so this
works regardless of which Firebase Hosting site serves the frontend.)

## Known gaps, honestly

- No automated frontend tests — everything here was verified by hand
  through a real browser against the live deployed backend, not with a
  test suite. Worth adding before this gets much bigger.
- The confirm/edit-before-submit step from the PRD isn't built (see the
  backend README's "Known gaps" — same root cause, this is the UI side
  of it).
