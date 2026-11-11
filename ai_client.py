"""Unico punto di accesso all'AI dell'app: Google Gemini tramite l'SDK ufficiale google-genai."""

from __future__ import annotations

import os
import re
import sys
import threading
import time
from typing import Iterator

import httpx
from google import genai
from google.genai import errors, types

import ai_config as cfg
from document_loader import Attachment

SYSTEM_PROMPT = """Sei "Smart CFO Assistant", un esperto di contabilità, bilancio, controllo di gestione e finanza d'impresa, con riferimento alla normativa italiana (Codice Civile artt. 2423-2435-ter, principi contabili OIC) e, quando pertinente, agli IFRS.

Linee guida:
- Rispondi in italiano, in modo professionale e strutturato, usando Markdown (titoli, elenchi, tabelle).
- Scritture contabili in partita doppia: presentale in tabella con colonne Data | Conto | Dare | Avere, con conti del piano dei conti civilistico, IVA separata ove applicabile, e verifica che Dare = Avere.
- Analisi di bilancio: riclassifica Stato Patrimoniale (criterio finanziario o funzionale) e Conto Economico (a valore aggiunto o a costo del venduto) e calcola gli indici (ROE, ROI, ROS, ROA, rotazione capitale investito, current ratio, quick ratio, indice di indebitamento, margine di struttura, PFN/EBITDA, DSO, DPO, DIO, ciclo monetario) mostrando le formule.
- Controllo di gestione: per scostamenti distingui effetto volume, prezzo/costo ed efficienza (mix se rilevante), indicando se favorevoli (F) o sfavorevoli (S); per il BEP mostra margine di contribuzione unitario, BEP in quantità e fatturato, margine di sicurezza e leva operativa.
- Mostra sempre i passaggi di calcolo e le unità di misura (€, %, giorni). Usa il formato numerico italiano (1.234,56 €).
- Scrivi formule e calcoli in testo semplice (es. ROE = Utile netto / Patrimonio netto = 60.000 / 600.000 = 10%), senza LaTeX né simboli $.
- Dichiara esplicitamente le ipotesi quando i dati sono incompleti e segnala eventuali incongruenze nei documenti.
- Concludi con una breve sintesi e, se utile, raccomandazioni operative.
- Non inventare dati che non sono presenti nei documenti forniti."""

MISSING_KEY_MSG = (
    f"Chiave API Gemini non trovata. Crea una chiave gratuita su https://aistudio.google.com/apikey, "
    f"poi in PowerShell esegui:  setx {cfg.API_KEY_ENV} \"la-tua-chiave\"  e riavvia l'app.")

_TRANSIENT_CODES = {500, 502, 503, 504}
_OVERLOAD_PAUSE_S = 60   # dopo un sovraccarico persistente il modello principale viene saltato per 1 minuto

# Segnale emesso dallo stream quando la risposta parziale va scartata perché la richiesta viene ripetuta.
RESET = "\x00reset\x00"

# Modello effettivamente usato per l'ultima risposta (principale o di riserva).
last_model_used = cfg.GEMINI_MODEL
# Modelli temporaneamente esclusi (limite raggiunto o sovraccarico): nome -> istante di sblocco.
_blocked_until: dict[str, float] = {}


class AIError(Exception):
    """Errore con messaggio in italiano pronto per l'utente."""


class _ModelUnavailable(Exception):
    """Il modello non può rispondere ora (limite, sovraccarico, non trovato): si prova il successivo."""

    def __init__(self, original: Exception, pause_s: float):
        super().__init__(str(original))
        self.original, self.pause_s = original, pause_s


# ----------------------------------------------------------------------------- chiave e client
def _read_api_key() -> str:
    key = os.environ.get(cfg.API_KEY_ENV, "").strip()
    if not key and sys.platform == "win32":
        # Variabile impostata con setx dopo l'avvio di Esplora risorse: la si legge dal registro utente.
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                key = str(winreg.QueryValueEx(k, cfg.API_KEY_ENV)[0]).strip()
        except OSError:
            pass
    return key


def api_key_available() -> bool:
    return bool(_read_api_key())


_client_lock = threading.Lock()
_client: genai.Client | None = None
_client_key = ""


def _get_client() -> genai.Client:
    global _client, _client_key
    key = _read_api_key()
    if not key:
        raise AIError(MISSING_KEY_MSG)
    with _client_lock:
        if _client is None or key != _client_key:
            _client = genai.Client(api_key=key, http_options=types.HttpOptions(
                timeout=cfg.REQUEST_TIMEOUT_S * 1000))
            _client_key = key
        return _client


# ----------------------------------------------------------------------------- contenuto richiesta
def compose_user_text(prompt: str, attachments: list[Attachment], native_pdf: set[int]) -> str:
    """Testo della richiesta con il contenuto estratto degli allegati non inviati in formato nativo."""
    parts = []
    for i, att in enumerate(attachments, start=1):
        header = f"### Allegato {i}: {att.name}"
        if att.kind == "pdf" and id(att) in native_pdf:
            parts.append(f"{header} (PDF allegato in formato originale, {att.pages} pagine)")
        elif att.kind == "pdf":
            body = att.text or "(nessun testo estraibile)"
            if att.images:
                body += f"\n\n[Allegate {len(att.images)} immagini delle pagine scansionate]"
            parts.append(f"{header} (testo estratto dal PDF)\n{body}")
        elif att.kind == "image":
            parts.append(f"{header} (immagine allegata: analizzala visivamente)")
        else:
            parts.append(f"{header} (dati tabellari)\n```csv\n{att.text}\n```")
    request = prompt.strip() or "Analizza i documenti allegati."
    if parts:
        return "## Documenti forniti\n\n" + "\n\n".join(parts) + "\n\n## Richiesta\n\n" + request
    return request


def _build_contents(prompt: str, attachments: list[Attachment]) -> list:
    """PDF e immagini inline entro il limite di dimensione; oltre, i PDF passano come testo estratto."""
    parts, native, budget = [], set(), cfg.INLINE_DATA_LIMIT
    for att in attachments:
        if att.kind == "pdf" and att.raw and len(att.raw) <= budget:
            parts.append(types.Part.from_bytes(data=att.raw, mime_type="application/pdf"))
            native.add(id(att))
            budget -= len(att.raw)
            continue
        for data, mime in att.images:
            if len(data) <= budget:
                parts.append(types.Part.from_bytes(data=data, mime_type=mime))
                budget -= len(data)
    parts.append(compose_user_text(prompt, attachments, native))
    return parts


# ----------------------------------------------------------------------------- errori
def _is_transient(e: Exception) -> bool:
    return isinstance(e, errors.APIError) and e.code in _TRANSIENT_CODES


def _retry_delay_s(e: errors.APIError) -> float | None:
    """Attesa suggerita da Google (RetryInfo.retryDelay o «Please retry in …»), in secondi."""
    try:
        for d in (e.details or {}).get("error", {}).get("details", []):
            if str(d.get("@type", "")).endswith("RetryInfo") and d.get("retryDelay"):
                return float(str(d["retryDelay"]).rstrip("s"))
    except (AttributeError, TypeError, ValueError):
        pass
    m = re.search(r"retry in (?:(\d+)h)?(?:(\d+)m)?([\d.]+)s", e.message or "")
    if m:
        h, mi, sec = m.groups()
        return int(h or 0) * 3600 + int(mi or 0) * 60 + float(sec)
    return None


def _wait_text(seconds: float | None) -> str:
    if not seconds:
        return ""
    if seconds >= 3600:
        return f" (circa {round(seconds / 3600)} ore)"
    if seconds >= 90:
        return f" (circa {round(seconds / 60)} minuti)"
    return f" (circa {max(1, round(seconds))} secondi)"


def friendly_error(e: Exception) -> str:
    if isinstance(e, AIError):
        return str(e)
    if isinstance(e, errors.APIError):
        msg = f"{e.status or ''} {e.message or ''}"
        if e.code == 429:
            wait = _wait_text(_retry_delay_s(e))
            if "PerDay" in msg or "per day" in msg.lower():
                return ("Limite giornaliero gratuito di Gemini raggiunto. Riprova più tardi" + wait
                        + ": i limiti si azzerano ogni giorno alle 9:00 circa, ora italiana.")
            return ("Limite gratuito di Gemini raggiunto (troppe richieste o documenti troppo grandi "
                    "in poco tempo). Attendi e riprova" + (wait or " (circa un minuto)") + ".")
        if "API_KEY_INVALID" in msg or "API key not valid" in msg or "API key expired" in msg:
            return (f"La chiave in {cfg.API_KEY_ENV} non è valida o è scaduta. Creane una nuova su "
                    "https://aistudio.google.com/apikey, aggiorna la variabile e riavvia l'app.")
        if e.code == 403:
            return ("La chiave API non è autorizzata a usare l'API Gemini. Verifica il progetto della chiave "
                    "su https://aistudio.google.com/apikey.")
        if e.code == 404:
            return (f"Il modello «{cfg.GEMINI_MODEL}» non è disponibile. Aggiorna GEMINI_MODEL in ai_config.py "
                    "con un modello Flash attuale.")
        if "location is not supported" in msg.lower():
            return "L'API Gemini gratuita non è disponibile nel Paese da cui ti connetti."
        if e.code in _TRANSIENT_CODES:
            return "Il servizio Gemini è temporaneamente sovraccarico o non disponibile. Riprova tra qualche minuto."
        if e.code == 400:
            return f"Richiesta rifiutata da Gemini (documenti troppo grandi o non validi?): {e.message}"
        return f"Errore Gemini ({e.code}): {e.message}"
    if isinstance(e, httpx.TimeoutException):
        return (f"Gemini non ha risposto entro {cfg.REQUEST_TIMEOUT_S} secondi. Controlla la connessione "
                "o prova con documenti più piccoli.")
    if isinstance(e, (httpx.ConnectError, httpx.NetworkError)):
        return "Nessuna connessione a Internet (o Google non raggiungibile). Controlla la rete e riprova."
    return f"Errore imprevisto: {type(e).__name__}: {e}"


# ----------------------------------------------------------------------------- generazione
def _stream_model(client: genai.Client, model: str, contents: list, config: types.GenerateContentConfig,
                  stop_event: threading.Event, can_switch: bool) -> Iterator[str]:
    for attempt in range(1, cfg.MAX_ATTEMPTS + 1):
        produced = False
        finish = block = None
        try:
            for chunk in client.models.generate_content_stream(model=model, contents=contents, config=config):
                if stop_event.is_set():
                    return
                if chunk.prompt_feedback and chunk.prompt_feedback.block_reason:
                    block = chunk.prompt_feedback.block_reason
                if chunk.candidates and chunk.candidates[0].finish_reason:
                    finish = chunk.candidates[0].finish_reason
                text = chunk.text if chunk.candidates else None
                if text:
                    produced = True
                    yield text
        except Exception as e:
            if stop_event.is_set():
                raise AIError(friendly_error(e)) from None
            if produced:
                # Interruzione a metà risposta: un solo nuovo tentativo, che sostituisce il testo parziale.
                if _is_transient(e) and attempt < cfg.MAX_ATTEMPTS:
                    yield RESET
                    stop_event.wait(cfg.RETRY_BASE_DELAY_S)
                    continue
                if _is_transient(e) and can_switch:  # ancora interrotto: si passa al modello di riserva
                    yield RESET
                    raise _ModelUnavailable(e, _OVERLOAD_PAUSE_S) from None
                raise AIError(friendly_error(e)) from None
            if _is_transient(e) and attempt < cfg.MAX_ATTEMPTS:
                stop_event.wait(cfg.RETRY_BASE_DELAY_S * 2 ** (attempt - 1))
                continue
            if isinstance(e, errors.APIError) and e.code == 429:
                raise _ModelUnavailable(e, _retry_delay_s(e) or 60) from None
            if isinstance(e, errors.APIError) and e.code == 404:
                raise _ModelUnavailable(e, 24 * 3600) from None
            if _is_transient(e):
                raise _ModelUnavailable(e, _OVERLOAD_PAUSE_S) from None
            raise AIError(friendly_error(e)) from None
        if block or (not produced and finish in (types.FinishReason.SAFETY, types.FinishReason.PROHIBITED_CONTENT)):
            raise AIError("Gemini ha bloccato la richiesta per i filtri di sicurezza. Riformula la richiesta.")
        if not produced:
            raise AIError("Gemini non ha restituito testo. Riprova o riformula la richiesta.")
        if finish == types.FinishReason.MAX_TOKENS:
            yield "\n\n> ⚠️ Risposta interrotta per raggiunto limite di lunghezza."
        return


def stream_analysis(prompt: str, attachments: list[Attachment], stop_event: threading.Event) -> Iterator[str]:
    """Genera la risposta in streaming. Solleva AIError con un messaggio in italiano."""
    global last_model_used
    client = _get_client()
    contents = _build_contents(prompt, attachments)
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        max_output_tokens=cfg.MAX_OUTPUT_TOKENS,
        thinking_config=types.ThinkingConfig(thinking_level=cfg.THINKING_LEVEL),
    )
    models = [m for m in dict.fromkeys((cfg.GEMINI_MODEL, cfg.FALLBACK_MODEL)) if m]
    last_error: Exception | None = None
    for i, model in enumerate(models):
        is_last = i == len(models) - 1
        if not is_last and _blocked_until.get(model, 0) > time.monotonic():
            continue  # limite già noto: niente chiamata inutile
        try:
            first = True
            for text in _stream_model(client, model, contents, config, stop_event, can_switch=not is_last):
                if text is RESET:
                    first = True
                    yield RESET
                    continue
                if first:
                    first = False
                    last_model_used = model
                    if model != cfg.GEMINI_MODEL:
                        yield (f"> ℹ️ Il modello principale {cfg.GEMINI_MODEL} ha raggiunto il limite gratuito "
                               f"o è sovraccarico: risposta generata con il modello di riserva {model}.\n\n")
                yield text
            return
        except _ModelUnavailable as e:
            _blocked_until[model] = time.monotonic() + e.pause_s
            last_error = e.original
    raise AIError(friendly_error(last_error) if last_error else "Nessun modello Gemini disponibile.")
