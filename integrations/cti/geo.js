"use strict";

/** Country centroids (lat, lng). Inlined via JSON require for Node + Workers bundle. */
var CENTROIDS = require("./data/centroids.json");

function setCentroids(obj) {
  if (!obj || typeof obj !== "object") return CENTROIDS;
  Object.keys(CENTROIDS).forEach(function (k) {
    delete CENTROIDS[k];
  });
  Object.keys(obj).forEach(function (k) {
    CENTROIDS[k] = obj[k];
  });
  return CENTROIDS;
}

function ipv4ToInt(ip) {
  var p = String(ip).split(".");
  if (p.length !== 4) return null;
  var n = 0;
  for (var i = 0; i < 4; i++) {
    var o = Number(p[i]);
    if (!Number.isInteger(o) || o < 0 || o > 255) return null;
    n = n * 256 + o;
  }
  return n >>> 0;
}

function extractIpv4(ioc) {
  var raw = String(ioc || "").trim();
  if (ipv4ToInt(raw) != null) return raw;
  try {
    var u = new URL(raw);
    var host = u.hostname;
    if (host.charAt(0) === "[") return null;
    return ipv4ToInt(host) == null ? null : host;
  } catch (e) {
    return null;
  }
}

function parseDelegated(text) {
  var ranges = [];
  var lines = String(text).split(/\n/);
  for (var i = 0; i < lines.length; i++) {
    var line = lines[i];
    if (!line || line.charAt(0) === "#") continue;
    var parts = line.split("|");
    if (parts.length < 7) continue;
    if (parts[2] !== "ipv4") continue;
    var cc = parts[1];
    if (!cc || cc.length !== 2 || cc === "*") continue;
    var start = ipv4ToInt(parts[3]);
    var count = Number(parts[4]);
    if (start == null || !count) continue;
    ranges.push({ start: start, end: start + count - 1, cc: cc.toUpperCase() });
  }
  return ranges;
}

/**
 * Parse packed RIR ranges binary.
 * Layout (see README):
 *   magic  uint32 BE  'CTIR' (0x43544952)
 *   count  uint32 BE
 *   then count records of:
 *     start uint32 BE
 *     end   uint32 BE
 *     cc    2 bytes ASCII
 */
function parseRangesBin(arrayBuffer) {
  var view;
  var byteLength;
  if (arrayBuffer instanceof ArrayBuffer) {
    view = new DataView(arrayBuffer);
    byteLength = arrayBuffer.byteLength;
  } else if (arrayBuffer && arrayBuffer.buffer instanceof ArrayBuffer) {
    view = new DataView(
      arrayBuffer.buffer,
      arrayBuffer.byteOffset || 0,
      arrayBuffer.byteLength
    );
    byteLength = arrayBuffer.byteLength;
  } else {
    throw new Error("parseRangesBin: expected ArrayBuffer or TypedArray");
  }
  if (byteLength < 8) throw new Error("parseRangesBin: buffer too short");
  var magic = view.getUint32(0, false);
  if (magic !== 0x43544952) {
    throw new Error("parseRangesBin: bad magic (expected CTIR)");
  }
  var count = view.getUint32(4, false);
  var need = 8 + count * 10;
  if (byteLength < need) {
    throw new Error("parseRangesBin: truncated (need " + need + ", have " + byteLength + ")");
  }
  var ranges = new Array(count);
  for (var i = 0; i < count; i++) {
    var o = 8 + i * 10;
    var start = view.getUint32(o, false);
    var end = view.getUint32(o + 4, false);
    var cc = String.fromCharCode(view.getUint8(o + 8), view.getUint8(o + 9));
    ranges[i] = { start: start, end: end, cc: cc };
  }
  return ranges;
}

function lookupCountry(ip, ranges) {
  var n = typeof ip === "number" ? ip : ipv4ToInt(ip);
  if (n == null || !ranges || !ranges.length) return null;
  var lo = 0;
  var hi = ranges.length - 1;
  while (lo <= hi) {
    var mid = (lo + hi) >> 1;
    var r = ranges[mid];
    if (n < r.start) hi = mid - 1;
    else if (n > r.end) lo = mid + 1;
    else return r.cc;
  }
  return null;
}

function geoForIp(ip, ranges) {
  var cc = lookupCountry(ip, ranges);
  if (!cc) return null;
  var c = CENTROIDS[cc];
  if (!c) return null;
  return { cc: cc, lat: c[0], lng: c[1], ip: ip };
}

function attachGeo(items, ranges) {
  var withGeo = 0;
  var withoutGeo = 0;
  var skippedNoIp = 0;
  (items || []).forEach(function (item) {
    var ip = extractIpv4(item.ioc);
    if (!ip) {
      item.geo = null;
      withoutGeo++;
      skippedNoIp++;
      return;
    }
    var g = geoForIp(ip, ranges);
    if (!g) {
      item.geo = null;
      withoutGeo++;
      return;
    }
    item.geo = g;
    withGeo++;
  });
  return { withGeo: withGeo, withoutGeo: withoutGeo, skippedNoIp: skippedNoIp };
}

function buildPins(items) {
  var byCc = Object.create(null);
  (items || []).forEach(function (item) {
    if (!item.geo || !item.geo.cc) return;
    var cc = item.geo.cc;
    if (!byCc[cc]) {
      byCc[cc] = { cc: cc, lat: item.geo.lat, lng: item.geo.lng, count: 0 };
    }
    byCc[cc].count++;
  });
  return Object.keys(byCc)
    .map(function (k) {
      return byCc[k];
    })
    .sort(function (a, b) {
      return b.count - a.count;
    });
}

function emptyMap(reason) {
  return {
    pins: [],
    withGeo: 0,
    withoutGeo: 0,
    skippedNoIp: 0,
    note: reason || "Sem geo comprovada.",
  };
}

module.exports = {
  CENTROIDS: CENTROIDS,
  setCentroids: setCentroids,
  ipv4ToInt: ipv4ToInt,
  extractIpv4: extractIpv4,
  parseDelegated: parseDelegated,
  parseRangesBin: parseRangesBin,
  lookupCountry: lookupCountry,
  geoForIp: geoForIp,
  attachGeo: attachGeo,
  buildPins: buildPins,
  emptyMap: emptyMap,
};
