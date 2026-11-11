"""Phase 5C.7: independent room, reflection, and observation studies.

Uses archived Phase 5C.6 direct-fit endpoint vectors for the seed-11 baseline.
All new configurations and fits are exploratory; no production code is added.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from time import perf_counter

import numpy as np
from scipy.spatial import ConvexHull

from batsight.datasets.toa import generate_toa_observations
from batsight.simulation.shoebox import ShoeboxRoom, image_sources


HERE = Path(__file__).resolve().parent
ARCHIVE = HERE / "phase5c6_results.json"


def load_phase56():
    path = HERE / "phase5c6_blind_initialization.py"
    spec = importlib.util.spec_from_file_location("batsight_phase5c6_exploratory", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load Phase 5C.6 model definitions")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


P56 = load_phase56()
C = 343.0
RANK_TOL = 1e-8


def raw_seed11():
    rng = np.random.default_rng(11)
    room = ShoeboxRoom((8.0, 7.0, 5.0), C)
    mics = rng.uniform((0.5, 0.5, 0.5), (7.5, 6.5, 4.5), (5, 3))
    sources = rng.uniform((0.5, 0.5, 0.5), (7.5, 6.5, 4.5), (13, 3))
    emissions = np.r_[0.0, rng.normal(0, 0.0005, 12)]
    offsets = rng.normal(0, 0.0005, 5)
    return room, mics, sources, emissions, offsets


def archive_endpoints():
    result = json.loads(ARCHIVE.read_text(encoding="utf-8"))
    runs = result["problems"]["seed11_noise_0s"]["runs"]
    wanted = {
        "generating": "oracle_positive_control",
        "competing_gaubitch": "Gaubitch100_plus_Crocco",
    }
    found = {}
    for key, label in wanted.items():
        row = next(item for item in runs if item["initializer"] == label)
        found[key] = {
            "parameters_scaled": np.asarray(row["final_parameters_scaled"], dtype=np.float64),
            "archived_record": row,
        }
    return result, found


def endpoint_summary(model, x, problem, *, name):
    residual_scaled, jac = model.residual_jac(x)
    mic, src, emission, offsets = model.unpack(x)
    residual = residual_scaled * model.ts
    singular = np.linalg.svd(jac, compute_uv=False)
    rank = int(np.count_nonzero(singular > singular[0] * RANK_TOL))
    geo = P56.aligned_metrics(mic, src, problem)
    timing = P56.timing_metrics(emission, offsets, problem)
    return {
        "name": name,
        "parameters_scaled": np.asarray(x).tolist(),
        "microphones_gauge_m": mic.tolist(),
        "sources_gauge_m": src.tolist(),
        "emissions_s": emission.tolist(),
        "clock_offsets_s": offsets.tolist(),
        "coordinate_rmse_m": geo[2],
        "microphone_rmse_m": geo[0],
        "source_rmse_m": geo[1],
        **timing,
        "direct_residual_norm_s": float(np.linalg.norm(residual)),
        "direct_max_abs_residual_s": float(np.max(np.abs(residual))),
        "minimum_corrected_tof_s": float(np.min(problem.q - emission[None, :] - offsets[:, None])),
        "jacobian_rank": rank,
        "jacobian_condition": float(singular[0] / singular[-1]),
        "jacobian_singular_values": singular.tolist(),
    }


def room_transform_from_true_mics(raw_mics: np.ndarray):
    origin = raw_mics[0].copy()
    ex = raw_mics[1] - origin
    ex /= np.linalg.norm(ex)
    ey = raw_mics[2] - origin
    ey -= np.dot(ey, ex) * ex
    ey /= np.linalg.norm(ey)
    ez = np.cross(ex, ey)
    return origin, np.column_stack((ex, ey, ez))


def candidate_room_bounds(endpoint, origin, basis, room: ShoeboxRoom):
    m = np.asarray(endpoint["microphones_gauge_m"])
    s = np.asarray(endpoint["sources_gauge_m"])
    raw = np.vstack((m, s)) @ basis.T + origin
    dims = np.asarray(room.dimensions_m)
    inside = np.all((raw > 0.0) & (raw < dims), axis=1)
    margin = np.minimum(raw, dims - raw)
    return {
        "all_points_strictly_inside_true_simulator_shoebox": bool(np.all(inside)),
        "outside_point_count": int(np.count_nonzero(~inside)),
        "minimum_wall_margin_m": float(np.min(margin)),
        "raw_coordinate_min_m": raw.min(axis=0).tolist(),
        "raw_coordinate_max_m": raw.max(axis=0).tolist(),
    }


def hull_room_report(points: np.ndarray):
    """Construct an explicitly data-derived expanded convex polytope."""
    center = np.mean(points, axis=0)
    scale = max(float(np.ptp(points, axis=0).max()), 1.0)
    expanded = center + (1.0 + 1e-6) * (points - center)
    hull = ConvexHull(expanded)
    signed = points @ hull.equations[:, :3].T + hull.equations[:, 3]
    return {
        "construction": "expanded convex hull of the candidate point set(s); no observed wall data",
        "facet_count_data_derived": int(len(hull.equations)),
        "volume_m3": float(hull.volume),
        "maximum_halfspace_value_m": float(np.max(signed)),
        "minimum_interior_slack_m": float(-np.max(signed)),
        "expansion_fraction": 1e-6,
        "scale_m": scale,
        "all_strictly_interior": bool(np.max(signed) < 0),
    }


def reflection_observations(room, mics, sources, emissions, offsets):
    """Use existing image_sources to make six unlabeled first-order TOAs per pair."""
    m_count, n_count = len(mics), len(sources)
    sets = np.empty((m_count, n_count, 6), dtype=np.float64)
    for j, source in enumerate(sources):
        images = image_sources(room, source, max_reflection_order=1)[1:]
        if len(images) != 6:
            raise RuntimeError("the simulator's first-order shoebox model did not produce six wall paths")
        for i, microphone in enumerate(mics):
            tof = [np.linalg.norm(np.asarray(image.position_m) - microphone) / room.speed_of_sound_m_s for image in images]
            # Echo arrivals are grouped by source event and microphone but sorted;
            # this deliberately withholds the simulator wall identifiers.
            sets[i, j] = np.sort(emissions[j] + offsets[i] + np.asarray(tof))
    return sets


def predict_endpoint_echoes(endpoint, origin, basis, room):
    mic_g = np.asarray(endpoint["microphones_gauge_m"])
    src_g = np.asarray(endpoint["sources_gauge_m"])
    mic_raw = mic_g @ basis.T + origin
    src_raw = src_g @ basis.T + origin
    points = np.vstack((mic_raw, src_raw))
    dims = np.asarray(room.dimensions_m)
    if not np.all((points > 0) & (points < dims)):
        return None, {"feasible": False, "reason": "candidate points are outside supplied simulator room"}
    echo = reflection_observations(
        room, mic_raw, src_raw,
        np.asarray(endpoint["emissions_s"]),
        np.asarray(endpoint["clock_offsets_s"]),
    )
    return echo, {"feasible": True}


def make_problem(name, room, raw_mics, raw_sources, emissions, offsets):
    data = generate_toa_observations(room, raw_sources, raw_mics, emissions, offsets, random_seed=701)
    mic_g, src_g = P56.canonicalize(raw_mics, raw_sources)
    return P56.Problem(name, np.asarray(data.measured_toas_s), room.speed_of_sound_m_s, mic_g, src_g, emissions, offsets)


def direct_fit_runs(problem, seeds=(17, 29), max_nfev=400):
    length, time = P56.characteristic_scales(problem.q, problem.c)
    model = P56.DirectFit(problem.q, problem.c, length, time)
    outputs = []
    # Known positions enter only the separately labeled positive control/scoring.
    truth = model.pack(problem.microphones_truth, problem.sources_truth, problem.emissions_truth, problem.offsets_truth)
    for label, start in [("oracle_control", truth)]:
        outputs.append(fit_record(problem, model, label, start, max_nfev))
    for seed in seeds:
        state = P56.random_blind_start(problem, seed, length)
        outputs.append(fit_record(problem, model, f"blind_random_{seed}", model.pack(*state), max_nfev))
    return outputs


def fit_record(problem, model, label, start, max_nfev):
    m0, s0, e0, b0 = model.unpack(start)
    init_geo = P56.aligned_metrics(m0, s0, problem)
    init_time = P56.timing_metrics(e0, b0, problem)
    init_r = model.residual_jac(start)[0] * model.ts
    fit = model.optimize(start, max_nfev)
    out = endpoint_summary(model, fit["x"], problem, name=label)
    out.update({
        "initial_coordinate_rmse_m": init_geo[2],
        "initial_microphone_rmse_m": init_geo[0],
        "initial_source_rmse_m": init_geo[1],
        "initial_emission_rmse_s": init_time["emission_rmse_s"],
        "initial_clock_rmse_s": init_time["clock_rmse_s"],
        "initial_direct_residual_norm_s": float(np.linalg.norm(init_r)),
        "optimizer_status": int(fit["optimizer"].status),
        "optimizer_success": bool(fit["optimizer"].success),
        "optimizer_message": str(fit["optimizer"].message),
        "nfev": int(fit["optimizer"].nfev),
        "njev": int(fit["optimizer"].njev or 0),
        "runtime_s": fit["runtime_s"],
        "evaluation_budget": max_nfev,
        "initial_parameters_scaled": np.asarray(start).tolist(),
    })
    print(problem.name, label, "init_xyz", f"{init_geo[2]:.4g}", "final_xyz", f"{out['coordinate_rmse_m']:.4g}", "res", f"{out['direct_residual_norm_s']:.4g}", "rank/cond", out["jacobian_rank"], f"{out['jacobian_condition']:.3g}", "status", out["optimizer_status"], out["optimizer_success"], "nfev", out["nfev"], "s", f"{out['runtime_s']:.3f}")
    return out


def count_and_placement_study(room, raw_mics, raw_sources, emissions, offsets):
    rng_m = np.random.default_rng(731)
    rng_s = np.random.default_rng(732)
    m_more = rng_m.uniform((0.4, 0.4, 0.4), (7.6, 6.6, 4.6), (3, 3))
    s_more = rng_s.uniform((0.4, 0.4, 0.4), (7.6, 6.6, 4.6), (7, 3))
    cases = {}
    # Count-only changes preserve all original devices/events as prefixes.
    cases["baseline_M5_N13"] = (raw_mics, raw_sources, emissions, offsets)
    cases["more_sources_M5_N20"] = (raw_mics, np.vstack((raw_sources, s_more)), np.r_[emissions, np.random.default_rng(733).normal(0, .0005, 7)], offsets)
    cases["more_microphones_M8_N13"] = (np.vstack((raw_mics, m_more)), raw_sources, emissions, np.r_[offsets, np.random.default_rng(734).normal(0, .0005, 3)])
    cases["more_both_M8_N20"] = (np.vstack((raw_mics, m_more)), np.vstack((raw_sources, s_more)), np.r_[emissions, np.random.default_rng(733).normal(0, .0005, 7)], np.r_[offsets, np.random.default_rng(734).normal(0, .0005, 3)])
    # Placement changes at fixed counts: centered shrink and expansion preserve timing.
    center = np.asarray(room.dimensions_m) / 2
    cases["clustered_M5_N13"] = (center + .35 * (raw_mics - center), center + .35 * (raw_sources - center), emissions, offsets)
    cases["spread_M5_N13"] = (center + 1.1 * (raw_mics - center), center + 1.1 * (raw_sources - center), emissions, offsets)

    results = {}
    for name, (mics, srcs, e, b) in cases.items():
        problem = make_problem(name, room, mics, srcs, e, b)
        length, time = P56.characteristic_scales(problem.q, problem.c)
        model = P56.DirectFit(problem.q, problem.c, length, time)
        truth = model.pack(problem.microphones_truth, problem.sources_truth, problem.emissions_truth, problem.offsets_truth)
        truth_res, truth_jac = model.residual_jac(truth)
        svals = np.linalg.svd(truth_jac, compute_uv=False)
        rank = int(np.sum(svals > svals[0] * RANK_TOL))
        runs = [] if name == "baseline_M5_N13" else direct_fit_runs(problem, max_nfev=300)
        results[name] = {
            "microphones": len(mics), "sources": len(srcs),
            "observation_count": int(len(mics) * len(srcs)),
            "unknown_count_after_gauge": int(model.size),
            "redundancy_count": int(len(mics) * len(srcs) - model.size),
            "all_positions_strictly_inside_generated_room": bool(np.all((np.vstack((mics, srcs)) > 0) & (np.vstack((mics, srcs)) < np.asarray(room.dimensions_m)))),
            "truth_residual_norm_s": float(np.linalg.norm(truth_res) * time),
            "truth_jacobian_rank": rank,
            "truth_jacobian_condition": float(svals[0] / svals[-1]),
            "truth_jacobian_singular_values": svals.tolist(),
            "baseline_endpoint_reference": "archived Phase 5C.6 seed-11 endpoints; no baseline endpoint was regenerated" if name == "baseline_M5_N13" else None,
            "runs": runs,
        }
    return results


def main():
    archived, saved = archive_endpoints()
    room, raw_mics, raw_sources, emissions, offsets = raw_seed11()
    baseline = P56.seed11_problem()
    length, time = P56.characteristic_scales(baseline.q, C)
    model = P56.DirectFit(baseline.q, C, length, time)
    endpoints = {
        key: endpoint_summary(model, saved[key]["parameters_scaled"], baseline, name=key)
        for key in saved
    }

    # Constraint A: an unconstrained convex polyhedral room is non-discriminatory.
    all_points = np.vstack([
        np.asarray(endpoints[k]["microphones_gauge_m"] + endpoints[k]["sources_gauge_m"])
        for k in ("generating", "competing_gaubitch")
    ])
    union_hull = hull_room_report(all_points)
    individual_hulls = {
        key: hull_room_report(np.vstack((endpoints[key]["microphones_gauge_m"], endpoints[key]["sources_gauge_m"])))
        for key in endpoints
    }
    origin, basis = room_transform_from_true_mics(raw_mics)
    true_room_check = {key: candidate_room_bounds(endpoints[key], origin, basis, room) for key in endpoints}

    # Constraint B: controlled first-order echo sets. The simulator generates the
    # six paths per source/mic pair; output arrival values are sorted to withhold
    # wall identifiers. Candidate evaluation under fixed simulator walls is marked
    # conditional because wall geometry is not among the acoustic observations.
    observed_echoes = reflection_observations(room, raw_mics, raw_sources, emissions, offsets)
    true_endpoint = endpoints["generating"]
    true_echo_predictions, true_echo_feasibility = predict_endpoint_echoes(true_endpoint, origin, basis, room)
    true_echo_diff = true_echo_predictions - observed_echoes if true_echo_predictions is not None else np.full_like(observed_echoes, np.nan)
    true_echo_rmse = float(np.sqrt(np.mean(true_echo_diff**2)))
    true_echo_max = float(np.max(np.abs(true_echo_diff)))
    competing_echo_predictions, competing_echo_feasibility = predict_endpoint_echoes(endpoints["competing_gaubitch"], origin, basis, room)
    true_echo_count = int(observed_echoes.size)
    reflection = {
        "simulator": "existing shoebox image_sources(max_reflection_order=1)",
        "echo_sets_shape_microphone_source_unlabeled_path": list(observed_echoes.shape),
        "echo_arrival_count": true_echo_count,
        "associations": "unknown wall identity; per-(microphone,source) echo TOAs are sorted, giving minimum squared one-dimensional assignment without emitting wall labels",
        "assumptions": ["all six first-order paths are detected per microphone/source pair", "direct/source-event and microphone grouping is known", "no noise", "fixed shoebox planes are available only for this conditional simulator check"],
        "generating_endpoint_reflection_residual_norm_s": true_echo_rmse,
        "generating_endpoint_reflection_max_abs_residual_s": true_echo_max,
        "generating_endpoint_room_feasibility": true_echo_feasibility,
        "competing_endpoint_reflection_residual_norm_s": None if competing_echo_predictions is None else float(np.linalg.norm(competing_echo_predictions - observed_echoes)),
        "competing_endpoint_reflection_max_abs_residual_s": None if competing_echo_predictions is None else float(np.max(np.abs(competing_echo_predictions - observed_echoes))),
        "competing_endpoint_room_feasibility": competing_echo_feasibility,
        "competing_endpoint_status": "not physically evaluable under the same supplied shoebox: the archived competing coordinates place points outside that room; an unknown room would require estimating wall planes, outside this phase",
        "direct_plus_reflection_fit_status": "not run as a blind unknown-room fit: predicting images requires wall planes; fixing the true room would mix reflection evidence with the room-geometry constraint",
        "independent_information_conclusion": "first-order echoes are additional measurements, but their wall-plane model is a shared geometric nuisance; a fair unknown-room fit requires wall/plane estimation and association handling, explicitly deferred",
        "echo_tof_sets_s": observed_echoes.tolist(),
    }

    # Constraint C: counts and placement are independently varied in new fixtures.
    count_placement = count_and_placement_study(room, raw_mics, raw_sources, emissions, offsets)

    results = {
        "phase": "5C.7",
        "baseline_source": str(ARCHIVE.name),
        "archived_endpoint_vectors_used_verbatim": True,
        "direct_objective_and_gauge": "Phase 5C.6 direct Euclidean TOA objective and m1-origin/m2-positive-x/m3-positive-y/e1-zero gauge",
        "no_production_changes": True,
        "baseline": {
            "archived_record_metadata": {k: saved[k]["archived_record"] for k in saved},
            "length_scale_m": length, "time_scale_s": time,
            "endpoints": endpoints,
        },
        "convex_room_geometry": {
            "unknown_room_constraint": "all generating and competing microphones/sources are tested for strict containment in one data-derived expanded convex hull; the hull is constructed from the endpoint positions themselves, so this is a feasibility demonstration, not independent evidence",
            "common_expanded_hull": union_hull,
            "individual_expanded_hulls": individual_hulls,
            "oracle_only_actual_simulator_shoebox_check": true_room_check,
            "inference": "with no known dimensions, wall observations, or face-count prior, both finite configurations fit inside a common convex polyhedron; convexity alone does not disambiguate",
        },
        "first_order_reflections": reflection,
        "additional_observations_and_placement": count_placement,
        "settings": {"jacobian_relative_rank_threshold": RANK_TOL, "extra_fixture_random_seeds": {"new_microphones": 731, "new_sources": 732, "new_emissions": 733, "new_clock_offsets": 734}, "blind_fit_max_nfev": 300},
    }
    path = HERE / "phase5c7_results.json"
    path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print("archived endpoint residuals", [(k, endpoints[k]["direct_residual_norm_s"], endpoints[k]["coordinate_rmse_m"], endpoints[k]["jacobian_rank"], endpoints[k]["jacobian_condition"]) for k in endpoints])
    print("room hull common", union_hull)
    print("true shoebox checks", true_room_check)
    print("reflection echoes", observed_echoes.shape, "true residual", true_echo_rmse, "alt status", reflection["competing_endpoint_status"])
    print("results_json", path)


if __name__ == "__main__":
    main()
