/** Small strict parsing helpers for the editable recording-session JSON contract. */
export function parseJsonObject(text: string): Record<string, unknown> {
  const value: unknown = JSON.parse(text)
  if (value === null || Array.isArray(value) || typeof value !== 'object') {
    throw new Error('Expected a JSON object.')
  }
  return value as Record<string, unknown>
}

export const emptyCalibrationTemplate = JSON.stringify({
  schema_version: '1.0', coordinate_frame: null, position_unit: null,
  time_unit: null, time_reference: null, sample_rate_hz: null,
  speed_of_sound_m_s: null,
  synchronization: { status: 'unknown', evidence_description: null },
  microphones: [], events: [],
}, null, 2)

export const defaultSessionAnalysis = {
  direct_tolerance_s: 0.002, minimum_echo_excess_delay_s: 0.0002,
  maximum_echo_excess_delay_s: 0.05, minimum_peak_separation_s: 0.00015,
  window_length_samples: 8, thr1: 0.9, thr2: 0.02,
  minimum_peak_prominence: 0, polarity: 'either', timing_uncertainty_s: null,
}
