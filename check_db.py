"""
Diagnostica database.
Uso:
    python check_db.py                          # usa l'URL in config_stampa.json
    python check_db.py postgresql://sagra:sagra@192.168.1.50:5432/sagra
"""
import sys

from src.config import AppConfig
from src.db import connect, is_postgres_url, sqlite_path_from_url


def main() -> None:
    cfg = AppConfig.load()
    db_url = sys.argv[1] if len(sys.argv) > 1 else cfg.db_url
    is_pg = is_postgres_url(db_url)

    print("=" * 60)
    print(f"URL:  {db_url}")
    print(f"Tipo: {'PostgreSQL (rete)' if is_pg else 'SQLite (locale)'}")

    if not is_pg:
        print(f"File: {sqlite_path_from_url(db_url)}")

    print("=" * 60)

    try:
        conn, is_pg = connect(db_url)
    except Exception as exc:
        print(f"❌ Connessione fallita: {exc}")
        return

    print("✅ Connessione riuscita!\n")

    try:
        # Elenco tabelle
        if is_pg:
            rows = conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' ORDER BY table_name"
            ).fetchall()
            tables = [r["table_name"] for r in rows]
        else:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
            tables = [r["name"] for r in rows]

        print(f"Tabelle trovate ({len(tables)}): {tables}\n")

        # Conteggi e campione
        for tabella in ("ordini", "righe"):
            if tabella not in tables:
                print(f"❌ Tabella '{tabella}' NON trovata")
                continue

            count = conn.execute(f"SELECT COUNT(*) AS n FROM {tabella}").fetchone()
            print(f"✅ {tabella}: {count['n']} record")

        if "ordini" in tables:
            print("\nPrime 5 serate:")
            rows = conn.execute(
                "SELECT CAST(serata AS TEXT) AS serata FROM ordini LIMIT 5"
            ).fetchall()
            for r in rows:
                print(f"  - {r['serata']}")

    except Exception as exc:
        print(f"❌ Errore durante la diagnostica: {exc}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()