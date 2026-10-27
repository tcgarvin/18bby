"""Route costs for the greedy bot's build planning, aware of planet exits.

A route is priced per hex entered (see ``route_costs``). With every planet an open hub, a route
passes through a planet for free. Under the facility rules a planet connects only
through its claimed exits (see ``bby18.network``), so a route also pays for the exits it needs
(``PlanetDoors``):

- Entering a planet as the route's end needs one usable side; passing through it needs two, the
  side it comes in by and the side it leaves by. A claimed side is usable. A side where a lane
  already dangles needs a facility, whose builder gives it the new exit. Any other side takes
  an unclaimed exit while the planet has one, and a facility after that
  (``HyperspaceNetwork.exits_needed``). So a planet with one exit is a dead end unless a
  facility is bought there.
- Each facility a route needs costs the current facility price. A planet without enough free
  facility slots for them, or any planet needing one when the corporation already owns the most
  facilities it may, is impassable that way.
- Where a route leaves the network from a tile, it goes out through one of the tile's exits,
  or pays for an upgrade that adds one (impassable if the tile cannot take one). With every
  planet an open hub a network can always grow from a planet's free sides, so the old planner
  treated every side of a tile as open; under the facility rules a full planet gives no free
  side, and pricing a tile's other sides as free would hide every reason to build a facility.

The search is exact for that model: an exit-limited planet is never a node of its own. A
route steps over it from the tile hex on one side to the tile hex on another, paying for both
sides at once, so a planet's spare exit is never counted twice. As before, a tile's own exits
are ignored beyond the network's edge (a charted hex costs the service price whichever way it
points), and a route's facilities are priced at today's price, not the price when they would
be bought. Without the facility rules there are no doors and every cost is what it was before
planet exits existed.
"""

from __future__ import annotations

import heapq
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field

from bby18.board import Board, Terrain
from bby18.game import Game
from bby18.hexgrid import Direction, Hex
from bby18.network import HyperspaceNetwork
from bby18.state import Corporation


@dataclass(frozen=True)
class PlanetDoors:
    """What exit-limited planets cost one corporation's routes (facility rules only)."""

    network: HyperspaceNetwork
    """The network whose claimed exits, unclaimed exits and dangling lanes the routes face."""
    facility_price: int
    """What each facility a route needs is charged."""
    can_build: bool
    """Whether the corporation may own another facility; if not, a route needing one is
    impassable."""
    slots: Mapping[Hex, int]
    """Free facility slots of each exit-limited planet (``Game.free_facility_slots``)."""
    upgrade_cost: int
    """What adding an exit to one of the corporation's tiles costs."""
    _costs: dict[tuple[Hex, frozenset[Direction]], int | None] = field(
        default_factory=dict, init=False, compare=False, repr=False
    )
    """Memo of ``cost``; ``dataclasses.replace`` starts a fresh one."""

    @classmethod
    def of(cls, game: Game, corp: Corporation) -> PlanetDoors | None:
        """The doors ``corp`` faces now; ``None`` without the facility rules, where every planet
        is an open hub."""
        if not game.config.facility_rules:
            return None
        net = game.network
        return cls(
            network=net,
            facility_price=game.fleet_price(),
            can_build=corp.fleets < game.config.fleet_limit,
            slots={
                p.hex: game.free_facility_slots(p.hex)
                for p in game.board.planets
                if net.has_exit_limit(p.hex)
            },
            upgrade_cost=game.config.upgrade_cost,
        )

    def limits(self, hex: Hex) -> bool:
        """Whether ``hex`` is a planet with limited exits."""
        return self.network.has_exit_limit(hex)

    def leaving_cost(self, hex: Hex, direction: Direction) -> int | None:
        """What a route pays to leave the network from ``hex`` (a hex the corporation reaches)
        through its ``direction`` side: an exit-limited planet's door (``cost``); for a tile,
        nothing through one of its exits and an upgrade otherwise; ``None`` if the tile cannot
        take another exit. An open hub has every exit."""
        if self.limits(hex):
            return self.cost(hex, (direction,))
        tile = self.network.tile_at(hex)
        if tile is None or direction in tile.exits:
            return 0
        board = self.network.board
        if (
            len(tile.exits) >= HyperspaceNetwork.MAX_EXITS
            or board.terrain_at(hex) is Terrain.NEBULA
            or direction not in board.on_board_directions(hex)
        ):
            return None
        return self.upgrade_cost

    def cost(self, planet: Hex, sides: Iterable[Direction]) -> int | None:
        """What the facilities cost that ``planet`` needs to connect through every one of
        ``sides``; ``None`` if it cannot get them (too few free slots, or the corporation may
        own no more)."""
        key = (planet, frozenset(sides))
        if key not in self._costs:
            needed = self.network.exits_needed(planet, key[1])
            if needed == 0:
                self._costs[key] = 0
            elif not self.can_build or needed > self.slots.get(planet, 0):
                self._costs[key] = None
            else:
                self._costs[key] = needed * self.facility_price
        return self._costs[key]


def route_costs(
    game: Game,
    net: HyperspaceNetwork,
    corp_id: str,
    targets: Iterable[Hex],
    blocked: frozenset[Hex],
    doors: PlanetDoors | None,
) -> dict[Hex, int]:
    """Cheapest cost to build from each hex to some target, charged per hex entered.

    Open space costs the chart cost, a nebula adds its surcharge, a tile someone already
    charted costs the service cost, and the corporation's own service is free. Asteroid fields
    are not on the board's adjacency, so routes go around them, as they go around ``blocked``
    hexes. Two hubs never connect directly, so a route never steps from a planet (or a reserved
    construction site, a future hub) straight to an adjacent one. An open hub costs nothing to
    enter or pass. An exit-limited planet (only with ``doors``) has no cost of its own: a route
    steps over it, paying for the exits it needs (see the module docstring), and a target of
    that kind is priced from the tile hexes beside it.
    """
    board = game.board
    served = net.service_of(corp_id)
    future_hubs = frozenset(game.death_star_reserved_sites())
    service_cost = game.config.service_cost

    def is_hub(hex: Hex) -> bool:
        return board.is_planet(hex) or hex in future_hubs

    def limited(hex: Hex) -> bool:
        return doors is not None and doors.limits(hex)

    def entry_cost(hex: Hex) -> int:
        if board.is_planet(hex) or hex in served:
            return 0
        if net.is_charted(hex):
            return service_cost
        return game.chart_cost(hex)

    dist: dict[Hex, int] = {}
    heap: list[tuple[int, Hex]] = []

    def relax(hex: Hex, cost: int) -> None:
        if cost < dist.get(hex, cost + 1):
            dist[hex] = cost
            heapq.heappush(heap, (cost, hex))

    target_list = list(targets)
    dist.update((h, 0) for h in target_list if not limited(h))
    heap.extend((0, h) for h in dist)
    heapq.heapify(heap)
    for target in target_list:
        if not limited(target):
            continue
        assert doors is not None
        for side, nxt in board.neighbors(target):
            if nxt in blocked or is_hub(nxt):
                continue
            door = doors.cost(target, (side,))
            if door is not None:
                relax(nxt, door + entry_cost(nxt))
    while heap:
        d, hex = heapq.heappop(heap)
        if d > dist.get(hex, d):
            continue
        for direction, nxt in board.neighbors(hex):
            if nxt in blocked or (is_hub(nxt) and is_hub(hex)):
                continue
            if not limited(nxt):
                relax(nxt, d + entry_cost(nxt))
                continue
            assert doors is not None
            toward_here = direction.opposite
            for side, beyond in board.neighbors(nxt):
                if beyond == hex or beyond in blocked or is_hub(beyond):
                    continue
                door = doors.cost(nxt, (toward_here, side))
                if door is not None:
                    relax(beyond, d + door + entry_cost(beyond))
    return dist


class RouteMap(Mapping[Hex, float]):
    """Remaining route costs to a set of weighted targets: a mapping from each hex a route can
    start or continue from to its cost (see ``route_costs``), which also prices a step into an
    exit-limited planet (``beyond``) and the cheapest route out of a network (``from_network``).
    A target of weight w is aimed at as if 1/w as far; a step into an exit-limited planet adds
    its door cost unweighted."""

    def __init__(
        self,
        costs: Mapping[Hex, float],
        board: Board,
        targets: Mapping[Hex, float],
        blocked: frozenset[Hex],
        future_hubs: frozenset[Hex],
        doors: PlanetDoors | None,
    ) -> None:
        self._costs = costs
        self._board = board
        self._targets = targets
        self._blocked = blocked
        self._future_hubs = future_hubs
        self._doors = doors

    def with_doors(self, doors: PlanetDoors | None) -> RouteMap:
        """The same costs, facing ``doors`` where a route leaves the network or steps into an
        exit-limited planet: for judging a network after a facility, when the build changes
        only the planet it is on and the route beyond is priced as before."""
        return RouteMap(
            self._costs, self._board, self._targets, self._blocked, self._future_hubs, doors
        )

    def __getitem__(self, hex: Hex) -> float:
        return self._costs[hex]

    def __iter__(self) -> Iterator[Hex]:
        return iter(self._costs)

    def __len__(self) -> int:
        return len(self._costs)

    def _is_hub(self, hex: Hex) -> bool:
        return self._board.is_planet(hex) or hex in self._future_hubs

    def _limited(self, hex: Hex) -> bool:
        return self._doors is not None and self._doors.limits(hex)

    def beyond(self, origin: Hex, far: Hex) -> float | None:
        """Route cost still to pay from ``far``, entered from the adjacent ``origin``; ``None``
        if no route leads on. For an exit-limited planet that is the cheaper of ending there,
        if it is a target, and passing through to a tile hex beside it, each with what its
        exits need."""
        if not self._limited(far):
            return self._costs.get(far)
        doors = self._doors
        assert doors is not None
        side = far.direction_to(origin)
        options: list[float] = []
        weight = self._targets.get(far)
        if weight is not None:
            door = doors.cost(far, (side,))
            if door is not None:
                options.append(door if weight == 1 else door / weight)
        for out, nxt in self._board.neighbors(far):
            if nxt == origin or nxt in self._blocked or self._is_hub(nxt):
                continue
            rest = self._costs.get(nxt)
            if rest is None:
                continue
            door = doors.cost(far, (side, out))
            if door is not None:
                options.append(door + rest)
        return min(options, default=None)

    def from_network(self, reach: frozenset[Hex]) -> float | None:
        """The cheapest route from the network ``reach`` to a target, counting every hex it
        enters, the first beside the network included; ``None`` if there is none.

        A route starts at a hex beside the network that is not a planet. Under the facility
        rules it pays to leave the network that way (``PlanetDoors.leaving_cost``), and it may
        also start by stepping into an unreached exit-limited planet beside the network (one
        that a lane of the network dangles at, say), to end there or pass on."""
        costs = (self.from_hex(hex, reach) for hex in reach)
        return min((c for c in costs if c is not None), default=None)

    def from_hex(self, hex: Hex, reach: frozenset[Hex]) -> float | None:
        """The cheapest route that leaves the network ``reach`` from ``hex``, one of its hexes,
        as ``from_network`` counts it; ``None`` if there is none."""
        board = self._board
        doors = self._doors
        best: float | None = None
        for direction, nxt in board.neighbors(hex):
            if nxt in reach:
                continue
            rest: float | None
            if not board.is_planet(nxt):
                rest = self._costs.get(nxt)
            elif self._limited(nxt) and not self._is_hub(hex):
                rest = self.beyond(hex, nxt)
            else:
                continue
            if rest is None:
                continue
            if doors is not None:
                leaving = doors.leaving_cost(hex, direction)
                if leaving is None:
                    continue
                rest += leaving
            if best is None or rest < best:
                best = rest
        return best
