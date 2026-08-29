import json

import httpx

from app.analyst.package import EvidencePackage
from app.analyst.prompts import build_analyst_prompt
from app.agents.providers import LLMRequest, MockLLMProvider
from app.agents.providers.openai_compatible import OpenAICompatibleProvider
from app.agents.providers.config import load_provider_config


def analyst_request() -> LLMRequest:
    return LLMRequest(
        prompt="Synthesize the supplied evidence.",
        context={
            "evidence_package": {
                "task": {"id": "task-1", "status": "SUCCESS"},
                "evidence": [{"id": "evidence-1", "summary": "Tests passed."}],
                "executions": [{"id": "execution-1", "status": "SUCCESS"}],
                "observations": [],
                "limitations": [],
                "truncated": False,
            }
        },
        output_schema={"type": "object"},
        system_instruction="Analyst-only boundary.",
    )


def test_llm_request_supports_optional_analyst_boundary():
    request = analyst_request()

    assert request.system_instruction == "Analyst-only boundary."
    assert LLMRequest(prompt="old", context={}, output_schema={}).system_instruction == ""


def test_mock_analyst_provider_is_deterministic_and_evidence_grounded():
    provider = MockLLMProvider()

    first = provider.generate_analyst(analyst_request())
    second = provider.generate_analyst(analyst_request())

    assert first.payload == second.payload
    assert first.payload["findings"][0]["evidence_refs"] == ["evidence-1"]
    assert "reasoning" not in json.dumps(dict(first.payload)).lower()
    assert first.provider == "mock"


def test_analyst_prompt_declares_json_object_report_contract():
    package = EvidencePackage(
        task={},
        project={},
        plan={},
        executions=(),
        observations=(),
        evidence=(),
        lifecycle={},
        limitations=(),
        truncated=False,
    )

    prompt = build_analyst_prompt(package)

    assert "Return valid JSON only" in prompt
    for field in (
        "summary",
        "overall_status",
        "release_recommendation",
        "findings",
        "next_actions",
        "limitations",
        "evidence_coverage",
    ):
        assert field in prompt
    assert "checked_dimensions" in prompt
    assert "Do not use legacy report fields" in prompt
    assert "notes (array of strings)" in prompt


def test_openai_analyst_provider_uses_dedicated_boundary_and_schema():
    captured = {}
    config = load_provider_config(
        {
            "AGENTFORGE_LLM_PROVIDER": "openai-compatible",
            "AGENTFORGE_LLM_BASE_URL": "https://llm.example.test/v1",
            "AGENTFORGE_LLM_MODEL": "example-model",
            "AGENTFORGE_LLM_API_KEY": "test-secret-not-output",
        }
    )

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "summary": "Tests passed.",
                                    "overall_status": "HEALTHY",
                                    "release_recommendation": "READY",
                                    "findings": [],
                                    "next_actions": [],
                                    "limitations": [],
                                    "evidence_coverage": {
                                        "available_count": 1,
                                        "referenced_count": 0,
                                        "truncated": False,
                                        "notes": [],
                                    },
                                }
                            )
                        }
                    }
                ]
            },
        )

    provider = OpenAICompatibleProvider(
        config, transport=httpx.MockTransport(handler), sleeper=lambda _: None
    )
    response = provider.generate_analyst(analyst_request())

    assert response.payload["overall_status"] == "HEALTHY"
    assert captured["body"]["messages"][0]["content"] == "Analyst-only boundary."
    assert captured["body"]["response_format"] == {"type": "json_object"}
    assert "json_schema" not in json.dumps(captured["body"])
    assert captured["body"]["thinking"] == {"type": "disabled"}
