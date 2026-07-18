"""
debug_session.py — Sesión interactiva para mapear los selectores reales de ARCA.

Uso:
    python debug_session.py

El script abre Chromium visible, hace el login y te deja pausar en cada
paso para inspeccionar el DOM con el inspector de Playwright.
Los selectores que encontrás se guardan en data/selectores.json
y agent.py los usa automáticamente.
"""

import os
import json
import time
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, Page

load_dotenv()

SELECTORES_FILE = "data/selectores.json"

# ── Selectores por defecto (punto de partida) ─────────────────────────────────
# Editá estos valores durante la sesión de debug o dejalos actualizar solos.
SELECTORES_DEFAULT = {
    "login": {
        "campo_cuit":      "#F1\\:username",
        "btn_siguiente":   "#F1\\:btnSiguiente",
        "campo_clave":     "#F1\\:password",
        "btn_ingresar":    "#F1\\:btnIngresar",
    },
    "siradig": {
        "btn_persona":         "input[type='submit']",
        "menu_carga_form":     "text=Carga de Formulario",
        "btn_nuevo_borrador":  "text=Crear Nuevo Borrador",
    },
    "deducciones": {
        "seccion_3":           "text=Deducciones y desgravaciones",
        "btn_agregar":         "text=Agregar Deducciones y Desgravaciones",
        "item_gastos_educ":    "text=Gastos de Educación",
    },
    "form_educacion": {
        "input_cuit":          "input[name*='cuit']",
        "input_denominacion":  "input[name*='denominacion']",
        "select_tipo_gasto":   "select[name*='tipoGasto']",
        "select_periodo":      "select[name*='periodo']",
        "input_monto":         "input[name*='monto']",
        "btn_sel_familiar":    "text=Seleccionar Familiar",
        "btn_alta_comprobante":"text=Alta de Comprobante",
        "btn_guardar":         "button:has-text('Guardar')",
    },
    "modal_comprobante": {
        "input_fecha":         "input[name*='fecha']",
        "select_tipo_comp":    "select[name*='tipo']",
        "input_nro_1":         "input[name*='nroComp']",
        "input_monto_comp":    "input[name*='montoComp']",
        "btn_agregar":         "button:has-text('Agregar')",
    }
}


def cargar_selectores() -> dict:
    if Path(SELECTORES_FILE).exists():
        with open(SELECTORES_FILE, encoding="utf-8") as f:
            return json.load(f)
    return SELECTORES_DEFAULT.copy()


def guardar_selectores(sel: dict):
    Path("data").mkdir(exist_ok=True)
    with open(SELECTORES_FILE, "w", encoding="utf-8") as f:
        json.dump(sel, f, ensure_ascii=False, indent=2)
    print(f"  💾 Selectores guardados en {SELECTORES_FILE}")


def pausar(msg: str):
    """Pausa la ejecución y espera Enter. Útil para inspeccionar el DOM."""
    print(f"\n{'─'*60}")
    print(f"⏸  PAUSA: {msg}")
    print("   Inspeccioná el browser. Cuando estés listo, presioná Enter.")
    print(f"{'─'*60}")
    input()


def probar_selector(page: Page, selector: str, descripcion: str) -> bool:
    """Prueba si un selector encuentra algo en la página actual."""
    try:
        count = page.locator(selector).count()
        if count > 0:
            print(f"  ✅ [{descripcion}] '{selector}' → {count} elemento(s)")
            return True
        else:
            print(f"  ❌ [{descripcion}] '{selector}' → NO encontrado")
            return False
    except Exception as e:
        print(f"  ❌ [{descripcion}] '{selector}' → Error: {e}")
        return False


def sugerir_selector(page: Page, descripcion: str) -> str:
    """
    Muestra el HTML visible y pide al usuario que ingrese el selector correcto.
    """
    print(f"\n  🔍 Ingresá el selector correcto para: {descripcion}")
    print("  (tips: 'text=...', '#id', 'input[name=...]', '.clase')")
    print("  O presioná Enter para saltear.")
    nuevo = input("  Selector > ").strip()
    return nuevo if nuevo else None


def step_login(page: Page, sel: dict) -> bool:
    print("\n📍 PASO 1: Login AFIP")
    cuit  = os.getenv("AFIP_CUIT", "")
    clave = os.getenv("AFIP_CLAVE", "")

    if not cuit or not clave:
        print("  ❌ Configurá AFIP_CUIT y AFIP_CLAVE en el .env")
        return False

    page.goto("https://auth.afip.gob.ar/contribuyente_/login.xhtml")
    page.wait_for_load_state("networkidle")
    time.sleep(1)

    # ── Paso 1: ingresar CUIT y clickear Siguiente ────────────────────────────
    print("  ▶ Ingresando CUIT...")
    try:
        page.fill(sel["login"]["campo_cuit"], cuit)
        page.click(sel["login"]["btn_siguiente"])
        page.wait_for_load_state("networkidle")
        time.sleep(2)
        print("  ✅ CUIT ingresado, esperando campo de clave...")
    except Exception as e:
        print(f"  ❌ Error al ingresar CUIT: {e}")
        pausar("Ingresá el CUIT manualmente y hacé click en Siguiente. Presioná Enter cuando cargue el campo de clave.")

    # ── Paso 2: esperar campo de clave (aparece dinámicamente) ───────────────
    # AFIP carga la segunda pantalla con JS, hay que esperar
    SELECTORES_CLAVE = [
        "#F1\\:password",
        "input[type='password']",
        "input[name='password']",
        "input[id*='password']",
        "input[id*='clave']",
    ]

    campo_clave_ok = None
    for sel_clave in SELECTORES_CLAVE:
        try:
            page.wait_for_selector(sel_clave, timeout=3000)
            campo_clave_ok = sel_clave
            print(f"  ✅ Campo de clave encontrado con: {sel_clave}")
            sel["login"]["campo_clave"] = sel_clave
            guardar_selectores(sel)
            break
        except Exception:
            continue

    if not campo_clave_ok:
        print("  ⚠️  No encontré el campo de clave automáticamente.")
        pausar("Buscá el campo de clave en el browser (F12 → Elements → buscá input type=password) e ingresalo abajo.")
        nuevo = sugerir_selector(page, "campo de clave fiscal (input de contraseña)")
        if nuevo:
            campo_clave_ok = nuevo
            sel["login"]["campo_clave"] = nuevo
            guardar_selectores(sel)

    # ── Paso 3: ingresar clave y clickear Ingresar ────────────────────────────
    SELECTORES_BTN = [
        "#F1\\:btnIngresar",
        "input[value='Ingresar']",
        "button[type='submit']",
        "input[type='submit']",
    ]

    btn_ingresar_ok = None
    for sel_btn in SELECTORES_BTN:
        if page.locator(sel_btn).count() > 0:
            btn_ingresar_ok = sel_btn
            sel["login"]["btn_ingresar"] = sel_btn
            guardar_selectores(sel)
            break

    try:
        if campo_clave_ok:
            page.fill(campo_clave_ok, clave)
        if btn_ingresar_ok:
            page.click(btn_ingresar_ok)
        else:
            page.keyboard.press("Enter")  # fallback: Enter desde el campo de clave

        page.wait_for_load_state("networkidle")
        time.sleep(2)
        print("  ✅ Login ejecutado")
    except Exception as e:
        print(f"  ❌ Error al ingresar clave: {e}")
        pausar("Completá el login manualmente (ingresá tu clave y clickeá Ingresar). Presioná Enter cuando estés adentro de AFIP.")

    pausar("¿Entraste correctamente? ¿Ves el portal de AFIP con tus servicios? Presioná Enter para continuar.")
    return True


def step_siradig(page: Page, sel: dict) -> bool:
    print("\n📍 PASO 2: Navegando a SiRADIG")

    # ── Escala 1: portal principal de AFIP ───────────────────────────────────
    # Necesario para que las cookies de sesión del SSO queden bien establecidas
    # antes de saltar a serviciosjava2 (dominio distinto).
    print("  ▶ Pasando por portal principal para establecer sesión...")
    page.goto("https://portalcf.cloud.afip.gob.ar/portal/app/")
    page.wait_for_load_state("networkidle")
    time.sleep(3)
    print(f"  URL portal: {page.url}")

    # Si redirigió al login, la sesión no quedó — avisamos
    if "auth.afip" in page.url or "login" in page.url.lower():
        print("  ❌ La sesión no quedó establecida después del login.")
        pausar("El browser volvió al login. Completá el login manualmente y presioná Enter cuando veas el portal de AFIP con tus servicios.")

    # ── Escala 2: clickear SiRADIG desde el portal ──────────────────────────
    # El link abre en nueva pestaña — hay que capturarla con expect_page()
    print("  ▶ Buscando link SiRADIG - Trabajador en el portal...")
    try:
        link = page.locator("text=SiRADIG - Trabajador").first
        link.wait_for(timeout=5000)

        # Capturar nueva pestaña si el link tiene target="_blank"
        with page.context.expect_page() as new_page_info:
            link.click()
        new_page = new_page_info.value
        new_page.wait_for_load_state("networkidle")
        time.sleep(3)
        page = new_page  # trabajar en la nueva pestaña
        print(f"  ✅ SiRADIG abierto en nueva pestaña: {page.url}")
    except Exception as e:
        print(f"  ⚠️  No abrió nueva pestaña ({e}), revisando pestaña actual...")
        # Puede ser que navegó en la misma pestaña
        page.wait_for_load_state("networkidle")
        time.sleep(2)
        if "serviciosjava2" not in page.url:
            pausar("Hacé click en 'SiRADIG - Trabajador' manualmente y presioná Enter cuando cargue SiRADIG.")

    print(f"  URL actual: {page.url}")

    # ── Selector de persona ───────────────────────────────────────────────────
    # Robusto ante jsessionid en la URL
    tiene_selector = (
        "menu_sel_empresa" in page.url or
        page.locator("text=Seleccione la Persona").count() > 0 or
        page.locator("text=Seleccione la Persona a representar").count() > 0
    )

    if tiene_selector:
        print("  ℹ️  Pantalla de selección de persona detectada")
        # Intentar varios selectores para el botón con el nombre
        candidatos = [
            "input[type='submit']",
            "input[type='button']",
            "button:not([type='reset'])",
        ]
        btn_ok = None
        for s in candidatos:
            if page.locator(s).count() > 0:
                btn_ok = s
                print(f"  ✅ Botón persona encontrado: {s}")
                sel["siradig"]["btn_persona"] = s
                guardar_selectores(sel)
                break

        if not btn_ok:
            pausar("Hacé click en 'KOVALEVSKI LEANDRO OSCAR' manualmente y presioná Enter cuando cargue el menú principal.")
        else:
            try:
                page.locator(btn_ok).first.click()
                page.wait_for_load_state("networkidle")
                time.sleep(2)
                print("  ✅ Persona seleccionada")
            except Exception as e:
                print(f"  ⚠️  {e}")
                pausar("Hacé click en tu nombre manualmente y presioná Enter.")
    else:
        print("  ℹ️  No hay selector de persona, ya estás en el menú principal")

    # Cerrar modal "Recordatorio" si aparece antes o después de seleccionar persona
    time.sleep(2)  # darle tiempo a AFIP para mostrar el modal
    if page.locator("text=Recordatorio").count() > 0 or page.locator("button:has-text('Aceptar')").count() > 0:
        print("  ℹ️  Modal 'Recordatorio - Formulario Borrador' detectado — cerrándolo...")
        cerrar_modal_recordatorio(page)
        time.sleep(1)

    pausar("¿Estás en el menú principal de SiRADIG con 'Período 2026'? (sin modal encima)")

    # Verificar selectores del menú
    for key, selector in sel["siradig"].items():
        if key != "btn_persona":
            probar_selector(page, selector, key)

    return page  # retornar la página activa (puede ser nueva pestaña)


def cerrar_modal_recordatorio(page: Page):
    """Cierra el modal 'Recordatorio - Formulario Borrador' si está presente."""
    SELECTORES_ACEPTAR = [
        "button:has-text('Aceptar')",
        "input[value='Aceptar']",
        "text=Aceptar",
        ".modal button",
        "button.aceptar",
    ]
    for s in SELECTORES_ACEPTAR:
        try:
            btn = page.locator(s).first
            if btn.is_visible():
                btn.click()
                time.sleep(1)
                print("  ✅ Modal 'Recordatorio' cerrado")
                return True
        except Exception:
            continue
    return False


def step_carga_formulario(page: Page, sel: dict) -> bool:
    print("\n📍 PASO 3: Abriendo Carga de Formulario")
    print(f"  URL actual: {page.url}")

    # Volver al menú principal — entre pasos la página puede haber cambiado
    page.goto("https://serviciosjava2.afip.gob.ar/radig/jsp/determinarContribuyente.do?codigo=2026")
    page.wait_for_load_state("networkidle")
    time.sleep(2)

    # Cerrar modal de recordatorio si está presente
    if page.locator("text=Recordatorio").count() > 0 or page.locator("text=Aceptar").count() > 0:
        print("  ℹ️  Modal 'Recordatorio' detectado — cerrándolo...")
        cerrar_modal_recordatorio(page)
        page.wait_for_load_state("networkidle")
        time.sleep(2)  # esperar que el menú recargue tras cerrar el modal

    # Usar el selector ya guardado (puede haber sido corregido manualmente)
    selector_carga = sel["siradig"]["menu_carga_form"]

    # Probar también candidatos alternativos por si el guardado no funciona
    CANDIDATOS = [
        selector_carga,
        "#btn_carga",
        "a:has-text('Carga de Formulario')",
        "text=Carga de Formulario",
        "span.ui-button-text:has-text('Carga')",
    ]
    menu_ok = None
    for s in CANDIDATOS:
        try:
            page.wait_for_selector(s, timeout=3000)
            if page.locator(s).count() > 0:
                menu_ok = s
                print(f"  ✅ 'Carga de Formulario' encontrado: {s}")
                sel["siradig"]["menu_carga_form"] = s
                guardar_selectores(sel)
                break
        except Exception:
            continue

    if not menu_ok:
        print("  ⚠️  No encontré el selector automáticamente")
        nuevo = sugerir_selector(page, "'Carga de Formulario' — usá el id del botón (ej: #btn_carga)")
        if nuevo:
            menu_ok = nuevo
            sel["siradig"]["menu_carga_form"] = nuevo
            guardar_selectores(sel)

    try:
        page.locator(menu_ok).first.click()
        page.wait_for_load_state("networkidle")
        time.sleep(1)
    except Exception as e:
        print(f"  ⚠️  {e}")
        nuevo = sugerir_selector(page, "'Carga de Formulario' en el menú")
        if nuevo:
            sel["siradig"]["menu_carga_form"] = nuevo
            guardar_selectores(sel)
            page.click(nuevo)
            page.wait_for_load_state("networkidle")

    pausar("¿Aparece 'Crear Nuevo Borrador' o directamente el F572?")

    # Borrador nuevo si hace falta
    if page.locator(sel["siradig"]["btn_nuevo_borrador"]).count() > 0:
        print("  ℹ️  Hay que crear un nuevo borrador")
        page.click(sel["siradig"]["btn_nuevo_borrador"])
        page.wait_for_load_state("networkidle")
        time.sleep(1)

    return True


def step_deducciones(page: Page, sel: dict) -> bool:
    print("\n📍 PASO 4: Sección Deducciones y desgravaciones")

    # Navegar directamente al F572 deducciones
    page.goto("https://serviciosjava2.afip.gob.ar/radig/jsp/verMenuDeducciones.do")
    page.wait_for_load_state("networkidle")
    time.sleep(2)

    pausar("¿Ves el F572 con las secciones? La sección 3 - Deducciones debe estar expandida (flecha roja apuntando abajo).")

    # La sección 3 ya viene expandida según las imágenes — verificar
    # Selectores reales observados en las imágenes:
    # - "3 - Deducciones y desgravaciones" es el título (ya expandido)
    # - Botón "+" junto a "Gastos de Educación" para agregar

    # Buscar el botón + de Gastos de Educación
    CANDIDATOS_BTN_EDUC = [
        # Selectores basados en estructura real de ARCA (jQuery UI fieldset)
        "span.ui-fieldset-legend:has-text('Gastos de Educación') + span button",
        "span.ui-fieldset-legend:has-text('Gastos de Educación') ~ span button",
        ".ui-fieldset-legend:has-text('Gastos de Educación') button",
        # El + suele ser un span/button con clase específica dentro del legend
        "legend:has-text('Gastos de Educación') button",
        "legend:has-text('Gastos de Educación') span[class*='agregar']",
        "legend:has-text('Gastos de Educación') a",
        # Por onclick
        "button[onclick*='GastoEduc']", "button[onclick*='gastoEduc']",
        "a[onclick*='GastoEduc']", "a[onclick*='gastoEduc']",
        "button[onclick*='Educacion']", "button[onclick*='educacion']",
        # El + es a veces un input type button con value="+"
        "fieldset:has-text('Gastos de Educación') input[value='+']",
        "fieldset:has-text('Gastos de Educación') button",
        # Selector exacto confirmado por inspección del DOM real de ARCA
        "#div_tabla_deducciones_agrupadas > fieldset:nth-child(3) > legend > span.mini_boton_agregar",
        "legend > span.mini_boton_agregar",
        "span.mini_boton_agregar",
        # Último recurso
        "text=Gastos de Educación",
    ]

    print("\n  Buscando botón + de Gastos de Educación...")
    btn_educ_ok = None
    for s in CANDIDATOS_BTN_EDUC:
        count = page.locator(s).count()
        if count > 0:
            print(f"  ✅ Encontrado: '{s}' → {count} elemento(s)")
            btn_educ_ok = s
            break
        else:
            print(f"  ❌ '{s}' → NO encontrado")

    if not btn_educ_ok:
        print("\n  ⚠️  No encontré el botón + automáticamente.")
        print("  Abrí DevTools (F12), hacé click derecho sobre el '+' de 'Gastos de Educación' → Inspeccionar")
        nuevo = sugerir_selector(page, "botón + junto a 'Gastos de Educación'")
        if nuevo:
            btn_educ_ok = nuevo

    if btn_educ_ok:
        sel["deducciones"]["btn_agregar_educ"] = btn_educ_ok
        guardar_selectores(sel)

    return True


def step_form_educacion(page: Page, sel: dict) -> bool:
    print("\n📍 PASO 5: Formulario de Gastos de Educación")
    print("  Vamos a abrir el formulario para mapear los campos.")
    print("  NO vamos a guardar nada — presioná 'Volver' al final.")

    # Asegurarse de estar en la página de deducciones
    if "verMenuDeducciones" not in page.url:
        page.goto("https://serviciosjava2.afip.gob.ar/radig/jsp/verMenuDeducciones.do")
        page.wait_for_load_state("networkidle")
        time.sleep(2)

    # Clickear el + de Gastos de Educación
    btn_educ = sel["deducciones"].get("btn_agregar_educ", "")
    abierto = False

    if btn_educ:
        try:
            page.locator(btn_educ).first.click()
            page.wait_for_load_state("networkidle")
            time.sleep(1)
            print(f"  ✅ Click en botón + de Gastos de Educación")
            abierto = True
        except Exception as e:
            print(f"  ⚠️  {e}")

    if not abierto:
        pausar("Hacé click manualmente en el '+' junto a 'Gastos de Educación' y presioná Enter cuando se abra el formulario.")

    pausar("¿Ves el formulario de Gastos de Educación con los campos CUIT, Tipo de Gasto, Período, Monto?")

    # ── Mapear campos del formulario ─────────────────────────────────────────
    print("\n  Mapeando campos del formulario...")

    # URL del formulario de gastos de educación
    print(f"  URL del formulario: {page.url}")

    # Guardar la URL para uso directo
    if "verGastosEducacion" in page.url or "GastoEduc" in page.url:
        sel["deducciones"]["url_form_educ"] = page.url.split("?")[0]
        guardar_selectores(sel)
        print(f"  ✅ URL del formulario guardada")

    # Probar selectores conocidos
    campos_a_mapear = [
        ("input_cuit",           "campo CUIT del emisor",          ["input[name*='cuit']", "#cuit", "input[id*='cuit']"]),
        ("input_denominacion",   "campo Denominación",             ["input[name*='denom']", "#denominacion", "input[id*='denom']"]),
        ("select_tipo_gasto",    "select Tipo de Gasto",           ["select[name*='tipoGasto']", "select[id*='tipoGasto']", "select[name*='tipo']"]),
        ("select_periodo",       "select Período",                 ["select[name*='periodo']", "select[id*='periodo']"]),
        ("input_monto",          "campo Monto Total",              ["input[name*='monto']", "input[name*='importe']", "input[id*='monto']"]),
        ("btn_sel_familiar",     "botón Seleccionar Familiar",     ["text=Seleccionar Familiar", "button:has-text('Familiar')", "input[value*='Familiar']"]),
        ("btn_alta_comprobante", "botón Alta de Comprobante",      ["text=Alta de Comprobante", "button:has-text('Comprobante')", "input[value*='Comprobante']"]),
        ("btn_guardar",          "botón Guardar",                  ["button:has-text('Guardar')", "input[value='Guardar']", "#btn_guardar"]),
    ]

    for key, desc, candidatos in campos_a_mapear:
        encontrado = False
        for s in candidatos:
            if page.locator(s).count() > 0:
                print(f"  ✅ [{desc}] → '{s}'")
                sel["form_educacion"][key] = s
                guardar_selectores(sel)
                encontrado = True
                break
        if not encontrado:
            print(f"  ❌ [{desc}] → no encontrado con candidatos conocidos")
            nuevo = sugerir_selector(page, desc)
            if nuevo:
                sel["form_educacion"][key] = nuevo
                guardar_selectores(sel)

    # ── Modal Alta de Comprobante ─────────────────────────────────────────────
    btn_comp = sel["form_educacion"].get("btn_alta_comprobante", "")
    if btn_comp and page.locator(btn_comp).count() > 0:
        try:
            page.locator(btn_comp).first.click()
            time.sleep(1)
            pausar("¿Apareció el modal 'Alta de Comprobante' con Fecha, Tipo, Número, Monto?")

            campos_modal = [
                ("input_fecha",      "campo Fecha",                ["input[name*='fecha']", "input[id*='fecha']"]),
                ("select_tipo_comp", "select Tipo de Comprobante", ["select[name*='tipo']", "select[id*='tipo']"]),
                ("input_nro_1",      "campo Número de Comprobante",["input[name*='nroComp']", "input[name*='numero']"]),
                ("input_monto_comp", "campo Monto del comprobante",["input[name*='montoComp']", "input[name*='monto']"]),
                ("btn_agregar",      "botón Agregar",              ["button:has-text('Agregar')", "input[value='Agregar']"]),
            ]

            print("\n  Mapeando campos del modal...")
            for key, desc, candidatos in campos_modal:
                for s in candidatos:
                    if page.locator(s).count() > 0:
                        print(f"  ✅ [{desc}] → '{s}'")
                        sel["modal_comprobante"][key] = s
                        guardar_selectores(sel)
                        break
                else:
                    nuevo = sugerir_selector(page, desc)
                    if nuevo:
                        sel["modal_comprobante"][key] = nuevo
                        guardar_selectores(sel)

            page.keyboard.press("Escape")
            time.sleep(0.5)
            print("  ✅ Modal cerrado")
        except Exception as e:
            print(f"  ⚠️  {e}")

    pausar("Sesión completada. Presioná Enter para cerrar el browser.\n(Si querés, hacé click en 'Volver' para no dejar cambios en ARCA.)")
    return True


def generar_reporte(sel: dict):
    """Genera un reporte legible de los selectores verificados."""
    reporte = ["# Reporte de Selectores — Tax Harvest Agent\n"]
    reporte.append("Generado por debug_session.py\n")

    for seccion, campos in sel.items():
        reporte.append(f"\n## {seccion}")
        for key, valor in campos.items():
            reporte.append(f"  {key}: `{valor}`")

    with open("data/reporte_selectores.md", "w", encoding="utf-8") as f:
        f.write("\n".join(reporte))

    print("\n📋 Reporte guardado en data/reporte_selectores.md")


def main():
    print("""
╔══════════════════════════════════════════════╗
║  🔬  Tax Harvest — Sesión de Debugging       ║
║      Mapeador interactivo de selectores ARCA ║
╚══════════════════════════════════════════════╝

Este script abre Chromium visible y te guía paso a paso
para verificar y corregir cada selector de ARCA.

Los selectores verificados se guardan en data/selectores.json
y el agent.py los usa automáticamente desde ahí.
""")

    Path("data").mkdir(exist_ok=True)
    sel = cargar_selectores()

    pasos = [
        ("Login AFIP",                step_login),
        ("Navegar SiRADIG",           step_siradig),
        ("Abrir Carga de Formulario", step_carga_formulario),
        ("Sección Deducciones",       step_deducciones),
        ("Formulario Educación",      step_form_educacion),
    ]

    print(f"Pasos a ejecutar: {len(pasos)}")
    print("Podés interrumpir con Ctrl+C en cualquier momento.\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=500)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        try:
            for nombre, fn in pasos:
                print(f"\n{'═'*60}")
                print(f"  PASO: {nombre}")
                print(f"{'═'*60}")
                result = fn(page, sel)
                # Si el paso devuelve una página (nueva pestaña), actualizamos
                if result is not None and result is not True and result is not False:
                    page = result
                    print(f"  ℹ️  Trabajando en nueva pestaña: {page.url}")
                elif not result:
                    print(f"\n⚠️  El paso '{nombre}' tuvo problemas pero continuamos.")

            print("\n" + "═"*60)
            print("✅ Sesión de debugging completada")
            print("═"*60)

        except KeyboardInterrupt:
            print("\n\n⚡ Interrumpido por el usuario")
        finally:
            guardar_selectores(sel)
            generar_reporte(sel)
            print(f"\n💾 Selectores finales guardados en {SELECTORES_FILE}")
            pausar("Último vistazo al browser antes de cerrarlo.")
            browser.close()


if __name__ == "__main__":
    main()
