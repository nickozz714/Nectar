# WireGuard — remote toegang tot het thuisnetwerk (en dus de HiveMind)

Draait als één container op de thuisserver (192.168.2.15). Vervangt de gestorven
Tritium-H5/OpenVPN. Eenmaal verbonden werkt alles op het LAN gewoon, dus ook
`http://192.168.2.<hive-host>:8642` voor de HiveMind — geen extra poorten naar buiten.

## Waarom dit "super duper veilig" is

- **WireGuard antwoordt niet op onbekenden.** Zonder geldige key reageert UDP 51820
  helemaal nergens op — voor een scanner bestaat de poort niet (in tegenstelling tot
  OpenVPN, dat wél handshaket).
- **Moderne vaste crypto** (Curve25519/ChaCha20-Poly1305), geen cipher-onderhandeling,
  ~4k regels kernelcode i.p.v. honderdduizenden.
- **Eén UDP-poort naar buiten, verder niets.** Geen web-UI (bewust niet gekozen: elke
  beheer-UI is extra aanvalsoppervlak), geen management-API.
- **Per apparaat een eigen keypair** (peer): apparaat kwijt → alleen die peer-config
  verwijderen en container herstarten.
- **Split tunnel**: alleen 192.168.2.0/24 gaat door de tunnel; gewoon internetverkeer
  van je laptop/telefoon niet (privacy + snelheid). Wil je full tunnel: zet
  `ALLOWEDIPS: 0.0.0.0/0`.
- `LOG_CONFS: false` — geen QR/keys in de containerlogs.

## Installatie (op de thuisserver)

```bash
# 1. deze map naar de server kopiëren en starten
docker compose up -d

# 2. peer-configs ophalen (eenmalig, per apparaat)
docker exec wireguard cat /config/peer_nick-macbook/peer_nick-macbook.conf
docker exec wireguard /app/show-peer nick-iphone     # toont QR-code voor de telefoon

# 3. KPN-router (mijnmodem.kpn): port-forward UDP 51820 -> 192.168.2.15
#    (dit is de enige handmatige stap; verder niets openzetten)
```

Apparaten: WireGuard-app installeren (macOS/iOS), config importeren (QR of bestand),
tunnel aanzetten. Daarna is de HiveMind-GUI bereikbaar op het LAN-adres en wijst
`HIVE_URL` in je Claude-omgeving daar ook naartoe.

## Beheer

- **Nieuw apparaat**: naam toevoegen aan `PEERS`, `docker compose up -d` (bestaande
  peers blijven ongemoeid), config/QR ophalen zoals hierboven.
- **Apparaat intrekken**: naam uit `PEERS` halen, `docker exec wireguard rm -rf
  /config/peer_<naam>`, `docker compose up -d --force-recreate`.
- **Status**: `docker exec wireguard wg show` (laatste handshake per peer).
- `WG_SERVERURL` in een `.env` naast deze compose zetten zodra er een vast
  WAN-adres/DDNS-naam is; `auto` pakt anders het huidige publieke IP.

---

**Waar dit draait.** De container draait op de server niet vanuit deze map maar
vanuit `/Server/Applications/wireguard/` — een eigen compose-project, los van de
HiveMind-stack, zodat een HiveMind-deploy de VPN nooit raakt. De bestanden hier
zijn de versiebeheerde kopie daarvan; wijzig ze hier en kopieer ze daarheen.
