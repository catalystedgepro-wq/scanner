#!/usr/bin/env python3
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import networkx as nx
import matplotlib.pyplot as plt


ROOT = Path("/home/operator/.openclaw/workspace")
OUT_DIR = ROOT / "graphify-out"
AST_GRAPH_PATH = OUT_DIR / "graph.json"


CATEGORY_COLORS = {
    "document": "#6C8AE4",
    "agent": "#D9A441",
    "surface": "#52B788",
    "code": "#9D4EDD",
    "system": "#3FA7D6",
    "concept": "#E76F51",
}


def load_ast_graph() -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    if not AST_GRAPH_PATH.exists():
        return {}, []
    data = json.loads(AST_GRAPH_PATH.read_text(encoding="utf-8"))
    nodes = {node["id"]: node for node in data.get("nodes", [])}
    return nodes, data.get("links", []) or data.get("edges", [])


def file_node_id(ast_nodes: dict[str, dict[str, Any]], path: str) -> str | None:
    normalized = str((ROOT / path).resolve())
    for node_id, node in ast_nodes.items():
        if node.get("source_file") == normalized and node.get("file_type") == "code":
            return node_id
    return None


def base_nodes(ast_nodes: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = [
        {"id": "doc_exec_board", "label": "Execution Board", "category": "document", "source_file": "CEREBRO_EXECUTION_BOARD.md"},
        {"id": "doc_team_workflow", "label": "Team Workflow", "category": "document", "source_file": "CEREBRO_TEAM_WORKFLOW.md"},
        {"id": "doc_experience_audit", "label": "Experience Audit", "category": "document", "source_file": "CEREBRO_EXPERIENCE_AUDIT_AND_AGENT_ASSIGNMENTS.md"},
        {"id": "doc_memory_policy", "label": "Memory Agent Policy", "category": "document", "source_file": "CEREBRO_MEMORY_AGENT_POLICY.md"},
        {"id": "doc_graphify_integration", "label": "Graphify Integration", "category": "document", "source_file": "CEREBRO_GRAPHIFY_INTEGRATION.md"},
        {"id": "doc_graphify_policy", "label": "Graphify Policy", "category": "document", "source_file": "CEREBRO_GRAPHIFY_AGENT_POLICY.md"},
        {"id": "doc_n8n_mvp", "label": "n8n Automation MVP", "category": "document", "source_file": "CEREBRO_N8N_AUTOMATION_MVP.md"},
        {"id": "doc_scanner_refresh", "label": "Scanner Refresh Contract", "category": "document", "source_file": "SCANNER_REFRESH_CONTRACT.md"},
        {"id": "doc_droplet_deploy", "label": "Droplet Deploy Runbook", "category": "document", "source_file": "ops/CEREBRO_DROPLET_DEPLOY.md"},
        {"id": "doc_release_checklist", "label": "Release Checklist", "category": "document", "source_file": "ops/CEREBRO_RELEASE_CHECKLIST.md"},
        {"id": "doc_memory_0408", "label": "Memory 2026-04-08", "category": "document", "source_file": "memory/2026-04-08.md"},
        {"id": "doc_memory_0407", "label": "Memory 2026-04-07", "category": "document", "source_file": "memory/2026-04-07.md"},
        {"id": "goodall", "label": "Goodall", "category": "agent"},
        {"id": "hume", "label": "Hume", "category": "agent"},
        {"id": "peirce", "label": "Peirce", "category": "agent"},
        {"id": "socrates", "label": "Socrates", "category": "agent"},
        {"id": "avicenna", "label": "Avicenna", "category": "agent"},
        {"id": "chandrasekhar", "label": "Chandrasekhar", "category": "agent"},
        {"id": "dirac", "label": "Dirac", "category": "agent"},
        {"id": "zeno", "label": "Zeno", "category": "agent"},
        {"id": "mnemosyne", "label": "Mnemosyne", "category": "agent"},
        {"id": "graphify_agent", "label": "Graphify", "category": "agent"},
        {"id": "scanner_surface", "label": "Public Scanner", "category": "surface"},
        {"id": "hud_surface", "label": "Cerebro HUD", "category": "surface"},
        {"id": "velocity_deck", "label": "Velocity Deck", "category": "surface"},
        {"id": "target_lock_rail", "label": "Target-Lock Rail", "category": "surface"},
        {"id": "node_inspector_surface", "label": "Node Inspector", "category": "surface"},
        {"id": "scanner_handoff_overlay", "label": "Scanner Handoff Overlay", "category": "concept"},
        {"id": "scanner_hud_parity", "label": "Scanner/HUD Parity", "category": "concept"},
        {"id": "authority_motion", "label": "Authority Motion Tranche", "category": "concept"},
        {"id": "field_line_damping", "label": "Field-Line Damping", "category": "concept"},
        {"id": "sympathy_propagation", "label": "Sympathy Propagation", "category": "concept"},
        {"id": "trust_layer", "label": "Trust Layer", "category": "concept"},
        {"id": "memory_stack", "label": "Memory Stack", "category": "concept"},
        {"id": "graph_strategy", "label": "Strategy Graph", "category": "concept"},
        {"id": "everos", "label": "EverOS", "category": "system"},
        {"id": "msa", "label": "MSA", "category": "system"},
        {"id": "n8n", "label": "n8n", "category": "system"},
        {"id": "mnemosyne_gate", "label": "Mnemosyne Gate", "category": "system"},
    ]

    code_map = {
        "code_cerebro_hud": ("hud/src/CerebroHUD.jsx", "CerebroHUD.jsx"),
        "code_velocity_deck": ("hud/src/VelocityDeck.jsx", "VelocityDeck.jsx"),
        "code_node_inspector": ("hud/src/NodeInspector.jsx", "NodeInspector.jsx"),
        "code_generate_seo": ("generate_seo_site.py", "generate_seo_site.py"),
        "code_api_server": ("api_server.py", "api_server.py"),
        "code_run_daily": ("run_daily_sec_catalyst.sh", "run_daily_sec_catalyst.sh"),
        "code_deploy": ("ops/deploy_cerebro_droplet.sh", "deploy_cerebro_droplet.sh"),
        "code_graphify_runner": ("ops/graphify_workspace.sh", "graphify_workspace.sh"),
        "code_everos_client": ("everos_memory_client.py", "everos_memory_client.py"),
        "code_sympathy_logger": ("build_sympathy_logger.py", "build_sympathy_logger.py"),
    }
    for node_id, (path, label) in code_map.items():
        structural_id = file_node_id(ast_nodes, path)
        node = {
            "id": node_id,
            "label": label,
            "category": "code",
            "source_file": path,
        }
        if structural_id:
            ast = ast_nodes[structural_id]
            node["ast_id"] = structural_id
            node["degree"] = ast.get("degree", 0)
            node["community"] = ast.get("community")
        nodes.append(node)
    return nodes


def base_edges() -> list[dict[str, Any]]:
    def edge(source: str, target: str, relation: str, confidence: float = 1.0) -> dict[str, Any]:
        return {
            "source": source,
            "target": target,
            "relation": relation,
            "confidence": confidence,
        }

    return [
        edge("doc_exec_board", "scanner_surface", "prioritizes"),
        edge("doc_exec_board", "hud_surface", "prioritizes"),
        edge("doc_exec_board", "authority_motion", "prioritizes"),
        edge("doc_team_workflow", "goodall", "assigns"),
        edge("doc_team_workflow", "hume", "assigns"),
        edge("doc_team_workflow", "peirce", "assigns"),
        edge("doc_team_workflow", "socrates", "assigns"),
        edge("doc_team_workflow", "avicenna", "assigns"),
        edge("doc_team_workflow", "chandrasekhar", "assigns"),
        edge("doc_team_workflow", "mnemosyne", "assigns"),
        edge("doc_team_workflow", "graphify_agent", "assigns"),
        edge("doc_experience_audit", "authority_motion", "defines"),
        edge("doc_experience_audit", "scanner_hud_parity", "documents"),
        edge("doc_experience_audit", "trust_layer", "documents"),
        edge("doc_memory_policy", "memory_stack", "defines"),
        edge("doc_memory_policy", "everos", "governs"),
        edge("doc_memory_policy", "msa", "governs"),
        edge("doc_graphify_integration", "graph_strategy", "defines"),
        edge("doc_graphify_integration", "graphify_agent", "coordinates"),
        edge("doc_graphify_policy", "graphify_agent", "governs"),
        edge("doc_n8n_mvp", "n8n", "defines"),
        edge("doc_scanner_refresh", "scanner_surface", "governs"),
        edge("doc_droplet_deploy", "code_deploy", "documents"),
        edge("doc_release_checklist", "mnemosyne_gate", "defines"),
        edge("doc_memory_0408", "authority_motion", "documents"),
        edge("doc_memory_0408", "scanner_handoff_overlay", "documents"),
        edge("doc_memory_0408", "scanner_hud_parity", "documents"),
        edge("doc_memory_0408", "trust_layer", "documents"),
        edge("doc_memory_0407", "scanner_surface", "documents"),
        edge("goodall", "scanner_surface", "audits"),
        edge("goodall", "hud_surface", "audits"),
        edge("hume", "authority_motion", "researches"),
        edge("hume", "field_line_damping", "researches"),
        edge("hume", "sympathy_propagation", "researches"),
        edge("peirce", "authority_motion", "implements"),
        edge("peirce", "target_lock_rail", "implements"),
        edge("socrates", "trust_layer", "audits"),
        edge("avicenna", "scanner_hud_parity", "implemented"),
        edge("chandrasekhar", "scanner_surface", "operates"),
        edge("dirac", "code_deploy", "operates"),
        edge("zeno", "memory_stack", "supports"),
        edge("mnemosyne", "everos", "coordinates"),
        edge("mnemosyne", "msa", "coordinates"),
        edge("graphify_agent", "graph_strategy", "builds"),
        edge("scanner_surface", "scanner_handoff_overlay", "hands_off_to"),
        edge("scanner_handoff_overlay", "hud_surface", "hands_off_to"),
        edge("hud_surface", "velocity_deck", "contains"),
        edge("hud_surface", "target_lock_rail", "contains"),
        edge("hud_surface", "node_inspector_surface", "contains"),
        edge("authority_motion", "field_line_damping", "depends_on"),
        edge("authority_motion", "sympathy_propagation", "depends_on"),
        edge("authority_motion", "target_lock_rail", "depends_on"),
        edge("authority_motion", "scanner_handoff_overlay", "depends_on"),
        edge("scanner_hud_parity", "hud_surface", "powers"),
        edge("scanner_hud_parity", "scanner_surface", "powers"),
        edge("trust_layer", "scanner_surface", "protects"),
        edge("trust_layer", "hud_surface", "protects"),
        edge("memory_stack", "everos", "contains"),
        edge("memory_stack", "msa", "contains"),
        edge("memory_stack", "mnemosyne_gate", "depends_on"),
        edge("n8n", "mnemosyne_gate", "coordinates"),
        edge("code_generate_seo", "scanner_surface", "implements"),
        edge("code_cerebro_hud", "hud_surface", "implements"),
        edge("code_velocity_deck", "velocity_deck", "implements"),
        edge("code_node_inspector", "node_inspector_surface", "implements"),
        edge("code_api_server", "hud_surface", "powers"),
        edge("code_api_server", "scanner_hud_parity", "powers"),
        edge("code_run_daily", "scanner_surface", "powers"),
        edge("code_deploy", "hud_surface", "deploys"),
        edge("code_deploy", "scanner_surface", "deploys"),
        edge("code_graphify_runner", "graph_strategy", "builds"),
        edge("code_everos_client", "everos", "implements"),
        edge("code_sympathy_logger", "sympathy_propagation", "feeds"),
        edge("code_cerebro_hud", "field_line_damping", "implements"),
        edge("code_cerebro_hud", "target_lock_rail", "implements"),
        edge("code_cerebro_hud", "sympathy_propagation", "implements"),
        edge("code_generate_seo", "scanner_handoff_overlay", "implements"),
        edge("code_run_daily", "scanner_hud_parity", "supports"),
        edge("code_deploy", "mnemosyne_gate", "checks"),
        edge("graph_strategy", "doc_exec_board", "maps"),
        edge("graph_strategy", "doc_team_workflow", "maps"),
        edge("graph_strategy", "doc_experience_audit", "maps"),
        edge("graph_strategy", "doc_memory_0408", "maps"),
        edge("graph_strategy", "code_cerebro_hud", "maps"),
        edge("graph_strategy", "code_generate_seo", "maps"),
    ]


def build_graph(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> nx.Graph:
    graph = nx.Graph()
    for node in nodes:
        graph.add_node(node["id"], **node)
    for edge in edges:
        graph.add_edge(edge["source"], edge["target"], **edge)
    return graph


def vis_nodes(graph: nx.Graph, pos: dict[str, tuple[float, float]]) -> list[dict[str, Any]]:
    items = []
    for node_id, data in graph.nodes(data=True):
        category = data["category"]
        degree = graph.degree(node_id)
        size = 18 + degree * 1.8
        x, y = pos[node_id]
        items.append(
            {
                "id": node_id,
                "label": data["label"],
                "category": category,
                "title": f"{data['label']} ({category})",
                "color": {
                    "background": CATEGORY_COLORS[category],
                    "border": CATEGORY_COLORS[category],
                    "highlight": {"background": "#ffffff", "border": CATEGORY_COLORS[category]},
                },
                "size": size,
                "x": x * 900,
                "y": y * 900,
                "source_file": data.get("source_file", ""),
                "community_name": category.title(),
                "degree": degree,
            }
        )
    return items


def vis_edges(graph: nx.Graph) -> list[dict[str, Any]]:
    items = []
    for source, target, data in graph.edges(data=True):
        relation = data["relation"]
        dashed = relation in {"depends_on", "coordinates", "maps", "supports"}
        width = 2.4 if relation in {"implements", "powers", "deploys", "hands_off_to"} else 1.6
        items.append(
            {
                "from": source,
                "to": target,
                "label": relation,
                "title": relation,
                "dashes": dashed,
                "width": width,
                "color": {"opacity": 0.5 if dashed else 0.85},
            }
        )
    return items


def write_html(nodes: list[dict[str, Any]], edges: list[dict[str, Any]], stats: dict[str, Any], path: Path) -> None:
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Cerebro Strategy Graph</title>
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<style>
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: #07111b; color: #e7edf5; font-family: "Segoe UI", system-ui, sans-serif; display: flex; height: 100vh; overflow: hidden; }}
  #graph {{ flex: 1; background:
    radial-gradient(circle at top, rgba(99, 135, 187, 0.18), transparent 32%),
    linear-gradient(180deg, #0a1624 0%, #07111b 100%);
  }}
  #sidebar {{ width: 320px; border-left: 1px solid rgba(111, 138, 173, 0.18); background: rgba(8, 18, 30, 0.96); padding: 18px; overflow: auto; }}
  h1 {{ font-size: 16px; letter-spacing: 0.08em; text-transform: uppercase; margin: 0 0 10px; color: #f1f5f9; }}
  .eyebrow {{ font-size: 11px; letter-spacing: 0.18em; text-transform: uppercase; color: #8aa3bf; margin-bottom: 14px; }}
  .card {{ border: 1px solid rgba(111, 138, 173, 0.18); border-radius: 16px; padding: 14px; margin-bottom: 14px; background: rgba(11, 22, 36, 0.78); backdrop-filter: blur(10px); }}
  .stat {{ font-size: 13px; color: #d7e2ef; margin: 6px 0; }}
  .legend-item {{ display: flex; align-items: center; gap: 8px; margin: 8px 0; font-size: 13px; color: #d7e2ef; }}
  .legend-dot {{ width: 12px; height: 12px; border-radius: 50%; }}
  #search {{ width: 100%; padding: 10px 12px; border-radius: 10px; border: 1px solid rgba(111, 138, 173, 0.28); background: rgba(5, 12, 20, 0.7); color: #f8fafc; }}
  #search-results {{ margin-top: 10px; }}
  .search-item {{ padding: 8px 10px; border-radius: 10px; cursor: pointer; margin-bottom: 6px; background: rgba(17, 32, 49, 0.8); }}
  .search-item:hover {{ background: rgba(31, 57, 86, 0.9); }}
  #info {{ font-size: 13px; line-height: 1.5; color: #d7e2ef; }}
  #info b {{ color: #ffffff; }}
</style>
</head>
<body>
  <div id="graph"></div>
  <aside id="sidebar">
    <div class="eyebrow">Combined Strategy Graph</div>
    <h1>Cerebro Authority Map</h1>
    <div class="card">
      <div class="stat"><b>{stats["nodes"]}</b> nodes</div>
      <div class="stat"><b>{stats["edges"]}</b> edges</div>
      <div class="stat"><b>{stats["documents"]}</b> strategy docs</div>
      <div class="stat"><b>{stats["agents"]}</b> active agent lanes</div>
      <div class="stat"><b>{stats["code"]}</b> live code surfaces</div>
    </div>
    <div class="card">
      <input id="search" type="text" placeholder="Search graph...">
      <div id="search-results"></div>
    </div>
    <div class="card">
      <div class="eyebrow">Node Detail</div>
      <div id="info">Click a node to inspect it.</div>
    </div>
    <div class="card">
      <div class="eyebrow">Legend</div>
      {"".join(f'<div class="legend-item"><span class="legend-dot" style="background:{color}"></span>{category.title()}</div>' for category, color in CATEGORY_COLORS.items())}
    </div>
  </aside>
<script>
const RAW_NODES = {json.dumps(nodes)};
const RAW_EDGES = {json.dumps(edges)};
const nodes = new vis.DataSet(RAW_NODES);
const edges = new vis.DataSet(RAW_EDGES);
const container = document.getElementById('graph');
const info = document.getElementById('info');
const network = new vis.Network(container, {{ nodes, edges }}, {{
  physics: false,
  interaction: {{ hover: true, tooltipDelay: 120 }},
  nodes: {{
    shape: 'dot',
    font: {{ color: '#ecf3fb', size: 16, face: 'Segoe UI' }},
    borderWidth: 2
  }},
  edges: {{
    font: {{ color: '#8fb6db', size: 10, strokeWidth: 0 }},
    smooth: {{ enabled: true, type: 'continuous', roundness: 0.18 }}
  }}
}});

network.on('click', (params) => {{
  const id = params.nodes[0];
  if (!id) return;
  const node = nodes.get(id);
  info.innerHTML = `
    <div><b>${{node.label}}</b></div>
    <div>Category: ${{node.category}}</div>
    <div>Degree: ${{node.degree}}</div>
    <div>Source: ${{node.source_file || 'n/a'}}</div>
  `;
}});

const input = document.getElementById('search');
const results = document.getElementById('search-results');
input.addEventListener('input', () => {{
  const q = input.value.trim().toLowerCase();
  results.innerHTML = '';
  if (!q) return;
  RAW_NODES.filter(n => n.label.toLowerCase().includes(q)).slice(0, 12).forEach(node => {{
    const div = document.createElement('div');
    div.className = 'search-item';
    div.textContent = `${{node.label}}`;
    div.onclick = () => {{
      network.focus(node.id, {{ scale: 1.1, animation: {{ duration: 500 }} }});
      network.selectNodes([node.id]);
      info.innerHTML = `
        <div><b>${{node.label}}</b></div>
        <div>Category: ${{node.category}}</div>
        <div>Degree: ${{node.degree}}</div>
        <div>Source: ${{node.source_file || 'n/a'}}</div>
      `;
    }};
    results.appendChild(div);
  }});
}});
</script>
</body>
</html>
"""
    path.write_text(html, encoding="utf-8")


def write_report(graph: nx.Graph, path: Path) -> None:
    category_counts = Counter(data["category"] for _, data in graph.nodes(data=True))
    hub_lines = []
    for node_id, degree in sorted(graph.degree, key=lambda item: item[1], reverse=True)[:10]:
        label = graph.nodes[node_id]["label"]
        hub_lines.append(f"- `{label}`: degree {degree}")

    report = [
        "# Combined Strategy Graph Report",
        "",
        "## Scope",
        "",
        "- combined planning docs, recent memory, active agent lanes, and live Scanner/HUD code surfaces",
        "- optimized for the current authority-motion tranche rather than full-repo noise",
        "",
        "## Category Counts",
        "",
    ]
    for category, count in sorted(category_counts.items()):
        report.append(f"- `{category}`: {count}")
    report.extend(
        [
            "",
            "## Highest-Connectivity Nodes",
            "",
            *hub_lines,
            "",
            "## Immediate Read of the Graph",
            "",
            "- `CerebroHUD.jsx` is the visual center of the authority pass and now directly binds field-line damping, sympathy propagation, and target-lock behavior.",
            "- `generate_seo_site.py` is the Scanner handoff center and remains the critical seam for branded transfer into the HUD.",
            "- `memory/2026-04-08.md`, the execution board, and the experience audit doc are the strongest strategy anchors for the current tranche.",
            "- `Mnemosyne`, `EverOS`, and `MSA` are fully integrated into the strategy layer but still correctly kept behind guarded production boundaries.",
            "- The authority-motion pass is now structurally downstream of parity, trust hardening, and stable deploy paths instead of floating as pure visual polish.",
        ]
    )
    path.write_text("\n".join(report) + "\n", encoding="utf-8")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ast_nodes, _ = load_ast_graph()
    nodes = base_nodes(ast_nodes)
    edges = base_edges()
    graph = build_graph(nodes, edges)
    pos = nx.spring_layout(graph, seed=42, k=1.35 / math.sqrt(max(graph.number_of_nodes(), 1)), iterations=250)

    strategy_nodes = vis_nodes(graph, pos)
    strategy_edges = vis_edges(graph)
    strategy_json = {
        "nodes": strategy_nodes,
        "edges": strategy_edges,
        "stats": {
            "nodes": graph.number_of_nodes(),
            "edges": graph.number_of_edges(),
            "documents": sum(1 for _, d in graph.nodes(data=True) if d["category"] == "document"),
            "agents": sum(1 for _, d in graph.nodes(data=True) if d["category"] == "agent"),
            "code": sum(1 for _, d in graph.nodes(data=True) if d["category"] == "code"),
        },
    }

    (OUT_DIR / "strategy_graph.json").write_text(json.dumps(strategy_json, indent=2), encoding="utf-8")
    write_html(strategy_nodes, strategy_edges, strategy_json["stats"], OUT_DIR / "strategy_graph.html")

    plt.figure(figsize=(16, 16), facecolor="#07111b")
    ax = plt.gca()
    ax.set_facecolor("#07111b")
    for category, color in CATEGORY_COLORS.items():
        group = [node_id for node_id, data in graph.nodes(data=True) if data["category"] == category]
        nx.draw_networkx_nodes(
            graph,
            pos,
            nodelist=group,
            node_color=color,
            node_size=[220 + graph.degree(n) * 35 for n in group],
            linewidths=1.0,
            edgecolors="#ecf3fb",
            alpha=0.9,
        )
    nx.draw_networkx_edges(graph, pos, alpha=0.28, width=1.4, edge_color="#9fb7cc")
    nx.draw_networkx_labels(
        graph,
        pos,
        labels={node_id: data["label"] for node_id, data in graph.nodes(data=True)},
        font_size=8,
        font_color="#f7fbff",
    )
    plt.axis("off")
    plt.tight_layout()
    plt.savefig(OUT_DIR / "strategy_graph.svg", format="svg", bbox_inches="tight", facecolor="#07111b")
    plt.savefig(OUT_DIR / "strategy_graph.png", format="png", dpi=220, bbox_inches="tight", facecolor="#07111b")
    plt.close()

    write_report(graph, OUT_DIR / "STRATEGY_GRAPH_REPORT.md")


if __name__ == "__main__":
    main()
