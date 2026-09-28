"""Every tunable number in one place. See docs/DECISIONS.md for the rationale."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CorporationSpec:
    id: str
    name: str
    homeworld: str


@dataclass(frozen=True)
class GameConfig:
    map_file: str = "map-127.json"
    corporations: tuple[CorporationSpec, ...] = (
        CorporationSpec("CEC", "Corellian Engineering Corporation", "Corellia"),
        CorporationSpec("KDY", "Kuat Drive Yards", "Kuat"),
        CorporationSpec("CSC", "Coruscant Shipping Consortium", "Coruscant"),
        CorporationSpec("KTG", "Kashyyyk Trade Guild", "Kashyyyk"),
    )

    # Network actions
    network_actions_per_turn: int = 1
    chart_cost: int = 20
    upgrade_cost: int = 20
    service_cost: int = 20

    # Economy
    typed_pair_value: int = 30
    typed_pairs: frozenset[frozenset[str]] = frozenset(
        {
            frozenset({"A", "M"}),
            frozenset({"R", "I"}),
            frozenset({"R", "S"}),
            frozenset({"I", "M"}),
            frozenset({"I", "S"}),
        }
    )
    regional_bonus: int = 20
    regional_bonus_regions: frozenset[str] = frozenset({"Core", "Outer Rim"})
    basic_route_value: int = 5

    # Stock market
    stock_track: tuple[int, ...] = (
        40,
        50,
        60,
        70,
        80,
        90,
        100,
        110,
        125,
        140,
        155,
        170,
        190,
        210,
        230,
        250,
        275,
        300,
        330,
        360,
        400,
    )
    par_prices: tuple[int, ...] = (60, 70, 80, 90, 100)
    shares_per_corporation: int = 10
    president_share_size: int = 2
    float_threshold_shares: int = 5

    # Players
    starting_cash_by_player_count: dict[int, int] = field(
        default_factory=lambda: {2: 600, 3: 400, 4: 300}
    )
    max_holding_shares: int = 6
    certificate_limit: int = 12

    # Game length
    total_rounds: int = 6
    operating_rounds_per_stock_round: int = 2

    def starting_cash(self, player_count: int) -> int:
        if player_count not in self.starting_cash_by_player_count:
            raise ValueError(f"No starting cash defined for {player_count} players")
        return self.starting_cash_by_player_count[player_count]


DEFAULT_CONFIG = GameConfig()
