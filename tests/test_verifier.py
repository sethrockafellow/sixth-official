"""The verifier: what it must stop, and what it must let through.

Planted errors: each test takes a comment that passes and breaks one rule.
"""
import copy

import pytest

from sixth import engine, generate, triggers
from sixth.narrator import TemplateNarrator
from sixth.pipeline import build_store, to_output
from sixth.schema import NarrativeOutput
from sixth.tools import MatchTools
from sixth.verifier import fallback_output, verify
import asyncio


@pytest.fixture(scope="module")
def world():
    E = engine.ReferenceStateEngine(generate.generate_match(4))
    store = build_store(E)
    trs = triggers.fire_triggers(E)
    goal = next(t for t in trs if t.is_goal)
    return E, store, trs, goal


def good(world, trig=None, lang="en"):
    E, store, trs, goal = world
    trig = trig or goal
    draft, _ = asyncio.run(TemplateNarrator().draft(trig.payload(lang).model_dump(), MatchTools(E, trig.match_clock_s)))
    return trig, to_output(draft, trig, lang, 1)


def check(world, out, trig):
    return verify(out, world[1], trig.match_clock_s)


def test_good_comments_pass(world):
    for trig in world[2][:20]:
        for lang in ("en", "es"):
            t, out = good(world, trig, lang)
            assert check(world, out, t).passed, out.text


def test_wrong_number_in_the_text(world):
    t, out = good(world)
    ev = [e for e in out.evidence if e.unit == "probability"][0]
    shown = ev.claim.split("%")[0].split()[-1]
    wrong = str(int(shown) + 12)
    out.text = out.text.replace(shown + "%", wrong + "%")
    ev.claim = ev.claim.replace(shown + "%", wrong + "%")
    r = check(world, out, t)
    assert not r.passed and "claim_number_matches" in {f.check for f in r.failures}


def test_wrong_value_reported(world):
    t, out = good(world)
    ev = [e for e in out.evidence if e.unit == "probability"][0]
    ev.value = float(ev.value) + 0.2
    assert not check(world, out, t).passed


def test_a_number_with_no_source(world):
    t, out = good(world)
    out.text = out.text.rstrip(".") + " after 7 shots."
    r = check(world, out, t)
    assert "no_loose_numbers" in {f.check for f in r.failures}


def test_a_source_from_the_future(world):
    E, store, trs, goal = world
    t, out = good(world)
    later = next(e for e in E.events if e.match_clock_s > t.match_clock_s + 60)
    out.evidence[-1].source = f"s_{later.event_id}.win_prob_home"
    r = check(world, out, t)
    assert "source_resolves" in {f.check for f in r.failures}


def test_a_wrong_label(world):
    t, out = good(world)
    lab = [e for e in out.evidence if e.label_metric == "xg"][0]
    wrong = "long shot" if lab.claim != "long shot" else "big chance"
    out.text = out.text.replace(lab.claim, wrong)
    lab.claim = wrong
    r = check(world, out, t)
    assert "label_matches" in {f.check for f in r.failures}


def test_a_spanish_label_is_checked(world):
    t, out = good(world, lang="es")
    lab = [e for e in out.evidence if e.label_metric == "xg"][0]
    wrong = "disparo lejano" if lab.claim != "disparo lejano" else "ocasión clara"
    out.text = out.text.replace(lab.claim, wrong)
    lab.claim = wrong
    assert not check(world, out, t).passed


def test_a_causal_word_with_no_delta(world):
    t, out = good(world)
    out.text = out.text.rstrip(".") + ", because the press broke them."
    r = check(world, out, t)
    assert "causal_words" in {f.check for f in r.failures}


def test_a_sentence_with_no_claim(world):
    t, out = good(world)
    out.text = out.text + " What a night."
    r = check(world, out, t)
    assert "sentence_rule" in {f.check for f in r.failures}


def test_every_fallback_passes_its_own_checks(world):
    E, store, trs, goal = world
    for trig in trs:
        for lang in ("en", "es"):
            t, out = good(world, trig, lang)
            fb = fallback_output(out, store)
            assert verify(fb, store, trig.match_clock_s).passed, fb.text


def test_decimals_stay_inside_their_sentence():
    from sixth.verifier import split_sentences
    assert split_sentences("Larkspur FC's momentum is 0.62. They now have a 40% chance to win.") == [
        "Larkspur FC's momentum is 0.62.", "They now have a 40% chance to win."]
    assert split_sentences("A big chance worth 0.31 xG") == ["A big chance worth 0.31 xG"]


def test_an_analyst_comment_with_a_decimal_passes(world):
    E, store, trs, goal = world
    from sixth.schema import EvidenceItem
    t, out = good(world)
    sid = "s_" + t.event_id
    mom = E.snapshot_by_id[sid].home.momentum
    claim = f"momentum {mom:.2f}"
    out.text = out.text.rstrip(".") + f". Larkspur FC have {claim}."
    out.evidence.append(EvidenceItem(claim=claim, source=f"{sid}.home.momentum", value=mom, unit="index"))
    r = check(world, out, t)
    assert r.passed, [f.detail for f in r.failures]
