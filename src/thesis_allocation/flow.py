"""Small deterministic minimum-cost maximum-flow implementation."""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class Edge:
    """One directed residual-graph edge."""

    to: int
    reverse_index: int
    capacity: int
    cost: int
    initial_capacity: int
    data: Any = None


class MinCostFlow:
    """Successive shortest augmenting paths with Johnson potentials.

    Forward edge costs must be non-negative. Residual reverse edges are created
    automatically.
    """

    def __init__(self, node_count: int):
        self.graph: list[list[Edge]] = [[] for _ in range(node_count)]

    def add_edge(
        self,
        source: int,
        target: int,
        capacity: int,
        cost: int,
        *,
        data: Any = None,
    ) -> None:
        """Add one capacitated edge and its residual reverse edge."""

        if capacity < 0:
            raise ValueError("capacity must be non-negative")
        if cost < 0:
            raise ValueError("forward edge cost must be non-negative")
        forward = Edge(
            to=target,
            reverse_index=len(self.graph[target]),
            capacity=capacity,
            cost=cost,
            initial_capacity=capacity,
            data=data,
        )
        reverse = Edge(
            to=source,
            reverse_index=len(self.graph[source]),
            capacity=0,
            cost=-cost,
            initial_capacity=0,
        )
        self.graph[source].append(forward)
        self.graph[target].append(reverse)

    def solve(self, source: int, sink: int, requested_flow: int) -> tuple[int, int]:
        """Return the maximum achieved flow and its minimum cost."""

        node_count = len(self.graph)
        potential = [0] * node_count
        total_flow = 0
        total_cost = 0
        infinity = 10**30

        while total_flow < requested_flow:
            distances = [infinity] * node_count
            previous_node = [-1] * node_count
            previous_edge = [-1] * node_count
            distances[source] = 0
            queue: list[tuple[int, int]] = [(0, source)]

            while queue:
                current_distance, node = heapq.heappop(queue)
                if current_distance != distances[node]:
                    continue
                for edge_index, edge in enumerate(self.graph[node]):
                    if edge.capacity <= 0:
                        continue
                    reduced_cost = edge.cost + potential[node] - potential[edge.to]
                    candidate_distance = current_distance + reduced_cost
                    if candidate_distance < distances[edge.to]:
                        distances[edge.to] = candidate_distance
                        previous_node[edge.to] = node
                        previous_edge[edge.to] = edge_index
                        heapq.heappush(queue, (candidate_distance, edge.to))

            if distances[sink] == infinity:
                break

            for node, distance in enumerate(distances):
                if distance < infinity:
                    potential[node] += distance

            augmentation = requested_flow - total_flow
            node = sink
            while node != source:
                parent = previous_node[node]
                edge_index = previous_edge[node]
                if parent < 0 or edge_index < 0:
                    raise RuntimeError("Residual path reconstruction failed")
                augmentation = min(
                    augmentation,
                    self.graph[parent][edge_index].capacity,
                )
                node = parent

            node = sink
            while node != source:
                parent = previous_node[node]
                edge_index = previous_edge[node]
                edge = self.graph[parent][edge_index]
                edge.capacity -= augmentation
                reverse = self.graph[node][edge.reverse_index]
                reverse.capacity += augmentation
                node = parent

            total_flow += augmentation
            total_cost += augmentation * potential[sink]

        return total_flow, total_cost

    def used_data_edges(self) -> list[Edge]:
        """Return data-bearing forward edges that carry flow."""

        used: list[Edge] = []
        for edges in self.graph:
            for edge in edges:
                if (
                    edge.data is not None
                    and edge.initial_capacity > 0
                    and edge.capacity < edge.initial_capacity
                ):
                    used.append(edge)
        return used

