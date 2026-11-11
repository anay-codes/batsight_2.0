"""Thin signal-processing service facade over existing BatSight modules."""

from batsight.signals import (
    AudioSignal,
    KnownReferenceSignal,
    SamplingFrequency,
    detect_peaks,
    generate_linear_sweep,
    generate_sine_wave,
    matched_filter,
)
from batsight.signals.recording_analysis import (
    RecordingAnalysisConfig,
    analyze_multichannel_recording,
)


class SignalProcessingService:
    def generate_reference(self, *, waveform: str, sample_rate_hz: float,
                           duration_s: float, start_frequency_hz: float = 900.0,
                           end_frequency_hz: float = 11000.0,
                           amplitude: float = 0.8) -> KnownReferenceSignal:
        fs = SamplingFrequency(sample_rate_hz)
        if waveform == "sine":
            signal = generate_sine_wave(start_frequency_hz, duration_s, fs, amplitude=amplitude)
        elif waveform == "linear_sweep":
            signal = generate_linear_sweep(
                start_frequency_hz, end_frequency_hz, duration_s, fs, amplitude=amplitude
            )
        else:
            raise ValueError("waveform must be 'sine' or 'linear_sweep'")
        return KnownReferenceSignal(signal, f"generic engineering {waveform}")

    def matched_filter(self, recording: AudioSignal, reference: KnownReferenceSignal, **options):
        return matched_filter(recording, reference, **options)

    def detect_peaks(self, values, sampling_frequency: SamplingFrequency, **options):
        return detect_peaks(values, sampling_frequency, **options)

    def extract_toas(self, recording: AudioSignal, reference: KnownReferenceSignal,
                     calibrated_inputs, *, config: RecordingAnalysisConfig | None = None,
                     recording_start_time_s: float = 0.0):
        return analyze_multichannel_recording(
            recording, reference, calibrated_inputs,
            config=config or RecordingAnalysisConfig(),
            recording_start_time_s=recording_start_time_s,
        )
