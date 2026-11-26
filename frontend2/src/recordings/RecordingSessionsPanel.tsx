import { useEffect, useMemo, useState } from 'react'
import { Activity, AudioLines, Check, FileUp, RefreshCw, Save, Upload } from 'lucide-react'
import { api, type RecordingSession, type SessionExtraction, type SessionValidation } from '../api'
import { defaultSessionAnalysis, emptyCalibrationTemplate, parseJsonObject } from './sessionMetadata'

type Props = { projectId?: number; refreshKey: number }

export function RecordingSessionsPanel({ projectId, refreshKey }: Props) {
  const [sessions, setSessions] = useState<RecordingSession[]>([])
  const [selected, setSelected] = useState('')
  const [sessionName, setSessionName] = useState('Calibrated multichannel session')
  const [provenance, setProvenance] = useState<'synthetic'|'imported_real_multichannel'|'laptop_single_device'>('imported_real_multichannel')
  const [calibrationText, setCalibrationText] = useState(emptyCalibrationTemplate)
  const [analysisText, setAnalysisText] = useState(JSON.stringify(defaultSessionAnalysis, null, 2))
  const [recordingId, setRecordingId] = useState<number>()
  const [recordingStart, setRecordingStart] = useState('')
  const [mapping, setMapping] = useState<Record<number,string>>({})
  const [selectedEventIds, setSelectedEventIds] = useState<string[]>([])
  const [validation, setValidation] = useState<SessionValidation|null>(null)
  const [extraction, setExtraction] = useState<SessionExtraction|null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const active = sessions.find(item => item.session_id === selected)

  async function loadSessions(keepSelection = true) {
    if (!projectId) { setSessions([]); setSelected(''); return }
    const rows = await api.recordingSessions(projectId)
    setSessions(rows)
    if (!keepSelection || !rows.some(row => row.session_id === selected)) setSelected(rows[0]?.session_id ?? '')
  }
  useEffect(() => { loadSessions().catch(e => setError(e.message)) }, [projectId, refreshKey])
  useEffect(() => {
    if (!selected) { setExtraction(null); setValidation(null); return }
    api.recordingSession(selected).then(row => {
      setCalibrationText(JSON.stringify(row.calibration, null, 2))
      setAnalysisText(JSON.stringify(row.analysis_configuration, null, 2))
      setProvenance(row.provenance)
      return api.latestSessionResult(selected)
    }).then(setExtraction).catch(e => setError(e.message))
  }, [selected])
  useEffect(() => {
    if (!extraction || !['queued','running'].includes(extraction.status)) return
    const timer = window.setTimeout(() => api.sessionExtraction(extraction.session_id, extraction.extraction_id).then(setExtraction).catch(e => setError(e.message)), 1000)
    return () => window.clearTimeout(timer)
  }, [extraction])
  const calibration = useMemo(() => { try { return parseJsonObject(calibrationText) } catch { return null } }, [calibrationText])
  const microphones = Array.isArray(calibration?.microphones) ? calibration.microphones as {microphone_id:string}[] : []

  async function createSession() {
    if (!projectId) { setError('Select a project before creating a session.'); return }
    setBusy(true); setError(''); setMessage('')
    try {
      const row = await api.createRecordingSession({ project_id: projectId, name: sessionName, provenance, calibration: parseJsonObject(calibrationText), analysis_configuration: parseJsonObject(analysisText) })
      await loadSessions(false); setSelected(row.session_id); setMessage('Draft session created. Complete metadata and attach WAV recordings.')
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  async function importWav(file?: File) {
    if (!file) return
    if (!projectId) { setError('Select a project before importing a WAV.'); return }
    setBusy(true); setError(''); setMessage('')
    try {
      const row = await api.uploadRecording(file, file.name, projectId)
      setRecordingId(row.id)
      setSelectedEventIds([])
      setMapping(Object.fromEntries(Array.from({length: row.channel_count}, (_, i) => [i, ''])))
      setMessage(`Imported ${row.original_filename}: ${row.channel_count} channel(s), ${row.sample_rate_hz} Hz. Map every channel before attaching.`)
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  async function attachRecording() {
    if (!selected || !recordingId) return
    const record = await api.recordings(projectId).then(rows => rows.find(row => row.id === recordingId))
    if (!record) { setError('Imported recording is no longer available.'); return }
    const channel_mapping = Array.from({length: record.channel_count}, (_, channel_index) => ({channel_index, microphone_id: mapping[channel_index] ?? ''}))
    setBusy(true); setError('')
    try {
      const row = await api.attachSessionRecording(selected, { recording_id: recordingId, recording_start_time_s: recordingStart === '' ? null : Number(recordingStart), channel_mapping, ...(selectedEventIds.length ? {event_ids:selectedEventIds} : {}) })
      setSessions(old => old.map(item => item.session_id === row.session_id ? row : item)); setRecordingId(undefined); setMessage('Recording attached; no resampling or channel inference was performed.')
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  async function saveMetadata() {
    if (!selected) return
    setBusy(true); setError('')
    try {
      const row = await api.updateRecordingSessionMetadata(selected, { calibration: parseJsonObject(calibrationText), analysis_configuration: parseJsonObject(analysisText), provenance })
      setSessions(old => old.map(item => item.session_id === row.session_id ? row : item)); setMessage('Session metadata saved.')
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  async function validateSession() {
    if (!selected) return
    setBusy(true); setError('')
    try { setValidation(await api.validateRecordingSession(selected)); setMessage('Validation completed.') } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  async function runExtraction() {
    if (!selected) return
    setBusy(true); setError('')
    try { const queued = await api.runSessionExtraction(selected); setExtraction(await api.sessionExtraction(selected, queued.extraction_id)); setMessage('TOA extraction queued.') }
    catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  const result = extraction?.result
  const pairs = Array.isArray(result?.pair_results) ? result.pair_results as any[] : []
  const recordings = Array.isArray(active?.recordings) ? active.recordings : []
  return <section className="panel recording-sessions-panel">
    <div className="table-toolbar"><div><h2>Calibrated multichannel sessions</h2><p>Group imported WAVs with explicit calibration, timing reference, and channel mapping.</p></div><span className="pill neutral">API v1</span></div>
    {!projectId && <div className="notice warning"><div><b>Select a project</b><span>Recording sessions are scoped to the selected project.</span></div></div>}
    {error && <div className="session-message error" role="alert">{error}</div>}{message && <div className="session-message" role="status">{message}</div>}
    <div className="session-create-grid">
      <label className="field"><span>Session name</span><input value={sessionName} onChange={e=>setSessionName(e.target.value)}/></label>
      <label className="field"><span>Provenance</span><select value={provenance} onChange={e=>setProvenance(e.target.value as typeof provenance)}><option value="imported_real_multichannel">Imported real multichannel</option><option value="synthetic">Synthetic</option><option value="laptop_single_device">Laptop single device (not accepted for calibrated array analysis)</option></select></label>
      <label className="field session-json"><span>Calibration metadata JSON · schema 1.0 · SI units · use null/empty values until measured</span><textarea rows={11} value={calibrationText} onChange={e=>setCalibrationText(e.target.value)} spellCheck={false}/><span className="session-file-label"><FileUp size={14}/> Load JSON file<input type="file" accept="application/json,.json" onChange={async e=>{const file=e.target.files?.[0];if(file)setCalibrationText(await file.text())}}/></span></label>
      <label className="field session-json"><span>Analysis configuration JSON</span><textarea rows={11} value={analysisText} onChange={e=>setAnalysisText(e.target.value)} spellCheck={false}/></label>
    </div>
    <div className="session-actions"><button className="button primary" onClick={createSession} disabled={busy||!projectId}><Check size={15}/> Create draft session</button>
      <label className="button secondary"><Upload size={15}/> Import WAV<input type="file" accept=".wav,audio/wav" onChange={e=>importWav(e.target.files?.[0])} hidden/></label>
      {sessions.length>0&&<label className="field session-select"><span>Session</span><select value={selected} onChange={e=>setSelected(e.target.value)}>{sessions.map(s=><option key={s.session_id} value={s.session_id}>{s.name} · {s.status}</option>)}</select></label>}
    </div>
    {recordingId!==undefined&&<div className="session-attach-box"><b>Map imported recording channels</b><div className="session-mapping-grid">{Object.keys(mapping).map(key=>{const index=Number(key);return <label className="field" key={key}><span>Channel {index}</span><select value={mapping[index]} onChange={e=>setMapping({...mapping,[index]:e.target.value})}><option value="">Choose calibrated microphone…</option>{microphones.map(m=><option key={m.microphone_id} value={m.microphone_id}>{m.microphone_id}</option>)}</select></label>})}<label className="field"><span>Included source events (empty means all session events)</span><select multiple value={selectedEventIds} onChange={e=>setSelectedEventIds(Array.from(e.target.selectedOptions, option=>option.value))}>{(Array.isArray(calibration?.events)?calibration.events as {event_id:string}[]:[]).map(event=><option key={event.event_id} value={event.event_id}>{event.event_id}</option>)}</select></label></div><div className="session-actions"><label className="field"><span>Recording start time (s, shared reference)</span><input type="number" step="any" value={recordingStart} onChange={e=>setRecordingStart(e.target.value)}/></label><button className="button primary" disabled={busy||!selected} onClick={attachRecording}>Attach mapping</button></div></div>}
    {active&&<>
      <div className="session-actions session-secondary-actions"><button className="button secondary" onClick={saveMetadata} disabled={busy}><Save size={15}/> Save metadata</button><button className="button secondary" onClick={validateSession} disabled={busy}><Check size={15}/> Validate</button><button className="button primary" onClick={runExtraction} disabled={busy||!validation?.valid}><Activity size={15}/> Run TOA extraction</button><button className="button secondary" onClick={()=>loadSessions()} disabled={busy}><RefreshCw size={15}/> Refresh</button><span className={`pill ${active.status}`}>{active.status}</span></div>
      <div className="notice warning"><div><b>Synchronization is metadata asserted only</b><span>BatSight does not independently verify shared clocks. Extraction returns direct-path candidates and unclassified echo candidates; it does not estimate room geometry.</span></div></div>
      {validation&&<div className={`session-validation ${validation.valid?'valid':'invalid'}`}><b>{validation.valid?'Session valid':'Session has required corrections'}</b><small>Synchronization interpretation: {validation.synchronization_interpretation}</small>{validation.errors.map((issue,i)=><p key={`e${i}`}>Error · {issue.field??'session'} · {issue.message}</p>)}{validation.warnings.map((issue,i)=><p key={`w${i}`}>Note · {issue.field??'session'} · {issue.message}</p>)}</div>}
      <div className="session-attached-list"><b>Attached WAVs</b>{recordings.length?recordings.map(r=><div key={r.recording_id}><AudioLines size={14}/><span>{r.filename} · {r.sample_rate_hz} Hz · {r.channel_count} channels · start {r.recording_start_time_s??'—'} s</span><small>{r.channel_mapping.map(m=>`ch ${m.channel_index} → ${m.microphone_id}`).join(' · ')}</small></div>):<small>No WAVs attached.</small>}</div>
      {extraction&&<div className="session-result"><h3>Extraction · <span className={`pill ${extraction.status}`}>{extraction.status}</span></h3>{extraction.error_message&&<div className="session-message error">{extraction.error_message}</div>}
        {result&&<><div className="result-badges"><span className="pill neutral">{String(result.data_provenance)}</span><span className="pill warning-pill">Estimated room geometry unavailable</span><span className="pill neutral">{result.summary?.missing_direct_path_count??0} missing direct paths</span><span className="pill neutral">{result.summary?.unclassified_echo_candidate_count??0} unclassified echoes</span></div>
          {(result.recordings??[]).map((r:any)=><div className="session-waveform" key={r.recording_id}><b>{r.filename} · bounded waveform envelope (preview)</b>{(r.waveform_preview?.channels??[]).map((channel:any)=><div key={channel.channel_index}><small>Channel {channel.channel_index}</small><div className="waveform-envelope">{channel.envelope.map((point:any,i:number)=><i key={i} style={{left:`${i/Math.max(1,channel.envelope.length)*100}%`,top:`${50-point.maximum*45}%`,height:`${Math.max(1,(point.maximum-point.minimum)*45)}%`}}/>)}</div></div>)}</div>)}
          <div className="table-scroll"><table><thead><tr><th>Microphone</th><th>Event</th><th>Expected direct (s)</th><th>Direct status / arrival (s)</th><th>Echo candidates</th><th>Rejected peaks</th></tr></thead><tbody>{pairs.map((pair:any,i:number)=><tr key={`${pair.recording_id}-${pair.microphone_id}-${pair.event_id}-${i}`}><td>{pair.microphone_id}</td><td>{pair.event_id}</td><td>{Number(pair.expected_direct_time_s).toFixed(6)}</td><td>{pair.direct_arrival?`candidate · ${Number(pair.direct_arrival.arrival_time_s).toFixed(6)}`:'missing'}</td><td>{(pair.echo_candidates??[]).map((e:any)=>`${Number(e.arrival_time_s).toFixed(6)} s (${Number(e.amplitude).toPrecision(3)})`).join(', ')||'—'}</td><td>{(pair.rejected_peaks??[]).length}</td></tr>)}</tbody></table></div>
          <details className="session-audit"><summary>Rejected peak and diagnostic audit</summary><pre>{JSON.stringify({pairs: pairs.map((p:any)=>({microphone_id:p.microphone_id,event_id:p.event_id,rejected_peaks:p.rejected_peaks,warnings:p.warnings,robust_noise_scale:p.robust_noise_scale})),observations:result.toa_observations},null,2)}</pre></details>
        </>}
      </div>}
    </>}
  </section>
}
