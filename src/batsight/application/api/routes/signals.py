"""Engineering waveform generation endpoints backed by BatSight signal modules."""

from fastapi import APIRouter, HTTPException, Response

from batsight.application.api.schemas.contracts import WaveformRequest
from batsight.application.services.waveform_service import WaveformService

router = APIRouter(prefix="/api/signals", tags=["signals"])


@router.post("/waveforms", summary="Generate a generic test waveform WAV", responses={200: {"content": {"audio/wav": {"schema": {"type": "string", "format": "binary"}}}}})
def generate_waveform(payload: WaveformRequest):
    if payload.waveform == "linear_sweep" and payload.sample_rate_hz / 2 <= max(payload.start_frequency_hz, payload.end_frequency_hz):
        raise HTTPException(422, "Waveform frequencies must be below the Nyquist frequency")
    if payload.waveform == "sine" and payload.start_frequency_hz >= payload.sample_rate_hz / 2:
        raise HTTPException(422, "Sine frequency must be below the Nyquist frequency")
    try:
        wav_bytes, sample_count, duration = WaveformService().generate_pcm16_wav(
            waveform=payload.waveform,
            sample_rate_hz=payload.sample_rate_hz,
            duration_s=payload.duration_s,
            start_frequency_hz=payload.start_frequency_hz,
            end_frequency_hz=payload.end_frequency_hz,
            amplitude=payload.amplitude,
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, str(exc)) from exc
    return Response(
        content=wav_bytes,
        media_type="audio/wav",
        headers={
            "X-Audio-Sample-Rate-Hz": str(payload.sample_rate_hz),
            "X-Audio-Sample-Count": str(sample_count),
            "X-Audio-Duration-S": str(duration),
            "X-Waveform-Convention": "generic_engineering_signal_not_paper_equation_10",
            "Content-Disposition": "inline",
        },
    )
