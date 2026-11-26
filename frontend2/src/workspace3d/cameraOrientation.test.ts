import { describe, expect, it } from 'vitest'
import { cameraOrientation } from './cameraOrientation'

describe('workspace camera orientation', () => {
  const center: [number, number, number] = [2, 1.5, 1.25]

  it('uses a nonparallel Y-up vector for the top view looking down Z', () => {
    const top = cameraOrientation('top', center, 5)
    expect(top.position).toEqual([2, 1.5, 5.25])
    expect(top.target).toEqual(center)
    expect(top.up).toEqual([0, 1, 0])
    expect(top.up).not.toEqual([0, 0, 1])
  })

  it('preserves Z-up for iso, front, and side views and aims at the room center', () => {
    for (const view of ['iso', 'front', 'side'] as const) {
      const orientation = cameraOrientation(view, center, 5)
      expect(orientation.up).toEqual([0, 0, 1])
      expect(orientation.target).toEqual(center)
      expect(orientation.position).not.toEqual(center)
    }
  })
})
