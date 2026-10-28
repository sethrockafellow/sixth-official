"""python -m sixth.check_foundry: one comment through Microsoft Foundry, with plain messages.

It checks, in order: the two settings, your Azure sign-in, the model, and the tool loop. It
writes one comment for one moment of match 4, and shows the tool calls and the verifier's
result. It costs a fraction of a cent.
"""
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def say(ok, text):
    print(f"  {'OK  ' if ok else 'FIX '} {text}")


def main():
    print("Sixth Official: Foundry check\n")
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
    ep, model = os.environ.get("FOUNDRY_PROJECT_ENDPOINT", ""), os.environ.get("FOUNDRY_MODEL", "")
    say(bool(ep), f"FOUNDRY_PROJECT_ENDPOINT {'= ' + ep if ep else 'is not set (put it in .env)'}")
    say(bool(model), f"FOUNDRY_MODEL {'= ' + model if model else 'is not set (put it in .env)'}")
    if not (ep and model):
        sys.exit(1)
    if ".services.ai.azure.com" not in ep and ".openai.azure.com" not in ep:
        say(False, "the endpoint should be a Foundry address (https://<resource>.services.ai.azure.com/...)")
        sys.exit(1)
    if "/api/projects/" in ep:
        say(True, "project endpoint: the agent uses Agent Framework's FoundryChatClient")
    else:
        from .narrator import openai_v1_base
        say(True, f"resource endpoint: the agent uses {openai_v1_base(ep)} with your Azure sign-in")
    try:
        from azure.identity import AzureCliCredential
        AzureCliCredential().get_token("https://ai.azure.com/.default")
        say(True, "signed in to Azure (az login)")
    except Exception as e:
        say(False, f"not signed in: run  az login --use-device-code  ({type(e).__name__})")
        sys.exit(1)

    from .narrator import FoundryNarrator
    from .pipeline import run_match
    try:
        res = asyncio.run(run_match(4, FoundryNarrator(), ("en",), limit=1, log=lambda *a: None))
    except Exception as e:
        msg = str(e)
        say(False, f"the model call failed: {type(e).__name__}: {msg[:300]}")
        low = msg.lower()
        if "401" in msg or "403" in msg or "permission" in low or "authoriz" in low:
            print("       Give yourself the Foundry User role on the project (Azure portal, the project,")
            print("       Access control (IAM), Add role assignment, Foundry User or Azure AI User), wait 5 minutes.")
        elif "404" in msg or "deploymentnotfound" in low.replace(" ", "") or "not found" in low:
            print(f"       Check FOUNDRY_MODEL: it must be the deployment name in Foundry (Build, Models), not '{model}'?")
        sys.exit(1)
    rec = res["comments"][0]
    say(True, f"the model answered ({sum(t.get('seconds', 0) for t in rec['tries'])} s)")
    calls = [c["tool"] for c in rec["tool_calls"]]
    say(bool(calls), f"tool calls: {', '.join(calls) or 'none: the model did not use a tool'}")
    for i, t in enumerate(rec["tries"], 1):
        draft = (t.get("draft") or {}).get("text", "")
        print(f"       try {i}: {'passed' if t['passed'] else 'failed'}: {draft}")
        for f in t["failures"]:
            print(f"         - {f['check']}: {f['detail']}")
    o = rec["output"]
    say(o["status"] != "fallback", f"result: {o['status']}: {o['text']}")
    print("\nAll good: run a full match with  python -m sixth.run --seed 4 --narrator foundry" if o["status"] != "fallback"
          else "\nThe model's comment did not pass: the lines above show which check failed and why.")


if __name__ == "__main__":
    main()
