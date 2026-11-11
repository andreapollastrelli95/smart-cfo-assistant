"""Caricamento e preparazione dei documenti allegati (PDF, immagini, CSV, Excel)."""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageOps
from pypdf import PdfReader

PDF_EXT = {".pdf"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
TABLE_EXT = {".csv", ".txt", ".xlsx", ".xlsm"}
SUPPORTED_EXT = PDF_EXT | IMAGE_EXT | TABLE_EXT

MAX_TEXT_CHARS = 150_000      # testo massimo per singolo allegato
MAX_IMAGE_SIDE = 2000         # lato massimo immagini inviate ai modelli vision
MAX_PDF_IMAGES = 12           # immagini estratte da PDF scansionati
MIN_CHARS_PER_PAGE = 40       # sotto questa soglia il PDF è considerato scansionato


@dataclass
class Attachment:
    path: Path
    kind: str                                     # "pdf" | "image" | "table"
    text: str = ""
    images: list[tuple[bytes, str]] = field(default_factory=list)   # (dati, mime)
    raw: bytes | None = None                      # PDF originale, per i provider che lo leggono nativamente
    pages: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def summary(self) -> str:
        if self.kind == "pdf":
            info = f"PDF · {self.pages} pag. · {len(self.text):,} caratteri".replace(",", ".")
            if self.images:
                info += f" · {len(self.images)} immagini (scansione)"
            return info
        if self.kind == "image":
            return "Immagine (richiede un modello vision)"
        return f"Tabella · {len(self.text):,} caratteri".replace(",", ".")


def _prepare_image(img: Image.Image) -> tuple[bytes, str]:
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "L"):
        background = Image.new("RGB", img.size, "white")
        rgba = img.convert("RGBA")
        background.paste(rgba, mask=rgba.split()[-1])
        img = background
    img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE), Image.LANCZOS)
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=90, optimize=True)
    return buf.getvalue(), "image/jpeg"


def _truncate(text: str, notes: list[str]) -> str:
    if len(text) > MAX_TEXT_CHARS:
        notes.append(f"Testo troncato a {MAX_TEXT_CHARS:,} caratteri".replace(",", "."))
        return text[:MAX_TEXT_CHARS] + "\n[... contenuto troncato ...]"
    return text


def _load_pdf(path: Path) -> Attachment:
    raw = path.read_bytes()
    reader = PdfReader(io.BytesIO(raw))
    if reader.is_encrypted and not reader.decrypt(""):
        raise ValueError("PDF protetto da password")
    att = Attachment(path, "pdf", raw=raw, pages=len(reader.pages))
    chunks = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            txt = (page.extract_text() or "").strip()
        except Exception:
            txt = ""
        if txt:
            chunks.append(f"--- Pagina {i} ---\n{txt}")
    att.text = _truncate("\n\n".join(chunks), att.notes)

    # PDF scansionato (poco testo): estrae le immagini di pagina per i modelli vision.
    if len(att.text) < MIN_CHARS_PER_PAGE * max(att.pages, 1):
        for page in reader.pages:
            try:
                for img in page.images:
                    if len(att.images) >= MAX_PDF_IMAGES:
                        break
                    att.images.append(_prepare_image(img.image))
            except Exception:
                continue
            if len(att.images) >= MAX_PDF_IMAGES:
                break
        att.notes.append("PDF con poco testo estraibile: probabilmente scansionato")
    return att


def _load_image(path: Path) -> Attachment:
    with Image.open(path) as img:
        img.load()
        data = _prepare_image(img)
    return Attachment(path, "image", images=[data])


def _read_text_file(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _load_table(path: Path) -> Attachment:
    att = Attachment(path, "table")
    if path.suffix.lower() in (".csv", ".txt"):
        att.text = _truncate(_read_text_file(path), att.notes)
        return att

    import pandas as pd  # import pesante: solo quando serve

    sheets = pd.read_excel(path, sheet_name=None, header=None, dtype=object)
    parts = []
    for name, df in sheets.items():
        df = df.dropna(how="all").dropna(axis=1, how="all")
        if df.empty:
            continue
        csv = df.to_csv(sep=";", index=False, header=False, decimal=",")
        parts.append(f"## Foglio: {name} ({df.shape[0]} righe x {df.shape[1]} colonne)\n{csv}")
    att.text = _truncate("\n\n".join(parts) or "(file Excel vuoto)", att.notes)
    return att


def load_attachment(path: str | Path) -> Attachment:
    path = Path(path)
    ext = path.suffix.lower()
    if ext in PDF_EXT:
        return _load_pdf(path)
    if ext in IMAGE_EXT:
        return _load_image(path)
    if ext in TABLE_EXT:
        return _load_table(path)
    raise ValueError(f"Formato non supportato: {ext}")
