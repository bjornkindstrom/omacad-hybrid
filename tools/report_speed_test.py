#!/usr/bin/env python3
"""Render the completed comparison into a Swedish report and standalone chart."""
import json
from pathlib import Path
import sys

folder=Path(sys.argv[1]).resolve()
report=json.loads((folder/'comparison.json').read_text())
labels={'bracket_holes':'Platta med hål','sphere_8192':'Sfär · 8 192 trianglar','sphere_131072':'Sfär · 131 072 trianglar'}
metrics={'mesh_pick':'Triangelplockning','body_pick':'Kroppsplockning i viewport','hover_cpu':'Hela hovringsberäkningen (CPU)','hover_plus_frame_readback':'Hovring + ny bild + bildavläsning','orbit_frame_readback':'Rotation + ny bild + bildavläsning'}
def number(value):return f'{value:.3f}'.replace('.',',')
text=['# Speedtest: Omacad mot Omacad Hybrid','',f"Utfört: {report['date']}. Tre oberoende omgångar per version, totalt sex processer.",'','## Slutsats','', 'Hybrid förbättrar framför allt plockning och hovring i täta modeller. GPU-ritningen använder samma Python/OpenGL-kod och ger ungefär samma bildtid. På den lilla modellen dominerar övrigt arbete och bildavläsning.','', '## Uppmätta tider','', 'Tiderna är medianen av tre körningsmedianer. Lägre är bättre.','', '| Modell | Arbete | Omacad, ms | Hybrid, ms | Omacad/Hybrid |','|---|---|---:|---:|---:|']
for scene,data in report['scenes'].items():
    for metric in metrics:
        m=data['metrics'][metric]
        text.append(f"| {labels[scene]} | {metrics[metric]} | {number(m['omacad_ms'])} | {number(m['hybrid_ms'])} | {m['speedup']:.2f}× |")
text+=['','## Första plockningen efter ny geometri','','Rust bygger ett BVH-index. Följande kalla tider inkluderar detta bygge; de snabba upprepade tiderna ovan gör det inte.','','| Modell | Omacad, ms | Hybrid, ms |','|---|---:|---:|']
for scene,data in report['scenes'].items():text.append(f"| {labels[scene]} | {number(data['cold_mesh_query_ms']['omacad'])} | {number(data['cold_mesh_query_ms']['hybrid'])} |")
text+=['','## Metod och kontroll','','- Originalrepot `omacad` och det separata `omacad-hybrid` kördes med sina egna Pythonmiljöer; detta är inte enbart en omkopplare i Hybrid.','- Körordning: original/hybrid, hybrid/original, original/hybrid. Inga mätprocesser kördes samtidigt.','- Samma Manifold-modeller, kameror, muspositioner, 900×600 logiska viewportpixlar, tema, inställningar och en BLAS-tråd.','- 120 stråltester per modell och körning; minst 72 muspositioner för hovring, plus kantnära punkter där modellen har kanter.','- Varmkörning av topologi, ytplockning och GPU-cacher före de upprepade mätningarna.','- Alla sex körningars geometriska SHA-256, triangelträffar, kroppsval, hovrade ytor/kanter och viewportstorlek stämmer överens.','- Bildmätningarna inkluderar `QOpenGLWidget.grabFramebuffer()`, alltså ritning, GPU-synkronisering och bildavläsning. De är **inte uppmätt skärm-FPS**.','- Hovrings-CPU omfattar den befintliga `_update_edge_hover`-kedjan, men exkluderar schemalagd Qt-ritning. Kombinationsmätningen inkluderar både hovring och den nya bilden.','- Den första kalla strålfrågan mäts separat. Första topologianalys och modellbygge ingår inte i varma hovringstider.','- Bakgrundsappar fortsatte köra. Små skillnader nära 1× bör tolkas som ungefär lika snabbt.','','## Miljö och versioner','','- CPU: AMD Ryzen 7 5800H, 16 logiska processorer.']
for name,info in report['roots'].items():text += [f"- {name}: `{info['revision']}` · Python {info['python']} · NumPy {info['numpy']} · backend `{info['backend']}`.",f"  GPU-renderer: {info['gpu_renderer']}."]
text+=['','## Filer','','- `comparison.json`: sammanställning och spridning mellan körningar.','- `omacad-1.json` … `hybrid-3.json`: rådata, p95 och varje kontrollerad träff.','- `speed-test.png`: diagram.','','## Upprepa','','```bash','.venv/bin/python tools/compare_omacad.py --output benchmarks/ny-korning --rounds 3','.venv/bin/python tools/report_speed_test.py benchmarks/ny-korning','```','']
(folder/'rapport.md').write_text('\n'.join(text))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
fig,axes=plt.subplots(1,3,figsize=(14,4.6))
scenes=list(report['scenes']);x=np.arange(len(scenes));width=.34
for ax,metric in zip(axes,['hover_cpu','hover_plus_frame_readback','orbit_frame_readback']):
    for index,(name,color,title) in enumerate([('omacad','#3b6da6','Omacad'),('hybrid','#d67b28','Hybrid (Rust)')]):
        values=[report['scenes'][s]['metrics'][metric][name+'_ms']for s in scenes]
        positions=x+(index-.5)*width
        bars=ax.bar(positions,values,width,color=color,label=title)
        for position,scene,value in zip(positions,scenes,values):
            runs=report['scenes'][scene]['metrics'][metric]['run_medians'][name]
            ax.scatter([position]*len(runs),runs,color='black',s=9,alpha=.5,zorder=4)
            ax.annotate(f'{value:.2f}',(position,value),ha='center',va='bottom',xytext=(0,4),textcoords='offset points',fontsize=8)
    ax.set_xticks(x,['Platta\n788 tri','Sfär\n8 192 tri','Sfär\n131 072 tri']);ax.set_ylabel('Millisekunder (lägre är bättre)');ax.set_title({'hover_cpu':'Hovring: CPU','hover_plus_frame_readback':'Hovring + bildavläsning','orbit_frame_readback':'Rotation + bildavläsning'}[metric]);ax.spines[['top','right']].set_visible(False);ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True);ax.margins(y=.18)
axes[0].set_yscale('log');axes[0].legend(frameon=False,fontsize=8,loc='upper left')
fig.suptitle('Omacad vs Omacad Hybrid · faktiska Qt-viewportar',fontsize=14)
fig.text(.5,.015,'Tre separata körningar per version · prickar = körningsmedianer · bildavläsning är inte skärm-FPS',ha='center',fontsize=9)
fig.tight_layout(rect=(0,.04,1,.94));fig.savefig(folder/'speed-test.png',dpi=160);plt.close(fig)
print(folder/'rapport.md');print(folder/'speed-test.png')
