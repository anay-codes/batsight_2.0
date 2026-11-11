import {isFiniteVec3, type Equipment, type PathRecord, type SceneDocument, type Vec3} from './sceneModel'

/** Canonical value emitted by SyntheticExperimentService's persisted result envelope. */
export const KNOWN_SYNTHETIC_GROUND_TRUTH_STATUS = 'known synthetic ground truth' as const

export interface ExperimentSnapshot {
  experiment_id: number
  name: string
  kind: string
  status: string
  classification: 'synthetic_forward_simulation'
  geometry_status: typeof KNOWN_SYNTHETIC_GROUND_TRUTH_STATUS
  estimated_geometry_available: false
  room_dimensions_m: Vec3
  speed_of_sound_m_s: number
  equipment: Equipment[]
  paths: PathRecord[]
  configuration: Record<string, unknown>
}

function record(value: unknown): value is Record<string, unknown> { return !!value && typeof value === 'object' && !Array.isArray(value) }
function finiteNumber(value: unknown): value is number { return typeof value === 'number' && Number.isFinite(value) }
function vec(value: unknown): value is Vec3 { return isFiniteVec3(value) }

export function parseSyntheticExperiment(experiment: {id:number;name:string;kind:string;status:string}, envelope: Record<string, unknown> | null): ExperimentSnapshot {
  if (experiment.kind !== 'synthetic_forward' || !record(envelope) || envelope.data_classification !== 'synthetic_forward_simulation' || envelope.geometry_status !== KNOWN_SYNTHETIC_GROUND_TRUTH_STATUS || envelope.is_room_reconstruction !== false || envelope.real_world_validation !== false) throw new Error('This result is not a supported synthetic-forward geometry result.')
  const result = envelope.result
  if (!record(result) || !record(result.room) || !record(result.configuration) || !Array.isArray(result.microphones) || !Array.isArray(result.microphone_results)) throw new Error('This experiment result does not contain the room, source, microphone, and path fields required for the 3D view.')
  const dimensions = result.room.dimensions_m
  const source = result.configuration.source_position_m
  const speed = result.room.speed_of_sound_m_s
  if (!vec(dimensions) || !vec(source) || !finiteNumber(speed)) throw new Error('Experiment geometry or speed-of-sound metadata is invalid.')
  const equipment: Equipment[] = [{id:'experiment-source',name:'Synthetic source',kind:'speaker',position_m:source,orientation_yaw_deg:0,visible:true}]
  const microphones = result.microphones.filter(record)
  if (microphones.length === 0 || microphones.some(m => !finiteNumber(m.index) || !vec(m.position_m))) throw new Error('Experiment microphone geometry is missing or invalid.')
  for (const microphone of microphones) equipment.push({id:`experiment-mic-${microphone.index}`,name:`Microphone ${Number(microphone.index)+1}`,kind:'microphone',position_m:microphone.position_m as Vec3,orientation_yaw_deg:0,visible:true})
  const micResults = result.microphone_results.filter(record)
  const paths: PathRecord[] = []
  for (const micResult of micResults) {
    if (!finiteNumber(micResult.microphone_index) || !vec(micResult.microphone_position_m) || !Array.isArray(micResult.paths)) continue
    for (const value of micResult.paths) {
      if (!record(value) || !finiteNumber(value.reflection_order) || !Array.isArray(value.reflection_sequence) || !vec(value.image_source_position_m) || !finiteNumber(value.distance_m) || !finiteNumber(value.time_of_flight_s) || !finiteNumber(value.reflection_coefficient)) continue
      paths.push({reflection_order:value.reflection_order,reflection_sequence:value.reflection_sequence.filter(x=>typeof x==='string') as string[],image_source_position_m:value.image_source_position_m,path_length_m:value.distance_m,time_of_flight_s:value.time_of_flight_s,reflection_coefficient:value.reflection_coefficient,microphone_index:micResult.microphone_index,microphone_position_m:micResult.microphone_position_m,source_position_m:source,provenance:'synthetic_experiment_simulated'})
    }
  }
  if (!paths.some(path=>path.reflection_order===0)) throw new Error('Experiment result has no direct path to visualize.')
  return {experiment_id:experiment.id,name:experiment.name,kind:experiment.kind,status:experiment.status,classification:'synthetic_forward_simulation',geometry_status:KNOWN_SYNTHETIC_GROUND_TRUTH_STATUS,estimated_geometry_available:false,room_dimensions_m:dimensions,speed_of_sound_m_s:speed,equipment,paths,configuration:result.configuration}
}

export function editableSceneFromExperiment(snapshot: ExperimentSnapshot): SceneDocument {
  return {schema_version:1,coordinate_convention:'corner_origin_x_length_y_width_z_height',unit:'m',room_dimensions_m:[...snapshot.room_dimensions_m],speed_of_sound_m_s:snapshot.speed_of_sound_m_s,equipment:snapshot.equipment.map(item=>({...item,position_m:[...item.position_m] as Vec3}))}
}
