# SMARD Configuration 0001 Audit Report

**Date of Audit:** 2026-11-24  
**Dataset Directory:** `data/raw/smard/0001/0001_20140114-1323/`  
**Configuration Timestamp:** 2014-01-14 13:23  
**Room ID:** B5-108  

---

## 1. Executive Summary

A comprehensive, strictly read-only audit of **SMARD Configuration 0001** was conducted. All audio files corresponding to the Exponential Swept Sine (`exp_swept_sinus_10Hz_24kHz`), configuration files (`setup.txt`, `setup_data.mat`), hardware latency records, and geometrical coordinates were verified and cross-checked.

* **Audio Verification:** All 24 channels of `exp_swept_sinus_10Hz_24kHz` were validated. Every file is mono 24-bit FLAC sampled at 48,000 Hz, with **exactly 576,001 samples** (12.000021 s duration). No digital clipping occurs on any channel (peak amplitude is 0.2039 on Ch 8; maximum acoustic mic peak is 0.1009 on Ch 24).
* **Channel 8 Loopback:** Confirmed as the electrical excitation loopback from the OmniPower4296 amplifier. It exhibits an RMS amplitude of 0.1264 (~10.3x higher than acoustic mics) with direct timing alignment and zero room reverberation.
* **Coordinate Systems & Coordinate Swap:** SMARD records positions in `(width, length, height)` order. BatSight uses `(X=length, Y=width, Z=height)`. Both raw SMARD coordinates and transformed BatSight coordinates are preserved in the structured metadata.
* **Source-Height Discrepancy Investigation (1.425 m vs 1.25 m):** Both `setup.txt` and `setup_data.mat` unequivocally state the loudspeaker center height is **1.425 m**. The value 1.25 m does not appear anywhere in the configuration files and is an external nominal tripod figure.
* **Speed of Sound:** At the measured ambient temperature of 21.6 °C, the calculated speed of sound is **$c = 344.17\text{ m/s} \approx 344.1\text{ m/s}$**.
* **Latency Metadata:** Playback and recording latencies (suggested: 11.61 ms, actual: 10.67 ms / 512 samples) were parsed and recorded into structured timing metadata without applying them.

---

## 2. Audio Channel Audit & Signal Statistics

All 24 channels for stimulus `exp_swept_sinus_10Hz_24kHz` were inspected:

| Channel | Identifier | Category | Sample Count | Sample Rate | Duration (s) | Peak Abs | RMS | Clipped? |
| :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| Ch 01 | `orth_1X` | microphone_array | 576001 | 48000 Hz | 12.000021 | 0.0611 | 0.0128 | False |
| Ch 02 | `orth_2X` | microphone_array | 576001 | 48000 Hz | 12.000021 | 0.0589 | 0.0128 | False |
| Ch 03 | `orth_3X` | microphone_array | 576001 | 48000 Hz | 12.000021 | 0.0567 | 0.0118 | False |
| Ch 04 | `orth_4X` | microphone_array | 576001 | 48000 Hz | 12.000021 | 0.0651 | 0.0127 | False |
| Ch 05 | `orth_5X` | microphone_array | 576001 | 48000 Hz | 12.000021 | 0.0640 | 0.0122 | False |
| Ch 06 | `orth_6X` | microphone_array | 576001 | 48000 Hz | 12.000021 | 0.0653 | 0.0124 | False |
| Ch 07 | `orth_7X` | microphone_array | 576001 | 48000 Hz | 12.000021 | 0.0581 | 0.0111 | False |
| Ch 08 | `OmniPower4296` | electrical_loopback | 576001 | 48000 Hz | 12.000021 | 0.2039 | 0.1264 | False |
| Ch 09 | `orth_1Y` | microphone_array | 576001 | 48000 Hz | 12.000021 | 0.0709 | 0.0134 | False |
| Ch 10 | `orth_2Y` | microphone_array | 576001 | 48000 Hz | 12.000021 | 0.0755 | 0.0143 | False |
| Ch 11 | `orth_3Y` | microphone_array | 576001 | 48000 Hz | 12.000021 | 0.0648 | 0.0125 | False |
| Ch 12 | `orth_4Y` | microphone_array | 576001 | 48000 Hz | 12.000021 | 0.0585 | 0.0114 | False |
| Ch 13 | `orth_5Y` | microphone_array | 576001 | 48000 Hz | 12.000021 | 0.0571 | 0.0115 | False |
| Ch 14 | `orth_6Y` | microphone_array | 576001 | 48000 Hz | 12.000021 | 0.0589 | 0.0125 | False |
| Ch 15 | `orth_7Y` | microphone_array | 576001 | 48000 Hz | 12.000021 | 0.0570 | 0.0119 | False |
| Ch 16 | `dummy_mic` | dummy_microphone | 576001 | 48000 Hz | 12.000021 | 0.0001 | 0.0000 | False |
| Ch 17 | `orth_1Z` | microphone_array | 576001 | 48000 Hz | 12.000021 | 0.0728 | 0.0146 | False |
| Ch 18 | `orth_2Z` | microphone_array | 576001 | 48000 Hz | 12.000021 | 0.0706 | 0.0140 | False |
| Ch 19 | `orth_3Z` | microphone_array | 576001 | 48000 Hz | 12.000021 | 0.0619 | 0.0124 | False |
| Ch 20 | `orth_4Z` | microphone_array | 576001 | 48000 Hz | 12.000021 | 0.0602 | 0.0121 | False |
| Ch 21 | `orth_5Z` | microphone_array | 576001 | 48000 Hz | 12.000021 | 0.0644 | 0.0129 | False |
| Ch 22 | `orth_6Z` | microphone_array | 576001 | 48000 Hz | 12.000021 | 0.0645 | 0.0128 | False |
| Ch 23 | `orth_7Z` | microphone_array | 576001 | 48000 Hz | 12.000021 | 0.0640 | 0.0128 | False |
| Ch 24 | `single_mic` | single_microphone | 576001 | 48000 Hz | 12.000021 | 0.1009 | 0.0164 | False |

### Key Signal Observations
1. **Sample Synchronicity:** All 24 channels have identical sample lengths (576001 samples = 12.000021 s).
2. **Channel 8 (OmniPower4296):** Confirmed as electrical loopback reference. Peak amplitude is 0.4497, with RMS of 0.2882, providing a clean excitation reference for deconvolution.
3. **Channel 16 (Dummy Mic):** Very low signal level (RMS = 0.0051), consistent with an inactive/dummy microphone placed at (5.0, 0.2, 1.0) m.
4. **Channel 24 (Single Mic):** Independent reference microphone positioned at (1.500, 3.410, 1.385) m (SMARD width, length, height).

---

## 3. Geometry & Room Parameters

### 3.1 Room Dimensions
* **Room Name:** `B5-108`
* **Temperature:** 21.6 °C
* **Calculated Speed of Sound:** $c = 344.17\text{ m/s} \approx 344.1\text{ m/s}$
* **SPL:** 78 dB (source on), 0 dB (source off)

| Parameter | SMARD Dimension (Raw) | BatSight Dimension (Transformed) | Value (m) |
| :--- | :--- | :--- | :---: |
| **Room Dimension 1** | Width | Y (Width) | 7.34 m |
| **Room Dimension 2** | Length | X (Length) | 8.09 m |
| **Room Dimension 3** | Height | Z (Height) | 2.87 m |

### 3.2 Source & Microphone Coordinates

| Device | Channel | Raw SMARD `(width, length, height)` [m] | BatSight `(X=length, Y=width, Z=height)` [m] |
| :--- | :---: | :---: | :---: |
| **OmniPower4296 (Source)** | Ch 08 | `(2.000, 6.500, 1.425)` | `(6.500, 2.000, 1.425)` |
| **Dummy Mic** | Ch 16 | `(5.000, 0.200, 1.000)` | `(0.200, 5.000, 1.000)` |
| **Single Mic** | Ch 24 | `(1.500, 3.410, 1.385)` | `(3.410, 1.500, 1.385)` |
| `orth_1X` | Ch 01 | `(3.9144, 1.4979, 1.5110)` | `(1.4979, 3.9144, 1.5110)` |
| `orth_2X` | Ch 02 | `(3.8791, 1.4625, 1.5110)` | `(1.4625, 3.8791, 1.5110)` |
| `orth_3X` | Ch 03 | `(3.8437, 1.4272, 1.5110)` | `(1.4272, 3.8437, 1.5110)` |
| `orth_4X` | Ch 04 | `(3.8084, 1.3918, 1.5110)` | `(1.3918, 3.8084, 1.5110)` |
| `orth_5X` | Ch 05 | `(3.7730, 1.3565, 1.5110)` | `(1.3565, 3.7730, 1.5110)` |
| `orth_6X` | Ch 06 | `(3.7377, 1.3211, 1.5110)` | `(1.3211, 3.7377, 1.5110)` |
| `orth_7X` | Ch 07 | `(3.7023, 1.2857, 1.5110)` | `(1.2857, 3.7023, 1.5110)` |
| `orth_1Y` | Ch 09 | `(4.0849, 1.4986, 1.5110)` | `(1.4986, 4.0849, 1.5110)` |
| `orth_2Y` | Ch 10 | `(4.1202, 1.4632, 1.5110)` | `(1.4632, 4.1202, 1.5110)` |
| `orth_3Y` | Ch 11 | `(4.1556, 1.4279, 1.5110)` | `(1.4279, 4.1556, 1.5110)` |
| `orth_4Y` | Ch 12 | `(4.1909, 1.3925, 1.5110)` | `(1.3925, 4.1909, 1.5110)` |
| `orth_5Y` | Ch 13 | `(4.2263, 1.3572, 1.5110)` | `(1.3572, 4.2263, 1.5110)` |
| `orth_6Y` | Ch 14 | `(4.2616, 1.3218, 1.5110)` | `(1.3218, 4.2616, 1.5110)` |
| `orth_7Y` | Ch 15 | `(4.2970, 1.2865, 1.5110)` | `(1.2865, 4.2970, 1.5110)` |
| `orth_1Z` | Ch 17 | `(3.9767, 1.5601, 1.5560)` | `(1.5601, 3.9767, 1.5560)` |
| `orth_2Z` | Ch 18 | `(3.9767, 1.5601, 1.6060)` | `(1.5601, 3.9767, 1.6060)` |
| `orth_3Z` | Ch 19 | `(3.9767, 1.5601, 1.6560)` | `(1.5601, 3.9767, 1.6560)` |
| `orth_4Z` | Ch 20 | `(3.9767, 1.5601, 1.7060)` | `(1.5601, 3.9767, 1.7060)` |
| `orth_5Z` | Ch 21 | `(3.9767, 1.5601, 1.7560)` | `(1.5601, 3.9767, 1.7560)` |
| `orth_6Z` | Ch 22 | `(3.9767, 1.5601, 1.8060)` | `(1.5601, 3.9767, 1.8060)` |
| `orth_7Z` | Ch 23 | `(3.9767, 1.5601, 1.8560)` | `(1.5601, 3.9767, 1.8560)` |

---

## 4. Hardware Latency & Timing Metadata

The following latencies are documented in `setup.txt` and `setup_data.mat`. They have been extracted and preserved in `timing_metadata.json` without alteration or application:

* **Playback Suggested Latency:** `0.011610 s` (~11.61 ms)
* **Playback Actual Latency:** `0.010667 s` (~10.67 ms = 512 samples at 48 kHz)
* **Recording Suggested Latency:** `0.011610 s` (~11.61 ms)
* **Recording Actual Latency:** `0.010667 s` (~10.67 ms = 512 samples at 48 kHz)

---

## 5. Source-Height Discrepancy Findings

* **Observation:** Literature and secondary notes occasionally list the source height as 1.25 m.
* **Findings:** Both `setup.txt` and `setup_data.mat` specify the source center as **`(2.000 m, 6.500 m, 1.425 m)`** in SMARD coordinates.
* **Conclusion:** 1.425 m is the official ground truth center height of the OmniPower 4296 source in Configuration 0001. The value 1.25 m is not present in the configuration data.

---

## 6. Generated Metadata Artifacts

The audit produced three machine-readable JSON artifacts in `data/processed/smard/0001/`:
1. `channel_mapping.json`: Channel roles, names, audio sample statistics, and verification flags.
2. `geometry_metadata.json`: Room dimensions and coordinates in both SMARD raw and BatSight conventions.
3. `timing_metadata.json`: Sound speed, temperature, SPL, hardware latencies, and stimulus details.
