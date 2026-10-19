# logic/auditoria_logic.py

def evaluar_salud_activo(variables_salida: list[dict], estado_nominal: str = "Operando") -> tuple[str, str]:
    """
    Evalúa dinámicamente la salud de un activo analizando la severidad de sus variables reales.
    """
    estado_upper = str(estado_nominal).strip().upper()

    if estado_upper in ["INACTIVO", "FALLA", "MANTENIMIENTO", "EMERGENCIA", "DETENIDO"]:
        return "ERROR", f"Activo fuera de servicio ({estado_nominal})"

    severidades = [var.get("severidad", "normal") for var in variables_salida]

    if "paro" in severidades:
        return "ERROR", "Se detectó parámetro crítico fuera de límite de seguridad"
    elif "alerta" in severidades:
        return "IRREGULAR", "Se detectó parámetro fuera de rango normal de operación"
    else:
        return "OPTIMO", "Todos los parámetros operan dentro de límites ideales"


def evaluar_estado_linea(lista_activos: list[dict]) -> tuple[str, str, str]:
    if not lista_activos:
        return "SIN ACTIVOS", "La línea de trabajo no cuenta con activos.", "slate"

    estados_salud = []

    for equipo in lista_activos:
        variables = equipo.get("variables", [])
        estado = equipo.get("estado", "Operando")

        salud, diag = evaluar_salud_activo(variables, estado)
        equipo["salud_individual"] = salud
        equipo["diagnostico_individual"] = diag
        estados_salud.append(salud)

    if "ERROR" in estados_salud:
        conteo = estados_salud.count("ERROR")
        return (
            "ERROR DE FUNCIONAMIENTO",
            f"Se detectaron fallas críticas o alertas en {conteo} activo(s) de la línea.",
            "danger-red"
        )
    elif "IRREGULAR" in estados_salud:
        conteo = estados_salud.count("IRREGULAR")
        return (
            "FUNCIONAMIENTO IRREGULAR",
            f"La línea presenta desviaciones operativas en {conteo} activo(s).",
            "warning-amber"
        )
    else:
        return (
            "FUNCIONAMIENTO OPTIMO",
            "Todos los activos operan dentro de parámetros nominales y de máxima eficiencia.",
            "success-emerald"
        )