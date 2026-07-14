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
  ██████╗  ██████╗ ██╗  ██╗███████╗
  ██╔══██╗██╔═══██╗██║ ██╔╝██╔════╝
  ██████╔╝██║   ██║█████╔╝ █████╗
  ██╔═══╝ ██║   ██║██╔═██╗ ██╔══╝
  ██║     ╚██████╔╝██║  ██╗███████╗
  ╚═╝      ╚═════╝ ╚═╝  ╚═╝╚══════╝
  {C.RESET}{C.YELLOW}Showdown Battle Assistant  v2.0{C.RESET}
  {C.DIM}──────────────────────────────────{C.RESET}
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


def ask(prompt: str, default: str = "") -> str:
    """Prompt with an optional default shown in brackets."""
    display = f"{prompt} [{default}]: " if default else f"{prompt}: "
    val = input(display).strip()
    return val if val else default


def section(title: str):
    print(f"\n{C.CYAN}{C.BOLD}── {title} {'─' * max(0, 50 - len(title))}{C.RESET}")


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

class PokémonAssistant(Player):

    # ── TEAM PREVIEW ──────────────────────────────────────────────────────────
    async def teampreview(self, battle) -> str:
        print("\n" + "═" * 70)
        print("🔍  STRATEGY PHASE: TEAM PREVIEW")
        print(f"\nOpponent's revealed team:\n{opp_team_summary(battle.opponent_team)}")
        print("═" * 70)

        team_list = list(battle.team.values())
        print("\n📋  YOUR TEAM:")
        for i, mon in enumerate(team_list, 1):
            print(f"  [{i}] {mon.species}")

        is_doubles = isinstance(battle, DoubleBattle)
        if is_doubles:
            print("\n[DECISION] Choose Lead 1 and Lead 2 (Enter number 1–6)")
            lead_idx_1 = -1
            lead_idx_2 = -1
            while True:
                try:
                    choice1 = await asyncio.to_thread(input, "Lead 1 > ")
                    idx1 = int(choice1.strip()) - 1
                    if 0 <= idx1 < len(team_list):
                        lead_idx_1 = idx1
                        break
                    print(f"❌  Pick a number between 1 and {len(team_list)}")
                except (ValueError, EOFError):
                    print("❌  Invalid input. Please enter a number.")
            while True:
                try:
                    choice2 = await asyncio.to_thread(input, "Lead 2 > ")
                    idx2 = int(choice2.strip()) - 1
                    if 0 <= idx2 < len(team_list) and idx2 != lead_idx_1:
                        lead_idx_2 = idx2
                        break
                    if idx2 == lead_idx_1:
                        print("❌  Lead 2 cannot be the same as Lead 1.")
                    else:
                        print(f"❌  Pick a number between 1 and {len(team_list)}")
                except (ValueError, EOFError):
                    print("❌  Invalid input. Please enter a number.")
            
            order = list(range(1, len(team_list) + 1))
            val1 = lead_idx_1 + 1
            val2 = lead_idx_2 + 1
            order.remove(val1)
            order.remove(val2)
            order.insert(0, val2)
            order.insert(0, val1)
            return "/team " + "".join(map(str, order))
        else:
            print("\n[DECISION] Who should LEAD? (Enter number 1–6)")
            while True:
                try:
                    choice = await asyncio.to_thread(input, "Lead > ")
                    idx = int(choice.strip()) - 1
                    if 0 <= idx < len(team_list):
                        order = list(range(1, len(team_list) + 1))
                        order.insert(0, order.pop(idx))
                        return "/team " + "".join(map(str, order))
                    print(f"❌  Pick a number between 1 and {len(team_list)}")
                except (ValueError, EOFError):
                    print("❌  Invalid input. Please enter a number.")

    # ── MAIN DECISION LOOP ────────────────────────────────────────────────────
    async def choose_move(self, battle) -> DoubleBattleOrder | SingleBattleOrder | DefaultBattleOrder:
        if isinstance(battle, DoubleBattle):
            return await self.choose_doubles_move(battle)

        me  = battle.active_pokemon
        opp = battle.opponent_active_pokemon

        if not me or not opp:
            return self.choose_random_move(battle)

        prompt       = build_llm_prompt(battle)
        clipboard_ok = copy_to_clipboard(prompt)

        print("\n" + "═" * 70)
        print(prompt)
        print("═" * 70)

        if clipboard_ok:
            print("\n✅  Prompt copied to clipboard — paste into your AI chat (Ctrl+V).")
        else:
            print("\n⚠️   Clipboard unavailable. Copy the prompt above manually.")

        print("\n📋  QUICK REFERENCE")
        print("  Attacks:")
        for i, m in enumerate(battle.available_moves, 1):
            tera_note = "  ← can TERA" if battle.can_tera else ""
            print(f"    move {i}  →  {m.id.upper()}{tera_note}")
        print("  Switches:")
        for i, s in enumerate(battle.available_switches, 1):
            print(f"    switch {i}  →  {s.species} ({s.current_hp_fraction*100:.0f}%)")
        if battle.can_tera:
            print("\n  ✨  TERASTALIZATION AVAILABLE  →  prefix with 'tera'")
            print("      e.g.  'tera move 1'  or  'tera 1'")

        print("\nCommands:  move <n>  |  switch <n>  |  tera [move] <n>  |  c (re-copy prompt)")

        while True:
            try:
                raw = await asyncio.to_thread(input, "\n[DECISION] > ")
            except (EOFError, KeyboardInterrupt):
                print("\nInterrupted — picking random move.")
                return self.choose_random_move(battle)

            tokens = raw.strip().lower().split()
            if not tokens:
                continue

            if tokens[0] == "c":
                if copy_to_clipboard(prompt):
                    print("✅  Prompt copied to clipboard!")
                else:
                    print("⚠️   Clipboard unavailable.")
                continue

            try:
                if tokens[0] == "tera":
                    if not battle.can_tera:
                        print("❌  Terastalization already used or unavailable.")
                        continue
                    idx = int(tokens[-1]) - 1
                    return self.create_order(battle.available_moves[idx], terastallize=True)

                elif tokens[0] == "move" and len(tokens) > 1:
                    idx = int(tokens[1]) - 1
                    return self.create_order(battle.available_moves[idx])

                elif tokens[0] == "switch" and len(tokens) > 1:
                    idx = int(tokens[1]) - 1
                    return self.create_order(battle.available_switches[idx])

                else:
                    print("❌  Unknown command. Use:  move <n>  |  switch <n>  |  tera [move] <n>  |  c")

            except (ValueError, IndexError):
                print(
                    f"❌  Invalid index. "
                    f"Moves: 1–{len(battle.available_moves)}  |  "
                    f"Switches: 1–{len(battle.available_switches)}"
                )

    async def choose_doubles_move(self, battle: DoubleBattle) -> DoubleBattleOrder:
        prompt = build_doubles_llm_prompt(battle)
        clipboard_ok = copy_to_clipboard(prompt)

        print("\n" + "═" * 70)
        print(prompt)
        print("═" * 70)

        if clipboard_ok:
            print("\n✅  Prompt copied to clipboard — paste into your AI chat (Ctrl+V).")
        else:
            print("\n⚠️   Clipboard unavailable. Copy the prompt above manually.")

        valid_orders = battle.valid_orders
        final_orders = [None, None]

        for slot in range(2):
            active_mon = battle.active_pokemon[slot]
            slot_orders = valid_orders[slot]

            non_pass_orders = [o for o in slot_orders if not isinstance(o, PassBattleOrder)]

            if not non_pass_orders:
                final_orders[slot] = PassBattleOrder()
                print(f"\nSlot {slot + 1} ({active_mon.species if active_mon else 'Empty'}): PASS (No action available)")
                continue

            print(f"\n📋  AVAILABLE ACTIONS FOR SLOT {slot + 1} ({active_mon.species if active_mon else 'Empty'}):")
            for idx, order in enumerate(non_pass_orders, 1):
                desc = format_order_for_display(order, battle)
                print(f"    [{idx}]  →  {desc}")

            print(f"Commands for Slot {slot + 1}: Enter choice number (1-{len(non_pass_orders)}) | 'c' to copy prompt")

            while True:
                try:
                    raw = await asyncio.to_thread(input, f"[SLOT {slot + 1} DECISION] > ")
                except (EOFError, KeyboardInterrupt):
                    print("\nInterrupted — picking random move.")
                    return self.choose_random_move(battle)

                choice = raw.strip().lower()
                if not choice:
                    continue

                if choice == "c":
                    if copy_to_clipboard(prompt):
                        print("✅  Prompt copied to clipboard!")
                    else:
                        print("⚠️   Clipboard unavailable.")
                    continue

                try:
                    idx = int(choice) - 1
                    if 0 <= idx < len(non_pass_orders):
                        final_orders[slot] = non_pass_orders[idx]
                        break
                    print(f"❌  Pick a number between 1 and {len(non_pass_orders)}")
                except ValueError:
                    print(f"❌  Invalid input. Enter a choice number.")

        return DoubleBattleOrder(first_order=final_orders[0] or PassBattleOrder(), second_order=final_orders[1] or PassBattleOrder())

    async def choose_move_order(self, battle) -> DoubleBattleOrder | SingleBattleOrder | DefaultBattleOrder:
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