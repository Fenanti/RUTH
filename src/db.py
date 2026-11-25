#25/11/2026
"""
Accesso dati dual-driver: SQLite (locale/NAS) e PostgreSQL (multicassa).
Equivalente di db.rs che usava sqlx::AnyPool.

L'URL decide il driver:
  sqlite:///C:\\sagra\\database.db
  sqlite:///W:\\sagra\\databaseNAS.db?check_same_thread=False
  postgresql://sagra:sagra@192.168.1.50:5432/sagra
"""
import os
import sqlite3

from .models import AggregatedRow, DailySummary

try:
    import psycopg  # type: ignore
    from psycopg import errors as pg_errors  # type: ignore
    from psycopg.rows import dict_row  # type: ignore

    HAS_PSYCOPG = True
except ImportError:
    psycopg = None
    pg_errors = None
    dict_row = None
    HAS_PSYCOPG = False


POSTGRES_PREFIXES = ("postgresql://", "postgres://", "postgresql+psycopg://")
CONNECT_TIMEOUT = 8


# ======================================================================
# PARSING URL
# ======================================================================

def is_postgres_url(db_url: str) -> bool:
    """True se l'URL è PostgreSQL."""
    return (db_url or "").strip().lower().startswith(POSTGRES_PREFIXES)


def postgres_conninfo(db_url: str) -> str:
    """Normalizza l'URL in un conninfo accettato da psycopg/libpq."""
    url = (db_url or "").strip()
    lowered = url.lower()

    if lowered.startswith("postgresql+psycopg://"):
        return "postgresql://" + url[len("postgresql+psycopg://"):]

    if lowered.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://"):]

    return url


def sqlite_path_from_url(db_url: str) -> str:
    """
    Estrae il percorso file da un URL SQLite.
    Gestisce i parametri ?check_same_thread=False (stringhe del manuale GSG)
    e i percorsi UNC di rete/NAS.
    """
    url = (db_url or "").strip()

    # Rimuove la query string: sqlite:///W:\...db?check_same_thread=False
    url = url.split("?", 1)[0]

    lowered = url.lower()
    for prefix in ("sqlite:///", "sqlite://"):
        if lowered.startswith(prefix):
            return url[len(prefix):]

    return url


# ======================================================================
# CONVERSIONI ROBUSTE
# ======================================================================

def _to_float(value) -> float:
    """Parsing monetario robusto (int, float, Decimal, stringa con virgola)."""
    if value is None:
        return 0.0

    try:
        return float(value)
    except (TypeError, ValueError):
        pass

    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


def _to_int(value) -> int:
    """Conversione robusta a intero."""
    if value is None:
        return 0

    try:
        return int(value)
    except (TypeError, ValueError):
        pass

    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


# ======================================================================
# CONNESSIONE
# ======================================================================

def connect(db_url: str):
    """
    Apre una connessione e restituisce (connessione, is_postgres).
    Equivalente di db::create_pool() in Rust.
    """
    db_url = (db_url or "").strip()

    if not db_url:
        raise ValueError("URL database vuoto.")

    # ---------- PostgreSQL ----------
    if is_postgres_url(db_url):
        if not HAS_PSYCOPG:
            raise RuntimeError(
                'Driver PostgreSQL mancante. Installa con: '
                'python -m pip install "psycopg[binary]"'
            )

        conn = psycopg.connect(
            postgres_conninfo(db_url),
            row_factory=dict_row,
            connect_timeout=CONNECT_TIMEOUT,
        )
        conn.autocommit = True  # solo lettura: niente transazioni appese
        return conn, True

    # ---------- SQLite ----------
    path = sqlite_path_from_url(db_url)

    if not path:
        raise ValueError("Percorso file SQLite vuoto.")

    if not os.path.exists(path):
        raise FileNotFoundError(f"Database non trovato: {path}")

    conn = sqlite3.connect(path, timeout=CONNECT_TIMEOUT)
    conn.row_factory = sqlite3.Row
    return conn, False


def _run_query(db_url: str, queries: list[str], params: tuple = ()):
    """
    Esegue la prima query che funziona.
    Su PostgreSQL, se la colonna quotata non esiste, ripiega su quella minuscola
    (dipende da come è stato creato lo schema in fase di migrazione).
    """
    conn, is_pg = connect(db_url)

    try:
        last_error = None

        for query in queries:
            try:
                return conn.execute(query, params).fetchall()
            except Exception as exc:
                last_error = exc

                column_missing = (
                    is_pg
                    and pg_errors is not None
                    and isinstance(exc, pg_errors.UndefinedColumn)
                )

                if column_missing:
                    continue

                raise

        raise last_error
    finally:
        conn.close()


# ======================================================================
# QUERY
# ======================================================================

def _summaries_queries(is_pg: bool) -> list[str]:
    """
    Query riepilogo serate.
    In PostgreSQL gli identificatori mixed-case vanno quotati ("totalePagato"),
    altrimenti vengono cercati tutti minuscoli.
    """
    base = "SELECT CAST(o.serata AS TEXT) AS serata, {} AS totale_pagato FROM ordini o"

    if is_pg:
        return [
            base.format('o."totalePagato"'),
            base.format("o.totalePagato"),
        ]

    return [base.format("o.totalePagato")]


def _aggregated_query(is_pg: bool) -> str:
    """Query distinta articoli. Placeholder: %s per PostgreSQL, ? per SQLite."""
    ph = "%s" if is_pg else "?"

    return f"""
        SELECT r.descrizione,
               SUM(r.quantita) AS qta_tot
        FROM righe r
        JOIN ordini o ON r.id_ordine = o.id
        WHERE CAST(o.serata AS TEXT) LIKE {ph}
        GROUP BY r.descrizione
        ORDER BY qta_tot DESC
    """


# ======================================================================
# FUNZIONI PUBBLICHE
# ======================================================================

def fetch_daily_summaries(db_url: str) -> list[DailySummary]:
    """
    Recupera tutte le serate con totale incasso e numero ordini.
    Equivalente di fetch_daily_summaries() in Rust.
    """
    rows = _run_query(db_url, _summaries_queries(is_postgres_url(db_url)))

    summaries: dict[str, dict] = {}

    for row in rows:
        serata = row["serata"] or "Sconosciuta"
        totale = _to_float(row["totale_pagato"])

        if serata not in summaries:
            summaries[serata] = {"numero_ordini": 0, "totale": 0.0}

        summaries[serata]["numero_ordini"] += 1
        summaries[serata]["totale"] += totale

    result = [
        DailySummary(
            data_serata=serata,
            totale_serata=f"{data['totale']:.2f}",
            numero_ordini=data["numero_ordini"],
        )
        for serata, data in summaries.items()
    ]

    result.sort(key=lambda s: s.data_serata, reverse=True)
    return result

def fetch_aggregated_rows_for_date(db_url: str, pattern: str) -> list[AggregatedRow]:
    """
    Articoli venduti aggregati per descrizione, filtrati per pattern data.
    Pattern: "2026", "2026-11", "2026-11-24", "" per tutto.
    """
    is_pg = is_postgres_url(db_url)
    like_pattern = f"{pattern}%" if pattern else "%"

    rows = _run_query(
        db_url,
        [_aggregated_query(is_pg)],
        (like_pattern,),
    )

    return [
        AggregatedRow(
            descrizione=row["descrizione"] or "Articolo",
            quantita_totale=_to_int(row["qta_tot"]),
        )
        for row in rows
    ]