# BatSight Frontend

React + TypeScript + Vite frontend. The dev server is configured for `http://localhost:5177`.

## Requirements

- Node.js 22.12 or newer in the Node 22 line (recommended: Node 22 LTS)
- npm 10 or newer
- Network access to the npm registry for the first install

Check versions:

```powershell
node --version
npm --version
```

## Install and run (Windows PowerShell)

Run these commands from the folder containing this `package.json` (the `frontend` folder):

```powershell
cd path\to\your\project\frontend
npm ci
npm run dev
```

Then open `http://localhost:5177`. `strictPort` is enabled, so Vite will report an error rather than silently switching ports if 5177 is already occupied.

If you do not have a lockfile or intentionally changed dependencies, use `npm install` instead of `npm ci`, then commit the updated `package-lock.json`. For a clean ZIP checkout with the supplied lockfile, prefer `npm ci`.

## If npm reports `ENOTFOUND registry.npmjs.org`

That is a DNS/network resolution failure, not a Vite configuration error. Neither `npm ci` nor `npm install` can fetch missing packages until the machine can resolve and reach the registry. Check the connection, VPN/proxy, DNS settings, or try another network, then run:

```powershell
npm ping --registry=https://registry.npmjs.org/
npm ci
```

Do not copy or symlink another project's `node_modules` into this project. Vite and its plugins should be installed into this frontend's own dependency tree by `npm ci`.

## Build and tests

```powershell
npm run build
npm test
```

The default backend URL is `http://127.0.0.1:8000`. Override it by setting `VITE_API_BASE_URL` before starting Vite.
