"""
Client per l'API Gemini.
Equivalent to api.rs
"""
import requests
from .models import RequestBody, Content, Part


def call_gemini(api_key: str, prompt: str) -> str:
    """
    Chiama l'API Gemini e restituisce il testo della risposta.
    Solleva un'eccezione se la risposta non è valida.
    """
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-3.8-flash:generateContent?key={api_key}"
    )

    body = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ]
    }

    response = requests.post(url, json=body, timeout=30)
    response.raise_for_status()

    data = response.json()
    candidates = data.get("candidates")
    if candidates and len(candidates) > 0:
        parts = candidates[0].get("content", {}).get("parts", [])
        if parts and len(parts) > 0:
            return parts[0].get("text", "")

    raise ValueError("Risposta non valida dall'API")