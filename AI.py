import asyncio
import socket
import subprocess
import time
import logging
import argparse
import os
import signal
import re
from pathlib import Path

from poke_env.ps_client.account_configuration import AccountConfiguration
from poke_env.teambuilder.constant_teambuilder import ConstantTeambuilder
from poke_env import LocalhostServerConfiguration, ShowdownServerConfiguration
from assistant_player import PokémonAssistant
from config_manager import BLUE_TEAM, C

FORMAT = "gen9nationaldexounotera"
SHOWDOWN_DIR = Path(__file__).resolve().parent / "pokemon-showdown"
SHOWDOWN_PORT = int(os.environ.get("PORT") or os.environ.get("PSPORT") or 8000)

def is_showdown_running() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex(("127.0.0.1", SHOWDOWN_PORT)) == 0

def ensure_showdown_server() -> subprocess.Popen | None:
    if is_showdown_running():
        print(f"✅  Local Pokémon Showdown already running on port {SHOWDOWN_PORT}.", flush=True)
        return None
    print(f"🚀  Starting local Pokémon Showdown on port {SHOWDOWN_PORT}…", flush=True)
    server = subprocess.Popen(
        ["node", "pokemon-showdown", "start", str(SHOWDOWN_PORT)],
        cwd=SHOWDOWN_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if server.poll() is not None:
            raise RuntimeError("Local Pokémon Showdown exited before it was ready.")
        if is_showdown_running():
            print("✅  Local Pokémon Showdown is ready.", flush=True)
            return server
        time.sleep(0.25)
    server.terminate()
    raise TimeoutError("Timed out waiting for local Pokémon Showdown to start.")

def has_unfinished_battle(blue_ai: PokémonAssistant) -> bool:
    return any(not b.finished for b in blue_ai._battles.values())

async def play_one_battle(blue_ai: PokémonAssistant, fmt: str, shutdown_event: asyncio.Event) -> bool:
    """Challenge Red Human, play one battle, return False on shutdown."""
    def target_user() -> str:
        name = (blue_ai.get_browser_username() or "").strip()
        userid = re.sub(r"[^a-z0-9]+", "", name.lower())
        if not userid or userid in {"blueai", "guest", "guest1", "guest2", "system"}:
            return "Red Human"
        return name

    async def challenge_loop():
        if shutdown_event.is_set():
            return
        target = target_user()
        try:
            print(f"🎯  Challenging target: {target}")
            try:
                await blue_ai.ps_client.send_message(f"/cancelchallenge {target}")
            except Exception:
                pass
            await asyncio.sleep(0.25)
            await blue_ai.ps_client.challenge(target, fmt, blue_ai.get_next_team())
        except Exception:
            pass
        while not has_unfinished_battle(blue_ai) and not shutdown_event.is_set():
            await asyncio.sleep(0.5)

    async def accept_loop():
        while not has_unfinished_battle(blue_ai) and not shutdown_event.is_set():
            try:
                await blue_ai.accept_challenges(target_user(), 1)
            except Exception:
                pass
            await asyncio.sleep(1)

    challenge_task = asyncio.create_task(challenge_loop())
    accept_task = asyncio.create_task(accept_loop())

    while not has_unfinished_battle(blue_ai) and not shutdown_event.is_set():
        await asyncio.sleep(0.5)

    if challenge_task:
        challenge_task.cancel()
    if accept_task:
        accept_task.cancel()

    if shutdown_event.is_set():
        return False

    n_before = blue_ai.n_finished_battles
    while blue_ai.n_finished_battles <= n_before and not shutdown_event.is_set():
        await asyncio.sleep(1)

    return not shutdown_event.is_set()

async def main():
    parser = argparse.ArgumentParser(description="Pokémon Showdown LLM Opponent")
    parser.add_argument("--provider", "-p", choices=["gemini", "ollama", "puter"], default="puter", help="LLM Provider (default: puter)")
    parser.add_argument("--model", "-m", default="qwen2.5:7b", help="Ollama model name (default: qwen2.5:7b)")
    parser.add_argument("--puter-model", default="claude-3-5-sonnet", help="Puter model name (default: claude-3-5-sonnet)")
    parser.add_argument("--server", "-s", choices=["localhost", "showdown"], default="localhost", help="Server to connect to (default: localhost)")
    parser.add_argument("--wizard", "-w", action="store_true", help="Run the interactive setup wizard")

    args = parser.parse_args()

    logging.basicConfig(format="%(message)s", level=logging.WARNING)
    logging.getLogger("poke_env").setLevel(logging.INFO)

    if args.wizard:
        from config_manager import startup_wizard
        cfg = startup_wizard()
        ai_team = cfg["_ai_team"]
        fmt = cfg["format"]
        server = cfg["server"]
        llm_provider = cfg.get("llm_provider", "puter")
        ollama_model = cfg.get("ollama_model", "qwen2.5:7b")
        puter_model = cfg.get("puter_model", "claude-3-5-sonnet")
        gemini_api_key = cfg.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY")
    else:
        ai_team = BLUE_TEAM
        fmt = FORMAT
        server = args.server
        llm_provider = args.provider
        ollama_model = args.model
        puter_model = args.puter_model
        gemini_api_key = os.environ.get("GEMINI_API_KEY")

    server_process = ensure_showdown_server()

    server_cfg = (
        LocalhostServerConfiguration if server == "localhost"
        else ShowdownServerConfiguration
    )

    ai_teambuilder = ConstantTeambuilder(ai_team)

    blue_ai = PokémonAssistant(
        account_configuration=AccountConfiguration("Blue AI", None),
        gemini_api_key=gemini_api_key,
        llm_provider=llm_provider,
        ollama_model=ollama_model,
        puter_model=puter_model,
        auto_play=True,
        battle_format=fmt,
        team=ai_teambuilder,
        server_configuration=server_cfg,
        log_level=logging.INFO,
    )

    print(f"\n{C.GREEN}{C.BOLD}🤖  Blue AI is online (LLM-controlled).{C.RESET}")
    print(f"🌐  Open: {C.CYAN}http://localhost:8000/{C.RESET}")
    print(f"👤  Open the browser, pick a difficulty, and battle!")

    shutdown_event = asyncio.Event()

    def _on_sigint():
        print(f"\n{C.YELLOW}⚠️  Interrupt received, forfeiting battles and shutting down...{C.RESET}")
        shutdown_event.set()

    loop = asyncio.get_event_loop()
    try:
        loop.add_signal_handler(signal.SIGINT, _on_sigint)
    except NotImplementedError:
        pass

    try:
        while not blue_ai.ps_client.logged_in.is_set() and not shutdown_event.is_set():
            await asyncio.sleep(0.1)
        if shutdown_event.is_set():
            return

        await blue_ai.ps_client.send_message("/join lobby")
        await blue_ai.ps_client.send_message("/avatar blue")
        print(f"\n{C.GREEN}🎮  Waiting for difficulty selection from browser...{C.RESET}")

        while not shutdown_event.is_set():
            # ── Outer loop: wait for a difficulty selection ──
            blue_ai.difficulty_event.clear()
            while not blue_ai.difficulty_event.is_set() and not shutdown_event.is_set():
                await asyncio.sleep(0.2)
            if shutdown_event.is_set():
                break

            print(f"⚔️  Challenging with {blue_ai.current_difficulty} difficulty…\n")
            blue_ai.difficulty_event.clear()

            # ── Inner loop: keep playing rematches with this difficulty ──
            while not shutdown_event.is_set():
                blue_ai.rematch_event.clear()
                ok = await play_one_battle(blue_ai, fmt, shutdown_event)
                if not ok:
                    break

                print(f"\n{C.GREEN}✅  Battle finished.{C.RESET}")

                # Wait for either rematch (!rematch) or difficulty change (!difficulty)
                while not shutdown_event.is_set():
                    if blue_ai.difficulty_event.is_set():
                        break  # Break all the way out to outer loop
                    if blue_ai.rematch_event.is_set():
                        blue_ai.rematch_event.clear()
                        print("🔄  Rematch requested! Challenging again...\n")
                        break  # Stay in inner loop
                    await asyncio.sleep(0.2)

                if blue_ai.difficulty_event.is_set():
                    break  # Back to outer loop (new difficulty)

    except asyncio.CancelledError:
        pass
    finally:
        if shutdown_event.is_set():
            for tag, battle in list(blue_ai.battles.items()):
                if not battle.finished:
                    try:
                        await blue_ai.ps_client.send_message("/forfeit", room=tag)
                        print(f"{C.YELLOW}  Forfeited battle: {tag}{C.RESET}")
                    except Exception:
                        pass
        if server_process is not None:
            server_process.terminate()


if __name__ == "__main__":
    asyncio.run(main())
