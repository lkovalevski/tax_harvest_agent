"""
app.py — Interfaz web para revisar, editar y aprobar facturas antes de cargarlas en ARCA.
Corre en http://localhost:5000
"""

import json
import os
from pathlib import Path
from flask import Flask, render_template_string, request, jsonify, redirect

app = Flask(__name__)
DATA_FILE = "data/facturas.json"

HTML = """
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <title>Tax Harvest — Revisión de Facturas</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, sans-serif; background: #0d1117; color: #c9d1d9; min-height: 100vh; }

    header {
      background: #161b22; border-bottom: 1px solid #30363d;
      padding: 1rem 2rem; display: flex; align-items: center; gap: 1rem;
    }
    header h1 { font-size: 1.2rem; color: #58a6ff; }
    .badge-total { background: #21262d; border: 1px solid #30363d; border-radius: 20px;
                   padding: 2px 10px; font-size: 12px; color: #8b949e; }

    .summary {
      display: flex; gap: 1rem; padding: 1.5rem 2rem;
      border-bottom: 1px solid #21262d;
    }
    .stat { background: #161b22; border: 1px solid #30363d; border-radius: 8px;
            padding: 1rem 1.5rem; flex: 1; text-align: center; }
    .stat .num { font-size: 2rem; font-weight: bold; }
    .stat .lbl { font-size: 12px; color: #8b949e; margin-top: 4px; }
    .stat.pendiente .num { color: #ffa657; }
    .stat.aprobado  .num { color: #7ee787; }
    .stat.cargado   .num { color: #58a6ff; }
    .stat.error     .num { color: #f85149; }
    .stat.total     .num { color: #c9d1d9; }

    .actions-bar {
      padding: 1rem 2rem; display: flex; gap: 0.75rem; align-items: center;
      border-bottom: 1px solid #21262d;
    }
    .btn { padding: 8px 16px; border-radius: 6px; border: none; cursor: pointer;
           font-size: 13px; font-weight: 500; transition: opacity .15s; }
    .btn:hover { opacity: .85; }
    .btn-green  { background: #238636; color: #fff; }
    .btn-red    { background: #da3633; color: #fff; }
    .btn-blue   { background: #1f6feb; color: #fff; }
    .btn-gray   { background: #21262d; color: #c9d1d9; border: 1px solid #30363d; }
    .btn-big    { padding: 12px 28px; font-size: 15px; }

    .grid { display: flex; flex-direction: column; gap: 0; }

    .factura-card {
      background: #161b22; border-bottom: 1px solid #21262d;
      padding: 1.25rem 2rem; display: grid;
      grid-template-columns: 28px 1fr 180px 120px 140px 160px;
      align-items: center; gap: 1rem; transition: background .15s;
    }
    .factura-card:hover { background: #1c2128; }
    .factura-card.aprobado { border-left: 3px solid #238636; }
    .factura-card.ignorado { border-left: 3px solid #6e7681; opacity: .5; }
    .factura-card.cargado  { border-left: 3px solid #1f6feb; }
    .factura-card.error    { border-left: 3px solid #da3633; }

    .cb { width: 16px; height: 16px; cursor: pointer; accent-color: #238636; }

    .info-main { display: flex; flex-direction: column; gap: 3px; }
    .denominacion { font-weight: 600; color: #e6edf3; font-size: 14px; }
    .archivo { font-size: 11px; color: #6e7681; }
    .cuit-badge { font-size: 11px; color: #8b949e; background: #21262d;
                  border-radius: 4px; padding: 1px 6px; display: inline-block; margin-top: 2px; }

    .monto { font-size: 18px; font-weight: 700; color: #7ee787; text-align: right; }
    .periodo { color: #ffa657; font-size: 13px; font-weight: 500; }
    .tipo-gasto { font-size: 12px; color: #8b949e; }
    .familiar { font-size: 13px; color: #d2a8ff; }

    .estado-badge {
      display: inline-block; padding: 3px 10px; border-radius: 12px;
      font-size: 12px; font-weight: 600; text-align: center;
    }
    .estado-pendiente { background: #2d2000; color: #ffa657; }
    .estado-aprobado  { background: #0f2d18; color: #7ee787; }
    .estado-ignorado  { background: #1c2128; color: #6e7681; }
    .estado-cargado   { background: #0d1f3c; color: #58a6ff; }
    .estado-error     { background: #2d0f0f; color: #f85149; }

    .card-actions { display: flex; gap: 6px; justify-content: flex-end; }
    .btn-sm { padding: 4px 10px; font-size: 12px; border-radius: 4px;
              border: 1px solid #30363d; background: #21262d; color: #c9d1d9;
              cursor: pointer; }
    .btn-sm:hover { background: #30363d; }
    .btn-sm.aprobar  { border-color: #238636; color: #7ee787; }
    .btn-sm.ignorar  { border-color: #6e7681; color: #8b949e; }

    /* Modal de edición */
    .modal-overlay {
      display: none; position: fixed; inset: 0;
      background: rgba(0,0,0,.7); z-index: 100; align-items: center; justify-content: center;
    }
    .modal-overlay.open { display: flex; }
    .modal { background: #161b22; border: 1px solid #30363d; border-radius: 12px;
             padding: 2rem; width: 520px; max-height: 80vh; overflow-y: auto; }
    .modal h3 { color: #58a6ff; margin-bottom: 1.5rem; }
    .field { margin-bottom: 1rem; }
    .field label { display: block; font-size: 12px; color: #8b949e; margin-bottom: 4px; }
    .field input, .field select {
      width: 100%; padding: 8px 10px; background: #0d1117;
      border: 1px solid #30363d; border-radius: 6px; color: #e6edf3; font-size: 14px;
    }
    .field input:focus, .field select:focus { outline: none; border-color: #58a6ff; }
    .modal-actions { display: flex; gap: 0.75rem; margin-top: 1.5rem; justify-content: flex-end; }

    .empty { text-align: center; padding: 4rem; color: #6e7681; }
    .footer { padding: 1.5rem 2rem; text-align: center; color: #6e7681; font-size: 12px; }

    .launch-btn {
      margin: 0 2rem 0 auto;
    }
  </style>
</head>
<body>

<header>
  <h1>🌿 Tax Harvest — Revisión de Facturas</h1>
  <span class="badge-total">Período 2026</span>
</header>

<div class="summary">
  <div class="stat total">
    <div class="num" id="cnt-total">0</div>
    <div class="lbl">Total</div>
  </div>
  <div class="stat pendiente">
    <div class="num" id="cnt-pendiente">0</div>
    <div class="lbl">Pendientes</div>
  </div>
  <div class="stat aprobado">
    <div class="num" id="cnt-aprobado">0</div>
    <div class="lbl">Aprobadas</div>
  </div>
  <div class="stat cargado">
    <div class="num" id="cnt-cargado">0</div>
    <div class="lbl">Cargadas en ARCA</div>
  </div>
  <div class="stat error">
    <div class="num" id="cnt-error">0</div>
    <div class="lbl">Con error</div>
  </div>
  <div class="stat aprobado" style="flex:1.5">
    <div class="num" id="total-monto" style="font-size:1.5rem">$0</div>
    <div class="lbl">Total a descargar</div>
  </div>
</div>

<div class="actions-bar">
  <button class="btn btn-green" onclick="aprobarSeleccionadas()">✅ Aprobar seleccionadas</button>
  <button class="btn btn-gray"  onclick="ignorarSeleccionadas()">🚫 Ignorar seleccionadas</button>
  <button class="btn btn-gray"  onclick="toggleAll()">☑️ Seleccionar todas</button>
  <div style="flex:1"></div>
  <button class="btn btn-blue btn-big launch-btn" onclick="lanzarAgente()">
    🚀 Lanzar agente en ARCA
  </button>
</div>

<div class="grid" id="lista"></div>

<div class="footer">
  Los datos se guardan automáticamente · El agente solo cargará las facturas <strong>aprobadas</strong>
</div>

<!-- Modal edición -->
<div class="modal-overlay" id="modal">
  <div class="modal">
    <h3>✏️ Editar factura</h3>
    <input type="hidden" id="edit-archivo">
    <div class="field"><label>Denominación</label><input id="edit-denominacion"></div>
    <div class="field"><label>CUIT Emisor</label><input id="edit-cuit"></div>
    <div class="field"><label>Tipo de Comprobante</label>
      <select id="edit-tipo-comp">
        <option>Factura A</option><option>Factura B</option>
        <option selected>Factura C</option><option>Recibo</option><option>Ticket</option>
      </select>
    </div>
    <div class="field"><label>Número de Comprobante</label><input id="edit-numero"></div>
    <div class="field"><label>Fecha</label><input id="edit-fecha" placeholder="DD/MM/AAAA"></div>
    <div class="field"><label>Tipo de Gasto</label>
      <select id="edit-tipo-gasto">
        <option>Servicios con fines educativos</option>
        <option>Herramientas educativas</option>
        <option>Útiles escolares</option>
      </select>
    </div>
    <div class="field"><label>Período</label>
      <select id="edit-periodo">
        <option>Enero</option><option>Febrero</option><option>Marzo</option>
        <option>Abril</option><option>Mayo</option><option>Junio</option>
        <option>Julio</option><option>Agosto</option><option>Septiembre</option>
        <option>Octubre</option><option>Noviembre</option><option>Diciembre</option>
      </select>
    </div>
    <div class="field"><label>Monto</label><input id="edit-monto" type="number"></div>
    <div class="field"><label>Familiar (Apellido Nombre)</label><input id="edit-familiar"></div>
    <div class="modal-actions">
      <button class="btn btn-gray" onclick="cerrarModal()">Cancelar</button>
      <button class="btn btn-blue" onclick="guardarEdicion()">Guardar</button>
    </div>
  </div>
</div>

<script>
let facturas = [];
let seleccionadas = new Set();

async function cargarFacturas() {
  const res = await fetch('/api/facturas');
  facturas = await res.json();
  renderizar();
}

function formatMonto(m) {
  return '$' + Number(m).toLocaleString('es-AR', {minimumFractionDigits: 2});
}

function renderizar() {
  const lista = document.getElementById('lista');
  
  // Contadores
  const cnts = {total: facturas.length, pendiente: 0, aprobado: 0, cargado: 0, error: 0};
  let totalMonto = 0;
  facturas.forEach(f => {
    if (cnts[f.estado] !== undefined) cnts[f.estado]++;
    if (f.estado === 'aprobado' || f.estado === 'pendiente') totalMonto += Number(f.monto || 0);
  });
  
  Object.entries(cnts).forEach(([k,v]) => {
    const el = document.getElementById('cnt-' + k);
    if (el) el.textContent = v;
  });
  document.getElementById('total-monto').textContent = formatMonto(totalMonto);

  if (!facturas.length) {
    lista.innerHTML = '<div class="empty">No hay facturas procesadas. Corré python run.py para empezar.</div>';
    return;
  }

  lista.innerHTML = facturas.map((f, i) => {
    const checked = seleccionadas.has(f.archivo) ? 'checked' : '';
    const familiar = [f.familiar_apellido, f.familiar_nombre].filter(Boolean).join(', ');
    return `
    <div class="factura-card ${f.estado}" data-i="${i}">
      <input type="checkbox" class="cb" ${checked}
             onchange="toggleSel('${f.archivo}', this.checked)"
             ${['cargado'].includes(f.estado) ? 'disabled' : ''}>
      <div class="info-main">
        <span class="denominacion">${f.denominacion || '—'}</span>
        <span class="archivo">📄 ${f.archivo}</span>
        <span class="cuit-badge">CUIT ${f.cuit_emisor || '—'}</span>
      </div>
      <div class="monto">${formatMonto(f.monto || 0)}</div>
      <div>
        <div class="periodo">${f.periodo || '—'}</div>
        <div class="tipo-gasto">${(f.tipo_gasto || '').replace('Servicios con fines ', '')}</div>
      </div>
      <div class="familiar">${familiar || '—'}</div>
      <div class="card-actions">
        <span class="estado-badge estado-${f.estado}">${f.estado}</span>
        <button class="btn-sm aprobar" onclick="cambiarEstado('${f.archivo}', 'aprobado')">✅</button>
        <button class="btn-sm ignorar" onclick="cambiarEstado('${f.archivo}', 'ignorado')">🚫</button>
        <button class="btn-sm" onclick="abrirModal(${i})">✏️</button>
      </div>
    </div>`;
  }).join('');
}

function toggleSel(archivo, checked) {
  if (checked) seleccionadas.add(archivo);
  else seleccionadas.delete(archivo);
}

let allSelected = false;
function toggleAll() {
  allSelected = !allSelected;
  facturas.forEach(f => {
    if (f.estado !== 'cargado') {
      if (allSelected) seleccionadas.add(f.archivo);
      else seleccionadas.delete(f.archivo);
    }
  });
  renderizar();
}

async function cambiarEstado(archivo, estado) {
  await fetch('/api/estado', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({archivo, estado})
  });
  await cargarFacturas();
}

async function aprobarSeleccionadas() {
  for (const arch of seleccionadas) await cambiarEstado(arch, 'aprobado');
  seleccionadas.clear();
}

async function ignorarSeleccionadas() {
  for (const arch of seleccionadas) await cambiarEstado(arch, 'ignorado');
  seleccionadas.clear();
}

function abrirModal(i) {
  const f = facturas[i];
  document.getElementById('edit-archivo').value      = f.archivo;
  document.getElementById('edit-denominacion').value = f.denominacion || '';
  document.getElementById('edit-cuit').value         = f.cuit_emisor || '';
  document.getElementById('edit-tipo-comp').value    = f.tipo_comprobante || 'Factura C';
  document.getElementById('edit-numero').value       = f.numero_comprobante || '';
  document.getElementById('edit-fecha').value        = f.fecha || '';
  document.getElementById('edit-tipo-gasto').value   = f.tipo_gasto || 'Servicios con fines educativos';
  document.getElementById('edit-periodo').value      = f.periodo || 'Mayo';
  document.getElementById('edit-monto').value        = f.monto || '';
  const familiar = [f.familiar_apellido, f.familiar_nombre].filter(Boolean).join(' ');
  document.getElementById('edit-familiar').value     = familiar;
  document.getElementById('modal').classList.add('open');
}

function cerrarModal() {
  document.getElementById('modal').classList.remove('open');
}

async function guardarEdicion() {
  const familiar = document.getElementById('edit-familiar').value.trim().split(/\s+/);
  const data = {
    archivo:            document.getElementById('edit-archivo').value,
    denominacion:       document.getElementById('edit-denominacion').value,
    cuit_emisor:        document.getElementById('edit-cuit').value,
    tipo_comprobante:   document.getElementById('edit-tipo-comp').value,
    numero_comprobante: document.getElementById('edit-numero').value,
    fecha:              document.getElementById('edit-fecha').value,
    tipo_gasto:         document.getElementById('edit-tipo-gasto').value,
    periodo:            document.getElementById('edit-periodo').value,
    monto:              parseFloat(document.getElementById('edit-monto').value),
    familiar_apellido:  familiar[0] || '',
    familiar_nombre:    familiar.slice(1).join(' ') || '',
  };
  await fetch('/api/editar', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(data)
  });
  cerrarModal();
  await cargarFacturas();
}

async function lanzarAgente() {
  const aprobadas = facturas.filter(f => f.estado === 'aprobado');
  if (!aprobadas.length) {
    alert('No hay facturas aprobadas. Aprobá al menos una antes de lanzar el agente.');
    return;
  }
  if (!confirm(`¿Lanzar el agente para cargar ${aprobadas.length} factura(s) en ARCA?`)) return;
  
  const res = await fetch('/api/lanzar', {method: 'POST'});
  const data = await res.json();
  alert(data.mensaje);
  await cargarFacturas();
}

// Cerrar modal clickeando afuera
document.getElementById('modal').addEventListener('click', e => {
  if (e.target.id === 'modal') cerrarModal();
});

cargarFacturas();
setInterval(cargarFacturas, 30000); // refresca cada 30s
</script>
</body>
</html>
"""


def leer_facturas() -> list:
    Path("data").mkdir(exist_ok=True)
    if not Path(DATA_FILE).exists():
        return []
    with open(DATA_FILE, encoding="utf-8") as f:
        return json.load(f)


def guardar_facturas(facturas: list):
    Path("data").mkdir(exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(facturas, f, ensure_ascii=False, indent=2)


@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/api/facturas")
def api_facturas():
    return jsonify(leer_facturas())


@app.route("/api/estado", methods=["POST"])
def api_estado():
    data = request.get_json()
    facturas = leer_facturas()
    for f in facturas:
        if f["archivo"] == data["archivo"]:
            f["estado"] = data["estado"]
            break
    guardar_facturas(facturas)
    return jsonify({"ok": True})


@app.route("/api/editar", methods=["POST"])
def api_editar():
    data = request.get_json()
    facturas = leer_facturas()
    for f in facturas:
        if f["archivo"] == data["archivo"]:
            f.update(data)
            break
    guardar_facturas(facturas)
    return jsonify({"ok": True})


@app.route("/api/lanzar", methods=["POST"])
def api_lanzar():
    """Lanza el agente Playwright en background."""
    import subprocess, sys
    try:
        subprocess.Popen([sys.executable, "agent.py", DATA_FILE])
        return jsonify({"ok": True, "mensaje": "✅ Agente lanzado. Mirá la ventana del navegador."})
    except Exception as e:
        return jsonify({"ok": False, "mensaje": f"❌ Error al lanzar agente: {e}"})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
