import sys
sys.path.insert(0, r'c:\Users\Anay tare\Desktop\Batsight\src')
import numpy as np
from batsight.application.config import Settings
from batsight.application.services.measurement_service import MeasurementService
from batsight.signals.generation import generate_linear_sweep
from batsight.signals import SamplingFrequency

fs = SamplingFrequency(48000)
chirp = generate_linear_sweep(300, 4000, 1.0, fs, amplitude=0.8).samples

# Direct arrival at 0.1s (4800 samples), Echo at 0.11s (delay 0.01s -> 1.715m)
rec = np.zeros(48000 * 2)
rec[4800:4800+len(chirp)] += chirp
rec[5280:5280+len(chirp)] += 0.5 * chirp

service = MeasurementService(Settings.from_environment())
res = service.process_samples(
    rec, 48000.0,
    waveform='linear_sweep',
    duration_s=1.0,
    start_frequency_hz=300,
    end_frequency_hz=4000,
    speed_of_sound_m_s=343.0,
    window_length_samples=240,
    thr1=0.4,
    thr2=0.05
)

print('Direct lag (s):', res['direct_lag_s'])
print('Direct distance (m):', res['direct_distance_m'])
print('Echo count:', res['echo_count'])
for p in res['peaks']:
    print('  Peak:', p['lag_seconds'], 's, delay:', p['delay_from_direct_s'], 's, dist:', p['distance_m'], 'm, class:', p['classification'])
