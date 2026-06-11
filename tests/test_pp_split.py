"""Tests for the in-process PP split used by the streaming orchestrator."""
import importlib.util, os, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "dictee_postprocess", ROOT / "dictee-postprocess.py")
pp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pp)

def test_run_pipeline_local_applies_capitalization():
    os.environ["DICTEE_PP_CAPITALIZATION"] = "true"
    try:
        out = pp.run_pipeline("bonjour le monde.", local_only=True)
        assert out.startswith("Bonjour")
    finally:
        os.environ.pop("DICTEE_PP_CAPITALIZATION", None)

def test_run_pipeline_local_skips_llm():
    # local_only must NOT call llm_postprocess even when LLM is enabled.
    os.environ["DICTEE_LLM_POSTPROCESS"] = "true"
    os.environ["DICTEE_LLM_POSITION"] = "last"
    called = {"n": 0}
    orig = pp.llm_postprocess
    pp.llm_postprocess = lambda t: (called.__setitem__("n", called["n"] + 1) or t)
    try:
        pp.run_pipeline("test", local_only=True)
    finally:
        pp.llm_postprocess = orig
        os.environ.pop("DICTEE_LLM_POSTPROCESS", None)
        os.environ.pop("DICTEE_LLM_POSITION", None)
    assert called["n"] == 0

def test_run_pipeline_full_runs_llm():
    os.environ["DICTEE_LLM_POSTPROCESS"] = "true"
    os.environ["DICTEE_LLM_POSITION"] = "last"
    called = {"n": 0}
    orig = pp.llm_postprocess
    pp.llm_postprocess = lambda t: (called.__setitem__("n", called["n"] + 1) or t)
    try:
        pp.run_pipeline("test", local_only=False)
    finally:
        pp.llm_postprocess = orig
        os.environ.pop("DICTEE_LLM_POSTPROCESS", None)
        os.environ.pop("DICTEE_LLM_POSITION", None)
    assert called["n"] == 1

def test_run_pipeline_local_skips_short_text():
    # short_text lowercases short utterances — must NOT run in local mode.
    os.environ["DICTEE_PP_SHORT_TEXT"] = "true"
    os.environ["DICTEE_PP_CAPITALIZATION"] = "true"
    try:
        out = pp.run_pipeline("bonjour", local_only=True)
        assert out == "Bonjour"  # capitalized, NOT lowercased by short_text
    finally:
        os.environ.pop("DICTEE_PP_SHORT_TEXT", None)
        os.environ.pop("DICTEE_PP_CAPITALIZATION", None)
