from backend.app.services.ontology_generator import ONTOLOGY_SYSTEM_PROMPT, OntologyGenerator


def test_ontology_prompt_examples_do_not_embed_instructional_suffixes_in_name_values():
    assert '"name": "EntityTypeName"' in ONTOLOGY_SYSTEM_PROMPT
    assert '"name": "EntityTypeName (영문 PascalCase)"' not in ONTOLOGY_SYSTEM_PROMPT
    assert '"name": "RELATION_NAME"' in ONTOLOGY_SYSTEM_PROMPT
    assert '"name": "RELATION_NAME (영문 UPPER_SNAKE_CASE)"' not in ONTOLOGY_SYSTEM_PROMPT


def test_ontology_generator_validate_and_process_sanitizes_instructional_suffixes():
    generator = OntologyGenerator(llm_client=object())
    result = generator._validate_and_process(
        {
            "entity_types": [
                {
                    "name": "MilitaryForce (영문 PascalCase)",
                    "description": "Military actor.",
                    "attributes": [],
                    "examples": [],
                },
                {
                    "name": "PoliticalLeader (영문 PascalCase)",
                    "description": "Political actor.",
                    "attributes": [],
                    "examples": [],
                },
                {
                    "name": "Person",
                    "description": "Fallback person.",
                    "attributes": [],
                    "examples": [],
                },
                {
                    "name": "Organization",
                    "description": "Fallback organization.",
                    "attributes": [],
                    "examples": [],
                },
            ],
            "edge_types": [
                {
                    "name": "HAS_TARGET (영문 UPPER_SNAKE_CASE)",
                    "description": "Target relationship.",
                    "source_targets": [
                        {
                            "source": "PoliticalLeader (영문 PascalCase)",
                            "target": "MilitaryForce (영문 PascalCase)",
                        }
                    ],
                    "attributes": [],
                }
            ],
            "analysis_summary": "",
        }
    )

    assert [entity["name"] for entity in result["entity_types"][:2]] == ["MilitaryForce", "PoliticalLeader"]
    assert result["edge_types"][0]["name"] == "HAS_TARGET"
    assert result["edge_types"][0]["source_targets"] == [
        {"source": "PoliticalLeader", "target": "MilitaryForce"}
    ]
