# Platen

Acht diagrammen die Nectar uitleggen, in de volgorde waarin je het aan een zaal vertelt.
Allemaal **1600 × 900** (16:9 — precies een slide) en **SVG**, dus scherp op elk formaat.

| # | Bestand | Waarvoor |
| --- | --- | --- |
| 1 | `nectar-1-wat-is-het.svg` | Wat het is: zonder/met, en wat er in het geheugen zit |
| 2 | `nectar-2-het-wereldbeeld.svg` | Korf, zwerm, nectar, pollen, bloei — en de rest van de woorden |
| 3 | `nectar-3-hoe-werkt-het.svg` | De cyclus: ophalen, werken, terugschrijven, onderhouden |
| 4 | `nectar-4-de-write-gate.svg` | De poort, uitvergroot: twee toetsen, drie uitkomsten |
| 5 | `nectar-5-zwerm-en-pollen.svg` | Hoe het zichzelf onderhoudt, en met welke waarborgen |
| 6 | `nectar-6-focus.svg` | Koers houden over sessies heen, en banen naast elkaar |
| 7 | `nectar-7-niets-staat-lokaal.svg` | Skills, workflows en afspraken komen uit Nectar |
| 8 | `nectar-8-wat-levert-het-op.svg` | Zes voordelen, en waar het ophoudt |

De nummering **is** de vertelvolgorde: eerst het beeld en de woorden, dan de werking, dan de
drie mechanismen die mensen altijd willen zien (de poort, de zwerm, de focus), en tot slot
wat het oplevert. Plaat 4 en 5 vergroten respectievelijk stap 3 en stap 4 van plaat 3 uit,
dus die drie horen bij elkaar.

**Bewust niet technisch.** Ze moeten het doen bij iemand die nog nooit van een kennisgraaf
heeft gehoord. Dus geen embeddings, geen RRF, geen DAG: "het zoekt op betekenis, niet op
exacte woorden", "wat gebruikt wordt stijgt, wat niemand raakt zakt weg". De techniek staat
in [ARCHITECTURE.md](../ARCHITECTURE.md) en
[ML-AND-ALGORITHMS.md](../ML-AND-ALGORITHMS.md) voor wie doorvraagt.

Plaat 8 sluit af met wat Nectar **niet** doet: het vult zichzelf niet en leest niet vanzelf
documenten mee. Dat hoort erbij — het maakt de zes punten erboven geloofwaardiger dan ze
weglaten, en het voorkomt een verwachting die je daarna moet terugdraaien.

## Beeldtaal

Honinggeel `#E08C1E` is Nectar (uit de mind-interface), donker `#0B1220` is de hive zelf.
De LabX-platen gebruiken blauw `#3B82F6`; op een plaat waar beide voorkomen zie je daardoor
zonder legenda welke kant welk product is.

## Naar PowerPoint

```bash
python3 maak-pptx.py --titel "Nectar" \
    --ondertitel "Het geheugen van de organisatie — acht platen, van wat het is tot wat het oplevert" \
    --accent E08C1E --uit Nectar-platen.pptx
```

Levert een 16:9-deck op met een titeldia, één dia per plaat en **sprekersnotities**
(waarvoor die plaat is, en waar je bij het vertellen op moet letten). In elke dia zit de
SVG én een bitmap-voorvertoning: PowerPoint 2019+ toont de vector — scherp op elk formaat en
met rechtermuis → *Converteren naar vorm* tot losse vormen te maken — en oudere versies
vallen terug op de bitmap. Zo gaat het deck overal open.

Het renderen gebeurt met Chrome in headless-modus en niet met ImageMagick: die laatste
rendert SVG-tekst met een eigen, beperkte engine en maakt er een potje van zodra er een
lettertype-fallback aan te pas komt.

De `.pptx` staat bewust **niet** in git — het is een gegenereerd bestand dat bij elke
regeneratie in zijn geheel verandert, en de platen ernaast zijn de bron. Het bouwen kost een
paar seconden.

## In een presentatie

- **PowerPoint / Keynote**: Invoegen → Afbeeldingen → het `.svg`-bestand.
- **Losse onderdelen aanpassen**: rechtermuis → *Converteren naar vorm*.
- **Google Slides** lust geen SVG — maak er eerst een PNG van.

De platen vragen om Archivo en vallen terug op Segoe UI / Helvetica Neue / Arial. Bewust
geen webfont: een plaat die in een presentatie belandt moet het ook doen op een machine die
dat lettertype niet heeft.
