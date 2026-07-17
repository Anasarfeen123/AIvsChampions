"""
Pokémon Showdown Battle Assistant
Enhanced with: startup wizard, team import, username config,
challenge mode (seek OR challenge player), and more.
"""

import asyncio
import subprocess
import shutil
import sys
import os
import json
import textwrap
import re
from typing import Optional, List, Dict
from poke_env.player import Player
from poke_env.player.battle_order import DoubleBattleOrder, SingleBattleOrder, PassBattleOrder
from poke_env.battle.battle import Battle
from poke_env.battle.double_battle import DoubleBattle
from poke_env.battle.pokemon import Pokemon
from poke_env.battle.move import Move
from poke_env.ps_client.account_configuration import AccountConfiguration
from poke_env.teambuilder.constant_teambuilder import ConstantTeambuilder
from poke_env import LocalhostServerConfiguration, ShowdownServerConfiguration


# ─────────────────────────────────────────────────────────────────────────────
# ANSI COLORS (terminal)
# ─────────────────────────────────────────────────────────────────────────────

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
  ######   ######  ##  ##  ######
  ##  ##  ##   ## ##  ##  ##
  ######  ##   ## ####    ####
  ##      ##   ## ##  ##  ##
  ##       ######  ##  ##  ######
  {C.RESET}{C.YELLOW}Showdown Battle Assistant  v2.0{C.RESET}
  {C.DIM}--------------------------------{C.RESET}
""")


# ─────────────────────────────────────────────────────────────────────────────
# CONFIG PERSISTENCE
# ─────────────────────────────────────────────────────────────────────────────

CONFIG_FILE = os.path.expanduser("~/.pokemon_assistant_config.json")

DEFAULT_CONFIG = {
    "username": "",
    "password": "",
    "server": "localhost",         # "localhost" or "showdown"
    "format": "gen9ou",
    "num_battles": 1,
    "last_team": "",
    "saved_teams": {},             # name → team_string
    "last_opponent": "",
    "llm_provider": "ollama",      # "ollama", "gemini", "openai"
    "llm_model": "llama3",         # default model name
    "llm_api_key": "",
    "llm_api_base": "",
}

def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                data = json.load(f)
            # Merge missing keys from default
            for k, v in DEFAULT_CONFIG.items():
                data.setdefault(k, v)
            return data
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()

def save_config(cfg: dict):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


# ─────────────────────────────────────────────────────────────────────────────
# DISPLAY HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def hp_str(mon: Pokemon) -> str:
    pct = mon.current_hp_fraction * 100
    bar_len = 20
    filled = int(pct / 100 * bar_len)
    bar = "█" * filled + "░" * (bar_len - filled)
    color = "🟢" if pct > 50 else ("🟡" if pct > 25 else "🔴")
    return f"{color} {pct:.1f}% [{bar}]"


def status_str(mon: Pokemon) -> str:
    return mon.status.name if mon.status else "None"


def boosts_str(mon: Pokemon) -> str:
    active = {k: v for k, v in mon.boosts.items() if v != 0}
    if not active:
        return "None"
    return ", ".join(f"{k.upper()}: {'+' if v > 0 else ''}{v}" for k, v in active.items())


def format_move(move: Move) -> str:
    power    = move.base_power if move.base_power else "—"
    acc      = f"{int(move.accuracy * 100)}%" if isinstance(move.accuracy, float) else "∞"
    category = move.category.name if move.category else "?"
    pp_left  = move.current_pp if hasattr(move, "current_pp") and move.current_pp is not None else "?"
    pp_max   = move.max_pp    if hasattr(move, "max_pp")     and move.max_pp     is not None else "?"
    return (
        f"{move.id.upper():20s} | Type: {move.type.name:8s} | "
        f"Cat: {category:8s} | BP: {str(power):4s} | Acc: {acc:4s} | PP: {pp_left}/{pp_max}"
    )


def team_summary(team: dict) -> str:
    lines = []
    for mon in team.values():
        status  = f" [{mon.status.name}]" if mon.status else ""
        fainted = " ☠️  FAINTED"           if mon.fainted else ""
        hp      = f"{mon.current_hp_fraction * 100:.0f}%" if not mon.fainted else "0%"
        item    = f" @{mon.item}"          if mon.item    else ""
        lines.append(f"  • {mon.species:16s} | HP: {hp:5s}{status}{item}{fainted}")
    return "\n".join(lines) if lines else "  (none)"


def opp_team_summary(team: dict) -> str:
    lines = []
    for mon in team.values():
        status    = f" [{mon.status.name}]"             if mon.status      else ""
        fainted   = " ☠️  FAINTED"                       if mon.fainted     else ""
        hp        = f"{mon.current_hp_fraction * 100:.0f}%" if not mon.fainted else "0%"
        item      = f" @{mon.item}"                     if mon.item        else " @Unknown"
        moves_seen = list(mon.moves.keys())
        move_str  = f" | Moves: [{', '.join(moves_seen)}]" if moves_seen  else ""
        lines.append(f"  • {mon.species:16s} | HP: {hp:5s}{status}{item}{fainted}{move_str}")
    return "\n".join(lines) if lines else "  (none)"


def hazards_str(conditions: dict) -> str:
    if not conditions:
        return "None"
    parts = []
    for cond, val in conditions.items():
        name = cond.name if hasattr(cond, "name") else str(cond)
        parts.append(f"{name}({val})" if val > 1 else name)
    return ", ".join(parts)


def weather_terrain_str(battle: Battle) -> str:
    parts = []
    for w in battle.weather:
        parts.append(f"Weather: {w.name if hasattr(w, 'name') else str(w)}")
    for f in battle.fields:
        parts.append(f"Terrain: {f.name if hasattr(f, 'name') else str(f)}")
    return " | ".join(parts) if parts else "None"


def screens_str(battle: Battle) -> str:
    SCREEN_NAMES = {"reflect", "lightscreen", "auroraveil"}
    my_screens, opp_screens = [], []
    for cond, val in battle.side_conditions.items():
        name = cond.name if hasattr(cond, "name") else str(cond)
        if name.lower() in SCREEN_NAMES:
            my_screens.append(f"{name}({val})")
    for cond, val in battle.opponent_side_conditions.items():
        name = cond.name if hasattr(cond, "name") else str(cond)
        if name.lower() in SCREEN_NAMES:
            opp_screens.append(f"{name}({val})")
    my  = ", ".join(my_screens)  or "None"
    opp = ", ".join(opp_screens) or "None"
    return f"Mine: {my} | Opp: {opp}"


# ─────────────────────────────────────────────────────────────────────────────
# PROMPT BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def build_llm_prompt(battle: Battle) -> str:
    me  = battle.active_pokemon
    opp = battle.opponent_active_pokemon

    raw = me.stats or {}
    stats_str = (
        f"HP:{raw.get('hp','?')} Atk:{raw.get('atk','?')} Def:{raw.get('def','?')} "
        f"SpA:{raw.get('spa','?')} SpD:{raw.get('spd','?')} Spe:{raw.get('spe','?')}"
    )

    my_moves_block = "\n".join(
        f"  [{i+1}] {format_move(m)}" for i, m in enumerate(battle.available_moves)
    ) or "  (none)"

    opp_moves_seen = list(opp.moves.keys()) if opp.moves else []
    opp_item    = opp.item    or "Unknown"
    opp_ability = opp.ability or "Unknown"
    opp_tera    = opp.tera_type.name if opp.tera_type else "Unknown"

    my_tera        = me.tera_type.name if me.tera_type else "Available (not yet used)"
    tera_activated = "YES – TYPE CHANGED" if me.is_terastallized else "No"
    tera_available = "✨ YES" if battle.can_tera else "No"

    switches_block = "\n".join(
        f"  [{i+1}] {s.species:16s} | HP: {s.current_hp_fraction*100:.0f}%"
        + (f" | Status: {s.status.name}" if s.status else "")
        + (f" | @{s.item}"               if s.item   else "")
        for i, s in enumerate(battle.available_switches)
    ) or "  (none)"

    return f"""
╔══════════════════════════════════════════════════════════════════╗
║          GRANDMASTER POKÉMON BATTLE STATE — TURN {battle.turn:>3}           ║
╚══════════════════════════════════════════════════════════════════╝

━━━━━━━━━━━━━━━━━━━━━━ MY ACTIVE ━━━━━━━━━━━━━━━━━━━━━━
[MY_ACTIVE]:     {me.species}
[HP_PERCENT]:    {hp_str(me)}
[ITEM]:          {me.item or 'Unknown'}
[ABILITY]:       {me.ability or 'Unknown'}
[STATS]:         {stats_str}
[STAT_STAGES]:   {boosts_str(me)}
[STATUS]:        {status_str(me)}
[TERA_TYPE]:     {my_tera}  (Activated: {tera_activated} | Available: {tera_available})

[MY MOVES]:
{my_moves_block}

━━━━━━━━━━━━━━━━━━━━ OPPONENT ACTIVE ━━━━━━━━━━━━━━━━━━
[OPP_ACTIVE]:    {opp.species}
[HP_PERCENT]:    {hp_str(opp)}
[ITEM]:          {opp_item}
[ABILITY]:       {opp_ability}
[STAT_STAGES]:   {boosts_str(opp)}
[STATUS]:        {status_str(opp)}
[TERA_TYPE]:     {opp_tera}  (Activated: {'YES' if opp.is_terastallized else 'No'})

[OPP_REVEALED_MOVES]:
{chr(10).join(f"  • {m}" for m in opp_moves_seen) if opp_moves_seen else "  (none revealed yet)"}

━━━━━━━━━━━━━━━━━━━━━━━ TEAMS ━━━━━━━━━━━━━━━━━━━━━━━━
[MY_TEAM]:
{team_summary(battle.team)}

[OPP_TEAM]:
{opp_team_summary(battle.opponent_team)}

━━━━━━━━━━━━━━━━━━━━━ FIELD STATE ━━━━━━━━━━━━━━━━━━━━
[WEATHER_TERRAIN]: {weather_terrain_str(battle)}
[HAZARDS_MINE]:    {hazards_str(battle.side_conditions)}
[HAZARDS_OPP]:     {hazards_str(battle.opponent_side_conditions)}
[SCREENS]:         {screens_str(battle)}

━━━━━━━━━━━━━━━━━━━ AVAILABLE SWITCHES ━━━━━━━━━━━━━━━
{switches_block}
""".strip()


def format_target(target) -> str:
    if not target:
        return "Unknown"
    name = target.name if hasattr(target, "name") else str(target)
    mapping = {
        "ADJACENT_FOE": "Adjacent Foe (Opponent 1 or 2)",
        "ANY": "Any adjacent or self (Ally/Opponent 1 or 2)",
        "NORMAL": "Normal (Ally/Opponent 1 or 2)",
        "ADJACENT_ALLY": "Adjacent Ally (partner)",
        "ADJACENT_ALLY_OR_SELF": "Adjacent Ally or Self",
        "ALL": "All field",
        "ALL_ADJACENT": "All adjacent",
        "ALL_ADJACENT_FOES": "All adjacent foes",
        "ALLIES": "Allies",
        "ALLY_SIDE": "Ally side",
        "ALLY_TEAM": "Ally team",
        "FOE_SIDE": "Foe side",
        "RANDOM_NORMAL": "Random normal foe",
        "SELF": "Self",
    }
    return mapping.get(name, name)


def format_order_for_display(order: SingleBattleOrder, battle: DoubleBattle) -> str:
    if isinstance(order, PassBattleOrder):
        return "Pass"
    
    # If it is a switch
    if isinstance(order.order, Pokemon):
        return f"Switch to {order.order.species} (HP: {order.order.current_hp_fraction * 100:.0f}%)"
    
    # If it is a move
    if isinstance(order.order, Move):
        move_name = order.order.id.upper()
        flags = []
        if order.mega:
            flags.append("MEGA")
        if order.z_move:
            flags.append("Z-MOVE")
        if order.dynamax:
            flags.append("DYNAMAX")
        if order.terastallize:
            flags.append("TERASTALLIZE")
        
        flag_str = f" [{'+'.join(flags)}]" if flags else ""
        
        # Target representation
        target_val = order.move_target
        target_name = "None"
        if target_val == -1:
            ally_mon = battle.active_pokemon[0]
            target_name = f"Ally Slot 1 ({ally_mon.species if ally_mon else 'Empty'})"
        elif target_val == -2:
            ally_mon = battle.active_pokemon[1]
            target_name = f"Ally Slot 2 ({ally_mon.species if ally_mon else 'Empty'})"
        elif target_val == 1:
            opp_mon = battle.opponent_active_pokemon[0]
            target_name = f"Opponent Slot 1 ({opp_mon.species if opp_mon else 'Empty'})"
        elif target_val == 2:
            opp_mon = battle.opponent_active_pokemon[1]
            target_name = f"Opponent Slot 2 ({opp_mon.species if opp_mon else 'Empty'})"
        elif target_val == 0:
            target_name = "Self / All / None (automatic)"
            
        return f"Move: {move_name}{flag_str} (target: {target_name})"
        
    return str(order)


def build_doubles_llm_prompt(battle: DoubleBattle) -> str:
    # Allies
    active_allies = battle.active_pokemon
    mon1 = active_allies[0] if len(active_allies) > 0 else None
    mon2 = active_allies[1] if len(active_allies) > 1 else None

    # Opponents
    active_opps = battle.opponent_active_pokemon
    opp1 = active_opps[0] if len(active_opps) > 0 else None
    opp2 = active_opps[1] if len(active_opps) > 1 else None

    # Weather, Terrain, Hazards, Screens
    weather_terrain = weather_terrain_str(battle)
    hazards_mine = hazards_str(battle.side_conditions)
    hazards_opp = hazards_str(battle.opponent_side_conditions)
    screens = screens_str(battle)

    # Format each mon block
    def format_mon_block(mon: Optional[Pokemon], slot_label: str) -> str:
        if mon is None:
            return f"[{slot_label}]: None (Fainted or Empty)"
        
        raw = mon.stats or {}
        stats_str = (
            f"HP:{raw.get('hp','?')} Atk:{raw.get('atk','?')} Def:{raw.get('def','?')} "
            f"SpA:{raw.get('spa','?')} SpD:{raw.get('spd','?')} Spe:{raw.get('spe','?')}"
        )
        boosts = boosts_str(mon)
        status = status_str(mon)
        item = mon.item or "Unknown"
        ability = mon.ability or "Unknown"
        
        return f"""
[{slot_label}]:     {mon.species}
[HP_PERCENT]:    {hp_str(mon)}
[ITEM]:          {item}
[ABILITY]:       {ability}
[STATS]:         {stats_str}
[STAT_STAGES]:   {boosts}
[STATUS]:        {status}
""".strip()

    # Ally 1
    mon1_block = format_mon_block(mon1, "MY_ACTIVE_SLOT_1")
    # Ally 2
    mon2_block = format_mon_block(mon2, "MY_ACTIVE_SLOT_2")
    # Opp 1
    opp1_block = format_mon_block(opp1, "OPP_ACTIVE_SLOT_1")
    # Opp 2
    opp2_block = format_mon_block(opp2, "OPP_ACTIVE_SLOT_2")

    # Move blocks
    def format_moves_block(moves: List[Move]) -> str:
        return "\n".join(f"  • {format_move(m)}" for m in moves) if moves else "  (none)"

    my_moves_1 = format_moves_block(battle.available_moves[0]) if len(battle.available_moves) > 0 else "  (none)"
    my_moves_2 = format_moves_block(battle.available_moves[1]) if len(battle.available_moves) > 1 else "  (none)"

    def format_opp_revealed(opp: Optional[Pokemon]) -> str:
        if opp is None or not opp.moves:
            return "  (none revealed yet)"
        return "\n".join(f"  • {m}" for m in opp.moves.keys())

    opp_moves_1 = format_opp_revealed(opp1)
    opp_moves_2 = format_opp_revealed(opp2)

    # Switches
    def format_switches(switches: List[Pokemon]) -> str:
        return "\n".join(
            f"  • {s.species:16s} | HP: {s.current_hp_fraction*100:.0f}%"
            + (f" | Status: {s.status.name}" if s.status else "")
            + (f" | @{s.item}"               if s.item   else "")
            for s in switches
        ) or "  (none)"

    switches_1 = format_switches(battle.available_switches[0]) if len(battle.available_switches) > 0 else "  (none)"
    switches_2 = format_switches(battle.available_switches[1]) if len(battle.available_switches) > 1 else "  (none)"

    # Tera details
    tera1_str = "Available (not yet used)" if (len(battle.can_tera) > 0 and battle.can_tera[0]) else "No / Already Used"
    tera2_str = "Available (not yet used)" if (len(battle.can_tera) > 1 and battle.can_tera[1]) else "No / Already Used"

    return f"""
╔══════════════════════════════════════════════════════════════════╗
║      GRANDMASTER POKÉMON DOUBLES BATTLE STATE — TURN {battle.turn:>3}      ║
╚══════════════════════════════════════════════════════════════════╝

━━━━━━━━━━━━━━━━━━━━━ MY ACTIVE SLOT 1 ━━━━━━━━━━━━━━━━━━━━━
{mon1_block}
[TERA_AVAILABLE]: {tera1_str}

[AVAILABLE MOVES SLOT 1]:
{my_moves_1}

━━━━━━━━━━━━━━━━━━━━━ MY ACTIVE SLOT 2 ━━━━━━━━━━━━━━━━━━━━━
{mon2_block}
[TERA_AVAILABLE]: {tera2_str}

[AVAILABLE MOVES SLOT 2]:
{my_moves_2}

━━━━━━━━━━━━━━━━━━ OPPONENT ACTIVE SLOT 1 ━━━━━━━━━━━━━━━━━━
{opp1_block}

[OPP_REVEALED_MOVES SLOT 1]:
{opp_moves_1}

━━━━━━━━━━━━━━━━━━ OPPONENT ACTIVE SLOT 2 ━━━━━━━━━━━━━━━━━━
{opp2_block}

[OPP_REVEALED_MOVES SLOT 2]:
{opp_moves_2}

━━━━━━━━━━━━━━━━━━━━━━━ TEAMS ━━━━━━━━━━━━━━━━━━━━━━━━
[MY_TEAM]:
{team_summary(battle.team)}

[OPP_TEAM]:
{opp_team_summary(battle.opponent_team)}

━━━━━━━━━━━━━━━━━━━━━ FIELD STATE ━━━━━━━━━━━━━━━━━━━━
[WEATHER_TERRAIN]: {weather_terrain}
[HAZARDS_MINE]:    {hazards_mine}
[HAZARDS_OPP]:     {hazards_opp}
[SCREENS]:         {screens}

━━━━━━━━━━━━━━━━━━ AVAILABLE SWITCHES ━━━━━━━━━━━━━━━━━━
[SLOT 1 SWITCHES]:
{switches_1}

[SLOT 2 SWITCHES]:
{switches_2}

━━━━━━━━━━━━━━━━━━ DOUBLES TARGETS KEY ━━━━━━━━━━━━━━━━━━
When outputting targets for slot-specific actions:
- Ally Slot 1 (first slot): target value is -1
- Ally Slot 2 (second slot): target value is -2
- Opponent Slot 1: target value is 1
- Opponent Slot 2: target value is 2
- Self / All / Field: target value is 0
""".strip()


# ─────────────────────────────────────────────────────────────────────────────
# CLIPBOARD
# ─────────────────────────────────────────────────────────────────────────────

def copy_to_clipboard(text: str) -> bool:
    data = text.encode()
    candidates = [
        (["wl-copy"],                          {}),
        (["xclip", "-selection", "clipboard"], {}),
        (["xsel",  "--clipboard", "--input"],  {}),
        (["pbcopy"],                           {}),
    ]
    for cmd, _ in candidates:
        if shutil.which(cmd[0]):
            try:
                subprocess.run(cmd, input=data, check=True, timeout=3)
                return True
            except Exception:
                pass
    return False


# ─────────────────────────────────────────────────────────────────────────────
# STARTUP WIZARD
# ─────────────────────────────────────────────────────────────────────────────

BUILTIN_TEAM = """
Pidgeot @ Heavy-Duty Boots
Ability: Keen Eye
EVs: 252 Atk / 4 SpD / 252 Spe
Jolly Nature
- Brave Bird
- U-turn
- Roost
- Quick Attack

Alakazam @ Life Orb
Ability: Magic Guard
EVs: 4 HP / 252 SpA / 252 Spe
Timid Nature
- Psychic
- Focus Blast
- Shadow Ball
- Recover

Rhydon @ Eviolite
Ability: Lightning Rod
EVs: 252 HP / 252 Atk / 4 SpD
Adamant Nature
- Earthquake
- Stone Edge
- Megahorn
- Stealth Rock

Gyarados @ Leftovers
Ability: Intimidate
EVs: 252 Atk / 4 SpD / 252 Spe
Jolly Nature
- Dragon Dance
- Waterfall
- Ice Fang
- Earthquake

Exeggutor @ Sitrus Berry
Ability: Harvest
EVs: 252 HP / 252 SpA / 4 SpD
Modest Nature
- Giga Drain
- Psychic
- Sleep Powder
- Leech Seed

Arcanine @ Heavy-Duty Boots
Ability: Intimidate
EVs: 252 Atk / 4 SpD / 252 Spe
Jolly Nature
- Flare Blitz
- Extreme Speed
- Wild Charge
- Morning Sun
"""

FORMATS = [
    "gen9ou", "gen9ubers", "gen9uu", "gen9ru", "gen9nu", "gen9pu",
    "gen9lc", "gen9nationaldex", "gen9randombattle", "gen9doublesou",
    "gen9doublesrandombattle", "gen9vgc2026regg", "gen8ou", "gen8ubers",
]


def ask(prompt: str, default: str = "") -> str:
    """Prompt with an optional default shown in brackets."""
    display = f"{prompt} [{default}]: " if default else f"{prompt}: "
    val = input(display).strip()
    return val if val else default


def section(title: str):
    print(f"\n{C.CYAN}{C.BOLD}== {title} {'=' * max(0, 50 - len(title))}{C.RESET}")


def team_manager_menu(cfg: dict) -> str:
    """Interactive team manager. Returns the selected team string."""
    while True:
        section("TEAM MANAGER")
        saved = cfg.get("saved_teams", {})

        # List saved teams
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
            # Try numeric selection
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
    """Full startup wizard. Returns a resolved config dict + team string."""
    banner()
    cfg = load_config()

    # ── USERNAME ──────────────────────────────────────────────────────────────
    section("ACCOUNT")
    username = ask("Username", cfg.get("username") or "Ironbotter")
    password = ask("Password (leave blank for guest/localhost)", cfg.get("password") or "")
    cfg["username"] = username
    cfg["password"] = password

    # ── SERVER ────────────────────────────────────────────────────────────────
    section("SERVER")
    print(f"  {C.BOLD}[1]{C.RESET} localhost  (local Showdown instance)")
    print(f"  {C.BOLD}[2]{C.RESET} Pokémon Showdown  (online: play.pokemonshowdown.com)")
    srv_choice = ask("Server", "1" if cfg.get("server", "localhost") == "localhost" else "2")
    cfg["server"] = "localhost" if srv_choice != "2" else "showdown"

    # ── FORMAT ────────────────────────────────────────────────────────────────
    section("BATTLE FORMAT")
    for i, fmt in enumerate(FORMATS, 1):
        print(f"  {C.BOLD}[{i:2d}]{C.RESET} {fmt}")
    fmt_default = cfg.get("format", "gen9ou")
    fmt_input = ask(f"Format (number or name)", fmt_default)
    try:
        cfg["format"] = FORMATS[int(fmt_input) - 1]
    except (ValueError, IndexError):
        cfg["format"] = fmt_input or fmt_default
    print(f"  {C.GREEN}✓ Format: {cfg['format']}{C.RESET}")

    # ── TEAM ──────────────────────────────────────────────────────────────────
    section("TEAM SELECTION")
    team_str = team_manager_menu(cfg)

    # ── BATTLE MODE ───────────────────────────────────────────────────────────
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

    # ── NUMBER OF BATTLES ─────────────────────────────────────────────────────
    section("SESSION")
    try:
        num = int(ask("Number of battles", str(cfg.get("num_battles", 1))))
    except ValueError:
        num = 1
    cfg["num_battles"] = max(1, num)

    # ── LLM CONFIGURATION ─────────────────────────────────────────────────────
    section("LOCAL LLM CONFIGURATION")
    print(f"  {C.BOLD}[1]{C.RESET} Ollama (local running instance)")
    print(f"  {C.BOLD}[2]{C.RESET} Gemini API (OpenAI-compatible)")
    print(f"  {C.BOLD}[3]{C.RESET} OpenAI API / Custom OpenAI-compatible endpoint")
    prov_choice = ask("Select LLM Provider", {"ollama": "1", "gemini": "2", "openai": "3"}.get(cfg.get("llm_provider", "ollama"), "1"))
    
    provider_map = {"1": "ollama", "2": "gemini", "3": "openai"}
    cfg["llm_provider"] = provider_map.get(prov_choice, "ollama")
    
    default_models = {
        "ollama": "llama3",
        "gemini": "gemini-2.5-flash",
        "openai": "gpt-4o-mini"
    }
    cfg["llm_model"] = ask("Model Name", cfg.get("llm_model") or default_models[cfg["llm_provider"]])
    
    if cfg["llm_provider"] in ("gemini", "openai"):
        env_key = os.environ.get("GEMINI_API_KEY") if cfg["llm_provider"] == "gemini" else os.environ.get("OPENAI_API_KEY")
        key_prompt = "API Key"
        if env_key:
            key_prompt += " (detected from env, press Enter to keep)"
        cfg["llm_api_key"] = ask(key_prompt, cfg.get("llm_api_key") or "")
        cfg["llm_api_base"] = ask("Custom API Base URL (optional)", cfg.get("llm_api_base") or "")

    # ── SUMMARY ───────────────────────────────────────────────────────────────
    section("SESSION SUMMARY")
    print(f"  Username  : {C.CYAN}{cfg['username']}{C.RESET}")
    print(f"  Server    : {C.CYAN}{cfg['server']}{C.RESET}")
    print(f"  Format    : {C.CYAN}{cfg['format']}{C.RESET}")
    print(f"  Mode      : {C.CYAN}{cfg['mode']}{C.RESET}"
          + (f"  →  {C.YELLOW}{opponent}{C.RESET}" if opponent else ""))
    print(f"  Battles   : {C.CYAN}{cfg['num_battles']}{C.RESET}")
    first_mon = team_str.strip().split("\n")[0]
    print(f"  Team lead : {C.CYAN}{first_mon}{C.RESET}")
    print(f"  LLM Prov  : {C.CYAN}{cfg['llm_provider']}{C.RESET}")
    print(f"  LLM Model : {C.CYAN}{cfg['llm_model']}{C.RESET}")

    confirm = ask(f"\n{C.GREEN}Start? (y/n)", "y")
    if confirm.lower() != "y":
        print("Aborted.")
        sys.exit(0)

    save_config(cfg)
    cfg["_team"]     = team_str
    cfg["_opponent"] = opponent
    return cfg


# ─────────────────────────────────────────────────────────────────────────────
# PLAYER
# ─────────────────────────────────────────────────────────────────────────────

def load_system_prompt() -> str:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    prompt_path = os.path.join(script_dir, "prompt.txt")
    if os.path.exists(prompt_path):
        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            print(f"⚠️ Error reading prompt.txt: {e}")
    else:
        print(f"⚠️ prompt.txt not found at {prompt_path}")
    return "You are a Grandmaster-level Competitive Pokémon Singles Player. Your goal is to maximize win probability."


class PokémonAssistant(Player):
    def __init__(self, *args, llm_config: dict = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.llm_config = llm_config or {}
        self.llm_provider = self.llm_config.get("llm_provider", "ollama")
        self.llm_model = self.llm_config.get("llm_model", "llama3")
        self.llm_api_key = self.llm_config.get("llm_api_key") or os.environ.get("GEMINI_API_KEY") or os.environ.get("OPENAI_API_KEY")
        self.llm_api_base = self.llm_config.get("llm_api_base")
        self.system_prompt = load_system_prompt()

    async def query_llm(self, user_prompt: str) -> str:
        provider = self.llm_provider.lower()
        model = self.llm_model
        
        print(f"\n🔮 Sending state to LLM ({provider} / {model})...")
        
        def _call():
            if provider == "ollama":
                import ollama
                response = ollama.chat(
                    model=model,
                    messages=[
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": user_prompt}
                    ]
                )
                return response['message']['content']
            elif provider in ("gemini", "openai"):
                from openai import OpenAI
                api_key = self.llm_api_key
                base_url = self.llm_api_base
                if not base_url:
                    if provider == "gemini":
                        base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
                    else:
                        base_url = "https://api.openai.com/v1/"
                client = OpenAI(api_key=api_key, base_url=base_url)
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": user_prompt}
                    ]
                )
                return response.choices[0].message.content
            else:
                raise ValueError(f"Unknown LLM provider: {provider}")
                
        return await asyncio.to_thread(_call)

    def parse_action(self, response_text: str, battle) -> DoubleBattleOrder | SingleBattleOrder | None:
        match = re.search(r'\*\*ACTION:\s*(.*?)\*\*', response_text, re.IGNORECASE)
        if not match:
            match = re.search(r'ACTION:\s*([^\n\r]+)', response_text, re.IGNORECASE)
            
        if not match:
            print("⚠️ Could not parse ACTION format from LLM response.")
            return None
            
        action_str = match.group(1).strip().lower()
        print(f"🤖 Parsed Action String: '{action_str}'")
        
        valid_actions = []
        is_doubles = isinstance(battle, DoubleBattle)
        
        if not is_doubles:
            for m in battle.available_moves:
                valid_actions.append(("move", m, False))
                if battle.can_tera:
                    valid_actions.append(("move", m, True))
            for s in battle.available_switches:
                valid_actions.append(("switch", s, False))
        
        digits = re.findall(r'\d+', action_str)
        if digits:
            idx = int(digits[0]) - 1
            if 0 <= idx < len(valid_actions):
                action_type, target, is_tera = valid_actions[idx]
                print(f"✅ Matched by index {idx+1}: {action_type} {target} (Tera: {is_tera})")
                return self.create_order(target, terastallize=is_tera)
                
        is_tera = "tera" in action_str
        
        for s in battle.available_switches:
            species_name = s.species.lower()
            if species_name in action_str:
                print(f"✅ Matched switch by name: {s.species}")
                return self.create_order(s)
                
        for m in battle.available_moves:
            move_id = m.id.lower()
            move_name_clean = m.name.lower().replace(" ", "").replace("-", "")
            action_clean = action_str.replace(" ", "").replace("-", "")
            if move_id in action_clean or move_name_clean in action_clean:
                print(f"✅ Matched move by name: {m.name} (Tera: {is_tera})")
                return self.create_order(m, terastallize=is_tera)
                
        print("⚠️ Could not match action string to any valid move or switch.")
        return None

    # ── TEAM PREVIEW ──────────────────────────────────────────────────────────
    async def teampreview(self, battle) -> str:
        print("\n" + "═" * 70)
        print("🤖  STRATEGY PHASE: TEAM PREVIEW")
        print(f"\nOpponent's revealed team:\n{opp_team_summary(battle.opponent_team)}")
        print("═" * 70)

        team_list = list(battle.team.values())
        opp_team = list(battle.opponent_team.values())
        
        prompt_lines = [
            "╔══════════════════════════════════════════════════════════════════╗",
            "║                  TEAM PREVIEW PHASE                              ║",
            "╚══════════════════════════════════════════════════════════════════╝",
            "",
            "📋 YOUR TEAM:",
        ]
        for i, mon in enumerate(team_list, 1):
            prompt_lines.append(f"  [{i}] {mon.species}")
            
        prompt_lines.extend([
            "",
            "📋 OPPONENT'S TEAM:",
        ])
        for mon in opp_team:
            prompt_lines.append(f"  • {mon.species}")
            
        prompt_lines.extend([
            "",
            "Please select the order of your team. The first Pokémon will be your lead.",
            "Respond in this exact format at the very end of your response:",
            "**ACTION: /team [digits]**",
            f"Example: **ACTION: /team 213456** (meaning slot 2 is lead, then slot 1, 3, 4, 5, 6)",
        ])
        
        user_prompt = "\n".join(prompt_lines)
        
        try:
            response_text = await self.query_llm(user_prompt)
            print(f"\n{C.CYAN}🧠 LLM Team Preview Thought Process:{C.RESET}")
            print(response_text)
            print(f"{C.CYAN}──────────────────────────────────────────────────{C.RESET}")
            
            match = re.search(r'\/team\s*([1-6]+)', response_text)
            if match:
                order_digits = match.group(1).strip()
                if len(order_digits) == len(team_list) and all(d in order_digits for d in map(str, range(1, len(team_list)+1))):
                    print(f"✅ LLM selected team preview order: {order_digits}")
                    return f"/team {order_digits}"
            print("⚠️ Could not parse valid team order. Falling back to default lead (1).")
        except Exception as e:
            print(f"⚠️ Team preview LLM call failed: {e}. Falling back to default lead (1).")
            
        order = list(range(1, len(team_list) + 1))
        return "/team " + "".join(map(str, order))

    # ── MAIN DECISION LOOP ────────────────────────────────────────────────────
    async def choose_move(self, battle) -> DoubleBattleOrder | SingleBattleOrder:
        if not battle.available_moves and not battle.available_switches:
            print("🤖 No actions available! Passing.")
            return self.choose_random_move(battle)

        valid_actions = []
        for i, m in enumerate(battle.available_moves):
            valid_actions.append(f"MOVE: {m.id}")
            if battle.can_tera:
                valid_actions.append(f"TERA_MOVE: {m.id}")
        for s in battle.available_switches:
            valid_actions.append(f"SWITCH: {s.species.lower()}")

        if len(valid_actions) == 1:
            print(f"🤖 Only one valid action available: {valid_actions[0]}. Executing directly.")
            if valid_actions[0].startswith("MOVE:"):
                return self.create_order(battle.available_moves[0])
            elif valid_actions[0].startswith("TERA_MOVE:"):
                return self.create_order(battle.available_moves[0], terastallize=True)
            else:
                return self.create_order(battle.available_switches[0])

        prompt_lines = [
            build_llm_prompt(battle),
            "",
            "━━━━━━━━━━━━━━━━━━━ VALID ACTIONS ━━━━━━━━━━━━━━━━━━━━",
            "You MUST choose exactly one of these actions:",
        ]
        for i, act in enumerate(valid_actions, 1):
            prompt_lines.append(f"  [{i}] {act}")
            
        prompt_lines.extend([
            "",
            "Please respond with your chosen action in this exact format at the very end of your response:",
            "**ACTION: <chosen_action>**",
            "For example: **ACTION: MOVE: bravebird** or **ACTION: SWITCH: alakazam** or **ACTION: TERA_MOVE: psychic** or **ACTION: 3**",
            "If choosing a MOVE or TERA_MOVE, use the move ID (lowercased, no spaces, e.g. bravebird).",
            "If choosing a SWITCH, use the pokemon species (lowercased, e.g. alakazam).",
            "You can also use the index number, e.g. **ACTION: 3**",
        ])
        
        user_prompt = "\n".join(prompt_lines)
        
        try:
            response_text = await self.query_llm(user_prompt)
            print(f"\n{C.CYAN}🧠 LLM Thought Process:{C.RESET}")
            print(response_text)
            print(f"{C.CYAN}──────────────────────────────────────────────────{C.RESET}")
            
            order = self.parse_action(response_text, battle)
            if order:
                return order
            else:
                print("⚠️ Action parsing failed. Falling back to random action.")
        except Exception as e:
            print(f"⚠️ LLM invocation failed: {e}. Falling back to random action.")
            
        return self.choose_random_move(battle)

    async def choose_doubles_move(self, battle: DoubleBattle) -> DoubleBattleOrder:
        prompt = build_doubles_llm_prompt(battle)
        
        valid_orders = battle.valid_orders
        final_orders = [None, None]
        
        prompt_lines = [
            prompt,
            "",
            "━━━━━━━━━━━━━━━━━━━ ACTIONS FOR SLOT 1 ━━━━━━━━━━━━━━━━━━━━",
        ]
        non_pass_orders_1 = [o for o in valid_orders[0] if not isinstance(o, PassBattleOrder)]
        if not non_pass_orders_1:
            prompt_lines.append("  [PASS] No action available (Fainted/Empty)")
        else:
            for idx, order in enumerate(non_pass_orders_1, 1):
                prompt_lines.append(f"  [{idx}] {format_order_for_display(order, battle)}")
                
        prompt_lines.append("\n━━━━━━━━━━━━━━━━━━━ ACTIONS FOR SLOT 2 ━━━━━━━━━━━━━━━━━━━━")
        non_pass_orders_2 = [o for o in valid_orders[1] if not isinstance(o, PassBattleOrder)]
        if not non_pass_orders_2:
            prompt_lines.append("  [PASS] No action available (Fainted/Empty)")
        else:
            for idx, order in enumerate(non_pass_orders_2, 1):
                prompt_lines.append(f"  [{idx}] {format_order_for_display(order, battle)}")
                
        prompt_lines.extend([
            "",
            "Please respond with your chosen actions for both slots at the very end of your response in this exact format:",
            "**SLOT 1 ACTION: <index or description>**",
            "**SLOT 2 ACTION: <index or description>**",
            "Example: If you choose index 2 for Slot 1 and index 1 for Slot 2, output:",
            "**SLOT 1 ACTION: 2**",
            "**SLOT 2 ACTION: 1**",
        ])
        
        user_prompt = "\n".join(prompt_lines)
        
        try:
            response_text = await self.query_llm(user_prompt)
            print(f"\n{C.CYAN}🧠 LLM Doubles Thought Process:{C.RESET}")
            print(response_text)
            print(f"{C.CYAN}──────────────────────────────────────────────────{C.RESET}")
            
            m1 = re.search(r'SLOT 1 ACTION:\s*(.*)', response_text, re.IGNORECASE)
            m2 = re.search(r'SLOT 2 ACTION:\s*(.*)', response_text, re.IGNORECASE)
            
            if m1 and non_pass_orders_1:
                act_str_1 = m1.group(1).strip()
                digits_1 = re.findall(r'\d+', act_str_1)
                if digits_1:
                    idx_1 = int(digits_1[0]) - 1
                    if 0 <= idx_1 < len(non_pass_orders_1):
                        final_orders[0] = non_pass_orders_1[idx_1]
            if m2 and non_pass_orders_2:
                act_str_2 = m2.group(1).strip()
                digits_2 = re.findall(r'\d+', act_str_2)
                if digits_2:
                    idx_2 = int(digits_2[0]) - 1
                    if 0 <= idx_2 < len(non_pass_orders_2):
                        final_orders[1] = non_pass_orders_2[idx_2]
        except Exception as e:
            print(f"⚠️ Doubles LLM call failed: {e}")
            
        if not final_orders[0]:
            final_orders[0] = non_pass_orders_1[0] if non_pass_orders_1 else PassBattleOrder()
        if not final_orders[1]:
            final_orders[1] = non_pass_orders_2[0] if non_pass_orders_2 else PassBattleOrder()
            
        return DoubleBattleOrder(first_order=final_orders[0], second_order=final_orders[1])

    async def choose_move_order(self, battle) -> DoubleBattleOrder | SingleBattleOrder:
        return await self.choose_move(battle)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

async def main():
    cfg = startup_wizard()

    team_str  = cfg["_team"]
    opponent  = cfg["_opponent"]
    username  = cfg["username"]
    password  = cfg["password"] or None
    fmt       = cfg["format"]
    num       = cfg["num_battles"]
    mode      = cfg["mode"]
    server    = cfg["server"]

    server_cfg = (
        LocalhostServerConfiguration if server == "localhost"
        else ShowdownServerConfiguration
    )

    teambuilder = ConstantTeambuilder(team_str)

    bot = PokémonAssistant(
        account_configuration=AccountConfiguration(username, password),
        battle_format=fmt,
        team=teambuilder,
        server_configuration=server_cfg,
        llm_config=cfg,
    )

    print(f"\n{C.GREEN}{C.BOLD}🤖  Bot '{username}' is online.{C.RESET}")
    print(f"📦  Team loaded.")
    print(f"🎮  Format: {fmt}")

    if mode == "accept":
        print("⏳  Waiting for an incoming challenge…\n")
        await bot.accept_challenges(None, num)

    elif mode == "challenge":
        print(f"⚔️   Challenging {C.YELLOW}{opponent}{C.RESET}…\n")
        await bot.send_challenges(opponent, num)

    elif mode == "ladder":
        print("🔍  Seeking a ladder match…\n")
        await bot.ladder(num)


if __name__ == "__main__":
    asyncio.run(main())