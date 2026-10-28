"""python -m sixth.run: narrate one match and save it for the screen.

  python -m sixth.run --seed 4 --narrator template          no Azure: rule-based comments
  python -m sixth.run --seed 4 --narrator foundry           Microsoft Foundry (az login first)
  python -m sixth.run --seed 4 --narrator foundry --limit 3 three moments only: a cheap first test

The result goes to data/match-<seed>-<narrator>.json, which the screen replays.
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

from .pipeline import LANGUAGES, run_match, save

ROOT = Path(__file__).resolve().parent.parent


def sign_in_check():
    """Stop before the first comment if Azure sign-in fails (2026-10-26). Without this check, every
    comment fails, airs as a template, and the run overwrites a good match file with templates."""
    try:
        from azure.identity import AzureCliCredential
        AzureCliCredential().get_token("https://ai.azure.com/.default")
    except Exception as e:                      # any sign-in error: show it and stop
        first = str(e).strip().splitlines()[0][:300] if str(e).strip() else type(e).__name__
        sys.exit("Azure sign-in failed, so nothing was narrated and no file was written.\n"
                 f"  {first}\n"
                 "Sign in again (az logout, then az login --tenant <your tenant id>) and complete the\n"
                 "multi-factor prompt. Then check with: python -m sixth.check_foundry")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m sixth.run", description=__doc__.splitlines()[0])
    ap.add_argument("--seed", type=int, default=4, help="the match (the same seed gives the same match)")
    ap.add_argument("--narrator", choices=("template", "foundry"), default="template")
    ap.add_argument("--limit", type=int, default=None, help="only the first N moments")
    ap.add_argument("--languages", default=",".join(LANGUAGES), help="for example en or en,es")
    ap.add_argument("--concurrency", type=int, default=4, help="comments written at the same time")
    ap.add_argument("--out", default=None, help="the output file (default: data/match-SEED-NARRATOR.json)")
    a = ap.parse_args(argv)

    if a.narrator == "foundry":
        try:
            from dotenv import load_dotenv
            load_dotenv(ROOT / ".env")
        except ImportError:
            pass
        missing = [k for k in ("FOUNDRY_PROJECT_ENDPOINT", "FOUNDRY_MODEL") if not os.environ.get(k)]
        if missing:
            sys.exit(f"Set {' and '.join(missing)} first (in .env next to README.md). See README.md.")
        sign_in_check()
        from .narrator import FoundryNarrator
        narrator = FoundryNarrator()
    else:
        from .narrator import TemplateNarrator
        narrator = TemplateNarrator()

    langs = tuple(x.strip() for x in a.languages.split(",") if x.strip())
    result = asyncio.run(run_match(a.seed, narrator, langs, a.limit, a.concurrency))
    out = Path(a.out) if a.out else ROOT / "data" / f"match-{a.seed}-{a.narrator}.json"
    save(result, out)
    c = result["catch"]
    print(f"\n{c['total']} comments: {c['total'] - c['verified_on_retry'] - c['fallback']} verified first time, "
          f"{c['verified_on_retry']} fixed on retry, {c['fallback']} replaced by the template.")
    print(f"The verifier stopped {len(result['stopped'])} drafts. Saved: {out} ({result['seconds']} s)")


if __name__ == "__main__":
    main()
