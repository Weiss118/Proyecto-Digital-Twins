def var(clave, etiqueta, unidad, minimo, maximo, decimales=1):
    return {
        "clave": clave,
        "etiqueta": etiqueta,
        "unidad": unidad,
        "min": minimo,
        "max": maximo,
        "decimales": decimales,
    }


def contador(clave, etiqueta, unidad, inicio, inc_min, inc_max, decimales=0):
    return {
        "clave": clave,
        "etiqueta": etiqueta,
        "unidad": unidad,
        "tipo": "contador",
        "inicio": inicio,
        "incremento": (inc_min, inc_max),
        "decimales": decimales,
    }


def texto(clave, etiqueta, valor):
    return {
        "clave": clave,
        "etiqueta": etiqueta,
        "unidad": "",
        "tipo": "texto",
        "valor": valor,
    }


def calculada(clave, etiqueta, unidad, funcion, decimales=1):
    return {
        "clave": clave,
        "etiqueta": etiqueta,
        "unidad": unidad,
        "calculo": funcion,
        "decimales": decimales,
    }


EQUIPOS = [
    {
        "id": "motor",
        "nombre": "Motor eléctrico",
        "tipo": "Motor trifásico 460 V, 4 polos",
        "variables": [
            var("rpm", "RPM", "RPM", 1740, 1820, 0),
            var("temp_devanado", "Temp. devanado", "°C", 70, 105, 1),
            var("temp_rodamiento", "Temp. rodamientos", "°C", 45, 68, 1),
            var("corriente", "Corriente", "A", 25, 38, 1),
            var("voltaje", "Voltaje", "V", 450, 470, 0),
            var("vibracion", "Vibración", "mm/s", 1.0, 3.5, 2),
            var("potencia", "Potencia", "kW", 15, 22, 1),
            contador("horas", "Horas de operación", "h", 1250, 1 / 3600, 1 / 3600, 2),
        ],
    },
    {
        "id": "banda",
        "nombre": "Banda transportadora",
        "tipo": "Banda con motorreductor",
        "variables": [
            var("velocidad", "Velocidad", "m/min", 18, 24, 1),
            var("corriente", "Corriente del motor", "A", 8, 14, 1),
            var("deslizamiento", "Deslizamiento", "%", 0.2, 1.8, 2),
            var("temp_rodillos", "Temp. rodillos", "°C", 40, 65, 1),
            contador("piezas", "Conteo de piezas", "piezas", 0, 0, 2, 0),
            texto("atasco", "Atasco de pieza", "Sin detección"),
            texto("paro_cable", "Paro por cable", "Inactivo"),
        ],
    },
    {
        "id": "compresor",
        "nombre": "Compresor de aire",
        "tipo": "Compresor de tornillo",
        "variables": [
            var("presion", "Presión de descarga", "bar", 7.0, 8.0, 2),
            var("temp_descarga", "Temp. de descarga", "°C", 75, 95, 1),
            var("temp_aceite", "Temp. de aceite", "°C", 60, 80, 1),
            var("dif_filtro", "Diferencial de filtro", "bar", 0.2, 0.5, 2),
            var("corriente", "Corriente", "A", 40, 60, 1),
            contador("horas_carga", "Horas en carga", "h", 3420, 1 / 3600, 1 / 3600, 2),
        ],
    },
    {
        "id": "bomba",
        "nombre": "Bomba centrífuga y tanque",
        "tipo": "Bomba de proceso con tanque de nivel",
        "variables": [
            var("nivel", "Nivel del tanque", "%", 45, 78, 1),
            var("presion_succion", "Presión de succión", "bar", 0.5, 1.5, 2),
            var("presion_descarga", "Presión de descarga", "bar", 3.0, 5.0, 2),
            var("flujo", "Flujo", "m³/h", 40, 60, 1),
            var("vibracion", "Vibración", "mm/s", 1.0, 3.5, 2),
            var("temp_rodamiento", "Temp. rodamientos", "°C", 45, 68, 1),
            var("corriente", "Corriente", "A", 12, 20, 1),
        ],
    },
    {
        "id": "chiller",
        "nombre": "Chiller",
        "tipo": "Enfriador de agua para proceso",
        "variables": [
            var("temp_suministro", "Agua de suministro", "°C", 6.5, 7.5, 1),
            var("temp_retorno", "Agua de retorno", "°C", 11.5, 13.0, 1),
            calculada(
                "delta_t", "ΔT", "°C",
                lambda v: v["temp_retorno"] - v["temp_suministro"], 1
            ),
            var("presion_refrigerante", "Presión de refrigerante", "bar", 6, 10, 1),
            var("flujo", "Flujo de agua", "m³/h", 30, 40, 1),
            var("corriente", "Corriente del compresor", "A", 60, 90, 1),
        ],
    },
    {
        "id": "reflujo",
        "nombre": "Horno de reflujo SMT",
        "tipo": "Perfil SAC305 con nitrógeno",
        "variables": [
            var("zona1", "Zona 1 (precalentamiento)", "°C", 150, 170, 1),
            var("zona2", "Zona 2 (estabilización)", "°C", 170, 200, 1),
            var("zona3", "Zona 3 (reflujo)", "°C", 235, 250, 1),
            var("pico", "Pico de reflujo", "°C", 240, 248, 1),
            var("velocidad", "Velocidad de banda", "cm/min", 70, 90, 1),
            var("oxigeno", "O₂", "ppm", 300, 900, 0),
            var("flujo_n2", "Flujo de N₂", "m³/h", 20, 30, 1),
            var("extraccion", "Extracción", "%", 70, 90, 1),
        ],
    },
    {
        "id": "inyectora",
        "nombre": "Inyectora de plástico",
        "tipo": "Inyectora hidráulica (ABS)",
        "variables": [
            var("barril1", "Temp. barril zona 1", "°C", 200, 210, 1),
            var("barril2", "Temp. barril zona 2", "°C", 215, 225, 1),
            var("barril3", "Temp. barril zona 3", "°C", 230, 240, 1),
            var("molde", "Temp. de molde", "°C", 40, 60, 1),
            var("presion_inyeccion", "Presión de inyección", "bar", 800, 1200, 0),
            var("fuerza_cierre", "Fuerza de cierre", "ton", 100, 110, 1),
            var("ciclo", "Tiempo de ciclo", "s", 18, 22, 1),
            var("temp_aceite", "Temp. aceite hidráulico", "°C", 40, 50, 1),
            var("scrap", "Scrap", "%", 0.5, 2.0, 2),
        ],
    },
    {
        "id": "cnc",
        "nombre": "Centro de maquinado CNC",
        "tipo": "Centro de maquinado vertical",
        "variables": [
            var("rpm", "RPM de husillo", "RPM", 8000, 12000, 0),
            var("carga", "Carga de husillo", "%", 40, 75, 1),
            var("temp_husillo", "Temp. de husillo", "°C", 30, 44, 1),
            var("vibracion", "Vibración", "mm/s", 0.5, 2.0, 2),
            var("nivel_refrigerante", "Nivel de refrigerante", "%", 55, 90, 1),
            var("temp_refrigerante", "Temp. de refrigerante", "°C", 20, 28, 1),
            var("presion_lubricacion", "Presión de lubricación", "bar", 1.5, 2.5, 2),
            var("vida_herramienta", "Vida de herramienta usada", "%", 20, 75, 1),
        ],
    },
]