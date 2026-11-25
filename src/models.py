"""
Modelli dati dell'applicazione.
"""
from dataclasses import dataclass


@dataclass
class DailySummary:
    data_serata: str
    totale_serata: str
    numero_ordini: int


@dataclass
class AggregatedRow:
    descrizione: str
    quantita_totale: int