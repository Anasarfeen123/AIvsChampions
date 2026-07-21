import os
import json
import httpx
from typing import Any, Optional
from pydantic import BaseModel, Field

try:
    from google import genai
    from google.genai import types
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

class SingleBattleDecision(BaseModel):
    reasoning_summary: str = Field(description="A concise, 1-2 sentence explanation of the move decision in English to post to the battle chat. E.g. 'Switching to Great Tusk to threaten the opponent's active Pokemon.'")
    rival_dialogue: str = Field(description="Write one short rival line as Blue in first person, using placeholders when they fit. Keep it cocky, natural, and punchy. Return only the final line.")
    action_index: int = Field(description="The index of the chosen action from the AVAILABLE ACTIONS list.")

class DoublesBattleDecision(BaseModel):
    reasoning_summary: str = Field(description="A concise, 1-2 sentence explanation of the moves chosen for both slots to post in the battle chat.")
    rival_dialogue: str = Field(description="Write one short rival line as Blue in first person, using placeholders when they fit. Keep it cocky, natural, and punchy. Return only the final line.")
    slot1_action_index: int = Field(description="The index of the chosen action for Slot 1 from the slot 1 available actions list.")
    slot2_action_index: int = Field(description="The index of the chosen action for Slot 2 from the slot 2 available actions list.")

class GeminiClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if self.api_key:
            os.environ["GEMINI_API_KEY"] = self.api_key
        self.genai_client = None
        self._init_client()

    def _init_client(self):
        if GEMINI_AVAILABLE and self.api_key:
            try:
                self.genai_client = genai.Client()
            except Exception as e:
                print(f"⚠️  Could not initialize Gemini Client: {e}")

    def is_configured(self) -> bool:
        return self.genai_client is not None

    async def get_decision(self, prompt: str, schema: Any) -> Optional[dict]:
        if not self.genai_client:
            self._init_client()
            if not self.genai_client:
                return None
        
        system_instruction = "You are a Grandmaster-level Competitive Pokémon Player."
        try:
            with open("prompt.txt") as f:
                system_instruction = f.read()
        except Exception:
            pass

        try:
            print("\n🤖  Querying Gemini API for decision...")
            response = self.genai_client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=schema,
                    temperature=0.1,
                ),
            )
            data = json.loads(response.text)
            return data
        except Exception as e:
            print(f"\n❌  Gemini API Request failed: {e}")
            return None


class OllamaClient:
    def __init__(self, model_name: str = "qwen2.5:7b", base_url: str = "http://localhost:11434"):
        self.model_name = model_name
        self.base_url = base_url

    def is_configured(self) -> bool:
        # Check if Ollama is running
        return True

    async def get_decision(self, prompt: str, schema: Any) -> Optional[dict]:
        system_instruction = "You are a Grandmaster-level Competitive Pokémon Player."
        try:
            with open("prompt.txt") as f:
                system_instruction = f.read()
        except Exception:
            pass

        # Inform Ollama of the required JSON fields in the prompt
        schema_info = ""
        if schema == SingleBattleDecision:
            schema_info = (
                "\n\nYou MUST return a JSON object with exactly these fields:\n"
                "{\n"
                '  "reasoning_summary": "A concise explanation of the move in English.",\n'
                '  "rival_dialogue": "One short rival line as Blue in first person using placeholders when they fit.",\n'
                '  "action_index": <integer index of the chosen action>\n'
                "}"
            )
        elif schema == DoublesBattleDecision:
            schema_info = (
                "\n\nYou MUST return a JSON object with exactly these fields:\n"
                "{\n"
                '  "reasoning_summary": "A concise explanation of the moves in English.",\n'
                '  "rival_dialogue": "One short rival line as Blue in first person using placeholders when they fit.",\n'
                '  "slot1_action_index": <integer index of slot 1 action>,\n'
                '  "slot2_action_index": <integer index of slot 2 action>\n'
                "}"
            )

        full_prompt = prompt + schema_info
        messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": full_prompt}
        ]

        try:
            print(f"\n🤖  Querying Ollama ({self.model_name}) for decision...")
            
            # Try structured JSON schema first, fallback to format="json" if Ollama version does not support it
            format_param = "json"
            try:
                format_param = schema.model_json_schema()
            except Exception:
                pass

            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "model": self.model_name,
                        "messages": messages,
                        "stream": False,
                        "format": format_param,
                        "options": {
                            "temperature": 0.1
                        }
                    }
                )
                
                # If structured schema failed, try fallback with format="json"
                if response.status_code != 200 and format_param != "json":
                    response = await client.post(
                        f"{self.base_url}/api/chat",
                        json={
                            "model": self.model_name,
                            "messages": messages,
                            "stream": False,
                            "format": "json",
                            "options": {
                                "temperature": 0.1
                            }
                        }
                    )

                if response.status_code == 200:
                    data = response.json()
                    content = data["message"]["content"]
                    decision = json.loads(content)
                    return decision
                else:
                    print(f"\n❌  Ollama API Request failed with status code {response.status_code}: {response.text}")
                    return None
        except Exception as e:
            print(f"\n❌  Ollama API Request failed: {e}")
            return None


class PuterClient:
    def __init__(self, model_name: str = "claude-3-5-sonnet"):
        self.model_name = model_name
        self.api_url = "https://api.puter.com/v2/ai/chat"

    def is_configured(self) -> bool:
        return True

    async def get_decision(self, prompt: str, schema: Any) -> Optional[dict]:
        import re
        system_instruction = "You are a Grandmaster-level Competitive Pokémon Player."
        try:
            with open("prompt.txt") as f:
                system_instruction = f.read()
        except Exception:
            pass

        schema_info = ""
        if schema == SingleBattleDecision:
            schema_info = (
                "\n\nYou MUST return a JSON object with exactly these fields:\n"
                "{\n"
                '  "reasoning_summary": "A concise explanation of the move in English.",\n'
                '  "rival_dialogue": "One short rival line as Blue in first person using placeholders when they fit.",\n'
                '  "action_index": <integer index of the chosen action>\n'
                "}"
            )
        elif schema == DoublesBattleDecision:
            schema_info = (
                "\n\nYou MUST return a JSON object with exactly these fields:\n"
                "{\n"
                '  "reasoning_summary": "A concise explanation of the moves in English.",\n'
                '  "rival_dialogue": "One short rival line as Blue in first person using placeholders when they fit.",\n'
                '  "slot1_action_index": <integer index of slot 1 action>,\n'
                '  "slot2_action_index": <integer index of slot 2 action>\n'
                "}"
            )

        full_prompt = prompt + schema_info
        messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": full_prompt}
        ]

        print(f"\n🤖  Querying Puter.js ({self.model_name}) for decision...")

        try:
            async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
                payload = {
                    "interface": "puter-chat-completion",
                    "driver": "openai",
                    "model": self.model_name,
                    "test_mode": False,
                    "messages": messages,
                    "temperature": 0.1
                }
                response = await client.post(self.api_url, json=payload)
                if response.status_code == 200:
                    data = response.json()
                    content = ""
                    if isinstance(data, dict):
                        if "message" in data and isinstance(data["message"], dict) and "content" in data["message"]:
                            content = data["message"]["content"]
                        elif "text" in data:
                            content = data["text"]
                        elif "result" in data:
                            content = data["result"]
                        elif "choices" in data and isinstance(data["choices"], list) and len(data["choices"]) > 0:
                            content = data["choices"][0].get("message", {}).get("content", "")
                        else:
                            content = json.dumps(data)
                    else:
                        content = str(data)

                    json_match = re.search(r"\{.*\}", content, re.DOTALL)
                    if json_match:
                        content = json_match.group(0)

                    decision = json.loads(content)
                    return decision
                else:
                    print(f"\n⚠️  Puter.js API returned status code {response.status_code}: {response.text[:150]}")
        except Exception as e:
            print(f"\n❌  Puter.js API Request failed: {e}")

        return None

