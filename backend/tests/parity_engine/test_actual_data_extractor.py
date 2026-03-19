import json
import re
from types import SimpleNamespace

from backend.app.parity_engine.extractor import GraphitiExtractionOverlay
from backend.app.parity_engine.graphiti_client import GraphitiEngine


ACTUAL_STYLE_ONTOLOGY = {
    "entity_types": [
        {"name": "MilitaryForce", "description": "Military actor or country conducting attacks.", "attributes": []},
        {"name": "PoliticalLeader", "description": "Political leader or decision-maker.", "attributes": []},
        {"name": "Target", "description": "Target facility, location, or strategic asset.", "attributes": []},
        {"name": "InternationalOrganization", "description": "International organization or institution.", "attributes": []},
        {"name": "MediaOutlet", "description": "Media outlet or news organization.", "attributes": []},
    ],
    "edge_types": [
        {
            "name": "plans_operation",
            "description": "Leader announces or plans military action.",
            "source_targets": [{"source": "PoliticalLeader", "target": "MilitaryForce"}],
            "attributes": [],
        },
        {
            "name": "targets",
            "description": "Military actor attacks a target.",
            "source_targets": [{"source": "MilitaryForce", "target": "Target"}],
            "attributes": [],
        },
        {
            "name": "reports_on",
            "description": "Organization reports damage involving a target.",
            "source_targets": [{"source": "InternationalOrganization", "target": "Target"}],
            "attributes": [],
        },
    ],
}


ACTUAL_STYLE_TEXT = (
    "미국 대통령 도널드 트럼프는 주요 전투 작전 개시를 발표했고, "
    "미군은 나탄즈 농축시설을 공습했다. "
    "국제원자력기구(IAEA)는 나탄즈 농축시설 피해를 보고했다."
)


ROLE_AWARE_GUARD_ONTOLOGY = {
    "entity_types": [
        {"name": "PoliticalLeader", "description": "Political actor.", "attributes": []},
        {"name": "MilitaryForce", "description": "Military actor.", "attributes": []},
        {"name": "Target", "description": "Attack or damage source.", "attributes": []},
        {"name": "CivilianPerson", "description": "Civilian or impacted party.", "attributes": []},
        {"name": "MediaOutlet", "description": "Reporting outlet.", "attributes": []},
        {"name": "Person", "description": "Person entity.", "attributes": []},
    ],
    "edge_types": [
        {
            "name": "plans_operation",
            "description": "Leader announces or plans military action.",
            "source_targets": [{"source": "PoliticalLeader", "target": "MilitaryForce"}],
            "attributes": [],
        },
        {
            "name": "impacts",
            "description": "Attack or war impact relation.",
            "source_targets": [{"source": "Target", "target": "CivilianPerson"}],
            "attributes": [],
        },
        {
            "name": "launches_attack_on",
            "description": "Military actor launches an attack.",
            "source_targets": [{"source": "MilitaryForce", "target": "Target"}],
            "attributes": [],
        },
        {
            "name": "reports_on",
            "description": "Outlet reports on a person.",
            "source_targets": [{"source": "MediaOutlet", "target": "Person"}],
            "attributes": [],
        },
    ],
}


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


def test_graphiti_overlay_uses_llm_json_for_actual_korean_report():
    fake_client = _FakeAsyncOpenAI(
        [
            {
                "entities": [
                    {"name": "도널드 트럼프", "type": "PoliticalLeader"},
                    {"name": "미군", "type": "MilitaryForce"},
                    {"name": "나탄즈 농축시설", "type": "Target"},
                    {"name": "국제원자력기구(IAEA)", "type": "InternationalOrganization"},
                ]
            },
            {
                "edges": [
                    {
                        "name": "PLANS_OPERATION",
                        "source": "도널드 트럼프",
                        "target": "미군",
                        "fact": "미국 대통령 도널드 트럼프는 주요 전투 작전 개시를 발표했고, 미군은 나탄즈 농축시설을 공습했다.",
                    },
                    {
                        "name": "TARGETS",
                        "source": "미군",
                        "target": "나탄즈 농축시설",
                        "fact": "미군은 나탄즈 농축시설을 공습했다.",
                    },
                ]
            },
            {
                "edges": [
                    {
                        "name": "REPORTS_ON",
                        "source": "국제원자력기구(IAEA)",
                        "target": "나탄즈 농축시설",
                        "fact": "국제원자력기구(IAEA)는 나탄즈 농축시설 피해를 보고했다.",
                    },
                ]
            },
        ]
    )
    overlay = GraphitiExtractionOverlay(
        llm_client=fake_client,
        model="fake-model",
    )

    result = overlay.extract(ACTUAL_STYLE_TEXT, ACTUAL_STYLE_ONTOLOGY)

    entity_names = {entity["name"] for entity in result["entities"]}
    edge_names = {edge["name"] for edge in result["edges"]}

    assert "도널드 트럼프" in entity_names
    assert "미군" in entity_names
    assert "나탄즈 농축시설" in entity_names
    assert "국제원자력기구(IAEA)" in entity_names
    assert edge_names == {"PLANS_OPERATION", "TARGETS", "REPORTS_ON"}
    assert len(fake_client.calls) >= 3


def test_graphiti_overlay_recovers_edges_when_llm_uses_type_placeholders():
    fake_client = _FakeAsyncOpenAI(
        [
            {
                "entities": [
                    {"name": "미국 대통령 도널드 트럼프", "type": "PoliticalLeader"},
                    {"name": "미국", "type": "MilitaryForce"},
                    {"name": "미군", "type": "MilitaryForce"},
                    {"name": "나탄즈(Natanz)", "type": "Target"},
                ]
            },
            {
                "edges": [
                    {
                        "name": "PLAN_OPERATION",
                        "source": "PoliticalLeader",
                        "target": "MilitaryForce",
                        "fact": "미국 대통령 도널드 트럼프는 영상 성명을 통해 주요 전투 작전 개시를 발표했다.",
                    },
                    {
                        "name": "TARGETS",
                        "source": "MilitaryForce",
                        "target": "Target",
                        "fact": "미군은 나탄즈(Natanz)를 표적으로 공습했다.",
                    },
                ]
            },
        ]
    )
    overlay = GraphitiExtractionOverlay(
        llm_client=fake_client,
        model="fake-model",
    )

    result = overlay.extract(ACTUAL_STYLE_TEXT, ACTUAL_STYLE_ONTOLOGY)
    edge_pairs = {(edge["name"], edge["source"], edge["target"]) for edge in result["edges"]}

    assert ("PLANS_OPERATION", "도널드 트럼프", "미국") in edge_pairs
    assert ("TARGETS", "미군", "나탄즈(Natanz)") in edge_pairs


def test_graphiti_overlay_trims_document_sized_fact_to_supporting_sentence():
    fake_client = _FakeAsyncOpenAI(
        [
            {
                "entities": [
                    {"name": "도널드 트럼프", "type": "PoliticalLeader"},
                    {"name": "미군", "type": "MilitaryForce"},
                    {"name": "나탄즈 농축시설", "type": "Target"},
                ]
            },
            {
                "edges": [
                    {
                        "name": "TARGETS",
                        "source": "미군",
                        "target": "나탄즈 농축시설",
                        "fact": ACTUAL_STYLE_TEXT,
                    }
                ]
            },
        ]
    )
    overlay = GraphitiExtractionOverlay(
        llm_client=fake_client,
        model="fake-model",
    )

    result = overlay.extract(ACTUAL_STYLE_TEXT, ACTUAL_STYLE_ONTOLOGY)

    assert result["edges"][0]["fact"] == "미군은 나탄즈 농축시설을 공습했다."


def test_graphiti_overlay_preserves_multiple_valid_edges():
    fake_client = _FakeAsyncOpenAI(
        [
            {
                "entities": [
                    {"name": "도널드 트럼프", "type": "PoliticalLeader"},
                    {"name": "미군", "type": "MilitaryForce"},
                    {"name": "나탄즈 농축시설", "type": "Target"},
                    {"name": "국제원자력기구(IAEA)", "type": "InternationalOrganization"},
                ]
            },
            {
                "edges": [
                    {
                        "name": "PLANS_OPERATION",
                        "source": "도널드 트럼프",
                        "target": "미군",
                        "fact": "도널드 트럼프는 주요 전투 작전 개시를 발표했다.",
                    },
                    {
                        "name": "TARGETS",
                        "source": "미군",
                        "target": "나탄즈 농축시설",
                        "fact": "미군은 나탄즈 농축시설을 공습했다.",
                    },
                ]
            },
            {
                "edges": [
                    {
                        "name": "REPORTS_ON",
                        "source": "국제원자력기구(IAEA)",
                        "target": "나탄즈 농축시설",
                        "fact": "국제원자력기구(IAEA)는 나탄즈 농축시설 피해를 보고했다.",
                    },
                ]
            },
        ]
    )
    overlay = GraphitiExtractionOverlay(
        llm_client=fake_client,
        model="fake-model",
    )

    result = overlay.extract(ACTUAL_STYLE_TEXT, ACTUAL_STYLE_ONTOLOGY)

    assert len(result["edges"]) == 3


def test_graphiti_overlay_runs_edge_pass_per_sentence():
    text = (
        "도널드 트럼프는 주요 전투 작전 개시를 발표했다. "
        "미군은 나탄즈 농축시설을 공습했다. "
        "국제원자력기구(IAEA)는 나탄즈 농축시설 피해를 보고했다."
    )
    fake_client = _FakeAsyncOpenAI(
        [
            {
                "entities": [
                    {"name": "도널드 트럼프", "type": "PoliticalLeader"},
                    {"name": "미군", "type": "MilitaryForce"},
                    {"name": "나탄즈 농축시설", "type": "Target"},
                    {"name": "국제원자력기구(IAEA)", "type": "InternationalOrganization"},
                ]
            },
            {
                "edges": [
                    {
                        "name": "PLANS_OPERATION",
                        "source": "도널드 트럼프",
                        "target": "미군",
                        "fact": "도널드 트럼프는 주요 전투 작전 개시를 발표했다.",
                    }
                ]
            },
            {
                "edges": [
                    {
                        "name": "TARGETS",
                        "source": "미군",
                        "target": "나탄즈 농축시설",
                        "fact": "미군은 나탄즈 농축시설을 공습했다.",
                    }
                ]
            },
            {
                "edges": [
                    {
                        "name": "REPORTS_ON",
                        "source": "국제원자력기구(IAEA)",
                        "target": "나탄즈 농축시설",
                        "fact": "국제원자력기구(IAEA)는 나탄즈 농축시설 피해를 보고했다.",
                    }
                ]
            },
        ]
    )
    overlay = GraphitiExtractionOverlay(llm_client=fake_client, model="fake-model")

    result = overlay.extract(text, ACTUAL_STYLE_ONTOLOGY)

    assert len(result["edges"]) == 3
    assert len(fake_client.calls) >= 4


def test_graphiti_overlay_uses_refinement_pass_to_fix_edge_quality():
    text = (
        "도널드 트럼프는 주요 전투 작전 개시를 발표했다. "
        "미군은 나탄즈 농축시설을 공습했다."
    )
    fake_client = _FakeAsyncOpenAI(
        [
            {
                "entities": [
                    {"name": "도널드 트럼프", "type": "PoliticalLeader"},
                    {"name": "미군", "type": "MilitaryForce"},
                    {"name": "나탄즈 농축시설", "type": "Target"},
                ]
            },
            {
                "edges": [
                    {
                        "name": "TARGETS",
                        "source": "도널드 트럼프",
                        "target": "미군",
                        "fact": text,
                    }
                ]
            },
            {
                "_refinement": True,
                "edges": [
                    {
                        "name": "PLANS_OPERATION",
                        "source": "도널드 트럼프",
                        "target": "미군",
                        "fact": "도널드 트럼프는 주요 전투 작전 개시를 발표했다.",
                    }
                ]
            },
            {
                "edges": [
                    {
                        "name": "TARGETS",
                        "source": "미군",
                        "target": "나탄즈 농축시설",
                        "fact": text,
                    }
                ]
            },
            {
                "_refinement": True,
                "edges": [
                    {
                        "name": "TARGETS",
                        "source": "미군",
                        "target": "나탄즈 농축시설",
                        "fact": "미군은 나탄즈 농축시설을 공습했다.",
                    }
                ]
            },
        ]
    )
    overlay = GraphitiExtractionOverlay(llm_client=fake_client, model="fake-model")

    result = overlay.extract(text, ACTUAL_STYLE_ONTOLOGY)
    edge_pairs = {(edge["name"], edge["source"], edge["target"], edge["fact"]) for edge in result["edges"]}

    assert ("PLANS_OPERATION", "도널드 트럼프", "미군", "도널드 트럼프는 주요 전투 작전 개시를 발표했다.") in edge_pairs
    assert ("TARGETS", "미군", "나탄즈 농축시설", "미군은 나탄즈 농축시설을 공습했다.") in edge_pairs


def test_graphiti_overlay_uses_final_consolidation_pass_to_fix_edge_set():
    text = (
        "도널드 트럼프는 주요 전투 작전 개시를 발표했다. "
        "미군은 나탄즈 농축시설을 공습했다."
    )
    fake_client = _FakeAsyncOpenAI(
        [
            {
                "entities": [
                    {"name": "도널드 트럼프", "type": "PoliticalLeader"},
                    {"name": "미군", "type": "MilitaryForce"},
                    {"name": "나탄즈 농축시설", "type": "Target"},
                ]
            },
            {
                "edges": [
                    {
                        "name": "TARGETS",
                        "source": "도널드 트럼프",
                        "target": "미군",
                        "fact": text,
                    }
                ]
            },
            {
                "_refinement": True,
                "edges": [
                    {
                        "name": "TARGETS",
                        "source": "도널드 트럼프",
                        "target": "미군",
                        "fact": text,
                    }
                ]
            },
            {
                "edges": [
                    {
                        "name": "TARGETS",
                        "source": "미군",
                        "target": "나탄즈 농축시설",
                        "fact": text,
                    },
                    {
                        "name": "TARGETS",
                        "source": "미군",
                        "target": "나탄즈 농축시설",
                        "fact": "미군은 나탄즈 농축시설을 공습했다.",
                    },
                ]
            },
            {
                "_refinement": True,
                "edges": [
                    {
                        "name": "TARGETS",
                        "source": "미군",
                        "target": "나탄즈 농축시설",
                        "fact": text,
                    },
                    {
                        "name": "TARGETS",
                        "source": "미군",
                        "target": "나탄즈 농축시설",
                        "fact": "미군은 나탄즈 농축시설을 공습했다.",
                    },
                ]
            },
            {
                "_consolidation": True,
                "edges": [
                    {
                        "name": "PLANS_OPERATION",
                        "source": "도널드 트럼프",
                        "target": "미군",
                        "fact": "도널드 트럼프는 주요 전투 작전 개시를 발표했다.",
                    },
                    {
                        "name": "TARGETS",
                        "source": "미군",
                        "target": "나탄즈 농축시설",
                        "fact": "미군은 나탄즈 농축시설을 공습했다.",
                    },
                ]
            },
        ]
    )
    overlay = GraphitiExtractionOverlay(llm_client=fake_client, model="fake-model")

    result = overlay.extract(text, ACTUAL_STYLE_ONTOLOGY)
    edge_pairs = {(edge["name"], edge["source"], edge["target"], edge["fact"]) for edge in result["edges"]}

    assert ("PLANS_OPERATION", "도널드 트럼프", "미군", "도널드 트럼프는 주요 전투 작전 개시를 발표했다.") in edge_pairs
    assert ("TARGETS", "미군", "나탄즈 농축시설", "미군은 나탄즈 농축시설을 공습했다.") in edge_pairs
    assert len(result["edges"]) == 2
    assert len(fake_client.calls) >= 7


def test_graphiti_overlay_prefers_shorter_fact_for_same_edge_triplet():
    text = "미군은 나탄즈 농축시설을 공습했다. 이후 추가 감시를 지시했다."
    fake_client = _FakeAsyncOpenAI(
        [
            {
                "entities": [
                    {"name": "미군", "type": "MilitaryForce"},
                    {"name": "나탄즈 농축시설", "type": "Target"},
                ]
            },
            {
                "edges": [
                    {
                        "name": "TARGETS",
                        "source": "미군",
                        "target": "나탄즈 농축시설",
                        "fact": text,
                    },
                    {
                        "name": "TARGETS",
                        "source": "미군",
                        "target": "나탄즈 농축시설",
                        "fact": "미군은 나탄즈 농축시설을 공습했다.",
                    },
                ]
            },
            {
                "_refinement": True,
                "edges": [
                    {
                        "name": "TARGETS",
                        "source": "미군",
                        "target": "나탄즈 농축시설",
                        "fact": text,
                    },
                    {
                        "name": "TARGETS",
                        "source": "미군",
                        "target": "나탄즈 농축시설",
                        "fact": "미군은 나탄즈 농축시설을 공습했다.",
                    },
                ]
            },
            {
                "_consolidation": True,
                "edges": [
                    {
                        "name": "TARGETS",
                        "source": "미군",
                        "target": "나탄즈 농축시설",
                        "fact": text,
                    },
                    {
                        "name": "TARGETS",
                        "source": "미군",
                        "target": "나탄즈 농축시설",
                        "fact": "미군은 나탄즈 농축시설을 공습했다.",
                    },
                ]
            },
        ]
    )
    overlay = GraphitiExtractionOverlay(llm_client=fake_client, model="fake-model")

    result = overlay.extract(text, ACTUAL_STYLE_ONTOLOGY)

    assert len(result["edges"]) == 1
    assert result["edges"][0]["fact"] == "미군은 나탄즈 농축시설을 공습했다."


def test_graphiti_overlay_keeps_distinct_valid_edges_when_consolidation_over_prunes():
    text = (
        "도널드 트럼프는 주요 전투 작전 개시를 발표했다. "
        "미군은 나탄즈 농축시설을 공습했다."
    )
    fake_client = _FakeAsyncOpenAI(
        [
            {
                "entities": [
                    {"name": "도널드 트럼프", "type": "PoliticalLeader"},
                    {"name": "미군", "type": "MilitaryForce"},
                    {"name": "나탄즈 농축시설", "type": "Target"},
                ]
            },
            {
                "edges": [
                    {
                        "name": "PLANS_OPERATION",
                        "source": "도널드 트럼프",
                        "target": "미군",
                        "fact": "도널드 트럼프는 주요 전투 작전 개시를 발표했다.",
                    }
                ]
            },
            {
                "_refinement": True,
                "edges": [
                    {
                        "name": "PLANS_OPERATION",
                        "source": "도널드 트럼프",
                        "target": "미군",
                        "fact": "도널드 트럼프는 주요 전투 작전 개시를 발표했다.",
                    }
                ]
            },
            {
                "edges": [
                    {
                        "name": "TARGETS",
                        "source": "미군",
                        "target": "나탄즈 농축시설",
                        "fact": "미군은 나탄즈 농축시설을 공습했다.",
                    }
                ]
            },
            {
                "_refinement": True,
                "edges": [
                    {
                        "name": "TARGETS",
                        "source": "미군",
                        "target": "나탄즈 농축시설",
                        "fact": "미군은 나탄즈 농축시설을 공습했다.",
                    }
                ]
            },
            {
                "_consolidation": True,
                "edges": [
                    {
                        "name": "TARGETS",
                        "source": "미군",
                        "target": "나탄즈 농축시설",
                        "fact": "미군은 나탄즈 농축시설을 공습했다.",
                    }
                ]
            },
        ]
    )
    overlay = GraphitiExtractionOverlay(llm_client=fake_client, model="fake-model")

    result = overlay.extract(text, ACTUAL_STYLE_ONTOLOGY)
    edge_names = {edge["name"] for edge in result["edges"]}

    assert edge_names == {"PLANS_OPERATION", "TARGETS"}


def test_graphiti_overlay_drops_edge_when_target_only_appears_inside_source_name():
    text = "미국과 이스라엘은 이란 해군 선박 50척 이상을 파괴·손상했다."
    fake_client = _FakeAsyncOpenAI(
        [
            {
                "entities": [
                    {"name": "이란 해군 선박", "type": "MilitaryForce"},
                    {"name": "이란", "type": "Target"},
                ]
            },
            {
                "edges": [
                    {
                        "name": "TARGETS",
                        "source": "이란 해군 선박",
                        "target": "이란",
                        "fact": "이란 해군 선박 50척 이상을 파괴·손상했다.",
                    }
                ]
            },
            {
                "_refinement": True,
                "edges": [
                    {
                        "name": "TARGETS",
                        "source": "이란 해군 선박",
                        "target": "이란",
                        "fact": "이란 해군 선박 50척 이상을 파괴·손상했다.",
                    }
                ]
            },
        ]
    )
    overlay = GraphitiExtractionOverlay(llm_client=fake_client, model="fake-model")

    result = overlay.extract(text, ACTUAL_STYLE_ONTOLOGY)

    assert result["edges"] == []


def test_graphiti_overlay_drops_edge_when_grounded_fact_omits_source_actor():
    text = "이란은 곧바로 주변국을 향한 미사일·드론 보복 타격으로 대응했다."
    fake_client = _FakeAsyncOpenAI(
        [
            {
                "entities": [
                    {"name": "미 국방 당국", "type": "MilitaryForce"},
                    {"name": "주변국", "type": "Target"},
                    {"name": "이란", "type": "MilitaryForce"},
                ]
            },
            {
                "edges": [
                    {
                        "name": "TARGETS",
                        "source": "미 국방 당국",
                        "target": "주변국",
                        "fact": text,
                    }
                ]
            },
            {
                "_refinement": True,
                "edges": [
                    {
                        "name": "TARGETS",
                        "source": "미 국방 당국",
                        "target": "주변국",
                        "fact": text,
                    }
                ]
            },
        ]
    )
    overlay = GraphitiExtractionOverlay(llm_client=fake_client, model="fake-model")

    result = overlay.extract(text, ACTUAL_STYLE_ONTOLOGY)

    assert result["edges"] == []


def test_graphiti_overlay_drops_plans_operation_without_planning_or_announcement_cue():
    text = "미국과 이스라엘은 대규모 합동 공습을 개시하며 전쟁이 발발했다."
    fake_client = _FakeAsyncOpenAI(
        [
            {
                "entities": [
                    {"name": "미국", "type": "PoliticalLeader"},
                    {"name": "이스라엘", "type": "MilitaryForce"},
                ]
            },
            {
                "edges": [
                    {
                        "name": "PLANS_OPERATION",
                        "source": "미국",
                        "target": "이스라엘",
                        "fact": text,
                    }
                ]
            },
            {
                "_refinement": True,
                "edges": [
                    {
                        "name": "PLANS_OPERATION",
                        "source": "미국",
                        "target": "이스라엘",
                        "fact": text,
                    }
                ]
            },
            {
                "_adjudication": True,
                "edges": []
            },
        ]
    )
    overlay = GraphitiExtractionOverlay(llm_client=fake_client, model="fake-model")

    result = overlay.extract(text, ROLE_AWARE_GUARD_ONTOLOGY)

    assert result["edges"] == []


def test_graphiti_overlay_drops_impacts_edge_when_target_is_only_reporting_source():
    text = "유엔 인권최고대표사무소는 적신월사(IRCS) 수치를 근거로 사망 787명을 언급했다."
    fake_client = _FakeAsyncOpenAI(
        [
            {
                "entities": [
                    {"name": "이란", "type": "Target"},
                    {"name": "적신월사(IRCS)", "type": "CivilianPerson"},
                ]
            },
            {
                "edges": [
                    {
                        "name": "IMPACTS",
                        "source": "이란",
                        "target": "적신월사(IRCS)",
                        "fact": text,
                    }
                ]
            },
            {
                "_refinement": True,
                "edges": [
                    {
                        "name": "IMPACTS",
                        "source": "이란",
                        "target": "적신월사(IRCS)",
                        "fact": text,
                    }
                ]
            },
            {
                "_adjudication": True,
                "edges": []
            },
        ]
    )
    overlay = GraphitiExtractionOverlay(llm_client=fake_client, model="fake-model")

    result = overlay.extract(text, ROLE_AWARE_GUARD_ONTOLOGY)

    assert result["edges"] == []


def test_graphiti_overlay_drops_launches_attack_on_when_fact_only_names_operation():
    text = "미군은 이를 Operation Epic Fury로 명명했고."
    fake_client = _FakeAsyncOpenAI(
        [
            {
                "entities": [
                    {"name": "미군", "type": "MilitaryForce"},
                    {"name": "자폭형(일회성) 드론 공격", "type": "Target"},
                ]
            },
            {
                "edges": [
                    {
                        "name": "LAUNCHES_ATTACK_ON",
                        "source": "미군",
                        "target": "자폭형(일회성) 드론 공격",
                        "fact": text,
                    }
                ]
            },
            {
                "_refinement": True,
                "edges": [
                    {
                        "name": "LAUNCHES_ATTACK_ON",
                        "source": "미군",
                        "target": "자폭형(일회성) 드론 공격",
                        "fact": text,
                    }
                ]
            },
        ]
    )
    overlay = GraphitiExtractionOverlay(llm_client=fake_client, model="fake-model")

    result = overlay.extract(text, ROLE_AWARE_GUARD_ONTOLOGY)

    assert result["edges"] == []


def test_graphiti_overlay_drops_reports_on_when_fact_omits_report_target():
    text = "로이터가 3월 10일 최대 150명을 보도했다."
    fake_client = _FakeAsyncOpenAI(
        [
            {
                "entities": [
                    {"name": "로이터", "type": "MediaOutlet"},
                    {"name": "도널드 트럼프", "type": "Person"},
                ]
            },
            {
                "edges": [
                    {
                        "name": "REPORTS_ON",
                        "source": "로이터",
                        "target": "도널드 트럼프",
                        "fact": text,
                    }
                ]
            },
            {
                "_refinement": True,
                "edges": [
                    {
                        "name": "REPORTS_ON",
                        "source": "로이터",
                        "target": "도널드 트럼프",
                        "fact": text,
                    }
                ]
            },
        ]
    )
    overlay = GraphitiExtractionOverlay(llm_client=fake_client, model="fake-model")

    result = overlay.extract(text, ROLE_AWARE_GUARD_ONTOLOGY)

    assert result["edges"] == []


def test_graphiti_overlay_regrounds_partial_plans_operation_fact_to_full_sentence():
    text = "미국 대통령 도널드 트럼프는 영상 성명을 통해 주요 전투 작전 개시를 발표했고, 미군은 이를 Operation Epic Fury로 명명했다."
    fake_client = _FakeAsyncOpenAI(
        [
            {
                "entities": [
                    {"name": "도널드 트럼프", "type": "PoliticalLeader"},
                    {"name": "미군", "type": "MilitaryForce"},
                ]
            },
            {
                "edges": [
                    {
                        "name": "PLANS_OPERATION",
                        "source": "도널드 트럼프",
                        "target": "미군",
                        "fact": "미군은 이를 Operation Epic Fury로 명명했다.",
                    }
                ]
            },
            {
                "_refinement": True,
                "edges": [
                    {
                        "name": "PLANS_OPERATION",
                        "source": "도널드 트럼프",
                        "target": "미군",
                        "fact": "미군은 이를 Operation Epic Fury로 명명했다.",
                    }
                ]
            },
        ]
    )
    overlay = GraphitiExtractionOverlay(llm_client=fake_client, model="fake-model")

    result = overlay.extract(text, ACTUAL_STYLE_ONTOLOGY)

    assert len(result["edges"]) == 1
    assert result["edges"][0]["name"] == "PLANS_OPERATION"
    assert result["edges"][0]["fact"] == text


def test_graphiti_overlay_recovers_missing_edge_via_whole_text_recovery_pass():
    text = (
        "도널드 트럼프는 주요 전투 작전 개시를 발표했다. "
        "미군은 나탄즈 농축시설을 공습했다."
    )
    fake_client = _FakeAsyncOpenAI(
        [
            {
                "entities": [
                    {"name": "도널드 트럼프", "type": "PoliticalLeader"},
                    {"name": "미군", "type": "MilitaryForce"},
                    {"name": "나탄즈 농축시설", "type": "Target"},
                ]
            },
            {
                "edges": [
                    {
                        "name": "TARGETS",
                        "source": "미군",
                        "target": "나탄즈 농축시설",
                        "fact": "미군은 나탄즈 농축시설을 공습했다.",
                    }
                ]
            },
            {
                "_refinement": True,
                "edges": [
                    {
                        "name": "TARGETS",
                        "source": "미군",
                        "target": "나탄즈 농축시설",
                        "fact": "미군은 나탄즈 농축시설을 공습했다.",
                    }
                ]
            },
            {
                "_recovery": True,
                "edges": [
                    {
                        "name": "PLANS_OPERATION",
                        "source": "도널드 트럼프",
                        "target": "미군",
                        "fact": "도널드 트럼프는 주요 전투 작전 개시를 발표했다.",
                    }
                ]
            },
        ]
    )
    overlay = GraphitiExtractionOverlay(llm_client=fake_client, model="fake-model")

    result = overlay.extract(text, ACTUAL_STYLE_ONTOLOGY)
    edge_names = {edge["name"] for edge in result["edges"]}

    assert edge_names == {"PLANS_OPERATION", "TARGETS"}


def test_graphiti_overlay_uses_semantic_adjudication_to_drop_false_positive_edge():
    text = (
        "미국과 이스라엘은 대규모 합동 공습을 개시하며 전쟁이 발발했다. "
        "미군은 나탄즈 농축시설을 공습했다."
    )
    fake_client = _FakeAsyncOpenAI(
        [
            {
                "entities": [
                    {"name": "미국", "type": "PoliticalLeader"},
                    {"name": "이스라엘", "type": "MilitaryForce"},
                    {"name": "미군", "type": "MilitaryForce"},
                    {"name": "나탄즈 농축시설", "type": "Target"},
                ]
            },
            {
                "edges": [
                    {
                        "name": "PLANS_OPERATION",
                        "source": "미국",
                        "target": "이스라엘",
                        "fact": "미국과 이스라엘은 대규모 합동 공습을 개시하며 전쟁이 발발했다.",
                    }
                ]
            },
            {
                "_refinement": True,
                "edges": [
                    {
                        "name": "PLANS_OPERATION",
                        "source": "미국",
                        "target": "이스라엘",
                        "fact": "미국과 이스라엘은 대규모 합동 공습을 개시하며 전쟁이 발발했다.",
                    }
                ]
            },
            {
                "edges": [
                    {
                        "name": "TARGETS",
                        "source": "미군",
                        "target": "나탄즈 농축시설",
                        "fact": "미군은 나탄즈 농축시설을 공습했다.",
                    }
                ]
            },
            {
                "_refinement": True,
                "edges": [
                    {
                        "name": "TARGETS",
                        "source": "미군",
                        "target": "나탄즈 농축시설",
                        "fact": "미군은 나탄즈 농축시설을 공습했다.",
                    }
                ]
            },
            {
                "_adjudication": True,
                "edges": [
                    {
                        "name": "TARGETS",
                        "source": "미군",
                        "target": "나탄즈 농축시설",
                        "fact": "미군은 나탄즈 농축시설을 공습했다.",
                    }
                ]
            },
        ]
    )
    overlay = GraphitiExtractionOverlay(llm_client=fake_client, model="fake-model")

    result = overlay.extract(text, ACTUAL_STYLE_ONTOLOGY)
    edge_names = {edge["name"] for edge in result["edges"]}
    prompt_texts = [call["messages"][1]["content"] for call in fake_client.calls]

    assert edge_names == {"TARGETS"}
    assert any("Adjudicate the candidate relations semantically" in prompt for prompt in prompt_texts)


def test_graphiti_overlay_drops_targets_edge_when_source_is_only_reporting_preamble():
    text = (
        "미 국방 당국과 다수 보도에 따르면, "
        "이란은 곧바로 이스라엘과 역내 미군 거점 및 주변국을 향한 미사일·드론 보복 타격으로 대응했다."
    )
    ontology = {
        "entity_types": [
            {"name": "MilitaryForce", "description": "Military actor.", "attributes": []},
            {"name": "Target", "description": "Attack target.", "attributes": []},
        ],
        "edge_types": [
            {
                "name": "targets",
                "description": "Military actor attacks a target.",
                "source_targets": [{"source": "MilitaryForce", "target": "Target"}],
                "attributes": [],
            }
        ],
    }
    fake_client = _FakeAsyncOpenAI(
        [
            {
                "entities": [
                    {"name": "미 국방 당국", "type": "MilitaryForce"},
                    {"name": "이란", "type": "MilitaryForce"},
                    {"name": "역내 미군 거점", "type": "Target"},
                ]
            },
            {
                "edges": [
                    {
                        "name": "TARGETS",
                        "source": "미 국방 당국",
                        "target": "역내 미군 거점",
                        "fact": text,
                    }
                ]
            },
            {
                "_refinement": True,
                "edges": [
                    {
                        "name": "TARGETS",
                        "source": "미 국방 당국",
                        "target": "역내 미군 거점",
                        "fact": text,
                    }
                ]
            },
            {
                "_adjudication": True,
                "edges": []
            },
        ]
    )
    overlay = GraphitiExtractionOverlay(llm_client=fake_client, model="fake-model")

    result = overlay.extract(text, ontology)

    assert result["edges"] == []


def test_graphiti_overlay_aggregates_entities_across_sentence_level_entity_passes():
    text = (
        "도널드 트럼프는 주요 전투 작전 개시를 발표했다. "
        "미군은 나탄즈 농축시설을 공습했다. "
        "국제원자력기구(IAEA)는 나탄즈 농축시설 피해를 보고했다."
    )
    fake_client = _FakeAsyncOpenAI(
        [
            {
                "entities": [
                    {"name": "도널드 트럼프", "type": "PoliticalLeader"},
                    {"name": "미군", "type": "MilitaryForce"},
                ]
            },
            {
                "entities": [
                    {"name": "국제원자력기구(IAEA)", "type": "InternationalOrganization"},
                    {"name": "나탄즈 농축시설", "type": "Target"},
                ]
            },
            {
                "edges": [
                    {
                        "name": "PLANS_OPERATION",
                        "source": "도널드 트럼프",
                        "target": "미군",
                        "fact": "도널드 트럼프는 주요 전투 작전 개시를 발표했다.",
                    }
                ]
            },
            {
                "edges": [
                    {
                        "name": "REPORTS_ON",
                        "source": "국제원자력기구(IAEA)",
                        "target": "나탄즈 농축시설",
                        "fact": "국제원자력기구(IAEA)는 나탄즈 농축시설 피해를 보고했다.",
                    }
                ]
            },
        ]
    )
    overlay = GraphitiExtractionOverlay(llm_client=fake_client, model="fake-model")

    result = overlay.extract(text, ACTUAL_STYLE_ONTOLOGY)
    entity_names = {entity["name"] for entity in result["entities"]}

    assert {"도널드 트럼프", "미군", "국제원자력기구(IAEA)", "나탄즈 농축시설"} <= entity_names
    assert len(fake_client.calls) >= 4


def test_graphiti_overlay_prefers_cleaner_display_names_from_llm_entities():
    fake_client = _FakeAsyncOpenAI(
        [
            {
                "entities": [
                    {"name": "미국 대통령 도널드 트럼프", "type": "PoliticalLeader", "aliases": ["도널드 트럼프"]},
                    {"name": "도널드 트럼프", "type": "PoliticalLeader"},
                    {"name": "GCC", "type": "InternationalOrganization"},
                    {"name": "걸프협력회의(GCC)", "type": "InternationalOrganization"},
                ]
            },
            {"edges": []},
        ]
    )
    overlay = GraphitiExtractionOverlay(
        llm_client=fake_client,
        model="fake-model",
    )

    result = overlay.extract(ACTUAL_STYLE_TEXT, ACTUAL_STYLE_ONTOLOGY)
    entity_names = {entity["name"] for entity in result["entities"]}

    assert "도널드 트럼프" in entity_names
    assert "미국 대통령 도널드 트럼프" not in entity_names
    assert "걸프협력회의(GCC)" in entity_names
    assert "GCC" not in entity_names


def test_graphiti_overlay_promotes_acronym_only_org_to_canonical_display_name():
    fake_client = _FakeAsyncOpenAI(
        [
            {
                "entities": [
                    {"name": "GCC", "type": "InternationalOrganization"},
                    {"name": "IAEA", "type": "InternationalOrganization"},
                ]
            },
            {"edges": []},
        ]
    )
    overlay = GraphitiExtractionOverlay(
        llm_client=fake_client,
        model="fake-model",
    )

    result = overlay.extract(ACTUAL_STYLE_TEXT, ACTUAL_STYLE_ONTOLOGY)
    entity_names = {entity["name"] for entity in result["entities"]}

    assert "걸프협력회의(GCC)" in entity_names
    assert "국제원자력기구(IAEA)" in entity_names
    assert "GCC" not in entity_names
    assert "IAEA" not in entity_names


def test_graphiti_overlay_filters_generic_document_titles():
    fake_client = _FakeAsyncOpenAI(
        [
            {
                "entities": [
                    {"name": "2026년 이란~미국 전쟁 심층 연대기 보고서", "type": "MediaOutlet"},
                    {"name": "도널드 트럼프", "type": "PoliticalLeader"},
                ]
            },
            {"edges": []},
        ]
    )
    overlay = GraphitiExtractionOverlay(
        llm_client=fake_client,
        model="fake-model",
    )

    result = overlay.extract(ACTUAL_STYLE_TEXT, ACTUAL_STYLE_ONTOLOGY)
    entity_names = {entity["name"] for entity in result["entities"]}

    assert "도널드 트럼프" in entity_names
    assert "2026년 이란~미국 전쟁 심층 연대기 보고서" not in entity_names


def test_graphiti_overlay_promotes_full_form_orgs_and_trims_quantity_names():
    fake_client = _FakeAsyncOpenAI(
        [
            {
                "entities": [
                    {"name": "유럽연합", "type": "InternationalOrganization"},
                    {"name": "걸프협력회의", "type": "InternationalOrganization"},
                    {"name": "이란 해군 선박 50척 이상", "type": "MilitaryForce"},
                    {"name": "이란 최고지도자 알리 하메네이", "type": "PoliticalLeader"},
                ]
            },
            {"edges": []},
        ]
    )
    overlay = GraphitiExtractionOverlay(
        llm_client=fake_client,
        model="fake-model",
    )

    result = overlay.extract(ACTUAL_STYLE_TEXT, ACTUAL_STYLE_ONTOLOGY)
    entity_names = {entity["name"] for entity in result["entities"]}

    assert "유럽연합(EU)" in entity_names
    assert "걸프협력회의(GCC)" in entity_names
    assert "이란 해군 선박" in entity_names
    assert "이란 최고지도자 알리 하메네이" not in entity_names
    assert "알리 하메네이" in entity_names


def test_graphiti_engine_inline_persists_llm_extraction(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHITI_EPISODE_INLINE", "true")
    monkeypatch.setenv("GRAPHITI_LLM_API_KEY", "dummy-key")
    monkeypatch.setenv("GRAPHITI_LLM_MODEL", "dummy-model")

    payload = {
        "entities": [
            {"name": "도널드 트럼프", "type": "PoliticalLeader"},
            {"name": "미군", "type": "MilitaryForce"},
            {"name": "나탄즈 농축시설", "type": "Target"},
            {"name": "국제원자력기구(IAEA)", "type": "InternationalOrganization"},
        ],
        "edges": [
            {
                "name": "PLANS_OPERATION",
                "source": "도널드 트럼프",
                "target": "미군",
                "fact": "미국 대통령 도널드 트럼프는 주요 전투 작전 개시를 발표했고, 미군은 나탄즈 농축시설을 공습했다.",
            },
            {
                "name": "TARGETS",
                "source": "미군",
                "target": "나탄즈 농축시설",
                "fact": "미군은 나탄즈 농축시설을 공습했다.",
            },
        ],
    }

    monkeypatch.setattr(
        GraphitiExtractionOverlay,
        "extract",
        lambda self, text, ontology: {
            **payload,
            "language": "ko",
            "ontology": ontology,
            "sentence_count": 2,
            "candidate_count": 4,
            "typed_entity_count": 4,
            "dropped_candidate_count": 0,
        },
    )

    engine = GraphitiEngine(db_path=tmp_path / "graphiti.kuzu")
    graph_id = engine.create_graph("Actual Style Graph", "desc")
    engine.set_ontology(graph_id, ACTUAL_STYLE_ONTOLOGY)
    engine.add_episode(graph_id, ACTUAL_STYLE_TEXT)

    nodes = engine.list_nodes(graph_id, limit=50)
    edges = engine.list_edges(graph_id, limit=50)

    assert len(nodes) >= 4
    assert len(edges) >= 2
