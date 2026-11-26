import {describe, expect, it} from 'vitest'
import {clampInside, createDefaultScene, isStrictlyInside, parseSceneDocument, reflectionPointFromImage, serializeScene, validateScene} from './sceneModel'
import {editableSceneFromExperiment, parseSyntheticExperiment} from './experimentGeometry'
import backendStoredExperiment from './fixtures/synthetic_experiment_result.json'

describe('shoebox scene model',()=>{
  it('uses the corner-origin x-length y-width z-height convention and metre dimensions',()=>{
    const scene=createDefaultScene()
    expect(scene.coordinate_convention).toBe('corner_origin_x_length_y_width_z_height')
    expect(scene.unit).toBe('m')
    expect(scene.room_dimensions_m).toEqual([6,5,3])
    expect(scene.speed_of_sound_m_s).toBe(343)
    expect(scene.equipment.every(item=>isStrictlyInside(item.position_m,scene.room_dimensions_m))).toBe(true)
  })
  it('clamps dragged objects to strict room interior and rejects invalid scene records',()=>{
    expect(clampInside([-1,5,4],[6,5,3])).toEqual([0.05,4.95,2.95])
    const scene=createDefaultScene(); scene.equipment[0].position_m=[0,1,1]
    expect(()=>validateScene(scene)).toThrow(/strictly inside/)
  })
  it('serializes and restores equipment without renderer state',()=>{
    const original=createDefaultScene(); const restored=parseSceneDocument(serializeScene(original))
    expect(restored).toEqual(original)
    expect(restored).not.toHaveProperty('camera')
    expect(parseSceneDocument('{invalid').room_dimensions_m).toEqual([6,5,3])
  })
  it('requires a finite positive sound speed for a persisted scene',()=>{
    const scene=createDefaultScene();scene.speed_of_sound_m_s=0
    expect(()=>validateScene(scene)).toThrow(/Speed of sound/)
    const legacy={...createDefaultScene()} as Record<string,unknown>;delete legacy.speed_of_sound_m_s
    expect(parseSceneDocument(JSON.stringify(legacy)).speed_of_sound_m_s).toBe(343)
  })
  it('derives finite first-order bounce points from image ray and wall plane',()=>{
    expect(reflectionPointFromImage([-1,1,1],[3,2,1],'x_min',[4,3,2.5])).toEqual([0,1.25,1])
    expect(reflectionPointFromImage([-10,10,1],[3,2,1],'x_min',[4,3,2.5])).toBeNull()
    expect(reflectionPointFromImage([-1,1,1],[3,2,1],'not_a_wall',[4,3,2.5])).toBeNull()
  })
})

describe('experiment geometry provenance gate',()=>{
  const experiment=backendStoredExperiment.experiment_metadata
  const envelope=backendStoredExperiment.result_envelope
  it('accepts the actual stored service envelope and keeps estimate unavailable',()=>{
    const snapshot=parseSyntheticExperiment(experiment,envelope)
    expect(snapshot.experiment_id).toBe(experiment.id)
    expect(snapshot.name).toBe(experiment.name)
    expect(snapshot.status).toBe('completed')
    expect(snapshot.classification).toBe('synthetic_forward_simulation')
    expect(snapshot.geometry_status).toBe('known synthetic ground truth')
    expect(snapshot.room_dimensions_m).toEqual([4,3,2.5])
    expect(snapshot.equipment[0].kind).toBe('speaker')
    expect(snapshot.equipment[0].position_m).toEqual([1,1,1])
    expect(snapshot.equipment[1].kind).toBe('microphone')
    expect(snapshot.equipment[1].position_m).toEqual([3,2,1])
    expect(snapshot.paths.length).toBeGreaterThan(0)
    expect(snapshot.paths.some(path=>path.reflection_order===0)).toBe(true)
    expect(snapshot.paths.some(path=>path.reflection_order===1)).toBe(true)
    expect(snapshot.estimated_geometry_available).toBe(false)
    expect(editableSceneFromExperiment(snapshot).equipment).toHaveLength(2)
  })
  it('refuses unsupported or incomplete results without substituting geometry',()=>{
    expect(()=>parseSyntheticExperiment({...experiment,kind:'unknown'},envelope)).toThrow(/not a supported/)
    expect(()=>parseSyntheticExperiment(experiment,{...envelope,data_classification:'real'})).toThrow(/not a supported/)
    expect(()=>parseSyntheticExperiment(experiment,{...envelope,geometry_status:'estimated'})).toThrow(/not a supported/)
    expect(()=>parseSyntheticExperiment(experiment,{...envelope,geometry_status:'known synthetic ground-truth geometry'})).toThrow(/not a supported/)
    expect(()=>parseSyntheticExperiment(experiment,{...envelope,is_room_reconstruction:true})).toThrow(/not a supported/)
  })
})
