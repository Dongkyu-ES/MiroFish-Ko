from backend.app.parity_engine.graphiti_ontology_adapter import build_graphiti_extraction_config


def test_build_graphiti_extraction_config_creates_entity_edge_maps():
    config = build_graphiti_extraction_config(
        {
            "entity_types": [
                {
                    "name": "Country",
                    "description": "A sovereign country.",
                    "attributes": [
                        {"name": "official_name", "description": "Official name"},
                    ],
                },
                {
                    "name": "Person",
                    "description": "A person.",
                    "attributes": [
                        {"name": "role", "description": "Role"},
                    ],
                },
            ],
            "edge_types": [
                {
                    "name": "supports",
                    "description": "Support relationship.",
                    "source_targets": [
                        {"source": "Country", "target": "Country"},
                        {"source": "Person", "target": "Country"},
                    ],
                    "attributes": [],
                }
            ],
        }
    )

    assert set(config.entity_types.keys()) == {"Country", "Person"}
    assert set(config.edge_types.keys()) == {"SUPPORTS"}
    assert config.edge_type_map[("Country", "Country")] == ["SUPPORTS"]
    assert config.edge_type_map[("Person", "Country")] == ["SUPPORTS"]
    assert "SUPPORTS" in config.custom_extraction_instructions


def test_build_graphiti_extraction_config_filters_invalid_source_targets():
    config = build_graphiti_extraction_config(
        {
            "entity_types": [
                {"name": "Country", "description": "A sovereign country.", "attributes": []},
            ],
            "edge_types": [
                {
                    "name": "ally_of",
                    "description": "Alliance relationship.",
                    "source_targets": [
                        {"source": "Country", "target": "Country"},
                        {"source": "Missing", "target": "Country"},
                    ],
                    "attributes": [],
                }
            ],
        }
    )

    assert config.edge_type_map == {("Country", "Country"): ["ALLY_OF"]}


def test_build_graphiti_extraction_config_is_compact_for_runtime_ingestion():
    config = build_graphiti_extraction_config(
        {
            "entity_types": [
                {
                    "name": "Country",
                    "description": "A sovereign country with diplomatic and military agency.",
                    "attributes": [
                        {"name": "official_name", "description": "Official name"},
                        {"name": "leader_name", "description": "Leader name"},
                    ],
                },
            ],
            "edge_types": [
                {
                    "name": "supports",
                    "description": "Support relationship between two actors in a conflict context.",
                    "source_targets": [
                        {"source": "Country", "target": "Country"},
                    ],
                    "attributes": [
                        {"name": "reason", "description": "Support reason"},
                    ],
                }
            ],
        }
    )

    assert config.entity_types["Country"].model_fields == {}
    assert config.edge_types["SUPPORTS"].model_fields == {}
    assert len(config.custom_extraction_instructions) < 500


def test_build_graphiti_extraction_config_sanitizes_instructional_suffixes():
    config = build_graphiti_extraction_config(
        {
            "entity_types": [
                {
                    "name": "MilitaryForce (영문 PascalCase)",
                    "description": "Military actor.",
                    "attributes": [],
                },
                {
                    "name": "PoliticalLeader (영문 PascalCase)",
                    "description": "Political actor.",
                    "attributes": [],
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
        }
    )

    assert set(config.entity_types.keys()) == {"MilitaryForce", "PoliticalLeader"}
    assert set(config.edge_types.keys()) == {"HAS_TARGET"}
    assert config.edge_type_map == {("PoliticalLeader", "MilitaryForce"): ["HAS_TARGET"]}
