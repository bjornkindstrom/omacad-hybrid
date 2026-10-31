# Avbrutet test: fillets och Jar with Lid

Alla benchmarkprocesser stoppades på användarens begäran. Inga fler körningar pågår.

## Färdiga byggtider

En körning per version/fall, alltså preliminära resultat, inte ett statistiskt säkerställt resultat.

| Fall | Kvalitetsinställning | Omacad | Hybrid | Tidsminskning |
|---|---:|---:|---:|---:|
| Box, fyra toppkanter, fillet R3 | 720 cirkelsegment | 0,058 s | 0,060 s | Ingen tydlig vinst |
| Cylinder, fillet R3 på övre cirkelkant | 720 cirkelsegment | 6,52 s | 6,11 s | Cirka 6 % |
| Jar with Lid, standardmått och full historik | 360 cirkelsegment | 61,62 s | 50,34 s | Cirka 18 % |

Båda versionerna gav identiska mesh-hashar, volymer, triangelantal och yt-/kantantal i alla tre färdigbyggda fallen. Burkparet hade totalt 51 432 trianglar. Burkens bygge blev klart i Hybrid men dess efterföljande viewportmätning stoppades.

## Kvalitet och begränsningar

- 360 är högsta förvalda smoothness-nivån i appens meny. 720 är kärnans övre gräns och användes som extra stresstest/filletinställning.
- Ingen interaktiv geometri-förenkling användes vid de redovisade byggena.
- De färdiga fillet-viewporttesterna verifierade 2560 × 1440 faktiska framebufferpixlar och 8× faktisk MSAA.
- En profilerad Omacad-körning av Jar with Lid vid 720 avbröts efter 600 sekunder. Detta är inte en normal oprofilerad byggtid och ger ingen rättvis jämförelse mot Hybrid.
- Vissa filletverktyg har fortfarande fasta 16/24 bågsegment. Den globala smoothness-inställningen styr därför inte alla filletbågar.
- Bildtider varierade mellan körningarna och får inte användas som belägg för högre FPS. Ingen komplett Jar-viewportjämförelse hann bli klar.

## Rust-utökningen

Hybrid har utökats lokalt från BVH-plockning till två batchade pass för plana triangelgrupper och plana skuggningsytor. Samma sammanslagningsordning, toleranser, grupp-ID:n och float32/float64-beteende bevaras. Pythonvägen finns kvar.

22 relevanta Python-/Qt-tester och fyra Rusttester passerade; strikt Clippy passerade. Detta inkluderar fillets, skuggningsnormaler, burkens redigerbara historik och exakt renderbuffer-/gruppjämförelse mot Python.

Koden är byggd och installerad i Hybrid-miljön men är fortfarande lokala, ocommittade ändringar; den är inte pushad. En redan öppen app laddar inte automatiskt den nya modulen. Original-Omacads källkod är oförändrad.

Burkresultatet pekar på en förbättring men merparten av väntetiden är kvar: summerad rendernät-/yt-/kantuppdatering tog ungefär 57,21 s i originalet och 46,64 s i Hybrid. Detta är inkluderande instrumenterade tider, inte separata tillägg till byggtiden.
