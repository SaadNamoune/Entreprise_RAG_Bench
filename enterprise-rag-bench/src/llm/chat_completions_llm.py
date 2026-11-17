"""OpenAI-compatible Chat Completions backend (Ollama, Mistral, LiteLLM gateways, ...).

Added for the PFE evaluation: the upstream OpenAI backend uses the Responses API, which these
servers do not offer. Configure with:
    LLM_PROVIDER=chat
    CHAT_BASE_URL=http://localhost:11434/v1     (Ollama)
    LLM_API_KEY=ollama                          (any non-empty value for Ollama)
    LLM_MODEL_NAME=..., CHEAP_LLM_MODEL_NAME=...
"""

import json
import os
import uuid
from collections.abc import Generator
from typing import Any

from openai import OpenAI

from src.llm.interface import LLMInterface, Message, ReasoningLevel, ToolCall


LLM_API_KEY = os.environ.get("LLM_API_KEY", "ollama")
CHAT_BASE_URL = os.environ.get("CHAT_BASE_URL", "http://localhost:11434/v1")
LLM_MODEL_NAME = os.environ.get("LLM_MODEL_NAME")
CHEAP_LLM_MODEL_NAME = os.environ.get("CHEAP_LLM_MODEL_NAME") or LLM_MODEL_NAME
CHAT_TIMEOUT = float(os.environ.get("CHAT_TIMEOUT", "900"))


class ChatCompletionsLLM(LLMInterface):
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        tools: list[dict] | None = None,
        quiet: bool = False,
        reasoning_level: ReasoningLevel = "medium",
    ):
        self.model = model or LLM_MODEL_NAME
        if not self.model:
            raise ValueError("Set LLM_MODEL_NAME for the chat provider.")
        self.tools = [self._convert_tool(t) for t in tools] if tools else None
        self.quiet = quiet
        self.client = OpenAI(api_key=api_key or LLM_API_KEY, base_url=CHAT_BASE_URL, timeout=CHAT_TIMEOUT)

    @staticmethod
    def _convert_tool(tool: dict) -> dict:
        """Responses-format tool ({type, name, parameters}) -> Chat Completions format."""
        if "function" in tool:
            return tool
        return {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("parameters", {"type": "object", "properties": {}}),
            },
        }

    @staticmethod
    def _build_messages(messages: list[Message]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for msg in messages:
            if msg.role in ("system", "user"):
                out.append({"role": msg.role, "content": msg.content})
            elif msg.role == "assistant":
                out.append({"role": "assistant", "content": msg.content})
            elif msg.role == "tool_call" and msg.tool_call:
                call = {
                    "id": msg.tool_call.call_id,
                    "type": "function",
                    "function": {"name": msg.tool_call.name, "arguments": json.dumps(msg.tool_call.args)},
                }
                last = out[-1] if out else None
                # parallel calls of one turn go into one assistant message
                if last and last["role"] == "assistant" and "tool_calls" in last:
                    last["tool_calls"].append(call)
                elif last and last["role"] == "assistant" and "tool_calls" not in last:
                    last["tool_calls"] = [call]
                else:
                    out.append({"role": "assistant", "content": "", "tool_calls": [call]})
            elif msg.role == "tool_result" and msg.call_id:
                out.append({"role": "tool", "tool_call_id": msg.call_id, "content": msg.content})
        return out

    def generate(self, messages: list[Message]) -> Generator[str | ToolCall, None, None]:
        if not self.quiet:
            print("Waiting on LLM...", flush=True)
        kwargs: dict[str, Any] = {"model": self.model, "messages": self._build_messages(messages)}
        if self.tools:
            kwargs["tools"] = self.tools
        resp = self.client.chat.completions.create(**kwargs)
        choice = resp.choices[0].message
        if choice.content:
            yield choice.content
        for tc in choice.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments) if tc.function.arguments else {}
            except json.JSONDecodeError:
                args = {}
            if not self.quiet:
                yield f"\n[Tool Call: {tc.function.name}]\n"
            yield ToolCall(name=tc.function.name, args=args, call_id=tc.id or f"call_{uuid.uuid4().hex[:12]}")
