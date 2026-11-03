/* Selector de métricas por activo.
 *
 * Añade, sobre las tarjetas de cada activo, un selector para elegir qué
 * métricas ver y concentrarse en ellas. No modifica el código existente del
 * dashboard: observa #equipos y oculta/muestra tarjetas ya renderizadas.
 *
 * Para que, al elegir un activo, NO se muestre ninguna métrica hasta que el
 * usuario elija (en lugar de mostrar todas), cambia la constante siguiente a false.
 */
(function () {
    "use strict";

    var MOSTRAR_TODAS_POR_DEFECTO = true;
    var CLAVE_ALMACEN = "metricasSeleccionadas";

    var contenedor = document.getElementById("equipos");
    if (!contenedor || !window.DT) return;
    var el = window.DT.el;

    // seleccion[equipoId] = "todas" | [indices de variable] | undefined (usa el valor por defecto)
    var seleccion = {};
    try { seleccion = JSON.parse(sessionStorage.getItem(CLAVE_ALMACEN)) || {}; } catch (e) { seleccion = {}; }

    function guardar() {
        try { sessionStorage.setItem(CLAVE_ALMACEN, JSON.stringify(seleccion)); } catch (e) { }
    }

    function idEquipo(bloque) {
        return bloque.id.replace(/^equipo-/, "");
    }

    // Tarjetas de variables del bloque, ordenadas por índice (la tarjeta «Estado» se excluye).
    function tarjetasVariables(bloque) {
        var lista = [];
        bloque.querySelectorAll(".cards-grid > .dashboard-card").forEach(function (tarjeta) {
            var valor = tarjeta.querySelector(".value");
            var m = valor && /^var-.*-(\d+)$/.exec(valor.id);
            if (m) lista.push({ indice: parseInt(m[1], 10), tarjeta: tarjeta, nombre: tarjeta.querySelector("h3").textContent });
        });
        return lista;
    }

    function visibles(equipoId, total) {
        var s = seleccion[equipoId];
        if (s === "todas") return null;                       // null = todas
        if (Array.isArray(s) && s.length) return s;
        return MOSTRAR_TODAS_POR_DEFECTO ? null : [];
    }

    function severidad(tarjeta) {
        if (tarjeta.classList.contains("estado-paro")) return "paro";
        if (tarjeta.classList.contains("estado-alerta")) return "alerta";
        return "normal";
    }

    function alternar(equipoId, indice, todos) {
        var actual = visibles(equipoId, todos.length);
        var conjunto;
        if (actual === null) {
            conjunto = [indice];                               // desde «Todas»: enfocar solo esta
        } else {
            conjunto = actual.indexOf(indice) >= 0
                ? actual.filter(function (i) { return i !== indice; })
                : actual.concat([indice]);
        }
        if (conjunto.length === 0) delete seleccion[equipoId];
        else if (conjunto.length === todos.length) seleccion[equipoId] = "todas";
        else seleccion[equipoId] = conjunto.sort(function (a, b) { return a - b; });
        guardar();
    }

    function construirSelector(bloque) {
        var equipoId = idEquipo(bloque);
        var variables = tarjetasVariables(bloque);
        var barra = el("div", { class: "foco-metricas", role: "group", "aria-label": "Métricas a mostrar" });
        var etiqueta = el("span", { class: "foco-etiqueta", text: "Métricas a mostrar" });
        var chips = el("div", { class: "foco-chips" });
        var aviso = el("span", { class: "foco-aviso", role: "status" });

        var chipTodas = el("button", {
            type: "button", class: "foco-chip", dataset: { chip: "todas" },
            onclick: function () { seleccion[equipoId] = "todas"; guardar(); aplicar(bloque); }
        }, ["Todas"]);
        chips.appendChild(chipTodas);

        variables.forEach(function (v) {
            chips.appendChild(el("button", {
                type: "button", class: "foco-chip", dataset: { chip: String(v.indice), sev: "normal" },
                onclick: function () { alternar(equipoId, v.indice, variables); aplicar(bloque); }
            }, [v.nombre]));
        });

        barra.append(etiqueta, chips, aviso);
        var rejilla = bloque.querySelector(".cards-grid");
        bloque.insertBefore(barra, rejilla);
        bloque.dataset.focoListo = "1";
    }

    function aplicar(bloque) {
        if (!bloque.dataset.focoListo) construirSelector(bloque);
        var equipoId = idEquipo(bloque);
        var variables = tarjetasVariables(bloque);
        var activas = visibles(equipoId, variables.length);   // null = todas
        var ocultasConProblema = 0;

        variables.forEach(function (v) {
            var mostrar = activas === null || activas.indexOf(v.indice) >= 0;
            v.tarjeta.style.display = mostrar ? "" : "none";
            var chip = bloque.querySelector('.foco-chip[data-chip="' + v.indice + '"]');
            if (chip) {
                chip.setAttribute("aria-pressed", activas !== null && mostrar ? "true" : "false");
                chip.dataset.sev = severidad(v.tarjeta);
            }
            if (!mostrar && severidad(v.tarjeta) !== "normal") ocultasConProblema++;
        });

        var chipTodas = bloque.querySelector('.foco-chip[data-chip="todas"]');
        if (chipTodas) chipTodas.setAttribute("aria-pressed", activas === null ? "true" : "false");

        var aviso = bloque.querySelector(".foco-aviso");
        if (aviso) {
            aviso.textContent = ocultasConProblema
                ? "⚠ " + ocultasConProblema + (ocultasConProblema === 1 ? " métrica oculta está" : " métricas ocultas están") + " en alerta o crítico"
                : (activas !== null && activas.length === 0 ? "Selecciona una métrica para verla" : "");
        }
    }

    function procesar() {
        contenedor.querySelectorAll(".equipo-bloque").forEach(aplicar);
    }

    // Se redibuja el bloque cuando cambia el activo seleccionado.
    new MutationObserver(procesar).observe(contenedor, { childList: true });
    // Mantiene al día los indicadores de severidad de cada opción (los valores cambian cada 2 s).
    setInterval(procesar, 2000);
    procesar();
})();
