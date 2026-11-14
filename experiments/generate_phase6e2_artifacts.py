import os
import sys
import numpy as np
import scipy.signal as sg
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

out_dir = "experiments/phase6e_results"
os.makedirs(out_dir, exist_ok=True)

# 1. Synthesize reference ESS probe according to author's stimulus.py
fs = 48000
n_seconds = 10
amplitude = 0.7
n_repetitions = 3
silence_at_start = 2
silence_at_end = 2
sweeprange = [100, 14000]

f1 = sweeprange[0]
f2 = sweeprange[1]
w1 = 2 * np.pi * f1 / fs
w2 = 2 * np.pi * f2 / fs
n_samples = n_seconds * fs
taxis = np.arange(0, n_samples, 1) / (n_samples - 1)
lw = np.log(w2 / w1)

sinsweep = amplitude * np.sin(w1 * (n_samples - 1) / lw * (np.exp(taxis * lw) - 1))

# Tapering as implemented in author's stimulus.py
taperStart = sg.windows.tukey(n_samples, 1/16)
taperEnding = sg.windows.tukey(n_samples, 1/128)
taperWindow = np.ones(n_samples)
taperWindow[0:int(n_samples/2)] = taperStart[0:int(n_samples/2)]
taperWindow[int(n_samples/2):] = taperEnding[int(n_samples/2):]
sinsweep = sinsweep * taperWindow

# Concatenate silence
zerostart = np.zeros(silence_at_start * fs)
zeroend = np.zeros(silence_at_end * fs)
single_cycle = np.concatenate([zerostart, sinsweep, zeroend])
full_signal = np.tile(single_cycle, n_repetitions)
time_axis = np.arange(len(full_signal)) / fs

print(f"Generated probe signal: shape={full_signal.shape}, duration={len(full_signal)/fs:.2f}s")

# 2. Generate Plot: Reference Loopback Waveform & Nominal Sweep Regions
fig, axes = plt.subplots(2, 1, figsize=(12, 6), sharex=True)

# Top: Waveform with regions
ax1 = axes[0]
ax1.plot(time_axis, full_signal, color='#1f77b4', lw=0.5, alpha=0.8, label="Nominal ESS Loopback Reference")
ax1.set_ylabel("Amplitude")
ax1.set_title("dEchorate ESS Probe Reference Model (3 Sweeps, 100 Hz - 14 kHz @ 48 kHz)")
ax1.grid(True, linestyle="--", alpha=0.5)

# Highlight sweep regions
sweep_windows = [(2, 12), (16, 26), (30, 40)]
colors = ['#ff7f0e', '#2ca02c', '#d62728']
for i, ((start, end), c) in enumerate(zip(sweep_windows, colors)):
    ax1.axvspan(start, end, color=c, alpha=0.2, label=f"Sweep {i+1} [{start}s - {end}s]")
    ax1.axvline(start, color=c, linestyle="--", alpha=0.8)
    ax1.axvline(end, color=c, linestyle="--", alpha=0.8)
ax1.legend(loc="upper right", framealpha=0.9)

# Bottom: Spectrogram
ax2 = axes[1]
f, t_spec, Sxx = sg.spectrogram(full_signal, fs, nperseg=2048, noverlap=1024)
im = ax2.pcolormesh(t_spec, f / 1000, 10 * np.log10(Sxx + 1e-12), shading='gouraud', cmap='inferno')
ax2.set_ylabel("Frequency [kHz]")
ax2.set_xlabel("Time [seconds]")
ax2.set_ylim([0, 24])
ax2.set_title("Spectrogram of Theoretical Reference Signal (Logarithmic Chirp Trajectory)")
plt.colorbar(im, ax=ax2, label="Power/Freq [dB/Hz]")

plt.tight_layout()
plot_path = os.path.join(out_dir, "dechorate_reference_loopback_and_sweeps.png")
fig.savefig(plot_path, dpi=150)
plt.close(fig)
print(f"Saved plot to {plot_path}")

