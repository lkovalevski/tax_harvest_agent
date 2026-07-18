"""
run.py — Punto de entrada único del Tax Harvest Agent.

Uso:
    python run.py              # extrae PDFs de ./facturas y abre la interfaz
    python run.py --solo-app   # solo abre la interfaz (si ya extrajiste)
    python run.py --solo-agente # carga directamente sin revisar (¡cuidado!)
"""

import sys
import os
import webbrowser
import threading
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()  # carga .env automáticamente

CARPETA_FACTURAS = Path(os.getenv("CARPETA_FACTURAS", "./facturas"))
DATA_FILE        = "data/facturas.json"
PORT             = int(os.getenv("PORT", 5000))


def verificar_config():
    """Chequea que las variables de entorno necesarias estén seteadas."""
    errores = []
    if not os.getenv("ANTHROPIC_API_KEY"):
        errores.append("  ❌ ANTHROPIC_API_KEY no está configurada")
    if not os.getenv("AFIP_CUIT"):
        errores.append("  ❌ AFIP_CUIT no está configurado")
    if not os.getenv("AFIP_CLAVE"):
        errores.append("  ❌ AFIP_CLAVE no está configurada")

    if errores:
        print("\n⚠️  Faltan variables en el archivo .env:\n")
        for e in errores:
            print(e)
        print("\n  Copiá .env.example a .env y completá los valores.")
        sys.exit(1)


def crear_carpetas():
    """Crea la estructura de carpetas si no existe."""
    for d in ["facturas", "procesadas", "data"]:
        Path(d).mkdir(exist_ok=True)


def extraer_pdfs():
    """Paso 1: extrae datos de los PDFs y guarda en data/facturas.json."""
    from extractor import procesar_carpeta, guardar_facturas

    pdfs = list(CARPETA_FACTURAS.glob("*.pdf")) + list(CARPETA_FACTURAS.glob("*.PDF"))

    if not pdfs:
        print(f"\n⚠️  No hay PDFs en {CARPETA_FACTURAS}/")
        print("   Tirálos ahí y volvé a correr run.py\n")
        sys.exit(0)

    print(f"\n📂 Procesando {len(pdfs)} PDF(s) en {CARPETA_FACTURAS}/...\n")
    facturas = procesar_carpeta(str(CARPETA_FACTURAS))

    # Mantener facturas anteriores que ya fueron procesadas
    import json
    existentes = {}
    if Path(DATA_FILE).exists():
        with open(DATA_FILE, encoding="utf-8") as f:
            for fac in json.load(f):
                existentes[fac["archivo"]] = fac

    # Merge: no pisar las ya aprobadas/cargadas
    for fac in facturas:
        arch = fac["archivo"]
        if arch in existentes and existentes[arch]["estado"] in ("aprobado", "cargado"):
            facturas[facturas.index(fac)] = existentes[arch]

    guardar_facturas(facturas, DATA_FILE)
    return facturas


def abrir_browser():
    """Abre el browser después de un segundo (para que Flask arranque)."""
    time.sleep(1.2)
    webbrowser.open(f"http://localhost:{PORT}")


def lanzar_app():
    """Paso 2: arranca Flask y abre el browser."""
    from app import app

    print(f"\n🌐 Abriendo interfaz en http://localhost:{PORT}")
    print("   Revisá las facturas, aprobá las correctas y hacé click en 'Lanzar agente'.")
    print("   Ctrl+C para detener.\n")

    threading.Thread(target=abrir_browser, daemon=True).start()
    app.run(port=PORT, debug=False)


def lanzar_agente_directo():
    """Carga directamente sin pasar por la interfaz (modo avanzado)."""
    from agent import ARCAAgent

    cuit  = os.getenv("AFIP_CUIT")
    clave = os.getenv("AFIP_CLAVE")

    agente = ARCAAgent(cuit, clave)
    agente.procesar_facturas(DATA_FILE)
    agente.guardar_log("data/agent_log.json")


def banner():
    print("""
╔══════════════════════════════════════════╗
║   🌿  Tax Harvest Agent — ARCA/SiRADIG  ║
╚══════════════════════════════════════════╝""")


if __name__ == "__main__":
    banner()
    verificar_config()
    crear_carpetas()

    args = sys.argv[1:]

    if "--solo-agente" in args:
        print("⚡ Modo directo: cargando facturas aprobadas en ARCA...")
        lanzar_agente_directo()

    elif "--solo-app" in args:
        print("🖥  Abriendo interfaz sin re-extraer PDFs...")
        lanzar_app()

    else:
        # Flujo completo
        facturas = extraer_pdfs()
        pendientes = sum(1 for f in facturas if f.get("estado") == "pendiente")
        print(f"\n✅ Extracción completa. {pendientes} factura(s) pendientes de revisión.")
        lanzar_app()
