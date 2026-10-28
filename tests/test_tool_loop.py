"""The real Microsoft Agent Framework tool loop, against a fake model server (no Azure).

The fake model calls get_event_context, then writes a comment that cites it. In the
"wrong_first" mode its first draft has a wrong percent: the verifier must catch it, and
the retry must fix it.
"""
import asyncio

import pytest

agent_framework = pytest.importorskip("agent_framework")

import fake_model
from sixth.narrator import FoundryNarrator
from sixth.pipeline import run_match


@pytest.fixture(scope="module")
def client():
    from agent_framework.openai import OpenAIChatCompletionClient
    srv = fake_model.start()
    yield OpenAIChatCompletionClient(model="fake", api_key="test", base_url=f"http://127.0.0.1:{srv.server_address[1]}/v1",
                                     function_invocation_configuration={"max_function_calls": 4})
    srv.shutdown()


def test_tools_are_called_and_comments_verified(client):
    fake_model.STATE.update(mode="good", calls=0)
    res = asyncio.run(run_match(4, FoundryNarrator(client=client), ("en",), limit=4, log=lambda *a: None))
    assert res["catch"]["total"] == 4 and res["catch"]["fallback"] == 0
    assert all(r["tool_calls"] and r["tool_calls"][0]["tool"] == "get_event_context" for r in res["comments"])
    assert all(r["output"]["status"] == "verified" for r in res["comments"])


def test_a_wrong_draft_is_caught_and_fixed_on_retry(client):
    fake_model.STATE.update(mode="wrong_first", calls=0)
    res = asyncio.run(run_match(4, FoundryNarrator(client=client), ("en",), limit=4, log=lambda *a: None))
    assert all(r["output"]["status"] == "verified_on_retry" for r in res["comments"])
    assert len(res["stopped"]) == 4
    assert all(any(f["check"] == "claim_number_matches" for f in s["failures"]) for s in res["stopped"])
