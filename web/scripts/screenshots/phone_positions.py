"""Sets up positions for trying the phone layout, and prints a link to each.

Needs the API (`uv run bby18 serve --port 8000`) and the web dev server (`npm run dev -- --host`)
running. Games live in the API's memory in local mode, where every browser is the same user, so a
phone on the same network can open them.

    uvx --with playwright==1.63.0 python web/scripts/screenshots/phone_positions.py --host 192.168.1.20

The harness's scripted human plays each game up to the position, using the same choices as the
measurements in the mobile plan:

- most-hexes: seed 12, OR8.1, the network turn with the most hexes to act on (16).
- tightest: seed 15, OR8.2, the network turn that frames smallest (10 hexes, spread widest).
- replay: the first developed dividend decision whose reply replays opponents' lanes and ends on
  another network turn. Pay or withhold to watch the replay; Undo to watch it again.
"""

from __future__ import annotations

import argparse
from types import SimpleNamespace
from typing import Any, Callable

from shoot import Api, choose, is_developed

API_URL = "http://localhost:8000"
DEVELOPED = SimpleNamespace(round=6, min_tiles=24, min_chains=2)
LANE_MOVES = ("chart", "upgrade", "service")

State = dict[str, Any]


def hex_count(state: State) -> int:
    return len({tuple(action["hex"]) for action in state["legalActions"] if "hex" in action})


def network_turn(round_label: str, hexes: int) -> Callable[[State], bool]:
    """Stops at the network decision in `round_label` with exactly `hexes` hexes to act on."""

    def reached(state: State) -> bool:
        return (
            state["phase"] == "network"
            and state["roundLabel"] == round_label
            and hex_count(state) == hexes
        )

    return reached


def play_to(api: Api, seed: int, reached: Callable[[State], bool]) -> tuple[str, State]:
    """Plays a new game until `reached`; raises if the game ends first, as a position must exist."""
    board = api.board()
    game_id, state = api.new_game(seed)
    while state["phase"] != "game_over" and state["waitingOnHuman"]:
        if reached(state):
            return game_id, state
        state = api.act(game_id, choose(state, board, state["deathStar"]["fleets"]["limit"]))
    raise RuntimeError(f"Seed {seed} ended at {state['roundLabel']} without reaching the position")


def replay_position(api: Api, seed: int) -> tuple[str, State]:
    """The dividend decision just before a reply with opponents' lanes that ends on a network turn.

    Finds it on one game, then plays a second game to just before it, since the search has to make
    the move to see the reply.
    """
    board = api.board()
    game_id, state = api.new_game(seed)
    decisions = 0
    while state["phase"] != "game_over" and state["waitingOnHuman"]:
        before = state
        state = api.act(game_id, choose(state, board, state["deathStar"]["fleets"]["limit"]))
        decisions += 1
        moves = [move for move in state.get("moves") or [] if move.get("automatic")]
        lanes = {move["corporation"] for move in moves if move["action"]["type"] in LANE_MOVES}
        if (
            before["phase"] == "dividend"
            and is_developed(before, DEVELOPED)
            and lanes
            and state["phase"] == "network"
        ):
            return play_decisions(api, seed, decisions - 1)
    raise RuntimeError(f"Seed {seed} has no dividend decision followed by a replay of lanes")


def play_decisions(api: Api, seed: int, decisions: int) -> tuple[str, State]:
    board = api.board()
    game_id, state = api.new_game(seed)
    for _ in range(decisions):
        state = api.act(game_id, choose(state, board, state["deathStar"]["fleets"]["limit"]))
    return game_id, state


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--host", default="localhost", help="address the phone reaches this machine at"
    )
    parser.add_argument("--port", type=int, default=5173, help="the web dev server's port")
    args = parser.parse_args()

    api = Api(API_URL)
    positions = {
        "most-hexes": play_to(api, 12, network_turn("OR8.1", 16)),
        "tightest": play_to(api, 15, network_turn("OR8.2", 10)),
        "replay": replay_position(api, 7),
    }
    for name, (game_id, state) in positions.items():
        corporation = state["currentCorporation"]
        print(
            f"{name:11} {state['roundLabel']:6} {state['phase']:9} {corporation:4} http://{args.host}:{args.port}/?game={game_id}"
        )


main()
