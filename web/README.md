# Payer Policy Compare — web app

React + Vite single-page app that compares medical & drug coverage policies across
payers, deployed to **Firebase Hosting** with the dataset shipped as a static bundle
(no database/billing). Built from the `policydb` SQLite dataset.

## Pages
- **Compare** (`/`) — searchable list of cross-payer topics → side-by-side comparison.
- **Topic** (`/topic/:id`) — each payer's matched policy in a column (policy #, dates,
  codes, coverage excerpt, link to source).
- **Browse** (`/browse`) — full-text search/filter across every policy.
- **Policy** (`/policy/:id`) — full text + metadata + procedure codes.

## Data bundle (regenerate after a new pull)

The site reads `web/public/data/` (git-ignored, regenerated from the dataset):

```bash
# from repo root, after scripts/pull.py has populated data/policies.db
python scripts/export_web.py --db data/policies.db --out web/public/data
```

This writes `index.json` (metadata), `topics.json` (cross-payer clusters from the
matcher in `policydb/match.py`), `meta.json`, and `text/<id>.json` (full text +
coverage excerpt, lazy-loaded per policy).

## Develop & build

```bash
cd web
npm install
npm run dev        # local dev server
npm run typecheck  # tsc --noEmit
npm run build      # -> web/dist
```

## Deploy to Firebase

One-time: create a Firebase project and put its id in `.firebaserc` (repo root,
replace `REPLACE_WITH_YOUR_FIREBASE_PROJECT_ID`). `firebase.json` (repo root) is
already configured to serve `web/dist` as an SPA.

```bash
npm install -g firebase-tools      # once
firebase login                     # once  (or: ! firebase login in this session)

# from repo root:
python scripts/export_web.py --db data/policies.db --out web/public/data
cd web && npm run build && cd ..
firebase deploy --only hosting
```

To refresh data later: re-run `scripts/pull.py` for each source, re-export, rebuild,
redeploy.
