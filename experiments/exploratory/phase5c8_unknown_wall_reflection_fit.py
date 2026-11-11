"""Phase 5C.8: exploratory unlabeled first-order echo / unknown-wall fit.

The archived direct-TOA endpoints are fixed; only six shared wall planes are
fit to the synthetic unlabeled echo sets. This is not a production estimator.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from time import perf_counter

import numpy as np
from scipy.optimize import least_squares
from scipy.spatial import ConvexHull

from batsight.simulation.shoebox import ShoeboxRoom

HERE = Path(__file__).resolve().parent
ARCHIVE = HERE / "phase5c6_results.json"
OUT = HERE / "phase5c8_results.json"
C = 343.0
SEEDS = (7, 11, 23, 37, 41, 53)
MAX_NFEV = 400


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load exploratory reference {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


P56 = load_module(HERE / "phase5c6_blind_initialization.py", "batsight_phase5c8_p56")
P57 = load_module(HERE / "phase5c7_competing_solution_disambiguation.py", "batsight_phase5c8_p57")


def plane_parameters(x: np.ndarray, points: np.ndarray):
    """Map 18 vars to six unit normals and inward-oriented offsets.

    Each normal uses azimuth/elevation. Offset is support(parameter points)
    plus a positive exponential gap, so all endpoints are strictly inside.
    The map permits arbitrary six plane orientations; it does not pair walls.
    """
    angles = x[:12].reshape(6, 2)
    az, el = angles[:, 0], angles[:, 1]
    cos_el = np.cos(el)
    normals = np.column_stack((cos_el * np.cos(az), cos_el * np.sin(az), np.sin(el)))
    scale = max(float(np.ptp(points, axis=0).max()), 1.0)
    numerical_clearance = 1e-4 * scale  # BatSight numerical guard, not a paper parameter.
    gaps = numerical_clearance + np.exp(np.clip(x[12:], -30.0, 20.0))
    offsets = -np.max(points @ normals.T, axis=0) - gaps
    return normals, offsets, gaps


def predicted_echo_sets(mics, sources, emissions, clocks, normals, offsets):
    """Return six specular first-order image TOAs for each (mic, source)."""
    images = sources[:, None, :] - 2.0 * (
        np.einsum("jkd,kd->jk", sources[:, None, :] * normals[None, :, :], normals)
        + offsets[None, :]
    )[:, :, None] * normals[None, :, :]
    # images shape (N,6,3); evaluate every receiver, then sort only the
    # unlabeled TOA set for optimal squared-error assignment.
    distances = np.linalg.norm(images[None, :, :, :] - mics[:, None, None, :], axis=3)
    if np.any(distances <= 1e-12) or not np.all(np.isfinite(distances)):
        raise FloatingPointError("nonpositive/nonfinite image-source distance")
    arrivals = emissions[None, :, None] + clocks[:, None, None] + distances / C
    return np.sort(arrivals, axis=2)


def predicted_echoes_with_associations(mics, sources, emissions, clocks, normals, offsets):
    images = sources[:, None, :] - 2.0 * (
        np.einsum("jkd,kd->jk", sources[:, None, :] * normals[None, :, :], normals)
        + offsets[None, :]
    )[:, :, None] * normals[None, :, :]
    distances = np.linalg.norm(images[None, :, :, :] - mics[:, None, None, :], axis=3)
    arrivals = emissions[None, :, None] + clocks[:, None, None] + distances / C
    order = np.argsort(arrivals, axis=2)
    return np.take_along_axis(arrivals, order, axis=2), order


def make_observations():
    room, mics, sources, emissions, clocks = P57.raw_seed11()
    observed = P57.reflection_observations(room, mics, sources, emissions, clocks)
    mic_g, src_g = P56.canonicalize(mics, sources)
    return room, mics, sources, emissions, clocks, observed, mic_g, src_g


def endpoint_vectors():
    archive = json.loads(ARCHIVE.read_text(encoding="utf-8"))
    runs = archive["problems"]["seed11_noise_0s"]["runs"]
    mapping = {"generating": "oracle_positive_control", "competing": "Gaubitch100_plus_Crocco"}
    output = {}
    for label, init in mapping.items():
        row = next(r for r in runs if r["initializer"] == init)
        x = np.asarray(row["final_parameters_scaled"], dtype=np.float64)
        model = P56.DirectFit(
            np.asarray(P56.seed11_problem().q), C,
            *P56.characteristic_scales(P56.seed11_problem().q, C),
        )
        mic, src, emission, clocks = model.unpack(x)
        output[label] = {
            "archive_initializer": init,
            "parameters_scaled": x,
            "microphones": mic,
            "sources": src,
            "emissions": emission,
            "clocks": clocks,
            "archive_row": row,
        }
    return archive, output


def feasible_geometry(normals, offsets, points, gaps):
    signed = points @ normals.T + offsets[None, :]
    inside = bool(np.max(signed) < 0.0)
    try:
        hull = ConvexHull(normals)
        # ConvexHull equations are unit-normalized by Qhull. Origin is strictly
        # interior iff every face evaluates negative there.
        bounded_slacks = -hull.equations[:, 3]
        bounded = bool(np.min(bounded_slacks) > 1e-9)
        min_slack = float(np.min(bounded_slacks))
        facet_count = int(len(hull.simplices))
    except Exception:
        bounded, min_slack, facet_count = False, None, 0
    singular = np.linalg.svd(normals, compute_uv=False)
    normal_condition = float(singular[0] / singular[-1]) if singular[-1] > 0 else float("inf")
    scale = max(float(np.ptp(points, axis=0).max()), 1.0)
    plane_design = np.column_stack((normals, offsets / scale))
    plane_singular = np.linalg.svd(plane_design, compute_uv=False)
    plane_condition = float(plane_singular[0] / plane_singular[-1]) if plane_singular[-1] > 0 else float("inf")
    return {
        "all_points_strictly_inside": inside,
        "maximum_inside_halfspace_value_m": float(np.max(signed)),
        "minimum_endpoint_to_plane_clearance_m": float(-np.max(signed)),
        "bounded_polyhedron_from_positive_spanning_normals": bounded,
        "normal_hull_minimum_origin_slack": min_slack,
        "normal_hull_facets": facet_count,
        "normal_matrix_singular_values": singular.tolist(),
        "normal_matrix_condition": normal_condition,
        "scaled_plane_design_singular_values": plane_singular.tolist(),
        "scaled_plane_design_condition": plane_condition,
        "minimum_support_gap_m": float(np.min(gaps)),
        "maximum_support_gap_m": float(np.max(gaps)),
        "valid_enclosure": bool(inside and bounded),
    }


def reflection_face_validity(mics, sources, normals, offsets):
    """Check each image path's plane intersection lies on that finite face."""
    scale = max(float(np.ptp(np.vstack((mics, sources)), axis=0).max()), 1.0)
    tol = 1e-8 * scale
    source_signed = sources @ normals.T + offsets
    images = sources[:, None, :] - 2.0 * source_signed[:, :, None] * normals[None, :, :]
    image_signed = np.einsum("nkd,ld->nkl", images, normals) + offsets[None, None, :]
    mic_signed = mics @ normals.T + offsets
    denom = np.broadcast_to(image_signed[:, np.arange(6), np.arange(6)][None, :, :] - mic_signed[:, None, :], (len(mics), len(sources), 6))
    numerator = np.broadcast_to(-mic_signed[:, None, :], denom.shape)
    t = np.divide(numerator, denom, out=np.full(denom.shape, np.nan), where=denom > 0)
    bounce = mics[:, None, None, :] + t[:, :, :, None] * (images[None, :, :, :] - mics[:, None, None, :])
    bounce_signed = np.einsum("mnkd,ld->mnkl", bounce, normals) + offsets[None, None, None, :]
    other_mask = ~np.eye(6, dtype=bool)
    other_max = np.max(np.where(other_mask[None, None, :, :], bounce_signed, -np.inf), axis=3)
    valid = np.isfinite(t) & (t > 0) & (t < 1) & (other_max <= tol)
    counts = valid.sum(axis=(0, 1))
    invalid = np.argwhere(~valid)
    total = int(valid.size)
    return {
        "valid_first_order_bounce_count": int(np.sum(counts)),
        "expected_first_order_bounce_count": total,
        "valid_bounce_count_by_plane_index": counts.tolist(),
        "invalid_bounce_count": int(invalid.shape[0]),
        "all_bounces_on_finite_faces": bool(np.all(valid)),
        "tolerance_m": tol,
        "first_invalid_examples": invalid[:20].tolist(),
    }


def face_penetration_residuals(mics, sources, normals, offsets):
    """Hinge residuals for image rays whose bounce point misses its face."""
    source_signed = sources @ normals.T + offsets
    images = sources[:, None, :] - 2.0 * source_signed[:, :, None] * normals[None, :, :]
    image_signed = np.einsum("nkd,ld->nkl", images, normals) + offsets[None, None, :]
    mic_signed = mics @ normals.T + offsets
    denom = np.broadcast_to(image_signed[:, np.arange(6), np.arange(6)][None, :, :] - mic_signed[:, None, :], (len(mics), len(sources), 6))
    numerator = np.broadcast_to(-mic_signed[:, None, :], denom.shape)
    t = np.divide(numerator, denom, out=np.full(denom.shape, np.nan), where=denom > 0)
    bounce = mics[:, None, None, :] + t[:, :, :, None] * (images[None, :, :, :] - mics[:, None, None, :])
    bounce_signed = np.einsum("mnkd,ld->mnkl", bounce, normals) + offsets[None, None, None, :]
    other_mask = ~np.eye(6, dtype=bool)
    other_max = np.max(np.where(other_mask[None, None, :, :], bounce_signed, -np.inf), axis=3)
    return np.maximum(np.nan_to_num(other_max, nan=1.0, posinf=1.0), 0.0)


def initial_start(seed: int, points: np.ndarray):
    rng = np.random.default_rng(max(seed, 0))
    if seed == -1:
        # Candidate-coordinate PCA gives a deterministic data-derived frame,
        # not simulator room axes or wall coefficients.
        centered = points - points.mean(axis=0)
        _, _, vt = np.linalg.svd(centered, full_matrices=False)
        vectors = vt[:3]
        jitter_scale = 0.0
    else:
        vectors = rng.normal(size=(3, 3))
        vectors /= np.linalg.norm(vectors, axis=1)[:, None]
        jitter_scale = 0.13
    # Generic approximately antipodal directions provide bounded starts; the
    # fitted normals are otherwise unconstrained and need not remain paired.
    base = np.vstack((vectors, -vectors))
    jitter = rng.normal(scale=jitter_scale, size=base.shape)
    normals = base + jitter
    normals /= np.linalg.norm(normals, axis=1)[:, None]
    az = np.arctan2(normals[:, 1], normals[:, 0])
    el = np.arcsin(np.clip(normals[:, 2], -1, 1))
    scale = max(float(np.ptp(points, axis=0).max()), 1.0)
    minimum = 1e-4 * scale
    if seed == -1:
        gaps = np.full(6, 0.12 * scale)
    else:
        gaps = rng.uniform(0.05 * scale, 0.6 * scale, size=6)
    return np.r_[np.column_stack((az, el)).ravel(), np.log(np.maximum(gaps - minimum, 1e-8))]


def fit_one(endpoint, observed, seed):
    mic, src = endpoint["microphones"], endpoint["sources"]
    emission, clocks = endpoint["emissions"], endpoint["clocks"]
    points = np.vstack((mic, src))
    target = np.sort(observed, axis=2)
    calls = 0

    def residual(x):
        nonlocal calls
        calls += 1
        normals, offsets, _ = plane_parameters(x, points)
        prediction = predicted_echo_sets(mic, src, emission, clocks, normals, offsets)
        # The rearrangement inequality proves sorted-to-sorted pairing is the
        # minimum squared residual one-to-one assignment for scalar TOAs.
        echo_residual = ((prediction - target) * C).ravel()  # distance-equivalent scale
        # The hinge term steers image-ray intersections onto their finite
        # convex faces. Final feasibility is checked separately as a hard gate.
        face_residual = (10.0 * C * face_penetration_residuals(mic, src, normals, offsets)).ravel()
        return np.r_[echo_residual, face_residual]

    start = initial_start(seed, points)
    begin = perf_counter()
    opt = least_squares(
        residual, start, method="trf", x_scale="jac", max_nfev=MAX_NFEV,
        ftol=1e-11, xtol=1e-11, gtol=1e-11,
    )
    runtime = perf_counter() - begin
    normals, offsets, gaps = plane_parameters(opt.x, points)
    pred, order = predicted_echoes_with_associations(mic, src, emission, clocks, normals, offsets)
    error = pred - target
    # Plane ordering is exchangeable; report sorted TOA assignment diagnostics.
    sorted_gaps = np.diff(pred, axis=2)
    observed_gaps = np.diff(target, axis=2)
    min_gap = float(min(np.min(sorted_gaps), np.min(observed_gaps)))
    rank_counts = np.zeros((6, 6), dtype=int)
    for pair_order in order.reshape(-1, 6):
        for rank, plane_index in enumerate(pair_order):
            rank_counts[int(plane_index), rank] += 1
    feasibility = feasible_geometry(normals, offsets, points, gaps)
    face_validity = reflection_face_validity(mic, src, normals, offsets)
    return {
        "seed": seed,
        "reflection_residual_norm_s": float(np.linalg.norm(error)),
        "reflection_residual_norm_distance_equivalent_m": float(np.linalg.norm(error) * C),
        "reflection_max_abs_residual_s": float(np.max(np.abs(error))),
        "optimizer_status": int(opt.status),
        "optimizer_success": bool(opt.success),
        "optimizer_message": str(opt.message),
        "nfev": int(opt.nfev),
        "residual_function_calls": int(calls),
        "runtime_s": float(runtime),
        "objective_half_squared_distance_residual_m2": float(0.5 * np.dot(opt.fun, opt.fun)),
        "reflection_only_half_squared_distance_residual_m2": float(0.5 * np.sum((error * C) ** 2)),
        "face_penetration_penalty_weight": 10.0,
        "plane_feasibility": feasibility,
        "finite_face_reflection_validity": face_validity,
        "plane_normals_canonical_gauge": normals.tolist(),
        "plane_offsets_canonical_gauge_m": offsets.tolist(),
        "support_gaps_m": gaps.tolist(),
        "echo_association": {
            "method": "optimal sorted scalar assignment per known (microphone, source) group; no wall labels supplied",
            "minimum_adjacent_predicted_or_observed_TOA_gap_s": min_gap,
            "ties_or_near_ties_below_1e-10_s": bool(min_gap < 1e-10),
            "consistent_fixed_wall_rank_across_groups": False,
            "explanation": "Wall identity can change arrival rank across microphone/source pairs; assignments are recomputed independently per group.",
            "fitted_plane_index_by_arrival_rank_count_across_65_groups": rank_counts.tolist(),
        },
        "physical_paths_positive": bool(np.all(np.isfinite(pred)) and np.all(pred > 0)),
        "all_required_first_order_paths_physically_valid": bool(feasibility["valid_enclosure"] and face_validity["all_bounces_on_finite_faces"] and np.all(pred > 0)),
    }


def main():
    room, raw_mics, raw_sources, raw_e, raw_b, observed, mic_g, src_g = make_observations()
    archive, endpoints = endpoint_vectors()
    summaries = {}
    for name, endpoint in endpoints.items():
        runs = [fit_one(endpoint, observed, seed) for seed in (-1, *SEEDS)]
        summaries[name] = {
            "archive_initializer": endpoint["archive_initializer"],
            "endpoint_direct_TOA_archive_metrics": {
                key: endpoint["archive_row"].get(key)
                for key in ("final_tof_residual_norm_s", "final_tof_max_abs_residual_s", "final_coordinate_rmse_m", "final_emission_rmse_s", "final_clock_rmse_s", "final_min_corrected_tof_s", "jacobian_rank", "jacobian_condition", "optimizer_success", "nfev", "runtime_s")
            },
            "runs": runs,
        }
    result = {
        "phase": "5C.8 exploratory unknown-wall first-order reflection fit",
        "archive": "phase5c6_results.json; endpoint parameter vectors copied verbatim",
        "observations": {
            "generation_only_simulator": "existing shoebox image-source model, first order, seed-11 room/source/microphone fixture",
            "shape_microphone_source_echo": list(observed.shape),
            "echo_count": int(observed.size),
            "observed_echo_TOAs_s_sorted_within_each_group": observed.tolist(),
            "fixture_seed": 11,
            "room_dimensions_and_true_planes_withheld_from_inverse": True,
            "wall_labels_withheld": True,
            "six_faces_assumed_as_requested": True,
            "sound_speed_m_s": C,
            "no_noise_and_all_six_echoes_detected_per_pair": True,
            "grouping_by_microphone_and_source_event_known": True,
        },
        "inverse_model": {
            "plane_model": "six arbitrary shared planes n_k dot x + d_k = 0; unit normals, inside means n_k dot x+d_k<0",
            "plane_parameterization": "six azimuth/elevation unit normals; d_k=-max_x(n_k dot x)-(1e-4*L+exp(g_k)), with L the candidate point-cloud maximum coordinate span, ensuring a numerical strict-containment margin; 18 free parameters",
            "convexity": "bounded enclosure iff origin lies strictly inside convex hull of the six outward normals; validated post-fit via hull halfspaces and normal rank diagnostics",
            "objective": "sum over each (mic,source) group of squared sorted-TOA differences, residuals multiplied by c, plus a weight-10 hinge penalty on bounce intersections outside finite convex faces; final all-path face feasibility is a hard acceptance check",
            "association_justification": "For equal-cardinality scalar sets and squared error, the rearrangement inequality makes sorted-to-sorted assignment globally minimum over all permutations. This does not imply a fixed wall identity/order across groups.",
            "optimizer": "SciPy least_squares trust-region reflective, numerical finite-difference Jacobian, x_scale=jac, ftol=xtol=gtol=1e-11, max_nfev=400",
            "initialization": "candidate-point PCA frame plus six deterministic independently seeded generic directions formed from perturbed antipodal random vectors; PCA-derived or random positive support gaps; no true plane information; no paired-wall constraint after initialization",
            "positive_paths": "image-source distances and arrival times checked finite and positive after fitting",
            "direct_endpoints_fixed": True,
            "no_truth_plane_initialization_or_constraint": True,
        },
        "initialization_seeds": ["candidate_point_PCA", *SEEDS],
        "runs_by_endpoint": summaries,
        "historical_archive_vectors_included": {k: v["parameters_scaled"].tolist() for k, v in endpoints.items()},
        "source_truth_metadata_not_used_for_fit": {"microphone_count": len(raw_mics), "source_count": len(raw_sources), "speed_of_sound_m_s": room.speed_of_sound_m_s},
        "limitations": [
            "The synthetic observations are generated from a shoebox, while the inverse allows any bounded six-plane convex enclosure.",
            "A failed local optimizer run is not evidence of infeasibility.",
            "Finite multi-start success is not proof of global uniqueness.",
            "No wall reflectivity/amplitude data are used; this is echo-TOA-only.",
            "The endpoint coordinates/timing are fixed separately; this test asks whether each can explain the echoes with some shared room.",
        ],
    }
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    for name, info in summaries.items():
        print(name)
        for row in info["runs"]:
            feas = row["plane_feasibility"]
            print(
                f" seed={row['seed']} residual={row['reflection_residual_norm_s']:.4g}s "
                f"max={row['reflection_max_abs_residual_s']:.4g}s valid={feas['valid_enclosure']} "
                f"bounded={feas['bounded_polyhedron_from_positive_spanning_normals']} "
                f"status={row['optimizer_status']} success={row['optimizer_success']} "
                f"nfev={row['nfev']} time={row['runtime_s']:.2f}s"
            )
    print(f"results_json {OUT}")


if __name__ == "__main__":
    main()
