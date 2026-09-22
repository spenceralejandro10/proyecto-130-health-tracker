"""Instala un acceso de inicio automático para el cliente de escritorio en Windows.
Ejecutar manualmente una vez: python desktop/install_autostart_windows.py
"""
from pathlib import Path
import os
import sys

if os.name != "nt":
    raise SystemExit("Este instalador de autoinicio es solo para Windows.")

startup = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
client = Path(__file__).resolve().parent / "client.py"
bat = startup / "Proyecto130.bat"
bat.write_text(f'@echo off\nstart "" "{sys.executable}" "{client}"\n', encoding="utf-8")
print(f"Autoinicio instalado en: {bat}")
