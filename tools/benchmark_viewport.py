#!/usr/bin/env python3
"""A/B benchmark through the SAME Omacad picking entrypoints, not a Rust-only microbench."""
import argparse
import json
import platform
from pathlib import Path
import sys
import time
from types import SimpleNamespace

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from omacad import viewport_accel as accel
from omacad.model import faces_hit_tests as picking
from omacad.model.kernel import CadKernel


def timed(fn):
    start=time.perf_counter_ns()
    result=fn()
    return result,(time.perf_counter_ns()-start)/1e6


def run(mesh,rays):
    triangles=np.asarray(mesh.vertices,dtype=np.float64).reshape(-1,3,3)
    # A dense triangle mesh and a many-face CAD boundary are distinct workloads.
    groups=min(1000,len(triangles))
    faces=[SimpleNamespace(tris=t)for t in np.array_split(triangles,groups)]
    report={"triangles":len(triangles),"face_groups":groups,"rays":len(rays),"backends":{}}
    native=accel._NATIVE
    results={}
    try:
        for backend in ["python","rust"]:
            accel._NATIVE=native if backend=="rust" else None
            picking._FACE_STACKS.clear()
            if hasattr(mesh,"_native_pick_index"):del mesh._native_pick_index
            timings={};results[backend]={}
            for operation,source,fn in [("mesh",mesh,picking.ray_mesh_hit),("faces",faces,picking.ray_hit_faces)]:
                _,cold=timed(lambda:fn(source,*rays[0]))
                values=[];samples=[]
                for origin,direction in rays:
                    value,elapsed=timed(lambda:fn(source,origin,direction));values.append(value);samples.append(elapsed)
                timings[operation]={"cold_first_ms":cold,"median_ms":float(np.median(samples)),"p95_ms":float(np.percentile(samples,95))}
                results[backend][operation]=values
            report["backends"][backend]=timings
    finally:
        accel._NATIVE=native
        picking._FACE_STACKS.clear()
    # Verify every measured ray, including the original triangle ID, before reporting speedups.
    for a,b in zip(results["python"]["mesh"],results["rust"]["mesh"]):
        assert (a is None)==(b is None)
        if a is not None:assert a[1]==b[1] and np.isclose(a[0],b[0],rtol=1e-10,atol=1e-8),(a,b)
    for a,b in zip(results["python"]["faces"],results["rust"]["faces"]):np.testing.assert_allclose(a,b,rtol=1e-10,atol=1e-8)
    report["matches_numpy"]=True
    report["warm_speedup"]={name:report["backends"]["python"][name]["median_ms"]/report["backends"]["rust"][name]["median_ms"] for name in ["mesh","faces"]}
    return report


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--rays",type=int,default=120);parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    if args.rays<1:parser.error("--rays must be positive")
    if accel.backend_name()!="rust":parser.error("Rust module is required; run ./tools/build_native.sh first")
    report={"python":platform.python_version(),"platform":platform.platform(),"numpy":np.__version__,"description":"CPU picking only, warm query medians; includes Python-to-Rust calls. No FPS or GPU claim.","scenes":{}}
    rng=np.random.default_rng(3014)
    for name,segments in [("sphere_medium",128),("sphere_dense",512)]:
        mesh=CadKernel.extract_render_mesh(CadKernel.create_sphere(50,segments))
        # Mostly hits, some silhouette misses; fixed seed and identical rays for each backend.
        origins=rng.normal(size=(args.rays,3));origins=origins/np.linalg.norm(origins,axis=1)[:,None]*150
        targets=rng.normal(size=(args.rays,3))*25
        directions=targets-origins;directions/=np.linalg.norm(directions,axis=1)[:,None]
        report["scenes"][name]=run(mesh,list(zip(origins,directions)))
    text=json.dumps(report,indent=2)
    if args.output:args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(text+"\n")
    print(text)

if __name__=="__main__":main()
