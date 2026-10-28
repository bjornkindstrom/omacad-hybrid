# Omacad – färdplan

Genomfört 0.9.9.80.69: Offset av öppna och slutna splines, med förhandsvisning och ångra.

Genomfört 0.9.9.80.64: infoga Canvas på plana kroppsytor via högerklick eller planlistan.

Genomfört 0.9.9.80.63: linjärt mönster av ihåliga kroppar ger kompletta kopior efter OK.

Genomfört 0.9.9.80.62: ihåligt loft och redigerbar lista med flera profiler.

Genomfört 0.9.9.80.45: fillet vid lutande ribba, hela skulderkanter, emboss bakom fillet, parallella tester (xdist).
Genomfört 0.9.9.80.44: #91–#99 läsbara värderutor, linjer mot cirkel ger yta, mått i browsern markeras, Construction-meny, 45°/90°-fäste, dolda kroppar orörda.
Genomfört 0.9.9.80.43: #89 läsbar palett/inspektör, #90 grå färdiga skisser.
Genomfört 0.9.9.80.42: bara Studio, Graphite, Atelier och Följ Omarchy i temavalet.
Genomfört 0.9.9.80.41: egen ikon per rektangeltyp.
Genomfört 0.9.9.80.40: Graphite och Atelier. 0.9.9.80.39: penna för värden i browsern.
Genomfört 0.9.9.80.38: browsern tar bara den höjd raderna behöver.
Genomfört 0.9.9.80.37: Studio-ikoner för alla funktioner, menyer, trädrader och historiksteg.
Genomfört 0.9.9.80.36: Studio-tema och Studio-ikoner (förslag 1 i design/appearance-proposals), valbara i inställningarna.
Genomfört 0.9.9.80.35: omdesignade inställningar med sidomeny och tydliga sektionskort.

Genomfört 0.9.9.80.34: rutnätet döljs bakom kroppen även underifrån (#87); dubbla kantval ger inga uppdelade fasytor, och plana fasremsor har kompletta ändsömmar.

Genomfört 0.9.9.80.33: fasning av rundade konturer utan falska kantlinjer; dubbel precision genom ytanalys och fasverktyg.

Genomfört 0.9.0: cirkulära featuregrupper för t.ex. Japandi-ribbor med fillet; val av features i tidslinjen samt cirkel-/cylinderyta som rotationsaxel.

Genomfört 2026-10-17 (0.8.0): Rotate i skiss med valbar pivot (figurens areacentrum, markeringens mitt, kroppsytans centrum, origo eller egen punkt), förhandsvisning och ångra/gör om.

Genomfört 2026-10-17: direkt storleksändring av Box/Cylinder/Sphere via måtthandtag i förhandsvisningen, med ångra och avbryt. Alla numeriska fält i dockade verktyg har sliders med fortsatt text-/formelinmatning. Box/Cylinder har parametrisk taper angle, även med shell. Shelled Box/Cylinder finns som egna menyval med sparad standardtjocklek för väggar och botten.

Nuvarande version: **0.8.0** (global ångra, testsvit, offset av bågar, rapportknappen, rektangelvarianter, automatisk omstart, jämnare vy ovanifrån, fotfillet som vilar på kroppen, tidslinjeklick som visar stegets ändring och kamerainställningar (synfält + ortografisk) är klara; resten av planen kvarstår). Milstolparna efter 0.6.x är omnumrerade (0.7 och uppåt) eftersom sidospåren tog 0.6.2–0.6.10. Den här planen skrevs 2026-10-11. `ROADMAP.md` är historiken (vad som är gjort), den här filen är vad vi bygger härnäst och varför. Versionslogg: `CHANGELOG.md`.

## Principer

1. **Smartast, inte störst.** Vi bygger inte det största CAD-programmet utan det smartaste och snabbaste. Varje släpp har (a) några Fusion 360-grunder som saknas, där Fusions beteende efterliknas så nära det går, och (b) minst en **smart genväg som Fusion inte har**. Redan byggt på den linjen: pattern som kopierar *vad stegen gjorde* (hål + fasningar till alla hörn), Fill the face, Auto-operation i Extrude, ytans kanter som skisslinjer, formler i alla fält, kanter som hittas igen efter ändrad historik.
2. **Inget får gå sönder, och vi kan alltid backa.** Arbete får aldrig försvinna. Allt ska vara ångringsbart, programmet sparar automatiskt en historik vid sidan av din fil, en trasig fil laddas så långt det går i stället för att krascha, och varje rättad bugg blir ett regressionstest som körs för alltid.
3. **AI är en del av arbetsflödet.** När något ser fel ut trycker man på en knapp: programmet skickar en bild av felet tillsammans med dokumentet och loggen till AI:n, som felsöker och rättar. Så bygger vi appen vidare.
4. **Efterlikna Fusion först.** Beteendet undersöks i Fusions hjälpsidor *före* varje funktion byggs.

**Uttryckliga icke-mål** (de gör oss till ett jätteprogram): assemblies/joints, CAM, simulering, rendering/animering, skulptering, molnsamarbete.

## Milstolpar

| Version | Tema | Innehåll |
|---|---|---|
| **0.6** ✔ | Trygghet | **Global ångra/gör om** för allt (se Del A), `delete_body` som riktigt steg, **pytest-svit** i `tests/` (de scriptade volymtesterna blir riktiga tester: fillet/chamfer med exakta volymer, shell, revolve, offset/trim/mirror, ytkanter, ångra/gör om, spara/ladda-rundtur) och ett CI-jobb som kör testerna före EXE-bygget |
| **0.6.1** ✔ | Rapportknappen + agentminne | **"Report problem" (F9)** skickar skärmbilder, dokument och logg till Omarchys standardagent (`omarchy agent prompt`), `omacad.md`/`AGENTS.md`/`CLAUDE.md` som minne för agenterna, offset behåller bågar och radier |
| **0.6.2–0.6.10** ✔ | Sidospår | Rounded Rect och Center Rounded Rect, rektangelknapp med rullgardin och valbar standard, **automatisk omstart** när en ny version committats (sparar och återställer dokument, öppen skiss och kamera), skisspaletten i inspektören, ytskisser med origo i ytans mitt, vyn ovanifrån rullar inte längre 90°, fotfillet krymper så den vilar på kroppen (0.6.7, bara slingor), tidslinjeklick färgar vad steget lade till/tog bort (0.6.8), **kamerainställningar**: synfält 10–60° (standard 30°) och ortografisk vy (0.6.9), värdet på extrudepilen när man drar och fler högerklicksmenyer i 3D och skiss (0.6.10) |
| **0.7** | Säkerhetsnät + AI-återkoppling | **Autosave-historik**, krasch-återställning, versionshistorik med miniatyrer, säker laddning, **"Starta om med ny version"** (klart i 0.6.3: sparar allt och fortsätter där du slutade; kvar är bara en knapp för att välja själv), **"Det blev fel"-knappen** (se Del C) |
| **0.8** | Lean, clean, unbreakable | Kodhälsa (se Del D): dela upp `viewport.py`, `main_window.py`, `timeline.py`, `dialogs.py`, lint och död kod bort, felgränser, CI-grindar |
| **0.8.5** | Fusion-lik B-Rep Topologi | **Enhetlig B-Rep-modell (se Del F):** strikta Vertices, Edges, Loops och Faces utan konkurrerande kantobjekt. `Tangent Chain` i Fillet/Chamfer, Face-picking för perimeterval, stabila topologiska referenser. |
| **0.9** | AI i appen | Inbyggd AI-konsol med levande utdata, layoutvakt som skärmdumpar och granskar automatiskt (se Del E) |
| **0.10** | Modellera | Hole-dialog, Extrude: Taper + Start + All/To object, Press/Pull (Q), **Text i skiss + extrudera/emboss/deboss**. Smart: **S1 Markera liknande** |
| **0.11** | Smart I | **S2 Stämpla**, **S3 Klicka-till-källa**, **S4 Print-verktygslåda**, **S5 Runda allt med regler** |
| **0.12** | Smart II + vy | **S6 Kommandorad + makron/konsol** (och inbyggd AI-hjälp), **S7 Varianter + scrub**, visningslägen, Home-vy, Fusion-musmappning, Delete, kopiera/klistra, Move/Copy |
| **0.13** | Robusthet | **S8 Associativa ytskisser**, **S9 Symmetriläge**, **S10 Checkpoints + visuell diff** |
| **0.14+** | Efter behov | Skiss: Extend, Break, Project av valda kurvor, Scale, ellips, spline, text på bana, fler villkor, bågar/slots i lösaren. Solider: Sweep, Loft, Draft, variabel fillet, gänga, Offset Face, målkroppar för Join/Cut, STEP-export/import |
| **1.0** | Komplett och pålitlig | Allt vi valt ovan, testsvit grön på varje push, inga kända dataförluster, dokumentation och sajt i fas |

## Del A – Global ångra (0.6)

Ångra fungerade bara för skissändringar. Nu ska allt kunna ångras som i Fusion.

- Dokumentet *är* sin historik (JSON: parametrar, tidslinje, skisser, plan, snitt, canvases); kroppar byggs om av `Timeline.recompute`. En ögonblicksbild är alltså det serialiserade dokumentläget, och återställning laddar in det på plats (samma `Document`-objekt och lyssnare) följt av en omräkning.
- (De)serialiseringen flyttas ur `Exporter` till `document_to_dict` / `apply_dict`; filformatet är oförändrat. Stora data (importerade meshar, canvas-bilder) delas, kopieras inte.
- En enhetlig ångra-stack med skiss-poster (som förut) och dokument-poster. Ett `@undoable("Extrude")`-omslag runt alla steg som ändrar dokumentet; bara ytterst räknas, och bara om något ändrats.
- `Finish Sketch` kan ångras och går då tillbaka in i skissläget. Ångra är avstängt medan ett verktygspanel eller en drag pågår.
- Menyn visar vad som ångras ("Undo Extrude 2").

## Del B – Smart-spåret: sådant Fusion inte har

Rankat efter tidsvinst per arbetsinsats.

- **S1 Markera liknande** (`S` på en kant/yta/hål): markerar allt med samma längd, riktning, konvexitet, radie eller diameter. "Alla hål på 6 mm", "alla lodräta kanter". Byggs på `faces.compute_planar_edges`, `CircularEdge`, `LoopEdge`.
- **S2 Stämpla**: välj ett eller flera steg (ett hål med fasningar, en pinne) och klicka på varje plats där det ska hamna; stegen återskapas riktade mot ytan du klickar på. Generaliserar dagens delta-pattern till oregelbundna placeringar.
- **S3 Klicka-till-källa**: pekar du på en yta eller kant säger statusraden vilket steg som skapade den; klick hoppar till steget och öppnar dess redigering. Gör långa historiker felsökbara.
- **S4 Print-verktygslåda** (3D-skrivare är primär målgrupp): global tolerans/spelrum som hål och tappar kan referera till, *Elefantfot*-preset (fasning på alla undre kanter i ett klick), skruvhålsbibliotek (M2–M5 med försänkning, ingjutningsmutter), analysvy för överhäng och väggtjocklek.
- **S5 Runda allt med regler**: ett reglage som live-förhandsgranskar fillet på alla konvexa kanter, med regler (utom basytan, bara lodräta, bara på vald yta).
- **S6 Kommandorad + makron/konsol**: `Ctrl+K` med tangentbordsstyrda kommandon ("box 40 30 10", "hål 6 djup 10", "runda 2 överkanter"), en inbyggd Python-konsol mot `Document`-API:et och en makroinspelare som kan spelas upp på en annan modell. Här kopplas även den inbyggda AI-hjälpen in (se Del C).
- **S7 Varianter + scrub**: namngivna parameteruppsättningar (S/M/L, 0,2/0,4 mm spel) som växlas med ett klick, Alt+dra på valfritt mått för att scrubba värdet med live-omräkning, och *Gör till parameter* direkt från Measure.
- **S8 Associativa ytskisser**: skisser på ytor och offset-plan följer ytan när kroppen ändras (ytans "fingeravtryck" matchas om som vi redan gör med kanter). Tar bort en känd begränsning och löser Fusions värsta ärr (topological naming) i vår enklare modell.
- **S9 Symmetriläge**: slå på ett symmetriplan så speglas varje steg automatiskt, parametriskt.
- **S10 Checkpoints + visuell diff**: namngivna versioner och en vy som visar vad som ändrats mellan två (tillagt grönt, bortaget rött).

### Text (klart i 0.7.9.50, kvar: wrap på cylinder och text-parametrar som {Namn})
Fusion: *Sketch > Text* öppnar en dialog (text, font, höjd, teckenavstånd, justering, fet/kursiv); man drar en ruta i skissen; texten förblir redigerbar tills den "exploderas". Textprofiler kan extruderas (join/cut) eller **Emboss/Deboss**. Enlinjefonter fungerar inte för solider. Text på bana kommer senare.
- Ny `SketchText`-entitet i `omacad/model/sketch.py`; konturer från Qt (`QPainterPath.addText` + `toSubpathPolygons`), hål (O, A, 8) via shapely så `solve_profiles` ger profiler som för cirklar och slots.
- Skissverktyget **Text** (ribbon och Create-menyn) med dialog och live-förhandsvisning, dubbelklick redigerar, *Explode* ger vanliga linjer. Typsnitt via `QFontDatabase`; saknas fonten på en annan maskin används en reservfont och en varning visas (viktigt för Windows-EXE:n).
- Egen **Emboss**-knapp: djup, upphöjd/ingraverad, väljer ytan texten ligger på.
- Test: volym av en extruderad bokstav ("I" = rektangel, "O" = ring) mot exakt beräkning.

## Del C – Säkerhetsnät och AI-återkoppling (0.7)

**Säkerhetsnät (inget får gå sönder):**
- **Autosave-historik**: efter varje ändring (med kort fördröjning) sparas en ögonblicksbild i `~/.local/share/omacad/history/<dokument>/`, oberoende av din fil; senaste 200 plus en per timme längre bakåt. Samma ögonblicksbild som ångra använder.
- **Krasch-återställning**: startar du efter en krasch erbjuds den senaste historiken. En global felfångare håller programmet vid liv, sparar och erbjuder *Rapportera*.
- **Versionshistorik** (Arkiv-menyn): lista med miniatyrbild per version; öppna en gammal version som nytt dokument eller återställ den på plats (och det går att ångra).
- **Säker spara och ladda**: `.bak` av föregående fil vid varje spara, redan atomisk skrivning. Okända eller trasiga steg i en fil *bevaras* (och hoppas över med en varning) i stället för att tappas, så en nyare fil aldrig förstörs av en äldre version. En trasig fil faller tillbaka på `.bak` och historiken.
- **Varje rättad bugg blir ett regressionstest** med det inskickade dokumentet som fixtur (se nedan).

**Starta om med ny version (`Ctrl+Shift+R`)** – utvecklingsloopen och uppdateringar:
- Du trycker, programmet sparar en **sessionsbild** i `~/.local/share/omacad/session/` (dokumentet inklusive osparade ändringar, filens sökväg, kamera, aktiv skiss och verktyg, markering, och ångra-stacken), startar sig självt på nytt med den senaste koden (`app.py --restore-session`) och stänger sig. Det nya fönstret öppnas med samma dokument, samma vy och samma skiss, så du fortsätter exakt där du var, och en bugg som just rättats är redan borta.
- **Utvecklingsläge** (`./run.sh --dev`): en filbevakare på `omacad/*.py` visar en liten notis "Ny version finns, ladda om (Ctrl+Shift+R)" varje gång jag sparat en rättning, så att du kan prova den direkt utan att stänga något.
- **Den installerade EXE:n**: samma knapp kollar GitHub efter en nyare release (`v<version>`) och erbjuder "Uppdatera och starta om" (hämtar, sparar sessionen, byter fil, återställer).
- Misslyckas återställningen (till exempel att en ny version inte kan läsa sessionsbilden) faller programmet tillbaka på senaste autosave och säger det tydligt; sessionsbilden raderas aldrig innan det nya fönstret har bekräftat att det laddat klart.

**"Det blev fel"-knappen och AI-återkoppling** – så bygger vi appen vidare:
- Knapp i verktygsraden (och kortkommando) som öppnar en liten dialog: du kan peka ut stället (klick i vyn, rektangel eller pil) och skriva en rad om vad som är fel.
- Programmet samlar automatiskt ett paket i `~/.local/share/omacad/feedback/<tid>/`: **skärmbild av vyn** (med markeringen), **dokumentet** (`document_to_dict`), **de senaste stegen och ångra-etiketterna**, en **händelselogg** (senaste 50 åtgärder och eventuella fel), kameran, markerade objekt och 3D-punkten du pekade på, version och plattform.
- En **Claude Code-färdighet** (`/omacad-feedback`) läser det senaste paketet (bilden och JSON-filen), felsöker, rättar och lägger paketets dokument som ett nytt regressionstest. Arbetsflödet: du ser något knasigt, trycker, och jag får bilden och modellen direkt.
- Senare (S6): en **inbyggd AI-hjälp** i programmet som kan svara på "varför blev det så här?" och föreslå en åtgärd, med samma paket som underlag. Det kräver en API-nyckel som lagras lokalt och skickar aldrig något utan att du bekräftar.

## Del D – Lean, clean, unbreakable (0.8)

Koden ska vara liten, tydlig och tålig. Mätbara mål, som CI kontrollerar:
- **Dela upp de stora filerna**: `ui/viewport/` är ett paket med rendering, plockning, overlays och separata input-, mät-, context menu-, skissverktygs-, pekar-, profil-, flytt-, dimensions-, måttritnings- och operationsmixins; viewportens pekar-, dimensions- och skissverktygsflöden är nu grupperade i separata moduler. `tool_prompts.py` är nu en kompatibilitetsfasad till grupperade controllers; skissentiteter är flyttade till `sketch_entities.py` medan `Sketch` stannar i `sketch.py`. `sketch.py` och `faces.py` har nu kompatibla fasader över uppdelade moduler. Fil-/session- och menyansvar är flyttade från `main_window.py` till controllers; temaikoner och QSS ligger i separata moduler. Ingen fil över ~800 rader.
- **Prestanda och effektivitet (High-Performance Engine)**:
  1. *Inkrementell Timeline Recompute*: cacha kropparnas `Manifold`-tillstånd vid varje steg, så att ändringar i steg $K$ bara räknar om från steg $K \to N$ i stället för från steg 0.
  2. *Topologicache för ytor och kanter*: cacha `compute_planar_faces_and_edges`-analysen på `Manifold`-hash/id så oförändrade kroppar i en scen inte analyseras om i onödan.
  3. *OpenGL VBO / VAO Caching*: ladda mesh och linjer direkt till GPU VBO:er så navigation (orbit/pan/zoom) flyter i full GPU-skärmhastighet (144+ FPS) utan CPU-tapp.
  4. *Bakgrundstråd för tunga beräkningar*: kör tunga booleska operationer och preview-beräkningar i `QThreadPool` så GUI:t förblir silkeslent utan mikrofrysningar.
  5. *Adaptiv tessellering*: snabbare förhandsvisning i viewport med färre segment under interaktiv redigering, full finkornighet vid slutförande och export.
- **Lint och död kod bort**: `ruff` (stil, oanvända importer, buggmönster) och `vulture`; formatering med `ruff format`; CI avvisar nya varningar.
- **Felgränser**: alla Qt-slots och musåtgärder går genom en dekoratör som fångar fel, loggar (`applog`), visar ett meddelande och erbjuder *Report problem*, så ett fel i ett verktyg aldrig fäller programmet eller lämnar ett halvt tillstånd. `print` ersätts av loggning.
- **Inga tysta `except: pass`**: varje `except` loggar eller har en kommentar varför det är säkert.
- **Fler tester**: egenskapstester (`hypothesis`) för geometri (offset, trim, fillet-volymer, ångra/gör om på slumpade stegföljder), regressionstest för varje rapporterad bugg (rapportens dokument läggs i `tests/regress/`), täckningsmätning, gräns i CI.
- **Typer** på modelllagret (`omacad/model`, `io`) med `mypy`, så ändrade datastrukturer fångas innan de når användaren.

## Del E – AI i appen (0.9)

Så att vi kan fixa allt inifrån programmet, med "dig" körandes i appen och en liten konsol som visar vad som händer. Bygger på rapportknappen (finns) och Omarchys standardagent.
- **AI-konsol** (dockbar panel längst ned): användaren skriver en uppgift ("gör hörnet runt", "varför blev offseten bruten?"). Programmet startar standardagenten på ett paket (skärmbild + dokument + logg + uppgiften) och strömmar agentens utdata till konsolen med levande rader för vad den läser, kör och ändrar (och testernas resultat). Teknik: `claude -p --output-format stream-json` när standardagenten är Claude Code, annars samma `omarchy agent prompt` i en terminal. Konsolen har *Avbryt*.
- **Layoutvakt**: efter ändringar i gränssnittet och vid inaktivitet tar programmet **skärmdumpar automatiskt** (flera fönsterstorlekar och teman) och kör först billiga automatiska kontroller via Qt:s geometri: överlappande eller avklippta widgetar, element utanför fönstret, för små träffytor, text som inte får plats. Hittar den något (eller på begäran) skickas bilderna och mätvärdena till AI:n, som granskar layouten *innan användaren hunnit be om det*, rättar och visar före/efter. Samma metod för 3D-vyn: kända testmodeller renderas och jämförs mot referensbilder.
- **Säkerhet för "inget får gå sönder"**: AI-ändringar görs i en git-gren/arbetsträd (`ai/<id>`), aldrig direkt på användarens fungerande version. Testerna måste vara gröna, annars återställs allt automatiskt. Knappen *Använd och starta om* slår ihop och startar om med den nya versionen (se 0.7); *Ångra* tar tillbaka den förra versionen. Autonominivå väljs i inställningarna: av, *föreslå*, *rätta med godkännande* (standard), *rätta småsaker automatiskt* (layout och stavning, aldrig geometri).
- **Minnet** är `omacad.md`: agenten läser den först och lägger till en rad i lösningsloggen efter varje rättning, så att samma fel inte görs om.

## Del F – Fusion-lik B-Rep Topologi (0.8.5)

För att garantera långsiktig stabilitet och förhindra tvetydigheter i kant- och yturval:
- **Ren B-Rep-topologi:**
  - En fast topologihierarki: `Body -> Faces -> Loops -> Edges -> Vertices`.
  - **Inga parallella/konkurrerande kantobjekt**: Varje kurva/segment på en solid representeras av exakt en unik topologisk Edge som delas mellan angränsande ytor.
  - Sammansatta slingor (`LoopEdge`) är inte längre separata kantobjekt som krockar med linjer och bågar, utan ytans `outer_loop` / `inner_loops` av ordnade Edges.
- **Urval i paritet med Fusion 360:**
  - **Tangent Chain (aktiv som standard i Fillet/Chamfer):** Klick på en linje eller båge plockar automatiskt alla sammanhängande tangentiella kanter ($G^1$).
  - **Face Selection:** Klick på en plan eller cylindrisk yta i Fillet/Chamfer väljer alla dess avgränsande kanter.
  - **Tangent propagation i 3D:** Automatisk spårning av kurvkedjor och $G^1$-skarvar utan tröskelproblem.
- **Topologisk stabilitet (Persistent Naming):**
  - Entiteter får deterministiska ID:n baserade på sin geometriska historik så att funktioner som Fillet och Chamfer inte tappar referenser vid uppströmsändringar.

## Arbetsregler

- Fusions beteende undersöks *före* varje funktion byggs.
- Ny funktion = test + `CHANGELOG.md` + `README.md`/`ROADMAP.md` + skärmbild.
- Version höjs per släpp; push till `main` bygger EXE och släpper `v<version>`.
- Sajtsidan (`/omacad/`) uppdateras per minor-version.
- Inget skickas, publiceras eller pushas utan att du ber om det.
