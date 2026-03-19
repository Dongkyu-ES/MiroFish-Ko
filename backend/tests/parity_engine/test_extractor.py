import json
import re
from types import SimpleNamespace

from backend.app.parity_engine.extractor import GraphitiExtractionOverlay, _build_edge_adjudication_prompt


class _FakeAsyncOpenAI:
    def __init__(self, payloads):
        if isinstance(payloads, dict):
            payloads = [payloads]
        self.entity_payloads = [payload for payload in payloads if "entities" in payload and "edges" not in payload]
        self.refinement_payloads = [payload for payload in payloads if payload.get("_refinement")]
        self.recovery_payloads = [payload for payload in payloads if payload.get("_recovery")]
        self.adjudication_payloads = [payload for payload in payloads if payload.get("_adjudication")]
        self.consolidation_payloads = [payload for payload in payloads if payload.get("_consolidation")]
        self.edge_payloads = [
            payload
            for payload in payloads
            if "edges" in payload
            and "entities" not in payload
            and not payload.get("_refinement")
            and not payload.get("_recovery")
            and not payload.get("_adjudication")
            and not payload.get("_consolidation")
        ]
        self.calls = []
        self.last_edge_payload = {"edges": []}

        async def create(**kwargs):
            self.calls.append(kwargs)
            prompt = kwargs["messages"][1]["content"]
            if "Consolidate the candidate relations" in prompt:
                queue = self.consolidation_payloads
                if queue:
                    payload = queue.pop(0) if len(queue) > 1 else queue[0]
                else:
                    match = re.search(
                        r"Candidate relations gathered from multiple sentence/window passes:\n(.*?)\nRules:",
                        prompt,
                        flags=re.DOTALL,
                    )
                    payload = {"edges": json.loads(match.group(1)).copy()} if match else self.last_edge_payload
            elif "Adjudicate the candidate relations semantically" in prompt:
                queue = self.adjudication_payloads
                if queue:
                    payload = queue.pop(0) if len(queue) > 1 else queue[0]
                else:
                    match = re.search(
                        r"Candidate relations to adjudicate:\n(.*?)\nRules:",
                        prompt,
                        flags=re.DOTALL,
                    )
                    payload = {"edges": json.loads(match.group(1)).copy()} if match else self.last_edge_payload
            elif "Find any additional missing relations" in prompt:
                queue = self.recovery_payloads
                payload = queue.pop(0) if len(queue) > 1 else (queue[0] if queue else {"edges": []})
            elif "Refine the candidate relations" in prompt:
                queue = self.refinement_payloads
                payload = queue.pop(0) if len(queue) > 1 else (queue[0] if queue else self.last_edge_payload)
            elif "Extract only entities" in prompt:
                queue = self.entity_payloads
                payload = queue.pop(0) if len(queue) > 1 else queue[0]
            else:
                queue = self.edge_payloads
                payload = queue.pop(0) if len(queue) > 1 else queue[0]
                self.last_edge_payload = payload
            if "_refinement" in payload or "_recovery" in payload or "_adjudication" in payload or "_consolidation" in payload:
                payload = {k: v for k, v in payload.items() if k not in {"_refinement", "_recovery", "_adjudication", "_consolidation"}}
            content = json.dumps(payload, ensure_ascii=False)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content=content)
                    )
                ]
            )

        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=create)
        )


def test_graphiti_overlay_returns_entities_and_edges():
    fake_client = _FakeAsyncOpenAI(
        [
            {
                "entities": [
                    {"name": "Alice", "type": "Person"},
                    {"name": "Example Labs", "type": "Company"},
                ]
            },
            {
                "edges": [
                    {
                        "name": "WORKS_FOR",
                        "source": "Alice",
                        "target": "Example Labs",
                        "fact": "Alice works for Example Labs.",
                    }
                ]
            },
        ]
    )
    overlay = GraphitiExtractionOverlay(
        llm_client=fake_client,
        model="fake-model",
    )
    ontology = {
        "entity_types": [{"name": "Person", "attributes": []}, {"name": "Company", "attributes": []}],
        "edge_types": [
            {
                "name": "works_for",
                "source_targets": [{"source": "Person", "target": "Company"}],
                "attributes": [],
            }
        ],
    }

    result = overlay.extract("Alice works for Example Labs.", ontology)

    assert "entities" in result
    assert "edges" in result
    assert result["edges"][0]["name"] == "WORKS_FOR"
    assert result["edges"][0]["provenance"]["text"] == "Alice works for Example Labs."
    assert len(fake_client.calls) >= 2


def test_edge_adjudication_prompt_rejects_weapon_event_targets_and_stat_trends():
    prompt = _build_edge_adjudication_prompt(
        text="탄도미사일 공격은 90% 감소했고 자폭형 드론 공격은 83% 감소했다.",
        ontology={
            "entity_types": [
                {"name": "MilitaryForce", "attributes": []},
                {"name": "Target", "attributes": []},
            ],
            "edge_types": [
                {
                    "name": "launches_attack_on",
                    "source_targets": [{"source": "MilitaryForce", "target": "Target"}],
                    "attributes": [],
                }
            ],
        },
        language="ko",
        entities=[
            {"name": "미군", "type": "MilitaryForce"},
            {"name": "탄도미사일 공격", "type": "Target"},
            {"name": "자폭형(일회성) 드론 공격", "type": "Target"},
        ],
        candidate_edges=[
            {
                "name": "LAUNCHES_ATTACK_ON",
                "source": "미군",
                "target": "탄도미사일 공격",
                "fact": "탄도미사일 공격은 90% 감소했다.",
            }
        ],
    )

    prompt_lower = prompt.lower()

    assert "weapon systems or attack types are not valid targets by themselves" in prompt_lower
    assert "count or trend sentences should not become attack-target relations" in prompt_lower
