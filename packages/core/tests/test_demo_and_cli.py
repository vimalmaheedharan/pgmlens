import json

import pytest
from pgmlens_core import Dataset, analyze
from pgmlens_core.cli import main
from pgmlens_core.demo import generate_demo


@pytest.fixture(scope="module")
def demo() -> Dataset:
    return generate_demo()


def test_demo_is_deterministic_for_a_seed():
    assert generate_demo(seed=1).model_dump_json() == generate_demo(seed=1).model_dump_json()
    assert generate_demo(seed=1).model_dump_json() != generate_demo(seed=2).model_dump_json()


def test_demo_survives_a_json_round_trip(demo):
    assert Dataset.model_validate_json(demo.model_dump_json()) == demo


def test_demo_tells_the_intended_story(demo):
    result = analyze(demo)
    rules = {f.rule_id for f in result.findings}
    assert {
        "milestone-slip", "stale-blocker", "blocked-chain", "unassigned-critical",
        "overloaded-owner", "scope-creep",
    } <= rules  # fmt: skip
    assert result.health.status == "off_track"
    assert any(f.severity.value == "critical" for f in result.findings)


def test_analysis_is_deterministic(demo):
    assert analyze(demo).model_dump_json() == analyze(demo).model_dump_json()


def test_demo_has_no_dependency_cycles(demo):
    assert analyze(demo).graph.cycles == []


@pytest.fixture
def demo_file(tmp_path, demo):
    path = tmp_path / "demo.json"
    path.write_text(demo.model_dump_json())
    return path


def test_cli_analyze_text(demo_file, capsys):
    assert main(["analyze", str(demo_file)]) == 0
    out = capsys.readouterr().out
    assert "Atlas Platform Migration" in out
    assert "RISKS" in out and "CRITICAL PATH" in out


def test_cli_analyze_json_is_valid_json(demo_file, capsys):
    assert main(["analyze", str(demo_file), "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["health"]["status"] == "off_track"


def test_cli_fail_on_gates_by_severity(demo_file):
    assert main(["analyze", str(demo_file), "--fail-on", "critical"]) == 1
    assert main(["analyze", str(demo_file)]) == 0


def test_cli_validate_and_bad_input(demo_file, tmp_path, capsys):
    assert main(["validate", str(demo_file)]) == 0
    bad = tmp_path / "bad.json"
    bad.write_text('{"program": {"id": "x"}}')
    assert main(["validate", str(bad)]) == 2
    assert main(["validate", str(tmp_path / "missing.json")]) == 2


def test_cli_custom_rules_file(demo_file, tmp_path, capsys):
    rules = tmp_path / "rules.yaml"
    rules.write_text(
        "extends: default\nrules:\n  - {id: scope-creep, type: scope_creep, title: x, enabled: false}\n"
    )
    assert main(["analyze", str(demo_file), "--format", "json", "--rules", str(rules)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert "scope-creep" not in {f["rule_id"] for f in payload["findings"]}


def test_cli_demo_and_schema(tmp_path, capsys):
    out = tmp_path / "d.json"
    assert main(["demo", "--out", str(out)]) == 0
    Dataset.model_validate_json(out.read_text())
    assert main(["schema"]) == 0
    assert "properties" in json.loads(capsys.readouterr().out.split("\n", 1)[1])
