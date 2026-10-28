# Objektbaserad historik i Omacad

Datum: 2026-10-24. Status: godkänd för implementation i autoläge.

## Mål

Varje modellobjekt får en egen historik i browsern till vänster. Ett objekt börjar med en skiss, primitiv eller import. Modelloperationer visas i byggordning under objektet, med redigerbara mått och referenser under respektive steg. Verkliga förgreningar skapas genom ett nytt objekt från ett valt steg.

```text
Projekt
├─ Parametrar
├─ Ursprung och konstruktionsplan
├─ Burk [aktiv]
│  ├─ Skiss: botten
│  │  └─ Diameter: 60 mm
│  ├─ Extrude
│  │  └─ Höjd: 80 mm
│  ├─ Shell
│  │  └─ Väggtjocklek: 2 mm
│  └─ Fillet
│     └─ Radie: 3 mm
└─ Lock
   ├─ Cylinder
   └─ Gänga
```

## Modell och arbetsflöde

- Modellobjekt har beständig identitet, oberoende av den för tillfället beräknade kroppen. Skissobjekt och objekt med fel finns kvar i browsern.
- Aktivt objekt styr var nya giltiga operationer hamnar. Fristående skiss eller primitiv skapar ett nytt objekt.
- Steg har stabila ID:n, ägare, uttryckliga indata och utdata. Globalt listindex får inte vara beständig identitet.
- Målobjekt väljs, förhandsvisas och sparas. Gamla operationers automatiska träffbaserade mål måste behålla äldre semantik tills säker konvertering finns.
- Trädet visar ägande; en acyklisk beroendegraf hanterar kopplingar mellan objekt.
- Delade skisser har en ägare och länkar från användarna. Ytbaserade skisser refererar ett bestämt källsteg och dess yta.
- Combine ägs av målobjektet och länkar till verktygsobjektet. Flerobjektsoperationer finns en gång och visas som länkar hos övriga berörda objekt.
- Länkad förgrening och fristående kopia är skilda kommandon. En fristående kopia utgår från fryst geometri.
- Befintliga Split-steg behåller sitt frysta eller parametriska beteende. Ny länkad delning ska vara ett uttryckligt alternativ.
- Markering, kamera och synlighet är vyinställningar, inte modelleringssteg.

## Måttredigering

Mått kan redigeras direkt i trädet med enheter och formler. Dubbelklick på steg öppnar befintlig fullständig editor. Skissmått använder befintliga dimensionsvillkor. Enter bekräftar, Escape avbryter, och en bekräftelse är ett ångra-steg. Styrande mått skiljs från uppmätta, skrivskyddade mått, särskilt för importgeometri.

## Historik, beroenden och fel

Varje objekt får lokal historikmarkör. Visa efter steg är tillfällig inspektion; infoga här är en modelländring som bevarar senare steg. Oberoende objekt påverkas inte. Bekräftade ändringar räknar om beroende grenar. Ångra/gör om förblir dokumentgemensamt.

Felande steg markeras med orsak; beroende steg blockeras och oberoende objekt fortsätter fungera. Senast giltig geometri får bara visas med tydlig markering som inaktuell. Förlorade yt-/kantreferenser ska kunna väljas om; osäker matchning får inte tyst accepteras.

## Etapper och klartkriterier

1. **Modell och kartläggning:** definiera identitet, ägande, indata/utdata och beroenden för alla featuretyper, inklusive Split, Combine, Pattern och delade skisser.
2. **Objektträd ovanpå befintlig motor:** visa och redigera historik per objekt med bibehållen global körordning och identisk geometri.
3. **Mått i trädet:** gemensamma parameterbeskrivningar, enheter, formler och validering. Träd och dialog ger samma resultat och ångra fungerar.
4. **Explicit beroendemodell:** stabila steg-ID:n, sparade mål/referenser och beroendeordnad beräkning. Oberoende objekt byggs inte om.
5. **Lokala historiker och grenar:** återblick, infogning, förgrening, undertryckning och beroendekontroller fungerar per objekt.
6. **Filkonvertering och övergång:** versionerat format och representativa gamla projekt verifierade. Den globala nedersta raden avvecklas när ersättningen fungerar.

Etapp 2 är en användbar mellanleverans, men självständiga timelines kräver etapp 4–5. Oklara äldre projekt ska behålla äldre körsemantik i stället för att konverteras genom gissning.

## Berörda moduler

- `omacad/model/document.py`: objektägande, redigering och ångra.
- `omacad/model/timeline.py`: historikmarkörer, beroenden, körordning och cache.
- `omacad/model/features/`: explicit målhantering, parameterbeskrivningar och referenser.
- `omacad/ui/browser.py`: objektträd, steg, mått och felstatus.
- `omacad/ui/feature_edit.py`: redigering i rätt historiskt tillstånd.
- `omacad/ui/timeline_bar.py`, `main_window.py`: övergång från global rad till browser.
- `omacad/io/exporter.py`: versionering, serialisering och migrering.

## Acceptanstester

- Två oberoende objekt: en ändring lämnar det andra oförändrat.
- Delad skiss: alla beroende objekt uppdateras korrekt.
- Infogning mitt i historiken bevarar senare steg.
- Combine, Split och förgrening behåller ägande/referenser efter sparning och återöppning.
- Ogiltiga mått och förlorade kanter ger begripliga fel utan förlorat arbete.
- Ångra/gör om återställer geometri, formler och objektkopplingar.
- Gamla projekt behåller geometri och tidigare Split-beteende.
- Synlighet, markering och expanderade grenar bevaras vid uppdatering.

## Arbetsregler

Implementera i små verifierbara steg. Kör riktade modell- och GUI-tester enligt projektets regler. Befintliga användarfiler lämnas orörda. Ingen push eller publicering utan separat instruktion.

## Genomförandelogg

- 2026-10-24: planen sparad; implementation påbörjas.
