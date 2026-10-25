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
    network_actions_per_turn: int = 2
    chart_cost: int = 60
    upgrade_cost: int = 80
    service_cost: int = 60
    nebula_chart_surcharge: int = 30
    """Extra cost to chart a nebula hex. Extending service onto one costs the usual amount."""

    # Terrain (see terrain.py). Placement is deterministic from the game seed.
    asteroid_fraction: float = 0.15
    """Share of non-planet hexes that are asteroid fields: impassable, never charted."""
    nebula_fraction: float = 0.15
    """Share of non-planet hexes that are nebulae: costlier to chart, never upgraded to 3 exits."""
    terrain_patch_size: int = 3
    """Largest contiguous patch of one terrain type; 1 scatters single hexes."""

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

    # Stock market (two-dimensional; see market.py). Top row first. Moving up one row is worth
    # about one column to the right; lower rows end sooner.
    stock_market: tuple[tuple[int, ...], ...] = (
        (80, 90, 100, 110, 120, 135, 150, 165, 180, 200, 220, 240, 260, 285, 310, 340, 370, 400),
        (70, 80, 90, 100, 110, 120, 135, 150, 165, 180, 200, 220, 240, 260, 285, 310, 340),
        (60, 70, 80, 90, 100, 110, 120, 135, 150, 165, 180, 200, 220, 240, 260, 285),
        (50, 60, 70, 80, 90, 100, 110, 120, 135, 150, 165, 180, 200, 220, 240),
        (40, 50, 60, 70, 80, 90, 100, 110, 120, 135, 150, 165, 180, 200),
        (30, 40, 50, 60, 70, 80, 90, 100, 110, 120, 135, 150, 165),
        (20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120, 135),
        (10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110),
    )
    par_column: int = 3
    """Market column holding the par cells; each par price must appear in it."""
    payout_step_fractions: tuple[float, ...] = (0.5, 1.5)
    """Paying dividends moves the price right one column for each fraction f with
    revenue >= f x share price. Below the first fraction a payout does not move the price."""
    par_prices: tuple[int, ...] = (60, 70, 80, 90, 100)
    shares_per_corporation: int = 10
    president_share_size: int = 2
    float_threshold_shares: int = 5
    float_capital_shares: int = 8
    """On floating, a corporation receives par times this many shares from the bank."""

    # Players
    starting_cash_by_player_count: dict[int, int] = field(
        default_factory=lambda: {2: 600, 3: 400, 4: 300}
    )
    max_holding_shares: int = 6
    certificate_limit: int = 12

    # Game length
    total_rounds: int = 6
    operating_rounds_per_stock_round: int = 2

    # Experimental rule variants. Defaults reproduce the current rules; the alternatives exist
    # so balance sweeps can compare them. None is an adopted rule until docs/DECISIONS.md says so.
    zero_revenue_moves_price: bool = True
    """EXPERIMENTAL. When False, an operating turn with zero revenue leaves the price unchanged
    (it is still logged as withholding 0)."""
    ipo_price_rule: str = "par"
    """EXPERIMENTAL. What an IPO share costs once the corporation is started.

    "par": always par. "market_after_float": par until the corporation floats, then
    max(par, current share price). Either way the cash goes to the bank (or the treasury under
    capitalization="incremental").
    """
    capitalization: str = "full"
    """EXPERIMENTAL. How a corporation gets its treasury.

    "full": on floating it receives par x float_capital_shares from the bank; IPO sale cash
    goes to the bank. "incremental": each IPO share sold (the president's shares included)
    puts its par into the treasury, paid out of the bank, and floating pays nothing extra.
    Floating still needs float_threshold_shares sold either way.
    """
    homeworld_basic_income: int = 0
    """EXPERIMENTAL. Minimum revenue per operating turn for a floated corporation, even with no
    planet pairs: revenue = max(pair revenue, homeworld_basic_income). 0 disables the floor."""

    def validate_rule_variants(self) -> None:
        """Raise ``ValueError`` if an experimental rule field names an unknown rule."""
        choices = {
            "ipo_price_rule": (self.ipo_price_rule, IPO_PRICE_RULES),
            "capitalization": (self.capitalization, CAPITALIZATION_RULES),
        }
        for name, (value, allowed) in choices.items():
            if value not in allowed:
                raise ValueError(f"Unknown {name} {value!r}; expected one of {allowed}")
        fractions = self.payout_step_fractions
        if any(f < 0 for f in fractions) or list(fractions) != sorted(fractions):
            raise ValueError("payout_step_fractions must be non-negative and ascending")
        if self.homeworld_basic_income < 0:
            raise ValueError("homeworld_basic_income cannot be negative")
        for name in ("asteroid_fraction", "nebula_fraction"):
            if not 0 <= getattr(self, name) <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        if self.asteroid_fraction + self.nebula_fraction > 1:
            raise ValueError("asteroid_fraction + nebula_fraction cannot exceed 1")
        if self.terrain_patch_size < 1:
            raise ValueError("terrain_patch_size must be at least 1")
        if self.nebula_chart_surcharge < 0:
            raise ValueError("nebula_chart_surcharge cannot be negative")

    def starting_cash(self, player_count: int) -> int:
        if player_count not in self.starting_cash_by_player_count:
            raise ValueError(f"No starting cash defined for {player_count} players")
        return self.starting_cash_by_player_count[player_count]


IPO_PRICE_RULES = ("par", "market_after_float")
CAPITALIZATION_RULES = ("full", "incremental")

DEFAULT_CONFIG = GameConfig()

# Harness settings (not game rules).
REVENUE_CACHE_SIZE = 1 << 16
"""Bound on memoized revenue matchings kept per process."""
