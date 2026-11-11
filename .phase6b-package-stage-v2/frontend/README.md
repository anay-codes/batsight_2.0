# BatSight Frontend

React + TypeScript + Vite local-first client for the Phase 6A FastAPI application.

## Run locally

Start the backend from the repository root:

```powershell
python -m batsight.application
```

Then start the frontend:

```powershell
cd frontend
npm install
npm run dev
```

The default backend URL is `http://127.0.0.1:8000`. Override it with `VITE_API_BASE_URL` before running Vite. Create an optimized build with `npm run build`; preview it with `npm run preview`.

## Scope and data handling

- Project, recording, experiment, health, and capability views use live API data.
- Sound Studio uses the backend's generic sine/linear-sweep generator. The 2016 paper's chirp equation remains unresolved and is not claimed to be reproduced.
- Browser microphone capture is a single-device recording. MediaRecorder output stays in its original browser format; exporting WAV creates an explicit decoded PCM16 copy and leaves the original available. Browser decoding may use a different sample rate; the export reports decoded rate and channel count.
- Upload accepts WAV only and the backend retains uploaded bytes without resampling. No frontend behavior combines sequential recordings into a synchronized array.
- Signal analysis uses the backend matched-filter and peak-detector services. Correlation candidates remain unclassified; no direct/echo identity or room geometry is inferred.
- Experiments expose only the backend's `synthetic_forward` pipeline and mark known synthetic ground truth as not estimated geometry or real-world validation.

There is no 3D reconstruction interface in this milestone.
