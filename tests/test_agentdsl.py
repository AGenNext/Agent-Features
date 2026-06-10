"""The agent DSL (*.agent.next): parse -> composite -> polyglot client stubs."""

from __future__ import annotations

from fastapi.testclient import TestClient

from gateway import agentdsl
from gateway.main import create_app

client = TestClient(create_app())

SAMPLE = """
agent greet-report
description "Greet someone, then report stats."
input name: string

step greeting = greet(name: input.name)
step stats = text_stats(text: greeting.greeting)

output greeting = greeting.greeting
output characters = stats.characters
"""


def test_parse_builds_a_composite():
    composite, errors = agentdsl.parse(SAMPLE)
    assert errors == []
    assert composite.name == "greet-report"
    assert [s.capability for s in composite.steps] == ["greet", "text_stats"]
    assert composite.input_schema["required"] == ["name"]
    assert composite.output == {"greeting": "greeting.greeting", "characters": "stats.characters"}


def test_parse_reports_line_numbered_errors():
    composite, errors = agentdsl.parse("agent x\nstep bad line\n")
    assert composite is None
    assert any("line 2" in e for e in errors)


def test_parse_requires_a_name():
    composite, errors = agentdsl.parse("step s = greet(name: input.n)")
    assert composite is None
    assert any("agent <name>" in e for e in errors)


def test_vendor_pinning_in_step():
    composite, errors = agentdsl.parse(
        "agent a\nstep g = greet@globex(name: input.n)\noutput o = g.greeting\ninput n: string"
    )
    assert errors == []
    assert composite.steps[0].vendor == "globex"


def test_codegen_all_languages_reference_the_agent():
    composite, _ = agentdsl.parse(SAMPLE)
    for lang in agentdsl.LANGUAGES:
        code = agentdsl.codegen(composite, lang)
        assert "greet-report" in code
        assert "/composites/greet-report/invoke" in code or lang == "proto"
    # language-specific signatures
    assert "export async function greetReport" in agentdsl.codegen(composite, "js")
    assert "interface GreetReportInput" in agentdsl.codegen(composite, "ts")
    assert "func GreetReport(" in agentdsl.codegen(composite, "go")
    assert "pub fn greet_report(" in agentdsl.codegen(composite, "rust")
    assert "class GreetReport" in agentdsl.codegen(composite, "java")
    assert "service GreetReport" in agentdsl.codegen(composite, "proto")


def test_aliases_resolve():
    composite, _ = agentdsl.parse(SAMPLE)
    assert agentdsl.codegen(composite, "typescript") == agentdsl.codegen(composite, "ts")


def test_compile_endpoint_returns_code_for_every_language():
    res = client.post("/agents/compile", json={"source": SAMPLE})
    body = res.json()
    assert body["ok"] is True
    assert set(body["code"]) == set(agentdsl.LANGUAGES)
    assert body["agent"]["name"] == "greet-report"


def test_compile_endpoint_reports_errors_cleanly():
    res = client.post("/agents/compile", json={"source": "nonsense line"})
    body = res.json()
    assert res.status_code == 200
    assert body["ok"] is False
    assert body["errors"]


def test_compiled_agent_can_be_published_and_run():
    # Publish via compile, then invoke — proving the DSL is executable.
    client.post("/agents/compile", json={"source": SAMPLE, "publish": True})
    run = client.post("/composites/greet-report/invoke", json={"input": {"name": "Ada"}}).json()
    assert run["output"]["greeting"] == "Hello, Ada. — Acme"
    assert run["output"]["characters"] == len("Hello, Ada. — Acme")
