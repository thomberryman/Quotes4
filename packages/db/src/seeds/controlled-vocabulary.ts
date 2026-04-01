export const CONTROLLED_VOCABULARY_REFERENCE_DATA_CATEGORIES = [
  "service",
  "deliverable",
  "quote_line_item_subcategory",
  "project_format",
  "pipeline_stage",
  "revenue_category",
  "actuals_mapping_category",
  "counterparty_tag",
] as const;

export type ControlledVocabularyReferenceDataCategory =
  (typeof CONTROLLED_VOCABULARY_REFERENCE_DATA_CATEGORIES)[number];

export interface DisciplineSeed {
  code: string;
  name: string;
  sortOrder: number;
  isActive: boolean;
}

export interface ControlledVocabularyMetadata {
  parentGroupKey?: string;
  disciplineKey?: string;
  mapsToProjectStatus?: string;
  synonyms?: string[];
  description?: string;
  systemDefined: true;
}

export interface ReferenceDataValueSeed {
  category: ControlledVocabularyReferenceDataCategory;
  key: string;
  label: string;
  sortOrder: number;
  isActive: boolean;
  metadata: ControlledVocabularyMetadata;
}

interface ReferenceDataValueDefinition {
  key: string;
  label: string;
  sortOrder: number;
  parentGroupKey?: string;
  disciplineKey?: string;
  mapsToProjectStatus?: string;
  synonyms: string[];
  description: string;
}

function buildReferenceDataSeeds(
  category: ControlledVocabularyReferenceDataCategory,
  definitions: ReferenceDataValueDefinition[],
): ReferenceDataValueSeed[] {
  return definitions.map((definition) => {
    const metadata: ControlledVocabularyMetadata = {
      synonyms: definition.synonyms,
      description: definition.description,
      systemDefined: true,
    };

    if (definition.parentGroupKey) {
      metadata.parentGroupKey = definition.parentGroupKey;
    }

    if (definition.disciplineKey) {
      metadata.disciplineKey = definition.disciplineKey;
    }

    if (definition.mapsToProjectStatus) {
      metadata.mapsToProjectStatus = definition.mapsToProjectStatus;
    }

    return {
      category,
      key: definition.key,
      label: definition.label,
      sortOrder: definition.sortOrder,
      isActive: true,
      metadata,
    };
  });
}

export const CONTROLLED_VOCABULARY_DISCIPLINE_SEEDS: DisciplineSeed[] = [
  { code: "offline", name: "Offline Edit", sortOrder: 10, isActive: true },
  { code: "edit_assist", name: "Edit Assist", sortOrder: 20, isActive: true },
  { code: "online", name: "Online / Conform", sortOrder: 30, isActive: true },
  { code: "grade", name: "Color Grading", sortOrder: 40, isActive: true },
  { code: "vfx", name: "Visual Effects", sortOrder: 50, isActive: true },
  {
    code: "graphics",
    name: "Graphics / Titles",
    sortOrder: 60,
    isActive: true,
  },
  {
    code: "sound_edit",
    name: "Sound Editorial",
    sortOrder: 70,
    isActive: true,
  },
  { code: "mix", name: "Sound Mix", sortOrder: 80, isActive: true },
  { code: "music", name: "Music", sortOrder: 90, isActive: true },
  {
    code: "localization",
    name: "Localization",
    sortOrder: 100,
    isActive: true,
  },
  { code: "qc", name: "QC", sortOrder: 110, isActive: true },
  {
    code: "delivery",
    name: "Delivery / Versioning",
    sortOrder: 120,
    isActive: true,
  },
  { code: "media_io", name: "Media I/O", sortOrder: 130, isActive: true },
  {
    code: "post_management",
    name: "Post Management",
    sortOrder: 140,
    isActive: true,
  },
];

const SERVICE_REFERENCE_DATA_SEEDS = buildReferenceDataSeeds("service", [
  {
    key: "editorial_cut",
    label: "Editorial Cut",
    sortOrder: 10,
    parentGroupKey: "offline",
    disciplineKey: "offline",
    synonyms: ["edit", "cut", "assembly", "recut"],
    description: "Main editorial crafting work.",
  },
  {
    key: "editorial_revision",
    label: "Editorial Revisions",
    sortOrder: 20,
    parentGroupKey: "offline",
    disciplineKey: "offline",
    synonyms: ["revisions", "notes pass", "reversion", "recuts"],
    description: "Iteration after client or producer feedback.",
  },
  {
    key: "assistant_edit_prep",
    label: "Assistant Edit Prep",
    sortOrder: 30,
    parentGroupKey: "edit_assist",
    disciplineKey: "edit_assist",
    synonyms: ["prep", "sync", "bins", "ingest", "turnover prep"],
    description: "Editorial support service.",
  },
  {
    key: "conform",
    label: "Conform",
    sortOrder: 40,
    parentGroupKey: "online",
    disciplineKey: "online",
    synonyms: ["conform", "online", "finishing", "relink"],
    description: "Assembling the final timeline from approved sources.",
  },
  {
    key: "color_grade",
    label: "Color Grade",
    sortOrder: 50,
    parentGroupKey: "grade",
    disciplineKey: "grade",
    synonyms: ["grade", "colour pass", "color session", "grading"],
    description: "Color treatment and review sessions.",
  },
  {
    key: "vfx_shot_work",
    label: "VFX Shot Work",
    sortOrder: 60,
    parentGroupKey: "vfx",
    disciplineKey: "vfx",
    synonyms: ["shot work", "cleanup", "comp", "roto", "paint"],
    description: "Discrete VFX work billed by shot, task, or package.",
  },
  {
    key: "graphics_build",
    label: "Graphics Build",
    sortOrder: 70,
    parentGroupKey: "graphics",
    disciplineKey: "graphics",
    synonyms: ["title build", "gfx", "lower thirds", "supers"],
    description: "Creation or revision of graphics packages.",
  },
  {
    key: "sound_edit_service",
    label: "Sound Edit",
    sortOrder: 80,
    parentGroupKey: "sound_edit",
    disciplineKey: "sound_edit",
    synonyms: ["dialogue edit", "foley edit", "sfx edit"],
    description: "Audio editorial work before final mix.",
  },
  {
    key: "adr_foley",
    label: "ADR / Foley",
    sortOrder: 90,
    parentGroupKey: "sound_edit",
    disciplineKey: "sound_edit",
    synonyms: ["adr", "foley", "voice record"],
    description: "Session-based replacement or enhancement recording.",
  },
  {
    key: "final_mix",
    label: "Final Mix",
    sortOrder: 100,
    parentGroupKey: "mix",
    disciplineKey: "mix",
    synonyms: ["mix", "final mix", "printmaster", "dub"],
    description: "Client-ready audio mix service.",
  },
  {
    key: "music_edit_supervision",
    label: "Music Edit / Supervision",
    sortOrder: 110,
    parentGroupKey: "music",
    disciplineKey: "music",
    synonyms: ["music edit", "music supervision", "score conform"],
    description: "Music-specific work outside final mix.",
  },
  {
    key: "subtitle_caption_prep",
    label: "Subtitle / Caption Prep",
    sortOrder: 120,
    parentGroupKey: "localization",
    disciplineKey: "localization",
    synonyms: ["subtitles", "captions", "sdh", "cc prep"],
    description: "Text-based localization preparation.",
  },
  {
    key: "qc_review",
    label: "QC Review",
    sortOrder: 130,
    parentGroupKey: "qc",
    disciplineKey: "qc",
    synonyms: ["qc pass", "tech review", "compliance check"],
    description: "Review service before delivery approval.",
  },
  {
    key: "versioning",
    label: "Versioning",
    sortOrder: 140,
    parentGroupKey: "delivery",
    disciplineKey: "delivery",
    synonyms: ["reversion", "localization version", "alt version"],
    description: "Building territory, client, or platform variants.",
  },
  {
    key: "mastering_packaging",
    label: "Mastering / Packaging",
    sortOrder: 150,
    parentGroupKey: "delivery",
    disciplineKey: "delivery",
    synonyms: ["mastering", "package", "imf build", "dcp build"],
    description: "Final container or package creation.",
  },
  {
    key: "media_prep_archive",
    label: "Media Prep / Archive",
    sortOrder: 160,
    parentGroupKey: "media_io",
    disciplineKey: "media_io",
    synonyms: ["transcode", "archive", "restore", "media prep"],
    description: "Media logistics and archival support.",
  },
  {
    key: "project_management",
    label: "Project Management",
    sortOrder: 170,
    parentGroupKey: "post_management",
    disciplineKey: "post_management",
    synonyms: ["producing", "supervision", "coordination", "management"],
    description: "Oversight, scheduling, and client-facing management.",
  },
]);

const DELIVERABLE_REFERENCE_DATA_SEEDS = buildReferenceDataSeeds(
  "deliverable",
  [
    {
      key: "review_export",
      label: "Review Export",
      sortOrder: 10,
      parentGroupKey: "review",
      synonyms: ["screener", "review link", "viewing copy", "h264"],
      description: "Temporary or approval-oriented review output.",
    },
    {
      key: "final_picture_master",
      label: "Final Picture Master",
      sortOrder: 20,
      parentGroupKey: "picture_master",
      synonyms: ["final master", "hero master", "mezzanine", "master file"],
      description: "Main approved picture deliverable.",
    },
    {
      key: "textless_master",
      label: "Textless Master",
      sortOrder: 30,
      parentGroupKey: "picture_master",
      synonyms: ["textless", "clean master", "international master"],
      description: "Picture master without burnt-in titles or captions.",
    },
    {
      key: "versioned_master",
      label: "Versioned Master",
      sortOrder: 40,
      parentGroupKey: "picture_master",
      synonyms: ["version", "local version", "territory version", "reversion"],
      description: "Variant of the main master for a platform or market.",
    },
    {
      key: "trailer_promo_master",
      label: "Trailer / Promo Master",
      sortOrder: 50,
      parentGroupKey: "picture_master",
      synonyms: ["trailer", "promo", "teaser"],
      description: "Marketing-focused master output.",
    },
    {
      key: "social_cutdown",
      label: "Social Cutdown",
      sortOrder: 60,
      parentGroupKey: "picture_master",
      synonyms: ["social", "cutdown", "vertical", "square", "15s", "30s"],
      description: "Short-form derived marketing output.",
    },
    {
      key: "final_audio_master",
      label: "Final Audio Master",
      sortOrder: 70,
      parentGroupKey: "audio_master",
      synonyms: ["printmaster", "full mix", "stems", "m&e", "split audio"],
      description: "Client-ready audio deliverable family.",
    },
    {
      key: "subtitle_package",
      label: "Subtitle Package",
      sortOrder: 80,
      parentGroupKey: "localization",
      synonyms: ["subtitles", "srt", "stl", "itt"],
      description: "Text subtitle files and package components.",
    },
    {
      key: "caption_package",
      label: "Caption Package",
      sortOrder: 90,
      parentGroupKey: "localization",
      synonyms: ["captions", "closed captions", "cc", "sdh"],
      description: "Accessibility caption deliverables.",
    },
    {
      key: "imf_package",
      label: "IMF Package",
      sortOrder: 100,
      parentGroupKey: "delivery_package",
      synonyms: ["imf", "cpl", "opl"],
      description: "IMF-based package delivery.",
    },
    {
      key: "dcp_package",
      label: "DCP Package",
      sortOrder: 110,
      parentGroupKey: "delivery_package",
      synonyms: ["dcp", "cinema package"],
      description: "Cinema delivery package.",
    },
    {
      key: "qc_report",
      label: "QC Report",
      sortOrder: 120,
      parentGroupKey: "delivery_package",
      synonyms: ["qc report", "technical report", "exception report"],
      description: "Report artifact attached to delivery readiness.",
    },
    {
      key: "graphics_package",
      label: "Graphics Package",
      sortOrder: 130,
      parentGroupKey: "supporting_assets",
      synonyms: ["titles package", "graphics export", "layered graphics"],
      description: "Source or rendered graphics assets.",
    },
    {
      key: "archive_turnover",
      label: "Archive / Turnover",
      sortOrder: 140,
      parentGroupKey: "supporting_assets",
      synonyms: ["archive", "turnover", "lto", "restore copy"],
      description: "Archival or handoff deliverable.",
    },
  ],
);

const QUOTE_LINE_ITEM_SUBCATEGORY_REFERENCE_DATA_SEEDS =
  buildReferenceDataSeeds("quote_line_item_subcategory", [
    {
      key: "labor_day",
      label: "Labor Day Rate",
      sortOrder: 10,
      parentGroupKey: "service_labor",
      synonyms: ["day", "days", "man day", "day rate"],
      description: "Use when a person or role is billed by day.",
    },
    {
      key: "labor_hour",
      label: "Labor Hour Rate",
      sortOrder: 20,
      parentGroupKey: "service_labor",
      synonyms: ["hour", "hours", "hr", "hourly"],
      description: "Use when a person or role is billed by hour.",
    },
    {
      key: "labor_fixed_fee",
      label: "Labor Fixed Fee",
      sortOrder: 30,
      parentGroupKey: "service_labor",
      synonyms: ["fixed fee", "flat fee", "creative fee"],
      description: "Fixed labor or creative charge not tied to units.",
    },
    {
      key: "package_fee",
      label: "Package Fee",
      sortOrder: 40,
      parentGroupKey: "service_labor",
      synonyms: ["package", "bundled fee", "lot price"],
      description: "Bundled scope crossing multiple tasks or sessions.",
    },
    {
      key: "facility_rental",
      label: "Facility Rental",
      sortOrder: 50,
      parentGroupKey: "service_facility_tech",
      synonyms: ["suite", "room", "theatre", "bay", "stage"],
      description: "Booked facility or room charge.",
    },
    {
      key: "software_license",
      label: "Software / License",
      sortOrder: 60,
      parentGroupKey: "service_facility_tech",
      synonyms: ["license", "software", "subscription", "plugin"],
      description: "Technology or licensed tool charge.",
    },
    {
      key: "media_storage",
      label: "Media / Storage",
      sortOrder: 70,
      parentGroupKey: "service_facility_tech",
      synonyms: ["drive", "storage", "transfer", "cloud", "lto"],
      description: "Media hardware, storage, archive, or transfer cost.",
    },
    {
      key: "third_party_vendor",
      label: "Third-Party Vendor",
      sortOrder: 80,
      parentGroupKey: "expense_pass_through",
      synonyms: ["vendor", "external vendor", "pass through", "outsource"],
      description: "External service rebilled to the client.",
    },
    {
      key: "stock_music_license",
      label: "Stock / Music License",
      sortOrder: 90,
      parentGroupKey: "expense_pass_through",
      synonyms: ["stock", "library music", "music license", "footage license"],
      description: "Rights-cleared content or music cost.",
    },
    {
      key: "travel_expense",
      label: "Travel / Expense",
      sortOrder: 100,
      parentGroupKey: "expense_pass_through",
      synonyms: ["travel", "hotel", "taxi", "per diem", "meals"],
      description: "Rebillable travel or expense item.",
    },
    {
      key: "shipping_courier",
      label: "Shipping / Courier",
      sortOrder: 110,
      parentGroupKey: "expense_pass_through",
      synonyms: ["courier", "shipping", "fedex", "messenger"],
      description: "Physical shipment or courier cost.",
    },
    {
      key: "markup",
      label: "Markup",
      sortOrder: 120,
      parentGroupKey: "commercial_adjustment",
      synonyms: ["markup", "handling", "procurement fee"],
      description: "Positive commercial adjustment on pass-through costs.",
    },
    {
      key: "contingency",
      label: "Contingency",
      sortOrder: 130,
      parentGroupKey: "commercial_adjustment",
      synonyms: ["contingency", "allowance", "reserve"],
      description: "Budgeted risk allowance.",
    },
    {
      key: "discount",
      label: "Discount",
      sortOrder: 140,
      parentGroupKey: "commercial_adjustment",
      synonyms: ["discount", "rebate", "credit", "write-off"],
      description: "Negative commercial adjustment.",
    },
    {
      key: "tax",
      label: "Tax",
      sortOrder: 150,
      parentGroupKey: "commercial_adjustment",
      synonyms: ["vat", "sales tax", "gst", "tax"],
      description:
        "Track separately and exclude from core revenue analytics by default.",
    },
  ]);

const PROJECT_FORMAT_REFERENCE_DATA_SEEDS = buildReferenceDataSeeds(
  "project_format",
  [
    {
      key: "feature_film",
      label: "Feature Film",
      sortOrder: 10,
      parentGroupKey: "long_form",
      synonyms: ["feature", "feature film", "movie"],
      description: "Long-form narrative or stand-alone factual film.",
    },
    {
      key: "documentary_feature",
      label: "Documentary Feature",
      sortOrder: 20,
      parentGroupKey: "long_form",
      synonyms: ["doc feature", "documentary feature"],
      description: "Stand-alone documentary film.",
    },
    {
      key: "episodic_series",
      label: "Episodic Series",
      sortOrder: 30,
      parentGroupKey: "series",
      synonyms: ["series", "episodic", "tv series", "serial"],
      description: "Multi-episode scripted series.",
    },
    {
      key: "documentary_series",
      label: "Documentary Series",
      sortOrder: 40,
      parentGroupKey: "series",
      synonyms: ["doc series", "documentary series"],
      description: "Multi-episode factual or documentary series.",
    },
    {
      key: "unscripted_series",
      label: "Unscripted / Reality Series",
      sortOrder: 50,
      parentGroupKey: "series",
      synonyms: [
        "reality",
        "entertainment",
        "factual entertainment",
        "competition",
      ],
      description: "Non-scripted episodic programming.",
    },
    {
      key: "commercial",
      label: "Commercial",
      sortOrder: 60,
      parentGroupKey: "short_form",
      synonyms: ["ad", "spot", "tvc", "commercial spot"],
      description: "Paid advertising work.",
    },
    {
      key: "trailer_promo",
      label: "Trailer / Promo",
      sortOrder: 70,
      parentGroupKey: "short_form",
      synonyms: ["promo", "trailer", "teaser", "on-air promo"],
      description: "Marketing content for another property.",
    },
    {
      key: "social_digital",
      label: "Social / Digital",
      sortOrder: 80,
      parentGroupKey: "short_form",
      synonyms: ["social", "digital", "online content", "platform content"],
      description: "Platform-first or social-first short-form work.",
    },
    {
      key: "branded_content",
      label: "Branded Content",
      sortOrder: 90,
      parentGroupKey: "short_form",
      synonyms: ["branded", "branded film", "sponsored content"],
      description: "Brand-funded editorial content outside pure ads.",
    },
    {
      key: "music_video",
      label: "Music Video",
      sortOrder: 100,
      parentGroupKey: "short_form",
      synonyms: ["mv", "music video", "promo video"],
      description: "Music-led short-form project.",
    },
    {
      key: "short_film",
      label: "Short Film",
      sortOrder: 110,
      parentGroupKey: "short_form",
      synonyms: ["short", "short film"],
      description: "Narrative or documentary short.",
    },
    {
      key: "corporate_internal",
      label: "Corporate / Internal",
      sortOrder: 120,
      parentGroupKey: "other",
      synonyms: ["internal", "corporate", "training", "sizzle"],
      description: "Non-broadcast internal or business communication work.",
    },
  ],
);

const PIPELINE_STAGE_REFERENCE_DATA_SEEDS = buildReferenceDataSeeds(
  "pipeline_stage",
  [
    {
      key: "lead",
      label: "Lead",
      sortOrder: 10,
      parentGroupKey: "pre_award",
      mapsToProjectStatus: "bid",
      synonyms: ["lead", "enquiry", "inquiry", "prospect"],
      description: "Earliest tracked opportunity stage.",
    },
    {
      key: "qualified",
      label: "Qualified",
      sortOrder: 20,
      parentGroupKey: "pre_award",
      mapsToProjectStatus: "bid",
      synonyms: ["qualified", "scoped", "briefed"],
      description: "Commercial opportunity has been qualified for effort.",
    },
    {
      key: "quoting",
      label: "Quoting",
      sortOrder: 30,
      parentGroupKey: "pre_award",
      mapsToProjectStatus: "bid",
      synonyms: ["estimating", "budgeting", "quote in progress"],
      description: "Commercial team is preparing quote detail.",
    },
    {
      key: "quote_submitted",
      label: "Quote Submitted",
      sortOrder: 40,
      parentGroupKey: "pre_award",
      mapsToProjectStatus: "bid",
      synonyms: ["submitted", "sent", "with client", "under review"],
      description: "Quote has been sent and is awaiting response.",
    },
    {
      key: "negotiation",
      label: "Negotiation",
      sortOrder: 50,
      parentGroupKey: "pre_award",
      mapsToProjectStatus: "bid",
      synonyms: ["negotiating", "revision requested", "best and final"],
      description: "Pricing or scope is being actively negotiated.",
    },
    {
      key: "awarded",
      label: "Awarded",
      sortOrder: 60,
      parentGroupKey: "delivery",
      mapsToProjectStatus: "awarded",
      synonyms: ["won", "greenlit", "awarded"],
      description: "Work has been commercially won.",
    },
    {
      key: "setup",
      label: "Setup",
      sortOrder: 70,
      parentGroupKey: "delivery",
      mapsToProjectStatus: "awarded",
      synonyms: ["onboarding", "kickoff", "preproduction setup"],
      description: "Operational setup before active delivery.",
    },
    {
      key: "active",
      label: "Active",
      sortOrder: 80,
      parentGroupKey: "delivery",
      mapsToProjectStatus: "active",
      synonyms: ["in progress", "live", "current"],
      description: "Work is underway.",
    },
    {
      key: "on_hold",
      label: "On Hold",
      sortOrder: 90,
      parentGroupKey: "delivery",
      mapsToProjectStatus: "active",
      synonyms: ["hold", "paused", "awaiting client"],
      description: "Operational work is paused but not closed.",
    },
    {
      key: "complete",
      label: "Complete",
      sortOrder: 100,
      parentGroupKey: "delivery",
      mapsToProjectStatus: "complete",
      synonyms: ["complete", "delivered", "wrapped"],
      description: "Delivery is complete.",
    },
    {
      key: "lost",
      label: "Lost",
      sortOrder: 110,
      parentGroupKey: "closed",
      mapsToProjectStatus: "lost",
      synonyms: ["lost", "not awarded", "dead"],
      description: "Opportunity was not won.",
    },
    {
      key: "archived",
      label: "Archived",
      sortOrder: 120,
      parentGroupKey: "closed",
      mapsToProjectStatus: "archived",
      synonyms: ["archived", "closed"],
      description: "Record is administratively archived.",
    },
  ],
);

const REVENUE_CATEGORY_REFERENCE_DATA_SEEDS = buildReferenceDataSeeds(
  "revenue_category",
  [
    {
      key: "editorial_services",
      label: "Editorial Services",
      sortOrder: 10,
      parentGroupKey: "core_services",
      synonyms: ["editorial", "offline", "edit"],
      description: "Revenue for editorial labor and related packages.",
    },
    {
      key: "picture_finishing",
      label: "Picture Finishing",
      sortOrder: 20,
      parentGroupKey: "core_services",
      synonyms: ["online", "conform", "grade", "finishing"],
      description: "Groups picture finishing work for reporting.",
    },
    {
      key: "vfx_graphics",
      label: "VFX / Graphics",
      sortOrder: 30,
      parentGroupKey: "core_services",
      synonyms: ["vfx", "graphics", "titles", "comp"],
      description:
        "Combined creative finishing bucket when finer split is not needed.",
    },
    {
      key: "audio_post",
      label: "Audio Post",
      sortOrder: 40,
      parentGroupKey: "core_services",
      synonyms: ["sound", "audio", "mix", "adr", "foley"],
      description: "Audio editorial and mixing revenue.",
    },
    {
      key: "localization",
      label: "Localization",
      sortOrder: 50,
      parentGroupKey: "core_services",
      synonyms: ["subtitles", "captions", "localisation", "version text"],
      description: "Language and territory adaptation revenue.",
    },
    {
      key: "delivery_versioning",
      label: "Delivery / Versioning",
      sortOrder: 60,
      parentGroupKey: "core_services",
      synonyms: ["delivery", "versioning", "mastering", "imf", "dcp"],
      description: "Final packaging and output revenue.",
    },
    {
      key: "post_management",
      label: "Post Management",
      sortOrder: 70,
      parentGroupKey: "core_services",
      synonyms: ["producing", "supervision", "coordination"],
      description: "Commercial value of project management and oversight.",
    },
    {
      key: "technology_facilities",
      label: "Technology / Facilities",
      sortOrder: 80,
      parentGroupKey: "core_services",
      synonyms: ["suite", "room", "storage", "software", "theatre"],
      description: "Facility and technical usage billed as revenue.",
    },
    {
      key: "third_party_rebill",
      label: "Third-Party Rebill",
      sortOrder: 90,
      parentGroupKey: "pass_through",
      synonyms: ["pass through", "vendor rebill", "external cost"],
      description: "External supplier costs rebilled to the client.",
    },
    {
      key: "expenses_rebill",
      label: "Expenses Rebill",
      sortOrder: 100,
      parentGroupKey: "pass_through",
      synonyms: ["travel", "courier", "expenses"],
      description: "Non-vendor pass-through items rebilled to the client.",
    },
    {
      key: "discount_adjustment",
      label: "Discount / Adjustment",
      sortOrder: 110,
      parentGroupKey: "adjustment",
      synonyms: ["discount", "rebate", "credit"],
      description: "Negative adjustment bucket for net-revenue reporting.",
    },
    {
      key: "tax_non_revenue",
      label: "Tax",
      sortOrder: 120,
      parentGroupKey: "adjustment",
      synonyms: ["vat", "tax", "sales tax", "gst"],
      description: "Keep separate from revenue analytics.",
    },
  ],
);

const ACTUALS_MAPPING_CATEGORY_REFERENCE_DATA_SEEDS = buildReferenceDataSeeds(
  "actuals_mapping_category",
  [
    {
      key: "internal_labor",
      label: "Internal Labor",
      sortOrder: 10,
      parentGroupKey: "labor",
      synonyms: ["payroll", "staff cost", "salary cost"],
      description: "Spend attributable to internal employees.",
    },
    {
      key: "freelance_labor",
      label: "Freelance Labor",
      sortOrder: 20,
      parentGroupKey: "labor",
      synonyms: ["freelance", "contractor", "day player"],
      description:
        "External individual labor not treated as a larger vendor service.",
    },
    {
      key: "facility_tech",
      label: "Facility / Tech",
      sortOrder: 30,
      parentGroupKey: "facility_tech",
      synonyms: ["suite", "room", "storage", "software", "machine room"],
      description: "Operational facility and technology costs.",
    },
    {
      key: "media_storage",
      label: "Media / Storage",
      sortOrder: 40,
      parentGroupKey: "facility_tech",
      synonyms: ["drive", "lto", "storage", "transfer", "cloud"],
      description: "Media handling and storage spend.",
    },
    {
      key: "external_vendor",
      label: "External Vendor Service",
      sortOrder: 50,
      parentGroupKey: "external",
      synonyms: ["vendor", "outsource", "po", "external service"],
      description: "Third-party company service cost.",
    },
    {
      key: "localization_vendor",
      label: "Localization Vendor",
      sortOrder: 60,
      parentGroupKey: "external",
      synonyms: ["subtitles vendor", "caption vendor", "dub vendor"],
      description: "Localization spend separated for reporting clarity.",
    },
    {
      key: "licensing",
      label: "Licensing",
      sortOrder: 70,
      parentGroupKey: "external",
      synonyms: ["stock", "music license", "footage license"],
      description: "Rights-based third-party spend.",
    },
    {
      key: "travel_expense",
      label: "Travel / Expense",
      sortOrder: 80,
      parentGroupKey: "expense",
      synonyms: ["travel", "hotel", "taxi", "meals", "per diem"],
      description: "Reimbursable or operational travel spend.",
    },
    {
      key: "shipping_courier",
      label: "Shipping / Courier",
      sortOrder: 90,
      parentGroupKey: "expense",
      synonyms: ["courier", "fedex", "shipping", "messenger"],
      description: "Shipment or messenger costs.",
    },
    {
      key: "tax_fee",
      label: "Tax / Fee",
      sortOrder: 100,
      parentGroupKey: "adjustment",
      synonyms: ["vat", "tax", "fee", "levy"],
      description: "Taxes and statutory or platform fees.",
    },
    {
      key: "adjustment_credit",
      label: "Adjustment / Credit",
      sortOrder: 110,
      parentGroupKey: "adjustment",
      synonyms: ["credit", "correction", "reversal", "write-off"],
      description: "Corrections that should not be treated as normal spend.",
    },
    {
      key: "unmapped_review",
      label: "Unmapped Review",
      sortOrder: 120,
      parentGroupKey: "exception",
      synonyms: ["suspense", "unknown", "uncoded"],
      description: "Explicit bucket for rows that still need human review.",
    },
  ],
);

const COUNTERPARTY_TAG_REFERENCE_DATA_SEEDS = buildReferenceDataSeeds(
  "counterparty_tag",
  [
    {
      key: "agency",
      label: "Agency",
      sortOrder: 10,
      parentGroupKey: "commercial",
      synonyms: ["agency", "creative agency", "media agency"],
      description: "Intermediary commercial counterparty tag.",
    },
    {
      key: "brand",
      label: "Brand",
      sortOrder: 20,
      parentGroupKey: "commercial",
      synonyms: ["advertiser", "brand", "sponsor"],
      description: "End-brand for commercial or branded projects.",
    },
    {
      key: "freelancer",
      label: "Freelancer",
      sortOrder: 30,
      parentGroupKey: "supply",
      synonyms: ["freelance", "contractor", "individual vendor"],
      description: "Individual worker or sole-trader counterparty tag.",
    },
    {
      key: "internal_entity",
      label: "Internal Entity",
      sortOrder: 40,
      parentGroupKey: "internal",
      synonyms: ["internal", "house", "affiliate"],
      description: "Internal business unit or related legal entity tag.",
    },
  ],
);

export const CONTROLLED_VOCABULARY_REFERENCE_DATA_VALUE_SEEDS = [
  ...SERVICE_REFERENCE_DATA_SEEDS,
  ...DELIVERABLE_REFERENCE_DATA_SEEDS,
  ...QUOTE_LINE_ITEM_SUBCATEGORY_REFERENCE_DATA_SEEDS,
  ...PROJECT_FORMAT_REFERENCE_DATA_SEEDS,
  ...PIPELINE_STAGE_REFERENCE_DATA_SEEDS,
  ...REVENUE_CATEGORY_REFERENCE_DATA_SEEDS,
  ...ACTUALS_MAPPING_CATEGORY_REFERENCE_DATA_SEEDS,
  ...COUNTERPARTY_TAG_REFERENCE_DATA_SEEDS,
] as const satisfies readonly ReferenceDataValueSeed[];

export const CONTROLLED_VOCABULARY_REFERENCE_DATA_COUNTS_BY_CATEGORY =
  CONTROLLED_VOCABULARY_REFERENCE_DATA_VALUE_SEEDS.reduce<
    Partial<Record<ControlledVocabularyReferenceDataCategory, number>>
  >((counts, seed) => {
    counts[seed.category] = (counts[seed.category] ?? 0) + 1;
    return counts;
  }, {});
