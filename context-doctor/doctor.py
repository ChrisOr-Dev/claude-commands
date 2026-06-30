"""Context Doctor — ``doctor`` console entry point (warehouse CLI).

This is the packaged CLI surface (ADR-0010). It exposes the warehouse
subcommands as an argparse skeleton:

    doctor ingest
    doctor report <name> [--params…]
    doctor reports
    doctor schema

with global ``--source <dir>`` / ``--db <path>`` overrides. The actual
ingest/report/schema LOGIC is implemented in later slices; here those
subcommands are stubbed with a clear "not yet implemented" message and a
non-zero exit.

The one piece of real behavior in this slice is the **duckdb degrade gate**
(``require_duckdb``): every warehouse subcommand first checks that the Python
``duckdb`` module can be imported and, if not, prints a one-line install hint
to stderr and exits non-zero — never silently. The stdlib-only ``analyze.sh``
summary path is unaffected and remains the graceful-degrade fallback.
"""

import argparse
import json
import os
import sys

# Slice number that will implement the actual logic of each subcommand. Used in
# the "not yet implemented" stubs so the message points at the right work.
_SLICE_FOR = {
    "report": 5,
    "reports": 5,
    "schema": 3,
}

# One-line, copy-pasteable hint shown when the duckdb module is unavailable.
DUCKDB_INSTALL_HINT = (
    "context-doctor: the 'duckdb' Python module is required for warehouse "
    "commands (ingest/report/reports/schema). Install the packaged tool with "
    "'uv tool install <context-doctor dir>', or 'pip install duckdb'. The "
    "stdlib summary still works: bash analyze.sh [days]."
)


class DuckDBUnavailable(RuntimeError):
    """Raised by :func:`require_duckdb` when the duckdb module can't be imported."""


def require_duckdb():
    """Return the imported ``duckdb`` module, or raise :class:`DuckDBUnavailable`.

    Factored out so tests can force the failure path two ways:

    * set ``DOCTOR_FORCE_NO_DUCKDB=1`` in the environment (no monkeypatching
      needed — simulates the module being absent), or
    * monkeypatch this function directly.

    This is the single chokepoint every warehouse subcommand goes through, so
    the degrade behavior is defined in exactly one place.
    """
    if os.environ.get("DOCTOR_FORCE_NO_DUCKDB") == "1":
        raise DuckDBUnavailable("duckdb import forced off via DOCTOR_FORCE_NO_DUCKDB")
    try:
        import duckdb  # noqa: F401  (presence check; real use lands in later slices)
    except ImportError as exc:  # pragma: no cover - exercised via the env-var path
        raise DuckDBUnavailable(str(exc)) from exc
    return duckdb


def _gate_or_exit():
    """Enforce the duckdb gate for a warehouse subcommand.

    On success returns the duckdb module. On failure prints the one-line install
    hint to stderr and raises ``SystemExit`` with a non-zero code — so the
    command never proceeds silently without the dependency.
    """
    try:
        return require_duckdb()
    except DuckDBUnavailable:
        print(DUCKDB_INSTALL_HINT, file=sys.stderr)
        raise SystemExit(3)


def _not_implemented(name):
    """Stub a warehouse subcommand: passes the gate, then exits non-zero."""
    _gate_or_exit()
    slice_n = _SLICE_FOR.get(name, "a later slice")
    print(
        "context-doctor: '%s' is not yet implemented (slice %s)." % (name, slice_n),
        file=sys.stderr,
    )
    return 1


def _do_ingest(args):
    """Run the real warehouse ingest: gate, connect, bootstrap, ingest, summary.

    A schema-version mismatch drops & rebuilds the store (ADR-0005); on a fresh
    or rebuilt store the ingest then backfills from scratch — both paths funnel
    through one ``warehouse.ingest`` call here."""
    duckdb_mod = _gate_or_exit()
    import warehouse

    conn = warehouse.connect(args.db, duckdb_mod=duckdb_mod)
    try:
        warehouse.bootstrap(conn)
        summary = warehouse.ingest(conn, source_dir=args.source)
    finally:
        conn.close()
    print(json.dumps(summary, indent=2))
    return 0


def _add_global_overrides(parser):
    """Attach the ADR-0010 global overrides to a subcommand parser.

    ``--source`` points ingest/report at a *frozen* copy of the logs instead of
    ``~/.claude/projects``; ``--db`` selects a throwaway store. Both are
    placeholders in this slice (parsed, not yet consumed) so the surface is
    stable for the slices that wire them in.
    """
    parser.add_argument(
        "--source", metavar="DIR", default=None,
        help="ingest/report from this projects dir instead of ~/.claude/projects",
    )
    parser.add_argument(
        "--db", metavar="PATH", default=None,
        help="use this DuckDB store instead of the default per-user location",
    )


def build_parser():
    parser = argparse.ArgumentParser(
        prog="doctor",
        description="Context Doctor — Claude Code token-usage metrics warehouse.",
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    p_ingest = sub.add_parser(
        "ingest", help="ingest session logs into the warehouse (manual refresh)",
    )
    _add_global_overrides(p_ingest)

    p_report = sub.add_parser(
        "report", help="run a catalog report by name",
    )
    p_report.add_argument("name", nargs="?", help="report name (see 'doctor reports')")
    p_report.add_argument(
        "--sql", action="store_true", help="print the underlying SQL instead of running it",
    )
    _add_global_overrides(p_report)

    p_reports = sub.add_parser("reports", help="list the report catalog")
    _add_global_overrides(p_reports)

    p_schema = sub.add_parser(
        "schema", help="print the canonical schema.sql DDL + schema_version",
    )
    p_schema.add_argument(
        "--live", action="store_true", help="dump an existing store's live DDL",
    )
    _add_global_overrides(p_schema)

    return parser


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help(sys.stderr)
        return 2

    # `ingest` is wired (slice 3); the rest stay gated stubs (later slices).
    if args.command == "ingest":
        return _do_ingest(args)
    return _not_implemented(args.command)


if __name__ == "__main__":
    sys.exit(main())
