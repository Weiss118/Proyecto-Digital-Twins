"""Acceso común a la base SQLite para los módulos de extensión.

Usa el mismo archivo que app.py (database.db) sin importar app.py, para evitar
importaciones circulares.
"""
import sqlite3

DB_NAME = "database.db"


def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn
