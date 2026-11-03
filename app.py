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

# IMPORTS DE SPRINT 2 (InfluxDB + Auditoría + Reportes)
from services.influxDB import InfluxDBService
from services.report_generator import generar_pdf_auditoria, generar_csv_auditoria
from logic.auditoria_logic import evaluar_estado_linea

# EXTENSIONES: umbrales configurables por rol y calendario de mantenimientos
import umbrales
import mantenimientos

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "clave-secreta-gemelo-digital-dev")

DB_NAME = "database.db"

# Inicializar servicio InfluxDB Cloud
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
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero_empleado TEXT NOT NULL UNIQUE,
            nombre TEXT NOT NULL,
            password TEXT NOT NULL,
            rol_id INTEGER NOT NULL,
            activo INTEGER DEFAULT 1,
            FOREIGN KEY (rol_id) REFERENCES roles(id)
        )
    """)

    try:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN activo INTEGER DEFAULT 1")
    except sqlite3.OperationalError:
        pass

    # Organizaciones (tenants): cada cliente registra la suya
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS organizaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL UNIQUE COLLATE NOCASE,
            fecha_registro TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    try:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN organizacion_id INTEGER REFERENCES organizaciones(id)")
    except sqlite3.OperationalError:
        pass

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS activos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            tipo TEXT NOT NULL,
            estado TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lineas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL UNIQUE
        )
    """)

    try:
        cursor.execute("ALTER TABLE activos ADD COLUMN linea_id INTEGER DEFAULT 1")
    except sqlite3.OperationalError:
        pass

    cursor.execute("SELECT COUNT(*) AS total FROM lineas")
    if cursor.fetchone()["total"] == 0:
        cursor.execute("INSERT INTO lineas (id, nombre) VALUES (1, 'Línea Principal de Manufactura')")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS metricas_produccion (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            produccion INTEGER,
            eficiencia REAL,
            tiempo_operacion REAL,
            fecha_hora TEXT DEFAULT CURRENT_TIMESTAMP
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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS eventos_alerta (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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

    roles = [("Operador",), ("Tecnico",), ("Supervisor",)]
    for rol in roles:
        cursor.execute("INSERT OR IGNORE INTO roles (nombre) VALUES (?)", rol)

    usuarios = [
        ("1001", "Operador Demo", "op123", "Operador"),
        ("2001", "Técnico Demo", "tec123", "Tecnico"),
        ("3001", "Supervisor Demo", "admin123", "Supervisor")
    ]

    for numero, nombre, password, rol in usuarios:
        cursor.execute("SELECT id FROM roles WHERE nombre = ?", (rol,))
        rol_row = cursor.fetchone()
        if not rol_row:
            continue
        rol_id = rol_row["id"]

        cursor.execute("SELECT id FROM usuarios WHERE numero_empleado = ?", (numero,))
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO usuarios (numero_empleado, nombre, password, rol_id)
                VALUES (?, ?, ?, ?)
            """, (numero, nombre, generate_password_hash(password), rol_id))

    # Los usuarios existentes (demo) quedan en una organización por defecto
    cursor.execute("INSERT OR IGNORE INTO organizaciones (nombre) VALUES ('Organización Demo')")
    cursor.execute("SELECT id FROM organizaciones WHERE nombre = 'Organización Demo'")
    org_demo_id = cursor.fetchone()["id"]
    cursor.execute(
        "UPDATE usuarios SET organizacion_id = ? WHERE organizacion_id IS NULL",
        (org_demo_id,)
    )

    activos = [
        ("Motor principal", "Motor", "Operando"),
        ("Banda transportadora", "Transportador", "Operando"),
        ("Sensor de temperatura", "Sensor virtual", "Activo"),
        ("Sensor de presión", "Sensor virtual", "Activo")
    ]

    for nombre, tipo, estado in activos:
        cursor.execute("SELECT id FROM activos WHERE nombre = ?", (nombre,))
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO activos (nombre, tipo, estado)
                VALUES (?, ?, ?)
            """, (nombre, tipo, estado))

    cursor.execute("SELECT COUNT(*) AS total FROM configuracion_linea")
    if cursor.fetchone()["total"] == 0:
        cursor.execute("""
            INSERT INTO configuracion_linea (nombre_linea, velocidad, temperatura, presion)
            VALUES (?, ?, ?, ?)
        """, ("Línea 1", 80, 70, 3.5))

    conn.commit()
    conn.close()


init_db()

# Registro de alertas
_severidad_alertas_anterior = {}


def registrar_cambio_alerta(equipo, variable, valor, unidad, resultado):
    clave = f"{equipo['id']}.{variable['clave']}"
    severidad = resultado["severidad"]
    anterior = _severidad_alertas_anterior.get(clave, "normal")
    _severidad_alertas_anterior[clave] = severidad

    if severidad == anterior or severidad == "normal":
        return

    conn = get_db_connection()
    conn.execute("""
        INSERT INTO eventos_alerta
        (equipo_id, equipo_nombre, variable, valor, unidad, severidad, mensaje, fecha_hora)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        equipo["id"], equipo["nombre"], variable["etiqueta"],
        float(valor) if valor is not None else None, unidad, severidad,
        resultado["mensaje"], datetime.now().astimezone().isoformat(timespec="seconds")
    ))
    conn.commit()
    conn.close()


# SIMULACIÓN DEL GEMELO DIGITAL GLOBAL

simulacion = {
    "temperatura": 70.0,
    "presion": 3.5,
    "velocidad": 80.0,
    "nivel": 75.0,
    "produccion": 0,
    "eficiencia": 92.0,
    "estado": "Operando",
    "ultimo_update": time.time()
}


def actualizar_simulacion():
    ahora = time.time()
    if ahora - simulacion["ultimo_update"] >= 1:
        simulacion["ultimo_update"] = ahora

        if simulacion["estado"] == "Operando":
            simulacion["temperatura"] = max(60, min(85, simulacion["temperatura"] + random.uniform(-0.8, 0.8)))
            simulacion["presion"] = max(2.5, min(4.5, simulacion["presion"] + random.uniform(-0.08, 0.08)))
            simulacion["velocidad"] = max(60, min(100, simulacion["velocidad"] + random.uniform(-2, 2)))
            simulacion["nivel"] = max(0, min(100, simulacion["nivel"] + random.uniform(-1.5, 1.5)))
            simulacion["produccion"] += random.randint(1, 4)
            simulacion["eficiencia"] = random.uniform(88, 97)
        else:
            # Enfriamiento global de simulación base al estar detenido
            simulacion["temperatura"] = max(25.0, simulacion["temperatura"] - 1.0)
            simulacion["velocidad"] = 0.0
            simulacion["presion"] = max(0.0, simulacion["presion"] - 0.5)


# ESTADO POR ACTIVO INDIVIDUAL Y SIMULACIÓN FÍSICA APLICADA
valores_equipos = {}
control_equipos = {"ultimo_update": time.time()}
estados_equipos = {}  # Guarda estados individuales ('Operando', 'Detenido', etc.)


def obtener_estado_activo(equipo_id):
    """Retorna el estado operativo efectivo del activo considerando paros globales."""
    if simulacion["estado"] in ["Detenido", "Emergencia"]:
        return simulacion["estado"]
    return estados_equipos.get(equipo_id, "Operando")


def inicializar_equipos():
    for equipo in EQUIPOS:
        estados_equipos[equipo["id"]] = "Operando"
        for variable in equipo["variables"]:
            if "calculo" in variable or variable.get("tipo") == "texto":
                continue

            clave = f'{equipo["id"]}.{variable["clave"]}'

            if variable.get("tipo") == "contador":
                valores_equipos[clave] = float(variable["inicio"])
            else:
                valores_equipos[clave] = random.uniform(variable["min"], variable["max"])


def actualizar_equipos():
    ahora = time.time()
    if ahora - control_equipos["ultimo_update"] < 1:
        return
    control_equipos["ultimo_update"] = ahora

    for equipo in EQUIPOS:
        estado_activo = obtener_estado_activo(equipo["id"])
        esta_operando = (estado_activo == "Operando")

        for variable in equipo["variables"]:
            if "calculo" in variable or variable.get("tipo") == "texto":
                continue

            clave = f'{equipo["id"]}.{variable["clave"]}'
            clave_var = variable["clave"].lower()

            # 1. Contadores (incrementan solo al estar operando)
            if variable.get("tipo") == "contador":
                if esta_operando:
                    minimo, maximo = variable["incremento"]
                    valores_equipos[clave] += random.uniform(minimo, maximo)
                continue

            # 2. Variables térmicas (calentamiento y enfriamiento paulatino)
            es_termica = any(t in clave_var for t in ["temp", "temperatura", "zona", "pico", "agua"])
            if es_termica:
                temp_actual = valores_equipos[clave]
                min_nom = variable["min"]
                max_nom = variable["max"]

                if esta_operando:
                    if temp_actual < min_nom:
                        # Calentamiento paulatino hasta alcanzar el rango nominal
                        valores_equipos[clave] = min(min_nom, temp_actual + random.uniform(1.0, 2.5))
                    elif temp_actual > max_nom:
                        # Estabilización progresiva hacia el rango máximo
                        valores_equipos[clave] = max(max_nom, temp_actual - random.uniform(0.5, 1.0))
                    else:
                        # Operación nominal con oscilación suave
                        rango = max_nom - min_nom
                        nuevo = temp_actual + random.uniform(-0.05, 0.05) * rango
                        valores_equipos[clave] = max(min_nom, min(max_nom, nuevo))
                else:
                    # Enfriamiento paulatino hacia temperatura ambiente (~25.0 °C)
                    if temp_actual > 25.0:
                        valores_equipos[clave] = max(25.0, temp_actual - random.uniform(0.5, 1.2))
                    elif temp_actual < 25.0:
                        valores_equipos[clave] = min(25.0, temp_actual + random.uniform(0.2, 0.5))
                continue

            # 3. Variables mecánicas y eléctricas (caen a 0 inmediatamente al detenerse)
            if esta_operando:
                rango = variable["max"] - variable["min"]
                nuevo = valores_equipos[clave] + random.uniform(-0.05, 0.05) * rango
                valores_equipos[clave] = max(variable["min"], min(variable["max"], nuevo))
            else:
                valores_equipos[clave] = 0.0


inicializar_equipos()


def obtener_estado_equipos_completo():
    actualizar_simulacion()
    actualizar_equipos()

    resultado = []

    for equipo in EQUIPOS:
        estado_activo = obtener_estado_activo(equipo["id"])
        valores = {}

        for variable in equipo["variables"]:
            if "calculo" in variable or variable.get("tipo") == "texto":
                continue
            valores[variable["clave"]] = valores_equipos[f'{equipo["id"]}.{variable["clave"]}']

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

            # Umbral vigente: el personalizado (si un usuario autorizado lo cambió) o el predeterminado
            regla = umbrales.obtener_regla(equipo["id"], clave_variable)

            # Si el activo está detenido, evitar disparar alertas por caída a 0 RPM
            if estado_activo in ["Detenido", "Inactivo"]:
                evaluacion = {"severidad": "normal", "mensaje": "Equipo en paro programado"}
            else:
                evaluacion = evaluar_valor(valor, regla) if regla else {
                    "severidad": "sin_regla",
                    "mensaje": "Variable sin umbral configurado"
                }

            if regla and estado_activo == "Operando":
                registrar_cambio_alerta(equipo, variable, valor, variable["unidad"], evaluacion)

            variables_salida.append({
                "clave": clave_variable,
                "etiqueta": variable["etiqueta"],
                "valor": valor,
                "unidad": variable["unidad"],
                "severidad": evaluacion["severidad"],
                "mensaje_alerta": evaluacion["mensaje"]
            })

            variables_dict_influx[clave_variable] = valor

        # Transmitir diccionario completo a InfluxDB Cloud
        influx_service.registrar_metricas_activo(
            linea_id=1,
            activo_id=equipo["id"],
            variables_dict=variables_dict_influx,
            estado=estado_activo
        )

        resultado.append({
            "id": equipo["id"],
            "nombre": equipo["nombre"],
            "tipo": equipo["tipo"],
            "estado": estado_activo,
            "variables": variables_salida
        })

    return resultado


# RUTAS DE AUTENTICACIÓN Y REGISTRO

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
            SELECT usuarios.*, roles.nombre AS rol,
                   organizaciones.nombre AS organizacion
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
    """Historia #3278: un nuevo cliente registra su organización.

    Crea la organización y su primer usuario administrador. El rol del
    administrador es siempre Supervisor y no se puede elegir en el formulario.
    """
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


# RUTAS API REST

@app.route("/api/equipos")
def api_equipos():
    if "usuario_id" not in session:
        return jsonify({"error": "No autorizado"}), 401
    return jsonify(obtener_estado_equipos_completo())


@app.route("/api/equipos/<equipo_id>/estado", methods=["POST"])
def cambiar_estado_equipo(equipo_id):
    if "usuario_id" not in session:
        return jsonify({"error": "No autorizado"}), 401

    rol = session.get("rol")
    if rol not in ["Tecnico", "Supervisor"]:
        return jsonify({"error": "No tienes permisos para realizar esta acción."}), 403

    datos = request.get_json() or {}
    nuevo_estado = datos.get("estado", "Operando")

    estados_equipos[equipo_id] = nuevo_estado
    return jsonify({"mensaje": f"Estado del activo {equipo_id} cambiado a {nuevo_estado}."})


@app.route("/api/variables")
def api_variables():
    if "usuario_id" not in session:
        return jsonify({"error": "No autorizado"}), 401

    actualizar_simulacion()
    return jsonify({
        "temperatura": round(simulacion["temperatura"], 2),
        "presion": round(simulacion["presion"], 2),
        "velocidad": round(simulacion["velocidad"], 2),
        "nivel": round(simulacion["nivel"], 2)
    })


@app.route("/api/estado")
def api_estado():
    if "usuario_id" not in session:
        return jsonify({"error": "No autorizado"}), 401

    actualizar_simulacion()
    return jsonify({"estado": simulacion["estado"]})


@app.route("/api/metricas")
def api_metricas():
    if "usuario_id" not in session:
        return jsonify({"error": "No autorizado"}), 401

    actualizar_simulacion()
    return jsonify({
        "produccion": simulacion["produccion"],
        "eficiencia": round(simulacion["eficiencia"], 2)
    })


@app.route("/api/activos")
def api_activos():
    if "usuario_id" not in session:
        return jsonify({"error": "No autorizado"}), 401

    conn = get_db_connection()
    activos = conn.execute("SELECT * FROM activos").fetchall()
    conn.close()

    return jsonify([
        {
            "id": activo["id"],
            "nombre": activo["nombre"],
            "tipo": activo["tipo"],
            "estado": activo["estado"]
        }
        for activo in activos
    ])


@app.route("/api/historicos")
def api_historicos():
    if "usuario_id" not in session:
        return jsonify({"error": "No autorizado"}), 401

    conn = get_db_connection()
    registros = conn.execute("""
        SELECT * FROM metricas_produccion
        ORDER BY id DESC LIMIT 20
    """).fetchall()
    conn.close()

    return jsonify([
        {
            "produccion": registro["produccion"],
            "eficiencia": registro["eficiencia"],
            "tiempo_operacion": registro["tiempo_operacion"],
            "fecha_hora": registro["fecha_hora"]
        }
        for registro in registros
    ])


@app.route("/api/alertas")
def api_alertas():
    if "usuario_id" not in session:
        return jsonify({"error": "No autorizado"}), 401

    actualizar_simulacion()
    actualizar_equipos()
    conn = get_db_connection()
    registros = conn.execute("""
        SELECT equipo_id, equipo_nombre, variable, valor, unidad,
               severidad, mensaje, fecha_hora
        FROM eventos_alerta
        ORDER BY id DESC LIMIT 50
    """).fetchall()
    conn.close()

    return jsonify({
        "eventos": [dict(registro) for registro in registros]
    })


@app.route("/api/configuracion")
def api_configuracion():
    if "usuario_id" not in session:
        return jsonify({"error": "No autorizado"}), 401

    conn = get_db_connection()
    configuracion = conn.execute("SELECT * FROM configuracion_linea LIMIT 1").fetchone()
    conn.close()

    if not configuracion:
        return jsonify({"error": "Sin configuración disponible"}), 404

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


# RUTAS DE AUDITORÍA Y EXPORTACIÓN DE REPORTES (SPRINT 2)

@app.route("/auditoria/linea/<int:linea_id>")
def ver_auditoria_linea(linea_id):
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    linea = conn.execute("SELECT * FROM lineas WHERE id = ?", (linea_id,)).fetchone()
    conn.close()

    nombre_linea = linea["nombre"] if linea else "Línea Principal de Manufactura"

    lista_activos = obtener_estado_equipos_completo()
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

    nombre_linea = linea["nombre"] if linea else "Línea Principal de Manufactura"

    lista_activos = obtener_estado_equipos_completo()
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

    flash("Formato de exportación no válido.", "danger")
    return redirect(url_for("dashboard"))


if __name__ == "__main__":
    app.run(debug=True, port=5000)