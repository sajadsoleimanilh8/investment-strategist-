"""Everything the app imports is declared.

Two dependencies reached production only because a container build failed on
them — `PyJWT` and `email-validator` were installed by hand during Phase 7 and
never written down. Locally the app worked; from a clean checkout it did not
start. That is the worst shape a bug can take: invisible to everyone who
already has the package.

This walks the imports in `app/` and asserts each third-party one is in
`requirements.txt`. It is a cheaper check than a container build and it fails
in the same second as the mistake.
"""
from __future__ import annotations

import ast
import pathlib
import sys

APP = pathlib.Path(__file__).resolve().parents[2] / "app"
REQUIREMENTS = pathlib.Path(__file__).resolve().parents[2] / "requirements.txt"

#: Import name -> the distribution that provides it, where they differ.
DISTRIBUTION = {
    "jwt": "PyJWT",
    "argon2": "argon2-cffi",
    "dotenv": "python-dotenv",
    "telegram": "python-telegram-bot",
    "apscheduler": "APScheduler",
    "sqlalchemy": "SQLAlchemy",
    "email_validator": "email-validator",
    "pydantic_settings": "pydantic-settings",
}

#: Our own packages. `app/main.py` imports the scheduler job from `scripts`,
#: which is why that directory is copied into the image alongside `app`.
FIRST_PARTY = {"app", "scripts", "tests", "migrations"}

#: Imported transitively rather than declared: `pydantic` pulls it in, and
#: pinning a package we do not import ourselves invites a version fight.
TRANSITIVE = {"starlette", "anyio", "click", "psycopg_binary"}


def declared() -> set[str]:
    names = set()
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        if not line:
            continue
        name = line.split("==")[0].split("[")[0].split(">")[0].split("<")[0]
        names.add(name.strip().lower().replace("_", "-"))
    return names


def top_level_imports() -> set[str]:
    """The root package of every import in `app/`, standard library removed."""
    roots: set[str] = set()
    for path in APP.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                roots.add(node.module.split(".")[0])

    return {
        root for root in roots
        if root not in FIRST_PARTY and root not in sys.stdlib_module_names
        and root not in TRANSITIVE
    }


def test_every_third_party_import_is_declared():
    missing = sorted(
        root for root in top_level_imports()
        if DISTRIBUTION.get(root, root).lower().replace("_", "-") not in declared()
    )

    assert missing == [], (
        f"imported by app/ but absent from requirements.txt: {missing}. "
        "The app will work for anyone who already has them and fail from a "
        "clean checkout."
    )


def test_the_two_that_got_away_are_pinned():
    """A named regression: both of these were found by a failing image build."""
    assert "pyjwt" in declared()
    assert "argon2-cffi" in declared()
    assert "email-validator" in declared()


def test_every_requirement_is_pinned_to_an_exact_version():
    """A range makes a rebuild non-reproducible: the image that passed CI and
    the image that ships can differ by a minor release."""
    unpinned = []
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        if line and "==" not in line:
            unpinned.append(line)

    assert unpinned == [], f"not pinned: {unpinned}"
