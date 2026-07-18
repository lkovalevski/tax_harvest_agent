"""
extractor.py — Lee PDFs de facturas y extrae los datos clave usando OpenAI GPT-4o.
Etapa 1: solo PDFs. Etapa 2 (futura): imágenes.
"""

import os
import json
import base64
from pathlib import Path
import pdfplumber
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()  # carga las variables del .env (OPENAI_API_KEY, etc.)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL      = os.getenv("MODEL", "gpt-4o")
MAX_TOKENS = int(os.getenv("MAX_TOKENS", 800))


def pdf_to_text(pdf_path: str) -> str:
    """Extrae texto plano de un PDF con pdfplumber."""
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text.strip()


def pdf_to_base64_png(pdf_path: str) -> list[str]:
    """
    Convierte cada página del PDF a imagen PNG en base64.
    Usado como fallback cuando el PDF es escaneado (poco texto).
    Requiere: pip install pdf2image
    """
    try:
        from pdf2image import convert_from_path
        pages = convert_from_path(pdf_path, dpi=150)
        result = []
        for page in pages:
            import io
            buf = io.BytesIO()
            page.save(buf, format="PNG")
            result.append(base64.b64encode(buf.getvalue()).decode("utf-8"))
        return result
    except ImportError:
        return []


PROMPT = """Sos un asistente especializado en facturas argentinas para el sistema ARCA/AFIP.

Analizá esta factura y extraé los siguientes campos en formato JSON exacto:

{
  "cuit_emisor": "XX-XXXXXXXX-X (con guiones, ej: 33-64336846-9)",
  "denominacion": "Nombre/razón social del emisor",
  "tipo_comprobante": "Factura A|B|C|Recibo|Ticket",
  "numero_comprobante": "XXXX-XXXXXXXX (ej: 0003-00058551)",
  "fecha": "DD/MM/AAAA",
  "monto": 999999.99,
  "periodo": "Enero|Febrero|...|Diciembre",
  "tipo_gasto": "Servicios con fines educativos|Herramientas educativas|Útiles escolares",
  "familiar_apellido": "Apellido del familiar o null",
  "familiar_nombre": "Nombre del familiar o null",
  "observaciones": "Datos adicionales relevantes"
}

REGLAS:
- cuotas/escolaridad → "Servicios con fines educativos"
- libros/útiles/herramientas → "Herramientas educativas"
- periodo: buscá el mes en la descripción (ej: "Mayo-26" → "Mayo"); si no hay, usá el mes de la fecha
- monto: número sin símbolo $, sin puntos de miles (ej: 270990.00)
- Respondé SOLO con el JSON, sin explicaciones ni backticks"""


def extract_invoice_data(pdf_path: str) -> dict:
    """
    Extrae los campos necesarios para cargar en ARCA F572.
    Intenta primero con texto; si el PDF está escaneado, usa visión.
    """
    texto = pdf_to_text(str(pdf_path))
    usar_vision = len(texto) < 100

    if usar_vision:
        # PDF escaneado: convertir a imágenes y usar vision
        imagenes_b64 = pdf_to_base64_png(str(pdf_path))
        if not imagenes_b64:
            raise ValueError("PDF sin texto y pdf2image no instalado. Corré: pip install pdf2image poppler-utils")

        content = [{"type": "text", "text": PROMPT}]
        for img_b64 in imagenes_b64[:2]:  # máximo 2 páginas
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{img_b64}"}
            })

        response = client.chat.completions.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": content}]
        )
    else:
        # PDF con texto: más rápido y barato
        response = client.chat.completions.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            messages=[{
                "role": "user",
                "content": f"{PROMPT}\n\nTEXTO DE LA FACTURA:\n{texto}"
            }]
        )

    response_text = response.choices[0].message.content.strip()

    # Limpiar backticks por si acaso
    if response_text.startswith("```"):
        parts = response_text.split("```")
        response_text = parts[1]
        if response_text.startswith("json"):
            response_text = response_text[4:]
    response_text = response_text.strip()

    data = json.loads(response_text)
    data["archivo"]       = os.path.basename(str(pdf_path))
    data["ruta_completa"] = str(pdf_path)
    data["estado"]        = "pendiente"

    return data


def procesar_carpeta(carpeta: str) -> list[dict]:
    """Lee todos los PDFs de una carpeta y extrae sus datos."""
    carpeta = Path(carpeta)
    # En Windows el filesystem no distingue mayúsculas — *.pdf y *.PDF
    # devuelven los mismos archivos duplicados. Usamos un set por nombre
    # para evitar procesar el mismo PDF dos veces.
    vistos = {}
    for patron in ("*.pdf", "*.PDF", "*.Pdf"):
        for p in carpeta.glob(patron):
            vistos[p.resolve()] = p
    pdfs = sorted(vistos.values())

    if not pdfs:
        print(f"⚠️  No se encontraron PDFs en {carpeta}")
        return []

    facturas = []
    for pdf in pdfs:
        print(f"📄 Procesando: {pdf.name}")
        try:
            datos = extract_invoice_data(str(pdf))
            facturas.append(datos)
            print(f"   ✅ {datos['denominacion']} — ${datos['monto']:,.2f} — {datos['periodo']}")
        except Exception as e:
            print(f"   ❌ Error: {e}")
            facturas.append({
                "archivo":       pdf.name,
                "ruta_completa": str(pdf),
                "estado":        "error",
                "error":         str(e)
            })

    return facturas


def guardar_facturas(facturas: list[dict], archivo_salida: str = "data/facturas.json"):
    Path("data").mkdir(exist_ok=True)
    with open(archivo_salida, "w", encoding="utf-8") as f:
        json.dump(facturas, f, ensure_ascii=False, indent=2)
    print(f"\n💾 {len(facturas)} factura(s) guardadas en {archivo_salida}")


if __name__ == "__main__":
    import sys
    carpeta  = sys.argv[1] if len(sys.argv) > 1 else "./facturas"
    facturas = procesar_carpeta(carpeta)
    guardar_facturas(facturas)
