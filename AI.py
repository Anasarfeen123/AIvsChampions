import asyncio
import socket
import subprocess
import time
import logging
import argparse
import os
from pathlib import Path

from poke_env.ps_client.account_configuration import AccountConfiguration
from poke_env.teambuilder.constant_teambuilder import ConstantTeambuilder
from poke_env import LocalhostServerConfiguration, ShowdownServerConfiguration
from assistant_player import PokémonAssistant
from config_manager import BLUE_TEAM, C

FORMAT = "gen9nationaldexounotera"
NUM_BATTLES = 1
SHOWDOWN_DIR = Path(__file__).resolve().parent / "pokemon-showdown"
SHOWDOWN_PORT = 8000

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

async def main():
    parser = argparse.ArgumentParser(description="Pokémon Showdown LLM Opponent")
    parser.add_argument("--provider", "-p", choices=["gemini", "ollama"], default="ollama", help="LLM Provider (default: ollama)")
    parser.add_argument("--model", "-m", default="qwen2.5:7b", help="Ollama model name (default: qwen2.5:7b)")
    parser.add_argument("--server", "-s", choices=["localhost", "showdown"], default="localhost", help="Server to connect to (default: localhost)")
    parser.add_argument("--battles", "-b", type=int, default=1, help="Number of battles to play (default: 1)")
    
    args = parser.parse_args()

    logging.basicConfig(format="%(message)s", level=logging.WARNING)
    logging.getLogger("poke_env").setLevel(logging.INFO)

    server_process = ensure_showdown_server()

    ai_team = BLUE_TEAM
    fmt = FORMAT
    server_cfg = (
        LocalhostServerConfiguration if args.server == "localhost"
        else ShowdownServerConfiguration
    )

    ai_teambuilder = ConstantTeambuilder(ai_team)

    blue_ai = PokémonAssistant(
        account_configuration=AccountConfiguration("AI", None),
        gemini_api_key=os.environ.get("GEMINI_API_KEY"),
        llm_provider=args.provider,
        ollama_model=args.model,
        auto_play=True,
        battle_format=fmt,
        team=ai_teambuilder,
        server_configuration=server_cfg,
    )

    print(f"\n{C.GREEN}{C.BOLD}🤖  Blue AI is online (LLM-controlled).{C.RESET}")
    print(f"🌐  Open: {C.CYAN}http://localhost:8000/{C.RESET}")
    print(f"👤  Log in to your browser as {C.CYAN}User{C.RESET} to challenge or accept challenges from Blue AI.")
    print(f"🧠  LLM Model: {args.provider} ({args.model if args.provider == 'ollama' else 'Gemini API'})")
    print(f"📦  AI team loaded: Blue.")
    print(f"🎮  Format: {fmt}")

    print(f"⚔️   Waiting for browser User, then challenging with Blue…\n")
    try:
        # Cross-thread safe check for login
        while not blue_ai.ps_client.logged_in.is_set():
            await asyncio.sleep(0.1)

        async def challenge_loop():
            while not blue_ai.battles:
                try:
                    await blue_ai.ps_client.challenge("User", fmt, blue_ai.get_next_team())
                except Exception:
                    pass
                await asyncio.sleep(12)

        async def accept_loop():
            try:
                await blue_ai.accept_challenges("User", args.battles)
            except Exception:
                pass

        challenge_task = asyncio.create_task(challenge_loop())
        accept_task = asyncio.create_task(accept_loop())

        while not blue_ai.battles:
            await asyncio.sleep(0.5)

        challenge_task.cancel()
        accept_task.cancel()

        while blue_ai.n_finished_battles < args.battles:
            await asyncio.sleep(1)
    finally:
        if server_process is not None:
            server_process.terminate()


if __name__ == "__main__":
    asyncio.run(main())
