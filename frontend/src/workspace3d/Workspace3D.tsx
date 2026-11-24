import { useEffect, useRef, useState } from 'react'
import { Canvas, useThree } from '@react-three/fiber'
import { GizmoHelper, GizmoViewport, Html, OrbitControls, TransformControls } from '@react-three/drei'
import type { Group } from 'three'
import { Camera, Cuboid, Grid3X3, LayoutDashboard, Maximize2, RotateCcw, Save, Layers, CheckCircle2 } from 'lucide-react'
import { RoomPlan2D } from './RoomPlan2D'
import { api, type MeasurementRecord, type SavedRoom, type Smard0001ReconstructionResponse } from '../api'
import { cameraOrientation, type CameraView } from './cameraOrientation'
import { clampInside, createDefaultScene, parseSceneDocument, serializeScene, type Equipment, type SceneDocument, type Vec3 } from './sceneModel'

type Props = {selectedProject?: number; setToast: (value:{kind:'error'|'success'|'info';text:string})=>void}
type View = CameraView
type Display = {grid:boolean;axes:boolean;walls:boolean;labels:boolean}
const displayDefault:Display={grid:true,axes:true,walls:true,labels:true}
const colorFor=(kind:Equipment['kind'])=>kind==='speaker'?'#f3a75c':'#50d5df'

export function Workspace3D({selectedProject,setToast}:Props) {
  const [scene,setScene]=useState<SceneDocument>(()=>parseSceneDocument(localStorage.getItem(sceneKey(selectedProject))))
  const [display,setDisplay]=useState<Display>(()=>{try{return {...displayDefault,...JSON.parse(localStorage.getItem('batsight-3d-display')||'{}')}}catch{return displayDefault}})
  const [viewMode,setViewMode]=useState<'3d'|'2d'>('3d')
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

  return <div className="workspace3d">
    {/* Clean Header */}
    <div className="ws-head">
      <div>
        <div className="ws-eyebrow">SPATIAL INSPECTION</div>
        <h1>3D & 2D Rooms</h1>
        <p>Inspect room geometry, device placement, and interior obstacles in 3D wireframe or 2D architectural blueprint.</p>
      </div>
      <div className="ws-head-actions">
        <button
          className={`ws-button ${smardData ? 'on' : ''}`}
          onClick={loadSmardPreset}
          disabled={loadingSmard}
          style={smardData ? { borderColor: '#a855f7', color: '#d8b4fe', background: '#2e1065', fontWeight: 600 } : {}}
          title="Load SMARD 0001 real measured acoustic room benchmark"
        >
          <Layers size={14} /> {loadingSmard ? 'Loading SMARD…' : 'SMARD 0001 (Real Room)'}
        </button>
        <label className="ws-select">
          <span>Saved Room</span>
          <select value={roomId} onChange={e=>selectRoom(e.target.value?Number(e.target.value):'')}>
            <option value="">Select Room…</option>
            {rooms.map(r=><option key={r.id} value={r.id}>🏠 {r.name} ({r.length_x_m} × {r.width_y_m} m)</option>)}
          </select>
        </label>
        <label className="ws-select">
          <span>Real measurement</span>
          <select value={measurementId} onChange={event=>{setMeasurementId(event.target.value?Number(event.target.value):'');setSelectedEchoIndex(null)}}>
            <option value="">None</option>
            {measurements.map(item=><option key={item.id} value={item.id}>📡 {item.name} ({item.echo_count} echoes)</option>)}
          </select>
        </label>
        <button className="ws-button" onClick={()=>{setScene(createDefaultScene());setSelectedId(null);setRoomId('');setSmardData(null)}} title="Reset to default room box">
          <RotateCcw size={14}/> Reset
        </button>
      </div>
    </div>

    {/* Status badge when room is loaded */}
    {selectedRoom&&<div className="ws-provenance" style={{background:'#0c1f28',borderColor:'#00f5d4',color:'#e6fffa',display:'flex',justifyContent:'space-between',alignItems:'center',padding:'8px 16px',borderRadius:6,margin:'0 0 12px 0'}}>
      <div>
        <b style={{color:'#00f5d4',display:'inline-flex',alignItems:'center',gap:6}}>
          <span style={{width:8,height:8,borderRadius:'50%',background:'#00f5d4',display:'inline-block'}}/>
          {selectedRoom.name}
        </b>
        <span style={{marginLeft:12,color:'#94a3b8',fontSize:13}}>
          {selectedRoom.length_x_m} × {selectedRoom.width_y_m} × {selectedRoom.height_z_m} m · {selectedRoom.floor_area_m2} m² · {selectedRoom.obstacles?.length||0} obstacle(s)
        </span>
      </div>
      <button style={{background:'#163542',color:'#00f5d4',border:'1px solid #00f5d4',borderRadius:4,padding:'3px 10px',cursor:'pointer',fontSize:12}} onClick={()=>setRoomId('')}>
        Clear Selection
      </button>
    </div>}

    {selectedMeasurement&&<div className="ws-provenance" style={{background:'#032e2b',borderColor:'#00f5d4',color:'#e6fffa',display:'flex',justifyContent:'space-between',alignItems:'center',padding:'8px 16px',borderRadius:6,margin:'0 0 12px 0'}}>
      <div>
        <b style={{color:'#00f5d4',display:'inline-flex',alignItems:'center',gap:6}}>
          <span style={{width:8,height:8,borderRadius:'50%',background:'#00f5d4',display:'inline-block'}}/>
          {selectedMeasurement.name}
        </b>
        <span style={{marginLeft:12,color:'#94a3b8',fontSize:13}}>
          {selectedMeasurement.echo_count} echo reflection(s) detected · Calibrated at {selectedMeasurement.speed_of_sound_m_s} m/s
        </span>
      </div>
      <button style={{background:'#044e46',color:'#00f5d4',border:'1px solid #00f5d4',borderRadius:4,padding:'3px 10px',cursor:'pointer',fontSize:12}} onClick={()=>setMeasurementId('')}>
        Dismiss
      </button>
    </div>}

    {smardData && (
      <div className="ws-provenance" style={{background:'#1e1035',borderColor:'#a855f7',color:'#f3e8ff',display:'flex',justifyContent:'space-between',alignItems:'center',padding:'8px 16px',borderRadius:6,margin:'0 0 12px 0',flexWrap:'wrap',gap:8}}>
        <div style={{display:'flex',alignItems:'center',gap:12,flexWrap:'wrap'}}>
          <b style={{color:'#c084fc',display:'inline-flex',alignItems:'center',gap:6}}>
            <span style={{width:8,height:8,borderRadius:'50%',background:'#a855f7',display:'inline-block'}}/>
            SMARD 0001 (Real Measured Room Benchmark)
          </b>
          <span style={{color:'#d8b4fe',fontSize:11,background:'#3b0764',padding:'2px 8px',borderRadius:4,border:'1px solid #7e22ce',fontWeight:600}}>
            ESTIMATED (CALIBRATED REAL DATA)
          </span>
          <span style={{color:'#e9d5ff',fontSize:12}}>
            Loopback delay: {smardData.diagnostics.timing_provenance.calibrated_loopback_offset_ms.toFixed(3)} ms applied · 132/132 reflections converged
          </span>
        </div>
        <div style={{display:'flex',alignItems:'center',gap:12}}>
          <label style={{display:'flex',alignItems:'center',gap:6,fontSize:12,cursor:'pointer',color:'#f3e8ff',userSelect:'none'}}>
            <input type="checkbox" checked={showGroundTruth} onChange={e=>setShowGroundTruth(e.target.checked)} style={{accentColor:'#f59e0b'}} />
            Show Ground Truth Box
          </label>
          <button style={{background:'#4c1d95',color:'#e9d5ff',border:'1px solid #a855f7',borderRadius:4,padding:'3px 10px',cursor:'pointer',fontSize:12}} onClick={()=>setSmardData(null)}>
            Dismiss
          </button>
        </div>
      </div>
    )}

    {/* Toolbar */}
    <div className="ws-toolbar" style={{display:'flex',justifyContent:'space-between',alignItems:'center',flexWrap:'wrap',gap:8}}>
      <div style={{display:'flex',gap:8,alignItems:'center'}}>
        {/* View Mode Switcher */}
        <div className="ws-tool-group">
          <button className={viewMode==='3d'?'on':''} onClick={()=>setViewMode('3d')} style={viewMode==='3d'?{borderColor:'#00f5d4',color:'#00f5d4',background:'#062d2b'}:{}}>
            <Cuboid size={14}/> 3D View
          </button>
          <button className={viewMode==='2d'?'on':''} onClick={()=>setViewMode('2d')} style={viewMode==='2d'?{borderColor:'#00f5d4',color:'#00f5d4',background:'#062d2b'}:{}}>
            <LayoutDashboard size={14}/> 2D Floor Plan
          </button>
        </div>

        {/* View Elements */}
        {viewMode==='3d'&&<div className="ws-tool-group">
          <button className={display.grid?'on':''} onClick={()=>updateDisplay('grid',!display.grid)} title="Toggle floor grid"><Grid3X3 size={15}/> Grid</button>
          <button className={display.axes?'on':''} onClick={()=>updateDisplay('axes',!display.axes)} title="Toggle coordinate axes">XYZ</button>
          <button className={display.walls?'on':''} onClick={()=>updateDisplay('walls',!display.walls)} title="Toggle room walls">Walls</button>
          <button className={display.labels?'on':''} onClick={()=>updateDisplay('labels',!display.labels)} title="Toggle labels">Labels</button>
          {selectedMeasurement&&<button className={displaySpheres?'on':''} style={displaySpheres?{borderColor:'#00f5d4',color:'#00f5d4'}:{}} onClick={()=>setDisplaySpheres(!displaySpheres)} title="Toggle measured echo distance spheres">Echo spheres</button>}
        </div>}
      </div>

      {viewMode==='3d'&&<div className="ws-tool-group">
        <button onClick={()=>setView('top')}>Top</button>
        <button onClick={()=>setView('front')}>Front</button>
        <button onClick={()=>setView('side')}>Side</button>
        <button onClick={()=>setView('iso')}><Camera size={14}/> Iso</button>
        <button onClick={()=>setView('iso')} title="Fit room to view"><Maximize2 size={13}/> Fit</button>
        <span className="ws-hint">Drag to orbit · right-drag to pan · scroll to zoom</span>
      </div>}
    </div>

    {/* Main Content Layout */}
    <div className="ws-layout" style={{display:'grid',gridTemplateColumns:'1fr 300px',gap:16,minHeight:560}}>
      {/* Primary Viewport */}
      <section className="ws-viewport" style={{background:'#0b1013',borderRadius:8,overflow:'hidden',position:'relative',display:'flex',flexDirection:'column'}}>
        {viewMode === '2d' ? (
          <div style={{ width: '100%', height: '100%', overflow: 'auto', background: '#090e11', padding: 12 }}>
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
          <div className="ws-canvas" style={{flex:1,position:'relative',minHeight:500}}>
            <Canvas camera={{position:[dimensions[0]*1.4,-dimensions[1]*1.6,dimensions[2]*1.3],fov:42,near:.01,far:2000,up:[0,0,1]}} onCreated={({camera})=>{camera.up.set(0,0,1)}}>
              <color attach="background" args={['#0e1418']}/>
              <ambientLight intensity={1.5}/>
              <directionalLight position={[6,-5,9]} intensity={2.4}/>
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
              <GizmoHelper alignment="bottom-right" margin={[65,65]}><GizmoViewport axisColors={['#f57474','#6bd58a','#58cbe0']} labelColor="white"/></GizmoHelper>
            </Canvas>
            <div className="ws-corner-label">X LENGTH · Y WIDTH · Z HEIGHT</div>
            <div className="ws-legend" style={{position:'absolute',bottom:12,left:12,display:'flex',gap:12,fontSize:11,background:'rgba(14,20,24,0.85)',padding:'6px 12px',borderRadius:6,border:'1px solid #1e2830',flexWrap:'wrap'}}>
              <span style={{display:'flex',alignItems:'center',gap:5}}><span style={{width:12,height:2,background:'#00f5d4',display:'inline-block'}}/>{smardData ? 'Estimated Room' : 'Room Boundary'}</span>
              {smardData && showGroundTruth && (
                <span style={{display:'flex',alignItems:'center',gap:5}}><span style={{width:12,height:2,background:'#f59e0b',display:'inline-block'}}/>Ground Truth Box</span>
              )}
              <span style={{display:'flex',alignItems:'center',gap:5}}><span style={{width:8,height:8,borderRadius:'50%',background:smardData?'#f3a75c':'#50d5df',display:'inline-block'}}/>{smardData ? 'Loudspeaker (Ch 08)' : 'BatSight Device'}</span>
              {smardData && (
                <span style={{display:'flex',alignItems:'center',gap:5}}><span style={{width:8,height:8,borderRadius:'50%',background:'#50d5df',display:'inline-block'}}/>22 Microphones</span>
              )}
              {!smardData && (
                <span style={{display:'flex',alignItems:'center',gap:5}}><span style={{width:8,height:8,borderRadius:2,background:'#f59e0b',display:'inline-block'}}/>Obstacles</span>
              )}
            </div>
          </div>
        )}
        <div className="ws-status" style={{background:'#090d10',padding:'8px 14px',display:'flex',justifyContent:'space-between',fontSize:11,color:'#70808b',borderTop:'1px solid #1a242a'}}>
          <span>{selectedRoom?`ROOM: ${selectedRoom.name}`:selectedMeasurement?`MEASUREMENT: ${selectedMeasurement.name}`:'ACTIVE SCENE'}</span>
          <span>Dimensions: {dimensions.map(x=>x.toFixed(2)).join(' × ')} m</span>
          <span>c = {speed.toFixed(1)} m/s</span>
        </div>
      </section>

      {/* Clean Right Inspector Panel */}
      <aside className="ws-panel ws-inspector" style={{background:'#0e1418',border:'1px solid #202b32',borderRadius:8,padding:16,display:'flex',flexDirection:'column',gap:14}}>
        <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',borderBottom:'1px solid #1e2830',paddingBottom:10}}>
          <b style={{fontSize:14,color:'#f0f6fc'}}>{smardData ? 'SMARD Benchmark' : selectedRoom ? 'Room Details' : 'Scene Properties'}</b>
          <span style={{fontSize:11,color: smardData ? '#c084fc' : selectedRoom ? '#00f5d4' : '#00f5d4',fontWeight:600}}>
            {smardData ? 'CALIBRATED ESTIMATE' : selectedRoom ? 'SAVED ROOM' : 'EDITABLE'}
          </span>
        </div>

        {smardData ? (
          <>
            <div>
              <div style={{display:'flex',alignItems:'center',gap:8,background:'#2e1065',border:'1px solid #7e22ce',padding:'8px 10px',borderRadius:6,marginBottom:12}}>
                <CheckCircle2 size={16} color="#c084fc" style={{flexShrink:0}} />
                <div>
                  <div style={{fontSize:11,fontWeight:700,color:'#f3e8ff'}}>ESTIMATED (CALIBRATED REAL DATA)</div>
                  <div style={{fontSize:10,color:'#d8b4fe'}}>SMARD Config 0001 · 22 Mics Acoustic Array</div>
                </div>
              </div>

              <div style={{fontSize:11,color:'#c084fc',fontWeight:600,marginBottom:6}}>ESTIMATED VS GROUND TRUTH</div>
              <table style={{width:'100%',borderCollapse:'collapse',fontSize:11,marginBottom:12}}>
                <thead>
                  <tr style={{color:'#94a3b8',borderBottom:'1px solid #1e2830',textAlign:'left'}}>
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
                      <tr key={row.axis} style={{borderBottom:'1px solid #182228'}}>
                        <td style={{padding:'5px 2px',color:'#cbd5e1',fontWeight:600}}>{row.name}</td>
                        <td style={{padding:'5px 2px',textAlign:'right',color:'#94a3b8'}}>{row.gt.toFixed(3)} m</td>
                        <td style={{padding:'5px 2px',textAlign:'right',color:'#00f5d4',fontWeight:700}}>{row.est.toFixed(3)} m</td>
                        <td style={{padding:'5px 2px',textAlign:'right',color: Math.abs(diffCm) < 8 ? '#4ade80' : '#f59e0b',fontWeight:600}}>
                          {diffCm >= 0 ? `+${diffCm.toFixed(1)}` : diffCm.toFixed(1)} cm ({relPct >= 0 ? `+${relPct.toFixed(2)}` : relPct.toFixed(2)}%)
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>

            <div>
              <div style={{fontSize:11,color:'#38bdf8',fontWeight:600,marginBottom:6}}>SOLVER DIAGNOSTICS</div>
              <div style={{display:'flex',flexDirection:'column',gap:5,fontSize:11}}>
                <div style={{display:'flex',justifyContent:'space-between',borderBottom:'1px solid #182228',paddingBottom:4}}>
                  <span style={{color:'#8b949e'}}>Residual RMS</span>
                  <b style={{color:'#38bdf8'}}>{smardData.diagnostics.residual_rms_ms.toFixed(3)} ms</b>
                </div>
                <div style={{display:'flex',justifyContent:'space-between',borderBottom:'1px solid #182228',paddingBottom:4}}>
                  <span style={{color:'#8b949e'}}>Jacobian Rank / Cond</span>
                  <b style={{color:'#f0f6fc'}}>{smardData.diagnostics.jacobian_rank} / 3 (cond {smardData.diagnostics.jacobian_condition_number.toFixed(2)})</b>
                </div>
                <div style={{display:'flex',justifyContent:'space-between',borderBottom:'1px solid #182228',paddingBottom:4}}>
                  <span style={{color:'#8b949e'}}>Optimizer Status</span>
                  <b style={{color:'#4ade80'}}>{smardData.diagnostics.optimizer_status}</b>
                </div>
                <div style={{display:'flex',justifyContent:'space-between',borderBottom:'1px solid #182228',paddingBottom:4}}>
                  <span style={{color:'#8b949e'}}>Reflections Used</span>
                  <b style={{color:'#f0f6fc'}}>{smardData.diagnostics.total_reflections_used} (22 per wall)</b>
                </div>
                <div style={{display:'flex',justifyContent:'space-between',borderBottom:'1px solid #182228',paddingBottom:4}}>
                  <span style={{color:'#8b949e'}}>Hardware Timing Offset</span>
                  <b style={{color:'#e879f9'}}>{smardData.diagnostics.timing_provenance.calibrated_loopback_offset_ms.toFixed(3)} ms</b>
                </div>
                <div style={{display:'flex',justifyContent:'space-between',paddingBottom:4}}>
                  <span style={{color:'#8b949e'}}>Speed of Sound (c)</span>
                  <b style={{color:'#f0f6fc'}}>{smardData.diagnostics.timing_provenance.speed_of_sound_mps.toFixed(1)} m/s (21.6 °C)</b>
                </div>
              </div>
            </div>

            <div style={{marginTop:'auto',display:'flex',flexDirection:'column',gap:8}}>
              <label style={{display:'flex',alignItems:'center',gap:6,fontSize:11,cursor:'pointer',color:'#f3e8ff'}}>
                <input type="checkbox" checked={showGroundTruth} onChange={e=>setShowGroundTruth(e.target.checked)} style={{accentColor:'#f59e0b'}} />
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
              <div style={{fontSize:11,color:'#70808b',fontWeight:600,marginBottom:6}}>DIMENSIONS & VOLUME</div>
              <div style={{display:'flex',flexDirection:'column',gap:6}}>
                <div style={{display:'flex',justifyContent:'space-between',fontSize:12,borderBottom:'1px solid #182228',paddingBottom:4}}>
                  <span style={{color:'#8b949e'}}>Length (X)</span>
                  <b style={{color:'#00f5d4'}}>{selectedRoom.length_x_m.toFixed(2)} m</b>
                </div>
                <div style={{display:'flex',justifyContent:'space-between',fontSize:12,borderBottom:'1px solid #182228',paddingBottom:4}}>
                  <span style={{color:'#8b949e'}}>Width (Y)</span>
                  <b style={{color:'#00f5d4'}}>{selectedRoom.width_y_m.toFixed(2)} m</b>
                </div>
                <div style={{display:'flex',justifyContent:'space-between',fontSize:12,borderBottom:'1px solid #182228',paddingBottom:4}}>
                  <span style={{color:'#8b949e'}}>Height (Z)</span>
                  <b style={{color:'#f0f6fc'}}>{selectedRoom.height_z_m.toFixed(2)} m</b>
                </div>
                <div style={{display:'flex',justifyContent:'space-between',fontSize:12,borderBottom:'1px solid #182228',paddingBottom:4}}>
                  <span style={{color:'#8b949e'}}>Floor Area</span>
                  <b style={{color:'#f0f6fc'}}>{selectedRoom.floor_area_m2} m²</b>
                </div>
                <div style={{display:'flex',justifyContent:'space-between',fontSize:12,paddingBottom:4}}>
                  <span style={{color:'#8b949e'}}>Room Volume</span>
                  <b style={{color:'#f0f6fc'}}>{selectedRoom.room_volume_m3} m³</b>
                </div>
              </div>
            </div>

            {/* Wall Distances */}
            {selectedRoom.wall_distances&&Object.keys(selectedRoom.wall_distances).length>0&&(
              <div>
                <div style={{fontSize:11,color:'#38bdf8',fontWeight:600,marginBottom:6}}>MEASURED WALL DISTANCES</div>
                <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:6}}>
                  {Object.entries(selectedRoom.wall_distances).map(([k,v])=>(
                    <div key={k} style={{background:'#12191e',border:'1px solid #202b32',padding:'5px 8px',borderRadius:4}}>
                      <div style={{fontSize:10,color:'#70808b',textTransform:'capitalize'}}>{k}</div>
                      <div style={{fontSize:12,fontWeight:700,color:'#38bdf8'}}>{Number(v).toFixed(2)} m</div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Detected Obstacles list */}
            <div>
              <div style={{fontSize:11,color:'#f59e0b',fontWeight:600,marginBottom:6}}>
                DETECTED OBSTACLES ({selectedRoom.obstacles?.length||0})
              </div>
              {selectedRoom.obstacles&&selectedRoom.obstacles.length>0 ? (
                <div style={{display:'flex',flexDirection:'column',gap:6}}>
                  {selectedRoom.obstacles.map((obs,i)=>(
                    <div key={i} style={{background:'#141b20',border:'1px solid #2b3944',padding:'6px 10px',borderRadius:4,display:'flex',justifyContent:'space-between',alignItems:'center'}}>
                      <span style={{fontSize:11,color:'#f0f6fc'}}>📦 {obs.label||`Obstacle (${obs.direction})`}</span>
                      <b style={{fontSize:11,color:'#f59e0b'}}>{Number(obs.distance_m).toFixed(2)} m</b>
                    </div>
                  ))}
                </div>
              ) : (
                <p style={{fontSize:12,color:'#70808b',margin:0}}>No interior obstacles detected.</p>
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
              <div style={{fontSize:11,color:'#70808b',fontWeight:600,marginBottom:8}}>ROOM DIMENSIONS (METRES)</div>
              <div style={{display:'flex',flexDirection:'column',gap:8}}>
                {(['Length (X)','Width (Y)','Height (Z)'] as const).map((label,index)=>(
                  <label key={label} style={{display:'flex',justifyContent:'space-between',alignItems:'center',fontSize:12,color:'#8b949e'}}>
                    <span>{label}</span>
                    <input
                      type="number"
                      min="0.5"
                      max="100"
                      step="0.1"
                      value={scene.room_dimensions_m[index]}
                      onChange={event=>updateDimensions(index,Number(event.target.value))}
                      style={{background:'#090d10',border:'1px solid #25333d',color:'#f0f6fc',padding:'4px 8px',borderRadius:4,width:75,textAlign:'right'}}
                    />
                  </label>
                ))}
              </div>
            </div>

            {selected&&<div style={{borderTop:'1px solid #1e2830',paddingTop:12}}>
              <div style={{fontSize:11,color:'#50d5df',fontWeight:600,marginBottom:6}}>SELECTED OBJECT</div>
              <div style={{fontSize:12,color:'#f0f6fc',fontWeight:600,marginBottom:6}}>{selected.name}</div>
              <div style={{display:'flex',flexDirection:'column',gap:6}}>
                {(['X','Y','Z'] as const).map((axis,index)=>(
                  <label key={axis} style={{display:'flex',justifyContent:'space-between',alignItems:'center',fontSize:11,color:'#8b949e'}}>
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
                      style={{background:'#090d10',border:'1px solid #25333d',color:'#f0f6fc',padding:'3px 6px',borderRadius:4,width:70,textAlign:'right'}}
                    />
                  </label>
                ))}
              </div>
            </div>}
          </>
        )}
      </aside>
    </div>

    <div className="ws-footer" style={{marginTop:12,display:'flex',justifyContent:'space-between',fontSize:12,color:'#70808b'}}>
      <span><Save size={13}/> Scene saved locally.</span>
      <span>Toggle between 3D View and 2D Floor Plan anytime.</span>
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
        <meshBasicMaterial color="#38bdf8" transparent opacity={.065} side={2}/>
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
      <span className="ws-3d-label" style={{background:'#0c1e28',borderColor:'#00f5d4',color:'#00f5d4',fontWeight:700,fontSize:11,padding:'3px 8px',borderRadius:4}}>
        ROOM · {x.toFixed(2)} × {y.toFixed(2)} × {z.toFixed(2)} m
      </span>
    </Html>}
  </group>
}

function WallLabels({dimensions}:{dimensions:Vec3}){
  const [x,y,z]=dimensions
  const points:[string,Vec3][]=[['Front (Y+)',[x/2,y,z/2]],['Back (Y-)',[x/2,0,z/2]],['Left (X-)',[0,y/2,z/2]],['Right (X+)',[x,y/2,z/2]]]
  return <>{points.map(([label,point])=><Html key={label} position={point} center distanceFactor={19}><span className="ws-3d-label wall" style={{fontSize:10}}>{label}</span></Html>)}</>
}

function RoomPlane({position,size,rotation}:{position:Vec3;size:[number,number];rotation:Vec3}){
  return <mesh position={position} rotation={rotation}><planeGeometry args={size}/><meshBasicMaterial color="#1b2a30" transparent opacity={.22} side={2}/></mesh>
}

function RoomEdges({dimensions}:{dimensions:Vec3}){
  const [x,y,z]=dimensions
  const vertices:Vec3[]=[[0,0,0],[x,0,0],[x,y,0],[0,y,0],[0,0,z],[x,0,z],[x,y,z],[0,y,z]]
  const edges=[[0,1],[1,2],[2,3],[3,0],[4,5],[5,6],[6,7],[7,4],[0,4],[1,5],[2,6],[3,7]]
  return <>{edges.map(([a,b],i)=><Line3 key={i} start={vertices[a]} end={vertices[b]} color="#00f5d4" opacity={0.85}/>)}</>
}

function GroundTruthRoomOverlay({dimensions,labels}:{dimensions:Vec3;labels:boolean}){
  const [x,y,z]=dimensions
  const vertices:Vec3[]=[[0,0,0],[x,0,0],[x,y,0],[0,y,0],[0,0,z],[x,0,z],[x,y,z],[0,y,z]]
  const edges=[[0,1],[1,2],[2,3],[3,0],[4,5],[5,6],[6,7],[7,4],[0,4],[1,5],[2,6],[3,7]]
  return <group>
    <mesh position={[x/2,y/2,z/2]}>
      <boxGeometry args={[x,y,z]}/>
      <meshBasicMaterial color="#f59e0b" transparent opacity={.04} side={2}/>
    </mesh>
    {edges.map(([a,b],i)=><Line3 key={i} start={vertices[a]} end={vertices[b]} color="#f59e0b" opacity={0.85}/>)}
    {labels&&<Html position={[x/2,y/2,z+.28]} center distanceFactor={18}>
      <span className="ws-3d-label" style={{background:'#2e1904',borderColor:'#f59e0b',color:'#f59e0b',fontWeight:700,fontSize:11,padding:'3px 8px',borderRadius:4}}>
        GROUND TRUTH · {x.toFixed(2)} × {y.toFixed(2)} × {z.toFixed(2)} m
      </span>
    </Html>}
  </group>
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
  return <gridHelper args={[maxDim*1.4,Math.ceil(maxDim*2),'#35484c','#1a262a']} position={[x/2,y/2,0.001]} rotation={[Math.PI/2,0,0]} />
}

function EquipmentLayer({items,selectedId,editable,onSelect,onMove,labels}:{items:Equipment[];selectedId:string|null;editable:boolean;onSelect:(id:string|null)=>void;onMove:(id:string,point:Vec3)=>void;labels:boolean}){
  return <>{items.filter(item=>item.visible).map(item=>{const marker=<EquipmentMarker key={item.id} item={item} selected={selectedId===item.id} labels={labels} onSelect={()=>onSelect(item.id)}/>;return editable&&selectedId===item.id?<TransformControls key={`control-${item.id}`} mode="translate" showX showY showZ onObjectChange={(event:any)=>{const object=event?.target?.object as Group|undefined;if(object)onMove(item.id,[object.position.x,object.position.y,object.position.z])}} onMouseUp={(event:any)=>{const object=event?.target?.object as Group|undefined;if(object)onMove(item.id,[object.position.x,object.position.y,object.position.z])}}>{marker}</TransformControls>:marker})}</>
}

function EquipmentMarker({item,selected,labels,onSelect}:{item:Equipment;selected:boolean;labels:boolean;onSelect:()=>void}){
  return <group position={item.position_m} onClick={event=>{event.stopPropagation();onSelect()}}>
    <mesh>
      <sphereGeometry args={[.11,20,14]}/>
      <meshStandardMaterial color={colorFor(item.kind)} emissive={colorFor(item.kind)} emissiveIntensity={selected ? .4 : .1}/>
    </mesh>
    <mesh position={[0,0,.16]} rotation={[0,0,item.orientation_yaw_deg*Math.PI/180]}>
      <cylinderGeometry args={item.kind==='speaker'?[.045,.075,.12,16]:[.028,.05,.12,12]}/>
      <meshStandardMaterial color={colorFor(item.kind)}/>
    </mesh>
    {selected&&<mesh><sphereGeometry args={[.18,16,12]}/><meshBasicMaterial color="#8cf4fa" wireframe transparent opacity={.55}/></mesh>}
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
