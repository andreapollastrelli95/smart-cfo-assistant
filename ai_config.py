"""Configurazione unica dell'assistente AI (Google Gemini, piano gratuito)."""

# Modello Flash più recente disponibile nel piano gratuito dell'API Gemini
# (fonte: aistudio.google.com/docs/models e /docs/pricing, novembre 2026).
GEMINI_MODEL = "gemini-3.8-flash"

# Modello di riserva (Flash stabile, gratuito, quota separata): usato solo se il principale
# ha raggiunto il limite gratuito (20 richieste/giorno) o è sovraccarico. "" per disattivarlo.
FALLBACK_MODEL = "gemini-3.6-flash"

# La chiave API viene letta solo da questa variabile d'ambiente.
API_KEY_ENV = "GEMINI_API_KEY"

# Ragionamento "low": meno token consumati e risposte più rapide (valori: low, medium, high).
THINKING_LEVEL = "low"
MAX_OUTPUT_TOKENS = 16384

# Rete: timeout per singola operazione e nuovi tentativi solo per errori temporanei del server (5xx).
# Pochi tentativi: anche le richieste fallite possono consumare la quota giornaliera gratuita.
REQUEST_TIMEOUT_S = 120
MAX_ATTEMPTS = 2
RETRY_BASE_DELAY_S = 2.0

# Limite complessivo dei dati inline (PDF e immagini) per richiesta: l'API accetta fino a 20 MB.
INLINE_DATA_LIMIT = 18 * 1024 * 1024
