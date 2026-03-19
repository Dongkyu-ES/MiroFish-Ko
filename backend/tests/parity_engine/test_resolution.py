from backend.app.parity_engine.resolver import EntityResolver
from backend.app.parity_engine.temporal import TemporalEdgeLifecycleOverlay


def test_entity_resolver_merges_aliases():
    resolver = EntityResolver()
    assert resolver.should_merge(
        {"name": "MIT", "type": "University"},
        {"name": "Massachusetts Institute of Technology", "type": "University"},
    ) is True


def test_entity_resolver_merges_korean_duplicate_names():
    resolver = EntityResolver()
    assert resolver.should_merge(
        {"name": "미사일·드론 보복", "type": "Operation"},
        {"name": "미사일 드론 보복", "type": "Operation"},
    ) is True


def test_entity_resolver_merges_acronym_with_korean_full_form():
    resolver = EntityResolver()
    assert resolver.should_merge(
        {"name": "GCC", "type": "InternationalOrganization"},
        {"name": "걸프협력회의", "type": "InternationalOrganization"},
    ) is True


def test_entity_resolver_merges_parenthetical_alias_with_acronym():
    resolver = EntityResolver()
    assert resolver.should_merge(
        {"name": "국제원자력기구(IAEA)", "type": "InternationalOrganization"},
        {"name": "IAEA", "type": "InternationalOrganization"},
    ) is True


def test_entity_resolver_merges_ohchr_aliases():
    resolver = EntityResolver()
    assert resolver.should_merge(
        {"name": "유엔 인권최고대표사무소(OHCHR)", "type": "InternationalOrganization"},
        {"name": "OHCHR", "type": "InternationalOrganization"},
    ) is True


def test_entity_resolver_merges_ircs_aliases():
    resolver = EntityResolver()
    assert resolver.should_merge(
        {"name": "적신월사(IRCS)", "type": "InternationalOrganization"},
        {"name": "IRCS", "type": "InternationalOrganization"},
    ) is True


def test_entity_resolver_prefers_full_form_with_acronym_for_orgs():
    resolver = EntityResolver()
    assert resolver.preferred_name("GCC", "걸프협력회의(GCC)") == "걸프협력회의(GCC)"


def test_entity_resolver_prefers_clean_person_name_over_title_heavy_name():
    resolver = EntityResolver()
    assert resolver.preferred_name("미국 대통령 도널드 트럼프", "도널드 트럼프") == "도널드 트럼프"


def test_entity_resolver_avoids_document_title_as_preferred_name():
    resolver = EntityResolver()
    assert resolver.preferred_name(
        "2026년 이란~미국 전쟁 심층 연대기 보고서",
        "국제원자력기구(IAEA)",
    ) == "국제원자력기구(IAEA)"


def test_entity_resolver_promotes_plain_full_form_org_to_parenthetical_alias():
    resolver = EntityResolver()
    assert resolver.promote_display_name("유럽연합") == "유럽연합(EU)"
    assert resolver.promote_display_name("걸프협력회의") == "걸프협력회의(GCC)"
    assert resolver.promote_display_name("국제원자력기구") == "국제원자력기구(IAEA)"


def test_entity_resolver_trims_quantity_suffixes_from_display_names():
    resolver = EntityResolver()
    assert resolver.promote_display_name("이란 해군 선박 50척 이상") == "이란 해군 선박"


def test_entity_resolver_trims_title_heavy_person_names():
    resolver = EntityResolver()
    assert resolver.promote_display_name("이란 최고지도자 알리 하메네이") == "알리 하메네이"


def test_temporal_lifecycle_marks_previous_edge_invalid():
    overlay = TemporalEdgeLifecycleOverlay()
    previous, current = overlay.supersede(
        previous_edge={
            "name": "WORKS_FOR",
            "valid_at": "2024-01-01T00:00:00Z",
            "invalid_at": None,
            "expired_at": None,
        },
        replacement_edge={
            "name": "WORKS_FOR",
            "valid_at": "2025-01-01T00:00:00Z",
        },
        invalidated_at="2025-01-01T00:00:00Z",
    )

    assert previous["invalid_at"] == "2025-01-01T00:00:00Z"
    assert previous["expired_at"] == "2025-01-01T00:00:00Z"
    assert current["valid_at"] == "2025-01-01T00:00:00Z"
