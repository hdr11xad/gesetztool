// Farbschema vor dem ersten Zeichnen setzen (sonst blitzt das helle Schema kurz auf).
// Gespeichert wird nur „hell“ oder „dunkel“, lokal im Browser, kein Cookie.
(function () {
  var d = document.documentElement;
  d.className += " js";
  try {
    var t = localStorage.getItem("nf-theme");
    if (t === "dark" || t === "light") d.setAttribute("data-theme", t);
  } catch (e) { /* Speicher gesperrt: Systemeinstellung gilt */ }
})();
