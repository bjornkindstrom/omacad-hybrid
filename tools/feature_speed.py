#!/usr/bin/env python3
"""Full-quality feature timing/profiling against an actual selected checkout."""
import argparse,cProfile,hashlib,json,os,pstats,subprocess,sys,tempfile,time
from pathlib import Path

p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--case',choices=['box_fillet','rim_fillet','jar'],required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--segments',type=int,choices=[360,720],default=720);p.add_argument('--profile',action='store_true');p.add_argument('--build-only',action='store_true');a=p.parse_args()
a.output.parent.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(a.root.resolve()))
import numpy as np
from omacad.ui import settings
state=Path(tempfile.mkdtemp(prefix='omacad-hq-profile-'));settings.CONFIG_DIR=state;settings.SETTINGS_FILE=state/'settings.json';settings._instance=settings.SettingsManager(state/'settings.json')
settings._instance.set('theme_mode','fixed');settings._instance.set('theme_name','studio');settings._instance.set('curve_segments',a.segments)
from omacad.ui import theme
theme.CUSTOM_DIR=state/'themes';theme._ARROW_DIR=state/'arrows'
from omacad.model import quality
quality.set_circle_segments(a.segments);quality.set_interactive_mode(False)
from omacad.model.document import Document
from omacad.model.features.base import Body
from omacad.model.jar import JarSpec
import omacad
stages=[]
original_update=Body.update_render_mesh

def instrumented_update(self):
    start=time.perf_counter()
    try:return original_update(self)
    finally:
        elapsed=time.perf_counter()-start;stages.append({'body':self.name,'seconds':elapsed})
        if elapsed>0.5:print(f'Render/topology: {self.name}: {elapsed:.2f}s',flush=True)
Body.update_render_mesh=instrumented_update

result={'root':str(a.root),'revision':subprocess.check_output(['git','-C',str(a.root),'rev-parse','HEAD'],text=True).strip(),'version':omacad.__version__,'case':a.case,'segments':a.segments,'interactive_simplification':False,'profiled':a.profile}
prof=cProfile.Profile()if a.profile else None
if prof:prof.enable()
doc=Document()
start=time.perf_counter()
if a.case=='jar':
    spec=JarSpec();result['spec']=spec.to_dict();print(f'Building full Jar with Lid at {a.segments} segments',flush=True)
    ids=doc.add_jar(spec)
else:
    if a.case=='box_fillet':
        body=doc.add_box(60,40,20)
        top=body.manifold.bounding_box()[5]
        selected=[e.ref()for e in body.edges if e.kind=='line'and abs(e.p0[2]-top)<1e-6 and abs(e.p1[2]-top)<1e-6]
        assert len(selected)==4
    else:
        body=doc.add_cylinder(20,40)
        selected=[e.ref()for e in body.edges if e.kind=='circle'and abs(e.center[2]-40)<1e-6]
        assert selected
    result['base_build_seconds']=time.perf_counter()-start
    start=time.perf_counter();print(f'Applying {a.case} R=3mm at {a.segments} segments',flush=True)
    feature=doc.add_fillet(selected,3.0)
    assert feature.skipped==0
result['operation_seconds']=time.perf_counter()-start
if prof:
    prof.disable();prof.dump_stats(str(a.output.with_suffix('.pstats')))
    with a.output.with_suffix('.profile.txt').open('w')as out:pstats.Stats(prof,stream=out).strip_dirs().sort_stats('cumtime').print_stats(35)
result['render_mesh_updates']=stages
result['render_mesh_update_seconds']=sum(s['seconds']for s in stages)
result['quality_after_build']=quality.circle_segments();assert result['quality_after_build']==a.segments and not quality.is_interactive_mode()
result['bodies']=[]
for body in doc.bodies.values():
    assert not body.manifold.is_empty()
    h=hashlib.sha256()
    for array in [body.render_mesh.vertices,body.render_mesh.normals,body.render_mesh.sharp_lines]:h.update(np.asarray(array).tobytes())
    result['bodies'].append({'id':body.body_id,'name':body.name,'volume':body.manifold.volume(),'triangles':len(body.render_mesh.vertices)//3,'faces':len(body.faces),'edges':len(body.edges),'mesh_sha256':h.hexdigest()})
result['triangles']=sum(x['triangles']for x in result['bodies'])
a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:result[k]for k in ['case','operation_seconds','triangles','render_mesh_update_seconds']}),flush=True)
if a.build_only:raise SystemExit(0)
# Actual high-resolution Qt/OpenGL viewport. The source geometry is never simplified.
from PySide6.QtCore import QEvent
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtWidgets import QApplication
from OpenGL import GL
from omacad.ui.viewport import Viewport3D
fmt=QSurfaceFormat();fmt.setSamples(8);fmt.setDepthBufferSize(24);fmt.setStencilBufferSize(8);fmt.setVersion(3,3);fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CompatibilityProfile);QSurfaceFormat.setDefaultFormat(fmt)
app=QApplication([]);theme.apply_saved_choice()
vp=Viewport3D(doc)
dpr=app.primaryScreen().devicePixelRatio();vp.setFixedSize(round(2560/dpr),round(1440/dpr))
lo=np.min([b.render_mesh.bounds_min for b in doc.bodies.values()],axis=0);hi=np.max([b.render_mesh.bounds_max for b in doc.bodies.values()],axis=0)
vp.target=(lo+hi)*0.5;vp.distance=max(120,float(np.linalg.norm(hi-lo))*2.1);vp.azimuth=30.;vp.elevation=28.
vp.show();app.processEvents();assert vp.isValid();vp.makeCurrent()
GL.glBindFramebuffer(GL.GL_FRAMEBUFFER,vp.defaultFramebufferObject())
result['requested_msaa']=8;result['active_msaa']=int(GL.glGetIntegerv(GL.GL_SAMPLES));result['gpu']=GL.glGetString(GL.GL_RENDERER).decode();vp.doneCurrent()
image=vp.grabFramebuffer();result['framebuffer_pixels']=[image.width(),image.height()];assert result['framebuffer_pixels']==[2560,1440],result['framebuffer_pixels']
assert result['active_msaa']==8,result['active_msaa']
result['format_samples']=vp.format().samples()
rng=np.random.default_rng(720)
points=[(float(x),float(y))for x,y in np.c_[rng.uniform(.25,.75,50)*vp.width(),rng.uniform(.2,.8,50)*vp.height()]]
for body in doc.bodies.values():
    for edge in body.edges[:12]:
        poly=np.asarray(edge.polyline()).reshape(-1,3)
        if len(poly):
            point=vp.world_to_screen(poly[len(poly)//2])
            if point is not None:points.append((float(point[0])+1.,float(point[1])+1.))
for x,y in points[:6]:vp._update_edge_hover(x,y)
for _ in range(3):vp.grabFramebuffer()
def metric(fn,values):
    samples=[];hits=[]
    for value in values:
        start=time.perf_counter_ns();hit=fn(value);samples.append((time.perf_counter_ns()-start)/1e6);hits.append(hit)
    return {'median_ms':float(np.median(samples)),'p95_ms':float(np.percentile(samples,95)),'samples':len(samples)},hits
result['body_pick'],result['body_hits']=metric(lambda xy:vp.pick_body(*xy),points)
def hover(xy):
    vp._update_edge_hover(*xy)
    return [None if vp.hover_face is None else [vp.hover_face.body_id,vp.hover_face.index],None if vp.hover_edge is None else vp.hover_edge.kind,None if vp.hover_surface is None else vp.hover_surface[0]]
result['hover_cpu'],result['hover_hits']=metric(hover,points)
def hover_frame(xy):hover(xy);vp.update();vp.grabFramebuffer()
result['hover_plus_frame'],_=metric(hover_frame,points[:20])
vp.hover_edge=vp.hover_face=vp.hover_surface=None

def orbit(i):vp.azimuth=30.+i*4.;vp.update();vp.grabFramebuffer()
result['orbit_frame'],_=metric(orbit,list(range(20)))
vp.azimuth=30.;vp.update();vp.grabFramebuffer().save(str(a.output.with_suffix('.png')))
a.output.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:result[k]for k in ['case','active_msaa','format_samples','framebuffer_pixels','hover_cpu','hover_plus_frame','orbit_frame']}),flush=True)
vp.close();vp.deleteLater();app.sendPostedEvents(None,QEvent.Type.DeferredDelete);app.processEvents()
