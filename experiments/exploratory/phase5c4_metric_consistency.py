"""Exploratory Phase 5C.4 metric-consistency experiment.

This diagnostic is intentionally outside ``src/batsight``. It reproduces the
seed-11 synthetic TOA fixture, rank-only timing candidates, and the approved
general Crocco coordinate objective. It is not a production localization API.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

import numpy as np
from scipy.optimize import minimize, root
from scipy.spatial.transform import Rotation

from batsight.datasets.toa import generate_toa_observations
from batsight.simulation.shoebox import ShoeboxRoom


@dataclass
class TimingCandidate:
    name: str
    parameters_s: np.ndarray
    origin: str
    optimizer_status: str = "not applicable"


def make_fixture():
    rng = np.random.default_rng(11)
    room = ShoeboxRoom((8.0, 7.0, 5.0), 343.0)
    microphones = rng.uniform((0.5, 0.5, 0.5), (7.5, 6.5, 4.5), (5, 3))
    sources = rng.uniform((0.5, 0.5, 0.5), (7.5, 6.5, 4.5), (13, 3))
    emission = np.r_[0.0, rng.normal(0.0, 0.0005, 12)]
    offsets = rng.normal(0.0, 0.0005, 5)
    data = generate_toa_observations(
        room, sources, microphones, emission, offsets, random_seed=11
    )
    q = np.asarray(data.measured_toas_s, dtype=np.float64)
    truth = np.r_[offsets + emission[0], emission[1:] - emission[0]]
    return room, microphones, sources, emission, offsets, q, truth


def timing_matrices(q: np.ndarray, p: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    m, n = q.shape
    offsets = p[:m]
    emission = np.r_[0.0, p[m:]]
    linear = np.empty((m - 1, n - 1), dtype=np.float64)
    bilinear = np.empty_like(linear)
    for i in range(1, m):
        for j in range(1, n):
            linear[i - 1, j - 1] = (
                -2.0 * (q[i, j] - q[i, 0]) * offsets[i]
                + 2.0 * (q[0, j] - q[0, 0]) * offsets[0]
                - 2.0 * (q[i, j] - q[0, j]) * emission[j]
            )
            bilinear[i - 1, j - 1] = 2.0 * (offsets[i] - offsets[0]) * emission[j]
    return linear, bilinear


def dd_squared(values: np.ndarray) -> np.ndarray:
    return (
        values[1:, 1:] ** 2
        - values[0, 1:][None, :] ** 2
        - values[1:, 0][:, None] ** 2
        + values[0, 0] ** 2
    )


def rank_alternatives(q: np.ndarray, truth: np.ndarray, t_scale: float) -> list[np.ndarray]:
    m, n = q.shape
    t = dd_squared(q)

    def corrected(u: np.ndarray) -> np.ndarray:
        a, gamma = timing_matrices(q, u * t_scale)
        return t + a + gamma

    def discarded(u: np.ndarray) -> np.ndarray:
        x = corrected(u)
        left, singular, right = np.linalg.svd(x, full_matrices=False)
        x3 = (left[:, :3] * singular[:3]) @ right[:3]
        return ((x - x3) / t_scale**2).ravel()

    u0 = truth / t_scale
    j = np.column_stack(
        [
            (discarded(u0 + np.eye(m + n - 1)[k] * 1e-4)
             - discarded(u0 - np.eye(m + n - 1)[k] * 1e-4)) / (2e-4)
            for k in range(m + n - 1)
        ]
    )
    _, _, vh = np.linalg.svd(j, full_matrices=True)
    observed = vh[:9].T
    null = vh[9:].T

    x0 = corrected(u0)
    best = (np.inf, None, None)
    for rows in combinations(range(m - 1), 3):
        for cols in combinations(range(n - 1), 3):
            block = x0[np.ix_(rows, cols)]
            sv = np.linalg.svd(block, compute_uv=False)
            cond = sv[0] / sv[-1] if sv[-1] else np.inf
            if cond < best[0]:
                best = (cond, rows, cols)
    _, rows, cols = best

    def schur(u: np.ndarray) -> np.ndarray:
        x = corrected(u)
        rest_rows = [i for i in range(m - 1) if i not in rows]
        rest_cols = [j for j in range(n - 1) if j not in cols]
        block = x[np.ix_(rows, cols)]
        top = x[np.ix_(rows, rest_cols)]
        left = x[np.ix_(rest_rows, cols)]
        lower = x[np.ix_(rest_rows, rest_cols)]
        return (lower - left @ np.linalg.solve(block, top)).ravel() / t_scale**2

    alternatives = []
    for amplitude in (0.1, 0.5, 1.0):
        direction = null[:, 0]
        solve = root(
            lambda v: schur(u0 + amplitude * direction + observed @ v),
            np.zeros(9),
            method="hybr",
            options={"xtol": 1e-10, "maxfev": 1000},
        )
        if not solve.success and np.max(np.abs(schur(u0 + amplitude * direction + observed @ solve.x))) > 1e-10:
            raise RuntimeError(f"rank-only continuation failed at amplitude {amplitude}")
        alternatives.append((u0 + amplitude * direction + observed @ solve.x) * t_scale)
    return alternatives


def direct_rank_candidates(q: np.ndarray, t_scale: float) -> list[TimingCandidate]:
    m, n = q.shape
    t = dd_squared(q)

    def corrected(u: np.ndarray) -> np.ndarray:
        a, gamma = timing_matrices(q, u * t_scale)
        return t + a + gamma

    output = []
    for seed in (0, 2, 3):
        start = np.zeros(m + n - 1) if seed == 0 else np.random.default_rng(seed).standard_normal(m + n - 1)

        def objective(u: np.ndarray) -> float:
            singular = np.linalg.svd(corrected(u), compute_uv=False)
            return float(np.dot(singular[3:], singular[3:]) / t_scale**4)

        result = minimize(
            objective,
            start,
            method="L-BFGS-B",
            jac="3-point",
            options={
                "maxfun": 15046,
                "maxiter": 10000,
                "ftol": 1e-12,
                "gtol": 1e-8,
                "finite_diff_rel_step": 1e-5,
                "maxls": 30,
            },
        )
        output.append(
            TimingCandidate(
                f"direct_seed_{seed}",
                result.x * t_scale,
                "direct-rank optimizer",
                f"success={result.success}; status={result.status}; message={result.message}; nfev={result.nfev}",
            )
        )
    return output


def traceless_basis() -> tuple[np.ndarray, ...]:
    root2 = np.sqrt(2.0)
    root6 = np.sqrt(6.0)
    return (
        np.diag((1.0, -1.0, 0.0)) / root2,
        np.diag((1.0, 1.0, -2.0)) / root6,
        np.array(((0.0, 1.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 0.0))) / root2,
        np.array(((0.0, 0.0, 1.0), (0.0, 0.0, 0.0), (1.0, 0.0, 0.0))) / root2,
        np.array(((0.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0))) / root2,
    )


def exp_symmetric(matrix: np.ndarray) -> np.ndarray:
    eigval, eigvec = np.linalg.eigh(matrix)
    if np.max(np.abs(eigval)) > 700.0:
        raise FloatingPointError("symmetric exponential would overflow")
    return (eigvec * np.exp(eigval)) @ eigvec.T


def coordinate_residual(
    z: np.ndarray,
    delta: int,
    u3: np.ndarray,
    singular3: np.ndarray,
    vt3: np.ndarray,
    distances_squared: np.ndarray,
    length_scale: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    ell = z[0]
    omega = z[1:4]
    h_coeff = z[4:9]
    alpha = z[9] * length_scale
    h = sum((coef * basis for coef, basis in zip(h_coeff, traceless_basis())), np.zeros((3, 3)))
    if abs(ell) > 100.0:
        raise FloatingPointError("isotropic log-scale is outside the finite evaluation range")
    exp_h = exp_symmetric(h)
    reflection = np.diag((1.0, 1.0, float(delta)))
    rotation = Rotation.from_rotvec(omega).as_matrix()
    factor = length_scale * np.exp(ell) * reflection @ rotation @ exp_h
    condition = float(np.linalg.cond(exp_h))
    rbar = u3 @ factor
    sigma_vt = singular3[:, None] * vt3
    sbar_t = -0.5 * np.linalg.solve(factor, sigma_vt)
    sbar = sbar_t.T
    microphones = np.vstack((np.zeros((1, 3)), rbar))
    sources = np.vstack((np.array((alpha, 0.0, 0.0)), alpha * np.array((1.0, 0.0, 0.0)) + sbar))
    residual = []
    for i in range(1, microphones.shape[0]):
        for j in range(1, sources.shape[0]):
            residual.append(
                np.dot(microphones[i], microphones[i])
                - 2.0 * np.dot(microphones[i], sources[j])
                - (distances_squared[i, j] - distances_squared[0, j])
            )
    return np.asarray(residual) / length_scale**2, microphones, sources, condition


def metric_fit(
    candidate: TimingCandidate,
    q: np.ndarray,
    speed: float,
    *,
    ground_truth_microphones: np.ndarray | None = None,
    ground_truth_sources: np.ndarray | None = None,
    seed: int = 5,
    finite_diff_step: float = 1e-6,
    oracle_only: bool = False,
):
    m, n = q.shape
    p = candidate.parameters_s
    offsets = p[:m]
    emission = np.r_[0.0, p[m:]]
    corrected_tof = q - offsets[:, None] - emission[None, :]
    if not np.all(np.isfinite(corrected_tof)) or np.min(corrected_tof) <= 0:
        return {"candidate": candidate, "corrected_tof": corrected_tof, "rejected": "nonpositive corrected TOF"}

    distances = corrected_tof * speed
    d2 = distances**2
    d0 = dd_squared(distances)
    u, singular, vt = np.linalg.svd(d0, full_matrices=False)
    u3, singular3, vt3 = u[:, :3], singular[:3], vt[:3]
    length_scale = float(np.sqrt(np.median(np.abs(d0))))
    if not np.isfinite(length_scale) or length_scale <= 0:
        return {"candidate": candidate, "corrected_tof": corrected_tof, "rejected": "invalid coordinate scale"}

    # Rank projection is not a replacement for metric constraints. These are
    # nonlinear least-squares searches over both determinant branches.
    rng = np.random.default_rng(seed)
    branch_results = []

    # Oracle-derived starts are used only as a positive-control check. They are
    # never used for rank-only alternative candidates or as a proposed engine
    # initialization.
    oracle_start_by_delta = {}
    if candidate.name == "generating" and ground_truth_microphones is not None and ground_truth_sources is not None:
        microphones_gt = ground_truth_microphones
        sources_gt = ground_truth_sources
        anchor = sources_gt[0] - microphones_gt[0]
        ex = anchor / np.linalg.norm(anchor)
        ey = None
        for point in microphones_gt[1:]:
            perpendicular = point - microphones_gt[0] - np.dot(point - microphones_gt[0], ex) * ex
            if np.linalg.norm(perpendicular) > 1e-8:
                ey = perpendicular / np.linalg.norm(perpendicular)
                break
        if ey is None:
            raise RuntimeError("oracle gauge frame is degenerate")
        ez = np.cross(ex, ey)
        basis = np.column_stack((ex, ey, ez))
        mic_canonical = (microphones_gt - microphones_gt[0]) @ basis
        src_canonical = (sources_gt - microphones_gt[0]) @ basis
        rbar_true = mic_canonical[1:]
        sbar_true = src_canonical[1:] - src_canonical[0]
        c_true = u3.T @ rbar_true
        for branch in (-1, 1):
            c_branch = c_true.copy()
            if np.sign(np.linalg.det(c_branch)) != branch:
                c_branch = c_branch @ np.diag((1.0, 1.0, -1.0))
            left, singular_c, right = np.linalg.svd(c_branch)
            orthogonal = left @ right
            reflection = np.diag((1.0, 1.0, float(branch)))
            rotation = reflection @ orthogonal
            polar = right.T @ np.diag(singular_c) @ right
            isotropic = float(np.exp(np.mean(np.log(singular_c))))
            h = right.T @ np.diag(np.log(singular_c / isotropic)) @ right
            h_coeff = np.array([np.sum(h * base) for base in traceless_basis()])
            rotvec = Rotation.from_matrix(rotation).as_rotvec()
            alpha = float(src_canonical[0, 0])
            oracle_start_by_delta[branch] = np.r_[np.log(isotropic / length_scale), rotvec, h_coeff, alpha / length_scale]

    for delta in (-1, 1):
        starts = []
        if delta in oracle_start_by_delta:
            starts.append(oracle_start_by_delta[delta])
        for alpha in (0.0, 5.0, -5.0):
            starts.append(np.r_[0.0, np.zeros(3), np.zeros(5), alpha])
        starts.append(np.r_[rng.normal(0.0, 0.4), rng.uniform(-0.6, 0.6, 3), rng.normal(0.0, 0.2, 5), rng.uniform(-5.0, 5.0)])
        if oracle_only:
            starts = [oracle_start_by_delta[delta]]

        for start_index, start in enumerate(starts):
            failures = []

            def objective(z: np.ndarray) -> float:
                try:
                    with np.errstate(over="raise", invalid="raise", divide="raise"):
                        residual, _, _, condition = coordinate_residual(
                            z, delta, u3, singular3, vt3, d2, length_scale
                        )
                        if not np.all(np.isfinite(residual)) or not np.isfinite(condition):
                            raise FloatingPointError("non-finite coordinate residual or condition")
                        value = float(np.dot(residual, residual))
                        return value if np.isfinite(value) else 1e50
                except (FloatingPointError, np.linalg.LinAlgError, OverflowError) as exc:
                    failures.append(str(exc))
                    return 1e50

            def condition_margin(z: np.ndarray) -> float:
                try:
                    h = sum((coef * basis for coef, basis in zip(z[4:9], traceless_basis())), np.zeros((3, 3)))
                    eigval = np.linalg.eigvalsh(h)
                    return float(np.log(1e8) - (eigval[-1] - eigval[0]))
                except (FloatingPointError, np.linalg.LinAlgError):
                    return -1e6

            bounds = [(None, None), (-np.pi, np.pi), (-np.pi, np.pi), (-np.pi, np.pi)] + [(None, None)] * 6
            result = minimize(
                objective,
                start,
                method="SLSQP",
                bounds=bounds,
                constraints=({"type": "ineq", "fun": condition_margin},),
                options={"maxiter": 2000, "ftol": 1e-12, "eps": finite_diff_step, "disp": False},
            )
            try:
                res, microphones, sources, condition = coordinate_residual(
                    result.x, delta, u3, singular3, vt3, d2, length_scale
                )
                objective_value = float(np.dot(res, res))
                residual_norm_m2 = float(np.linalg.norm(res) * length_scale**2)
                determinant_sign = float(np.sign(np.linalg.det(
                    length_scale * np.exp(result.x[0]) * np.diag((1.0, 1.0, float(delta)))
                    @ Rotation.from_rotvec(result.x[1:4]).as_matrix()
                    @ exp_symmetric(sum((coef * basis for coef, basis in zip(result.x[4:9], traceless_basis())), np.zeros((3, 3))))
                )))
                branch_results.append(
                    {
                        "delta": delta,
                        "start_index": start_index,
                        "objective": objective_value,
                        "residual_norm_m2": residual_norm_m2,
                        "condition": condition,
                        "condition_feasible": bool(condition <= 1e8 * (1.0 + 1e-10)),
                        "determinant_sign": determinant_sign,
                        "success": bool(result.success),
                        "status": int(result.status),
                        "message": str(result.message),
                        "iterations": int(result.nit),
                        "failures": failures,
                        "microphones": microphones,
                        "sources": sources,
                        "max_abs_metric_residual_m2": float(np.max(np.abs(res)) * length_scale**2),
                    }
                )
            except (FloatingPointError, np.linalg.LinAlgError, OverflowError) as exc:
                branch_results.append(
                    {
                        "delta": delta,
                        "start_index": start_index,
                        "objective": np.inf,
                        "success": False,
                        "message": f"final factor evaluation failed: {exc}",
                        "failures": failures,
                    }
                )

    return {
        "candidate": candidate,
        "corrected_tof": corrected_tof,
        "distance_matrix_m": distances,
        "d0": d0,
        "singular_values": singular,
        "rank_residual": np.linalg.norm(singular[3:]) / np.linalg.norm(d0),
        "length_scale_m": length_scale,
        "branches": branch_results,
    }


def aligned_coordinate_errors(
    estimated_microphones: np.ndarray,
    estimated_sources: np.ndarray,
    true_microphones: np.ndarray,
    true_sources: np.ndarray,
) -> tuple[float, float, float]:
    estimated = np.vstack((estimated_microphones, estimated_sources))
    truth = np.vstack((true_microphones, true_sources))
    est_mean = np.mean(estimated, axis=0)
    truth_mean = np.mean(truth, axis=0)
    centered_est = estimated - est_mean
    centered_truth = truth - truth_mean
    left, _, right = np.linalg.svd(centered_est.T @ centered_truth)
    rotation = left @ right
    aligned = centered_est @ rotation + truth_mean
    mic_error = np.sqrt(np.mean(np.sum((aligned[: len(true_microphones)] - true_microphones) ** 2, axis=1)))
    src_error = np.sqrt(np.mean(np.sum((aligned[len(true_microphones) :] - true_sources) ** 2, axis=1)))
    combined = np.sqrt(np.mean(np.sum((aligned - truth) ** 2, axis=1)))
    return float(mic_error), float(src_error), float(combined)


def main() -> None:
    room, microphones, sources, emission, offsets, q, truth = make_fixture()
    t = dd_squared(q)
    t_scale = max(np.sqrt(np.median(np.abs(t))), 1.4826 * np.median(np.abs(q - np.median(q))))
    exact = rank_alternatives(q, truth, t_scale)
    direct = direct_rank_candidates(q, t_scale)
    candidates = [TimingCandidate("generating", truth, "known fixture truth")]
    candidates.extend(TimingCandidate(f"schur_alt_{i+1}", p, "Schur complement") for i, p in enumerate(exact))
    candidates.extend(direct)

    print(f"fixture: seed=11, M={len(microphones)}, N={len(sources)}, c={room.speed_of_sound_m_s}")
    print(f"t_scale_s={t_scale:.12g}")
    for candidate in candidates:
        result = metric_fit(
            candidate,
            q,
            room.speed_of_sound_m_s,
            ground_truth_microphones=microphones if candidate.name == "generating" else None,
            ground_truth_sources=sources if candidate.name == "generating" else None,
        )
        if "rejected" in result:
            print(candidate.name, candidate.origin, candidate.optimizer_status, "parameters_s", np.array2string(candidate.parameters_s, precision=12), "corrected_TOF_s", np.array2string(result["corrected_tof"], precision=9), "REJECT", result["rejected"])
            continue
        finite = [row for row in result["branches"] if np.isfinite(row["objective"])]
        print(
            candidate.name,
            candidate.origin,
            candidate.optimizer_status,
            "timing_RMSE_ms", f"{np.sqrt(np.mean((candidate.parameters_s - truth) ** 2)) * 1000.0:.9g}",
            "parameters_s", np.array2string(candidate.parameters_s, precision=12),
            "rank_residual", f"{result['rank_residual']:.6e}",
            "min_TOF_s", f"{np.min(result['corrected_tof']):.9g}",
            "corrected_TOF_s", np.array2string(result["corrected_tof"], precision=9),
            "D0_singular_values", np.array2string(result["singular_values"], precision=5),
        )
        for delta in (-1, 1):
            branch = [x for x in result["branches"] if x["delta"] == delta]
            best = min(branch, key=lambda item: item["objective"])
            failures = [
                (x["start_index"], x["message"], x.get("failures", []))
                for x in branch
                if not x["success"] or not x.get("condition_feasible", False)
            ]
            print(
                " branch", delta,
                "best_obj", f"{best['objective']:.6e}",
                "best_residual_norm_m2", f"{best.get('residual_norm_m2', np.inf):.6e}",
                "best_max_abs_g_m2", f"{best.get('max_abs_metric_residual_m2', np.inf):.6e}",
                "cond", f"{best.get('condition', np.inf):.6e}",
                "condition_ok", best.get("condition_feasible", False),
                "success", best["success"],
                "message", best["message"],
                "start_statuses", [(x["start_index"], x["success"], x["objective"]) for x in branch],
                "failure_diagnostics", failures,
            )
            if candidate.name == "generating" and best.get("success") and best.get("condition_feasible"):
                em, es, ec = aligned_coordinate_errors(
                    best["microphones"], best["sources"], microphones, sources
                )
                print("  aligned_errors_m", f"microphones={em:.6e}", f"sources={es:.6e}", f"combined={ec:.6e}")
                print("  recovered_microphones_m", np.array2string(best["microphones"], precision=9))
                print("  recovered_sources_m", np.array2string(best["sources"], precision=9))

        if candidate.name == "generating":
            sensitivity = metric_fit(
                candidate,
                q,
                room.speed_of_sound_m_s,
                ground_truth_microphones=microphones,
                ground_truth_sources=sources,
                finite_diff_step=1e-7,
                oracle_only=True,
            )
            print("generating_oracle_finite_difference_sensitivity eps=1e-7")
            for delta in (-1, 1):
                best = min(
                    (x for x in sensitivity["branches"] if x["delta"] == delta),
                    key=lambda item: item["objective"],
                )
                em, es, ec = aligned_coordinate_errors(
                    best["microphones"], best["sources"], microphones, sources
                )
                print(
                    " branch", delta,
                    "objective", f"{best['objective']:.6e}",
                    "residual_norm_m2", f"{best['residual_norm_m2']:.6e}",
                    "condition", f"{best['condition']:.6e}",
                    "coordinate_errors_m", f"{em:.6e}", f"{es:.6e}", f"{ec:.6e}",
                    "status", best["success"], best["message"],
                )


if __name__ == "__main__":
    main()
