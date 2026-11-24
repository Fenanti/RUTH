"""
Script di diagnostica per verificare il database della sagra.
Uso: python check_db.py
"""
import os
import sqlite3

db_path = r"C:\sagra\database.db"

print(f"Percorso DB: {db_path}")
print(f"Esiste: {os.path.exists(db_path)}")

if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)

    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    print(f"\nTabelle trovate: {tables}")

    if "ordini" in tables:
        cursor = conn.execute("SELECT COUNT(*) FROM ordini")
        print(f"\nNumero ordini: {cursor.fetchone()[0]}")

        cursor = conn.execute("SELECT serata, totalePagato FROM ordini LIMIT 5")
        print("Primi 5 ordini:")
        for row in cursor.fetchall():
            print(f"  serata={row[0]}  totale={row[1]}")
    else:
        print("❌ Tabella 'ordini' NON trovata")

    if "righe" in tables:
        cursor = conn.execute("SELECT COUNT(*) FROM righe")
        print(f"\nNumero righe: {cursor.fetchone()[0]}")
    else:
        print("❌ Tabella 'righe' NON trovata")

    conn.close()
else:
    print("\n❌ Il database non esiste.")
    print("   Verifica che la tua app Rust lo abbia creato in C:\\sagra\\database.db")
    print("   oppure cambia il percorso nella tab Configurazione.")