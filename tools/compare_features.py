#!/usr/bin/env python3
"""Bounded real feature operations, then matched full-resolution viewport measurements."""
import argparse,json,os,subprocess,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--rounds',type=int,default=1);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
# Wait for the diagnostic profile launched by this task; no overlapping timed workloads.
while Path('/proc/1373691/cmdline').exists() and b'feature_speed.py'in Path('/proc/1373691/cmdline').read_bytes():time.sleep(1)
roots={'omacad':Path('/home/kindstrom/Work/omacad'),'hybrid':Path('/home/kindstrom/Work/omacad-hybrid')}
records=[]
for run in range(a.rounds):
 for case,segments in [('box_fillet',720),('rim_fillet',720),('jar',360)]:
  for label in (['omacad','hybrid']if run%2==0 else['hybrid','omacad']):
   root=roots[label];out=a.output/f'{label}-{case}-{segments}-{run+1}.json';log=out.with_suffix('.log')
   print(f'{label}: {case}, {segments} segments, round {run+1}',flush=True)
   env={**os.environ,'OMACAD_VIEWPORT_BACKEND':'rust'if label=='hybrid'else'python','OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','OMACAD_HYBRID_STATE_DIR':str(a.output/'profile')}
   cmd=[str(root/'.venv/bin/python'),'/home/kindstrom/Work/omacad-hybrid/tools/feature_speed.py','--root',str(root),'--case',case,'--segments',str(segments),'--output',str(out)]
   started=time.perf_counter()
   try:
    with log.open('w')as stream:subprocess.run(cmd,cwd=root,env=env,stdout=stream,stderr=subprocess.STDOUT,check=True,timeout=240)
    result=json.loads(out.read_text());result['status']='completed'
   except subprocess.TimeoutExpired:
    result={'case':case,'segments':segments,'status':'timeout','limit_seconds':240,'elapsed_seconds':time.perf_counter()-started}
   except subprocess.CalledProcessError as error:
    result={'case':case,'segments':segments,'status':'failed','returncode':error.returncode}
   result['label']=label;result['round']=run+1;records.append(result)
   (a.output/'feature-results.json').write_text(json.dumps(records,indent=2)+'\n')
print('Feature comparison complete',flush=True)
