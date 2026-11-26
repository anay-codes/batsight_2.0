export type Vec3 = [number, number, number]
export type EquipmentKind = 'speaker' | 'microphone'
export interface Equipment {
  id: string
  name: string
  kind: EquipmentKind
  position_m: Vec3
  orientation_yaw_deg: number
  visible: boolean
}
export interface SceneDocument {
  schema_version: 1
  coordinate_convention: 'corner_origin_x_length_y_width_z_height'
  unit: 'm'
  room_dimensions_m: Vec3
  speed_of_sound_m_s: number
  equipment: Equipment[]
}
export interface PathRecord {
  reflection_order: number
  reflection_sequence: string[]
  image_source_position_m: Vec3
  path_length_m: number
  time_of_flight_s: number
  reflection_coefficient: number
  reflection_point_m?: Vec3 | null
  finite_wall_bounce_valid?: boolean | null
  microphone_index: number
  microphone_position_m: Vec3
  source_position_m: Vec3
  provenance: 'visualization_only_simulated' | 'synthetic_experiment_simulated'
}

export function isFiniteVec3(value: unknown): value is Vec3 {
  return Array.isArray(value) && value.length === 3 && value.every(x => typeof x === 'number' && Number.isFinite(x))
}

export function validRoomDimensions(value: unknown): value is Vec3 {
  return isFiniteVec3(value) && value.every(x => x >= 0.5 && x <= 100)
}

export function isStrictlyInside(point: Vec3, dimensions: Vec3, margin = 0): boolean {
  return point.every((coordinate, axis) => coordinate > margin && coordinate < dimensions[axis] - margin)
}

export function clampInside(point: Vec3, dimensions: Vec3, margin = 0.05): Vec3 {
  const safeMargin = Math.min(margin, ...dimensions.map(d => d / 4))
  return point.map((coordinate, axis) => Math.max(safeMargin, Math.min(dimensions[axis] - safeMargin, coordinate))) as Vec3
}

export function createDefaultScene(): SceneDocument {
  return {schema_version: 1, coordinate_convention: 'corner_origin_x_length_y_width_z_height', unit: 'm', room_dimensions_m: [6, 5, 3], speed_of_sound_m_s: 343, equipment: [
    {id: 'speaker-1', name: 'Speaker 1', kind: 'speaker', position_m: [1.25, 1.1, 1.25], orientation_yaw_deg: 0, visible: true},
    {id: 'microphone-1', name: 'Microphone 1', kind: 'microphone', position_m: [4.6, 3.6, 1.35], orientation_yaw_deg: 0, visible: true},
  ]}
}

export function parseSceneDocument(serialized: string | null): SceneDocument {
  if (!serialized) return createDefaultScene()
  try {
    const value = JSON.parse(serialized) as Partial<SceneDocument>
    if (value.schema_version !== 1 || value.coordinate_convention !== 'corner_origin_x_length_y_width_z_height' || value.unit !== 'm' || !validRoomDimensions(value.room_dimensions_m) || typeof value.speed_of_sound_m_s !== 'number' || !Number.isFinite(value.speed_of_sound_m_s) || value.speed_of_sound_m_s <= 0 || !Array.isArray(value.equipment)) return createDefaultScene()
    const ids = new Set<string>()
    const equipment = value.equipment.filter(isEquipment).filter(item => { if (ids.has(item.id)) return false; ids.add(item.id); return true }).map(item => ({...item, position_m: clampInside(item.position_m, value.room_dimensions_m as Vec3)}))
    return {schema_version: 1, coordinate_convention: 'corner_origin_x_length_y_width_z_height', unit: 'm', room_dimensions_m: value.room_dimensions_m, speed_of_sound_m_s: value.speed_of_sound_m_s, equipment}
  } catch {
    return createDefaultScene()
  }
}

export function serializeScene(scene: SceneDocument): string {
  validateScene(scene)
  return JSON.stringify(scene)
}

export function validateScene(scene: SceneDocument): void {
  if (!validRoomDimensions(scene.room_dimensions_m)) throw new Error('Room dimensions must be finite and between 0.5 m and 100 m.')
  if (!Number.isFinite(scene.speed_of_sound_m_s) || scene.speed_of_sound_m_s <= 0) throw new Error('Speed of sound must be a finite positive value in m/s.')
  const ids = new Set<string>()
  for (const item of scene.equipment) {
    if (!isEquipment(item)) throw new Error('Invalid equipment record.')
    if (ids.has(item.id)) throw new Error(`Equipment IDs must be unique: ${item.id}`)
    ids.add(item.id)
    if (!isStrictlyInside(item.position_m, scene.room_dimensions_m)) throw new Error(`${item.name} must be strictly inside the room.`)
  }
}

function isEquipment(value: unknown): value is Equipment {
  if (!value || typeof value !== 'object') return false
  const item = value as Partial<Equipment>
  return typeof item.id === 'string' && item.id.length > 0 && typeof item.name === 'string' && (item.kind === 'speaker' || item.kind === 'microphone') && isFiniteVec3(item.position_m) && typeof item.orientation_yaw_deg === 'number' && Number.isFinite(item.orientation_yaw_deg) && typeof item.visible === 'boolean'
}

export function reflectionPointFromImage(image: Vec3, receiver: Vec3, wallId: string, dimensions: Vec3): Vec3 | null {
  const match = /^(x|y|z)_(min|max)$/.exec(wallId)
  if (!match) return null
  const axis = match[1] === 'x' ? 0 : match[1] === 'y' ? 1 : 2
  const plane = match[2] === 'min' ? 0 : dimensions[axis]
  const delta = receiver[axis] - image[axis]
  if (Math.abs(delta) < 1e-12) return null
  const t = (plane - image[axis]) / delta
  if (t < 0 || t > 1) return null
  const point = image.map((value, index) => value + t * (receiver[index] - value)) as Vec3
  const tolerance = 1e-8
  if (!point.every((value, index) => index === axis ? Math.abs(value - plane) <= tolerance : value >= -tolerance && value <= dimensions[index] + tolerance)) return null
  point[axis] = plane
  return point
}
