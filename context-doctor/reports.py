"""Context Doctor — report catalog engine (the primary read interface).

ADR-0006 (hybrid catalog): each named report is a ``.sql`` template plus a typed
param schema declared in ``reports/catalog.toml``. This module loads that
manifest, validates + binds params, and executes the bound SQL against a
warehouse connection, returning JSON-able results.

Param kinds
-----------
* ``int`` / ``float`` / ``text`` — bound via DuckDB ``$name`` placeholders
  (never string-interpolated, so injection-safe).
* ``int_list`` — accepts a ``"50k,200k,400k"`` shorthand expanded to
  ``[50000, 200000, 400000]`` and bound as a list via ``$name``.
* ``ident`` — a column name, validated against the manifest's ``choices`` and
  only then substituted into a ``{name}`` token in the template. Raw user text
  never reaches a ``{...}`` slot.

Loader safety (all reject with a clear, non-traceback error + non-zero exit at
the CLI layer):
  (a) any ``{token}`` in a template not declared ``ident`` in the manifest,
  (b) an ``int_list`` element that is not numeric after shorthand expansion,
  (c) an ``ident`` value not in ``choices``,
  (d) an unknown param name,
  (e) a malformed ``int`` / ``float``.

pytz note: any timestamp a report returns to Python is ``CAST(... AS VARCHAR)``
in the SQL — fetching a ``TIMESTAMPTZ`` natively raises ``ModuleNotFoundError:
pytz`` in this environment. No ``pytz`` dependency is added.
"""

import re
import tomllib
from pathlib import Path

CATALOG_DIR = Path(__file__).with_name("reports")
CATALOG_TOML = CATALOG_DIR / "catalog.toml"

# A `{token}` placeholder in a .sql template (ident substitution slot).
_TOKEN_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
# A valid SQL identifier (defense-in-depth: choices are author-controlled, but a
# substituted ident must still be a bare identifier).
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_VALID_KINDS = {"int", "float", "text", "int_list", "ident"}


class ReportError(Exception):
    """A clear, user-facing report/param error (never surfaced as a traceback).

    The CLI catches this, prints ``str(exc)`` to stderr, and exits non-zero.
    """


class Param:
    """One declared param: its kind, default, and (for ``ident``) choices."""

    __slots__ = ("name", "kind", "default", "choices")

    def __init__(self, name, spec):
        if not isinstance(spec, dict):
            raise ReportError(
                "param '%s' must be a table (got %r)" % (name, spec))
        kind = spec.get("type")
        if kind not in _VALID_KINDS:
            raise ReportError(
                "param '%s' has invalid type %r (expected one of %s)"
                % (name, kind, ", ".join(sorted(_VALID_KINDS))))
        self.name = name
        self.kind = kind
        self.default = spec.get("default")
        self.choices = spec.get("choices")
        if kind == "ident":
            if not self.choices or not isinstance(self.choices, list):
                raise ReportError(
                    "ident param '%s' must declare a non-empty 'choices' list"
                    % name)
            for ch in self.choices:
                if not isinstance(ch, str) or not _IDENT_RE.match(ch):
                    raise ReportError(
                        "ident param '%s' has a non-identifier choice %r"
                        % (name, ch))


class Report:
    """A loaded catalog entry: name, description, SQL template, param schema."""

    __slots__ = ("name", "description", "sql_file", "sql_file_dir", "sql",
                 "params", "assembled")

    def __init__(self, name, entry, catalog_dir):
        self.name = name
        self.description = entry.get("description", "")
        sql_file = entry.get("sql")
        if not sql_file:
            raise ReportError("report '%s' is missing a 'sql' file" % name)
        self.sql_file = sql_file
        self.sql_file_dir = catalog_dir
        path = catalog_dir / sql_file
        try:
            self.sql = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ReportError(
                "report '%s': cannot read SQL file '%s': %s"
                % (name, sql_file, exc))
        self.assembled = bool(entry.get("assembled"))

        params_spec = entry.get("params", {}) or {}
        if not isinstance(params_spec, dict):
            raise ReportError("report '%s': 'params' must be a table" % name)
        self.params = {
            pname: Param(pname, pspec) for pname, pspec in params_spec.items()
        }

        # (a) every {token} in the template must be a declared `ident` param.
        idents = {p.name for p in self.params.values() if p.kind == "ident"}
        for tok in set(_TOKEN_RE.findall(self.sql)):
            if tok not in idents:
                raise ReportError(
                    "report '%s': template references {%s}, which is not an "
                    "'ident' param in the manifest" % (name, tok))


def load_catalog(catalog_toml=CATALOG_TOML):
    """Load + validate the report catalog. Returns ``{name: Report}``.

    Raises :class:`ReportError` on a malformed manifest (bad param kind, an
    ident without choices, an undeclared ``{token}`` in a template, …)."""
    catalog_toml = Path(catalog_toml)
    try:
        raw = tomllib.loads(catalog_toml.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ReportError("cannot read report catalog '%s': %s"
                          % (catalog_toml, exc))
    except tomllib.TOMLDecodeError as exc:
        raise ReportError("report catalog '%s' is not valid TOML: %s"
                          % (catalog_toml, exc))
    catalog_dir = catalog_toml.parent
    catalog = {}
    for name, entry in raw.items():
        if not isinstance(entry, dict):
            raise ReportError("catalog entry '%s' must be a table" % name)
        catalog[name] = Report(name, entry, catalog_dir)
    return catalog


def get_report(name, catalog=None):
    """Resolve a report by name, or raise a clear :class:`ReportError`."""
    if catalog is None:
        catalog = load_catalog()
    if name not in catalog:
        known = ", ".join(sorted(catalog)) or "(none)"
        raise ReportError(
            "unknown report '%s'. Known reports: %s" % (name, known))
    return catalog[name]


def list_reports(catalog=None):
    """Return ``[{"name", "description", "params"}, …]`` sorted by name."""
    if catalog is None:
        catalog = load_catalog()
    out = []
    for name in sorted(catalog):
        rep = catalog[name]
        out.append({
            "name": name,
            "description": rep.description,
            "params": {
                p.name: {"type": p.kind, "default": p.default}
                for p in rep.params.values()
            },
        })
    return out


# --- param coercion --------------------------------------------------------

def _expand_int_list_token(tok, param_name):
    """Expand one int_list element, honoring a ``50k``/``2m`` shorthand."""
    s = str(tok).strip()
    if not s:
        raise ReportError(
            "param '%s': empty element in int_list" % param_name)
    mult = 1
    if s[-1:].lower() == "k":
        mult, s = 1000, s[:-1]
    elif s[-1:].lower() == "m":
        mult, s = 1000000, s[:-1]
    try:
        val = float(s) if ("." in s) else int(s)
    except ValueError:
        raise ReportError(
            "param '%s': int_list element %r is not numeric" % (param_name, tok))
    return int(val * mult)


def _coerce_int_list(value, param_name):
    """Coerce a value to a list[int]. Accepts a list (from a TOML default) or a
    ``"50k,200k,400k"`` shorthand string (from the CLI)."""
    if isinstance(value, str):
        items = [p for p in value.split(",")]
    elif isinstance(value, (list, tuple)):
        items = list(value)
    else:
        raise ReportError(
            "param '%s': expected an int_list (list or 'a,b,c'), got %r"
            % (param_name, value))
    if not items:
        raise ReportError("param '%s': int_list is empty" % param_name)
    return [_expand_int_list_token(it, param_name) for it in items]


def _coerce_int(value, param_name):
    if isinstance(value, bool):
        raise ReportError("param '%s' must be an integer" % param_name)
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        raise ReportError(
            "param '%s' must be an integer (got %r)" % (param_name, value))


def _coerce_float(value, param_name):
    if isinstance(value, bool):
        raise ReportError("param '%s' must be a number" % param_name)
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (ValueError, TypeError):
        raise ReportError(
            "param '%s' must be a number (got %r)" % (param_name, value))


def resolve_params(report, overrides):
    """Validate ``overrides`` against ``report``'s schema; return
    ``(bind, idents)``.

    * ``bind`` — ``{name: value}`` for ``int``/``float``/``text``/``int_list``,
      passed to DuckDB as named ``$name`` parameters (never interpolated).
    * ``idents`` — ``{name: column}`` for ``ident`` params, validated against
      ``choices`` and substituted into ``{name}`` template tokens.

    ``overrides`` keys not declared in the schema raise (unknown param).
    Missing params fall back to their declared ``default``.
    """
    if overrides is None:
        overrides = {}
    # (d) unknown param name.
    for key in overrides:
        if key not in report.params:
            known = ", ".join(sorted(report.params)) or "(none)"
            raise ReportError(
                "report '%s': unknown param '%s'. Known params: %s"
                % (report.name, key, known))

    bind = {}
    idents = {}
    for name, p in report.params.items():
        value = overrides[name] if name in overrides else p.default
        if value is None:
            raise ReportError(
                "report '%s': param '%s' has no value and no default"
                % (report.name, name))
        if p.kind == "int":
            bind[name] = _coerce_int(value, name)
        elif p.kind == "float":
            bind[name] = _coerce_float(value, name)
        elif p.kind == "text":
            bind[name] = str(value)
        elif p.kind == "int_list":
            bind[name] = _coerce_int_list(value, name)
        elif p.kind == "ident":
            col = str(value)
            # (c) ident value must be one of the whitelisted choices.
            if col not in p.choices:
                raise ReportError(
                    "report '%s': param '%s'=%r is not allowed. Choices: %s"
                    % (report.name, name, col, ", ".join(p.choices)))
            idents[name] = col
    return bind, idents


def render_sql(report, idents):
    """Substitute validated ``ident`` columns into ``{name}`` template tokens.

    ``$name`` placeholders for value params are left untouched (DuckDB binds
    those). Any ``{token}`` without a resolved ident is a manifest bug and the
    loader already rejected it — assert defensively here too."""
    def repl(match):
        tok = match.group(1)
        if tok not in idents:
            raise ReportError(
                "report '%s': unresolved template token {%s}"
                % (report.name, tok))
        col = idents[tok]
        if not _IDENT_RE.match(col):  # belt-and-suspenders
            raise ReportError(
                "report '%s': ident %r is not a bare identifier"
                % (report.name, col))
        return col
    return _TOKEN_RE.sub(repl, report.sql)


def report_sql(name, catalog=None):
    """Return a report's SQL template text (for ``doctor report <name> --sql``).

    Prints the template WITHOUT executing or ingesting; ``$name`` placeholders
    and any ``{ident}`` tokens are shown as authored so a power user can copy and
    adapt it."""
    return get_report(name, catalog).sql


def run_report(conn, name, overrides=None, catalog=None):
    """Validate params, bind, execute, and return the report's JSON-able payload.

    ``conn`` is a live warehouse DuckDB connection. ``overrides`` is a
    ``{param: value}`` map (typically from CLI flags). Returns either a
    list-of-dict rows (tabular reports) or, for an ``assembled`` report, the
    report's structured payload (e.g. ``summary``)."""
    report = get_report(name, catalog)
    bind, idents = resolve_params(report, overrides)
    sql = render_sql(report, idents)

    if report.assembled:
        assembler = _ASSEMBLERS.get(report.name)
        if assembler is None:
            raise ReportError(
                "report '%s' is marked assembled but has no assembler" % name)
        # idents are passed as a 5th argument so assemblers can substitute the
        # same ident tokens into helper SQL without re-running resolve_params.
        # The bind dict is kept clean (no extra keys that DuckDB would reject).
        return assembler(conn, sql, bind, report, idents)

    return _rows_to_dicts(conn.execute(sql, bind))


def _rows_to_dicts(cursor):
    """Materialize a DuckDB cursor as a list of ``{column: value}`` dicts."""
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


# --- assembled reports -----------------------------------------------------

def _assemble_summary(conn, main_sql, bind, report, idents=None):
    """Reproduce ``doctor_core.build_summary`` field-for-field, sourced from the
    ``turns`` table (not by re-parsing JSONL).

    The main query (``summary.sql``, already bound with ``$days``) supplies the
    global aggregates; a sibling per-session helper (``_summary_sessions.sql``,
    same ``$days`` window) supplies the per-session rollups for top_expensive /
    over-band / avg-context. Truncation and rounding mirror build_summary
    exactly: ``int(x / 1000)`` truncation, ``cache_hit_rate_pct`` to 1 dp, the
    ``extra_tokens_from_misses_k`` formula, top-3 by max context with session
    id ``[:8]``, and the ``"<min> ~ <max>"`` period string (NULL days -> "")."""
    grow = conn.execute(main_sql, bind).fetchone()
    (total_turns, total_input, total_output, total_cr, total_cw,
     total_misses, min_day, max_day) = grow

    total_turns = int(total_turns or 0)
    total_misses = int(total_misses or 0)
    min_day = min_day or ""
    max_day = max_day or ""

    # Per-session rollups (same $days window). Helper SQL sits beside the
    # catalog; it is not itself a catalog report.
    helper_sql = (report.sql_file_dir / "_summary_sessions.sql").read_text(
        encoding="utf-8")
    sess_rows = conn.execute(helper_sql, bind).fetchall()
    # rows: (session_id, max_ctx, sess_total, project, first_day)

    sess_count = 0
    sum_ctx = 0.0
    over_200k = over_400k = 0
    max_ctx_all = 0
    top = []  # (max_ctx, sid, project, sess_total, first_day)
    for sid, max_ctx, sess_total, project, first_day in sess_rows:
        sess_count += 1
        mctx = int(max_ctx or 0)
        ck = mctx / 1000
        sum_ctx += ck
        if ck > 200:
            over_200k += 1
        if ck > 400:
            over_400k += 1
        if mctx > max_ctx_all:
            max_ctx_all = mctx
        top.append((mctx, sid, project or "", int(sess_total or 0),
                    first_day or ""))

    # build_summary's top-3 is a stable sort by max_ctx desc, ties preserving
    # first-seen order. We approximate first-seen with (first_day, session_id)
    # — deterministic and identical when there are no max_ctx ties (the real
    # case; token counts don't collide).
    top.sort(key=lambda r: (r[4], r[1]))          # tie-break proxy first
    top.sort(key=lambda r: r[0], reverse=True)    # then by max_ctx desc (stable)
    top = top[:3]

    avg_ctx = (sum_ctx / sess_count) if sess_count > 0 else 0
    hit_rate = (((total_turns - total_misses) / total_turns) * 100
                if total_turns > 0 else 0)
    extra = int(total_misses * avg_ctx * 0.9)

    return {
        "period": "%s ~ %s" % (min_day, max_day),
        "sessions_analyzed": sess_count,
        "total_turns": total_turns,
        "avg_final_context_k": int(avg_ctx),
        "max_context_k": int(max_ctx_all / 1000),
        "sessions_over_200k": over_200k,
        "sessions_over_400k": over_400k,
        "cache_hit_rate_pct": round(hit_rate, 1),
        "cache_misses": total_misses,
        "total_input_k": int(total_input / 1000),
        "total_output_k": int(total_output / 1000),
        "total_cache_read_k": int(total_cr / 1000),
        "total_cache_creation_k": int(total_cw / 1000),
        "extra_tokens_from_misses_k": extra,
        "top_expensive": [
            {
                "session": sid[:8],
                "project": project,
                "max_context_k": int(mctx / 1000),
                "total_tokens_k": int(tot / 1000),
            }
            for (mctx, sid, project, tot, _fd) in top
        ],
    }


def _assemble_rolling(conn, main_sql, bind, report, idents=None):
    """Dispatch to mode-specific helper SQL (rolling_days.sql / rolling_turns.sql).

    The ``mode`` text param selects which helper to load.  Accepted values:
    ``'days'`` (per-day buckets, N-day moving average — the Grafana-style default)
    and ``'turns'`` (last-N-turns window over individual turns).  Any other value
    raises :class:`ReportError` with a clear user-facing message.

    The ``metric`` ident is already resolved in ``idents`` (passed through from
    :func:`run_report`).  We re-apply the same token substitution to the helper
    template so DuckDB sees a concrete column name, never a raw ``{metric}`` token.

    Returns a list-of-dict rows (tabular time-series output).
    """
    if idents is None:
        idents = {}

    # `mode` is an `ident` param (whitelisted choices=["days","turns"]), so it is
    # resolved into `idents` (not `bind`) by resolve_params — the engine already
    # rejected any value outside the whitelist. It selects which helper template
    # to load; it is never interpolated into SQL. `metric` (also an ident) stays
    # in `idents` and is substituted into the {metric} token below.
    mode = idents.get("mode", "days")
    if mode not in ("days", "turns"):  # belt-and-suspenders; resolve_params guards
        raise ReportError(
            "report 'rolling': param 'mode' must be 'days' or 'turns' "
            "(got %r)" % mode)

    # Load the mode-specific helper SQL from the same reports/ directory.
    helper_name = "rolling_%s.sql" % mode
    helper_path = report.sql_file_dir / helper_name
    try:
        helper_sql_template = helper_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ReportError(
            "report 'rolling': cannot read helper '%s': %s" % (helper_name, exc))

    # Substitute ident tokens ({metric}) into the helper template — the same
    # whitelist-validated column that was substituted into the main SQL.
    helper_sql = _TOKEN_RE.sub(
        lambda m: idents.get(m.group(1), m.group(0)), helper_sql_template)

    return _rows_to_dicts(conn.execute(helper_sql, bind))


_ASSEMBLERS = {
    "summary": _assemble_summary,
    "rolling": _assemble_rolling,
}
