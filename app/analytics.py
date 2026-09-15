"""
Graph analytics for Изолят, built on NetworkX.

Positive nominations (cinema + project) form a directed graph. The "who is
often alone" question is aggregated separately as a perceived-isolation vote.
All metrics required by the spec are computed here and shaped for vis-network.

ПРИВАТНОСТЬ. Здесь проходит граница между тем, что психологу видеть можно,
и тем, что нельзя.

Положительные выборы (кино, проект) — это и есть социограмма: психолог видит
направленные связи «кто кого выбрал». Без направления метод не работает, и
это нормальная, всем известная часть социометрии.

Негативная номинация «кто часто остаётся один» — другое дело. Она не создаёт
рёбер графа и не атрибутируется автору нигде и никогда: наружу уходит только
число, и только начиная с ALONE_MIN_REPORT. Карточка ученика раньше это
правило нарушала — показывала поимённо, кто отметил ребёнка одиноким, — и
именно это исправлено. Инвариант закреплён тестом tests/test_privacy.py.

ДОСТОВЕРНОСТЬ. Отсутствие входящих выборов означает изоляцию только тогда,
когда достаточная часть класса реально прошла опрос. Если ответили не все,
популярный ребёнок, чьи друзья не ответили, выглядит изолятом. Поэтому
статус «изолят» ставится только при достаточном покрытии, а срез с низкой
явкой помечается как недостоверный.
"""
import networkx as nx
from networkx.algorithms import community as nx_community

from .config import POSITIVE_KEYS

# Доля одноклассников, которые должны были ответить, чтобы отсутствие входящих
# выборов можно было трактовать как изоляцию. Ниже порога ученик получает
# статус "unknown": мы не знаем, изолят он или его просто некому было выбрать.
ISOLATE_MIN_COVERAGE = 0.7

# Пороги достоверности среза по доле прошедших опрос.
RELIABILITY_HIGH = 0.85
RELIABILITY_MEDIUM = 0.7

# Минимальное число номинаций «часто остаётся один», при котором счётчик
# вообще показывается. Одна-две номинации — это мнение одного-двух детей, а не
# сигнал класса; показывать их точным числом значит вешать на ребёнка ярлык с
# чужих слов. Ниже порога интерфейс пишет «менее 3», а не конкретное число.
ALONE_MIN_REPORT = 3


def reliability_of(participation):
    """Достоверность среза по доле прошедших опрос."""
    if participation >= RELIABILITY_HIGH:
        return "high"
    if participation >= RELIABILITY_MEDIUM:
        return "medium"
    return "low"


def _isolation_status(in_degree, coverage):
    """Статус ученика: connected / isolate / unknown.

    "unknown" — честный ответ «данных не хватает», а не мягкая форма «изолят».
    Именно он не даёт психологу пойти работать с ребёнком, у которого нет
    проблемы, просто потому что его друзья не прошли опрос.
    """
    if in_degree > 0:
        return "connected"
    if coverage >= ISOLATE_MIN_COVERAGE:
        return "isolate"
    return "unknown"


def build_analysis(students, choices, responded_ids=None):
    """
    students: list of {"id": int, "full_name": str}
    choices:  list of {"from_student": int, "to_student": int, "question": str}
    responded_ids: id учеников, реально прошедших срез. None — считать, что
        ответили все (юнит-тесты и разбор уже готового графа).
    """
    ids = [s["id"] for s in students]
    idset = set(ids)
    n = len(ids)

    responded = (idset & set(responded_ids)) if responded_ids is not None else set(idset)
    # Пустой класс считаем вырожденным, но достоверным: иначе интерфейс покажет
    # предупреждение о низкой явке там, где просто нет ни одного ученика.
    participation = (len(responded) / n) if n else 1.0
    reliability = reliability_of(participation)

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
    # Плотность и взаимность считаем на подграфе ОТВЕТИВШИХ: только у них была
    # возможность сделать выбор. Если считать по всему списку, класс с явкой 40%
    # арифметически неотличим от реально разобщённого класса — обе метрики
    # падают просто от неявки.
    resp_nodes = sorted(responded)
    RG = G.subgraph(resp_nodes)
    r = len(resp_nodes)

    density = round(nx.density(RG), 4) if r > 1 else 0.0
    try:
        reciprocity = round(nx.reciprocity(RG) or 0.0, 4)
    except Exception:
        reciprocity = 0.0

    # reciprocated (mutual) pairs. Ребро существует только если его автор прошёл
    # опрос, поэтому взаимные пары по построению уже внутри подграфа ответивших.
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
    unknown = []
    for i in ids:
        recv = in_deg.get(i, 0)
        # Сколько одноклассников реально могли выбрать этого ученика.
        possible = len(responded - {i})
        coverage = (possible / (n - 1)) if n > 1 else 0.0
        status = _isolation_status(recv, coverage)
        if status == "isolate":
            isolates.append(i)
        elif status == "unknown":
            unknown.append(i)
        alone = alone_votes.get(i, 0)
        per[i] = {
            "id": i,
            "in_degree": recv,
            "out_degree": out_deg.get(i, 0),
            "mutual": sum(1 for (a, b) in mutual_set if a == i),
            "alone_votes": alone,
            "alone_reportable": alone >= ALONE_MIN_REPORT,
            "responded": i in responded,
            "coverage": round(coverage, 4),
            "degree_centrality": round(degree_cent.get(i, 0.0), 4),
            "betweenness": round(betweenness.get(i, 0.0), 4),
            "community": community_of.get(i, 0),
            "status": status,
            "is_isolate": status == "isolate",
        }

    possible_pairs = r * (r - 1) / 2 if r > 1 else 1
    cohesion = round(len(mutual_pairs) / possible_pairs, 4) if possible_pairs else 0.0

    # Единый индекс благополучия класса, 0..100. Взвешенное среднее четырёх
    # долей (каждая в [0,1], больше = лучше):
    #   * доля НЕ-изолятов среди тех, кого вообще можно классифицировать, —
    #     вес 0.40: изоляция — главная проблема, которую ищет «Изолят»;
    #   * reciprocity (доля взаимных выборов) — вес 0.30: взаимные связи —
    #     самый сильный положительный сигнал сплочённости;
    #   * cohesion (взаимные пары / все возможные) — вес 0.15;
    #   * density (плотность графа) — вес 0.15.
    # Ученики со статусом "unknown" из знаменателя исключены: иначе низкая явка
    # утаскивала бы индекс вниз, изображая проблему там, где просто нет данных.
    classified = [i for i in ids if per[i]["status"] != "unknown"]
    non_isolated = (1 - len(isolates) / len(classified)) if classified else 0.0
    wellbeing_index = round(100 * (
        0.40 * non_isolated
        + 0.30 * reciprocity
        + 0.15 * cohesion
        + 0.15 * density
    ))
    wellbeing_index = max(0, min(100, wellbeing_index))
    if reliability == "low":
        # При низкой явке индекс измеряет неявку, а не класс. Показывать такое
        # число психологу хуже, чем не показывать ничего.
        wellbeing_index = None

    graph_metrics = {
        "students": n,
        "responded": len(responded),
        "participation": round(participation, 4),
        "reliability": reliability,
        "positive_edges": len(edge_weight),
        "mutual_pairs": len(mutual_pairs),
        "isolates": len(isolates),
        "unknown": len(unknown),
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
        alone_txt = str(m["alone_votes"]) if m["alone_reportable"] else "менее " + str(ALONE_MIN_REPORT)
        vis_nodes.append({
            "id": i,
            "label": name_of[i],
            "size": node_size(m["in_degree"]),
            "group": m["community"],
            "isolate": m["is_isolate"],
            "status": m["status"],
            "responded": m["responded"],
            "alone_votes": m["alone_votes"],
            "alone_reportable": m["alone_reportable"],
            "title": (
                name_of[i]
                + "\nВходящие: " + str(m["in_degree"])
                + "\nИсходящие: " + str(m["out_degree"])
                + "\nВзаимные: " + str(m["mutual"])
                + "\n«Часто один»: " + alone_txt
                + "\nBetweenness: " + str(m["betweenness"])
                + ("" if m["responded"] else "\n⚠ Не прошёл опрос")
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
        "unknown": unknown,
        "communities": [sorted(list(c)) for c in communities],
        "bridges": [{"from": a, "to": b} for (a, b) in bridges],
        "nodes": vis_nodes,
        "edges": vis_edges,
    }


def metrics_for_student(student_id, students, choices, responded_ids=None):
    """Convenience: per-student metrics for one survey (used for динамика)."""
    result = build_analysis(students, choices, responded_ids)
    return result["per_student"].get(str(student_id))


def student_survey_summary(student_id, students, choices, responded_ids=None):
    """
    Агрегат по одному ученику за один срез — для карточки ученика.

    Сознательно НЕ возвращает авторство: ни «кто выбрал», ни тем более «кто
    назвал одиноким». Поимённо раскрываются только взаимные пары (см. заголовок
    модуля). Число номинаций «часто один» отдаётся лишь начиная с
    ALONE_MIN_REPORT, иначе None — интерфейс покажет «менее 3».

    Считается за один проход по выборам, без построения графа: карточка
    открывает все срезы сразу, и полный пересчёт betweenness на каждый срез
    там не нужен.
    """
    idset = {s["id"] for s in students}
    n = len(idset)
    responded = (idset & set(responded_ids)) if responded_ids is not None else set(idset)

    out_pos, in_pos = set(), set()
    alone = 0
    for c in choices:
        u, v, q = c["from_student"], c["to_student"], c["question"]
        if u not in idset or v not in idset or u == v:
            continue
        if q == "alone":
            if v == student_id:
                alone += 1
        elif q in POSITIVE_KEYS:
            if u == student_id:
                out_pos.add(v)
            if v == student_id:
                in_pos.add(u)

    mutual = out_pos & in_pos
    possible = len(responded - {student_id})
    coverage = (possible / (n - 1)) if n > 1 else 0.0

    return {
        "in_count": len(in_pos),
        "out_count": len(out_pos),
        "mutual_count": len(mutual),
        "mutual_ids": sorted(mutual),
        "alone_count": alone if alone >= ALONE_MIN_REPORT else None,
        "status": _isolation_status(len(in_pos), coverage),
        "responded": student_id in responded,
        "participation": round(len(responded) / n, 4) if n else 0.0,
        "reliability": reliability_of((len(responded) / n) if n else 1.0),
    }
