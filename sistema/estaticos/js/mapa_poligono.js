// Mapa de la pestaña Ubicación (HU-1.3): municipio, polígono vigente, anteriores y dibujo de respaldo.
(function () {
  const div = document.getElementById("mapa");
  if (!div || !window.L) return;
  const mapa = L.map(div, { zoomControl: true });
  window.mapaPoligono = mapa;
  if (div.dataset.teselas) {
    L.tileLayer(div.dataset.teselas, {
      maxZoom: 19,
      attribution: "&copy; colaboradores de OpenStreetMap",
      // OSM bloquea las teselas que llegan sin Referer; el sistema no lo envía a otros sitios (Referrer-Policy:
      // same-origin), así que las teselas mandan solo el origen (sin la ruta ni el folio).
      referrerPolicy: "strict-origin-when-cross-origin",
    }).addTo(mapa);
  }
  mapa.setView([19.35, -99.6], 9);

  fetch(div.dataset.url, { credentials: "same-origin" })
    .then((r) => r.json())
    .then((datos) => {
      const municipio = L.geoJSON(datos.municipio, {
        style: { color: "#c47f00", weight: 2, fill: false }, pmIgnore: true,
      }).addTo(mapa);
      const anteriores = L.geoJSON(datos.poligonos, {
        filter: (f) => !f.properties.vigente,
        style: { color: "#888", weight: 2, dashArray: "6 4", fillOpacity: 0.05 }, pmIgnore: true,
      }).addTo(mapa);
      const vigente = L.geoJSON(datos.poligonos, {
        filter: (f) => f.properties.vigente,
        style: { color: "#1f5130", weight: 3, fillOpacity: 0.25 }, pmIgnore: true,
        onEachFeature: (f, capa) => capa.bindTooltip(f.properties.superficie_ha.toFixed(2) + " ha"),
      }).addTo(mapa);
      const limites = vigente.getLayers().length ? vigente.getBounds() : municipio.getBounds();
      if (anteriores.getLayers().length) limites.extend(anteriores.getBounds());
      mapa.fitBounds(limites, { padding: [20, 20] });
      div.dataset.listo = "1";
    });

  if (div.dataset.editable !== "1" || !mapa.pm) return;
  mapa.pm.setLang("es");
  mapa.pm.addControls({
    position: "topleft", drawMarker: false, drawCircleMarker: false, drawPolyline: false, drawCircle: false,
    drawText: false, drawRectangle: true, drawPolygon: true, editMode: true, dragMode: false, cutPolygon: false,
    removalMode: true, rotateMode: false,
  });
  const campo = document.querySelector("#form-poligono input[name=dibujo]");
  function actualizar() {
    const capas = mapa.pm.getGeomanLayers().filter((c) => c.toGeoJSON && !c.options.pmIgnore);
    const elementos = capas.map((c) => c.toGeoJSON()).filter((f) => f.geometry && f.geometry.type.includes("Polygon"));
    campo.value = elementos.length ? JSON.stringify({ type: "FeatureCollection", features: elementos }) : "";
  }
  mapa.on("pm:create", (e) => {
    e.layer.on("pm:edit", actualizar);
    actualizar();
  });
  mapa.on("pm:remove", actualizar);
})();
