"use strict";

var NEWS_LIMIT = 12;
var HOUR_MS = 60 * 60 * 1000;

var NEWS_SOURCES = [
  { id: "cisa", label: "CISA", url: "https://www.cisa.gov/ncas/alerts.xml" },
  { id: "bc", label: "BleepingComputer", url: "https://www.bleepingcomputer.com/feed/" },
  { id: "krebs", label: "Krebs on Security", url: "https://krebsonsecurity.com/feed/" },
];

function decodeXml(s) {
  return String(s)
    .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, "$1")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&apos;/g, "'")
    .replace(/\s+/g, " ")
    .trim();
}

function innerTag(block, name) {
  var re = new RegExp("<" + name + "(?:\\s[^>]*)?>([\\s\\S]*?)</" + name + ">", "i");
  var m = block.match(re);
  return m ? decodeXml(m[1]) : "";
}

function parseRssDate(pub) {
  var s = String(pub || "").trim();
  var m = s.match(/^([A-Za-z]{3},?\s+\d{1,2}\s+[A-Za-z]{3}\s+)(\d{2})(\s+)/);
  if (m) {
    var yy = Number(m[2]);
    s = m[1] + (yy < 70 ? "20" + m[2] : "19" + m[2]) + m[3] + s.slice(m[0].length);
  }
  var ts = Date.parse(s);
  return Number.isFinite(ts) ? ts : 0;
}

function parseRss(xml, sourceLabel) {
  if (typeof xml !== "string") throw new Error("RSS: esperado texto XML.");
  var items = [];
  var re = /<item\b[\s\S]*?<\/item>/gi;
  var m;
  while ((m = re.exec(xml))) {
    var block = m[0];
    var title = innerTag(block, "title");
    var link = innerTag(block, "link");
    if (!link) {
      var lm = block.match(/<link[^>]*href=["']([^"']+)["']/i);
      if (lm) link = decodeXml(lm[1]);
    }
    var pub = innerTag(block, "pubDate") || innerTag(block, "dc:date") || innerTag(block, "updated");
    if (!title || !link) continue;
    if (!/^https?:\/\//i.test(link)) continue;
    items.push({
      source: sourceLabel,
      title: title.slice(0, 240),
      url: link,
      date: pub,
      ts: parseRssDate(pub),
    });
  }
  if (!items.length) throw new Error("RSS sem itens reconhecíveis (" + sourceLabel + ").");
  return items;
}

function pickLatest(items, now) {
  var list = (items || []).slice().sort(function (a, b) {
    return (b.ts || 0) - (a.ts || 0);
  });
  var hour = list.filter(function (it) {
    return it.ts && now - it.ts <= HOUR_MS;
  });
  var chosen = hour.length ? hour : list;
  return chosen.slice(0, NEWS_LIMIT);
}

async function loadNews(fetchers) {
  var all = [];
  var errors = [];
  var now = Date.now();
  for (var i = 0; i < NEWS_SOURCES.length; i++) {
    var src = NEWS_SOURCES[i];
    var fn = fetchers && fetchers[src.id];
    if (!fn) {
      errors.push(src.label + " não foi pedido.");
      continue;
    }
    try {
      var xml = await fn();
      all = all.concat(parseRss(xml, src.label));
    } catch (e) {
      errors.push(src.label + ": " + (e && e.message ? e.message : String(e)));
    }
  }
  var seen = Object.create(null);
  all = all.filter(function (it) {
    if (seen[it.url]) return false;
    seen[it.url] = 1;
    return true;
  });
  if (!all.length) {
    return {
      ok: false,
      error: errors.length ? errors.join(" · ") : "RSS indisponível.",
      items: [],
      total: 0,
      window: "none",
    };
  }
  var hourCount = all.filter(function (it) {
    return it.ts && now - it.ts <= HOUR_MS;
  }).length;
  return {
    ok: true,
    error: errors.length ? errors.join(" · ") : null,
    items: pickLatest(all, now),
    total: all.length,
    window: hourCount ? "hour" : "latest",
  };
}

module.exports = {
  NEWS_SOURCES: NEWS_SOURCES,
  NEWS_LIMIT: NEWS_LIMIT,
  parseRss: parseRss,
  parseRssDate: parseRssDate,
  pickLatest: pickLatest,
  loadNews: loadNews,
};
