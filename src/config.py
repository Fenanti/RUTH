"""
Gestione configurazione dell'applicazione.
Equivalent to config.rs
"""
import json
import os
from pathlib import Path

CONFIG_DIR = r"C:\sagra"
CONFIG_PATH = os.path.join(CONFIG_DIR, "config_stampa.json")


class AppConfig:
    """Configurazione dell'app: percorso DB e stampante."""

    def __init__(self, db_url: str = "", printer_name: str = ""):
        self.db_url = db_url or r"sqlite:///C:\sagra\database.db"
        self.printer_name = printer_name

    @classmethod
    def default(cls) -> "AppConfig":
        return cls()

    @classmethod
    def load(cls) -> "AppConfig":
        """Carica la config da C:\\sagra\\config_stampa.json, o crea il default."""
        # 1. Crea la cartella se non esiste
        Path(CONFIG_DIR).mkdir(parents=True, exist_ok=True)

        # 2. Prova a leggere il file esistente
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return cls(
                    db_url=data.get("db_url", ""),
                    printer_name=data.get("printer_name", ""),
                )
            except (json.JSONDecodeError, IOError) as e:
                print(f"⚠️ Errore lettura config: {e}")

        # 3. Se non esiste, salva il default
        cfg = cls.default()
        cfg.save()
        return cfg

    def save(self) -> None:
        """Salva la config su disco."""
        Path(CONFIG_DIR).mkdir(parents=True, exist_ok=True)
        data = {
            "db_url": self.db_url,
            "printer_name": self.printer_name,
        }
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def get_db_path(self) -> str:
        """Estrae il percorso del DB dal URL sqlite:///..."""
        url = self.db_url
        if url.startswith("sqlite:///"):
            return url[len("sqlite:///"):]
        elif url.startswith("sqlite://"):
            return url[len("sqlite://"):]
        return url