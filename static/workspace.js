"use strict";
let projects = [],
  activeProject = "",
  projectDetail = null,
  graphScale = 1,
  graphX = 0,
  graphY = 0;
const typeLabels = {
  target: "Alvo",
  indicator: "Indicador reportado",
  domain: "Domínio",
  ip: "Endereço IP",
  asn: "ASN",
  organization: "Organização",
  certificate: "Certificado",
};
async function api(path, body) {
  const r = await fetch(
    path,
    body === undefined
      ? {}
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
  );
  const data = await r.json();
  if (!r.ok) throw Error(data.error || "Não foi possível concluir a operação.");
  return data;
}
function notify(text, error = false) {
  $("message").className = "message" + (error ? " error" : "");
  $("message").textContent = text;
}
async function action(fn) {
  try {
    await fn();
  } catch (error) {
    notify(error.message, true);
    $("project-message").textContent = error.message;
  }
}
function downloadJson(value, name) {
  const u = URL.createObjectURL(
    new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }),
  );
  const a = el("a");
  a.href = u;
  a.download = name;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(u), 1000);
}
async function loadProjects() {
  projects = await api("/api/projects");
  const previous =
    activeProject ||
    (() => {
      try {
        return localStorage.getItem("atlas.activeProject") || "";
      } catch {
        return "";
      }
    })();
  $("active-project").replaceChildren(
    new Option("Pesquisa avulsa · sem guardar", ""),
  );
  projects.forEach((p) =>
    $("active-project").append(
      new Option(`${p.name} (${p.report_count})`, p.id),
    ),
  );
  activeProject = projects.some((p) => p.id === previous) ? previous : "";
  $("active-project").value = activeProject;
  $("storage-status").textContent = activeProject
    ? "Novas pesquisas guardadas neste projeto"
    : "Avulso: só guardado se escolheres um projeto";
  renderProjectList();
}
function renderProjectList() {
  $("project-list").replaceChildren();
  if (!projects.length) {
    $("project-list").append(
      el(
        "p",
        "Ainda não há projetos. Cria um para guardar pesquisas e agendar monitorizações.",
        "panel-description",
      ),
    );
  }
  for (const p of projects) {
    const b = el(
      "button",
      undefined,
      "project-choice" + (p.id === activeProject ? " selected" : ""),
    );
    b.dataset.projectId = p.id;
    b.append(
      el("strong", p.name),
      el("span", `${p.report_count} relatório(s)`),
    );
    b.addEventListener("click", () => action(() => selectProject(p.id)));
    $("project-list").append(b);
  }
}
async function selectProject(id) {
  activeProject = id;
  try {
    if (id) localStorage.setItem("atlas.activeProject", id);
    else localStorage.removeItem("atlas.activeProject");
  } catch {}
  $("active-project").value = id;
  renderProjectList();
  $("storage-status").textContent = id
    ? "Novas pesquisas guardadas neste projeto"
    : "Pesquisa avulsa";
  if (id) {
    projectDetail = await api("/api/projects/" + id);
    renderProjectDetail();
  } else {
    $("project-detail").hidden = true;
    projectDetail = null;
  }
  if (report) renderWorkspaceReport();
}
function reportOption(r) {
  return `${new Date(r.created_at).toLocaleString("pt-PT")} · ${r.target} · ${r.mode === "deep" ? "Aprofundada" : r.mode === "company" ? "Empresa" : "Essencial"}`;
}
function renderProjectDetail() {
  const p = projectDetail;
  $("project-detail").hidden = false;
  $("project-detail-name").textContent = p.name;
  $("project-notes").value = p.notes;
  $("project-reports").replaceChildren();
  $("compare-before").replaceChildren();
  $("compare-after").replaceChildren();
  for (const r of p.reports) {
    $("compare-before").append(new Option(reportOption(r), r.id));
    $("compare-after").append(new Option(reportOption(r), r.id));
    const row = el("div", undefined, "saved-report-row");
    const info = el("div");
    info.append(
      el("strong", r.target),
      el("small", reportOption(r)),
      el("small", `${r.bookmarks.length} evidência(s) marcada(s)`),
    );
    const open = el("button", "Abrir relatório", "secondary");
    open.addEventListener("click", () =>
      action(async () => {
        report = await api("/api/reports/" + r.id);
        $("filter").value = "";
        setTab("all");
        render();
        $("projects-dialog").close();
        $("results").scrollIntoView({ behavior: "smooth" });
      }),
    );
    row.append(info, open);
    $("project-reports").append(row);
  }
  if (p.reports.length > 1) $("compare-before").selectedIndex = 1;
  $("compare-reports").disabled = p.reports.length < 2;
  $("monitor-list").replaceChildren();
  for (const m of p.monitors) {
    const row = el("div", undefined, "monitor-row");
    const info = el("div");
    info.append(
      el("strong", m.target),
      el(
        "p",
        `${m.enabled ? "Ativa" : "Pausada"} · ${m.hours}h · próxima: ${new Date(m.next_run * 1000).toLocaleString("pt-PT")}`,
      ),
      el(
        "p",
        m.last_run
          ? "Última execução: " + new Date(m.last_run).toLocaleString("pt-PT")
          : "Ainda não executada",
      ),
    );
    if (m.last_error) info.append(el("p", m.last_error, "monitor-error"));
    const buttons = el("div", undefined, "report-actions");
    const toggle = el("button", m.enabled ? "Pausar" : "Retomar", "secondary");
    toggle.addEventListener("click", () =>
      action(async () => {
        await api("/api/monitors/toggle", { id: m.id, enabled: !m.enabled });
        await selectProject(p.id);
      }),
    );
    const run = el("button", "Executar agora", "secondary");
    run.addEventListener("click", () =>
      action(async () => {
        run.disabled = true;
        run.textContent = "A pesquisar…";
        $("project-message").textContent =
          "Monitorização em curso. Mantém esta janela aberta.";
        try {
          report = await api("/api/monitors/run", { id: m.id });
          render();
          await loadProjects();
          await selectProject(p.id);
          $("project-message").textContent =
            "Pesquisa guardada. " +
            (report.comparison
              ? report.comparison.changes.length +
                " alteração(ões) comparável(is)."
              : "Primeira observação deste alvo e modo.");
        } finally {
          run.disabled = false;
          run.textContent = "Executar agora";
        }
      }),
    );
    if (m.last_report_id) {
      const view = el("button", "Abrir última pesquisa", "secondary");
      view.addEventListener("click", () =>
        action(async () => {
          report = await api("/api/reports/" + m.last_report_id);
          render();
          $("projects-dialog").close();
        }),
      );
      buttons.append(view);
    }
    buttons.append(toggle, run);
    row.append(info, buttons);
    $("monitor-list").append(row);
  }
  if (!p.monitors.length)
    $("monitor-list").append(
      el("p", "Sem monitorizações neste projeto.", "panel-description"),
    );
}
async function persistReport(value) {
  if (!activeProject) return value;
  try {
    const saved = await api("/api/reports/save", {
      project_id: activeProject,
      report: value,
    });
    await loadProjects();
    return saved;
  } catch (e) {
    value.save_error = e.message;
    return value;
  }
}
function renderWorkspaceReport() {
  const saved = !!report.saved_id;
  const p = projects.find((p) => p.id === report.project_id);
  $("saved-state").textContent = report.save_error
    ? "Não foi possível guardar: " + report.save_error
    : saved
      ? "Guardado em " + (p?.name || "projeto local")
      : "Pesquisa avulsa · não guardada";
  $("save-report").disabled = !activeProject || saved;
  $("report-notes-panel").hidden = !saved;
  $("report-notes").value = report.analyst_notes || "";
  $("bookmarked-list").replaceChildren();
  const marks = report.bookmarks || [];
  if (marks.length)
    $("bookmarked-list").append(
      el(
        "p",
        "Evidências marcadas: " +
          marks.map((k) => modules[k]?.title || k).join(" · "),
        "panel-description",
      ),
    );
  for (const card of document.querySelectorAll(".result-card")) {
    const old = card.querySelector(".pin-evidence");
    if (old) old.remove();
    const b = el(
      "button",
      marks.includes(card.dataset.name) ? "★ Guardada" : "☆ Marcar evidência",
      "secondary pin-evidence",
    );
    b.disabled = !saved;
    b.title = saved
      ? "Guardar este módulo como evidência do relatório"
      : "Guarda primeiro o relatório num projeto";
    b.addEventListener("click", () =>
      action(async () => {
        const next = new Set(report.bookmarks || []);
        next.has(card.dataset.name)
          ? next.delete(card.dataset.name)
          : next.add(card.dataset.name);
        report = await api("/api/reports/annotate", {
          id: report.saved_id,
          notes: $("report-notes").value,
          bookmarks: [...next],
        });
        renderWorkspaceReport();
      }),
    );
    card.append(b);
  }
  renderGraph();
  renderSubdomains();
  renderCompanyCandidates();
  renderComparison(report.comparison || null);
  const success = Object.values(report.results).filter(
    (r) => r.status === "ok",
  ).length;
  const notes = report.summary?.findings || [];
  $("cover-target").textContent = report.target;
  $("cover-date").textContent = new Date(report.created_at).toLocaleString(
    "pt-PT",
  );
  $("cover-project").textContent = p ? "Projeto: " + p.name : "Pesquisa avulsa";
  $("cover-summary").textContent =
    `${success} de ${Object.keys(report.results).length} módulos concluídos. ${notes.length} ponto(s) a rever. ${
      notes.length
        ? notes
            .slice(0, 5)
            .map((f) => f.title)
            .join("; ")
        : "Não foram produzidos pontos a rever com os dados disponíveis."
    } A cobertura e as limitações das fontes devem acompanhar a interpretação.`;
}
function renderSubdomains() {
  const r = report.results.subdomains;
  $("subdomain-panel").hidden = !r || r.status !== "ok";
  if (!r || r.status !== "ok") return;
  const d = r.data;
  $("subdomain-summary").textContent =
    `${d.checked}/${d.total_candidates} verificados`;
  $("subdomain-rows").replaceChildren();
  for (const h of d.hosts) {
    const row = el("tr");
    const name = el("td");
    name.append(el("strong", h.host), el("small", h.sources.join(" · ")));
    const dns = el("td");
    dns.append(
      el(
        "span",
        h.dns_state === "resolved"
          ? "Resolvido"
          : h.dns_state === "not_found"
            ? "Nome não encontrado"
            : "Não confirmado",
        "status-pill " + (h.dns_state === "resolved" ? "good" : "unknown"),
      ),
      el("small", h.addresses.join(", ") || h.error || "Sem dados"),
    );
    const http = el("td");
    http.append(
      el(
        "span",
        h.http_state === "responded"
          ? "HTTP " + h.http_status
          : "Não confirmado",
        "status-pill " + (h.http_state === "responded" ? "good" : "unknown"),
      ),
    );
    if (h.http_error) http.append(el("small", h.http_error));
    const td = el("td");
    const b = el("button", "Investigar", "secondary");
    b.addEventListener("click", () => investigateCandidate(h.host));
    td.append(b);
    row.append(name, dns, http, td);
    $("subdomain-rows").append(row);
  }
  $("unverified-list").replaceChildren(valueNode(d.unverified || []));
  $("unverified-hosts").hidden = !(d.unverified || []).length;
}
function investigateCandidate(value) {
  $("domain-search").hidden = false;
  $("company-panel").hidden = true;
  $("target").value = value;
  $("target").focus();
  $("search").scrollIntoView({ behavior: "smooth", block: "center" });
  notify("Alvo preparado. Clica em Investigar para iniciar a pesquisa.");
}
function renderCompanyCandidates() {
  const r = report.results.company;
  $("company-candidates").hidden = !r || r.status !== "ok";
  $("candidate-list").replaceChildren();
  if (!r || r.status !== "ok") return;
  for (const c of r.data.candidates) {
    const card = el("article", undefined, "company-candidate");
    card.append(
      el("span", "HIPÓTESE · CORRESPONDÊNCIA POR NOME", "candidate-label"),
      el("h3", c.name),
      el("p", c.description || "Sem descrição disponível."),
    );
    for (const url of c.websites) {
      if (!safeLink(url)) continue;
      const row = el("div", undefined, "candidate-site");
      const a = el("a", url);
      a.href = url;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      const b = el("button", "Investigar site", "secondary");
      b.addEventListener("click", () => investigateCandidate(url));
      row.append(a, b);
      card.append(row);
    }
    const a = el("a", "Ver entidade na fonte ↗");
    a.href = c.source;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    if (safeLink(c.source)) card.append(a);
    $("candidate-list").append(card);
  }
  if (!r.data.candidates.length)
    $("candidate-list").append(
      el(
        "p",
        "Não foram encontrados candidatos com site ou identificador empresarial. Isto não prova que a empresa não exista.",
        "panel-description",
      ),
    );
}
function renderComparison(data) {
  $("comparison-panel").hidden = !data;
  $("comparison-content").replaceChildren();
  if (!data) return;
  $("comparison-count").textContent = data.changes.length + " alteração(ões)";
  $("comparison-content").append(
    el(
      "p",
      `${new Date(data.before_date).toLocaleString("pt-PT")} → ${new Date(data.after_date).toLocaleString("pt-PT")}`,
      "panel-description",
    ),
    el("p", data.note, "panel-description"),
  );
  for (const change of data.changes) {
    const block = el("details", undefined, "change-row");
    block.append(
      el(
        "summary",
        change.path +
          " · " +
          ({ changed: "alterado", added: "adicionado", removed: "removido" }[
            change.type
          ] || change.type),
      ),
    );
    const cols = el("div", undefined, "change-columns");
    const before = el("div"),
      after = el("div");
    before.append(el("strong", "Antes"), valueNode(change.before));
    after.append(el("strong", "Depois"), valueNode(change.after));
    cols.append(before, after);
    block.append(cols);
    $("comparison-content").append(block);
  }
  if (!data.changes.length)
    $("comparison-content").append(
      el(
        "p",
        "Sem alterações nos dados comparáveis. Verifica também a cobertura das duas pesquisas.",
      ),
    );
  if (data.coverage.length)
    $("comparison-content").append(
      detail("Módulos não comparáveis por indisponibilidade", data.coverage),
    );
  if (data.limit_reached)
    $("comparison-content").append(
      el(
        "p",
        "Atingido o limite de 200 alterações apresentadas. Consulta os relatórios completos.",
      ),
    );
}
function svgEl(tag, attrs = {}) {
  const n = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, String(v));
  return n;
}
let graphModel = { nodes: [], edges: [] },
  graphPositions = new Map(),
  graphView;
function renderGraph() {
  graphModel = report.graph || {
    nodes: [
      { id: "target:" + report.target, type: "target", label: report.target },
    ],
    edges: [],
  };
  graphScale = 1;
  graphX = 0;
  graphY = 0;
  drawGraph();
  $("graph-note").textContent =
    graphModel.note ||
    "Não existem relações adicionais confirmadas neste relatório.";
}
function selectNode(node) {
  $("graph-detail").replaceChildren(
    el("span", typeLabels[node.type] || node.type, "candidate-label"),
    el("h3", node.label),
  );
  const edges = graphModel.edges.filter(
    (e) => e.from === node.id || e.to === node.id,
  );
  for (const edge of edges) {
    const other = graphModel.nodes.find(
      (n) => n.id === (edge.from === node.id ? edge.to : edge.from),
    );
    const block = el("div", undefined, "graph-evidence");
    block.append(
      el("strong", edge.label + " → " + (other?.label || "")),
      el("p", "Fonte: " + (modules[edge.source]?.title || edge.source)),
      el(
        "span",
        edge.confidence === "hypothesis"
          ? "Hipótese por nome"
          : "Relação observada",
        "status-pill " +
          (edge.confidence === "hypothesis" ? "unknown" : "good"),
      ),
    );
    $("graph-detail").append(block);
  }
  if (!edges.length)
    $("graph-detail").append(
      el("p", "Sem relações adicionais nesta pesquisa."),
    );
  if (["domain", "ip"].includes(node.type)) {
    const b = el("button", "Preparar pesquisa", "secondary");
    b.addEventListener("click", () => investigateCandidate(node.label));
    $("graph-detail").append(b);
  }
  document
    .querySelectorAll(".graph-node")
    .forEach((n) =>
      n.classList.toggle("selected", n.dataset.nodeId === node.id),
    );
}
function drawGraph() {
  const filter = $("graph-filter").value;
  const nodes = graphModel.nodes.filter(
    (n) => filter === "all" || n.type === filter || n.type === "target",
  );
  const ids = new Set(nodes.map((n) => n.id));
  const edges = graphModel.edges.filter(
    (e) => ids.has(e.from) && ids.has(e.to),
  );
  const groups = [
    nodes.filter((n) => n.type === "target"),
    nodes.filter((n) => n.type === "domain"),
    nodes.filter((n) => n.type === "ip"),
    nodes.filter((n) => !["target", "domain", "ip"].includes(n.type)),
  ];
  const height = Math.max(480, ...groups.map((g) => g.length * 62 + 70));
  graphPositions = new Map();
  groups.forEach((group, column) =>
    group.forEach((node, i) =>
      graphPositions.set(node.id, {
        x: 100 + column * 245,
        y: group.length === 1 ? height / 2 : 50 + i * 62,
      }),
    ),
  );
  const svg = $("relation-graph");
  svg.replaceChildren();
  svg.setAttribute("viewBox", `0 0 960 ${height}`);
  svg.setAttribute("role", "group");
  svg.setAttribute("height", height);
  graphView = svgEl("g");
  svg.append(graphView);
  for (const e of edges) {
    const a = graphPositions.get(e.from),
      b = graphPositions.get(e.to);
    const path = svgEl("path", {
      d: `M${a.x},${a.y} C${(a.x + b.x) / 2},${a.y} ${(a.x + b.x) / 2},${b.y} ${b.x},${b.y}`,
      class:
        "graph-edge" + (e.confidence === "hypothesis" ? " hypothesis" : ""),
    });
    const title = svgEl("title");
    title.textContent = e.label + " · " + e.source;
    path.append(title);
    graphView.append(path);
  }
  for (const node of nodes) {
    const pos = graphPositions.get(node.id);
    const g = svgEl("g", {
      transform: `translate(${pos.x},${pos.y})`,
      class: "graph-node type-" + node.type,
      tabindex: 0,
      role: "button",
      "aria-label": node.label + " · " + (typeLabels[node.type] || node.type),
    });
    g.dataset.nodeId = node.id;
    g.append(svgEl("circle", { r: node.type === "target" ? 21 : 13 }));
    const label = svgEl("text", {
      x: 0,
      y: node.type === "target" ? 38 : 29,
      "text-anchor": "middle",
    });
    label.textContent =
      node.label.length > 29 ? node.label.slice(0, 26) + "…" : node.label;
    const title = svgEl("title");
    title.textContent = node.label;
    g.append(label, title);
    g.addEventListener("click", () => selectNode(node));
    g.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        selectNode(node);
      }
    });
    graphView.append(g);
  }
  graphTransform();
  if (nodes[0]) selectNode(nodes[0]);
}
function graphTransform() {
  if (graphView)
    graphView.setAttribute(
      "transform",
      `translate(${graphX},${graphY}) scale(${graphScale})`,
    );
}
$("graph-filter").addEventListener("change", () => {
  graphScale = 1;
  graphX = graphY = 0;
  drawGraph();
});
$("graph-in").addEventListener("click", () => {
  graphScale = Math.min(3, graphScale + 0.2);
  graphTransform();
});
$("graph-out").addEventListener("click", () => {
  graphScale = Math.max(0.4, graphScale - 0.2);
  graphTransform();
});
$("graph-reset").addEventListener("click", () => {
  graphScale = 1;
  graphX = graphY = 0;
  graphTransform();
});
let pan = null;
$("relation-graph").addEventListener("pointerdown", (e) => {
  if (e.target.closest(".graph-node")) return;
  pan = { x: e.clientX, y: e.clientY, oldX: graphX, oldY: graphY };
  $("relation-graph").setPointerCapture(e.pointerId);
});
$("relation-graph").addEventListener("pointermove", (e) => {
  if (!pan) return;
  const ratio = 960 / $("relation-graph").getBoundingClientRect().width;
  graphX = pan.oldX + (e.clientX - pan.x) * ratio;
  graphY = pan.oldY + (e.clientY - pan.y) * ratio;
  graphTransform();
});
$("relation-graph").addEventListener("pointerup", () => (pan = null));
$("relation-graph").addEventListener("pointercancel", () => (pan = null));
$("active-project").addEventListener("change", () =>
  action(() => selectProject($("active-project").value)),
);
function openProjects() {
  action(async () => {
    await loadProjects();
    if (activeProject) await selectProject(activeProject);
    $("projects-dialog").showModal();
  });
}
$("show-projects").addEventListener("click", openProjects);
$("quick-project").addEventListener("click", () => {
  openProjects();
  setTimeout(() => $("project-name").focus(), 100);
});
$("close-projects").addEventListener("click", () =>
  $("projects-dialog").close(),
);
$("project-create").addEventListener("submit", (e) => {
  e.preventDefault();
  action(async () => {
    const p = await api("/api/projects", { name: $("project-name").value });
    activeProject = p.id;
    $("project-name").value = "";
    await loadProjects();
    await selectProject(p.id);
    $("project-message").textContent =
      "Projeto criado. As próximas pesquisas ficam guardadas neste projeto.";
  });
});
$("save-project-notes").addEventListener("click", () =>
  action(async () => {
    await api("/api/projects/edit", {
      id: activeProject,
      notes: $("project-notes").value,
    });
    $("project-message").textContent = "Notas do projeto guardadas.";
  }),
);
$("project-delete").addEventListener("click", () =>
  action(async () => {
    if (
      !confirm(
        "Eliminar este projeto, relatórios, notas e monitorizações? Esta ação não pode ser desfeita.",
      )
    )
      return;
    await api("/api/projects/delete", { id: activeProject });
    activeProject = "";
    projectDetail = null;
    $("project-detail").hidden = true;
    if (report?.saved_id) {
      report.saved_id = null;
      report.project_id = null;
      renderWorkspaceReport();
    }
    await loadProjects();
    $("project-message").textContent = "Projeto eliminado.";
  }),
);
$("project-backup").addEventListener("click", () =>
  action(async () =>
    downloadJson(
      await api("/api/projects/" + activeProject + "/export"),
      "atlas-projeto-" + activeProject + ".json",
    ),
  ),
);
$("save-report").addEventListener("click", () =>
  action(async () => {
    if (!report || !activeProject) return;
    report = await api("/api/reports/save", {
      project_id: activeProject,
      report,
    });
    await loadProjects();
    renderWorkspaceReport();
    notify("Relatório guardado no projeto.");
  }),
);
$("save-notes").addEventListener("click", () =>
  action(async () => {
    report = await api("/api/reports/annotate", {
      id: report.saved_id,
      notes: $("report-notes").value,
      bookmarks: report.bookmarks || [],
    });
    renderWorkspaceReport();
    notify("Notas do relatório guardadas.");
  }),
);
$("monitor-create").addEventListener("submit", (e) => {
  e.preventDefault();
  action(async () => {
    await api("/api/monitors", {
      project_id: activeProject,
      target: $("monitor-target").value,
      deep: true,
      hours: Number($("monitor-hours").value),
    });
    await selectProject(activeProject);
    $("project-message").textContent =
      "Monitorização criada. Executa enquanto o Atlas estiver aberto.";
  });
});
$("compare-reports").addEventListener("click", () =>
  action(async () => {
    const before = $("compare-before").value,
      after = $("compare-after").value;
    if (before === after) throw Error("Escolhe dois relatórios diferentes.");
    const comparison = await api(
      "/api/compare?before=" +
        encodeURIComponent(before) +
        "&after=" +
        encodeURIComponent(after),
    );
    report = await api("/api/reports/" + after);
    report.comparison = comparison;
    render();
    $("projects-dialog").close();
    $("comparison-panel").scrollIntoView({ behavior: "smooth" });
  }),
);
$("show-company").addEventListener("click", () => {
  $("company-panel").hidden = false;
  $("domain-search").hidden = true;
  $("company-query").focus();
  $("company-panel").scrollIntoView({ behavior: "smooth" });
});
$("close-company").addEventListener("click", () => {
  $("company-panel").hidden = true;
  $("domain-search").hidden = false;
  $("target").focus();
});
$("company-search").addEventListener("submit", (e) => {
  e.preventDefault();
  action(async () => {
    $("company-submit").disabled = true;
    $("company-submit").textContent = "A cruzar fontes…";
    try {
      const data = await api("/api/company", {
        query: $("company-query").value,
      });
      report = await persistReport(data);
      history.unshift(report);
      history = history.slice(0, 12);
      $("filter").value = "";
      setTab("all");
      render();
      renderHistory();
    } finally {
      $("company-submit").disabled = false;
      $("company-submit").textContent = "Pesquisar empresa";
    }
  });
});
loadProjects().catch((error) => {
  $("storage-status").textContent =
    "Armazenamento indisponível: " + error.message;
});

let graphPrintState = null;
window.addEventListener("beforeprint", () => {
  if (!report) return;
  $("print-notes").textContent = $("report-notes").value;
  graphPrintState = {
    filter: $("graph-filter").value,
    scale: graphScale,
    x: graphX,
    y: graphY,
  };
  $("graph-filter").value = "all";
  graphScale = 1;
  graphX = graphY = 0;
  drawGraph();
});
window.addEventListener("afterprint", () => {
  if (!graphPrintState) return;
  $("graph-filter").value = graphPrintState.filter;
  drawGraph();
  graphScale = graphPrintState.scale;
  graphX = graphPrintState.x;
  graphY = graphPrintState.y;
  graphTransform();
  graphPrintState = null;
});

$("refresh-projects").addEventListener("click", () =>
  action(async () => {
    await loadProjects();
    if (activeProject) await selectProject(activeProject);
    $("project-message").textContent =
      "Relatórios e estados de monitorização atualizados.";
  }),
);
setInterval(async () => {
  if (document.hidden || !activeProject) return;
  try {
    const latest = await api("/api/projects");
    const old = projects.find((p) => p.id === activeProject),
      current = latest.find((p) => p.id === activeProject);
    if (old && current && current.report_count > old.report_count) {
      projects = latest;
      renderProjectList();
      notify(
        "Há novos relatórios no projeto. Abre Projetos & monitorização e clica em Atualizar para consultar as alterações.",
      );
    }
  } catch {
    /* Existing reports remain usable while the local server restarts. */
  }
}, 30000);

const incomingIndicator = new URLSearchParams(location.search).get("indicator");
if (incomingIndicator) {
  (async () => {
    try {
      await loadProjects();
      notify(
        "A comparar o indicador com fontes CTI. O destino não será visitado.",
      );
      report = await persistReport(
        await api("/api/cti/lookup", { indicator: incomingIndicator }),
      );
      $("target").value = report.target;
      render();
      history.unshift(report);
      renderHistory();
      window.history.replaceState({}, "", location.pathname);
    } catch (error) {
      notify(error.message, true);
    }
  })();
}
