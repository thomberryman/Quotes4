from __future__ import annotations

import argparse
import os
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_session_factory
from app.core.normalization import build_full_name, normalize_email
from app.core.rbac import PERMISSION_DEFINITIONS, ROLE_DEFINITIONS
from app.core.security import build_password_hasher
from app.models import (
    Company,
    CompanyClassification,
    CompanyContact,
    ComparableProjectLink,
    Contact,
    ContactRole,
    Discipline,
    LossReason,
    Permission,
    Project,
    ProjectBenchmarkDisciplineSummary,
    ProjectBenchmarkSummary,
    ProjectContact,
    ProjectDiscipline,
    ProjectExternalReference,
    ProjectMetadata,
    ProjectOutcome,
    ProjectParty,
    ProjectScheduleRange,
    Quote,
    QuoteLineItem,
    QuoteSection,
    QuoteVersion,
    ReferenceDataValue,
    ReferenceTermAlias,
    Role,
    RolePermission,
    UploadedFile,
    User,
    UserRoleAssignment,
)
from app.models.enums import (
    ActualMappingApprovalAction,
    BenchmarkActualsStatus,
    CetaImportCoverageMode,
    CetaImportIssueSeverity,
    CetaRowFinancialType,
    CompanyClassificationType,
    ComparableProjectLinkDisposition,
    ProjectOutcomeType,
    ProjectPartyRole,
    ProjectStatus,
    QuoteLineItemType,
    QuoteVersionStatus,
    UploadedFileCategory,
    UploadedFileStatus,
)
from app.modules.actuals_imports.schemas import (
    ApproveActualsImportBatchRequest,
    CreateActualsImportBatchRequest,
    UpdateActualsImportRowDecisionRequest,
    WorkerActualsImportIssue,
    WorkerActualsImportResultRequest,
    WorkerActualsImportRow,
)
from app.modules.actuals_imports.service import actuals_import_service
from app.modules.forecasts.engine import DEFAULT_CURVE_PROFILES, DEFAULT_SEQUENCE_TEMPLATES
from app.modules.forecasts.schemas import (
    ForecastLineAllocationsReplaceRequest,
    ForecastLineMonthAllocationWrite,
    ForecastVersionCreateRequest,
)
from app.modules.forecasts.service import forecast_service

SEED_MODE_DEMO = "demo"
SEED_MODE_BASELINE = "baseline"
VALID_SEED_MODES = frozenset({SEED_MODE_DEMO, SEED_MODE_BASELINE})


def _utc(
    year: int,
    month: int,
    day: int,
    hour: int = 9,
    minute: int = 0,
) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.strip().lower().split())
    return normalized or None


def _resolve_seed_mode(seed_mode: str | None = None) -> str:
    normalized = (seed_mode or os.getenv("SEED_MODE", SEED_MODE_DEMO)).strip().lower()
    if normalized not in VALID_SEED_MODES:
        valid_modes = ", ".join(sorted(VALID_SEED_MODES))
        raise RuntimeError(f"Unsupported seed mode '{normalized}'. Expected one of: {valid_modes}.")
    return normalized


def _line_amount(line_spec: dict[str, object]) -> float:
    if line_spec.get("amount") is not None:
        return round(float(line_spec["amount"]), 2)

    quantity = float(line_spec.get("quantity", 1) or 1)
    rate = float(line_spec.get("rate", 0) or 0)
    return round(quantity * rate, 2)


def _line_rate(line_spec: dict[str, object]) -> float:
    if line_spec.get("rate") is not None:
        return round(float(line_spec["rate"]), 2)

    quantity = float(line_spec.get("quantity", 1) or 1)
    if quantity == 0:
        return 0
    return round(_line_amount(line_spec) / quantity, 2)


def _section_total(section_spec: dict[str, object]) -> float:
    return round(
        sum(_line_amount(line_spec) for line_spec in section_spec["line_items"]),
        2,
    )


def _version_subtotal(version_spec: dict[str, object]) -> float:
    return round(
        sum(_section_total(section_spec) for section_spec in version_spec["sections"]),
        2,
    )


def _version_tax(version_spec: dict[str, object]) -> float:
    return round(float(version_spec.get("tax_amount", 0) or 0), 2)


def _version_total(version_spec: dict[str, object]) -> float:
    return round(_version_subtotal(version_spec) + _version_tax(version_spec), 2)


def _to_float(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 2)


def _build_variance_amount(
    quoted_amount: float,
    actual_amount: float | None,
) -> float | None:
    if actual_amount is None:
        return None
    return round(actual_amount - quoted_amount, 2)


def _build_variance_pct(quoted_amount: float, actual_amount: float | None) -> float | None:
    if actual_amount is None or quoted_amount <= 0:
        return None
    return round(((actual_amount - quoted_amount) / quoted_amount) * 100, 2)


CONTACT_ROLE_SEEDS = [
    ("executive_producer", "Executive Producer", "Commercial and client lead."),
    ("producer", "Producer", "Delivery and vendor coordination."),
    ("post_supervisor", "Post Supervisor", "Schedule and technical workflow owner."),
    ("finance", "Finance", "Commercial review and PO owner."),
    ("commissioning_editor", "Commissioning Editor", "Editorial stakeholder at broadcaster."),
    ("head_of_post", "Head of Post", "Internal post-production lead."),
    ("creative_director", "Creative Director", "Creative approval stakeholder."),
    ("partner_manager", "Partner Manager", "Platform or studio relationship lead."),
    ("account_director", "Account Director", "Vendor-side commercial contact."),
    ("client_services", "Client Services", "Facility-side day-to-day contact."),
]

DISCIPLINE_SEEDS = [
    ("offline", "Offline", 10),
    ("online", "Online", 20),
    ("grade", "Grade", 30),
    ("sound", "Sound", 40),
    ("localization", "Localization", 50),
    ("production", "Production", 60),
    ("gfx", "Graphics", 70),
]

LOSS_REASON_SEEDS = [
    ("price", "Price / Budget", "Lost on commercial positioning.", "commercial"),
    ("schedule", "Schedule Conflict", "Lost due to delivery timing.", "timing"),
    ("scope", "Scope Change", "Lost after the client changed scope.", "scope"),
    ("in_house", "Client Kept In-House", "Client moved the work internal.", "client"),
    (
        "creative_change",
        "Creative Direction Shift",
        "Lost after the brief changed materially.",
        "creative",
    ),
]

REFERENCE_DATA_SEEDS = {
    "currency": [
        ("GBP", "GBP", 10),
        ("USD", "USD", 20),
        ("EUR", "EUR", 30),
    ],
    "project_stage": [
        ("bid_submitted", "Bid Submitted", 10),
        ("active", "Active", 20),
        ("complete", "Complete", 30),
    ],
    "actuals_mapping_category": [
        ("editorial_labor", "Editorial Labor", 10),
        ("finishing_labor", "Finishing Labor", 20),
        ("audio_labor", "Audio Labor", 30),
        ("third_party_vendor", "Third-Party Vendor", 40),
        ("facility_cost", "Facility Cost", 50),
        ("travel_expense", "Travel / Expense", 60),
    ],
    "revenue_category": [
        ("editorial_services", "Editorial Services", 10),
        ("finishing_services", "Finishing Services", 20),
        ("audio_services", "Audio Services", 30),
        ("delivery_services", "Delivery Services", 40),
        ("pass_through", "Pass-Through Revenue", 50),
    ],
    "forecast_curve_profile": [
        {
            "key": key,
            "label": key.replace("_", " ").title(),
            "sort_order": index * 10,
            "metadata": {
                "shapeKey": str(definition.get("shapeKey", key)),
                "description": definition.get("description"),
                "defaultDisciplineCodes": definition.get("defaultDisciplineCodes", []),
                **{
                    config_key: definition[config_key]
                    for config_key in (
                        "startMultiplier",
                        "endMultiplier",
                        "baseMultiplier",
                        "peakMultiplier",
                        "pulseMultiplier",
                        "pulseSharpness",
                        "minimumMultiplier",
                        "flatMultiplier",
                    )
                    if definition.get(config_key) is not None
                },
            },
        }
        for index, (key, definition) in enumerate(DEFAULT_CURVE_PROFILES.items(), start=1)
    ],
    "forecast_sequence_template": [
        {
            "key": key,
            "label": key.replace("_", " ").title(),
            "sort_order": index * 10,
            "metadata": {
                "projectFormatKeys": [] if key == "default" else [key],
                "stages": [
                    {
                        "disciplineCode": discipline_code,
                        "stageKey": str(stage["stage"]),
                        "startPct": float(stage["start_pct"]),
                        "endPct": float(stage["end_pct"]),
                        "overlapPct": float(stage["overlap_pct"]),
                    }
                    for discipline_code, stage in template.items()
                ],
            },
        }
        for index, (key, template) in enumerate(DEFAULT_SEQUENCE_TEMPLATES.items(), start=1)
    ],
}

COMPANY_SEEDS = [
    {
        "name": "BBC Studios",
        "normalized_name": "bbc studios",
        "legal_name": "BBC Studios Distribution Limited",
        "currency_code": "GBP",
        "website_url": "https://www.bbcstudios.com",
        "notes": "Seeded client and broadcaster account for scripted launch campaigns.",
        "classifications": [
            CompanyClassificationType.client,
            CompanyClassificationType.broadcaster,
        ],
    },
    {
        "name": "North Star Pictures",
        "normalized_name": "north star pictures",
        "legal_name": "North Star Pictures Ltd",
        "currency_code": "GBP",
        "website_url": "https://northstarpictures.example",
        "notes": "Recurring scripted feature and promo client.",
        "classifications": [CompanyClassificationType.client],
    },
    {
        "name": "Silverline Media",
        "normalized_name": "silverline media",
        "legal_name": "Silverline Media Group Ltd",
        "currency_code": "GBP",
        "website_url": "https://silverlinemedia.example",
        "notes": "Factual and broadcaster-facing campaign client.",
        "classifications": [CompanyClassificationType.client],
    },
    {
        "name": "Aurora Creative",
        "normalized_name": "aurora creative",
        "legal_name": "Aurora Creative Ltd",
        "currency_code": "GBP",
        "website_url": "https://auroracreative.example",
        "notes": "Agency client for launch spots and branded campaigns.",
        "classifications": [CompanyClassificationType.client],
    },
    {
        "name": "Global Media",
        "normalized_name": "global media",
        "legal_name": "Global Media Networks plc",
        "currency_code": "GBP",
        "website_url": "https://globalmedia.example",
        "notes": "International broadcaster account with localization-heavy work.",
        "classifications": [
            CompanyClassificationType.client,
            CompanyClassificationType.broadcaster,
        ],
    },
    {
        "name": "Studio East",
        "normalized_name": "studio east",
        "legal_name": "Studio East Entertainment LLC",
        "currency_code": "USD",
        "website_url": "https://studioeast.example",
        "notes": "Studio-side client for launch spot campaigns.",
        "classifications": [
            CompanyClassificationType.client,
            CompanyClassificationType.studio,
        ],
    },
    {
        "name": "Harborlight Productions",
        "normalized_name": "harborlight productions",
        "legal_name": "Harborlight Productions Ltd",
        "currency_code": "GBP",
        "website_url": "https://harborlightproductions.example",
        "notes": "Primary production company partner on scripted campaigns.",
        "classifications": [CompanyClassificationType.production_company],
    },
    {
        "name": "Atlas Unit",
        "normalized_name": "atlas unit",
        "legal_name": "Atlas Unit Ltd",
        "currency_code": "GBP",
        "website_url": "https://atlasunit.example",
        "notes": "Production company partner for promos and branded work.",
        "classifications": [CompanyClassificationType.production_company],
    },
    {
        "name": "Netstream",
        "normalized_name": "netstream",
        "legal_name": "Netstream Media Inc.",
        "currency_code": "USD",
        "website_url": "https://netstream.example",
        "notes": "Global streaming platform counterparty.",
        "classifications": [CompanyClassificationType.streamer],
    },
    {
        "name": "Public Screen Network",
        "normalized_name": "public screen network",
        "legal_name": "Public Screen Network Ltd",
        "currency_code": "GBP",
        "website_url": "https://publicscreen.example",
        "notes": "Broadcast partner for linear campaign deliveries.",
        "classifications": [CompanyClassificationType.broadcaster],
    },
    {
        "name": "Apex Studios",
        "normalized_name": "apex studios",
        "legal_name": "Apex Studios LLC",
        "currency_code": "USD",
        "website_url": "https://apexstudios.example",
        "notes": "Studio distribution partner.",
        "classifications": [CompanyClassificationType.studio],
    },
    {
        "name": "Pixel Forge Post",
        "normalized_name": "pixel forge post",
        "legal_name": "Pixel Forge Post Ltd",
        "currency_code": "GBP",
        "website_url": "https://pixelforgepost.example",
        "notes": "Named competitor used for lost-opportunity examples.",
        "classifications": [CompanyClassificationType.competitor],
    },
    {
        "name": "Halo Post",
        "normalized_name": "halo post",
        "legal_name": "Halo Post Facilities Ltd",
        "currency_code": "GBP",
        "website_url": "https://halopost.example",
        "notes": "Facility vendor used in CETA import examples.",
        "classifications": [CompanyClassificationType.vendor],
    },
    {
        "name": "Waveform Audio",
        "normalized_name": "waveform audio",
        "legal_name": "Waveform Audio Ltd",
        "currency_code": "GBP",
        "website_url": "https://waveformaudio.example",
        "notes": "Audio finishing vendor used in import examples.",
        "classifications": [CompanyClassificationType.vendor],
    },
    {
        "name": "LinguaHub",
        "normalized_name": "linguahub",
        "legal_name": "LinguaHub GmbH",
        "currency_code": "EUR",
        "website_url": "https://linguahub.example",
        "notes": "Localization vendor used in import examples.",
        "classifications": [CompanyClassificationType.vendor],
    },
    {
        "name": "Prism Colour",
        "normalized_name": "prism colour",
        "legal_name": "Prism Colour Ltd",
        "currency_code": "GBP",
        "website_url": "https://prismcolour.example",
        "notes": "Color vendor for benchmark actual examples.",
        "classifications": [CompanyClassificationType.vendor],
    },
    {
        "name": "Music Vault",
        "normalized_name": "music vault",
        "legal_name": "Music Vault Licensing Ltd",
        "currency_code": "GBP",
        "website_url": "https://musicvault.example",
        "notes": "Music licensing vendor for ambiguous import rows.",
        "classifications": [CompanyClassificationType.vendor],
    },
]

CONTACT_SEEDS = [
    {
        "first_name": "Maya",
        "last_name": "Grant",
        "email": "maya.grant@northstarpictures.example",
        "phone": "+44 20 7946 4001",
        "mobile": "+44 7700 900101",
        "notes": "Primary client lead for scripted promo bids.",
    },
    {
        "first_name": "Oliver",
        "last_name": "Chen",
        "email": "oliver.chen@northstarpictures.example",
        "phone": "+44 20 7946 4002",
        "mobile": "+44 7700 900102",
        "notes": "Client-side post supervisor for active campaigns.",
    },
    {
        "first_name": "Priya",
        "last_name": "Desai",
        "email": "priya.desai@northstarpictures.example",
        "phone": "+44 20 7946 4003",
        "mobile": "+44 7700 900103",
        "notes": "Commercial approval contact for POs and revisions.",
    },
    {
        "first_name": "Sarah",
        "last_name": "Cole",
        "email": "sarah.cole@bbcstudios.example",
        "phone": "+44 20 7946 4101",
        "mobile": "+44 7700 900111",
        "notes": "Commissioning stakeholder on launch work.",
    },
    {
        "first_name": "Tom",
        "last_name": "Wilkes",
        "email": "tom.wilkes@bbcstudios.example",
        "phone": "+44 20 7946 4102",
        "mobile": "+44 7700 900112",
        "notes": "Finance approver for scripted campaigns.",
    },
    {
        "first_name": "Ellie",
        "last_name": "Rowe",
        "email": "ellie.rowe@silverlinemedia.example",
        "phone": "+44 20 7946 4201",
        "mobile": "+44 7700 900121",
        "notes": "Lead executive producer for promo packages.",
    },
    {
        "first_name": "Ben",
        "last_name": "Patel",
        "email": "ben.patel@silverlinemedia.example",
        "phone": "+44 20 7946 4202",
        "mobile": "+44 7700 900122",
        "notes": "Finance contact for broadcaster-facing work.",
    },
    {
        "first_name": "Nina",
        "last_name": "Clarke",
        "email": "nina.clarke@auroracreative.example",
        "phone": "+44 20 7946 4301",
        "mobile": "+44 7700 900131",
        "notes": "Creative lead for brand launch spots.",
    },
    {
        "first_name": "Harriet",
        "last_name": "Lowe",
        "email": "harriet.lowe@globalmedia.example",
        "phone": "+44 20 7946 4401",
        "mobile": "+44 7700 900141",
        "notes": "Head of Post for international rollouts.",
    },
    {
        "first_name": "Daniel",
        "last_name": "Kerr",
        "email": "daniel.kerr@studioeast.example",
        "phone": "+1 310 555 4101",
        "mobile": "+1 310 555 5101",
        "notes": "Studio-side executive producer for launch spots.",
    },
    {
        "first_name": "Sam",
        "last_name": "Okoro",
        "email": "sam.okoro@harborlightproductions.example",
        "phone": "+44 20 7946 4501",
        "mobile": "+44 7700 900151",
        "notes": "Production-side delivery owner.",
    },
    {
        "first_name": "Mia",
        "last_name": "Torres",
        "email": "mia.torres@atlasunit.example",
        "phone": "+44 20 7946 4601",
        "mobile": "+44 7700 900161",
        "notes": "Producer for broadcast and branded packages.",
    },
    {
        "first_name": "Rachel",
        "last_name": "Bloom",
        "email": "rachel.bloom@netstream.example",
        "phone": "+1 323 555 4201",
        "mobile": "+1 323 555 5201",
        "notes": "Streaming-platform partner manager.",
    },
    {
        "first_name": "Oscar",
        "last_name": "Bennett",
        "email": "oscar.bennett@publicscreen.example",
        "phone": "+44 20 7946 4701",
        "mobile": "+44 7700 900171",
        "notes": "Broadcaster-side commissioning contact.",
    },
    {
        "first_name": "Ava",
        "last_name": "Monroe",
        "email": "ava.monroe@apexstudios.example",
        "phone": "+1 310 555 4301",
        "mobile": "+1 310 555 5301",
        "notes": "Studio partner manager for theatrical marketing work.",
    },
    {
        "first_name": "Marcus",
        "last_name": "Vale",
        "email": "marcus.vale@halopost.example",
        "phone": "+44 20 7946 4801",
        "mobile": "+44 7700 900181",
        "notes": "Facility-side commercial lead.",
    },
    {
        "first_name": "Lena",
        "last_name": "Fischer",
        "email": "lena.fischer@linguahub.example",
        "phone": "+49 30 555 4101",
        "mobile": "+49 151 5550 4101",
        "notes": "Localization account director.",
    },
]

COMPANY_CONTACT_SEEDS = [
    {
        "company": "north star pictures",
        "email": "maya.grant@northstarpictures.example",
        "contact_role": "executive_producer",
        "job_title": "Executive Producer",
        "department": "Originals Marketing",
        "is_primary": True,
    },
    {
        "company": "north star pictures",
        "email": "oliver.chen@northstarpictures.example",
        "contact_role": "post_supervisor",
        "job_title": "Post Supervisor",
        "department": "Marketing Production",
        "is_primary": False,
    },
    {
        "company": "north star pictures",
        "email": "priya.desai@northstarpictures.example",
        "contact_role": "finance",
        "job_title": "Finance Director",
        "department": "Production Finance",
        "is_primary": False,
    },
    {
        "company": "bbc studios",
        "email": "sarah.cole@bbcstudios.example",
        "contact_role": "commissioning_editor",
        "job_title": "Commissioning Editor",
        "department": "Creative Marketing",
        "is_primary": True,
    },
    {
        "company": "bbc studios",
        "email": "tom.wilkes@bbcstudios.example",
        "contact_role": "finance",
        "job_title": "Finance Manager",
        "department": "Production Finance",
        "is_primary": False,
    },
    {
        "company": "silverline media",
        "email": "ellie.rowe@silverlinemedia.example",
        "contact_role": "executive_producer",
        "job_title": "Executive Producer",
        "department": "Marketing",
        "is_primary": True,
    },
    {
        "company": "silverline media",
        "email": "ben.patel@silverlinemedia.example",
        "contact_role": "finance",
        "job_title": "Finance Director",
        "department": "Finance",
        "is_primary": False,
    },
    {
        "company": "aurora creative",
        "email": "nina.clarke@auroracreative.example",
        "contact_role": "creative_director",
        "job_title": "Creative Director",
        "department": "Creative",
        "is_primary": True,
    },
    {
        "company": "global media",
        "email": "harriet.lowe@globalmedia.example",
        "contact_role": "head_of_post",
        "job_title": "Head of Post",
        "department": "Creative Services",
        "is_primary": True,
    },
    {
        "company": "studio east",
        "email": "daniel.kerr@studioeast.example",
        "contact_role": "executive_producer",
        "job_title": "Executive Producer",
        "department": "Marketing",
        "is_primary": True,
    },
    {
        "company": "harborlight productions",
        "email": "sam.okoro@harborlightproductions.example",
        "contact_role": "producer",
        "job_title": "Senior Producer",
        "department": "Production",
        "is_primary": True,
    },
    {
        "company": "atlas unit",
        "email": "mia.torres@atlasunit.example",
        "contact_role": "producer",
        "job_title": "Producer",
        "department": "Production",
        "is_primary": True,
    },
    {
        "company": "netstream",
        "email": "rachel.bloom@netstream.example",
        "contact_role": "partner_manager",
        "job_title": "Partner Manager",
        "department": "Content Partnerships",
        "is_primary": True,
    },
    {
        "company": "public screen network",
        "email": "oscar.bennett@publicscreen.example",
        "contact_role": "commissioning_editor",
        "job_title": "Commissioning Editor",
        "department": "Creative Marketing",
        "is_primary": True,
    },
    {
        "company": "apex studios",
        "email": "ava.monroe@apexstudios.example",
        "contact_role": "partner_manager",
        "job_title": "Partner Marketing Director",
        "department": "Theatrical Marketing",
        "is_primary": True,
    },
    {
        "company": "halo post",
        "email": "marcus.vale@halopost.example",
        "contact_role": "client_services",
        "job_title": "Client Services Director",
        "department": "Operations",
        "is_primary": True,
    },
    {
        "company": "linguahub",
        "email": "lena.fischer@linguahub.example",
        "contact_role": "account_director",
        "job_title": "Account Director",
        "department": "Localization",
        "is_primary": True,
    },
]

REFERENCE_ALIAS_SEEDS = [
    {
        "category": "actuals_mapping_category",
        "alias_text": "Conform suite",
        "canonical_key": "finishing_labor",
        "source_system": "ceta",
        "source_field_path": "description",
        "confidence_hint": 95,
    },
    {
        "category": "actuals_mapping_category",
        "alias_text": "Subtitle prep",
        "canonical_key": "third_party_vendor",
        "source_system": "ceta",
        "source_field_path": "description",
        "confidence_hint": 92,
    },
]

PROJECT_SEEDS = [
    {
        "id": "project_red_room",
        "code": "RR-TRAILER",
        "name": "Red Room Trailer Campaign",
        "status": ProjectStatus.bid,
        "description": (
            "Launch trailer campaign for a scripted thriller feature with a tight finishing "
            "window and staged client reviews."
        ),
        "quote_currency_code": "GBP",
        "start_date": date(2026, 4, 7),
        "end_date": date(2026, 6, 24),
        "bid_due_date": date(2026, 3, 27),
        "bid_submitted_at": _utc(2026, 3, 28, 9, 0),
        "metadata": {
            "content_type": "marketing",
            "content_subtype": "theatrical_trailer",
            "genre": "thriller",
            "format_type": "trailer_promo",
            "runtime_minutes": 2,
            "duration_weeks": 11,
            "episode_count": 1,
            "territory": "UK / EMEA",
            "language": "en-GB",
            "budget_target": 115000,
            "metadata": {
                "projectFormatKey": "trailer_promo",
                "primaryLanguageCode": "en-GB",
                "deliverableKeys": [
                    "theatrical_trailer_master",
                    "social_cutdowns",
                    "caption_package",
                ],
                "localizationKeys": ["caption_package:en-GB"],
                "complexityProfile": {
                    "finishing": "complex",
                    "audio": "standard",
                    "vfx": "medium",
                },
            },
        },
        "parties": [
            ("client", "north star pictures", True, "Lead commissioning client."),
            (
                "production_company",
                "harborlight productions",
                True,
                "Production company coordinating supplied media.",
            ),
            ("streamer", "netstream", True, "Streaming destination for the launch."),
        ],
        "contacts": [
            {
                "email": "maya.grant@northstarpictures.example",
                "company": "north star pictures",
                "contact_role": "executive_producer",
                "job_title": "Executive Producer",
                "is_primary": True,
                "notes": "Primary client approver.",
            },
            {
                "email": "oliver.chen@northstarpictures.example",
                "company": "north star pictures",
                "contact_role": "post_supervisor",
                "job_title": "Post Supervisor",
                "is_primary": False,
                "notes": "Handles turnovers and schedule updates.",
            },
            {
                "email": "sam.okoro@harborlightproductions.example",
                "company": "harborlight productions",
                "contact_role": "producer",
                "job_title": "Senior Producer",
                "is_primary": False,
                "notes": "Coordinates producer-side turnover.",
            },
            {
                "email": "rachel.bloom@netstream.example",
                "company": "netstream",
                "contact_role": "partner_manager",
                "job_title": "Partner Manager",
                "is_primary": False,
                "notes": "Approves final platform delivery list.",
            },
        ],
        "disciplines": ["offline", "online", "grade", "sound"],
        "schedule_ranges": [
            {
                "discipline": "offline",
                "label": "Offline editorial",
                "start_date": date(2026, 4, 7),
                "end_date": date(2026, 5, 8),
                "notes": "Cut build and first client review.",
            },
            {
                "discipline": "online",
                "label": "Online finish",
                "start_date": date(2026, 5, 4),
                "end_date": date(2026, 6, 12),
                "notes": "Conform, graphics integration, and master exports.",
            },
            {
                "discipline": "grade",
                "label": "Final grade",
                "start_date": date(2026, 6, 2),
                "end_date": date(2026, 6, 18),
                "notes": "HDR trim and final color.",
            },
            {
                "discipline": "sound",
                "label": "Trailer mix",
                "start_date": date(2026, 6, 10),
                "end_date": date(2026, 6, 24),
                "notes": "Mix, stems, and versioned outputs.",
            },
        ],
        "outcomes": [
            {
                "outcome_type": ProjectOutcomeType.bid,
                "effective_at": _utc(2026, 3, 28, 9, 0),
                "notes": "Bid submitted after final scope review.",
            }
        ],
        "quote": {
            "quote_number": "RR-TRAILER-Q",
            "title": "Red Room Trailer Campaign Quote",
            "versions": [
                {
                    "version_number": 1,
                    "status": QuoteVersionStatus.superseded,
                    "title": "Initial client issue",
                    "issued_at": _utc(2026, 3, 14, 10, 0),
                    "source_document_date": date(2026, 3, 14),
                    "source_version_label": "V1",
                    "client_facing_notes": "Initial scope for offline, finish, grade, and mix.",
                    "internal_notes": "Assumes supplied captions and final text copy.",
                    "sections": [
                        {
                            "name": "Editorial",
                            "line_items": [
                                {
                                    "discipline": "offline",
                                    "description": "Offline assembly",
                                    "quantity": 14,
                                    "unit": "day",
                                    "rate": 2000,
                                },
                                {
                                    "discipline": "offline",
                                    "description": "Client revisions",
                                    "quantity": 5,
                                    "unit": "day",
                                    "rate": 2000,
                                },
                            ],
                        },
                        {
                            "name": "Picture Finish",
                            "line_items": [
                                {
                                    "discipline": "online",
                                    "description": "Online conform",
                                    "quantity": 8,
                                    "unit": "day",
                                    "rate": 3500,
                                },
                                {
                                    "discipline": "online",
                                    "description": "Versioned exports",
                                    "quantity": 3,
                                    "unit": "deliverable",
                                    "rate": 2000,
                                },
                                {
                                    "discipline": "grade",
                                    "description": "Grade pass",
                                    "quantity": 5,
                                    "unit": "day",
                                    "rate": 4000,
                                },
                            ],
                        },
                        {
                            "name": "Audio",
                            "line_items": [
                                {
                                    "discipline": "sound",
                                    "description": "Trailer mix",
                                    "quantity": 8,
                                    "unit": "day",
                                    "rate": 2000,
                                }
                            ],
                        },
                    ],
                },
                {
                    "version_number": 2,
                    "status": QuoteVersionStatus.issued,
                    "title": "Revised client issue",
                    "issued_at": _utc(2026, 3, 28, 9, 0),
                    "source_document_date": date(2026, 3, 28),
                    "source_version_label": "V2",
                    "client_facing_notes": (
                        "Includes extra client revision time and revised audio delivery scope."
                    ),
                    "internal_notes": "Used as the working forecast source in the demo.",
                    "is_current": True,
                    "sections": [
                        {
                            "name": "Editorial",
                            "line_items": [
                                {
                                    "discipline": "offline",
                                    "description": "Offline assembly",
                                    "quantity": 15,
                                    "unit": "day",
                                    "rate": 2000,
                                },
                                {
                                    "discipline": "offline",
                                    "description": "Producer-led revisions",
                                    "quantity": 6,
                                    "unit": "day",
                                    "rate": 2000,
                                },
                            ],
                        },
                        {
                            "name": "Picture Finish",
                            "line_items": [
                                {
                                    "discipline": "online",
                                    "description": "Online conform and comps",
                                    "quantity": 10,
                                    "unit": "day",
                                    "rate": 3000,
                                },
                                {
                                    "discipline": "online",
                                    "description": "Versioned finishing passes",
                                    "quantity": 4,
                                    "unit": "deliverable",
                                    "rate": 2000,
                                },
                                {
                                    "discipline": "grade",
                                    "description": "Grade and HDR trims",
                                    "quantity": 7,
                                    "unit": "day",
                                    "rate": 3000,
                                },
                            ],
                        },
                        {
                            "name": "Audio",
                            "line_items": [
                                {
                                    "discipline": "sound",
                                    "description": "Trailer mix and stems",
                                    "quantity": 7,
                                    "unit": "day",
                                    "rate": 2000,
                                }
                            ],
                        },
                    ],
                },
            ],
        },
        "forecast": {
            "title": "Bid Working Forecast",
            "notes_text": "Working forecast for the live bid workspace.",
            "probability_percent": 65,
            "revision_reason": "Initial seeded bid forecast.",
            "manual_overrides": [
                {
                    "line_label_contains": "Offline assembly",
                    "reason": "Front-loaded editorial prep ahead of the first review.",
                    "allocations": [("2026-04", 18000), ("2026-05", 12000)],
                }
            ],
        },
    },
    {
        "id": "project_black_glass",
        "code": "BG-LAUNCH",
        "name": "Black Glass Series Launch",
        "status": ProjectStatus.complete,
        "description": "Completed scripted series launch campaign for streamer rollout.",
        "quote_currency_code": "GBP",
        "start_date": date(2025, 9, 29),
        "end_date": date(2025, 11, 14),
        "bid_due_date": date(2025, 9, 12),
        "bid_submitted_at": _utc(2025, 9, 12, 16, 0),
        "awarded_at": _utc(2025, 9, 18, 10, 0),
        "active_at": _utc(2025, 9, 29, 9, 0),
        "completed_at": _utc(2025, 11, 14, 18, 0),
        "metadata": {
            "content_type": "marketing",
            "content_subtype": "series_launch",
            "genre": "science_fiction",
            "format_type": "trailer_promo",
            "runtime_minutes": 2,
            "duration_weeks": 7,
            "episode_count": 1,
            "territory": "UK / Global",
            "language": "en-GB",
            "budget_target": 110000,
            "metadata": {
                "projectFormatKey": "trailer_promo",
                "primaryLanguageCode": "en-GB",
                "deliverableKeys": [
                    "launch_trailer_master",
                    "captions",
                    "social_cutdowns",
                ],
                "localizationKeys": ["caption_package:en-GB"],
                "complexityProfile": {
                    "finishing": "complex",
                    "audio": "standard",
                    "vfx": "low",
                },
            },
        },
        "parties": [
            ("client", "bbc studios", True, "Primary client account."),
            (
                "production_company",
                "harborlight productions",
                True,
                "Production-side delivery partner.",
            ),
            ("streamer", "netstream", True, "Launch destination."),
        ],
        "contacts": [
            {
                "email": "sarah.cole@bbcstudios.example",
                "company": "bbc studios",
                "contact_role": "commissioning_editor",
                "job_title": "Commissioning Editor",
                "is_primary": True,
                "notes": "Primary client creative approver.",
            },
            {
                "email": "tom.wilkes@bbcstudios.example",
                "company": "bbc studios",
                "contact_role": "finance",
                "job_title": "Finance Manager",
                "is_primary": False,
                "notes": "PO and change order approver.",
            },
            {
                "email": "sam.okoro@harborlightproductions.example",
                "company": "harborlight productions",
                "contact_role": "producer",
                "job_title": "Senior Producer",
                "is_primary": False,
                "notes": "Handles weekly schedule changes.",
            },
        ],
        "disciplines": ["offline", "online", "grade"],
        "schedule_ranges": [
            {
                "discipline": "offline",
                "label": "Editorial launch pass",
                "start_date": date(2025, 9, 29),
                "end_date": date(2025, 10, 23),
                "notes": "Editorial build and supervised reviews.",
            },
            {
                "discipline": "online",
                "label": "Finishing and outputs",
                "start_date": date(2025, 10, 13),
                "end_date": date(2025, 11, 7),
                "notes": "Conform, mastering, caption integration.",
            },
            {
                "discipline": "grade",
                "label": "Color finish",
                "start_date": date(2025, 11, 3),
                "end_date": date(2025, 11, 14),
                "notes": "Final grade and master approval.",
            },
        ],
        "outcomes": [
            {
                "outcome_type": ProjectOutcomeType.bid,
                "effective_at": _utc(2025, 9, 12, 16, 0),
                "notes": "Bid submitted with alternate finishing options.",
            },
            {
                "outcome_type": ProjectOutcomeType.awarded,
                "effective_at": _utc(2025, 9, 18, 10, 0),
                "notes": "Awarded after client creative sign-off.",
            },
        ],
        "quote": {
            "quote_number": "BG-LAUNCH-Q",
            "title": "Black Glass Series Launch Quote",
            "versions": [
                {
                    "version_number": 1,
                    "status": QuoteVersionStatus.superseded,
                    "title": "Initial issue",
                    "issued_at": _utc(2025, 9, 10, 12, 0),
                    "source_document_date": date(2025, 9, 10),
                    "source_version_label": "V1",
                    "client_facing_notes": "Initial issue for launch trailer scope.",
                    "internal_notes": "Superseded after online scope was expanded.",
                    "sections": [
                        {
                            "name": "Core Scope",
                            "line_items": [
                                {
                                    "discipline": "offline",
                                    "description": "Offline launch edit",
                                    "amount": 40000,
                                    "quantity": 1,
                                    "unit": "package",
                                },
                                {
                                    "discipline": "online",
                                    "description": "Online finishing",
                                    "amount": 35000,
                                    "quantity": 1,
                                    "unit": "package",
                                },
                                {
                                    "discipline": "grade",
                                    "description": "Grade and masters",
                                    "amount": 29000,
                                    "quantity": 1,
                                    "unit": "package",
                                },
                            ],
                        }
                    ],
                },
                {
                    "version_number": 2,
                    "status": QuoteVersionStatus.accepted,
                    "title": "Accepted issue",
                    "issued_at": _utc(2025, 9, 18, 11, 0),
                    "accepted_at": _utc(2025, 9, 19, 14, 0),
                    "source_document_date": date(2025, 9, 18),
                    "source_version_label": "V2",
                    "client_facing_notes": "Accepted issue with expanded online finishing.",
                    "internal_notes": "Used as the locked actuals benchmark source.",
                    "is_current": True,
                    "sections": [
                        {
                            "name": "Core Scope",
                            "line_items": [
                                {
                                    "discipline": "offline",
                                    "description": "Offline launch edit",
                                    "amount": 42000,
                                    "quantity": 1,
                                    "unit": "package",
                                },
                                {
                                    "discipline": "online",
                                    "description": "Online finishing",
                                    "amount": 38000,
                                    "quantity": 1,
                                    "unit": "package",
                                },
                                {
                                    "discipline": "grade",
                                    "description": "Grade and masters",
                                    "amount": 30000,
                                    "quantity": 1,
                                    "unit": "package",
                                },
                            ],
                        }
                    ],
                },
            ],
        },
        "benchmark": {
            "actuals_status": BenchmarkActualsStatus.complete,
            "actuals_as_of_date": date(2026, 3, 31),
            "discipline_actuals": {
                "offline": 45000,
                "online": 41000,
                "grade": 32000,
            },
        },
        "forecast": {
            "title": "Locked delivery forecast",
            "notes_text": "Seeded locked forecast tied to the accepted quote.",
            "revision_reason": "Initial delivery baseline.",
            "submit_after": True,
            "lock_after": True,
        },
    },
    {
        "id": "project_north_passage",
        "code": "NP-PROMO",
        "name": "North Passage Promo Package",
        "status": ProjectStatus.complete,
        "description": "Completed broadcaster promo package with straightforward finish.",
        "quote_currency_code": "GBP",
        "start_date": date(2025, 12, 1),
        "end_date": date(2026, 2, 13),
        "bid_due_date": date(2025, 11, 10),
        "bid_submitted_at": _utc(2025, 11, 10, 15, 0),
        "awarded_at": _utc(2025, 11, 14, 14, 0),
        "active_at": _utc(2025, 12, 1, 9, 0),
        "completed_at": _utc(2026, 2, 13, 18, 0),
        "metadata": {
            "content_type": "marketing",
            "content_subtype": "broadcast_promo",
            "genre": "adventure",
            "format_type": "trailer_promo",
            "runtime_minutes": 1,
            "duration_weeks": 10,
            "episode_count": 1,
            "territory": "UK",
            "language": "en-GB",
            "budget_target": 98000,
            "metadata": {
                "projectFormatKey": "trailer_promo",
                "primaryLanguageCode": "en-GB",
                "deliverableKeys": ["broadcast_master", "caption_package"],
                "localizationKeys": ["caption_package:en-GB"],
                "complexityProfile": {
                    "finishing": "complex",
                    "audio": "standard",
                    "vfx": "low",
                },
            },
        },
        "parties": [
            ("client", "silverline media", True, "Primary client account."),
            (
                "production_company",
                "atlas unit",
                True,
                "Production company handling source turnovers.",
            ),
            (
                "broadcaster",
                "public screen network",
                True,
                "Broadcast destination with caption requirement.",
            ),
        ],
        "contacts": [
            {
                "email": "ellie.rowe@silverlinemedia.example",
                "company": "silverline media",
                "contact_role": "executive_producer",
                "job_title": "Executive Producer",
                "is_primary": True,
                "notes": "Primary client lead.",
            },
            {
                "email": "ben.patel@silverlinemedia.example",
                "company": "silverline media",
                "contact_role": "finance",
                "job_title": "Finance Director",
                "is_primary": False,
                "notes": "Commercial approver.",
            },
            {
                "email": "mia.torres@atlasunit.example",
                "company": "atlas unit",
                "contact_role": "producer",
                "job_title": "Producer",
                "is_primary": False,
                "notes": "Coordinates deliveries.",
            },
            {
                "email": "oscar.bennett@publicscreen.example",
                "company": "public screen network",
                "contact_role": "commissioning_editor",
                "job_title": "Commissioning Editor",
                "is_primary": False,
                "notes": "Broadcast-side approver.",
            },
        ],
        "disciplines": ["offline", "online", "grade"],
        "schedule_ranges": [
            {
                "discipline": "offline",
                "label": "Editorial",
                "start_date": date(2025, 12, 1),
                "end_date": date(2025, 12, 18),
                "notes": "Offline cut build.",
            },
            {
                "discipline": "online",
                "label": "Online finish",
                "start_date": date(2026, 1, 4),
                "end_date": date(2026, 1, 29),
                "notes": "Conform and master creation.",
            },
            {
                "discipline": "grade",
                "label": "Grade",
                "start_date": date(2026, 2, 2),
                "end_date": date(2026, 2, 13),
                "notes": "Final color finish.",
            },
        ],
        "outcomes": [
            {
                "outcome_type": ProjectOutcomeType.awarded,
                "effective_at": _utc(2025, 11, 14, 14, 0),
                "notes": "Awarded after broadcaster review.",
            }
        ],
        "quote": {
            "quote_number": "NP-PROMO-Q",
            "title": "North Passage Promo Package Quote",
            "versions": [
                {
                    "version_number": 1,
                    "status": QuoteVersionStatus.accepted,
                    "title": "Accepted issue",
                    "issued_at": _utc(2025, 11, 14, 14, 0),
                    "accepted_at": _utc(2025, 11, 15, 10, 0),
                    "source_document_date": date(2025, 11, 14),
                    "source_version_label": "V1",
                    "client_facing_notes": "Accepted promo package issue.",
                    "internal_notes": "Used for completed benchmark data.",
                    "is_current": True,
                    "sections": [
                        {
                            "name": "Core Scope",
                            "line_items": [
                                {
                                    "discipline": "offline",
                                    "description": "Offline edit package",
                                    "amount": 39000,
                                    "quantity": 1,
                                    "unit": "package",
                                },
                                {
                                    "discipline": "online",
                                    "description": "Online finishing package",
                                    "amount": 33000,
                                    "quantity": 1,
                                    "unit": "package",
                                },
                                {
                                    "discipline": "grade",
                                    "description": "Grade and masters",
                                    "amount": 26000,
                                    "quantity": 1,
                                    "unit": "package",
                                },
                            ],
                        }
                    ],
                }
            ],
        },
        "benchmark": {
            "actuals_status": BenchmarkActualsStatus.complete,
            "actuals_as_of_date": date(2026, 3, 31),
            "discipline_actuals": {
                "offline": 41500,
                "online": 35500,
                "grade": 27500,
            },
        },
        "forecast": {
            "title": "Locked completion forecast",
            "notes_text": "Historical locked forecast for completed work.",
            "revision_reason": "Seeded historical baseline.",
            "submit_after": True,
            "lock_after": True,
        },
    },
    {
        "id": "project_silver_tide",
        "code": "ST-TEASER",
        "name": "Silver Tide Teaser Rollout",
        "status": ProjectStatus.complete,
        "description": "Completed teaser rollout with heavy finishing emphasis.",
        "quote_currency_code": "GBP",
        "start_date": date(2025, 12, 15),
        "end_date": date(2026, 3, 5),
        "bid_due_date": date(2025, 12, 10),
        "bid_submitted_at": _utc(2025, 12, 10, 11, 0),
        "awarded_at": _utc(2026, 1, 16, 10, 0),
        "active_at": _utc(2026, 1, 18, 9, 0),
        "completed_at": _utc(2026, 3, 5, 18, 0),
        "metadata": {
            "content_type": "marketing",
            "content_subtype": "teaser_rollout",
            "genre": "fantasy",
            "format_type": "trailer_promo",
            "runtime_minutes": 1,
            "duration_weeks": 11,
            "episode_count": 1,
            "territory": "Global",
            "language": "en-GB",
            "budget_target": 122000,
            "metadata": {
                "projectFormatKey": "trailer_promo",
                "primaryLanguageCode": "en-GB",
                "deliverableKeys": [
                    "teaser_master",
                    "social_versions",
                    "caption_package",
                ],
                "localizationKeys": ["caption_package:en-GB"],
                "complexityProfile": {
                    "finishing": "complex",
                    "audio": "standard",
                    "vfx": "low",
                },
            },
        },
        "parties": [
            ("client", "north star pictures", True, "Primary client account."),
            (
                "production_company",
                "harborlight productions",
                True,
                "Production company turnover lead.",
            ),
            ("streamer", "netstream", True, "Streaming destination."),
        ],
        "contacts": [
            {
                "email": "maya.grant@northstarpictures.example",
                "company": "north star pictures",
                "contact_role": "executive_producer",
                "job_title": "Executive Producer",
                "is_primary": True,
                "notes": "Primary client lead.",
            },
            {
                "email": "oliver.chen@northstarpictures.example",
                "company": "north star pictures",
                "contact_role": "post_supervisor",
                "job_title": "Post Supervisor",
                "is_primary": False,
                "notes": "Client-side scheduling contact.",
            },
            {
                "email": "sam.okoro@harborlightproductions.example",
                "company": "harborlight productions",
                "contact_role": "producer",
                "job_title": "Senior Producer",
                "is_primary": False,
                "notes": "Production-side producer.",
            },
        ],
        "disciplines": ["offline", "online", "grade"],
        "schedule_ranges": [
            {
                "discipline": "offline",
                "label": "Editorial",
                "start_date": date(2026, 1, 4),
                "end_date": date(2026, 1, 29),
                "notes": "Teaser editorial cut.",
            },
            {
                "discipline": "online",
                "label": "Online finish",
                "start_date": date(2026, 2, 2),
                "end_date": date(2026, 2, 20),
                "notes": "Mastering and social cutdowns.",
            },
            {
                "discipline": "grade",
                "label": "Grade",
                "start_date": date(2026, 2, 23),
                "end_date": date(2026, 3, 5),
                "notes": "Final grade and QC.",
            },
        ],
        "outcomes": [
            {
                "outcome_type": ProjectOutcomeType.awarded,
                "effective_at": _utc(2026, 1, 16, 10, 0),
                "notes": "Awarded after scope confirmation.",
            }
        ],
        "quote": {
            "quote_number": "ST-TEASER-Q",
            "title": "Silver Tide Teaser Rollout Quote",
            "versions": [
                {
                    "version_number": 1,
                    "status": QuoteVersionStatus.accepted,
                    "title": "Accepted issue",
                    "issued_at": _utc(2026, 1, 16, 10, 0),
                    "accepted_at": _utc(2026, 1, 17, 11, 0),
                    "source_document_date": date(2026, 1, 16),
                    "source_version_label": "V1",
                    "client_facing_notes": "Accepted teaser rollout scope.",
                    "internal_notes": "Completed project benchmark source.",
                    "is_current": True,
                    "sections": [
                        {
                            "name": "Core Scope",
                            "line_items": [
                                {
                                    "discipline": "offline",
                                    "description": "Offline edit package",
                                    "amount": 45000,
                                    "quantity": 1,
                                    "unit": "package",
                                },
                                {
                                    "discipline": "online",
                                    "description": "Online finishing package",
                                    "amount": 42000,
                                    "quantity": 1,
                                    "unit": "package",
                                },
                                {
                                    "discipline": "grade",
                                    "description": "Grade and masters",
                                    "amount": 35000,
                                    "quantity": 1,
                                    "unit": "package",
                                },
                            ],
                        }
                    ],
                }
            ],
        },
        "benchmark": {
            "actuals_status": BenchmarkActualsStatus.complete,
            "actuals_as_of_date": date(2026, 3, 31),
            "discipline_actuals": {
                "offline": 48500,
                "online": 45500,
                "grade": 38000,
            },
        },
        "forecast": {
            "title": "Locked teaser forecast",
            "notes_text": "Historical locked forecast for comparison.",
            "revision_reason": "Seeded historical baseline.",
            "submit_after": True,
            "lock_after": True,
        },
    },
    {
        "id": "project_blue_echo",
        "code": "BE-SPOT",
        "name": "Blue Echo Spot Burst",
        "status": ProjectStatus.complete,
        "description": "Completed brand launch spots with agency approvals.",
        "quote_currency_code": "GBP",
        "start_date": date(2026, 1, 25),
        "end_date": date(2026, 4, 4),
        "bid_due_date": date(2026, 1, 30),
        "bid_submitted_at": _utc(2026, 1, 30, 13, 0),
        "awarded_at": _utc(2026, 2, 8, 10, 0),
        "active_at": _utc(2026, 2, 10, 9, 0),
        "completed_at": _utc(2026, 4, 4, 18, 0),
        "metadata": {
            "content_type": "marketing",
            "content_subtype": "brand_launch_spots",
            "genre": "factual_entertainment",
            "format_type": "brand_spot_campaign",
            "runtime_minutes": 1,
            "duration_weeks": 9,
            "episode_count": 3,
            "territory": "UK / US",
            "language": "en-GB",
            "budget_target": 116000,
            "metadata": {
                "projectFormatKey": "brand_spot_campaign",
                "primaryLanguageCode": "en-GB",
                "deliverableKeys": [
                    "tv_spots",
                    "social_cutdowns",
                    "graphic_adaptations",
                ],
                "localizationKeys": [],
                "complexityProfile": {
                    "finishing": "complex",
                    "audio": "standard",
                    "vfx": "low",
                },
            },
        },
        "parties": [
            ("client", "aurora creative", True, "Primary agency client."),
            (
                "production_company",
                "atlas unit",
                True,
                "Production partner coordinating brand assets.",
            ),
            ("studio", "apex studios", True, "Studio stakeholder for release."),
        ],
        "contacts": [
            {
                "email": "nina.clarke@auroracreative.example",
                "company": "aurora creative",
                "contact_role": "creative_director",
                "job_title": "Creative Director",
                "is_primary": True,
                "notes": "Primary agency approver.",
            },
            {
                "email": "mia.torres@atlasunit.example",
                "company": "atlas unit",
                "contact_role": "producer",
                "job_title": "Producer",
                "is_primary": False,
                "notes": "Production contact for supplied graphics.",
            },
            {
                "email": "ava.monroe@apexstudios.example",
                "company": "apex studios",
                "contact_role": "partner_manager",
                "job_title": "Partner Marketing Director",
                "is_primary": False,
                "notes": "Studio-side approvals.",
            },
        ],
        "disciplines": ["offline", "online", "grade"],
        "schedule_ranges": [
            {
                "discipline": "offline",
                "label": "Editorial",
                "start_date": date(2026, 2, 1),
                "end_date": date(2026, 2, 20),
                "notes": "Cut build and internal reviews.",
            },
            {
                "discipline": "online",
                "label": "Online finish",
                "start_date": date(2026, 2, 23),
                "end_date": date(2026, 3, 20),
                "notes": "Finishing and resize outputs.",
            },
            {
                "discipline": "grade",
                "label": "Grade and output",
                "start_date": date(2026, 3, 23),
                "end_date": date(2026, 4, 4),
                "notes": "Grade and final exports.",
            },
        ],
        "outcomes": [
            {
                "outcome_type": ProjectOutcomeType.awarded,
                "effective_at": _utc(2026, 2, 8, 10, 0),
                "notes": "Awarded after final creative review.",
            }
        ],
        "quote": {
            "quote_number": "BE-SPOT-Q",
            "title": "Blue Echo Spot Burst Quote",
            "versions": [
                {
                    "version_number": 1,
                    "status": QuoteVersionStatus.accepted,
                    "title": "Accepted issue",
                    "issued_at": _utc(2026, 2, 8, 10, 0),
                    "accepted_at": _utc(2026, 2, 9, 11, 0),
                    "source_document_date": date(2026, 2, 8),
                    "source_version_label": "V1",
                    "client_facing_notes": "Accepted launch spot package issue.",
                    "internal_notes": "Completed campaign benchmark source.",
                    "is_current": True,
                    "sections": [
                        {
                            "name": "Core Scope",
                            "line_items": [
                                {
                                    "discipline": "offline",
                                    "description": "Offline cutdown suite",
                                    "amount": 43000,
                                    "quantity": 1,
                                    "unit": "package",
                                },
                                {
                                    "discipline": "online",
                                    "description": "Online versioning",
                                    "amount": 40000,
                                    "quantity": 1,
                                    "unit": "package",
                                },
                                {
                                    "discipline": "grade",
                                    "description": "Grade and outputs",
                                    "amount": 33000,
                                    "quantity": 1,
                                    "unit": "package",
                                },
                            ],
                        }
                    ],
                }
            ],
        },
        "benchmark": {
            "actuals_status": BenchmarkActualsStatus.complete,
            "actuals_as_of_date": date(2026, 3, 31),
            "discipline_actuals": {
                "offline": 48000,
                "online": 44500,
                "grade": 36000,
            },
        },
        "forecast": {
            "title": "Locked brand campaign forecast",
            "notes_text": "Historical locked forecast for benchmark coverage.",
            "revision_reason": "Seeded historical baseline.",
            "submit_after": True,
            "lock_after": True,
        },
    },
    {
        "id": "project_global_cut",
        "code": "GC-INTL",
        "name": "Global Cut International Promo",
        "status": ProjectStatus.active,
        "description": "Active international promo package with localization work in progress.",
        "quote_currency_code": "GBP",
        "start_date": date(2026, 3, 10),
        "end_date": date(2026, 6, 26),
        "bid_due_date": date(2026, 2, 20),
        "bid_submitted_at": _utc(2026, 2, 22, 10, 0),
        "awarded_at": _utc(2026, 3, 5, 10, 0),
        "active_at": _utc(2026, 3, 10, 9, 0),
        "metadata": {
            "content_type": "post",
            "content_subtype": "localization_rollout",
            "genre": "feature_film",
            "format_type": "feature_film_localization",
            "runtime_minutes": 120,
            "duration_weeks": 16,
            "episode_count": 1,
            "territory": "Global",
            "language": "en-US",
            "budget_target": 130000,
            "metadata": {
                "projectFormatKey": "feature_film_localization",
                "primaryLanguageCode": "en-US",
                "deliverableKeys": [
                    "international_master",
                    "subtitle_package",
                    "localized_audio_elements",
                ],
                "localizationKeys": [
                    "subtitle_package:fr-FR",
                    "subtitle_package:de-DE",
                    "subtitle_package:es-ES",
                ],
                "complexityProfile": {
                    "finishing": "standard",
                    "audio": "standard",
                    "vfx": "low",
                },
            },
        },
        "parties": [
            ("client", "global media", True, "Primary broadcaster client."),
            (
                "broadcaster",
                "public screen network",
                True,
                "Linear destination and review stakeholder.",
            ),
            ("studio", "apex studios", True, "Studio rights holder."),
        ],
        "contacts": [
            {
                "email": "harriet.lowe@globalmedia.example",
                "company": "global media",
                "contact_role": "head_of_post",
                "job_title": "Head of Post",
                "is_primary": True,
                "notes": "Primary delivery stakeholder.",
            },
            {
                "email": "oscar.bennett@publicscreen.example",
                "company": "public screen network",
                "contact_role": "commissioning_editor",
                "job_title": "Commissioning Editor",
                "is_primary": False,
                "notes": "Broadcast approval contact.",
            },
            {
                "email": "ava.monroe@apexstudios.example",
                "company": "apex studios",
                "contact_role": "partner_manager",
                "job_title": "Partner Marketing Director",
                "is_primary": False,
                "notes": "Studio-side localization approvals.",
            },
            {
                "email": "lena.fischer@linguahub.example",
                "company": "linguahub",
                "contact_role": "account_director",
                "job_title": "Account Director",
                "is_primary": False,
                "notes": "Localization vendor contact.",
            },
        ],
        "disciplines": ["online", "sound", "localization"],
        "schedule_ranges": [
            {
                "discipline": "online",
                "label": "International conform",
                "start_date": date(2026, 3, 10),
                "end_date": date(2026, 4, 24),
                "notes": "International conform and master prep.",
            },
            {
                "discipline": "sound",
                "label": "Audio finishing",
                "start_date": date(2026, 4, 13),
                "end_date": date(2026, 5, 15),
                "notes": "Audio deliverables and language elements.",
            },
            {
                "discipline": "localization",
                "label": "Subtitle and metadata localization",
                "start_date": date(2026, 4, 27),
                "end_date": date(2026, 6, 26),
                "notes": "Subtitle preparation, QC, and territory delivery.",
            },
        ],
        "outcomes": [
            {
                "outcome_type": ProjectOutcomeType.awarded,
                "effective_at": _utc(2026, 3, 5, 10, 0),
                "notes": "Awarded after the territory list was finalized.",
            }
        ],
        "quote": {
            "quote_number": "GC-INTL-Q",
            "title": "Global Cut International Promo Quote",
            "versions": [
                {
                    "version_number": 1,
                    "status": QuoteVersionStatus.superseded,
                    "title": "Initial issue",
                    "issued_at": _utc(2026, 2, 22, 10, 0),
                    "source_document_date": date(2026, 2, 22),
                    "source_version_label": "V1",
                    "client_facing_notes": "Initial international promo estimate.",
                    "internal_notes": "Superseded after localization scope increased.",
                    "sections": [
                        {
                            "name": "Core Scope",
                            "line_items": [
                                {
                                    "discipline": "online",
                                    "description": "Online international finish",
                                    "amount": 47000,
                                    "quantity": 1,
                                    "unit": "package",
                                },
                                {
                                    "discipline": "sound",
                                    "description": "Sound mix and deliverables",
                                    "amount": 33000,
                                    "quantity": 1,
                                    "unit": "package",
                                },
                                {
                                    "discipline": "localization",
                                    "description": "Localization package",
                                    "amount": 44000,
                                    "quantity": 1,
                                    "unit": "package",
                                },
                            ],
                        }
                    ],
                },
                {
                    "version_number": 2,
                    "status": QuoteVersionStatus.accepted,
                    "title": "Accepted issue",
                    "issued_at": _utc(2026, 3, 3, 11, 0),
                    "accepted_at": _utc(2026, 3, 5, 15, 0),
                    "source_document_date": date(2026, 3, 3),
                    "source_version_label": "V2",
                    "client_facing_notes": (
                        "Accepted issue covering expanded subtitle territories."
                    ),
                    "internal_notes": "Current operational quote for forecast and variance demos.",
                    "is_current": True,
                    "sections": [
                        {
                            "name": "Core Scope",
                            "line_items": [
                                {
                                    "discipline": "online",
                                    "description": "Online international finish",
                                    "amount": 50000,
                                    "quantity": 1,
                                    "unit": "package",
                                },
                                {
                                    "discipline": "sound",
                                    "description": "Sound mix and deliverables",
                                    "amount": 35000,
                                    "quantity": 1,
                                    "unit": "package",
                                },
                                {
                                    "discipline": "localization",
                                    "description": "Localization package",
                                    "amount": 45000,
                                    "quantity": 1,
                                    "unit": "package",
                                },
                            ],
                        }
                    ],
                },
            ],
        },
        "benchmark": {
            "actuals_status": BenchmarkActualsStatus.partial,
            "actuals_as_of_date": date(2026, 3, 31),
            "discipline_actuals": {
                "online": 23000,
                "sound": 17000,
                "localization": 14000,
            },
        },
        "forecast": {
            "title": "Current active forecast",
            "notes_text": "Active locked forecast tied to the accepted quote.",
            "revision_reason": "Seeded active baseline.",
            "manual_overrides": [
                {
                    "line_label_contains": "Localization package",
                    "reason": "Localized deliveries were manually weighted into May and June.",
                    "allocations": [("2026-05", 20000), ("2026-06", 25000)],
                }
            ],
            "submit_after": True,
            "lock_after": True,
        },
    },
    {
        "id": "project_amber_lane",
        "code": "AL-SPOTS",
        "name": "Amber Lane Launch Spots",
        "status": ProjectStatus.awarded,
        "description": "Awarded launch spot package pending production kick-off.",
        "quote_currency_code": "USD",
        "start_date": date(2026, 4, 14),
        "end_date": date(2026, 6, 18),
        "bid_due_date": date(2026, 3, 6),
        "bid_submitted_at": _utc(2026, 3, 7, 12, 0),
        "awarded_at": _utc(2026, 3, 18, 10, 0),
        "metadata": {
            "content_type": "marketing",
            "content_subtype": "launch_spots",
            "genre": "drama",
            "format_type": "brand_spot_campaign",
            "runtime_minutes": 1,
            "duration_weeks": 10,
            "episode_count": 3,
            "territory": "US",
            "language": "en-US",
            "budget_target": 92000,
            "metadata": {
                "projectFormatKey": "brand_spot_campaign",
                "primaryLanguageCode": "en-US",
                "deliverableKeys": ["tv_spots", "social_cutdowns", "graphics_package"],
                "localizationKeys": [],
                "complexityProfile": {
                    "finishing": "standard",
                    "audio": "standard",
                    "vfx": "medium",
                },
            },
        },
        "parties": [
            ("client", "studio east", True, "Primary studio client."),
            ("production_company", "atlas unit", True, "Production partner."),
            ("studio", "apex studios", True, "Rights holder and release partner."),
        ],
        "contacts": [
            {
                "email": "daniel.kerr@studioeast.example",
                "company": "studio east",
                "contact_role": "executive_producer",
                "job_title": "Executive Producer",
                "is_primary": True,
                "notes": "Primary client lead.",
            },
            {
                "email": "mia.torres@atlasunit.example",
                "company": "atlas unit",
                "contact_role": "producer",
                "job_title": "Producer",
                "is_primary": False,
                "notes": "Production partner contact.",
            },
            {
                "email": "ava.monroe@apexstudios.example",
                "company": "apex studios",
                "contact_role": "partner_manager",
                "job_title": "Partner Marketing Director",
                "is_primary": False,
                "notes": "Studio-side approver.",
            },
        ],
        "disciplines": ["offline", "online", "gfx"],
        "schedule_ranges": [
            {
                "discipline": "offline",
                "label": "Editorial",
                "start_date": date(2026, 4, 14),
                "end_date": date(2026, 5, 1),
                "notes": "Initial cut build.",
            },
            {
                "discipline": "online",
                "label": "Online adaptation",
                "start_date": date(2026, 5, 4),
                "end_date": date(2026, 5, 29),
                "notes": "Finishing and resize outputs.",
            },
            {
                "discipline": "gfx",
                "label": "GFX toolkit",
                "start_date": date(2026, 5, 18),
                "end_date": date(2026, 6, 18),
                "notes": "Graphics package and cutdown adapts.",
            },
        ],
        "outcomes": [
            {
                "outcome_type": ProjectOutcomeType.awarded,
                "effective_at": _utc(2026, 3, 18, 10, 0),
                "notes": "Awarded pending production start.",
            }
        ],
        "quote": {
            "quote_number": "AL-SPOTS-Q",
            "title": "Amber Lane Launch Spots Quote",
            "versions": [
                {
                    "version_number": 1,
                    "status": QuoteVersionStatus.accepted,
                    "title": "Accepted issue",
                    "issued_at": _utc(2026, 3, 18, 10, 0),
                    "accepted_at": _utc(2026, 3, 19, 9, 30),
                    "source_document_date": date(2026, 3, 18),
                    "source_version_label": "V1",
                    "client_facing_notes": "Accepted launch spot package scope.",
                    "internal_notes": "Awarded but not yet started.",
                    "is_current": True,
                    "sections": [
                        {
                            "name": "Core Scope",
                            "line_items": [
                                {
                                    "discipline": "offline",
                                    "description": "Offline campaign edit",
                                    "amount": 28000,
                                    "quantity": 1,
                                    "unit": "package",
                                },
                                {
                                    "discipline": "online",
                                    "description": "Online adaptation passes",
                                    "amount": 32000,
                                    "quantity": 1,
                                    "unit": "package",
                                },
                                {
                                    "discipline": "gfx",
                                    "description": "GFX toolkit and resize package",
                                    "amount": 32000,
                                    "quantity": 1,
                                    "unit": "package",
                                },
                            ],
                        }
                    ],
                }
            ],
        },
        "forecast": {
            "title": "Submitted awarded forecast",
            "notes_text": "Submitted awarded forecast pending project start.",
            "revision_reason": "Initial awarded baseline.",
            "submit_after": True,
        },
    },
    {
        "id": "project_ember_fade",
        "code": "EF-PITCH",
        "name": "Ember Fade Pitch Package",
        "status": ProjectStatus.lost,
        "description": "Lost pitch package used to demo loss tracking and outcome history.",
        "quote_currency_code": "GBP",
        "start_date": date(2026, 3, 1),
        "end_date": date(2026, 5, 15),
        "bid_due_date": date(2026, 3, 12),
        "bid_submitted_at": _utc(2026, 3, 15, 12, 0),
        "lost_at": _utc(2026, 3, 22, 16, 0),
        "metadata": {
            "content_type": "development",
            "content_subtype": "pitch_package",
            "genre": "documentary",
            "format_type": "pitch_package",
            "runtime_minutes": 5,
            "duration_weeks": 8,
            "episode_count": 1,
            "territory": "UK",
            "language": "en-GB",
            "budget_target": 76000,
            "metadata": {
                "projectFormatKey": "pitch_package",
                "primaryLanguageCode": "en-GB",
                "deliverableKeys": ["pitch_reel", "deck_video", "audio_polish"],
                "localizationKeys": [],
                "complexityProfile": {
                    "finishing": "standard",
                    "audio": "standard",
                    "vfx": "low",
                },
            },
        },
        "parties": [
            ("client", "north star pictures", True, "Primary client account."),
            ("production_company", "harborlight productions", True, "Pitch partner."),
        ],
        "contacts": [
            {
                "email": "maya.grant@northstarpictures.example",
                "company": "north star pictures",
                "contact_role": "executive_producer",
                "job_title": "Executive Producer",
                "is_primary": True,
                "notes": "Primary client lead.",
            },
            {
                "email": "sam.okoro@harborlightproductions.example",
                "company": "harborlight productions",
                "contact_role": "producer",
                "job_title": "Senior Producer",
                "is_primary": False,
                "notes": "Production-side partner.",
            },
        ],
        "disciplines": ["offline", "production", "sound"],
        "schedule_ranges": [
            {
                "discipline": "offline",
                "label": "Pitch reel edit",
                "start_date": date(2026, 3, 1),
                "end_date": date(2026, 3, 20),
                "notes": "Initial reel assembly.",
            },
            {
                "discipline": "production",
                "label": "Deck build",
                "start_date": date(2026, 3, 9),
                "end_date": date(2026, 4, 10),
                "notes": "Pitch deck and references.",
            },
            {
                "discipline": "sound",
                "label": "Audio polish",
                "start_date": date(2026, 4, 6),
                "end_date": date(2026, 4, 17),
                "notes": "Mix and final polish.",
            },
        ],
        "outcomes": [
            {
                "outcome_type": ProjectOutcomeType.bid,
                "effective_at": _utc(2026, 3, 15, 12, 0),
                "notes": "Pitch package submitted.",
            },
            {
                "outcome_type": ProjectOutcomeType.lost,
                "effective_at": _utc(2026, 3, 22, 16, 0),
                "competitor_company": "pixel forge post",
                "loss_reason": "price",
                "notes": "Lost on commercial positioning after final round.",
            },
        ],
        "quote": {
            "quote_number": "EF-PITCH-Q",
            "title": "Ember Fade Pitch Package Quote",
            "versions": [
                {
                    "version_number": 1,
                    "status": QuoteVersionStatus.rejected,
                    "title": "Rejected issue",
                    "issued_at": _utc(2026, 3, 15, 12, 0),
                    "rejected_at": _utc(2026, 3, 22, 16, 0),
                    "source_document_date": date(2026, 3, 15),
                    "source_version_label": "V1",
                    "client_facing_notes": "Pitch package proposal for review.",
                    "internal_notes": "Rejected after final commercial round.",
                    "is_current": True,
                    "sections": [
                        {
                            "name": "Core Scope",
                            "line_items": [
                                {
                                    "discipline": "offline",
                                    "description": "Offline pitch assembly",
                                    "amount": 28000,
                                    "quantity": 1,
                                    "unit": "package",
                                },
                                {
                                    "discipline": "sound",
                                    "description": "Sound polish",
                                    "amount": 24000,
                                    "quantity": 1,
                                    "unit": "package",
                                },
                                {
                                    "discipline": "production",
                                    "description": "Production deck build",
                                    "amount": 24000,
                                    "quantity": 1,
                                    "unit": "package",
                                },
                            ],
                        }
                    ],
                }
            ],
        },
    },
]

ACTUALS_IMPORT_BATCH_SEEDS = [
    {
        "project_id": "project_black_glass",
        "storage_key": "actuals/2025-11/black-glass-snapshot.csv",
        "file_name": "black-glass-november-snapshot.csv",
        "coverage_mode": CetaImportCoverageMode.snapshot,
        "source_export_id": "BGS-LAUNCH-NOV",
        "source_exported_at": _utc(2025, 11, 15, 7, 30),
        "coverage_start": date(2025, 10, 1),
        "coverage_end": date(2025, 11, 30),
        "parser_profile_hint": "generic-ledger",
        "notes": "Approved snapshot import used to seed mapped actuals and workflow history.",
        "uploaded_at": _utc(2025, 11, 15, 7, 35),
        "worker_result": {
            "job_id": "job_seed_black_glass",
            "status": "in_review",
            "parser_name": "seed-parser",
            "parser_version": "2026.03.31",
            "parser_profile": "generic-ledger",
            "source_system": "ceta",
            "coverage_start": date(2025, 10, 1),
            "coverage_end": date(2025, 11, 30),
            "rows": [
                {
                    "row_number": 1,
                    "source_row_uid": "bg-row-1",
                    "row_hash": "bg-row-hash-1",
                    "business_key_hash": "bg-actual-online-1",
                    "external_project_code": "BGS-LAUNCH-FINAL",
                    "normalized_project_code": "bgs-launch-final",
                    "work_date": date(2025, 10, 21),
                    "posting_date": date(2025, 10, 21),
                    "source_discipline_code": "online",
                    "description": "Conform suite",
                    "normalized_description": "conform suite",
                    "vendor_name": "Halo Post",
                    "normalized_vendor_name": "halo post",
                    "amount": 41000,
                    "currency_code": "GBP",
                    "financial_type": CetaRowFinancialType.cost,
                    "raw_payload": {"department": "online"},
                    "issues": [],
                },
                {
                    "row_number": 2,
                    "source_row_uid": "bg-row-2",
                    "row_hash": "bg-row-hash-2",
                    "business_key_hash": "bg-actual-offline-1",
                    "external_project_code": "BGS-LAUNCH-FINAL",
                    "normalized_project_code": "bgs-launch-final",
                    "work_date": date(2025, 10, 17),
                    "posting_date": date(2025, 10, 17),
                    "source_discipline_code": "offline",
                    "description": "Launch edit package",
                    "normalized_description": "launch edit package",
                    "vendor_name": "Harborlight Productions",
                    "normalized_vendor_name": "harborlight productions",
                    "amount": 45000,
                    "currency_code": "GBP",
                    "financial_type": CetaRowFinancialType.cost,
                    "raw_payload": {"department": "offline"},
                    "issues": [],
                },
                {
                    "row_number": 3,
                    "source_row_uid": "bg-row-3",
                    "row_hash": "bg-row-hash-3",
                    "business_key_hash": "bg-actual-grade-1",
                    "external_project_code": "BGS-LAUNCH-FINAL",
                    "normalized_project_code": "bgs-launch-final",
                    "work_date": date(2025, 11, 7),
                    "posting_date": date(2025, 11, 7),
                    "source_discipline_code": "grade",
                    "description": "DI theatre and masters",
                    "normalized_description": "di theatre and masters",
                    "vendor_name": "Prism Colour",
                    "normalized_vendor_name": "prism colour",
                    "amount": 32000,
                    "currency_code": "GBP",
                    "financial_type": CetaRowFinancialType.cost,
                    "raw_payload": {"department": "grade"},
                    "issues": [],
                },
            ],
        },
        "decisions": [
            {
                "row_number": 1,
                "mapped_discipline": "online",
                "financial_type": CetaRowFinancialType.cost,
                "cost_category_key": "finishing_labor",
                "approval_action": ActualMappingApprovalAction.post_new,
                "reviewer_note": "Approved as finishing labor.",
                "save_project_external_reference": True,
                "save_rule": True,
                "rule_name": "Black Glass conform mapping",
            },
            {
                "row_number": 2,
                "mapped_discipline": "offline",
                "financial_type": CetaRowFinancialType.cost,
                "cost_category_key": "editorial_labor",
                "approval_action": ActualMappingApprovalAction.post_new,
                "reviewer_note": "Approved as editorial labor.",
            },
            {
                "row_number": 3,
                "mapped_discipline": "grade",
                "financial_type": CetaRowFinancialType.cost,
                "cost_category_key": "finishing_labor",
                "approval_action": ActualMappingApprovalAction.post_new,
                "reviewer_note": "Approved as finishing labor.",
            },
        ],
        "approve": {"withdraw_actual_ids": []},
    },
    {
        "project_id": "project_global_cut",
        "storage_key": "actuals/2026-03/global-cut-incremental.csv",
        "file_name": "global-cut-march-incremental.csv",
        "coverage_mode": CetaImportCoverageMode.incremental,
        "source_export_id": "GC-INTL-MAR",
        "source_exported_at": _utc(2026, 3, 31, 6, 30),
        "coverage_start": date(2026, 3, 1),
        "coverage_end": date(2026, 3, 31),
        "parser_profile_hint": "generic-ledger",
        "notes": "Approved incremental import showing partial actual coverage on an active job.",
        "uploaded_at": _utc(2026, 3, 31, 6, 35),
        "worker_result": {
            "job_id": "job_seed_global_cut",
            "status": "in_review",
            "parser_name": "seed-parser",
            "parser_version": "2026.03.31",
            "parser_profile": "generic-ledger",
            "source_system": "ceta",
            "coverage_start": date(2026, 3, 1),
            "coverage_end": date(2026, 3, 31),
            "rows": [
                {
                    "row_number": 1,
                    "source_row_uid": "gc-row-1",
                    "row_hash": "gc-row-hash-1",
                    "business_key_hash": "gc-actual-online-1",
                    "external_project_code": "GC-INTL-LOC",
                    "normalized_project_code": "gc-intl-loc",
                    "work_date": date(2026, 3, 18),
                    "posting_date": date(2026, 3, 18),
                    "source_discipline_code": "online",
                    "description": "International conform",
                    "normalized_description": "international conform",
                    "vendor_name": "Halo Post",
                    "normalized_vendor_name": "halo post",
                    "amount": 23000,
                    "currency_code": "GBP",
                    "financial_type": CetaRowFinancialType.cost,
                    "raw_payload": {"department": "online"},
                    "issues": [],
                },
                {
                    "row_number": 2,
                    "source_row_uid": "gc-row-2",
                    "row_hash": "gc-row-hash-2",
                    "business_key_hash": "gc-actual-sound-1",
                    "external_project_code": "GC-INTL-LOC",
                    "normalized_project_code": "gc-intl-loc",
                    "work_date": date(2026, 3, 24),
                    "posting_date": date(2026, 3, 24),
                    "source_discipline_code": "sound",
                    "description": "Foreign language mix prep",
                    "normalized_description": "foreign language mix prep",
                    "vendor_name": "Waveform Audio",
                    "normalized_vendor_name": "waveform audio",
                    "amount": 17000,
                    "currency_code": "GBP",
                    "financial_type": CetaRowFinancialType.cost,
                    "raw_payload": {"department": "sound"},
                    "issues": [],
                },
                {
                    "row_number": 3,
                    "source_row_uid": "gc-row-3",
                    "row_hash": "gc-row-hash-3",
                    "business_key_hash": "gc-actual-loc-1",
                    "external_project_code": "GC-INTL-LOC",
                    "normalized_project_code": "gc-intl-loc",
                    "work_date": date(2026, 3, 26),
                    "posting_date": date(2026, 3, 26),
                    "source_discipline_code": "localization",
                    "description": "Subtitle prep",
                    "normalized_description": "subtitle prep",
                    "vendor_name": "LinguaHub",
                    "normalized_vendor_name": "linguahub",
                    "amount": 14000,
                    "currency_code": "GBP",
                    "financial_type": CetaRowFinancialType.cost,
                    "raw_payload": {"department": "localization"},
                    "issues": [],
                },
            ],
        },
        "decisions": [
            {
                "row_number": 1,
                "mapped_discipline": "online",
                "financial_type": CetaRowFinancialType.cost,
                "cost_category_key": "finishing_labor",
                "approval_action": ActualMappingApprovalAction.post_new,
                "reviewer_note": "Approved as online finishing labor.",
                "save_project_external_reference": True,
            },
            {
                "row_number": 2,
                "mapped_discipline": "sound",
                "financial_type": CetaRowFinancialType.cost,
                "cost_category_key": "audio_labor",
                "approval_action": ActualMappingApprovalAction.post_new,
                "reviewer_note": "Approved as audio labor.",
            },
            {
                "row_number": 3,
                "mapped_discipline": "localization",
                "financial_type": CetaRowFinancialType.cost,
                "cost_category_key": "third_party_vendor",
                "approval_action": ActualMappingApprovalAction.post_new,
                "reviewer_note": "Approved as localization vendor cost.",
            },
        ],
        "approve": {"withdraw_actual_ids": []},
    },
    {
        "project_id": "project_red_room",
        "storage_key": "actuals/2026-04/red-room-review.csv",
        "file_name": "red-room-april-review.csv",
        "coverage_mode": CetaImportCoverageMode.snapshot,
        "source_export_id": "RR-TRAILER-APR",
        "source_exported_at": _utc(2026, 4, 29, 7, 15),
        "coverage_start": date(2026, 4, 1),
        "coverage_end": date(2026, 4, 30),
        "parser_profile_hint": "generic-ledger",
        "notes": "In-review batch used to demo staged reconciliation and decision queues.",
        "uploaded_at": _utc(2026, 4, 29, 7, 20),
        "worker_result": {
            "job_id": "job_seed_red_room",
            "status": "in_review",
            "parser_name": "seed-parser",
            "parser_version": "2026.03.31",
            "parser_profile": "generic-ledger",
            "source_system": "ceta",
            "coverage_start": date(2026, 4, 1),
            "coverage_end": date(2026, 4, 30),
            "batch_issues": [
                {
                    "severity": CetaImportIssueSeverity.warning,
                    "issue_code": "mixed_vendor_naming",
                    "field_name": "vendor_name",
                    "message": "One or more vendors used inconsistent naming in the export.",
                    "details": {"source": "seed"},
                }
            ],
            "rows": [
                {
                    "row_number": 1,
                    "source_row_uid": "rr-row-1",
                    "row_hash": "rr-row-hash-1",
                    "business_key_hash": "rr-actual-online-1",
                    "external_project_code": "RR-TRAILER-APR",
                    "normalized_project_code": "rr-trailer-apr",
                    "work_date": date(2026, 4, 21),
                    "posting_date": date(2026, 4, 21),
                    "source_discipline_code": "online",
                    "description": "Conform suite",
                    "normalized_description": "conform suite",
                    "vendor_name": "Halo Post",
                    "normalized_vendor_name": "halo post",
                    "amount": 9500,
                    "currency_code": "GBP",
                    "financial_type": CetaRowFinancialType.cost,
                    "raw_payload": {"department": "online"},
                    "issues": [],
                },
                {
                    "row_number": 2,
                    "source_row_uid": "rr-row-2",
                    "row_hash": "rr-row-hash-2",
                    "business_key_hash": "rr-actual-sound-1",
                    "external_project_code": "RR-TRAILER-APR",
                    "normalized_project_code": "rr-trailer-apr",
                    "work_date": date(2026, 4, 23),
                    "posting_date": date(2026, 4, 23),
                    "source_discipline_code": "sound",
                    "description": "Temp music pull",
                    "normalized_description": "temp music pull",
                    "vendor_name": "Music Vault",
                    "normalized_vendor_name": "music vault",
                    "amount": 4200,
                    "currency_code": "GBP",
                    "financial_type": CetaRowFinancialType.cost,
                    "raw_payload": {"department": "sound"},
                    "issues": [],
                },
                {
                    "row_number": 3,
                    "source_row_uid": "rr-row-3",
                    "row_hash": "rr-row-hash-3",
                    "business_key_hash": "rr-revenue-session-1",
                    "external_project_code": "RR-TRAILER-APR",
                    "normalized_project_code": "rr-trailer-apr",
                    "work_date": date(2026, 4, 24),
                    "posting_date": date(2026, 4, 24),
                    "source_discipline_code": "offline",
                    "description": "Client review session",
                    "normalized_description": "client review session",
                    "vendor_name": "North Star Pictures",
                    "normalized_vendor_name": "north star pictures",
                    "amount": 7500,
                    "currency_code": "GBP",
                    "financial_type": CetaRowFinancialType.revenue,
                    "raw_payload": {"department": "revenue"},
                    "issues": [],
                },
                {
                    "row_number": 4,
                    "source_row_uid": "rr-row-4",
                    "row_hash": "rr-row-hash-4",
                    "business_key_hash": "rr-caption-check-1",
                    "external_project_code": "RR-TRAILER-APR",
                    "normalized_project_code": "rr-trailer-apr",
                    "work_date": None,
                    "posting_date": date(2026, 4, 28),
                    "source_discipline_code": "sound",
                    "description": "Caption check",
                    "normalized_description": "caption check",
                    "vendor_name": "Waveform Audio",
                    "normalized_vendor_name": "waveform audio",
                    "amount": 1800,
                    "currency_code": "GBP",
                    "financial_type": CetaRowFinancialType.cost,
                    "raw_payload": {"department": "sound"},
                    "issues": [
                        {
                            "severity": CetaImportIssueSeverity.blocking,
                            "issue_code": "missing_work_date",
                            "field_name": "work_date",
                            "message": (
                                "Work date is missing and must be confirmed before approval."
                            ),
                            "details": {"source": "seed"},
                        }
                    ],
                },
            ],
        },
    },
    {
        "project_id": "project_amber_lane",
        "storage_key": "actuals/2026-04/amber-lane-uploaded.csv",
        "file_name": "amber-lane-april-uploaded.csv",
        "coverage_mode": CetaImportCoverageMode.snapshot,
        "source_export_id": "AL-SPOTS-APR",
        "source_exported_at": _utc(2026, 4, 30, 8, 0),
        "coverage_start": date(2026, 4, 1),
        "coverage_end": date(2026, 4, 30),
        "parser_profile_hint": "generic-ledger",
        "notes": "Uploaded-only batch to show pre-parse queue state.",
        "uploaded_at": _utc(2026, 4, 30, 8, 5),
    },
]


def _get_or_create_role(session: Session, key: str, label: str, description: str) -> Role:
    role = session.scalar(select(Role).where(Role.key == key))
    if role is None:
        role = Role(key=key, label=label, description=description)
        session.add(role)
        session.flush()
    else:
        role.label = label
        role.description = description
    return role


def _get_or_create_permission(
    session: Session, key: str, label: str, description: str
) -> Permission:
    permission = session.scalar(select(Permission).where(Permission.key == key))
    if permission is None:
        permission = Permission(key=key, label=label, description=description)
        session.add(permission)
        session.flush()
    else:
        permission.label = label
        permission.description = description
    return permission


def _seed_roles_and_permissions(session: Session) -> dict[str, Role]:
    permissions: dict[str, Permission] = {}
    for key, definition in PERMISSION_DEFINITIONS.items():
        permissions[key] = _get_or_create_permission(
            session,
            key,
            str(definition["label"]),
            str(definition["description"]),
        )

    roles: dict[str, Role] = {}
    for key, definition in ROLE_DEFINITIONS.items():
        role = _get_or_create_role(
            session,
            key,
            str(definition["label"]),
            str(definition["description"]),
        )
        roles[key] = role
        permission_keys = {str(value) for value in definition["permissions"]}
        existing_links = {
            link.permission.key: link
            for link in session.scalars(
                select(RolePermission)
                .join(Permission, Permission.id == RolePermission.permission_id)
                .where(RolePermission.role_id == role.id)
            )
        }
        for permission_key in permission_keys - existing_links.keys():
            session.add(
                RolePermission(role_id=role.id, permission_id=permissions[permission_key].id)
            )
        for permission_key, link in existing_links.items():
            if permission_key not in permission_keys:
                session.delete(link)

    session.flush()
    return roles


def _seed_contact_roles(session: Session) -> None:
    for key, label, description in CONTACT_ROLE_SEEDS:
        contact_role = session.scalar(select(ContactRole).where(ContactRole.key == key))
        if contact_role is None:
            session.add(
                ContactRole(
                    key=key,
                    label=label,
                    description=description,
                    is_active=True,
                )
            )
        else:
            contact_role.label = label
            contact_role.description = description
            contact_role.is_active = True


def _seed_disciplines(session: Session) -> None:
    for code, name, sort_order in DISCIPLINE_SEEDS:
        discipline = session.scalar(select(Discipline).where(Discipline.code == code))
        if discipline is None:
            session.add(Discipline(code=code, name=name, sort_order=sort_order, is_active=True))
        else:
            discipline.name = name
            discipline.sort_order = sort_order
            discipline.is_active = True


def _seed_loss_reasons(session: Session) -> None:
    for code, label, description, category in LOSS_REASON_SEEDS:
        loss_reason = session.scalar(select(LossReason).where(LossReason.code == code))
        if loss_reason is None:
            session.add(
                LossReason(
                    code=code,
                    label=label,
                    description=description,
                    category=category,
                    is_active=True,
                )
            )
        else:
            loss_reason.label = label
            loss_reason.description = description
            loss_reason.category = category
            loss_reason.is_active = True


def _seed_reference_data(session: Session) -> None:
    for category, values in REFERENCE_DATA_SEEDS.items():
        for value in values:
            if isinstance(value, dict):
                key = str(value["key"])
                label = str(value["label"])
                sort_order = int(value["sort_order"])
                metadata = value.get("metadata")
            else:
                key, label, sort_order = value
                metadata = None
            reference = session.scalar(
                select(ReferenceDataValue).where(
                    ReferenceDataValue.category == category,
                    ReferenceDataValue.key == key,
                )
            )
            if reference is None:
                session.add(
                    ReferenceDataValue(
                        category=category,
                        key=key,
                        label=label,
                        sort_order=sort_order,
                        is_active=True,
                        metadata_json=metadata if isinstance(metadata, dict) else None,
                    )
                )
            else:
                reference.label = label
                reference.sort_order = sort_order
                reference.is_active = True
                reference.metadata_json = metadata if isinstance(metadata, dict) else None


def _seed_companies(session: Session) -> None:
    for spec in COMPANY_SEEDS:
        company = session.scalar(
            select(Company).where(Company.normalized_name == spec["normalized_name"])
        )
        if company is None:
            company = Company(
                name=spec["name"],
                legal_name=spec["legal_name"],
                normalized_name=spec["normalized_name"],
                website_url=spec["website_url"],
                default_currency_code=spec["currency_code"],
                notes=spec["notes"],
                is_active=True,
            )
            session.add(company)
            session.flush()
        else:
            company.name = spec["name"]
            company.legal_name = spec["legal_name"]
            company.website_url = spec["website_url"]
            company.default_currency_code = spec["currency_code"]
            company.notes = spec["notes"]
            company.is_active = True

        existing = {
            item.classification
            for item in session.scalars(
                select(CompanyClassification).where(CompanyClassification.company_id == company.id)
            )
        }
        for classification in spec["classifications"]:
            if classification not in existing:
                session.add(
                    CompanyClassification(
                        company_id=company.id,
                        classification=classification,
                        created_at=date.today(),
                    )
                )
    session.flush()


def _seed_contacts(session: Session) -> None:
    for spec in CONTACT_SEEDS:
        normalized_email = normalize_email(spec["email"])
        contact = session.scalar(
            select(Contact).where(Contact.normalized_email == normalized_email)
        )
        if contact is None:
            session.add(
                Contact(
                    first_name=spec["first_name"],
                    last_name=spec["last_name"],
                    full_name=build_full_name(spec["first_name"], spec["last_name"]),
                    email=spec["email"],
                    normalized_email=normalized_email,
                    phone=spec["phone"],
                    mobile=spec["mobile"],
                    notes=spec["notes"],
                    is_active=True,
                )
            )
        else:
            contact.first_name = spec["first_name"]
            contact.last_name = spec["last_name"]
            contact.full_name = build_full_name(spec["first_name"], spec["last_name"])
            contact.email = spec["email"]
            contact.normalized_email = normalized_email
            contact.phone = spec["phone"]
            contact.mobile = spec["mobile"]
            contact.notes = spec["notes"]
            contact.is_active = True
    session.flush()


def _get_company_ids_by_name(session: Session) -> dict[str, str]:
    companies = session.scalars(select(Company)).all()
    return {company.normalized_name: company.id for company in companies}


def _get_contact_ids_by_email(session: Session) -> dict[str, str]:
    contacts = session.scalars(select(Contact)).all()
    result: dict[str, str] = {}
    for contact in contacts:
        if contact.normalized_email:
            result[contact.normalized_email] = contact.id
    return result


def _get_contact_role_ids_by_key(session: Session) -> dict[str, str]:
    roles = session.scalars(select(ContactRole)).all()
    return {role.key: role.id for role in roles}


def _get_discipline_ids_by_code(session: Session) -> dict[str, str]:
    disciplines = session.scalars(select(Discipline)).all()
    return {discipline.code: discipline.id for discipline in disciplines}


def _get_loss_reason_ids_by_code(session: Session) -> dict[str, str]:
    loss_reasons = session.scalars(select(LossReason)).all()
    return {loss_reason.code: loss_reason.id for loss_reason in loss_reasons}


def _seed_company_contacts(session: Session) -> None:
    company_ids = _get_company_ids_by_name(session)
    contact_ids = _get_contact_ids_by_email(session)
    role_ids = _get_contact_role_ids_by_key(session)

    for spec in COMPANY_CONTACT_SEEDS:
        normalized_email = normalize_email(spec["email"])
        existing = session.scalar(
            select(CompanyContact).where(
                CompanyContact.company_id == company_ids[spec["company"]],
                CompanyContact.contact_id == contact_ids[normalized_email],
                CompanyContact.contact_role_id == role_ids[spec["contact_role"]],
            )
        )
        if existing is None:
            session.add(
                CompanyContact(
                    company_id=company_ids[spec["company"]],
                    contact_id=contact_ids[normalized_email],
                    contact_role_id=role_ids[spec["contact_role"]],
                    job_title=spec["job_title"],
                    department=spec["department"],
                    is_primary=bool(spec["is_primary"]),
                    start_date=date(2025, 1, 1),
                )
            )
        else:
            existing.job_title = spec["job_title"]
            existing.department = spec["department"]
            existing.is_primary = bool(spec["is_primary"])
            existing.start_date = date(2025, 1, 1)
            existing.end_date = None
    session.flush()


def _seed_reference_aliases(session: Session, *, actor_id: str) -> None:
    for spec in REFERENCE_ALIAS_SEEDS:
        normalized_alias_text = _normalize_text(spec["alias_text"])
        alias = session.scalar(
            select(ReferenceTermAlias).where(
                ReferenceTermAlias.category == spec["category"],
                ReferenceTermAlias.source_system == spec["source_system"],
                ReferenceTermAlias.source_field_path == spec["source_field_path"],
                ReferenceTermAlias.normalized_alias_text == normalized_alias_text,
            )
        )
        if alias is None:
            session.add(
                ReferenceTermAlias(
                    category=spec["category"],
                    alias_text=spec["alias_text"],
                    normalized_alias_text=normalized_alias_text or spec["alias_text"].lower(),
                    canonical_key=spec["canonical_key"],
                    source_system=spec["source_system"],
                    source_field_path=spec["source_field_path"],
                    confidence_hint=float(spec["confidence_hint"]),
                    is_active=True,
                    created_by_id=actor_id,
                )
            )
        else:
            alias.canonical_key = spec["canonical_key"]
            alias.confidence_hint = float(spec["confidence_hint"])
            alias.is_active = True
    session.flush()


def _seed_admin_user(session: Session, roles: dict[str, Role], *, seed_mode: str) -> User:
    legacy_email = normalize_email("admin@quotes4.local")
    email = normalize_email(os.getenv("DEV_ADMIN_EMAIL", "admin@quotes4.dev"))
    password = os.getenv("DEV_ADMIN_PASSWORD", "quotes4-admin-password")
    first_name = os.getenv(
        "DEV_ADMIN_FIRST_NAME",
        "Demo" if seed_mode == SEED_MODE_DEMO else "System",
    )
    last_name = os.getenv("DEV_ADMIN_LAST_NAME", "Admin")
    display_name = os.getenv("DEV_ADMIN_DISPLAY_NAME", f"{first_name} {last_name}".strip())
    user = session.scalar(select(User).where(User.normalized_email == email))
    if user is None and email != legacy_email:
        user = session.scalar(select(User).where(User.normalized_email == legacy_email))
    password_hash = build_password_hasher().hash_password(password)
    now = datetime.now(UTC)

    if user is None:
        user = User(
            email=email,
            normalized_email=email,
            first_name=first_name,
            last_name=last_name,
            display_name=display_name,
            job_title="System Administrator",
            password_hash=password_hash,
            is_active=True,
            invited_at=now,
            accepted_at=now,
        )
        session.add(user)
        session.flush()
    else:
        user.email = email
        user.normalized_email = email
        user.first_name = first_name
        user.last_name = last_name
        user.password_hash = password_hash
        user.is_active = True
        user.display_name = display_name
        user.job_title = "System Administrator"

    existing_role_ids = {
        assignment.role_id
        for assignment in session.scalars(
            select(UserRoleAssignment).where(UserRoleAssignment.user_id == user.id)
        )
    }
    admin_role = roles["system_admin"]
    if admin_role.id not in existing_role_ids:
        session.add(
            UserRoleAssignment(
                user_id=user.id,
                role_id=admin_role.id,
                assigned_by_id=user.id,
                created_at=now,
            )
        )

    return user


def _quote_version_discipline_totals(version_spec: dict[str, object]) -> dict[str, float]:
    totals: defaultdict[str, float] = defaultdict(float)
    for section_spec in version_spec["sections"]:
        for line_spec in section_spec["line_items"]:
            discipline_code = line_spec.get("discipline")
            if discipline_code is None:
                continue
            totals[str(discipline_code)] += _line_amount(line_spec)
    return {key: round(value, 2) for key, value in totals.items()}


def _seed_quote_sections(
    session: Session,
    quote_version: QuoteVersion,
    section_specs: list[dict[str, object]],
    *,
    discipline_ids: dict[str, str],
) -> None:
    for section_index, section_spec in enumerate(section_specs, start=1):
        section = QuoteSection(
            quote_version_id=quote_version.id,
            name=str(section_spec["name"]),
            sort_order=section_index,
            subtotal_amount=_section_total(section_spec),
        )
        session.add(section)
        session.flush()
        for line_index, line_spec in enumerate(section_spec["line_items"], start=1):
            discipline_code = line_spec.get("discipline")
            session.add(
                QuoteLineItem(
                    quote_section_id=section.id,
                    sort_order=line_index,
                    line_type=QuoteLineItemType(
                        line_spec.get("line_type", QuoteLineItemType.service)
                    ),
                    discipline_id=(
                        discipline_ids[str(discipline_code)]
                        if discipline_code is not None
                        else None
                    ),
                    description=str(line_spec["description"]),
                    quantity=float(line_spec.get("quantity", 1) or 1),
                    unit=str(line_spec.get("unit", "package")),
                    rate=_line_rate(line_spec),
                    amount=_line_amount(line_spec),
                    notes=(
                        str(line_spec["notes"])
                        if line_spec.get("notes") is not None
                        else None
                    ),
                )
            )


def _seed_benchmark_summary(
    session: Session,
    *,
    project_id: str,
    source_quote_version_id: str,
    currency_code: str,
    version_spec: dict[str, object],
    benchmark_spec: dict[str, object],
    discipline_ids: dict[str, str],
) -> None:
    quoted_amount = _version_total(version_spec)
    quoted_by_discipline = _quote_version_discipline_totals(version_spec)
    actual_by_discipline = {
        key: _to_float(float(value))
        for key, value in benchmark_spec["discipline_actuals"].items()
    }
    actual_amount = _to_float(
        float(
            benchmark_spec.get("actual_amount")
            or sum(value for value in actual_by_discipline.values() if value is not None)
        )
    )

    benchmark_summary = ProjectBenchmarkSummary(
        project_id=project_id,
        source_quote_version_id=source_quote_version_id,
        currency_code=currency_code,
        quoted_amount=quoted_amount,
        actual_amount=actual_amount,
        quote_to_actual_variance_amount=_build_variance_amount(quoted_amount, actual_amount),
        quote_to_actual_variance_pct=_build_variance_pct(quoted_amount, actual_amount),
        actuals_status=benchmark_spec["actuals_status"],
        actuals_as_of_date=benchmark_spec["actuals_as_of_date"],
        generated_at=_utc(2026, 3, 31, 12, 0),
    )
    session.add(benchmark_summary)
    session.flush()

    for discipline_code, quoted_value in sorted(quoted_by_discipline.items()):
        actual_value = actual_by_discipline.get(discipline_code)
        session.add(
            ProjectBenchmarkDisciplineSummary(
                benchmark_summary_id=benchmark_summary.id,
                discipline_id=discipline_ids[discipline_code],
                quoted_amount=quoted_value,
                actual_amount=actual_value,
                quote_to_actual_variance_amount=_build_variance_amount(
                    quoted_value,
                    actual_value,
                ),
                quote_to_actual_variance_pct=_build_variance_pct(quoted_value, actual_value),
                actuals_status=benchmark_spec["actuals_status"],
                generated_at=_utc(2026, 3, 31, 12, 0),
            )
        )


def _seed_project(
    session: Session,
    spec: dict[str, object],
    *,
    actor_id: str,
    company_ids: dict[str, str],
    contact_ids: dict[str, str],
    contact_role_ids: dict[str, str],
    discipline_ids: dict[str, str],
    loss_reason_ids: dict[str, str],
) -> None:
    project = Project(
        id=str(spec["id"]),
        code=str(spec["code"]),
        name=str(spec["name"]),
        status=spec["status"],
        description=str(spec["description"]),
        quote_currency_code=str(spec["quote_currency_code"]),
        start_date=spec.get("start_date"),
        end_date=spec.get("end_date"),
        bid_due_date=spec.get("bid_due_date"),
        bid_submitted_at=spec.get("bid_submitted_at"),
        awarded_at=spec.get("awarded_at"),
        lost_at=spec.get("lost_at"),
        active_at=spec.get("active_at"),
        completed_at=spec.get("completed_at"),
        created_by_id=actor_id,
        updated_by_id=actor_id,
    )
    session.add(project)
    session.flush()

    metadata_spec = spec["metadata"]
    session.add(
        ProjectMetadata(
            project_id=project.id,
            content_type=metadata_spec.get("content_type"),
            content_subtype=metadata_spec.get("content_subtype"),
            genre=metadata_spec.get("genre"),
            format_type=metadata_spec.get("format_type"),
            runtime_minutes=metadata_spec.get("runtime_minutes"),
            duration_weeks=metadata_spec.get("duration_weeks"),
            episode_count=metadata_spec.get("episode_count"),
            territory=metadata_spec.get("territory"),
            language=metadata_spec.get("language"),
            budget_target=float(metadata_spec["budget_target"]),
            metadata_json=metadata_spec.get("metadata"),
        )
    )

    for role_key, company_name, is_primary, notes in spec["parties"]:
        session.add(
            ProjectParty(
                project_id=project.id,
                company_id=company_ids[company_name],
                role=ProjectPartyRole(role_key),
                is_primary=bool(is_primary),
                notes=str(notes),
            )
        )

    discipline_created_at = _utc(2026, 1, 1, 9, 0)
    for index, discipline_code in enumerate(spec["disciplines"]):
        session.add(
            ProjectDiscipline(
                project_id=project.id,
                discipline_id=discipline_ids[str(discipline_code)],
                is_primary=index == 0,
                created_at=discipline_created_at,
            )
        )

    for schedule_spec in spec["schedule_ranges"]:
        session.add(
            ProjectScheduleRange(
                project_id=project.id,
                discipline_id=discipline_ids[str(schedule_spec["discipline"])],
                label=str(schedule_spec["label"]),
                start_date=schedule_spec["start_date"],
                end_date=schedule_spec["end_date"],
                allocation_percent=(
                    float(schedule_spec["allocation_percent"])
                    if schedule_spec.get("allocation_percent") is not None
                    else None
                ),
                notes=(
                    str(schedule_spec["notes"])
                    if schedule_spec.get("notes") is not None
                    else None
                ),
            )
        )

    for contact_spec in spec["contacts"]:
        normalized_email = normalize_email(contact_spec["email"])
        session.add(
            ProjectContact(
                project_id=project.id,
                contact_id=contact_ids[normalized_email],
                company_id=company_ids[str(contact_spec["company"])],
                contact_role_id=contact_role_ids[str(contact_spec["contact_role"])],
                job_title=str(contact_spec["job_title"]),
                is_primary=bool(contact_spec["is_primary"]),
                notes=str(contact_spec["notes"]),
            )
        )

    for outcome_spec in spec["outcomes"]:
        session.add(
            ProjectOutcome(
                project_id=project.id,
                outcome_type=outcome_spec["outcome_type"],
                effective_at=outcome_spec["effective_at"],
                competitor_company_id=(
                    company_ids[str(outcome_spec["competitor_company"])]
                    if outcome_spec.get("competitor_company") is not None
                    else None
                ),
                loss_reason_id=(
                    loss_reason_ids[str(outcome_spec["loss_reason"])]
                    if outcome_spec.get("loss_reason") is not None
                    else None
                ),
                notes=(
                    str(outcome_spec["notes"])
                    if outcome_spec.get("notes") is not None
                    else None
                ),
                recorded_by_id=actor_id,
                created_at=outcome_spec["effective_at"],
            )
        )

    quote_spec = spec["quote"]
    quote = Quote(
        project_id=project.id,
        quote_number=str(quote_spec["quote_number"]),
        title=str(quote_spec["title"]),
    )
    session.add(quote)
    session.flush()

    previous_version: QuoteVersion | None = None
    current_version: QuoteVersion | None = None
    current_version_spec: dict[str, object] | None = None
    for version_spec in quote_spec["versions"]:
        source_document_date = version_spec.get("source_document_date")
        valid_until = version_spec.get("valid_until")
        if valid_until is None and source_document_date is not None:
            valid_until = source_document_date + timedelta(days=30)
        version = QuoteVersion(
            quote_id=quote.id,
            parent_version_id=previous_version.id if previous_version is not None else None,
            version_number=int(version_spec["version_number"]),
            status=version_spec["status"],
            title=str(version_spec["title"]),
            currency_code=str(spec["quote_currency_code"]),
            valid_until=valid_until,
            issued_at=version_spec.get("issued_at"),
            accepted_at=version_spec.get("accepted_at"),
            rejected_at=version_spec.get("rejected_at"),
            created_by_id=actor_id,
            issued_by_id=actor_id if version_spec.get("issued_at") is not None else None,
            client_facing_notes=version_spec.get("client_facing_notes"),
            internal_notes=version_spec.get("internal_notes"),
            source_document_date=source_document_date,
            source_version_label=version_spec.get("source_version_label"),
            subtotal_amount=_version_subtotal(version_spec),
            tax_amount=_version_tax(version_spec),
            total_amount=_version_total(version_spec),
        )
        session.add(version)
        session.flush()
        _seed_quote_sections(
            session,
            version,
            version_spec["sections"],
            discipline_ids=discipline_ids,
        )
        previous_version = version
        if version_spec.get("is_current"):
            current_version = version
            current_version_spec = version_spec

    if current_version is None:
        current_version = previous_version
        current_version_spec = quote_spec["versions"][-1]
    if current_version is not None:
        quote.current_version_id = current_version.id

    benchmark_spec = spec.get("benchmark")
    if (
        benchmark_spec is not None
        and current_version is not None
        and current_version_spec is not None
    ):
        _seed_benchmark_summary(
            session,
            project_id=project.id,
            source_quote_version_id=current_version.id,
            currency_code=str(spec["quote_currency_code"]),
            version_spec=current_version_spec,
            benchmark_spec=benchmark_spec,
            discipline_ids=discipline_ids,
        )


def _seed_demo_projects(session: Session, *, actor_id: str) -> None:
    if session.get(Project, "project_red_room") is not None:
        return

    company_ids = _get_company_ids_by_name(session)
    contact_ids = _get_contact_ids_by_email(session)
    contact_role_ids = _get_contact_role_ids_by_key(session)
    discipline_ids = _get_discipline_ids_by_code(session)
    loss_reason_ids = _get_loss_reason_ids_by_code(session)

    for spec in PROJECT_SEEDS:
        _seed_project(
            session,
            spec,
            actor_id=actor_id,
            company_ids=company_ids,
            contact_ids=contact_ids,
            contact_role_ids=contact_role_ids,
            discipline_ids=discipline_ids,
            loss_reason_ids=loss_reason_ids,
        )

    selection_note = (
        "Pinned Silver Tide for the shared streamer workflow and excluded Blue Echo after "
        "reviewing it as a client-specific outlier."
    )
    session.add_all(
        [
            ComparableProjectLink(
                project_id="project_red_room",
                comparable_project_id="project_silver_tide",
                disposition=ComparableProjectLinkDisposition.pinned,
                score=86,
                note=selection_note,
                created_by_id=actor_id,
                scoring_model_version="comparable-project-v1",
                reasons_json={
                    "source": "seed",
                    "detail": "Pinned seeded comparable for manual review coverage.",
                },
            ),
            ComparableProjectLink(
                project_id="project_red_room",
                comparable_project_id="project_blue_echo",
                disposition=ComparableProjectLinkDisposition.excluded,
                score=74,
                note=selection_note,
                created_by_id=actor_id,
                scoring_model_version="comparable-project-v1",
                reasons_json={
                    "source": "seed",
                    "detail": "Excluded seeded comparable to exercise override surfacing.",
                },
            ),
        ]
    )


def _seed_demo_forecasts(session: Session, *, actor_id: str) -> None:
    for spec in PROJECT_SEEDS:
        forecast_spec = spec.get("forecast")
        if forecast_spec is None:
            continue

        version = forecast_service.create_or_clone_version(
            session,
            str(spec["id"]),
            ForecastVersionCreateRequest(
                title=str(forecast_spec["title"]),
                notes_text=(
                    str(forecast_spec["notes_text"])
                    if forecast_spec.get("notes_text") is not None
                    else None
                ),
                probability_percent=(
                    float(forecast_spec["probability_percent"])
                    if forecast_spec.get("probability_percent") is not None
                    else None
                ),
                revision_reason=(
                    str(forecast_spec["revision_reason"])
                    if forecast_spec.get("revision_reason") is not None
                    else None
                ),
            ),
            actor_id=actor_id,
        )

        for manual_override in forecast_spec.get("manual_overrides", []):
            line = next(
                (
                    item
                    for item in version.lines
                    if str(manual_override["line_label_contains"]).lower() in item.label.lower()
                ),
                None,
            )
            if line is None:
                raise RuntimeError(
                    f"Could not find forecast line containing "
                    f"{manual_override['line_label_contains']} for {spec['id']}."
                )
            version = forecast_service.replace_line_allocations(
                session,
                line.id,
                ForecastLineAllocationsReplaceRequest(
                    expected_updated_at=version.updated_at,
                    allocation_method="manual",
                    allocations=[
                        ForecastLineMonthAllocationWrite(month=month, amount=amount)
                        for month, amount in manual_override["allocations"]
                    ],
                    reason=str(manual_override["reason"]),
                ),
                actor_id=actor_id,
            )

        if forecast_spec.get("submit_after"):
            version = forecast_service.submit_version(session, version.id, actor_id=actor_id)
        if forecast_spec.get("lock_after"):
            forecast_service.lock_version(session, version.id, actor_id=actor_id)


def _create_uploaded_file(
    session: Session,
    *,
    storage_key: str,
    file_name: str,
    actor_id: str,
    uploaded_at: datetime,
) -> UploadedFile:
    record = UploadedFile(
        storage_key=storage_key,
        original_filename=file_name,
        mime_type="text/csv",
        size_bytes=4096,
        checksum_sha256=f"seed-{file_name}",
        file_category=UploadedFileCategory.ceta_export,
        status=UploadedFileStatus.uploaded,
        uploaded_by_id=actor_id,
        created_at=uploaded_at,
        uploaded_at=uploaded_at,
    )
    session.add(record)
    session.flush()
    return record


def _seed_demo_actuals_imports(
    session: Session,
    *,
    actor_id: str,
) -> None:
    discipline_ids = _get_discipline_ids_by_code(session)

    if session.scalar(select(ProjectExternalReference.id).limit(1)) is not None:
        return

    for batch_spec in ACTUALS_IMPORT_BATCH_SEEDS:
        uploaded_file = _create_uploaded_file(
            session,
            storage_key=str(batch_spec["storage_key"]),
            file_name=str(batch_spec["file_name"]),
            actor_id=actor_id,
            uploaded_at=batch_spec["uploaded_at"],
        )

        batch = actuals_import_service.create_batch(
            session,
            CreateActualsImportBatchRequest(
                uploaded_file_id=uploaded_file.id,
                coverage_mode=batch_spec["coverage_mode"],
                project_id=str(batch_spec["project_id"]),
                source_system="ceta",
                source_export_id=(
                    str(batch_spec["source_export_id"])
                    if batch_spec.get("source_export_id") is not None
                    else None
                ),
                source_exported_at=batch_spec.get("source_exported_at"),
                coverage_start=batch_spec.get("coverage_start"),
                coverage_end=batch_spec.get("coverage_end"),
                parser_profile_hint=(
                    str(batch_spec["parser_profile_hint"])
                    if batch_spec.get("parser_profile_hint") is not None
                    else None
                ),
                notes=(str(batch_spec["notes"]) if batch_spec.get("notes") is not None else None),
            ),
            actor_id=actor_id,
        )

        worker_result = batch_spec.get("worker_result")
        if worker_result is None:
            continue
        process_job = actuals_import_service.build_process_job(session, batch.id)

        actuals_import_service.apply_worker_result(
            session,
            batch.id,
            WorkerActualsImportResultRequest(
                job_id=process_job.id,
                status=str(worker_result["status"]),
                parser_name=str(worker_result["parser_name"]),
                parser_version=str(worker_result["parser_version"]),
                parser_profile=str(worker_result["parser_profile"]),
                source_system=str(worker_result["source_system"]),
                coverage_start=worker_result.get("coverage_start"),
                coverage_end=worker_result.get("coverage_end"),
                batch_issues=[
                    WorkerActualsImportIssue(
                        severity=issue["severity"],
                        issue_code=str(issue["issue_code"]),
                        field_name=(
                            str(issue["field_name"])
                            if issue.get("field_name") is not None
                            else None
                        ),
                        message=str(issue["message"]),
                        details=issue.get("details"),
                    )
                    for issue in worker_result.get("batch_issues", [])
                ],
                rows=[
                    WorkerActualsImportRow(
                        row_number=int(row["row_number"]),
                        source_row_uid=(
                            str(row["source_row_uid"])
                            if row.get("source_row_uid") is not None
                            else None
                        ),
                        row_hash=str(row["row_hash"]),
                        business_key_hash=str(row["business_key_hash"]),
                        duplicate_group_key=(
                            str(row["duplicate_group_key"])
                            if row.get("duplicate_group_key") is not None
                            else None
                        ),
                        external_project_code=(
                            str(row["external_project_code"])
                            if row.get("external_project_code") is not None
                            else None
                        ),
                        normalized_project_code=(
                            str(row["normalized_project_code"])
                            if row.get("normalized_project_code") is not None
                            else None
                        ),
                        work_date=row.get("work_date"),
                        posting_date=row.get("posting_date"),
                        source_discipline_code=(
                            str(row["source_discipline_code"])
                            if row.get("source_discipline_code") is not None
                            else None
                        ),
                        description=(
                            str(row["description"])
                            if row.get("description") is not None
                            else None
                        ),
                        normalized_description=(
                            str(row["normalized_description"])
                            if row.get("normalized_description") is not None
                            else None
                        ),
                        vendor_name=(
                            str(row["vendor_name"])
                            if row.get("vendor_name") is not None
                            else None
                        ),
                        normalized_vendor_name=(
                            str(row["normalized_vendor_name"])
                            if row.get("normalized_vendor_name") is not None
                            else None
                        ),
                        amount=float(row["amount"]),
                        currency_code=str(row["currency_code"]),
                        financial_type=row["financial_type"],
                        raw_payload=row.get("raw_payload"),
                        issues=[
                            WorkerActualsImportIssue(
                                severity=issue["severity"],
                                issue_code=str(issue["issue_code"]),
                                field_name=(
                                    str(issue["field_name"])
                                    if issue.get("field_name") is not None
                                    else None
                                ),
                                message=str(issue["message"]),
                                details=issue.get("details"),
                            )
                            for issue in row.get("issues", [])
                        ],
                    )
                    for row in worker_result["rows"]
                ],
            ),
        )

        decisions = batch_spec.get("decisions")
        if decisions:
            rows = actuals_import_service.list_rows(session, batch.id).items
            rows_by_number = {row.row_number: row for row in rows}
            for decision in decisions:
                row = rows_by_number[int(decision["row_number"])]
                actuals_import_service.update_row_decision(
                    session,
                    row.id,
                    UpdateActualsImportRowDecisionRequest(
                        mapped_project_id=str(batch_spec["project_id"]),
                        mapped_discipline_id=discipline_ids[str(decision["mapped_discipline"])],
                        financial_type=decision["financial_type"],
                        cost_category_key=decision.get("cost_category_key"),
                        revenue_category_key=decision.get("revenue_category_key"),
                        approval_action=decision["approval_action"],
                        reviewer_note=(
                            str(decision["reviewer_note"])
                            if decision.get("reviewer_note") is not None
                            else None
                        ),
                        save_project_external_reference=bool(
                            decision.get("save_project_external_reference", False)
                        ),
                        save_rule=bool(decision.get("save_rule", False)),
                        rule_name=(
                            str(decision["rule_name"])
                            if decision.get("rule_name") is not None
                            else None
                        ),
                    ),
                    actor_id=actor_id,
                )
            session.expire_all()

        approve_spec = batch_spec.get("approve")
        if approve_spec is not None:
            actuals_import_service.approve_batch(
                session,
                batch.id,
                ApproveActualsImportBatchRequest(
                    withdraw_actual_ids=list(approve_spec.get("withdraw_actual_ids", []))
                ),
                actor_id=actor_id,
            )


def run_seed(*, seed_mode: str | None = None) -> None:
    resolved_seed_mode = _resolve_seed_mode(seed_mode)
    session_factory = get_session_factory()
    with session_factory() as session:
        roles = _seed_roles_and_permissions(session)
        _seed_contact_roles(session)
        _seed_disciplines(session)
        _seed_loss_reasons(session)
        _seed_reference_data(session)
        _seed_companies(session)
        _seed_contacts(session)
        _seed_company_contacts(session)
        admin_user = _seed_admin_user(session, roles, seed_mode=resolved_seed_mode)
        _seed_reference_aliases(session, actor_id=admin_user.id)
        if resolved_seed_mode == SEED_MODE_DEMO:
            _seed_demo_projects(session, actor_id=admin_user.id)
            _seed_demo_forecasts(session, actor_id=admin_user.id)
            _seed_demo_actuals_imports(session, actor_id=admin_user.id)
        session.commit()

    if resolved_seed_mode == SEED_MODE_DEMO:
        print(
            "Seed complete (demo): reference data, counterparties, contacts, demo projects, "
            "quote history, forecasts, actuals imports, and benchmark summaries"
        )
        return

    print(
        "Seed complete (baseline): reference data, counterparties, contacts, aliases, "
        "and admin access only"
    )


def _build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Seed the Quotes4 database.")
    parser.add_argument(
        "--mode",
        choices=sorted(VALID_SEED_MODES),
        default=None,
        help="Seed baseline operational data only, or include the full demo dataset.",
    )
    return parser


if __name__ == "__main__":
    args = _build_cli_parser().parse_args()
    run_seed(seed_mode=args.mode)
