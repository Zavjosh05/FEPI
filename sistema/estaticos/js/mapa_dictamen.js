// Mapa del análisis cartográfico (HU-2.1): polígono vigente, traslapes con otros expedientes y municipio.
(function () {
  const div = document.getElementById("mapa");
  if (!div || !window.L) return;
  const mapa = L.map(div);
  if (div.dataset.teselas) {
    L.tileLayer(div.dataset.teselas, {
      maxZoom: 19, attribution: "&copy; colaboradores de OpenStreetMap",
      referrerPolicy: "strict-origin-when-cross-origin",   // OSM bloquea las teselas sin Referer (ver mapa_poligono.js)
    }).addTo(mapa);
  }
  mapa.setView([19.35, -99.6], 9);
  fetch(div.dataset.url, { credentials: "same-origin" })
    .then((r) => r.json())
    .then((datos) => {
      const municipio = L.geoJSON(datos.municipio, { style: { color: "#c47f00", weight: 2, fill: false } }).addTo(mapa);
      const otros = L.geoJSON(datos.poligonos, {
        filter: (f) => f.properties.tipo === "traslape",
        style: { color: "#b02a37", weight: 2, fillOpacity: 0.15 },
        onEachFeature: (f, capa) => capa.bindTooltip(f.properties.folio),
      }).addTo(mapa);
      const vigente = L.geoJSON(datos.poligonos, {
        filter: (f) => f.properties.tipo === "vigente",
        style: { color: "#1f5130", weight: 3, fillOpacity: 0.25 },
        onEachFeature: (f, capa) => capa.bindTooltip(f.properties.superficie_ha.toFixed(2) + " ha"),
      }).addTo(mapa);
      const limites = vigente.getLayers().length ? vigente.getBounds() : municipio.getBounds();
      if (otros.getLayers().length) limites.extend(otros.getBounds());
      mapa.fitBounds(limites, { padding: [30, 30] });
      div.dataset.listo = "1";
    });
})();
