# Optima Pars as a Progressive Web App

Phase 1: the app is installable (standalone window, home-screen icon) with safe static caching.
It is **not** an offline app: pages and all data still require the network, and nothing
authenticated, per-user or unpublished is ever cached (the service worker caches only the hashed
`/assets` bundle, `/fonts`, and the icon/manifest shell — never `/api/` or navigations).

## Pieces

- `public/manifest.webmanifest` — identity (`id: "/"`), standalone display, start URL `/`, ivory
  background `#F7F3EA`, forest-green theme `#355740`, 192/512 PNG icons + SVG.
- `index.html` — manifest link, viewport, dynamic theme-color, apple-touch-icon, and the
  mobile/apple standalone metas.
- `public/sw.js` — one service worker for both push notifications (unchanged handlers) and
  versioned static caching (`optima-pars-static-v1`; bump the suffix to invalidate). Registered on
  load from `src/main.tsx` (idempotent with the registration the notification settings perform;
  notification permission is still only requested from the explicit button).
- Vercel serves `sw.js` with `Cache-Control: no-cache` and `/assets` as immutable (`vercel.json`).

## Manual installation checklist (not yet performed on real devices)

Desktop (Chrome/Edge, production HTTPS or `http://localhost:5173` with the backend running):
1. Open the app, sign in. DevTools → Application → Manifest: no installability warnings;
   Service Workers: `sw.js` activated.
2. The install icon appears in the address bar → install → the app opens in a standalone window
   with the Optima Pars icon and green title bar; navigation, The Oratory, Rule of Life and the
   Calendar all behave as in the browser.
3. Reload inside the installed window; check Network panel: `/assets/*` and `/fonts/*` served
   from the service worker, every `/api/*` request from the network.

Android (Chrome): browser menu → "Add to Home screen" (or the install prompt) → launches
standalone. Push notifications continue to work once enabled from Rule of Life.

iPhone/iPad (Safari ≥ 16.4): Share → "Add to Home Screen" — Safari offers no automatic prompt, so
this manual step is the only install path. Web Push on iOS works **only** from the installed
home-screen app. The apple-touch-icon supplies the home-screen artwork.

Uninstall/re-install once to confirm the start URL and icon survive.

## Known limitations

- No offline mode: without a network the installed app cannot load pages or data (deliberate —
  the app shell is not cached to avoid serving a stale index or caching anything sensitive).
- Safari/iOS: manual installation only; notifications require the installed app.
- The 512px icon is not declared `purpose: "maskable"`; Android may letterbox it inside the
  adaptive-icon circle. If that looks poor on a real device, export a padded maskable variant and
  add it to the manifest (do not mark the existing art maskable without checking the safe zone).
