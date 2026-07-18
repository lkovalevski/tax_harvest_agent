"""
agent.py — Agente Playwright que navega ARCA/SiRADIG y carga las facturas.
Lee los selectores desde data/selectores.json (generado por debug_session.py).
"""

import json
import time
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, Page, TimeoutError as PWTimeout
from dotenv import load_dotenv

load_dotenv()  # carga las variables del .env (AFIP_CUIT, AFIP_CLAVE, etc.)

HEADLESS        = False
SELECTORES_FILE = "data/selectores.json"

SEL_DEFAULT = {
    "login": {
        "campo_cuit":    "#F1\\:username",
        "btn_siguiente": "#F1\\:btnSiguiente",
        "campo_clave":   "#F1\\:password",
        "btn_ingresar":  "#F1\\:btnIngresar",
    },
    "siradig": {
        "btn_persona":        "input[type='submit']",
        "menu_carga_form":    "text=Carga de Formulario",
        "btn_nuevo_borrador": "text=Crear Nuevo Borrador",
    },
    "deducciones": {
        "seccion_3":        "text=Deducciones y desgravaciones",
        "btn_agregar":      "text=Agregar Deducciones y Desgravaciones",
        "item_gastos_educ": "text=Gastos de Educación",
    },
    "form_educacion": {
        "input_cuit":           "input[name*='cuit']",
        "input_denominacion":   "input[name*='denominacion']",
        "select_tipo_gasto":    "select[name*='tipoGasto']",
        "select_periodo":       "select[name*='periodo']",
        "input_monto":          "input[name*='monto']",
        "btn_sel_familiar":     "text=Seleccionar Familiar",
        "btn_alta_comprobante": "text=Alta de Comprobante",
        "btn_guardar":          "button:has-text('Guardar')",
    },
    "modal_comprobante": {
        "input_fecha":      "input[name*='fecha']",
        "select_tipo_comp": "select[name*='tipo']",
        "input_nro_1":      "input[name*='nroComp']",
        "input_monto_comp": "input[name*='montoComp']",
        "btn_agregar":      "button:has-text('Agregar')",
    }
}

# El select de Período en ARCA usa VALORES numéricos (1=Enero...12=Diciembre)
PERIODO_VALUE = {
    "Enero": "1", "Febrero": "2", "Marzo": "3", "Abril": "4",
    "Mayo": "5", "Junio": "6", "Julio": "7", "Agosto": "8",
    "Septiembre": "9", "Octubre": "10", "Noviembre": "11", "Diciembre": "12",
}


def cargar_selectores() -> dict:
    if Path(SELECTORES_FILE).exists():
        with open(SELECTORES_FILE, encoding="utf-8") as f:
            sel = json.load(f)
        print(f"  📋 Selectores cargados desde {SELECTORES_FILE}")
        return sel
    print(f"  ⚠️  {SELECTORES_FILE} no encontrado — usando defaults.")
    print(f"     Corré debug_session.py primero para mejores resultados.")
    return SEL_DEFAULT.copy()


class ARCAAgent:
    def __init__(self, cuit_usuario: str, clave_fiscal: str):
        self.cuit  = cuit_usuario
        self.clave = clave_fiscal
        self.sel   = cargar_selectores()
        self.playwright = None
        self.browser    = None
        self.page       = None
        self.log        = []

    def _log(self, msg, nivel="info"):
        icono = {"ok": "✅", "error": "❌", "warn": "⚠️ "}.get(nivel, "ℹ️ ")
        print(f"  {icono} {msg}")
        self.log.append({"nivel": nivel, "msg": msg})

    def _click(self, selector, desc=""):
        try:
            self.page.locator(selector).first.click()
            return True
        except Exception as e:
            self._log(f"No pude clickear '{desc or selector}': {e}", "error")
            return False

    def _fill(self, selector, valor, desc=""):
        try:
            self.page.locator(selector).first.fill(str(valor))
            return True
        except Exception as e:
            self._log(f"No pude completar '{desc or selector}': {e}", "error")
            return False

    def _select(self, selector, label, desc=""):
        try:
            self.page.locator(selector).first.select_option(label=label)
            return True
        except Exception as e:
            self._log(f"No pude seleccionar '{label}' en '{desc or selector}': {e}", "error")
            return False

    def _wait(self, seg=1.0):
        time.sleep(seg)

    def iniciar(self):
        self.playwright = sync_playwright().start()
        self.browser    = self.playwright.chromium.launch(headless=HEADLESS, slow_mo=400)
        context         = self.browser.new_context(viewport={"width": 1280, "height": 800})
        self.page       = context.new_page()
        self._log("Navegador iniciado", "ok")

    def cerrar(self):
        if self.browser:    self.browser.close()
        if self.playwright: self.playwright.stop()

    def login_afip(self):
        s = self.sel["login"]
        self._log("Login AFIP...")
        self.page.goto("https://auth.afip.gob.ar/contribuyente_/login.xhtml")
        self.page.wait_for_load_state("networkidle")
        self._fill(s["campo_cuit"], self.cuit, "CUIT")
        self._click(s["btn_siguiente"], "Siguiente")
        self.page.wait_for_load_state("networkidle")
        self._wait(1)
        self._fill(s["campo_clave"], self.clave, "Clave")
        self._click(s["btn_ingresar"], "Ingresar")
        self.page.wait_for_load_state("networkidle")
        self._wait(2)
        self._log("Login OK", "ok")

    def _cerrar_modal_si_existe(self):
        """Cierra cualquier modal de recordatorio que esté bloqueando la UI."""
        for s in ["button:has-text('Aceptar')", "input[value='Aceptar']", "text=Aceptar"]:
            try:
                btn = self.page.locator(s).first
                if btn.is_visible():
                    btn.click()
                    self._wait(1)
                    self._log("Modal cerrado", "ok")
                    return True
            except Exception:
                continue
        return False

    def navegar_siradig(self):
        s = self.sel["siradig"]

        # Escala por portal principal primero para establecer cookies de sesión
        self._log("Estableciendo sesión en portal AFIP...")
        self.page.goto("https://portalcf.cloud.afip.gob.ar/portal/app/")
        self.page.wait_for_load_state("networkidle")
        self._wait(3)

        # Clickear desde el portal — el link abre en nueva pestaña
        self._log("Buscando SiRADIG en el portal...")
        try:
            link = self.page.locator("text=SiRADIG - Trabajador").first
            link.wait_for(timeout=5000)
            with self.page.context.expect_page() as new_page_info:
                link.click()
            new_page = new_page_info.value
            new_page.wait_for_load_state("networkidle")
            self._wait(3)
            self.page = new_page  # trabajar en la nueva pestaña
            self._log(f"SiRADIG abierto: {self.page.url}", "ok")
        except Exception as e:
            self._log(f"No abrió nueva pestaña ({e}), revisando pestaña actual...", "warn")
            self.page.wait_for_load_state("networkidle")
            self._wait(2)
            if "serviciosjava2" not in self.page.url:
                self._log("Intentando URL directa como fallback...")
                self.page.goto("https://serviciosjava2.afip.gob.ar/radig/jsp/determinarContribuyente.do?codigo=2026")
                self.page.wait_for_load_state("networkidle")
                self._wait(2)

        if ("menu_sel_empresa" in self.page.url or
                self.page.locator("text=Seleccione la Persona").count() > 0):
            self._click(s["btn_persona"], "persona")
            self.page.wait_for_load_state("networkidle")
            self._wait(1)
        # Cerrar modal Recordatorio que aparece al entrar al período
        self._wait(2)
        self._cerrar_modal_si_existe()
        self._log("En SiRADIG", "ok")

    def _cerrar_modal_recordatorio(self):
        """Cierra el modal 'Recordatorio - Formulario Borrador' si está presente."""
        for s in ["button:has-text('Aceptar')", "input[value='Aceptar']", "text=Aceptar"]:
            try:
                btn = self.page.locator(s).first
                if btn.is_visible():
                    btn.click()
                    self._wait(1)
                    self._log("Modal Recordatorio cerrado", "ok")
                    return
            except Exception:
                continue

    def abrir_carga_formulario(self):
        s = self.sel["siradig"]
        # Cerrar modal recordatorio si está bloqueando el menú
        if (self.page.locator("text=Recordatorio").count() > 0 or
                self.page.locator("text=Aceptar").count() > 0):
            self._log("Cerrando modal Recordatorio...")
            self._cerrar_modal_recordatorio()
            self.page.wait_for_load_state("networkidle")
            self._wait(2)

        # Probar selector guardado + candidatos alternativos
        CANDIDATOS_CARGA = [
            s.get("menu_carga_form", ""),
            "#btn_carga",
            "a:has-text('Carga de Formulario')",
            "text=Carga de Formulario",
        ]
        for sel_carga in CANDIDATOS_CARGA:
            if not sel_carga:
                continue
            try:
                self.page.wait_for_selector(sel_carga, timeout=3000)
                if self.page.locator(sel_carga).count() > 0:
                    s["menu_carga_form"] = sel_carga
                    break
            except Exception:
                continue

        self._click(s["menu_carga_form"], "Carga de Formulario")
        self.page.wait_for_load_state("networkidle")
        self._wait(1)
        if self.page.locator(s["btn_nuevo_borrador"]).count() > 0:
            self._click(s["btn_nuevo_borrador"], "Nuevo Borrador")
            self.page.wait_for_load_state("networkidle")
            self._wait(1)
        self._log("F572 abierto", "ok")

    def abrir_deducciones(self):
        s = self.sel["deducciones"]
        self.page.goto(
            "https://serviciosjava2.afip.gob.ar/radig/jsp/verMenuDeducciones.do"
        )
        self.page.wait_for_load_state("networkidle")
        self._wait(1)
        if self.page.locator(s["seccion_3"]).count() > 0:
            self._click(s["seccion_3"], "Sección 3")
            self._wait(1)
        self._log("Deducciones abiertas", "ok")

    def cargar_gasto_educacion(self, factura: dict) -> bool:
        sf = self.sel["form_educacion"]
        sm = self.sel["modal_comprobante"]
        sd = self.sel["deducciones"]
        self._log(f"Cargando: {factura['archivo']}")
        try:
            # Abrir formulario de Gastos de Educación (el + correspondiente)
            btns = self.page.locator("span.mini_boton_agregar").all()
            if len(btns) >= 2:
                btns[1].click()  # índice 1 = Gastos de Educación
            else:
                btn_educ = sd.get("btn_agregar_educ", "")
                self._click(btn_educ, "btn + Gastos de Educación")
            self.page.wait_for_load_state("networkidle")
            self._wait(1)

            # ── PASO 1: CUIT del emisor (autocompleta denominación) ───────────
            cuit_limpio = factura["cuit_emisor"].replace("-", "")
            self._fill(sf["input_cuit"], cuit_limpio, "CUIT")
            self.page.keyboard.press("Tab")
            self._wait(1.5)  # esperar autocompletado de denominación

            # ── PASO 2: Tipo de gasto ───────────────────────────────────────
            self._select(sf["select_tipo_gasto"],
                         factura.get("tipo_gasto", "Servicios con fines educativos"), "Tipo gasto")
            self._wait(0.3)

            # ── PASO 3: Período (select por VALOR numérico, no por label) ────
            periodo_nombre = factura.get("periodo", "")
            periodo_val = PERIODO_VALUE.get(periodo_nombre, "")
            if periodo_val:
                try:
                    self.page.locator(sf["select_periodo"]).first.select_option(value=periodo_val)
                except Exception as e:
                    self._log(f"No pude seleccionar período por valor: {e}", "error")
            self._wait(0.3)

            # ── PASO 4: Familiar ─────────────────────────────────────────────
            # El modal "Selección de Familiar" muestra una tabla con radio buttons
            # por cada carga de familia (Apellido y Nombre, CUIL, Parentesco).
            if factura.get("familiar_apellido"):
                self._click(sf["btn_sel_familiar"], "Familiar")
                self._wait(1.5)

                apellido = factura["familiar_apellido"].upper().strip()
                nombre   = (factura.get("familiar_nombre") or "").upper().strip()

                try:
                    # La tabla específica de cargas de familia (id confirmado: tabla_cargas_familia)
                    tabla = self.page.locator("#tabla_cargas_familia")
                    tabla.wait_for(timeout=5000)

                    # IMPORTANTE: si solo filtramos por apellido, hermanos con el
                    # mismo apellido matchean la misma fila (siempre cae en .first).
                    # Hay que filtrar por apellido Y nombre combinados.
                    fila = None
                    if nombre:
                        candidata = tabla.locator(f"tr:has-text('{apellido}'):has-text('{nombre}')")
                        if candidata.count() == 1:
                            fila = candidata.first
                        elif candidata.count() > 1:
                            self._log(f"⚠️ Ambiguo: {candidata.count()} filas matchean '{apellido} {nombre}'", "warn")
                            fila = candidata.first

                    if fila is None:
                        # Fallback: solo apellido (puede ser ambiguo con hermanos)
                        todas = tabla.locator(f"tr:has-text('{apellido}')")
                        cant = todas.count()
                        if cant > 1:
                            self._log(
                                f"⚠️ {cant} familiares con apellido '{apellido}' y sin nombre "
                                f"para desambiguar — revisar manualmente cuál se seleccionó",
                                "warn"
                            )
                        fila = todas.first

                    fila.wait_for(timeout=5000)

                    # Clickear el radio button de esa fila específicamente
                    radio = fila.locator("input.radioCargaFamilia, input[type='radio']").first
                    radio.click(force=True)
                    self._wait(0.5)

                    # Verificar que quedó marcado
                    if not radio.is_checked():
                        radio.check(force=True)
                        self._wait(0.3)

                    # Click en Aceptar del modal
                    self.page.locator("button:has-text('Aceptar'), input[value='Aceptar']").first.click()
                    self._wait(1)
                    self._log(f"Familiar seleccionado: {apellido}", "ok")
                except Exception as e:
                    self._log(f"No pude seleccionar familiar '{apellido}': {e}", "error")
                    try:
                        self.page.locator("button:has-text('Cancelar'), .ui-dialog-titlebar-close").first.click()
                        self._wait(0.5)
                    except Exception:
                        pass
                    raise

            # ── PASO 5: Alta de Comprobante (SOLO después de lo anterior) ─────
            self._click(sf["btn_alta_comprobante"], "Alta Comprobante")
            self._wait(1)

            self._fill(sm["input_fecha"], factura["fecha"], "Fecha")
            self._select(sm["select_tipo_comp"],
                         factura.get("tipo_comprobante", "Factura C"), "Tipo comp")

            # Número de comprobante: dos campos separados (punto de venta y número)
            nro = str(factura.get("numero_comprobante", ""))
            if "-" in nro:
                partes = nro.split("-")
                pto_venta = partes[0].lstrip("0") or "0"
                numero    = partes[1].lstrip("0") or "0"
            else:
                pto_venta, numero = "3", nro

            self._fill(sm["input_pto_venta"], pto_venta, "Punto de venta")
            self._fill(sm["input_numero"],    numero,    "Número")

            monto = str(factura["monto"]).replace(",", ".")
            self._fill(sm["input_monto_comp"], monto, "Monto comp")

            # Agregar comprobante (esto autocompleta Monto Total del formulario)
            self._click(sm["btn_agregar"], "Agregar comp")
            self._wait(1.5)

            # ── PASO 6: Guardar el gasto completo ─────────────────────────────
            CANDIDATOS_GUARDAR = [
                sf["btn_guardar"],
                "span.ui-button-text:has-text('Guardar')",
                "button:has(span:text('Guardar'))",
                "#btn_guardar",
            ]
            guardado = False
            for s in CANDIDATOS_GUARDAR:
                try:
                    el = self.page.locator(s).first
                    if el.is_visible():
                        el.click()
                        guardado = True
                        break
                except Exception:
                    continue
            if not guardado:
                self._log("No pude clickear Guardar con ningún candidato", "error")
            self.page.wait_for_load_state("networkidle")
            self._wait(1.5)

            self._log(
                f"Cargado: {factura.get('denominacion','')} — "
                f"${factura['monto']:,.2f} — {factura.get('periodo','')} — "
                f"{factura.get('familiar_apellido','')}", "ok"
            )
            return True

        except Exception as e:
            self._log(f"Error en {factura['archivo']}: {e}", "error")
            try:
                path = f"data/error_{factura['archivo'].replace('.pdf','')}.png"
                self.page.screenshot(path=path)
                self._log(f"Screenshot: {path}", "warn")
            except Exception:
                pass
            return False

    def procesar_facturas(self, archivo_json="data/facturas.json"):
        with open(archivo_json, encoding="utf-8") as f:
            facturas = json.load(f)

        aprobadas = [f for f in facturas if f.get("estado") == "aprobado"]
        if not aprobadas:
            print("\n⚠️  No hay facturas aprobadas.")
            return

        print(f"\n📋 Procesando {len(aprobadas)} factura(s)...\n")
        self.iniciar()
        try:
            self.login_afip()
            self.navegar_siradig()
            self.abrir_carga_formulario()
            self.abrir_deducciones()

            for factura in aprobadas:
                exito = self.cargar_gasto_educacion(factura)
                factura["estado"] = "cargado" if exito else "error_carga"
                self._wait(2)

            idx = {f["archivo"]: f for f in facturas}
            for f in aprobadas:
                idx[f["archivo"]] = f
            with open(archivo_json, "w", encoding="utf-8") as fh:
                json.dump(list(idx.values()), fh, ensure_ascii=False, indent=2)

            ok  = sum(1 for f in aprobadas if f["estado"] == "cargado")
            err = len(aprobadas) - ok
            print(f"\n  ✅ Cargadas: {ok}  |  ❌ Errores: {err}")
        finally:
            self.cerrar()

    def guardar_log(self, archivo="data/agent_log.json"):
        Path("data").mkdir(exist_ok=True)
        with open(archivo, "w", encoding="utf-8") as f:
            json.dump(self.log, f, ensure_ascii=False, indent=2)
        print(f"  📋 Log guardado en {archivo}")


if __name__ == "__main__":
    import sys
    cuit  = os.environ.get("AFIP_CUIT", "")
    clave = os.environ.get("AFIP_CLAVE", "")
    if not cuit or not clave:
        print("❌ Configurá AFIP_CUIT y AFIP_CLAVE en .env")
        sys.exit(1)
    agente = ARCAAgent(cuit, clave)
    agente.procesar_facturas(sys.argv[1] if len(sys.argv) > 1 else "data/facturas.json")
    agente.guardar_log()
