# BatSight 2.0 — Presentation Slide Content (Copy-Paste Ready)

Each slide below has a **title**, **bullet content**, and **speaker notes**.

---

## SLIDE 1: Title Slide

**Title:** BatSight 2.0: Acoustic Soundscape-to-3D Spatial Mapping Engine

**Subtitle:** Integrated Skill Project Report

**Details:**
- Student Name: [YOUR NAME]
- PRN: [YOUR PRN]
- Guide: [GUIDE NAME]
- Department / University: [FILL IN]

---

## SLIDE 2: What is BatSight?

**Title:** What is BatSight 2.0?

**Content:**
- End-to-end system that **reconstructs room geometry from sound**
- Emits a known sound (Exponential Swept Sine) → Records echoes → Estimates wall positions
- Based on the **Image-Source Model**: each wall reflection = a virtual "mirror" source
- Validated on a **real physical room** (not just simulation)
- Full-stack: Python DSP backend + React 3D frontend

**Speaker Notes:** BatSight uses echoes instead of cameras or lasers. We play a known sound, record it with microphones, and work backward from the echo arrival times to figure out where the walls are. Think of it like a bat's echolocation, but with math.

---

## SLIDE 3: Problem Statement

**Title:** The Problem

**Content:**
- Existing acoustic room reconstruction works **only in simulation** — fails on real hardware
- Real hardware introduces a **hidden timing offset** (−0.353 ms loopback latency)
- Real rooms produce **massive echo clutter** — 94.4% false positives in our dEchorate test
- Datasets use **different coordinate axes** — silent axis swaps corrupt results
- No reconstruction tool reports **why** its answer is reliable (no diagnostics)

**Speaker Notes:** When we took code that worked perfectly on synthetic data and ran it on real recordings, three things broke. First, the sound card adds a timing delay nobody told us about. Second, real rooms produce so many echoes that most detected peaks are garbage. Third, one dataset says width-length-height and another says length-width-height — if you don't catch that, every dimension is wrong.

---

## SLIDE 4: Objectives

**Title:** Project Objectives (5 Measurable Goals)

**Content:**
1. Build a typed DSP pipeline for **matched-filter TOA extraction** with sub-sample precision
2. Implement a **calibrated shoebox dimension estimator** with Jacobian diagnostics
3. Validate on **real physical data** (SMARD 0001) — target: <1% error on all axes
4. Expose results via **FastAPI REST API** with Pydantic contracts
5. Render in **interactive 3D workspace** (React + Three.js) with ground-truth overlay

**Speaker Notes:** These aren't vague goals — each one has a testable pass/fail criterion. Number 3 is the hardest: <1% error on a real 8-metre room means every wall must be within 8 centimetres of truth.

---

## SLIDE 5: Architecture Overview

**Title:** System Architecture

**Content:**
```
SMARD Raw Audio (24ch FLAC @ 48kHz)
        ↓
   DSP Engine (matched_filter.py, peaks.py)
        ↓
   TOA Extraction + Loopback Calibration (−0.353 ms)
        ↓
   Shoebox Dimension Estimator (least_squares, analytic Jacobian)
        ↓
   FastAPI + SQLite Backend (GET /api/reconstructions/smard-0001)
        ↓
   React 3D Workspace (Three.js wireframe + diagnostics panel)
```

**Speaker Notes:** Data flows top to bottom. Raw FLAC files in, 3D room model out. The key innovation is the calibration step in the middle — without subtracting the loopback offset, every wall is 12 cm wrong.

---

## SLIDE 6: The Dataset — SMARD Configuration 0001

**Title:** SMARD 0001: Our Real-World Benchmark

**Content:**
- **Room B5-108**, Aalborg University: 8.09 × 7.34 × 2.87 m
- **24 channels**: 21 B&K 4957 mics (X/Y/Z orthogonal arrays) + 1 single mic + 1 loopback + 1 dummy
- **Excitation**: Exponential Swept Sine, 10 Hz – 24 kHz
- **Sample rate**: 48,000 Hz, 24-bit FLAC
- **Duration**: 12.000 s (576,001 samples per channel)
- **Temperature**: 21.6 °C → speed of sound c = 344.17 m/s

**Speaker Notes:** This is a real, physical listening room at Aalborg University in Denmark. The microphones are arranged in three orthogonal lines of 7, spaced 5 cm apart. Channel 8 is the electrical loopback — the signal tapped directly from the amplifier without going through the air. That's our timing reference.

---

## SLIDE 7: DSP Pipeline — Matched Filtering

**Title:** Step 1: Matched Filtering

**Content:**
- Cross-correlate each mic recording with Ch 08 (electrical loopback reference)
- Peak of |correlation| = direct-path arrival time
- Sub-sample interpolation via parabolic fit → ~0.02 ms precision
- Two-stage threshold peak detection (local window thr1=0.9, global thr2=0.02)

**Code (simplified):**
```python
corr = correlate(recording, reference, mode="full")
lags = correlation_lags(len(recording), len(reference))
peak_lag = lags[np.argmax(np.abs(corr))]
arrival_time = peak_lag / sample_rate
```

**Speaker Notes:** The matched filter is the standard detection technique — it maximizes signal-to-noise ratio for a known waveform. We use the electrical loopback as the reference because it's the purest copy of what was actually played.

---

## SLIDE 8: The Discovery — Hardware Loopback Offset

**Title:** Step 2: Hardware Calibration (The −0.353 ms Discovery)

**Content:**
- **Raw timing error** across all 22 mics: constant bias of **−0.353 ms** (12.16 cm)
- This is the electrical-to-acoustic delay in the sound card hardware
- **Invisible in synthetic tests** — only appears with real hardware
- After subtracting this offset:
  - MAE drops from **12.05 cm → 1.98 mm**
  - p95 error: 12.28 cm → 6.25 mm

| Metric | Before Calibration | After Calibration |
|--------|:-:|:-:|
| MAE | 12.05 cm | **1.98 mm** |
| p95 | 12.28 cm | **6.25 mm** |

**Speaker Notes:** This was the single biggest discovery. Every microphone's measured arrival time was 0.353 milliseconds too early compared to theory. That's because the electrical loopback taps the signal before it reaches the speaker's transducer. Once we subtract this constant, our timing precision drops from centimetre-level to millimetre-level.

---

## SLIDE 9: Dimension Estimation Algorithm

**Title:** Step 3: Bounded Nonlinear Least-Squares

**Content:**
- **132 labeled first-order reflections** (22 mics × 6 walls)
- Residual: r_k = t_observed − t_predicted(Lx, Ly, Lz)
- Analytic Jacobian: ∂t/∂L computed from image-source geometry
- Optimizer: `scipy.optimize.least_squares`, Trust Region Reflective
- Bounds: lower = max(known positions) + clearance, upper = 15 m
- Convergence tolerances: ftol = xtol = gtol = 1e-12

**Speaker Notes:** We minimize the sum of squared timing residuals. The Jacobian is computed analytically, not numerically — this makes the optimizer faster and more accurate. Only "max" wall reflections (x_max, y_max, z_max) have nonzero derivatives with respect to room dimensions; "min" wall reflections are anchored at the origin.

---

## SLIDE 10: Results — Dimension Accuracy

**Title:** Results: <1% Error on All 3 Axes

**Content:**

| Dimension | Ground Truth | Estimated | Error | % Error |
|:-:|:-:|:-:|:-:|:-:|
| **Lx (Length)** | 8.090 m | 8.162 m | +7.21 cm | **+0.89%** |
| **Ly (Width)** | 7.340 m | 7.349 m | +0.94 cm | **+0.13%** |
| **Lz (Height)** | 2.870 m | 2.898 m | +2.78 cm | **+0.97%** |

- **Residual RMS**: 0.250 ms
- **Jacobian Rank**: 3/3 (full rank)
- **Condition Number**: 2.07 (well-conditioned)
- **3 starting guesses → identical result** (no local minima)

**Speaker Notes:** Every axis is within 1% of ground truth. The width estimate is within 1 centimetre. All three starting guesses converge to exactly the same answer, which means there's only one minimum. The condition number of 2.07 means the problem is very well-posed — the information from 132 reflections strongly constrains all three dimensions.

---

## SLIDE 11: 3-Start Convergence Proof

**Title:** Convergence from 3 Different Starting Guesses

**Content:**

| Starting Guess (m) | Result (m) | Func Evals | Status |
|:-:|:-:|:-:|:-:|
| [7.0, 5.0, 2.2] | [8.162, 7.349, 2.898] | 6 | Converged ✅ |
| [10.0, 10.0, 4.0] | [8.162, 7.349, 2.898] | 7 | Converged ✅ |
| [7.5, 8.5, 3.2] | [8.162, 7.349, 2.898] | 6 | Converged ✅ |

- Identical estimated dimensions from all 3 starts
- 6–7 function evaluations each (fast convergence)
- Same residual RMS, same Jacobian rank, same condition number

**Speaker Notes:** This is strong evidence of a unique global minimum. We deliberately pick very different starting points — one undersized, one oversized, one asymmetric — and they all land on the same answer in 6–7 iterations.

---

## SLIDE 12: 3D Workspace UI

**Title:** Interactive 3D Visualization

**Content:**
- **SMARD 0001 (Real Room)** preset button loads calibrated reconstruction
- **Estimated room**: teal wireframe box (8.162 × 7.349 × 2.898 m)
- **Ground-truth overlay**: amber wireframe (8.090 × 7.340 × 2.870 m), toggleable
- **22 microphones**: cyan spheres at array positions
- **Loudspeaker**: orange sphere at (6.500, 2.000, 1.425) m
- **Diagnostics panel**: Estimated vs GT table, % errors, residual RMS, Jacobian rank, condition number, loopback offset badge

`[INSERT SCREENSHOT: Full 3D workspace with mics + room + diagnostics]`

**Speaker Notes:** This is the final output. The user clicks one button and sees the entire reconstruction. The amber wireframe is the actual room — you can see it almost perfectly overlapping the estimated teal wireframe. The right panel shows every diagnostic number so you can judge whether to trust the result.

---

## SLIDE 13: Backend API

**Title:** FastAPI REST Endpoint

**Content:**
- `GET /api/reconstructions/smard-0001`
- Returns JSON with:
  - Estimated dimensions [Lx, Ly, Lz]
  - Ground truth dimensions
  - 22 microphone coordinates (transformed to BatSight XYZ)
  - Loudspeaker coordinates
  - Diagnostics: residual RMS, Jacobian rank, condition number, optimizer status
  - Timing provenance: loopback offset, speed of sound, temperature
- Pydantic response models with field validation
- Interactive Swagger docs at `/docs`

**Speaker Notes:** The frontend fetches this single endpoint and has everything it needs to render the 3D scene and diagnostics. Pydantic ensures the response schema is always valid — if any field is missing or wrong-typed, the server returns a 500 with a clear error.

---

## SLIDE 14: Tech Stack Summary

**Title:** Technology Stack

**Content:**

| Layer | Technology |
|-------|-----------|
| DSP / Math | Python 3.13, NumPy, SciPy |
| Backend API | FastAPI, Pydantic v2, Uvicorn |
| Database | SQLAlchemy 2.0 + SQLite |
| Frontend | React 18, TypeScript 5.6 |
| 3D Rendering | React Three Fiber + Three.js |
| Build Tool | Vite 8.3 |
| Data Format | 24-bit FLAC (audio), JSON (metadata) |

**Speaker Notes:** Everything is open-source. No paid APIs, no cloud services, no GPU required. It runs entirely on localhost.

---

## SLIDE 15: Challenges & Lessons Learned

**Title:** Challenges Faced

**Content:**
1. **Coordinate convention trap**: SMARD = (width, length, height) ≠ BatSight = (X=length, Y=width, Z=height). Caught only by auditing raw `.mat` files.
2. **Source height discrepancy**: External docs say 1.25 m, actual metadata says 1.425 m. Trust primary data.
3. **−0.353 ms loopback offset**: Invisible in synthetic tests. Would have caused 12 cm systematic bias.
4. **Echo clutter**: dEchorate test showed 94.4% false peak rate. Motivated labeled approach over blind association.
5. **AttributeError in production**: Reconstruction model field names (`dimensions_m` vs `estimated_dimensions_m`) required careful code-to-schema alignment.

**Speaker Notes:** The coordinate swap was the scariest. If you swap X and Y, the room dimensions look plausible (7.34 vs 8.09) but every microphone position is wrong, and the estimator silently gives you a wrong answer that still converges. The only defense is to audit every coordinate against the primary metadata files.

---

## SLIDE 16: Future Scope

**Title:** Future Work

**Content:**
1. **Automatic echo association**: Replace manual labeling with Hungarian/optimal-transport assignment that handles clutter
2. **Self-calibration**: Estimate mic positions from direct-path TOAs before reconstruction
3. **Single-device scanning**: Room estimation from a laptop mic + chirp playback (requires solving Phase 5C initialization problem)
4. **Non-rectangular rooms**: L-shaped, trapezoidal, general convex polyhedral
5. **Real-time operation**: Sub-second pipeline for live scanning applications

**Speaker Notes:** The biggest scientific challenge is number 3 — estimating room dimensions from a single microphone. This requires solving the blind initialization problem that Phase 5C showed is severely ill-conditioned. It's an open research problem.

---

## SLIDE 17: Learning Outcomes

**Title:** What We Learned

**Content:**
1. **DSP**: Matched filtering on real 48 kHz audio — 0.02 ms timing precision, not textbook theory
2. **Numerical Optimization**: Bounded least-squares with analytic Jacobian, SVD rank analysis, condition monitoring
3. **Data Auditing**: Real datasets have coordinate traps, hidden offsets, discrepant metadata. Audit everything.
4. **Full-Stack**: SciPy backend → FastAPI REST → React Three Fiber 3D visualization
5. **Measurement > Simulation**: 100% synthetic pass rate ≠ real-world reliability. The −0.353 ms offset was invisible in simulation.
6. **Provenance-First**: Never report a number without its diagnostic context

**Speaker Notes:** The single most important lesson: synthetic tests are necessary but not sufficient. If we had stopped at simulation, we would have shipped a system with a 12 cm systematic bias and never known.

---

## SLIDE 18: Summary / Conclusion

**Title:** Summary

**Content:**
- ✅ End-to-end pipeline: Raw FLAC audio → Matched filter → Calibrated TOA → Estimated room → 3D visualization
- ✅ Real-world validated on SMARD 0001 (22 mics, B&K OmniPower speaker)
- ✅ Hardware loopback offset discovered and calibrated (−0.353 ms)
- ✅ Direct-path MAE: **1.98 mm** (after calibration)
- ✅ Room dimensions: **<1% error** on all 3 axes
- ✅ Full diagnostic transparency (residuals, Jacobian, provenance)
- ✅ Interactive 3D workspace with ground-truth overlay

**Speaker Notes:** BatSight 2.0 proves that acoustic room reconstruction works on real hardware, not just in simulation. The key was being narrow and honest — calibrated positions, labeled reflections, and full diagnostics — rather than claiming to solve the harder uncalibrated problem that Phase 5C showed is currently intractable.

---

## SLIDE 19: References

**Title:** References

**Content:**
1. Allen & Berkley (1979) — Image-Source Method, JASA
2. Nielsen et al. (2014) — SMARD Dataset, Aalborg University
3. Di Carlo et al. (2021) — dEchorate Dataset, EURASIP
4. Crocco, Trucco & Del Bue (2016) — Uncalibrated Room Reconstruction, arXiv:1606.06258
5. SciPy, FastAPI, Three.js, React Three Fiber

---

## SLIDE 20: Thank You / Q&A

**Title:** Thank You

**Content:**
- **Demo**: http://localhost:5173/workspace/3d
- **API Docs**: http://localhost:8000/docs
- **Repository**: https://github.com/anay-codes/batsight_2.0

Questions?
