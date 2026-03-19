import json
import re
from types import SimpleNamespace

from backend.app.parity_engine.extractor import GraphitiExtractionOverlay


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
        self.last_edge_payload = {"edges": []}

        async def create(**kwargs):
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


def test_graphiti_overlay_supports_korean_and_english_documents():
    fake_client = _FakeAsyncOpenAI(
        [
            {
                "entities": [
                    {"name": "민수", "type": "Person"},
                    {"name": "네이버", "type": "Company"},
                ]
            },
            {
                "edges": [
                    {
                        "name": "WORKS_FOR",
                        "source": "민수",
                        "target": "네이버",
                        "fact": "민수는 네이버에서 일한다.",
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
        "entity_types": [
            {"name": "Person", "attributes": []},
            {"name": "Company", "attributes": []},
        ],
        "edge_types": [
            {
                "name": "works_for",
                "source_targets": [{"source": "Person", "target": "Company"}],
                "attributes": [],
            }
        ],
    }

    result = overlay.extract("민수는 네이버에서 일한다.", ontology)
    entity_names = {entity["name"] for entity in result["entities"]}

    assert "민수" in entity_names
    assert "네이버" in entity_names
    assert result["edges"][0]["name"] == "WORKS_FOR"
