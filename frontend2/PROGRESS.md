# BatSight frontend2 Progress

## Stack
- React 18.3.1, TypeScript 5.6.3, Vite 8.3.8, react-router-dom 7.18.5
- Tailwind CSS 3.4.16 + custom CSS (`styles.css`, `workspace-shell.css`)
- Three.js 0.170 / @react-three/fiber 8.18 / @react-three/drei 9.122, Recharts 2.15, Lucide 0.468
- Package manager: npm (`frontend2/package-lock.json`)

## Structure
- `src/App.tsx`: Routes + `LandingPage` + all workspace pages wrapped in `WorkspaceShell`
- `src/workspace/WorkspaceShell.tsx` + `workspace-shell.css`: Teal-grey Gotham shell, cobweb/spider toggle, 3 swaying bats, frosted panel, 2-layer skyline + cats, hover-reveal sidebar
- `src/scanner/RoomScanner.tsx`: Guided 4-wall acoustic scanner (default `/workspace` route)
- `src/workspace3d/Workspace3D.tsx` + `RoomPlan2D.tsx`: 3D View, 2D Floor Plan, Wireframe Sketch (graph-paper + hand-drawn cube SVG), SMARD 0001 preset
- `src/api.ts`: Exact copy of `/frontend/src/api.ts` (`VITE_API_BASE_URL`)

## Done
- Step 2: Dependencies installed, `tsc -b && vite build` & `vitest` (11/11) pass, API wired
- Step 3: All buttons/forms/routes wired to `api.ts` with loading/empty/error states
- Step 4: `WorkspaceShell` with `/workspace` defaulting to Room Scanner, hover sidebar + spider toggle (`Enter`/`Space`/`Esc`)
- Step 5: `RoomScanner` inside `WorkspaceShell`
- Step 6: `Workspace3D` with graph-paper + hand-drawn cube SVG + 3D/2D/SMARD + all other pages in `WorkspaceShell`
- Step 7: Google Font `Anton` on hero `BATSIGHT` and `--ws-title-font` on workspace titles

## Pending
- Final live dev server + Playwright/headless verification of all routes, buttons, responsiveness, and console errors

## Mock Buttons
- None (all buttons use real `api.ts` endpoints or local state; `RoomScanner` has graceful mic-unavailable fallback distances)

## Gotchas
- `/frontend` and `/backend` are strictly read-only
- `WorkspaceShell` uses `margin-bottom: clamp(36px, 5vh, 56px)` so frosted panel overlaps skyline bottom like Screenshot 1
