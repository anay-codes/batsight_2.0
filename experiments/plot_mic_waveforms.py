import os
import h5py
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

sofa_path = "data/raw/dechorate_phase6e/dEchorate_room000000_src1_arr1_mics1-5.sofa"
out_dir = "experiments/phase6e_results"
os.makedirs(out_dir, exist_ok=True)

with h5py.File(sofa_path, "r") as f:
    fs = float(np.asarray(f["Data.SamplingRate"]).reshape(-1)[0])
    # Data.IR shape: (1, 5, 48000)
    ir = np.asarray(f["Data.IR"][0], dtype=np.float64)  # 5 x 48000
    source_pos = np.asarray(f["SourcePosition"][0])
    receiver_pos = np.asarray(f["ReceiverPosition"][:, :, 0])

# Plot representative microphone waveforms (mics 1 to 5)
fig, axes = plt.subplots(5, 1, figsize=(12, 10), sharex=True)
fig.suptitle(f"dEchorate Measured Real Multichannel Waveforms (Room 000000, Source 1, Array 1, Mics 1–5)", fontsize=13)

time_axis = np.arange(ir.shape[1]) / fs * 1000  # in ms

# Zoom into first 50 ms where direct arrival and early reflections occur
zoom_ms = 40
zoom_samples = int(zoom_ms * fs / 1000)

for i in range(5):
    ax = axes[i]
    ax.plot(time_axis[:zoom_samples], ir[i, :zoom_samples], color=f"C{i}", lw=0.8, label=f"Mic {i+1} (Ch {i})")
    ax.set_ylabel(f"Mic {i+1}")
    ax.grid(True, linestyle="--", alpha=0.5)
    ax.legend(loc="upper right")
    
    # Annotate direct path peak
    peak_idx = np.argmax(np.abs(ir[i, :zoom_samples]))
    peak_time = time_axis[peak_idx]
    peak_val = ir[i, peak_idx]
    ax.plot(peak_time, peak_val, "ro", markersize=4)
    ax.annotate(f"Direct: {peak_time:.2f} ms", xy=(peak_time, peak_val), xytext=(peak_time + 1.5, peak_val * 0.9),
                arrowprops=dict(arrowstyle="->", color="red", lw=0.8), fontsize=8)

axes[-1].set_xlabel("Time [ms] (relative to RIR recording zero)")
plt.tight_layout()

plot_path = os.path.join(out_dir, "dechorate_representative_mic_waveforms.png")
fig.savefig(plot_path, dpi=150)
plt.close(fig)
print(f"Saved representative microphone waveforms to {plot_path}")

