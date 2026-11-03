/* Calendario de mantenimiento por activo. */
(function () {
    "use strict";

    var seccion = document.getElementById("sec-mantenimiento");
    if (!seccion || !window.DT) return;
    var DT = window.DT, el = DT.el;

    var puedeEditar = seccion.dataset.puedeEditar === "1";
    var selector = document.getElementById("mant-equipo");
    var rejilla = document.getElementById("mant-calendario");
    var panel = document.getElementById("mant-panel");
    var msg = document.getElementById("mant-msg");
    var MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];
    var DIAS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];

    var estado = { hoy: "", tipos: [], equipos: [], equipoId: null, anio: 0, mes: 0, eventos: [] };

    function mostrarMensaje(texto, tipo) {
        msg.textContent = texto || "";
        msg.className = "dt-msg" + (tipo ? " " + tipo : "");
    }

    function dos(n) { return (n < 10 ? "0" : "") + n; }
    function claveFecha(anio, mes, dia) { return anio + "-" + dos(mes + 1) + "-" + dos(dia); }

    function datosEquipo(id) {
        return estado.equipos.find(function (e) { return e.equipo_id === id; });
    }

    function claseEvento(ev) {
        if (ev.estado === "Realizado") return "realizado";
        return ev.vencido ? "vencido" : "programado";
    }

    function textoPlazo(m) {
        if (m.vencido) return "Vencido hace " + Math.abs(m.dias_restantes) + (Math.abs(m.dias_restantes) === 1 ? " día" : " días");
        if (m.dias_restantes === 0) return "Es hoy";
        if (m.dias_restantes === 1) return "Mañana";
        return "En " + m.dias_restantes + " días";
    }

    // ---------------- Resumen (último / próximo) ----------------
    function pintarResumenActivo() {
        var d = datosEquipo(estado.equipoId);
        var u = d && d.ultimo, p = d && d.proximo;

        document.getElementById("mant-ultimo").textContent = u ? DT.fmtFecha(u.fecha_realizada) : "Sin registros";
        document.getElementById("mant-ultimo-det").textContent = u
            ? u.tipo + (u.responsable ? " — " + u.responsable : "") : "";

        var nodoP = document.getElementById("mant-proximo");
        var detP = document.getElementById("mant-proximo-det");
        nodoP.textContent = p ? DT.fmtFecha(p.fecha_programada) : "Sin programar";
        detP.replaceChildren();
        if (p) {
            detP.appendChild(document.createTextNode("Tipo: " + p.tipo + " · "));
            detP.appendChild(el("span", { class: p.vencido ? "vencido" : "", text: textoPlazo(p) }));
        }
    }

    function pintarTablaResumen() {
        var cuerpo = document.getElementById("mant-resumen-filas");
        cuerpo.replaceChildren();
        estado.equipos.forEach(function (d) {
            cuerpo.appendChild(el("tr", {}, [
                el("td", { text: d.nombre }),
                el("td", { text: d.ultimo ? DT.fmtFecha(d.ultimo.fecha_realizada) + " — " + d.ultimo.tipo : "Sin registros" }),
                el("td", {}, [
                    d.proximo ? DT.fmtFecha(d.proximo.fecha_programada) + " — " + d.proximo.tipo + " " : "Sin programar",
                    d.proximo && d.proximo.vencido ? el("span", { class: "vencido", text: "(vencido)" }) : null
                ]),
                el("td", {}, [el("button", {
                    type: "button", class: "dt-btn secundario", text: "Ver calendario",
                    onclick: function () { selector.value = d.equipo_id; cambiarEquipo(); seccion.scrollIntoView({ behavior: "smooth", block: "start" }); }
                })])
            ]));
        });
    }

    // ---------------- Calendario ----------------
    function pintarCalendario() {
        document.getElementById("mant-mes").textContent = MESES[estado.mes] + " " + estado.anio;
        rejilla.replaceChildren();
        DIAS.forEach(function (d) { rejilla.appendChild(el("div", { class: "mant-dia-semana", text: d })); });

        var primerDia = (new Date(estado.anio, estado.mes, 1).getDay() + 6) % 7; // lunes = 0
        var totalDias = new Date(estado.anio, estado.mes + 1, 0).getDate();
        for (var i = 0; i < primerDia; i++) rejilla.appendChild(el("div", { class: "mant-dia vacio" }));

        for (var dia = 1; dia <= totalDias; dia++) {
            (function (dia) {
                var fecha = claveFecha(estado.anio, estado.mes, dia);
                var celda = el("div", {
                    class: "mant-dia" + (fecha === estado.hoy ? " hoy" : "") + (puedeEditar ? " editable" : ""),
                    role: "gridcell"
                }, [el("span", { class: "mant-num", text: String(dia) })]);

                estado.eventos.filter(function (e) { return e.fecha === fecha; }).forEach(function (ev) {
                    celda.appendChild(el("button", {
                        type: "button", class: "mant-ev " + claseEvento(ev), text: ev.tipo,
                        title: ev.tipo + " — " + ev.estado,
                        onclick: function (e) { e.stopPropagation(); mostrarDetalle(ev); }
                    }));
                });

                if (puedeEditar) {
                    celda.addEventListener("click", function () { mostrarFormulario(null, fecha); });
                }
                rejilla.appendChild(celda);
            })(dia);
        }
    }

    async function cargarMes() {
        var mes = estado.anio + "-" + dos(estado.mes + 1);
        var r = await DT.api("/api/mantenimientos?equipo_id=" + encodeURIComponent(estado.equipoId) + "&mes=" + mes);
        if (!r.ok) { mostrarMensaje(r.data.error || "No se pudo cargar el calendario.", "error"); return; }
        estado.eventos = r.data.eventos;
        pintarCalendario();
    }

    async function cargarResumen() {
        var r = await DT.api("/api/mantenimientos/resumen");
        if (!r.ok) { mostrarMensaje(r.data.error || "No se pudo cargar el resumen.", "error"); return false; }
        estado.hoy = r.data.hoy;
        estado.tipos = r.data.tipos;
        estado.equipos = r.data.equipos;
        pintarResumenActivo();
        pintarTablaResumen();
        return true;
    }

    async function refrescar() {
        await cargarResumen();
        await cargarMes();
    }

    function cambiarEquipo() {
        estado.equipoId = selector.value;
        cerrarPanel();
        mostrarMensaje("");
        pintarResumenActivo();
        cargarMes();
    }

    function moverMes(delta) {
        var f = new Date(estado.anio, estado.mes + delta, 1);
        estado.anio = f.getFullYear();
        estado.mes = f.getMonth();
        cargarMes();
    }

    // ---------------- Panel de detalle / formularios ----------------
    function cerrarPanel() { panel.hidden = true; panel.replaceChildren(); }

    function abrirPanel(nodos) {
        panel.replaceChildren.apply(panel, nodos);
        panel.hidden = false;
        panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }

    async function ejecutar(promesa, textoOk) {
        var r = await promesa;
        if (!r.ok) { mostrarMensaje(r.data.error || "No se pudo completar la acción.", "error"); return false; }
        mostrarMensaje(textoOk || r.data.mensaje, "ok");
        cerrarPanel();
        await refrescar();
        return true;
    }

    function mostrarDetalle(ev) {
        var nombre = (datosEquipo(ev.equipo_id) || {}).nombre || ev.equipo_id;
        var lineas = [
            el("p", {}, [el("strong", { text: "Activo: " }), nombre]),
            el("p", {}, [el("strong", { text: "Tipo: " }), ev.tipo]),
            el("p", {}, [el("strong", { text: "Estado: " }), ev.estado + (ev.vencido ? " (vencido)" : "")]),
            el("p", {}, [el("strong", { text: ev.estado === "Realizado" ? "Realizado el: " : "Fecha programada: " }),
                DT.fmtFecha(ev.estado === "Realizado" ? ev.fecha_realizada : ev.fecha_programada)])
        ];
        if (ev.responsable) lineas.push(el("p", {}, [el("strong", { text: "Responsable: " }), ev.responsable]));
        if (ev.descripcion) lineas.push(el("p", {}, [el("strong", { text: "Descripción: " }), ev.descripcion]));
        if (ev.notas_cierre) lineas.push(el("p", {}, [el("strong", { text: "Notas de cierre: " }), ev.notas_cierre]));

        var acciones = el("div", { class: "umb-acciones" });
        if (puedeEditar && ev.estado === "Programado") {
            acciones.append(
                el("button", { type: "button", class: "dt-btn", text: "Marcar como realizado", onclick: function () { mostrarCierre(ev); } }),
                el("button", { type: "button", class: "dt-btn secundario", text: "Editar / reprogramar", onclick: function () { mostrarFormulario(ev); } }),
                el("button", {
                    type: "button", class: "dt-btn peligro", text: "Cancelar mantenimiento",
                    onclick: function () {
                        if (window.confirm("¿Cancelar este mantenimiento programado?"))
                            ejecutar(DT.api("/api/mantenimientos/" + ev.id + "/cancelar", { method: "POST", body: {} }));
                    }
                })
            );
        }
        acciones.appendChild(el("button", { type: "button", class: "dt-btn secundario", text: "Cerrar", onclick: cerrarPanel }));

        abrirPanel([el("h3", { text: "Detalle del mantenimiento" }), el("div", { class: "mant-detalle" }, lineas), acciones]);
    }

    function mostrarCierre(ev) {
        var fecha = el("input", { type: "date", value: estado.hoy, max: estado.hoy, id: "mant-f-realizada" });
        var notas = el("textarea", { id: "mant-f-notas", rows: "2", maxlength: "500" });
        abrirPanel([
            el("h3", { text: "Marcar como realizado — " + ev.tipo }),
            el("div", { class: "mant-form" }, [
                el("div", {}, [el("label", { for: "mant-f-realizada", text: "Fecha de realización" }), fecha]),
                el("div", { class: "ancho-total" }, [el("label", { for: "mant-f-notas", text: "Notas (opcional)" }), notas])
            ]),
            el("div", { class: "umb-acciones" }, [
                el("button", {
                    type: "button", class: "dt-btn", text: "Confirmar",
                    onclick: function () {
                        ejecutar(DT.api("/api/mantenimientos/" + ev.id + "/realizar",
                            { method: "POST", body: { fecha_realizada: fecha.value, notas_cierre: notas.value } }));
                    }
                }),
                el("button", { type: "button", class: "dt-btn secundario", text: "Volver", onclick: function () { mostrarDetalle(ev); } })
            ])
        ]);
    }

    function mostrarFormulario(ev, fechaInicial) {
        if (!puedeEditar) return;
        var editando = !!ev;
        var tipo = el("select", { id: "mant-f-tipo" }, estado.tipos.map(function (t) {
            return el("option", { value: t, text: t, selected: editando && ev.tipo === t });
        }));
        var fecha = el("input", { type: "date", id: "mant-f-fecha", value: editando ? ev.fecha_programada : (fechaInicial || estado.hoy) });
        var responsable = el("input", { type: "text", id: "mant-f-resp", maxlength: "80", value: editando ? ev.responsable : "" });
        var descripcion = el("textarea", { id: "mant-f-desc", rows: "2", maxlength: "500" });
        descripcion.value = editando ? ev.descripcion : "";
        var yaRealizado = el("input", { type: "checkbox", id: "mant-f-hecho" });

        var nombre = (datosEquipo(estado.equipoId) || {}).nombre || "";
        var campos = [
            el("div", {}, [el("label", { for: "mant-f-tipo", text: "Tipo de mantenimiento" }), tipo]),
            el("div", {}, [el("label", { for: "mant-f-fecha", text: "Fecha" }), fecha]),
            el("div", {}, [el("label", { for: "mant-f-resp", text: "Responsable (opcional)" }), responsable]),
            el("div", { class: "ancho-total" }, [el("label", { for: "mant-f-desc", text: "Descripción (opcional)" }), descripcion])
        ];
        if (!editando) {
            campos.push(el("div", { class: "ancho-total" }, [el("label", {}, [yaRealizado, " Registrar como ya realizado (la fecha indicada es la de realización)"])]));
        }

        abrirPanel([
            el("h3", { text: (editando ? "Editar mantenimiento" : "Programar mantenimiento") + " — " + nombre }),
            el("div", { class: "mant-form" }, campos),
            el("div", { class: "umb-acciones" }, [
                el("button", {
                    type: "button", class: "dt-btn", text: "Guardar",
                    onclick: function () {
                        var cuerpo = { tipo: tipo.value, fecha_programada: fecha.value, responsable: responsable.value, descripcion: descripcion.value };
                        if (editando) {
                            ejecutar(DT.api("/api/mantenimientos/" + ev.id, { method: "PUT", body: cuerpo }));
                        } else {
                            cuerpo.equipo_id = estado.equipoId;
                            cuerpo.ya_realizado = yaRealizado.checked;
                            ejecutar(DT.api("/api/mantenimientos", { method: "POST", body: cuerpo }));
                        }
                    }
                }),
                el("button", { type: "button", class: "dt-btn secundario", text: "Cancelar", onclick: cerrarPanel })
            ])
        ]);
    }

    // ---------------- Inicio ----------------
    async function iniciar() {
        if (!(await cargarResumen())) return;
        selector.replaceChildren();
        estado.equipos.forEach(function (d) { selector.appendChild(el("option", { value: d.equipo_id, text: d.nombre })); });

        var preferido = null;
        try { preferido = sessionStorage.getItem("equipoSeleccionado"); } catch (e) { }
        selector.value = datosEquipo(preferido) ? preferido : estado.equipos[0].equipo_id;
        estado.equipoId = selector.value;

        var hoy = estado.hoy.split("-");
        estado.anio = parseInt(hoy[0], 10);
        estado.mes = parseInt(hoy[1], 10) - 1;

        pintarResumenActivo();
        await cargarMes();
    }

    selector.addEventListener("change", cambiarEquipo);
    document.getElementById("mant-prev").addEventListener("click", function () { moverMes(-1); });
    document.getElementById("mant-sig").addEventListener("click", function () { moverMes(1); });
    document.getElementById("mant-hoy").addEventListener("click", function () {
        var h = estado.hoy.split("-");
        estado.anio = parseInt(h[0], 10);
        estado.mes = parseInt(h[1], 10) - 1;
        cargarMes();
    });
    var btnNuevo = document.getElementById("mant-nuevo");
    if (btnNuevo) btnNuevo.addEventListener("click", function () { mostrarFormulario(null); });

    // Sigue al selector principal del dashboard cuando el usuario cambia de equipo allí.
    var selectorPrincipal = document.getElementById("selector-equipo");
    if (selectorPrincipal) {
        selectorPrincipal.addEventListener("change", function (e) {
            if (datosEquipo(e.target.value)) { selector.value = e.target.value; cambiarEquipo(); }
        });
    }

    iniciar();
})();
