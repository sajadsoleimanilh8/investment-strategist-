"""The architectural rule, enforced by tests rather than by good intentions.

docs/ARCHITECTURE.md: free text -> intent.parse -> structured params ->
deterministic engine -> verified numbers -> LLM prose -> safety -> user.

The LLM never does arithmetic, so the simulators must not be able to reach one
and the parser must not either. Going the other way, the explanation layer must
not reach the database or the engine: it is handed a finished context. These
tests enforce both directions.
"""
import ast
import pathlib

import pytest

APP = pathlib.Path(__file__).resolve().parents[2] / "app"
SIMULATION_MODULES = ("simulation_engine", "time_machine", "decision_simulator")
LLM_MODULES = ("httpx", "requests", "openai", "anthropic", "ollama")


def imported_modules(path: pathlib.Path) -> set[str]:
    """Every module a file imports.

    `from app.repositories import chat as chat_repo` counts as importing both
    `app.repositories` and `app.repositories.chat` — the submodule is the thing
    the rules care about, and the alias must not hide it.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


@pytest.mark.parametrize("module", SIMULATION_MODULES)
def test_simulators_import_nothing_from_the_ai_layer(module):
    imports = imported_modules(APP / "services" / f"{module}.py")
    assert not [name for name in imports if name.startswith("app.ai")]


@pytest.mark.parametrize("module", SIMULATION_MODULES)
def test_simulators_import_no_llm_client(module):
    imports = imported_modules(APP / "services" / f"{module}.py")
    assert not [name for name in imports if name.split(".")[0] in LLM_MODULES]


@pytest.mark.parametrize("module", SIMULATION_MODULES)
def test_simulators_stay_persistence_free(module):
    imports = imported_modules(APP / "services" / f"{module}.py")
    forbidden = [
        name for name in imports
        if name.startswith(("app.repositories", "app.db", "app.models", "sqlalchemy"))
    ]
    assert forbidden == [], f"{module} reached into persistence: {forbidden}"


def test_the_intent_parser_reaches_no_model_in_phase_three():
    imports = imported_modules(APP / "ai" / "intent.py")

    assert not [name for name in imports if name.split(".")[0] in LLM_MODULES]
    assert not [name for name in imports if name.startswith(("app.ai.local", "app.ai.remote"))]


def test_running_a_simulation_loads_no_ai_module():
    """The proof that matters: exercise the engine and check `sys.modules`."""
    import sys

    for name in [n for n in sys.modules if n.startswith("app.ai")]:
        del sys.modules[name]

    from app.schemas.finance import ExpenseBreakdown, FinancialProfileIn, GoalIn
    from app.schemas.simulation import WhatIfParams
    from app.services.decision_simulator import evaluate_purchase
    from app.services.financial_twin import build_twin
    from app.services.simulation_engine import run_what_if
    from app.services.time_machine import compare_paths

    twin = build_twin(
        FinancialProfileIn(monthly_income=30_000_000,
                           expenses=ExpenseBreakdown(housing=8_000_000),
                           current_savings=45_000_000, emergency_fund=30_000_000),
        [GoalIn(name="Laptop", target_amount=60_000_000, current_amount=20_000_000)],
    )
    run_what_if(twin, WhatIfParams(monthly_savings_delta=5_000_000))
    compare_paths(twin)
    evaluate_purchase(twin, 40_000_000)

    assert [n for n in sys.modules if n.startswith("app.ai")] == []


# --- phase 5: the explanation layer stays on its own side ----------------

AI_MODULES = ("synthesizer", "safety", "rendering", "prompts")


@pytest.mark.parametrize("module", AI_MODULES)
def test_the_ai_layer_is_persistence_free(module):
    """`app/ai` never touches the database — routes/ai.py owns every write."""
    imports = imported_modules(APP / "ai" / f"{module}.py")
    forbidden = [
        name for name in imports
        if name.startswith(("app.repositories", "app.db", "app.models", "sqlalchemy"))
    ]
    assert forbidden == [], f"{module} reached into persistence: {forbidden}"


@pytest.mark.parametrize("module", ("synthesizer", "safety", "rendering"))
def test_the_ai_layer_never_calls_the_engine(module):
    """It explains a finished context; it must not recompute anything."""
    imports = imported_modules(APP / "ai" / f"{module}.py")
    assert not [name for name in imports if name.startswith("app.services")]


def test_safety_reaches_no_network():
    imports = imported_modules(APP / "ai" / "safety.py")
    assert not [name for name in imports if name.split(".")[0] in LLM_MODULES]


def test_only_the_ask_pipeline_imports_the_synthesizer():
    """One entry point into the model, so one place safety can be bypassed.

    Both delivery surfaces (HTTP route and Telegram bot) go through
    `app/api/ask.py`; neither may reach the synthesizer on its own.
    """
    importers = [
        path.relative_to(APP).as_posix()
        for path in APP.rglob("*.py")
        if path.name != "synthesizer.py"
        and "app.ai.synthesizer" in imported_modules(path)
    ]

    assert importers == ["api/ask.py"], f"unexpected synthesizer importers: {importers}"


def test_every_synthesizer_return_goes_through_safety():
    """Static check: `explain` returns only via the `_finish` wrapper."""
    source = (APP / "ai" / "synthesizer.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    explain = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "explain"
    )

    returns = [node for node in ast.walk(explain) if isinstance(node, ast.Return)]
    assert returns, "explain must return something"
    for node in returns:
        assert isinstance(node.value, ast.Call), "every return must call the safety wrapper"
        assert node.value.func.id == "_finish"

    finish = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_finish"
    )
    calls = [
        n.func.attr for n in ast.walk(finish)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
    ]
    assert "enforce" in calls, "_finish must call safety.enforce"


def test_every_answer_carries_a_safety_report():
    """The runtime proof: exercise all three tiers and check each result."""
    from app.ai import synthesizer
    from app.ai.local_llm import FakeLocalProvider

    context = {"financial_health_score": 62.3, "monthly_savings": 10_500_000.0}
    results = [synthesizer.explain("q", context)]

    FakeLocalProvider.unavailable = True
    try:
        results.append(synthesizer.explain("q", context))
    finally:
        FakeLocalProvider.unavailable = False

    for result in results:
        assert result["safety_report"], "no answer may skip the safety layer"
        assert result["text"].strip()
        assert result["used_context"] == context


def test_the_ask_pipeline_is_the_only_place_the_transcript_is_written():
    writers = [
        path.relative_to(APP).as_posix()
        for path in APP.rglob("*.py")
        if "app.repositories.chat" in imported_modules(path)
        and path.name != "__init__.py"          # the package re-export is not a writer
    ]
    assert writers == ["api/ask.py"], f"unexpected transcript writers: {writers}"


# --- phase 6: the bot is a delivery layer, nothing more ------------------

BOT = APP / "bot"


def test_the_bot_never_reaches_persistence_models_directly():
    """Handlers read and write through repositories, never raw ORM queries."""
    offenders = {}
    for path in BOT.rglob("*.py"):
        forbidden = [
            name for name in imported_modules(path)
            if name.startswith("sqlalchemy.orm.Query") or name == "app.db.base"
        ]
        if forbidden:
            offenders[path.name] = forbidden
    assert offenders == {}, offenders


def test_view_builders_import_no_telegram():
    """views.py is pure data-in/string-out, which is what makes it testable."""
    imports = imported_modules(BOT / "views.py")
    assert not [name for name in imports if name.split(".")[0] == "telegram"]


def test_the_bot_reaches_the_model_only_through_the_ask_pipeline():
    """No handler may call a synthesizer or an LLM client itself."""
    for path in BOT.rglob("*.py"):
        imports = imported_modules(path)
        assert not [n for n in imports if n.split(".")[0] in LLM_MODULES], path.name
        assert "app.ai.synthesizer" not in imports, path.name
        assert not [n for n in imports if n.startswith(("app.ai.local", "app.ai.remote"))]


def test_nothing_below_delivery_imports_the_bot():
    """`app/bot` is a leaf: services, ai, market and repositories never see it."""
    importers = []
    for package in ("services", "ai", "market", "repositories", "models", "core"):
        for path in (APP / package).rglob("*.py"):
            if [n for n in imported_modules(path) if n.startswith("app.bot")]:
                importers.append(path.relative_to(APP).as_posix())
    assert importers == [], f"the bot leaked downwards: {importers}"
