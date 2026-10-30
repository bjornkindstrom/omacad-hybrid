#!/usr/bin/env python3
"""Compare actual source checkouts in isolated processes; no application source is patched."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time


def summary(values):
    import numpy as np
    return {"median_ms":float(np.median(values)),"p95_ms":float(np.percentile(values,95)),"samples":len(values)}


def worker(args):
    root=args.root.resolve();sys.path.insert(0,str(root))
    import numpy as np
    import omacad
    assert Path(omacad.__file__).resolve().parent==root/'omacad'
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QSurfaceFormat
    from PySide6.QtWidgets import QApplication
    from OpenGL import GL
    # Both checkouts use identical private settings, without writing the installed profile.
    from omacad.ui import settings
    state=Path(tempfile.mkdtemp(prefix='omacad-speed-profile-'))
    settings.CONFIG_DIR=state;settings.SETTINGS_FILE=state/'settings.json'
    settings._instance=settings.SettingsManager(state/'settings.json')
    settings._instance.set('theme_mode','fixed');settings._instance.set('theme_name','studio')
    from omacad.ui import theme
    theme.CUSTOM_DIR=state/'themes';theme._ARROW_DIR=state/'arrows'
    fmt=QSurfaceFormat();fmt.setSamples(4);fmt.setDepthBufferSize(24);fmt.setStencilBufferSize(8);fmt.setVersion(3,3);fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CompatibilityProfile);QSurfaceFormat.setDefaultFormat(fmt)
    app=QApplication([]);theme.apply_saved_choice()
    from omacad.model.document import Document
    from omacad.model.features.base import Body
    from omacad.model.kernel import CadKernel
    from omacad.model import faces_hit_tests as picking
    from omacad.ui.viewport import Viewport3D
    from omacad.ui.math3d import ray_from_screen
    result={"root":str(root),"revision":subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip(),"version":omacad.__version__,"python":platform.python_version(),"numpy":np.__version__,"pid":os.getpid(),"scenes":{}}
    try:
        from omacad.viewport_accel import backend_name
        result['backend']=backend_name()
    except ModuleNotFoundError:
        result['backend']='original-numpy'
    for scene in ['bracket_holes','sphere_8192','sphere_131072']:
        print(f'{args.label}: {scene}',flush=True)
        start=time.perf_counter()
        if scene=='bracket_holes':
            solid=CadKernel.create_box(80,50,20)
            for x in [20,60]:solid=solid-CadKernel.create_cylinder(7,40,segments=96).translate((x,25,-10))
        else:solid=CadKernel.create_sphere(50,128 if scene=='sphere_8192' else 512)
        body=Body('benchmark-body',scene,solid);body.update_render_mesh()
        build_ms=(time.perf_counter()-start)*1000
        mesh=body.render_mesh
        digest=hashlib.sha256()
        for array in [mesh.vertices,mesh.normals,mesh.sharp_lines]:digest.update(np.asarray(array).tobytes())
        record={"triangles":len(mesh.vertices)//3,"faces":len(body.faces),"edges":len(body.edges),"geometry_sha256":digest.hexdigest(),"model_and_mesh_build_ms":build_ms}
        rng=np.random.default_rng(3014)
        origins=rng.normal(size=(120,3));origins=origins/np.linalg.norm(origins,axis=1)[:,None]*180+mesh.center
        targets=rng.normal(size=(120,3))*20+mesh.center
        directions=targets-origins;directions/=np.linalg.norm(directions,axis=1)[:,None]
        # Cold means actual first native index build, not a warmed-up wrapper.
        picking._FACE_STACKS.clear()
        if hasattr(mesh,'_native_pick_index'):del mesh._native_pick_index
        t=time.perf_counter_ns();picking.ray_mesh_hit(mesh,origins[0],directions[0]);record['mesh_first_query_ms']=(time.perf_counter_ns()-t)/1e6
        timings=[];hits=[]
        for o,d in zip(origins,directions):
            t=time.perf_counter_ns();hit=picking.ray_mesh_hit(mesh,o,d);timings.append((time.perf_counter_ns()-t)/1e6)
            hits.append(None if hit is None else [round(hit[0],7),int(hit[1])])
        record['mesh_pick']=summary(timings);record['mesh_hits']=hits
        doc=Document();doc.bodies={body.body_id:body}
        vp=Viewport3D(doc);vp.setFixedSize(900,600)
        vp.target=np.asarray(mesh.center,dtype=np.float32);vp.distance=max(150,float(np.linalg.norm(mesh.bounds_max-mesh.bounds_min))*2.0);vp.azimuth=35.;vp.elevation=28.
        vp.show();app.processEvents();assert vp.isValid(),'Invalid OpenGL context'
        vp.makeCurrent()
        renderer=GL.glGetString(GL.GL_RENDERER);vendor=GL.glGetString(GL.GL_VENDOR)
        result['gpu_renderer']=renderer.decode();result['gpu_vendor']=vendor.decode();vp.doneCurrent()
        points=[(float(x),float(y))for x,y in np.c_[rng.uniform(280,620,72),rng.uniform(135,465,72)]]
        for edge in body.edges[:12]:
            poly=np.asarray(edge.polyline()).reshape(-1,3)
            if len(poly):
                p=vp.world_to_screen(poly[len(poly)//2])
                if p is not None:points.append((float(p[0])+1.0,float(p[1])+1.0))
        # Warm up topology/surface classification, edge projections, shader and GPU caches.
        for x,y in points[:8]:vp._update_edge_hover(x,y)
        for _ in range(4):vp.grabFramebuffer()
        samples=[];body_hits=[]
        for x,y in points:
            t=time.perf_counter_ns();hit=vp.pick_body(x,y);samples.append((time.perf_counter_ns()-t)/1e6);body_hits.append(hit)
        record['body_pick']=summary(samples);record['body_hits']=body_hits
        samples=[];hover_hits=[]
        for x,y in points:
            t=time.perf_counter_ns();vp._update_edge_hover(x,y);samples.append((time.perf_counter_ns()-t)/1e6)
            face=vp.hover_face;edge=vp.hover_edge;surface=vp.hover_surface
            hover_hits.append([None if face is None else face.index,None if edge is None else edge.kind,None if surface is None else surface[0]])
        record['hover_cpu']=summary(samples);record['hover_hits']=hover_hits
        # Full hover calculation PLUS a freshly rendered/read-back Qt OpenGL frame.
        samples=[]
        for x,y in points[:30]:
            t=time.perf_counter_ns();vp._update_edge_hover(x,y);vp.update();image=vp.grabFramebuffer();samples.append((time.perf_counter_ns()-t)/1e6)
            assert not image.isNull()
        record['hover_plus_frame_readback']=summary(samples)
        vp.hover_edge=vp.hover_face=vp.hover_surface=None
        samples=[]
        for i in range(30):
            t=time.perf_counter_ns();vp.azimuth=35.0+i*3.;vp.update();image=vp.grabFramebuffer();samples.append((time.perf_counter_ns()-t)/1e6)
        record['orbit_frame_readback']=summary(samples)
        record['viewport_size']=[vp.width(),vp.height(),vp.devicePixelRatioF()]
        result['scenes'][scene]=record
        vp.close();vp.deleteLater();app.sendPostedEvents(None,QEvent.Type.DeferredDelete);app.processEvents()
    args.output.write_text(json.dumps(result,indent=2)+'\n')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--worker',action='store_true');parser.add_argument('--root',type=Path);parser.add_argument('--label');parser.add_argument('--output',type=Path,required=True);parser.add_argument('--rounds',type=int,default=3)
    args=parser.parse_args()
    if args.worker:return worker(args)
    args.output.mkdir(parents=True,exist_ok=True)
    repositories={'omacad':Path('/home/kindstrom/Work/omacad'),'hybrid':Path('/home/kindstrom/Work/omacad-hybrid')}
    records={name:[]for name in repositories}
    script=Path(__file__).resolve()
    for round_index in range(args.rounds):
        order=['omacad','hybrid']if round_index%2==0 else ['hybrid','omacad']
        for label in order:
            root=repositories[label];file=args.output/f'{label}-{round_index+1}.json';log=args.output/f'{label}-{round_index+1}.log'
            env={**os.environ,'OMACAD_VIEWPORT_BACKEND':'rust'if label=='hybrid'else'python','OMACAD_HYBRID_STATE_DIR':str(args.output/'profile'),'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'}
            print(f'Round {round_index+1}/{args.rounds}: {label}',flush=True)
            with log.open('w')as stream:
                subprocess.run([str(root/'.venv/bin/python'),str(script),'--worker','--root',str(root),'--label',label,'--output',str(file)],cwd=root,env=env,stdout=stream,stderr=subprocess.STDOUT,check=True)
            records[label].append(json.loads(file.read_text()))
    # Every cross-process run must use identical geometry AND produce identical picks.
    scenes=records['omacad'][0]['scenes']
    for scene in scenes:
        baseline=records['omacad'][0]['scenes'][scene]
        for runs in records.values():
            for run in runs:
                current=run['scenes'][scene]
                for key in ['geometry_sha256','mesh_hits','body_hits','hover_hits','viewport_size']:
                    assert current[key]==baseline[key],(scene,key)
    import numpy as np
    report={'date':time.strftime('%Y-%m-%d %H:%M:%S %z'),'method':'Actual independent checkouts, one process at a time, alternating order. Fixed geometry, rays, viewport, camera, settings and one BLAS thread. Frame times include GPU framebuffer readback, not display FPS.','rounds':args.rounds,'parity':True,'roots':{name:{k:v for k,v in runs[0].items()if k!='scenes'}for name,runs in records.items()},'scenes':{}}
    for scene in scenes:
        data={'triangles':scenes[scene]['triangles'],'faces':scenes[scene]['faces'],'edges':scenes[scene]['edges'],'metrics':{}}
        for metric in ['mesh_pick','body_pick','hover_cpu','hover_plus_frame_readback','orbit_frame_readback']:
            medians={name:float(np.median([r['scenes'][scene][metric]['median_ms']for r in runs]))for name,runs in records.items()}
            data['metrics'][metric]={**{name+'_ms':value for name,value in medians.items()},'speedup':medians['omacad']/medians['hybrid'],'run_medians':{name:[r['scenes'][scene][metric]['median_ms']for r in runs]for name,runs in records.items()}}
        data['cold_mesh_query_ms']={name:float(np.median([r['scenes'][scene]['mesh_first_query_ms']for r in runs]))for name,runs in records.items()}
        report['scenes'][scene]=data
    (args.output/'comparison.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)

if __name__=='__main__':main()
