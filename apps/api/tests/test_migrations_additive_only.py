"""Migrations written after the live tool's last one may only add.

The v2 tool shares one database, and one migration chain, with the tool that is
already running. That tool keeps reading and inserting against whatever the
chain leaves behind, so a migration that removes, renames or tightens something
it uses breaks production the moment it is applied.

This reads each migration after BASELINE as source and refuses the operations
that would do that. It is static, so it needs no database, and it only looks at
`upgrade()`: a downgrade is allowed to undo what the upgrade added.

What it cannot see: a new unique constraint or index on a table the live tool
inserts into, and any data change made through a computed SQL string. Review
those by hand.
"""

from __future__ import annotations

import ast
import re

from alembic.config import Config
from alembic.script import ScriptDirectory

#: The last migration the running tool already depends on. Everything after it
#: is v2's and is held to the additive-only rule.
BASELINE = "0059_copilot_conversations"

_DESTRUCTIVE_SQL = re.compile(
    r"\bdrop\s+(table|column)\b|\brename\s+(to|column)\b", re.IGNORECASE
)
_ALWAYS_FORBIDDEN = {
    "drop_table": "drops a table the live tool may read",
    "drop_column": "drops a column the live tool may read",
    "rename_table": "renames a table the live tool reads by name",
}


def _op_name(call: ast.Call) -> str | None:
    """`op.add_column(...)` -> "add_column"; anything else -> None."""
    func = call.func
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id == "op":
        return func.attr
    return None


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


def _is_false(node: ast.expr | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is False


def _string_args(call: ast.Call) -> list[str]:
    """Literal SQL passed to op.execute, bare or wrapped in sa.text(...)."""
    out: list[str] = []
    for arg in call.args:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            out.append(arg.value)
        elif isinstance(arg, ast.Call) and arg.args:
            first = arg.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                out.append(first.value)
    return out


def find_violations(source: str) -> list[str]:
    """Why this migration's `upgrade()` is not additive; empty when it is."""
    tree = ast.parse(source)
    upgrade = next(
        (n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "upgrade"), None
    )
    if upgrade is None:
        return []

    found: list[str] = []
    for node in ast.walk(upgrade):
        if not isinstance(node, ast.Call):
            continue
        name = _op_name(node)
        if name is None:
            continue

        if name in _ALWAYS_FORBIDDEN:
            found.append(f"op.{name}: {_ALWAYS_FORBIDDEN[name]}")

        elif name == "alter_column":
            if _keyword(node, "new_column_name") is not None:
                found.append("op.alter_column(new_column_name=...): renames a column the live tool reads")
            if _keyword(node, "type_") is not None:
                found.append("op.alter_column(type_=...): changes the type of a column the live tool uses")
            if _is_false(_keyword(node, "nullable")):
                found.append(
                    "op.alter_column(nullable=False): the live tool may still insert NULL into it"
                )

        elif name == "add_column":
            column = node.args[1] if len(node.args) > 1 else None
            if (
                isinstance(column, ast.Call)
                and _is_false(_keyword(column, "nullable"))
                and _keyword(column, "server_default") is None
            ):
                found.append(
                    "op.add_column: NOT NULL with no server_default, so the live tool's "
                    "inserts, which do not set it, would fail"
                )

        elif name == "execute":
            for sql in _string_args(node):
                if _DESTRUCTIVE_SQL.search(sql):
                    found.append("op.execute: raw SQL that drops or renames")
    return found


def _migrations_after_baseline() -> list[tuple[str, str]]:
    """(revision, source) for every migration after BASELINE, oldest first."""
    scripts = ScriptDirectory.from_config(Config("alembic.ini"))
    out: list[tuple[str, str]] = []
    for script in scripts.iterate_revisions("heads", BASELINE):
        if script.revision == BASELINE:
            continue
        with open(script.path, encoding="utf-8") as handle:
            out.append((script.revision, handle.read()))
    return list(reversed(out))


def test_chain_has_a_single_head():
    """Two heads and `alembic upgrade head` refuses to run on either tool."""
    scripts = ScriptDirectory.from_config(Config("alembic.ini"))
    assert len(scripts.get_heads()) == 1, scripts.get_heads()


def test_baseline_is_in_the_chain():
    scripts = ScriptDirectory.from_config(Config("alembic.ini"))
    assert scripts.get_revision(BASELINE) is not None


def test_migrations_after_baseline_only_add():
    problems = {
        revision: found
        for revision, source in _migrations_after_baseline()
        if (found := find_violations(source))
    }
    assert not problems, problems


# The checker itself, against migrations written for the purpose.


def _upgrade(body: str) -> str:
    indented = "\n".join(f"    {line}" for line in body.strip().splitlines())
    return f"import sqlalchemy as sa\nfrom alembic import op\n\ndef upgrade():\n{indented}\n"


def test_creating_and_adding_is_allowed():
    source = _upgrade(
        """
op.create_table("watchlist_buckets", sa.Column("id", sa.Integer, primary_key=True))
op.add_column("clients", sa.Column("feed_urls", sa.JSON, nullable=True))
op.add_column("clients", sa.Column("flag", sa.Boolean, nullable=False, server_default=sa.false()))
op.create_index("ix_buckets_name", "watchlist_buckets", ["name"])
"""
    )
    assert find_violations(source) == []


def test_dropping_and_renaming_are_refused():
    for body in (
        'op.drop_table("clients")',
        'op.drop_column("clients", "domain")',
        'op.rename_table("clients", "accounts")',
        'op.alter_column("clients", "domain", new_column_name="site")',
    ):
        assert find_violations(_upgrade(body)), body


def test_tightening_a_column_is_refused():
    for body in (
        'op.alter_column("clients", "domain", nullable=False)',
        'op.alter_column("clients", "domain", type_=sa.Integer())',
    ):
        assert find_violations(_upgrade(body)), body


def test_not_null_column_without_default_is_refused():
    source = _upgrade('op.add_column("clients", sa.Column("feed", sa.String, nullable=False))')
    assert find_violations(source)


def test_raw_destructive_sql_is_refused():
    for body in (
        'op.execute("DROP TABLE clients")',
        'op.execute(sa.text("alter table clients drop column domain"))',
        'op.execute("ALTER TABLE clients RENAME COLUMN domain TO site")',
    ):
        assert find_violations(_upgrade(body)), body


def test_downgrade_may_undo_what_upgrade_added():
    source = _upgrade('op.create_table("t", sa.Column("id", sa.Integer))') + (
        '\ndef downgrade():\n    op.drop_table("t")\n'
    )
    assert find_violations(source) == []
