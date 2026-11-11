"""Exploratory direct Euclidean TOA joint-fit study (Phase 5C.5).

No production APIs are added. The model is the original direct-path TOA
equation, optimized by scaled nonlinear least squares with an analytic Jacobian.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from time import perf_counter

import numpy as np
from scipy.optimize import least_squares

from batsight.datasets.toa import generate_toa_observations
from batsight.simulation.shoebox import ShoeboxRoom


M, N, C = 5, 13, 343.0
L_SCALE_M = 5.0
T_SCALE_S = 0.00877191949225
RANK_RELATIVE_TOLERANCE = 1e-8
MAX_NFEV = 2500
RUNS: list[dict] = []


@dataclass
class Fixture:
    name: str
    microphones: np.ndarray
    sources: np.ndarray
    emissions: np.ndarray
    offsets: np.ndarray
    q: np.ndarray


def canonicalize(mics: np.ndarray, srcs: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Place m1 at origin, m2 on +x, and m3 in xy with positive y."""
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
        raise ValueError("fixture cannot satisfy the chosen coordinate gauge")
    return cm, cs


def make_fixtures() -> tuple[Fixture, Fixture, Fixture]:
    rng = np.random.default_rng(11)
    room = ShoeboxRoom((8.0, 7.0, 5.0), C)
    raw_mics = rng.uniform((0.5, 0.5, 0.5), (7.5, 6.5, 4.5), (M, 3))
    raw_srcs = rng.uniform((0.5, 0.5, 0.5), (7.5, 6.5, 4.5), (N, 3))
    e = np.r_[0.0, rng.normal(0.0, 0.0005, N - 1)]
    b = rng.normal(0.0, 0.0005, M)
    d_mics, d_srcs = canonicalize(raw_mics, raw_srcs)

    def make(name: str, mics: np.ndarray, srcs: np.ndarray) -> Fixture:
        q = e[None, :] + np.linalg.norm(srcs[None, :, :] - mics[:, None, :], axis=2) / C + b[:, None]
        return Fixture(name, mics, srcs, e.copy(), b.copy(), q)

    # The main case is the exact seed-11 geometry and generated observations.
    original = generate_toa_observations(room, raw_srcs, raw_mics, e, b, random_seed=11)
    q_original = np.asarray(original.measured_toas_s, dtype=np.float64)
    # Canonical coordinates preserve distances; the generated q is retained verbatim.
    main = Fixture("nondegenerate_seed11", d_mics, d_srcs, e.copy(), b.copy(), q_original)

    planar_mics = d_mics.copy()
    planar_srcs = d_srcs.copy()
    planar_mics[:, 2] = 0.0
    planar_srcs[:, 2] = 0.0
    planar = make("planar", planar_mics, planar_srcs)

    # Flatten z by 1/100 while retaining nonzero spread: deliberately ill-conditioned,
    # but not exactly planar. All coordinates and TOAs are deterministic transforms.
    weak_mics = d_mics.copy()
    weak_srcs = d_srcs.copy()
    weak_mics[:, 2] *= 0.01
    weak_srcs[:, 2] *= 0.01
    weak_mics[0] = 0.0
    weak_mics[1, 1:] = 0.0
    weak_mics[2, 2] = 0.0
    weak = make("poorly_conditioned_nonplanar", weak_mics, weak_srcs)
    return main, planar, weak


def encode(mics: np.ndarray, srcs: np.ndarray, emissions: np.ndarray, offsets: np.ndarray) -> np.ndarray:
    """Encode 65 free parameters using positive log coordinates for gauge distances."""
    values: list[float] = [np.log(mics[1, 0] / L_SCALE_M)]
    values.extend((mics[2, 0:1] / L_SCALE_M).tolist())
    values.append(float(np.log(mics[2, 1] / L_SCALE_M)))
    values.extend((mics[3:] / L_SCALE_M).ravel().tolist())
    values.extend((srcs / L_SCALE_M).ravel().tolist())
    values.extend((offsets / T_SCALE_S).tolist())
    values.extend((emissions[1:] / T_SCALE_S).tolist())
    return np.asarray(values, dtype=np.float64)


def decode(x: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    mics = np.zeros((M, 3), dtype=np.float64)
    k = 0
    mics[1, 0] = L_SCALE_M * np.exp(x[k]); k += 1
    mics[2, 0] = L_SCALE_M * x[k]; k += 1
    mics[2, 1] = L_SCALE_M * np.exp(x[k]); k += 1
    mics[3:] = L_SCALE_M * x[k:k + (M - 3) * 3].reshape(M - 3, 3); k += (M - 3) * 3
    srcs = L_SCALE_M * x[k:k + N * 3].reshape(N, 3); k += N * 3
    offsets = T_SCALE_S * x[k:k + M]; k += M
    emissions = np.r_[0.0, T_SCALE_S * x[k:k + N - 1]]
    return mics, srcs, emissions, offsets


def residual_and_jacobian(x: np.ndarray, fixture: Fixture) -> tuple[np.ndarray, np.ndarray]:
    mics, srcs, emissions, offsets = decode(x)
    delta = srcs[None, :, :] - mics[:, None, :]
    distance = np.linalg.norm(delta, axis=2)
    if np.any(distance <= 1e-12) or not np.all(np.isfinite(distance)):
        raise FloatingPointError("coincident or nonfinite source/microphone distance")
    unit = delta / distance[:, :, None]
    residual = (fixture.q - emissions[None, :] - distance / C - offsets[:, None]) / T_SCALE_S

    jac = np.zeros((M * N, 65), dtype=np.float64)
    row = 0
    for i in range(M):
        for j in range(N):
            # Coordinate block is the derivative of -distance/c, scaled by L/t_scale.
            d_m = unit[i, j] * (L_SCALE_M / (C * T_SCALE_S))
            d_s = -d_m
            if i == 1:
                jac[row, 0] = d_m[0] * mics[1, 0] / L_SCALE_M
            elif i == 2:
                jac[row, 1] = d_m[0]
                jac[row, 2] = d_m[1] * mics[2, 1] / L_SCALE_M
            elif i >= 3:
                start = 3 + (i - 3) * 3
                jac[row, start:start + 3] = d_m
            source_start = 9 + j * 3
            jac[row, source_start:source_start + 3] = d_s
            offset_start = 9 + 3 * N
            jac[row, offset_start + i] = -1.0
            emission_start = offset_start + M
            if j > 0:
                jac[row, emission_start + j - 1] = -1.0
            row += 1
    return residual.ravel(), jac


def solve(fixture: Fixture, start: np.ndarray) -> dict:
    started = perf_counter()
    result = least_squares(
        lambda x: residual_and_jacobian(x, fixture)[0], start,
        jac=lambda x: residual_and_jacobian(x, fixture)[1],
        method="trf", x_scale="jac", ftol=1e-13, xtol=1e-13, gtol=1e-13,
        max_nfev=MAX_NFEV, verbose=0,
    )
    elapsed = perf_counter() - started
    mics, srcs, emissions, offsets = decode(result.x)
    r = result.fun * T_SCALE_S
    singular = np.linalg.svd(result.jac, compute_uv=False)
    rank = int(np.count_nonzero(singular > singular[0] * RANK_RELATIVE_TOLERANCE))
    return {
        "result": result, "elapsed": elapsed, "microphones": mics, "sources": srcs,
        "emissions": emissions, "offsets": offsets, "residual_s": r,
        "singular_values": singular, "rank": rank,
        "condition": float(singular[0] / singular[-1]) if singular[-1] > 0 else np.inf,
    }


def aligned_errors(fit: dict, fixture: Fixture) -> tuple[float, float, float]:
    # Kabsch with O(3), rather than SO(3), intentionally permits the discrete mirror.
    estimated = np.vstack((fit["microphones"], fit["sources"]))
    truth = np.vstack((fixture.microphones, fixture.sources))
    ec, tc = estimated.mean(axis=0), truth.mean(axis=0)
    u, _, vt = np.linalg.svd((estimated - ec).T @ (truth - tc))
    q = u @ vt
    aligned = (estimated - ec) @ q + tc
    me = np.sqrt(np.mean(np.sum((aligned[:M] - fixture.microphones) ** 2, axis=1)))
    se = np.sqrt(np.mean(np.sum((aligned[M:] - fixture.sources) ** 2, axis=1)))
    combined = np.sqrt(np.mean(np.sum((aligned - truth) ** 2, axis=1)))
    return float(me), float(se), float(combined)


def timing_errors(fit: dict, fixture: Fixture) -> tuple[float, float, float, float]:
    de = fit["emissions"] - fixture.emissions
    db = fit["offsets"] - fixture.offsets
    return (
        float(np.sqrt(np.mean(de**2))), float(np.max(np.abs(de))),
        float(np.sqrt(np.mean(db**2))), float(np.max(np.abs(db))),
    )


def describe(label: str, fixture: Fixture, start: np.ndarray) -> dict:
    out = solve(fixture, start)
    result = out["result"]
    geom = aligned_errors(out, fixture)
    te = timing_errors(out, fixture)
    corrected_propagation = fixture.q - out["emissions"][None, :] - out["offsets"][:, None]
    valid_tof = bool(np.all(np.isfinite(corrected_propagation)) and np.min(corrected_propagation) > 0)
    pairwise_distances = np.linalg.norm(out["sources"][None, :, :] - out["microphones"][:, None, :], axis=2)
    valid_positions = bool(
        np.all(np.isfinite(out["microphones"])) and np.all(np.isfinite(out["sources"]))
        and np.all(np.isfinite(pairwise_distances)) and np.all(pairwise_distances > 0)
    )
    print(
        label, "status", result.status, "success", result.success, "nfev", result.nfev,
        "njev", result.njev, "runtime_s", f"{out['elapsed']:.6g}",
        "residual_norm_s", f"{np.linalg.norm(out['residual_s']):.6e}",
        "max_abs_residual_s", f"{np.max(np.abs(out['residual_s'])):.6e}",
        "mic_RMSE_m", f"{geom[0]:.6e}", "src_RMSE_m", f"{geom[1]:.6e}",
        "combined_RMSE_m", f"{geom[2]:.6e}", "emission_RMSE_s", f"{te[0]:.6e}",
        "emission_max_s", f"{te[1]:.6e}", "clock_RMSE_s", f"{te[2]:.6e}",
        "clock_max_s", f"{te[3]:.6e}", "rank", f"{out['rank']}/65",
        "condition", f"{out['condition']:.6e}", "jac_singular_head3_tail3",
        np.array2string(np.r_[out["singular_values"][:3], out["singular_values"][-3:]], precision=5),
        "physical_positions_finite_noncoincident", valid_positions,
        "positive_corrected_TOF", valid_tof, "min_corrected_TOF_s", f"{np.min(corrected_propagation):.6e}",
        "message", result.message,
    )
    RUNS.append({
        "label": label,
        "geometry": fixture.name,
        "success": bool(result.success),
        "status": int(result.status),
        "message": str(result.message),
        "nfev": int(result.nfev),
        "njev": int(result.njev or 0),
        "runtime_s": out["elapsed"],
        "scaled_objective": float(result.cost),
        "residual_norm_s": float(np.linalg.norm(out["residual_s"])),
        "max_abs_residual_s": float(np.max(np.abs(out["residual_s"]))),
        "microphone_rmse_m": geom[0],
        "source_rmse_m": geom[1],
        "combined_coordinate_rmse_m": geom[2],
        "emission_rmse_s": te[0],
        "emission_max_abs_error_s": te[1],
        "clock_rmse_s": te[2],
        "clock_max_abs_error_s": te[3],
        "jacobian_rank": out["rank"],
        "jacobian_condition": out["condition"],
        "jacobian_singular_values": out["singular_values"].tolist(),
        "positive_corrected_tof": valid_tof,
        "valid_positions_finite_noncoincident": valid_positions,
        "minimum_corrected_tof_s": float(np.min(corrected_propagation)),
        "initial_parameters_scaled": np.asarray(start).tolist(),
        "final_parameters_scaled": np.asarray(result.x).tolist(),
    })
    return out


def truth_parameters(fixture: Fixture) -> np.ndarray:
    return encode(fixture.microphones, fixture.sources, fixture.emissions, fixture.offsets)


def blind_position_start(rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    m = np.zeros((M, 3)); s = np.zeros((N, 3))
    m[1] = (rng.uniform(1.0, 7.0), 0.0, 0.0)
    m[2] = (rng.uniform(-2.0, 2.0), rng.uniform(0.5, 5.0), 0.0)
    m[3:] = rng.uniform(-2.0, 8.0, (M - 3, 3))
    s[:] = rng.uniform(-2.0, 8.0, (N, 3))
    return m, s


def main() -> None:
    main_fixture, planar, weak = make_fixtures()
    p_truth = truth_parameters(main_fixture)
    print("equation q=e+distance/c+b; gauge m1=(0,0,0), m2=(+x,0,0), m3=(x,+y,0), e1=0")
    print("counts M=5 N=13 observations=65 unknowns=9 mic+39 source+5 offsets+12 emissions=65")
    print("scales", L_SCALE_M, "m and", T_SCALE_S, "s; objective 0.5*sum((r_ij/t_scale)^2)")
    print("main_fixture canonicalized from exact seed-11; q observations retained unchanged")

    # Oracle starts first, then deterministic perturbations in both coordinate/time units.
    truth = describe("oracle_exact", main_fixture, p_truth)
    rng = np.random.default_rng(5305)
    for magnitude in (0.01, 0.1, 0.5):
        trial = p_truth.copy()
        # Perturb physical coordinate variables in scaled coordinates and all timing vars.
        trial[:9 + 3 * N] += rng.normal(0.0, magnitude / L_SCALE_M, 9 + 3 * N)
        trial[9 + 3 * N:] += rng.normal(0.0, magnitude * 1e-3 / T_SCALE_S, M + N - 1)
        describe(f"oracle_perturb_{magnitude:g}", main_fixture, trial)

    # Blind starts: previous rank-only timings are initialized with independent blind
    # coordinates; additionally, zero timing and seeded random coordinates are used.
    alternatives = [
        np.array([8.416698158909e-05,-5.738707518515e-04,-2.384541737848e-04,-1.871446406539e-04,6.600078859312e-04,6.512713546160e-04,-7.129588455866e-04,3.662938044403e-04,1.636856800977e-04,-8.795980659098e-04,2.755709908512e-04,-2.529510740837e-04,7.883449014191e-05,-3.090685296906e-04,2.646192523606e-05,2.382688068677e-04,-5.174220146072e-04]),
        np.array([-6.493690211474e-04,-2.935383465500e-03,-2.450078153751e-03,9.307613554643e-05,1.092739680854e-03,1.107999456235e-03,-9.336971070048e-04,5.290662285725e-04,-2.530868180933e-04,-8.260753568466e-04,6.021566325035e-04,-6.296574286600e-04,-7.996513300262e-04,-6.195997927947e-04,1.428421852702e-04,4.065483128139e-04,-7.940533549208e-04]),
        np.array([-0.001292370749,-0.006312268329,-0.005635511239,0.000393834936,0.001536176646,0.00138365683,-0.00120584384,0.000631492271,-0.000558045136,-0.000708431023,0.000862022631,-0.000897748447,-0.001386527353,-0.000919862493,0.00023336582,0.000487228301,-0.001036387276]),
        np.array([-1.142049110180e-04,-2.828529989164e-05,2.677657408531e-04,-5.731949482860e-04,3.319918159435e-04,2.132226066973e-04,-3.179421181979e-04,5.339736782635e-04,1.582250339891e-04,-8.752018705691e-04,-5.043269331237e-05,-5.830862594659e-05,3.653138659429e-04,6.022159506726e-05,1.145539641217e-04,3.152184850824e-05,-2.760595003872e-04]),
        np.array([-0.004327196524,0.002503758532,0.00271157177,-0.021299608735,0.02206608443,0.004182133015,0.006908649776,0.00134423688,-0.003621938796,-0.005252028377,0.008968252736,0.000598418781,0.005098479613,0.002911985504,-0.006512277575,-0.00144292499,0.005944198051]),
        np.array([0.020904962034,-0.019542400525,-0.002755075341,-0.003728788784,-0.005328670179,-0.001894424847,-0.016028576704,-0.007769036699,0.002761220406,0.028583612656,-0.001125183948,-0.003424392952,-0.005395380212,-0.003511461011,-0.008946735654,-0.003738533216,0.001600334352]),
    ]
    labels = ["schur_exact_1", "schur_exact_2", "schur_exact_3", "direct_rank_zero", "direct_rank_seed2", "direct_rank_seed3"]
    blind_rng = np.random.default_rng(5306)
    zero_timing = np.zeros(M + N - 1)
    for i, timing in enumerate([*alternatives, zero_timing]):
        m, s = blind_position_start(blind_rng)
        initial = encode(m, s, np.r_[0.0, timing[M:]], timing[:M])
        describe(f"blind_{labels[i]}" if i < len(labels) else "blind_zero_timing", main_fixture, initial)
    for seed in (11, 29):
        brng = np.random.default_rng(seed)
        m, s = blind_position_start(brng)
        initial = encode(m, s, np.zeros(N), np.zeros(M))
        describe(f"blind_random_geometry_seed_{seed}", main_fixture, initial)

    # Geometry-conditioned studies: oracle and moderate deterministic local start.
    for fixture in (planar, weak):
        p = truth_parameters(fixture)
        describe(f"{fixture.name}_oracle", fixture, p)
        perturbed = p.copy()
        perturbed[:9 + 3 * N] += np.random.default_rng(5307).normal(0, 0.02 / L_SCALE_M, 9 + 3 * N)
        perturbed[9 + 3 * N:] += np.random.default_rng(5308).normal(0, 2e-5 / T_SCALE_S, M + N - 1)
        describe(f"{fixture.name}_perturb_0.02m_20us", fixture, perturbed)

    output_path = Path(__file__).with_name("phase5c5_results.json")
    output_path.write_text(json.dumps({
        "seed": 11,
        "model": "q_ij=e_j+||s_j-m_i||/c+b_i",
        "speed_of_sound_m_s": C,
        "length_scale_m": L_SCALE_M,
        "time_scale_s": T_SCALE_S,
        "rank_relative_tolerance": RANK_RELATIVE_TOLERANCE,
        "max_nfev": MAX_NFEV,
        "runs": RUNS,
    }, indent=2), encoding="utf-8")
    print("full_diagnostics_json", output_path)


if __name__ == "__main__":
    main()
