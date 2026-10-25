#!/usr/bin/env python3
"""Generates podflow-dashboards.yaml: the Grafana dashboards for the podflow flow agent.

    python3 gen-podflow-dashboards.py          # rewrites podflow-dashboards.yaml next to this file

One ConfigMap holds all dashboards; it is mounted at /var/lib/grafana/dashboards/podflow, which Grafana turns
into the "podflow" folder (foldersFromFilesStructure). The dashboards are modelled on a router's flow-stats pages
(device table, per-device detail, categories, active flows, connection history), with pods instead of devices:

  pf-pods        Pod Traffic          table of pods: rate, 24h/7d/30d totals, status; click a pod for its detail
  pf-pod         Pod Detail           one pod: throughput, applications, categories, peers, recent connections
  pf-categories  Traffic Categories   volume and rate by category/application
  pf-flows       Active Flows         top flows by rate, with a minimum-rate filter
  pf-history     Connection History   recently closed flows
  pf-tailnet     Tailnet Devices      devices using the Tailscale exit nodes / subnet routers

Metrics: podflow_bytes_total, podflow_flows_total, podflow_peer_bytes_total, podflow_tailnet_* and the recording
rules podflow:*:increase5m / increase1h (prometheus-config). Flow lines: Loki {job="podflow"}.
"""
import json
import os

DS_P = {"type": "prometheus", "uid": "Prometheus"}
DS_L = {"type": "loki", "uid": "Loki"}

_next_id = [0]


def pid():
    _next_id[0] += 1
    return _next_id[0]


# ---------------------------------------------------------------- targets
def pt(expr, ref="A", legend=None, instant=False, table=False):
    t = {"datasource": DS_P, "expr": expr, "refId": ref, "editorMode": "code"}
    if instant:
        t.update({"instant": True, "range": False})
    else:
        t.update({"instant": False, "range": True})
    if legend is not None:
        t["legendFormat"] = legend
    if table:
        t["format"] = "table"
    return t


def lt(expr, ref="A", instant=False, lines=None):
    t = {"datasource": DS_L, "expr": expr, "refId": ref, "editorMode": "code", "queryType": "instant" if instant else "range"}
    if lines:
        t["maxLines"] = lines
    return t


# ---------------------------------------------------------------- variables
def qvar(name, query, label=None, multi=False, all_=False, ds=DS_P, hide=0):
    v = {
        "name": name, "label": label or name, "type": "query", "datasource": ds, "hide": hide,
        "definition": query, "query": {"query": query, "refId": "v-" + name}, "refresh": 2, "sort": 1,
        "includeAll": all_, "multi": multi, "regex": "",
    }
    if all_:
        v["allValue"] = ".*"
        v["current"] = {"selected": True, "text": "All", "value": "$__all"}
    return v


def textvar(name, default, label=None):
    return {"name": name, "label": label or name, "type": "textbox", "query": default,
            "current": {"selected": False, "text": default, "value": default}, "options": [{"selected": True, "text": default, "value": default}]}


def customvar(name, options, default, label=None):
    """options: [(label, value)]"""
    q = ",".join(f"{l} : {v}" for l, v in options)
    cur = next((l, v) for l, v in options if v == default)
    return {"name": name, "label": label or name, "type": "custom", "query": q,
            "current": {"selected": True, "text": cur[0], "value": cur[1]},
            "options": [{"selected": v == default, "text": l, "value": v} for l, v in options]}


# ---------------------------------------------------------------- panels
def grid(x, y, w, h):
    return {"x": x, "y": y, "w": w, "h": h}


def stat(title, expr, unit, g, decimals=None, desc=None, color="green"):
    d = {"unit": unit, "color": {"mode": "fixed", "fixedColor": color}, "thresholds": {"mode": "absolute", "steps": [{"color": color, "value": None}]}}
    if decimals is not None:
        d["decimals"] = decimals
    return {"id": pid(), "type": "stat", "title": title, "description": desc or "", "datasource": DS_P, "gridPos": g,
            "targets": [pt(expr, instant=True)],
            "fieldConfig": {"defaults": d, "overrides": []},
            "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "colorMode": "value", "graphMode": "none", "textMode": "auto", "justifyMode": "auto"}}


def timeseries(title, targets, unit, g, stack=False, negate=None, desc=None, ds=DS_P):
    custom = {"drawStyle": "line", "lineWidth": 1, "fillOpacity": 25 if stack else 12, "showPoints": "never", "spanNulls": True,
              "stacking": {"mode": "normal" if stack else "none", "group": "A"}}
    overrides = []
    if negate:
        overrides.append({"matcher": {"id": "byRegexp", "options": negate}, "properties": [{"id": "custom.transform", "value": "negative-Y"}]})
    return {"id": pid(), "type": "timeseries", "title": title, "description": desc or "", "datasource": ds, "gridPos": g, "targets": targets,
            "fieldConfig": {"defaults": {"unit": unit, "custom": custom, "color": {"mode": "palette-classic"}}, "overrides": overrides},
            "options": {"legend": {"displayMode": "table", "placement": "bottom", "calcs": ["mean", "max"]}, "tooltip": {"mode": "multi", "sort": "desc"}}}


def donut(title, expr, unit, g, desc=None):
    return {"id": pid(), "type": "piechart", "title": title, "description": desc or "", "datasource": DS_P, "gridPos": g,
            "targets": [pt(expr, legend="{{category}}", instant=True)],
            "fieldConfig": {"defaults": {"unit": unit, "color": {"mode": "palette-classic"}}, "overrides": []},
            "options": {"pieType": "donut", "legend": {"displayMode": "table", "placement": "right", "values": ["value", "percent"]},
                        "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "tooltip": {"mode": "single"}}}


def table(title, targets, transformations, g, overrides=None, sort=None, ds=DS_P, desc=None):
    # sorting is a table option (by display name); a sortBy transformation does not see renamed fields
    for tr in list(transformations):
        if tr["id"] == "sortBy":
            first = tr["options"]["sort"][0]
            sort = (first["field"], first["desc"])
            transformations = [t for t in transformations if t is not tr]
    opts = {"showHeader": True, "cellHeight": "sm", "footer": {"show": False}}
    if sort:
        opts["sortBy"] = [{"displayName": sort[0], "desc": sort[1]}]
    return {"id": pid(), "type": "table", "title": title, "description": desc or "", "datasource": ds, "gridPos": g, "targets": targets,
            "transformations": transformations,
            "fieldConfig": {"defaults": {"custom": {"align": "auto", "cellOptions": {"type": "auto"}, "filterable": True}}, "overrides": overrides or []},
            "options": opts}


def prop(id_, value):
    return {"id": id_, "value": value}


def by_name(name, *props):
    return {"matcher": {"id": "byName", "options": name}, "properties": list(props)}


def unit_override(name, unit):
    return by_name(name, prop("unit", unit))


def link_override(name, title, url):
    return by_name(name, prop("links", [{"title": title, "url": url, "targetBlank": False}]))


STATUS_MAP = prop("mappings", [
    {"type": "special", "options": {"match": "null", "result": {"text": "Idle", "color": "yellow", "index": 0}}},
    {"type": "value", "options": {"0": {"text": "Idle", "color": "yellow", "index": 1}}},
    {"type": "range", "options": {"from": 0.000001, "to": 1e18, "result": {"text": "Active", "color": "green", "index": 2}}},
])
STATUS_CELL = prop("custom.cellOptions", {"type": "color-text"})


def organize(rename, hide=("Time",)):
    # indexByName is keyed by the original field names (before the rename), in the order the columns should appear
    return {"id": "organize", "options": {"excludeByName": {h: True for h in hide}, "indexByName": {n: i for i, n in enumerate(rename)}, "renameByName": rename}}


def dashboard(uid, title, panels, variables, desc, time_from="now-6h"):
    return {
        "uid": uid, "title": title, "description": desc, "tags": ["podflow"], "timezone": "browser", "schemaVersion": 39, "version": 1,
        "editable": True, "graphTooltip": 1, "refresh": "30s", "time": {"from": time_from, "to": "now"},
        "annotations": {"list": []},
        "links": [{"type": "dashboards", "title": "podflow", "tags": ["podflow"], "asDropdown": True, "includeVars": False, "keepTime": True, "icon": "dashboard"}],
        "templating": {"list": variables}, "panels": panels,
    }


# ---------------------------------------------------------------- LogQL pieces
def json_fields(*pairs):
    """`| json a="x.y", ...` extracting nested fields of the flow lines into labels"""
    return "| json " + ", ".join(f'{a}="{b}"' for a, b in pairs)


COMMON = [("src_kind", "src.kind"), ("src_ns", "src.ns"), ("src_name", "src.name"), ("src_ip", "src.ip"), ("src_port", "src.port"),
          ("dst_kind", "dst.kind"), ("dst_ns", "dst.ns"), ("dst_name", "dst.name"), ("dst_host", "dst.host"), ("dst_ip", "dst.ip"),
          ("dst_port", "dst.port"), ("dst_country", "dst.country"), ("proto", "proto"), ("app", "app"), ("category", "category"),
          ("node", "node")]


def ns_filter():
    return '| src_ns=~"$ns" or dst_ns=~"$ns"'


# ================================================================= Pod Traffic
def pods_dashboard():
    _next_id[0] = 0
    sel = 'ns=~"$ns", pod_name=~"$search"'
    p = [
        stat("Throughput (rx + tx)", 'sum(rate(podflow_bytes_total{ns=~"$ns"}[5m])) * 8', "bps", grid(0, 0, 6, 4),
             desc="Bytes sent plus received by pods, summed. Traffic between two pods is counted at both ends."),
        stat("Active pods", 'count(sum by (ns, pod_name) (rate(podflow_bytes_total{ns=~"$ns"}[5m])) > 0)', "none", grid(6, 0, 6, 4), desc="Pods that moved data in the last 5 minutes."),
        stat("Traffic, last 24h", 'sum(sum_over_time(podflow:pod_bytes:increase5m{ns=~"$ns"}[24h]))', "bytes", grid(12, 0, 6, 4), color="blue"),
        stat("Closed flows / min", 'sum(rate(podflow_flows_total{ns=~"$ns"}[5m])) * 60', "none", grid(18, 0, 6, 4), decimals=1, color="blue"),
        timeseries("Top 10 pods by throughput", [pt(f'topk(10, sum by (ns, pod_name) (rate(podflow_bytes_total{{{sel}}}[$__rate_interval])) * 8)', legend="{{ns}}/{{pod_name}}")], "bps", grid(0, 4, 24, 8)),
    ]
    pod_table = [
        pt(f'sum by (ns, pod_name, workload) (rate(podflow_bytes_total{{direction="rx", {sel}}}[5m])) * 8', "A", instant=True, table=True),
        pt(f'sum by (ns, pod_name, workload) (rate(podflow_bytes_total{{direction="tx", {sel}}}[5m])) * 8', "B", instant=True, table=True),
        pt(f'sum by (ns, pod_name, workload) (sum_over_time(podflow:pod_bytes:increase5m{{direction="rx", {sel}}}[24h]))', "C", instant=True, table=True),
        pt(f'sum by (ns, pod_name, workload) (sum_over_time(podflow:pod_bytes:increase5m{{direction="tx", {sel}}}[24h]))', "D", instant=True, table=True),
        pt(f'sum by (ns, pod_name, workload) (sum_over_time(podflow:pod_bytes:increase1h{{direction="rx", {sel}}}[7d]))', "E", instant=True, table=True),
        pt(f'sum by (ns, pod_name, workload) (sum_over_time(podflow:pod_bytes:increase1h{{direction="tx", {sel}}}[7d]))', "F", instant=True, table=True),
        pt(f'sum by (ns, pod_name, workload) (sum_over_time(podflow:pod_bytes:increase1h{{direction="rx", {sel}}}[30d]))', "G", instant=True, table=True),
        pt(f'sum by (ns, pod_name, workload) (sum_over_time(podflow:pod_bytes:increase1h{{direction="tx", {sel}}}[30d]))', "H", instant=True, table=True),
    ]
    rename = {"ns": "Namespace", "pod_name": "Pod", "workload": "Workload", "Value #A": "RX rate", "Value #B": "TX rate",
              "Value #C": "24h RX", "Value #D": "24h TX", "Value #E": "7d RX", "Value #F": "7d TX", "Value #G": "30d RX", "Value #H": "30d TX", "Status": "Status"}
    tf = [
        {"id": "merge", "options": {}},
        {"id": "calculateField", "options": {"mode": "reduceRow", "reduce": {"reducer": "sum", "include": ["Value #A", "Value #B"]}, "alias": "Status", "replaceFields": False}},
        organize(rename),
        {"id": "sortBy", "options": {"fields": {}, "sort": [{"field": "RX rate", "desc": True}]}},
    ]
    ov = [unit_override("RX rate", "bps"), unit_override("TX rate", "bps")] + [unit_override(n, "bytes") for n in ("24h RX", "24h TX", "7d RX", "7d TX", "30d RX", "30d TX")]
    ov += [by_name("Status", STATUS_MAP, STATUS_CELL, prop("custom.width", 90)),
           link_override("Pod", "Pod detail", "/d/pf-pod/pod-detail?var-ns=${__data.fields[\"Namespace\"]}&var-pod=${__value.raw}&${__url_time_range}")]
    p.append(table("Pods", pod_table, tf, grid(0, 12, 24, 18), ov, desc="Rates are the last 5 minutes. 24h totals come from 5-minute rollups, 7d and 30d from hourly ones, so long windows fill up over time (data starts when podflow was deployed). Click a pod name for its detail."))
    vars_ = [qvar("ns", "label_values(podflow_bytes_total, ns)", "Namespace", multi=True, all_=True), textvar("search", ".*", "Pod name (regex)")]
    return dashboard("pf-pods", "Pod Traffic", p, vars_, "Per-pod network traffic from podflow: rates, totals and status for every pod.")


# ================================================================= Pod Detail
def pod_dashboard():
    _next_id[0] = 0
    sel = 'ns="$ns", pod_name="$pod"'
    w = [
        stat("RX rate", f'sum(rate(podflow_bytes_total{{direction="rx", {sel}}}[5m])) * 8', "bps", grid(0, 0, 4, 4), color="green"),
        stat("TX rate", f'sum(rate(podflow_bytes_total{{direction="tx", {sel}}}[5m])) * 8', "bps", grid(4, 0, 4, 4), color="orange"),
        stat("Last 24h", f'sum(sum_over_time(podflow:pod_bytes:increase5m{{{sel}}}[24h]))', "bytes", grid(8, 0, 4, 4), color="blue"),
        stat("Last 7d", f'sum(sum_over_time(podflow:pod_bytes:increase1h{{{sel}}}[7d]))', "bytes", grid(12, 0, 4, 4), color="blue"),
        stat("Last 30d", f'sum(sum_over_time(podflow:pod_bytes:increase1h{{{sel}}}[30d]))', "bytes", grid(16, 0, 4, 4), color="blue"),
        stat("Closed flows / min", f'sum(rate(podflow_flows_total{{{sel}}}[5m])) * 60', "none", grid(20, 0, 4, 4), decimals=1, color="purple"),
        timeseries("Throughput", [pt(f'sum by (direction) (rate(podflow_bytes_total{{{sel}}}[$__rate_interval])) * 8', legend="{{direction}}")], "bps", grid(0, 4, 12, 9),
                   negate="rx", desc="Sent (tx) above the axis, received (rx) below."),
        timeseries("Throughput by application", [pt(f'sum by (application) (rate(podflow_bytes_total{{{sel}}}[$__rate_interval])) * 8', legend="{{application}}")], "bps", grid(12, 4, 12, 9), stack=True),
        donut("Traffic by category (selected range)", f'sum by (category) (sum_over_time(podflow:pod_app_bytes:increase5m{{{sel}}}[$__range]))', "bytes", grid(0, 13, 8, 9)),
    ]
    app_q = [
        pt(f'sum by (application, category) (sum_over_time(podflow:pod_app_bytes:increase5m{{direction="rx", {sel}}}[$__range]))', "A", instant=True, table=True),
        pt(f'sum by (application, category) (sum_over_time(podflow:pod_app_bytes:increase5m{{direction="tx", {sel}}}[$__range]))', "B", instant=True, table=True),
    ]
    app_tf = [{"id": "merge", "options": {}}, organize({"application": "Application", "category": "Category", "Value #A": "Downloaded", "Value #B": "Uploaded"}),
              {"id": "sortBy", "options": {"fields": {}, "sort": [{"field": "Downloaded", "desc": True}]}}]
    w.append(table("Applications (selected range)", app_q, app_tf, grid(8, 13, 16, 9), [unit_override("Downloaded", "bytes"), unit_override("Uploaded", "bytes")]))
    peer_sel = 'ns="$ns", workload="$workload"'
    peer_q = [
        pt(f'sum by (peer_kind, peer_ns, peer_workload, peer_country) (sum_over_time(podflow:peer_bytes:increase1h{{direction="tx", {peer_sel}}}[$__range]))', "A", instant=True, table=True),
        pt(f'sum by (peer_kind, peer_ns, peer_workload, peer_country) (sum_over_time(podflow:peer_bytes:increase1h{{direction="rx", {peer_sel}}}[$__range]))', "B", instant=True, table=True),
    ]
    peer_tf = [{"id": "merge", "options": {}},
               organize({"peer_kind": "Peer kind", "peer_ns": "Peer namespace", "peer_workload": "Peer workload", "peer_country": "Country", "Value #A": "Sent", "Value #B": "Received"}),
               {"id": "sortBy", "options": {"fields": {}, "sort": [{"field": "Received", "desc": True}]}}]
    w.append(table("Peers (workload level, selected range)", peer_q, peer_tf, grid(0, 22, 24, 9), [unit_override("Sent", "bytes"), unit_override("Received", "bytes")],
                   desc="Who this workload talked to. External peers show only their country; hourly rollups, so the newest hour is missing."))
    hist = (f'{{job="podflow", event="close"}} {json_fields(*COMMON, ("duration_ms", "duration_ms"), ("tx_bytes", "tx_bytes"), ("rx_bytes", "rx_bytes"), ("count", "count"))} '
            f'| src_name="$pod" or dst_name="$pod"')
    w.append(table("Recent connections", [lt(hist, lines=100)], history_tf(), grid(0, 31, 24, 12), history_overrides(), ds=DS_L, desc="Closed flows (newest first); short flows are aggregated, see Count."))
    vars_ = [qvar("ns", "label_values(podflow_bytes_total, ns)", "Namespace"), qvar("pod", 'label_values(podflow_bytes_total{ns="$ns"}, pod_name)', "Pod"),
             qvar("workload", 'label_values(podflow_bytes_total{ns="$ns", pod_name="$pod"}, workload)', "Workload", hide=2)]
    return dashboard("pf-pod", "Pod Detail", w, vars_, "One pod: throughput, applications, categories, peers and recent connections.")


# ================================================================= Categories
def categories_dashboard():
    _next_id[0] = 0
    p = [
        donut("Volume by category", 'sum by (category) (sum_over_time(podflow:ns_app_bytes:increase5m{ns=~"$ns"}[$window]))', "bytes", grid(0, 0, 12, 9)),
        donut("Current rate by category", 'sum by (category) (rate(podflow_bytes_total{ns=~"$ns"}[5m])) * 8', "bps", grid(12, 0, 12, 9)),
        timeseries("Rate by category", [pt('sum by (category) (rate(podflow_bytes_total{ns=~"$ns"}[$__rate_interval])) * 8', legend="{{category}}")], "bps", grid(0, 9, 24, 8), stack=True),
    ]
    q = [
        pt('sum by (application, category) (sum_over_time(podflow:ns_app_flows:increase1h{ns=~"$ns"}[$window]))', "A", instant=True, table=True),
        pt('sum by (application, category) (sum_over_time(podflow:ns_app_bytes:increase5m{direction="rx", ns=~"$ns"}[$window]))', "B", instant=True, table=True),
        pt('sum by (application, category) (sum_over_time(podflow:ns_app_bytes:increase5m{direction="tx", ns=~"$ns"}[$window]))', "C", instant=True, table=True),
        pt('sum by (application, category) (rate(podflow_bytes_total{direction="rx", ns=~"$ns"}[5m])) * 8', "D", instant=True, table=True),
        pt('sum by (application, category) (rate(podflow_bytes_total{direction="tx", ns=~"$ns"}[5m])) * 8', "E", instant=True, table=True),
    ]
    tf = [{"id": "merge", "options": {}},
          {"id": "calculateField", "options": {"mode": "reduceRow", "reduce": {"reducer": "sum", "include": ["Value #B", "Value #C"]}, "alias": "Total", "replaceFields": False}},
          organize({"application": "Application", "category": "Category", "Value #A": "Flows", "Value #B": "Downloaded", "Value #C": "Uploaded", "Total": "Total",
                    "Value #D": "RX rate", "Value #E": "TX rate"}),
          {"id": "sortBy", "options": {"fields": {}, "sort": [{"field": "Total", "desc": True}]}}]
    ov = [unit_override("Downloaded", "bytes"), unit_override("Uploaded", "bytes"), unit_override("RX rate", "bps"), unit_override("TX rate", "bps"),
          by_name("Total", prop("unit", "bytes"), prop("custom.cellOptions", {"type": "gauge", "mode": "gradient"}))]
    p.append(table("Applications", q, tf, grid(0, 17, 24, 14), ov,
                   desc="Flows are closed flows (hourly rollup). Volumes cover the selected window; rates are the last 5 minutes. Pod-to-pod traffic is counted at both ends."))
    vars_ = [qvar("ns", "label_values(podflow_bytes_total, ns)", "Namespace", multi=True, all_=True),
             customvar("window", [("1h", "1h"), ("6h", "6h"), ("24h", "24h"), ("7d", "7d"), ("30d", "30d")], "24h", "Window")]
    return dashboard("pf-categories", "Traffic Categories", p, vars_, "Network traffic by category and application.")


# ================================================================= Active Flows
def flows_dashboard():
    _next_id[0] = 0
    base = (f'{{job="podflow", event="active"}} {json_fields(*COMMON, ("rate_bps", "rate_bps"))} '
            f'| rate_bps >= $minrate {ns_filter()} | src_name=~"$pod" or dst_name=~"$pod"')
    by = "src_kind, src_ns, src_name, src_ip, dst_kind, dst_ns, dst_name, dst_host, dst_ip, dst_port, proto, app, category, node"
    top = f'topk(50, max by ({by}) (max_over_time({base} | unwrap rate_bps [2m])))'
    p = [
        {"id": pid(), "type": "stat", "title": "Active flows", "datasource": DS_L, "gridPos": grid(0, 0, 6, 4),
         "targets": [lt(f'count(max by ({by}) (max_over_time({base} | unwrap rate_bps [2m])))', instant=True)],
         "fieldConfig": {"defaults": {"unit": "none", "color": {"mode": "fixed", "fixedColor": "blue"}}, "overrides": []},
         "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "colorMode": "value", "graphMode": "none", "textMode": "auto"}},
    ]
    # the order here is the column order: who, to whom, how fast first; the rest to the right
    rename = {"Value #A": "Rate", "src_name": "Source", "src_ip": "Src IP", "src_ns": "Src namespace", "dst_host": "Destination host", "dst_name": "Dst pod/service", "dst_ip": "Dst IP",
              "dst_port": "Dst port", "proto": "Protocol", "app": "Classification", "category": "Category", "dst_ns": "Dst namespace",
              "node": "Node", "src_kind": "Src kind", "dst_kind": "Dst kind"}
    hide = ("Time", "Src kind", "Dst kind", "Node")
    tf = [{"id": "labelsToFields", "options": {"mode": "columns"}}, {"id": "merge", "options": {}}, organize(rename, hide=("Time", "src_kind", "dst_kind")),
          {"id": "sortBy", "options": {"fields": {}, "sort": [{"field": "Rate", "desc": True}]}}]
    p.append(table("Top 50 active flows", [lt(top, instant=True)], tf, grid(0, 4, 24, 20), [by_name("Rate", prop("unit", "bps"), prop("custom.cellOptions", {"type": "gauge", "mode": "gradient"}))],
                   ds=DS_L, desc="Flows that moved at least the minimum rate in the last 2 minutes (the agent reports every 60s). Flows between the same endpoints are merged."))
    vars_ = [customvar("minrate", [("1 Kbps", "1000"), ("100 Kbps", "100000"), ("1 Mbps", "1000000"), ("10 Mbps", "10000000"), ("100 Mbps", "100000000")], "1000", "Min rate"),
             textvar("ns", ".*", "Namespace (regex)"), textvar("pod", ".*", "Pod (regex)")]
    return dashboard("pf-flows", "Active Flows", p, vars_, "Top flows by rate right now.", time_from="now-15m")


# ================================================================= Connection History
def history_tf():
    rename = {"Time": "Closed at", "src_kind": "Src kind", "src_ns": "Src namespace", "src_name": "Source", "src_ip": "Src IP", "src_port": "Src port",
              "dst_kind": "Dst kind", "dst_ns": "Dst namespace", "dst_name": "Dst pod/service", "dst_host": "Destination host", "dst_ip": "Dst IP", "dst_port": "Dst port",
              "dst_country": "Country", "proto": "Protocol", "app": "Classification", "category": "Category", "duration_ms": "Duration", "rx_bytes": "RX", "tx_bytes": "TX",
              "count": "Count", "node": "Node"}
    # besides the fields we asked for, extractFields also surfaces the stream labels promtail/Loki attach
    exclude = {k: True for k in ("Line", "labels", "tsNs", "id", "src_kind", "dst_kind", "node", "labelTypes", "Src kind", "Dst kind", "Node", "exit_node",
                                 "container_name", "event", "filename", "job", "namespace", "node_name", "pod_name", "service_name", "stream", "detected_level")}
    return [{"id": "limit", "options": {"limitField": "$rows"}},
            {"id": "extractFields", "options": {"source": "labels", "format": "json"}},
            {"id": "organize", "options": {"excludeByName": exclude, "indexByName": {n: i for i, n in enumerate(rename)}, "renameByName": rename}}]


def history_overrides():
    return [unit_override("Duration", "ms"), unit_override("RX", "bytes"), unit_override("TX", "bytes"), by_name("Src port", prop("custom.width", 80)), by_name("Dst port", prop("custom.width", 80))]


def history_dashboard():
    _next_id[0] = 0
    expr = (f'{{job="podflow", event="close"}} {json_fields(*COMMON, ("duration_ms", "duration_ms"), ("tx_bytes", "tx_bytes"), ("rx_bytes", "rx_bytes"), ("count", "count"))} '
            f'{ns_filter()} | src_name=~"$pod" or dst_name=~"$pod" | dst_host=~"(?i).*${{dst}}.*" or dst_ip=~".*${{dst}}.*" or dst_name=~"(?i).*${{dst}}.*"')
    p = [table("Recently closed connections", [lt(expr, lines=1000)], history_tf(), grid(0, 0, 24, 26), history_overrides(), ds=DS_L,
               desc="Newest first. Flows under 1 KB (and all DNS and ICMP) are aggregated per minute into one row with a Count; Duration is last activity minus start (conntrack's own lifetime includes the idle timeout).")]
    vars_ = [customvar("rows", [("25", "25"), ("50", "50"), ("100", "100"), ("250", "250"), ("1000", "1000")], "100", "Rows"),
             textvar("ns", ".*", "Namespace (regex)"), textvar("pod", ".*", "Pod (regex)"), textvar("dst", "", "Destination contains")]
    return dashboard("pf-history", "Connection History", p, vars_, "Recently closed network connections.", time_from="now-1h")


# ================================================================= Tailnet Devices
def tailnet_dashboard():
    _next_id[0] = 0
    sel = 'exit_node=~"$exit_node"'
    dsel = 'exit_node=~"$exit_node", device="$device"'
    p = [
        stat("Throughput (rx + tx)", f'sum(rate(podflow_tailnet_bytes_total{{{sel}}}[5m])) * 8', "bps", grid(0, 0, 6, 4), desc="Traffic of tailnet devices through the selected exit nodes / subnet routers."),
        stat("Active devices", f'count(sum by (device) (rate(podflow_tailnet_bytes_total{{{sel}}}[5m])) > 0)', "none", grid(6, 0, 6, 4)),
        stat("Traffic, last 24h", f'sum(sum_over_time(podflow:tailnet_bytes:increase5m{{{sel}}}[24h]))', "bytes", grid(12, 0, 6, 4), color="blue"),
        stat("Closed flows / min", f'sum(rate(podflow_tailnet_flows_total{{{sel}}}[5m])) * 60', "none", grid(18, 0, 6, 4), decimals=1, color="blue"),
    ]
    dq = [
        pt(f'sum by (device, exit_node) (rate(podflow_tailnet_bytes_total{{direction="rx", {sel}}}[5m])) * 8', "A", instant=True, table=True),
        pt(f'sum by (device, exit_node) (rate(podflow_tailnet_bytes_total{{direction="tx", {sel}}}[5m])) * 8', "B", instant=True, table=True),
        pt(f'sum by (device, exit_node) (sum_over_time(podflow:tailnet_bytes:increase5m{{direction="rx", {sel}}}[24h]))', "C", instant=True, table=True),
        pt(f'sum by (device, exit_node) (sum_over_time(podflow:tailnet_bytes:increase5m{{direction="tx", {sel}}}[24h]))', "D", instant=True, table=True),
        pt(f'sum by (device, exit_node) (sum_over_time(podflow:tailnet_bytes:increase1h{{direction="rx", {sel}}}[7d]))', "E", instant=True, table=True),
        pt(f'sum by (device, exit_node) (sum_over_time(podflow:tailnet_bytes:increase1h{{direction="tx", {sel}}}[7d]))', "F", instant=True, table=True),
        pt(f'sum by (device, exit_node) (sum_over_time(podflow:tailnet_bytes:increase1h{{direction="rx", {sel}}}[30d]))', "G", instant=True, table=True),
        pt(f'sum by (device, exit_node) (sum_over_time(podflow:tailnet_bytes:increase1h{{direction="tx", {sel}}}[30d]))', "H", instant=True, table=True),
    ]
    rename = {"device": "Device", "exit_node": "Exit node", "Value #A": "RX rate", "Value #B": "TX rate", "Value #C": "24h RX", "Value #D": "24h TX",
              "Value #E": "7d RX", "Value #F": "7d TX", "Value #G": "30d RX", "Value #H": "30d TX", "Status": "Status"}
    tf = [{"id": "merge", "options": {}},
          {"id": "calculateField", "options": {"mode": "reduceRow", "reduce": {"reducer": "sum", "include": ["Value #A", "Value #B"]}, "alias": "Status", "replaceFields": False}},
          organize(rename), {"id": "sortBy", "options": {"fields": {}, "sort": [{"field": "RX rate", "desc": True}]}}]
    ov = [unit_override("RX rate", "bps"), unit_override("TX rate", "bps")] + [unit_override(n, "bytes") for n in ("24h RX", "24h TX", "7d RX", "7d TX", "30d RX", "30d TX")]
    ov += [by_name("Status", STATUS_MAP, STATUS_CELL, prop("custom.width", 90)),
           link_override("Device", "Show this device", "/d/pf-tailnet/tailnet-devices?var-device=${__value.raw}&${__url_time_range}")]
    p.append(table("Devices", dq, tf, grid(0, 4, 24, 10), ov,
                   desc="Devices whose traffic left through a Tailscale exit node or subnet router in this cluster (names come from each pod's own tailscaled). Traffic between two devices that never touches the cluster is invisible. Click a device to inspect it below."))
    p += [
        timeseries("Throughput of $device", [pt(f'sum by (direction) (rate(podflow_tailnet_bytes_total{{{dsel}}}[$__rate_interval])) * 8', legend="{{direction}}")], "bps", grid(0, 14, 12, 9),
                   negate="rx", desc="Sent (tx) above the axis, received (rx) below."),
        timeseries("Throughput of $device by application", [pt(f'sum by (application) (rate(podflow_tailnet_bytes_total{{{dsel}}}[$__rate_interval])) * 8', legend="{{application}}")], "bps", grid(12, 14, 12, 9), stack=True),
        donut("Traffic by category (selected range)", f'sum by (category) (sum_over_time(podflow:tailnet_bytes:increase5m{{{dsel}}}[$__range]))', "bytes", grid(0, 23, 8, 9)),
    ]
    flt = '| src_kind="tailnet" | src_name="$device"'
    top_fields = json_fields(("src_kind", "src.kind"), ("src_name", "src.name"), ("dst_host", "dst.host"), ("dst_ip", "dst.ip"), ("app", "app"), ("rx_bytes", "rx_bytes"), ("tx_bytes", "tx_bytes"))
    tq = [lt(f'topk(20, sum by (dst_host, dst_ip, app) (sum_over_time({{job="podflow", event="close"}} {top_fields} {flt} | unwrap rx_bytes [$__range])))', "A", instant=True),
          lt(f'topk(20, sum by (dst_host, dst_ip, app) (sum_over_time({{job="podflow", event="close"}} {top_fields} {flt} | unwrap tx_bytes [$__range])))', "B", instant=True)]
    ttf = [{"id": "labelsToFields", "options": {"mode": "columns"}}, {"id": "merge", "options": {}},
           organize({"dst_host": "Destination host", "dst_ip": "IP", "app": "Classification", "Value #A": "Received", "Value #B": "Sent"}),
           {"id": "sortBy", "options": {"fields": {}, "sort": [{"field": "Received", "desc": True}]}}]
    p.append(table("Top destinations of $device (completed flows, selected range)", tq, ttf, grid(8, 23, 16, 9), [unit_override("Received", "bytes"), unit_override("Sent", "bytes")], ds=DS_L,
                   desc="From closed-flow log lines, so flows still open (long downloads) appear when they end."))
    hist = (f'{{job="podflow", event="close"}} {json_fields(*COMMON, ("duration_ms", "duration_ms"), ("tx_bytes", "tx_bytes"), ("rx_bytes", "rx_bytes"), ("count", "count"), ("exit_node", "exit_node"))} '
            f'{flt}')
    p.append(table("Recent connections of $device", [lt(hist, lines=100)], history_tf(), grid(0, 32, 24, 12), history_overrides(), ds=DS_L))
    vars_ = [qvar("exit_node", "label_values(podflow_tailnet_bytes_total, exit_node)", "Exit node", multi=True, all_=True),
             qvar("device", f'label_values(podflow_tailnet_bytes_total{{exit_node=~"$exit_node"}}, device)', "Device")]
    return dashboard("pf-tailnet", "Tailnet Devices", p, vars_, "Devices using the Tailscale exit nodes and subnet routers.")


DASHBOARDS = {
    "podflow-pods.json": pods_dashboard,
    "podflow-pod.json": pod_dashboard,
    "podflow-categories.json": categories_dashboard,
    "podflow-flows.json": flows_dashboard,
    "podflow-history.json": history_dashboard,
    "podflow-tailnet.json": tailnet_dashboard,
}


def build():
    return {name: fn() for name, fn in DASHBOARDS.items()}


def render_yaml(dashboards):
    out = ["# Generated by gen-podflow-dashboards.py; edit that script and re-run it, not this file.",
           "apiVersion: v1", "kind: ConfigMap", "metadata:", "  name: grafana-dashboard-podflow", "  namespace: monitoring", "  labels:", '    grafana_dashboard: "1"', "data:"]
    for name, d in dashboards.items():
        out.append(f"  {name}: |")
        for line in json.dumps(d, indent=1, sort_keys=False).split("\n"):
            out.append("    " + line)
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    dashboards = build()
    text = render_yaml(dashboards)
    with open(os.path.join(here, "podflow-dashboards.yaml"), "w") as f:
        f.write(text)
    print(f"wrote podflow-dashboards.yaml ({len(text)} bytes, {len(dashboards)} dashboards)")
