# HiveMind — installeren in dit project (instructies voor Claude)

Je hebt dit install-pakket (`hivemind-install.zip`) in een project gekregen. Doel: dit
project koppelen aan de HiveMind zodat relevante org-memories automatisch bij elke prompt
worden opgehaald en je met `hive_search` / `hive_remember` e.d. kunt werken.

**Dit pakket bevat GEEN token.** Vraag de gebruiker om de gegevens hieronder als je ze nog
niet hebt.

## Wat je van de gebruiker nodig hebt
- **HIVE_URL** — bijv. `http://your-server:8642` (thuis-LAN of via VPN).
- **HIVE_TOKEN** — het account-token (per persoon/machine; los intrekbaar).
- **anchors** (optioneel) — komma-lijst van onderwerp-topics waar dit project op leunt,
  bijv. `Swinkels,Fabric werkwijzen`. Deze krijgen voorrang in de recall-ranking.

## Installeren (de makkelijke weg)
Pak de zip uit in de projectroot en draai de installer:

```bash
unzip -o hivemind-install.zip
cd hivemind-install
./install.sh "<HIVE_URL>" "<HIVE_TOKEN>" "<anchors-optioneel>"
```

`install.sh` doet dit veilig (merget, overschrijft geen bestaande keys):
1. plaatst de hook-scripts onder `.hivemind/scripts/` in de projectroot;
2. merget in `.claude/settings.json`: `env` (HIVE_ENABLED/URL/TOKEN/ANCHORS) + een
   `UserPromptSubmit`-hook die `.hivemind/scripts/hive_recall.sh` aanroept;
3. merget in `.mcp.json`: de `hivemind` MCP-server (bearer-token);
4. checkt of `HIVE_URL/health` bereikbaar is.

Start daarna een **nieuwe** Claude-sessie in dit project — de recall-hook draait dan mee.

## Verifiëren
Stel in de nieuwe sessie een vraag die alleen uit de HiveMind te beantwoorden is (iets
projectspecifieks dat niet in de code/CLAUDE.md staat). Komt het juiste antwoord eruit,
dan werkt de koppeling. Of roep de tool `topic_list` aan — die geeft de topics in de mind.

## Belangrijk
- **Token niet committen.** Is dit project een git-repo, zet dan `.claude/settings.json`,
  `.mcp.json` en `.hivemind/` in `.gitignore` (of gebruik `settings.local.json`). De
  installer waarschuwt hiervoor.
- **Memories schrijf je in de HiveMind**, niet in losse markdown: gebruik `hive_remember`
  (type `decision` voor expliciete keuzes), `skill_put` / `workflow_put` voor skills/
  workflows. De write-gate regelt kwaliteit/PII/dedup.
- Geen token? Vraag een org_admin om er een aan te maken met `hive_invite` (dan registreer
  je met de invite-code) of rechtstreeks via `/manage/tokens`.

## Handmatig (fallback, als `install.sh` niet kan draaien)
Doe wat de installer doet: kopieer `scripts/` naar `.hivemind/scripts/`, schrijf de
`env` + `UserPromptSubmit`-hook in `.claude/settings.json` (commando = het absolute pad
naar `.hivemind/scripts/hive_recall.sh`), en zet `mcpServers.hivemind` in `.mcp.json`
(`type: http`, `url: <HIVE_URL>/mcp`, header `Authorization: Bearer <HIVE_TOKEN>`).
