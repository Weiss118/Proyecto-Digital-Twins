/* Configuración de umbrales por activo (solo roles autorizados). */
(function () {
    "use strict";

    var seccion = document.getElementById("sec-umbrales");
    if (!seccion || !window.DT) return;
    var DT = window.DT, el = DT.el;

    var CAMPOS = ["paro_bajo", "alerta_baja", "alerta_alta", "paro_alto"];
    var selector = document.getElementById("umbral-equipo");
    var filas = document.getElementById("umbral-filas");
    var msg = document.getElementById("umbral-msg");
    var equipos = [];

    function mostrarMensaje(texto, tipo) {
        msg.textContent = texto || "";
        msg.className = "dt-msg" + (tipo ? " " + tipo : "");
    }

    function equipoActual() {
        return equipos.find(function (e) { return e.id === selector.value; });
    }

    function filaVariable(equipo, variable) {
        var entradas = {};
        var tr = el("tr", { dataset: { variable: variable.clave } });

        var celdaNombre = el("td", {}, [
            el("strong", { text: variable.etiqueta }),
            el("span", { class: "umb-pred", text: variable.unidad ? "Unidad: " + variable.unidad : "" }),
            variable.personalizado ? el("span", { class: "umb-etiqueta-personalizado", text: "Personalizado" }) : null
        ]);
        tr.appendChild(celdaNombre);

        CAMPOS.forEach(function (campo) {
            var entrada = el("input", {
                type: "number", step: "any", inputmode: "decimal",
                value: DT.fmtNumero(variable.actual[campo]),
                "aria-label": variable.etiqueta + " — " + campo.replace("_", " ")
            });
            entradas[campo] = entrada;
            var pred = variable.predeterminado[campo];
            tr.appendChild(el("td", {}, [
                entrada,
                el("span", { class: "umb-pred", text: "Pred.: " + (pred === null ? "—" : pred) })
            ]));
        });

        var btnGuardar = el("button", { type: "button", class: "dt-btn", text: "Guardar" });
        var btnRestablecer = el("button", {
            type: "button", class: "dt-btn secundario", text: "Restablecer", disabled: !variable.personalizado
        });

        btnGuardar.addEventListener("click", async function () {
            var cuerpo = {};
            CAMPOS.forEach(function (c) { cuerpo[c] = entradas[c].value.trim() === "" ? null : entradas[c].value; });
            btnGuardar.disabled = true;
            var r = await DT.api("/api/umbrales/" + encodeURIComponent(equipo.id) + "/" + encodeURIComponent(variable.clave),
                { method: "PUT", body: cuerpo });
            btnGuardar.disabled = false;
            if (!r.ok) { mostrarMensaje(r.data.error || "No se pudo guardar.", "error"); return; }
            reemplazar(equipo, r.data.variable);
            mostrarMensaje(variable.etiqueta + ": umbrales actualizados.", "ok");
            cargarHistorial();
        });

        btnRestablecer.addEventListener("click", async function () {
            if (!window.confirm("¿Restablecer «" + variable.etiqueta + "» a los valores originales?")) return;
            var r = await DT.api("/api/umbrales/" + encodeURIComponent(equipo.id) + "/" + encodeURIComponent(variable.clave),
                { method: "DELETE" });
            if (!r.ok) { mostrarMensaje(r.data.error || "No se pudo restablecer.", "error"); return; }
            reemplazar(equipo, r.data.variable);
            mostrarMensaje(variable.etiqueta + ": valores originales restablecidos.", "ok");
            cargarHistorial();
        });

        tr.appendChild(el("td", {}, [el("div", { class: "umb-acciones" }, [btnGuardar, btnRestablecer])]));
        return tr;
    }

    function reemplazar(equipo, variableNueva) {
        var i = equipo.variables.findIndex(function (v) { return v.clave === variableNueva.clave; });
        if (i >= 0) equipo.variables[i] = variableNueva;
        pintarTabla();
    }

    function pintarTabla() {
        var equipo = equipoActual();
        filas.replaceChildren();
        if (!equipo) return;
        equipo.variables.forEach(function (v) { filas.appendChild(filaVariable(equipo, v)); });
    }

    function describir(limites) {
        if (!limites) return "—";
        var nombres = { paro_bajo: "crít. mín", alerta_baja: "alerta mín", alerta_alta: "alerta máx", paro_alto: "crít. máx" };
        var partes = CAMPOS.filter(function (c) { return limites[c] !== null && limites[c] !== undefined; })
            .map(function (c) { return nombres[c] + " " + limites[c]; });
        return partes.length ? partes.join(", ") : "sin límites";
    }

    async function cargarHistorial() {
        var lista = document.getElementById("umbral-historial");
        var r = await DT.api("/api/umbrales/historial");
        if (!r.ok) return;
        lista.replaceChildren();
        if (!r.data.eventos.length) { lista.appendChild(el("li", { text: "Aún no hay cambios registrados." })); return; }
        r.data.eventos.forEach(function (e) {
            var accion = e.accion === "restablecer" ? "restableció" : "modificó";
            lista.appendChild(el("li", {
                text: e.fecha_hora.replace("T", " ").slice(0, 16) + " — " + e.usuario + " " + accion + " " + e.equipo +
                    " / " + e.variable + ": " + describir(e.anterior) + " → " + describir(e.nuevo)
            }));
        });
    }

    async function iniciar() {
        var r = await DT.api("/api/umbrales");
        if (!r.ok) { mostrarMensaje(r.data.error || "No se pudieron cargar los umbrales.", "error"); return; }
        equipos = r.data.equipos;
        selector.replaceChildren();
        equipos.forEach(function (e) { selector.appendChild(el("option", { value: e.id, text: e.nombre })); });
        var preferido = null;
        try { preferido = sessionStorage.getItem("equipoSeleccionado"); } catch (e) { }
        if (preferido && equipos.some(function (e) { return e.id === preferido; })) selector.value = preferido;
        pintarTabla();
        cargarHistorial();
    }

    selector.addEventListener("change", function () { mostrarMensaje(""); pintarTabla(); });
    iniciar();
})();
