"""Smart CFO Assistant – interfaccia desktop CustomTkinter."""

from __future__ import annotations

import ctypes
import queue
import sys
import threading
import time
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

import ai_client
from ai_config import API_KEY_ENV, GEMINI_MODEL
from config_manager import ConfigManager
from document_loader import IMAGE_EXT, PDF_EXT, TABLE_EXT, Attachment, load_attachment
from markdown_render import render_panel_html, render_report_html, render_report_markdown

try:
    from tkinterweb import HtmlFrame
except Exception:  # rendering HTML non disponibile: si usa solo la vista testo
    HtmlFrame = None

APP_NAME = "Smart CFO Assistant"
BASE_DIR = Path(__file__).resolve().parent
ICON_PATH = BASE_DIR / "assets" / "smartcfo.ico"

AI_LABEL = "Google Gemini"
PRIVACY_NOTE = ("Piano gratuito: Google può usare i testi e i documenti inviati per migliorare i propri "
                "servizi. Evita di inviare dati personali, finanziari o sanitari non necessari.")

TEMPLATES = {
    "📊  Analisi di bilancio":
        "Esegui un'analisi completa del bilancio allegato: riclassifica lo Stato Patrimoniale secondo il "
        "criterio finanziario e il Conto Economico a valore aggiunto, calcola i principali indici di "
        "redditività (ROE, ROI, ROS), solidità e liquidità, e commenta l'andamento rispetto all'esercizio "
        "precedente se disponibile.",
    "📒  Scritture in partita doppia":
        "Registra in partita doppia le operazioni descritte nei documenti allegati (es. fatture di acquisto "
        "o vendita), indicando data, conti movimentati, importi in Dare e Avere e trattamento IVA. "
        "Verifica la quadratura.",
    "🧾  Lettura fattura":
        "Estrai i dati della fattura allegata (fornitore, cliente, P.IVA, numero, data, imponibile, "
        "aliquote e importo IVA, totale, scadenze) in una tabella, verifica la correttezza dei calcoli e "
        "proponi la relativa scrittura contabile.",
    "📉  Scostamenti budget/consuntivo":
        "Confronta budget e consuntivo dai dati allegati: calcola gli scostamenti totali e scomponili in "
        "effetto volume, prezzo e efficienza per ricavi e costi variabili. Evidenzia gli scostamenti "
        "favorevoli e sfavorevoli e le possibili cause.",
    "⚖️  Break-even point":
        "Calcola il punto di pareggio (BEP) in quantità e in fatturato, il margine di contribuzione "
        "unitario e percentuale, il margine di sicurezza e il grado di leva operativa.\n"
        "Dati: costi fissi = … €; prezzo unitario = … €; costo variabile unitario = … €; "
        "volumi previsti = … unità.",
    "💧  Rendiconto finanziario":
        "Redigi il rendiconto finanziario con metodo indiretto (OIC 10) a partire dai bilanci allegati, "
        "evidenziando i flussi della gestione operativa, di investimento e di finanziamento, e commenta la "
        "variazione della posizione finanziaria netta.",
    "🏦  Indicatori finanziari":
        "Calcola gli indicatori finanziari: PFN, PFN/EBITDA, PFN/PN, DSCR, copertura degli oneri "
        "finanziari, ciclo del circolante (DSO, DIO, DPO). Valuta la sostenibilità del debito e il merito "
        "creditizio dell'impresa.",
}

APPEARANCE = {"Scuro": "dark", "Chiaro": "light", "Sistema": "system"}
FILE_ICONS = {"pdf": "📄", "image": "🖼️", "table": "📊"}


def _ext_pattern(exts) -> str:
    return " ".join(f"*{e}" for e in sorted(exts))


class SmartCFOApp(ctk.CTk):
    def __init__(self):
        self.cfg = ConfigManager()
        ctk.set_appearance_mode(self.cfg.get("appearance", "dark"))
        ctk.set_default_color_theme("blue")
        super().__init__()

        self.title(APP_NAME)
        self.geometry("1280x820")
        self.minsize(980, 640)
        self.after(0, lambda: self.state("zoomed"))
        if ICON_PATH.exists() and sys.platform == "win32":
            self.iconbitmap(str(ICON_PATH))
            # CustomTkinter reimposta la propria icona dopo ~200 ms: la si riapplica.
            self.after(300, lambda: self.iconbitmap(str(ICON_PATH)))

        self.attachments: list[Attachment] = []
        self.response_md = ""
        self.last_prompt = ""
        self.last_meta = ("", "")
        self.events: queue.Queue = queue.Queue()
        self.stop_event = threading.Event()
        self.busy = False
        self._privacy_ack = False

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_sidebar()
        self._build_main()
        self._build_statusbar()

        self.bind("<Control-Return>", lambda e: self.on_send())
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self._refresh_key_status()
        self._render_response()
        self.after(60, self._poll_events)

    # ------------------------------------------------------------------ UI build
    def _build_sidebar(self):
        sb = ctk.CTkFrame(self, width=300, corner_radius=0)
        sb.grid(row=0, column=0, rowspan=2, sticky="nsew")
        sb.grid_propagate(False)
        sb.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(sb, text="Smart CFO", font=ctk.CTkFont(size=24, weight="bold")).grid(
            row=0, column=0, padx=20, pady=(22, 0), sticky="w")
        ctk.CTkLabel(sb, text="Contabilità · Bilancio · Controllo · Finanza",
                     font=ctk.CTkFont(size=12), text_color=("gray35", "gray65")).grid(
            row=1, column=0, padx=20, pady=(0, 16), sticky="w")

        self._section_label(sb, "Motore IA", 2)
        info = ctk.CTkFrame(sb)
        info.grid(row=3, column=0, padx=14, pady=(0, 12), sticky="ew")
        info.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(info, text=f"{AI_LABEL} · piano gratuito", font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=0, column=0, padx=10, pady=(8, 0), sticky="w")
        ctk.CTkLabel(info, text=f"Modello: {GEMINI_MODEL}", font=ctk.CTkFont(size=12),
                     text_color=("gray35", "gray65")).grid(row=1, column=0, padx=10, sticky="w")
        self.key_status = ctk.CTkLabel(info, text="", font=ctk.CTkFont(size=11), wraplength=250,
                                       justify="left", anchor="w")
        self.key_status.grid(row=2, column=0, padx=10, pady=(4, 0), sticky="ew")
        ctk.CTkLabel(info, text="⚠ " + PRIVACY_NOTE, font=ctk.CTkFont(size=11), wraplength=250,
                     justify="left", anchor="w", text_color=("#9a6700", "#e3b341")).grid(
            row=3, column=0, padx=10, pady=(6, 8), sticky="ew")

        self._section_label(sb, "Analisi rapide", 8)
        tpl = ctk.CTkScrollableFrame(sb, fg_color="transparent")
        tpl.grid(row=9, column=0, padx=10, pady=(0, 6), sticky="nsew")
        tpl.grid_columnconfigure(0, weight=1)
        sb.grid_rowconfigure(9, weight=1)
        for i, (name, text) in enumerate(TEMPLATES.items()):
            ctk.CTkButton(tpl, text=name, anchor="w", height=30, fg_color="transparent",
                          text_color=("gray15", "gray90"), hover_color=("gray80", "gray30"),
                          command=lambda t=text: self._apply_template(t)).grid(
                row=i, column=0, pady=1, sticky="ew")

        arow = ctk.CTkFrame(sb, fg_color="transparent")
        arow.grid(row=10, column=0, padx=20, pady=(4, 16), sticky="ew")
        ctk.CTkLabel(arow, text="Tema").pack(side="left")
        current = next((k for k, v in APPEARANCE.items() if v == self.cfg.get("appearance")), "Scuro")
        self.appearance_var = ctk.StringVar(value=current)
        ctk.CTkSegmentedButton(arow, values=list(APPEARANCE), variable=self.appearance_var,
                               command=self.on_appearance_change).pack(side="right")

    def _section_label(self, parent, text, row):
        ctk.CTkLabel(parent, text=text.upper(), font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=("gray40", "gray60")).grid(row=row, column=0, padx=20, pady=(4, 2), sticky="w")

    def _build_main(self):
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=0, column=1, sticky="nsew", padx=16, pady=(14, 6))
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(2, weight=1)

        # --- Documenti
        docs = ctk.CTkFrame(main)
        docs.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        docs.grid_columnconfigure(0, weight=1)
        head = ctk.CTkFrame(docs, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))
        ctk.CTkLabel(head, text="Documenti", font=ctk.CTkFont(size=15, weight="bold")).pack(side="left")
        ctk.CTkLabel(head, text="  PDF · PNG/JPG · CSV · XLSX", text_color=("gray40", "gray60"),
                     font=ctk.CTkFont(size=12)).pack(side="left")
        ctk.CTkButton(head, text="Svuota", width=70, height=28, fg_color="transparent", border_width=1,
                      text_color=("gray20", "gray85"), command=self.clear_files).pack(side="right")
        ctk.CTkButton(head, text="＋ Aggiungi file", width=120, height=28,
                      command=self.add_files).pack(side="right", padx=(0, 6))
        self.files_frame = ctk.CTkScrollableFrame(docs, height=72, fg_color=("gray92", "gray14"))
        # La scrollbar di CTk ha un'altezza minima di 200 px che impedirebbe un elenco compatto.
        self.files_frame._scrollbar.configure(height=0)
        self.files_frame.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 12))
        self.files_frame.grid_columnconfigure(1, weight=1)

        # --- Richiesta
        req = ctk.CTkFrame(main)
        req.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        req.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(req, text="Richiesta", font=ctk.CTkFont(size=15, weight="bold")).grid(
            row=0, column=0, padx=12, pady=(10, 4), sticky="w")
        self.prompt_box = ctk.CTkTextbox(req, height=110, wrap="word", font=ctk.CTkFont(size=14))
        self.prompt_box.grid(row=1, column=0, sticky="ew", padx=12)
        actions = ctk.CTkFrame(req, fg_color="transparent")
        actions.grid(row=2, column=0, sticky="ew", padx=12, pady=(6, 10))
        ctk.CTkLabel(actions, text="Ctrl+Invio per inviare", text_color=("gray40", "gray60"),
                     font=ctk.CTkFont(size=11)).pack(side="left")
        self.send_btn = ctk.CTkButton(actions, text="Analizza  ▶", width=150, height=34,
                                      font=ctk.CTkFont(size=14, weight="bold"), command=self.on_send)
        self.send_btn.pack(side="right")

        # --- Risposta
        resp = ctk.CTkFrame(main)
        resp.grid(row=2, column=0, sticky="nsew")
        resp.grid_columnconfigure(0, weight=1)
        resp.grid_rowconfigure(2, weight=1)
        rhead = ctk.CTkFrame(resp, fg_color="transparent")
        rhead.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))
        ctk.CTkLabel(rhead, text="Risposta", font=ctk.CTkFont(size=15, weight="bold")).pack(side="left")
        self.view_var = ctk.StringVar(value="Formattato" if HtmlFrame else "Markdown")
        self.view_switch = ctk.CTkSegmentedButton(rhead, values=["Formattato", "Markdown"],
                                                  variable=self.view_var, command=lambda v: self._show_view())
        self.view_switch.pack(side="left", padx=14)
        if not HtmlFrame:
            self.view_switch.configure(state="disabled")
        self.export_menu = ctk.CTkOptionMenu(rhead, values=["Report HTML…", "Markdown (.md)…", "Testo (.txt)…",
                                                            "Apri nel browser / Stampa PDF"],
                                             command=self.on_export, width=150, height=28)
        self.export_menu.set("Esporta ▾")
        self.export_menu.pack(side="right")
        ctk.CTkButton(rhead, text="Copia", width=70, height=28, command=self.copy_response).pack(
            side="right", padx=(0, 6))

        self.progress = ctk.CTkProgressBar(resp, mode="indeterminate", height=4)
        self.progress.grid(row=1, column=0, sticky="ew", padx=12)
        self.progress.grid_remove()

        self.view_host = ctk.CTkFrame(resp, fg_color="transparent")
        self.view_host.grid(row=2, column=0, sticky="nsew", padx=12, pady=(4, 12))
        self.view_host.grid_columnconfigure(0, weight=1)
        self.view_host.grid_rowconfigure(0, weight=1)
        self.raw_box = ctk.CTkTextbox(self.view_host, wrap="word", font=ctk.CTkFont(family="Consolas", size=13))
        self.raw_box.grid(row=0, column=0, sticky="nsew")
        self.raw_box.configure(state="disabled")
        self.html_view = None
        if HtmlFrame:
            scale = ctk.ScalingTracker.get_window_scaling(self)
            self.html_view = HtmlFrame(self.view_host, messages_enabled=False, fontscale=scale,
                                       on_link_click=webbrowser.open, vertical_scrollbar="auto",
                                       horizontal_scrollbar="auto")
            self.html_view.grid(row=0, column=0, sticky="nsew")
        self._show_view()

    def _build_statusbar(self):
        self.status = ctk.CTkLabel(self, text="Pronto", anchor="w", font=ctk.CTkFont(size=12),
                                   text_color=("gray35", "gray65"))
        self.status.grid(row=1, column=1, sticky="ew", padx=20, pady=(0, 8))

    # ------------------------------------------------------------------ chiave API
    def _refresh_key_status(self) -> bool:
        ok = ai_client.api_key_available()
        if ok:
            self.key_status.configure(text=f"✓ Chiave API trovata ({API_KEY_ENV})",
                                      text_color=("#1e7e34", "#4cc970"))
        else:
            self.key_status.configure(text=f"✗ Variabile {API_KEY_ENV} non impostata",
                                      text_color=("#c0392b", "#ff6b6b"))
        return ok

    # ------------------------------------------------------------------ file
    def add_files(self):
        paths = filedialog.askopenfilenames(
            parent=self, title="Seleziona documenti", initialdir=self.cfg.get("last_dir"),
            filetypes=[("Documenti supportati", _ext_pattern(PDF_EXT | IMAGE_EXT | TABLE_EXT)),
                       ("PDF", "*.pdf"), ("Immagini", _ext_pattern(IMAGE_EXT)),
                       ("Fogli di calcolo / CSV", _ext_pattern(TABLE_EXT)), ("Tutti i file", "*.*")])
        if not paths:
            return
        self.cfg.set("last_dir", str(Path(paths[0]).parent))
        self._set_status(f"Lettura di {len(paths)} file…")
        self.configure(cursor="watch")

        def work():
            for p in paths:
                try:
                    self.events.put(("file", load_attachment(p)))
                except Exception as e:
                    self.events.put(("file_error", f"{Path(p).name}: {e}"))
            self.events.put(("files_done", None))

        threading.Thread(target=work, daemon=True).start()

    def _render_files(self):
        for w in self.files_frame.winfo_children():
            w.destroy()
        if not self.attachments:
            ctk.CTkLabel(self.files_frame, text="Nessun documento caricato: puoi anche scrivere solo la richiesta.",
                         text_color=("gray45", "gray55")).grid(row=0, column=0, columnspan=3, padx=6, pady=6, sticky="w")
            return
        for i, att in enumerate(self.attachments):
            ctk.CTkLabel(self.files_frame, text=FILE_ICONS.get(att.kind, "📎")).grid(row=i, column=0, padx=(6, 4))
            info = att.summary + ("  ⚠ " + "; ".join(att.notes) if att.notes else "")
            ctk.CTkLabel(self.files_frame, text=f"{att.name}   ", font=ctk.CTkFont(weight="bold"),
                         anchor="w").grid(row=i, column=1, sticky="w")
            ctk.CTkLabel(self.files_frame, text=info, anchor="e", text_color=("gray35", "gray65"),
                         font=ctk.CTkFont(size=11)).grid(row=i, column=2, sticky="e", padx=6)
            ctk.CTkButton(self.files_frame, text="✕", width=26, height=22, fg_color="transparent",
                          text_color=("gray30", "gray75"), hover_color=("gray80", "gray30"),
                          command=lambda a=att: self.remove_file(a)).grid(row=i, column=3, padx=(0, 4), pady=1)

    def remove_file(self, att: Attachment):
        self.attachments.remove(att)
        self._render_files()

    def clear_files(self):
        self.attachments.clear()
        self._render_files()

    # ------------------------------------------------------------------ invio richiesta
    def _apply_template(self, text: str):
        self.prompt_box.delete("1.0", "end")
        self.prompt_box.insert("1.0", text)
        self.prompt_box.focus_set()

    def on_send(self):
        if self.busy:
            self.stop_event.set()
            self._set_status("Interruzione in corso…")
            return
        prompt = self.prompt_box.get("1.0", "end").strip()
        if not prompt and not self.attachments:
            messagebox.showinfo(APP_NAME, "Scrivi una richiesta o carica almeno un documento.", parent=self)
            return
        if not self._refresh_key_status():
            messagebox.showwarning(APP_NAME, ai_client.MISSING_KEY_MSG, parent=self)
            return
        if not self._privacy_ack:
            if not messagebox.askokcancel(
                    APP_NAME, PRIVACY_NOTE + "\n\nI documenti allegati e la richiesta verranno inviati a Google. "
                    "Continuare?", icon="warning", parent=self):
                return
            self._privacy_ack = True  # avviso mostrato una volta per sessione

        self.busy = True
        self.stop_event.clear()
        self.response_md = ""
        self.last_prompt = prompt or "Analizza i documenti allegati."
        self.last_meta = (AI_LABEL, GEMINI_MODEL)
        self._started = time.monotonic()
        self.send_btn.configure(text="■  Interrompi", fg_color=("#c0392b", "#a93226"),
                                hover_color=("#a93226", "#922b21"))
        self.progress.grid()
        self.progress.start()
        self.view_var.set("Markdown")
        self._show_view()
        self._set_raw("")
        self._set_status(f"Elaborazione con {GEMINI_MODEL}…")
        attachments = list(self.attachments)

        def work():
            try:
                for chunk in ai_client.stream_analysis(prompt, attachments, self.stop_event):
                    self.events.put(("reset", None) if chunk is ai_client.RESET else ("chunk", chunk))
                self.events.put(("done", self.stop_event.is_set()))
            except Exception as e:
                self.events.put(("error", ai_client.friendly_error(e)))

        threading.Thread(target=work, daemon=True).start()

    def _finish(self, status: str):
        self.busy = False
        self.progress.stop()
        self.progress.grid_remove()
        self.send_btn.configure(text="Analizza  ▶", fg_color=ctk.ThemeManager.theme["CTkButton"]["fg_color"],
                                hover_color=ctk.ThemeManager.theme["CTkButton"]["hover_color"])
        if HtmlFrame:
            self.view_var.set("Formattato")
        self._render_response()
        self._show_view()
        self._set_status(status)

    # ------------------------------------------------------------------ coda eventi dai thread
    def _poll_events(self):
        chunks = []
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "chunk":
                    chunks.append(payload)
                    continue
                if chunks:
                    self._append_chunks(chunks)
                    chunks = []
                if kind == "done":
                    words = len(self.response_md.split())
                    elapsed = time.monotonic() - self._started
                    self.last_meta = (AI_LABEL, ai_client.last_model_used)
                    self._finish(("Interrotto dall'utente" if payload else "Completato")
                                 + f" · {ai_client.last_model_used} · {words} parole · {elapsed:.1f} s")
                elif kind == "error":
                    if self.response_md:
                        self.response_md += "\n\n"
                    self.response_md += f"> ❌ **Errore:** {payload}"
                    self._finish("Errore durante l'elaborazione")
                elif kind == "reset":
                    self.response_md = ""
                    self._set_raw("")
                    self._set_status("Connessione interrotta: nuovo tentativo in corso…")
                elif kind == "file":
                    if all(a.path != payload.path for a in self.attachments):
                        self.attachments.append(payload)
                elif kind == "file_error":
                    messagebox.showerror(APP_NAME, f"Impossibile leggere il file:\n{payload}", parent=self)
                elif kind == "files_done":
                    self.configure(cursor="")
                    self._render_files()
                    self._set_status(f"{len(self.attachments)} documenti pronti")
        except queue.Empty:
            pass
        if chunks:
            self._append_chunks(chunks)
        self.after(50, self._poll_events)

    def _append_chunks(self, chunks):
        text = "".join(chunks)
        self.response_md += text
        self.raw_box.configure(state="normal")
        self.raw_box.insert("end", text)
        self.raw_box.see("end")
        self.raw_box.configure(state="disabled")

    # ------------------------------------------------------------------ visualizzazione risposta
    def _set_raw(self, text: str):
        self.raw_box.configure(state="normal")
        self.raw_box.delete("1.0", "end")
        self.raw_box.insert("1.0", text)
        self.raw_box.configure(state="disabled")

    def _is_dark(self) -> bool:
        return ctk.get_appearance_mode() == "Dark"

    def _render_response(self):
        text = self.response_md or (
            "## Benvenuto in Smart CFO Assistant\n\n"
            f"1. Carica fatture, bilanci o prospetti (PDF, immagini, CSV, Excel).\n"
            f"2. Scrivi la richiesta o usa un'**analisi rapida**, quindi premi **Analizza**.\n"
            f"3. La risposta arriva in streaming da **{AI_LABEL}** (`{GEMINI_MODEL}`).\n\n"
            "> I risultati generati dall'IA vanno sempre verificati prima dell'uso contabile o fiscale.")
        self._set_raw(self.response_md)
        if self.html_view:
            self.html_view.load_html(render_panel_html(text, self._is_dark()))

    def _show_view(self):
        if self.html_view and self.view_var.get() == "Formattato":
            self.html_view.tkraise()
        else:
            self.raw_box.tkraise()

    def on_appearance_change(self, label: str):
        mode = APPEARANCE[label]
        ctk.set_appearance_mode(mode)
        self.cfg.set("appearance", mode)
        if not self.busy:
            self.after(50, self._render_response)

    # ------------------------------------------------------------------ copia / esporta
    def copy_response(self):
        if not self.response_md:
            self._set_status("Nessuna risposta da copiare.")
            return
        self.clipboard_clear()
        self.clipboard_append(self.response_md)
        self._set_status("Risposta copiata negli appunti (Markdown).")

    def on_export(self, choice: str):
        self.export_menu.set("Esporta ▾")
        if not self.response_md:
            messagebox.showinfo(APP_NAME, "Nessuna risposta da esportare.", parent=self)
            return
        files = [a.name for a in self.attachments]
        provider, model = self.last_meta
        if choice.startswith("Apri"):
            out = Path(self.cfg.path.parent) / "ultimo_report.html"
            out.write_text(render_report_html(self.response_md, self.last_prompt, provider, model, files),
                           encoding="utf-8")
            webbrowser.open(out.as_uri())
            self._set_status("Report aperto nel browser: usa Ctrl+P → «Salva come PDF».")
            return
        ext, ftype = {"R": (".html", ("Report HTML", "*.html")), "M": (".md", ("Markdown", "*.md")),
                      "T": (".txt", ("Testo", "*.txt"))}[choice[0]]
        path = filedialog.asksaveasfilename(parent=self, defaultextension=ext, filetypes=[ftype],
                                            initialdir=self.cfg.get("last_dir"),
                                            initialfile=f"Report_SmartCFO{ext}")
        if not path:
            return
        if ext == ".html":
            content = render_report_html(self.response_md, self.last_prompt, provider, model, files)
        elif ext == ".md":
            content = render_report_markdown(self.response_md, self.last_prompt, provider, model, files)
        else:
            content = self.response_md
        Path(path).write_text(content, encoding="utf-8")
        self._set_status(f"Report esportato: {path}")

    # ------------------------------------------------------------------ varie
    def _set_status(self, text: str):
        self.status.configure(text=text)

    def on_close(self):
        self.stop_event.set()
        self.destroy()


def main():
    if sys.platform == "win32":
        try:  # icona propria nella barra delle applicazioni invece di quella di Python
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SmartCFO.Assistant")
        except Exception:
            pass
    app = SmartCFOApp()
    app._render_files()
    app.mainloop()


if __name__ == "__main__":
    main()
