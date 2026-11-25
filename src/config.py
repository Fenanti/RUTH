"""
Gestione configurazione dell'applicazione.
Supporta SQLite (locale/NAS) e PostgreSQL (multicassa in rete).
Equivalente di config.rs
"""
import json
from pathlib import Path

CONFIG_DIR = Path(r"C:\sagra")
CONFIG_PATH = CONFIG_DIR / "config_stampa.json"

DEFAULT_DB_URL = r"sqlite:///C:\sagra\database.db"

POSTGRES_PREFIXES = ("postgresql://", "postgres://", "postgresql+psycopg://")


class AppConfig:
    """Configurazione dell'app: URL database e stampante."""

    def __init__(self, db_url: str = "", printer_name: str = ""):
        self.db_url = (db_url or "").strip() or DEFAULT_DB_URL
        self.printer_name = (printer_name or "").strip()

    # ------------------------------------------------------------------
    # Persistenza
    # ------------------------------------------------------------------

    @classmethod
    def default(cls) -> "AppConfig":
        return cls()

    @classmethod
    def load(cls) -> "AppConfig":
        """Carica la config da C:\\sagra\\config_stampa.json (la crea se manca)."""
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            print(f"⚠️ Errore creazione cartella {CONFIG_DIR}: {e}")

        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)

                return cls(
                    db_url=str(data.get("db_url", "")),
                    printer_name=str(data.get("printer_name", "")),
                )
            except (OSError, json.JSONDecodeError) as e:
                print(f"⚠️ Errore lettura config: {e}")

        cfg = cls.default()

        try:
            cfg.save()
        except OSError as e:
            print(f"⚠️ Errore salvataggio config di default: {e}")

        return cfg

    def save(self) -> None:
        """Salva la config su disco."""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

        data = {
            "db_url": self.db_url,
            "printer_name": self.printer_name,
        }

        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # Informazioni sul database
    # ------------------------------------------------------------------

    @property
    def is_postgres(self) -> bool:
        """True se l'URL punta a PostgreSQL."""
        return self.db_url.lower().startswith(POSTGRES_PREFIXES)

    @property
    def db_label(self) -> str:
        """Etichetta leggibile per la GUI."""
        return "PostgreSQL (rete / multicassa)" if self.is_postgres else "SQLite (locale)"