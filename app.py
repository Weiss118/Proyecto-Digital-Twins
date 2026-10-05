import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'clave_secreta_pwa_gemelo_digital'

DB_NAME = "database.db"

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Crear tabla de roles
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            descripcion TEXT
        )
    ''')
    
    # Crear tabla de usuarios
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero_empleado TEXT UNIQUE NOT NULL,
            nombre_completo TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            rol_id INTEGER NOT NULL,
            estado TEXT DEFAULT 'ACTIVO',
            FOREIGN KEY (rol_id) REFERENCES roles (id)
        )
    ''')
    
    # Insertar roles por defecto
    roles = [
        ('Operador', 'Acceso de solo lectura a historicos y gemelo digital'),
        ('Tecnico', 'Lectura, manipulacion de gemelos, nuevas lineas y reportes'),
        ('Supervisor', 'Administración total: alta/baja de usuarios y permisos')
    ]
    cursor.executemany("INSERT OR IGNORE INTO roles (nombre, descripcion) VALUES (?, ?)", roles)
    conn.commit()

    # Insertar 3 usuarios de prueba (Sprint 0)
    cursor.execute("SELECT COUNT(*) FROM usuarios")
    if cursor.fetchone()[0] == 0:
        usuarios_prueba = [
            ('1001', 'Carlos Operador', generate_password_hash('op123'), 1),
            ('2001', 'Ana Técnica', generate_password_hash('tec123'), 2),
            ('3001', 'Ing. Roberto Supervisor', generate_password_hash('admin123'), 3)
        ]
        cursor.executemany('''
            INSERT INTO usuarios (numero_empleado, nombre_completo, password_hash, rol_id)
            VALUES (?, ?, ?, ?)
        ''', usuarios_prueba)
        conn.commit()
        print("-> Base de datos inicializada con los 3 usuarios de prueba.")

    conn.close()

@app.route('/')
def index():
    if 'usuario_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        numero_empleado = request.form['numero_empleado'].strip()
        password = request.form['password']
        
        conn = get_db_connection()
        user = conn.execute('''
            SELECT u.*, r.nombre AS rol_nombre 
            FROM usuarios u 
            JOIN roles r ON u.rol_id = r.id 
            WHERE u.numero_empleado = ? AND u.estado = 'ACTIVO'
        ''', (numero_empleado,)).fetchone()
        conn.close()

        if user and check_password_hash(user['password_hash'], password):
            session['usuario_id'] = user['id']
            session['numero_empleado'] = user['numero_empleado']
            session['nombre'] = user['nombre_completo']
            session['rol'] = user['rol_nombre']
            return redirect(url_for('dashboard'))
        else:
            flash('Número de empleado o contraseña incorrectos.', 'danger')
            
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'usuario_id' not in session:
        return redirect(url_for('login'))
    return render_template('dashboard.html', 
                           nombre=session['nombre'], 
                           rol=session['rol'], 
                           numero_empleado=session['numero_empleado'])

@app.route('/logout')
def logout():
    session.clear()
    flash('Has cerrado sesión correctamente.', 'info')
    return redirect(url_for('login'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)