import os
import sqlite3
import random
import time

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

from equipos import EQUIPOS

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "clave-secreta-gemelo-digital-dev")

DB_NAME = "database.db"


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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS activos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            tipo TEXT NOT NULL,
            estado TEXT NOT NULL
        )
    """)

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


# SIMULACIÓN DEL GEMELO DIGITAL

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

        simulacion["temperatura"] = max(60, min(85, simulacion["temperatura"] + random.uniform(-0.8, 0.8)))
        simulacion["presion"] = max(2.5, min(4.5, simulacion["presion"] + random.uniform(-0.08, 0.08)))
        simulacion["velocidad"] = max(60, min(100, simulacion["velocidad"] + random.uniform(-2, 2)))
        simulacion["nivel"] = max(0, min(100, simulacion["nivel"] + random.uniform(-1.5, 1.5)))

        if simulacion["estado"] == "Operando":
            simulacion["produccion"] += random.randint(1, 4)

        simulacion["eficiencia"] = random.uniform(88, 97)


# SIMULACIÓN DE LOS EQUIPOS (definidos en equipos.py)

valores_equipos = {}
control_equipos = {"ultimo_update": time.time()}


def inicializar_equipos():
    for equipo in EQUIPOS:
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

    operando = simulacion["estado"] == "Operando"

    for equipo in EQUIPOS:
        for variable in equipo["variables"]:
            if "calculo" in variable or variable.get("tipo") == "texto":
                continue

            clave = f'{equipo["id"]}.{variable["clave"]}'

            if variable.get("tipo") == "contador":
                if operando:
                    minimo, maximo = variable["incremento"]
                    valores_equipos[clave] += random.uniform(minimo, maximo)
            else:
                rango = variable["max"] - variable["min"]
                nuevo = valores_equipos[clave] + random.uniform(-0.05, 0.05) * rango
                valores_equipos[clave] = max(variable["min"], min(variable["max"], nuevo))


inicializar_equipos()

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
            SELECT usuarios.*, roles.nombre AS rol
            FROM usuarios
            INNER JOIN roles ON usuarios.rol_id = roles.id
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


@app.route("/dashboard")
def dashboard():
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    return render_template(
        "dashboard.html",
        nombre=session["nombre"],
        numero_empleado=session["numero_empleado"],
        rol=session["rol"]
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

    actualizar_simulacion()
    actualizar_equipos()

    resultado = []

    for equipo in EQUIPOS:
        # Primero los valores base de este equipo
        valores = {}
        for variable in equipo["variables"]:
            if "calculo" in variable or variable.get("tipo") == "texto":
                continue
            valores[variable["clave"]] = valores_equipos[f'{equipo["id"]}.{variable["clave"]}']

        # Después los valores calculados a partir de los anteriores
        for variable in equipo["variables"]:
            if "calculo" in variable:
                valores[variable["clave"]] = variable["calculo"](valores)

        # Armar la respuesta respetando el orden definido en equipos.py
        variables_salida = []
        for variable in equipo["variables"]:
            if variable.get("tipo") == "texto":
                valor = variable["valor"]
            else:
                decimales = variable.get("decimales", 1)
                valor = round(valores[variable["clave"]], decimales)
                if decimales == 0:
                    valor = int(valor)

            variables_salida.append({
                "etiqueta": variable["etiqueta"],
                "valor": valor,
                "unidad": variable["unidad"]
            })

        resultado.append({
            "id": equipo["id"],
            "nombre": equipo["nombre"],
            "tipo": equipo["tipo"],
            "estado": simulacion["estado"],
            "variables": variables_salida
        })

    return jsonify(resultado)


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
    alertas = []

    if simulacion["temperatura"] >= 82:
        alertas.append("Temperatura elevada.")
    if simulacion["presion"] >= 4.2:
        alertas.append("Presión elevada.")
    if simulacion["nivel"] <= 15:
        alertas.append("Nivel bajo.")

    if not alertas:
        alertas.append("No existen alertas activas.")

    return jsonify({"alertas": alertas})


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


if __name__ == "__main__":
    app.run(debug=True, port=5000)