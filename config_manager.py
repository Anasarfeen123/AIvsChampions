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

CONFIG_FILE = os.path.expanduser("~/.pokemon_assistant_config.json")

DEFAULT_CONFIG = {
    "username": "",
    "password": "",
    "server": "localhost",
    "format": "gen9ou",
    "num_battles": 1,
    "last_team": "",
    "saved_teams": {},
    "last_opponent": "",
    "gemini_api_key": "",
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

BUILTIN_TEAM = """
Great Tusk @ Leftovers
Ability: Protosynthesis
Shiny: Yes
Tera Type: Water
EVs: 252 HP / 252 Def / 4 Spe
Impish Nature
- Earthquake
- Rapid Spin
- Knock Off
- Ice Spinner

Gholdengo @ Choice Scarf
Ability: Good as Gold
Shiny: Yes
Tera Type: Steel
EVs: 4 HP / 252 SpA / 252 Spe
Timid Nature
IVs: 0 Atk
- Make It Rain
- Shadow Ball
- Trick
- Focus Blast

Dragapult @ Choice Specs
Ability: Infiltrator
Shiny: Yes
Tera Type: Dragon
EVs: 4 HP / 252 SpA / 252 Spe
Timid Nature
- Draco Meteor
- Shadow Ball
- Flamethrower
- U-turn

Gliscor @ Toxic Orb
Ability: Poison Heal
Shiny: Yes
Tera Type: Water
EVs: 244 HP / 184 Def / 80 Spe
Impish Nature
- Spikes
- Earthquake
- Protect
- Toxic

Kingambit @ Black Glasses
Ability: Supreme Overlord
Shiny: Yes
Tera Type: Dark
EVs: 168 HP / 252 Atk / 88 Spe
Adamant Nature
- Kowtow Cleave
- Sucker Punch
- Iron Head
- Swords Dance

Iron Valiant @ Booster Energy
Ability: Quark Drive
Shiny: Yes
Tera Type: Fairy
EVs: 4 Atk / 252 SpA / 252 Spe
Naive Nature
- Moonblast
- Close Combat
- Thunderbolt
- Calm Mind
"""

FORMATS = [
    "gen9ou", "gen9ubers", "gen9uu", "gen9ru", "gen9nu", "gen9pu",
    "gen9lc", "gen9nationaldex", "gen9randombattle", "gen9doublesou",
    "gen9doublesrandombattle", "gen9vgc2026regg", "gen8ou", "gen8ubers",
]

def team_manager_menu(cfg: dict) -> str:
    while True:
        section("TEAM MANAGER")
        saved = cfg.get("saved_teams", {})

        if saved:
            print(f"{C.YELLOW}Saved teams:{C.RESET}")
            for i, name in enumerate(saved, 1):
                snippet = saved[name].strip().split("\n")[0]
                print(f"  {C.BOLD}[{i}]{C.RESET} {name:20s} → {C.DIM}{snippet}{C.RESET}")
        else:
            print(f"  {C.DIM}No saved teams yet.{C.RESET}")

        print(f"\n  {C.BOLD}[n]{C.RESET}  Import new team (paste showdown export)")
        if cfg.get("last_team"):
            print(f"  {C.BOLD}[l]{C.RESET}  Use last team")
        print(f"  {C.BOLD}[b]{C.RESET}  Use built-in example team")
        if saved:
            print(f"  {C.BOLD}[d]{C.RESET}  Delete a saved team")

        choice = input("\nChoice > ").strip().lower()

        if choice == "b":
            print(f"{C.GREEN}✓ Using built-in team.{C.RESET}")
            return BUILTIN_TEAM

        elif choice == "l" and cfg.get("last_team"):
            print(f"{C.GREEN}✓ Using last team.{C.RESET}")
            return cfg["last_team"]

        elif choice == "n":
            print(f"\n{C.YELLOW}Paste your Showdown team export below.")
            print(f"Enter a blank line followed by END (or just END) when done:{C.RESET}\n")
            lines = []
            while True:
                try:
                    line = input()
                except EOFError:
                    break
                if line.strip().upper() == "END":
                    break
                lines.append(line)
            team_str = "\n".join(lines).strip()
            if not team_str:
                print(f"{C.RED}Empty team — try again.{C.RESET}")
                continue

            save_name = input("Save this team as (leave blank to skip saving): ").strip()
            if save_name:
                cfg.setdefault("saved_teams", {})[save_name] = team_str
            cfg["last_team"] = team_str
            save_config(cfg)
            print(f"{C.GREEN}✓ Team loaded.{C.RESET}")
            return team_str

        elif choice == "d" and saved:
            name = input("Team name to delete: ").strip()
            if name in saved:
                del saved[name]
                save_config(cfg)
                print(f"{C.GREEN}✓ Deleted '{name}'.{C.RESET}")
            else:
                print(f"{C.RED}Team '{name}' not found.{C.RESET}")

        else:
            try:
                idx = int(choice) - 1
                name = list(saved.keys())[idx]
                team_str = saved[name]
                cfg["last_team"] = team_str
                save_config(cfg)
                print(f"{C.GREEN}✓ Using team: {name}{C.RESET}")
                return team_str
            except (ValueError, IndexError):
                print(f"{C.RED}Invalid choice.{C.RESET}")

def startup_wizard() -> dict:
    banner()
    cfg = load_config()

    section("ACCOUNT")
    username = ask("Bot Username (Separate from your browser account)", cfg.get("username") or "LLM_Bot")
    password = ask("Password (leave blank for guest/localhost)", cfg.get("password") or "")
    cfg["username"] = username
    cfg["password"] = password

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

    # Always use Gen 9 OU format
    cfg["format"] = "gen9ou"

    section("TEAM SELECTION")
    team_str = team_manager_menu(cfg)

    section("BATTLE MODE")
    print(f"  {C.BOLD}[1]{C.RESET} Accept challenges  (wait for someone to challenge you)")
    print(f"  {C.BOLD}[2]{C.RESET} Challenge a player  (you challenge someone by username)")
    print(f"  {C.BOLD}[3]{C.RESET} Ladder (seek random match)")
    mode_choice = ask("Mode", "1")

    opponent = ""
    if mode_choice == "2":
        last_opp = cfg.get("last_opponent", "")
        opponent = ask("Opponent username", last_opp)
        cfg["last_opponent"] = opponent

    cfg["mode"] = {"1": "accept", "2": "challenge", "3": "ladder"}.get(mode_choice, "accept")

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
    gemini_status = f"{C.GREEN}Configured{C.RESET}" if os.environ.get("GEMINI_API_KEY") else f"{C.YELLOW}Not Configured (Manual Fallback){C.RESET}"
    print(f"  Gemini API: {gemini_status}")

    confirm = ask(f"\n{C.GREEN}Start? (y/n)", "y")
    if confirm.lower() != "y":
        print("Aborted.")
        sys.exit(0)

    save_config(cfg)
    cfg["_team"]     = team_str
    cfg["_opponent"] = opponent
    return cfg
