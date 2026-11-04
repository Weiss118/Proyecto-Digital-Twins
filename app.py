# app.py
import os
import sqlite3
import random
import time
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file
from werkzeug.security import generate_password_hash, check_password_hash

from equipos import EQUIPOS
from alertas import REGLAS_ALERTAS, evaluar_valor

from services.influxDB import InfluxDBService
from services.report_generator import generar_pdf_auditoria, generar_csv_auditoria, generar_pdf_multilinea
from logic.auditoria_logic import evaluar_estado_linea

import umbrales
import mantenimientos

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "clave-secreta-gemelo-digital-dev")

DB_NAME = "database.db"
influx_service = InfluxDBService()

app.register_blueprint(umbrales.bp)
app.register_blueprint(mantenimientos.bp)


def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL UNIQUE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS organizaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL UNIQUE COLLATE NOCASE,
            fecha_registro TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero_empleado TEXT NOT NULL UNIQUE,
            nombre TEXT NOT NULL,
            password TEXT NOT NULL,
            rol_id INTEGER NOT NULL,
            organizacion_id INTEGER,
            activo INTEGER DEFAULT 1,
            FOREIGN KEY (rol_id) REFERENCES roles(id),
            FOREIGN KEY (organizacion_id) REFERENCES organizaciones(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lineas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organizacion_id INTEGER,
            nombre TEXT NOT NULL,
            descripcion TEXT,
            creado_por TEXT,
            fecha_creacion TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (organizacion_id) REFERENCES organizaciones(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS linea_activos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            linea_id INTEGER NOT NULL,
            equipo_id TEXT NOT NULL,
            orden INTEGER NOT NULL,
            FOREIGN KEY (linea_id) REFERENCES lineas(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS linea_personal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            linea_id INTEGER NOT NULL,
            usuario_id INTEGER NOT NULL,
            rol_asignado TEXT,
            fecha_asignacion TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (linea_id) REFERENCES lineas(id) ON DELETE CASCADE,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS eventos_alerta (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            linea_id INTEGER DEFAULT 1,
            equipo_id TEXT NOT NULL,
            equipo_nombre TEXT NOT NULL,
            variable TEXT NOT NULL,
            valor REAL,
            unidad TEXT,
            severidad TEXT NOT NULL,
            mensaje TEXT NOT NULL,
            fecha_hora TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS configuracion_linea (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_linea TEXT NOT NULL,
            velocidad REAL,
            temperatura REAL,
            presion REAL
        )
    """)

    # -------------------------------------------------------------------
    # MIGRACIÓN AUTOMÁTICA DE ESQUEMA PARA BASES DE DATOS PREVIAS
    # -------------------------------------------------------------------
    try:
        cursor.execute("ALTER TABLE lineas ADD COLUMN organizacion_id INTEGER REFERENCES organizaciones(id)")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE lineas ADD COLUMN descripcion TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE lineas ADD COLUMN creado_por TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE eventos_alerta ADD COLUMN linea_id INTEGER DEFAULT 1")
    except sqlite3.OperationalError:
        pass

    # Sembrar roles por defecto
    roles = [("Operador",), ("Tecnico",), ("Supervisor",)]
    for rol in roles:
        cursor.execute("INSERT OR IGNORE INTO roles (nombre) VALUES (?)", rol)

    # Sembrar Organización Demo por defecto
    cursor.execute("INSERT OR IGNORE INTO organizaciones (nombre) VALUES ('Organización Demo')")
    cursor.execute("SELECT id FROM organizaciones WHERE nombre = 'Organización Demo'")
    org_demo_row = cursor.fetchone()
    org_demo_id = org_demo_row["id"] if org_demo_row else None

    # Sembrar usuarios demo por defecto
    usuarios_demo = [
        ("1001", "Operador Demo", "op123", "Operador"),
        ("2001", "Técnico Demo", "tec123", "Tecnico"),
        ("3001", "Supervisor Demo", "admin123", "Supervisor")
    ]

    for numero, nombre, password, rol_nombre in usuarios_demo:
        cursor.execute("SELECT id FROM roles WHERE nombre = ?", (rol_nombre,))
        rol_row = cursor.fetchone()
        if not rol_row:
            continue
        rol_id = rol_row["id"]

        cursor.execute("SELECT id FROM usuarios WHERE numero_empleado = ?", (numero,))
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO usuarios (numero_empleado, nombre, password, rol_id, organizacion_id)
                VALUES (?, ?, ?, ?, ?)
            """, (numero, nombre, generate_password_hash(password), rol_id, org_demo_id))

    # Sembrar línea predeterminada si no existe ninguna
    cursor.execute("SELECT COUNT(*) AS total FROM lineas")
    if cursor.fetchone()["total"] == 0:
        cursor.execute("INSERT INTO lineas (id, organizacion_id, nombre, descripcion) VALUES (1, ?, 'Línea Ensamblado Principal', 'Línea base predeterminada')", (org_demo_id,))
        
        activos_default = ["motor", "banda", "compresor", "bomba", "chiller", "reflujo", "inyectora", "cnc"]
        for idx, eq_id in enumerate(activos_default, start=1):
            cursor.execute("INSERT INTO linea_activos (linea_id, equipo_id, orden) VALUES (1, ?, ?)", (eq_id, idx))

    cursor.execute("SELECT COUNT(*) AS total FROM configuracion_linea")
    if cursor.fetchone()["total"] == 0:
        cursor.execute("""
            INSERT INTO configuracion_linea (nombre_linea, velocidad, temperatura, presion)
            VALUES (?, ?, ?, ?)
        """, ("Línea 1", 80, 70, 3.5))

    conn.commit()
    conn.close()


init_db()

_severidad_alertas_anterior = {}


def registrar_cambio_alerta(linea_id, equipo, variable, valor, unidad, resultado):
    clave = f"{linea_id}.{equipo['id']}.{variable['clave']}"
    severidad = resultado["severidad"]
    anterior = _severidad_alertas_anterior.get(clave, "normal")
    _severidad_alertas_anterior[clave] = severidad

    if severidad == anterior or severidad == "normal":
        return

    conn = get_db_connection()
    conn.execute("""
        INSERT INTO eventos_alerta
        (linea_id, equipo_id, equipo_nombre, variable, valor, unidad, severidad, mensaje, fecha_hora)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        linea_id, equipo["id"], equipo["nombre"], variable["etiqueta"],
        float(valor) if valor is not None else None, unidad, severidad,
        resultado["mensaje"], datetime.now().astimezone().isoformat(timespec="seconds")
    ))
    conn.commit()
    conn.close()


simulacion = {"estado": "Operando", "ultimo_update": time.time()}
valores_equipos = {}
estados_equipos = {}
control_equipos = {"ultimo_update": time.time()}


def obtener_estado_activo(linea_id, equipo_id):
    clave = f"{linea_id}.{equipo_id}"
    if simulacion["estado"] in ["Detenido", "Emergencia"]:
        return simulacion["estado"]
    return estados_equipos.get(clave, "Operando")


def actualizar_equipos_linea(linea_id, lista_equipos_ordenados):
    ahora = time.time()
    if ahora - control_equipos["ultimo_update"] < 1:
        return
    control_equipos["ultimo_update"] = ahora

    for equipo in lista_equipos_ordenados:
        estado_activo = obtener_estado_activo(linea_id, equipo["id"])
        esta_operando = (estado_activo == "Operando")

        for variable in equipo["variables"]:
            if "calculo" in variable or variable.get("tipo") == "texto":
                continue

            clave = f'{linea_id}.{equipo["id"]}.{variable["clave"]}'
            clave_var = variable["clave"].lower()

            if clave not in valores_equipos:
                valores_equipos[clave] = float(variable["inicio"]) if variable.get("tipo") == "contador" else random.uniform(variable["min"], variable["max"])

            if variable.get("tipo") == "contador":
                if esta_operando:
                    minimo, maximo = variable["incremento"]
                    valores_equipos[clave] += random.uniform(minimo, maximo)
                continue

            es_termica = any(t in clave_var for t in ["temp", "temperatura", "zona", "pico", "agua"])
            if es_termica:
                temp_actual = valores_equipos[clave]
                min_nom, max_nom = variable["min"], variable["max"]

                if esta_operando:
                    if temp_actual < min_nom:
                        valores_equipos[clave] = min(min_nom, temp_actual + random.uniform(1.0, 2.5))
                    elif temp_actual > max_nom:
                        valores_equipos[clave] = max(max_nom, temp_actual - random.uniform(0.5, 1.0))
                    else:
                        rango = max_nom - min_nom
                        nuevo = temp_actual + random.uniform(-0.05, 0.05) * rango
                        valores_equipos[clave] = max(min_nom, min(max_nom, nuevo))
                else:
                    if temp_actual > 25.0:
                        valores_equipos[clave] = max(25.0, temp_actual - random.uniform(0.5, 1.2))
                continue

            if esta_operando:
                rango = variable["max"] - variable["min"]
                nuevo = valores_equipos[clave] + random.uniform(-0.05, 0.05) * rango
                valores_equipos[clave] = max(variable["min"], min(variable["max"], nuevo))
            else:
                valores_equipos[clave] = 0.0


def obtener_estado_linea_completo(linea_id):
    conn = get_db_connection()
    filas = conn.execute("""
        SELECT id, equipo_id, orden FROM linea_activos
        WHERE linea_id = ? ORDER BY orden ASC
    """, (linea_id,)).fetchall()
    conn.close()

    dict_equipos = {e["id"]: e for e in EQUIPOS}
    equipos_linea = []

    for f in filas:
        eq_base = dict_equipos.get(f["equipo_id"])
        if not eq_base:
            continue

        instancia_id = f"{f['equipo_id']}_{f['orden']}"
        nombre_instancia = f"{eq_base['nombre']} #{f['orden']}"

        variables_copia = [dict(v) for v in eq_base["variables"]]

        equipos_linea.append({
            "id": instancia_id,
            "base_id": eq_base["id"],
            "nombre": nombre_instancia,
            "tipo": eq_base["tipo"],
            "variables": variables_copia
        })

    actualizar_equipos_linea(linea_id, equipos_linea)
    resultado = []

    for equipo in equipos_linea:
        estado_activo = obtener_estado_activo(linea_id, equipo["id"])
        valores = {}

        for variable in equipo["variables"]:
            if "calculo" in variable or variable.get("tipo") == "texto":
                continue
            clave_sp = f'{linea_id}.{equipo["id"]}.{variable["clave"]}'
            valores[variable["clave"]] = valores_equipos.get(clave_sp, variable.get("min", 0))

        for variable in equipo["variables"]:
            if "calculo" in variable:
                valores[variable["clave"]] = variable["calculo"](valores)

        variables_salida = []
        variables_dict_influx = {}

        for variable in equipo["variables"]:
            clave_variable = variable["clave"]

            if variable.get("tipo") == "texto":
                valor = "Sin detección" if (estado_activo == "Detenido" and "atasco" in clave_variable) else variable["valor"]
            else:
                decimales = variable.get("decimales", 1)
                valor = round(valores[variable["clave"]], decimales)
                if decimales == 0:
                    valor = int(valor)

            regla = umbrales.obtener_regla(equipo["base_id"], clave_variable)

            if estado_activo in ["Detenido", "Inactivo"]:
                evaluacion = {"severidad": "normal", "mensaje": "Equipo en paro programado"}
            else:
                evaluacion = evaluar_valor(valor, regla) if regla else {"severidad": "sin_regla", "mensaje": "Sin umbral"}

            if regla and estado_activo == "Operando":
                registrar_cambio_alerta(linea_id, equipo, variable, valor, variable["unidad"], evaluacion)

            variables_salida.append({
                "clave": clave_variable,
                "etiqueta": variable["etiqueta"],
                "valor": valor,
                "unidad": variable["unidad"],
                "severidad": evaluacion["severidad"],
                "mensaje_alerta": evaluacion["mensaje"]
            })

            variables_dict_influx[clave_variable] = valor

        influx_service.registrar_metricas_activo(
            linea_id=str(linea_id),
            activo_id=equipo["id"],
            variables_dict=variables_dict_influx,
            estado=estado_activo
        )

        resultado.append({
            "id": equipo["id"],
            "base_id": equipo["base_id"],
            "nombre": equipo["nombre"],
            "tipo": equipo["tipo"],
            "estado": estado_activo,
            "variables": variables_salida
        })

    return resultado


# RUTAS DE VISTA BASE Y AUTENTICACIÓN

@app.route("/")
def inicio():
    if "usuario_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        numero_empleado = request.form.get("numero_empleado")
        password = request.form.get("password")

        conn = get_db_connection()
        usuario = conn.execute("""
            SELECT usuarios.*, roles.nombre AS rol, organizaciones.nombre AS organizacion
            FROM usuarios
            INNER JOIN roles ON usuarios.rol_id = roles.id
            LEFT JOIN organizaciones ON usuarios.organizacion_id = organizaciones.id
            WHERE usuarios.numero_empleado = ? AND usuarios.activo = 1
        """, (numero_empleado,)).fetchone()
        conn.close()

        if usuario:
            pwd_db = usuario["password"]
            es_valido = False
            try:
                es_valido = check_password_hash(pwd_db, password)
            except Exception:
                es_valido = (pwd_db == password)

            if es_valido:
                session["usuario_id"] = usuario["id"]
                session["numero_empleado"] = usuario["numero_empleado"]
                session["nombre"] = usuario["nombre"]
                session["rol"] = usuario["rol"]
                session["organizacion_id"] = usuario["organizacion_id"]
                session["organizacion"] = usuario["organizacion"]
                return redirect(url_for("dashboard"))

        flash("Número de empleado o contraseña incorrectos.", "danger")

    return render_template("login.html")


@app.route("/registro", methods=["GET", "POST"])
def registro():
    conn = get_db_connection()

    if request.method == "POST":
        numero_empleado = request.form.get("numero_empleado")
        nombre = request.form.get("nombre")
        password = request.form.get("password")
        rol_id = request.form.get("rol_id")

        if not numero_empleado or not nombre or not password or not rol_id:
            flash("Por favor completa todos los campos del formulario.", "danger")
        else:
            existente = conn.execute(
                "SELECT id FROM usuarios WHERE numero_empleado = ?", (numero_empleado,)
            ).fetchone()

            if existente:
                flash("El número de empleado ya se encuentra registrado.", "danger")
            else:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO usuarios (numero_empleado, nombre, password, rol_id)
                    VALUES (?, ?, ?, ?)
                """, (numero_empleado, nombre, generate_password_hash(password), rol_id))
                conn.commit()
                conn.close()

                flash("Usuario registrado exitosamente. Ya puedes iniciar sesión.", "info")
                return redirect(url_for("login"))

    roles = conn.execute("SELECT * FROM roles").fetchall()
    conn.close()
    return render_template("registro.html", roles=roles)


@app.route("/registro-organizacion", methods=["GET", "POST"])
def registro_organizacion():
    datos = {
        "organizacion": (request.form.get("organizacion") or "").strip(),
        "nombre": (request.form.get("nombre") or "").strip(),
        "numero_empleado": (request.form.get("numero_empleado") or "").strip(),
    }

    if request.method == "POST":
        password = request.form.get("password") or ""
        confirmar = request.form.get("confirmar_password") or ""
        error = None

        if not all(datos.values()) or not password:
            error = "Por favor completa todos los campos del formulario."
        elif len(password) < 6:
            error = "La contraseña debe tener al menos 6 caracteres."
        elif password != confirmar:
            error = "Las contraseñas no coinciden."

        if error is None:
            conn = get_db_connection()
            try:
                if conn.execute(
                    "SELECT id FROM organizaciones WHERE nombre = ?", (datos["organizacion"],)
                ).fetchone():
                    error = "Ya existe una organización con ese nombre."
                elif conn.execute(
                    "SELECT id FROM usuarios WHERE numero_empleado = ?", (datos["numero_empleado"],)
                ).fetchone():
                    error = "El número de empleado ya se encuentra registrado."
                else:
                    rol = conn.execute(
                        "SELECT id FROM roles WHERE nombre = 'Supervisor'"
                    ).fetchone()
                    cursor = conn.cursor()
                    cursor.execute(
                        "INSERT INTO organizaciones (nombre) VALUES (?)", (datos["organizacion"],)
                    )
                    cursor.execute("""
                        INSERT INTO usuarios (numero_empleado, nombre, password, rol_id, organizacion_id)
                        VALUES (?, ?, ?, ?, ?)
                    """, (datos["numero_empleado"], datos["nombre"],
                          generate_password_hash(password), rol["id"], cursor.lastrowid))
                    conn.commit()
            except sqlite3.IntegrityError:
                conn.rollback()
                error = "No se pudo registrar la organización. Verifica los datos e intenta de nuevo."
            finally:
                conn.close()

        if error is None:
            flash("Organización registrada. Inicia sesión con tu número de empleado.", "info")
            return redirect(url_for("login"))

        flash(error, "danger")

    return render_template("registro_organizacion.html", datos=datos)


@app.route("/dashboard")
def dashboard():
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    return render_template(
        "dashboard.html",
        nombre=session["nombre"],
        numero_empleado=session["numero_empleado"],
        rol=session["rol"],
        organizacion=session.get("organizacion")
    )


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# API REST

@app.route("/api/lineas", methods=["GET", "POST"])
def api_lineas():
    if "usuario_id" not in session:
        return jsonify({"error": "No autorizado"}), 401

    conn = get_db_connection()

    if request.method == "POST":
        if session.get("rol") != "Supervisor":
            return jsonify({"error": "Acceso denegado. Solo el Supervisor tiene permisos para crear líneas de trabajo."}), 403

        datos = request.get_json() or {}
        nombre = datos.get("nombre", "").strip()
        descripcion = datos.get("descripcion", "").strip()
        activos_ordenados = datos.get("activos", [])

        if not nombre or not activos_ordenados:
            return jsonify({"error": "El nombre y al menos un activo son requeridos."}), 400

        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO lineas (organizacion_id, nombre, descripcion, creado_por)
            VALUES (?, ?, ?, ?)
        """, (session.get("organizacion_id"), nombre, descripcion, session.get("nombre")))
        linea_id = cursor.lastrowid

        for idx, eq_id in enumerate(activos_ordenados, start=1):
            cursor.execute("""
                INSERT INTO linea_activos (linea_id, equipo_id, orden)
                VALUES (?, ?, ?)
            """, (linea_id, eq_id, idx))

        conn.commit()
        conn.close()
        return jsonify({"mensaje": f"Línea de trabajo '{nombre}' creada exitosamente.", "linea_id": linea_id}), 201

    lineas = conn.execute("SELECT * FROM lineas ORDER BY id ASC").fetchall()
    conn.close()
    return jsonify([dict(l) for l in lineas])


@app.route("/api/lineas/<int:linea_id>/personal", methods=["GET", "POST"])
def api_linea_personal(linea_id):
    if "usuario_id" not in session:
        return jsonify({"error": "No autorizado"}), 401

    conn = get_db_connection()

    if request.method == "POST":
        if session.get("rol") != "Supervisor":
            return jsonify({"error": "Solo el supervisor puede asignar personal."}), 403

        datos = request.get_json() or {}
        usuario_id = datos.get("usuario_id")
        rol_asignado = datos.get("rol_asignado", "Operador de Línea")

        conn.execute("""
            INSERT INTO linea_personal (linea_id, usuario_id, rol_asignado)
            VALUES (?, ?, ?)
        """, (linea_id, usuario_id, rol_asignado))
        conn.commit()
        conn.close()
        return jsonify({"mensaje": "Personal asignado a la línea."})

    personal = conn.execute("""
        SELECT lp.id, u.nombre, u.numero_empleado, lp.rol_asignado, lp.fecha_asignacion
        FROM linea_personal lp
        INNER JOIN usuarios u ON lp.usuario_id = u.id
        WHERE lp.linea_id = ?
    """, (linea_id,)).fetchall()
    conn.close()
    return jsonify([dict(p) for p in personal])


@app.route("/api/equipos/disponibles")
def api_equipos_disponibles():
    if "usuario_id" not in session:
        return jsonify({"error": "No autorizado"}), 401
    
    return jsonify([
        {"id": e["id"], "nombre": e["nombre"], "tipo": e["tipo"]}
        for e in EQUIPOS
    ])


@app.route("/api/equipos/linea/<int:linea_id>")
def api_equipos_linea(linea_id):
    if "usuario_id" not in session:
        return jsonify({"error": "No autorizado"}), 401
    return jsonify(obtener_estado_linea_completo(linea_id))


@app.route("/api/equipos")
def api_equipos():
    if "usuario_id" not in session:
        return jsonify({"error": "No autorizado"}), 401
    return jsonify(obtener_estado_linea_completo(1))


@app.route("/api/lineas/<int:linea_id>/estado-equipo", methods=["POST"])
def cambiar_estado_equipo_linea(linea_id):
    if "usuario_id" not in session:
        return jsonify({"error": "No autorizado"}), 401

    datos = request.get_json() or {}
    equipo_id = datos.get("equipo_id")
    nuevo_estado = datos.get("estado", "Operando")

    estados_equipos[f"{linea_id}.{equipo_id}"] = nuevo_estado
    return jsonify({"mensaje": f"Estado del activo cambiado a {nuevo_estado}."})


@app.route("/api/equipos/<equipo_id>/estado", methods=["POST"])
def cambiar_estado_equipo(equipo_id):
    if "usuario_id" not in session:
        return jsonify({"error": "No autorizado"}), 401

    rol = session.get("rol")
    if rol not in ["Tecnico", "Supervisor"]:
        return jsonify({"error": "No tienes permisos para realizar esta acción."}), 403

    datos = request.get_json() or {}
    nuevo_estado = datos.get("estado", "Operando")

    estados_equipos[f"1.{equipo_id}"] = nuevo_estado
    return jsonify({"mensaje": f"Estado del activo {equipo_id} cambiado a {nuevo_estado}."})


@app.route("/api/alertas")
def api_alertas():
    if "usuario_id" not in session:
        return jsonify({"error": "No autorizado"}), 401

    linea_id = request.args.get("linea_id", type=int, default=1)

    conn = get_db_connection()
    registros = conn.execute("""
        SELECT equipo_id, equipo_nombre, variable, valor, unidad, severidad, mensaje, fecha_hora
        FROM eventos_alerta
        WHERE linea_id = ?
        ORDER BY id DESC LIMIT 50
    """, (linea_id,)).fetchall()
    conn.close()

    return jsonify({"eventos": [dict(r) for r in registros]})


@app.route("/api/configuracion")
def api_configuracion():
    if "usuario_id" not in session:
        return jsonify({"error": "No autorizado"}), 401

    conn = get_db_connection()
    configuracion = conn.execute("SELECT * FROM configuracion_linea LIMIT 1").fetchone()
    conn.close()

    if not configuracion:
        return jsonify({
            "nombre_linea": "Línea 1",
            "velocidad": 80.0,
            "temperatura": 70.0,
            "presion": 3.5
        })

    return jsonify({
        "nombre_linea": configuracion["nombre_linea"],
        "velocidad": configuracion["velocidad"],
        "temperatura": configuracion["temperatura"],
        "presion": configuracion["presion"]
    })


@app.route("/api/funciones/<accion>", methods=["POST"])
def funciones(accion):
    if "usuario_id" not in session:
        return jsonify({"error": "No autorizado"}), 401

    rol = session.get("rol")
    if rol not in ["Tecnico", "Supervisor"]:
        return jsonify({"error": "No tienes permisos para realizar esta acción."}), 403

    if accion == "encender":
        simulacion["estado"] = "Operando"
        return jsonify({"mensaje": "Sistema virtual encendido."})

    elif accion == "detener":
        simulacion["estado"] = "Detenido"
        return jsonify({"mensaje": "Sistema virtual detenido."})

    elif accion == "emergencia":
        simulacion["estado"] = "Emergencia"
        return jsonify({"mensaje": "Paro de emergencia virtual activado."})

    return jsonify({"error": "Acción no reconocida."}), 400


# RUTAS DE AUDITORÍA Y EXPORTACIÓN DE REPORTES

@app.route("/auditoria/linea/<int:linea_id>")
def ver_auditoria_linea(linea_id):
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    linea = conn.execute("SELECT * FROM lineas WHERE id = ?", (linea_id,)).fetchone()
    conn.close()

    nombre_linea = linea["nombre"] if linea else f"Línea #{linea_id}"

    lista_activos = obtener_estado_linea_completo(linea_id)
    dictamen, descripcion, color_badge = evaluar_estado_linea(lista_activos)

    return render_template(
        "auditoria_linea.html",
        linea_id=linea_id,
        nombre_linea=nombre_linea,
        dictamen=dictamen,
        descripcion=descripcion,
        color_badge=color_badge,
        activos=lista_activos,
        nombre_usuario=session.get("nombre"),
        rol=session.get("rol")
    )


@app.route("/exportar/auditoria/<int:linea_id>/<formato>")
def exportar_auditoria(linea_id, formato):
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    linea = conn.execute("SELECT * FROM lineas WHERE id = ?", (linea_id,)).fetchone()
    conn.close()

    nombre_linea = linea["nombre"] if linea else f"Línea #{linea_id}"

    lista_activos = obtener_estado_linea_completo(linea_id)
    dictamen, descripcion, _ = evaluar_estado_linea(lista_activos)
    fecha_str = datetime.now().strftime("%d/%m/%Y %H:%M hrs")
    auditor = session.get("nombre", "Auditor PWA")

    if formato.lower() == "pdf":
        pdf_buffer = generar_pdf_auditoria(
            nombre_linea=nombre_linea,
            dictamen_linea=dictamen,
            descripcion_dictamen=descripcion,
            lista_activos=lista_activos,
            fecha_str=fecha_str,
            auditor=auditor
        )
        return send_file(
            pdf_buffer,
            as_attachment=True,
            download_name=f"Reporte_Auditoria_Linea_{linea_id}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
            mimetype="application/pdf"
        )

    elif formato.lower() == "csv":
        csv_buffer = generar_csv_auditoria(
            nombre_linea=nombre_linea,
            dictamen_linea=dictamen,
            lista_activos=lista_activos
        )
        return send_file(
            csv_buffer,
            as_attachment=True,
            download_name=f"Auditoria_Linea_{linea_id}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mimetype="text/csv"
        )

    return redirect(url_for("dashboard"))


@app.route("/exportar/auditoria/multilinea", methods=["POST"])
def exportar_auditoria_multilinea():
    if "usuario_id" not in session:
        return jsonify({"error": "No autorizado"}), 401

    datos = request.get_json() or {}
    lineas_ids = datos.get("lineas_ids", [1])

    conn = get_db_connection()
    lineas_reporte = []

    for lid in lineas_ids:
        linea_row = conn.execute("SELECT * FROM lineas WHERE id = ?", (lid,)).fetchone()
        nombre_linea = linea_row["nombre"] if linea_row else f"Línea #{lid}"
        activos = obtener_estado_linea_completo(lid)
        dictamen, descripcion, _ = evaluar_estado_linea(activos)

        lineas_reporte.append({
            "linea_id": lid,
            "nombre": nombre_linea,
            "dictamen": dictamen,
            "descripcion": descripcion,
            "activos": activos
        })

    conn.close()

    fecha_str = datetime.now().strftime("%d/%m/%Y %H:%M hrs")
    auditor = session.get("nombre", "Auditor PWA")

    pdf_buffer = generar_pdf_multilinea(
        lineas_datos=lineas_reporte,
        fecha_str=fecha_str,
        auditor=auditor
    )

    return send_file(
        pdf_buffer,
        as_attachment=True,
        download_name=f"Reporte_Consolidado_Zonas_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
        mimetype="application/pdf"
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)