"""Every tunable number in one place. See docs/DECISIONS.md for the rationale."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum


@dataclass(frozen=True)
class CorporationSpec:
    id: str
    name: str
    homeworld: str


class Unlimited(Enum):
    """The count of a fleet tier that never sells out."""

    UNLIMITED = "unlimited"


UNLIMITED = Unlimited.UNLIMITED


@dataclass(frozen=True)
class FleetTier:
    """``count`` fleets for sale at ``price`` each, before the next tier's price applies."""

    count: int | Unlimited
    price: int


FOUR_CORPORATIONS = (
    CorporationSpec("CEC", "Corellian Engineering Corporation", "Corellia"),
    CorporationSpec("KDY", "Kuat Drive Yards", "Kuat"),
    CorporationSpec("CSC", "Coruscant Shipping Consortium", "Coruscant"),
    CorporationSpec("KTG", "Kashyyyk Trade Guild", "Kashyyyk"),
)
"""The corporations before 2026-10-28."""
SIX_CORPORATIONS = FOUR_CORPORATIONS + (
    CorporationSpec("IGB", "InterGalactic Banking Clan", "Mygeeto"),
    CorporationSpec("RRC", "Ryloth Ryll Combine", "Ryloth"),
)
"""The corporations since 2026-10-28."""

SEIZURE = "seizure"
"""Death Star stage result: every floated corporation with a fleet loses one."""
SITE_MOVE = "move"
"""Death Star stage result: the construction site moves to the second site."""
COMPLETION = "completion"
"""Death Star stage result: the station launches; the game ends after the current set of
operating rounds."""
STAGE_RESULTS = (SEIZURE, SITE_MOVE, COMPLETION)


@dataclass(frozen=True)
class GameConfig:
    map_file: str = "map-117.json"
    """The board: since 2026-10-26 the 127-hex map with the empty hexes east of Ryloth cut away.
    ``CLASSIC_CONFIG`` keeps the full ``map-127.json``."""
    corporations: tuple[CorporationSpec, ...] = SIX_CORPORATIONS
    """Since 2026-10-28 six, more than the players can run, so where the Death Star sites are
    is part of choosing what to float. ``FLEET_CONFIG`` and ``CLASSIC_CONFIG`` keep the four of
    ``FOUR_CORPORATIONS``."""

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
    planet_pair_bonus: dict[str, int] = field(default_factory=lambda: {"Coruscant": 10})
    """Planet name -> extra value of every pair (typed or basic, not a Death Star contract) that
    includes that planet. Since 2026-10-28 Coruscant's pairs pay 10 more: it lies far from
    every construction site, and without the bonus no one floats its corporation."""

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

    # Rule variants. Defaults are the current rules; the alternatives exist so balance sweeps
    # can compare them. Those marked EXPERIMENTAL are not adopted rules until docs/DECISIONS.md
    # says so.
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
    withhold_moves_price: bool = True
    """EXPERIMENTAL. When False, withholding positive revenue leaves the price unchanged. A
    zero-revenue turn still follows ``zero_revenue_moves_price``."""
    treasury_in_final_worth: float = 0.0
    """EXPERIMENTAL. Each share is worth its price plus this fraction of its corporation's
    treasury divided by shares_per_corporation, in player worth and so in final score."""
    death_star_rules: bool = True
    """Adopted 2026-10-26 (``CLASSIC_CONFIG`` turns it off). Pair capacity (fleets, or
    facilities under ``facility_rules``), bankruptcy and the Death Star construction track (see
    "Death Star and fleets" in docs/DECISIONS.md and ``bby18.death_star``). When True, revenue
    uses at most one pair per fleet or facility owned, each operating turn has a fleet step after
    the network actions, the construction site and its contracts are on the board, and the game
    ends after the set of operating rounds in which the station launches, or after
    ``death_star_backstop_rounds`` (``total_rounds`` is then ignored). The ``fleet_*``,
    ``facility*`` and ``death_star_*`` fields below apply only when this is True."""
    fleet_tiers: tuple[FleetTier, ...] = (
        FleetTier(6, 60),
        FleetTier(6, 90),
        FleetTier(6, 120),
        FleetTier(UNLIMITED, 160),
    )
    """The shared fleet supply, cheapest tier first. The price rises when a tier sells out; the
    last tier must be ``UNLIMITED``. Under ``facility_rules`` the same tiers price facilities
    (a free home facility does not come from the supply)."""
    fleet_limit: int = 3
    """Most facilities one corporation may own (3 since 2026-10-27); with ``facility_rules`` off,
    most fleets (``FLEET_CONFIG``: 4)."""
    facility_rules: bool = True
    """Adopted 2026-10-27 (``FLEET_CONFIG`` and ``CLASSIC_CONFIG`` turn it off); requires
    ``death_star_rules``. Facilities and planet exits (see "Facilities and planet exits" in
    docs/DECISIONS.md): facilities replace fleets as pair capacity, one pair per facility a
    corporation owns, and each sits on a planet. A planet (not the construction site) has
    ``planet_base_exits`` exits plus one per facility on it; a lane claims an exit when charted
    (or upgraded) toward the planet, first come, first served, and the planet connects only
    through claimed sides. A seizure turns the facility nearest the site Imperial."""
    chain_rules: bool = True
    """Supply chains, adopted 2026-10-30 (``FACILITY_CONFIG`` and older configs turn it off;
    requires ``facility_rules``; see "Supply chains" in docs/DECISIONS.md).
    Revenue runs at most one chain per facility owned instead of one pair: a chain carries
    goods up ``commodity_order`` along typed links (contracts count as links into the site), and
    a planet holding one of the corporation's facilities may be a middle stop, where the chain
    drops one cargo and picks up the next. Each link pays its pair value and a chain whose ends
    are in the regional-bonus regions earns the regional bonus once. A seizure takes the
    facility each corporation chooses to surrender, not the one nearest the site."""
    commodity_order: dict[str, int] = field(
        default_factory=lambda: {"A": 0, "R": 0, "I": 1, "M": 2, "S": 2, "W": 3}
    )
    """Tag -> rank under ``chain_rules``: a link runs from the lower rank to the higher, so a
    chain only climbs. Raw goods (A, R), then Industry, then Market and Shipyards, then the Death
    Star site. Every typed pair needs two ranked tags of different rank."""
    planet_base_exits: int = 1
    """Exits a planet has before any facility is built on it (``facility_rules`` only)."""
    facilities_per_planet: int = 2
    """Most facilities, corporate or Imperial, one planet may hold (``facility_rules`` only)."""
    death_star_tag: str = "W"
    """Tag of the construction site (Imperial Works)."""
    contract_partner_tags: frozenset[str] = frozenset({"R", "I", "S"})
    """A planet with one of these tags paired with the site is a contract pair."""
    death_star_stage_values: tuple[int, ...] = (50, 60, 70, 80)
    """Contract pair value while each stage is being built, first stage first. 50-80 since
    2026-10-27, with the facility rules; ``FLEET_CONFIG`` keeps 40-70."""
    death_star_stage_results: tuple[str, ...] = (SEIZURE, SITE_MOVE, SEIZURE, COMPLETION)
    """What happens when each stage fills: one of ``STAGE_RESULTS``. Exactly one stage moves
    the site, and the last stage, only, completes the station."""
    death_star_cubes_per_stage: int = 5
    """Cubes that fill one stage; extra cubes carry over to the next."""
    empire_cubes_per_stock_round: int = 1
    """Cubes the Empire adds at the end of every stock round."""
    death_star_backstop_rounds: int = 8
    """The game ends after this many rounds (stock round plus its operating rounds) if the
    station has not launched."""
    death_star_site_regions: tuple[str, ...] = ("Outer Rim", "Mid Rim")
    """Region of the first construction site, then of the second."""
    death_star_min_homeworld_distance: int = 3
    """Each site is at least this many hexes from every corporation's homeworld."""
    death_star_max_homeworld_distance: int = 4
    """Each site is at most this many hexes from at least ``death_star_near_homeworlds``
    homeworlds, so that several corporations can contest it. If no hex qualifies on a seed, the
    limit is relaxed one hex at a time. A value larger than any board (99) is no constraint."""
    death_star_near_homeworlds: int = 2
    """How many homeworlds must be within ``death_star_max_homeworld_distance`` of each site."""
    death_star_min_planet_distance: int = 1
    """Each site is at least this many hexes from every planet. 1 (no constraint beyond not
    being a planet) allows a site next to a planet (two hubs still need a charted lane
    between them to connect); 2 forbids that but leaves the Mid Rim almost no qualifying hexes on this
    map."""
    death_star_min_chartable_neighbors: int = 2
    """Each site has at least this many neighbours that could be charted."""

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
        if not 0 <= self.treasury_in_final_worth <= 1:
            raise ValueError("treasury_in_final_worth must be between 0 and 1")
        for name in ("asteroid_fraction", "nebula_fraction"):
            if not 0 <= getattr(self, name) <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        if self.asteroid_fraction + self.nebula_fraction > 1:
            raise ValueError("asteroid_fraction + nebula_fraction cannot exceed 1")
        if self.terrain_patch_size < 1:
            raise ValueError("terrain_patch_size must be at least 1")
        if self.nebula_chart_surcharge < 0:
            raise ValueError("nebula_chart_surcharge cannot be negative")
        self._validate_death_star_rules()
        self._validate_facility_rules()

    def _validate_facility_rules(self) -> None:
        """Raise ``ValueError`` if the facility switch or numbers cannot make a game."""
        if self.facility_rules and not self.death_star_rules:
            raise ValueError("facility_rules requires death_star_rules")
        if self.planet_base_exits < 0:
            raise ValueError("planet_base_exits cannot be negative")
        if self.facilities_per_planet < 1:
            raise ValueError("facilities_per_planet must be at least 1")
        if self.chain_rules and not self.facility_rules:
            raise ValueError("chain_rules requires facility_rules")
        best_basic = self.basic_route_value + sum(
            sorted(self.planet_pair_bonus.values(), reverse=True)[:2]
        )
        if self.chain_rules and min(self.death_star_stage_values, default=0) < best_basic:
            # The chain search fills leftover chains with basic routes on the premise that a
            # contract is never worth less than a basic route.
            raise ValueError("chain_rules needs every contract value to be at least a basic route")
        rank = self.commodity_order
        for pair in self.typed_pairs:
            if len(pair) != 2 or any(tag not in rank for tag in pair):
                raise ValueError(f"commodity_order must rank both tags of typed pair {set(pair)}")
            low, high = sorted(rank[tag] for tag in pair)
            if low == high:
                raise ValueError(f"Typed pair {set(pair)} needs tags of different rank")
        for tag in self.contract_partner_tags:
            if tag not in rank or rank.get(self.death_star_tag, -1) <= rank[tag]:
                raise ValueError("commodity_order must rank the site above every partner tag")

    def _validate_death_star_rules(self) -> None:
        """Raise ``ValueError`` if the fleet or Death Star numbers cannot make a game."""
        tiers = self.fleet_tiers
        if not tiers:
            raise ValueError("fleet_tiers needs at least one tier")
        if not isinstance(tiers[-1].count, Unlimited):
            raise ValueError("The last fleet tier must be UNLIMITED")
        for tier in tiers[:-1]:
            if isinstance(tier.count, Unlimited) or tier.count < 1:
                raise ValueError("Every fleet tier but the last needs a positive count")
        if any(tier.price < 1 for tier in tiers):
            raise ValueError("Fleet prices must be positive")
        if self.fleet_limit < 1:
            raise ValueError("fleet_limit must be at least 1")
        if not self.death_star_tag or self.death_star_tag in self.contract_partner_tags:
            raise ValueError("death_star_tag must be a non-empty tag that is not a partner tag")
        results = self.death_star_stage_results
        if len(results) != len(self.death_star_stage_values):
            raise ValueError("death_star_stage_results and _values need one entry per stage")
        unknown = sorted(set(results) - set(STAGE_RESULTS))
        if unknown:
            raise ValueError(f"Unknown Death Star stage results {unknown}; use {STAGE_RESULTS}")
        if not results or results[-1] != COMPLETION or results.count(COMPLETION) != 1:
            raise ValueError("The last Death Star stage, and only it, must be completion")
        if results.count(SITE_MOVE) != 1:
            raise ValueError("Exactly one Death Star stage must move the site")
        if any(v < 0 for v in self.death_star_stage_values):
            raise ValueError("death_star_stage_values cannot be negative")
        if self.death_star_cubes_per_stage < 1:
            raise ValueError("death_star_cubes_per_stage must be at least 1")
        if self.empire_cubes_per_stock_round < 0:
            raise ValueError("empire_cubes_per_stock_round cannot be negative")
        if self.death_star_backstop_rounds < 1:
            raise ValueError("death_star_backstop_rounds must be at least 1")
        if len(self.death_star_site_regions) != 2:
            raise ValueError("death_star_site_regions names the first and second site's region")
        for name in (
            "death_star_min_homeworld_distance",
            "death_star_min_planet_distance",
            "death_star_min_chartable_neighbors",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} cannot be negative")
        if not 1 <= self.death_star_near_homeworlds <= len(self.corporations):
            raise ValueError("death_star_near_homeworlds must be between 1 and the corporations")
        if self.death_star_max_homeworld_distance < self.death_star_min_homeworld_distance:
            raise ValueError(
                "death_star_max_homeworld_distance cannot be below "
                "death_star_min_homeworld_distance"
            )

    def starting_cash(self, player_count: int) -> int:
        if player_count not in self.starting_cash_by_player_count:
            raise ValueError(f"No starting cash defined for {player_count} players")
        return self.starting_cash_by_player_count[player_count]


IPO_PRICE_RULES = ("par", "market_after_float")
CAPITALIZATION_RULES = ("full", "incremental")

DEFAULT_CONFIG = GameConfig()
"""The adopted rules (2026-10-30): the Death Star track with facilities and planet exits, supply
chains (one chain per facility, at most 3 facilities per corporation, the owner choosing what a
seizure takes), contracts at 50/60/70/80. The web app serves these."""

FACILITY_CONFIG = replace(DEFAULT_CONFIG, chain_rules=False, fleet_limit=3)
"""The rules adopted 2026-10-27 and played until supply chains, kept for comparison sweeps and
tests: facilities and planet exits, one pair per facility, at most 3 facilities, the Empire
seizing the facility nearest the site."""

FLEET_CONFIG = GameConfig(
    chain_rules=False,
    corporations=FOUR_CORPORATIONS,
    planet_pair_bonus={},
    facility_rules=False,
    fleet_limit=4,
    death_star_stage_values=(40, 50, 60, 70),
)
"""The rules adopted 2026-10-26, kept for comparison sweeps and tests: the Death Star track with
fleets as pair capacity (at most 4 per corporation), planets as open hubs, and contracts at
40/50/60/70."""

CLASSIC_CONFIG = replace(
    FLEET_CONFIG,
    map_file="map-127.json",
    death_star_rules=False,
    death_star_cubes_per_stage=6,
    death_star_max_homeworld_distance=99,
    death_star_near_homeworlds=1,
)
"""The rules before 2026-10-26, kept for comparison sweeps and tests: the full 127-hex map, no
fleets, facilities or Death Star, a fixed ``total_rounds``, and the Death Star numbers the
experimental switch used to default to."""

# Harness settings (not game rules).
REVENUE_CACHE_SIZE = 1 << 16
"""Bound on memoized revenue matchings kept per process."""

# AI difficulty for the web app's named opponents (see bby18.bots.roster).
DIFFICULTY_TARGET_SHARE: dict[str, float] = {"very-easy": 0.43, "easy": 0.40}
"""Per difficulty, the worth share a reference player (the stable's ``builder``) should take
when seated with two bots of any one strategy. A fair share at three players is 0.333. Under the
facility rules the 1.0 noise maximum gives 0.45-0.53, depending on the strategy."""
BOT_NOISE: dict[str, dict[str, float]] = {
    # Calibrated 2026-10-30 for DIFFICULTY_TARGET_SHARE under the supply-chain rules
    # (docs/sweeps/difficulty-2026-10-30). Churner barely responds to noise and keeps its
    # earlier values.
    "very-easy": {
        "baron": 0.86,
        "baron-prestige": 0.92,
        "baron-tycoon": 0.84,
        "builder": 0.79,
        "churner": 0.28,
        "diversifier": 0.8,
        "early-builder": 0.83,
        "hoarder": 0.4,
        "prestige": 0.83,
        "spoiler": 0.73,
        "straight": 0.69,
        "targeted": 0.79,
        "tycoon": 0.76,
    },
    "easy": {
        "baron": 0.76,
        "baron-prestige": 0.86,
        "baron-tycoon": 0.76,
        "builder": 0.66,
        "churner": 0.12,
        "diversifier": 0.65,
        "early-builder": 0.73,
        "hoarder": 0.5,
        "prestige": 0.57,
        "spoiler": 0.41,
        "straight": 0.1,
        "targeted": 0.74,
        "tycoon": 0.63,
    },
}
"""Per difficulty, each roster strategy's ``GreedyPolicy.noise``. Re-run the calibration when the
target, the rules or a strategy changes."""
