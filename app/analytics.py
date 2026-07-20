"""
Graph analytics for Изолят, built on NetworkX.

Positive nominations (cinema + project) form a directed graph. The "who is
often alone" question is aggregated separately as a perceived-isolation vote.
All metrics required by the spec are computed here and shaped for vis-network.
"""
import networkx as nx
from networkx.algorithms import community as nx_community

from .config import POSITIVE_KEYS


def build_analysis(students, choices):
    """
    students: list of {"id": int, "full_name": str}
    choices:  list of {"from_student": int, "to_student": int, "question": str}
    """
    ids = [s["id"] for s in students]
    idset = set(ids)
    n = len(ids)

    G = nx.DiGraph()
    G.add_nodes_from(ids)

    alone_votes = {i: 0 for i in ids}
    edge_weight = {}       # (u, v) -> number of positive nominations
    edge_questions = {}    # (u, v) -> set of question keys

    for c in choices:
        u, v, q = c["from_student"], c["to_student"], c["question"]
        if u not in idset or v not in idset or u == v:
            continue
        if q == "alone":
            alone_votes[v] += 1
        elif q in POSITIVE_KEYS:
            edge_weight[(u, v)] = edge_weight.get((u, v), 0) + 1
            edge_questions.setdefault((u, v), set()).add(q)

    for (u, v), w in edge_weight.items():
        G.add_edge(u, v, weight=w)

    UG = G.to_undirected()

    # -------- graph-level metrics --------
    density = round(nx.density(G), 4) if n > 1 else 0.0
    try:
        reciprocity = round(nx.reciprocity(G) or 0.0, 4)
    except Exception:
        reciprocity = 0.0

    # reciprocated (mutual) pairs
    mutual_pairs = []
    counted = set()
    for (u, v) in edge_weight:
        if (v, u) in edge_weight and (u, v) not in counted and (v, u) not in counted:
            mutual_pairs.append((u, v))
            counted.add((u, v))
    mutual_set = set()
    for (u, v) in mutual_pairs:
        mutual_set.add((u, v))
        mutual_set.add((v, u))

    components = list(nx.connected_components(UG))

    if UG.number_of_edges() == 0:
        communities = [{i} for i in ids]
    else:
        try:
            communities = [set(c) for c in nx_community.greedy_modularity_communities(UG)]
        except Exception:
            communities = [set(c) for c in nx.connected_components(UG)]
    community_of = {}
    for idx, comm in enumerate(communities):
        for node in comm:
            community_of[node] = idx

    try:
        bridges = [tuple(sorted(e)) for e in nx.bridges(UG)]
    except Exception:
        bridges = []
    bridge_set = set()
    for (a, b) in bridges:
        bridge_set.add((a, b))
        bridge_set.add((b, a))

    degree_cent = nx.degree_centrality(G) if n > 1 else {i: 0.0 for i in ids}
    try:
        betweenness = nx.betweenness_centrality(G) if n > 2 else {i: 0.0 for i in ids}
    except Exception:
        betweenness = {i: 0.0 for i in ids}

    in_deg = dict(G.in_degree())
    out_deg = dict(G.out_degree())

    # -------- per-student metrics --------
    per = {}
    isolates = []
    for i in ids:
        recv = in_deg.get(i, 0)
        is_isolate = recv == 0
        if is_isolate:
            isolates.append(i)
        per[i] = {
            "id": i,
            "in_degree": recv,
            "out_degree": out_deg.get(i, 0),
            "mutual": sum(1 for (a, b) in mutual_set if a == i),
            "alone_votes": alone_votes.get(i, 0),
            "degree_centrality": round(degree_cent.get(i, 0.0), 4),
            "betweenness": round(betweenness.get(i, 0.0), 4),
            "community": community_of.get(i, 0),
            "is_isolate": is_isolate,
        }

    possible_pairs = n * (n - 1) / 2 if n > 1 else 1
    cohesion = round(len(mutual_pairs) / possible_pairs, 4) if possible_pairs else 0.0

    # Единый индекс благополучия класса, 0..100. Взвешенное среднее четырёх
    # долей (каждая в [0,1], больше = лучше):
    #   * доля НЕ-изолятов (1 - isolates/n) — вес 0.40: изоляция — главная
    #     проблема, которую ищет «Изолят», поэтому она весит больше всего;
    #   * reciprocity (доля взаимных выборов) — вес 0.30: взаимные связи —
    #     самый сильный положительный сигнал сплочённости;
    #   * cohesion (взаимные пары / все возможные) — вес 0.15;
    #   * density (плотность графа) — вес 0.15.
    # Веса подобраны так, чтобы индекс в первую очередь отражал отсутствие
    # изоляции и наличие взаимности, а плотность/сплочённость лишь уточняли.
    non_isolated = (1 - len(isolates) / n) if n else 0.0
    wellbeing_index = round(100 * (
        0.40 * non_isolated
        + 0.30 * reciprocity
        + 0.15 * cohesion
        + 0.15 * density
    ))
    wellbeing_index = max(0, min(100, wellbeing_index))

    graph_metrics = {
        "students": n,
        "positive_edges": len(edge_weight),
        "mutual_pairs": len(mutual_pairs),
        "isolates": len(isolates),
        "density": density,
        "reciprocity": reciprocity,
        "cohesion": cohesion,
        "wellbeing_index": wellbeing_index,
        "components": len(components),
        "communities": len(communities),
        "bridges": len(bridges),
    }

    # -------- vis-network payload --------
    # Node radius = min-max normalised in_degree into a fixed pixel range, so
    # the graph stays readable for ANY distribution (e.g. one popular student
    # among many with zero incoming). Raw in_degree+1 could make one node
    # dwarf the rest; here the biggest node is always SIZE_MAX and the
    # smallest SIZE_MIN, and if everyone is equal (incl. all-zero) they share
    # a neutral base size.
    SIZE_MIN, SIZE_MAX, SIZE_BASE = 14.0, 40.0, 20.0
    in_values = [in_deg.get(i, 0) for i in ids]
    d_min = min(in_values) if in_values else 0
    d_max = max(in_values) if in_values else 0

    def node_size(value):
        if d_max == d_min:
            return SIZE_BASE
        return round(SIZE_MIN + (value - d_min) / (d_max - d_min) * (SIZE_MAX - SIZE_MIN), 1)

    name_of = {s["id"]: s["full_name"] for s in students}
    vis_nodes = []
    for i in ids:
        m = per[i]
        vis_nodes.append({
            "id": i,
            "label": name_of[i],
            "size": node_size(m["in_degree"]),
            "group": m["community"],
            "isolate": m["is_isolate"],
            "alone_votes": m["alone_votes"],
            "title": (
                name_of[i]
                + "\nВходящие: " + str(m["in_degree"])
                + "\nИсходящие: " + str(m["out_degree"])
                + "\nВзаимные: " + str(m["mutual"])
                + "\n«Часто один»: " + str(m["alone_votes"])
                + "\nBetweenness: " + str(m["betweenness"])
            ),
        })

    vis_edges = []
    for (u, v), w in edge_weight.items():
        vis_edges.append({
            "from": u,
            "to": v,
            "weight": w,
            "mutual": (u, v) in mutual_set,
            "bridge": (u, v) in bridge_set,
            "questions": sorted(edge_questions.get((u, v), [])),
        })

    return {
        "graph_metrics": graph_metrics,
        "per_student": {str(k): v for k, v in per.items()},
        "isolates": isolates,
        "communities": [sorted(list(c)) for c in communities],
        "bridges": [{"from": a, "to": b} for (a, b) in bridges],
        "nodes": vis_nodes,
        "edges": vis_edges,
    }


def metrics_for_student(student_id, students, choices):
    """Convenience: per-student metrics for one survey (used for динамика)."""
    result = build_analysis(students, choices)
    return result["per_student"].get(str(student_id))
