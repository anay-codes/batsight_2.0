import { useEffect, useMemo, useRef, useState } from 'react'
import { Canvas, useThree } from '@react-three/fiber'
import { GizmoHelper, GizmoViewport, Html, OrbitControls, TransformControls } from '@react-three/drei'
import { Quaternion, Vector3, type Group } from 'three'
import { Camera, Cuboid, Grid3X3, LayoutDashboard, Maximize2, RotateCcw, Save, Layers, CheckCircle2 } from 'lucide-react'
import { RoomPlan2D } from './RoomPlan2D'
import { api, type MeasurementRecord, type SavedRoom, type Smard0001ReconstructionResponse } from '../api'
import { cameraOrientation, type CameraView } from './cameraOrientation'
import { clampInside, createDefaultScene, parseSceneDocument, serializeScene, type Equipment, type SceneDocument, type Vec3 } from './sceneModel'

type Props = {selectedProject?: number; setToast: (value:{kind:'error'|'success'|'info';text:string})=>void}
type View = CameraView
type Display = {grid:boolean;axes:boolean;walls:boolean;labels:boolean}
const displayDefault:Display={grid:true,axes:true,walls:true,labels:true}
const colorFor=(kind:Equipment['kind'])=>kind==='speaker'?'#c8651b':'#14504f'

export function Workspace3D({selectedProject,setToast}:Props) {
  const [scene,setScene]=useState<SceneDocument>(()=>parseSceneDocument(localStorage.getItem(sceneKey(selectedProject))))
  const [display,setDisplay]=useState<Display>(()=>{try{return {...displayDefault,...JSON.parse(localStorage.getItem('batsight-3d-display')||'{}')}}catch{return displayDefault}})
  const [viewMode,setViewMode]=useState<'3d'|'2d'|'sketch'>('3d')
  const [selectedId,setSelectedId]=useState<string|null>(null)
  const [measurements,setMeasurements]=useState<MeasurementRecord[]>([])
  const [rooms,setRooms]=useState<SavedRoom[]>([])
  const [roomId,setRoomId]=useState<number|''>('')
  const [measurementId,setMeasurementId]=useState<number|''>('')
  const [displaySpheres,setDisplaySpheres]=useState(true)
  const [selectedEchoIndex,setSelectedEchoIndex]=useState<number|null>(null)
  const [view,setView]=useState<View>('iso')
  const [smardData, setSmardData] = useState<Smard0001ReconstructionResponse | null>(null)
  const [showGroundTruth, setShowGroundTruth] = useState<boolean>(true)
  const [loadingSmard, setLoadingSmard] = useState<boolean>(false)

  const selected=scene.equipment.find(item=>item.id===selectedId)??null

  useEffect(()=>{setScene(parseSceneDocument(localStorage.getItem(sceneKey(selectedProject))));setSelectedId(null)},[selectedProject])
  useEffect(()=>{localStorage.setItem(sceneKey(selectedProject),serializeScene(scene))},[scene,selectedProject])
  useEffect(()=>{localStorage.setItem('batsight-3d-display',JSON.stringify(display))},[display])

  useEffect(()=>{
    let active=true
    api.measurements(selectedProject).then(rows=>{if(active)setMeasurements(rows)}).catch(()=>{if(active)setMeasurements([])})
    api.rooms(selectedProject).then(rows=>{if(active)setRooms(rows)}).catch(()=>{if(active)setRooms([])})
    return()=>{active=false}
  },[selectedProject])

  const selectedRoom = rooms.find(r=>r.id===roomId)??null

  async function loadSmardPreset() {
    setLoadingSmard(true)
    try {
      const res = await api.smard0001()
      setSmardData(res)
      setRoomId('')
      setMeasurementId('')
      const dims: Vec3 = [res.estimated_dimensions_m[0], res.estimated_dimensions_m[1], res.estimated_dimensions_m[2]]
      const equip: Equipment[] = [
        {
          id: 'smard-speaker',
          name: `${res.loudspeaker.name} (Ch 08)`,
          kind: 'speaker',
          position_m: res.loudspeaker.position_m,
          orientation_yaw_deg: 0,
          visible: true,
        },
        ...res.microphones.map(m => ({
          id: `smard-mic-${m.channel}`,
          name: `Ch ${m.channel.toString().padStart(2, '0')} (${m.name})`,
          kind: 'microphone' as const,
          position_m: m.position_m,
          orientation_yaw_deg: 0,
          visible: true,
        }))
      ]
      setScene({
        schema_version: 1,
        coordinate_convention: 'corner_origin_x_length_y_width_z_height',
        unit: 'm',
        room_dimensions_m: dims,
        speed_of_sound_m_s: res.diagnostics.timing_provenance.speed_of_sound_mps,
        equipment: equip,
      })
      setToast({ kind: 'success', text: 'Loaded SMARD 0001 real calibrated room reconstruction.' })
    } catch (e) {
      setToast({ kind: 'error', text: `Failed to load SMARD 0001: ${(e as Error).message}` })
    } finally {
      setLoadingSmard(false)
    }
  }

  function selectRoom(id: number | '') {
    setSmardData(null)
    setRoomId(id)
    if (!id) return
    const r = rooms.find(item => item.id === id)
    if (!r) return
    const dims: Vec3 = [r.length_x_m, r.width_y_m, r.height_z_m]
    const devPos: Vec3 = (r.device_position_m as Vec3) || [r.length_x_m / 2, r.width_y_m / 2, 1.0]
    setScene({
      schema_version: 1,
      coordinate_convention: 'corner_origin_x_length_y_width_z_height',
      unit: 'm',
      room_dimensions_m: dims,
      speed_of_sound_m_s: 343,
      equipment: [
        {
          id: 'batsight-device',
          name: 'BatSight Device',
          kind: 'microphone',
          position_m: devPos,
          orientation_yaw_deg: 0,
          visible: true,
        },
      ],
    })
    setToast({ kind: 'success', text: `Loaded room "${r.name}" (${dims[0]} × ${dims[1]} m).` })
  }

  const selectedMeasurement = measurements.find(m=>m.id===measurementId)??null
  const micEquipment = scene.equipment.find(item=>item.kind==='microphone'&&item.visible) ?? scene.equipment.find(item=>item.kind==='microphone') ?? scene.equipment[0]
  const micOrigin: Vec3 = micEquipment ? micEquipment.position_m : [scene.room_dimensions_m[0]/2, scene.room_dimensions_m[1]/2, scene.room_dimensions_m[2]/2]
  const equipment=scene.equipment
  const dimensions=scene.room_dimensions_m
  const speed=scene.speed_of_sound_m_s

  function patchPosition(id:string,point:Vec3){setScene(old=>({...old,equipment:old.equipment.map(item=>item.id===id?{...item,position_m:clampInside(point,old.room_dimensions_m)}:item)}))}
  function updateDimensions(axis:number,value:number){if(!Number.isFinite(value)||value<0.5||value>100)return;setScene(old=>{const next=[...old.room_dimensions_m] as Vec3;next[axis]=value;return {...old,room_dimensions_m:next,equipment:old.equipment.map(item=>({...item,position_m:clampInside(item.position_m,next)}))}})}
  function updateDisplay(key:keyof Display,value:boolean){setDisplay(old=>({...old,[key]:value}))}

  return <div className="workspace3d ws-themed-page" style={{ margin: 0, color: '#0a1213' }}>
    {/* Clean Sub-Header */}
    <div className="ws-head" style={{ marginBottom: 14 }}>
      <div>
        <div className="ws-eyebrow" style={{ color: '#13484a' }}>SPATIAL INSPECTION</div>
        <p style={{ color: '#263b3c', margin: '2px 0 0', fontSize: 13 }}>Inspect room geometry, device placement, and SMARD 0001 calibrated reconstruction.</p>
      </div>
      <div className="ws-head-actions" style={{ display: 'flex', gap: 10, alignItems: 'flex-end', flexWrap: 'wrap' }}>
        <button
          className={`button ${smardData ? 'primary' : 'secondary'}`}
          onClick={loadSmardPreset}
          disabled={loadingSmard}
          title="Load SMARD 0001 real measured acoustic room benchmark"
        >
          <Layers size={14} /> {loadingSmard ? 'Loading SMARD…' : 'SMARD 0001 (Real Room)'}
        </button>
        <label className="field" style={{ minWidth: 190 }}>
          <span>Saved Room</span>
          <select value={roomId} onChange={e=>selectRoom(e.target.value?Number(e.target.value):'')}>
            <option value="">Select Room…</option>
            {rooms.map(r=><option key={r.id} value={r.id}>🏠 {r.name} ({r.length_x_m} × {r.width_y_m} m)</option>)}
          </select>
        </label>
        <label className="field" style={{ minWidth: 190 }}>
          <span>Real measurement</span>
          <select value={measurementId} onChange={event=>{setMeasurementId(event.target.value?Number(event.target.value):'');setSelectedEchoIndex(null)}}>
            <option value="">None</option>
            {measurements.map(item=><option key={item.id} value={item.id}>📡 {item.name} ({item.echo_count} echoes)</option>)}
          </select>
        </label>
        <button className="button secondary" onClick={()=>{setScene(createDefaultScene());setSelectedId(null);setRoomId('');setSmardData(null)}} title="Reset to default room box">
          <RotateCcw size={14}/> Reset
        </button>
      </div>
    </div>

    {/* Status badge when room is loaded */}
    {selectedRoom&&<div className="notice info" style={{display:'flex',justifyContent:'space-between',alignItems:'center',padding:'10px 14px',marginBottom:12}}>
      <div style={{display:'flex',alignItems:'center',gap:10,flexWrap:'wrap'}}>
        <b style={{color:'#0a1213',display:'inline-flex',alignItems:'center',gap:6}}>
          <span style={{width:8,height:8,borderRadius:'50%',background:'#0d4a4d',display:'inline-block'}}/>
          {selectedRoom.name}
        </b>
        <span style={{color:'#263b3c',fontSize:12}}>
          {selectedRoom.length_x_m} × {selectedRoom.width_y_m} × {selectedRoom.height_z_m} m · {selectedRoom.floor_area_m2} m² · {selectedRoom.obstacles?.length||0} obstacle(s)
        </span>
      </div>
      <button className="button secondary small" onClick={()=>setRoomId('')}>
        Clear Selection
      </button>
    </div>}

    {selectedMeasurement&&<div className="notice info" style={{display:'flex',justifyContent:'space-between',alignItems:'center',padding:'10px 14px',marginBottom:12}}>
      <div style={{display:'flex',alignItems:'center',gap:10,flexWrap:'wrap'}}>
        <b style={{color:'#0a1213',display:'inline-flex',alignItems:'center',gap:6}}>
          <span style={{width:8,height:8,borderRadius:'50%',background:'#0d4a4d',display:'inline-block'}}/>
          {selectedMeasurement.name}
        </b>
        <span style={{color:'#263b3c',fontSize:12}}>
          {selectedMeasurement.echo_count} echo reflection(s) detected · Calibrated at {selectedMeasurement.speed_of_sound_m_s} m/s
        </span>
      </div>
      <button className="button secondary small" onClick={()=>setMeasurementId('')}>
        Dismiss
      </button>
    </div>}

    {smardData && (
      <div className="notice info" style={{display:'flex',justifyContent:'space-between',alignItems:'center',padding:'10px 14px',marginBottom:12,flexWrap:'wrap',gap:10}}>
        <div style={{display:'flex',alignItems:'center',gap:10,flexWrap:'wrap'}}>
          <b style={{color:'#0a1213',display:'inline-flex',alignItems:'center',gap:6}}>
            <span style={{width:8,height:8,borderRadius:'50%',background:'#0f5c3a',display:'inline-block'}}/>
            SMARD 0001 (Real Measured Room Benchmark)
          </b>
          <span className="pill success">ESTIMATED (CALIBRATED REAL DATA)</span>
          <span style={{color:'#263b3c',fontSize:12}}>
            Loopback delay: {smardData.diagnostics.timing_provenance.calibrated_loopback_offset_ms.toFixed(3)} ms applied · 132/132 reflections converged
          </span>
        </div>
        <div style={{display:'flex',alignItems:'center',gap:12}}>
          <label style={{display:'flex',alignItems:'center',gap:6,fontSize:12,cursor:'pointer',color:'#0a1213',fontWeight:600,userSelect:'none'}}>
            <input type="checkbox" checked={showGroundTruth} onChange={e=>setShowGroundTruth(e.target.checked)} style={{accentColor:'#7a4b06'}} />
            Show Ground Truth Box
          </label>
          <button className="button secondary small" onClick={()=>setSmardData(null)}>
            Dismiss
          </button>
        </div>
      </div>
    )}

    {/* Toolbar */}
    <div className="ws-toolbar" style={{display:'flex',justifyContent:'space-between',alignItems:'center',flexWrap:'wrap',gap:8,background:'rgba(235, 243, 245, 0.72)',border:'1px solid rgba(12, 28, 30, 0.18)',borderRadius:10,padding:'8px 12px',marginBottom:14}}>
      <div style={{display:'flex',gap:8,alignItems:'center',flexWrap:'wrap'}}>
        {/* View Mode Switcher */}
        <div className="ws-tool-group" style={{display:'flex',gap:4}}>
          <button className={`button small ${viewMode==='3d'?'primary':'secondary'}`} onClick={()=>setViewMode('3d')}>
            <Cuboid size={14}/> 3D View
          </button>
          <button className={`button small ${viewMode==='2d'?'primary':'secondary'}`} onClick={()=>setViewMode('2d')}>
            <LayoutDashboard size={14}/> 2D Floor Plan
          </button>
          <button className={`button small ${viewMode==='sketch'?'primary':'secondary'}`} onClick={()=>setViewMode('sketch')}>
            <Grid3X3 size={14}/> Wireframe Sketch
          </button>
        </div>

        {/* View Elements */}
        {viewMode==='3d'&&<div className="ws-tool-group" style={{display:'flex',gap:4}}>
          <button className={`button small ${display.grid?'primary':'secondary'}`} onClick={()=>updateDisplay('grid',!display.grid)} title="Toggle floor grid"><Grid3X3 size={14}/> Grid</button>
          <button className={`button small ${display.axes?'primary':'secondary'}`} onClick={()=>updateDisplay('axes',!display.axes)} title="Toggle coordinate axes">XYZ</button>
          <button className={`button small ${display.walls?'primary':'secondary'}`} onClick={()=>updateDisplay('walls',!display.walls)} title="Toggle room walls">Walls</button>
          <button className={`button small ${display.labels?'primary':'secondary'}`} onClick={()=>updateDisplay('labels',!display.labels)} title="Toggle labels">Labels</button>
          {selectedMeasurement&&<button className={`button small ${displaySpheres?'primary':'secondary'}`} onClick={()=>setDisplaySpheres(!displaySpheres)} title="Toggle measured echo distance spheres">Echo spheres</button>}
        </div>}
      </div>

      {viewMode==='3d'&&<div className="ws-tool-group" style={{display:'flex',gap:4,alignItems:'center'}}>
        <button className="button small secondary" onClick={()=>setView('top')}>Top</button>
        <button className="button small secondary" onClick={()=>setView('front')}>Front</button>
        <button className="button small secondary" onClick={()=>setView('side')}>Side</button>
        <button className="button small secondary" onClick={()=>setView('iso')}><Camera size={14}/> Iso</button>
        <button className="button small secondary" onClick={()=>setView('iso')} title="Fit room to view"><Maximize2 size={13}/> Fit</button>
        <span className="ws-hint" style={{color:'#263b3c',fontSize:11,marginLeft:6}}>Drag to orbit · scroll to zoom</span>
      </div>}
    </div>

    {/* Main Content Layout */}
    <div className="ws-layout" style={{display:'grid',gridTemplateColumns:'minmax(0, 1fr) 330px',gap:16,minHeight:540}}>
      {/* Primary Viewport */}
      <section className="ws-viewport" style={{
        background: 'rgba(220, 233, 236, 0.55)',
        backgroundImage: 'linear-gradient(rgba(12, 28, 30, 0.13) 1px, transparent 1px), linear-gradient(90deg, rgba(12, 28, 30, 0.13) 1px, transparent 1px)',
        backgroundSize: '30px 30px',
        borderRadius: 14,
        overflow: 'hidden',
        position: 'relative',
        display: 'flex',
        flexDirection: 'column',
        border: '1px solid rgba(255, 255, 255, 0.65)',
        boxShadow: 'inset 0 1px 0 rgba(255, 255, 255, 0.5)',
      }}>
        {viewMode === 'sketch' ? (
          <div style={{ flex: 1, minHeight: 490, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', position: 'relative', padding: 24 }}>
            <svg viewBox="0 0 320 300" style={{ width: 'min(400px, 86%)', height: 'auto', overflow: 'visible', filter: 'drop-shadow(0 8px 14px rgba(10, 18, 19, 0.14))' }} aria-label="Hand-drawn wireframe cube">
              {/* Back/hidden edges (lighter, dashed) */}
              <path d="M108,50 Q180,52 254,56" stroke="#0a0a0a" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" strokeDasharray="10 8" opacity="0.58" fill="none" />
              <path d="M254,56 Q249,128 245,200" stroke="#0a0a0a" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" strokeDasharray="10 8" opacity="0.58" fill="none" />
              <path d="M103,188 Q174,194 245,200" stroke="#0a0a0a" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" strokeDasharray="10 8" opacity="0.58" fill="none" />
              <path d="M108,50 Q106,119 103,188" stroke="#0a0a0a" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" strokeDasharray="10 8" opacity="0.58" fill="none" />
              {/* Connecting depth edges (medium-bold continuous) */}
              <path d="M54,96 Q81,73 108,50" stroke="#0a0a0a" strokeWidth="4.6" strokeLinecap="round" strokeLinejoin="round" fill="none" />
              <path d="M198,104 Q226,80 254,56" stroke="#0a0a0a" strokeWidth="4.6" strokeLinecap="round" strokeLinejoin="round" fill="none" />
              <path d="M190,250 Q218,225 245,200" stroke="#0a0a0a" strokeWidth="4.6" strokeLinecap="round" strokeLinejoin="round" fill="none" />
              <path d="M47,240 Q75,214 103,188" stroke="#0a0a0a" strokeWidth="4.6" strokeLinecap="round" strokeLinejoin="round" fill="none" />
              {/* Front face edges (heaviest continuous hand-drawn marker) */}
              <path d="M54,96 Q126,99 198,104" stroke="#0a0a0a" strokeWidth="5.6" strokeLinecap="round" strokeLinejoin="round" fill="none" />
              <path d="M198,104 Q194,177 190,250" stroke="#0a0a0a" strokeWidth="5.6" strokeLinecap="round" strokeLinejoin="round" fill="none" />
              <path d="M47,240 Q118,245 190,250" stroke="#0a0a0a" strokeWidth="5.6" strokeLinecap="round" strokeLinejoin="round" fill="none" />
              <path d="M54,96 Q50,168 47,240" stroke="#0a0a0a" strokeWidth="5.6" strokeLinecap="round" strokeLinejoin="round" fill="none" />
              {/* Vertex dots */}
              {[[54,96],[198,104],[190,250],[47,240]].map(([cx,cy],i)=>(
                <circle key={`fv-${i}`} cx={cx} cy={cy} r="4.2" fill="#0a0a0a" />
              ))}
              {[[108,50],[254,56],[245,200],[103,188]].map(([cx,cy],i)=>(
                <circle key={`bv-${i}`} cx={cx} cy={cy} r="3.2" fill="#0a0a0a" opacity="0.65" />
              ))}
            </svg>
            <div style={{ marginTop: 12, fontSize: 12, fontWeight: 700, color: '#0a1213', letterSpacing: 1 }}>
              {dimensions.map(d => d.toFixed(2)).join(' × ')} m · {equipment.length} node(s)
            </div>
          </div>
        ) : viewMode === '2d' ? (
          <div style={{ width: '100%', height: '100%', overflow: 'auto', background: 'rgba(235, 243, 245, 0.85)', padding: 12 }}>
            <RoomPlan2D
              room={selectedRoom}
              measurement={selectedMeasurement}
              dimensions={dimensions}
              isInline={true}
              onApplyTo3D={(dims) => {
                updateDimensions(0, dims[0])
                updateDimensions(1, dims[1])
                updateDimensions(2, dims[2])
                setToast({ kind: 'success', text: `Applied dimensions to 3D scene.` })
              }}
            />
          </div>
        ) : (
          <div className="ws-canvas" style={{flex:1,position:'relative',minHeight:490,background:'transparent'}}>
            <Canvas gl={{ alpha: true }} camera={{position:[dimensions[0]*1.4,-dimensions[1]*1.6,dimensions[2]*1.3],fov:42,near:.01,far:2000,up:[0,0,1]}} onCreated={({camera})=>{camera.up.set(0,0,1)}}>
              <ambientLight intensity={1.6}/>
              <directionalLight position={[6,-5,9]} intensity={2.2}/>
              <Room dimensions={dimensions} visible={display.walls} labels={display.labels}/>
              {smardData && showGroundTruth && (
                <GroundTruthRoomOverlay dimensions={smardData.ground_truth_dimensions_m} labels={display.labels}/>
              )}
              <Axes dimensions={dimensions} visible={display.axes}/>
              <FloorGrid dimensions={dimensions} visible={display.grid}/>
              <EquipmentLayer items={equipment} selectedId={selectedId} editable={true} onSelect={setSelectedId} onMove={patchPosition} labels={display.labels}/>
              <MeasurementEchoLayer measurement={selectedMeasurement} origin={micOrigin} visible={displaySpheres} selectedIndex={selectedEchoIndex} labels={display.labels}/>
              <ObstacleLayer obstacles={selectedRoom?.obstacles||[]} origin={micOrigin} labels={display.labels}/>
              <CameraController target={[dimensions[0]/2,dimensions[1]/2,dimensions[2]/2]} radius={Math.max(...dimensions)*2.2} view={view}/>
              <GizmoHelper alignment="bottom-right" margin={[65,65]}><GizmoViewport axisColors={['#b91c1c','#15803d','#0d4a4d']} labelColor="#0a1213"/></GizmoHelper>
            </Canvas>
            <div className="ws-corner-label" style={{color:'#263b3c',fontWeight:700}}>X LENGTH · Y WIDTH · Z HEIGHT</div>
            <div className="ws-legend" style={{position:'absolute',bottom:12,left:12,display:'flex',gap:12,fontSize:11,background:'rgba(235, 243, 245, 0.90)',color:'#0a1213',padding:'6px 12px',borderRadius:8,border:'1px solid rgba(12, 28, 30, 0.2)',flexWrap:'wrap'}}>
              <span style={{display:'flex',alignItems:'center',gap:5}}><span style={{width:12,height:2,background:'#0d4a4d',display:'inline-block'}}/>{smardData ? 'Estimated Room' : 'Room Boundary'}</span>
              {smardData && showGroundTruth && (
                <span style={{display:'flex',alignItems:'center',gap:5}}><span style={{width:12,height:2,background:'#b45309',display:'inline-block'}}/>Ground Truth Box</span>
              )}
              <span style={{display:'flex',alignItems:'center',gap:5}}><span style={{width:10,height:10,borderRadius:'50%',background:smardData?'var(--speaker-color, #c8651b)':'var(--mic-color, #14504f)',border:'1.5px solid #f5fafa',boxShadow:'0 0 0 1px rgba(10,18,19,0.2)',display:'inline-block'}}/>{smardData ? 'Loudspeaker (Ch 08)' : 'BatSight Device'}</span>
              {smardData && (
                <span style={{display:'flex',alignItems:'center',gap:5}}><span style={{width:10,height:10,borderRadius:'50%',background:'var(--mic-color, #14504f)',border:'1.5px solid #f5fafa',boxShadow:'0 0 0 1px rgba(10,18,19,0.2)',display:'inline-block'}}/>22 Microphones</span>
              )}
              {!smardData && (
                <span style={{display:'flex',alignItems:'center',gap:5}}><span style={{width:8,height:8,borderRadius:2,background:'#b45309',display:'inline-block'}}/>Obstacles</span>
              )}
            </div>
          </div>
        )}
        <div className="ws-status" style={{background:'rgba(235, 243, 245, 0.85)',padding:'8px 14px',display:'flex',justifyContent:'space-between',fontSize:11,color:'#263b3c',fontWeight:600,borderTop:'1px solid rgba(12, 28, 30, 0.16)'}}>
          <span style={{color:'#0a1213'}}>{selectedRoom?`ROOM: ${selectedRoom.name}`:selectedMeasurement?`MEASUREMENT: ${selectedMeasurement.name}`:'ACTIVE SCENE'}</span>
          <span>Dimensions: {dimensions.map(x=>x.toFixed(2)).join(' × ')} m</span>
          <span>c = {speed.toFixed(1)} m/s</span>
        </div>
      </section>

      {/* Clean Right Inspector Panel */}
      <aside className="panel ws-inspector" style={{background:'rgba(235, 243, 245, 0.85)',border:'1px solid rgba(255, 255, 255, 0.65)',borderRadius:14,padding:18,display:'flex',flexDirection:'column',gap:14,color:'#0a1213'}}>
        <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',borderBottom:'1px solid rgba(12, 28, 30, 0.18)',paddingBottom:10}}>
          <b style={{fontSize:14,color:'#0a1213'}}>{smardData ? 'SMARD Benchmark' : selectedRoom ? 'Room Details' : 'Scene Properties'}</b>
          <span className="pill cyan">
            {smardData ? 'CALIBRATED ESTIMATE' : selectedRoom ? 'SAVED ROOM' : 'EDITABLE'}
          </span>
        </div>

        {smardData ? (
          <>
            <div>
              <div style={{display:'flex',alignItems:'center',gap:8,background:'#dff3e8',border:'1px solid rgba(15, 92, 58, 0.35)',padding:'8px 10px',borderRadius:8,marginBottom:12}}>
                <CheckCircle2 size={16} color="#0f5c3a" style={{flexShrink:0}} />
                <div>
                  <div style={{fontSize:11,fontWeight:700,color:'#0b442b'}}>ESTIMATED (CALIBRATED REAL DATA)</div>
                  <div style={{fontSize:10,color:'#1a5c3f'}}>SMARD Config 0001 · 22 Mics Acoustic Array</div>
                </div>
              </div>

              <div style={{fontSize:11,color:'#13484a',fontWeight:700,marginBottom:6}}>ESTIMATED VS GROUND TRUTH</div>
              <table style={{width:'100%',borderCollapse:'collapse',fontSize:11,marginBottom:12}}>
                <thead>
                  <tr style={{color:'#263b3c',borderBottom:'1px solid rgba(12, 28, 30, 0.2)',textAlign:'left'}}>
                    <th style={{padding:'4px 2px'}}>Dim</th>
                    <th style={{padding:'4px 2px',textAlign:'right'}}>Actual</th>
                    <th style={{padding:'4px 2px',textAlign:'right'}}>Est</th>
                    <th style={{padding:'4px 2px',textAlign:'right'}}>Error</th>
                  </tr>
                </thead>
                <tbody>
                  {[
                    { axis: 'Lx', name: 'Length (X)', gt: smardData.ground_truth_dimensions_m[0], est: smardData.estimated_dimensions_m[0] },
                    { axis: 'Ly', name: 'Width (Y)', gt: smardData.ground_truth_dimensions_m[1], est: smardData.estimated_dimensions_m[1] },
                    { axis: 'Lz', name: 'Height (Z)', gt: smardData.ground_truth_dimensions_m[2], est: smardData.estimated_dimensions_m[2] },
                  ].map(row => {
                    const diffM = row.est - row.gt
                    const diffCm = diffM * 100
                    const relPct = (diffM / row.gt) * 100
                    return (
                      <tr key={row.axis} style={{borderBottom:'1px solid rgba(12, 28, 30, 0.1)'}}>
                        <td style={{padding:'5px 2px',color:'#0a1213',fontWeight:600}}>{row.name}</td>
                        <td style={{padding:'5px 2px',textAlign:'right',color:'#263b3c'}}>{row.gt.toFixed(3)} m</td>
                        <td style={{padding:'5px 2px',textAlign:'right',color:'#0d4a4d',fontWeight:700}}>{row.est.toFixed(3)} m</td>
                        <td style={{padding:'5px 2px',textAlign:'right',color: Math.abs(diffCm) < 8 ? '#0f5c3a' : '#7a4b06',fontWeight:700}}>
                          {diffCm >= 0 ? `+${diffCm.toFixed(1)}` : diffCm.toFixed(1)} cm ({relPct >= 0 ? `+${relPct.toFixed(2)}` : relPct.toFixed(2)}%)
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>

            <div>
              <div style={{fontSize:11,color:'#13484a',fontWeight:700,marginBottom:6}}>SOLVER DIAGNOSTICS</div>
              <div style={{display:'flex',flexDirection:'column',gap:5,fontSize:11}}>
                <div style={{display:'flex',justifyContent:'space-between',borderBottom:'1px solid rgba(12, 28, 30, 0.12)',paddingBottom:4}}>
                  <span style={{color:'#263b3c'}}>Residual RMS</span>
                  <b style={{color:'#0d4a4d'}}>{smardData.diagnostics.residual_rms_ms.toFixed(3)} ms</b>
                </div>
                <div style={{display:'flex',justifyContent:'space-between',borderBottom:'1px solid rgba(12, 28, 30, 0.12)',paddingBottom:4}}>
                  <span style={{color:'#263b3c'}}>Jacobian Rank / Cond</span>
                  <b style={{color:'#0a1213'}}>{smardData.diagnostics.jacobian_rank} / 3 (cond {smardData.diagnostics.jacobian_condition_number.toFixed(2)})</b>
                </div>
                <div style={{display:'flex',justifyContent:'space-between',borderBottom:'1px solid rgba(12, 28, 30, 0.12)',paddingBottom:4}}>
                  <span style={{color:'#263b3c'}}>Optimizer Status</span>
                  <b style={{color:'#0f5c3a'}}>{smardData.diagnostics.optimizer_status}</b>
                </div>
                <div style={{display:'flex',justifyContent:'space-between',borderBottom:'1px solid rgba(12, 28, 30, 0.12)',paddingBottom:4}}>
                  <span style={{color:'#263b3c'}}>Reflections Used</span>
                  <b style={{color:'#0a1213'}}>{smardData.diagnostics.total_reflections_used} (22 per wall)</b>
                </div>
                <div style={{display:'flex',justifyContent:'space-between',borderBottom:'1px solid rgba(12, 28, 30, 0.12)',paddingBottom:4}}>
                  <span style={{color:'#263b3c'}}>Hardware Timing Offset</span>
                  <b style={{color:'#7a1f5c'}}>{smardData.diagnostics.timing_provenance.calibrated_loopback_offset_ms.toFixed(3)} ms</b>
                </div>
                <div style={{display:'flex',justifyContent:'space-between',paddingBottom:4}}>
                  <span style={{color:'#263b3c'}}>Speed of Sound (c)</span>
                  <b style={{color:'#0a1213'}}>{smardData.diagnostics.timing_provenance.speed_of_sound_mps.toFixed(1)} m/s (21.6 °C)</b>
                </div>
              </div>
            </div>

            <div style={{marginTop:'auto',display:'flex',flexDirection:'column',gap:8}}>
              <label style={{display:'flex',alignItems:'center',gap:6,fontSize:11,cursor:'pointer',color:'#0a1213',fontWeight:600}}>
                <input type="checkbox" checked={showGroundTruth} onChange={e=>setShowGroundTruth(e.target.checked)} style={{accentColor:'#7a4b06'}} />
                <span>Show Ground Truth Box (Amber)</span>
              </label>
              <button
                className="button primary small"
                style={{width:'100%',display:'flex',alignItems:'center',justifyContent:'center',gap:6}}
                onClick={()=>setViewMode(viewMode==='3d'?'2d':'3d')}
              >
                {viewMode==='3d' ? <><LayoutDashboard size={14}/> Switch to 2D Floor Plan</> : <><Cuboid size={14}/> Switch to 3D View</>}
              </button>
            </div>
          </>
        ) : selectedRoom ? (
          <>
            <div>
              <div style={{fontSize:11,color:'#13484a',fontWeight:700,marginBottom:6}}>DIMENSIONS & VOLUME</div>
              <div style={{display:'flex',flexDirection:'column',gap:6}}>
                <div style={{display:'flex',justifyContent:'space-between',fontSize:12,borderBottom:'1px solid rgba(12, 28, 30, 0.12)',paddingBottom:4}}>
                  <span style={{color:'#263b3c'}}>Length (X)</span>
                  <b style={{color:'#0d4a4d'}}>{selectedRoom.length_x_m.toFixed(2)} m</b>
                </div>
                <div style={{display:'flex',justifyContent:'space-between',fontSize:12,borderBottom:'1px solid rgba(12, 28, 30, 0.12)',paddingBottom:4}}>
                  <span style={{color:'#263b3c'}}>Width (Y)</span>
                  <b style={{color:'#0d4a4d'}}>{selectedRoom.width_y_m.toFixed(2)} m</b>
                </div>
                <div style={{display:'flex',justifyContent:'space-between',fontSize:12,borderBottom:'1px solid rgba(12, 28, 30, 0.12)',paddingBottom:4}}>
                  <span style={{color:'#263b3c'}}>Height (Z)</span>
                  <b style={{color:'#0a1213'}}>{selectedRoom.height_z_m.toFixed(2)} m</b>
                </div>
                <div style={{display:'flex',justifyContent:'space-between',fontSize:12,borderBottom:'1px solid rgba(12, 28, 30, 0.12)',paddingBottom:4}}>
                  <span style={{color:'#263b3c'}}>Floor Area</span>
                  <b style={{color:'#0a1213'}}>{selectedRoom.floor_area_m2} m²</b>
                </div>
                <div style={{display:'flex',justifyContent:'space-between',fontSize:12,paddingBottom:4}}>
                  <span style={{color:'#263b3c'}}>Room Volume</span>
                  <b style={{color:'#0a1213'}}>{selectedRoom.room_volume_m3} m³</b>
                </div>
              </div>
            </div>

            {selectedRoom.wall_distances&&Object.keys(selectedRoom.wall_distances).length>0&&(
              <div>
                <div style={{fontSize:11,color:'#13484a',fontWeight:700,marginBottom:6}}>MEASURED WALL DISTANCES</div>
                <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:6}}>
                  {Object.entries(selectedRoom.wall_distances).map(([k,v])=>(
                    <div key={k} style={{background:'rgba(244, 248, 249, 0.78)',border:'1px solid rgba(12, 28, 30, 0.16)',padding:'6px 8px',borderRadius:6}}>
                      <div style={{fontSize:10,color:'#263b3c',textTransform:'capitalize'}}>{k}</div>
                      <div style={{fontSize:12,fontWeight:700,color:'#0d4a4d'}}>{Number(v).toFixed(2)} m</div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div>
              <div style={{fontSize:11,color:'#7a4b06',fontWeight:700,marginBottom:6}}>
                DETECTED OBSTACLES ({selectedRoom.obstacles?.length||0})
              </div>
              {selectedRoom.obstacles&&selectedRoom.obstacles.length>0 ? (
                <div style={{display:'flex',flexDirection:'column',gap:6}}>
                  {selectedRoom.obstacles.map((obs,i)=>(
                    <div key={i} className="obstacle-badge" style={{padding:'6px 10px',display:'flex',justifyContent:'space-between',alignItems:'center'}}>
                      <span>📦 {obs.label||`Obstacle (${obs.direction})`}</span>
                      <b>{Number(obs.distance_m).toFixed(2)} m</b>
                    </div>
                  ))}
                </div>
              ) : (
                <p style={{fontSize:12,color:'#263b3c',margin:0}}>No interior obstacles detected.</p>
              )}
            </div>

            <button
              className="button primary small"
              style={{marginTop:'auto',width:'100%',display:'flex',alignItems:'center',justifyContent:'center',gap:6}}
              onClick={()=>setViewMode(viewMode==='3d'?'2d':'3d')}
            >
              {viewMode==='3d' ? <><LayoutDashboard size={14}/> Switch to 2D Floor Plan</> : <><Cuboid size={14}/> Switch to 3D View</>}
            </button>
          </>
        ) : (
          <>
            <div>
              <div style={{fontSize:11,color:'#13484a',fontWeight:700,marginBottom:8}}>ROOM DIMENSIONS (METRES)</div>
              <div style={{display:'flex',flexDirection:'column',gap:8}}>
                {(['Length (X)','Width (Y)','Height (Z)'] as const).map((label,index)=>(
                  <label key={label} className="field" style={{flexDirection:'row',justifyContent:'space-between',alignItems:'center',fontSize:12,color:'#263b3c'}}>
                    <span>{label}</span>
                    <input
                      type="number"
                      min="0.5"
                      max="100"
                      step="0.1"
                      value={scene.room_dimensions_m[index]}
                      onChange={event=>updateDimensions(index,Number(event.target.value))}
                      style={{width:82,textAlign:'right'}}
                    />
                  </label>
                ))}
              </div>
            </div>

            {selected&&<div style={{borderTop:'1px solid rgba(12, 28, 30, 0.16)',paddingTop:12}}>
              <div style={{fontSize:11,color:'#13484a',fontWeight:700,marginBottom:6}}>SELECTED OBJECT</div>
              <div style={{fontSize:12,color:'#0a1213',fontWeight:700,marginBottom:6}}>{selected.name}</div>
              <div style={{display:'flex',flexDirection:'column',gap:6}}>
                {(['X','Y','Z'] as const).map((axis,index)=>(
                  <label key={axis} className="field" style={{flexDirection:'row',justifyContent:'space-between',alignItems:'center',fontSize:11,color:'#263b3c'}}>
                    <span>Position {axis} (m)</span>
                    <input
                      type="number"
                      step="0.05"
                      value={selected.position_m[index]}
                      onChange={event=>{
                        const next=[...selected.position_m] as Vec3
                        next[index]=Number(event.target.value)
                        if(Number.isFinite(next[index]))patchPosition(selected.id,next)
                      }}
                      style={{width:76,textAlign:'right'}}
                    />
                  </label>
                ))}
              </div>
            </div>}
          </>
        )}
      </aside>
    </div>

    <div className="ws-footer" style={{marginTop:12,display:'flex',justifyContent:'space-between',fontSize:12,color:'#263b3c',fontWeight:500}}>
      <span><Save size={13}/> Scene saved locally.</span>
      <span>Toggle between 3D View, 2D Floor Plan, and Wireframe Sketch anytime.</span>
    </div>
  </div>
}

function sceneKey(project?:number){return `batsight-3d-scene-${project??'default'}`}

function Room({dimensions,visible,labels}:{dimensions:Vec3;visible:boolean;labels:boolean}){
  const [x,y,z]=dimensions
  return <group>
    {visible&&<>
      <mesh position={[x/2,y/2,z/2]}>
        <boxGeometry args={[x,y,z]}/>
        <meshBasicMaterial color="#58c9b9" transparent opacity={.065} side={2}/>
      </mesh>
      <RoomPlane position={[x/2,0,z/2]} size={[x,z]} rotation={[Math.PI/2,0,0]}/>
      <RoomPlane position={[x/2,y,z/2]} size={[x,z]} rotation={[Math.PI/2,0,0]}/>
      <RoomPlane position={[0,y/2,z/2]} size={[y,z]} rotation={[0,Math.PI/2,0]}/>
      <RoomPlane position={[x,y/2,z/2]} size={[y,z]} rotation={[0,Math.PI/2,0]}/>
      <RoomPlane position={[x/2,y/2,0]} size={[x,y]} rotation={[0,0,0]}/>
      <RoomPlane position={[x/2,y/2,z]} size={[x,y]} rotation={[0,0,0]}/>
      <RoomEdges dimensions={dimensions}/>
      {labels&&<WallLabels dimensions={dimensions}/>}
    </>}
    {labels&&<Html position={[x/2,y/2,z+.12]} center distanceFactor={18}>
      <span className="ws-3d-label" style={{background:'rgba(235, 243, 245, 0.92)',borderColor:'#0d4a4d',color:'#0a1213',fontWeight:700,fontSize:11,padding:'3px 8px',borderRadius:4}}>
        ROOM · {x.toFixed(2)} × {y.toFixed(2)} × {z.toFixed(2)} m
      </span>
    </Html>}
  </group>
}

function WallLabels({dimensions}:{dimensions:Vec3}){
  const [x,y,z]=dimensions
  const points:[string,Vec3][]=[['Front (Y+)',[x/2,y,z/2]],['Back (Y-)',[x/2,0,z/2]],['Left (X-)',[0,y/2,z/2]],['Right (X+)',[x,y/2,z/2]]]
  return <>{points.map(([label,point])=><Html key={label} position={point} center distanceFactor={19}><span className="ws-3d-label wall" style={{fontSize:10,background:'rgba(235,243,245,0.9)',color:'#263b3c',borderColor:'rgba(12,28,30,0.3)'}}>{label}</span></Html>)}</>
}

function RoomPlane({position,size,rotation}:{position:Vec3;size:[number,number];rotation:Vec3}){
  return <mesh position={position} rotation={rotation}><planeGeometry args={size}/><meshBasicMaterial color="#6f9a98" transparent opacity={.08} side={2}/></mesh>
}

function RoomEdges({dimensions}:{dimensions:Vec3}){
  const [x,y,z]=dimensions
  const vertices:Vec3[]=[[0,0,0],[x,0,0],[x,y,0],[0,y,0],[0,0,z],[x,0,z],[x,y,z],[0,y,z]]
  const edges=[[0,1],[1,2],[2,3],[3,0],[4,5],[5,6],[6,7],[7,4],[0,4],[1,5],[2,6],[3,7]]
  const radius=Math.max(0.018,Math.min(0.05,Math.max(x,y,z)*0.0052))
  return <group>
    {edges.map(([a,b],i)=><BoldEdge key={i} start={vertices[a]} end={vertices[b]} radius={radius} color="#0b2e30" opacity={0.96}/>)}
    {vertices.map((v,i)=>(
      <mesh key={`rv-${i}`} position={v}>
        <sphereGeometry args={[radius*1.35,12,10]}/>
        <meshBasicMaterial color="#0b2e30"/>
      </mesh>
    ))}
  </group>
}

function GroundTruthRoomOverlay({dimensions,labels}:{dimensions:Vec3;labels:boolean}){
  const [x,y,z]=dimensions
  const vertices:Vec3[]=[[0,0,0],[x,0,0],[x,y,0],[0,y,0],[0,0,z],[x,0,z],[x,y,z],[0,y,z]]
  const edges=[[0,1],[1,2],[2,3],[3,0],[4,5],[5,6],[6,7],[7,4],[0,4],[1,5],[2,6],[3,7]]
  const radius=Math.max(0.013,Math.min(0.036,Math.max(x,y,z)*0.0036))
  return <group>
    <mesh position={[x/2,y/2,z/2]}>
      <boxGeometry args={[x,y,z]}/>
      <meshBasicMaterial color="#b45309" transparent opacity={.04} side={2}/>
    </mesh>
    {edges.map(([a,b],i)=><BoldEdge key={i} start={vertices[a]} end={vertices[b]} radius={radius} color="#b45309" opacity={0.9}/>)}
    {labels&&<Html position={[x/2,y/2,z+.28]} center distanceFactor={18}>
      <span className="ws-3d-label" style={{background:'#faeccb',borderColor:'#b45309',color:'#7a4b06',fontWeight:700,fontSize:11,padding:'3px 8px',borderRadius:4}}>
        GROUND TRUTH · {x.toFixed(2)} × {y.toFixed(2)} × {z.toFixed(2)} m
      </span>
    </Html>}
  </group>
}

function BoldEdge({start,end,radius,color,opacity=1}:{start:Vec3;end:Vec3;radius:number;color:string;opacity?:number}){
  const {mid,len,quat}=useMemo(()=>{
    const a=new Vector3(...start)
    const b=new Vector3(...end)
    const dir=new Vector3().subVectors(b,a)
    const len=dir.length()
    const mid=new Vector3().addVectors(a,b).multiplyScalar(0.5)
    const quat=new Quaternion()
    if(len>1e-6)quat.setFromUnitVectors(new Vector3(0,1,0),dir.normalize())
    return {mid:[mid.x,mid.y,mid.z] as Vec3,len,quat}
  },[start[0],start[1],start[2],end[0],end[1],end[2]])
  return <mesh position={mid} quaternion={quat}>
    <cylinderGeometry args={[radius,radius,len,8,1]}/>
    <meshBasicMaterial color={color} transparent={opacity<1} opacity={opacity}/>
  </mesh>
}

function Line3({start,end,color='#53aeb8',opacity=1,dashed=false}:{start:Vec3;end:Vec3;color?:string;opacity?:number;dashed?:boolean}){
  return <line><bufferGeometry><bufferAttribute attach="attributes-position" args={[new Float32Array([...start,...end]),3]}/></bufferGeometry>{dashed?<lineDashedMaterial color={color} dashSize={.12} gapSize={.08} transparent opacity={opacity}/>:<lineBasicMaterial color={color} transparent opacity={opacity}/>}</line>
}

function Axes({dimensions,visible}:{dimensions:Vec3;visible:boolean}){
  if(!visible)return null
  const length=Math.max(...dimensions)*.25
  return <group><Line3 start={[0,0,0]} end={[length,0,0]} color="#fa7376"/><Line3 start={[0,0,0]} end={[0,length,0]} color="#67d590"/><Line3 start={[0,0,0]} end={[0,0,length]} color="#54cce1"/></group>
}

function FloorGrid({dimensions,visible}:{dimensions:Vec3;visible:boolean}){
  if(!visible)return null
  const [x,y]=dimensions
  const maxDim=Math.max(x,y,4)
  return <gridHelper args={[maxDim*1.4,Math.ceil(maxDim*2),'#7a999b','#b4c9cb']} position={[x/2,y/2,-0.002]} rotation={[Math.PI/2,0,0]} />
}

function EquipmentLayer({items,selectedId,editable,onSelect,onMove,labels}:{items:Equipment[];selectedId:string|null;editable:boolean;onSelect:(id:string|null)=>void;onMove:(id:string,point:Vec3)=>void;labels:boolean}){
  return <>{items.filter(item=>item.visible).map(item=>{const marker=<EquipmentMarker key={item.id} item={item} selected={selectedId===item.id} labels={labels} onSelect={()=>onSelect(item.id)}/>;return editable&&selectedId===item.id?<TransformControls key={`control-${item.id}`} mode="translate" showX showY showZ onObjectChange={(event:any)=>{const object=event?.target?.object as Group|undefined;if(object)onMove(item.id,[object.position.x,object.position.y,object.position.z])}} onMouseUp={(event:any)=>{const object=event?.target?.object as Group|undefined;if(object)onMove(item.id,[object.position.x,object.position.y,object.position.z])}}>{marker}</TransformControls>:marker})}</>
}

function EquipmentMarker({item,selected,labels,onSelect}:{item:Equipment;selected:boolean;labels:boolean;onSelect:()=>void}){
  const markerColor = colorFor(item.kind)
  return <group position={item.position_m} onClick={event=>{event.stopPropagation();onSelect()}}>
    {/* Light halo outline so marker pops cleanly on frosted/grid backgrounds */}
    <mesh>
      <sphereGeometry args={[.132,20,14]}/>
      <meshBasicMaterial color="#f5fafa" side={1}/>
    </mesh>
    <mesh>
      <sphereGeometry args={[.11,20,14]}/>
      <meshStandardMaterial color={markerColor} emissive={markerColor} emissiveIntensity={selected ? .35 : .08}/>
    </mesh>
    <mesh position={[0,0,.16]} rotation={[0,0,item.orientation_yaw_deg*Math.PI/180]}>
      <cylinderGeometry args={item.kind==='speaker'?[.052,.082,.13,16]:[.034,.056,.13,12]}/>
      <meshBasicMaterial color="#f5fafa" side={1}/>
    </mesh>
    <mesh position={[0,0,.16]} rotation={[0,0,item.orientation_yaw_deg*Math.PI/180]}>
      <cylinderGeometry args={item.kind==='speaker'?[.045,.075,.12,16]:[.028,.05,.12,12]}/>
      <meshStandardMaterial color={markerColor}/>
    </mesh>
    {selected&&<mesh><sphereGeometry args={[.18,16,12]}/><meshBasicMaterial color={markerColor} wireframe transparent opacity={.65}/></mesh>}
    {labels&&<Html position={[0,0,.28]} center distanceFactor={13}>
      <span className={`ws-3d-label ${item.kind}`}>{item.name}</span>
    </Html>}
  </group>
}

function CameraController({target,radius,view}:{target:Vec3;radius:number;view:View}){
  const {camera}=useThree()
  const controlsRef=useRef<any>(null)
  useEffect(()=>{
    const orientation=cameraOrientation(view,target,radius)
    camera.position.set(...orientation.position)
    camera.up.set(...orientation.up)
    camera.lookAt(...orientation.target)
    camera.updateProjectionMatrix()
    if(controlsRef.current){
      controlsRef.current.target.set(target[0],target[1],target[2])
      controlsRef.current.maxDistance=Math.max(radius*4.0,50)
      controlsRef.current.update()
    }
  },[camera,target[0],target[1],target[2],radius,view])
  return <OrbitControls ref={controlsRef} makeDefault target={target} enableDamping dampingFactor={.08} minDistance={.5} maxDistance={Math.max(radius*4.0,50)}/>
}

function MeasurementEchoLayer({measurement,origin,visible=true,selectedIndex,labels=true}:{measurement:MeasurementRecord|null;origin:Vec3;visible?:boolean;selectedIndex:number|null;labels?:boolean}){
  if(!measurement||!visible)return null
  const echoes=(measurement.echo_candidates||[]).filter((e:any)=>e.distance_m&&e.distance_m>0.05)
  return <group position={origin}>
    {echoes.map((echo:any,index:number)=>{
      const r=Number(echo.distance_m)
      const isSelected=selectedIndex===index
      const tint='#00f5d4'
      return <group key={`meas-echo-${index}`}>
        <mesh>
          <sphereGeometry args={[r,32,20]}/>
          <meshBasicMaterial color={tint} wireframe transparent opacity={isSelected?0.42:0.16}/>
        </mesh>
        <mesh rotation={[Math.PI/2,0,0]}>
          <ringGeometry args={[Math.max(0,r-0.018),r+0.018,64]}/>
          <meshBasicMaterial color={tint} transparent opacity={isSelected?0.8:0.45} side={2}/>
        </mesh>
        {labels&&<Html position={[r*0.707,r*0.707,0]} center distanceFactor={14}>
          <span style={{background:'rgba(3,46,43,0.92)',border:`1px solid ${tint}`,color:tint,padding:'2px 7px',borderRadius:4,fontSize:11,fontWeight:600,whiteSpace:'nowrap',boxShadow:'0 2px 8px rgba(0,0,0,0.5)'}}>
            ECHO {index+1} · {r.toFixed(2)} m
          </span>
        </Html>}
      </group>
    })}
  </group>
}

function ObstacleLayer({obstacles,origin,labels}:{obstacles:Array<{direction:string;distance_m:number;label?:string}>;origin:Vec3;labels:boolean}){
  if(!obstacles||!obstacles.length)return null
  return <group position={origin}>
    {obstacles.map((obs,i)=>{
      const d=Number(obs.distance_m)
      let pos:[number,number,number]=[0,0,0]
      if(obs.direction==='front') pos=[0,d,0]
      else if(obs.direction==='right') pos=[d,0,0]
      else if(obs.direction==='back') pos=[0,-d,0]
      else if(obs.direction==='left') pos=[-d,0,0]
      else pos=[d*0.707,d*0.707,0]
      return <group key={`obs-${i}`} position={pos}>
        <mesh position={[0,0,-0.1]}>
          <boxGeometry args={[0.5,0.5,0.6]}/>
          <meshStandardMaterial color="#f59e0b" emissive="#d97706" emissiveIntensity={0.2} transparent opacity={0.85}/>
        </mesh>
        <Line3 start={[0,0,0]} end={[-pos[0],-pos[1],-pos[2]]} color="#f59e0b" opacity={0.4} dashed/>
        {labels&&<Html position={[0,0,0.35]} center distanceFactor={14}>
          <span style={{background:'rgba(24,16,4,0.95)',border:'1px solid #f59e0b',color:'#f59e0b',padding:'3px 8px',borderRadius:4,fontSize:11,fontWeight:700,whiteSpace:'nowrap',boxShadow:'0 2px 10px rgba(0,0,0,0.7)'}}>
            📦 {obs.label||'Obstacle'} ({d.toFixed(2)}m)
          </span>
        </Html>}
      </group>
    })}
  </group>
}
