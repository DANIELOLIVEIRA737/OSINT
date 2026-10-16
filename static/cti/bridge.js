(function () {
  "use strict";
  const selector = document.getElementById("cti-project"),
    status = document.getElementById("cti-save-status");
  async function api(path, body) {
    const r = await fetch(
      path,
      body
        ? {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          }
        : {},
    );
    const data = await r.json();
    if (!r.ok) throw Error(data.error || "Falha na operação.");
    return data;
  }
  async function projects() {
    try {
      const data = await api("/api/projects");
      const active = localStorage.getItem("atlas.activeProject") || "";
      data.forEach((p) => selector.append(new Option(p.name, p.id)));
      if (data.some((p) => p.id === active)) selector.value = active;
    } catch (e) {
      status.textContent = e.message;
    }
  }
  selector.addEventListener("change", () => {
    try {
      if (selector.value)
        localStorage.setItem("atlas.activeProject", selector.value);
      else localStorage.removeItem("atlas.activeProject");
    } catch {}
  });
  window.addEventListener("atlas-save-ioc", async (e) => {
    if (!selector.value) {
      status.textContent =
        "Seleciona um projeto ou cria um no Atlas antes de guardar.";
      return;
    }
    status.textContent = "A guardar evidência…";
    try {
      const report = await api("/api/cti/lookup", { indicator: e.detail.ioc });
      if (report.results.threat_intelligence.status !== "ok")
        throw Error(report.results.threat_intelligence.error);
      const saved = await api("/api/reports/save", {
        project_id: selector.value,
        report,
      });
      await api("/api/reports/annotate", {
        id: saved.saved_id,
        notes:
          "Indicador selecionado no dashboard CTI. Fonte: " +
          e.detail.sourceLabel +
          ". Os destinos IOC não foram visitados.",
        bookmarks: ["threat_intelligence"],
      });
      status.textContent =
        "Evidência guardada no projeto. Abre os relatórios no Atlas.";
    } catch (error) {
      status.textContent = "Não foi possível guardar: " + error.message;
    }
  });
  projects();
})();
