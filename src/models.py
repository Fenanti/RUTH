"""
Modelli dati per l'API Gemini.
Equivalent to model.rs
"""
from dataclasses import dataclass, field


@dataclass
class DailySummary:
    data_serata: str
    totale_serata: str
    numero_ordini: int


@dataclass
class AggregatedRow:
    descrizione: str
    quantita_totale: int


# --- Modelli API Gemini ---

@dataclass
class Part:
    text: str


@dataclass
class Content:
    parts: list[Part] = field(default_factory=list)


@dataclass
class RequestBody:
    contents: list[Content] = field(default_factory=list)


@dataclass
class ResponsePart:
    text: str


@dataclass
class ResponseContent:
    parts: list[ResponsePart] = field(default_factory=list)


@dataclass
class Candidate:
    content: ResponseContent


@dataclass
class ApiResponse:
    candidates: list[Candidate] | None = None