# Smart CFO Assistant

Assistente desktop per contabilità, bilancio, controllo di gestione e finanza: si caricano fatture, bilanci o prospetti e si ottiene un'analisi strutturata, con tabelle e punti d'attenzione.

**[Prova la demo](https://andreapollastrelli95.github.io/smart-cfo-assistant/)** · Analisi rapide su documenti d'esempio, con risposte già pronte. Tutti i dati sono fittizi.

![Analisi degli scostamenti nella demo](docs/demo-1.png)

![Smart CFO Assistant](docs/screenshot-1.png)

## Cosa fa

- **Documenti in ingresso**: PDF, immagini (fatture fotografate), CSV ed Excel, letti e passati al modello insieme alla richiesta.
- **Analisi rapide pronte**: analisi di bilancio, scritture in partita doppia, lettura di una fattura, scostamenti budget/consuntivo, break-even point, rendiconto finanziario, indicatori finanziari.
- **Risposta in streaming** con vista formattata (tabelle, elenchi, avvisi) o Markdown, copia ed esportazione in HTML, Markdown e testo.
- **Uso attento della quota gratuita**: modello di riserva se il principale è al limite, pochi tentativi solo per errori temporanei, timeout per operazione.
- **Privacy**: avviso prima di inviare documenti; la chiave API si legge solo dalla variabile d'ambiente `GEMINI_API_KEY` e non viene mai salvata.
- Tema chiaro, scuro o di sistema.

Progetto di [Andrea Pollastrelli](https://andreapollastrelli95.github.io/).
