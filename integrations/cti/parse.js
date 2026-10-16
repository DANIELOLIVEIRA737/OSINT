"use strict";

var KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json";
var URLHAUS_CSV_URL = "https://urlhaus.abuse.ch/downloads/csv_recent/";
var DSHIELD_SOURCES_URL = "https://isc.sans.edu/api/sources/attacks/40?json";
var DSHIELD_IP_URL = "https://isc.sans.edu/api/ip/";
var FEODO_CSV_URL = "https://feodotracker.abuse.ch/downloads/ipblocklist.csv";
var CISA_CATALOG = "https://www.cisa.gov/known-exploited-vulnerabilities-catalog";
var KEV_LIMIT = 300;
var URLHAUS_LIMIT = 300;
var DSHIELD_LIMIT = 40;
var FEODO_LIMIT = 300;
var DSHIELD_CONCURRENCY = 5;
var geo = require("./geo.js");

function parseCsvLine(line) {
  var out = [];
  var cur = "";
  var inQuotes = false;
  for (var i = 0; i < line.length; i++) {
    var ch = line[i];
    if (inQuotes) {
      if (ch === '"') {
        if (line[i + 1] === '"') {
          cur += '"';
          i++;
        } else {
          inQuotes = false;
        }
      } else {
        cur += ch;
      }
    } else if (ch === '"') {
      inQuotes = true;
    } else if (ch === ",") {
      out.push(cur);
      cur = "";
    } else {
      cur += ch;
    }
  }
  out.push(cur);
  return out;
}

function parseKev(payload) {
  var data = typeof payload === "string" ? JSON.parse(payload) : payload;
  if (!data || !Array.isArray(data.vulnerabilities)) {
    throw new Error("KEV: resposta sem lista de vulnerabilidades.");
  }
  var items = data.vulnerabilities
    .filter(function (v) {
      return v && v.cveID;
    })
    .map(function (v) {
      var cve = String(v.cveID);
      return {
        source: "kev",
        sourceLabel: "CISA KEV",
        id: cve,
        vendor: String(v.vendorProject || "").trim(),
        product: String(v.product || "").trim(),
        family: "",
        date: String(v.dateAdded || ""),
        ioc: cve,
        sourceUrl: CISA_CATALOG,
        detailUrl: "https://nvd.nist.gov/vuln/detail/" + encodeURIComponent(cve),
      };
    });
  items.sort(function (a, b) {
    return String(b.date).localeCompare(String(a.date));
  });
  return {
    catalogVersion: data.catalogVersion || "",
    dateReleased: data.dateReleased || "",
    total: items.length,
    items: items.slice(0, KEV_LIMIT),
  };
}

function parseUrlhausCsv(text) {
  if (typeof text !== "string") throw new Error("URLhaus: esperado texto CSV.");
  var lines = text.split(/\r?\n/);
  var rows = [];
  for (var i = 0; i < lines.length; i++) {
    var line = lines[i].trim();
    if (!line || line.charAt(0) === "#") continue;
    var cols = parseCsvLine(line);
    if (cols.length < 8) continue;
    if (cols[0] === "id") continue;
    var tags = cols[6] && cols[6] !== "None" ? cols[6] : "";
    rows.push({
      source: "urlhaus",
      sourceLabel: "URLhaus",
      id: cols[0],
      vendor: "",
      product: "",
      family: tags,
      date: cols[1],
      ioc: cols[2],
      status: cols[3],
      sourceUrl: cols[7] || "https://urlhaus.abuse.ch/",
      detailUrl: cols[7] || "https://urlhaus.abuse.ch/",
    });
  }
  if (!rows.length && text.indexOf("id,dateadded,url") === -1 && text.indexOf("#") === -1) {
    throw new Error("URLhaus: CSV sem linhas reconhecíveis.");
  }
  rows.sort(function (a, b) {
    return String(b.date).localeCompare(String(a.date));
  });
  return { total: rows.length, items: rows.slice(0, URLHAUS_LIMIT) };
}

function parseDshieldSources(payload) {
  var data = typeof payload === "string" ? JSON.parse(payload) : payload;
  if (!Array.isArray(data)) {
    throw new Error("DShield: esperado array de sources.");
  }
  var items = [];
  for (var i = 0; i < data.length; i++) {
    var row = data[i];
    if (!row || !row.ip) continue;
    var ip = String(row.ip).trim();
    if (!ip) continue;
    items.push({
      source: "dshield",
      sourceLabel: "SANS DShield",
      id: ip,
      ioc: ip,
      vendor: "",
      product: "",
      family: "",
      attacks: Number(row.attacks) || 0,
      count: Number(row.count) || 0,
      firstseen: String(row.firstseen || ""),
      lastseen: String(row.lastseen || ""),
      date: String(row.lastseen || row.firstseen || ""),
      asnCountry: null,
      geo: null,
      sourceUrl: "https://isc.sans.edu/",
      detailUrl: "https://isc.sans.edu/ipinfo.html?ip=" + encodeURIComponent(ip),
    });
  }
  items.sort(function (a, b) {
    return (b.attacks || 0) - (a.attacks || 0);
  });
  return { total: items.length, items: items.slice(0, DSHIELD_LIMIT) };
}

function applyDshieldEnrichment(item, enrichPayload) {
  var data = typeof enrichPayload === "string" ? JSON.parse(enrichPayload) : enrichPayload;
  var ipBlock = data && data.ip ? data.ip : data;
  if (!ipBlock || typeof ipBlock !== "object") return item;
  var cc = ipBlock.ascountry != null ? String(ipBlock.ascountry).trim().toUpperCase() : "";
  if (cc.length === 2 && /^[A-Z]{2}$/.test(cc)) {
    item.asnCountry = cc;
    var c = geo.CENTROIDS[cc];
    if (c) {
      item.geo = { cc: cc, lat: c[0], lng: c[1], kind: "asn", ip: item.ioc };
    } else {
      item.geo = { cc: cc, kind: "asn", ip: item.ioc };
    }
  } else {
    item.asnCountry = null;
    item.geo = null;
  }
  if (ipBlock.asname) item.asname = String(ipBlock.asname);
  if (ipBlock.as != null) item.asn = ipBlock.as;
  return item;
}

function parseFeodoCsv(text) {
  if (typeof text !== "string") throw new Error("Feodo: esperado texto CSV.");
  var lines = text.split(/\r?\n/);
  var rows = [];
  for (var i = 0; i < lines.length; i++) {
    var line = lines[i].trim();
    if (!line || line.charAt(0) === "#") continue;
    var cols = parseCsvLine(line);
    if (cols.length < 6) continue;
    if (cols[0] === "first_seen_utc" || cols[0].indexOf("first_seen") === 0) continue;
    var dstIp = String(cols[1] || "").trim();
    if (!dstIp) continue;
    rows.push({
      source: "feodo",
      sourceLabel: "Feodo Tracker",
      id: dstIp + ":" + String(cols[2] || ""),
      ioc: dstIp,
      port: String(cols[2] || ""),
      status: String(cols[3] || ""),
      malware: String(cols[5] || ""),
      family: String(cols[5] || ""),
      date: String(cols[0] || ""),
      lastOnline: String(cols[4] || ""),
      vendor: "",
      product: "",
      geo: null,
      sourceUrl: "https://feodotracker.abuse.ch/",
      detailUrl: "https://feodotracker.abuse.ch/",
    });
  }
  if (!rows.length && text.indexOf("dst_ip") === -1 && text.indexOf("#") === -1) {
    throw new Error("Feodo: CSV sem linhas reconhecíveis.");
  }
  rows.sort(function (a, b) {
    return String(b.date).localeCompare(String(a.date));
  });
  return { total: rows.length, items: rows.slice(0, FEODO_LIMIT) };
}

function emptySource(error) {
  return { ok: false, error: error || "Falha a obter o feed.", total: 0, items: [] };
}

function buildAsnMap(items, note) {
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
      var lat = item.geo.lat;
      var lng = item.geo.lng;
      if ((lat == null || lng == null) && geo.CENTROIDS[cc]) {
        lat = geo.CENTROIDS[cc][0];
        lng = geo.CENTROIDS[cc][1];
      }
      byCc[cc] = { cc: cc, lat: lat, lng: lng, count: 0, kind: "asn" };
    }
    byCc[cc].count++;
  });
  var pins = Object.keys(byCc)
    .map(function (k) { return byCc[k]; })
    .sort(function (a, b) { return b.count - a.count; });
  return {
    pins: pins,
    withGeo: withGeo,
    withoutGeo: withoutGeo,
    skippedNoIp: 0,
    note: note || "País = ASN ascountry (registo do ASN), não GPS nem ataques em directo.",
  };
}

function sleep(ms) {
  return new Promise(function (resolve) { setTimeout(resolve, ms); });
}

async function enrichDshieldItems(items, fetchDshieldIp) {
  var enrich = {
    attempted: (items || []).length,
    fetched: 0,
    withAsn: 0,
    withoutAsn: 0,
    failed: 0,
    skipped: 0,
    stopped429: false,
    incomplete: false,
  };
  if (!fetchDshieldIp || !items.length) {
    enrich.skipped = items.length;
    enrich.withoutAsn = items.length;
    enrich.incomplete = !!items.length && !fetchDshieldIp;
    return { items: items, enrich: enrich };
  }
  var idx = 0;
  var stopped = false;
  async function worker() {
    while (true) {
      if (stopped) return;
      var i = idx++;
      if (i >= items.length) return;
      if (stopped) {
        enrich.skipped++;
        return;
      }
      var item = items[i];
      try {
        var raw = await fetchDshieldIp(item.ioc);
        enrich.fetched++;
        applyDshieldEnrichment(item, raw);
      } catch (e) {
        var msg = e && e.message ? e.message : String(e);
        if (/\b429\b/.test(msg) || (e && e.status === 429)) {
          enrich.stopped429 = true;
          enrich.skipped++;
          stopped = true;
          await sleep(800);
          return;
        }
        enrich.failed++;
        item.asnCountry = null;
        item.geo = null;
      }
    }
  }
  var n = Math.min(DSHIELD_CONCURRENCY, items.length);
  var workers = [];
  for (var w = 0; w < n; w++) workers.push(worker());
  await Promise.all(workers);
  // IPs never claimed after 429 stop
  for (var j = 0; j < items.length; j++) {
    if (items[j].geo && items[j].geo.cc) enrich.withAsn++;
    else if (items[j].asnCountry === null || !items[j].geo) {
      // count without after loop below
    }
  }
  enrich.withAsn = 0;
  enrich.withoutAsn = 0;
  for (var k = 0; k < items.length; k++) {
    if (items[k].geo && items[k].geo.cc) enrich.withAsn++;
    else enrich.withoutAsn++;
  }
  // skipped = attempted - fetched - failed (approx remaining untried)
  var accounted = enrich.fetched + enrich.failed;
  if (enrich.stopped429 && accounted < enrich.attempted) {
    enrich.skipped = enrich.attempted - accounted;
  }
  enrich.incomplete = !!(enrich.stopped429 || enrich.failed > 0 || enrich.skipped > 0);
  return { items: items, enrich: enrich };
}

async function loadFeeds(io) {
  io = io || {};
  var fetchKev = io.fetchKev;
  var fetchUrlhaus = io.fetchUrlhaus;
  var fetchDshieldSources = io.fetchDshieldSources;
  var fetchDshieldIp = io.fetchDshieldIp;
  var fetchFeodo = io.fetchFeodo;
  var kev = emptySource("KEV não foi pedido.");
  var urlhaus = emptySource("URLhaus não foi pedido.");
  var dshield = { ok: true, error: null, total: 0, items: [] };
  var feodo = { ok: true, error: null, total: 0, items: [] };

  async function loadKev() {
    if (typeof fetchKev !== "function") return emptySource("KEV não foi pedido.");
    try {
      var rawKev = await fetchKev();
      var parsed = parseKev(rawKev);
      return {
        ok: true,
        error: null,
        catalogVersion: parsed.catalogVersion,
        dateReleased: parsed.dateReleased,
        total: parsed.total,
        items: parsed.items,
      };
    } catch (e) {
      return emptySource("CISA KEV indisponível: " + (e && e.message ? e.message : String(e)));
    }
  }

  async function loadUrlhaus() {
    if (typeof fetchUrlhaus !== "function") return emptySource("URLhaus não foi pedido.");
    try {
      var rawUh = await fetchUrlhaus();
      var parsedUh = parseUrlhausCsv(rawUh);
      return {
        ok: true,
        error: null,
        total: parsedUh.total,
        items: parsedUh.items,
      };
    } catch (e) {
      return emptySource("URLhaus indisponível: " + (e && e.message ? e.message : String(e)));
    }
  }

  async function loadDshield() {
    if (typeof fetchDshieldSources !== "function") {
      return { ok: true, error: null, total: 0, items: [] };
    }
    try {
      var rawDs = await fetchDshieldSources();
      var parsedDs = parseDshieldSources(rawDs);
      var enriched = await enrichDshieldItems(parsedDs.items, fetchDshieldIp);
      var enrich = enriched.enrich || {};
      var note = null;
      if (enrich.incomplete) {
        note = enrich.stopped429
          ? "DShield: enrich ASN incompleto (HTTP 429). Países em falta não são inventados."
          : "DShield: enrich ASN parcial. Países em falta não são inventados.";
      }
      return {
        ok: true,
        error: null,
        total: parsedDs.total,
        items: enriched.items,
        enrich: enrich,
        enrichIncomplete: !!enrich.incomplete,
        enrichNote: note,
      };
    } catch (e) {
      return emptySource("DShield indisponível: " + (e && e.message ? e.message : String(e)));
    }
  }

  async function loadFeodoFeed() {
    if (typeof fetchFeodo !== "function") {
      return { ok: true, error: null, total: 0, items: [] };
    }
    try {
      var rawFe = await fetchFeodo();
      var parsedFe = parseFeodoCsv(rawFe);
      return {
        ok: true,
        error: null,
        total: parsedFe.total,
        items: parsedFe.items,
      };
    } catch (e) {
      return emptySource("Feodo indisponível: " + (e && e.message ? e.message : String(e)));
    }
  }

  var parallel = await Promise.all([loadKev(), loadUrlhaus(), loadDshield(), loadFeodoFeed()]);
  kev = parallel[0];
  urlhaus = parallel[1];
  dshield = parallel[2];
  feodo = parallel[3];

  var map;
  if (!urlhaus.ok) {
    map = geo.emptyMap(urlhaus.error);
  } else if (!io.ranges) {
    map = geo.emptyMap("Dataset IP→país em falta; o mapa não inventa coordenadas.");
    urlhaus.items.forEach(function (item) { item.geo = null; });
  } else {
    var stats = geo.attachGeo(urlhaus.items, io.ranges);
    map = {
      pins: geo.buildPins(urlhaus.items),
      withGeo: stats.withGeo,
      withoutGeo: stats.withoutGeo,
      skippedNoIp: stats.skippedNoIp,
      note: "Pins = país de alocação RIR de IPs literais no CSV URLhaus. KEV não tem geo. Hostnames não são resolvidos.",
    };
  }

  var mapDshield;
  if (!dshield.ok) {
    mapDshield = geo.emptyMap(dshield.error);
    mapDshield.note = (dshield.error || "DShield indisponível.") + " País ASN ≠ GPS.";
  } else {
    mapDshield = buildAsnMap(
      dshield.items,
      "Pins = país do ASN (ascountry) dos scanners reportados ao DShield. ASN ≠ GPS; não são ataques em directo."
    );
  }

  var mapFeodo;
  if (!feodo.ok) {
    mapFeodo = geo.emptyMap(feodo.error);
    mapFeodo.note = (feodo.error || "Feodo indisponível.") + " C2 destino via RIR.";
  } else if (!io.ranges) {
    mapFeodo = geo.emptyMap("Dataset IP→país em falta; o mapa Feodo não inventa coordenadas.");
    feodo.items.forEach(function (item) { item.geo = null; });
  } else {
    var feStats = geo.attachGeo(feodo.items, io.ranges);
    mapFeodo = {
      pins: geo.buildPins(feodo.items),
      withGeo: feStats.withGeo,
      withoutGeo: feStats.withoutGeo,
      skippedNoIp: feStats.skippedNoIp,
      note: "Pins = país RIR dos IPs destino C2 (dst_ip) no Feodo Tracker. Infra destino, não origem do atacante.",
    };
  }

  return {
    fetchedAt: new Date().toISOString(),
    kev: kev,
    urlhaus: urlhaus,
    dshield: dshield,
    feodo: feodo,
    map: map,
    mapDshield: mapDshield,
    mapFeodo: mapFeodo,
  };
}

module.exports = {
  KEV_URL: KEV_URL,
  URLHAUS_CSV_URL: URLHAUS_CSV_URL,
  DSHIELD_SOURCES_URL: DSHIELD_SOURCES_URL,
  DSHIELD_IP_URL: DSHIELD_IP_URL,
  FEODO_CSV_URL: FEODO_CSV_URL,
  KEV_LIMIT: KEV_LIMIT,
  URLHAUS_LIMIT: URLHAUS_LIMIT,
  DSHIELD_LIMIT: DSHIELD_LIMIT,
  FEODO_LIMIT: FEODO_LIMIT,
  parseKev: parseKev,
  parseUrlhausCsv: parseUrlhausCsv,
  parseDshieldSources: parseDshieldSources,
  parseFeodoCsv: parseFeodoCsv,
  applyDshieldEnrichment: applyDshieldEnrichment,
  loadFeeds: loadFeeds,
  emptySource: emptySource,
};
