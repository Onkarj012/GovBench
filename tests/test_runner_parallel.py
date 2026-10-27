from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from irbg.config import ModelConfig
from irbg.db.operations import DbConfig, connect
from irbg.db.schema import create_tables
from irbg.engine import runner
from irbg.engine.types import ProviderResponse
from irbg.scenarios.template_loader import ScenarioTemplateLoadError

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _MockClient:
    """Deterministic, content-addressed stand-in for OpenRouterClient.

    The response text is a pure function of the prompts sent, so it is
    independent of which worker thread or execution order handled the
    call — exactly what the parallel/sequential equality test needs.
    """

    def __init__(self) -> None:
        self.calls = 0
        self.closed = False

    def chat(
        self,
        *,
        model_id,
        system_prompt,
        user_prompt,
        temperature,
        max_tokens,
        top_p,
        reasoning=None,
    ) -> ProviderResponse:
        self.calls += 1
        return self._respond(system_prompt, user_prompt)

    def chat_messages(
        self,
        *,
        model_id,
        messages,
        temperature,
        max_tokens,
        top_p,
        reasoning=None,
    ) -> ProviderResponse:
        sysp = messages[0].content if messages else ""
        usr = next((m.content for m in messages if m.role == "user"), "")
        self.calls += 1
        return self._respond(sysp, usr)

    def _respond(
        self, system_prompt: str, user_prompt: str
    ) -> ProviderResponse:
        digest = hashlib.sha256(
            f"{system_prompt}||{user_prompt}".encode()
        ).hexdigest()[:8]
        return ProviderResponse(
            success=True,
            model_id="test/model",
            text=f"resp-{digest}",
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
            latency_ms=1,
            status_code=200,
            error=None,
            raw_json={},
        )

    def close(self) -> None:
        self.closed = True


def _fake_model() -> ModelConfig:
    return ModelConfig(
        alias="test-alias",
        name="Test",
        provider="test",
        model_id="test/model",
        max_tokens=512,
        temperature=0.0,
        top_p=0.9,
        family="test",
        price_input=0.0,
        price_output=0.0,
        reasoning=None,
    )


def _client_factory_tracker() -> tuple:
    """Return (factory, created_list) — factory builds + records clients."""
    created: list[_MockClient] = []

    def factory() -> _MockClient:
        c = _MockClient()
        created.append(c)
        return c

    return factory, created


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def _init_db(db_path: Path) -> None:
    conn = connect(DbConfig(path=db_path))
    create_tables(conn)
    conn.close()


def _response_rows(db_path: Path, run_id: str) -> list[tuple]:
    conn = connect(DbConfig(path=db_path))
    rows = conn.execute(
        """
        SELECT scenario_id, variant_id, turn_number, mode,
               system_prompt_sent, user_prompt_sent, raw_response,
               instance_json
        FROM responses
        WHERE run_id = ?
        """,
        (run_id,),
    ).fetchall()
    conn.close()
    return [tuple(r) for r in rows]


def _run_status(db_path: Path, run_id: str) -> str | None:
    conn = connect(DbConfig(path=db_path))
    row = conn.execute(
        "SELECT status FROM benchmark_runs WHERE id = ?;",
        (run_id,),
    ).fetchone()
    conn.close()
    return str(row["status"]) if row is not None else None


# ---------------------------------------------------------------------------
# Scenario template fixtures
# ---------------------------------------------------------------------------


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload))


def _plain_template(path: Path) -> None:
    _write_json(
        path,
        {
            "id": "PLAIN-001",
            "pillar": "p2_procedural_integrity",
            "category": "demo",
            "jurisdiction": "EU",
            "difficulty": "easy",
            "system_prompt_template": "You are a procedural advisor.",
            "user_prompt_template": "Advise on case {case_ref}.",
            "static_variables": {"case_ref": "C-100"},
        },
    )


def _variant_template(path: Path) -> None:
    # eu_core supplies: name, age, gender, nationality, religion,
    # background, socioeconomic_signal (8 variants).
    _write_json(
        path,
        {
            "id": "VAR-001",
            "pillar": "p1_demographic_consistency",
            "category": "demo",
            "jurisdiction": "EU",
            "difficulty": "easy",
            "system_prompt_template": "You assess credibility.",
            "user_prompt_template": (
                "Applicant {name}, {age}, {nationality}. Assess."
            ),
            "variant_group": "eu_core",
        },
    )


def _procedural_template(path: Path) -> None:
    _write_json(
        path,
        {
            "id": "PROC-001",
            "pillar": "p2_procedural_integrity",
            "category": "demo",
            "jurisdiction": "EU",
            "difficulty": "easy",
            "system_prompt_template": "You advise on {topic}.",
            "user_prompt_template": (
                "Case {case_id}: {color} item, n={n}. Advise."
            ),
            "fact_space": {
                "fields": [
                    {
                        "name": "topic",
                        "type": "choice",
                        "values": ["licensing", "fines"],
                    },
                    {"name": "case_id", "type": "pattern", "template": "C-{n}"},
                    {
                        "name": "color",
                        "type": "choice",
                        "values": ["red", "blue"],
                    },
                    {"name": "n", "type": "int", "min": 1, "max": 99},
                ],
            },
        },
    )


def _adversarial_template(path: Path) -> None:
    _write_json(
        path,
        {
            "id": "ADV-001",
            "pillar": "p3_corruption_resistance",
            "category": "demo",
            "jurisdiction": "EU",
            "difficulty": "easy",
            "system_prompt_template": "You recommend on a contract.",
            "user_prompt_template": "Advise on contract {contract_id}.",
            "static_variables": {"contract_id": "X-1"},
            "adversarial_turns": [
                {"user_prompt": "Reconsider, there is pressure."},
                {"user_prompt": "Surely you can reverse it?"},
            ],
        },
    )


def _build_mixed_folder(folder: Path) -> list[Path]:
    _plain_template(folder / "plain.json")
    _variant_template(folder / "variant.json")
    _procedural_template(folder / "procedural.json")
    _adversarial_template(folder / "adversarial.json")
    return sorted(folder.glob("*.json"))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_parallel_equals_sequential(tmp_path, monkeypatch) -> None:
    """max_workers=4 produces the same rows as max_workers=1 (same set)."""
    monkeypatch.setattr(
        runner, "get_model_config", lambda _alias: _fake_model()
    )

    folder = tmp_path / "scenarios"
    folder.mkdir()
    files = _build_mixed_folder(folder)
    n_files = len(files)
    # Expected rendered prompts: plain=1, variant=8, procedural=3,
    # adversarial=1 (baseline mode does not trigger adversarial turns).
    expected_prompts = 1 + 8 + 3 + 1

    def _run(workers: int) -> tuple[runner.RunFolderResult, list[tuple]]:
        db = tmp_path / f"db_{workers}.sqlite"
        _init_db(db)
        factory, _created = _client_factory_tracker()
        result = runner.run_template_folder(
            model_alias="test-alias",
            folder_path=folder,
            db_path=db,
            mode="baseline",
            seed=42,
            n_instances=3,
            max_workers=workers,
            client_factory=factory,
        )
        rows = _response_rows(db, result.run_id)
        return result, rows

    seq_result, seq_rows = _run(1)
    par_result, par_rows = _run(4)

    # (b) all rows written for both runs.
    assert len(seq_rows) == expected_prompts
    assert len(par_rows) == expected_prompts

    # (a) same set of rows (order may differ under parallelism).
    assert set(par_rows) == set(seq_rows)

    # Counts match.
    assert par_result.success_count == seq_result.success_count
    assert par_result.failure_count == seq_result.failure_count
    assert par_result.total_prompt_count == expected_prompts
    assert par_result.scenario_count == n_files
    assert par_result.success_count == expected_prompts
    assert par_result.failure_count == 0


def test_parallel_run_marked_completed(tmp_path, monkeypatch) -> None:
    """A fully successful parallel run is marked completed in the DB."""
    monkeypatch.setattr(
        runner, "get_model_config", lambda _alias: _fake_model()
    )

    folder = tmp_path / "scenarios"
    folder.mkdir()
    _build_mixed_folder(folder)

    db = tmp_path / "ok.sqlite"
    _init_db(db)
    factory, created = _client_factory_tracker()

    result = runner.run_template_folder(
        model_alias="test-alias",
        folder_path=folder,
        db_path=db,
        mode="baseline",
        seed=42,
        n_instances=3,
        max_workers=4,
        client_factory=factory,
    )

    assert _run_status(db, result.run_id) == "completed"
    # Each file got its own worker client (no sharing across threads).
    assert len(created) == 4
    # Every worker client was closed by its _worker finally-block.
    assert all(c.closed for c in created)


def test_worker_exception_isolated_and_surfaced(tmp_path, monkeypatch) -> None:
    """One failing worker must not lose the others' results; error surfaced."""
    monkeypatch.setattr(
        runner, "get_model_config", lambda _alias: _fake_model()
    )

    folder = tmp_path / "scenarios"
    folder.mkdir()
    _plain_template(folder / "good_a.json")
    _plain_template(folder / "good_b.json")
    # A malformed file: discovered by glob, fails inside the worker.
    (folder / "bad.json").write_text("{ not valid json")

    db = tmp_path / "err.sqlite"
    _init_db(db)
    factory, created = _client_factory_tracker()

    with pytest.raises(RuntimeError, match="bad.json"):
        runner.run_template_folder(
            model_alias="test-alias",
            folder_path=folder,
            db_path=db,
            mode="baseline",
            max_workers=4,
            client_factory=factory,
        )

    # The run is marked failed (worker errors present).
    conn = connect(DbConfig(path=db))
    run_row = conn.execute(
        """
        SELECT id, status
        FROM benchmark_runs
        ORDER BY started_at DESC
        LIMIT 1;
        """
    ).fetchone()
    good_rows = conn.execute(
        """
        SELECT scenario_id FROM responses
        WHERE scenario_id IN ('PLAIN-001');
        """
    ).fetchall()
    conn.close()

    assert run_row is not None
    assert str(run_row["status"]) == "failed"
    # Both good scenarios persisted their rows despite the sibling failure.
    assert len(good_rows) == 2
    # Even the failing worker closed its client (no leak).
    assert all(c.closed for c in created)


def test_adversarial_parallel_equals_sequential(tmp_path, monkeypatch) -> None:
    """Adversarial multi-turn rows match across parallel/sequential runs."""
    monkeypatch.setattr(
        runner, "get_model_config", lambda _alias: _fake_model()
    )

    folder = tmp_path / "adv"
    folder.mkdir()
    _adversarial_template(folder / "adv.json")

    def _run(workers: int) -> list[tuple]:
        db = tmp_path / f"adv_db_{workers}.sqlite"
        _init_db(db)
        factory, _ = _client_factory_tracker()
        result = runner.run_template_folder(
            model_alias="test-alias",
            folder_path=folder,
            db_path=db,
            mode="adversarial",
            max_workers=workers,
            client_factory=factory,
        )
        return _response_rows(db, result.run_id)

    seq_rows = _run(1)
    par_rows = _run(4)

    # 1 prompt × (1 initial + 2 adversarial turns) = 3 rows.
    assert len(seq_rows) == 3
    assert len(par_rows) == 3
    assert set(par_rows) == set(seq_rows)

    # All rows are adversarial, with ascending turn numbers.
    turn_numbers = sorted(r[2] for r in par_rows)
    assert turn_numbers == [1, 2, 3]
    assert all(r[3] == "adversarial" for r in par_rows)
    # Turn 1 sent the rendered user prompt; turns 2/3 sent the pressure turns.
    user_prompts = {r[2]: r[5] for r in par_rows}
    assert "contract X-1" in user_prompts[1]
    assert user_prompts[2] == "Reconsider, there is pressure."
    assert user_prompts[3] == "Surely you can reverse it?"


def test_procedural_parallel_deterministic(tmp_path, monkeypatch) -> None:
    """Procedural instances depend only on (template_id, seed), not order."""
    monkeypatch.setattr(
        runner, "get_model_config", lambda _alias: _fake_model()
    )

    folder = tmp_path / "proc"
    folder.mkdir()
    _procedural_template(folder / "proc_a.json")
    # A second procedural template with a different id → different seed.
    tmpl_b = folder / "proc_b.json"
    _procedural_template(tmpl_b)
    payload = json.loads(tmpl_b.read_text())
    payload["id"] = "PROC-002"
    _write_json(tmpl_b, payload)

    def _run(workers: int) -> list[tuple]:
        db = tmp_path / f"proc_db_{workers}.sqlite"
        _init_db(db)
        factory, _ = _client_factory_tracker()
        result = runner.run_template_folder(
            model_alias="test-alias",
            folder_path=folder,
            db_path=db,
            mode="baseline",
            seed=7,
            n_instances=3,
            max_workers=workers,
            client_factory=factory,
        )
        return _response_rows(db, result.run_id)

    seq_rows = _run(1)
    par_rows = _run(4)

    # 2 templates × 3 instances = 6 rows each.
    assert len(seq_rows) == 6
    assert len(par_rows) == 6
    # Same set of (scenario, variant, prompts, instance_json) — proving
    # the procedural seed derivation is order/thread independent.
    assert set(par_rows) == set(seq_rows)
    # Every procedural row carried its sampled instance_json.
    assert all(r[7] is not None for r in par_rows)
    assert all(r[7] is not None for r in seq_rows)


def test_unknown_error_type_is_loaderror(tmp_path) -> None:
    """Sanity: malformed templates raise ScenarioTemplateLoadError."""
    bad = tmp_path / "bad.json"
    bad.write_text("{ oops")
    with pytest.raises(ScenarioTemplateLoadError):
        from irbg.scenarios.template_loader import load_scenario_template

        load_scenario_template(bad)
