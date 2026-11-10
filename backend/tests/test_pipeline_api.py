import json

import pytest
from fastapi.testclient import TestClient

from apex.models.performance import ModelConfig
from apex.pipeline import run as pipeline


@pytest.fixture(scope="module")
def snap(season2026, tmp_path_factory):
    reg = tmp_path_factory.mktemp("reg") / "registry.json"
    sub = season2026.truncated(19)  # clinch happens here
    return pipeline.build_snapshot(sub, n_sims=4000, n_hist=1500, n_cf=800, cfg=ModelConfig(),
                                   registry_path=reg, source="seed", progress=lambda *_: None)


def test_champion_state_is_exact(snap):
    assert snap["status"]["clinched"]
    assert snap["status"]["champion"] == "drv_antonelli"
    t = snap["forecast"]["title"]
    assert t["drv_antonelli"] == 1.0 and all(v == 0.0 for d, v in t.items() if d != "drv_antonelli")


def test_history_is_leakage_free_and_sums_to_one(snap):
    assert [h["round"] for h in snap["history"]] == list(range(1, 20))
    for h in snap["history"]:
        assert abs(sum(h["title"].values()) - 1) < 1e-4  # stored rounded to 6 dp
        for d, s in h["status"].items():
            if s == "ELIMINATED":
                assert h["title"].get(d, 0) == 0


def test_explanations_grounded(snap):
    ex = snap["history"][10]["explanations"]
    assert ex and all("Title probability" in v["text"] for v in ex.values())
    for v in ex.values():
        assert v["delta"] == pytest.approx(v["points_effect"] + v["form_effect"], abs=1e-9)


def test_publish_versioned_and_api(snap, tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "SNAP_DIR", tmp_path)
    p1 = pipeline.publish(snap, tmp_path)
    assert (tmp_path / "latest.json").exists() and p1.exists()
    from apex.api import main as api
    monkeypatch.setattr(api, "SNAP_DIR", tmp_path)
    c = TestClient(api.app)
    assert c.get("/api/health").json()["last_round"] == 19
    assert c.get("/api/drivers/drv_antonelli").json()["title"] == 1.0
    base = 14
    nxt = json.loads((tmp_path / "latest.json").read_text())["sim_inputs"][str(base)]["events"][0]
    r = c.post("/api/scenario", json={"base_round": base, "n_sims": 2000,
                                       "conditions": [{"round": nxt["round"], "kind": nxt["kind"],
                                                       "positions": {"drv_russell": 1}}]})
    assert r.status_code == 200 and r.json()["hypothetical"] is True
    bad = c.post("/api/scenario", json={"base_round": base, "conditions": [
        {"round": nxt["round"], "kind": nxt["kind"], "positions": {"drv_russell": 1, "drv_hamilton": 1}}]})
    assert bad.status_code == 400
