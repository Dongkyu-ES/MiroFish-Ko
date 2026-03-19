"""Entity resolution helpers for parity overlays."""

from __future__ import annotations

import re


KNOWN_ALIASES = {
    "GCC": {"걸프협력회의", "GULFCOOPERATIONCOUNCIL"},
    "IAEA": {"국제원자력기구"},
    "EU": {"유럽연합", "EUROPEANUNION"},
    "OHCHR": {"유엔인권최고대표사무소", "유엔 인권최고대표사무소"},
    "UNHCR": {"유엔난민기구", "유엔 난민기구"},
    "IRCS": {"적신월사", "이란적신월사", "이란 적신월사"},
}


class EntityResolver:
    def should_merge(self, left: dict, right: dict) -> bool:
        if left.get("type") != right.get("type"):
            return False

        left_aliases = self.alias_keys(left.get("name", ""))
        right_aliases = self.alias_keys(right.get("name", ""))
        if left_aliases & right_aliases:
            return True

        left_acronym = self._acronym(left.get("name", ""))
        right_acronym = self._acronym(right.get("name", ""))
        return bool(left_acronym) and left_acronym == right_acronym

    def canonical_entity_key(self, name: str, type_: str) -> str:
        return f"{type_.strip().lower()}::{self.canonical_name(name)}"

    def canonical_name(self, value: str) -> str:
        return re.sub(r"[^a-z0-9가-힣]+", "", self._strip_parenthetical_alias(value).lower())

    def alias_keys(self, value: str) -> set[str]:
        aliases: set[str] = set()
        canonical = self.canonical_name(value)
        if canonical:
            aliases.add(canonical)

        person_core = self._person_core_name(value)
        if person_core:
            aliases.add(self.canonical_name(person_core))

        acronym = self._parenthetical_acronym(value) or self._acronym(value)
        if acronym:
            aliases.add(acronym.upper())
            for mapped in KNOWN_ALIASES.get(acronym.upper(), set()):
                aliases.add(self.canonical_name(mapped))

        stripped = self._strip_parenthetical_alias(value)
        if stripped:
            aliases.add(re.sub(r"[^A-Z0-9]+", "", stripped.upper()))

        if canonical.upper() in KNOWN_ALIASES:
            for mapped in KNOWN_ALIASES[canonical.upper()]:
                aliases.add(self.canonical_name(mapped))

        return {alias for alias in aliases if alias}

    def preferred_name(self, left: str, right: str) -> str:
        left_score = self._display_name_score(left)
        right_score = self._display_name_score(right)
        if right_score > left_score:
            return right
        if left_score > right_score:
            return left
        return right if len(right) > len(left) else left

    def promote_display_name(self, value: str) -> str:
        compact = value.strip()
        acronym = self._parenthetical_acronym(compact) or (compact if self._is_acronym(compact) else "")
        if acronym and acronym.upper() in KNOWN_ALIASES:
            choices = sorted(KNOWN_ALIASES[acronym.upper()], key=self._display_alias_priority, reverse=True)
            mapped = choices[0]
            if self._is_acronym(compact):
                return f"{mapped}({acronym.upper()})"

        for known_acronym, aliases in KNOWN_ALIASES.items():
            for alias in aliases:
                if self.canonical_name(compact) == self.canonical_name(alias):
                    best_alias = sorted(aliases, key=self._display_alias_priority, reverse=True)[0]
                    return f"{best_alias}({known_acronym})"

        quantity_trimmed = self._strip_quantity_suffix(compact)
        if quantity_trimmed != compact:
            compact = quantity_trimmed

        person_core = self._person_core_name(compact)
        if person_core != compact and self._looks_like_person_name(person_core):
            compact = person_core

        return compact

    def is_generic_title(self, value: str) -> bool:
        compact = value.strip()
        if any(token in compact for token in ("연대기 보고서", "심층 연대기 보고서", "보고서", "요약", "문서")):
            return True
        return False

    def _display_alias_priority(self, value: str) -> tuple[int, int]:
        has_korean = 1 if re.search(r"[가-힣]", value) else 0
        has_spaces = 1 if " " in value else 0
        no_country_prefix = 0 if re.match(r"^(이란|미국|영국|프랑스|독일|일본|중국|러시아)\s+", value) else 1
        return (has_korean, no_country_prefix, has_spaces, -len(value))

    def _strip_quantity_suffix(self, value: str) -> str:
        return re.sub(
            r"\s+\d[\d,]*(?:척|명|개|건|배럴(?:/일)?|%)(?:\s*(?:이상|이하|가량|정도))?$",
            "",
            value.strip(),
        )

    def _looks_like_person_name(self, value: str) -> bool:
        if re.fullmatch(r"[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,2}", value):
            return True
        tokens = [token for token in value.split() if token]
        if len(tokens) == 2 and all(re.search(r"[가-힣A-Za-z]", token) for token in tokens):
            return True
        if len(tokens) == 1 and 2 <= len(tokens[0]) <= 6 and re.search(r"[가-힣]", tokens[0]):
            return True
        return False

    def _acronym(self, value: str) -> str:
        parenthetical = self._parenthetical_acronym(value)
        if parenthetical:
            return parenthetical
        tokens = re.findall(r"[A-Za-z0-9가-힣]+", value)
        if len(tokens) == 1:
            return tokens[0].upper()
        stopwords = {"of", "the", "and"}
        return "".join(
            token[0].upper()
            for token in tokens
            if token and token.lower() not in stopwords
        )

    def _parenthetical_acronym(self, value: str) -> str:
        match = re.search(r"\(([A-Z]{2,10})\)", value)
        return match.group(1) if match else ""

    def _strip_parenthetical_alias(self, value: str) -> str:
        return re.sub(r"\([A-Z]{2,10}\)", "", value).strip()

    def _has_parenthetical_alias(self, value: str) -> bool:
        return bool(re.search(r"\([A-Z]{2,10}\)", value))

    def _is_acronym(self, value: str) -> bool:
        return bool(re.fullmatch(r"[A-Z0-9]{2,10}", value.strip()))

    def _display_name_score(self, value: str) -> int:
        score = 0
        stripped = self._strip_parenthetical_alias(value)

        if self._has_parenthetical_alias(value):
            score += 8
        if self._is_acronym(value):
            score -= 6
        if any(token in value for token in ("보고서", "요약", "문서", "연대기")):
            score -= 8
        if any(token in value for token in ("대통령", "총리", "장관", "사무총장", "최고지도자", "대사")):
            score -= 3
        if len(stripped.split()) <= 2:
            score += 3
        if len(stripped) > 30:
            score -= 2
        return score

    def _person_core_name(self, value: str) -> str:
        compact = value.strip()
        compact = re.sub(
            r"^(?:[가-힣A-Za-z]{2,12}\s+)?(?:대통령|총리|장관|외무장관|사무총장|최고지도자|대사)\s+",
            "",
            compact,
        )
        return compact.strip()
