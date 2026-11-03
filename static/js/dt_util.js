/* Utilidades compartidas por los módulos nuevos del dashboard. */
(function () {
    "use strict";

    function el(tag, props, hijos) {
        var nodo = document.createElement(tag);
        if (props) {
            Object.keys(props).forEach(function (k) {
                if (k === "class") nodo.className = props[k];
                else if (k === "text") nodo.textContent = props[k];
                else if (k === "dataset") Object.keys(props[k]).forEach(function (d) { nodo.dataset[d] = props[k][d]; });
                else if (k.indexOf("on") === 0 && typeof props[k] === "function") nodo.addEventListener(k.slice(2), props[k]);
                else if (props[k] !== null && props[k] !== undefined && props[k] !== false) nodo.setAttribute(k, props[k] === true ? "" : props[k]);
            });
        }
        (hijos || []).forEach(function (h) {
            if (h === null || h === undefined || h === false) return;
            nodo.appendChild(typeof h === "string" ? document.createTextNode(h) : h);
        });
        return nodo;
    }

    async function api(url, opciones) {
        var o = Object.assign({ headers: {} }, opciones || {});
        if (o.body !== undefined && typeof o.body !== "string") {
            o.body = JSON.stringify(o.body);
            o.headers["Content-Type"] = "application/json";
        }
        try {
            var r = await fetch(url, o);
            var datos = null;
            try { datos = await r.json(); } catch (e) { }
            return { ok: r.ok, status: r.status, data: datos || {} };
        } catch (e) {
            return { ok: false, status: 0, data: { error: "No se pudo conectar con el servidor." } };
        }
    }

    function fmtFecha(iso) {
        if (!iso) return "—";
        var p = String(iso).split("-");
        return p.length === 3 ? p[2] + "/" + p[1] + "/" + p[0] : iso;
    }

    function fmtNumero(n) {
        return n === null || n === undefined ? "" : String(n);
    }

    window.DT = { el: el, api: api, fmtFecha: fmtFecha, fmtNumero: fmtNumero };
})();
