#!/usr/bin/env python3
"""
scripts/reconstruct_smard_0001.py

Extracts first-order reflections from SMARD Configuration 0001 using BatSight's
signals pipeline and runs BatSight's existing calibrated shoebox dimension estimator.
"""

import json
import math
import sys
from pathlib import Path

# Add workspace root and src to python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import numpy as np
from scipy.signal import peak_prominences

from batsight.datasets.calibrated import (
    CalibratedMicrophone,
    CalibratedMicrophoneArray,
    CalibratedShoeboxInputs,
    CalibratedSourceEvent,
    CalibratedTOAObservationSet,
    DirectPathTOAObservation,
    FirstOrderReflectionTOAObservation,
    TOAReading,
)
from batsight.reconstruction.shoebox_dimensions import estimate_shoebox_dimensions
from batsight.signals import AudioSignal, SamplingFrequency, matched_filter
from batsight.signals.recording_analysis import _parabolic_peak_offset
from scripts.inspect_smard_0001 import decode_flac_audio

RAW_DIR = Path("data/raw/smard/0001/0001_20140114-1323")
PROCESSED_DIR = Path("data/processed/smard/0001")
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

# Hardware loopback-to-acoustic offset validated in direct_toa_validation.json
LOOPBACK_OFFSET_S = -0.000353  # -0.353 ms

def main():
    print("=" * 85)
    print("SMARD 0001 — First-Order Reflection Extraction & Shoebox Reconstruction")
    print("=" * 85)

    # 1. Load existing metadata
    geo_file = PROCESSED_DIR / "geometry_metadata.json"
    with open(geo_file, "r", encoding="utf-8") as f:
        geo = json.load(f)

    c = float(geo["speed_of_sound_mps"])  # 344.172 m/s
    src_pos = tuple(geo["source"]["transformed_batsight_coordinates_x_y_z_m"])
    dims = geo["transformed_batsight_dimensions_m"]
    gt_Lx = float(dims["length_x"])  # 8.09 m
    gt_Ly = float(dims["width_y"])   # 7.34 m
    gt_Lz = float(dims["height_z"])  # 2.87 m
    sr = 48000.0
    fs = SamplingFrequency(sr)

    print(f"Ground Truth Room Dimensions (BatSight): Lx={gt_Lx:.3f} m, Ly={gt_Ly:.3f} m, Lz={gt_Lz:.3f} m")
    print(f"Source Position: {src_pos} m | Speed of Sound: {c:.3f} m/s")
    print(f"Calibrated Hardware Timing Offset: {LOOPBACK_OFFSET_S*1000:+.3f} ms (explicitly recorded in provenance)")

    # 2. Construct CalibratedShoeboxInputs
    mics_data = geo["microphones"]
    cal_mics = []
    for ch_str in sorted(mics_data.keys(), key=lambda x: int(x)):
        ch = int(ch_str)
        if ch in (8, 16):
            continue
        m = mics_data[ch_str]
        cal_mics.append(CalibratedMicrophone(
            microphone_id=f"mic_{ch:02d}",
            position_m=tuple(m["transformed_batsight_coordinates_x_y_z_m"])
        ))

    mic_array = CalibratedMicrophoneArray(
        microphones=tuple(cal_mics),
        sampling_frequency=fs,
        clocks_synchronized=True
    )
    source_event = CalibratedSourceEvent(
        event_id="event_01",
        source_id="OmniPower4296",
        position_m=src_pos,
        emission_time_s=0.0
    )
    inputs = CalibratedShoeboxInputs(
        microphone_array=mic_array,
        source_events=(source_event,),
        speed_of_sound_m_s=c
    )

    # 3. Load reference signal and pre-decode all active microphone FLAC files into memory
    print("\nLoading reference Ch 08 and pre-decoding active microphone audio...")
    ref_path = RAW_DIR / "exp_swept_sinus_10Hz_24kHz_ch8_OmniPower4296.flac"
    ref_data, sr_val, _, _ = decode_flac_audio(ref_path)
    ref_sig = AudioSignal(ref_data.astype(np.float64), fs)

    mic_signals = {}
    for ch_str in sorted(mics_data.keys(), key=lambda x: int(x)):
        ch = int(ch_str)
        if ch in (8, 16):
            continue
        m_info = mics_data[ch_str]
        flac_name = f"exp_swept_sinus_10Hz_24kHz_ch{ch}_{m_info['name']}.flac"
        m_data, _, _, _ = decode_flac_audio(RAW_DIR / flac_name)
        mic_sig = AudioSignal(m_data.astype(np.float64), fs)
        mic_signals[ch] = (mic_sig, m_info)

    # 4. First-Order Image Source geometry
    image_sources = {
        "x_min": (-src_pos[0], src_pos[1], src_pos[2]),
        "x_max": (2.0 * gt_Lx - src_pos[0], src_pos[1], src_pos[2]),
        "y_min": (src_pos[0], -src_pos[1], src_pos[2]),
        "y_max": (src_pos[0], 2.0 * gt_Ly - src_pos[1], src_pos[2]),
        "z_min": (src_pos[0], src_pos[1], -src_pos[2]),
        "z_max": (src_pos[0], src_pos[1], 2.0 * gt_Lz - src_pos[2]),
    }

    # 5. Extract first-order reflections across the 6 walls
    print("\nExtracting first-order reflections across 6 walls (tolerance ±0.5 ms)...")
    labeled_observations = []
    labeled_records = []
    wall_counts = {w: 0 for w in image_sources.keys()}
    wall_residuals = {w: [] for w in image_sources.keys()}

    for wall_id, img_pos in image_sources.items():
        for ch, (m_sig, m_info) in mic_signals.items():
            m_pos = m_info["transformed_batsight_coordinates_x_y_z_m"]
            dist_m = math.sqrt(sum((a - b)**2 for a, b in zip(img_pos, m_pos)))
            theo_toa_s = dist_m / c
            theo_toa_ms = theo_toa_s * 1000.0

            # Target position in raw correlation sequence
            raw_target_time = theo_toa_s + LOOPBACK_OFFSET_S
            tol_s = 0.0005  # ±0.5 ms tolerance window

            mf = matched_filter(m_sig, ref_sig, normalization="reference_energy")
            mask = (mf.lags_seconds >= raw_target_time - tol_s) & (mf.lags_seconds <= raw_target_time + tol_s)
            sub_indices = np.where(mask)[0]

            if len(sub_indices) > 0:
                sub_corr_abs = np.abs(mf.correlation[mask])
                best_idx = sub_indices[np.argmax(sub_corr_abs)]

                # Sub-sample peak refinement
                frac_offset = _parabolic_peak_offset(np.abs(mf.correlation), best_idx)
                meas_raw_lag = float(mf.lags_samples[best_idx]) + frac_offset
                meas_raw_toa_s = meas_raw_lag / sr

                # Apply calibrated timing offset to get true acoustic TOA
                cal_acoustic_toa_s = meas_raw_toa_s - LOOPBACK_OFFSET_S
                cal_acoustic_toa_ms = cal_acoustic_toa_s * 1000.0

                # Residual relative to ground truth theoretical TOA
                residual_ms = (cal_acoustic_toa_s - theo_toa_s) * 1000.0
                residual_cm = (cal_acoustic_toa_s - theo_toa_s) * c * 100.0

                # Peak amplitude and prominence
                corr_full = np.abs(mf.correlation)
                prominences, _, _ = peak_prominences(corr_full, [best_idx])
                prom = float(prominences[0]) if len(prominences) > 0 else float(corr_full[best_idx])
                peak_amp = float(mf.correlation[best_idx])

                # Noise scale
                noise_scale = float(1.4826 * np.median(np.abs(mf.correlation - np.median(mf.correlation))))
                pnr = float(abs(peak_amp) / max(noise_scale, 1e-12))

                wall_counts[wall_id] += 1
                wall_residuals[wall_id].append(residual_ms)

                obs = FirstOrderReflectionTOAObservation(
                    microphone_id=f"mic_{ch:02d}",
                    event_id="event_01",
                    wall_id=wall_id,
                    reading=TOAReading(
                        arrival_time_s=float(cal_acoustic_toa_s),
                        uncertainty_s=None,
                        status="observed"
                    ),
                    label_source="external_annotation"
                )
                labeled_observations.append(obs)

                labeled_records.append({
                    "channel": ch,
                    "microphone_id": f"mic_{ch:02d}",
                    "microphone_name": m_info["name"],
                    "wall_id": wall_id,
                    "theoretical_toa_ms": round(theo_toa_ms, 4),
                    "raw_measured_toa_ms": round(meas_raw_toa_s * 1000.0, 4),
                    "calibrated_acoustic_toa_ms": round(cal_acoustic_toa_ms, 4),
                    "timing_residual_ms": round(residual_ms, 4),
                    "distance_residual_cm": round(residual_cm, 3),
                    "matched_filter_amplitude": round(peak_amp, 5),
                    "prominence": round(prom, 5),
                    "peak_to_noise_ratio": round(pnr, 2)
                })

    print("\nFirst-Order Reflection Detections by Wall:")
    for w in ("x_min", "x_max", "y_min", "y_max", "z_min", "z_max"):
        res_arr = np.array(wall_residuals[w])
        print(f"  • {w:<6}: {wall_counts[w]}/22 reflections | Mean Residual: {np.mean(res_arr):+.3f} ms | Std: {np.std(res_arr):.3f} ms")

    # 6. Save labeled first-order reflections JSON
    labeled_out = {
        "dataset": "SMARD",
        "configuration": "0001",
        "reference_channel": 8,
        "calibrated_offset_s": LOOPBACK_OFFSET_S,
        "tolerance_window_s": 0.0005,
        "total_first_order_reflections": len(labeled_observations),
        "wall_counts": wall_counts,
        "reflections": labeled_records
    }
    labeled_json_path = PROCESSED_DIR / "labeled_first_order_reflections.json"
    labeled_json_path.write_text(json.dumps(labeled_out, indent=2), encoding="utf-8")
    print(f"\nSaved labeled reflections to: {labeled_json_path}")

    # 7. Construct CalibratedTOAObservationSet
    obs_set = CalibratedTOAObservationSet(
        inputs=inputs,
        origin="real",
        direct_paths=(),
        labeled_first_order_reflections=tuple(labeled_observations),
        unlabeled_echoes=()
    )

    # 8. Run BatSight's existing shoebox dimension estimator from 3 starting guesses
    print("\nRunning BatSight estimate_shoebox_dimensions from 3 different initial guesses...")
    starting_guesses = [
        [7.0, 5.0, 2.2],
        [10.0, 10.0, 4.0],
        [7.5, 8.5, 3.2]
    ]
    upper_bounds = [15.0, 15.0, 6.0]

    reconstruction_runs = []
    for guess in starting_guesses:
        res = estimate_shoebox_dimensions(
            obs_set,
            initial_dimensions_m=guess,
            upper_bounds_m=upper_bounds,
            interior_clearance_m=1e-6
        )
        est = res.estimated_dimensions_m
        est_Lx, est_Ly, est_Lz = float(est[0]), float(est[1]), float(est[2])

        err_Lx_cm = (est_Lx - gt_Lx) * 100.0
        err_Ly_cm = (est_Ly - gt_Ly) * 100.0
        err_Lz_cm = (est_Lz - gt_Lz) * 100.0

        rel_Lx_pct = abs(est_Lx - gt_Lx) / gt_Lx * 100.0
        rel_Ly_pct = abs(est_Ly - gt_Ly) / gt_Ly * 100.0
        rel_Lz_pct = abs(est_Lz - gt_Lz) / gt_Lz * 100.0

        rms_ms = float(res.residual_statistics.rms_s) * 1000.0 if res.residual_statistics else 0.0

        run_info = {
            "initial_guess_m": guess,
            "upper_bounds_m": upper_bounds,
            "status": res.status,
            "function_evaluations": res.function_evaluations,
            "jacobian_rank": res.jacobian_rank,
            "jacobian_condition_number": round(float(res.jacobian_condition_number), 2) if res.jacobian_condition_number is not None else None,
            "residual_rms_ms": round(rms_ms, 4),
            "estimated_dimensions_m": {
                "Lx": round(est_Lx, 4),
                "Ly": round(est_Ly, 4),
                "Lz": round(est_Lz, 4)
            },
            "ground_truth_dimensions_m": {
                "Lx": round(gt_Lx, 4),
                "Ly": round(gt_Ly, 4),
                "Lz": round(gt_Lz, 4)
            },
            "absolute_error_cm": {
                "Lx": round(err_Lx_cm, 2),
                "Ly": round(err_Ly_cm, 2),
                "Lz": round(err_Lz_cm, 2)
            },
            "relative_error_percent": {
                "Lx": round(rel_Lx_pct, 3),
                "Ly": round(rel_Ly_pct, 3),
                "Lz": round(rel_Lz_pct, 3)
            }
        }
        reconstruction_runs.append(run_info)

    # 9. Save reconstruction results JSON
    reconstruction_output = {
        "dataset": "SMARD",
        "configuration": "0001",
        "method": "BatSight calibrated shoebox dimension estimator",
        "ground_truth_dimensions_m": [gt_Lx, gt_Ly, gt_Lz],
        "total_first_order_observations": len(labeled_observations),
        "wall_counts": wall_counts,
        "runs": reconstruction_runs
    }
    recon_json_path = PROCESSED_DIR / "reconstruction_result.json"
    recon_json_path.write_text(json.dumps(reconstruction_output, indent=2), encoding="utf-8")
    print(f"Saved reconstruction results to: {recon_json_path}")

    # 10. Print clean summary table
    print("\n" + "=" * 98)
    print("RECONSTRUCTION ACCURACY SUMMARY — SMARD CONFIGURATION 0001")
    print("=" * 98)
    print(f"{'Run / Guess':<18} {'Param':<6} {'GT (m)':<9} {'Est (m)':<9} {'Abs Err (cm)':<15} {'Rel Err (%)':<13} {'RMS Res (ms)':<14} {'Status':<10}")
    print("-" * 98)

    for idx, run in enumerate(reconstruction_runs, 1):
        g_str = f"Run {idx} {run['initial_guess_m']}"
        rms_str = f"{run['residual_rms_ms']:.3f} ms"
        stat_str = f"{run['status']} (n={run['function_evaluations']})"

        print(f"{g_str:<18} {'Lx':<6} {gt_Lx:<9.3f} {run['estimated_dimensions_m']['Lx']:<9.3f} "
              f"{run['absolute_error_cm']['Lx']:+10.2f} cm     {run['relative_error_percent']['Lx']:<10.2f} %   {rms_str:<14} {stat_str:<10}")
        print(f"{'':<18} {'Ly':<6} {gt_Ly:<9.3f} {run['estimated_dimensions_m']['Ly']:<9.3f} "
              f"{run['absolute_error_cm']['Ly']:+10.2f} cm     {run['relative_error_percent']['Ly']:<10.2f} %   {'Rank: ' + str(run['jacobian_rank']):<14} {'Cond: ' + str(run['jacobian_condition_number']):<10}")
        print(f"{'':<18} {'Lz':<6} {gt_Lz:<9.3f} {run['estimated_dimensions_m']['Lz']:<9.3f} "
              f"{run['absolute_error_cm']['Lz']:+10.2f} cm     {run['relative_error_percent']['Lz']:<10.2f} %")
        if idx < len(reconstruction_runs):
            print("-" * 98)
    print("=" * 98)

if __name__ == "__main__":
    main()
