(function () {
  "use strict";
  document.body.classList.add("design-v2");
  const $ = (id) => document.getElementById(id);
  const panelIds = {
    urlhaus: "panel-urlhaus",
    dshield: "panel-dshield",
    feodo: "panel-feodo",
    kev: "panel-kev",
    news: "panel-news",
  };
  let activeFeed = "urlhaus",
    layer = "urlhaus";
  function selectFeed(feed) {
    activeFeed = feed;
    document.querySelectorAll("[data-feed-tab]").forEach((button) => {
      const on = button.dataset.feedTab === feed;
      button.classList.toggle("selected", on);
      button.setAttribute("aria-pressed", String(on));
    });
    for (const [name, id] of Object.entries(panelIds))
      $(id).classList.toggle("feed-selected", name === feed);
  }
  document.querySelectorAll("[data-feed-tab]").forEach((button) =>
    button.addEventListener("click", () => {
      const feed = button.dataset.feedTab;
      selectFeed(feed);
      if (["urlhaus", "dshield", "feodo"].includes(feed) && layer !== feed)
        document
          .querySelector('#map-layers [data-map-layer="' + feed + '"]')
          .click();
    }),
  );
  selectFeed(activeFeed);
  window.addEventListener("cti-view", (event) => {
    const d = event.detail;
    if (d.layer !== layer) {
      layer = d.layer;
      selectFeed(layer);
    }
    const map = d.map || {},
      source = d.source || {};
    $("map-empty").hidden = !d.ready || !!d.pins.length;
    $("map-empty-message").textContent = source.ok
      ? "Esta amostra não tem países confirmados. Os indicadores sem localização continuam disponíveis na lista."
      : "A fonte está indisponível. Consulta o estado das fontes; nenhum país foi inventado.";
    $("map-coverage").textContent = d.ready
      ? `${map.withGeo || 0} com país · ${map.withoutGeo || 0} sem país`
      : "A consultar as fontes…";
  });
  window.addEventListener("cti-data", (event) => {
    const data = event.detail;
    let available = 0;
    $("source-health-list").replaceChildren();
    for (const [key, label] of [
      ["kev", "CISA KEV"],
      ["urlhaus", "URLhaus"],
      ["dshield", "SANS DShield"],
      ["feodo", "Feodo Tracker"],
      ["news", "Notícias RSS"],
    ]) {
      const source = data[key] || {};
      if (source.ok) available++;
      const row = document.createElement("div");
      row.className = "health-row";
      row.title =
        source.error ||
        (source.enrichIncomplete
          ? "Dados disponíveis; enriquecimento parcial."
          : "Dados obtidos na última consulta.");
      const text = document.createElement("span");
      text.textContent = label;
      const state = document.createElement("i");
      state.className = source.ok ? "ok" : "";
      state.setAttribute("role", "img");
      state.setAttribute(
        "aria-label",
        source.ok ? "Fonte com dados" : "Fonte indisponível",
      );
      row.append(text, state);
      $("source-health-list").append(row);
    }
    $("feed-health").textContent = available + " / 5";
    $("feed-health").title =
      available + " de 5 fontes com dados; não indica atividade em direto.";
  });
  function control(action) {
    window.dispatchEvent(
      new CustomEvent("cti-map-control", { detail: action }),
    );
  }
  $("map-home").addEventListener("click", () => control("home"));
  $("map-tiles").addEventListener("click", () => {
    const on = $("map-tiles").getAttribute("aria-pressed") !== "true";
    $("map-tiles").setAttribute("aria-pressed", String(on));
    $("map-tiles").setAttribute(
      "aria-label",
      on ? "Desativar base OpenStreetMap" : "Ativar base OpenStreetMap",
    );
    control("tiles");
  });
  function expand(on) {
    const stage = document.querySelector(".map-stage");
    stage.classList.toggle("is-expanded", on);
    document.body.classList.toggle("map-expanded", on);
    $("map-expand").setAttribute("aria-pressed", String(on));
    $("map-expand").setAttribute(
      "aria-label",
      on ? "Recolher mapa" : "Expandir mapa",
    );
    control("resize");
  }
  $("map-expand").addEventListener("click", () =>
    expand($("map-expand").getAttribute("aria-pressed") !== "true"),
  );
  document.addEventListener(
    "keydown",
    (event) => {
      if (
        event.key === "Escape" &&
        $("map-expand").getAttribute("aria-pressed") === "true"
      ) {
        event.preventDefault();
        event.stopImmediatePropagation();
        expand(false);
        $("map-expand").focus();
      }
    },
    true,
  );
  // The current map header can wrap on small screens. Keep controls below it.
  const header = document.querySelector(".map-hud");
  const resize = new ResizeObserver(() => {
    const height = header.getBoundingClientRect().height;
    document
      .querySelector(".map-stage")
      .style.setProperty("--map-header-height", height + "px");
    $("map-home").parentElement.style.top = height + 12 + "px";
    control("resize");
  });
  resize.observe(header);
  $("map-layers").addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    const buttons = [...$("map-layers").querySelectorAll("button")];
    const index = buttons.indexOf(document.activeElement);
    if (index < 0) return;
    event.preventDefault();
    const next =
      event.key === "Home"
        ? 0
        : event.key === "End"
          ? buttons.length - 1
          : (index + (event.key === "ArrowRight" ? 1 : -1) + buttons.length) %
            buttons.length;
    buttons[next].focus();
    buttons[next].click();
  });
  window.dispatchEvent(new Event("cti-design-ready"));
})();
