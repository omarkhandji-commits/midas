# MIDAS web — operator dashboard SPA

React + Vite + TypeScript + Tailwind + shadcn-style components. Built to static assets
shipped inside the Python wheel at `src/midas/flagship/dashboard/static/app/`. No CDN,
no telemetry, no remote dependencies at runtime — everything runs from loopback.

## Develop

```bash
cd web
npm install
npm run dev          # http://127.0.0.1:5173 (proxies /api, /events, /login to FastAPI)
```

Start FastAPI in another shell so the proxy targets exist:

```bash
midas dashboard      # http://127.0.0.1:8765
```

## Build (the wheel ships this)

```bash
npm run build        # outputs to ../src/midas/flagship/dashboard/static/app/
```

## Quality

```bash
npm run lint         # eslint
npm run typecheck    # tsc -b --noEmit
npm run test         # vitest
```

The Node toolchain is a build-time and contributor-time tool only. End users install
with `pip install` and never see Node — the wheel ships the prebuilt assets.
