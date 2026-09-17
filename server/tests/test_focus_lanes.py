"""Een focus hoort bij één sessie — en bij niemand anders.

Aanleiding: op de draaiende hive stonden 22 focus-banen, allemaal op het gedeelde
LabX-account, allemaal met een leeg project, en geen ervan met een gebonden sessie.
`get_focus` viel dan terug op baan "" — waar toevallig "KRI-73: TRIM alle gepadde
tekstkolommen" in stond — en spoot die in bij elke agent, in elk lab, bij elke prompt.

Twee dingen die dat oplossen en hier vastliggen:
  1. een beller die zichzelf identificeert en geen eigen baan heeft, krijgt NIETS;
  2. een beller die zich niet identificeert houdt de oude projectbrede focus.

Dit draait zonder Neo4j: de graph-laag wordt nagedaan, want wat hier getoetst wordt
is de BESLISSING welke baan je krijgt, niet of de query loopt.
"""
from types import SimpleNamespace

from src.repository import focus_repo


class _Record(dict):
    def __getitem__(self, k):
        return dict.get(self, k)


class _Result:
    def __init__(self, rec):
        self._rec = rec

    def single(self):
        return self._rec


class _Graph:
    def __init__(self, lane_voor_sessie=None, focus=None):
        self.lane_voor_sessie = lane_voor_sessie
        self.focus = focus

    def run(self, query, **kw):
        if "WHERE $tok IN coalesce(f.sessions, [])" in query:
            return _Result(_Record(lane=self.lane_voor_sessie)
                           if self.lane_voor_sessie is not None else None)
        if self.focus is None:
            return _Result(None)
        return _Result(_Record(**{**self.focus, "lane": kw.get("lane", "")}))


def _account():
    return SimpleNamespace(uid="acc-1", org_uid="org-1")


def test_sessie_zonder_eigen_baan_krijgt_niets():
    """De kern. Hier kwam vroeger de projectbrede focus uit — de taak van een ander."""
    graph = _Graph(lane_voor_sessie=None, focus={"goal": "taak van iemand anders"})
    assert focus_repo.get_focus(graph, _account(), project="", session_id="thread-abc") is None


def test_sessie_met_eigen_baan_krijgt_die_baan():
    graph = _Graph(lane_voor_sessie="kri-60", focus={"goal": "KRI-60 afmaken"})
    uit = focus_repo.get_focus(graph, _account(), project="", session_id="thread-abc")
    assert uit and uit["goal"] == "KRI-60 afmaken"
    assert uit["lane"] == "kri-60"


def test_beller_zonder_sessie_houdt_de_projectbrede_focus():
    """Een client die nooit een sessie meestuurde merkt niets van deze wijziging."""
    graph = _Graph(lane_voor_sessie=None, focus={"goal": "projectbreed"})
    uit = focus_repo.get_focus(graph, _account(), project="", session_id="")
    assert uit and uit["goal"] == "projectbreed"
    assert uit["lane"] == ""


def test_een_naam_wint_altijd():
    """Met een naam bedoel je díé baan, ook als je sessie al ergens aan hangt — zo
    hervat je een baan nadat een /clear je een nieuwe sessie gaf."""
    graph = _Graph(lane_voor_sessie="oude-baan", focus={"goal": "x"})
    uit = focus_repo.get_focus(graph, _account(), project="",
                               session_id="thread-abc", name="Ollama migratie")
    assert uit["lane"] == "ollama-migratie"


def test_sessietoken_is_kort_en_stabiel():
    """LabX stuurt een hele thread-id mee; die moet op dezelfde baan uitkomen als het
    korte token dat een model uit zijn recall-blok overtikt."""
    vol = "73527612-4d4e-4b5d-a5ff-2bcff695d1ec"
    assert focus_repo.session_token(vol) == "73527612"
    assert focus_repo.session_token(focus_repo.session_token(vol)) == "73527612"
