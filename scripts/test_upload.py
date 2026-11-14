import urllib.request, io, json
from scipy.signal import chirp
from scipy.io import wavfile
import numpy as np

fs = 48000
duration = 0.6
t = np.linspace(0, duration, int(fs * duration), endpoint=False)
ref = chirp(t, 1500, duration, 4000, method='linear')

rec = np.zeros(int(fs * 1.0), dtype=np.float32)
rec[int(fs * 0.04):int(fs * 0.04) + len(ref)] += 1.0 * ref.astype(np.float32)
rec[int(fs * 0.05399):int(fs * 0.05399) + len(ref)] += 0.25 * ref.astype(np.float32)

buf = io.BytesIO()
wavfile.write(buf, fs, (rec * 32767).astype(np.int16))
wav_bytes = buf.getvalue()

boundary = '----WebKitFormBoundaryXYZ123'
parts = [
    f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="scan.wav"\r\nContent-Type: audio/wav\r\n\r\n'.encode(),
    wav_bytes,
    f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="duration_s"\r\n\r\n0.6\r\n'.encode(),
    f'--{boundary}\r\nContent-Disposition: form-data; name="start_frequency_hz"\r\n\r\n1500\r\n'.encode(),
    f'--{boundary}\r\nContent-Disposition: form-data; name="end_frequency_hz"\r\n\r\n4000\r\n'.encode(),
    f'--{boundary}--\r\n'.encode(),
]
body = b''.join(parts)

req = urllib.request.Request(
    'http://127.0.0.1:8000/api/measurements/process-upload',
    data=body,
    headers={'Content-Type': f'multipart/form-data; boundary={boundary}'}
)

res = urllib.request.urlopen(req)
data = json.loads(res.read().decode())
echoes = [p for p in data['peaks'] if p['classification'] == 'echo' and p['distance_m'] > 0.35]
print('Direct lag:', data['direct_lag_s'], 's')
for e in echoes[:5]:
    print(f"Detected distance: {e['distance_m']} m | amplitude: {e['amplitude']}")
