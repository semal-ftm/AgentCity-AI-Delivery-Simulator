"""The simulated city: a road network graph plus the landmarks drawn on the 2D map.

All data is fictional. The city is a grid of streets measured in map *tiles*;
one tile is 0.2 km, so every edge length (and therefore every route length,
travel time and cost) is derived from the same geometry the map draws.

Nodes are intersections, edges are road segments. Every edge inherits the
attributes of its street: road type, speed limit, base safety, traffic zone and
whether it floods in the rain. Candidate delivery routes A-D are node paths
through this graph from the restaurant to the customer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

TILE_KM = 0.2
MAP_W, MAP_H = 34, 23

Node = Tuple[int, int]


@dataclass(frozen=True)
class Street:
    id: str
    name: str
    axis: str              # "h" (constant y) or "v" (constant x)
    at: int                # the y (h) or x (v) coordinate in tiles
    kind: str              # expressway | arterial | boulevard | street | lane | link
    speed_kmh: float       # free-flow speed
    safety: float          # base safety 0..1 in clear daylight
    zone: str              # traffic zone (traffic level is set per zone)
    span: Tuple[int, int]  # first and last coordinate along the street
    flood_prone: bool = False
    lanes: int = 2


STREETS: List[Street] = [
    Street("expressway", "Northern Expressway", "h", 1, "expressway", 80, 0.93, "expressway", (4, 29), lanes=3),
    Street("ring", "Canal Ring Road", "h", 4, "arterial", 46, 0.88, "ring", (0, 33)),
    Street("gulberg", "Gulberg Street", "h", 8, "street", 30, 0.84, "midtown", (0, 33)),
    Street("main", "Main Boulevard", "h", 12, "boulevard", 40, 0.80, "downtown", (0, 33), lanes=3),
    Street("lanes", "Old Town Lanes", "h", 16, "lane", 30, 0.74, "oldtown", (0, 33), flood_prone=True, lanes=1),
    Street("bazaar", "Bazaar Road", "h", 20, "street", 28, 0.80, "bazaar", (0, 33)),
    Street("west", "Canal Link Road", "v", 4, "link", 36, 0.86, "links", (1, 22)),
    Street("liberty", "Liberty Street", "v", 9, "street", 28, 0.82, "midtown", (0, 22)),
    Street("mall", "Mall Road", "v", 14, "street", 28, 0.82, "midtown", (0, 22)),
    Street("jail", "Jail Road", "v", 19, "street", 28, 0.82, "midtown", (0, 22)),
    Street("ferozpur", "Ferozpur Road", "v", 24, "street", 28, 0.82, "midtown", (0, 22)),
    Street("east", "Airport Link Road", "v", 29, "link", 36, 0.86, "links", (1, 22)),
]
STREET = {s.id: s for s in STREETS}

# Intersections with traffic lights. Main Boulevard is signalled at every crossing;
# the ring road only at its two major junctions; old-town lanes have none.
SIGNALS: List[Node] = [(9, 12), (14, 12), (19, 12), (24, 12), (14, 4), (24, 4), (9, 8), (19, 8), (14, 20)]
TOLL_EDGE: Tuple[Node, Node] = ((14, 1), (19, 1))
TOLL_CU = 3.0

RESTAURANT: Node = (4, 12)
CUSTOMER: Node = (29, 12)

ROUTE_PATHS: Dict[str, List[Node]] = {
    "A": [(4, 12), (9, 12), (14, 12), (19, 12), (24, 12), (29, 12)],
    "B": [(4, 12), (4, 8), (4, 4), (9, 4), (14, 4), (19, 4), (24, 4), (29, 4), (29, 8), (29, 12)],
    "C": [(4, 12), (4, 16), (9, 16), (14, 16), (19, 16), (24, 16), (29, 16), (29, 12)],
    "D": [(4, 12), (4, 8), (4, 4), (4, 1), (9, 1), (14, 1), (19, 1), (24, 1), (29, 1), (29, 4), (29, 8), (29, 12)],
}
ROUTE_META = {
    "A": {"name": "Main Boulevard (downtown)", "key_zone": "downtown",
          "summary": "Shortest route, straight through downtown; four traffic lights."},
    "B": {"name": "Canal Ring Road", "key_zone": "ring",
          "summary": "Longer arterial ring around the centre; wide, well-lit lanes."},
    "C": {"name": "Old Town Lanes", "key_zone": "oldtown",
          "summary": "Narrow back lanes with no lights, but poor drainage: floods in rain."},
    "D": {"name": "Northern Expressway (toll)", "key_zone": "expressway",
          "summary": "Longest route but fastest road; charges a toll; risky at speed in the wet."},
}
ROUTE_IDS = list(ROUTE_PATHS)

# A second, optional delivery from the top of the map to the bottom. It uses the same kinds of
# road as delivery 1 (downtown boulevard, ring road, flood-prone lanes, toll expressway), so the
# three test situations mean the same thing on both deliveries.
DELIVERIES: Dict[int, dict] = {
    1: {"title": "Delivery 1 (default)", "from": "Restaurant (west)", "to": "Customer (east)", "direction": "west to east",
        "restaurant": RESTAURANT, "customer": CUSTOMER, "paths": ROUTE_PATHS, "meta": ROUTE_META,
        "rest_pos": (1.6, 9.75), "cust_pos": (31.4, 14.45), "rest_turn": 0, "extra_min": 0,
        "restaurant_name": None, "customer_name": None},
    2: {"title": "Delivery 2 (new)", "from": "Food Street Kitchen (north)", "to": "Johar Town (south)", "direction": "top to bottom",
        "restaurant": (19, 4), "customer": (9, 20),
        "paths": {
            "A": [(19, 4), (19, 8), (19, 12), (14, 12), (9, 12), (9, 16), (9, 20)],
            "B": [(19, 4), (14, 4), (9, 4), (4, 4), (4, 8), (4, 12), (4, 16), (4, 20), (9, 20)],
            "C": [(19, 4), (19, 8), (19, 12), (19, 16), (14, 16), (9, 16), (9, 20)],
            "D": [(19, 4), (19, 1), (14, 1), (9, 1), (4, 1), (4, 4), (4, 8), (4, 12), (4, 16), (4, 20), (9, 20)],
        },
        "meta": {
            "A": {"name": "Main Boulevard (downtown)", "key_zone": "downtown",
                  "summary": "Shortest route: down Jail Road, across downtown on Main Boulevard, then down Liberty Street; four traffic lights."},
            "B": {"name": "Canal Ring Road", "key_zone": "ring",
                  "summary": "West along the ring road, then down the Canal Link Road; longer but wide and well lit."},
            "C": {"name": "Old Town Lanes", "key_zone": "oldtown",
                  "summary": "Down Jail Road and through the old-town lanes; as short as A but the lanes flood in rain."},
            "D": {"name": "Northern Expressway (toll)", "key_zone": "expressway",
                  "summary": "Up to the expressway, west at high speed, then down the Canal Link Road; longest, toll, slippery in rain."},
        },
        "rest_pos": (21.5, 6.25), "cust_pos": (7.4, 21.7), "rest_turn": 1,
        "extra_min": 3,          # a longer trip, so the customer is promised 3 more minutes
        "restaurant_name": "Food Street Kitchen", "customer_name": "Johar Town, House 18"},
}
DELIVERY_IDS = list(DELIVERIES)


def delivery_paths(delivery: int = 1) -> Dict[str, List[Node]]:
    return DELIVERIES[delivery]["paths"]


def delivery_meta(delivery: int = 1) -> Dict[str, dict]:
    return DELIVERIES[delivery]["meta"]


@dataclass(frozen=True)
class Edge:
    a: Node
    b: Node
    street: Street

    @property
    def length_km(self) -> float:
        return round((abs(self.a[0] - self.b[0]) + abs(self.a[1] - self.b[1])) * TILE_KM, 3)

    @property
    def key(self) -> Tuple[Node, Node]:
        return edge_key(self.a, self.b)


def edge_key(a: Node, b: Node) -> Tuple[Node, Node]:
    return (a, b) if a <= b else (b, a)


@dataclass
class RoadNetwork:
    """Undirected graph of intersections (nodes) and road segments (edges)."""
    nodes: List[Node] = field(default_factory=list)
    edges: Dict[Tuple[Node, Node], Edge] = field(default_factory=dict)
    adj: Dict[Node, List[Node]] = field(default_factory=dict)

    def add_edge(self, a: Node, b: Node, street: Street) -> None:
        e = Edge(a, b, street)
        self.edges[e.key] = e
        for n in (a, b):
            if n not in self.adj:
                self.adj[n] = []
                self.nodes.append(n)
        self.adj[a].append(b)
        self.adj[b].append(a)

    def edge(self, a: Node, b: Node) -> Edge:
        return self.edges[edge_key(a, b)]

    def path_edges(self, path: List[Node]) -> List[Edge]:
        """Edges along a node path. Raises KeyError if the path is not continuous."""
        return [self.edge(a, b) for a, b in zip(path, path[1:])]

    def is_valid_path(self, path: List[Node], start: Node, goal: Node) -> bool:
        if not path or path[0] != start or path[-1] != goal or len(set(path)) != len(path):
            return False
        return all(edge_key(a, b) in self.edges for a, b in zip(path, path[1:]))


def build_network() -> RoadNetwork:
    """Split every street into edges at each point where it crosses another street."""
    net = RoadNetwork()
    for s in STREETS:
        cuts = set(s.span)
        for o in STREETS:
            if o.axis != s.axis and o.span[0] <= s.at <= o.span[1] and s.span[0] <= o.at <= s.span[1]:
                cuts.add(o.at)
        pts = sorted(cuts)
        for p, q in zip(pts, pts[1:]):
            a, b = ((p, s.at), (q, s.at)) if s.axis == "h" else ((s.at, p), (s.at, q))
            net.add_edge(a, b, s)
    return net


NETWORK = build_network()


def world_json() -> dict:
    """Everything the browser needs to draw the city, straight from the graph above."""
    return {
        "tile_km": TILE_KM, "w": MAP_W, "h": MAP_H,
        "streets": [{"id": s.id, "name": s.name, "axis": s.axis, "at": s.at, "kind": s.kind, "span": s.span,
                     "lanes": s.lanes, "speed": s.speed_kmh, "safety": s.safety, "zone": s.zone,
                     "flood_prone": s.flood_prone} for s in STREETS],
        "nodes": NETWORK.nodes,
        "edges": [{"a": e.a, "b": e.b, "street": e.street.id, "zone": e.street.zone, "km": e.length_km}
                  for e in NETWORK.edges.values()],
        "signals": SIGNALS, "toll": {"edge": TOLL_EDGE, "cu": TOLL_CU},
        "restaurant": RESTAURANT, "customer": CUSTOMER,
        "routes": {rid: {"path": p, **ROUTE_META[rid]} for rid, p in ROUTE_PATHS.items()},
        "deliveries": {d: {k: v for k, v in D.items() if k not in ("paths", "meta")} |
                          {"routes": {rid: {"path": p, **D["meta"][rid]} for rid, p in D["paths"].items()}}
                       for d, D in DELIVERIES.items()},
    }
