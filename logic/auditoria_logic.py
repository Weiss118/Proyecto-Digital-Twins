# logic/auditoria_logic.py

def evaluar_salud_activo(variables_salida: list[dict], estado_nominal: str = "Operando") -> tuple[str, str]:
    """
    Evalúa dinámicamente la salud de un activo analizando la severidad de sus variables reales
    y diferenciando un paro programado de una falla crítica.
    """
    estado_upper = str(estado_nominal).strip().upper()

    # 1. Paro programado o inactividad nominal (NO es error)
    if estado_upper in ["DETENIDO", "INACTIVO", "APAGADO"]:
        return "DETENIDO", f"Activo fuera de servicio por paro programado ({estado_nominal})"

    # 2. Emergencia o falla explícita
    if estado_upper in ["EMERGENCIA", "FALLA"]:
        return "ERROR", f"Paro de emergencia o falla técnica en activo ({estado_nominal})"

    # 3. Evaluación de severidades si el activo está Operando
    severidades = [var.get("severidad", "normal") for var in variables_salida]

    if "paro" in severidades:
        return "ERROR", "Se detectó parámetro crítico fuera de límite de seguridad"
    elif "alerta" in severidades:
        return "IRREGULAR", "Se detectó parámetro fuera de rango normal de operación"
    else:
        return "OPTIMO", "Todos los parámetros operan dentro de límites ideales"


def evaluar_estado_linea(lista_activos: list[dict]) -> tuple[str, str, str]:
    """
    Dictamina el estado global de la línea de trabajo considerando estados parciales y paros programados.
    """
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

    # Evaluación jerárquica de la línea
    conteo_errores = estados_salud.count("ERROR")
    conteo_detenidos = estados_salud.count("DETENIDO")
    total_activos = len(lista_activos)

    if conteo_errores > 0:
        return (
            "ERROR DE FUNCIONAMIENTO",
            f"Se detectó falla crítica o emergencia en {conteo_errores} activo(s) de la línea.",
            "danger-red"
        )
    elif conteo_detenidos == total_activos:
        return (
            "LÍNEA DETENIDA",
            "La línea de producción se encuentra totalmente detenida por paro programado.",
            "slate"
        )
    elif conteo_detenidos > 0:
        return (
            "OPERACIÓN PARCIAL",
            f"La línea opera parcialmente con {conteo_detenidos} activo(s) detenido(s) y {total_activos - conteo_detenidos} en operación.",
            "primary-blue"
        )
    elif "IRREGULAR" in estados_salud:
        conteo_irreg = estados_salud.count("IRREGULAR")
        return (
            "FUNCIONAMIENTO IRREGULAR",
            f"La línea presenta desviaciones operativas en {conteo_irreg} activo(s).",
            "warning-amber"
        )
    else:
        return (
            "FUNCIONAMIENTO OPTIMO",
            "Todos los activos operan dentro de parámetros nominales y de máxima eficiencia.",
            "success-emerald"
        )