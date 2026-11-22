#!/usr/bin/env python3
"""
Generates a standalone, dependency-free interactive HTML dashboard
for CloudServe Support FDE Capstone demo and audit review.

Usage:
    python demo/generate_dashboard.py
    open demo/dashboard.html
"""

import json
import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO_OUT = REPO_ROOT / "demo" / "out"
VAL_OUT = REPO_ROOT / "evaluation" / "validation_run"
OUTPUT_HTML = REPO_ROOT / "demo" / "dashboard.html"


def load_dataset_data(data_dir: Path):
    if not data_dir.exists():
        return None
    
    results = []
    results_file = data_dir / "results.jsonl"
    if results_file.exists():
        with open(results_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    results.append(json.loads(line))
                    
    metrics = {}
    metrics_file = data_dir / "metrics.json"
    if metrics_file.exists():
        with open(metrics_file, "r", encoding="utf-8") as f:
            metrics = json.load(f)
            
    decisions = []
    db_file = data_dir / "decisions.db"
    if db_file.exists():
        conn = sqlite3.connect(db_file)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT ticket_id, stage, action_taken, reason, requirement_ids, timestamp FROM decisions ORDER BY decision_id")
        decisions = [dict(r) for r in cur.fetchall()]
        conn.close()
        
    return {
        "results": results,
        "metrics": metrics,
        "decisions": decisions
    }


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CloudServe Support — Decision & Audit Dashboard</title>
<style>
  :root {
    --bg: #0c1017;
    --card-bg: #161b22;
    --border: #30363d;
    --text-primary: #f0f6fc;
    --text-muted: #8b949e;
    --accent-blue: #58a6ff;
    --accent-green: #3fb950;
    --accent-yellow: #d29922;
    --accent-red: #f85149;
    --accent-purple: #bc8cff;
    --badge-bg: #21262d;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background: var(--bg);
    color: var(--text-primary);
    line-height: 1.5;
    padding: 24px;
  }
  .container { max-width: 1300px; margin: 0 auto; }
  
  /* Header */
  header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid var(--border);
    padding-bottom: 18px;
    margin-bottom: 24px;
  }
  .brand { display: flex; align-items: center; gap: 14px; }
  .logo-badge {
    background: linear-gradient(135deg, #1f6feb, #8957e5);
    color: white;
    font-weight: 700;
    font-size: 13px;
    padding: 6px 12px;
    border-radius: 6px;
    letter-spacing: 0.5px;
  }
  h1 { font-size: 22px; font-weight: 600; color: #fff; }
  .subtitle { font-size: 13px; color: var(--text-muted); }
  
  .mode-switch {
    display: flex;
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 4px;
    gap: 4px;
  }
  .mode-btn {
    background: none;
    border: none;
    color: var(--text-muted);
    padding: 6px 14px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 13px;
    font-weight: 500;
    transition: all 0.2s;
  }
  .mode-btn.active {
    background: #21262d;
    color: var(--text-primary);
    border: 1px solid var(--border);
  }

  /* Pipeline Banner */
  .pipeline-card {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px 20px;
    margin-bottom: 24px;
  }
  .pipeline-title { font-size: 11px; text-transform: uppercase; color: var(--text-muted); font-weight: 700; margin-bottom: 12px; letter-spacing: 0.8px; }
  .pipeline-steps {
    display: flex;
    align-items: center;
    gap: 8px;
    overflow-x: auto;
  }
  .step {
    background: #0d1117;
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 12px;
    text-align: center;
    flex-shrink: 0;
  }
  .step-label { font-weight: 600; color: var(--text-primary); }
  .step-detail { font-size: 11px; color: var(--text-muted); margin-top: 2px; }
  .arrow { color: var(--text-muted); font-weight: bold; flex-shrink: 0; }

  /* Metric KPI Grid */
  .kpi-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 16px;
    margin-bottom: 24px;
  }
  .kpi-card {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px;
  }
  .kpi-title { font-size: 11px; color: var(--text-muted); font-weight: 600; text-transform: uppercase; }
  .kpi-value { font-size: 26px; font-weight: 700; margin-top: 4px; }
  .kpi-sub { font-size: 11px; color: var(--text-muted); margin-top: 4px; }
  
  .val-green { color: var(--accent-green); }
  .val-yellow { color: var(--accent-yellow); }
  .val-red { color: var(--accent-red); }
  .val-blue { color: var(--accent-blue); }

  /* Filter bar */
  .toolbar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
  }
  .filter-group { display: flex; gap: 8px; }
  .filter-btn {
    background: var(--card-bg);
    border: 1px solid var(--border);
    color: var(--text-muted);
    padding: 6px 12px;
    font-size: 12px;
    border-radius: 6px;
    cursor: pointer;
  }
  .filter-btn.active {
    background: #238636;
    color: white;
    border-color: #2ea043;
  }

  /* Ticket Cards */
  .ticket-list { display: flex; flex-direction: column; gap: 14px; margin-bottom: 32px; }
  .ticket-card {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    overflow: hidden;
    transition: border-color 0.2s;
  }
  .ticket-card:hover { border-color: #58a6ff66; }
  .ticket-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 16px;
    background: #1b212a;
    border-bottom: 1px solid var(--border);
  }
  .ticket-meta { display: flex; align-items: center; gap: 10px; }
  .ticket-id { font-family: monospace; font-weight: 700; font-size: 14px; }
  .badge {
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 12px;
    font-weight: 600;
    text-transform: uppercase;
  }
  .badge-auto { background: #1f6feb22; color: #58a6ff; border: 1px solid #1f6feb55; }
  .badge-escalate { background: #d2992222; color: #e3b341; border: 1px solid #d2992255; }
  .badge-block { background: #f8514922; color: #ff7b72; border: 1px solid #f8514955; }
  .badge-channel { background: #21262d; color: var(--text-muted); }

  .ticket-body { padding: 16px; display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  @media (max-width: 900px) { .ticket-body { grid-template-columns: 1fr; } }

  .section-title { font-size: 11px; text-transform: uppercase; color: var(--text-muted); font-weight: 700; margin-bottom: 6px; letter-spacing: 0.5px; }
  .inquiry-box { background: #0d1117; padding: 12px; border-radius: 6px; border: 1px solid var(--border); font-size: 13px; color: #e6edf3; }
  .details-box { background: #0d1117; padding: 12px; border-radius: 6px; border: 1px solid var(--border); font-size: 12px; }
  
  .detail-row { display: flex; justify-content: space-between; padding: 4px 0; border-bottom: 1px solid #21262d; }
  .detail-row:last-child { border-bottom: none; }
  .detail-key { color: var(--text-muted); }
  .detail-val { font-family: monospace; font-weight: 600; }

  .guardrail-checks { display: flex; gap: 6px; margin-top: 10px; flex-wrap: wrap; }
  .check-tag {
    font-size: 11px;
    padding: 2px 6px;
    border-radius: 4px;
    background: #21262d;
  }
  .check-pass { color: var(--accent-green); }
  .check-fail { color: var(--accent-red); font-weight: bold; background: #f8514922; border: 1px solid #f8514955; }

  /* Decision Log Table */
  .log-card {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px;
    margin-top: 32px;
  }
  table { width: 100%; border-collapse: collapse; font-size: 12px; }
  th { text-align: left; padding: 10px; color: var(--text-muted); border-bottom: 1px solid var(--border); text-transform: uppercase; font-size: 11px; }
  td { padding: 10px; border-bottom: 1px solid #21262d; font-family: monospace; }
  tr:hover td { background: #1f242c; }
</style>
</head>
<body>
<div class="container">
  <header>
    <div class="brand">
      <div class="logo-badge">FDE CAPSTONE</div>
      <div>
        <h1>CloudServe Support — Decision & Audit Dashboard</h1>
        <div class="subtitle">Answering only what documentation can prove • Deterministic routing • Traceable governance</div>
      </div>
    </div>
    <div class="mode-switch">
      <button class="mode-btn active" id="btn-demo" onclick="switchDataset('demo')">6 Demo Tickets</button>
      <button class="mode-btn" id="btn-val" onclick="switchDataset('validation')">80 Validation Tickets</button>
    </div>
  </header>

  <!-- High-Level Pipeline -->
  <div class="pipeline-card">
    <div class="pipeline-title">Deterministic Architecture Pipeline</div>
    <div class="pipeline-steps">
      <div class="step">
        <div class="step-label">1. Ingest</div>
        <div class="step-detail">4 Channels Normalised</div>
      </div>
      <div class="arrow">&rarr;</div>
      <div class="step">
        <div class="step-label">2. Prompt Injection Check</div>
        <div class="step-detail">Regex + Rules (Pre-routing)</div>
      </div>
      <div class="arrow">&rarr;</div>
      <div class="step">
        <div class="step-label">3. Local Classifier</div>
        <div class="step-detail">Intent & P(safe to auto)</div>
      </div>
      <div class="arrow">&rarr;</div>
      <div class="step">
        <div class="step-label">4. Policy Router</div>
        <div class="step-detail">5 Must-Escalate ≥ 0.85</div>
      </div>
      <div class="arrow">&rarr;</div>
      <div class="step">
        <div class="step-label">5. LLM Draft (Citations)</div>
        <div class="step-detail">MiniLM + Strict Sentence Cite</div>
      </div>
      <div class="arrow">&rarr;</div>
      <div class="step">
        <div class="step-label">6. Release Checks</div>
        <div class="step-detail">PII, Commitments, Grounding</div>
      </div>
      <div class="arrow">&rarr;</div>
      <div class="step">
        <div class="step-label">7. Log & Dispatch</div>
        <div class="step-detail">SQLite Audit Trail</div>
      </div>
    </div>
  </div>

  <!-- KPI Metrics -->
  <div class="kpi-grid" id="kpi-grid"></div>

  <!-- Ticket Browser -->
  <div class="toolbar">
    <div class="filter-group">
      <button class="filter-btn active" onclick="filterTickets('all')">All Tickets (<span id="count-all">0</span>)</button>
      <button class="filter-btn" onclick="filterTickets('auto_respond')">Auto-Answered (<span id="count-auto">0</span>)</button>
      <button class="filter-btn" onclick="filterTickets('escalate')">Escalated (<span id="count-esc">0</span>)</button>
      <button class="filter-btn" onclick="filterTickets('block')">Blocked by Guardrail (<span id="count-block">0</span>)</button>
    </div>
    <div style="font-size:12px; color:var(--text-muted);" id="current-dataset-label">Showing Demo Tickets</div>
  </div>

  <div class="ticket-list" id="ticket-list"></div>

  <!-- Decision Log -->
  <div class="log-card">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
      <h3 style="font-size:14px; font-weight:600;">SQLite Decision Log (Reconciled with Audit Trail)</h3>
      <span style="font-size:12px; color:var(--text-muted);">Table: decisions.db</span>
    </div>
    <table>
      <thead>
        <tr>
          <th>Ticket</th>
          <th>Stage</th>
          <th>Action</th>
          <th>Requirement</th>
          <th>Reason</th>
        </tr>
      </thead>
      <tbody id="decision-table-body"></tbody>
    </table>
  </div>
</div>

<script>
const data = __DATA_PAYLOAD__;
let currentMode = "demo";
let currentFilter = "all";

function switchDataset(mode) {
  currentMode = mode;
  document.getElementById("btn-demo").classList.toggle("active", mode === "demo");
  document.getElementById("btn-val").classList.toggle("active", mode === "validation");
  document.getElementById("current-dataset-label").innerText = mode === "demo" ? "Showing Demo Run (6 tickets)" : "Showing Validation Run (80 tickets)";
  render();
}

function filterTickets(filter) {
  currentFilter = filter;
  document.querySelectorAll(".filter-btn").forEach(b => b.classList.remove("active"));
  event.target.classList.add("active");
  renderTickets();
}

function render() {
  const dataset = data[currentMode];
  if (!dataset) return;
  
  // Render KPIs
  const vol = dataset.metrics.volume || {};
  const gov = dataset.metrics.governance || {};
  const tech = dataset.metrics.technical || {};
  
  const total = vol.processed || 0;
  const auto = vol.auto_answered || 0;
  const esc = vol.escalated || 0;
  const blocked = vol.blocked || 0;
  const piiLeaks = gov.private_data_in_sent_replies ?? 0;
  const unsupp = tech.sent_unsupported_sentence_pct ?? 0;
  
  document.getElementById("count-all").innerText = total;
  document.getElementById("count-auto").innerText = auto;
  document.getElementById("count-esc").innerText = esc;
  document.getElementById("count-block").innerText = blocked;

  document.getElementById("kpi-grid").innerHTML = `
    <div class="kpi-card">
      <div class="kpi-title">Total Tickets</div>
      <div class="kpi-value">${total}</div>
      <div class="kpi-sub">100% processed unattended</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-title">Auto-Answered</div>
      <div class="kpi-value val-blue">${auto} (${total ? ((auto/total)*100).toFixed(1) : 0}%)</div>
      <div class="kpi-sub">≥ 0.85 P(safe) threshold</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-title">Escalated to Agent</div>
      <div class="kpi-value val-yellow">${esc} (${total ? ((esc/total)*100).toFixed(1) : 0}%)</div>
      <div class="kpi-sub">Packets with topic & docs</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-title">Guardrail Blocks</div>
      <div class="kpi-value val-red">${blocked}</div>
      <div class="kpi-sub">Injection & Grounding fails</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-title">PII Leaks Sent</div>
      <div class="kpi-value val-green">${piiLeaks}</div>
      <div class="kpi-sub">Hard safety zero</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-title">Unsupported in Sent</div>
      <div class="kpi-value val-green">${unsupp}%</div>
      <div class="kpi-sub">Release gate: fail-closed</div>
    </div>
  `;

  renderTickets();
  renderDecisions();
}

function renderTickets() {
  const dataset = data[currentMode];
  const listEl = document.getElementById("ticket-list");
  listEl.innerHTML = "";
  
  const results = dataset.results || [];
  const filtered = results.filter(t => {
    if (currentFilter === "all") return true;
    if (currentFilter === "auto_respond") return t.final === "auto_respond";
    if (currentFilter === "escalate") return t.final === "escalate";
    if (currentFilter === "block") return t.final === "block";
    return true;
  });

  if (filtered.length === 0) {
    listEl.innerHTML = "<div style='color:var(--text-muted); padding:20px; text-align:center;'>No tickets matching filter.</div>";
    return;
  }

  filtered.forEach(t => {
    let actionBadge = `<span class="badge badge-auto">AUTO-RESPOND</span>`;
    if (t.final === "escalate") actionBadge = `<span class="badge badge-escalate">ESCALATE</span>`;
    if (t.final === "block") actionBadge = `<span class="badge badge-block">GUARDRAIL BLOCK</span>`;

    const checks = (t.validation && t.validation.checks) || {};
    const checkBadges = Object.entries(checks).map(([k, v]) => {
      const cls = v === "pass" ? "check-pass" : (v === "fail" ? "check-fail" : "");
      return `<span class="check-tag ${cls}">${k}: ${v}</span>`;
    }).join(" ");

    let responseContent = "";
    if (t.reply) {
      responseContent = `
        <div class="section-title" style="margin-top:10px;">Sent Automated Reply</div>
        <div class="inquiry-box" style="border-left: 3px solid var(--accent-green); white-space:pre-wrap;">${t.reply}</div>
      `;
    } else if (t.packet) {
      const articles = (t.packet.articles || []).join(", ") || "None";
      responseContent = `
        <div class="section-title" style="margin-top:10px;">Escalation Packet Given to Agent</div>
        <div class="inquiry-box" style="border-left: 3px solid var(--accent-yellow);">
          <div><strong>Summary:</strong> ${t.packet.summary || 'N/A'}</div>
          <div><strong>Reason:</strong> ${t.packet.uncertainty || t.route?.reason || 'Policy rule'}</div>
          <div><strong>Suggested Docs:</strong> ${articles}</div>
        </div>
      `;
    }

    const card = document.createElement("div");
    card.className = "ticket-card";
    card.innerHTML = `
      <div class="ticket-header">
        <div class="ticket-meta">
          <span class="ticket-id">${t.ticket_id}</span>
          ${actionBadge}
          <span class="badge badge-channel">${t.channel}</span>
          <span style="font-size:12px; color:var(--text-muted);">${t.customer_tier} • ${t.customer_region}</span>
        </div>
        <div style="font-size:12px; color:var(--accent-blue); font-family:monospace;">
          P(safe): ${t.classification?.p_auto ? (t.classification.p_auto * 100).toFixed(1) + '%' : 'N/A'}
        </div>
      </div>
      <div class="ticket-body">
        <div>
          <div class="section-title">Inbound Inquiry / Context</div>
          <div class="inquiry-box">
            ${t.packet?.summary || t.route?.reason || 'Ticket body ingested from ' + t.channel}
          </div>
          ${responseContent}
        </div>
        <div>
          <div class="section-title">Pipeline Diagnostics & Reasoning</div>
          <div class="details-box">
            <div class="detail-row"><span class="detail-key">Predicted Topic:</span><span class="detail-val">${t.classification?.intent?.value || 'N/A'} (${t.classification?.intent?.confidence ? (t.classification.intent.confidence*100).toFixed(1)+'%' : 'N/A'})</span></div>
            <div class="detail-row"><span class="detail-key">Policy Decision:</span><span class="detail-val">${t.route?.action || 'N/A'}</span></div>
            <div class="detail-row"><span class="detail-key">Requirement IDs:</span><span class="detail-val">${(t.route?.requirement_ids || []).join(', ') || 'N/A'}</span></div>
            <div class="detail-row"><span class="detail-key">Route Reason:</span><span class="detail-val" style="font-family:sans-serif; font-size:11px;">${t.route?.reason || 'N/A'}</span></div>
            <div class="detail-row"><span class="detail-key">Retrieved Chunks:</span><span class="detail-val">${(t.hits || []).length} hits</span></div>
          </div>
          <div class="section-title" style="margin-top:12px;">Release Guardrails</div>
          <div class="guardrail-checks">
            ${checkBadges || '<span style="color:var(--text-muted);">No release checks needed</span>'}
          </div>
        </div>
      </div>
    `;
    listEl.appendChild(card);
  });
}

function renderDecisions() {
  const dataset = data[currentMode];
  const tbody = document.getElementById("decision-table-body");
  tbody.innerHTML = "";
  const decisions = (dataset.decisions || []).slice(0, 30);
  
  decisions.forEach(d => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td style="color:var(--accent-blue);">${d.ticket_id}</td>
      <td>${d.stage}</td>
      <td><span class="badge ${d.action_taken === 'auto_respond' ? 'badge-auto' : (d.action_taken === 'escalate' ? 'badge-escalate' : 'badge-block')}">${d.action_taken}</span></td>
      <td style="color:var(--accent-purple);">${d.requirement_ids || ''}</td>
      <td style="color:#c9d1d9;">${d.reason || ''}</td>
    `;
    tbody.appendChild(tr);
  });
}

// Initialize
render();
</script>
</body>
</html>
"""


def build_dashboard():
    demo_data = load_dataset_data(DEMO_OUT)
    val_data = load_dataset_data(VAL_OUT)
    
    dashboard_payload = {
        "demo": demo_data,
        "validation": val_data
    }
    
    html_content = HTML_TEMPLATE.replace("__DATA_PAYLOAD__", json.dumps(dashboard_payload))
    
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html_content)
        
    print(f"Generated standalone dashboard: {OUTPUT_HTML}")


if __name__ == "__main__":
    build_dashboard()
