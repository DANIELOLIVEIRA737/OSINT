"use strict";
const $ = (id) => document.getElementById(id);
const paths = {
  search: "m21 21-4.5-4.5 M19 10.5a8.5 8.5 0 1 1-17 0 8.5 8.5 0 0 1 17 0",
  layers: "m12 3 10 6-10 6L2 9z M2 13l10 6 10-6 M2 17l10 6 10-6",
  shield: "M12 3 3 7v6c0 5 9 9 9 9s9-4 9-9V7z m-4 9 3 3 5-6",
  globe:
    "M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0 M3 12h18 M12 3c5 5 5 13 0 18-5-5-5-13 0-18",
  scan: "M8 3H3v5 M16 3h5v5 M21 16v5h-5 M8 21H3v-5 M7 12h10 M12 7v10",
  arrow: "M5 12h14 m-5-5 5 5-5 5",
  spark: "m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z",
  lock: "M6 10h12v11H6z M8 10V6a4 4 0 0 1 8 0v4",
  network: "M9 3h6v6H9z M2 16h6v6H2z M16 16h6v6h-6z M12 9v4 M5 16v-3h14v3",
  clock: "M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0 M12 7v5l3 2",
  info: "M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0 M12 11v6 M12 7v1",
  print: "M6 9V3h12v6 M6 18H3v-9h18v9h-3 M6 14h12v8H6z",
  download: "M12 3v12 m-5-5 5 5 5-5 M4 16v5h16v-5",
  activity: "M2 12h5l3-8 4 16 3-8h5",
  filter: "M3 5h18 M6 12h12 M10 19h4",
  link: "m10 13 4-4 M8 16l-2 2a4 4 0 0 1-6-6l4-4a4 4 0 0 1 6 0 M14 8l2-2a4 4 0 0 1 6 6l-4 4a4 4 0 0 1-6 0",
  alert: "m12 3 10 18H2z M12 9v5 M12 17v1",
};
function icon(name) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "1.5");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("aria-hidden", "true");
  const p = document.createElementNS(svg.namespaceURI, "path");
  p.setAttribute("d", paths[name] || paths.info);
  svg.append(p);
  return svg;
}
document
  .querySelectorAll("[data-icon]")
  .forEach((n) => n.append(icon(n.dataset.icon)));
const modules = {
  network: { title: "Resolução de rede", group: "infra", icon: "network" },
  dns: { title: "DNS & autenticação de email", group: "infra", icon: "layers" },
  ip: { title: "Rede, operador & ASN", group: "infra", icon: "globe" },
  registration: {
    title: "Registo público · RDAP",
    group: "infra",
    icon: "layers",
  },
  reverse: { title: "DNS reverso · PTR", group: "infra", icon: "network" },
  website: {
    title: "Presença & configuração web",
    group: "web",
    icon: "globe",
  },
  tls: { title: "Certificado & confiança TLS", group: "web", icon: "shield" },
  discovery: { title: "Documentos públicos", group: "web", icon: "link" },
  transparency: {
    title: "Nomes em certificados · CT",
    group: "footprint",
    icon: "network",
  },
  archives: {
    title: "Histórico · Internet Archive",
    group: "footprint",
    icon: "clock",
  },
};
const labels = {
  addresses: "Endereços IP",
  url: "URL",
  status: "Estado",
  title: "Título da página",
  valid_from: "Válido desde",
  valid_until: "Válido até",
  names: "Nomes no certificado",
  protocol: "Protocolo",
  subject: "Titular",
  issuer: "Emissor",
  ip: "Endereço IP",
  type: "Tipo",
  country: "País",
  region: "Região",
  city: "Cidade",
  latitude: "Latitude",
  longitude: "Longitude",
  connection: "Operador e ASN",
  timezone: "Fuso horário",
  truncated: "Conteúdo limitado",
  metadata: "Metadados públicos",
  scripts: "Scripts públicos",
  redirects: "Cadeia de redirecionamentos",
  technologies: "Tecnologias observadas",
  security: "Configuração de segurança",
  checks: "Indicadores observados",
  present: "Indicadores presentes",
  total: "Total de indicadores",
  records: "Registos",
  name: "Nome",
  handle: "Identificador no registo",
  events: "Eventos do registo",
  event: "Evento",
  date: "Data",
  nameservers: "Servidores de nomes",
  entities: "Entidades do registo",
  roles: "Funções",
  organizations: "Organizações",
  start_address: "Início do bloco IP",
  end_address: "Fim do bloco IP",
  domains: "Nomes observados",
  total_discovered: "Total de nomes distintos",
  shown_limit: "Limite de nomes apresentados",
  certificate_entries: "Entradas de certificados",
  snapshots: "Páginas arquivadas",
  timestamp: "Data do arquivo (UTC, AAAAMMDDhhmmss)",
  mime: "Tipo de conteúdo",
  archive: "Consultar arquivo",
  limit: "Limite da amostra",
  documents: "Documentos",
  excerpt: "Excerto público",
  hostname: "Nome PTR",
  technology: "Tecnologia",
  evidence: "Evidência",
  asn: "ASN",
  isp: "Operador",
  org: "Organização",
  domain: "Domínio da rede",
  id: "Identificador",
  utc: "UTC",
  offset: "Desvio UTC",
  abbr: "Abreviatura",
  is_dst: "Horário de verão",
  current_time: "Hora reportada",
  error: "Falha da consulta",
  value: "Valor",
  ttl: "TTL (segundos)",
  note: "Nota",
};
const catalog = [
  ["Google Public DNS", "DNS e políticas de email", "Essencial"],
  [
    "Resolução do sistema",
    "Endereços IP e DNS reverso",
    "Essencial / aprofundada",
  ],
  [
    "Site consultado",
    "HTML, cabeçalhos, metadados e documentos públicos",
    "Essencial / aprofundada",
  ],
  ["Ligação TLS ao alvo", "Certificado validado e protocolo", "Essencial"],
  ["ipwho.is", "Operador, ASN e localização aproximada", "Essencial"],
  [
    "IANA + serviço RDAP do registo",
    "Registo de domínio ou bloco IP",
    "Aprofundada",
  ],
  ["crt.sh", "Nomes observados em certificados públicos", "Aprofundada"],
  ["Internet Archive", "Amostra de páginas históricas", "Aprofundada"],
];
let report = null,
  deep = true,
  tab = "all",
  history = [],
  timer = null;
function el(tag, text, cls) {
  const n = document.createElement(tag);
  if (text !== undefined) n.textContent = text;
  if (cls) n.className = cls;
  return n;
}
function safeLink(value) {
  try {
    const u = new URL(value);
    return (
      ["http:", "https:"].includes(u.protocol) && !u.username && !u.password
    );
  } catch {
    return false;
  }
}
function valueNode(value, depth = 0) {
  const node = el("div");
  if (value === null || value === undefined || value === "") {
    node.append(el("span", "Não disponível", "data-empty"));
    return node;
  }
  if (typeof value === "boolean") {
    node.append(
      el(
        "span",
        value ? "Observado" : "Não observado",
        "bool" + (value ? "" : " no"),
      ),
    );
    return node;
  }
  if (Array.isArray(value)) {
    if (!value.length) {
      node.append(
        el("span", "Nenhum registo devolvido nesta consulta.", "data-empty"),
      );
      return node;
    }
    const list = el("ul", undefined, "object-list");
    for (const item of value) {
      const li = el("li");
      li.append(valueNode(item, depth + 1));
      list.append(li);
    }
    node.append(list);
    return node;
  }
  if (typeof value === "object") {
    node.append(dataList(value, depth + 1));
    return node;
  }
  const text = String(value);
  if (safeLink(text)) {
    const a = el("a", text);
    a.href = text;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    node.append(a);
  } else node.textContent = text;
  return node;
}
function dataList(data, depth = 0) {
  const dl = el("dl", undefined, "data-list");
  for (const [key, value] of Object.entries(data)) {
    const row = el("div", undefined, "data-row");
    const dd = el("dd");
    if (key === "excerpt") {
      dd.append(el("pre", String(value), "pre-text"));
    } else {
      dd.append(valueNode(value, depth));
    }
    row.append(el("dt", labels[key] || key), dd);
    dl.append(row);
  }
  return dl;
}
function detail(label, value) {
  const d = el("details");
  d.append(el("summary", label));
  d.append(valueNode(value));
  return d;
}
function renderCard(name, result) {
  const meta = modules[name] || { title: name, group: "infra", icon: "info" };
  const card = el("article", undefined, "result-card");
  card.dataset.group = meta.group;
  card.dataset.name = name;
  const head = el("div", undefined, "card-heading");
  head.append(
    icon(meta.icon),
    el("h3", meta.title),
    el(
      "span",
      result.status === "ok" ? "CONCLUÍDO" : "INDISPONÍVEL",
      "state" + (result.status === "ok" ? "" : " failed"),
    ),
  );
  card.append(head);
  const content = el("div", undefined, "card-content");
  if (result.status !== "ok") {
    content.append(
      el("p", result.error, "error-detail"),
      el(
        "p",
        "Não foi possível validar esta fonte. Verifica a ligação, as permissões de rede ou os limites do fornecedor.",
        "error-help",
      ),
    );
  } else {
    const {
      source,
      note,
      headers,
      links,
      scripts,
      snapshots,
      domains,
      documents,
      records,
      ...data
    } = result.data;
    content.append(dataList(data));
    if (records) content.append(valueNode(records));
    if (domains)
      content.append(detail(`Nomes observados (${domains.length})`, domains));
    if (snapshots)
      content.append(
        detail(`Páginas arquivadas (${snapshots.length})`, snapshots),
      );
    if (documents) {
      for (const [path, document] of Object.entries(documents))
        content.append(detail(path, document));
    }
    if (headers) content.append(detail("Cabeçalhos HTTP", headers));
    if (links)
      content.append(detail(`Ligações públicas (${links.length})`, links));
    if (scripts)
      content.append(detail(`Scripts públicos (${scripts.length})`, scripts));
    if (note) content.append(el("p", note, "card-note"));
  }
  card.append(content);
  const foot = el("div", undefined, "source");
  const source = result.data?.source;
  if (source && safeLink(source)) {
    const a = el("a", source);
    a.href = source;
    a.rel = "noopener noreferrer";
    a.target = "_blank";
    foot.append(a);
  } else foot.append(el("span", source || "Consulta sem dados confirmados"));
  foot.append(
    el(
      "span",
      `${((result.duration_ms || 0) / 1000).toFixed(1)}s`,
      "source-time",
    ),
  );
  card.append(foot);
  return card;
}
function renderFindings() {
  const findings = report.summary?.findings || [];
  $("findings").replaceChildren();
  if (!findings.length) {
    $("findings").append(
      el(
        "p",
        "Nenhum ponto a rever foi produzido com os dados disponíveis. Isto não confirma que o alvo seja seguro; consulta a cobertura e as evidências abaixo.",
        "findings-empty",
      ),
    );
  }
  for (const f of findings) {
    const row = el("div", undefined, "finding");
    const text = el("div");
    text.append(
      el("strong", f.title),
      el("p", f.detail),
      el("small", "Evidência: " + (modules[f.source]?.title || f.source)),
    );
    row.append(icon("alert"), text);
    $("findings").append(row);
  }
}
function renderCoverage() {
  $("coverage").replaceChildren();
  for (const [name, result] of Object.entries(report.results)) {
    const row = el("div", undefined, "coverage-row");
    const nameNode = el("span");
    nameNode.append(
      el("i", undefined, "dot" + (result.status === "ok" ? "" : " failed")),
      el("span", modules[name]?.title || name),
    );
    row.append(
      nameNode,
      el(
        "span",
        `${result.status === "ok" ? "OK" : "Falhou"} · ${((result.duration_ms || 0) / 1000).toFixed(1)}s`,
        "coverage-time",
      ),
    );
    $("coverage").append(row);
  }
}
function render() {
  const results = report.results;
  const completed = Object.values(results).filter(
      (r) => r.status === "ok",
    ).length,
    total = Object.keys(results).length;
  $("cards").replaceChildren();
  for (const [name, result] of Object.entries(results))
    $("cards").append(renderCard(name, result));
  $("report-title").textContent = report.target;
  $("report-date").textContent =
    `${new Date(report.created_at).toLocaleString("pt-PT")} · ${report.mode === "deep" ? "Pesquisa aprofundada" : "Pesquisa essencial"} · ${((report.duration_ms || 0) / 1000).toFixed(1)}s`;
  $("metric-sources").textContent = `${completed}/${total}`;
  $("metric-status").textContent =
    completed === total
      ? "Cobertura completa dos módulos"
      : `${total - completed} módulo(s) indisponível(is)`;
  $("metric-ips").textContent =
    results.network?.status === "ok"
      ? results.network.data.addresses.length
      : "—";
  $("metric-domains").textContent =
    results.transparency?.status === "ok"
      ? results.transparency.data.total_discovered
      : "—";
  $("metric-findings").textContent = report.summary?.findings.length ?? 0;
  renderFindings();
  renderCoverage();
  $("results").hidden = false;
  $("welcome").hidden = true;
  $("message").className = "message";
  $("message").textContent = completed
    ? `Investigação concluída. ${completed} de ${total} módulos com dados; consulta as limitações de cada fonte.`
    : "As fontes ficaram indisponíveis. O relatório contém os erros de cada consulta; não há dados confirmados sobre o alvo.";
  applyFilters();
}
function applyFilters() {
  const query = $("filter").value.toLocaleLowerCase("pt-PT");
  let count = 0;
  document.querySelectorAll(".result-card").forEach((card) => {
    card.hidden = !(
      (tab === "all" || card.dataset.group === tab) &&
      card.textContent.toLocaleLowerCase("pt-PT").includes(query)
    );
    if (!card.hidden) count++;
  });
  $("no-matches").hidden = count > 0;
}
function setTab(value) {
  tab = value;
  document.querySelectorAll("[data-tab]").forEach((b) => {
    const selected = b.dataset.tab === tab;
    b.classList.toggle("selected", selected);
    b.setAttribute("aria-pressed", String(selected));
  });
  applyFilters();
}
function renderHistory() {
  $("history").replaceChildren();
  $("history-count").textContent = history.length;
  history.forEach((item, i) => {
    const button = el("button", undefined, "history-item");
    button.append(
      icon("clock"),
      el("span", item.target),
      el("small", item.mode === "deep" ? "PROF." : "ESS."),
    );
    button.title = "Abrir relatório desta sessão: " + item.target;
    button.addEventListener("click", () => {
      report = item;
      $("target").value = item.input || item.target;
      $("filter").value = "";
      setTab("all");
      render();
      $("results").scrollIntoView({ behavior: "smooth", block: "start" });
    });
    $("history").append(button);
  });
}
function setMode(value) {
  deep = value;
  for (const [id, on] of [
    ["mode-standard", !deep],
    ["mode-deep", deep],
  ]) {
    $(id).classList.toggle("selected", on);
    $(id).setAttribute("aria-pressed", String(on));
  }
  $("mode-description").textContent = deep
    ? "Até 10 módulos · fontes públicas · sem chave de API"
    : "Até 5 módulos · DNS, web, TLS e rede";
}
$("mode-standard").addEventListener("click", () => setMode(false));
$("mode-deep").addEventListener("click", () => setMode(true));
$("search").addEventListener("submit", async (e) => {
  e.preventDefault();
  const target = $("target").value.trim();
  if (!target) return;
  $("submit").disabled = true;
  $("submit-label").textContent = "A investigar";
  $("loading").hidden = false;
  $("loading-target").textContent = target;
  $("elapsed").textContent = "0s";
  $("results").hidden = true;
  $("welcome").hidden = true;
  $("message").textContent = "";
  $("mode-standard").disabled = true;
  $("mode-deep").disabled = true;
  document
    .querySelectorAll(".history-item")
    .forEach((b) => (b.disabled = true));
  const started = Date.now();
  timer = setInterval(
    () =>
      ($("elapsed").textContent =
        Math.floor((Date.now() - started) / 1000) + "s"),
    1000,
  );
  try {
    const response = await fetch("/api/investigate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target, deep }),
    });
    const data = await response.json();
    if (!response.ok)
      throw Error(data.error || "Não foi possível concluir a pesquisa.");
    report = data;
    history.unshift(report);
    history = history.slice(0, 12);
    $("filter").value = "";
    setTab("all");
    render();
    renderHistory();
  } catch (error) {
    $("message").className = "message error";
    $("message").textContent = error.message;
    if (report) {
      render();
      $("message").className = "message error";
      $("message").textContent =
        error.message + " O relatório anterior continua abaixo.";
    } else $("welcome").hidden = false;
  } finally {
    clearInterval(timer);
    $("loading").hidden = true;
    $("submit").disabled = false;
    $("submit-label").textContent = "Investigar";
    $("mode-standard").disabled = false;
    $("mode-deep").disabled = false;
    document
      .querySelectorAll(".history-item")
      .forEach((b) => (b.disabled = false));
  }
});
$("filter").addEventListener("input", applyFilters);
document
  .querySelectorAll("[data-tab]")
  .forEach((b) => b.addEventListener("click", () => setTab(b.dataset.tab)));
$("new-search").addEventListener("click", () => {
  $("target").focus();
  $("search").scrollIntoView({ behavior: "smooth", block: "center" });
});
document.addEventListener("keydown", (e) => {
  if (
    e.key === "/" &&
    !["INPUT", "TEXTAREA"].includes(document.activeElement.tagName) &&
    !$("sources-dialog").open
  ) {
    e.preventDefault();
    $("target").focus();
  }
});
$("export").addEventListener("click", () => {
  if (!report) return;
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(report, null, 2)], { type: "application/json" }),
  );
  const a = el("a");
  a.href = url;
  a.download = `atlas-${report.target.replace(/[^a-z0-9.-]/gi, "_")}-${report.created_at.slice(0, 10)}.json`;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
let printState = [];
window.addEventListener("beforeprint", () => {
  printState = [];
  document.querySelectorAll(".result-card").forEach((n) => {
    printState.push([n, "hidden", n.hidden]);
    n.hidden = false;
  });
  document.querySelectorAll("#results details").forEach((n) => {
    printState.push([n, "open", n.open]);
    n.open = true;
  });
});
window.addEventListener("afterprint", () => {
  for (const [n, key, value] of printState) n[key] = value;
  printState = [];
});
$("print").addEventListener("click", () => window.print());
for (const [name, description, mode] of catalog) {
  const row = el("div", undefined, "catalog-entry");
  const info = el("div");
  info.append(el("strong", name), el("p", description));
  row.append(info, el("span", mode));
  $("source-list").append(row);
}
$("show-sources").addEventListener("click", () =>
  $("sources-dialog").showModal(),
);
$("close-sources").addEventListener("click", () => $("sources-dialog").close());
