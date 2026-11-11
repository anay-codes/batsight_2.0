"""Phase 5C.6: blind initialization study for direct Euclidean TOA fitting.

Exploratory only. Every initializer receives TOAs and sound speed only; ground
truth is used exclusively after optimization to score the outputs.
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib.util
import json
from pathlib import Path
import sys
from time import perf_counter

import numpy as np
from scipy.optimize import least_squares
from scipy.stats import qmc

from batsight.datasets.toa import generate_toa_observations
from batsight.simulation.shoebox import ShoeboxRoom


def load_phase5c4():
    path = Path(__file__).with_name("phase5c4_metric_consistency.py")
    spec = importlib.util.spec_from_file_location("batsight_phase5c4_exploratory", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load Phase 5C.4 exploratory metric-fit reference")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


C4 = load_phase5c4()
C = 343.0
L_SCALE = 5.0
T_SCALE = 0.00877191949225
MAX_NFEV = 2500
RANK_TOL = 1e-8


@dataclass
class Problem:
    name: str
    q: np.ndarray
    c: float
    microphones_truth: np.ndarray
    sources_truth: np.ndarray
    emissions_truth: np.ndarray
    offsets_truth: np.ndarray
    noise_std_s: float = 0.0


def canonicalize(mics: np.ndarray, srcs: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    origin = mics[0].copy()
    ex = mics[1] - origin
    ex /= np.linalg.norm(ex)
    ey = mics[2] - origin
    ey -= np.dot(ey, ex) * ex
    ey /= np.linalg.norm(ey)
    ez = np.cross(ex, ey)
    basis = np.column_stack((ex, ey, ez))
    cm = (mics - origin) @ basis
    cs = (srcs - origin) @ basis
    cm[0] = 0.0
    cm[1, 1:] = 0.0
    cm[2, 2] = 0.0
    if cm[1, 0] <= 0 or cm[2, 1] <= 0:
        raise ValueError("cannot construct the selected gauge from this layout")
    return cm, cs


def seed11_problem(noise_std_s: float = 0.0, noise_seed: int = 116) -> Problem:
    rng = np.random.default_rng(11)
    room = ShoeboxRoom((8.0, 7.0, 5.0), C)
    m0 = rng.uniform((0.5, 0.5, 0.5), (7.5, 6.5, 4.5), (5, 3))
    s0 = rng.uniform((0.5, 0.5, 0.5), (7.5, 6.5, 4.5), (13, 3))
    e = np.r_[0.0, rng.normal(0, 0.0005, 12)]
    b = rng.normal(0, 0.0005, 5)
    data = generate_toa_observations(room, s0, m0, e, b, random_seed=11)
    q = np.asarray(data.measured_toas_s, dtype=float).copy()
    if noise_std_s:
        q += np.random.default_rng(noise_seed).normal(0, noise_std_s, q.shape)
    m, s = canonicalize(m0, s0)
    return Problem(f"seed11_noise_{noise_std_s:g}s", q, C, m, s, e, b, noise_std_s)


def larger_problem() -> Problem:
    rng = np.random.default_rng(5206)
    room = ShoeboxRoom((8.0, 7.0, 5.0), C)
    m0 = rng.uniform((0.5, 0.5, 0.5), (7.5, 6.5, 4.5), (8, 3))
    s0 = rng.uniform((0.5, 0.5, 0.5), (7.5, 6.5, 4.5), (20, 3))
    e = np.r_[0.0, rng.normal(0, 0.0005, 19)]
    b = rng.normal(0, 0.0005, 8)
    data = generate_toa_observations(room, s0, m0, e, b, random_seed=5206)
    m, s = canonicalize(m0, s0)
    return Problem("larger_M8_N20", np.asarray(data.measured_toas_s), C, m, s, e, b)


class DirectFit:
    """Gauge-fixed scaled direct-range least squares for a given M,N."""

    def __init__(self, q: np.ndarray, c: float, l_scale: float, t_scale: float):
        self.q, self.c = np.asarray(q, dtype=float), float(c)
        self.m, self.n = self.q.shape
        self.ls, self.ts = float(l_scale), float(t_scale)
        self.coord_count = 3 * self.m - 6 + 3 * self.n
        self.size = self.coord_count + self.m + self.n - 1
        self.clock_start = self.coord_count
        self.emission_start = self.clock_start + self.m

    def pack(self, mics: np.ndarray, srcs: np.ndarray, emissions: np.ndarray, offsets: np.ndarray) -> np.ndarray:
        m, n = self.m, self.n
        out = [np.log(mics[1, 0] / self.ls), mics[2, 0] / self.ls, np.log(mics[2, 1] / self.ls)]
        out.extend((mics[3:] / self.ls).ravel())
        out.extend((srcs / self.ls).ravel())
        out.extend((offsets / self.ts).ravel())
        out.extend((emissions[1:] / self.ts).ravel())
        if len(out) != self.size:
            raise RuntimeError(f"parameter count mismatch: {len(out)} != {self.size}")
        return np.asarray(out, dtype=float)

    def unpack(self, x: np.ndarray):
        m, n = self.m, self.n
        mic = np.zeros((m, 3))
        k = 0
        mic[1, 0] = self.ls * np.exp(x[k]); k += 1
        mic[2, 0] = self.ls * x[k]; k += 1
        mic[2, 1] = self.ls * np.exp(x[k]); k += 1
        mic[3:] = self.ls * x[k:k + 3 * (m - 3)].reshape(m - 3, 3); k += 3 * (m - 3)
        source_count = 3 * n
        src = self.ls * x[k:k + source_count].reshape(n, 3); k += source_count
        clocks = self.ts * x[k:k + m]; k += m
        emission = np.r_[0.0, self.ts * x[k:k + n - 1]]
        return mic, src, emission, clocks

    def residual_jac(self, x: np.ndarray):
        mic, src, emission, clocks = self.unpack(x)
        delta = src[None, :, :] - mic[:, None, :]
        dist = np.linalg.norm(delta, axis=2)
        if np.any(dist <= 1e-12) or not np.all(np.isfinite(dist)):
            raise FloatingPointError("coincident or invalid source/microphone positions")
        unit = delta / dist[:, :, None]
        residual = (self.q - emission[None, :] - dist / self.c - clocks[:, None]) / self.ts
        jac = np.zeros((self.m * self.n, self.size))
        row = 0
        for i in range(self.m):
            for j in range(self.n):
                dm = unit[i, j] * self.ls / (self.c * self.ts)
                ds = -dm
                if i == 1:
                    jac[row, 0] = dm[0] * mic[1, 0] / self.ls
                elif i == 2:
                    jac[row, 1] = dm[0]
                    jac[row, 2] = dm[1] * mic[2, 1] / self.ls
                elif i >= 3:
                    start = 3 + 3 * (i - 3)
                    jac[row, start:start + 3] = dm
                s0 = 3 * self.m - 6 + 3 * j
                jac[row, s0:s0 + 3] = ds
                jac[row, self.clock_start + i] = -1
                if j:
                    jac[row, self.emission_start + j - 1] = -1
                row += 1
        return residual.ravel(), jac

    def optimize(self, start: np.ndarray, max_nfev: int = MAX_NFEV) -> dict:
        begin = perf_counter()
        opt = least_squares(
            lambda x: self.residual_jac(x)[0], start,
            jac=lambda x: self.residual_jac(x)[1], method="trf", x_scale="jac",
            ftol=1e-13, xtol=1e-13, gtol=1e-13, max_nfev=max_nfev,
        )
        runtime = perf_counter() - begin
        mic, src, emission, clocks = self.unpack(opt.x)
        singular = np.linalg.svd(opt.jac, compute_uv=False)
        rank = int(np.sum(singular > singular[0] * RANK_TOL))
        raw_residual = opt.fun * self.ts
        return {
            "x": opt.x, "optimizer": opt, "microphones": mic, "sources": src,
            "emissions": emission, "offsets": clocks, "runtime_s": runtime,
            "residual_s": raw_residual, "singular_values": singular, "rank": rank,
            "condition": float(singular[0] / singular[-1]) if singular[-1] else float("inf"),
        }


def aligned_metrics(mic: np.ndarray, src: np.ndarray, problem: Problem):
    estimated = np.vstack((mic, src))
    truth = np.vstack((problem.microphones_truth, problem.sources_truth))
    em, tm = estimated.mean(0), truth.mean(0)
    u, _, vt = np.linalg.svd((estimated - em).T @ (truth - tm))
    rot = u @ vt  # O(3) intentionally permits the discrete reflection.
    fit = (estimated - em) @ rot + tm
    m = len(problem.microphones_truth)
    mic_rms = float(np.sqrt(np.mean(np.sum((fit[:m] - problem.microphones_truth) ** 2, axis=1))))
    src_rms = float(np.sqrt(np.mean(np.sum((fit[m:] - problem.sources_truth) ** 2, axis=1))))
    all_rms = float(np.sqrt(np.mean(np.sum((fit - truth) ** 2, axis=1))))
    return mic_rms, src_rms, all_rms


def timing_metrics(em: np.ndarray, off: np.ndarray, problem: Problem):
    de, db = em - problem.emissions_truth, off - problem.offsets_truth
    return {
        "emission_rmse_s": float(np.sqrt(np.mean(de**2))),
        "emission_max_abs_s": float(np.max(np.abs(de))),
        "clock_rmse_s": float(np.sqrt(np.mean(db**2))),
        "clock_max_abs_s": float(np.max(np.abs(db))),
    }


def score_state(mic, src, em, off, problem: Problem):
    dist = np.linalg.norm(src[None, :, :] - mic[:, None, :], axis=2)
    residual = problem.q - em[None, :] - dist / problem.c - off[:, None]
    return {
        "initial_tof_residual_norm_s": float(np.linalg.norm(residual)),
        "initial_tof_max_abs_residual_s": float(np.max(np.abs(residual))),
        "initial_min_corrected_tof_s": float(np.min(problem.q - em[None, :] - off[:, None])),
        "initial_position_valid": bool(np.all(np.isfinite(mic)) and np.all(np.isfinite(src)) and np.all(dist > 0)),
    }


def run_fit(problem: Problem, label: str, start: np.ndarray, model: DirectFit, max_nfev: int = MAX_NFEV):
    init_m, init_s, init_e, init_b = model.unpack(start)
    init_geo = aligned_metrics(init_m, init_s, problem)
    init_time = timing_metrics(init_e, init_b, problem)
    init_score = score_state(init_m, init_s, init_e, init_b, problem)
    fit = model.optimize(start, max_nfev)
    final_dist = np.linalg.norm(fit["sources"][None, :, :] - fit["microphones"][:, None, :], axis=2)
    final_corrected = problem.q - fit["emissions"][None, :] - fit["offsets"][:, None]
    fin_geo = aligned_metrics(fit["microphones"], fit["sources"], problem)
    fin_time = timing_metrics(fit["emissions"], fit["offsets"], problem)
    opt = fit["optimizer"]
    record = {
        "problem": problem.name, "initializer": label,
        "initial_coordinate_rmse_m": init_geo[2],
        "initial_microphone_rmse_m": init_geo[0], "initial_source_rmse_m": init_geo[1],
        **init_time, **init_score,
        "final_coordinate_rmse_m": fin_geo[2],
        "final_microphone_rmse_m": fin_geo[0], "final_source_rmse_m": fin_geo[1],
        "final_emission_rmse_s": fin_time["emission_rmse_s"],
        "final_emission_max_abs_s": fin_time["emission_max_abs_s"],
        "final_clock_rmse_s": fin_time["clock_rmse_s"],
        "final_clock_max_abs_s": fin_time["clock_max_abs_s"],
        "final_tof_residual_norm_s": float(np.linalg.norm(fit["residual_s"])),
        "final_tof_max_abs_residual_s": float(np.max(np.abs(fit["residual_s"]))),
        "final_min_corrected_tof_s": float(np.min(problem.q - fit["emissions"][None, :] - fit["offsets"][:, None])),
        "final_position_valid_finite_noncoincident": bool(np.all(np.isfinite(final_dist)) and np.all(final_dist > 0)),
        "final_corrected_tof_positive": bool(np.all(np.isfinite(final_corrected)) and np.all(final_corrected > 0)),
        "jacobian_rank": fit["rank"], "jacobian_condition": fit["condition"],
        "jacobian_singular_values": fit["singular_values"].tolist(),
        "optimizer_status": int(opt.status), "optimizer_success": bool(opt.success),
        "optimizer_message": str(opt.message), "nfev": int(opt.nfev), "njev": int(opt.njev or 0),
        "runtime_s": fit["runtime_s"],
        "initial_parameters_scaled": start.tolist(), "final_parameters_scaled": fit["x"].tolist(),
    }
    print(label, problem.name, "init_pos_rmse", f"{init_geo[2]:.5g}", "init_emit_rmse", f"{init_time['emission_rmse_s']:.5g}", "init_clock_rmse", f"{init_time['clock_rmse_s']:.5g}", "init_TOA_norm", f"{init_score['initial_tof_residual_norm_s']:.5g}", "final_pos_rmse", f"{fin_geo[2]:.5g}", "final_emit_rmse", f"{fin_time['emission_rmse_s']:.5g}", "final_clock_rmse", f"{fin_time['clock_rmse_s']:.5g}", "final_TOA_norm", f"{record['final_tof_residual_norm_s']:.5g}", "max_TOA", f"{record['final_tof_max_abs_residual_s']:.5g}", "rank", fit["rank"], "cond", f"{fit['condition']:.5g}", "status", opt.status, opt.success, "nfev", opt.nfev, "runtime", f"{fit['runtime_s']:.3f}")
    return record


def characteristic_scales(q: np.ndarray, c: float):
    distance_scale = float(c * np.median(np.abs(q)))
    t = C4.dd_squared(q)
    time_scale = max(float(np.sqrt(np.median(np.abs(t)))), float(1.4826 * np.median(np.abs(q - np.median(q)))))
    if not np.isfinite(distance_scale) or distance_scale <= 0 or not np.isfinite(time_scale) or time_scale <= 0:
        raise ValueError("TOA-derived initialization scale is invalid")
    return distance_scale, time_scale


def algebraic_metric_start(q: np.ndarray, c: float, p: np.ndarray, name: str, *, seed: int = 5):
    m, n = q.shape
    cls = C4.TimingCandidate
    cand = cls(name, np.asarray(p, dtype=float), "measured-TOA-derived");
    result = C4.metric_fit(cand, q, c, seed=seed)
    if "rejected" in result:
        return None, {"rejected": result["rejected"], "minimum_corrected_tof_s": float(np.min(result["corrected_tof"]))}
    branches = [x for x in result.get("branches", []) if np.isfinite(x.get("objective", np.inf))]
    if not branches:
        return None, {"rejected": result.get("rejected", "no finite Crocco coordinate fit")}
    best = min(branches, key=lambda x: x["objective"])
    if not np.all(np.isfinite(best["microphones"])) or not np.all(np.isfinite(best["sources"])):
        return None, {"rejected": "Crocco fit returned nonfinite coordinates"}
    try:
        mic, src = canonicalize(best["microphones"], best["sources"])
    except (ValueError, np.linalg.LinAlgError) as exc:
        return None, {"rejected": f"coordinate gauge failed: {exc}"}
    offsets = p[:m]
    emissions = np.r_[0.0, p[m:]]
    return (mic, src, emissions, offsets), {
        "crocco_objective_normalized": float(best["objective"]),
        "crocco_residual_norm_m2": float(best.get("residual_norm_m2", np.nan)),
        "crocco_max_abs_residual_m2": float(best.get("max_abs_metric_residual_m2", np.nan)),
        "crocco_condition": float(best.get("condition", np.inf)),
        "crocco_optimizer_success": bool(best.get("success", False)),
        "crocco_delta_branch": int(best["delta"]),
        "rank3_residual": float(result.get("rank_residual", np.nan)),
        "minimum_corrected_tof_s": float(np.min(result["corrected_tof"])),
    }


def direct_rank_starts(q: np.ndarray, t_scale: float):
    return C4.direct_rank_candidates(q, t_scale)


def gaubitch_timing_start(q: np.ndarray, t_scale: float, outer_iterations: int = 100):
    """Approved alternating rank-3 correction, used only as an initializer."""
    m, n = q.shape
    t = C4.dd_squared(q)
    p = np.zeros(m + n - 1)
    inner_evals = 0
    rank_history = []
    for _ in range(outer_iterations):
        a, g = C4.timing_matrices(q, p)
        x = t + a + g
        u, singular, vt = np.linalg.svd(x, full_matrices=False)
        x3 = (u[:, :3] * singular[:3]) @ vt[:3]
        target = x3 - t
        rank_history.append(float(np.linalg.norm(x - x3) / max(np.linalg.norm(x), 1e-30)))

        def residual(upar):
            aa, gg = C4.timing_matrices(q, upar * t_scale)
            return ((aa + gg - target) / t_scale**2).ravel()

        def jacobian(upar):
            pp = upar * t_scale
            b = pp[:m]
            e = np.r_[0.0, pp[m:]]
            jac = np.zeros(((m - 1) * (n - 1), m + n - 1))
            row = 0
            for i in range(1, m):
                for j in range(1, n):
                    jac[row, i] = (-2 * (q[i, j] - q[i, 0]) + 2 * e[j]) / t_scale
                    jac[row, 0] = (2 * (q[0, j] - q[0, 0]) - 2 * e[j]) / t_scale
                    jac[row, m + j - 1] = (-2 * (q[i, j] - q[0, j]) + 2 * (b[i] - b[0])) / t_scale
                    row += 1
            return jac

        opt = least_squares(residual, p / t_scale, jac=jacobian, method="trf", x_scale="jac", max_nfev=100, ftol=1e-10, xtol=1e-10, gtol=1e-10)
        inner_evals += int(opt.nfev)
        p = opt.x * t_scale
    return p, {"outer_iterations": outer_iterations, "inner_nfev": inner_evals, "rank_residual_history": rank_history}


def random_blind_start(problem: Problem, seed: int, scale: float):
    m, n = problem.q.shape
    rng = np.random.default_rng(seed)
    mic = np.zeros((m, 3)); src = np.zeros((n, 3))
    mic[1] = (rng.uniform(0.3, 1.0) * scale, 0, 0)
    mic[2] = (rng.uniform(-0.5, 0.5) * scale, rng.uniform(0.3, 1.0) * scale, 0)
    mic[3:] = rng.uniform(-scale, scale, (m - 3, 3))
    src[:] = rng.uniform(-scale, scale, (n, 3))
    return mic, src, np.zeros(n), np.zeros(m)


def structured_starts(problem: Problem, model: DirectFit, scales=(0.5, 1.0, 2.0)):
    """Deterministic space-filling starts at TOA-derived metric scales."""
    m, n = problem.q.shape
    length, _ = characteristic_scales(problem.q, problem.c)
    engine = qmc.Halton(d=3 * (m - 2 + n), scramble=False)
    engine.fast_forward(1)  # skip the all-zero point, which coincides with m1
    points = engine.random(len(scales))
    starts = []
    for k, factor in enumerate(scales):
        cloud = (2 * points[k].reshape(-1, 3) - 1) * (factor * length)
        mic = np.zeros((m, 3)); src = np.zeros((n, 3))
        mic[1] = (factor * length, 0, 0)
        mic[2] = (cloud[0, 0], factor * length, 0)
        mic[3:] = cloud[1:1 + (m - 3)]
        src[:] = cloud[1 + (m - 3):]
        starts.append((f"structured_halton_scale_{factor:g}", model.pack(mic, src, np.zeros(n), np.zeros(m))))
    return starts


def execute_problem(problem: Problem, include_crocco: bool, include_gaubitch: bool, large_budget: int | None = None):
    m, n = problem.q.shape
    length, ts = characteristic_scales(problem.q, problem.c)
    model = DirectFit(problem.q, problem.c, length, ts)
    records, init_details = [], {}

    # All candidate initializer functions below receive q, c and dimensions only.
    init_candidates: list[tuple[str, tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray], dict]] = []
    if include_crocco:
        pzero = np.zeros(m + n - 1)
        zero_state, detail = algebraic_metric_start(problem.q, problem.c, pzero, "zero_timing")
        init_details["crocco_zero_timing"] = detail
        if zero_state is not None:
            init_candidates.append(("cross_distance_Crocco_zero_timing", zero_state, detail))
        for cseed in (2, 11):
            state, d = algebraic_metric_start(problem.q, problem.c, pzero, f"zero_timing_seed_{cseed}", seed=cseed)
            init_details[f"crocco_zero_timing_seed_{cseed}"] = d
            if state is not None:
                init_candidates.append((f"cross_distance_Crocco_zero_timing_seed_{cseed}", state, d))

        tscale = max(float(np.sqrt(np.median(np.abs(C4.dd_squared(problem.q))))), float(1.4826 * np.median(np.abs(problem.q - np.median(problem.q)))))
        rank_cands = direct_rank_starts(problem.q, tscale)
        for cand in rank_cands:
            state, d = algebraic_metric_start(problem.q, problem.c, cand.parameters_s, f"direct_rank_{cand.name}")
            init_details[f"crocco_{cand.name}"] = d
            if state is not None:
                init_candidates.append((f"rank_timing_plus_Crocco_{cand.name}", state, d))

    if include_gaubitch:
        p, details = gaubitch_timing_start(problem.q, ts, outer_iterations=100)
        init_details["gaubitch_alternating_100"] = details
        state, d = algebraic_metric_start(problem.q, problem.c, p, "gaubitch_100")
        init_details["crocco_gaubitch_100"] = d
        if state is not None:
            init_candidates.append(("Gaubitch100_plus_Crocco", state, d))

    budget = large_budget or MAX_NFEV
    for label, state, details in init_candidates:
        start = model.pack(*state)
        init_details[f"initial_state_{label}"] = details
        records.append(run_fit(problem, label, start, model, budget))
        if label == "cross_distance_Crocco_zero_timing" and problem.name == "seed11_noise_0s":
            for magnitude, seed in ((0.1, 53061), (0.5, 53062)):
                perturbed = start.copy()
                jitter = np.random.default_rng(seed)
                perturbed[:model.coord_count] += jitter.normal(0, magnitude / length, model.coord_count)
                perturbed[model.coord_count:] += jitter.normal(0, magnitude * 1e-3 / ts, model.size - model.coord_count)
                records.append(run_fit(problem, f"Crocco_zero_timing_perturb_{magnitude:g}m_{magnitude:g}e-3s", perturbed, model, budget))

    # Same direct objective, blind random baseline with TOA-derived scale.
    for seed in (11, 29):
        state = random_blind_start(problem, seed, length)
        records.append(run_fit(problem, f"blind_random_seed_{seed}", model.pack(*state), model, budget))
    # Structured deterministic multistart uses only q-derived length scale, no room box.
    for label, start in structured_starts(problem, model):
        records.append(run_fit(problem, label, start, model, budget))

    return records, init_details


def main():
    results = {"model": "q_ij=e_j+distance(s_j,m_i)/c+b_i", "known_initializer_inputs": ["measured TOA matrix", "sound speed", "TOA matrix shape (M,N)"], "seed": 11, "settings": {"length_scale": "c*median(abs(q))", "time_scale": "approved timing design robust scale", "direct_optimizer": "SciPy least_squares TRF with analytic Jacobian, x_scale=jac", "tolerances": [1e-13, 1e-13, 1e-13], "max_nfev": MAX_NFEV, "jacobian_rank_relative_threshold": RANK_TOL}, "problems": {}}
    main_problem = seed11_problem()
    main_runs, init_meta = execute_problem(main_problem, include_crocco=True, include_gaubitch=True)
    # Oracle remains a separately labeled positive control and is never an initializer.
    m0 = DirectFit(main_problem.q, main_problem.c, characteristic_scales(main_problem.q, main_problem.c)[0], characteristic_scales(main_problem.q, main_problem.c)[1])
    oracle = m0.pack(main_problem.microphones_truth, main_problem.sources_truth, main_problem.emissions_truth, main_problem.offsets_truth)
    oracle_record = run_fit(main_problem, "oracle_positive_control", oracle, m0)
    results["problems"][main_problem.name] = {"evaluation_budget": MAX_NFEV, "noise_std_s": 0.0, "initializer_metadata": init_meta, "runs": main_runs + [oracle_record]}

    noisy = seed11_problem(noise_std_s=20e-6, noise_seed=116)
    noisy_runs, noisy_meta = execute_problem(noisy, include_crocco=True, include_gaubitch=False, large_budget=500)
    noisy_model = DirectFit(noisy.q, noisy.c, characteristic_scales(noisy.q, noisy.c)[0], characteristic_scales(noisy.q, noisy.c)[1])
    noisy_oracle = noisy_model.pack(noisy.microphones_truth, noisy.sources_truth, noisy.emissions_truth, noisy.offsets_truth)
    noisy_runs.append(run_fit(noisy, "oracle_positive_control_noisy", noisy_oracle, noisy_model, 500))
    results["problems"][noisy.name] = {"evaluation_budget": 500, "noise_std_s": noisy.noise_std_s, "noise_seed": 116, "initializer_metadata": noisy_meta, "runs": noisy_runs}

    large = larger_problem()
    large_runs, large_meta = execute_problem(large, include_crocco=False, include_gaubitch=False, large_budget=300)
    large_model = DirectFit(large.q, large.c, characteristic_scales(large.q, large.c)[0], characteristic_scales(large.q, large.c)[1])
    large_oracle = large_model.pack(large.microphones_truth, large.sources_truth, large.emissions_truth, large.offsets_truth)
    large_runs.append(run_fit(large, "oracle_positive_control_large", large_oracle, large_model, 300))
    results["problems"][large.name] = {"evaluation_budget": 300, "noise_std_s": 0.0, "geometry_seed": 5206, "initializer_metadata": large_meta, "runs": large_runs}

    path = Path(__file__).with_name("phase5c6_results.json")
    path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print("results_json", path)


if __name__ == "__main__":
    main()
