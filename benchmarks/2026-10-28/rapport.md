# Speedtest: Omacad mot Omacad Hybrid

Utfört: 2026-10-28 21:18:40 +0100. Tre oberoende omgångar per version, totalt sex processer.

## Slutsats

Hybrid förbättrar framför allt plockning och hovring i täta modeller. GPU-ritningen använder samma Python/OpenGL-kod och ger ungefär samma bildtid. På den lilla modellen dominerar övrigt arbete och bildavläsning.

## Uppmätta tider

Tiderna är medianen av tre körningsmedianer. Lägre är bättre.

| Modell | Arbete | Omacad, ms | Hybrid, ms | Omacad/Hybrid |
|---|---|---:|---:|---:|
| Platta med hål | Triangelplockning | 0,126 | 0,006 | 20.77× |
| Platta med hål | Kroppsplockning i viewport | 0,077 | 0,074 | 1.04× |
| Platta med hål | Hela hovringsberäkningen (CPU) | 0,367 | 0,333 | 1.10× |
| Platta med hål | Hovring + ny bild + bildavläsning | 8,518 | 8,747 | 0.97× |
| Platta med hål | Rotation + ny bild + bildavläsning | 8,357 | 8,092 | 1.03× |
| Sfär · 8 192 trianglar | Triangelplockning | 0,570 | 0,005 | 107.46× |
| Sfär · 8 192 trianglar | Kroppsplockning i viewport | 0,671 | 0,071 | 9.47× |
| Sfär · 8 192 trianglar | Hela hovringsberäkningen (CPU) | 0,800 | 0,195 | 4.11× |
| Sfär · 8 192 trianglar | Hovring + ny bild + bildavläsning | 8,583 | 8,539 | 1.01× |
| Sfär · 8 192 trianglar | Rotation + ny bild + bildavläsning | 8,054 | 7,685 | 1.05× |
| Sfär · 131 072 trianglar | Triangelplockning | 11,613 | 0,006 | 1868.20× |
| Sfär · 131 072 trianglar | Kroppsplockning i viewport | 11,367 | 0,071 | 159.63× |
| Sfär · 131 072 trianglar | Hela hovringsberäkningen (CPU) | 11,461 | 0,250 | 45.80× |
| Sfär · 131 072 trianglar | Hovring + ny bild + bildavläsning | 20,549 | 8,937 | 2.30× |
| Sfär · 131 072 trianglar | Rotation + ny bild + bildavläsning | 8,410 | 8,594 | 0.98× |

## Första plockningen efter ny geometri

Rust bygger ett BVH-index. Följande kalla tider inkluderar detta bygge; de snabba upprepade tiderna ovan gör det inte.

| Modell | Omacad, ms | Hybrid, ms |
|---|---:|---:|
| Platta med hål | 0,187 | 0,178 |
| Sfär · 8 192 trianglar | 0,739 | 1,935 |
| Sfär · 131 072 trianglar | 11,426 | 39,673 |

## Metod och kontroll

- Originalrepot `omacad` och det separata `omacad-hybrid` kördes med sina egna Pythonmiljöer; detta är inte enbart en omkopplare i Hybrid.
- Körordning: original/hybrid, hybrid/original, original/hybrid. Inga mätprocesser kördes samtidigt.
- Samma Manifold-modeller, kameror, muspositioner, 900×600 logiska viewportpixlar, tema, inställningar och en BLAS-tråd.
- 120 stråltester per modell och körning; minst 72 muspositioner för hovring, plus kantnära punkter där modellen har kanter.
- Varmkörning av topologi, ytplockning och GPU-cacher före de upprepade mätningarna.
- Alla sex körningars geometriska SHA-256, triangelträffar, kroppsval, hovrade ytor/kanter och viewportstorlek stämmer överens.
- Bildmätningarna inkluderar `QOpenGLWidget.grabFramebuffer()`, alltså ritning, GPU-synkronisering och bildavläsning. De är **inte uppmätt skärm-FPS**.
- Hovrings-CPU omfattar den befintliga `_update_edge_hover`-kedjan, men exkluderar schemalagd Qt-ritning. Kombinationsmätningen inkluderar både hovring och den nya bilden.
- Den första kalla strålfrågan mäts separat. Första topologianalys och modellbygge ingår inte i varma hovringstider.
- Bakgrundsappar fortsatte köra. Små skillnader nära 1× bör tolkas som ungefär lika snabbt.

## Miljö och versioner

- CPU: AMD Ryzen 7 5800H, 16 logiska processorer.
- omacad: `fdf4331b00d014521de916ce65bb2863d06ee444` · Python 3.14.8 · NumPy 2.5.4 · backend `original-numpy`.
  GPU-renderer: AMD Radeon Graphics (radeonsi, renoir, ACO, DRM 3.64, 7.2.8-9-omarchy).
- hybrid: `9cd3697f98a2b2d7ac3bbece69822a3a01427139` · Python 3.14.8 · NumPy 2.5.4 · backend `rust`.
  GPU-renderer: AMD Radeon Graphics (radeonsi, renoir, ACO, DRM 3.64, 7.2.8-9-omarchy).

## Filer

- `comparison.json`: sammanställning och spridning mellan körningar.
- `omacad-1.json` … `hybrid-3.json`: rådata, p95 och varje kontrollerad träff.
- `speed-test.png`: diagram.

## Upprepa

```bash
.venv/bin/python tools/compare_omacad.py --output benchmarks/ny-korning --rounds 3
.venv/bin/python tools/report_speed_test.py benchmarks/ny-korning
```
