"""narrator.py: the commentary agent, on Microsoft Foundry through Microsoft Agent Framework.

One agent writes one comment for one viewer and one moment. It may only state facts it got
from its tools (sixth.tools), and it must cite each one. The verifier then checks every claim
(sixth.verifier). A failed comment goes back to the agent once with the list of failures; a
second failure airs a template sentence instead.

Two narrators:
  FoundryNarrator   the real one: a Foundry model (for example gpt-5-mini) through Agent Framework.
                    It signs in as you with `az login` (AzureCliCredential): no keys.
  TemplateNarrator  a fixed, rule-based writer that uses the same tools. For tests and for a demo
                    with no Azure. It is labelled "template" everywhere it appears.

Settings for FoundryNarrator come from the environment (or a .env file):
  FOUNDRY_PROJECT_ENDPOINT  https://<resource>.services.ai.azure.com/api/projects/<project>
  FOUNDRY_MODEL             the model deployment name, for example gpt-5-mini
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field

from .roster import CLUBS, player as player_name
from .tools import MatchTools, ReplayClockError

PROMPT = (Path(__file__).parent / "prompts" / "narrator.md").read_text(encoding="utf-8")
MAX_TOOL_CALLS = 4


def parse_draft(text: str) -> dict:
    """The agent's answer as {"text", "evidence"}. Accepts a JSON object inside other text."""
    text = (text or "").strip()
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON object in the answer")
    d = json.loads(m.group(0))
    if not isinstance(d, dict) or not isinstance(d.get("text"), str) or not isinstance(d.get("evidence"), list):
        raise ValueError("the answer needs text and evidence")
    return {"text": d["text"].strip(), "evidence": [e for e in d["evidence"] if isinstance(e, dict)]}


def _safe(fn, *args, **kwargs) -> str:
    """A tool answer as JSON text. Errors go back to the model as data, so it can correct itself."""
    try:
        return json.dumps(fn(*args, **kwargs), default=str)
    except (ReplayClockError, ValueError) as e:
        return json.dumps({"error": str(e)})


def make_tools(T: MatchTools) -> list:
    """The four tools as Agent Framework function tools, bound to one moment of the match."""
    from agent_framework import tool

    @tool(name="get_event_context", approval_mode="never_require")
    def get_event_context(event_id: Annotated[str, Field(description="The event id, for example e000412.")]) -> str:
        """The event, the state before and after it, and the change (deltas) in every number. Call it first."""
        return _safe(T.get_event_context, event_id)

    @tool(name="get_match_state", approval_mode="never_require")
    def get_match_state(at_s: Annotated[float, Field(description="Seconds from kick-off; not after the moment.")]) -> str:
        """Score, possession and win chances at a time. Cite fields as <snapshot_id>.<field>."""
        return _safe(T.get_match_state, at_s)

    @tool(name="get_tactical_state", approval_mode="never_require")
    def get_tactical_state(team_id: Annotated[str, Field(description="home or away")],
                           at_s: Annotated[float, Field(description="Seconds from kick-off; not after the moment.")]) -> str:
        """One team's momentum, pressing, line height, block, possession share and xG total.
        Cite fields as <snapshot_id>.<team_id>.<field>."""
        return _safe(T.get_tactical_state, team_id, at_s)

    @tool(name="get_events", approval_mode="never_require")
    def get_events(type: Annotated[str, Field(description="pass, shot, save, recovery, pressure, foul, offside, carry, or empty for all")],
                   from_s: Annotated[float, Field(description="Window start, seconds from kick-off.")],
                   to_s: Annotated[float, Field(description="Window end; not after the moment.")],
                   limit: Annotated[int, Field(description="At most 50.")] = 10) -> str:
        """Events in a time window. Cite fields as <event_id>.<field>."""
        return _safe(T.get_events, type or None, from_s, to_s, limit)

    return [get_event_context, get_match_state, get_tactical_state, get_events]


def openai_v1_base(endpoint: str) -> str:
    """The resource's OpenAI v1 address from any address of the same Foundry resource."""
    ep = endpoint.strip().rstrip("/")
    root = ep.split("/openai")[0].split("/api/projects")[0]
    return root + "/openai/v1"


def default_client():
    """The model client, signed in as you through the Azure CLI (`az login`): no keys.

    FOUNDRY_PROJECT_ENDPOINT may be either address that the Foundry portal shows:
      .../api/projects/<project>   the project endpoint: Agent Framework's FoundryChatClient
      .../openai/v1 (or /responses) the resource's model endpoint, as in the portal's sample
                                    code: an OpenAI-format client with your Azure sign-in
    Both reach the same model deployment in Microsoft Foundry.
    """
    import os
    ep = os.environ.get("FOUNDRY_PROJECT_ENDPOINT", "")
    fic = {"max_function_calls": MAX_TOOL_CALLS}
    if "/api/projects/" in ep:
        from agent_framework.foundry import FoundryChatClient
        from azure.identity import AzureCliCredential
        return FoundryChatClient(credential=AzureCliCredential(), function_invocation_configuration=fic)
    from agent_framework.openai import OpenAIChatCompletionClient
    from azure.identity.aio import AzureCliCredential as AsyncAzureCliCredential, get_bearer_token_provider
    from openai import AsyncOpenAI
    token = get_bearer_token_provider(AsyncAzureCliCredential(), "https://ai.azure.com/.default")
    client = AsyncOpenAI(base_url=openai_v1_base(ep), api_key=token)
    return OpenAIChatCompletionClient(model=os.environ.get("FOUNDRY_MODEL"), async_client=client,
                                      function_invocation_configuration=fic)


class FoundryNarrator:
    name = "foundry"

    def __init__(self, client=None):
        import os
        self.client = client or default_client()
        self.model = os.environ.get("FOUNDRY_MODEL") or getattr(self.client, "model", None)
        # gpt-5 models think before they answer. A one-sentence comment needs little of that:
        # "low" is faster and cheaper. FOUNDRY_REASONING_EFFORT=none sends no setting (for models
        # without reasoning, such as gpt-4.1-mini). Used on the resource (/openai/v1) path.
        effort = os.environ.get("FOUNDRY_REASONING_EFFORT", "low").strip().lower()
        chat_path = type(self.client).__name__ == "OpenAIChatCompletionClient"
        self.options = {"reasoning_effort": effort} if chat_path and effort not in ("", "none") else None

    async def draft(self, payload: dict, tools: MatchTools, previous: dict | None = None,
                    failures: list | None = None) -> tuple[dict, dict]:
        """One draft. Returns (draft, info). info has the time taken and the model's raw answer."""
        from agent_framework import Agent
        agent = Agent(client=self.client, instructions=PROMPT, name="narrator", tools=make_tools(tools))
        message = "Trigger:\n" + json.dumps(payload)
        if previous is not None:
            message += ("\n\nYour last answer:\n" + json.dumps(previous) +
                        "\n\nThe verifier found these failures. Fix only these:\n" +
                        "\n".join(f"- {getattr(f, 'check', '')}: {getattr(f, 'detail', f)}" for f in failures or []))
        t0 = time.perf_counter()
        result = await agent.run(message, options=self.options) if self.options else await agent.run(message)
        raw = getattr(result, "text", None) or str(result)
        info = {"seconds": round(time.perf_counter() - t0, 2), "raw": raw[:4000]}
        usage = getattr(result, "usage_details", None)
        if usage is not None:
            info["usage"] = {k: v for k, v in (usage.items() if hasattr(usage, "items") else vars(usage).items())
                             if isinstance(v, (int, float))}
        return parse_draft(raw), info


# ---------------------------------------------------------------------------------------------
# The template narrator: rule-based, the same tools, the same evidence rules. No model.
# ---------------------------------------------------------------------------------------------
MOM_ES = {"on_top": "dominando", "even": "igualado", "under_pressure": "bajo presión"}
XG_ES = {"big chance": "ocasión clara", "half chance": "media ocasión", "long shot": "disparo lejano"}


def _xg_label(xg: float) -> str:
    return "big chance" if xg >= 0.3 else ("half chance" if xg >= 0.1 else "long shot")


class TemplateNarrator:
    name = "template"

    async def draft(self, payload: dict, tools: MatchTools, previous=None, failures=None) -> tuple[dict, dict]:
        eid, prefs = payload["event_id"], payload["preferences"]
        es = prefs.get("language", "en").startswith("es")
        lang = "es" if es else "en"
        ctx = tools.get_event_context(eid)
        ev, after = ctx["event"], ctx["state_after"]
        sid = after["snapshot_id"]
        side = ev["team_id"]
        team = CLUBS[side]
        wph = after["win_prob_home"]
        pct = f"{round(wph * 100)}%"
        evidence = []
        if ev["type"] == "shot" and ev.get("shot_outcome") == "goal":
            lab = _xg_label(ev.get("xg") or 0.0)
            lab_txt = XG_ES[lab] if es else lab
            chance = (f"probabilidad de victoria local del {pct}" if es else f"home win chance of {pct}")
            text = (f"{team} marca tras una {lab_txt}, {chance}." if es else f"{team} score from a {lab_txt}, {chance}.")
            evidence = [{"claim": lab_txt, "source": f"{eid}.xg", "value": ev.get("xg"), "unit": "label", "label_metric": "xg"},
                        {"claim": chance, "source": f"{sid}.win_prob_home", "value": wph, "unit": "probability", "label_metric": None}]
        else:
            mom = after[side]["momentum_label"]
            mom_txt = MOM_ES.get(mom, mom) if es else mom.replace("_", " ")
            chance = (f"victoria local {pct}" if es else f"home win chance {pct}")
            text = (f"{team}, ritmo {mom_txt}, {chance}." if es else f"{team} {mom_txt}, {chance}.")
            evidence = [{"claim": mom_txt, "source": f"{sid}.{side}.momentum_label", "value": mom, "unit": "label", "label_metric": "momentum"},
                        {"claim": chance, "source": f"{sid}.win_prob_home", "value": wph, "unit": "probability", "label_metric": None}]
        if prefs.get("favorite_player") and ev.get("player_id") == prefs["favorite_player"]:
            text = f"{player_name(ev['player_id'])}: " + text
        return {"text": text, "evidence": evidence}, {"seconds": 0.0, "raw": ""}

