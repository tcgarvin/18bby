"""Screenshot harness for the 18BBY web app (see README.md in this directory).

Starts the API (local mode, in-memory games) and a Vite dev server on free ports, plays one human
seat against bots with a fixed seed until the game is well developed, then screenshots the real UI
at the first stop in each phase. Exits non-zero if any phase is not reached.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from playwright.sync_api import Browser, Locator, Page, ViewportSize, sync_playwright

WEB_DIRECTORY = Path(__file__).resolve().parents[2]
REPO_ROOT = WEB_DIRECTORY.parent
DEFAULT_OUT = Path(
    "/tmp/claude-1000/-home-timg-code-18bby/03d2a5bf-1aa6-4c38-a53e-3f014af5b88e/scratchpad/shots"
)
PHASES = ("stock", "network", "fleet", "dividend")
VIEWPORT: ViewportSize = {"width": 1600, "height": 1000}
SEATS = [{"name": "Tim"}] + [
    {"name": f"Bot {n}", "bot": True, "difficulty": "very-easy"} for n in "ABC"
]
# A hex's neighbours by exit name, as in src/bby18/hexgrid.py; the harness talks only to the API.
EXIT_DELTAS = {"E": (1, 0), "SE": (0, 1), "SW": (-1, 1), "W": (-1, 0), "NW": (0, -1), "NE": (1, -1)}
# The human pays dividends once its corporation holds this much, so it has cash to show in stock
# rounds; below this it withholds to keep building.
PAY_DIVIDEND_FROM_TREASURY = 200
MAP_SELECTOR = ".stage svg.hexmap:not(.mapthumb *)"
SWITCH_SETTLE_MS = 400


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for(url: str, process: subprocess.Popen[bytes], seconds: float = 60) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Server for {url} exited with code {process.returncode}")
        try:
            urllib.request.urlopen(url, timeout=2).read()
            return
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            time.sleep(0.3)
    raise TimeoutError(f"{url} did not come up within {seconds}s")


@contextmanager
def servers() -> Iterator[tuple[str, str]]:
    """Yield (api_url, web_url); both servers are stopped on exit."""
    api_port, web_port = free_port(), free_port()
    env_api = {"BBY18_MODE": "local"}
    env_web = {"SHOT_API_PORT": str(api_port), "SHOT_WEB_PORT": str(web_port)}
    api = subprocess.Popen(
        ["uv", "run", "bby18", "serve", "--port", str(api_port)],
        cwd=REPO_ROOT,
        env={**os.environ, **env_api},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    web = subprocess.Popen(
        [
            "node_modules/.bin/vite",
            "--config",
            "scripts/screenshots/vite.config.mjs",
            "--host",
            "127.0.0.1",
        ],
        cwd=WEB_DIRECTORY,
        env={**os.environ, **env_web},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        wait_for(f"http://127.0.0.1:{api_port}/api/board", api)
        wait_for(f"http://127.0.0.1:{web_port}/", web)
        yield f"http://127.0.0.1:{api_port}", f"http://127.0.0.1:{web_port}"
    finally:
        # Each server leads its own process group (uv and vite spawn children): stop the group.
        for process in (web, api):
            os.killpg(process.pid, signal.SIGTERM)
        for process in (web, api):
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()


class Api:
    def __init__(self, base: str) -> None:
        self.base = base
        self.token = ""
        self.token = self._request("/api/accounts", {})["token"]

    def _request(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        headers = {"content-type": "application/json"}
        if self.token:
            headers["authorization"] = f"Bearer {self.token}"
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.base + path, data=data, headers=headers)
        try:
            with urllib.request.urlopen(request) as response:
                return json.load(response)  # type: ignore[no-any-return]
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"{path}: {exc.code} {exc.read().decode()}") from exc

    def board(self) -> dict[str, Any]:
        return self._request("/api/board")

    def new_game(self, seed: int) -> tuple[str, dict[str, Any]]:
        game = self._request("/api/games", {"seats": SEATS, "seed": seed})
        return game["gameId"], game["state"]

    def act(self, game_id: str, action: dict[str, Any]) -> dict[str, Any]:
        return self._request(f"/api/games/{game_id}/actions", {"action": action})


def legal_of_type(state: dict[str, Any], kind: str) -> dict[str, Any]:
    for action in state["legalActions"]:
        if action["type"] == kind:
            return action  # type: ignore[no-any-return]
    raise RuntimeError(f"{state['roundLabel']}: no legal {kind} in {state['legalActions']}")


def current_corporation(state: dict[str, Any]) -> dict[str, Any]:
    return next(c for c in state["corporations"] if c["id"] == state["currentCorporation"])


def human_corporations(state: dict[str, Any]) -> list[dict[str, Any]]:
    """The corporations presided over by the human, the first player."""
    human = state["players"][0]["id"]
    return [c for c in state["corporations"] if c["president"] == human]


def choose_stock(state: dict[str, Any]) -> dict[str, Any]:
    """Start one corporation at the lowest par and buy it until it floats, then pass.

    The human must float it alone: web opponents start corporations of their own and rarely buy
    into another's, and a player's cash only stretches to the shares a float needs at the lowest
    par. A corporation parred any higher never operates, and the human's money is stuck in it.
    """
    corporations = human_corporations(state)
    if not corporations:
        pars = [a for a in state["legalActions"] if a["type"] == "buy" and "par" in a]
        return min(pars, key=lambda a: a["par"]) if pars else legal_of_type(state, "pass")
    for corporation in corporations:
        if corporation["status"] == "parred":
            for action in state["legalActions"]:
                if (
                    action["type"] == "buy"
                    and action["corp"] == corporation["id"]
                    and action["source"] == "ipo"
                ):
                    return action  # type: ignore[no-any-return]
    return legal_of_type(state, "pass")


def hex_distance(a: tuple[int, int], b: tuple[int, int]) -> int:
    dq, dr = a[0] - b[0], a[1] - b[1]
    return (abs(dq) + abs(dr) + abs(dq + dr)) // 2


def unreached_hubs(state: dict[str, Any], board: dict[str, Any]) -> list[tuple[int, int]]:
    """The planets the current corporation could still connect to, and the construction site."""
    corporation = current_corporation(state)
    reached = {*corporation["reachablePlanets"], corporation["homeworld"]}
    exits = {p["name"]: p["unclaimed"] for p in state["facilities"]["planets"]}
    hubs = [
        tuple(planet["hex"])
        for planet in board["planets"]
        if planet["name"] not in reached and exits.get(planet["name"], 1) > 0
    ]
    sites = state["deathStar"]["sites"]
    return hubs + [tuple(site["hex"]) for site in sites if site["status"] == "active"]


def choose_network(state: dict[str, Any], board: dict[str, Any]) -> dict[str, Any]:
    """Build toward the nearest hub the corporation has not reached, the cheapest way, keeping
    the price of a facility in the treasury so its facility step still comes up."""
    hubs = unreached_hubs(state, board)
    budget = current_corporation(state)["treasury"] - state["deathStar"]["fleets"]["price"]

    def score(action: dict[str, Any]) -> tuple[int, int]:
        q, r = action["hex"]
        exits = action["exits"] if action["type"] == "chart" else [action["exit"]]
        ends = [(q + EXIT_DELTAS[e][0], r + EXIT_DELTAS[e][1]) for e in exits]
        nearest = min((hex_distance(end, hub) for end in ends for hub in hubs), default=len(ends))
        return nearest, action["cost"]

    builds = [
        a
        for a in state["legalActions"]
        if a["type"] in ("chart", "upgrade") and a["cost"] <= budget
    ]
    return min(builds, key=score) if builds else legal_of_type(state, "no_action")


def choose_facility(state: dict[str, Any], facility_cap: int) -> dict[str, Any]:
    """Build the facility that earns the most while under `facility_cap`, if it earns more."""
    corporation = current_corporation(state)
    options = state["facilities"]["options"]
    if corporation["fleets"] == 0 or (options and corporation["fleets"] < facility_cap):
        best = max(options, key=lambda o: (o["revenue"], len(o["reaches"]), -o["action"]["cost"]))
        if corporation["fleets"] == 0 or best["revenue"] > corporation["revenue"]["total"]:
            return best["action"]  # type: ignore[no-any-return]
    return legal_of_type(state, "finish_fleets")


def choose_dividend(state: dict[str, Any]) -> dict[str, Any]:
    rich = current_corporation(state)["treasury"] >= PAY_DIVIDEND_FROM_TREASURY
    choice = "pay" if rich else "withhold"
    return next(a for a in state["legalActions"] if a.get("choice") == choice)


def choose_surrender(state: dict[str, Any]) -> dict[str, Any]:
    options = state["facilities"]["surrenderOptions"]
    return max(options, key=lambda o: o["revenue"])["action"]  # type: ignore[no-any-return]


def choose(state: dict[str, Any], board: dict[str, Any], facility_cap: int) -> dict[str, Any]:
    """The human's move, always one the engine lists as legal."""
    phase = state["phase"]
    if phase == "stock":
        action = choose_stock(state)
    elif phase == "network":
        action = choose_network(state, board)
    elif phase == "fleet":
        action = choose_facility(state, facility_cap)
    elif phase == "dividend":
        action = choose_dividend(state)
    elif phase == "surrender":
        action = choose_surrender(state)
    else:
        raise RuntimeError(f"The human has no policy for the {phase} phase")
    if action not in state["legalActions"]:
        raise RuntimeError(f"{state['roundLabel']}: {action} is not a legal action")
    return action


def chain_count(state: dict[str, Any]) -> int:
    """The most supply chains any of the human's corporations runs."""
    floated = [c for c in human_corporations(state) if c["status"] == "floated"]
    return max((len(c["revenue"]["chains"]) for c in floated), default=0)


def is_developed(state: dict[str, Any], args: argparse.Namespace) -> bool:
    return bool(
        state["roundNumber"] >= args.round
        and len(state["tiles"]) >= args.min_tiles
        and chain_count(state) >= args.min_chains
    )


def game_stats(state: dict[str, Any]) -> str:
    exits = Counter(len(tile["exits"]) for tile in state["tiles"])
    shared = sum(1 for tile in state["tiles"] if len(tile.get("service", [])) > 1)
    networks = ", ".join(
        f"{c['id']} {len(c['revenue']['chains'])} chains/"
        f"{len(c['revenue']['pairs'])} links/{c['revenue']['total']}"
        for c in state["corporations"]
        if c["status"] == "floated"
    )
    return (
        f"{len(state['tiles'])} tiles, exit counts {dict(sorted(exits.items()))}, "
        f"{shared} shared; {networks}"
    )


def open_game(page: Page, web_url: str, game_id: str, phase: str) -> None:
    page.goto(f"{web_url}/?game={game_id}")
    page.wait_for_selector(f".stage--{phase}")
    page.wait_for_function("!document.querySelector('.stage--replaying')")
    page.wait_for_timeout(1200)


def open_browsed_map(page: Page) -> None:
    """The stock round shows only a thumbnail: switch to the read-only Map view (the M key)."""
    page.keyboard.press("m")
    page.wait_for_selector(MAP_SELECTOR)
    page.wait_for_timeout(1000)


def map_crop(page: Page) -> Locator:
    """The map, with its frame when the frame holds the map's view toggle, so the crop shows it."""
    svg = page.locator(MAP_SELECTOR).first
    frame = svg.locator("xpath=..")
    return frame if frame.locator("[data-map-view]").count() > 0 else svg


def routes_blocked(page: Page) -> str:
    """Why the Routes view cannot be shot here; empty when it can."""
    button = page.locator('button[data-map-view="routes"]')
    if button.count() == 0:
        return "no Regular | Routes toggle on the page"
    if button.first.is_disabled():
        return f"Routes is disabled: {button.first.get_attribute('title')}"
    return ""


def settle_after_click(page: Page) -> None:
    """Move the pointer off what was clicked, so shots show its resting style and not :hover."""
    page.mouse.move(0, 0)
    page.wait_for_timeout(SWITCH_SETTLE_MS)


def switch_map_view(page: Page, view: str) -> None:
    page.locator(f'button[data-map-view="{view}"]').first.click()
    page.wait_for_selector(f'button[data-map-view="{view}"][aria-pressed="true"]')
    settle_after_click(page)


@contextmanager
def map_view(page: Page, view: str) -> Iterator[None]:
    """Show the map's `view`, and put the toggle (saved in localStorage) back afterwards."""
    pressed = page.locator('button[data-map-view][aria-pressed="true"]').first
    before = pressed.get_attribute("data-map-view")
    if before is None:
        raise RuntimeError("No map view is pressed on the Regular | Routes toggle")
    switch_map_view(page, view)
    yield
    switch_map_view(page, before)


def shoot_routes(page: Page, label: str, phase: str, out: Path, crop: bool) -> str:
    """The extra Routes shots of a page already showing its map. Returns the reason if skipped."""
    blocked = routes_blocked(page)
    if blocked:
        return blocked
    with map_view(page, "routes"):
        if crop:
            map_crop(page).screenshot(path=str(out / f"{label}-map-routes.png"))
            print(f"  {label}-map-routes.png")
        else:
            page.screenshot(path=str(out / f"{label}-routes.png"))
            print(f"  {label}-routes.png")
    if crop and phase == "dividend":
        with map_view(page, "regular"):
            map_crop(page).screenshot(path=str(out / f"{label}-map-regular.png"))
            print(f"  {label}-map-regular.png")
    return ""


def shoot_phase(
    browser: Browser,
    web_url: str,
    token: str,
    game_id: str,
    out: Path,
    state: dict[str, Any],
    scale: float,
) -> str:
    """A full-viewport screenshot and the map alone at `scale` device pixels per CSS pixel, each
    with its Routes variant. Returns why the Routes shots were skipped, empty if they were not."""
    phase = state["phase"]
    label = f"{phase}-{state['roundLabel']}"
    skipped = ""
    for factor, crop in ((1, False), (scale, True)):
        context = browser.new_context(
            viewport=VIEWPORT, device_scale_factor=factor, color_scheme="dark"
        )
        context.add_init_script(f"localStorage.setItem('bby18.token', {json.dumps(token)})")
        page = context.new_page()
        open_game(page, web_url, game_id, phase)
        if not crop:
            page.screenshot(path=str(out / f"{label}.png"))
            print(f"  {label}.png")
        if phase == "stock":
            open_browsed_map(page)
        if crop:
            # The dividend view's map is zoomed to the paying network.
            map_crop(page).screenshot(path=str(out / f"{label}-map.png"))
            print(f"  {label}-map.png")
        if phase == "stock":
            # The browsed map starts with no corporation in focus, and Routes needs one.
            corporation = human_corporations(state)[0]["id"]
            page.locator(f'.rail--corporations [data-corp-id="{corporation}"]').first.click()
            settle_after_click(page)
        skipped = shoot_routes(page, label, phase, out, crop) or skipped
        context.close()
    return skipped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", nargs="?", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--round", type=int, default=6, help="first round (0 = SR1) to capture")
    parser.add_argument("--min-tiles", type=int, default=24)
    parser.add_argument(
        "--min-chains", type=int, default=2, help="supply chains the human's corporation must run"
    )
    parser.add_argument("--scale", type=float, default=2, help="device scale factor of map crops")
    args = parser.parse_args()
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)

    with servers() as (api_url, web_url), sync_playwright() as playwright:
        api = Api(api_url)
        board = api.board()
        game_id, state = api.new_game(args.seed)
        browser = playwright.chromium.launch()
        todo = list(PHASES)
        routes_skipped: dict[str, str] = {}
        while todo and state["phase"] != "game_over" and state["waitingOnHuman"]:
            phase = state["phase"]
            if phase in todo and is_developed(state, args):
                todo.remove(phase)
                # The game stays at this state while we look at it; the loop resumes afterwards.
                focus = state["currentCorporation"] or "none (the Routes shots focus the human's)"
                print(f"{phase}-{state['roundLabel']}: seed {args.seed}, focus {focus}")
                print(f"  {game_stats(state)}")
                routes_skipped[phase] = shoot_phase(
                    browser, web_url, api.token, game_id, out, state, args.scale
                )
            # At the facility limit the session skips the facility step, so the human keeps one
            # back until that step has been shot.
            limit = state["deathStar"]["fleets"]["limit"]
            facility_cap = limit - 1 if "fleet" in todo else limit
            state = api.act(game_id, choose(state, board, facility_cap))
        browser.close()
    for phase, reason in routes_skipped.items():
        print(f"Routes shots of {phase}: {'skipped, ' + reason if reason else 'taken'}")
    if todo:
        print(
            f"Not reached: {', '.join(todo)}. The game stopped at {state['roundLabel']} with "
            f"{len(state['tiles'])} tiles and {chain_count(state)} chains (wanted round "
            f"{args.round}, {args.min_tiles} tiles, {args.min_chains} chains). Try another --seed "
            "or lower the thresholds.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
