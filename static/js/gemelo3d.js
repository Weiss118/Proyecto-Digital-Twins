/* Gemelo 3D del activo.
 *
 * Dibuja, a la izquierda de las métricas de cada activo, una representación
 * tridimensional ligera (canvas 2D, sin librerías externas). Se puede girar
 * arrastrando. Al tocar una métrica (su tarjeta o su opción del selector
 * «Métricas a mostrar») la parte del activo que la origina se marca de forma
 * sutil, con el color de su severidad actual (normal / alerta / crítico).
 *
 * No modifica el código existente del dashboard: observa #equipos igual que
 * metricas_foco.js y se apoya en window.DT (dt_util.js).
 *
 * Para añadir o ajustar un activo, edita su entrada en MODELOS (más abajo).
 * El id es el de equipos.py. En «marcas», cada clave de variable de equipos.py
 * indica qué partes del modelo se marcan ("*" = todo el activo). Los activos
 * sin modelo se muestran igual que antes, sin visor.
 */
(function () {
    "use strict";

    var contenedor = document.getElementById("equipos");
    if (!contenedor || !window.DT) return;
    var el = window.DT.el;

    var CELDA = 0.9;                       // tamaño máximo de las caras (mejora el orden de dibujo)
    var FONDO = [238, 242, 247];           // color de fondo del visor (para atenuar lo no marcado)
    var ACENTO = {                         // mismos colores que usa el dashboard para cada severidad
        normal: [37, 99, 235],
        alerta: [202, 138, 4],
        paro: [220, 38, 38]
    };
    var REDUCIDO = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);

    // Paleta del modelo: tonos neutros para que la marca destaque.
    var K = {
        claro: [214, 222, 233], acero: [176, 188, 204], medio: [142, 156, 176],
        oscuro: [104, 120, 142], carbon: [66, 80, 100], azul: [122, 162, 206],
        azulOsc: [90, 124, 172], rojo: [208, 120, 108], ambar: [214, 182, 128],
        verde: [146, 176, 148], caliente: [222, 186, 166], tibio: [214, 204, 196]
    };

    /* ===================================================================
       Geometría: cajas y cilindros convertidos en caras planas
       =================================================================== */
    function dist(a, b) {
        var x = a[0] - b[0], y = a[1] - b[1], z = a[2] - b[2];
        return Math.sqrt(x * x + y * y + z * z);
    }
    function lerp3(a, b, t) {
        return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
    }

    function Malla() { this.caras = []; this.cajas = {}; }

    Malla.prototype.cara = function (parte, v, n, color) {
        this.caras.push({ p: parte, v: v, n: n, c: color });
        var caja = this.cajas[parte] || (this.cajas[parte] = { min: [1e9, 1e9, 1e9], max: [-1e9, -1e9, -1e9] });
        for (var i = 0; i < v.length; i++) {
            for (var k = 0; k < 3; k++) {
                if (v[i][k] < caja.min[k]) caja.min[k] = v[i][k];
                if (v[i][k] > caja.max[k]) caja.max[k] = v[i][k];
            }
        }
    };

    // Cuadrilátero a-b-c-d dividido en celdas pequeñas.
    Malla.prototype.quad = function (parte, a, b, c, d, n, color) {
        var celda = this.celda || CELDA;
        var nu = Math.max(1, Math.ceil(dist(a, b) / celda));
        var nv = Math.max(1, Math.ceil(dist(a, d) / celda));
        function P(u, v) { return lerp3(lerp3(a, b, u), lerp3(d, c, u), v); }
        for (var i = 0; i < nu; i++) {
            for (var j = 0; j < nv; j++) {
                var u0 = i / nu, u1 = (i + 1) / nu, v0 = j / nv, v1 = (j + 1) / nv;
                this.cara(parte, [P(u0, v0), P(u1, v0), P(u1, v1), P(u0, v1)], n, color);
            }
        }
    };

    // Caja centrada en (x, y, z). La cara inferior no se dibuja (nunca se ve).
    Malla.prototype.B = function (parte, x, y, z, w, h, d, color) {
        var x0 = x - w / 2, x1 = x + w / 2, y0 = y - h / 2, y1 = y + h / 2, z0 = z - d / 2, z1 = z + d / 2;
        this.quad(parte, [x1, y0, z1], [x1, y0, z0], [x1, y1, z0], [x1, y1, z1], [1, 0, 0], color);
        this.quad(parte, [x0, y0, z0], [x0, y0, z1], [x0, y1, z1], [x0, y1, z0], [-1, 0, 0], color);
        this.quad(parte, [x0, y1, z1], [x1, y1, z1], [x1, y1, z0], [x0, y1, z0], [0, 1, 0], color);
        this.quad(parte, [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1], [0, 0, 1], color);
        this.quad(parte, [x1, y0, z0], [x0, y0, z0], [x0, y1, z0], [x1, y1, z0], [0, 0, -1], color);
    };

    // Cilindro (o tronco de cono) centrado en (x, y, z) con su eje en "x", "y" o "z".
    // r = radio en el extremo negativo del eje, o.r2 = radio en el extremo positivo.
    Malla.prototype.C = function (parte, eje, x, y, z, r, L, color, o) {
        o = o || {};
        this.celda = o.celda || 0;
        var r2 = o.r2 === undefined ? r : o.r2;
        var seg = o.seg || (Math.max(r, r2) < 0.2 ? 10 : 18);
        function pt(t, c, s, rad) {
            if (eje === "x") return [x + t, y + c * rad, z + s * rad];
            if (eje === "y") return [x + c * rad, y + t, z + s * rad];
            return [x + c * rad, y + s * rad, z + t];
        }
        function radial(c, s) {
            if (eje === "x") return [0, c, s];
            if (eje === "y") return [c, 0, s];
            return [c, s, 0];
        }
        var eje1 = eje === "x" ? [1, 0, 0] : (eje === "y" ? [0, 1, 0] : [0, 0, 1]);
        var tapaSup = [], tapaInf = [];

        for (var i = 0; i < seg; i++) {
            var a0 = 2 * Math.PI * i / seg, a1 = 2 * Math.PI * (i + 1) / seg, am = (a0 + a1) / 2;
            var c0 = Math.cos(a0), s0 = Math.sin(a0), c1 = Math.cos(a1), s1 = Math.sin(a1);
            this.quad(parte, pt(-L / 2, c0, s0, r), pt(-L / 2, c1, s1, r), pt(L / 2, c1, s1, r2), pt(L / 2, c0, s0, r2),
                radial(Math.cos(am), Math.sin(am)), color);
            tapaSup.push(pt(L / 2, c0, s0, r2));
            tapaInf.push(pt(-L / 2, c0, s0, r));
        }

        // Tapas: anillos concéntricos (o un solo polígono si son pequeñas). Con o.hueco solo se
        // dibuja la corona exterior, útil para aletas finas.
        var tapaClara = lerp3(color, [255, 255, 255], 0.06);
        var hueco = o.hueco || 0;
        var tapas = [[L / 2, r2, eje1], [-L / 2, r, [-eje1[0], -eje1[1], -eje1[2]]]];
        for (var k = 0; k < tapas.length; k++) {
            if (eje === "y" && k === 1) continue;                  // la base de un cilindro vertical no se ve
            var tt = tapas[k][0], rad = tapas[k][1], nrm = tapas[k][2];
            if (rad < 0.02) continue;
            if (rad < 0.3 && !hueco) {
                var anillo = [];
                for (var q = 0; q < seg; q++) anillo.push(pt(tt, Math.cos(2 * Math.PI * q / seg), Math.sin(2 * Math.PI * q / seg), rad));
                this.cara(parte, anillo, nrm, tapaClara);
                continue;
            }
            var nr = Math.max(1, Math.ceil((rad - hueco) / 0.5));
            for (var g = 0; g < nr; g++) {
                var ra = hueco + (rad - hueco) * g / nr, rb = hueco + (rad - hueco) * (g + 1) / nr;
                for (var j = 0; j < seg; j++) {
                    var b0 = 2 * Math.PI * j / seg, b1 = 2 * Math.PI * (j + 1) / seg;
                    var pA = pt(tt, Math.cos(b0), Math.sin(b0), ra), pB = pt(tt, Math.cos(b0), Math.sin(b0), rb);
                    var pC = pt(tt, Math.cos(b1), Math.sin(b1), rb), pD = pt(tt, Math.cos(b1), Math.sin(b1), ra);
                    this.cara(parte, ra < 0.001 ? [pA, pB, pC] : [pA, pB, pC, pD], nrm, tapaClara);
                }
            }
        }
        this.celda = 0;
    };

    /* ===================================================================
       Modelos de los activos (ids de equipos.py)
       =================================================================== */
    var MODELOS = {};

    MODELOS.motor = {
        marcas: {
            rpm: ["eje"], temp_devanado: ["cuerpo"], temp_rodamiento: ["rodamiento"],
            corriente: ["caja"], voltaje: ["caja"], vibracion: ["base"],
            potencia: ["cuerpo", "caja"], horas: "*"
        },
        construir: function (m) {
            m.B("base", 0, 0.1, 0, 4.3, 0.2, 1.7, K.carbon);
            m.B("base", -0.4, 0.28, 0.62, 1.6, 0.16, 0.4, K.oscuro);
            m.B("base", -0.4, 0.28, -0.62, 1.6, 0.16, 0.4, K.oscuro);
            m.C("cuerpo", "x", -0.3, 1.3, 0, 0.95, 2.4, K.acero, { celda: 0.3 });
            for (var i = 0; i < 7; i++) m.C("cuerpo", "x", -1.3 + i * 0.33, 1.3, 0, 1.03, 0.09, K.medio, { seg: 20, hueco: 0.93 });
            m.C("rodamiento", "x", 1.05, 1.3, 0, 0.86, 0.3, K.oscuro);
            m.C("rodamiento", "x", -1.62, 1.3, 0, 0.86, 0.24, K.oscuro);
            m.C("ventilador", "x", -2.02, 1.3, 0, 0.78, 0.55, K.medio);
            m.C("ventilador", "x", -2.32, 1.3, 0, 0.6, 0.06, K.carbon);
            m.C("eje", "x", 1.78, 1.3, 0, 0.17, 1.15, K.claro);
            m.B("eje", 2.05, 1.3, 0, 0.5, 0.07, 0.07, K.acero);
            m.B("caja", -0.35, 2.4, 0, 0.9, 0.36, 0.8, K.azulOsc);
        }
    };

    MODELOS.banda = {
        marcas: {
            velocidad: ["banda"], corriente: ["motor"], deslizamiento: ["banda", "rodillos"],
            temp_rodillos: ["rodillos"], piezas: ["piezas"], atasco: ["sensor"], paro_cable: ["cable"]
        },
        construir: function (m) {
            var sx = [-2.0, 2.0], sz = [-0.6, 0.6];
            for (var i = 0; i < 2; i++) for (var j = 0; j < 2; j++) m.B("estructura", sx[i], 0.45, sz[j], 0.14, 0.9, 0.14, K.medio);
            m.B("estructura", 0, 0.88, 0.6, 5.0, 0.2, 0.1, K.acero);
            m.B("estructura", 0, 0.88, -0.6, 5.0, 0.2, 0.1, K.acero);
            m.B("banda", 0, 0.94, 0, 4.9, 0.1, 1.0, K.carbon);
            m.C("rodillos", "z", -2.45, 0.9, 0, 0.19, 1.14, K.acero);
            m.C("rodillos", "z", 2.45, 0.9, 0, 0.19, 1.14, K.acero);
            m.B("motor", 2.45, 0.9, 0.98, 0.5, 0.5, 0.45, K.azulOsc);
            m.C("motor", "z", 2.45, 0.9, 1.5, 0.27, 0.7, K.azul);
            m.B("piezas", -1.4, 1.2, 0, 0.5, 0.4, 0.5, K.ambar);
            m.B("piezas", -0.2, 1.17, 0.05, 0.45, 0.33, 0.4, K.ambar);
            m.B("piezas", 1.0, 1.2, -0.05, 0.5, 0.4, 0.45, K.ambar);
            m.B("sensor", 1.8, 1.3, -0.72, 0.1, 0.8, 0.1, K.medio);
            m.B("sensor", 1.8, 1.78, -0.62, 0.22, 0.16, 0.3, K.oscuro);
            for (var p = -1; p <= 1; p++) m.B("cable", p * 1.9, 1.2, 0.8, 0.06, 0.55, 0.06, K.medio);
            m.C("cable", "x", 0, 1.5, 0.8, 0.035, 3.9, K.rojo, { seg: 8 });
        }
    };

    MODELOS.compresor = {
        marcas: {
            presion: ["tanque", "manometro"], temp_descarga: ["descarga"], temp_aceite: ["aceite"],
            dif_filtro: ["filtro"], corriente: ["motor"], horas_carga: ["airend"]
        },
        construir: function (m) {
            m.B("base", -0.2, 0.1, 0, 4.7, 0.2, 1.9, K.carbon);
            m.B("base", -1.5, 0.25, 0, 0.4, 0.1, 0.9, K.medio);
            m.B("base", -0.6, 0.25, 0, 0.4, 0.1, 0.9, K.medio);
            m.C("tanque", "x", -1.15, 1.1, 0, 0.8, 2.3, K.acero);
            m.C("manometro", "z", -1.15, 1.35, 0.84, 0.17, 0.1, K.claro);
            m.C("descarga", "x", 0.28, 1.1, 0, 0.09, 0.7, K.medio);
            m.B("airend", 1.15, 0.8, 0, 1.2, 1.2, 1.1, K.azulOsc);
            m.C("motor", "x", 1.15, 1.97, 0, 0.5, 1.7, K.acero);
            m.C("aceite", "y", 1.55, 0.85, 0.85, 0.32, 1.3, K.claro);
            m.C("filtro", "y", 0.88, 0.7, 0.85, 0.26, 1.0, K.oscuro);
        }
    };

    MODELOS.bomba = {
        marcas: {
            nivel: ["tanque", "nivel"], presion_succion: ["succion"], presion_descarga: ["descarga"],
            flujo: ["succion", "descarga"], vibracion: ["bomba"], temp_rodamiento: ["rodamiento"], corriente: ["motor"]
        },
        construir: function (m) {
            m.B("base", 0.8, 0.1, 0, 3.4, 0.2, 1.3, K.carbon);
            m.C("tanque", "y", -1.8, 1.25, 0, 0.95, 2.5, K.acero);
            m.C("tanque", "y", -1.8, 2.55, 0, 0.7, 0.1, K.medio);
            m.B("nivel", -1.8, 1.25, 0.98, 0.18, 1.9, 0.08, K.claro);
            m.B("nivel", -1.8, 0.85, 1.03, 0.09, 1.1, 0.04, K.azul);
            m.C("succion", "x", -0.1, 0.75, 0, 0.13, 1.5, K.medio);
            m.C("bomba", "x", 0.9, 0.75, 0, 0.5, 0.5, K.azulOsc);
            m.C("rodamiento", "x", 1.4, 0.75, 0, 0.3, 0.4, K.oscuro);
            m.C("motor", "x", 2.05, 0.75, 0, 0.45, 0.9, K.acero);
            m.C("descarga", "y", 0.9, 1.8, 0, 0.12, 1.1, K.medio);
            m.C("descarga", "x", 1.5, 2.35, 0, 0.12, 1.2, K.medio);
        }
    };

    MODELOS.chiller = {
        marcas: {
            temp_suministro: ["suministro"], temp_retorno: ["retorno"], delta_t: ["suministro", "retorno"],
            presion_refrigerante: ["evaporador"], flujo: ["suministro", "retorno"], corriente: ["compresor"]
        },
        construir: function (m) {
            m.B("base", 0, 0.075, 0, 4.3, 0.15, 1.9, K.carbon);
            var px = [-1.95, 1.95], pz = [-0.8, 0.8];
            for (var i = 0; i < 2; i++) for (var j = 0; j < 2; j++) m.B("gabinete", px[i], 0.9, pz[j], 0.1, 1.5, 0.1, K.claro);
            m.B("gabinete", 0, 1.65, 0, 4.0, 0.1, 1.7, K.acero);
            m.B("gabinete", 0, 0.9, -0.8, 4.0, 1.5, 0.05, K.acero);
            m.B("gabinete", -1.95, 0.9, 0, 0.05, 1.5, 1.7, K.acero);
            m.B("gabinete", 1.95, 0.9, 0, 0.05, 1.5, 1.7, K.acero);
            m.C("evaporador", "x", 0.5, 0.65, -0.15, 0.42, 2.2, K.azul);
            m.C("compresor", "x", -1.3, 0.65, 0.25, 0.45, 1.1, K.azulOsc);
            m.C("suministro", "x", 2.2, 0.82, 0.05, 0.1, 1.1, [110, 168, 218]);
            m.C("retorno", "x", 2.2, 0.5, -0.45, 0.1, 1.1, [216, 144, 128]);
            for (var f = 0; f < 3; f++) {
                var fx = -1.2 + f * 1.2;
                m.C("condensador", "y", fx, 1.76, 0, 0.5, 0.12, K.oscuro);
                m.C("condensador", "y", fx, 1.86, 0, 0.12, 0.1, K.claro);
                m.B("condensador", fx, 1.83, 0, 0.9, 0.03, 0.12, K.medio);
                m.B("condensador", fx, 1.83, 0, 0.12, 0.03, 0.9, K.medio);
            }
        }
    };

    MODELOS.reflujo = {
        marcas: {
            zona1: ["zona1"], zona2: ["zona2"], zona3: ["zona3"], pico: ["zona3"], velocidad: ["banda"],
            oxigeno: ["zona1", "zona2", "zona3"], flujo_n2: ["n2"], extraccion: ["extraccion"]
        },
        construir: function (m) {
            m.B("base", -0.1, 0.225, 0, 5.0, 0.45, 1.2, K.carbon);
            m.B("banda", -0.1, 0.78, 0, 6.5, 0.06, 0.7, K.oscuro);
            m.B("zona1", -1.95, 0.98, 0, 1.3, 1.06, 1.3, K.claro);
            m.B("zona2", -0.65, 0.98, 0, 1.3, 1.06, 1.3, K.tibio);
            m.B("zona3", 0.65, 0.98, 0, 1.3, 1.06, 1.3, K.caliente);
            m.B("enfriamiento", 1.85, 0.98, 0, 1.1, 1.06, 1.3, K.acero);
            m.B("tapas", -1.95, 1.54, 0, 1.1, 0.06, 1.0, K.medio);
            m.B("tapas", -0.65, 1.54, 0, 1.1, 0.06, 1.0, K.medio);
            m.B("tapas", 0.65, 1.54, 0, 1.1, 0.06, 1.0, K.medio);
            m.B("tapas", 1.85, 1.54, 0, 0.9, 0.06, 1.0, K.medio);
            m.C("extraccion", "y", -1.9, 1.95, -0.35, 0.2, 0.8, K.oscuro);
            m.C("extraccion", "y", 0.6, 1.95, -0.35, 0.2, 0.8, K.oscuro);
            m.C("n2", "x", -0.2, 1.7, 0.38, 0.09, 4.2, K.azul);
        }
    };

    MODELOS.inyectora = {
        marcas: {
            barril1: ["barril1"], barril2: ["barril2"], barril3: ["barril3"], molde: ["molde"],
            presion_inyeccion: ["inyeccion"], fuerza_cierre: ["barras", "cierre"], ciclo: "*",
            temp_aceite: ["aceite"], scrap: ["molde"]
        },
        construir: function (m) {
            var calor = [226, 172, 124];
            m.B("base", 0, 0.35, 0, 6.2, 0.7, 1.3, K.medio);
            m.B("aceite", 1.5, 0.4, 0.98, 1.7, 0.6, 0.5, K.azul);
            m.B("cierre", -2.6, 1.55, 0, 0.3, 1.6, 1.3, K.acero);
            m.B("cierre", -1.1, 1.55, 0, 0.3, 1.6, 1.3, K.acero);
            m.B("cierre", -0.2, 1.55, 0, 0.3, 1.6, 1.3, K.acero);
            m.C("cilindro", "x", -1.85, 1.55, 0, 0.3, 1.6, K.oscuro);
            m.C("barras", "x", -1.4, 1.1, 0.5, 0.1, 2.5, K.claro);
            m.C("barras", "x", -1.4, 1.1, -0.5, 0.1, 2.5, K.claro);
            m.C("barras", "x", -1.4, 2.0, 0.5, 0.1, 2.5, K.claro);
            m.C("barras", "x", -1.4, 2.0, -0.5, 0.1, 2.5, K.claro);
            m.B("molde", -0.8, 1.55, 0, 0.3, 0.95, 0.9, K.azulOsc);
            m.B("molde", -0.5, 1.55, 0, 0.3, 0.95, 0.9, K.azulOsc);
            m.C("barril", "x", 1.5, 1.55, 0, 0.22, 3.1, K.medio);
            m.C("barril3", "x", 0.55, 1.55, 0, 0.29, 0.4, calor);
            m.C("barril2", "x", 1.35, 1.55, 0, 0.29, 0.4, calor);
            m.C("barril1", "x", 2.15, 1.55, 0, 0.29, 0.4, calor);
            m.C("tolva", "y", 2.5, 2.2, 0, 0.22, 0.85, K.claro, { r2: 0.6 });
            m.C("inyeccion", "x", 3.4, 1.55, 0, 0.34, 0.8, K.azulOsc);
        }
    };

    MODELOS.cnc = {
        marcas: {
            rpm: ["husillo"], carga: ["cabezal"], temp_husillo: ["husillo"], vibracion: ["columna"],
            nivel_refrigerante: ["refrigerante"], temp_refrigerante: ["refrigerante"],
            presion_lubricacion: ["lubricacion"], vida_herramienta: ["herramienta"]
        },
        construir: function (m) {
            m.B("base", 0, 0.3, 0, 3.2, 0.6, 2.4, K.medio);
            m.B("mesa", 0, 0.75, 0.2, 2.2, 0.3, 1.4, K.claro);
            for (var i = -1; i <= 1; i++) m.B("mesa", i * 0.6, 0.905, 0.2, 0.06, 0.02, 1.3, K.oscuro);
            m.B("pieza", 0, 1.025, 0.1, 0.8, 0.25, 0.6, K.ambar);
            m.B("columna", 0, 1.8, -0.9, 1.4, 2.4, 0.8, K.acero);
            m.B("cabezal", 0, 2.45, 0, 1.0, 1.2, 1.1, K.azulOsc);
            m.C("husillo", "y", 0, 3.3, 0, 0.3, 0.5, K.oscuro);
            m.C("husillo", "y", 0, 1.75, 0, 0.2, 0.2, K.claro);
            m.C("herramienta", "y", 0, 1.4, 0, 0.03, 0.5, K.claro, { r2: 0.1 });
            m.B("refrigerante", 2.1, 0.4, 0, 1.0, 0.8, 0.9, K.azul);
            m.B("lubricacion", -2.0, 0.35, 0.2, 0.5, 0.5, 0.5, K.verde);
        }
    };

    // Los modelos se construyen una sola vez y se comparten entre bloques.
    var cacheModelos = {};
    function obtenerModelo(id) {
        if (cacheModelos[id] !== undefined) return cacheModelos[id];
        var def = MODELOS[id];
        if (!def) return (cacheModelos[id] = null);

        var malla = new Malla();
        def.construir(malla);

        var mn = [1e9, 1e9, 1e9], mx = [-1e9, -1e9, -1e9];
        Object.keys(malla.cajas).forEach(function (p) {
            for (var k = 0; k < 3; k++) {
                mn[k] = Math.min(mn[k], malla.cajas[p].min[k]);
                mx[k] = Math.max(mx[k], malla.cajas[p].max[k]);
            }
        });
        var centro = [(mn[0] + mx[0]) / 2, (mn[1] + mx[1]) / 2, (mn[2] + mx[2]) / 2];
        var radio = 0;
        malla.caras.forEach(function (c) {
            c.v = c.v.map(function (p) { return [p[0] - centro[0], p[1] - centro[1], p[2] - centro[2]]; });
            c.v.forEach(function (p) { radio = Math.max(radio, Math.sqrt(p[0] * p[0] + p[1] * p[1] + p[2] * p[2])); });
        });
        Object.keys(malla.cajas).forEach(function (p) {
            var c = malla.cajas[p];
            for (var k = 0; k < 3; k++) { c.min[k] -= centro[k]; c.max[k] -= centro[k]; }
        });

        return (cacheModelos[id] = {
            caras: malla.caras, cajas: malla.cajas, marcas: def.marcas, radio: radio,
            suelo: mn[1] - centro[1],
            huella: [mn[0] - centro[0], mx[0] - centro[0], mn[2] - centro[2], mx[2] - centro[2]]
        });
    }

    /* ===================================================================
       Dibujo
       =================================================================== */
    function mezclar(a, b, k) {
        return [a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k, a[2] + (b[2] - a[2]) * k];
    }
    function rgb(c) {
        return "rgb(" + Math.max(0, Math.min(255, Math.round(c[0]))) + "," +
            Math.max(0, Math.min(255, Math.round(c[1]))) + "," +
            Math.max(0, Math.min(255, Math.round(c[2]))) + ")";
    }

    var LUZ = (function () {            // luz fija respecto a la cámara: arriba, a la izquierda y de frente
        var v = [-0.45, 0.8, 0.55], l = Math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]);
        return [v[0] / l, v[1] / l, v[2] / l];
    })();

    function dibujar(inst, t) {
        var modelo = inst.modelo, ctx = inst.ctx, W = inst.ancho, H = inst.alto;
        if (!ctx || W < 20 || H < 20) return;

        var yaw = inst.yaw + (REDUCIDO ? 0 : 0.3 * Math.sin(inst.fase));
        var cy = Math.cos(yaw), sy = Math.sin(yaw), cp = Math.cos(inst.pitch), sp = Math.sin(inst.pitch);
        var D = modelo.radio * 3.4;
        var F = D * Math.min(W * 0.96, H * 1.2) * 0.5 / modelo.radio;
        var ox = W / 2, oy = H * 0.47;

        // Transformación: giro en Y (yaw), inclinación en X (pitch) y proyección en perspectiva.
        function rot(p) {
            var x1 = p[0] * cy + p[2] * sy, z1 = -p[0] * sy + p[2] * cy;
            return [x1, p[1] * cp - z1 * sp, p[1] * sp + z1 * cp];
        }
        function rotN(n) { return rot(n); }
        function proy(q) { var f = F / (D - q[2]); return [ox + q[0] * f, oy - q[1] * f]; }

        ctx.setTransform(inst.dpr, 0, 0, inst.dpr, 0, 0);
        ctx.clearRect(0, 0, W, H);

        // Suelo: sombra y cuadrícula tenue.
        var hu = modelo.huella, ys = modelo.suelo, mg = 0.7;
        var x0 = hu[0] - mg, x1 = hu[1] + mg, z0 = hu[2] - mg, z1 = hu[3] + mg, i, a, b;
        function lineaSuelo(ax, az, bx, bz) {
            a = proy(rot([ax, ys, az])); b = proy(rot([bx, ys, bz]));
            ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]);
        }
        ctx.beginPath();
        for (i = Math.ceil(x0); i <= x1; i++) lineaSuelo(i, z0, i, z1);
        for (i = Math.ceil(z0); i <= z1; i++) lineaSuelo(x0, i, x1, i);
        ctx.strokeStyle = "rgba(100,116,139,0.16)";
        ctx.lineWidth = 1;
        ctx.stroke();

        ctx.beginPath();
        var sombra = [[hu[0] - 0.15, hu[2] - 0.15], [hu[1] + 0.15, hu[2] - 0.15], [hu[1] + 0.15, hu[3] + 0.15], [hu[0] - 0.15, hu[3] + 0.15]];
        for (i = 0; i < 4; i++) {
            a = proy(rot([sombra[i][0], ys, sombra[i][1]]));
            if (i === 0) ctx.moveTo(a[0], a[1]); else ctx.lineTo(a[0], a[1]);
        }
        ctx.closePath();
        ctx.fillStyle = "rgba(15,23,42,0.09)";
        ctx.fill();

        // Caras visibles ordenadas de la más lejana a la más cercana.
        var acento = ACENTO[inst.severidad] || ACENTO.normal;
        var hay = inst.partes !== null;
        var lista = [];
        var caras = modelo.caras;
        for (i = 0; i < caras.length; i++) {
            var cara = caras[i], vs = cara.v, n = rotN(cara.n);
            var q = [], cx = 0, cyy = 0, cz = 0;
            for (var k = 0; k < vs.length; k++) {
                var r = rot(vs[k]);
                q.push(r); cx += r[0]; cyy += r[1]; cz += r[2];
            }
            cx /= vs.length; cyy /= vs.length; cz /= vs.length;
            if (n[0] * (0 - cx) + n[1] * (0 - cyy) + n[2] * (D - cz) <= 0) continue;     // cara de espaldas

            var luz = Math.max(0, n[0] * LUZ[0] + n[1] * LUZ[1] + n[2] * LUZ[2]);
            var s = 0.58 + 0.5 * luz;
            var color = [cara.c[0] * s, cara.c[1] * s, cara.c[2] * s];
            if (hay) {
                color = (inst.partes === "*" || inst.partes[cara.p])
                    ? mezclar(color, acento, 0.3)
                    : mezclar(color, FONDO, 0.1);
            }
            var pts = [];
            for (k = 0; k < q.length; k++) pts.push(proy(q[k]));
            lista.push({ d: cx * cx + cyy * cyy + (D - cz) * (D - cz), pts: pts, col: rgb(color) });
        }
        lista.sort(function (u, v) { return v.d - u.d; });

        ctx.lineJoin = "round";
        ctx.lineWidth = 0.8;
        for (i = 0; i < lista.length; i++) {
            var f = lista[i];
            ctx.beginPath();
            ctx.moveTo(f.pts[0][0], f.pts[0][1]);
            for (var j = 1; j < f.pts.length; j++) ctx.lineTo(f.pts[j][0], f.pts[j][1]);
            ctx.closePath();
            ctx.fillStyle = f.col;
            ctx.strokeStyle = f.col;
            ctx.fill();
            ctx.stroke();
        }

        // Marcador discreto sobre la parte seleccionada.
        if (hay && inst.centroMarca) {
            var pm = proy(rot(inst.centroMarca));
            var ciclo = REDUCIDO ? 0.35 : ((t / 1000) % 1.8) / 1.8;
            var col = acento[0] + "," + acento[1] + "," + acento[2];
            ctx.beginPath();
            ctx.arc(pm[0], pm[1], 5 + 9 * ciclo, 0, Math.PI * 2);
            ctx.strokeStyle = "rgba(" + col + "," + (0.55 * (1 - ciclo)).toFixed(3) + ")";
            ctx.lineWidth = 1.5;
            ctx.stroke();
            ctx.beginPath();
            ctx.arc(pm[0], pm[1], 2.6, 0, Math.PI * 2);
            ctx.fillStyle = "rgba(" + col + ",0.9)";
            ctx.fill();
            ctx.lineWidth = 1;
            ctx.strokeStyle = "rgba(255,255,255,0.9)";
            ctx.stroke();
        }
    }

    /* ===================================================================
       Bucle de animación (solo trabaja mientras hay algo visible que animar)
       =================================================================== */
    var instancias = [];
    var corriendo = false, ultimo = 0;

    function pedir() {
        if (!corriendo) { corriendo = true; requestAnimationFrame(bucle); }
    }

    function severidadDe(tarjeta) {
        if (!tarjeta) return "normal";
        if (tarjeta.classList.contains("estado-paro")) return "paro";
        if (tarjeta.classList.contains("estado-alerta")) return "alerta";
        return "normal";
    }

    function anima(inst) {
        if (REDUCIDO) return false;
        return !(inst.pausado || inst.arrastrando) || inst.partes !== null;
    }

    function bucle(t) {
        corriendo = false;
        var dt = Math.min(0.1, Math.max(0, (t - ultimo) / 1000));
        ultimo = t;
        var seguir = false;

        for (var i = instancias.length - 1; i >= 0; i--) {
            var inst = instancias[i];
            if (!inst.canvas.isConnected) { desmontar(inst); instancias.splice(i, 1); continue; }
            if (!inst.visible) continue;

            if (inst.tarjeta) {
                var sev = severidadDe(inst.tarjeta);
                if (sev !== inst.severidad) { inst.severidad = sev; inst.sucio = true; inst.visor.dataset.sev = sev; }
            }
            var animando = anima(inst);
            if (!inst.pausado && !inst.arrastrando && !REDUCIDO) inst.fase += dt * 2 * Math.PI / 18;
            if (inst.sucio || animando) {
                dibujar(inst, t);
                inst.sucio = false;
            }
            if (animando) seguir = true;
        }
        if (seguir) pedir();
    }

    function desmontar(inst) {
        if (inst.io) inst.io.disconnect();
        if (inst.ro) inst.ro.disconnect();
    }

    /* ===================================================================
       Integración con el dashboard
       =================================================================== */
    var marcado = {};                      // marcado[equipoId] = índice de la métrica marcada (o ausente)

    function idEquipo(bloque) { return bloque.id.replace(/^equipo-/, ""); }
    function idBase(id) { return id.replace(/_\d+$/, ""); }

    function claveDe(equipoId, indice) {
        try {
            if (typeof equiposDatos === "undefined") return null;      // lista global del dashboard
            for (var i = 0; i < equiposDatos.length; i++) {
                if (equiposDatos[i].id === equipoId) {
                    var v = equiposDatos[i].variables[indice];
                    return v ? v.clave : null;
                }
            }
        } catch (e) { }
        return null;
    }

    function tarjetaDe(bloque, indice) {
        var valor = bloque.querySelector("#var-" + idEquipo(bloque) + "-" + indice);
        return valor ? valor.closest(".dashboard-card") : null;
    }

    function instanciaDe(bloque) {
        for (var i = 0; i < instancias.length; i++) if (instancias[i].bloque === bloque) return instancias[i];
        return null;
    }

    // Aplica (o quita) la marca de la métrica `indice` sobre el visor del bloque.
    function marcar(bloque, indice) {
        var inst = instanciaDe(bloque);
        if (!inst) return;
        var equipoId = idEquipo(bloque);

        bloque.querySelectorAll(".dashboard-card.dt3d-sel").forEach(function (t) {
            t.classList.remove("dt3d-sel");
            t.removeAttribute("aria-pressed");
        });

        if (indice === null || indice === undefined) {
            delete marcado[equipoId];
            inst.partes = null; inst.centroMarca = null; inst.tarjeta = null;
            inst.visor.querySelector(".dt3d-leyenda").textContent = "";
            inst.severidad = "normal"; inst.visor.dataset.sev = "normal";
            inst.sucio = true; pedir();
            return;
        }

        marcado[equipoId] = indice;
        var tarjeta = tarjetaDe(bloque, indice);
        if (tarjeta) { tarjeta.classList.add("dt3d-sel"); tarjeta.setAttribute("aria-pressed", "true"); }

        var clave = claveDe(equipoId, indice);
        var def = clave && inst.modelo.marcas[clave] ? inst.modelo.marcas[clave] : "*";
        var caja = null;
        if (def === "*") {
            inst.partes = "*";
        } else {
            inst.partes = {};
            def.forEach(function (p) {
                inst.partes[p] = true;
                var c = inst.modelo.cajas[p];
                if (!c) return;
                caja = caja || { min: c.min.slice(), max: c.max.slice() };
                for (var k = 0; k < 3; k++) {
                    caja.min[k] = Math.min(caja.min[k], c.min[k]);
                    caja.max[k] = Math.max(caja.max[k], c.max[k]);
                }
            });
        }
        inst.centroMarca = caja
            ? [(caja.min[0] + caja.max[0]) / 2, (caja.min[1] + caja.max[1]) / 2, (caja.min[2] + caja.max[2]) / 2]
            : [0, 0, 0];

        inst.tarjeta = tarjeta;
        inst.severidad = severidadDe(tarjeta);
        inst.visor.dataset.sev = inst.severidad;
        var h3 = tarjeta ? tarjeta.querySelector("h3") : null;
        inst.visor.querySelector(".dt3d-leyenda").textContent = h3 ? h3.textContent : "";
        inst.sucio = true; pedir();
    }

    function montar(bloque) {
        if (bloque.dataset.dt3d) return;
        var equipoId = idEquipo(bloque);
        var modelo = obtenerModelo(idBase(equipoId));
        var titulo = bloque.querySelector(".equipo-titulo");
        bloque.dataset.dt3d = modelo && titulo ? "1" : "0";
        if (!modelo || !titulo) return;

        var nombre = (titulo.querySelector("h3") || {}).textContent || "activo";
        var lienzo = el("canvas", {
            class: "dt3d-lienzo", tabindex: "0", role: "img",
            "aria-label": "Representación 3D: " + nombre + ". Arrastra o usa las flechas para girar."
        });
        var leyenda = el("span", { class: "dt3d-leyenda", "aria-live": "polite" });
        var pie = el("div", { class: "dt3d-pie" }, [leyenda, el("span", { text: "Arrastra para girar" })]);
        var visor = el("div", { class: "dt3d-visor" }, [lienzo, pie]);
        visor.dataset.sev = "normal";
        titulo.parentNode.insertBefore(visor, titulo.nextSibling);
        bloque.classList.add("dt3d-activo");

        var inst = {
            bloque: bloque, visor: visor, canvas: lienzo, ctx: lienzo.getContext("2d"), modelo: modelo,
            ancho: 0, alto: 0, dpr: 1, yaw: -0.55, pitch: 0.38, fase: 0,
            partes: null, centroMarca: null, tarjeta: null, severidad: "normal",
            pausado: false, arrastrando: false, visible: true, sucio: true
        };
        instancias.push(inst);

        function ajustar() {
            var r = lienzo.getBoundingClientRect();
            inst.dpr = Math.min(window.devicePixelRatio || 1, 2);
            inst.ancho = r.width; inst.alto = r.height;
            lienzo.width = Math.round(r.width * inst.dpr);
            lienzo.height = Math.round(r.height * inst.dpr);
            inst.sucio = true; pedir();
        }
        if (window.ResizeObserver) {
            inst.ro = new ResizeObserver(ajustar);
            inst.ro.observe(lienzo);
        } else {
            window.addEventListener("resize", ajustar);
        }
        ajustar();

        if (window.IntersectionObserver) {
            inst.visible = false;
            inst.io = new IntersectionObserver(function (entradas) {
                inst.visible = entradas[entradas.length - 1].isIntersecting;
                if (inst.visible) { inst.sucio = true; pedir(); }
            });
            inst.io.observe(lienzo);
        }

        // Girar con el puntero (el scroll vertical táctil sigue funcionando).
        var ultimoX = 0, ultimoY = 0;
        lienzo.addEventListener("pointerdown", function (e) {
            inst.arrastrando = true; ultimoX = e.clientX; ultimoY = e.clientY;
            try { lienzo.setPointerCapture(e.pointerId); } catch (err) { }
        });
        lienzo.addEventListener("pointermove", function (e) {
            if (!inst.arrastrando) return;
            inst.yaw += (e.clientX - ultimoX) * 0.01;
            if (e.pointerType === "mouse") inst.pitch = Math.max(0.05, Math.min(1.2, inst.pitch + (e.clientY - ultimoY) * 0.008));
            ultimoX = e.clientX; ultimoY = e.clientY;
            inst.sucio = true; pedir();
        });
        function soltar() { inst.arrastrando = false; inst.sucio = true; pedir(); }
        lienzo.addEventListener("pointerup", soltar);
        lienzo.addEventListener("pointercancel", soltar);
        lienzo.addEventListener("pointerenter", function () { inst.pausado = true; });
        lienzo.addEventListener("pointerleave", function () { inst.pausado = false; pedir(); });
        lienzo.addEventListener("dblclick", function () { inst.yaw = -0.55; inst.pitch = 0.38; inst.sucio = true; pedir(); });
        lienzo.addEventListener("keydown", function (e) {
            var usado = true;
            if (e.key === "ArrowLeft") inst.yaw -= 0.12;
            else if (e.key === "ArrowRight") inst.yaw += 0.12;
            else if (e.key === "ArrowUp") inst.pitch = Math.min(1.2, inst.pitch + 0.08);
            else if (e.key === "ArrowDown") inst.pitch = Math.max(0.05, inst.pitch - 0.08);
            else if (e.key === "Home") { inst.yaw = -0.55; inst.pitch = 0.38; }
            else usado = false;
            if (usado) { e.preventDefault(); inst.sucio = true; pedir(); }
        });

        // Las tarjetas de métricas se pueden tocar también con teclado.
        bloque.querySelectorAll(".cards-grid > .dashboard-card").forEach(function (t) {
            if (t.querySelector('.value[id^="var-"]')) t.setAttribute("tabindex", "0");
        });

        if (marcado[equipoId] !== undefined) marcar(bloque, marcado[equipoId]);
    }

    function indiceDeTarjeta(tarjeta) {
        var valor = tarjeta.querySelector(".value");
        var m = valor && /^var-.+-(\d+)$/.exec(valor.id);
        return m ? parseInt(m[1], 10) : null;
    }

    // Toque en una tarjeta o en una opción del selector «Métricas a mostrar».
    contenedor.addEventListener("click", function (e) {
        var bloque = e.target.closest ? e.target.closest(".equipo-bloque.dt3d-activo") : null;
        if (!bloque) return;
        var equipoId = idEquipo(bloque);

        var chip = e.target.closest(".foco-chip");
        if (chip) {
            // metricas_foco.js ya actualizó aria-pressed en su propio manejador.
            var idx = chip.dataset.chip;
            if (idx === "todas") { marcar(bloque, null); return; }
            idx = parseInt(idx, 10);
            if (chip.getAttribute("aria-pressed") === "true") marcar(bloque, idx);
            else if (marcado[equipoId] === idx) marcar(bloque, null);
            return;
        }

        var tarjeta = e.target.closest(".cards-grid > .dashboard-card");
        if (!tarjeta) return;
        var indice = indiceDeTarjeta(tarjeta);
        if (indice === null) return;
        marcar(bloque, marcado[equipoId] === indice ? null : indice);
    });

    contenedor.addEventListener("keydown", function (e) {
        if (e.key !== "Enter" && e.key !== " ") return;
        var tarjeta = e.target.closest ? e.target.closest(".cards-grid > .dashboard-card") : null;
        if (!tarjeta || e.target !== tarjeta) return;
        e.preventDefault();
        tarjeta.click();
    });

    function procesar() {
        contenedor.querySelectorAll(".equipo-bloque").forEach(montar);
        // Si el selector oculta la tarjeta marcada, se retira la marca.
        instancias.forEach(function (inst) {
            if (inst.tarjeta && inst.tarjeta.style.display === "none") marcar(inst.bloque, null);
        });
    }

    new MutationObserver(procesar).observe(contenedor, { childList: true });
    setInterval(procesar, 2000);
    procesar();
})();
