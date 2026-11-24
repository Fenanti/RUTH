"""
Accesso al database SQLite.
Equivalent to db.rs
"""
import sqlite3
from .models import DailySummary, AggregatedRow


def get_connection(db_path: str) -> sqlite3.Connection:
    """Crea una connessione al database SQLite."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def fetch_daily_summaries(db_path: str) -> list[DailySummary]:
    """
    Recupera tutte le serate con totale incasso e numero ordini.
    Equivalente di fetch_daily_summaries() in Rust.
    """
    conn = get_connection(db_path)
    try:
        cursor = conn.execute(
            "SELECT CAST(o.serata AS TEXT) as serata, o.id, o.totalePagato FROM ordini o"
        )
        rows = cursor.fetchall()
    finally:
        conn.close()

    # Aggrega per serata
    summaries: dict[str, dict] = {}
    for row in rows:
        serata = row["serata"] or "Sconosciuta"
        tot_raw = row["totalePagato"]

        # Parsing robusto del totale (come in Rust: i64, f64, o stringa)
        try:
            tot = float(tot_raw)
        except (TypeError, ValueError):
            try:
                tot = float(str(tot_raw).replace(",", "."))
            except (TypeError, ValueError):
                tot = 0.0

        if serata not in summaries:
            summaries[serata] = {"numero_ordini": 0, "totale": 0.0}
        summaries[serata]["numero_ordini"] += 1
        summaries[serata]["totale"] += tot

    # Costruisci la lista ordinata per data decrescente
    result = []
    for serata, data in summaries.items():
        result.append(DailySummary(
            data_serata=serata,
            totale_serata=f"{data['totale']:.2f}",
            numero_ordini=data["numero_ordini"],
        ))
    result.sort(key=lambda s: s.data_serata, reverse=True)
    return result


def fetch_aggregated_rows_for_date(db_path: str, pattern: str) -> list[AggregatedRow]:
    """
    Recupera gli articoli venduti aggregati per descrizione,
    filtrati per pattern data (es. '2026-10' o '2026-10-29').
    Equivalente di fetch_aggregated_rows_for_date() in Rust.
    """
    like_pattern = f"{pattern}%"
    conn = get_connection(db_path)
    try:
        cursor = conn.execute(
            """
            SELECT r.descrizione, SUM(r.quantita) as qta_tot
            FROM righe r
            JOIN ordini o ON r.id_ordine = o.id
            WHERE CAST(o.serata AS TEXT) LIKE ?
            GROUP BY r.descrizione
            ORDER BY qta_tot DESC
            """,
            (like_pattern,),
        )
        rows = cursor.fetchall()
    finally:
        conn.close()

    result = []
    for row in rows:
        descrizione = row["descrizione"] or "Articolo"
        quantita = int(row["qta_tot"] or 0)
        result.append(AggregatedRow(
            descrizione=descrizione,
            quantita_totale=quantita,
        ))
    return result