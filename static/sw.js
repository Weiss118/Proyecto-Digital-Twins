// Service Worker para la PWA del Gemelo Digital

self.addEventListener("install", function(event) {

    console.log("[Service Worker] Instalado");

    self.skipWaiting();

});


self.addEventListener("activate", function(event) {

    console.log("[Service Worker] Activado");

});


self.addEventListener("fetch", function(event) {

    event.respondWith(
        fetch(event.request)
            .catch(function() {

                return new Response(
                    "Sin conexión con el servidor.",
                    {
                        headers: {
                            "Content-Type": "text/plain"
                        }
                    }
                );

            })
    );

});