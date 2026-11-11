export const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000').replace(/\/$/, '')

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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init)
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`
    try { const body = await response.json(); message = body.detail ?? message } catch { /* Non-JSON response */ }
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
}

export function formatDuration(seconds:number) { if (!Number.isFinite(seconds)) return '—'; const m=Math.floor(seconds/60); const s=seconds%60; return `${m}:${s.toFixed(1).padStart(4,'0')}` }
export function formatBytes(bytes:number) { if(bytes<1024)return `${bytes} B`; if(bytes<1024**2)return `${(bytes/1024).toFixed(1)} KB`; return `${(bytes/1024**2).toFixed(2)} MB` }
