export const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? (typeof window !== 'undefined' ? `http://${window.location.hostname}:8000` : 'http://127.0.0.1:8000')).replace(/\/$/, '')

export interface Project { id: number; name: string; description: string | null; metadata: Record<string, unknown>; created_at: string; updated_at: string }
export interface Recording { id: number; project_id: number | null; name: string; description: string | null; original_filename: string; file_size_bytes: number; sample_rate_hz: number; channel_count: number; sample_count: number; duration_s: number; metadata: Record<string, unknown>; created_at: string }
export interface Experiment { id: number; project_id: number; name: string; kind: string; status: 'pending'|'running'|'completed'|'failed'; configuration: Record<string, unknown>; error_message: string|null; created_at: string; updated_at: string }
export interface Health { application: string; version: string; backend_status: string; database_status: string }
export interface RecordingAnalysis {
  recording_id:string; channel_index:number; sample_rate_hz:number; channel_count:number; sample_count:number; duration_s:number;
  amplitude_statistics:{minimum:number;maximum:number;mean:number;rms:number;amplitude_units:string};
  matched_filter:{correlation_convention:string;normalization:'reference_energy'|'none';reference_sample_count:number;curve:{time_s:number;value:number}[];peak_detection:{window_length_samples:number;thr1:number;thr2:number;accepted_peak_count:number;threshold_rejection_reasons_available:boolean};peaks:{correlation_sample_index:number;lag_samples:number;lag_seconds:number;amplitude:number;classification:'unclassified_correlation_peak'}[];direct_or_echo_classification_available:boolean};
  spectrogram:{frequencies_hz:number[];times_s:number[];magnitude_db_re_1_sample_amplitude:number[][];window:string;nperseg:number;noverlap:number;time_bin_count_is_decimated:boolean};
  provenance:string;
}
export interface SimulatedPath { reflection_order:number; reflection_sequence:string[]; image_source_position_m:[number,number,number]; path_length_m:number; time_of_flight_s:number; reflection_coefficient:number; reflection_point_m:[number,number,number]|null; finite_wall_bounce_valid:boolean|null }
export interface SimulationPaths { room_dimensions_m:[number,number,number]; source_position_m:[number,number,number]; speed_of_sound_m_s:number; max_reflection_order:number; microphone_paths:{microphone_index:number;microphone_position_m:[number,number,number];paths:SimulatedPath[]}[]; provenance:string; model_description:string }
export interface RecordingSession { session_id:string; project_id:number; name:string; provenance:'synthetic'|'imported_real_multichannel'|'laptop_single_device'; status:string; calibration:Record<string,any>; analysis_configuration:Record<string,any>; recordings:SessionRecordingFile[]; latest_extraction_id:string|null; created_at:string }
export interface SessionRecordingFile { recording_id:number; filename:string; sample_rate_hz:number; channel_count:number; duration_s:number; recording_start_time_s:number|null; channel_mapping:{channel_index:number;microphone_id:string}[]; event_ids:string[]|null }
export interface SessionValidation { session_id:string; valid:boolean; errors:{code:string;message:string;field:string|null}[]; warnings:{code:string;message:string;field:string|null}[]; synchronization_interpretation:string }
export interface SessionExtraction { session_id:string; extraction_id:string; status:'queued'|'running'|'completed'|'failed'; error_message:string|null; result:Record<string,any>|null; created_at:string; completed_at:string|null }
export interface EchoPeak { correlation_sample_index:number; lag_samples:number; lag_seconds:number; amplitude:number; delay_from_direct_s:number; distance_m:number; path_length_m:number; classification:'direct_path'|'echo'|'pre_trigger' }
export interface MeasurementProcessResult { sample_rate_hz:number; duration_s:number; speed_of_sound_m_s:number; direct_lag_s:number|null; direct_distance_m:number|null; peaks:EchoPeak[]; echo_count:number; closest_reflector_m:number|null; farthest_reflector_m:number|null; provenance:string }
export interface MeasurementRecord { id:number; project_id:number|null; name:string; description:string|null; chirp_config:Record<string,any>; speed_of_sound_m_s:number; direct_lag_s:number|null; direct_distance_m:number|null; echo_candidates:EchoPeak[]; echo_count:number; closest_reflector_m:number|null; farthest_reflector_m:number|null; scan_angle_deg:number|null; created_at:string }
export interface RoomReconstruction { estimated_dimensions_m:[number,number,number]; length_x_m:number; width_y_m:number; height_z_m:number; floor_area_m2:number; room_volume_m3:number; device_position_m:[number,number,number]; wall_distances:{x_min:number;x_max:number;y_min:number;y_max:number;z_min:number;z_max:number}; echo_distances_used:number[]; method:string; confidence:string }
export interface SavedRoom { id:number; project_id:number|null; name:string; description:string|null; length_x_m:number; width_y_m:number; height_z_m:number; floor_area_m2:number; room_volume_m3:number; device_position_m:[number,number,number]; wall_distances:Record<string,number>; obstacles:Array<{direction:string;distance_m:number;label?:string}>; scan_metadata:Record<string,any>; created_at:string; updated_at:string }

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init)
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`
    try { const body = await response.json(); const detail = body.detail; message = typeof detail === 'string' ? detail : detail?.message ?? (detail === undefined ? message : JSON.stringify(detail)) } catch { /* Non-JSON response */ }
    throw new Error(message)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export const api = {
  health: () => request<Health>('/api/health'),
  info: () => request<{ application: string; version: string; python_version: string; capabilities: Record<string,string>; storage: Record<string,string|number> }>('/api/system/info'),
  projects: () => request<Project[]>('/api/projects'),
  project: (id: number) => request<Project>(`/api/projects/${id}`),
  createProject: (body: {name:string;description:string|null}) => request<Project>('/api/projects', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({...body,metadata:{}})}),
  deleteProject: (id: number) => request<void>(`/api/projects/${id}`, {method:'DELETE'}),
  recordings: (projectId?: number) => request<Recording[]>(`/api/recordings${projectId ? `?project_id=${projectId}` : ''}`),
  uploadRecording: (file: File, name: string, projectId?: number) => { const data = new FormData(); data.set('file',file); data.set('name',name); data.set('metadata_json','{}'); if(projectId) data.set('project_id',String(projectId)); return request<Recording>('/api/recordings',{method:'POST',body:data}) },
  deleteRecording: (id:number) => request<void>(`/api/recordings/${id}`,{method:'DELETE'}),
  audioUrl: (id:number) => `${API_BASE}/api/recordings/${id}/audio`,
  analyze: (id:number, body: Record<string,unknown>) => request<RecordingAnalysis>(`/api/recordings/${id}/analysis`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),
  waveform: async (body: Record<string,unknown>) => { const response = await fetch(`${API_BASE}/api/signals/waveforms`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}); if(!response.ok){let message=`${response.status} ${response.statusText}`;try{message=(await response.json()).detail??message}catch{};throw new Error(message)}; return {blob:await response.blob(), sampleRate:Number(response.headers.get('X-Audio-Sample-Rate-Hz')), count:Number(response.headers.get('X-Audio-Sample-Count')), duration:Number(response.headers.get('X-Audio-Duration-S'))} },
  experiments: (projectId?:number) => request<Experiment[]>(`/api/experiments${projectId?`?project_id=${projectId}`:''}`),
  createExperiment: (body:Record<string,unknown>) => request<Experiment>('/api/experiments',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),
  runExperiment: (id:number) => request<{experiment_id:number;status:string;message:string}>(`/api/experiments/${id}/run`,{method:'POST'}),
  experiment: (id:number) => request<Experiment>(`/api/experiments/${id}`),
  experimentResults: (id:number) => request<{experiment_id:number;result:Record<string,any>|null}>(`/api/experiments/${id}/results`),
  simulationPaths: (body:Record<string,unknown>) => request<SimulationPaths>('/api/simulation/paths',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),
  recordingSessions: (projectId?:number) => request<RecordingSession[]>(`/api/v1/recording-sessions${projectId?`?project_id=${projectId}`:''}`),
  recordingSession: (id:string) => request<RecordingSession>(`/api/v1/recording-sessions/${id}`),
  createRecordingSession: (body:Record<string,unknown>) => request<RecordingSession>('/api/v1/recording-sessions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),
  updateRecordingSessionMetadata: (id:string,body:Record<string,unknown>) => request<RecordingSession>(`/api/v1/recording-sessions/${id}/metadata`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),
  attachSessionRecording: (id:string,body:Record<string,unknown>) => request<RecordingSession>(`/api/v1/recording-sessions/${id}/recordings`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),
  validateRecordingSession: (id:string) => request<SessionValidation>(`/api/v1/recording-sessions/${id}/validate`,{method:'POST'}),
  runSessionExtraction: (id:string) => request<{session_id:string;extraction_id:string;status:'queued';message:string}>(`/api/v1/recording-sessions/${id}/extractions`,{method:'POST'}),
  sessionExtraction: (id:string,extractionId:string) => request<SessionExtraction>(`/api/v1/recording-sessions/${id}/extractions/${extractionId}`),
  latestSessionResult: (id:string) => request<SessionExtraction|null>(`/api/v1/recording-sessions/${id}/results`),
  processMeasurement: (body:Record<string,unknown>) => request<MeasurementProcessResult>('/api/measurements/process',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),
  processMeasurementUpload: (file:File|Blob,options?:Record<string,string|number>) => { const data=new FormData(); data.append('file',file,'measurement.wav'); if(options){for(const [k,v] of Object.entries(options)){data.append(k,String(v))}} return request<MeasurementProcessResult>('/api/measurements/process-upload',{method:'POST',body:data}) },
  measurements: (projectId?:number) => request<MeasurementRecord[]>(`/api/measurements${projectId?`?project_id=${projectId}`:''}`),
  measurement: (id:number) => request<MeasurementRecord>(`/api/measurements/${id}`),
  createMeasurement: (body:Record<string,unknown>) => request<MeasurementRecord>('/api/measurements',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),
  deleteMeasurement: (id:number) => request<void>(`/api/measurements/${id}`,{method:'DELETE'}),
  reconstructRoom: (body:{measurement_id?:number;distances_m?:number[];default_ceiling_height_m?:number;centered_assumption?:boolean}) => request<RoomReconstruction>('/api/measurements/reconstruct-room',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),
  rooms: (projectId?:number) => request<SavedRoom[]>(`/api/rooms${projectId?`?project_id=${projectId}`:''}`),
  room: (id:number) => request<SavedRoom>(`/api/rooms/${id}`),
  createRoom: (body:Record<string,unknown>) => request<SavedRoom>('/api/rooms',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),
  updateRoom: (id:number,body:Record<string,unknown>) => request<SavedRoom>(`/api/rooms/${id}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),
  deleteRoom: (id:number) => request<void>(`/api/rooms/${id}`,{method:'DELETE'}),
}

export function formatDuration(seconds:number) { if (!Number.isFinite(seconds)) return '—'; const m=Math.floor(seconds/60); const s=seconds%60; return `${m}:${s.toFixed(1).padStart(4,'0')}` }
export function formatBytes(bytes:number) { if(bytes<1024)return `${bytes} B`; if(bytes<1024**2)return `${(bytes/1024).toFixed(1)} KB`; return `${(bytes/1024**2).toFixed(2)} MB` }
