import { describe, expect, it } from 'vitest'
import { emptyCalibrationTemplate, parseJsonObject } from './sessionMetadata'

describe('recording-session metadata helpers', () => {
  it('starts with explicit unknown calibration values rather than fabricated values', () => {
    const value = parseJsonObject(emptyCalibrationTemplate)
    expect(value.sample_rate_hz).toBeNull()
    expect(value.microphones).toEqual([])
    expect(value.synchronization).toEqual({ status: 'unknown', evidence_description: null })
  })
  it('rejects JSON arrays and primitives for object contracts', () => {
    expect(() => parseJsonObject('[]')).toThrow('Expected a JSON object')
    expect(() => parseJsonObject('null')).toThrow('Expected a JSON object')
  })
})
