"""Reglas de detección de anomalías para el gemelo digital.

Los umbrales son referencias configurables y deben validarse con mantenimiento.
Este módulo solo clasifica y reporta; no controla maquinaria real.
"""

# Cada regla puede tener alerta_baja/alerta_alta y paro_bajo/paro_alto.
# Una medición fuera de los límites de alerta se clasifica como alerta;
# los límites de paro tienen prioridad.
REGLAS_ALERTAS = {
    "motor": {
        "rpm": {"alerta_baja": 1744.4, "alerta_alta": 1815.6, "paro_bajo": 1602, "paro_alto": 1958},
        "temp_devanado": {"alerta_alta": 110, "paro_alto": 140},
        "temp_rodamiento": {"alerta_alta": 70, "paro_alto": 90},
        # La corriente depende de la FLA real de placa. No se inventa un límite en amperios.
        "vibracion": {"alerta_alta": 4.5, "paro_alto": 11.2},
        "voltaje": {"alerta_baja": 437, "alerta_alta": 483, "paro_bajo": 414, "paro_alto": 506},
    },
    "banda": {
        "velocidad": {"alerta_baja": 18, "alerta_alta": 24, "paro_bajo": 0},
        "deslizamiento": {"alerta_alta": 2, "paro_alto": 10},
        "temp_rodillos": {"alerta_alta": 70, "paro_alto": 95},
    },
    "compresor": {
        "presion": {"alerta_baja": 6, "alerta_alta": 8.8, "paro_bajo": 0, "paro_alto": 10},
        "temp_descarga": {"alerta_alta": 100, "paro_alto": 110},
        "dif_filtro": {"alerta_alta": 0.5, "paro_alto": 1},
    },
    "bomba": {
        "nivel": {"alerta_baja": 25, "alerta_alta": 90, "paro_bajo": 15, "paro_alto": 95},
        "vibracion": {"alerta_alta": 4.5, "paro_alto": 11.2},
        "temp_rodamiento": {"alerta_alta": 70, "paro_alto": 90},
    },
    "chiller": {
        "temp_suministro": {"alerta_alta": 9, "paro_alto": 12},
        "delta_t": {"alerta_baja": 3, "alerta_alta": 7, "paro_bajo": 2},
        # El flujo nominal depende del modelo del chiller; se usan los rangos definidos en equipos.py.
        "flujo": {"alerta_baja": 34, "paro_bajo": 28},
    },
    "reflujo": {
        "zona1": {"alerta_baja": 147, "alerta_alta": 173, "paro_bajo": 135, "paro_alto": 185},
        "zona2": {"alerta_baja": 165, "alerta_alta": 205, "paro_bajo": 155, "paro_alto": 215},
        "zona3": {"alerta_baja": 230, "alerta_alta": 255, "paro_bajo": 0, "paro_alto": 280},
        "pico": {"alerta_baja": 235, "alerta_alta": 255, "paro_alto": 260},
        "oxigeno": {"alerta_alta": 1000, "paro_alto": 5000},
    },
    "inyectora": {
        "barril1": {"alerta_baja": 190, "alerta_alta": 220, "paro_bajo": 180, "paro_alto": 230},
        "barril2": {"alerta_baja": 205, "alerta_alta": 235, "paro_bajo": 195, "paro_alto": 245},
        "barril3": {"alerta_baja": 220, "alerta_alta": 250, "paro_bajo": 210, "paro_alto": 260},
        "temp_aceite": {"alerta_alta": 55, "paro_alto": 65},
        "ciclo": {"alerta_baja": 16.2, "alerta_alta": 24.2, "paro_alto": 26.4},
        "fuerza_cierre": {"alerta_baja": 93.5},
        "scrap": {"alerta_alta": 2, "paro_alto": 8},
    },
    "cnc": {
        "carga": {"alerta_alta": 80, "paro_alto": 110},
        "temp_husillo": {"alerta_alta": 50, "paro_alto": 60},
        "vibracion": {"alerta_alta": 3.0, "paro_alto": 4.0},
        "nivel_refrigerante": {"alerta_baja": 30, "paro_bajo": 15},
        "presion_lubricacion": {"alerta_baja": 1.275, "paro_bajo": 0.75},
        "vida_herramienta": {"alerta_alta": 80, "paro_alto": 100},
    },
}


def evaluar_valor(valor, regla):
    """Devuelve normal, alerta, paro o sin_datos para una medición."""
    if valor is None:
        return {"severidad": "sin_datos", "mensaje": "Sin datos disponibles"}
    try:
        valor = float(valor)
    except (TypeError, ValueError):
        return {"severidad": "sin_datos", "mensaje": "Medición no numérica"}

    if "paro_bajo" in regla and valor < regla["paro_bajo"]:
        return {"severidad": "paro", "mensaje": "Valor por debajo del límite crítico"}
    if "paro_alto" in regla and valor >= regla["paro_alto"]:
        return {"severidad": "paro", "mensaje": "Valor alcanzó o superó el límite crítico"}
    if "alerta_baja" in regla and valor < regla["alerta_baja"]:
        return {"severidad": "alerta", "mensaje": "Valor fuera del rango esperado (bajo)"}
    if "alerta_alta" in regla and valor >= regla["alerta_alta"]:
        return {"severidad": "alerta", "mensaje": "Valor fuera del rango esperado (alto)"}
    return {"severidad": "normal", "mensaje": "Operación dentro de los límites configurados"}
