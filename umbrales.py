"""Umbrales de alerta configurables por rol.

Los valores de alertas.py (REGLAS_ALERTAS) siguen siendo los PREDETERMINADOS.
Este módulo guarda en SQLite solo los cambios que hace un usuario autorizado
y los combina con los predeterminados al evaluar cada medición.

Cada regla puede tener cuatro límites (cualquiera puede omitirse):
    paro_bajo <= alerta_baja <= alerta_alta <= paro_alto
Mismo significado que en alertas.evaluar_valor.
"""
import json
import math
import time
from datetime import datetime

from flask import Blueprint, jsonify, request, session

from alertas import REGLAS_ALERTAS
from db_comun import get_db_connection
from equipos import EQUIPOS

# Roles (de los ya existentes: Operador, Tecnico, Supervisor) que pueden
# modificar umbrales. Para permitir también al Técnico: ("Tecnico", "Supervisor").
ROLES_CONFIGURAN_UMBRALES = ("Supervisor",)

# Orden lógico de menor a mayor.
CAMPOS = ("paro_bajo", "alerta_baja", "alerta_alta", "paro_alto")

bp = Blueprint("umbrales", __name__)


def init_tables():
    conn = get_db_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS umbrales_personalizados (
            equipo_id TEXT NOT NULL,
            variable TEXT NOT NULL,
            paro_bajo REAL,
            alerta_baja REAL,
            alerta_alta REAL,
            paro_alto REAL,
            actualizado_por TEXT,
            fecha_hora TEXT NOT NULL,
            PRIMARY KEY (equipo_id, variable)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS historial_umbrales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            equipo_id TEXT NOT NULL,
            variable TEXT NOT NULL,
            accion TEXT NOT NULL,
            anterior TEXT,
            nuevo TEXT,
            usuario TEXT,
            fecha_hora TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


init_tables()


@bp.app_context_processor
def _contexto_plantillas():
    return {"roles_umbrales": ROLES_CONFIGURAN_UMBRALES}


# ---------------------------------------------------------------------------
# Regla efectiva (predeterminada + personalizada) usada por app.py
# ---------------------------------------------------------------------------
_cache = {"t": 0.0, "datos": {}}
_TTL_SEGUNDOS = 2.0


def _invalidar_cache():
    _cache["t"] = 0.0


def _personalizados():
    ahora = time.time()
    if ahora - _cache["t"] < _TTL_SEGUNDOS:
        return _cache["datos"]
    try:
        conn = get_db_connection()
        filas = conn.execute("SELECT * FROM umbrales_personalizados").fetchall()
        conn.close()
        datos = {
            (f["equipo_id"], f["variable"]): {c: f[c] for c in CAMPOS if f[c] is not None}
            for f in filas
        }
    except Exception:
        # Si la lectura falla se conserva lo último válido (o los predeterminados).
        datos = _cache["datos"]
    _cache["datos"] = datos
    _cache["t"] = ahora
    return datos


def obtener_regla(equipo_id, variable):
    """Regla vigente de una variable: la personalizada si existe; si no, la predeterminada."""
    personalizada = _personalizados().get((equipo_id, variable))
    if personalizada is not None:
        return dict(personalizada)
    return REGLAS_ALERTAS.get(equipo_id, {}).get(variable)


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def _variables_configurables():
    """Solo variables numéricas medidas (sin textos ni contadores acumulativos)."""
    resultado = {}
    for equipo in EQUIPOS:
        resultado[equipo["id"]] = {
            v["clave"]: v for v in equipo["variables"]
            if v.get("tipo") not in ("texto", "contador")
        }
    return resultado


def _regla_completa(regla):
    regla = regla or {}
    return {c: regla.get(c) for c in CAMPOS}


def _error(mensaje, codigo=400):
    return jsonify({"error": mensaje}), codigo


def _autenticado():
    return "usuario_id" in session


def _puede_configurar():
    return session.get("rol") in ROLES_CONFIGURAN_UMBRALES


def _parsear_limites(cuerpo):
    """Convierte y valida los cuatro límites. Devuelve (limites, mensaje_error)."""
    limites = {}
    for campo in CAMPOS:
        bruto = cuerpo.get(campo)
        if bruto is None or (isinstance(bruto, str) and bruto.strip() == ""):
            limites[campo] = None
            continue
        if isinstance(bruto, bool):
            return None, f"Valor inválido en {campo}."
        try:
            numero = float(bruto)
        except (TypeError, ValueError):
            return None, f"Valor no numérico en {campo}."
        if not math.isfinite(numero):
            return None, f"Valor inválido en {campo}."
        limites[campo] = numero

    presentes = [(c, limites[c]) for c in CAMPOS if limites[c] is not None]
    if not presentes:
        return None, "Define al menos un límite. Para volver a los valores originales usa «Restablecer»."
    for (c1, v1), (c2, v2) in zip(presentes, presentes[1:]):
        if v1 > v2:
            return None, (
                "Los límites deben ir en orden: crítico mín. ≤ alerta mín. ≤ alerta máx. ≤ crítico máx. "
                f"({c1.replace('_', ' ')} no puede ser mayor que {c2.replace('_', ' ')})."
            )
    return limites, None


def _registrar_historial(conn, equipo_id, variable, accion, anterior, nuevo):
    conn.execute("""
        INSERT INTO historial_umbrales
        (equipo_id, variable, accion, anterior, nuevo, usuario, fecha_hora)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        equipo_id, variable, accion,
        json.dumps(anterior), json.dumps(nuevo),
        f'{session.get("nombre", "?")} ({session.get("numero_empleado", "?")})',
        datetime.now().astimezone().isoformat(timespec="seconds"),
    ))


def _serializar_variable(equipo_id, variable, personalizados):
    predeterminado = _regla_completa(REGLAS_ALERTAS.get(equipo_id, {}).get(variable["clave"]))
    personalizado = personalizados.get((equipo_id, variable["clave"]))
    actual = _regla_completa(personalizado if personalizado is not None else predeterminado)
    return {
        "clave": variable["clave"],
        "etiqueta": variable["etiqueta"],
        "unidad": variable["unidad"],
        "rango_nominal": [variable.get("min"), variable.get("max")],
        "predeterminado": predeterminado,
        "actual": actual,
        "personalizado": personalizado is not None,
    }


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
@bp.route("/api/umbrales")
def api_umbrales():
    if not _autenticado():
        return _error("No autorizado", 401)

    _invalidar_cache()
    personalizados = _personalizados()
    configurables = _variables_configurables()
    return jsonify({
        "puede_editar": _puede_configurar(),
        "equipos": [
            {
                "id": equipo["id"],
                "nombre": equipo["nombre"],
                "variables": [
                    _serializar_variable(equipo["id"], v, personalizados)
                    for v in configurables[equipo["id"]].values()
                ],
            }
            for equipo in EQUIPOS
        ],
    })


@bp.route("/api/umbrales/<equipo_id>/<variable>", methods=["PUT"])
def api_guardar_umbral(equipo_id, variable):
    if not _autenticado():
        return _error("No autorizado", 401)
    if not _puede_configurar():
        return _error("No tienes permisos para modificar umbrales.", 403)

    variables = _variables_configurables().get(equipo_id, {})
    if variable not in variables:
        return _error("Variable no encontrada o no configurable.", 404)

    cuerpo = request.get_json(silent=True)
    if not isinstance(cuerpo, dict):
        return _error("Solicitud inválida.")
    limites, mensaje = _parsear_limites(cuerpo)
    if mensaje:
        return _error(mensaje)

    predeterminado = _regla_completa(REGLAS_ALERTAS.get(equipo_id, {}).get(variable))
    conn = get_db_connection()
    try:
        anterior = _regla_completa(obtener_regla(equipo_id, variable))
        if limites == predeterminado:
            # Volvió a los valores originales: no se guarda como personalizado.
            conn.execute(
                "DELETE FROM umbrales_personalizados WHERE equipo_id = ? AND variable = ?",
                (equipo_id, variable),
            )
        else:
            conn.execute("""
                INSERT INTO umbrales_personalizados
                (equipo_id, variable, paro_bajo, alerta_baja, alerta_alta, paro_alto,
                 actualizado_por, fecha_hora)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(equipo_id, variable) DO UPDATE SET
                    paro_bajo = excluded.paro_bajo,
                    alerta_baja = excluded.alerta_baja,
                    alerta_alta = excluded.alerta_alta,
                    paro_alto = excluded.paro_alto,
                    actualizado_por = excluded.actualizado_por,
                    fecha_hora = excluded.fecha_hora
            """, (
                equipo_id, variable, limites["paro_bajo"], limites["alerta_baja"],
                limites["alerta_alta"], limites["paro_alto"],
                session.get("numero_empleado"),
                datetime.now().astimezone().isoformat(timespec="seconds"),
            ))
        _registrar_historial(conn, equipo_id, variable, "modificar", anterior, limites)
        conn.commit()
    finally:
        conn.close()

    _invalidar_cache()
    return jsonify({
        "mensaje": "Umbrales actualizados.",
        "variable": _serializar_variable(equipo_id, variables[variable], _personalizados()),
    })


@bp.route("/api/umbrales/<equipo_id>/<variable>", methods=["DELETE"])
def api_restablecer_umbral(equipo_id, variable):
    if not _autenticado():
        return _error("No autorizado", 401)
    if not _puede_configurar():
        return _error("No tienes permisos para modificar umbrales.", 403)

    variables = _variables_configurables().get(equipo_id, {})
    if variable not in variables:
        return _error("Variable no encontrada o no configurable.", 404)

    conn = get_db_connection()
    try:
        anterior = _regla_completa(obtener_regla(equipo_id, variable))
        conn.execute(
            "DELETE FROM umbrales_personalizados WHERE equipo_id = ? AND variable = ?",
            (equipo_id, variable),
        )
        predeterminado = _regla_completa(REGLAS_ALERTAS.get(equipo_id, {}).get(variable))
        _registrar_historial(conn, equipo_id, variable, "restablecer", anterior, predeterminado)
        conn.commit()
    finally:
        conn.close()

    _invalidar_cache()
    return jsonify({
        "mensaje": "Umbrales restablecidos a los valores originales.",
        "variable": _serializar_variable(equipo_id, variables[variable], _personalizados()),
    })


@bp.route("/api/umbrales/historial")
def api_historial_umbrales():
    if not _autenticado():
        return _error("No autorizado", 401)
    if not _puede_configurar():
        return _error("No tienes permisos para ver este historial.", 403)

    conn = get_db_connection()
    filas = conn.execute("""
        SELECT equipo_id, variable, accion, anterior, nuevo, usuario, fecha_hora
        FROM historial_umbrales ORDER BY id DESC LIMIT 15
    """).fetchall()
    conn.close()

    etiquetas = {
        (e["id"], v["clave"]): (e["nombre"], v["etiqueta"])
        for e in EQUIPOS for v in e["variables"]
    }
    eventos = []
    for f in filas:
        equipo_nombre, etiqueta = etiquetas.get((f["equipo_id"], f["variable"]), (f["equipo_id"], f["variable"]))
        eventos.append({
            "equipo": equipo_nombre,
            "variable": etiqueta,
            "accion": f["accion"],
            "anterior": json.loads(f["anterior"]) if f["anterior"] else None,
            "nuevo": json.loads(f["nuevo"]) if f["nuevo"] else None,
            "usuario": f["usuario"],
            "fecha_hora": f["fecha_hora"],
        })
    return jsonify({"eventos": eventos})
