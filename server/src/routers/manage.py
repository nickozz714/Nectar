from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from neo4j import Session

from pydantic import BaseModel

from src.authentication.deps import ROLES, AuthedAccount, require_account, require_role
from src.components.db import get_graph
from src.repository import registration_repo, tenancy_repo
from src.services import org_service
from src.models.core import (
    AccountOut,
    InviteCreate,
    OrgAccountCreate,
    TokenCreate,
    TokenOut,
    TokenRoleBody,
)

# Everything here is done with an org_admin ACCOUNT TOKEN — no operator admin token.
# All actions are scoped to the caller's own org.
router = APIRouter(prefix="/manage", tags=["manage"])


class ConsensusBody(BaseModel):
    threshold: int


class CognitionBody(BaseModel):
    enabled: bool


@router.get("/teams")
def list_teams(
    account: AuthedAccount = Depends(require_role("org_admin")),
    session: Session = Depends(get_graph),
):
    """Teams in the org (name + uid) — for name-based pickers in the GUI."""
    return tenancy_repo.list_teams(session, account.org_uid)


@router.get("/swarm")
def swarm_settings(
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    """The Swarm's consensus threshold (min votes before a Pollen is actionable). Any member."""
    return org_service.get_swarm_settings(session, account)


@router.get("/settings")
def tuning_settings(
    account: AuthedAccount = Depends(require_role("org_admin")),
    session: Session = Depends(get_graph),
):
    """Read-only view of the live tuning knobs so an org_admin can SEE how the brain is
    configured. Grouped for the GUI. Only the consensus threshold is editable at runtime
    (POST /swarm/consensus); the rest are set via env/config and take effect on restart."""
    from src.components.config import get_settings
    s = get_settings()
    consensus = org_service.get_swarm_settings(session, account).get("consensus_threshold")
    return {
        "groups": [
            {"title": "Swarm & consensus", "icon": "🐝", "items": [
                {"key": "Consensus-drempel", "value": consensus, "editable": True, "env": "CONSENSUS_THRESHOLD",
                 "what": "Aantal onafhankelijke stemmen (geteld per account+model) dat een voorgestelde wijziging nodig heeft voordat de Swarm 'm mag uitvoeren. Op 1 = één stem is meteen genoeg (goed voor een solo/kleine swarm); hoger = meer ogen vereist.",
                 "risk": "Te laag: één (mogelijk foute) agent kan wijzigingen doordrukken. Te hoog: Pollen blijven hangen omdat de drempel nooit gehaald wordt. Een org_admin kan altijd handmatig 'direct toepassen'."},
                {"key": "Claim-TTL", "value": f"{s.CLAIM_TTL_MIN} min", "env": "CLAIM_TTL_MIN",
                 "what": "Hoe lang een door een agent geclaimde Pollen voor andere agents verborgen blijft (stigmergie: voorkomt dat twee agents dezelfde taak oppakken).",
                 "risk": "Te kort: dubbel werk. Te lang: een taak blijft geblokkeerd als de claimende agent 'm niet afmaakt."},
            ]},
            {"title": "Recall & injectie", "icon": "🎯", "items": [
                {"key": "Max. memories per recall", "value": s.RECALL_MAX_MEMORIES, "env": "RECALL_MAX_MEMORIES",
                 "what": "Harde bovengrens op hoeveel memories per prompt in de context worden geïnjecteerd. Bewust laag tegen 'context-rot' — te veel tekst verslechtert juist het antwoord van het model.",
                 "risk": "Te hoog: ruis en context-rot, het model raakt afgeleid. Te laag: relevante kennis mist."},
                {"key": "Relevantie-ondergrens", "value": s.RECALL_REL_FLOOR, "env": "RECALL_REL_FLOOR",
                 "what": "Een hit wordt weggelaten als zijn score onder deze fractie van de béste hit ligt. Houdt zwakke matches uit de context.",
                 "risk": "Te hoog: alleen de topper blijft over, context wordt mager. Te laag: half-relevante hits sluipen mee."},
                {"key": "Multi-hop buren", "value": s.MULTIHOP_ANCHORS, "env": "MULTIHOP_ANCHORS",
                 "what": "Van hoeveel top-memories ook de directe buren (1 stap in de graph) als kandidaat meekomen. Vangt gerelateerde kennis die niet letterlijk matcht.",
                 "risk": "Hoger: breder maar meer ruis en trager. Lager: samenhangende kennis wordt gemist."},
            ]},
            {"title": "Ranking-gewichten", "icon": "🎚️", "items": [
                {"key": "Semantiek / freshness", "value": f"{s.SEMANTIC_WEIGHT} / {s.FRESHNESS_WEIGHT}", "env": "SEMANTIC_WEIGHT / FRESHNESS_WEIGHT",
                 "what": "De basisweging tussen betekenis-gelijkenis en versheid. 0.7/0.3 = betekenis weegt zwaarder dan hoe recent iets is.",
                 "risk": "Meer freshness: nieuwe kennis dringt voor, ook als 'm minder relevant is. Let op: een getrainde learning-to-rank overschrijft deze gewichten."},
                {"key": "Anchor-boost", "value": s.ANCHOR_BOOST, "env": "ANCHOR_BOOST",
                 "what": "Ranking-bonus voor memories onder het actieve project-anker-topic, zodat projectkennis voorrang krijgt zonder andere kennis hard uit te sluiten.",
                 "risk": "Te hoog: je ziet bijna alleen nog projectkennis. Te laag: projectcontext weegt nauwelijks mee."},
                {"key": "Besluit / learning boost", "value": f"{s.DECISION_BOOST} / {s.LEARNING_BOOST}", "env": "DECISION_BOOST / LEARNING_BOOST",
                 "what": "Extra gewicht zodat besluiten en learnings (geleerde lessen) sneller bovenkomen — die wil je bijna altijd zien.",
                 "risk": "Te hoog: besluiten/learnings verdringen actueel-relevantere memories."},
                {"key": "Belang-gewicht", "value": s.IMPORTANCE_WEIGHT, "env": "IMPORTANCE_WEIGHT",
                 "what": "Hoe zwaar de handmatige 'belang'-pin (0..1) meetelt. Verschuiving = gewicht × (belang − 0,5): belangrijk stijgt, triviaal zakt.",
                 "risk": "Te hoog: handmatige pins overrulen de automatische relevantie."},
                {"key": "Uitkomst (Worth) gewicht", "value": f"{s.OUTCOME_WEIGHT} (min {s.OUTCOME_MIN_SAMPLES})", "env": "OUTCOME_WEIGHT / OUTCOME_MIN_SAMPLES",
                 "what": "Hoe zwaar het causale 'heeft-het-geholpen?'-signaal (Memory Worth) meetelt — pas vanaf genoeg feedback-samples.",
                 "risk": "Te hoog: een paar toevallige duimpjes sturen de ranking te sterk."},
                {"key": "PageRank-gewicht", "value": s.PAGERANK_WEIGHT, "env": "PAGERANK_WEIGHT",
                 "what": "Bonus voor structureel-centrale, goed-verbonden kennis (PageRank in de graph).",
                 "risk": "Te hoog: 'populaire' hubs komen altijd boven, ook als ze niet bij de vraag passen."},
                {"key": "Supersede-straf", "value": s.SUPERSEDE_PENALTY, "env": "SUPERSEDE_PENALTY",
                 "what": "Hoe ver een door een nieuwere versie vervangen (superseded) memory in de ranking zakt. Blijft vindbaar, maar onderaan.",
                 "risk": "Te laag: verouderde kennis blijft meekomen naast de nieuwe waarheid. Te hoog: historie is de facto onvindbaar."},
                {"key": "Rerank (cross-encoder)", "value": "aan" if s.RERANK_ENABLED else "uit", "env": "RERANK_ENABLED / RERANK_TOP_K / RERANK_MODEL",
                 "what": f"Een klein lokaal model her-weegt de beste hits nauwkeurig na de eerste selectie (top-{s.RERANK_TOP_K}) voor een scherpere volgorde.",
                 "risk": "Uitzetten: ruwere volgorde maar sneller/lichter. Het model draait lokaal (CPU) en kost wat rekentijd per recall."},
                {"key": "Learning-to-rank", "value": "aan" if s.LTR_ENABLED else "uit", "env": "LTR_ENABLED / LTR_MIN_EXAMPLES",
                 "what": f"Zodra er ≥ {s.LTR_MIN_EXAMPLES} feedback-voorbeelden zijn, leert een model de beste weging zélf en vervangt de handmatige gewichten hierboven.",
                 "risk": "Met weinig/scheve feedback kan een getrainde ranker slechter zijn dan de defaults. Je kunt 'm opnieuw trainen op de Onderhoud-tab."},
            ]},
            {"title": "Verval (decay)", "icon": "⏳", "items": [
                {"key": "Half-life standaard", "value": f"{s.FRESHNESS_HALF_LIFE_DAYS:.0f} dagen", "env": "FRESHNESS_HALF_LIFE_DAYS",
                 "what": "Na hoeveel dagen de versheid-score van een gewone memory halveert. Elke recall ververst een memory (touch-on-read), dus veelgebruikte kennis veroudert niet.",
                 "risk": "Korter: kennis veroudert snel in de ranking. Langer: oude kennis blijft lang bovenaan."},
                {"key": "Half-life stabiel (besluit/conventie)", "value": f"{s.STABLE_HALF_LIFE_DAYS:.0f} dagen", "env": "STABLE_HALF_LIFE_DAYS",
                 "what": "Dezelfde halvering, maar voor besluiten & conventies — die verouderen bewust veel trager.",
                 "risk": "Te kort: afspraken en besluiten zakken te snel weg uit de recall."},
                {"key": "Staleness-review", "value": f"na {s.STALE_REVIEW_DAYS} dagen · min {s.STALE_MIN_USE}× gebruikt", "env": "STALE_REVIEW_DAYS / STALE_MIN_USE",
                 "what": "Wanneer oude-maar-veelgebruikte kennis een 'klopt dit nog?'-review-Pollen krijgt: ouder dan X dagen én minstens Y keer gebruikt.",
                 "risk": "Te streng: veel review-Pollen. Te los: verouderde 'waarheden' worden nooit gecontroleerd."},
            ]},
            {"title": "Write-gate & dedup", "icon": "🚪", "items": [
                {"key": "Dedup: weigeren ≥", "value": s.DEDUP_SIMILARITY_THRESHOLD, "env": "DEDUP_SIMILARITY_THRESHOLD",
                 "what": "Boven deze gelijkenis wordt een nieuwe memory als duplicaat gezien en niet apart opgeslagen (de bestaande wordt 'getoucht').",
                 "risk": "Te laag: verschillende-maar-lijkende memories worden ten onrechte geweigerd. Te hoog: bijna-duplicaten stapelen op."},
                {"key": "Dedup: grijze band ≥", "value": s.DEDUP_REVIEW_THRESHOLD, "env": "DEDUP_REVIEW_THRESHOLD",
                 "what": "Tussen deze waarde en de weiger-drempel ligt de 'grijze band': de memory wordt wél opgeslagen, maar er komt een think-Pollen zodat de Swarm beslist (apart houden / samenvoegen).",
                 "risk": "Te laag: veel grijze-band-Pollen. Te hoog: bijna-duplicaten glippen door zonder review."},
                {"key": "Topic-hergebruik ≥", "value": s.TOPIC_SIMILARITY_THRESHOLD, "env": "TOPIC_SIMILARITY_THRESHOLD",
                 "what": "Boven deze gelijkenis hergebruikt de write-gate een bestaand topic i.p.v. een nieuw aan te maken — voorkomt topic-wildgroei.",
                 "risk": "Te laag: losjes-verwante dingen belanden onder één topic. Te hoog: veel bijna-gelijke topics."},
                {"key": "Min. titel / inhoud", "value": f"{s.MIN_TITLE_LENGTH} / {s.MIN_CONTENT_LENGTH} tekens", "env": "MIN_TITLE_LENGTH / MIN_CONTENT_LENGTH",
                 "what": "Minimale lengte voor titel en inhoud; houdt lege of nietszeggende memories buiten de Hive.",
                 "risk": "Te hoog: legitieme korte weetjes worden geweigerd."},
                {"key": "Max. bijlage", "value": f"{s.ATTACHMENT_MAX_MB} MB", "env": "ATTACHMENT_MAX_MB",
                 "what": "Maximale grootte van één bijlage. Bijlagen leven in Neo4j zelf, dus bewust bescheiden — link liever naar een groot bestand dan het bij te voegen.",
                 "risk": "Te hoog: de graph-store zwelt op, back-ups en geheugengebruik lopen op."},
            ]},
            {"title": "Zwerm-onderhoud", "icon": "🧹", "items": [
                {"key": "Tegenspraak-band", "value": f"{s.CONTRA_MIN_SIM}–{s.DEDUP_SIMILARITY_THRESHOLD} · top {s.CONTRA_TOP}", "env": "CONTRA_MIN_SIM / CONTRA_TOP",
                 "what": "Memory-paren met een gelijkenis in deze band worden als mogelijke tegenspraak aan de Swarm voorgelegd (max N per scan). Onder de band = ongerelateerd; erboven = duplicaat.",
                 "risk": "Ondergrens te laag: veel ruis (losse paren). Te hoog: echte tegenspraken worden gemist. (We zetten 'm bewust op 0,82 om ruis te snijden.)"},
                {"key": "Link-predictie", "value": f"sim ≥ {s.LINKPRED_MIN_SIM} · ≥{s.LINKPRED_MIN_COMMON} gedeeld · top {s.LINKPRED_TOP}", "env": "LINKPRED_MIN_SIM / LINKPRED_MIN_COMMON / LINKPRED_TOP",
                 "what": "Wanneer link-predictie een RELATES-koppeling voorstelt: gelijkenis ≥ X én ≥ Y gedeelde buren, top N kandidaten. Altijd als voorstel (Pollen), nooit automatisch.",
                 "risk": "Losser: meer maar zwakkere koppelvoorstellen. Strenger: echte verbanden worden gemist."},
                {"key": "Cognition (wereld-research)",
                 "value": ("aan" if org_service.get_swarm_settings(session, account).get("cognition_enabled") else "uit")
                          + f" · max {s.COGNITION_MAX_NEW_MEMORIES}/job · {s.COGNITION_MAX_DEPTH} rondes · {s.COGNITION_DAILY_CAP}/dag",
                 "env": "COGNITION_MAX_NEW_MEMORIES / COGNITION_MAX_DEPTH / COGNITION_DAILY_CAP",
                 "what": "Optioneel: bij elke nieuwe memory opent de hive een cognition-Pollen — een zwerm-agent zoekt de onbekende begrippen op (websearch) en schrijft ze als reference-memories terug. Aan/uit per org via POST /manage/swarm/cognition of de MCP-tool hive_set_cognition.",
                 "risk": "Aanzetten kost websearches en tokens. Het budget (memories per job, rondes, dagplafond) begrenst de nieuwsgierigheid hard."},
            ]},
            {"title": "Embeddings", "icon": "🧬", "items": [
                {"key": "Model", "value": s.EMBEDDINGS_MODEL, "env": "EMBEDDINGS_MODEL",
                 "what": "Het lokale model dat tekst naar vectoren omzet — de basis van semantisch zoeken én dedup.",
                 "risk": "Na wisselen is 'Her-embedden' (Onderhoud-tab) verplicht, anders zijn oude en nieuwe vectoren onvergelijkbaar en wordt recall onbetrouwbaar."},
                {"key": "Dimensies", "value": s.EMBEDDINGS_DIM, "env": "EMBEDDINGS_DIM",
                 "what": "De vectorlengte van het embeddingmodel. Moet exact bij het gekozen model passen.",
                 "risk": "Verkeerd getal: de vector-index klopt niet en zoeken faalt. Alleen wijzigen samen met een passend model + reindex."},
                {"key": "Lokaal", "value": "ja" if s.EMBEDDINGS_LOCAL else "extern endpoint", "env": "EMBEDDINGS_LOCAL",
                 "what": "Draait het embeddingmodel in-process (lokaal, geen cloud) of via een extern OpenAI-compatible endpoint.",
                 "risk": "Extern: data verlaat de server en je bent afhankelijk van dat endpoint. Lokaal houdt alles op de server (aanbevolen)."},
            ]},
        ]
    }


@router.post("/swarm/consensus")
def set_consensus(
    body: ConsensusBody,
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    """Set the minimum Swarm size for consensus (org_admin, enforced in the service)."""
    try:
        return org_service.set_consensus_threshold(session, account, body.threshold)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/swarm/cognition")
def set_cognition(
    body: CognitionBody,
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    """Toggle cognition-Pollen — optional world research on newly written memories
    (org_admin, enforced in the service)."""
    try:
        return org_service.set_cognition_enabled(session, account, body.enabled)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/invites")
def create_invite(
    body: InviteCreate,
    account: AuthedAccount = Depends(require_role("org_admin")),
    session: Session = Depends(get_graph),
):
    try:
        return registration_repo.create_invite(
            session, account.org_uid, body.role, body.uses, body.expires_days
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/invites")
def list_invites(
    account: AuthedAccount = Depends(require_role("org_admin")),
    session: Session = Depends(get_graph),
):
    return registration_repo.list_invites(session, account.org_uid)


@router.post("/invites/{code_hash}/revoke")
def revoke_invite(
    code_hash: str,
    account: AuthedAccount = Depends(require_role("org_admin")),
    session: Session = Depends(get_graph),
):
    if not registration_repo.revoke_invite(session, account.org_uid, code_hash):
        raise HTTPException(status_code=404, detail="Invite not found")
    return {"revoked": True}


@router.post("/accounts", response_model=AccountOut)
def create_account(
    body: OrgAccountCreate,
    account: AuthedAccount = Depends(require_role("org_admin")),
    session: Session = Depends(get_graph),
):
    """Create an account in the caller's own org — the org is taken from the session token,
    so an org_admin never needs the operator admin token for this."""
    if body.role not in ROLES:
        raise HTTPException(status_code=400, detail=f"role must be one of: {', '.join(ROLES)}")
    created = tenancy_repo.create_account(
        session, account.org_uid, body.name, body.team_uid, body.role, body.person, body.email
    )
    if created is None:
        raise HTTPException(status_code=404, detail="Team not found")
    return created


@router.get("/accounts")
def list_accounts(
    account: AuthedAccount = Depends(require_role("org_admin")),
    session: Session = Depends(get_graph),
):
    return tenancy_repo.list_accounts(session, account.org_uid)


@router.get("/accounts/{account_uid}/tokens")
def list_tokens(
    account_uid: str,
    account: AuthedAccount = Depends(require_role("org_admin")),
    session: Session = Depends(get_graph),
):
    return tenancy_repo.list_tokens(session, account_uid)


@router.post("/tokens", response_model=TokenOut)
def create_token(
    body: TokenCreate,
    account: AuthedAccount = Depends(require_role("org_admin")),
    session: Session = Depends(get_graph),
):
    token = tenancy_repo.create_token(session, body.account_uid, body.label,
                                      body.expires_days, body.role)
    if token is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return token


@router.post("/tokens/{token_hash}/role")
def set_token_role(
    token_hash: str,
    body: TokenRoleBody,
    account: AuthedAccount = Depends(require_role("org_admin")),
    session: Session = Depends(get_graph),
):
    """Bind a role to a specific token (member/maintainer/org_admin)."""
    if body.role not in registration_repo.VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"role must be one of {registration_repo.VALID_ROLES}")
    if not tenancy_repo.set_token_role(session, token_hash, body.role):
        raise HTTPException(status_code=404, detail="Token not found")
    return {"role": body.role}


@router.post("/tokens/{token_hash}/rotate", response_model=TokenOut)
def rotate_token(
    token_hash: str,
    account: AuthedAccount = Depends(require_role("org_admin")),
    session: Session = Depends(get_graph),
):
    fresh = tenancy_repo.rotate_token(session, token_hash, None)
    if fresh is None:
        raise HTTPException(status_code=404, detail="Token not found")
    return fresh


@router.post("/tokens/{token_hash}/revoke")
def revoke_token(
    token_hash: str,
    account: AuthedAccount = Depends(require_role("org_admin")),
    session: Session = Depends(get_graph),
):
    if not tenancy_repo.revoke_token(session, token_hash):
        raise HTTPException(status_code=404, detail="Token not found")
    return {"revoked": True}


@router.post("/tokens/cleanup")
def cleanup_tokens(
    account: AuthedAccount = Depends(require_role("org_admin")),
    session: Session = Depends(get_graph),
):
    return {"removed": tenancy_repo.cleanup_tokens(session, account.org_uid)}
