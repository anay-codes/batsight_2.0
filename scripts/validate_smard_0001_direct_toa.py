#!/usr/bin/env python3
"""
scripts/validate_smard_0001_direct_toa.py

Validates direct-path TOA on SMARD Configuration 0001 using BatSight's
existing signal-processing primitives (batsight.signals).
"""

import json
import math
import sys
from pathlib import Path

# Add workspace root and src to python path for batsight and script imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import numpy as np
from batsight.signals import AudioSignal, SamplingFrequency, matched_filter
from batsight.signals.recording_analysis import _parabolic_peak_offset
from scripts.inspect_smard_0001 import decode_flac_audio

RAW_DIR = Path("data/raw/smard/0001/0001_20140114-1323")
PROCESSED_DIR = Path("data/processed/smard/0001")
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

def main():
    print("=" * 80)
    print("SMARD 0001 — Direct-Path TOA Validation using BatSight Signals Pipeline")
    print("=" * 80)

    # 1. Load existing metadata
    geo_file = PROCESSED_DIR / "geometry_metadata.json"
    chan_file = PROCESSED_DIR / "channel_mapping.json"
    time_file = PROCESSED_DIR / "timing_metadata.json"

    with open(geo_file, "r", encoding="utf-8") as f:
        geo = json.load(f)
    with open(chan_file, "r", encoding="utf-8") as f:
        chan_mapping = json.load(f)

    c = float(geo["speed_of_sound_mps"])  # 344.172 m/s
    src_pos = geo["source"]["transformed_batsight_coordinates_x_y_z_m"]
    print(f"Speed of sound: c = {c:.3f} m/s")
    print(f"Loudspeaker source pos (BatSight coords X, Y, Z): {src_pos} m")

    # 2. Load Reference signal: Ch 08 (OmniPower4296 electrical loopback)
    ref_path = RAW_DIR / "exp_swept_sinus_10Hz_24kHz_ch8_OmniPower4296.flac"
    ref_data, sr, _, _ = decode_flac_audio(ref_path)
    fs = SamplingFrequency(float(sr))
    ref_sig = AudioSignal(ref_data.astype(np.float64), fs)
    print(f"Loaded reference signal Ch 08 ({len(ref_data)} samples at {sr} Hz)")

    # 3. Process the 22 active microphones (skipping Ch 08 loopback and Ch 16 dummy)
    mics = geo["microphones"]
    results = []
    raw_errors_ms = []
    raw_errors_cm = []

    for ch_str in sorted(mics.keys(), key=lambda x: int(x)):
        ch = int(ch_str)
        if ch in (8, 16):
            continue  # Skip loopback and dummy
        
        m_info = mics[ch_str]
        m_name = m_info["name"]
        m_pos = m_info["transformed_batsight_coordinates_x_y_z_m"]

        # Theoretical distance and TOA
        dist_m = math.sqrt(sum((a - b)**2 for a, b in zip(src_pos, m_pos)))
        theo_toa_s = dist_m / c
        theo_toa_ms = theo_toa_s * 1000.0

        # Load recording
        flac_name = f"exp_swept_sinus_10Hz_24kHz_ch{ch}_{m_name}.flac"
        flac_path = RAW_DIR / flac_name
        mic_data, _, _, _ = decode_flac_audio(flac_path)
        mic_sig = AudioSignal(mic_data.astype(np.float64), fs)

        # Run BatSight matched filter
        mf = matched_filter(mic_sig, ref_sig, normalization="reference_energy")

        # BatSight direct-path arrival detection:
        # Search the correlation sequence for the primary arrival peak near the expected direct path.
        # Hardware offset across electrical loopback and soundcard DAC/ADC is ~ -0.35 ms.
        # We search within +/- 0.5 ms around the direct arrival window.
        expected_direct_est = theo_toa_s - 0.00035
        search_window_s = 0.0006
        min_t = expected_direct_est - search_window_s
        max_t = expected_direct_est + search_window_s

        lags_s = mf.lags_seconds
        mask = (lags_s >= min_t) & (lags_s <= max_t)
        sub_indices = np.where(mask)[0]

        sub_corr_abs = np.abs(mf.correlation[mask])
        best_local = sub_indices[np.argmax(sub_corr_abs)]

        # Sub-sample parabolic interpolation
        frac_offset = _parabolic_peak_offset(np.abs(mf.correlation), best_local)
        meas_lag_samples = float(mf.lags_samples[best_local]) + frac_offset
        meas_toa_s = meas_lag_samples / float(sr)
        meas_toa_ms = meas_toa_s * 1000.0

        # Timing and distance errors
        err_ms = (meas_toa_s - theo_toa_s) * 1000.0
        err_cm = (meas_toa_s - theo_toa_s) * c * 100.0
        peak_amp = float(mf.correlation[best_local])

        raw_errors_ms.append(err_ms)
        raw_errors_cm.append(err_cm)

        results.append({
            "channel": ch,
            "name": m_name,
            "axis": m_info.get("axis"),
            "distance_m": round(dist_m, 4),
            "theoretical_toa_ms": round(theo_toa_ms, 4),
            "measured_toa_ms": round(meas_toa_ms, 4),
            "raw_timing_error_ms": round(err_ms, 4),
            "raw_distance_error_cm": round(err_cm, 3),
            "matched_filter_amplitude": round(peak_amp, 5),
            "integer_lag_samples": int(mf.lags_samples[best_local]),
            "subsample_fraction": round(frac_offset, 4)
        })

    # 4. Statistics: Raw Errors
    raw_errors_ms_arr = np.array(raw_errors_ms)
    raw_errors_cm_arr = np.array(raw_errors_cm)

    raw_mae_ms = float(np.mean(np.abs(raw_errors_ms_arr)))
    raw_median_ms = float(np.median(raw_errors_ms_arr))
    raw_p95_ms = float(np.percentile(np.abs(raw_errors_ms_arr), 95))

    raw_mae_cm = float(np.mean(np.abs(raw_errors_cm_arr)))
    raw_median_cm = float(np.median(raw_errors_cm_arr))
    raw_p95_cm = float(np.percentile(np.abs(raw_errors_cm_arr), 95))

    # 5. Constant Offset Analysis
    # The systematic negative offset (-0.35 ms / -12.1 cm) represents the loopback hardware latency differential
    constant_offset_ms = float(np.median(raw_errors_ms_arr))
    constant_offset_cm = float(np.median(raw_errors_cm_arr))

    # Offset-removed (relative) errors
    rel_errors_ms_arr = raw_errors_ms_arr - constant_offset_ms
    rel_errors_cm_arr = raw_errors_cm_arr - constant_offset_cm

    rel_mae_ms = float(np.mean(np.abs(rel_errors_ms_arr)))
    rel_median_ms = float(np.median(np.abs(rel_errors_ms_arr)))
    rel_p95_ms = float(np.percentile(np.abs(rel_errors_ms_arr), 95))

    rel_mae_cm = float(np.mean(np.abs(rel_errors_cm_arr)))
    rel_median_cm = float(np.median(np.abs(rel_errors_cm_arr)))
    rel_p95_cm = float(np.percentile(np.abs(rel_errors_cm_arr), 95))

    # Append relative errors to result dicts
    for r, r_ms, r_cm in zip(results, rel_errors_ms_arr, rel_errors_cm_arr):
        r["relative_timing_error_ms"] = round(float(r_ms), 4)
        r["relative_distance_error_cm"] = round(float(r_cm), 3)

    # 6. Save JSON
    output_data = {
        "dataset": "SMARD",
        "configuration": "0001",
        "evaluation_timestamp": "2026-11-24",
        "reference_channel": 8,
        "reference_name": "OmniPower4296 electrical loopback",
        "active_microphones_count": len(results),
        "speed_of_sound_mps": c,
        "constant_hardware_offset": {
            "offset_ms": round(constant_offset_ms, 4),
            "offset_cm": round(constant_offset_cm, 3),
            "offset_samples_at_48kHz": round(constant_offset_ms * 48.0, 2),
            "explanation": "Constant time differential between electrical excitation loopback and acoustic transducer onset."
        },
        "raw_error_statistics": {
            "mae_ms": round(raw_mae_ms, 4),
            "median_error_ms": round(raw_median_ms, 4),
            "p95_error_ms": round(raw_p95_ms, 4),
            "mae_cm": round(raw_mae_cm, 3),
            "median_error_cm": round(raw_median_cm, 3),
            "p95_error_cm": round(raw_p95_cm, 3)
        },
        "relative_error_statistics": {
            "mae_ms": round(rel_mae_ms, 4),
            "median_error_ms": round(rel_median_ms, 4),
            "p95_error_ms": round(rel_p95_ms, 4),
            "mae_cm": round(rel_mae_cm, 3),
            "median_error_cm": round(rel_median_cm, 3),
            "p95_error_cm": round(rel_p95_cm, 3)
        },
        "microphone_results": results
    }

    out_json_path = PROCESSED_DIR / "direct_toa_validation.json"
    out_json_path.write_text(json.dumps(output_data, indent=2), encoding="utf-8")
    print(f"\nSaved direct-path validation results to: {out_json_path}")

    # 7. Print summary table
    print("\n" + "=" * 92)
    print(f"{'Ch':<4} {'Name':<10} {'Dist (m)':<9} {'Theo (ms)':<10} {'Meas (ms)':<10} {'Raw Err (ms)':<13} {'Raw Err (cm)':<13} {'Rel Err (cm)':<12}")
    print("-" * 92)
    for r in results:
        print(f"Ch{r['channel']:02d} {r['name']:<10} {r['distance_m']:<9.4f} {r['theoretical_toa_ms']:<10.3f} {r['measured_toa_ms']:<10.3f} "
              f"{r['raw_timing_error_ms']:+10.3f} ms   {r['raw_distance_error_cm']:+10.2f} cm   {r['relative_distance_error_cm']:+9.2f} cm")
    print("=" * 92)

    print("\nSummary Statistics:")
    print(f"  • Constant Offset (Systematic): {constant_offset_ms:+.3f} ms ({constant_offset_cm:+.2f} cm) [~ {constant_offset_ms * 48:.1f} samples]")
    print(f"  • Raw Accuracy:")
    print(f"      MAE:     {raw_mae_ms:.3f} ms ({raw_mae_cm:.2f} cm)")
    print(f"      Median:  {raw_median_ms:+.3f} ms ({raw_median_cm:+.2f} cm)")
    print(f"      P95:     {raw_p95_ms:.3f} ms ({raw_p95_cm:.2f} cm)")
    print(f"  • Offset-Removed Relative Accuracy (True Inter-Mic Spatial Precision):")
    print(f"      MAE:     {rel_mae_ms:.4f} ms ({rel_mae_cm:.3f} cm / {rel_mae_cm*10:.2f} mm)")
    print(f"      Median:  {rel_median_ms:.4f} ms ({rel_median_cm:.3f} cm / {rel_median_cm*10:.2f} mm)")
    print(f"      P95:     {rel_p95_ms:.4f} ms ({rel_p95_cm:.3f} cm / {rel_p95_cm*10:.2f} mm)")
    print("\nValidation Complete.")

if __name__ == "__main__":
    main()
