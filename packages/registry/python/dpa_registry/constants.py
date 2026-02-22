from __future__ import annotations

from dataclasses import dataclass

from dpa_registry.models import RegistrySourceType

RAW_BUCKET = "legal-source-raw"
PARSED_BUCKET = "legal-source-parsed"

DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_OPENROUTER_MODEL = "openai/gpt-4o-mini"
DEFAULT_HTTP_TIMEOUT_SECONDS = 45


@dataclass(frozen=True)
class SeedSource:
    source_id: str
    authority: str
    celex_or_doc_id: str
    source_type: RegistrySourceType
    languages: tuple[str, ...]
    status_rule: str
    fetch_url_map: dict[str, str]


DEFAULT_SEED_SOURCES: tuple[SeedSource, ...] = (
    SeedSource(
        source_id="gdpr_regulation_2016_679",
        authority="EUR-Lex",
        celex_or_doc_id="32016R0679",
        source_type=RegistrySourceType.LAW,
        languages=("EN", "FR", "DE"),
        status_rule="IN_FORCE_FINAL_ONLY",
        fetch_url_map={
            "EN": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32016R0679",
            "FR": "https://eur-lex.europa.eu/legal-content/FR/TXT/?uri=CELEX:32016R0679",
            "DE": "https://eur-lex.europa.eu/legal-content/DE/TXT/?uri=CELEX:32016R0679",
        },
    ),
    SeedSource(
        source_id="scc_controller_processor_2021_915",
        authority="EUR-Lex",
        celex_or_doc_id="32021D0915",
        source_type=RegistrySourceType.LAW,
        languages=("EN", "FR", "DE"),
        status_rule="IN_FORCE_FINAL_ONLY",
        fetch_url_map={
            "EN": "https://eur-lex.europa.eu/legal-content/EN/ALL/?uri=CELEX%3A32021D0915",
            "FR": "https://eur-lex.europa.eu/legal-content/FR/ALL/?uri=CELEX%3A32021D0915",
            "DE": "https://eur-lex.europa.eu/legal-content/DE/ALL/?uri=CELEX%3A32021D0915",
        },
    ),
    SeedSource(
        source_id="scc_transfers_2021_914",
        authority="EUR-Lex",
        celex_or_doc_id="32021D0914",
        source_type=RegistrySourceType.LAW,
        languages=("EN", "FR", "DE"),
        status_rule="IN_FORCE_FINAL_ONLY",
        fetch_url_map={
            "EN": "https://eur-lex.europa.eu/legal-content/EN/ALL/?uri=CELEX%3A32021D0914",
            "FR": "https://eur-lex.europa.eu/legal-content/FR/ALL/?uri=CELEX%3A32021D0914",
            "DE": "https://eur-lex.europa.eu/legal-content/DE/ALL/?uri=CELEX%3A32021D0914",
        },
    ),
    SeedSource(
        source_id="edpb_guidelines_07_2020",
        authority="EDPB",
        celex_or_doc_id="GUIDELINES_07_2020",
        source_type=RegistrySourceType.GUIDELINE,
        languages=("EN",),
        status_rule="FINAL_OR_ADOPTED_ONLY",
        fetch_url_map={
            "EN": "https://www.edpb.europa.eu/our-work-tools/our-documents/guidelines/guidelines-072020-concepts-controller-and-processor-gdpr_en"
        },
    ),
    SeedSource(
        source_id="edpb_recommendations_01_2020",
        authority="EDPB",
        celex_or_doc_id="RECOMMENDATIONS_01_2020",
        source_type=RegistrySourceType.GUIDELINE,
        languages=("EN",),
        status_rule="FINAL_OR_ADOPTED_ONLY",
        fetch_url_map={
            "EN": "https://www.edpb.europa.eu/our-work-tools/our-documents/recommendations/recommendations-012020-measures-supplement-transfer_en"
        },
    ),
    SeedSource(
        source_id="edpb_opinion_22_2024",
        authority="EDPB",
        celex_or_doc_id="OPINION_22_2024",
        source_type=RegistrySourceType.GUIDELINE,
        languages=("EN",),
        status_rule="FINAL_OR_ADOPTED_ONLY",
        fetch_url_map={
            "EN": "https://www.edpb.europa.eu/our-work-tools/our-documents/opinion-board-art-64/opinion-222024-certain-data-protection-obligations_en"
        },
    ),
    SeedSource(
        source_id="edpb_processor_topic_monitor",
        authority="EDPB",
        celex_or_doc_id="TOPIC_PROCESSOR",
        source_type=RegistrySourceType.MONITOR,
        languages=("EN",),
        status_rule="FINAL_OR_ADOPTED_ONLY",
        fetch_url_map={
            "EN": "https://www.edpb.europa.eu/our-work-tools/our-documents/topic/processor_en"
        },
    ),
    SeedSource(
        source_id="eu_commission_adequacy_decisions",
        authority="European Commission",
        celex_or_doc_id="ADEQUACY_DECISIONS",
        source_type=RegistrySourceType.MONITOR,
        languages=("EN",),
        status_rule="FINAL_OR_ADOPTED_ONLY",
        fetch_url_map={
            "EN": "https://commission.europa.eu/law/law-topic/data-protection/international-dimension-data-protection/adequacy-decisions_en"
        },
    ),
)
