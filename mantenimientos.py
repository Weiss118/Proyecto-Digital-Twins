"""Calendario de mantenimientos por activo.

Cada registro pertenece a una organización y a un activo (id de equipos.py).
Estados: Programado, Realizado, Cancelado.
  - Último mantenimiento = el Realizado con fecha_realizada más reciente.
  - Próximo mantenimiento = el Programado con fecha más cercana (marcado como
    vencido si su fecha ya pasó).
"""
import calendar
from datetime import date, datetime

from flask import Blueprint, jsonify, request, session

from db_comun import get_db_connection
from equipos import EQUIPOS

# Quién puede programar / cerrar / cancelar. Los demás roles solo consultan.
ROLES_GESTIONAN_MANTENIMIENTO = ("Tecnico", "Supervisor")

TIPOS_MANTENIMIENTO = (
    "Preventivo", "Correctivo", "Predictivo", "Inspección", "Calibración", "Lubricación",
)

bp = Blueprint("mantenimientos", __name__)


def init_tables():
    conn = get_db_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mantenimientos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organizacion_id INTEGER,
            equipo_id TEXT NOT NULL,
            tipo TEXT NOT NULL,
            descripcion TEXT,
            estado TEXT NOT NULL DEFAULT 'Programado',
            fecha_programada TEXT NOT NULL,
            fecha_realizada TEXT,
            responsable TEXT,
            notas_cierre TEXT,
            creado_por TEXT,
            creado_en TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_mantenimientos_equipo
        ON mantenimientos (organizacion_id, equipo_id, estado)
    """)
    conn.commit()
    conn.close()


init_tables()


@bp.app_context_processor
def _contexto_plantillas():
    return {"roles_mantenimiento": ROLES_GESTIONAN_MANTENIMIENTO}


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
_IDS_EQUIPOS = {e["id"]: e["nombre"] for e in EQUIPOS}


def _error(mensaje, codigo=400):
    return jsonify({"error": mensaje}), codigo


def _autenticado():
    return "usuario_id" in session


def _puede_gestionar():
    return session.get("rol") in ROLES_GESTIONAN_MANTENIMIENTO


def _org():
    return session.get("organizacion_id")


def _parsear_fecha(texto):
    try:
        return date.fromisoformat(str(texto))
    except (TypeError, ValueError):
        return None


def _texto_opcional(cuerpo, campo, maximo):
    valor = cuerpo.get(campo)
    if valor is None:
        return "", None
    if not isinstance(valor, str):
        return None, f"El campo {campo} debe ser texto."
    valor = valor.strip()
    if len(valor) > maximo:
        return None, f"El campo {campo} admite máximo {maximo} caracteres."
    return valor, None


def _fila(r, hoy):
    programado = r["estado"] == "Programado"
    fecha_prog = _parsear_fecha(r["fecha_programada"])
    return {
        "id": r["id"],
        "equipo_id": r["equipo_id"],
        "tipo": r["tipo"],
        "descripcion": r["descripcion"] or "",
        "estado": r["estado"],
        "fecha_programada": r["fecha_programada"],
        "fecha_realizada": r["fecha_realizada"],
        "fecha": r["fecha_realizada"] if r["estado"] == "Realizado" and r["fecha_realizada"] else r["fecha_programada"],
        "responsable": r["responsable"] or "",
        "notas_cierre": r["notas_cierre"] or "",
        "vencido": bool(programado and fecha_prog and fecha_prog < hoy),
        "dias_restantes": (fecha_prog - hoy).days if (programado and fecha_prog) else None,
    }


def _obtener(conn, mantenimiento_id):
    return conn.execute(
        "SELECT * FROM mantenimientos WHERE id = ? AND organizacion_id IS ?",
        (mantenimiento_id, _org()),
    ).fetchone()


def _validar_equipo(equipo_id):
    return equipo_id in _IDS_EQUIPOS


# ---------------------------------------------------------------------------
# Consultas
# ---------------------------------------------------------------------------
@bp.route("/api/mantenimientos/resumen")
def api_resumen():
    if not _autenticado():
        return _error("No autorizado", 401)

    hoy = date.today()
    conn = get_db_connection()
    equipos = []
    for equipo in EQUIPOS:
        ultimo = conn.execute("""
            SELECT * FROM mantenimientos
            WHERE organizacion_id IS ? AND equipo_id = ? AND estado = 'Realizado'
            ORDER BY fecha_realizada DESC, id DESC LIMIT 1
        """, (_org(), equipo["id"])).fetchone()
        proximo = conn.execute("""
            SELECT * FROM mantenimientos
            WHERE organizacion_id IS ? AND equipo_id = ? AND estado = 'Programado'
            ORDER BY fecha_programada ASC, id ASC LIMIT 1
        """, (_org(), equipo["id"])).fetchone()
        equipos.append({
            "equipo_id": equipo["id"],
            "nombre": equipo["nombre"],
            "ultimo": _fila(ultimo, hoy) if ultimo else None,
            "proximo": _fila(proximo, hoy) if proximo else None,
        })
    conn.close()

    return jsonify({
        "hoy": hoy.isoformat(),
        "tipos": list(TIPOS_MANTENIMIENTO),
        "puede_editar": _puede_gestionar(),
        "equipos": equipos,
    })


@bp.route("/api/mantenimientos")
def api_listar():
    if not _autenticado():
        return _error("No autorizado", 401)

    equipo_id = request.args.get("equipo_id", "")
    if not _validar_equipo(equipo_id):
        return _error("Activo no encontrado.", 404)

    mes = request.args.get("mes", "")
    try:
        anio, numero_mes = (int(x) for x in mes.split("-"))
        primero = date(anio, numero_mes, 1)
    except (ValueError, TypeError):
        return _error("Mes inválido. Usa el formato AAAA-MM.")
    ultimo = date(anio, numero_mes, calendar.monthrange(anio, numero_mes)[1])

    hoy = date.today()
    conn = get_db_connection()
    filas = conn.execute("""
        SELECT * FROM mantenimientos
        WHERE organizacion_id IS ? AND equipo_id = ? AND estado != 'Cancelado'
          AND CASE WHEN estado = 'Realizado' AND fecha_realizada IS NOT NULL
                   THEN fecha_realizada ELSE fecha_programada END BETWEEN ? AND ?
        ORDER BY fecha_programada, id
    """, (_org(), equipo_id, primero.isoformat(), ultimo.isoformat())).fetchall()
    conn.close()

    return jsonify({"eventos": [_fila(f, hoy) for f in filas]})


# ---------------------------------------------------------------------------
# Altas y cambios (Técnico / Supervisor)
# ---------------------------------------------------------------------------
def _datos_comunes(cuerpo):
    """Valida tipo, descripción y responsable. Devuelve (datos, error)."""
    tipo = cuerpo.get("tipo")
    if tipo not in TIPOS_MANTENIMIENTO:
        return None, "Selecciona un tipo de mantenimiento válido."
    descripcion, err = _texto_opcional(cuerpo, "descripcion", 500)
    if err:
        return None, err
    responsable, err = _texto_opcional(cuerpo, "responsable", 80)
    if err:
        return None, err
    return {"tipo": tipo, "descripcion": descripcion, "responsable": responsable}, None


@bp.route("/api/mantenimientos", methods=["POST"])
def api_crear():
    if not _autenticado():
        return _error("No autorizado", 401)
    if not _puede_gestionar():
        return _error("No tienes permisos para gestionar mantenimientos.", 403)

    cuerpo = request.get_json(silent=True)
    if not isinstance(cuerpo, dict):
        return _error("Solicitud inválida.")
    if not _validar_equipo(cuerpo.get("equipo_id")):
        return _error("Activo no encontrado.", 404)

    fecha = _parsear_fecha(cuerpo.get("fecha_programada"))
    if fecha is None:
        return _error("Fecha inválida.")
    datos, err = _datos_comunes(cuerpo)
    if err:
        return _error(err)

    ya_realizado = bool(cuerpo.get("ya_realizado"))
    if ya_realizado and fecha > date.today():
        return _error("Un mantenimiento realizado no puede tener fecha futura.")

    conn = get_db_connection()
    cursor = conn.execute("""
        INSERT INTO mantenimientos
        (organizacion_id, equipo_id, tipo, descripcion, estado, fecha_programada,
         fecha_realizada, responsable, creado_por, creado_en)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        _org(), cuerpo["equipo_id"], datos["tipo"], datos["descripcion"],
        "Realizado" if ya_realizado else "Programado",
        fecha.isoformat(), fecha.isoformat() if ya_realizado else None,
        datos["responsable"], session.get("nombre"),
        datetime.now().astimezone().isoformat(timespec="seconds"),
    ))
    conn.commit()
    nuevo = conn.execute("SELECT * FROM mantenimientos WHERE id = ?", (cursor.lastrowid,)).fetchone()
    conn.close()
    return jsonify({"mensaje": "Mantenimiento guardado.", "mantenimiento": _fila(nuevo, date.today())}), 201


@bp.route("/api/mantenimientos/<int:mantenimiento_id>", methods=["PUT"])
def api_editar(mantenimiento_id):
    if not _autenticado():
        return _error("No autorizado", 401)
    if not _puede_gestionar():
        return _error("No tienes permisos para gestionar mantenimientos.", 403)

    cuerpo = request.get_json(silent=True)
    if not isinstance(cuerpo, dict):
        return _error("Solicitud inválida.")

    conn = get_db_connection()
    try:
        actual = _obtener(conn, mantenimiento_id)
        if not actual:
            return _error("Mantenimiento no encontrado.", 404)
        if actual["estado"] != "Programado":
            return _error("Solo se pueden editar mantenimientos programados.", 409)

        fecha = _parsear_fecha(cuerpo.get("fecha_programada"))
        if fecha is None:
            return _error("Fecha inválida.")
        datos, err = _datos_comunes(cuerpo)
        if err:
            return _error(err)

        conn.execute("""
            UPDATE mantenimientos
            SET tipo = ?, descripcion = ?, responsable = ?, fecha_programada = ?
            WHERE id = ?
        """, (datos["tipo"], datos["descripcion"], datos["responsable"], fecha.isoformat(), mantenimiento_id))
        conn.commit()
        fila = conn.execute("SELECT * FROM mantenimientos WHERE id = ?", (mantenimiento_id,)).fetchone()
        return jsonify({"mensaje": "Mantenimiento actualizado.", "mantenimiento": _fila(fila, date.today())})
    finally:
        conn.close()


@bp.route("/api/mantenimientos/<int:mantenimiento_id>/realizar", methods=["POST"])
def api_realizar(mantenimiento_id):
    if not _autenticado():
        return _error("No autorizado", 401)
    if not _puede_gestionar():
        return _error("No tienes permisos para gestionar mantenimientos.", 403)

    cuerpo = request.get_json(silent=True)
    if not isinstance(cuerpo, dict):
        cuerpo = {}

    conn = get_db_connection()
    try:
        actual = _obtener(conn, mantenimiento_id)
        if not actual:
            return _error("Mantenimiento no encontrado.", 404)
        if actual["estado"] != "Programado":
            return _error("Solo se pueden cerrar mantenimientos programados.", 409)

        fecha = _parsear_fecha(cuerpo.get("fecha_realizada") or date.today().isoformat())
        if fecha is None:
            return _error("Fecha inválida.")
        if fecha > date.today():
            return _error("La fecha de realización no puede ser futura.")
        notas, err = _texto_opcional(cuerpo, "notas_cierre", 500)
        if err:
            return _error(err)

        conn.execute("""
            UPDATE mantenimientos
            SET estado = 'Realizado', fecha_realizada = ?, notas_cierre = ?
            WHERE id = ?
        """, (fecha.isoformat(), notas, mantenimiento_id))
        conn.commit()
        fila = conn.execute("SELECT * FROM mantenimientos WHERE id = ?", (mantenimiento_id,)).fetchone()
        return jsonify({"mensaje": "Mantenimiento marcado como realizado.", "mantenimiento": _fila(fila, date.today())})
    finally:
        conn.close()


@bp.route("/api/mantenimientos/<int:mantenimiento_id>/cancelar", methods=["POST"])
def api_cancelar(mantenimiento_id):
    if not _autenticado():
        return _error("No autorizado", 401)
    if not _puede_gestionar():
        return _error("No tienes permisos para gestionar mantenimientos.", 403)

    conn = get_db_connection()
    try:
        actual = _obtener(conn, mantenimiento_id)
        if not actual:
            return _error("Mantenimiento no encontrado.", 404)
        if actual["estado"] != "Programado":
            return _error("Solo se pueden cancelar mantenimientos programados.", 409)
        conn.execute("UPDATE mantenimientos SET estado = 'Cancelado' WHERE id = ?", (mantenimiento_id,))
        conn.commit()
        return jsonify({"mensaje": "Mantenimiento cancelado."})
    finally:
        conn.close()
