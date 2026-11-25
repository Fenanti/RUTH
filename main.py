#25/11/2026
"""
Stand Gastronomico - Totali Serata
Conversione Python dell'applicazione Rust (egui/eframe -> CustomTkinter).

Database: SQLite (locale/NAS) oppure PostgreSQL (rete / multicassa)
          -> il driver viene scelto automaticamente dall'URL in configurazione
Stampa:   PowerShell + Out-Printer su stampante termica 80mm
"""
import os
import subprocess
import tempfile
import threading
from datetime import datetime

import customtkinter as ctk

from src.config import AppConfig
from src.db import fetch_aggregated_rows_for_date, fetch_daily_summaries

try:
    import win32print

    HAS_WIN32PRINT = True
except ImportError:
    HAS_WIN32PRINT = False


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

NO_PRINTER_LABEL = "Nessuna stampante trovata"


def get_printers() -> list[str]:
    """
    Ottiene la lista delle stampanti installate su Windows.
    Gestisce i diversi formati restituiti da pywin32 (tuple, dict, oggetti)
    provando più livelli di EnumPrinters.
    """
    if not HAS_WIN32PRINT:
        return []

    names: set[str] = set()

    # Level 4 è il più leggero; 2 e 1 sono fallback
    for level in (4, 2, 1):
        try:
            flags = (
                win32print.PRINTER_ENUM_LOCAL
                | win32print.PRINTER_ENUM_CONNECTIONS
            )
            printers = win32print.EnumPrinters(flags, None, level)
        except Exception as e:
            print(f"EnumPrinters level {level} fallito: {e}")
            continue

        for item in printers:
            name = ""

            # Caso dizionario
            if isinstance(item, dict):
                name = item.get("pPrinterName") or item.get("Name") or ""

            # Caso tupla/lista
            elif isinstance(item, (tuple, list)):
                # PRINTER_INFO_4: (pPrinterName, pServerName, Attributes) -> index 0
                # PRINTER_INFO_2: pPrinterName -> index 1
                # PRINTER_INFO_1: pName -> index 2
                if level == 4 and len(item) > 0:
                    name = item[0]
                elif level == 2 and len(item) > 1:
                    name = item[1]
                elif level == 1 and len(item) > 2:
                    name = item[2]
                elif len(item) > 0:
                    name = item[0]

            # Caso oggetto con attributi
            else:
                name = (
                    getattr(item, "pPrinterName", "")
                    or getattr(item, "Name", "")
                )

            if name:
                names.add(str(name))

        # Se abbiamo trovato stampanti, non serve provare altri livelli
        if names:
            break

    return sorted(names)


class SagraApp(ctk.CTk):
    """Applicazione principale: totali serate, distinta articoli e stampa."""

    def __init__(self):
        super().__init__()

        # --- Configurazione finestra ---
        self.title("Stand Gastronomico - Totali Serata")
        self.geometry("750x500")
        self.minsize(650, 450)

        # --- Stato dell'applicazione ---
        self.config_app = AppConfig.load()
        self.status_message = "Avvio in corso..."

        self.daily_summaries = []
        self.aggregated_rows = []
        self.printer_list = get_printers()

        now = datetime.now()
        self.filter_day = ""
        self.filter_month = now.strftime("%m")
        self.filter_year = now.strftime("%Y")

        # --- Costruzione interfaccia ---
        self._build_ui()

        # --- Caricamento iniziale in thread separato (non blocca la GUI) ---
        initial_pattern = self._get_filter_pattern()

        threading.Thread(
            target=self._load_summaries_thread,
            args=(initial_pattern,),
            daemon=True,
        ).start()

    # ======================================================================
    # COSTRUZIONE INTERFACCIA
    # ======================================================================

    def _build_ui(self):
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=10, pady=10)

        self.tab_sales = self.tabview.add("📊 Totali Giornalieri & Venduto")
        self.tab_config = self.tabview.add("⚙️ Configurazione")

        self._build_sales_tab()
        self._build_config_tab()

    def _build_sales_tab(self):
        ctk.CTkLabel(
            self.tab_sales,
            text="Totale Vendite per Serata e Distinta Articoli",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(anchor="w", padx=10, pady=(10, 5))

        # --- Barra controlli: pulsante carica + filtri + pulsante stampa ---
        controls_frame = ctk.CTkFrame(self.tab_sales, fg_color="transparent")
        controls_frame.pack(fill="x", padx=10, pady=5)

        self.btn_refresh = ctk.CTkButton(
            controls_frame,
            text="🔄 Carica / Aggiorna Dati",
            width=190,
            height=45,
            command=self._on_refresh_click,
        )
        self.btn_refresh.pack(side="left", padx=(0, 12))

        ctk.CTkLabel(controls_frame, text="Filtra Serata:").pack(
            side="left", padx=(0, 8)
        )

        ctk.CTkLabel(controls_frame, text="Giorno:").pack(side="left", padx=(8, 2))
        self.entry_day = ctk.CTkEntry(controls_frame, width=45)
        self.entry_day.pack(side="left")
        self.entry_day.bind("<KeyRelease>", self._on_filter_change)

        ctk.CTkLabel(controls_frame, text="Mese:").pack(side="left", padx=(8, 2))
        self.entry_month = ctk.CTkEntry(controls_frame, width=45)
        self.entry_month.insert(0, self.filter_month)
        self.entry_month.pack(side="left")
        self.entry_month.bind("<KeyRelease>", self._on_filter_change)

        ctk.CTkLabel(controls_frame, text="Anno:").pack(side="left", padx=(8, 2))
        self.entry_year = ctk.CTkEntry(controls_frame, width=60)
        self.entry_year.insert(0, self.filter_year)
        self.entry_year.pack(side="left")
        self.entry_year.bind("<KeyRelease>", self._on_filter_change)

        self.btn_print = ctk.CTkButton(
            controls_frame,
            text="🖨️ Stampa Totali",
            width=130,
            height=45,
            fg_color="#2e7d32",
            hover_color="#1b5e20",
            command=self._on_print_click,
        )
        self.btn_print.pack(side="right")

        # --- Riga di stato ---
        self.status_label = ctk.CTkLabel(
            self.tab_sales,
            text=f"Stato: {self.status_message}",
            text_color="gray",
        )
        self.status_label.pack(anchor="w", padx=10, pady=5)

        # --- Contenuto a due colonne (50% / 50%) ---
        columns_frame = ctk.CTkFrame(self.tab_sales, fg_color="transparent")
        columns_frame.pack(fill="both", expand=True, padx=10, pady=5)

        columns_frame.columnconfigure(0, weight=1)
        columns_frame.columnconfigure(1, weight=1)
        columns_frame.rowconfigure(0, weight=1)

        # Colonna sinistra: Riepilogo Serate
        left_frame = ctk.CTkFrame(columns_frame)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

        ctk.CTkLabel(
            left_frame,
            text="Riepilogo Serate",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", padx=10, pady=(10, 5))

        self.scroll_summaries = ctk.CTkScrollableFrame(left_frame)
        self.scroll_summaries.pack(
            fill="both", expand=True, padx=10, pady=(0, 10)
        )

        # Container interno: svuotiamo questo, non lo ScrollableFrame,
        # così non rischiamo di distruggere canvas e scrollbar interni.
        self.summaries_container = ctk.CTkFrame(
            self.scroll_summaries, fg_color="transparent"
        )
        self.summaries_container.pack(fill="x")

        # Colonna destra: Distinta Articoli
        right_frame = ctk.CTkFrame(columns_frame)
        right_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0))

        ctk.CTkLabel(
            right_frame,
            text="Distinta Articoli Venduti",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", padx=10, pady=(10, 5))

        self.label_period = ctk.CTkLabel(
            right_frame,
            text="Periodo selezionato: Nessuno",
            text_color="gray",
        )
        self.label_period.pack(anchor="w", padx=10)

        self.scroll_articles = ctk.CTkScrollableFrame(right_frame)
        self.scroll_articles.pack(
            fill="both", expand=True, padx=10, pady=(5, 10)
        )

        self.articles_container = ctk.CTkFrame(
            self.scroll_articles, fg_color="transparent"
        )
        self.articles_container.pack(fill="x")

    def _build_config_tab(self):
        ctk.CTkLabel(
            self.tab_config,
            text="Configurazione",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(anchor="w", padx=10, pady=(10, 5))

        # --- URL Database ---
        ctk.CTkLabel(
            self.tab_config,
            text="📁 URL di Connessione Database:",
        ).pack(anchor="w", padx=10, pady=(15, 5))

        self.entry_db_url = ctk.CTkEntry(self.tab_config)
        self.entry_db_url.insert(0, self.config_app.db_url)
        self.entry_db_url.pack(fill="x", padx=10)

        # Etichetta che mostra quale driver verrà usato (SQLite o PostgreSQL)
        self.label_db_kind = ctk.CTkLabel(
            self.tab_config,
            text=f"Tipo rilevato: {self.config_app.db_label}",
            text_color="gray",
        )
        self.label_db_kind.pack(anchor="w", padx=10, pady=(2, 0))

        ctk.CTkLabel(
            self.tab_config,
            text=(
                "Esempi:  sqlite:///C:\\sagra\\database.db   •   "
                "postgresql://sagra:sagra@192.168.1.50:5432/sagra"
            ),
            text_color="#6b6b6b",
            font=ctk.CTkFont(size=11),
        ).pack(anchor="w", padx=10, pady=(2, 0))

        # --- Stampante ---
        ctk.CTkLabel(
            self.tab_config,
            text="🖨️ Stampante Termica (80mm):",
        ).pack(anchor="w", padx=10, pady=(20, 5))

        printer_frame = ctk.CTkFrame(self.tab_config, fg_color="transparent")
        printer_frame.pack(fill="x", padx=10)

        self.label_selected_printer = ctk.CTkLabel(
            printer_frame,
            text=self._get_printer_status_text(),
        )
        self.label_selected_printer.pack(side="left", padx=(0, 15))

        self.combo_printer = ctk.CTkComboBox(
            printer_frame,
            values=self._get_printer_combo_values(),
            width=280,
            command=self._on_printer_selected,
        )
        self.combo_printer.set(self.config_app.printer_name)
        self.combo_printer.pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            printer_frame,
            text="🔄 Ricarica Lista",
            width=130,
            command=self._on_refresh_printers,
        ).pack(side="left")

        # --- Salva configurazione ---
        ctk.CTkButton(
            self.tab_config,
            text="💾 Salva Configurazione",
            width=200,
            height=40,
            command=self._on_save_config,
        ).pack(anchor="w", padx=10, pady=25)

        self.status_label_config = ctk.CTkLabel(
            self.tab_config,
            text=f"Stato: {self.status_message}",
            text_color="gray",
        )
        self.status_label_config.pack(anchor="w", padx=10, pady=10)

    # ======================================================================
    # UTILITY
    # ======================================================================

    def _get_printer_combo_values(self) -> list[str]:
        """Valori del menu stampanti, mantenendo visibile quella salvata."""
        values = list(self.printer_list)

        if (
            self.config_app.printer_name
            and self.config_app.printer_name not in values
        ):
            values.insert(0, self.config_app.printer_name)

        if not values:
            values = [NO_PRINTER_LABEL]

        return values

    def _normalize_printer_choice(self, choice: str) -> str:
        """Converte il placeholder in stringa vuota (nessuna stampante)."""
        if not choice or choice == NO_PRINTER_LABEL:
            return ""

        return choice.strip()

    def _get_printer_status_text(self) -> str:
        if self.config_app.printer_name:
            return f"Selezionata: {self.config_app.printer_name}"

        return "Nessuna stampante selezionata"

    def _sanitize_entry(self, entry: ctk.CTkEntry, max_length: int) -> str:
        """Mantiene solo cifre, per la lunghezza massima indicata."""
        value = entry.get().strip()
        cleaned = "".join(ch for ch in value if ch.isdigit())[:max_length]

        if cleaned != value:
            entry.delete(0, "end")
            entry.insert(0, cleaned)

        return cleaned

    def _get_filter_pattern(self) -> str:
        """
        Costruisce il pattern di filtro data:
        "2026", "2026-11", "2026-11-24" oppure "" (tutto).
        Mese e giorno vengono normalizzati a due cifre.
        """
        day = self._sanitize_entry(self.entry_day, 2)
        month = self._sanitize_entry(self.entry_month, 2)
        year = self._sanitize_entry(self.entry_year, 4)

        self.filter_day = day.zfill(2) if day else ""
        self.filter_month = month.zfill(2) if month else ""
        self.filter_year = year

        if year and month and day:
            return f"{year}-{self.filter_month}-{self.filter_day}"

        if year and month:
            return f"{year}-{self.filter_month}"

        if year:
            return year

        return ""

    def _set_status(self, message: str):
        """Aggiorna le righe di stato di entrambi i tab (chiamare dal main thread)."""
        self.status_message = message
        self.status_label.configure(text=f"Stato: {message}")
        self.status_label_config.configure(text=f"Stato: {message}")

    def _bind_click(self, widget, command):
        """Rende un widget cliccabile con cursore a manina."""
        widget.bind("<Button-1>", command)

        try:
            widget.configure(cursor="hand2")
        except Exception:
            pass

    # ======================================================================
    # EVENTI
    # ======================================================================

    def _on_refresh_click(self):
        # Come nella versione Rust: il refresh azzera il filtro giorno
        self.entry_day.delete(0, "end")
        pattern = self._get_filter_pattern()

        threading.Thread(
            target=self._load_summaries_thread,
            args=(pattern,),
            daemon=True,
        ).start()

    def _on_filter_change(self, event=None):
        pattern = self._get_filter_pattern()

        threading.Thread(
            target=self._load_aggregated_thread,
            args=(pattern,),
            daemon=True,
        ).start()

    def _on_printer_selected(self, choice: str):
        printer = self._normalize_printer_choice(choice)

        self.config_app.printer_name = printer
        self.label_selected_printer.configure(
            text=self._get_printer_status_text()
        )

        if printer:
            self._set_status(f"Stampante selezionata: {printer}")
        else:
            self._set_status("Nessuna stampante selezionata.")

    def _on_refresh_printers(self):
        self.printer_list = get_printers()

        self.combo_printer.configure(values=self._get_printer_combo_values())

        if self.config_app.printer_name:
            self.combo_printer.set(self.config_app.printer_name)
        else:
            self.combo_printer.set("")

        self._set_status(
            f"Stampanti ricaricate: trovate {len(self.printer_list)}"
        )

    def _on_save_config(self):
        self.config_app.db_url = self.entry_db_url.get().strip()
        self.config_app.printer_name = self._normalize_printer_choice(
            self.combo_printer.get()
        )

        try:
            self.config_app.save()
        except Exception as exc:
            error = str(exc)
            self._set_status(f"Errore nel salvataggio: {error}")
            return

        self.label_db_kind.configure(
            text=f"Tipo rilevato: {self.config_app.db_label}"
        )
        self._set_status(
            "Configurazione salvata in C:\\sagra\\config_stampa.json! "
            "Premi 'Carica / Aggiorna Dati' per applicarla."
        )

    # ======================================================================
    # CARICAMENTO DATI (thread separati)
    # ======================================================================

    def _load_summaries_thread(self, pattern: str):
        """Carica il riepilogo serate dal database (SQLite o PostgreSQL)."""
        self.after(0, lambda: self._set_status("Caricamento in corso..."))

        try:
            db_url = self.config_app.db_url
            summaries = fetch_daily_summaries(db_url)
        except Exception as exc:
            error = str(exc)

            self.daily_summaries = []
            self.aggregated_rows = []

            self.after(
                0,
                lambda: self._set_status(f"Errore connessione DB: {error}"),
            )
            self.after(0, self._render_summaries)
            self.after(0, lambda: self._render_articles(pattern))
            return

        self.daily_summaries = summaries

        n = len(summaries)
        msg = f"Caricata {n} serata." if n == 1 else f"Caricate {n} serate."
        msg += f" [{self.config_app.db_label}]"

        self.after(0, lambda: self._set_status(msg))
        self.after(0, self._render_summaries)

        # Carica anche la distinta articoli per il filtro corrente
        self._load_aggregated_thread(pattern)

    def _load_aggregated_thread(self, pattern: str):
        """Carica la distinta articoli aggregata per il pattern indicato."""
        try:
            db_url = self.config_app.db_url
            rows = fetch_aggregated_rows_for_date(db_url, pattern)
            self.aggregated_rows = rows
        except Exception:
            self.aggregated_rows = []
        finally:
            self.after(0, lambda: self._render_articles(pattern))

    # ======================================================================
    # RENDERING LISTE
    # ======================================================================

    def _render_summaries(self):
        """Disegna le card delle serate nella colonna sinistra."""
        for widget in self.summaries_container.winfo_children():
            widget.destroy()

        pattern = self._get_filter_pattern()

        if not self.daily_summaries:
            ctk.CTkLabel(
                self.summaries_container,
                text="Nessuna serata caricata.",
            ).pack(pady=20)
            return

        visible_count = 0

        for ds in self.daily_summaries:
            if pattern and not ds.data_serata.startswith(pattern):
                continue

            visible_count += 1
            self._create_summary_card(ds)

        if visible_count == 0:
            ctk.CTkLabel(
                self.summaries_container,
                text="Nessuna serata per il filtro corrente.",
            ).pack(pady=20)

    def _create_summary_card(self, ds):
        """Crea una card cliccabile per una serata."""
        is_selected = (
            bool(self.filter_day)
            and ds.data_serata
            == f"{self.filter_year}-{self.filter_month}-{self.filter_day}"
        )

        bg_color = "#1e6eb4" if is_selected else "#2d2d2d"

        card = ctk.CTkFrame(
            self.summaries_container,
            fg_color=bg_color,
            corner_radius=6,
        )
        card.pack(fill="x", padx=5, pady=4)

        content = ctk.CTkFrame(card, fg_color="transparent")
        content.pack(fill="x", padx=10, pady=8)

        label_date = ctk.CTkLabel(
            content,
            text=f"📅 Serata: {ds.data_serata}",
            anchor="w",
            font=ctk.CTkFont(size=13),
        )
        label_date.pack(anchor="w")

        label_orders = ctk.CTkLabel(
            content,
            text=f"Ordini: {ds.numero_ordini} | Totale Incasso:",
            anchor="w",
            text_color="gray",
        )
        label_orders.pack(anchor="w")

        label_total = ctk.CTkLabel(
            content,
            text=f"€ {ds.totale_serata}",
            anchor="w",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        label_total.pack(anchor="w")

        # L'intera card è cliccabile
        click_handler = lambda event, ds=ds: self._on_summary_clicked(ds)

        for widget in (card, content, label_date, label_orders, label_total):
            self._bind_click(widget, click_handler)

    def _on_summary_clicked(self, ds):
        """Cliccando una serata si impostano i filtri e si ricarica la distinta."""
        parts = ds.data_serata.split("-")

        if len(parts) == 3:
            self.entry_year.delete(0, "end")
            self.entry_year.insert(0, parts[0])

            self.entry_month.delete(0, "end")
            self.entry_month.insert(0, parts[1])

            self.entry_day.delete(0, "end")
            self.entry_day.insert(0, parts[2])

        threading.Thread(
            target=self._load_aggregated_thread,
            args=(ds.data_serata,),
            daemon=True,
        ).start()

        self._render_summaries()  # aggiorna l'evidenziazione della card

    def _render_articles(self, pattern: str):
        """Disegna la distinta articoli nella colonna destra."""
        for widget in self.articles_container.winfo_children():
            widget.destroy()

        display_pattern = pattern if pattern else "Tutti"
        self.label_period.configure(
            text=f"Periodo selezionato: {display_pattern}"
        )

        if not self.aggregated_rows:
            ctk.CTkLabel(
                self.articles_container,
                text="Nessun articolo trovato per questo periodo.",
            ).pack(pady=20)
            return

        for row in self.aggregated_rows:
            ctk.CTkLabel(
                self.articles_container,
                text=f"• {row.descrizione}  [Qtà: {row.quantita_totale}]",
                anchor="w",
                wraplength=280,
                justify="left",
            ).pack(anchor="w", padx=5, pady=2)

    # ======================================================================
    # STAMPA
    # ======================================================================

    def _on_print_click(self):
        pattern = self._get_filter_pattern()
        printer_name = self.config_app.printer_name

        if not printer_name:
            self._set_status(
                "⚠️ Nessuna stampante selezionata! Vai in Configurazione."
            )
            return

        if not pattern:
            self._set_status("⚠️ Inserisci almeno mese e anno!")
            return

        threading.Thread(
            target=self._stampa_totali_thread,
            args=(pattern, printer_name),
            daemon=True,
        ).start()

    def _stampa_totali_thread(self, pattern: str, printer_name: str):
        """Compone il layout e lo invia alla stampante via PowerShell."""
        serata_selezionata = next(
            (
                s
                for s in self.daily_summaries
                if s.data_serata.startswith(pattern)
            ),
            None,
        )

        totale_incasso = (
            serata_selezionata.totale_serata
            if serata_selezionata
            else "0.00"
        )

        testo_stampa = self._costruisci_layout_stampa(
            pattern,
            totale_incasso,
            self.aggregated_rows,
        )

        temp_path = os.path.join(tempfile.gettempdir(), "stampa_totali.txt")

        try:
            # utf-8-sig (BOM) per far leggere correttamente gli accenti a PowerShell
            with open(temp_path, "w", encoding="utf-8-sig") as f:
                f.write(testo_stampa)
        except OSError as exc:
            error = str(exc)
            self.after(
                0,
                lambda: self._set_status(
                    f"❌ Errore creazione file temporaneo: {error}"
                ),
            )
            return

        escaped_path = temp_path.replace("'", "''")
        escaped_printer = printer_name.replace("'", "''")

        comando_ps = (
            f"Get-Content -Path '{escaped_path}' -Raw -Encoding UTF8 | "
            f"Out-Printer -Name '{escaped_printer}'"
        )

        self.after(
            0,
            lambda: self._set_status(f"Invio stampa a '{printer_name}'..."),
        )

        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", comando_ps],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )

            stderr = (result.stderr or "").strip()

            if result.returncode == 0 and not stderr:
                self.after(
                    0,
                    lambda: self._set_status(
                        f"✅ Stampa inviata con successo per {pattern}"
                    ),
                )
            else:
                detail = stderr if stderr else "Nessun errore"
                self.after(
                    0,
                    lambda: self._set_status(
                        f"❌ Errore stampa. Dettagli: {detail}"
                    ),
                )

        except Exception as exc:
            error = str(exc)
            self.after(
                0,
                lambda: self._set_status(
                    f"❌ Errore esecuzione PowerShell: {error}"
                ),
            )

        finally:
            try:
                os.remove(temp_path)
            except OSError:
                pass  # il file potrebbe essere già stato rimosso

    def _costruisci_layout_stampa(
        self,
        data: str,
        totale: str,
        articoli,
    ) -> str:
        """
        Costruisce il testo formattato per stampante termica 80mm.
        Larghezza standard: 32 caratteri.
        """
        larghezza = 32

        output = []

        linea_piena = "=" * larghezza
        linea_trattini = "-" * larghezza

        def centra(testo: str, larghezza: int) -> str:
            if len(testo) >= larghezza:
                return testo

            spazi = larghezza - len(testo)
            return (
                " " * (spazi // 2)
                + testo
                + " " * (spazi - spazi // 2)
            )

        def formatta_riga(desc: str, qta: int, larghezza: int) -> str:
            qta_str = f"x{qta}"
            spazio_desc = max(0, larghezza - len(qta_str) - 1)

            desc_troncata = (
                desc[:spazio_desc] if len(desc) > spazio_desc else desc
            )

            return f"{desc_troncata:<{spazio_desc}} {qta_str}"

        output.append(linea_piena)
        output.append(centra("TOTALI SERATA", larghezza))
        output.append(linea_piena)
        output.append("")
        output.append(f"Periodo: {data}")
        output.append(f"Totale: EUR {totale}")
        output.append("")
        output.append(linea_piena)
        output.append(centra("ARTICOLI VENDUTI", larghezza))
        output.append(linea_trattini)

        if not articoli:
            output.append(centra("Nessun articolo", larghezza))
        else:
            for articolo in articoli:
                output.append(
                    formatta_riga(
                        articolo.descrizione,
                        articolo.quantita_totale,
                        larghezza,
                    )
                )

        output.append(linea_trattini)
        output.append("")
        output.append(linea_piena)
        output.append(centra("Grazie e buona serata!", larghezza))
        output.append(linea_piena)
        output.append("\n\n\n")

        return "\n".join(output)


if __name__ == "__main__":
    app = SagraApp()
    app.mainloop()