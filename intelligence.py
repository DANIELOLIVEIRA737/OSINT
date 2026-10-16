"""Evidence-derived graphs and comparisons. No network access here."""

import json


def graph(report):
    nodes, edges = {}, []
    company_leis = {}

    def node(kind, label):
        ident = kind + ":" + str(label)
        nodes[ident] = {"id": ident, "type": kind, "label": str(label)}
        return ident

    root = node("target", report["target"])

    def link(a, b, label, source, confidence="observed"):
        edge = {
            "from": a,
            "to": b,
            "label": label,
            "source": source,
            "confidence": confidence,
        }
        if a != b and edge not in edges:
            edges.append(edge)

    for name, result in report.get("results", {}).items():
        if result.get("status") != "ok":
            continue
        d = result["data"]
        if name == "network":
            for ip in d.get("addresses", [])[:20]:
                link(root, node("ip", ip), "resolve para", name)
        elif name == "dns":
            for kind in ("MX", "NS", "CNAME"):
                for record in d.get("records", {}).get(kind, [])[:8]:
                    link(
                        root,
                        node("domain", record["value"].split()[-1].rstrip(".")),
                        kind,
                        name,
                    )
        elif name == "ip":
            address = node("ip", d.get("ip", report["target"]))
            conn = d.get("connection") or {}
            if conn.get("asn"):
                link(
                    address, node("asn", "AS" + str(conn["asn"])), "anunciado por", name
                )
            if conn.get("org"):
                link(address, node("organization", conn["org"]), "rede indicada", name)
        elif name == "tls":
            cert = node(
                "certificate",
                str(d.get("issuer", {}).get("commonName", "TLS"))
                + " · "
                + str(d.get("valid_until", "")),
            )
            link(root, cert, "apresentou certificado", name)
            for domain in d.get("names", [])[:8]:
                link(cert, node("domain", domain), "nome no certificado", name)
        elif name == "subdomains":
            for record in d.get("hosts", [])[:20]:
                host = node("domain", record["host"])
                link(root, host, "nome observado", name)
                for ip in record.get("addresses", [])[:4]:
                    link(host, node("ip", ip), "resolve para", name)
        elif name == "registration":
            for entity in d.get("entities", []):
                if "registrant" in entity.get("roles", []):
                    for org in entity.get("organizations", [])[:3]:
                        link(
                            root,
                            node("organization", str(org)),
                            "organização no registo",
                            name,
                        )
        elif name == "company":
            for candidate in d.get("candidates", [])[:10]:
                entity = node(
                    "organization", candidate["name"] + " · " + candidate["id"]
                )
                link(root, entity, "correspondência de pesquisa", name, "hypothesis")
                for lei in candidate.get("lei", []):
                    company_leis.setdefault(lei, []).append(entity)
                for url in candidate.get("websites", [])[:3]:
                    link(entity, node("domain", url), "site indicado pela fonte", name)
        elif name == "threat_intelligence":
            for match in d.get("matches", [])[:20]:
                link(
                    root,
                    node("indicator", match["ioc"]),
                    "reportado por " + match["sourceLabel"],
                    name,
                )
        elif name == "business_registry":
            for record in d.get("records", [])[:8]:
                entity = node(
                    "organization",
                    str(record.get("name", "Entidade"))
                    + " · "
                    + str(record.get("lei", "")),
                )
                link(root, entity, "correspondência em registo LEI", name, "hypothesis")
                for candidate in company_leis.get(record.get("lei"), []):
                    link(candidate, entity, "mesmo identificador LEI", name)
    kept = list(nodes.values())[:120]
    valid = {n["id"] for n in kept}
    return {
        "nodes": kept,
        "edges": [e for e in edges if e["from"] in valid and e["to"] in valid][:220],
        "note": "As ligações representam as evidências indicadas. Partilhar IP, ASN ou certificado não comprova propriedade comum. Correspondências por nome são hipóteses.",
    }


IGNORE = {
    "observed_at",
    "observedAt",
    "fetchedAt",
    "assessment",
    "source",
    "note",
    "ttl",
    "checked_at",
    "duration_ms",
    "current_time",
    "cached",
    "fetched_at",
    "cache_expires_at",
}


def normalize(value):
    if isinstance(value, dict):
        return {k: normalize(v) for k, v in sorted(value.items()) if k not in IGNORE}
    if isinstance(value, list):
        return sorted(
            (normalize(v) for v in value), key=lambda v: json.dumps(v, sort_keys=True)
        )
    return value


def compare(before, after):
    if before["target"] != after["target"] or before.get("mode") != after.get("mode"):
        raise ValueError("Escolhe relatórios do mesmo alvo e modo.")
    changes, coverage = [], []

    def walk(a, b, path):
        if len(changes) >= 200:
            return
        if isinstance(a, dict) and isinstance(b, dict):
            for key in sorted(set(a) | set(b)):
                if key not in a:
                    changes.append(
                        {
                            "path": path + "." + key,
                            "type": "added",
                            "before": None,
                            "after": b[key],
                        }
                    )
                elif key not in b:
                    changes.append(
                        {
                            "path": path + "." + key,
                            "type": "removed",
                            "before": a[key],
                            "after": None,
                        }
                    )
                else:
                    walk(a[key], b[key], path + "." + key)
        elif a != b:
            changes.append({"path": path, "type": "changed", "before": a, "after": b})

    for name in sorted(set(before["results"]) | set(after["results"])):
        old, new = before["results"].get(name, {}), after["results"].get(name, {})
        if old.get("status") != "ok" or new.get("status") != "ok":
            coverage.append(
                {
                    "module": name,
                    "before": old.get("status", "unrun"),
                    "after": new.get("status", "unrun"),
                }
            )
            continue
        old_data, new_data = old["data"], new["data"]
        if name == "threat_intelligence":
            states = [
                {s["source"]: s["available"] for s in d.get("sources_checked", [])}
                for d in (old_data, new_data)
            ]
            common = {
                source
                for source in set(states[0]) | set(states[1])
                if states[0].get(source) and states[1].get(source)
            }
            for source in sorted(set(states[0]) | set(states[1])):
                if source not in common:
                    coverage.append(
                        {
                            "module": name + "/" + source,
                            "before": "ok" if states[0].get(source) else "error",
                            "after": "ok" if states[1].get(source) else "error",
                        }
                    )
            if not common:
                continue
            old_data = {
                **old_data,
                "matches": [
                    m for m in old_data.get("matches", []) if m["source"] in common
                ],
                "sources_checked": [
                    s
                    for s in old_data.get("sources_checked", [])
                    if s["source"] in common
                ],
            }
            new_data = {
                **new_data,
                "matches": [
                    m for m in new_data.get("matches", []) if m["source"] in common
                ],
                "sources_checked": [
                    s
                    for s in new_data.get("sources_checked", [])
                    if s["source"] in common
                ],
            }
        walk(normalize(old_data), normalize(new_data), name)
    return {
        "target": after["target"],
        "before_date": before["created_at"],
        "after_date": after["created_at"],
        "changes": changes[:200],
        "coverage": coverage,
        "limit": 200,
        "limit_reached": len(changes) >= 200,
        "note": "Só são comparados dados de módulos bem-sucedidos nas duas pesquisas. Indisponibilidade não é tratada como remoção; TTL, ordem e tempos de consulta são ignorados.",
    }
