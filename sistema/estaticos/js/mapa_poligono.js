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

  // Vista previa del archivo elegido: el sistema lo lee (igual que al registrar) y se dibuja punteado en azul, con su
  // superficie y su ubicación. No se guarda hasta pulsar «Registrar polígono».
  const entrada = document.querySelector("#form-poligono input[name=archivo]");
  const aviso = document.getElementById("vista-previa-poligono");
  let previa = null;
  function texto(clase, html) { aviso.className = "small mb-2 alert py-1 px-2 " + clase; aviso.innerHTML = html; }
  if (entrada && aviso && div.dataset.vistaPrevia) {
    entrada.addEventListener("change", () => {
      if (previa) { mapa.removeLayer(previa); previa = null; }
      if (!entrada.files.length) { aviso.className = "small mb-2"; aviso.textContent = ""; return; }
      const datos = new FormData();
      datos.append("archivo", entrada.files[0]);
      datos.append("csrfmiddlewaretoken", document.querySelector("#form-poligono input[name=csrfmiddlewaretoken]").value);
      texto("alert-secondary", "Leyendo el archivo…");
      fetch(div.dataset.vistaPrevia, { method: "POST", body: datos, credentials: "same-origin" })
        .then((r) => r.json())
        .then((r) => {
          if (r.error) { texto("alert-danger", r.error); return; }
          previa = L.geoJSON(r.geometria, {
            style: { color: "#1d5fbf", weight: 3, dashArray: "8 5", fillOpacity: 0.15 }, pmIgnore: true,
          }).addTo(mapa);
          previa.bindTooltip("Archivo elegido: " + r.superficie_ha.toFixed(2) + " ha (sin registrar)");
          mapa.fitBounds(previa.getBounds(), { padding: [30, 30], maxZoom: 15 });
          const ubicacion = { dentro: "dentro del municipio", parcial: "parte fuera del municipio", fuera: "fuera del municipio" };
          let html = "<strong>Vista previa, aún sin registrar:</strong> " + r.superficie_ha.toFixed(2) + " ha, " +
            ubicacion[r.ubicacion] + ". " + r.tipo_cambio +
            (r.traslape_pct !== null ? " (cubre el " + r.traslape_pct.toFixed(1) + " % del polígono vigente)" : "") + ".";
          if (r.aviso) html += "<div>" + r.aviso + "</div>";
          html += "<div>Complete los datos" + (r.pide_motivo ? ", incluido el <strong>motivo del cambio</strong>," : "") +
            " y pulse «Registrar polígono».</div>";
          texto(r.ubicacion === "dentro" ? "alert-info" : "alert-warning", html);
          const motivo = document.querySelector("#form-poligono [name=motivo_cambio]");
          if (motivo) motivo.required = !!r.pide_motivo;
        })
        .catch(() => texto("alert-danger", "No se pudo leer el archivo. Intente de nuevo."));
    });
  }
})();
