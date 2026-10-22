import pytest
from fastapi.testclient import TestClient
from pgmlens_api.main import create_app
from pgmlens_api.settings import Settings
from pgmlens_core.demo import generate_demo


def make_client(**overrides) -> TestClient:
    return TestClient(create_app(Settings(**overrides)))


@pytest.fixture(scope="module")
def client() -> TestClient:
    return make_client()


@pytest.fixture
def empty_client() -> TestClient:
    return make_client(demo=False)


def dataset_json(program_id="extra", name="Extra program") -> dict:
    data = generate_demo(seed=3).model_dump(mode="json")
    data["program"] = {"id": program_id, "name": name, "description": ""}
    return data


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["programs"] == 1


def test_demo_program_is_served_out_of_the_box(client):
    (summary,) = client.get("/api/programs").json()
    assert summary["id"] == "atlas"
    assert summary["health"]["status"] == "off_track"
    assert summary["next_milestone"]["scope_name"] == "Private beta"
    assert 1 <= len(summary["top_risks"]) <= 3
    assert summary["top_risks"][0]["severity"] == "critical"


def test_program_detail_has_everything_the_dashboard_needs(client):
    detail = client.get("/api/programs/atlas").json()
    assert {"summary", "analysis", "issues", "milestones", "projects", "graph"} <= set(detail)
    issues = {i["id"]: i for i in detail["issues"]}
    graph = detail["graph"]
    assert graph["critical_path"] and all(i in issues for i in graph["critical_path"])
    assert any(e["critical"] for e in graph["edges"])
    assert all(e["source"] in issues and e["target"] in issues for e in graph["edges"])
    assert any(i["critical"] for i in issues.values())
    assert {m["name"] for m in detail["milestones"]} >= {"Private beta", "General availability"}


def test_unknown_program_is_404(client):
    assert client.get("/api/programs/nope").status_code == 404
    assert client.get("/api/programs/nope/briefing").status_code == 404


def test_briefing_is_deterministic_by_default_and_warns_when_llm_unconfigured(client):
    body = client.get("/api/programs/atlas/briefing").json()
    assert body["briefing"]["source"] == "deterministic" and body["briefing"]["warnings"] == []
    assert body["markdown"].startswith("# Atlas Platform Migration")
    asked = client.get("/api/programs/atlas/briefing?llm=true").json()
    assert any("No LLM is configured" in w for w in asked["briefing"]["warnings"])


def test_register_replace_and_delete(empty_client):
    c = empty_client
    assert c.get("/api/programs").json() == []
    created = c.post("/api/programs", json=dataset_json())
    assert created.status_code == 201 and created.json()["id"] == "extra"
    assert c.post("/api/programs", json=dataset_json()).status_code == 409
    assert (
        c.post("/api/programs?replace=true", json=dataset_json(name="Renamed")).status_code == 201
    )
    assert c.get("/api/programs/extra").json()["summary"]["name"] == "Renamed"
    assert c.delete("/api/programs/extra").status_code == 204
    assert c.delete("/api/programs/extra").status_code == 404


def test_invalid_datasets_are_rejected_with_422(empty_client):
    bad = dataset_json()
    bad["issues"][0]["project_id"] = "does-not-exist"
    response = empty_client.post("/api/programs", json=bad)
    assert response.status_code == 422
    assert "unknown project_id" in response.text


def test_stateless_analysis_does_not_store(empty_client):
    result = empty_client.post("/api/analyze", json=dataset_json()).json()
    assert result["program"]["id"] == "extra" and result["findings"]
    assert empty_client.get("/api/programs").json() == []


def test_write_endpoints_require_the_token_when_configured():
    c = make_client(demo=False, api_token="s3cret-token")
    assert c.post("/api/programs", json=dataset_json()).status_code == 401
    assert (
        c.post(
            "/api/programs", json=dataset_json(), headers={"Authorization": "Bearer wrong"}
        ).status_code
        == 401
    )
    ok = c.post(
        "/api/programs", json=dataset_json(), headers={"Authorization": "Bearer s3cret-token"}
    )
    assert ok.status_code == 201
    assert c.get("/api/programs").status_code == 200  # reads stay open
    assert c.delete("/api/programs/extra").status_code == 401


def test_rules_and_connectors_are_discoverable(client):
    rules = client.get("/api/rules").json()
    assert "milestone-slip" in {r["id"] for r in rules["rules"]}
    assert {"jira", "gitlab"} <= {c["name"] for c in client.get("/api/connectors").json()}


def test_datasets_are_persisted_and_reloaded(tmp_path):
    first = make_client(demo=False, data_dir=tmp_path)
    assert first.post("/api/programs", json=dataset_json()).status_code == 201
    assert (tmp_path / "extra.json").exists()
    second = make_client(data_dir=tmp_path, demo=False)
    assert [p["id"] for p in second.get("/api/programs").json()] == ["extra"]
    second.delete("/api/programs/extra")
    assert not (tmp_path / "extra.json").exists()


def test_broken_files_in_the_data_dir_do_not_stop_startup(tmp_path):
    (tmp_path / "broken.json").write_text("{not json")
    assert make_client(demo=False, data_dir=tmp_path).get("/api/programs").json() == []


def test_settings_from_env(tmp_path):
    (tmp_path / "x.json").write_text("{}")
    s = Settings.from_env(
        {
            "PGMLENS_DATA_DIR": str(tmp_path),
            "PGMLENS_CORS_ORIGINS": "https://a.test, https://b.test",
        }
    )
    assert s.demo is False  # data present, so no demo unless asked for
    assert s.cors_origins == ("https://a.test", "https://b.test")
    assert Settings.from_env({}).demo is True
    assert Settings.from_env({"PGMLENS_DEMO": "1", "PGMLENS_DATA_DIR": str(tmp_path)}).demo is True


def test_built_dashboard_is_served_without_shadowing_the_api(tmp_path):
    (tmp_path / "index.html").write_text("<h1>dashboard</h1>")
    c = make_client(web_dir=tmp_path)
    assert "dashboard" in c.get("/").text
    assert c.get("/api/health").json()["status"] == "ok"
