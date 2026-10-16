(function () {
  "use strict";
  var REFRESH_MS = 5 * 60 * 1000;
  var PAGE = 50;
  var els = {
    clock: document.getElementById("clock"),
    refresh: document.getElementById("refresh-btn"),
    banner: document.getElementById("error-banner"),
    q: document.getElementById("q"),
    kevN: document.getElementById("kev-n"),
    kpiKev: document.getElementById("kpi-kev"),
    kpiHosts: document.getElementById("kpi-hosts"),
    kpiCountries: document.getElementById("kpi-countries"),
    legend: document.getElementById("choro-legend"),
    uhN: document.getElementById("uh-n"),
    newsN: document.getElementById("news-n"),
    newsHint: document.getElementById("news-hint"),
    kevList: document.getElementById("kev-list"),
    uhList: document.getElementById("uh-list"),
    newsList: document.getElementById("news-list"),
    kevMore: document.getElementById("kev-more"),
    uhMore: document.getElementById("uh-more"),
    mapEl: document.getElementById("world-map"),
    mapMeta: document.getElementById("map-meta"),
    mapPins: document.getElementById("map-pins"),
    toast: document.getElementById("copy-toast"),
    countryCard: document.getElementById("country-card"),
    countryName: document.getElementById("country-name"),
    countryCc: document.getElementById("country-cc"),
    countryHosts: document.getElementById("country-hosts"),
    countryTags: document.getElementById("country-tags"),
    countryIocs: document.getElementById("country-iocs"),
    countryClear: document.getElementById("country-clear"),
    countryFilter: document.getElementById("country-filter"),
    refreshStatus: document.getElementById("refresh-status"),
    hudRefresh: document.getElementById("hud-refresh"),
    settingsBtn: document.getElementById("settings-btn"),
    settingsPanel: document.getElementById("settings-panel"),
    settingsBackdrop: document.getElementById("settings-backdrop"),
    settingsClose: document.getElementById("settings-close"),
    themeGrid: document.getElementById("theme-grid"),
    autoCountry: document.getElementById("auto-country"),
    autoStatus: document.getElementById("auto-status"),
    autoInterval: document.getElementById("auto-interval"),
    motionOrnamental: document.getElementById("motion-ornamental"),
    chipTopSelect: document.getElementById("chip-top"),
    settingsReset: document.getElementById("settings-reset"),
    countryExport: document.getElementById("country-export"),
    autoHistoryEl: document.getElementById("auto-history"),
    densityCompact: document.getElementById("density-compact"),
    kpiHostsLabel: document.getElementById("kpi-hosts-label"),
    mapTitle: document.getElementById("map-title"),
    disclaimer: document.getElementById("disclaimer"),
    mapLayers: document.getElementById("map-layers"),
    layerBadge: document.getElementById("layer-badge"),
    dsN: document.getElementById("ds-n"),
    feodoN: document.getElementById("feodo-n"),
    dsList: document.getElementById("ds-list"),
    feodoList: document.getElementById("feodo-list"),
    dsMore: document.getElementById("ds-more"),
    feodoMore: document.getElementById("feodo-more"),
    countryStat: document.querySelector(".country-stat"),
    countryKev: document.getElementById("country-kev"),
  };

  var leafletMap = null;
  var tileLayer = null;
  var choroLayer = null;
  var countryMarkers = null;
  var worldGeo = null;
  var worldWait = null;
  var mapGen = 0;
  var lastFit = "";
  var DEFAULTS = {
    theme: "night",
    autoCountry: false,
    autoInterval: 10,
    motionOrnamental: true,
    chipTop: 8,
    autoHistory: [],
    compact: false,
  };
  function chipTopN() {
    var n = Number(document.body.getAttribute("data-chip-top"));
    if (n === 6 || n === 8 || n === 12) return n;
    return 8;
  }
  var lastEnvelope = null;
  var lastKev = { ok: false, items: [] };
  var lastUh = { ok: false, items: [] };
  var lastDshield = { ok: false, items: [] };
  var lastFeodo = { ok: false, items: [] };
  var lastMap = { pins: [], withGeo: 0, note: "" };
  var lastMapDshield = { pins: [], withGeo: 0, note: "" };
  var lastMapFeodo = { pins: [], withGeo: 0, note: "" };
  var lastNews = { ok: false, items: [] };
  var kevVisible = PAGE;
  var uhVisible = PAGE;
  var dsVisible = PAGE;
  var feodoVisible = PAGE;
  var mapLayer = "urlhaus";
  var toastTimer = null;
  var motion = {
    ready: false,
    reduce: false,
    newUh: Object.create(null),
    newNews: Object.create(null),
    choroPulse: Object.create(null),
    reemphUh: Object.create(null),
    reemphNews: Object.create(null),
    reemphChoro: Object.create(null),
    seenUh: Object.create(null),
    seenNews: Object.create(null),
    pinCounts: Object.create(null),
  };
  try {
    motion.reduce = !!(
      window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    );
  } catch (e) {}
  document.body.setAttribute("data-arcs", "0");
  if (!document.body.getAttribute("data-map-layer")) {
    document.body.setAttribute("data-map-layer", "urlhaus");
  }
  mapLayer = document.body.getAttribute("data-map-layer") || "urlhaus";

  function osmTileUrl() {
    return (
      "https://" +
      ["tile", "openstreetmap", "org"].join(".") +
      "/{z}/{x}/{y}.png"
    );
  }

  function ensureMap() {
    if (leafletMap || typeof L === "undefined") return;
    leafletMap = L.map(els.mapEl, {
      worldCopyJump: true,
      minZoom: 0.5,
      zoomSnap: 0.25,
      maxZoom: 6,
      zoomControl: false,
    }).setView([20, 10], 1.5);
    L.control.zoom({ position: "bottomleft" }).addTo(leafletMap);
    els.mapEl.setAttribute("data-basemap", "vector");
    els.mapEl.classList.add("osm-dark");
    tileLayer = L.tileLayer(osmTileUrl(), {
      attribution: "&copy; OpenStreetMap contributors",
      maxZoom: 6,
      noWrap: true,
    });
    leafletMap.fitBounds(
      [
        [-55, -175],
        [80, 175],
      ],
      { padding: [20, 20], animate: false },
    );
    window.dispatchEvent(new Event("cti-map-ready"));
  }

  window.addEventListener("cti-map-control", function (event) {
    if (!leafletMap) return;
    if (event.detail === "home") {
      clearCountryFilter();
      leafletMap.fitBounds(
        [
          [-55, -175],
          [80, 175],
        ],
        { padding: [20, 20], animate: !prefersReduce() },
      );
    }
    if (event.detail === "resize")
      setTimeout(function () {
        leafletMap.invalidateSize();
      }, 60);
    if (event.detail === "tiles") {
      if (leafletMap.hasLayer(tileLayer)) {
        leafletMap.removeLayer(tileLayer);
        els.mapEl.dataset.basemap = "vector";
      } else {
        tileLayer.addTo(leafletMap);
        els.mapEl.dataset.basemap = "osm";
      }
    }
  });

  function loadWorld() {
    if (worldGeo) return Promise.resolve(worldGeo);
    if (!worldWait) {
      worldWait = fetch("/cti/vendor/world.geojson", { cache: "force-cache" })
        .then(function (r) {
          if (!r.ok) throw new Error("HTTP " + r.status);
          return r.json();
        })
        .then(function (g) {
          worldGeo = g;
          if (leafletMap && typeof L !== "undefined") {
            L.geoJSON(g, {
              interactive: false,
              style: {
                fillColor: "#262b40",
                fillOpacity: 0.85,
                color: "#626680",
                opacity: 0.65,
                weight: 0.5,
                className: "atlas-world-outline",
              },
            })
              .addTo(leafletMap)
              .bringToBack();
          }
          return g;
        })
        .catch(function (e) {
          worldWait = null;
          throw e;
        });
    }
    return worldWait;
  }

  function choroColor(t) {
    var x = Math.max(0, Math.min(1, t));
    var hue =
      currentMapLayer() === "dshield"
        ? 264
        : currentMapLayer() === "feodo"
          ? 14
          : 38;
    return "hsl(" + hue + ", 78%, " + (72 - Math.round(x * 20)) + "%)";
  }

  function fmtTime(iso) {
    try {
      return new Intl.DateTimeFormat("pt-PT", {
        dateStyle: "short",
        timeStyle: "medium",
        timeZone: "Europe/Lisbon",
      }).format(new Date(iso));
    } catch (e) {
      return iso;
    }
  }

  function fmtNewsTime(item) {
    if (item.ts) return fmtTime(new Date(item.ts).toISOString());
    return item.date || "sem hora";
  }

  function setSource(ok, dot, meta, text) {
    if (!dot || !meta) return;
    dot.className = "dot " + (ok ? "ok" : "bad");
    meta.textContent = text;
  }

  function selectedCountry(pins) {
    var q = query();
    if (!q || q.length !== 2) return "";
    var cc = q.toUpperCase();
    if (!/^[A-Z]{2}$/.test(cc)) return "";
    return pins.some(function (p) {
      return p.cc === cc;
    })
      ? cc
      : "";
  }

  function renderLegend(max) {
    var el = els.legend;
    if (!el) return;
    el.innerHTML = "";
    if (!max) {
      el.hidden = true;
      el.removeAttribute("data-max");
      return;
    }
    el.hidden = false;
    el.dataset.max = String(max);
    var steps = 5;
    var cap0 = document.createElement("span");
    cap0.className = "legend-cap";
    cap0.textContent = "1";
    el.appendChild(cap0);
    for (var i = 0; i < steps; i++) {
      var t = i / (steps - 1);
      var sw = document.createElement("span");
      sw.className = "swatch";
      sw.style.background = choroColor(t);
      var val = i === 0 ? 1 : Math.round(1 + t * (max - 1));
      sw.dataset.value = String(val);
      sw.title = String(val) + " hosts";
      el.appendChild(sw);
    }
    var cap1 = document.createElement("span");
    cap1.className = "legend-cap";
    cap1.textContent = String(max);
    el.appendChild(cap1);
  }

  function prefersReduce() {
    try {
      return !!(
        window.matchMedia &&
        window.matchMedia("(prefers-reduced-motion: reduce)").matches
      );
    } catch (e) {
      return !!motion.reduce;
    }
  }

  function bumpClass(el, cls, ms) {
    if (!el || prefersReduce()) return;
    el.classList.remove(cls);
    void el.offsetWidth;
    el.classList.add(cls);
    setTimeout(function () {
      el.classList.remove(cls);
    }, ms || 1000);
  }

  function setKpiEl(el, next, allowBump) {
    if (!el) return;
    var val = String(next);
    var prev = el.getAttribute("data-value");
    el.textContent = val;
    el.setAttribute("data-value", val);
    var canBump =
      allowBump !== false &&
      motion.ready &&
      !prefersReduce() &&
      prev !== null &&
      prev !== val;
    if (canBump) {
      bumpClass(el, "kpi-bump", 520);
      el.setAttribute("data-changed", "1");
    } else {
      el.removeAttribute("data-changed");
      el.classList.remove("kpi-bump");
    }
  }

  function setKpis(kevN, hosts, countries, opts) {
    opts = opts || {};
    setKpiEl(els.kpiKev, kevN, opts.bumpKev !== false);
    setKpiEl(els.kpiHosts, hosts, opts.bumpUh !== false);
    setKpiEl(els.kpiCountries, countries, opts.bumpUh !== false);
  }

  function itemKeyUh(item) {
    return String((item && (item.id || item.ioc)) || "");
  }

  function itemKeyNews(item) {
    return String((item && (item.url || item.title)) || "");
  }

  function seedMotion(uh, news, pins) {
    motion.seenUh = Object.create(null);
    motion.seenNews = Object.create(null);
    motion.pinCounts = Object.create(null);
    motion.newUh = Object.create(null);
    motion.newNews = Object.create(null);
    motion.choroPulse = Object.create(null);
    ((uh && uh.items) || []).forEach(function (item) {
      var k = itemKeyUh(item);
      if (k) motion.seenUh[k] = 1;
    });
    ((news && news.items) || []).forEach(function (item) {
      var k = itemKeyNews(item);
      if (k) motion.seenNews[k] = 1;
    });
    (pins || []).forEach(function (p) {
      motion.pinCounts[p.cc] = p.count;
    });
  }

  function diffMotion(nextUh, nextNews, nextPins) {
    motion.newUh = Object.create(null);
    motion.newNews = Object.create(null);
    motion.choroPulse = Object.create(null);
    (nextUh && nextUh.ok ? nextUh.items : []).forEach(function (item) {
      var k = itemKeyUh(item);
      if (!k) return;
      if (!motion.seenUh[k]) motion.newUh[k] = 1;
      motion.seenUh[k] = 1;
    });
    (nextNews && nextNews.ok ? nextNews.items : []).forEach(function (item) {
      var k = itemKeyNews(item);
      if (!k) return;
      if (!motion.seenNews[k]) motion.newNews[k] = 1;
      motion.seenNews[k] = 1;
    });
    (nextPins || []).forEach(function (p) {
      var prev = motion.pinCounts[p.cc];
      if (prev !== undefined && prev !== p.count) motion.choroPulse[p.cc] = 1;
      if (prev === undefined && motion.ready) motion.choroPulse[p.cc] = 1;
      motion.pinCounts[p.cc] = p.count;
    });
  }

  function takeNew(map, key) {
    if (!key || !map[key]) return false;
    delete map[key];
    return true;
  }

  function setRefreshing(on) {
    document.body.setAttribute("data-refreshing", on ? "1" : "0");
    if (on) {
      var n = Number(document.body.getAttribute("data-refresh-n") || "0") || 0;
      document.body.setAttribute("data-refresh-n", String(n + 1));
    }
    if (els.refreshStatus) {
      els.refreshStatus.hidden = !on;
      els.refreshStatus.setAttribute("data-state", on ? "busy" : "idle");
    }
    if (els.hudRefresh) els.hudRefresh.hidden = !on;
    if (els.refresh) els.refresh.disabled = !!on;
  }

  function ornamentalOn() {
    return document.body.getAttribute("data-motion-ornamental") !== "0";
  }

  function planReemphasis(uh, news, pins) {
    motion.reemphUh = Object.create(null);
    motion.reemphNews = Object.create(null);
    motion.reemphChoro = Object.create(null);
    document.body.setAttribute("data-reemph", "0");
    document.body.setAttribute("data-reemph-cap", String(chipTopN()));
    if (prefersReduce() || !ornamentalOn()) return;
    var uhOk = !!(uh && uh.ok);
    var newsOk = !!(news && news.ok);
    if (uhOk) {
      (uh.items || []).slice(0, 6).forEach(function (item) {
        var k = itemKeyUh(item);
        if (k && !motion.newUh[k]) motion.reemphUh[k] = 1;
      });
      (pins || []).slice(0, chipTopN()).forEach(function (p) {
        if (!motion.choroPulse[p.cc]) motion.reemphChoro[p.cc] = 1;
      });
    }
    if (newsOk) {
      (news.items || []).slice(0, 4).forEach(function (item) {
        var k = itemKeyNews(item);
        if (k && !motion.newNews[k]) motion.reemphNews[k] = 1;
      });
    }
    var any =
      Object.keys(motion.reemphUh).length ||
      Object.keys(motion.reemphNews).length ||
      Object.keys(motion.reemphChoro).length ||
      Object.keys(motion.choroPulse).length ||
      Object.keys(motion.newUh).length ||
      Object.keys(motion.newNews).length;
    document.body.setAttribute("data-reemph", any ? "1" : "0");
  }

  function markFresh(el, key, reemphMap) {
    if (!el || prefersReduce()) return false;
    if (takeNew(reemphMap, key)) {
      el.classList.add("is-fresh");
      el.setAttribute("data-motion", "fresh");
      return true;
    }
    return false;
  }

  function setBanner(messages) {
    if (!messages.length) {
      els.banner.hidden = true;
      els.banner.textContent = "";
      return;
    }
    els.banner.hidden = false;
    els.banner.textContent = messages.join(" · ");
  }

  function query() {
    return (els.q && els.q.value ? els.q.value : "").trim().toLowerCase();
  }

  function matches(item, q) {
    if (!q) return true;
    var cc = item.geo && item.geo.cc ? item.geo.cc : "";
    var hay = [
      item.ioc,
      item.id,
      item.sourceLabel,
      item.source,
      item.vendor,
      item.product,
      item.family,
      item.date,
      cc,
    ]
      .join(" ")
      .toLowerCase();
    return hay.indexOf(q) !== -1;
  }

  var regionNames = null;
  function countryName(cc) {
    try {
      if (!regionNames)
        regionNames = new Intl.DisplayNames(["pt"], { type: "region" });
      return regionNames.of(cc) || cc;
    } catch (e) {
      return cc;
    }
  }

  function currentMapLayer() {
    var layer =
      document.body.getAttribute("data-map-layer") || mapLayer || "urlhaus";
    if (layer !== "urlhaus" && layer !== "dshield" && layer !== "feodo")
      layer = "urlhaus";
    mapLayer = layer;
    return layer;
  }

  function layerBundle() {
    var layer = currentMapLayer();
    if (layer === "dshield") {
      return {
        layer: layer,
        source: lastDshield,
        map: lastMapDshield,
        title: "Scanners · país ASN",
        disclaimer:
          "Cor = scanners reportados ao DShield por país do ASN (ascountry) — ASN ≠ GPS, não ataques em directo, sem arcos.",
        kpiLabel: "Scanners ASN",
        tooltipSuffix:
          " scanner(s) DShield · país ASN (≠ GPS) — não ataques em directo",
        filterLabel: "Filtro activo · país ASN (DShield)",
        hostWord: "scanners",
        emptyNote: "Sem scanners DShield com ASN neste país.",
        moreLabel: "na lista DShield",
        kind: "dshield",
      };
    }
    if (layer === "feodo") {
      return {
        layer: layer,
        source: lastFeodo,
        map: lastMapFeodo,
        title: "C2 destino · alocação RIR",
        disclaimer:
          "Cor = IPs destino C2 (Feodo dst_ip) por país de alocação RIR — infra destino, não origem do atacante, sem arcos.",
        kpiLabel: "C2 destinos",
        tooltipSuffix:
          " C2 destino(s) Feodo neste país RIR — não origem do atacante",
        filterLabel: "Filtro activo · alocação RIR (Feodo C2)",
        hostWord: "C2 destinos",
        emptyNote: "Sem C2 Feodo com RIR neste país.",
        moreLabel: "na lista Feodo",
        kind: "feodo",
      };
    }
    return {
      layer: "urlhaus",
      source: lastUh,
      map: lastMap,
      title: "País de alocação RIR",
      disclaimer:
        "Cor = quantidade de hosts URLhaus nesse país RIR — não ataques neste segundo, sem arcos.",
      kpiLabel: "Hosts pintados",
      tooltipSuffix:
        " host(s) URLhaus neste país RIR — não são ataques em directo",
      filterLabel: "Filtro activo · alocação RIR",
      hostWord: "hosts URLhaus",
      emptyNote: "Sem hosts URLhaus RIR neste país.",
      moreLabel: "na lista URLhaus",
      kind: "uh",
    };
  }

  function activePins() {
    var b = layerBundle();
    var pins = (b.map && b.map.pins) || [];
    if (pins.length) return pins;
    return pinsFromItems(b.source && b.source.ok ? b.source.items : []).pins;
  }

  function layerBadgeText(layer) {
    if (layer === "dshield") return "Camada: DShield · ASN ≠ GPS";
    if (layer === "feodo") return "Camada: Feodo · C2 destino RIR";
    return "Camada: URLhaus · RIR";
  }

  function focusLayerRail(layer) {
    var map = {
      urlhaus: "panel-urlhaus",
      dshield: "panel-dshield",
      feodo: "panel-feodo",
    };
    var activeId = map[layer] || map.urlhaus;
    var ids = ["panel-urlhaus", "panel-dshield", "panel-feodo"];
    ids.forEach(function (id) {
      var el = document.getElementById(id);
      if (!el) return;
      el.classList.remove("is-layer-focus", "is-layer-dim");
      if (id === activeId) {
        el.classList.add("is-layer-focus");
        try {
          if (document.body.classList.contains("design-v2")) return;
          el.scrollIntoView({
            block: "nearest",
            inline: "nearest",
            behavior: "smooth",
          });
        } catch (e) {
          try {
            el.scrollIntoView(false);
          } catch (e2) {}
        }
      } else {
        el.classList.add("is-layer-dim");
      }
    });
    // News stays undimmed (not a map-layer feed panel).
  }

  function setMapLayer(layer) {
    if (layer !== "urlhaus" && layer !== "dshield" && layer !== "feodo")
      layer = "urlhaus";
    mapLayer = layer;
    document.body.setAttribute("data-map-layer", layer);
    document.body.setAttribute("data-arcs", "0");
    if (els.mapLayers) {
      Array.prototype.forEach.call(
        els.mapLayers.querySelectorAll("[data-map-layer]"),
        function (btn) {
          var on = btn.getAttribute("data-map-layer") === layer;
          btn.setAttribute("aria-selected", on ? "true" : "false");
          if (on) btn.classList.add("is-active");
          else btn.classList.remove("is-active");
        },
      );
    }
    if (els.layerBadge) els.layerBadge.textContent = layerBadgeText(layer);
    focusLayerRail(layer);
    kevVisible = PAGE;
    uhVisible = PAGE;
    dsVisible = PAGE;
    feodoVisible = PAGE;
    renderAll();
  }

  function itemsForCountry(cc) {
    if (!cc) return [];
    var b = layerBundle();
    if (!b.source || !b.source.ok) return [];
    return (b.source.items || []).filter(function (item) {
      return item.geo && item.geo.cc === cc;
    });
  }

  function topTags(items) {
    var counts = Object.create(null);
    (items || []).forEach(function (item) {
      var raw = String(item.family || "").trim();
      if (!raw) return;
      raw.split(/[,;|/]+/).forEach(function (tag) {
        tag = tag.trim().toLowerCase();
        if (!tag || tag === "none") return;
        counts[tag] = (counts[tag] || 0) + 1;
      });
    });
    return Object.keys(counts)
      .map(function (k) {
        return { tag: k, n: counts[k] };
      })
      .sort(function (a, b) {
        return b.n - a.n || a.tag.localeCompare(b.tag);
      })
      .slice(0, 5);
  }

  function renderCountryCard(sel) {
    var card = els.countryCard;
    if (!card) return;
    if (!sel) {
      card.hidden = true;
      card.setAttribute("data-open", "0");
      card.removeAttribute("data-cc");
      return;
    }
    var items = itemsForCountry(sel);
    card.hidden = false;
    card.setAttribute("data-open", "1");
    card.dataset.cc = sel;
    var bundle = layerBundle();
    if (els.countryFilter) els.countryFilter.textContent = bundle.filterLabel;
    if (els.countryName) els.countryName.textContent = countryName(sel);
    if (els.countryCc) els.countryCc.textContent = sel;
    if (els.countryHosts) els.countryHosts.textContent = String(items.length);
    if (els.countryStat) {
      var kevBit =
        bundle.layer === "urlhaus"
          ? "KEV sem geo RIR"
          : bundle.layer === "dshield"
            ? "ASN ≠ GPS"
            : "destino C2 · RIR";
      els.countryStat.innerHTML =
        '<span id="country-hosts">' +
        items.length +
        "</span> " +
        bundle.hostWord +
        ' · IOCs no recorte · <span id="country-kev">' +
        kevBit +
        "</span>";
      els.countryHosts = document.getElementById("country-hosts");
      els.countryKev = document.getElementById("country-kev");
    }
    if (els.countryTags) {
      els.countryTags.innerHTML = "";
      var tags = topTags(items);
      if (!tags.length) {
        els.countryTags.hidden = true;
      } else {
        els.countryTags.hidden = false;
        tags.forEach(function (row) {
          var s = document.createElement("span");
          s.className = "tag";
          s.dataset.tag = row.tag;
          s.dataset.n = String(row.n);
          s.textContent = row.tag + " · " + row.n;
          els.countryTags.appendChild(s);
        });
      }
    }
    if (els.countryIocs) {
      els.countryIocs.innerHTML = "";
      var shown = items.slice(0, 8);
      shown.forEach(function (item) {
        var li = document.createElement("li");
        li.dataset.ioc = item.ioc;
        var uk = itemKeyUh(item);
        if (takeNew(motion.newUh, uk)) {
          if (!prefersReduce()) {
            li.classList.add("is-new");
            li.setAttribute("data-motion", "new");
          }
        } else {
          markFresh(li, uk, motion.reemphUh);
        }
        var row = document.createElement("div");
        row.className = "ioc-row";
        var code = document.createElement("code");
        code.textContent = item.ioc;
        code.title = "Clicar para copiar o IOC";
        code.addEventListener("click", function () {
          copyIoc(item.ioc);
        });
        var copyBtn = document.createElement("button");
        copyBtn.type = "button";
        copyBtn.className = "btn btn-copy copy-ioc";
        copyBtn.textContent = "Copiar";
        copyBtn.addEventListener("click", function (ev) {
          ev.preventDefault();
          ev.stopPropagation();
          copyIoc(item.ioc);
        });
        row.appendChild(code);
        row.appendChild(copyBtn);
        li.appendChild(row);
        if (item.date) {
          var d = document.createElement("span");
          d.className = "meta";
          d.textContent = item.date;
          li.appendChild(d);
        }
        els.countryIocs.appendChild(li);
      });
      if (items.length > shown.length) {
        var more = document.createElement("li");
        more.className = "more";
        more.textContent =
          "+" + (items.length - shown.length) + " " + bundle.moreLabel;
        els.countryIocs.appendChild(more);
      }
    }
  }

  function applyCountryFilter(cc, opts) {
    if (!els.q || !cc) return;
    opts = opts || {};
    var cur = (els.q.value || "").trim().toUpperCase();
    if (opts.force) {
      els.q.value = cc;
    } else {
      els.q.value = cur === cc ? "" : cc;
    }
    kevVisible = PAGE;
    uhVisible = PAGE;
    dsVisible = PAGE;
    feodoVisible = PAGE;
    renderAll();
    if (!opts.force) {
      var applied = (els.q.value || "").trim().toUpperCase();
      if (/^[A-Z]{2}$/.test(applied)) pushAutoHistory(applied);
    }
  }

  function clearCountryFilter() {
    if (els.q) els.q.value = "";
    kevVisible = PAGE;
    uhVisible = PAGE;
    dsVisible = PAGE;
    feodoVisible = PAGE;
    renderAll();
  }

  function showToast(text) {
    if (!els.toast) return;
    els.toast.textContent = text;
    els.toast.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      els.toast.hidden = true;
    }, 1800);
  }

  function copyIoc(text) {
    var value = String(text || "");
    if (!value) return;
    function done() {
      showToast(value.slice(0, 64) + " copiado");
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(value).then(done).catch(done);
    } else {
      done();
    }
  }

  function emptyState(title, hint, fail) {
    var wrap = document.createElement("div");
    wrap.className = fail ? "fail" : "empty";
    var t = document.createElement("p");
    t.className = fail ? "fail-title" : "empty-title";
    t.textContent = title;
    var h = document.createElement("p");
    h.className = fail ? "fail-hint" : "empty-hint";
    h.textContent = hint;
    wrap.appendChild(t);
    if (hint) wrap.appendChild(h);
    return wrap;
  }

  function card(item, kind) {
    var el = document.createElement("article");
    el.className = "card";
    el.dataset.id = item.id || "";
    if (kind === "uh") {
      var uk = itemKeyUh(item);
      if (takeNew(motion.newUh, uk)) {
        if (!prefersReduce()) {
          el.classList.add("is-new");
          el.setAttribute("data-motion", "new");
        }
      } else {
        markFresh(el, uk, motion.reemphUh);
      }
    }
    el.dataset.date = item.date || "";
    if (item.geo && item.geo.cc) el.dataset.cc = item.geo.cc;
    var top = document.createElement("div");
    top.className = "card-top";
    var badge = document.createElement("span");
    badge.className = "badge " + kind;
    badge.textContent = item.sourceLabel;
    var copyBtn = document.createElement("button");
    copyBtn.type = "button";
    copyBtn.className = "btn btn-copy copy-ioc";
    copyBtn.textContent = "Copiar";
    copyBtn.addEventListener("click", function (ev) {
      ev.preventDefault();
      copyIoc(item.ioc);
    });
    top.appendChild(badge);
    top.appendChild(copyBtn);
    var id = document.createElement("p");
    id.className = "id";
    id.textContent = item.ioc;
    id.title = "Clicar para copiar o IOC";
    id.addEventListener("click", function () {
      copyIoc(item.ioc);
    });
    var meta = document.createElement("p");
    meta.className = "meta";
    var bits = [];
    if (item.vendor || item.product)
      bits.push([item.vendor, item.product].filter(Boolean).join(" / "));
    if (item.family) bits.push(item.family);
    if (item.date) bits.push(item.date);
    if (item.geo && item.geo.cc) {
      if (kind === "dshield" || item.geo.kind === "asn")
        bits.push("país ASN " + item.geo.cc);
      else bits.push("país RIR " + item.geo.cc);
    } else if (item.asnCountry) {
      bits.push("país ASN " + item.asnCountry);
    }
    if (kind === "dshield" && item.attacks)
      bits.push(item.attacks + " attacks");
    if (kind === "feodo" && item.port) bits.push("porta " + item.port);
    if (kind === "feodo" && item.status) bits.push(item.status);
    meta.textContent = bits.join(" · ") || "—";
    el.appendChild(top);
    el.appendChild(id);
    el.appendChild(meta);
    if (kind === "kev" || kind === "uh") {
      var links = document.createElement("p");
      links.className = "links";
      var a = document.createElement("a");
      a.href =
        kind === "kev"
          ? "https://nvd.nist.gov/vuln/detail/" + encodeURIComponent(item.id)
          : /^https:\/\/urlhaus\.abuse\.ch\//.test(item.detailUrl || "")
            ? item.detailUrl
            : "https://urlhaus.abuse.ch/";
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      a.textContent = kind === "kev" ? "NVD / CISA" : "Ficha URLhaus";
      links.appendChild(a);
      el.appendChild(links);
    } else if (kind === "dshield") {
      var linksDs = document.createElement("p");
      linksDs.className = "links";
      var aDs = document.createElement("a");
      aDs.href = "https://isc.sans.edu/";
      aDs.target = "_blank";
      aDs.rel = "noopener noreferrer";
      aDs.textContent = "SANS ISC";
      linksDs.appendChild(aDs);
      el.appendChild(linksDs);
    } else if (kind === "feodo") {
      var linksFe = document.createElement("p");
      linksFe.className = "links";
      var aFe = document.createElement("a");
      aFe.href = "https://feodotracker.abuse.ch/";
      aFe.target = "_blank";
      aFe.rel = "noopener noreferrer";
      aFe.textContent = "Feodo Tracker";
      linksFe.appendChild(aFe);
      el.appendChild(linksFe);
    }
    var actions = document.createElement("div");
    actions.className = "atlas-ioc-actions";
    var analyse = document.createElement("a");
    analyse.className = "btn atlas-analyse";
    analyse.textContent = "Analisar no Atlas";
    analyse.href = "/?indicator=" + encodeURIComponent(item.ioc);
    analyse.title = "Análise passiva: não visita o destino do indicador";
    actions.appendChild(analyse);
    var save = document.createElement("button");
    save.className = "btn atlas-save";
    save.type = "button";
    save.textContent = "Guardar evidência";
    save.addEventListener("click", function () {
      window.dispatchEvent(new CustomEvent("atlas-save-ioc", { detail: item }));
    });
    actions.appendChild(save);
    el.appendChild(actions);
    return el;
  }

  function newsCard(item) {
    var el = document.createElement("article");
    el.className = "news-card";
    var nk = itemKeyNews(item);
    if (takeNew(motion.newNews, nk)) {
      if (!prefersReduce()) {
        el.classList.add("is-new");
        el.setAttribute("data-motion", "new");
      }
    } else {
      markFresh(el, nk, motion.reemphNews);
    }
    var badge = document.createElement("span");
    badge.className = "badge news";
    badge.textContent = item.source;
    var title = document.createElement("p");
    title.className = "title";
    var a = document.createElement("a");
    a.href = item.url;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.textContent = item.title;
    title.appendChild(a);
    var meta = document.createElement("p");
    meta.className = "meta";
    meta.textContent = fmtNewsTime(item);
    el.appendChild(badge);
    el.appendChild(title);
    el.appendChild(meta);
    return el;
  }

  function renderList(node, source, kind, limit, countEl) {
    node.innerHTML = "";
    if (!source.ok) {
      node.appendChild(
        emptyState(
          "Fonte indisponível",
          source.error || "Não foi possível obter este feed.",
          true,
        ),
      );
      if (countEl) countEl.textContent = "—";
      return 0;
    }
    var q = query();
    var filtered = (source.items || []).filter(function (item) {
      return matches(item, q);
    });
    if (countEl) countEl.textContent = String(filtered.length);
    var countryCc = selectedCountry(activePins());
    var activeKind = layerBundle().kind;
    if (
      kind === activeKind &&
      countryCc &&
      (kind === "uh" || kind === "dshield" || kind === "feodo")
    ) {
      var note = document.createElement("div");
      note.className = "empty rail-note";
      note.id =
        kind === "uh"
          ? "uh-country-note"
          : kind === "dshield"
            ? "ds-country-note"
            : "feodo-country-note";
      var nt = document.createElement("p");
      nt.className = "empty-title";
      nt.textContent = filtered.length + " na lista · ver card";
      var nh = document.createElement("p");
      nh.className = "empty-hint";
      nh.textContent =
        "Os IOCs deste país estão no card do mapa, sem repetir aqui.";
      note.appendChild(nt);
      note.appendChild(nh);
      var anyNew = filtered.some(function (item) {
        return !!motion.newUh[itemKeyUh(item)];
      });
      var anyFresh = filtered.some(function (item) {
        return !!motion.reemphUh[itemKeyUh(item)];
      });
      if (!prefersReduce()) {
        if (anyNew) {
          note.classList.add("is-new");
          note.setAttribute("data-motion", "new");
        } else if (anyFresh) {
          note.classList.add("is-fresh");
          note.setAttribute("data-motion", "fresh");
        }
      }
      node.appendChild(note);
      return { shown: filtered.length, total: filtered.length };
    }
    if (!filtered.length) {
      if (kind === "kev" && countryCc) {
        node.appendChild(
          emptyState(
            "KEV sem geo RIR — o filtro de país não aplica a CVEs",
            "",
          ),
        );
        return 0;
      }
      node.appendChild(
        emptyState(
          q ? "Nada corresponde ao filtro" : "Sem entradas",
          q
            ? "O filtro aplica-se à lista. O mapa recorta visualmente um país se o filtro for o código ISO."
            : "A fonte respondeu, mas não há linhas para mostrar.",
        ),
      );
      return 0;
    }
    var shown = typeof limit === "number" ? filtered.slice(0, limit) : filtered;
    shown.forEach(function (item) {
      node.appendChild(card(item, kind));
    });
    return { shown: shown.length, total: filtered.length };
  }

  function renderNews() {
    if (!els.newsList) return;
    els.newsList.innerHTML = "";
    var src = lastNews || { ok: false, items: [] };
    if (!src.ok) {
      els.newsList.appendChild(
        emptyState(
          "RSS indisponível",
          src.error || "Nenhuma notícia real foi obtida.",
          true,
        ),
      );
      if (els.newsN) els.newsN.textContent = "0";
      if (els.newsHint)
        els.newsHint.textContent =
          src.error || "RSS falhou — lista vazia, nada inventado.";
      return;
    }
    var hadNew = false;
    (src.items || []).forEach(function (item) {
      var cardEl = newsCard(item);
      var m = cardEl.getAttribute("data-motion");
      if (m === "new" || m === "fresh") hadNew = true;
      els.newsList.appendChild(cardEl);
    });
    if (els.newsN) els.newsN.textContent = String((src.items || []).length);
    if (hadNew && els.newsList && !prefersReduce()) {
      try {
        els.newsList.scrollTo({ top: 0, behavior: "smooth" });
      } catch (e) {
        els.newsList.scrollTop = 0;
      }
      els.newsList.setAttribute("data-ticker", "1");
      setTimeout(function () {
        els.newsList.removeAttribute("data-ticker");
      }, 900);
    }
    var hint =
      src.window === "hour"
        ? "Última hora (timestamp do RSS)"
        : "Mais recentes do RSS (hora à vista)";
    if (src.error) hint += " · " + src.error;
    if (els.newsHint) els.newsHint.textContent = hint;
  }

  function pinsFromItems(items) {
    var byCc = Object.create(null);
    var withGeo = 0;
    var withoutGeo = 0;
    (items || []).forEach(function (item) {
      if (!item.geo || !item.geo.cc) {
        withoutGeo++;
        return;
      }
      withGeo++;
      var cc = item.geo.cc;
      if (!byCc[cc]) {
        byCc[cc] = { cc: cc, lat: item.geo.lat, lng: item.geo.lng, count: 0 };
      }
      byCc[cc].count++;
    });
    var pins = Object.keys(byCc)
      .map(function (k) {
        return byCc[k];
      })
      .sort(function (a, b) {
        return b.count - a.count;
      });
    return { pins: pins, withGeo: withGeo, withoutGeo: withoutGeo };
  }

  function paintChips(pins) {
    els.mapPins.innerHTML = "";
    var cap = chipTopN();
    els.mapPins.setAttribute("data-cap", String(cap));
    var sel = selectedCountry(pins);
    var shown = pins.slice(0, cap);
    if (
      sel &&
      !shown.some(function (p) {
        return p.cc === sel;
      })
    ) {
      var extra = null;
      pins.forEach(function (p) {
        if (p.cc === sel) extra = p;
      });
      if (extra) shown = shown.slice(0, Math.max(1, cap - 1)).concat([extra]);
    }
    shown.forEach(function (p) {
      var li = document.createElement("li");
      li.dataset.cc = p.cc;
      li.dataset.lat = String(p.lat);
      li.dataset.lng = String(p.lng);
      li.dataset.count = String(p.count);
      li.textContent = p.cc + " · " + p.count;
      if (p.cc === selectedCountry(pins)) li.className = "active";
      if (motion.choroPulse[p.cc]) {
        li.classList.add("chip-pulse");
        li.setAttribute("data-motion", "pulse");
      } else if (motion.reemphChoro[p.cc] && !prefersReduce()) {
        li.classList.add("chip-reemph");
        li.setAttribute("data-motion", "fresh");
      }
      li.tabIndex = 0;
      li.setAttribute("role", "button");
      li.title = "Filtrar por " + p.cc;
      li.addEventListener("click", function () {
        applyCountryFilter(p.cc);
      });
      li.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          applyCountryFilter(p.cc);
        }
      });
      els.mapPins.appendChild(li);
    });
    var hiddenN = pins.length - shown.length;
    if (hiddenN > 0) {
      var more = document.createElement("li");
      more.className = "chip-more";
      more.dataset.more = String(hiddenN);
      more.textContent = "+" + hiddenN;
      more.title =
        pins.length +
        " países no feed; a mostrar os de maior contagem e o seleccionado";
      els.mapPins.appendChild(more);
    }
  }

  function focusSelected(sel) {
    if (!leafletMap) return;
    if (!sel || !choroLayer) {
      if (lastFit) {
        leafletMap.fitBounds(
          [
            [-55, -175],
            [80, 175],
          ],
          { padding: [20, 20], animate: false },
        );
        lastFit = "";
      }
      els.mapEl.setAttribute("data-focus", "");
      els.mapEl.setAttribute("data-zoom", String(leafletMap.getZoom()));
      return;
    }
    var target = null;
    choroLayer.eachLayer(function (layer) {
      if (layer.feature && layer.feature.properties.cc === sel) target = layer;
    });
    if (!target || !target.getBounds) return;
    if (sel !== lastFit) {
      leafletMap.fitBounds(target.getBounds(), {
        padding: [56, 56],
        maxZoom: 5,
        animate: false,
      });
      lastFit = sel;
    }
    els.mapEl.setAttribute("data-focus", sel);
    els.mapEl.setAttribute("data-zoom", String(leafletMap.getZoom()));
  }

  function paintChoropleth(pins) {
    if (choroLayer && leafletMap) {
      leafletMap.removeLayer(choroLayer);
      choroLayer = null;
    }
    if (countryMarkers && leafletMap) {
      leafletMap.removeLayer(countryMarkers);
      countryMarkers = null;
    }
    var counts = Object.create(null);
    var max = 0;
    pins.forEach(function (p) {
      counts[p.cc] = p.count;
      if (p.count > max) max = p.count;
    });
    els.mapEl.setAttribute("data-choro", max ? String(pins.length) : "0");
    if (!worldGeo || !max || typeof L === "undefined" || !leafletMap) {
      focusSelected("");
      return;
    }
    var feats = worldGeo.features.filter(function (f) {
      return (counts[f.properties.cc] || 0) > 0;
    });
    choroLayer = L.geoJSON(
      { type: "FeatureCollection", features: feats },
      {
        interactive: true,
        style: function (feature) {
          var cc = feature.properties.cc;
          var n = counts[cc] || 0;
          var t = max ? n / max : 0;
          var sel = selectedCountry(pins);
          var dim = sel && cc !== sel;
          var on = sel && cc === sel;
          return {
            fillColor: choroColor(t),
            fillOpacity: dim ? 0.14 : 0.32 + 0.55 * t,
            color: on ? "#ffffff" : choroColor(0.2),
            weight: on ? 2.6 : 0.8,
            className:
              "choro" +
              (on ? " choro-selected" : "") +
              (dim ? " choro-dim" : ""),
          };
        },
        onEachFeature: function (feature, layer) {
          var cc = feature.properties.cc;
          var n = counts[cc] || 0;
          var sel = selectedCountry(pins);
          layer.on("click", function () {
            applyCountryFilter(cc);
          });
          layer.bindTooltip(cc + " · " + n + layerBundle().tooltipSuffix, {
            sticky: true,
          });
          layer.on("add", function () {
            var node = layer.getElement();
            if (!node) return;
            node.setAttribute("data-cc", cc);
            node.setAttribute("data-count", String(n));
            if (sel && cc === sel) node.setAttribute("data-selected", "1");
            if (sel && cc !== sel) node.setAttribute("data-dim", "1");
          });
        },
      },
    ).addTo(leafletMap);
    countryMarkers = L.layerGroup().addTo(leafletMap);
    pins.forEach(function (pin) {
      if (!Number.isFinite(pin.lat) || !Number.isFinite(pin.lng)) return;
      const label =
        pin.cc +
        " · " +
        pin.count +
        " indicador(es). Centro do país de registo, não localização do host.";
      const marker = L.circleMarker([pin.lat, pin.lng], {
        radius: Math.min(13, 5 + Math.log2(pin.count + 1)),
        color: choroColor(0.15),
        fillColor: choroColor(0.75),
        fillOpacity: 0.95,
        weight: 1.5,
        className: "country-count-marker",
      });
      marker.on("click", function () {
        applyCountryFilter(pin.cc);
      });
      marker.on("add", function () {
        const element = marker.getElement();
        if (!element) return;
        element.setAttribute("data-cc", pin.cc);
        element.setAttribute("data-count", String(pin.count));
        element.setAttribute("tabindex", "0");
        element.setAttribute("role", "button");
        element.setAttribute("aria-label", label);
        element.addEventListener("keydown", function (event) {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            applyCountryFilter(pin.cc);
          }
        });
      });
      marker.bindTooltip(label, { direction: "top" }).addTo(countryMarkers);
    });
    setTimeout(function () {
      if (!choroLayer) return;
      var sel = selectedCountry(pins);
      choroLayer.eachLayer(function (layer) {
        var node = layer.getElement();
        if (!node || !layer.feature) return;
        var cc = layer.feature.properties.cc;
        node.setAttribute("data-cc", cc);
        node.setAttribute("data-count", String(counts[cc] || 0));
        if (sel && cc === sel) node.setAttribute("data-selected", "1");
        if (sel && cc !== sel) node.setAttribute("data-dim", "1");
      });
      focusSelected(sel);
      var pulsed = [];
      var reemph = [];
      choroLayer.eachLayer(function (layer) {
        var node = layer.getElement();
        if (!node || !layer.feature) return;
        var cc = layer.feature.properties.cc;
        if (motion.choroPulse[cc]) {
          node.classList.add("choro-pulse");
          node.setAttribute("data-motion", "pulse");
          pulsed.push(cc);
          delete motion.choroPulse[cc];
          delete motion.reemphChoro[cc];
          setTimeout(function () {
            node.classList.remove("choro-pulse");
            node.removeAttribute("data-motion");
          }, 1100);
        } else if (motion.reemphChoro[cc] && !prefersReduce()) {
          node.classList.add("choro-reemph");
          node.setAttribute("data-motion", "fresh");
          reemph.push(cc);
          delete motion.reemphChoro[cc];
          setTimeout(function () {
            node.classList.remove("choro-reemph");
            if (node.getAttribute("data-motion") === "fresh")
              node.removeAttribute("data-motion");
          }, 1200);
        }
      });
      els.mapEl.setAttribute("data-pulse", pulsed.join(","));
      els.mapEl.setAttribute("data-reemph", reemph.join(","));
      setTimeout(function () {
        els.mapEl.setAttribute("data-pulse", "");
        els.mapEl.setAttribute("data-reemph", "");
      }, 1200);
    }, 0);
  }

  function renderMapFromFilter() {
    ensureMap();
    document.body.setAttribute("data-arcs", "0");
    var gen = ++mapGen;
    var bundle = layerBundle();
    var pins = activePins();
    var withGeo =
      bundle.map && typeof bundle.map.withGeo === "number"
        ? bundle.map.withGeo
        : pins.reduce(function (s, p) {
            return s + (p.count || 0);
          }, 0);
    var sel = selectedCountry(pins);
    els.mapEl.setAttribute("data-pin-count", String(pins.length));
    els.mapEl.setAttribute("data-selected", sel);
    els.mapEl.setAttribute("data-map-layer", bundle.layer);
    var kevCount = lastKev.ok
      ? lastKev.total || (lastKev.items || []).length
      : 0;
    var layerOk = !!(bundle.source && bundle.source.ok);
    setKpis(kevCount, withGeo, pins.length, {
      bumpKev: !!lastKev.ok,
      bumpUh: layerOk,
    });
    if (els.kpiHostsLabel) els.kpiHostsLabel.textContent = bundle.kpiLabel;
    if (els.mapTitle) els.mapTitle.textContent = bundle.title;
    if (els.disclaimer) els.disclaimer.textContent = bundle.disclaimer;
    renderLegend(
      pins.reduce(function (m, p) {
        return p.count > m ? p.count : m;
      }, 0),
    );
    if (els.mapMeta) {
      els.mapMeta.textContent =
        (sel ? "País seleccionado " + sel + ". " : "") +
        bundle.disclaimer +
        " " +
        withGeo +
        " · " +
        pins.length +
        " países. Sem arcos.";
    }
    paintChips(pins);
    renderCountryCard(sel);
    if (!pins.length) {
      paintChoropleth([]);
    }
    loadWorld()
      .then(function () {
        if (gen !== mapGen) return;
        paintChoropleth(pins);
      })
      .catch(function () {
        if (gen !== mapGen) return;
        els.mapEl.setAttribute("data-choro", "0");
      });
    if (leafletMap)
      setTimeout(function () {
        leafletMap.invalidateSize();
      }, 200);
  }

  function moreBtn(btn, stats) {
    if (!btn) return;
    var more = stats && stats.total > stats.shown;
    btn.hidden = !more;
    if (more)
      btn.textContent =
        "Mostrar mais (" + stats.shown + " de " + stats.total + ")";
  }

  function renderAll() {
    var kev = renderList(els.kevList, lastKev, "kev", kevVisible, els.kevN);
    var uh = renderList(els.uhList, lastUh, "uh", uhVisible, els.uhN);
    var ds = els.dsList
      ? renderList(els.dsList, lastDshield, "dshield", dsVisible, els.dsN)
      : 0;
    var fe = els.feodoList
      ? renderList(els.feodoList, lastFeodo, "feodo", feodoVisible, els.feodoN)
      : 0;
    moreBtn(els.kevMore, kev);
    moreBtn(els.uhMore, uh);
    moreBtn(els.dsMore, ds);
    moreBtn(els.feodoMore, fe);
    renderNews();
    renderMapFromFilter();
    window.dispatchEvent(
      new CustomEvent("cti-view", {
        detail: {
          ready: !!lastEnvelope,
          layer: currentMapLayer(),
          pins: activePins(),
          map: layerBundle().map,
          source: layerBundle().source,
        },
      }),
    );
  }

  window.addEventListener("cti-design-ready", function () {
    if (lastEnvelope)
      window.dispatchEvent(
        new CustomEvent("cti-data", { detail: lastEnvelope }),
      );
    renderAll();
  });

  var STORAGE_KEY = "cti.settings.v1";
  var autoTimer = null;
  var THEMES = ["night", "slate", "forest", "sand"];

  function readSettings() {
    try {
      var raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return {};
      var parsed = JSON.parse(raw);
      return parsed && typeof parsed === "object" ? parsed : {};
    } catch (e) {
      return {};
    }
  }

  function writeSettings(partial) {
    var next = Object.assign({}, readSettings(), partial);
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch (e) {}
    return next;
  }

  function applyTheme(id) {
    if (THEMES.indexOf(id) === -1) id = "night";
    document.documentElement.setAttribute("data-theme", id);
    document.body.setAttribute("data-theme", id);
    if (els.themeGrid) {
      Array.prototype.forEach.call(
        els.themeGrid.querySelectorAll("[data-theme]"),
        function (btn) {
          btn.setAttribute(
            "aria-pressed",
            btn.getAttribute("data-theme") === id ? "true" : "false",
          );
        },
      );
    }
    writeSettings({ theme: id });
  }

  function applyChipTop(n) {
    n = Number(n);
    if (n !== 6 && n !== 8 && n !== 12) n = 8;
    document.body.setAttribute("data-chip-top", String(n));
    if (els.chipTopSelect) els.chipTopSelect.value = String(n);
    writeSettings({ chipTop: n });
  }

  function applyMotionOrnamental(on) {
    document.body.setAttribute("data-motion-ornamental", on ? "1" : "0");
    if (els.motionOrnamental) els.motionOrnamental.checked = !!on;
    writeSettings({ motionOrnamental: !!on });
  }

  function applyDensityCompact(on) {
    on = !!on;
    if (on) document.body.setAttribute("data-density", "compact");
    else document.body.removeAttribute("data-density");
    if (els.densityCompact) els.densityCompact.checked = on;
    writeSettings({ compact: on });
  }

  var autoHistory = [];

  function normalizeHistory(list) {
    var out = [];
    if (!Array.isArray(list)) return out;
    list.forEach(function (cc) {
      cc = String(cc || "").toUpperCase();
      if (/^[A-Z]{2}$/.test(cc)) out.push(cc);
    });
    return out.slice(0, 8);
  }

  function renderAutoHistory() {
    if (els.autoHistoryEl) {
      els.autoHistoryEl.innerHTML = "";
      els.autoHistoryEl.setAttribute("data-count", String(autoHistory.length));
      if (!autoHistory.length) {
        els.autoHistoryEl.textContent = "—";
      } else {
        autoHistory.forEach(function (cc, i) {
          if (i) {
            var sep = document.createElement("span");
            sep.className = "hist-sep";
            sep.setAttribute("aria-hidden", "true");
            sep.textContent = " · ";
            els.autoHistoryEl.appendChild(sep);
          }
          var btn = document.createElement("button");
          btn.type = "button";
          btn.className = "hist-cc";
          btn.setAttribute("data-cc", cc);
          btn.setAttribute("aria-label", "Abrir país " + cc);
          btn.textContent = cc;
          els.autoHistoryEl.appendChild(btn);
        });
      }
    }
    document.body.setAttribute("data-auto-history", autoHistory.join(","));
  }

  function loadAutoHistory(list) {
    autoHistory = normalizeHistory(list);
    renderAutoHistory();
  }

  function clearAutoHistory() {
    autoHistory = [];
    writeSettings({ autoHistory: [] });
    renderAutoHistory();
  }

  function pushAutoHistory(cc) {
    cc = String(cc || "").toUpperCase();
    if (!/^[A-Z]{2}$/.test(cc)) return;
    if (autoHistory[0] === cc) {
      renderAutoHistory();
      return;
    }
    autoHistory = [cc].concat(autoHistory);
    if (autoHistory.length > 8) autoHistory = autoHistory.slice(0, 8);
    writeSettings({ autoHistory: autoHistory.slice() });
    renderAutoHistory();
  }

  function hostFromIoc(ioc) {
    try {
      var u = new URL(String(ioc || ""));
      return u.hostname || "";
    } catch (e) {
      return "";
    }
  }

  function csvEscape(val) {
    var s = String(val == null ? "" : val);
    if (/[",\n\r]/.test(s)) return '"' + s.replace(/"/g, '""') + '"';
    return s;
  }

  function exportCountryCsv() {
    var card = els.countryCard;
    var cc =
      card && card.getAttribute("data-open") === "1"
        ? card.getAttribute("data-cc") || ""
        : "";
    if (!cc) {
      showToast("Seleccione um país com IOCs");
      return;
    }
    var items = itemsForCountry(cc);
    if (!items.length) {
      showToast("Sem IOCs na camada activa para " + cc);
      return;
    }
    var bundle = layerBundle();
    var lines =
      bundle.layer === "dshield"
        ? ["ip,attacks,count,asn_country,firstseen,lastseen"]
        : bundle.layer === "feodo"
          ? ["dst_ip,port,status,malware,date,rir_cc"]
          : ["url,host,tags,date,urlhaus_link"];
    items.forEach(function (item) {
      if (bundle.layer === "dshield") {
        lines.push(
          [
            csvEscape(item.ioc || ""),
            csvEscape(item.attacks || ""),
            csvEscape(item.count || ""),
            csvEscape(item.asnCountry || (item.geo && item.geo.cc) || ""),
            csvEscape(item.firstseen || ""),
            csvEscape(item.lastseen || ""),
          ].join(","),
        );
      } else if (bundle.layer === "feodo") {
        lines.push(
          [
            csvEscape(item.ioc || ""),
            csvEscape(item.port || ""),
            csvEscape(item.status || ""),
            csvEscape(item.malware || item.family || ""),
            csvEscape(item.date || ""),
            csvEscape((item.geo && item.geo.cc) || ""),
          ].join(","),
        );
      } else {
        lines.push(
          [
            csvEscape(item.ioc || ""),
            csvEscape(hostFromIoc(item.ioc)),
            csvEscape(item.family || ""),
            csvEscape(item.date || ""),
            csvEscape(item.detailUrl || item.sourceUrl || ""),
          ].join(","),
        );
      }
    });
    var blob = new Blob([lines.join("\n") + "\n"], {
      type: "text/csv;charset=utf-8",
    });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url;
    a.download = "cti-" + cc + "-iocs.csv";
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(function () {
      try {
        URL.revokeObjectURL(url);
      } catch (e) {}
    }, 1500);
    document.body.setAttribute("data-export", "1");
    if (card) card.setAttribute("data-export", "1");
    setTimeout(function () {
      document.body.removeAttribute("data-export");
      if (card) card.removeAttribute("data-export");
    }, 2000);
    showToast("CSV · " + items.length + " IOCs · " + cc);
  }

  function isFormField(el) {
    if (!el) return false;
    var tag = (el.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select") return true;
    if (el.isContentEditable) return true;
    return false;
  }

  function bindHotkeys() {
    document.addEventListener("keydown", function (ev) {
      if (ev.defaultPrevented || ev.altKey || ev.ctrlKey || ev.metaKey) return;
      var key = ev.key;
      if (key === "Escape") {
        if (document.body.getAttribute("data-settings-open") === "1") {
          openSettings(false);
          ev.preventDefault();
          return;
        }
        if (
          els.countryCard &&
          els.countryCard.getAttribute("data-open") === "1"
        ) {
          clearCountryFilter();
          ev.preventDefault();
        }
        return;
      }
      if (isFormField(ev.target)) return;
      if (key === "r" || key === "R") {
        if (els.refresh && !els.refresh.disabled) {
          els.refresh.click();
          ev.preventDefault();
        }
        return;
      }
      if (key === "s" || key === "S") {
        openSettings(document.body.getAttribute("data-settings-open") !== "1");
        ev.preventDefault();
        return;
      }
      if (key === "/") {
        if (els.q) {
          els.q.focus();
          ev.preventDefault();
        }
        return;
      }
      if (key === "1") {
        setMapLayer("urlhaus");
        ev.preventDefault();
        return;
      }
      if (key === "2") {
        setMapLayer("dshield");
        ev.preventDefault();
        return;
      }
      if (key === "3") {
        setMapLayer("feodo");
        ev.preventDefault();
        return;
      }
    });
  }

  function applyAutoInterval(sec) {
    sec = Number(sec);
    if (sec !== 5 && sec !== 10 && sec !== 30) sec = 10;
    document.body.setAttribute("data-auto-interval", String(sec));
    if (els.autoInterval) els.autoInterval.value = String(sec);
    writeSettings({ autoInterval: sec });
    if (document.body.getAttribute("data-auto-country") === "1") {
      startAutoCountry();
    }
  }

  function openSettings(open) {
    if (!els.settingsPanel) return;
    els.settingsPanel.hidden = !open;
    if (els.settingsBackdrop) els.settingsBackdrop.hidden = !open;
    document.body.setAttribute("data-settings-open", open ? "1" : "0");
  }

  function autoIntervalMs() {
    var override = Number(document.body.getAttribute("data-auto-ms"));
    if (override > 0) return override;
    var sec = Number(document.body.getAttribute("data-auto-interval"));
    if (sec === 5 || sec === 10 || sec === 30) return sec * 1000;
    return 10000;
  }

  function autoIntervalLabelSec() {
    var sec = Number(document.body.getAttribute("data-auto-interval"));
    if (sec === 5 || sec === 10 || sec === 30) return sec;
    return Math.max(1, Math.round(autoIntervalMs() / 1000));
  }

  function paintedCountries() {
    return activePins().map(function (p) {
      return p.cc;
    });
  }

  function pickRandomCountry(exclude) {
    var list = paintedCountries();
    if (!list.length) return "";
    if (list.length === 1) return list[0];
    var pool = list.filter(function (cc) {
      return cc !== exclude;
    });
    if (!pool.length) pool = list;
    return pool[Math.floor(Math.random() * pool.length)];
  }

  function stopAutoCountry() {
    if (autoTimer) {
      clearInterval(autoTimer);
      autoTimer = null;
    }
    document.body.setAttribute("data-auto-country", "0");
    if (els.autoStatus) {
      els.autoStatus.textContent = paintedCountries().length
        ? "Desligado"
        : "Desligado";
    }
  }

  function tickAutoCountry() {
    var list = paintedCountries();
    if (!list.length) {
      if (els.autoStatus) {
        var ly = currentMapLayer();
        els.autoStatus.textContent =
          ly === "dshield"
            ? "Sem países ASN DShield — à espera do feed"
            : ly === "feodo"
              ? "Sem países Feodo RIR — à espera do feed"
              : "Sem países RIR com hosts — à espera do feed";
      }
      document.body.setAttribute("data-auto-empty", "1");
      return;
    }
    document.body.setAttribute("data-auto-empty", "0");
    var cur = selectedCountry(
      list.map(function (cc) {
        return { cc: cc };
      }),
    );
    var next = pickRandomCountry(cur);
    if (!next) return;
    applyCountryFilter(next, { force: true });
    document.body.setAttribute("data-auto-last", next);
    pushAutoHistory(next);
    if (els.autoStatus) {
      els.autoStatus.textContent =
        "Activo · último " + next + " · a cada " + autoIntervalLabelSec() + "s";
    }
  }

  function startAutoCountry() {
    stopAutoCountry();
    document.body.setAttribute("data-auto-country", "1");
    if (els.autoStatus)
      els.autoStatus.textContent =
        "Activo · a cada " + autoIntervalLabelSec() + "s";
    tickAutoCountry();
    autoTimer = setInterval(tickAutoCountry, autoIntervalMs());
  }

  function setAutoCountry(on) {
    writeSettings({ autoCountry: !!on });
    if (els.autoCountry) els.autoCountry.checked = !!on;
    if (on) startAutoCountry();
    else stopAutoCountry();
  }

  function resetSettings() {
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch (e) {}
    setAutoCountry(false);
    applyTheme(DEFAULTS.theme);
    applyChipTop(DEFAULTS.chipTop);
    applyMotionOrnamental(DEFAULTS.motionOrnamental);
    applyAutoInterval(DEFAULTS.autoInterval);
    applyDensityCompact(DEFAULTS.compact);
    setAutoCountry(DEFAULTS.autoCountry);
    clearAutoHistory();
    renderAll();
  }

  function initSettings() {
    var s = Object.assign({}, DEFAULTS, readSettings());
    applyTheme(s.theme);
    applyChipTop(s.chipTop);
    applyMotionOrnamental(s.motionOrnamental !== false);
    applyAutoInterval(s.autoInterval);
    applyDensityCompact(!!s.compact);
    loadAutoHistory(s.autoHistory);
    if (els.autoCountry) els.autoCountry.checked = !!s.autoCountry;
    if (s.autoCountry) startAutoCountry();
    else stopAutoCountry();

    if (els.settingsBtn) {
      els.settingsBtn.addEventListener("click", function () {
        openSettings(!!els.settingsPanel.hidden);
      });
    }
    if (els.settingsClose) {
      els.settingsClose.addEventListener("click", function () {
        openSettings(false);
      });
    }
    if (els.settingsBackdrop) {
      els.settingsBackdrop.addEventListener("click", function () {
        openSettings(false);
      });
    }
    if (els.themeGrid) {
      els.themeGrid.addEventListener("click", function (ev) {
        var btn = ev.target.closest("[data-theme]");
        if (!btn) return;
        applyTheme(btn.getAttribute("data-theme"));
      });
    }
    if (els.autoCountry) {
      els.autoCountry.addEventListener("change", function () {
        setAutoCountry(!!els.autoCountry.checked);
      });
    }
    if (els.autoInterval) {
      els.autoInterval.addEventListener("change", function () {
        applyAutoInterval(els.autoInterval.value);
      });
    }
    if (els.motionOrnamental) {
      els.motionOrnamental.addEventListener("change", function () {
        applyMotionOrnamental(!!els.motionOrnamental.checked);
      });
    }
    if (els.chipTopSelect) {
      els.chipTopSelect.addEventListener("change", function () {
        applyChipTop(els.chipTopSelect.value);
        renderAll();
      });
    }
    if (els.densityCompact) {
      els.densityCompact.addEventListener("change", function () {
        applyDensityCompact(!!els.densityCompact.checked);
      });
    }
    if (els.autoHistoryEl) {
      els.autoHistoryEl.addEventListener("click", function (ev) {
        var btn =
          ev.target && ev.target.closest
            ? ev.target.closest("button.hist-cc[data-cc]")
            : null;
        if (!btn) return;
        var cc = (btn.getAttribute("data-cc") || "").toUpperCase();
        if (/^[A-Z]{2}$/.test(cc)) applyCountryFilter(cc, { force: true });
      });
    }
    if (els.settingsReset) {
      els.settingsReset.addEventListener("click", function () {
        resetSettings();
      });
    }
    if (els.countryExport) {
      els.countryExport.addEventListener("click", function () {
        exportCountryCsv();
      });
    }
    bindHotkeys();
    document.body.setAttribute("data-hotkeys", "1");
  }

  async function load(force) {
    setRefreshing(true);
    var url = "/api/cti/feed" + (force ? "?force=1" : "");
    try {
      var res = await fetch(url, { cache: "no-store" });
      if (!res.ok) throw new Error("HTTP " + res.status);
      var data = await res.json();
      lastEnvelope = data;
      var errors = [];
      if (!data.kev || !data.kev.ok)
        errors.push((data.kev && data.kev.error) || "CISA KEV falhou.");
      if (!data.urlhaus || !data.urlhaus.ok)
        errors.push((data.urlhaus && data.urlhaus.error) || "URLhaus falhou.");
      if (!data.dshield || !data.dshield.ok)
        errors.push((data.dshield && data.dshield.error) || "DShield falhou.");
      if (!data.feodo || !data.feodo.ok)
        errors.push((data.feodo && data.feodo.error) || "Feodo falhou.");
      lastNews = data.news || { ok: false, error: "Sem RSS.", items: [] };
      if (!lastNews.ok) errors.push(lastNews.error || "RSS falhou.");

      lastKev = data.kev || { ok: false, error: "Sem dados KEV.", items: [] };
      lastUh = data.urlhaus || {
        ok: false,
        error: "Sem dados URLhaus.",
        items: [],
      };
      lastDshield = data.dshield || {
        ok: false,
        error: "Sem dados DShield.",
        items: [],
      };
      lastFeodo = data.feodo || {
        ok: false,
        error: "Sem dados Feodo.",
        items: [],
      };
      lastMap = data.map || { pins: [], withGeo: 0, note: "" };
      lastMapDshield = data.mapDshield || { pins: [], withGeo: 0, note: "" };
      lastMapFeodo = data.mapFeodo || { pins: [], withGeo: 0, note: "" };
      kevVisible = PAGE;
      uhVisible = PAGE;
      dsVisible = PAGE;
      feodoVisible = PAGE;
      var nextPins = activePins();
      if (!motion.ready) {
        seedMotion(
          lastUh.ok ? lastUh : { items: [] },
          lastNews.ok ? lastNews : { items: [] },
          nextPins,
        );
      } else {
        diffMotion(lastUh, lastNews, nextPins);
      }
      planReemphasis(lastUh, lastNews, nextPins);
      document.body.setAttribute("data-motion-ready", motion.ready ? "1" : "0");

      setSource(
        !!lastKev.ok,
        els.kevDot,
        els.kevMeta,
        lastKev.ok
          ? (lastKev.total || lastKev.items.length) +
              " no catálogo · " +
              lastKev.items.length +
              " em lista"
          : lastKev.error,
      );
      setSource(
        !!lastUh.ok,
        els.uhDot,
        els.uhMeta,
        lastUh.ok
          ? (lastUh.total || lastUh.items.length) +
              " no dump · por data · até " +
              lastUh.items.length
          : lastUh.error,
      );
      els.clock.textContent =
        "Actualizado " + fmtTime(data.fetchedAt) + " (PT) · ~5 min";
      var bannerMsgs = errors.slice();
      if (lastDshield.ok && lastDshield.enrichIncomplete) {
        var enote =
          lastDshield.enrichNote ||
          "DShield: enrich ASN incompleto. Países em falta não são inventados.";
        bannerMsgs.push(enote);
        document.body.setAttribute("data-dshield-enrich", "partial");
        // The persistent banner already explains incomplete enrichment.
      } else if (lastDshield.ok) {
        document.body.setAttribute("data-dshield-enrich", "ok");
      } else {
        document.body.setAttribute("data-dshield-enrich", "fail");
      }
      setBanner(bannerMsgs);
      document.body.setAttribute(
        "data-feed-ok",
        lastKev.ok && lastUh.ok ? "1" : "0",
      );
      renderAll();
      window.dispatchEvent(new CustomEvent("cti-data", { detail: data }));
      motion.ready = true;
      document.body.setAttribute("data-motion-ready", "1");
    } catch (e) {
      lastEnvelope = { error: e.message };
      window.dispatchEvent(
        new CustomEvent("cti-data", { detail: lastEnvelope }),
      );
      lastKev = { ok: false, error: e.message, items: [] };
      lastUh = { ok: false, error: e.message, items: [] };
      lastDshield = { ok: false, error: e.message, items: [] };
      lastFeodo = { ok: false, error: e.message, items: [] };
      lastMap = { pins: [], withGeo: 0, note: e.message };
      lastMapDshield = { pins: [], withGeo: 0, note: e.message };
      lastMapFeodo = { pins: [], withGeo: 0, note: e.message };
      lastNews = { ok: false, error: e.message, items: [] };
      setBanner(["Não foi possível falar com o fetcher local: " + e.message]);
      setSource(false, els.kevDot, els.kevMeta, "Fetcher inacessível");
      setSource(false, els.uhDot, els.uhMeta, "Fetcher inacessível");
      motion.newUh = Object.create(null);
      motion.newNews = Object.create(null);
      motion.choroPulse = Object.create(null);
      motion.reemphUh = Object.create(null);
      motion.reemphNews = Object.create(null);
      motion.reemphChoro = Object.create(null);
      document.body.setAttribute("data-feed-ok", "0");
      document.body.setAttribute("data-reemph", "0");
      document.body.setAttribute("data-dshield-enrich", "fail");
      renderAll();
    }
    setRefreshing(false);
  }

  els.refresh.addEventListener("click", function () {
    load(true);
  });
  if (els.countryClear) {
    els.countryClear.addEventListener("click", function () {
      clearCountryFilter();
    });
  }
  if (els.q) {
    els.q.addEventListener("input", function () {
      kevVisible = PAGE;
      uhVisible = PAGE;
      dsVisible = PAGE;
      feodoVisible = PAGE;
      renderAll();
    });
  }
  if (els.uhMore) {
    els.uhMore.addEventListener("click", function () {
      uhVisible += PAGE;
      renderAll();
    });
  }
  if (els.kevMore) {
    els.kevMore.addEventListener("click", function () {
      kevVisible += PAGE;
      renderAll();
    });
  }
  if (els.dsMore) {
    els.dsMore.addEventListener("click", function () {
      dsVisible += PAGE;
      renderAll();
    });
  }
  if (els.feodoMore) {
    els.feodoMore.addEventListener("click", function () {
      feodoVisible += PAGE;
      renderAll();
    });
  }
  if (els.mapLayers) {
    els.mapLayers.addEventListener("click", function (ev) {
      var btn =
        ev.target && ev.target.closest
          ? ev.target.closest("[data-map-layer]")
          : null;
      if (!btn) return;
      setMapLayer(btn.getAttribute("data-map-layer"));
    });
    setMapLayer(currentMapLayer());
  } else {
    document.body.setAttribute("data-map-layer", "urlhaus");
    document.body.setAttribute("data-arcs", "0");
  }
  initSettings();
  load(false);
  setInterval(function () {
    load(false);
  }, REFRESH_MS);
})();
