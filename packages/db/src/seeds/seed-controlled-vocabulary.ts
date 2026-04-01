import process from "node:process";
import { fileURLToPath } from "node:url";

import { PrismaClient, type Prisma } from "@prisma/client";

import {
  CONTROLLED_VOCABULARY_DISCIPLINE_SEEDS,
  CONTROLLED_VOCABULARY_REFERENCE_DATA_COUNTS_BY_CATEGORY,
  CONTROLLED_VOCABULARY_REFERENCE_DATA_VALUE_SEEDS,
  type ControlledVocabularyReferenceDataCategory,
} from "./controlled-vocabulary.js";

export interface ControlledVocabularySeedSummary {
  disciplineCount: number;
  referenceDataValueCount: number;
  countsByCategory: Partial<
    Record<ControlledVocabularyReferenceDataCategory, number>
  >;
}

function toJsonValue(value: unknown): Prisma.InputJsonValue {
  return value as Prisma.InputJsonValue;
}

export async function seedControlledVocabulary(
  prisma: PrismaClient,
): Promise<ControlledVocabularySeedSummary> {
  for (const seed of CONTROLLED_VOCABULARY_DISCIPLINE_SEEDS) {
    await prisma.discipline.upsert({
      where: { code: seed.code },
      update: {
        name: seed.name,
        sortOrder: seed.sortOrder,
        isActive: seed.isActive,
      },
      create: {
        code: seed.code,
        name: seed.name,
        sortOrder: seed.sortOrder,
        isActive: seed.isActive,
      },
    });
  }

  for (const seed of CONTROLLED_VOCABULARY_REFERENCE_DATA_VALUE_SEEDS) {
    await prisma.referenceDataValue.upsert({
      where: {
        category_key: {
          category: seed.category,
          key: seed.key,
        },
      },
      update: {
        label: seed.label,
        sortOrder: seed.sortOrder,
        isActive: seed.isActive,
        metadata: toJsonValue(seed.metadata),
      },
      create: {
        category: seed.category,
        key: seed.key,
        label: seed.label,
        sortOrder: seed.sortOrder,
        isActive: seed.isActive,
        metadata: toJsonValue(seed.metadata),
      },
    });
  }

  return {
    disciplineCount: CONTROLLED_VOCABULARY_DISCIPLINE_SEEDS.length,
    referenceDataValueCount:
      CONTROLLED_VOCABULARY_REFERENCE_DATA_VALUE_SEEDS.length,
    countsByCategory: CONTROLLED_VOCABULARY_REFERENCE_DATA_COUNTS_BY_CATEGORY,
  };
}

function formatSeedSummary(summary: ControlledVocabularySeedSummary): string {
  const categoryLines = Object.entries(summary.countsByCategory)
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([category, count]) => `  - ${category}: ${count ?? 0}`)
    .join("\n");

  return [
    "Controlled vocabulary seed complete.",
    `Disciplines: ${summary.disciplineCount}`,
    `Reference data values: ${summary.referenceDataValueCount}`,
    "Counts by category:",
    categoryLines,
  ].join("\n");
}

async function main(): Promise<void> {
  const prisma = new PrismaClient();

  try {
    const summary = await seedControlledVocabulary(prisma);
    console.info(formatSeedSummary(summary));
  } finally {
    await prisma.$disconnect();
  }
}

const isDirectExecution =
  process.argv[1] !== undefined &&
  fileURLToPath(import.meta.url) === process.argv[1];

if (isDirectExecution) {
  void main().catch((error: unknown) => {
    console.error("Failed to seed controlled vocabulary.", error);
    process.exitCode = 1;
  });
}
