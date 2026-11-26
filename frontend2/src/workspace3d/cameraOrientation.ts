import type { Vec3 } from './sceneModel'

export type CameraView = 'iso' | 'top' | 'front' | 'side'
export interface CameraOrientation {
  position: Vec3
  up: Vec3
  target: Vec3
}

/** Return a stable camera frame for the workspace's corner-origin XYZ scene. */
export function cameraOrientation(view: CameraView, target: Vec3, radius: number): CameraOrientation {
  const offsets: Record<CameraView, Vec3> = {
    iso: [1.25, -1.5, 1.2],
    top: [0, 0, 2],
    front: [0, -2, 0],
    side: [2, 0, 0],
  }
  const offset = offsets[view]
  const scale = radius / 2.5
  return {
    position: [target[0] + offset[0] * scale, target[1] + offset[1] * scale, target[2] + offset[2] * scale],
    up: view === 'top' ? [0, 1, 0] : [0, 0, 1],
    target: [...target],
  }
}
