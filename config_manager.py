import os
import json
import sys

class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    RED    = "\033[91m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    BLUE   = "\033[94m"
    MAGENTA= "\033[95m"
    CYAN   = "\033[96m"
    WHITE  = "\033[97m"

def banner():
    print(f"""
{C.CYAN}{C.BOLD}
  ██████╗  ██████╗ ██╗  ██╗███████╗
  ██╔══██╗██╔═══██╗██║ ██╔╝██╔════╝
  ██████╔╝██║   ██║█████╔╝ █████╗
  ██╔═══╝ ██║   ██║██╔═██╗ ██╔══╝
  ██║     ╚██████╔╝██║  ██╗███████╗
  ╚═╝      ╚═════╝ ╚═╝  ╚═╝╚══════╝
  {C.RESET}{C.YELLOW}Showdown Battle Assistant  v2.0{C.RESET}
  {C.DIM}──────────────────────────────────{C.RESET}
""")

import urllib.request

CONFIG_FILE = os.path.expanduser("~/.pokemon_assistant_config.json")

def get_ollama_models() -> list:
    try:
        req = urllib.request.Request("http://localhost:11434/api/tags")
        with urllib.request.urlopen(req, timeout=2) as response:
            data = json.loads(response.read().decode())
            return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []

DEFAULT_CONFIG = {
    "username": "User",
    "password": "",
    "server": "localhost",
    "format": "gen9nationaldexounotera",
    "num_battles": 1,
    "last_team": "",
    "saved_teams": {},
    "last_opponent": "",
    "gemini_api_key": "",
    "llm_provider": "puter",
    "ollama_model": "qwen2.5:7b",
    "puter_model": "claude-3-5-sonnet",
}

def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                data = json.load(f)
            for k, v in DEFAULT_CONFIG.items():
                data.setdefault(k, v)
            return data
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()

def save_config(cfg: dict):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)

def ask(prompt: str, default: str = "") -> str:
    display = f"{prompt} [{default}]: " if default else f"{prompt}: "
    val = input(display).strip()
    return val if val else default

def section(title: str):
    print(f"\n{C.CYAN}{C.BOLD}── {title} {'─' * max(0, 50 - len(title))}{C.RESET}")

RED_MT_SILVER_TEAM = """
Pikachu @ Light Ball
Ability: Static
EVs: 252 Atk / 4 SpA / 252 Spe
Naive Nature
- Volt Tackle
- Thunderbolt
- Iron Tail
- Quick Attack

Espeon @ Light Clay
Ability: Magic Bounce
EVs: 252 HP / 4 SpA / 252 Spe
Timid Nature
IVs: 0 Atk
- Psychic
- Shadow Ball
- Reflect
- Calm Mind

Snorlax @ Leftovers
Ability: Thick Fat
EVs: 252 HP / 4 Atk / 252 SpD
Careful Nature
- Body Slam
- Crunch
- Earthquake
- Rest

Venusaur @ Black Sludge
Ability: Overgrow
EVs: 252 HP / 4 SpA / 252 Spe
Timid Nature
IVs: 0 Atk
- Giga Drain
- Sludge Bomb
- Leech Seed
- Growth

Charizard @ Heavy-Duty Boots
Ability: Blaze
EVs: 4 Atk / 252 SpA / 252 Spe
Naive Nature
- Flamethrower
- Air Slash
- Dragon Pulse
- Earthquake

Blastoise @ White Herb
Ability: Torrent
EVs: 4 Def / 252 SpA / 252 Spe
Modest Nature
IVs: 0 Atk
- Hydro Pump
- Ice Beam
- Flash Cannon
- Shell Smash
"""

BLUE_TEAM = """
Pidgeot @ Heavy-Duty Boots
Ability: Keen Eye
EVs: 4 Def / 252 SpA / 252 Spe
Timid Nature
IVs: 0 Atk
- Hurricane
- Heat Wave
- Roost
- Defog

Alakazam @ Focus Sash
Ability: Magic Guard
EVs: 4 Def / 252 SpA / 252 Spe
Timid Nature
IVs: 0 Atk
- Psychic
- Focus Blast
- Shadow Ball
- Nasty Plot

Rhydon @ Eviolite
Ability: Lightning Rod
EVs: 252 HP / 252 Atk / 4 SpD
Adamant Nature
- Earthquake
- Stone Edge
- Megahorn
- Stealth Rock

Exeggutor @ Sitrus Berry
Ability: Chlorophyll
EVs: 252 HP / 252 SpA / 4 SpD
Modest Nature
IVs: 0 Atk
- Psychic
- Giga Drain
- Leech Seed
- Sunny Day

Gyarados @ Heavy-Duty Boots
Ability: Intimidate
EVs: 252 Atk / 4 SpD / 252 Spe
Jolly Nature
- Waterfall
- Crunch
- Earthquake
- Dragon Dance

Arcanine @ Heavy-Duty Boots
Ability: Intimidate
EVs: 252 Atk / 4 SpD / 252 Spe
Jolly Nature
- Flare Blitz
- Extreme Speed
- Close Combat
- Morning Sun
"""

BUILTIN_TEAM = RED_MT_SILVER_TEAM

FORMATS = [
    "gen9nationaldexounotera", "gen9ounotera", "gen9ou", "gen9ubers", "gen9uu", "gen9ru", "gen9nu", "gen9pu",
    "gen9lc", "gen9nationaldex", "gen9randombattle", "gen9doublesou",
    "gen9doublesrandombattle", "gen9vgc2026regg", "gen8ou", "gen8ubers",
]

def team_manager_menu(cfg: dict) -> str:
    section("TEAM LOCK")
    cfg["last_team"] = RED_MT_SILVER_TEAM
    cfg["ai_team"] = BLUE_TEAM
    cfg["saved_teams"] = {
        "Red - Mt. Silver": RED_MT_SILVER_TEAM,
        "Blue": BLUE_TEAM,
    }
    print(f"  Player team: {C.CYAN}Red - Mt. Silver{C.RESET}")
    print(f"  AI team    : {C.CYAN}Blue{C.RESET}")
    return RED_MT_SILVER_TEAM

def startup_wizard() -> dict:
    banner()
    cfg = load_config()

    section("ACCOUNT")
    cfg["username"] = "User"
    cfg["password"] = ""
    print(f"  Logged in as: {C.CYAN}{cfg['username']}{C.RESET}")
    print(f"  {C.DIM}Using guest/localhost login; username is fixed for this assistant.{C.RESET}")

    section("LLM PROVIDER")
    print(f"  {C.BOLD}[1]{C.RESET} Gemini API  (cloud)")
    print(f"  {C.BOLD}[2]{C.RESET} Ollama  (local model)")
    print(f"  {C.BOLD}[3]{C.RESET} Puter.js  (Puter cloud AI)")
    default_provider = "3" if cfg.get("llm_provider") == "puter" else ("2" if cfg.get("llm_provider") == "ollama" else "1")
    provider_choice = ask("LLM Provider", default_provider)

    if provider_choice == "3":
        cfg["llm_provider"] = "puter"
        cfg["puter_model"] = ask("Puter model", cfg.get("puter_model", "claude-3-5-sonnet"))
    elif provider_choice == "2":
        cfg["llm_provider"] = "ollama"
        models = get_ollama_models()
        if models:
            print("\n  Available local models:")
            for i, model in enumerate(models, 1):
                print(f"    {C.BOLD}[{i}]{C.RESET} {model}")
            
            # Select qwen2.5:7b or llama3:latest as default if present
            default_idx = "1"
            for idx, m in enumerate(models, 1):
                if "qwen" in m.lower():
                    default_idx = str(idx)
                    break
            
            choice_idx = int(ask("Select model number", default_idx)) - 1
            if 0 <= choice_idx < len(models):
                cfg["ollama_model"] = models[choice_idx]
            else:
                cfg["ollama_model"] = models[0]
        else:
            print(f"\n  {C.YELLOW}⚠️  No local Ollama models detected. Is Ollama running on localhost:11434?{C.RESET}")
            cfg["ollama_model"] = ask("Enter Ollama model name manually", "qwen2.5:7b")
    else:
        cfg["llm_provider"] = "gemini"
        section("GEMINI API CONFIG")
        gemini_key = os.environ.get("GEMINI_API_KEY") or cfg.get("gemini_api_key") or ""
        prompt_key = f"{gemini_key[:4]}...{gemini_key[-4:]}" if len(gemini_key) > 8 else ""
        user_key = ask(f"Gemini API Key {f'({prompt_key})' if prompt_key else ''}", "")
        if user_key:
            cfg["gemini_api_key"] = user_key
            os.environ["GEMINI_API_KEY"] = user_key
        elif gemini_key:
            cfg["gemini_api_key"] = gemini_key
            os.environ["GEMINI_API_KEY"] = gemini_key

    section("SERVER")
    print(f"  {C.BOLD}[1]{C.RESET} localhost  (local Showdown instance)")
    print(f"  {C.BOLD}[2]{C.RESET} Pokémon Showdown  (online: play.pokemonshowdown.com)")
    srv_choice = ask("Server", "1" if cfg.get("server", "localhost") == "localhost" else "2")
    cfg["server"] = "localhost" if srv_choice != "2" else "showdown"

    # Use National Dex so Red and Blue's classic teams are legal, with Tera disabled.
    cfg["format"] = "gen9nationaldexounotera"
    print(f"\n  Format locked to: {C.CYAN}National Dex OU (No Tera){C.RESET} ({cfg['format']})")

    section("TEAM SELECTION")
    team_str = team_manager_menu(cfg)

    section("BATTLE MODE")
    print(f"  {C.BOLD}[1]{C.RESET} Accept Blue AI challenge")
    print(f"  {C.BOLD}[2]{C.RESET} Challenge Blue AI")
    mode_choice = ask("Mode", "2")

    opponent = ""
    if mode_choice == "2":
        opponent = "AI"
        cfg["last_opponent"] = opponent

    cfg["mode"] = {"1": "accept", "2": "challenge"}.get(mode_choice, "challenge")

    section("SESSION")
    try:
        num = int(ask("Number of battles", str(cfg.get("num_battles", 1))))
    except ValueError:
        num = 1
    cfg["num_battles"] = max(1, num)

    section("SESSION SUMMARY")
    print(f"  Username  : {C.CYAN}{cfg['username']}{C.RESET}")
    print(f"  Server    : {C.CYAN}{cfg['server']}{C.RESET}")
    print(f"  Format    : {C.CYAN}{cfg['format']}{C.RESET}")
    print(f"  Mode      : {C.CYAN}{cfg['mode']}{C.RESET}" + (f"  →  {C.YELLOW}{opponent}{C.RESET}" if opponent else ""))
    print(f"  Battles   : {C.CYAN}{cfg['num_battles']}{C.RESET}")
    first_mon = team_str.strip().split("\n")[0]
    print(f"  Team lead : {C.CYAN}{first_mon}{C.RESET}")
    ai_first_mon = BLUE_TEAM.strip().split("\n")[0]
    print(f"  AI team   : {C.CYAN}{ai_first_mon} / Blue{C.RESET}")
    llm_provider = cfg.get("llm_provider", "puter")
    if llm_provider == "puter":
        llm_status = f"{C.GREEN}Puter.js ({cfg.get('puter_model', 'claude-3-5-sonnet')}){C.RESET}"
    elif llm_provider == "ollama":
        llm_status = f"{C.GREEN}Ollama ({cfg.get('ollama_model')}){C.RESET}"
    else:
        gemini_status = f"{C.GREEN}Configured{C.RESET}" if os.environ.get("GEMINI_API_KEY") else f"{C.YELLOW}Not Configured (Manual Fallback){C.RESET}"
        llm_status = f"Gemini API ({gemini_status})"
    print(f"  LLM Model : {llm_status}")

    confirm = ask(f"\n{C.GREEN}Start? (y/n)", "y")
    if confirm.lower() != "y":
        print("Aborted.")
        sys.exit(0)

    save_config(cfg)
    cfg["_team"]     = team_str
    cfg["_ai_team"]  = BLUE_TEAM
    cfg["_opponent"] = opponent
    return cfg
