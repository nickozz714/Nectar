# Platen

Vier diagrammen die Nectar uitleggen, in de volgorde waarin je het aan een zaal vertelt.
Allemaal **1600 × 900** (16:9 — precies een slide) en **SVG**, dus scherp op elk formaat.

| # | Bestand | Waarvoor |
| --- | --- | --- |
| 1 | `nectar-1-wat-is-het.svg` | Wat het is: zonder/met, en wat er in het geheugen zit |
| 2 | `nectar-2-hoe-werkt-het.svg` | De cyclus: ophalen, werken, terugschrijven, onderhouden |
| 3 | `nectar-3-niets-staat-lokaal.svg` | Skills, workflows en afspraken komen uit Nectar — niets lokaal |
| 4 | `nectar-4-wat-levert-het-op.svg` | Zes voordelen, en waar het ophoudt |

**Bewust niet technisch.** Ze moeten het doen bij iemand die nog nooit van een kennisgraaf
heeft gehoord. Dus geen embeddings, geen RRF, geen DAG: "het zoekt op betekenis, niet op
exacte woorden", "wat gebruikt wordt stijgt, wat niemand raakt zakt weg". De techniek staat
in [ARCHITECTURE.md](../ARCHITECTURE.md) en
[ML-AND-ALGORITHMS.md](../ML-AND-ALGORITHMS.md) voor wie doorvraagt.

Plaat 4 sluit af met wat Nectar **niet** doet: het vult zichzelf niet en leest niet vanzelf
documenten mee. Dat hoort erbij — het maakt de zes punten erboven geloofwaardiger dan ze
weglaten, en het voorkomt een verwachting die je daarna moet terugdraaien.

## Beeldtaal

Honinggeel `#E08C1E` is Nectar (uit de mind-interface), donker `#0B1220` is de hive zelf.
De LabX-platen gebruiken blauw `#3B82F6`; op een plaat waar beide voorkomen zie je daardoor
zonder legenda welke kant welk product is.

## In een presentatie

- **PowerPoint / Keynote**: Invoegen → Afbeeldingen → het `.svg`-bestand.
- **Losse onderdelen aanpassen**: rechtermuis → *Converteren naar vorm*.
- **Google Slides** lust geen SVG — maak er eerst een PNG van.

De platen vragen om Archivo en vallen terug op Segoe UI / Helvetica Neue / Arial. Bewust
geen webfont: een plaat die in een presentatie belandt moet het ook doen op een machine die
dat lettertype niet heeft.
