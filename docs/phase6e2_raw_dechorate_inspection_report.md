# BatSight Phase 6E.2 — Raw dEchorate Dataset Acquisition & Inspection Report

**Audit Date:** 2026-11-12  
**Task:** Inspection of Candidate Raw Multichannel Recording (`room-000000.zip` / `000000/2020-01-23__20-24-07.wav`)  
**Status:** **BLOCKED AT DATASET ACQUISITION GATE** (Missing Raw Archive on Public Distribution Mirror)

---

## 1. Executive Summary

This report establishes the findings for **BatSight Phase 6E.2 — Raw dEchorate Dataset Acquisition & Inspection**. In accordance with the BatSight research and validation methodology:
- No BatSight production code or existing signal processing logic was altered.
- No synthetic substitutes were passed off as real raw audio.
- The official sources, repository scripts, and Google Drive endpoints were rigorously audited.

### Key Finding & Verdict
The candidate raw archive **`room-000000.zip` does not exist on the official raw dataset Google Drive** (`1yGTh_BjnVNwDgBsn5mkuW3i4rJIgZwlS`) nor on the public Zenodo records (6576203, 5562386, 4626590). The Google Drive endpoint contains only post-processed `.sofa` files and secondary `.h5` files.

Furthermore, deep inspection of the author's reference processing scripts (`main_build_sound_datasets.py`, `main_estimate_rirs.py`, `stimulus.py`, and `__init__.py`) revealed that **the authors themselves discarded the calculated loopback cross-correlation delay in their production pipeline**, falling back to a hardcoded standard offset of **4,444 samples (92.58 ms)**.

Consequently, **this candidate cannot be validated as a raw recording at this stage**, and Phase 6E remains restricted to the already-verified SOFA measured-RIR evaluation.

---

## 2. Archive Acquisition & Google Drive Audit

### 2.1 Target Candidate Specification
- **Archive Name:** `room-000000.zip`
- **Expected WAV Member:** `000000/2020-01-23__20-24-07.wav`
- **Room Code:** `000000` (Anechoic / all-absorbent configuration)
- **Source ID:** `0` (Directional source 1)
- **Signal:** `chirp` (Exponential Sine Sweep, ESS)
- **Documented Channels:** 31 (Channels 0–29: capsule microphones; Channel 30: loopback reference)

### 2.2 Google Drive Audit (`1yGTh_BjnVNwDgBsn5mkuW3i4rJIgZwlS`)
We queried and parsed the contents of the official Google Drive folder provided in the prompt and cited in the official `Chutlhu/dEchorate` README.

| Item Name | Type | Size / Items | Google Drive ID / Notes |
|---|---|---|---|
| `sofa/` | Folder | 595 files | `1iKjhy7QvdQ38HwxQ5ZCBI-eCQTuVLlgt` (Pre-processed SOFA RIRs) |
| `dEchorate_annotations.h5` | HDF5 File | 30,324 bytes | `1zFs4P2pRkX-IcTlvGMoc7lLca9xihJNW` |
| `dEchorate_database.csv` | CSV File | 2,931,172 bytes | `1sErbvkuvSwoBlHXz7ssQM8VhrAD1_4mj` (SHA-256: `8f777491...`) |
| `dEchorate_rir.h5` | HDF5 File | ~4.19 GB | `1fsDNVwalMYrI9pq0Q3BI7PFBr0Z_L9PB` (Deconvolved RIRs) |
| `Load dataset.ipynb` | Jupyter Notebook | 229,088 bytes | `1pFEI_KEwZROR1EXUHbx7OMLryY6NN47O` |
| **`room-000000.zip`** | Archive | **MISSING** | **Not found in Google Drive or subfolders** |

Total items discovered across the entire Google Drive folder: **599 items**. Not a single raw `.zip` or `.wav` recording is hosted in this folder.

### 2.3 Zenodo & Author Repository Provenance Audit
To determine if `room-000000.zip` was hosted elsewhere:
1. **Zenodo Record 6576203 (v2.0.0, 25.8 GB):** Hosts `dEchorate_rirs_gzip7.hdf5`, `dEchorate_speech_gzip7.hdf5`, `dEchorate_noise_gzip7.hdf5`, `dEchorate_babble_gzip7.hdf5`, and `dEchorate_silence_gzip7.hdf5`. The chirp dataset was not included, and no raw ZIP archives are present.
2. **Zenodo Concept 4626589 (Records 5562386 & 4626590):** Contained an older 83.8 GB `dechorate.hdf5`, not individual room ZIPs.
3. **GitHub Issue Tracker (`Chutlhu/dEchorate`):**
   - In Issue #37, the author stated that the Google Drive folder was created temporarily because Zenodo HDF5 files were experiencing read errors. The author regenerated only the HDF5 and SOFA deliverables.
   - In `run_deploy_dataset_from_raws.sh`, raw files are read from a private workstation path (`path_to_data_dir="/home/dicarlod/Documents/Dataset/dEchorate"`). The raw archives were never released publicly.

---

## 3. Metadata & Provenance Verification

We downloaded and analyzed the official `dEchorate_database.csv` (SHA-256: `8f777491e90bc3286d5a2afe47195515e8429baea073545a007eb7795a883ec3`).

### 3.1 Metadata Query for `2020-01-23__20-24-07`
A filter on `filename == '2020-01-23__20-24-07'` returns exactly **31 rows**:
- **Rows 0 to 29:**
  - `src_id`: `1.0`, `src_ch`: `33.0`, `src_signal`: `chirp`, `room_code`: `000000`
  - `mic_id`: `0.0` through `29.0` (0-indexed)
  - `mic_ch`: `1.0` through `30.0` (1-indexed hardware channel)
  - `mic_type`: `capsule`
  - `array_id`: `0.0` to `5.0` (6 spatial arrays, 5 capsules each)
- **Row 30:**
  - `src_id`: `1.0`, `src_ch`: `33.0`, `src_signal`: `chirp`, `room_code`: `000000`
  - `mic_id`: `30.0`
  - `mic_ch`: `""` (**Empty string**; not recorded in database)
  - `mic_type`: `loopback`
  - `array_id`: `""` (**Empty string**)

### 3.2 Metadata Inconsistencies & Mismatches
1. **Empty Channel Identifier:** While capsules have explicitly numbered hardware channels `mic_ch = 1.0 ... 30.0`, the loopback channel has an empty string for `mic_ch`. Code parsing `float(row['mic_ch'])` throws an exception unless special-cased.
2. **Indexing Discrepancy:** The CSV uses 1-indexed source IDs (`src_id = 1.0` for the first directional source), while the Python codebase uses 0-indexed integer identifiers (`src_ids = [0, 1, 2, 3, 4, 5, 6, 7, 8]`).
3. **Inter-Sweep Silent Gaps:** The dataset paper states there are *"two-second gaps between sweeps"*. However, `stimulus.py` appends 2 seconds of silence to the end of each sweep and prefixes 2 seconds of silence to the beginning of each sweep (`zerostart` + `sinsweep` + `zeroend`), producing a **4-second silence gap** between consecutive sweeps in the 3-repetition stimulus.

---

## 4. ESS Probe & Loopback Structure Analysis

From `experiments/dechorate_reference/stimulus.py` and `__init__.py`:
- **Sampling Frequency ($F_s$):** 48,000 Hz
- **Sweep Duration ($T_{sweep}$):** 10.0 seconds ($480,000$ samples)
- **Frequency Range:** 100 Hz to 14,000 Hz (logarithmic / exponential sweep)
- **Repetitions:** 3
- **Cycle Duration:** $2\text{ s (pre-silence)} + 10\text{ s (sweep)} + 2\text{ s (post-silence)} = 14.0\text{ s}$
- **Total Duration:** $14.0\text{ s} \times 3 = 42.0\text{ seconds}$ ($2,016,000$ samples)

### Nominal Sweep Timing Windows
> [!NOTE]
> These timings represent the mathematical generator specification from `stimulus.py`. They are **nominal reference values**, not verified hardware timestamps from a physical recording.

| Interval | Start Time | End Time | Duration | Description |
|---|---|---|---|---|
| Initial Silence | 0.000 s | 2.000 s | 2.000 s | Lead-in zero padding |
| **Sweep 1** | **2.000 s** | **12.000 s** | **10.000 s** | First ESS sweep (100 Hz $\to$ 14 kHz) |
| Gap 1 | 12.000 s | 16.000 s | 4.000 s | Combined post/pre-sweep silence |
| **Sweep 2** | **16.000 s** | **26.000 s** | **10.000 s** | Second ESS sweep (100 Hz $\to$ 14 kHz) |
| Gap 2 | 26.000 s | 30.000 s | 4.000 s | Combined post/pre-sweep silence |
| **Sweep 3** | **30.000 s** | **40.000 s** | **10.000 s** | Third ESS sweep (100 Hz $\to$ 14 kHz) |
| Final Silence | 40.000 s | 42.000 s | 2.000 s | Trailing zero padding |

---

## 5. Loopback Timing & The Author Pipeline Workaround

A critical inspection of `experiments/dechorate_reference/main_estimate_rirs.py` reveals how the original authors handled loopback synchronization:

```python
# From main_estimate_rirs.py (lines 104-109)
rir_loop = ps.compute_rir(loopback[:,None], windowing=False)
delay = np.argmax(np.abs(rir_loop)) # in samples
```

The authors computed the delay via loopback deconvolution. **However, in lines 156–161, they completely bypassed `delay`**:

```python
# From main_estimate_rirs.py (lines 156-161)
if group in rec_offset.keys():
    d = rec_offset[group]
else:
    d = rec_offset['standard']

rirs = rirs[d:d+L,:]
```

Where in `__init__.py`:
```python
constants['recording_offset']['standard'] = 4444 # samples (~92.583 ms)
```

### Scientific Implication
1. **Loopback delay was not trusted or utilized for RIR alignment by the authors.**
2. A fixed hardcoded offset of **4,444 samples** was used for room 000000, with arbitrary overrides (`8,540` or `12,636` samples) for specific problematic room configurations (`000001`, `001000`, `011100`).
3. This directly confirms the BatSight Phase 6E caution: **the raw-to-RIR timing contract cannot be inferred purely from loopback correlation without accounting for the author's empirical offset convention.**

---

## 6. Representative Microphone Waveform Inspection (Room 000000)

While the raw uncompressed 42-second WAV is unavailable on the public mirror, we verified the real measured multichannel acoustic responses from the verified SOFA measurement for Room `000000` (`dEchorate_room000000_src1_arr1_mics1-5.sofa`, SHA-256: `26a76bbafb80af0dc29a6838ae9d8fdc4846249c8a4e60a2ef87d13b87496b07`).

Below is the verified 5-channel response for Array 1 (Mics 1–5), zoomed into the first 40 ms showing the direct arrivals and early reflections:

- [Waveform Plots in Artifact Directory](file:///C:/Users/Anay%20tare/.gemini/antigravity/brain/49670d0d-4454-4667-9be6-a638241edf1d/dechorate_representative_mic_waveforms.png)

---

## 7. Artifact Manifest & Provenance Hashes

| File Path | Description | SHA-256 Hash |
|---|---|---|
| `experiments/dEchorate_database.csv` | Official dEchorate metadata database | `8f777491e90bc3286d5a2afe47195515e8429baea073545a007eb7795a883ec3` |
| `data/raw/dechorate_phase6e/dEchorate_room000000_src1_arr1_mics1-5.sofa` | Verified Room 000000 SOFA measured RIR | `26a76bbafb80af0dc29a6838ae9d8fdc4846249c8a4e60a2ef87d13b87496b07` |
| `experiments/phase6e_results/dechorate_reference_loopback_and_sweeps.png` | Plot of ESS reference probe & sweep intervals | `89a560493b0dd28b82f1cdc601a729ca05e132e8fed2ce17f31c4856b0dd3403` |
| `experiments/phase6e_results/dechorate_representative_mic_waveforms.png` | Plot of measured Room 000000 mic channels | `e2a69e866629efbb91bd1aca21ce37fa32710780d96a8be1f3355222182c280a` |
| `experiments/dechorate_reference/main_build_sound_datasets.py` | Official dataset builder script | `9364df4133aec9489c33c076905590d4e73bf8a40cdebb90f57da99d1b256363` |
| `experiments/dechorate_reference/main_estimate_rirs.py` | Official RIR deconvolution script | `0b7855908ac2614dcdd63345b8d6cb55dc9fdde04d9a70ec565f9e244698d45a` |
| `experiments/dechorate_reference/stimulus.py` | Official ESS probe generator script | `6fcba3f225e67ca631763bdc6a638d025dccef3c6e0a56af007c600a1bac69fe` |
| `experiments/dechorate_reference/__init__.py` | Official dataset constants & offsets | `aa26defc926b23a9338b41602d865f64a27f9d453288e75af9fbe55c7c221be5` |

*(Note: Because `room-000000.zip` was not provided in the public Google Drive folder, its physical hash and extracted WAV path cannot be measured.)*

---

## 8. Conclusions & Recommendation

1. **Gate Decision:** **BLOCKED** for raw sweep audio validation. The raw ZIP files were not distributed in the public Google Drive or Zenodo release.
2. **Honesty & Integrity:** Following BatSight guidelines, missing data has been recorded accurately rather than synthesized or faked.
3. **Next Steps:**
   - Continue using the verified Phase 6E SOFA RIR dataset for room acoustic TOA and echo detection validation.
   - If raw multichannel sweep validation is required in a future phase, a request must be made directly to the dataset authors (Di Carlo et al., Inria/Bar-Ilan) for the archival raw ZIP files, or alternative open raw sweep datasets must be acquired.

