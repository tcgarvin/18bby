"""Screenshot harness for the 18BBY web app (see README.md in this directory).

Starts the API (local mode, in-memory games) and a Vite dev server on free ports, plays one human
seat against bots with a fixed seed until the board has plenty of lanes, then screenshots the real
UI at the first stop in each phase.
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

from playwright.sync_api import Browser, sync_playwright

WEB_DIRECTORY = Path(__file__).resolve().parents[2]
REPO_ROOT = WEB_DIRECTORY.parent
DEFAULT_OUT = Path(
    "/tmp/claude-1000/-home-timg-code-18bby/03d2a5bf-1aa6-4c38-a53e-3f014af5b88e/scratchpad/shots"
)
PHASES = ("stock", "network", "fleet", "dividend")
VIEWPORT = {"width": 1600, "height": 1000}
SEATS = [{"name": "Tim"}] + [{"name": f"Bot {n}", "bot": True, "difficulty": "easy"} for n in "ABC"]
# The human charts as much as possible so the board fills up; every action is one the engine
# lists as legal. Upgrades add exits to charted tiles, which is what makes junctions.
ACTION_PREFERENCE = ("buy", "chart", "upgrade", "service", "build_facility", "dividend")


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
        self.token = self._request("/api/accounts", {})["token"]

    def _request(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        headers = {"content-type": "application/json"}
        if hasattr(self, "token"):
            headers["authorization"] = f"Bearer {self.token}"
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.base + path, data=data, headers=headers)
        try:
            with urllib.request.urlopen(request) as response:
                return json.load(response)  # type: ignore[no-any-return]
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"{path}: {exc.code} {exc.read().decode()}") from exc

    def new_game(self, seed: int) -> tuple[str, dict[str, Any]]:
        game = self._request("/api/games", {"seats": SEATS, "seed": seed})
        return game["gameId"], game["state"]

    def act(self, game_id: str, action: dict[str, Any]) -> dict[str, Any]:
        return self._request(f"/api/games/{game_id}/actions", {"action": action})


def choose(state: dict[str, Any]) -> dict[str, Any]:
    legal = state["legalActions"]
    for kind in ACTION_PREFERENCE:
        # Buying from the pool is skipped: it only shuffles shares between players.
        options = [a for a in legal if a["type"] == kind and a.get("source") != "pool"]
        if options:
            # The highest par puts the most cash in the new corporation's treasury to chart with.
            return max(options, key=lambda a: a.get("par", 0)) if kind == "buy" else options[0]
    return legal[0]


def lane_stats(state: dict[str, Any]) -> str:
    exits = Counter(len(tile["exits"]) for tile in state["tiles"])
    shared = sum(1 for tile in state["tiles"] if len(tile.get("service", [])) > 1)
    return (
        f"{len(state['tiles'])} tiles, exit counts {dict(sorted(exits.items()))}, {shared} shared"
    )


def play(api: Api, game_id: str, state: dict[str, Any], target_round: int, min_tiles: int):
    """Yield each state the human is asked to move in, once the game is far enough along."""
    while state["phase"] != "game_over" and state["waitingOnHuman"]:
        if state["roundNumber"] >= target_round and len(state["tiles"]) >= min_tiles:
            yield state
        state = api.act(game_id, choose(state))


INLINE_MAP_PHASES = ("network", "fleet")


def open_game(page: Page, web_url: str, game_id: str, phase: str) -> None:
    page.goto(f"{web_url}/?game={game_id}")
    page.wait_for_selector(f".stage--{phase}")
    page.wait_for_function("!document.querySelector('.stage--replaying')")
    page.wait_for_timeout(1200)


def shoot_phase(browser: Browser, web_url: str, token: str, game_id: str, out: Path, state, scale):
    """A full-viewport screenshot, then the map alone at `scale` device pixels per CSS pixel."""
    phase = state["phase"]
    label = f"{phase}-{state['roundLabel']}"
    for factor, suffix in ((1, ""), (scale, "-map")):
        context = browser.new_context(
            viewport=VIEWPORT, device_scale_factor=factor, color_scheme="dark"
        )
        context.add_init_script(f"localStorage.setItem('bby18.token', {json.dumps(token)})")
        page = context.new_page()
        open_game(page, web_url, game_id, phase)
        if factor == 1:
            page.screenshot(path=str(out / f"{label}.png"))
        else:
            # Only the network and facility views draw the map full size; the other views show a
            # thumbnail, so open the map overlay (the M key) and crop that.
            target = page.locator(".stage svg.hexmap")
            if phase not in INLINE_MAP_PHASES:
                page.keyboard.press("m")
                page.wait_for_selector(".overlay-map svg.hexmap")
                page.wait_for_timeout(1000)
                target = page.locator(".overlay__panel")
            target.first.screenshot(path=str(out / f"{label}{suffix}.png"))
        context.close()
        print(f"  {label}{suffix}.png")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", nargs="?", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--round", type=int, default=7, help="first round (0 = SR1) to capture")
    parser.add_argument("--min-tiles", type=int, default=20)
    parser.add_argument("--scale", type=float, default=2, help="device scale factor of map crops")
    args = parser.parse_args()
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)

    with servers() as (api_url, web_url), sync_playwright() as playwright:
        api = Api(api_url)
        game_id, state = api.new_game(args.seed)
        browser = playwright.chromium.launch()
        todo = list(PHASES)
        captured: dict[str, dict[str, Any]] = {}
        for state in play(api, game_id, state, args.round, args.min_tiles):
            phase = state["phase"]
            if phase in todo:
                todo.remove(phase)
                captured[phase] = state
                # The game stays at this state while we look at it; the driver resumes afterwards.
                label = f"{phase}-{state['roundLabel']}"
                print(f"{label}: {lane_stats(state)}")
                shoot_phase(browser, web_url, api.token, game_id, out, state, args.scale)
            if not todo:
                break
        browser.close()
        missing = [p for p in PHASES if p not in captured]
        if missing:
            print(f"Not reached: {', '.join(missing)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
