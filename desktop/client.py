"""Cliente de escritorio de solo lectura + acciones de recordatorios.

No edita mediciones. Consulta el dashboard y permite responder a recordatorios.
"""
from __future__ import annotations

import json
import os
import tkinter as tk
import urllib.error
import urllib.request
from datetime import datetime

API_URL = os.getenv("PROJECT130_API_URL", "http://127.0.0.1:8000").rstrip("/")
API_KEY = os.getenv("PROJECT130_API_KEY", "")
POLL_MS = int(os.getenv("PROJECT130_POLL_MS", "60000"))


def request_json(path: str, method: str = "GET", payload: dict | None = None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f"{API_URL}{path}", data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if API_KEY:
        req.add_header("X-API-Key", API_KEY)
    with urllib.request.urlopen(req, timeout=5) as response:
        return json.loads(response.read().decode())


class Widget:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Proyecto 130")
        self.root.attributes("-topmost", True)
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)
        self.expanded = False
        self.last_due_ids: set[int] = set()

        self.frame = tk.Frame(self.root, padx=14, pady=10, bg="#ffffff", highlightthickness=1, highlightbackground="#d8e0e4")
        self.frame.pack(fill="both", expand=True)
        self.title = tk.Label(self.frame, text="Proyecto 130", font=("Segoe UI", 9, "bold"), bg="#ffffff", fg="#50616a")
        self.title.pack(anchor="w")
        self.summary = tk.Label(self.frame, text="Sincronizando…", font=("Segoe UI", 11, "bold"), bg="#ffffff", fg="#1e3039", justify="left")
        self.summary.pack(anchor="w", pady=(4, 0))
        self.detail = tk.Label(self.frame, text="", font=("Segoe UI", 8), bg="#ffffff", fg="#64747c", justify="left")
        self.detail.pack(anchor="w", pady=(2, 0))
        self.actions = tk.Frame(self.frame, bg="#ffffff")
        self.toggle = tk.Button(self.actions, text="Detalles", command=self.toggle_expand)
        self.toggle.pack(side="left")
        self.hide_btn = tk.Button(self.actions, text="Ocultar 30 min", command=self.hide_temporarily)
        self.hide_btn.pack(side="left", padx=(5,0))
        self.actions.pack(anchor="e", pady=(8, 0))
        self.position_bottom_right()
        self.refresh()

    def position_bottom_right(self):
        self.root.update_idletasks()
        w, h = 330, 125
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry(f"{w}x{h}+{sw-w-24}+{sh-h-72}")

    def toggle_expand(self):
        self.expanded = not self.expanded
        self.root.geometry("390x220" if self.expanded else "330x125")

    def hide_temporarily(self):
        self.root.withdraw()
        self.root.after(30 * 60 * 1000, self.show_again)

    def show_again(self):
        self.root.deiconify()
        self.position_bottom_right()

    def refresh(self):
        try:
            d = request_json("/api/dashboard")
            weight = "—" if d["current_weight_kg"] is None else f'{d["current_weight_kg"]:.1f} kg'
            day = "inicio pendiente" if not d["day_number"] else f'Día {d["day_number"]}/130'
            self.summary.config(text=f"{day} · {weight} · {d['activity_minutes_today']:.0f} min hoy")
            next_text = d["next_reminder"]["title"] if d.get("next_reminder") else "Sin recordatorio próximo"
            self.detail.config(text=f"{next_text}\n{d['operational_message'] if self.expanded else ''}")
            self.title.config(text=f"Proyecto 130 · actualizado {datetime.now().strftime('%H:%M')}")
            self.check_due()
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            self.title.config(text="Proyecto 130 · sin conexión")
            self.detail.config(text=f"Se conserva el último estado visible. {type(exc).__name__}")
        finally:
            self.root.after(POLL_MS, self.refresh)

    def check_due(self):
        try:
            due = request_json("/api/reminders/due")
        except Exception:
            return
        for item in due:
            if item["id"] in self.last_due_ids:
                continue
            self.last_due_ids.add(item["id"])
            self.show_reminder(item)

    def show_reminder(self, item: dict):
        win = tk.Toplevel(self.root)
        win.title("Recordatorio Proyecto 130")
        win.attributes("-topmost", True)
        tk.Label(win, text=item["title"], font=("Segoe UI", 11, "bold"), padx=18, pady=14).pack()
        buttons = tk.Frame(win, padx=12, pady=10)
        buttons.pack()
        for label, action in (("Hecho", "done"), ("Posponer", "snooze"), ("Descartar hoy", "dismiss")):
            tk.Button(buttons, text=label, command=lambda a=action: self.respond(item["id"], a, win)).pack(side="left", padx=4)

    def respond(self, reminder_id: int, action: str, win: tk.Toplevel):
        try:
            request_json(f"/api/reminders/{reminder_id}/event", "POST", {"action": action})
        except Exception as exc:
            win.title(f"No se pudo guardar: {type(exc).__name__}")
            return
        if action == "snooze":
            self.last_due_ids.discard(reminder_id)
        win.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    Widget().run()
