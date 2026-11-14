import { useState, useEffect } from 'react'
import { Check, Cuboid, RefreshCw, X } from 'lucide-react'
import { api, type MeasurementRecord, type RoomReconstruction, type SavedRoom } from '../api'

export interface RoomPlan2DProps {
  measurement?: MeasurementRecord | null
  room?: SavedRoom | null
  dimensions?: [number, number, number]
  onClose?: () => void
  onApplyTo3D?: (dimensions: [number, number, number], devicePos: [number, number, number]) => void
  isInline?: boolean
}

export function RoomPlan2D({
  measurement,
  room,
  dimensions,
  onClose,
  onApplyTo3D,
  isInline = false,
}: RoomPlan2DProps) {
  const [reconstruction, setReconstruction] = useState<RoomReconstruction | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [applied, setApplied] = useState(false)
  const [ceilingHeight] = useState(room?.height_z_m ?? dimensions?.[2] ?? 2.8)
  const [centered] = useState(true)

  // Load reconstruction only if measurement is provided without room
  useEffect(() => {
    if (measurement && !room) {
      let active = true
      setLoading(true)
      setError('')
      api.reconstructRoom({
        measurement_id: measurement.id,
        default_ceiling_height_m: ceilingHeight,
        centered_assumption: centered,
      })
        .then(res => {
          if (active) setReconstruction(res)
        })
        .catch(e => {
          if (active) setError((e as Error).message)
        })
        .finally(() => {
          if (active) setLoading(false)
        })
      return () => { active = false }
    }
  }, [measurement?.id, ceilingHeight, centered, room])

  function handleApply() {
    const finalDims: [number, number, number] = room
      ? [room.length_x_m, room.width_y_m, room.height_z_m]
      : reconstruction?.estimated_dimensions_m ?? [5, 4, 2.8]
    const devPos: [number, number, number] = room
      ? (room.device_position_m as [number, number, number])
      : reconstruction?.device_position_m ?? [2.5, 2, 1]

    if (onApplyTo3D) {
      onApplyTo3D(finalDims, devPos)
    }
    setApplied(true)
    setTimeout(() => setApplied(false), 3000)
  }

  // Determine geometry parameters
  const lx = room?.length_x_m ?? reconstruction?.length_x_m ?? dimensions?.[0] ?? 5.0
  const ly = room?.width_y_m ?? reconstruction?.width_y_m ?? dimensions?.[1] ?? 4.0
  const lz = room?.height_z_m ?? reconstruction?.height_z_m ?? dimensions?.[2] ?? ceilingHeight
  const floorArea = room?.floor_area_m2 ?? reconstruction?.floor_area_m2 ?? Number((lx * ly).toFixed(1))
  const roomVolume = room?.room_volume_m3 ?? reconstruction?.room_volume_m3 ?? Number((lx * ly * lz).toFixed(1))

  const devX = room?.device_position_m?.[0] ?? reconstruction?.device_position_m[0] ?? lx / 2
  const devY = room?.device_position_m?.[1] ?? reconstruction?.device_position_m[1] ?? ly / 2

  const title = room?.name ?? measurement?.name ?? '2D Architectural Floor Plan'
  const obstacles = room?.obstacles ?? []
  const wallDistances = room?.wall_distances ?? {}

  // SVG viewport dimensions
  const svgWidth = isInline ? 640 : 560
  const svgHeight = isInline ? 440 : 400
  const margin = 55

  // Scale metres to SVG pixels
  const availableW = svgWidth - margin * 2
  const availableH = svgHeight - margin * 2
  const scale = Math.min(availableW / Math.max(lx, 1), availableH / Math.max(ly, 1))

  const roomPixelW = lx * scale
  const roomPixelH = ly * scale
  const roomOriginX = margin + (availableW - roomPixelW) / 2
  const roomOriginY = margin + (availableH - roomPixelH) / 2

  // In SVG coordinates: Y increases downwards. Let bottom be Y=0.
  const devPixelX = roomOriginX + devX * scale
  const devPixelY = roomOriginY + roomPixelH - devY * scale

  const echoDistances = reconstruction?.echo_distances_used ?? (measurement?.echo_candidates?.map(e => e.distance_m) ?? [])

  const content = (
    <div
      className="room-plan-container"
      style={{
        background: '#0b1013',
        border: isInline ? 'none' : '1px solid #27343d',
        borderRadius: isInline ? 0 : 12,
        width: '100%',
        maxWidth: isInline ? '100%' : 840,
        boxShadow: isInline ? 'none' : '0 24px 64px rgba(0,0,0,0.7)',
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {/* Plan Header */}
      <div
        style={{
          padding: '14px 20px',
          borderBottom: '1px solid #1a252c',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          background: '#0e1418',
        }}
      >
        <div>
          <div style={{ fontSize: 11, fontWeight: 700, color: '#00f5d4', letterSpacing: 1 }}>
            2D ACOUSTIC ROOM FLOOR PLAN
          </div>
          <h2 style={{ fontSize: 17, color: '#f0f6fc', margin: '2px 0 0 0' }}>
            {title}
          </h2>
        </div>
        {onClose && (
          <button className="icon-button" onClick={onClose} style={{ color: '#70808b' }}>
            <X size={18} />
          </button>
        )}
      </div>

      {/* Plan Body */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 260px', minHeight: 440 }}>
        {/* SVG Drawing Canvas */}
        <div style={{ padding: 20, display: 'flex', flexDirection: 'column', alignItems: 'center', background: '#090e11', justifyContent: 'center' }}>
          {loading ? (
            <div style={{ height: svgHeight, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#70808b', gap: 10 }}>
              <RefreshCw size={18} className="spinner" /> Calculating floor plan…
            </div>
          ) : error ? (
            <div style={{ height: svgHeight, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#f87171' }}>
              Error: {error}
            </div>
          ) : (
            <svg width={svgWidth} height={svgHeight} style={{ overflow: 'visible', maxWidth: '100%' }}>
              <defs>
                <pattern id="planGrid2" width={scale * 0.5} height={scale * 0.5} patternUnits="userSpaceOnUse">
                  <path d={`M ${scale * 0.5} 0 L 0 0 0 ${scale * 0.5}`} fill="none" stroke="#162228" strokeWidth="0.8" />
                </pattern>
              </defs>

              {/* Background Grid */}
              <rect x={roomOriginX} y={roomOriginY} width={roomPixelW} height={roomPixelH} fill="url(#planGrid2)" />

              {/* Room Boundary Box */}
              <rect
                x={roomOriginX}
                y={roomOriginY}
                width={roomPixelW}
                height={roomPixelH}
                fill="rgba(0, 245, 212, 0.04)"
                stroke="#00f5d4"
                strokeWidth="2.5"
                rx="4"
              />

              {/* Dimension Arrows and Labels */}
              {/* Horizontal Length (X) */}
              <line
                x1={roomOriginX}
                y1={roomOriginY - 20}
                x2={roomOriginX + roomPixelW}
                y2={roomOriginY - 20}
                stroke="#48d6df"
                strokeWidth="1.2"
              />
              <circle cx={roomOriginX} cy={roomOriginY - 20} r="2.5" fill="#48d6df" />
              <circle cx={roomOriginX + roomPixelW} cy={roomOriginY - 20} r="2.5" fill="#48d6df" />
              <text
                x={roomOriginX + roomPixelW / 2}
                y={roomOriginY - 28}
                fill="#48d6df"
                fontSize="12"
                fontWeight="700"
                textAnchor="middle"
              >
                Length (X): {lx.toFixed(2)} m
              </text>

              {/* Vertical Width (Y) */}
              <line
                x1={roomOriginX - 20}
                y1={roomOriginY}
                x2={roomOriginX - 20}
                y2={roomOriginY + roomPixelH}
                stroke="#48d6df"
                strokeWidth="1.2"
              />
              <circle cx={roomOriginX - 20} cy={roomOriginY} r="2.5" fill="#48d6df" />
              <circle cx={roomOriginX - 20} cy={roomOriginY + roomPixelH} r="2.5" fill="#48d6df" />
              <text
                x={roomOriginX - 28}
                y={roomOriginY + roomPixelH / 2}
                fill="#48d6df"
                fontSize="12"
                fontWeight="700"
                textAnchor="middle"
                transform={`rotate(-90 ${roomOriginX - 28} ${roomOriginY + roomPixelH / 2})`}
              >
                Width (Y): {ly.toFixed(2)} m
              </text>

              {/* Directional Wall Distance Rays if available */}
              {wallDistances.front && (
                <g>
                  <line x1={devPixelX} y1={devPixelY} x2={devPixelX} y2={roomOriginY} stroke="#38bdf8" strokeWidth="1" strokeDasharray="3 3" />
                  <text x={devPixelX + 6} y={(devPixelY + roomOriginY) / 2} fill="#38bdf8" fontSize="10" fontWeight="600">
                    Front: {wallDistances.front.toFixed(2)}m
                  </text>
                </g>
              )}
              {wallDistances.back && (
                <g>
                  <line x1={devPixelX} y1={devPixelY} x2={devPixelX} y2={roomOriginY + roomPixelH} stroke="#38bdf8" strokeWidth="1" strokeDasharray="3 3" />
                  <text x={devPixelX + 6} y={(devPixelY + roomOriginY + roomPixelH) / 2} fill="#38bdf8" fontSize="10" fontWeight="600">
                    Back: {wallDistances.back.toFixed(2)}m
                  </text>
                </g>
              )}
              {wallDistances.left && (
                <g>
                  <line x1={devPixelX} y1={devPixelY} x2={roomOriginX} y2={devPixelY} stroke="#38bdf8" strokeWidth="1" strokeDasharray="3 3" />
                  <text x={(devPixelX + roomOriginX) / 2} y={devPixelY - 6} fill="#38bdf8" fontSize="10" fontWeight="600" textAnchor="middle">
                    Left: {wallDistances.left.toFixed(2)}m
                  </text>
                </g>
              )}
              {wallDistances.right && (
                <g>
                  <line x1={devPixelX} y1={devPixelY} x2={roomOriginX + roomPixelW} y2={devPixelY} stroke="#38bdf8" strokeWidth="1" strokeDasharray="3 3" />
                  <text x={(devPixelX + roomOriginX + roomPixelW) / 2} y={devPixelY - 6} fill="#38bdf8" fontSize="10" fontWeight="600" textAnchor="middle">
                    Right: {wallDistances.right.toFixed(2)}m
                  </text>
                </g>
              )}

              {/* Echo distance circles if available */}
              {echoDistances.slice(0, 4).map((dist, idx) => {
                const circleRadius = dist * scale
                return (
                  <circle
                    key={`echo-c-${idx}`}
                    cx={devPixelX}
                    cy={devPixelY}
                    r={circleRadius}
                    fill="none"
                    stroke="#00f5d4"
                    strokeWidth="1.2"
                    strokeDasharray="4 3"
                    opacity={0.5}
                  />
                )
              })}

              {/* Obstacles plotted in room */}
              {obstacles.map((obs, idx) => {
                const d = Number(obs.distance_m)
                let ox = devPixelX
                let oy = devPixelY
                if (obs.direction === 'front') oy = devPixelY - d * scale
                else if (obs.direction === 'back') oy = devPixelY + d * scale
                else if (obs.direction === 'right') ox = devPixelX + d * scale
                else if (obs.direction === 'left') ox = devPixelX - d * scale
                else {
                  ox = devPixelX + d * scale * 0.707
                  oy = devPixelY - d * scale * 0.707
                }

                return (
                  <g key={`obs-svg-${idx}`}>
                    <rect
                      x={ox - 16}
                      y={oy - 12}
                      width={32}
                      height={24}
                      fill="rgba(245, 158, 11, 0.85)"
                      stroke="#f59e0b"
                      strokeWidth="1.5"
                      rx="3"
                    />
                    <text x={ox} y={oy + 22} fill="#f59e0b" fontSize="10" fontWeight="700" textAnchor="middle">
                      {obs.label || `Obstacle (${obs.direction})`}
                    </text>
                    <text x={ox} y={oy + 33} fill="#d97706" fontSize="9" textAnchor="middle">
                      {d.toFixed(2)} m
                    </text>
                  </g>
                )
              })}

              {/* BatSight Device Marker */}
              <circle cx={devPixelX} cy={devPixelY} r="10" fill="#50d5df" stroke="#0e1418" strokeWidth="2.5" />
              <circle cx={devPixelX} cy={devPixelY} r="3.5" fill="#ffffff" />
              <text x={devPixelX} y={devPixelY + 22} fill="#f0f6fc" fontSize="11" fontWeight="700" textAnchor="middle">
                BatSight Device
              </text>
              <text x={devPixelX} y={devPixelY + 34} fill="#8b949e" fontSize="9" textAnchor="middle">
                ({devX.toFixed(2)}, {devY.toFixed(2)}) m
              </text>
            </svg>
          )}

          {/* Canvas Legend */}
          <div style={{ display: 'flex', gap: 18, marginTop: 16, fontSize: 11, color: '#70808b' }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ width: 14, height: 2.5, background: '#00f5d4', display: 'inline-block' }} /> Walls
            </span>
            <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#50d5df', display: 'inline-block' }} /> Device
            </span>
            <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ width: 12, height: 10, background: '#f59e0b', borderRadius: 2, display: 'inline-block' }} /> Obstacles
            </span>
          </div>
        </div>

        {/* Right Metrics & Details Sidebar */}
        <div style={{ padding: 20, borderLeft: '1px solid #1a252c', display: 'flex', flexDirection: 'column', gap: 16, background: '#0c1215' }}>
          <div>
            <div style={{ fontSize: 11, color: '#70808b', fontWeight: 600 }}>ROOM GEOMETRY</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 8 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid #182228', paddingBottom: 4 }}>
                <span style={{ color: '#8b949e', fontSize: 12 }}>Length (X)</span>
                <b style={{ color: '#00f5d4' }}>{lx.toFixed(2)} m</b>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid #182228', paddingBottom: 4 }}>
                <span style={{ color: '#8b949e', fontSize: 12 }}>Width (Y)</span>
                <b style={{ color: '#00f5d4' }}>{ly.toFixed(2)} m</b>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid #182228', paddingBottom: 4 }}>
                <span style={{ color: '#8b949e', fontSize: 12 }}>Height (Z)</span>
                <b style={{ color: '#f0f6fc' }}>{lz.toFixed(2)} m</b>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid #182228', paddingBottom: 4 }}>
                <span style={{ color: '#8b949e', fontSize: 12 }}>Floor Area</span>
                <b style={{ color: '#f0f6fc' }}>{floorArea.toFixed(1)} m²</b>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: 4 }}>
                <span style={{ color: '#8b949e', fontSize: 12 }}>Room Volume</span>
                <b style={{ color: '#f0f6fc' }}>{roomVolume.toFixed(1)} m³</b>
              </div>
            </div>
          </div>

          {/* Obstacles list */}
          {obstacles.length > 0 && (
            <div>
              <div style={{ fontSize: 11, color: '#f59e0b', fontWeight: 600, marginBottom: 8 }}>
                DETECTED OBSTACLES ({obstacles.length})
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {obstacles.map((obs, i) => (
                  <div key={i} style={{ background: '#131b20', border: '1px solid #293842', padding: '6px 10px', borderRadius: 4, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: 11, color: '#f0f6fc' }}>
                      📦 {obs.label || `Obstacle in ${obs.direction}`}
                    </span>
                    <b style={{ fontSize: 11, color: '#f59e0b' }}>
                      {Number(obs.distance_m).toFixed(2)} m
                    </b>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Wall distances */}
          {Object.keys(wallDistances).length > 0 && (
            <div>
              <div style={{ fontSize: 11, color: '#38bdf8', fontWeight: 600, marginBottom: 8 }}>
                WALL DISTANCES
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
                {Object.entries(wallDistances).map(([k, v]) => (
                  <div key={k} style={{ background: '#10161a', border: '1px solid #1c272e', padding: '4px 8px', borderRadius: 4 }}>
                    <div style={{ fontSize: 10, color: '#70808b', textTransform: 'capitalize' }}>{k}</div>
                    <div style={{ fontSize: 11, fontWeight: 700, color: '#38bdf8' }}>{Number(v).toFixed(2)} m</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div style={{ marginTop: 'auto', display: 'flex', flexDirection: 'column', gap: 8 }}>
            {onApplyTo3D && (
              <button
                className={`button ${applied ? 'accent' : 'primary'} full-button`}
                onClick={handleApply}
                disabled={loading}
                style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}
              >
                {applied ? <Check size={16} /> : <Cuboid size={16} />}
                {applied ? 'Applied to 3D Scene!' : 'Apply to 3D Scene'}
              </button>
            )}
            {onClose && (
              <button className="button subtle full-button" onClick={onClose}>
                Close
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )

  if (isInline) {
    return content
  }

  return (
    <div
      className="room-plan-modal-backdrop"
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(5, 10, 14, 0.85)',
        backdropFilter: 'blur(6px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
        padding: 20,
      }}
    >
      {content}
    </div>
  )
}
