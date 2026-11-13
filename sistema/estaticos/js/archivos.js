// Campos de archivo en español con el estilo de Bootstrap (el texto del control nativo depende del idioma
// del navegador). Se aplica a la página y a lo que HTMX inserte después.
(function () {
  function mejorar(raiz) {
    raiz.querySelectorAll("input[type=file]:not([data-archivo])").forEach(function (campo) {
      campo.dataset.archivo = "1";
      const grupo = document.createElement("div");
      grupo.className = "input-group" + (campo.classList.contains("form-control-sm") ? " input-group-sm" : "");
      if (campo.style.maxWidth) grupo.style.maxWidth = campo.style.maxWidth;
      const boton = document.createElement("button");
      boton.type = "button";
      boton.className = "btn btn-outline-secondary";
      boton.textContent = "Elegir archivo";
      const nombre = document.createElement("span");
      nombre.className = "form-control text-truncate text-secondary";
      nombre.textContent = "Ningún archivo seleccionado";
      campo.parentNode.insertBefore(grupo, campo);
      grupo.append(boton, nombre, campo);
      campo.classList.add("d-none");
      boton.addEventListener("click", function () { campo.click(); });
      campo.addEventListener("change", function () {
        const archivos = Array.from(campo.files || []);
        nombre.textContent = archivos.length ? archivos.map(function (a) { return a.name; }).join(", ") : "Ningún archivo seleccionado";
        nombre.classList.toggle("text-secondary", !archivos.length);
      });
    });
  }
  if (window.htmx) {
    htmx.onLoad(mejorar);
  } else {
    document.addEventListener("DOMContentLoaded", function () { mejorar(document); });
  }
})();
