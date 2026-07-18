import asyncio
import os
import shutil
import subprocess
import argparse
from typing import Optional, Any

from poke_env.player import Player
from poke_env.player.battle_order import DoubleBattleOrder, SingleBattleOrder, PassBattleOrder, DefaultBattleOrder
from poke_env.battle.battle import Battle
from poke_env.battle.double_battle import DoubleBattle
from poke_env.ps_client.account_configuration import AccountConfiguration
from poke_env.teambuilder.constant_teambuilder import ConstantTeambuilder

from poke_env import ShowdownServerConfiguration, LocalhostServerConfiguration
from config_manager import C, startup_wizard
from prompt_builder import (
    build_llm_prompt,
    build_doubles_llm_prompt,
    opp_team_summary,
    format_order_for_display,
)
from llm_client import GeminiClient, OllamaClient, SingleBattleDecision, DoublesBattleDecision

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

class PokémonAssistant(Player):
    def __init__(
        self,
        *args,
        gemini_api_key: Optional[str] = None,
        llm_provider: str = "gemini",
        ollama_model: str = "qwen2.5:7b",
        auto_play: bool = True,
        **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.llm_provider = llm_provider
        self.auto_play = auto_play
        if llm_provider == "ollama":
            self.llm_client = OllamaClient(model_name=ollama_model)
        else:
            self.llm_client = GeminiClient(api_key=gemini_api_key)

    def _non_tera_orders(self, orders):
        return [order for order in orders if not getattr(order, "terastallize", False)]

    def _auto_single_order(self, battle):
        if battle.available_moves:
            move = battle.available_moves[0]
            print(f"\n🤖  Auto fallback: move {move.id}")
            return self.create_order(move)
        if battle.available_switches:
            switch = battle.available_switches[0]
            print(f"\n🤖  Auto fallback: switch to {switch.species}")
            return self.create_order(switch)
        return self.choose_random_move(battle)

    # ── TEAM PREVIEW ──────────────────────────────────────────────────────────
    async def teampreview(self, battle) -> str:
        await self.ps_client.send_message(f"/join {battle.battle_tag}")
        print("\n" + "═" * 70)
        print("🔍  STRATEGY PHASE: TEAM PREVIEW")
        print(f"\nOpponent's revealed team:\n{opp_team_summary(battle.opponent_team)}")
        print("═" * 70)

        team_list = list(battle.team.values())
        print("\n📋  YOUR TEAM:")
        for i, mon in enumerate(team_list, 1):
            print(f"  [{i}] {mon.species}")

        is_doubles = isinstance(battle, DoubleBattle)
        if self.auto_play:
            if is_doubles:
                lead_count = min(2, len(team_list))
                leads = " and ".join(mon.species for mon in team_list[:lead_count])
                print(f"\n🤖  Auto lead: {leads}")
                return "/team " + "".join(str(i) for i in range(1, len(team_list) + 1))
            print(f"\n🤖  Auto lead: {team_list[0].species}")
            return "/team " + "".join(str(i) for i in range(1, len(team_list) + 1))

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

        await self.ps_client.send_message(f"/join {battle.battle_tag}")
        me  = battle.active_pokemon
        opp = battle.opponent_active_pokemon

        if not me or not opp:
            return self.choose_random_move(battle)

        if self.auto_play and not self.llm_client.is_configured():
            return self._auto_single_order(battle)

        prompt       = build_llm_prompt(battle)
        clipboard_ok = copy_to_clipboard(prompt)

        print("\n" + "═" * 70)
        print(prompt)
        print("═" * 70)

        if clipboard_ok:
            print("\n✅  Prompt copied to clipboard — paste into your AI chat (Ctrl+V).")
        else:
            print("\n⚠️   Clipboard unavailable. Copy the prompt above manually.")

        # Construct AVAILABLE ACTIONS list
        actions = []
        for idx, move in enumerate(battle.available_moves):
            actions.append({
                "type": "move",
                "index": idx,
                "description": f"Move: {move.id.upper()}"
            })
        for idx, switch in enumerate(battle.available_switches):
            actions.append({
                "type": "switch",
                "index": idx,
                "description": f"Switch to {switch.species} ({switch.current_hp_fraction*100:.0f}% HP)"
            })

        print("\n📋  AVAILABLE ACTIONS:")
        for i, a in enumerate(actions, 1):
            print(f"    [{i}]  →  {a['description']}")

        # Query Gemini if configured
        if self.llm_client.is_configured():
            actions_str = "AVAILABLE ACTIONS:\n" + "\n".join(
                f"  [{i+1}] {a['description']}" for i, a in enumerate(actions)
            )
            full_prompt = f"{prompt}\n\n{actions_str}\n\nYou MUST select one action index from the AVAILABLE ACTIONS list. Respond with the schema."
            
            decision = await self.llm_client.get_decision(full_prompt, SingleBattleDecision)
            if decision:
                reason = decision.get("reasoning_summary")
                action_idx = decision.get("action_index", 1) - 1
                
                if 0 <= action_idx < len(actions):
                    chosen_action = actions[action_idx]
                    provider_title = "Ollama" if self.llm_provider == "ollama" else "Gemini"
                    print(f"\n🤖  {C.GREEN}{C.BOLD}{provider_title} Decision:{C.RESET} {chosen_action['description']}")
                    print(f"💬  {C.YELLOW}Reasoning:{C.RESET} {reason}")
                    
                    dialogue = decision.get("rival_dialogue")
                    if dialogue:
                        dialogue_clean = dialogue.replace("\n", " ").strip()
                        print(f"🗣️  {C.CYAN}{C.BOLD}Rival Dialogue:{C.RESET} {dialogue_clean}")
                        await self.ps_client.send_message(dialogue_clean, room=battle.battle_tag)
                    
                    if chosen_action["type"] == "move":
                        return self.create_order(battle.available_moves[chosen_action["index"]])
                    elif chosen_action["type"] == "switch":
                        return self.create_order(battle.available_switches[chosen_action["index"]])
                else:
                    print(f"\n❌  Gemini selected invalid action index: {action_idx + 1}")

        # Fallback to manual selection
        if self.auto_play:
            return self._auto_single_order(battle)

        print("\nCommands:  move <n>  |  switch <n>  |  c (re-copy prompt)")

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
                    print("❌  Terastalization is disabled: format is National Dex OU (No Tera).")
                    continue

                if tokens[0] == "move" and len(tokens) > 1:
                    idx = int(tokens[1]) - 1
                    return self.create_order(battle.available_moves[idx])

                elif tokens[0] == "switch" and len(tokens) > 1:
                    idx = int(tokens[1]) - 1
                    return self.create_order(battle.available_switches[idx])

                else:
                    print("❌  Unknown command. Use:  move <n>  |  switch <n>  |  c")

            except (ValueError, IndexError):
                print(
                    f"❌  Invalid index. "
                    f"Moves: 1–{len(battle.available_moves)}  |  "
                    f"Switches: 1–{len(battle.available_switches)}"
                )

    async def choose_doubles_move(self, battle: DoubleBattle) -> DoubleBattleOrder:
        await self.ps_client.send_message(f"/join {battle.battle_tag}")
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
        slot_actions = [[], []]

        for slot in range(2):
            active_mon = battle.active_pokemon[slot]
            slot_orders = valid_orders[slot]
            non_pass_orders = self._non_tera_orders(
                o for o in slot_orders if not isinstance(o, PassBattleOrder)
            )
            
            for idx, order in enumerate(non_pass_orders):
                desc = format_order_for_display(order, battle)
                slot_actions[slot].append({
                    "index": idx,
                    "description": desc,
                    "order": order
                })

        # Query Gemini if configured
        if self.llm_client.is_configured():
            actions_str = ""
            for slot in range(2):
                active_mon = battle.active_pokemon[slot]
                mon_name = active_mon.species if active_mon else f"Slot {slot+1}"
                actions_str += f"\nAVAILABLE ACTIONS FOR {mon_name} (Slot {slot+1}):\n"
                if not slot_actions[slot]:
                    actions_str += "  [1] PASS (No action available)\n"
                else:
                    for i, a in enumerate(slot_actions[slot]):
                        actions_str += f"  [{i+1}] {a['description']}\n"
            
            full_prompt = f"{prompt}\n\n{actions_str}\n\nYou MUST select one action index for Slot 1 and one action index for Slot 2 from the lists above. Respond with the schema."
            
            decision = await self.llm_client.get_decision(full_prompt, DoublesBattleDecision)
            if decision:
                reason = decision.get("reasoning_summary")
                provider_title = "Ollama" if self.llm_provider == "ollama" else "Gemini"
                print(f"\n🤖  {C.GREEN}{C.BOLD}{provider_title} Doubles Decision:{C.RESET}")
                print(f"💬  {C.YELLOW}Reasoning:{C.RESET} {reason}")
                
                dialogue = decision.get("rival_dialogue")
                if dialogue:
                    dialogue_clean = dialogue.replace("\n", " ").strip()
                    print(f"🗣️  {C.CYAN}{C.BOLD}Rival Dialogue:{C.RESET} {dialogue_clean}")
                    await self.ps_client.send_message(dialogue_clean, room=battle.battle_tag)
                
                for slot in range(2):
                    active_mon = battle.active_pokemon[slot]
                    if not slot_actions[slot]:
                        final_orders[slot] = PassBattleOrder()
                        continue
                    
                    key = f"slot{slot+1}_action_index"
                    action_idx = decision.get(key, 1) - 1
                    
                    if 0 <= action_idx < len(slot_actions[slot]):
                        chosen = slot_actions[slot][action_idx]
                        print(f"  Slot {slot+1} action: {chosen['description']}")
                        final_orders[slot] = chosen["order"]
                    else:
                        print(f"  Slot {slot+1} action index invalid ({action_idx+1}), using first option.")
                        final_orders[slot] = slot_actions[slot][0]["order"]
                
                return DoubleBattleOrder(first_order=final_orders[0] or PassBattleOrder(), second_order=final_orders[1] or PassBattleOrder())

        # Fallback to manual selection
        if self.auto_play:
            for slot in range(2):
                if slot_actions[slot]:
                    final_orders[slot] = slot_actions[slot][0]["order"]
                    print(f"\n🤖  Auto fallback slot {slot + 1}: {slot_actions[slot][0]['description']}")
                else:
                    final_orders[slot] = PassBattleOrder()
            return DoubleBattleOrder(first_order=final_orders[0] or PassBattleOrder(), second_order=final_orders[1] or PassBattleOrder())

        for slot in range(2):
            active_mon = battle.active_pokemon[slot]
            non_pass_orders = [a["order"] for a in slot_actions[slot]]

            if not non_pass_orders:
                final_orders[slot] = PassBattleOrder()
                print(f"\nSlot {slot + 1} ({active_mon.species if active_mon else 'Empty'}): PASS (No action available)")
                continue

            print(f"\n📋  AVAILABLE ACTIONS FOR SLOT {slot + 1} ({active_mon.species if active_mon else 'Empty'}):")
            for idx, action in enumerate(slot_actions[slot], 1):
                print(f"    [{idx}]  →  {action['description']}")

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


async def main():
    parser = argparse.ArgumentParser(description="Pokémon Showdown AI Assistant")
    parser.add_argument("--wizard", "-w", action="store_true", help="Run the interactive setup wizard")
    parser.add_argument("--provider", "-p", choices=["gemini", "ollama"], default="ollama", help="LLM Provider (default: ollama)")
    parser.add_argument("--model", "-m", default="qwen2.5:7b", help="Ollama model name (default: qwen2.5:7b)")
    parser.add_argument("--server", "-s", choices=["localhost", "showdown"], default="localhost", help="Server to connect to (default: localhost)")
    parser.add_argument("--battles", "-b", type=int, default=1, help="Number of battles to play (default: 1)")
    parser.add_argument("--opponent", "-o", default="AI", help="Opponent username to challenge (default: AI)")
    
    args = parser.parse_args()

    if args.wizard:
        cfg = startup_wizard()
        team_str  = cfg["_team"]
        opponent  = cfg["_opponent"]
        username  = cfg["username"]
        password  = cfg["password"] or None
        fmt       = cfg["format"]
        num       = cfg["num_battles"]
        mode      = cfg["mode"]
        server    = cfg["server"]
        llm_provider = cfg.get("llm_provider", "gemini")
        ollama_model = cfg.get("ollama_model", "qwen2.5:7b")
        gemini_api_key = cfg.get("gemini_api_key")
    else:
        # Load from config files or default
        from config_manager import RED_MT_SILVER_TEAM, BLUE_TEAM
        team_str = RED_MT_SILVER_TEAM
        opponent = args.opponent
        username = "User"
        password = None
        fmt = "gen9nationaldexounotera"
        num = args.battles
        mode = "challenge"
        server = args.server
        llm_provider = args.provider
        ollama_model = args.model
        gemini_api_key = os.environ.get("GEMINI_API_KEY")

    server_cfg = (
        LocalhostServerConfiguration if server == "localhost"
        else ShowdownServerConfiguration
    )

    teambuilder = ConstantTeambuilder(team_str)

    bot = PokémonAssistant(
        account_configuration=AccountConfiguration(username, password),
        gemini_api_key=gemini_api_key,
        llm_provider=llm_provider,
        ollama_model=ollama_model,
        auto_play=True,
        battle_format=fmt,
        team=teambuilder,
        server_configuration=server_cfg,
    )

    print(f"\n{C.GREEN}{C.BOLD}🤖  Bot '{username}' is online.{C.RESET}")
    print(f"📦  Team loaded.")
    print(f"🎮  Format: {fmt}")
    
    if llm_provider == "ollama":
        print(f"🧠  LLM Model: Ollama ({ollama_model})")
    else:
        print(f"🧠  LLM Model: Gemini API")

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
