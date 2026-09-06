"""Local masked-key setup window. No secrets are printed or sent to chat."""

import asyncio
import os
import re
import tempfile
from pathlib import Path
from queue import Empty, Queue
from threading import Thread

from app.config import Settings
from app.domain.exceptions import ProviderUnavailableError
from app.providers.tts.azure import AzureTextToSpeech

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = "Bok, ovdje Zvonko. Zovem da te podsjetim na dogovor. Možeš mi reći da te nazovem za petnaest minuta."


def save_configuration(path: Path, key: str, region: str) -> None:
    """Replace only Azure entries, preserving other settings and comments."""
    if not re.fullmatch(r"[A-Za-z0-9+/=_-]{16,256}", key):
        raise ValueError("Kopiraj Azure KEY 1 ili KEY 2, bez razmaka.")
    if not re.fullmatch(r"[a-z0-9]{2,40}", region):
        raise ValueError("Unesi oznaku regije, primjerice westeurope.")
    updates = {
        "AZURE_SPEECH_KEY": key,
        "AZURE_SPEECH_REGION": region,
        "AZURE_SPEECH_VOICE": "hr-HR-SreckoNeural",
        "AZURE_SPEECH_RATE_PERCENT": "-10",
        "TTS_PROVIDER": "azure",
    }
    original = path.read_text(encoding="utf-8-sig") if path.exists() else ""
    lines = []
    for line in original.splitlines():
        match = re.match(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
        if not match or match[1].upper() not in updates:
            lines.append(line)
    lines.extend(f"{name}={value}" for name, value in updates.items())
    # No backup copy containing secrets; replace atomically in the same directory.
    fd, temporary = tempfile.mkstemp(prefix=".azure-setup-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write("\n".join(lines) + "\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main() -> None:
    import tkinter as tk
    from tkinter import ttk

    window = tk.Tk()
    window.title("Zvonko — Azure glas")
    window.geometry("580x350")
    window.resizable(False, False)
    frame = ttk.Frame(window, padding=20)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="Azure Speech: hrvatski glas Srećko", font=("Segoe UI", 14)).pack(anchor="w")
    ttk.Label(frame, text="U Azureu otvori Speech resurs → Keys and Endpoint.").pack(anchor="w", pady=(8, 12))
    ttk.Label(frame, text="KEY 1 ili KEY 2 (unos je skriven):").pack(anchor="w")
    key = ttk.Entry(frame, show="*", width=70)
    key.pack(fill="x", pady=(4, 8))
    ttk.Label(frame, text="Regija (oznaka iz Azurea):").pack(anchor="w")
    region = ttk.Entry(frame, width=30)
    region.insert(0, "westeurope")
    region.pack(anchor="w", pady=(4, 10))
    status = tk.StringVar(value="Ključ se sprema samo u lokalni .env. Pozivi se ne pokreću.")
    ttk.Label(frame, textvariable=status, wraplength=530).pack(anchor="w", pady=8)
    results: Queue[str] = Queue()

    def save() -> None:
        try:
            save_configuration(ROOT / ".env", key.get().strip(), region.get().strip().lower())
        except ValueError as exc:
            status.set(str(exc))
            return
        except OSError:
            status.set("Ne mogu spremiti .env. Provjeri dopuštenja mape.")
            return
        key.delete(0, tk.END)
        status.set("Spremljeno. Možeš poslušati probnu rečenicu; troši Azure TTS kvotu, bez telefonskog poziva.")

    def generate() -> None:
        try:
            settings = Settings(_env_file=ROOT / ".env")
            audio = asyncio.run(AzureTextToSpeech(settings).synthesize(SAMPLE))
            target = ROOT / "zvonko-azure-preview.wav"
            target.write_bytes(audio)
            if os.name == "nt":
                import winsound

                winsound.PlaySound(str(target), winsound.SND_FILENAME)
            results.put("Proba je gotova. Audio: zvonko-azure-preview.wav. Telefonski pozivi još nisu uključeni.")
        except ProviderUnavailableError as exc:
            results.put(f"Proba nije uspjela: {exc}. Provjeri ključ, regiju i Azure kvotu.")
        except Exception:
            # Validation errors may embed inputs; never display their full representation.
            results.put("Proba nije uspjela. Provjeri konfiguraciju .env i mrežnu vezu.")

    def preview() -> None:
        preview_button.configure(state="disabled")
        status.set("Generiram i reproduciram kratku probnu rečenicu…")
        Thread(target=generate, daemon=True).start()

    def poll() -> None:
        try:
            status.set(results.get_nowait())
            preview_button.configure(state="normal")
        except Empty:
            pass
        window.after(200, poll)

    buttons = ttk.Frame(frame)
    buttons.pack(anchor="w", pady=8)
    ttk.Button(buttons, text="1. Spremi ključ i regiju", command=save).pack(side="left", padx=(0, 12))
    preview_button = ttk.Button(buttons, text="2. Poslušaj probu", command=preview)
    preview_button.pack(side="left")
    window.after(200, poll)
    window.mainloop()


if __name__ == "__main__":
    main()
