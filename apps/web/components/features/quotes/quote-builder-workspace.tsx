"use client";

import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import type {
  DisciplineRead,
  ProjectPredictiveGuidanceResponse,
  QuoteRead,
  QuoteSummary,
  QuoteVersionRead,
  QuoteVersionStatus,
} from "@quotes4/contracts";
import { ApiClientError } from "@quotes4/contracts";

import { getBrowserApiClient } from "@/lib/api/browser-client";
import { formatCurrency, formatDate, formatStatusLabel } from "@/lib/format";
import { getExpectedScenarioSpend } from "@/lib/predictions/advisory-spend";
import { queryKeys } from "@/lib/query/keys";

import { InlineActionBar } from "@/components/forms/inline-action-bar";
import { SelectField } from "@/components/forms/select-field";
import { TextAreaField } from "@/components/forms/text-area-field";
import { TextInput } from "@/components/forms/text-input";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { SectionCard } from "@/components/ui/section-card";
import { StatusBadge } from "@/components/ui/status-badge";
import { Button } from "@/components/ui/button";
import { SummaryStat } from "@/components/ui/summary-stat";

type EditableLine = {
  sortOrder: number;
  lineType: "service" | "expense" | "discount" | "adjustment";
  disciplineId: string;
  subcategoryKey: string;
  revenueCategoryKey: string;
  description: string;
  unit: string;
  quantity: number;
  rate: number;
  amount: number;
  notes: string;
};

type EditableSection = {
  name: string;
  sortOrder: number;
  lineItems: EditableLine[];
};

function normalizeSections(
  version: QuoteVersionRead | null,
): EditableSection[] {
  if (!version) {
    return [];
  }

  return version.sections.map((section) => ({
    name: section.name,
    sortOrder: section.sortOrder,
    lineItems: section.lineItems.map((lineItem) => ({
      sortOrder: lineItem.sortOrder,
      lineType: lineItem.lineType,
      disciplineId: lineItem.disciplineId ?? "",
      subcategoryKey: lineItem.subcategoryKey ?? "",
      revenueCategoryKey: lineItem.revenueCategoryKey ?? "",
      description: lineItem.description,
      unit: lineItem.unit,
      quantity: lineItem.quantity,
      rate: lineItem.rate,
      amount: lineItem.amount,
      notes: lineItem.notes ?? "",
    })),
  }));
}

function stringFromNumericContext(value: unknown): string {
  return typeof value === "number" ? String(value) : "";
}

export function QuoteBuilderWorkspace({
  projectId,
  projectName,
  quotes,
  initialSelectedVersionId = null,
  initialPredictiveGuidance = null,
}: {
  projectId: string;
  projectName: string;
  quotes: QuoteSummary[];
  initialSelectedVersionId?: string | null;
  initialPredictiveGuidance?: ProjectPredictiveGuidanceResponse | null;
}) {
  const api = getBrowserApiClient();
  const queryClient = useQueryClient();
  const [availableQuotes, setAvailableQuotes] = useState(quotes);
  const [selectedQuoteId, setSelectedQuoteId] = useState<string | null>(
    quotes[0]?.id ?? null,
  );
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(
    initialSelectedVersionId,
  );
  const [quoteNumber, setQuoteNumber] = useState("");
  const [quoteTitle, setQuoteTitle] = useState("");
  const [versionTitle, setVersionTitle] = useState("");
  const [currencyCode, setCurrencyCode] = useState("GBP");
  const [sourceVersionLabel, setSourceVersionLabel] = useState("");
  const [sourceDocumentDate, setSourceDocumentDate] = useState("");
  const [clientFacingNotes, setClientFacingNotes] = useState("");
  const [internalNotes, setInternalNotes] = useState("");
  const [discountPercent, setDiscountPercent] = useState("");
  const [marginPercent, setMarginPercent] = useState("");
  const [thirdPartyCostPercent, setThirdPartyCostPercent] = useState("");
  const [reviewCycleCount, setReviewCycleCount] = useState("");
  const [externalVendorUsage, setExternalVendorUsage] = useState("no");
  const [taxAmount, setTaxAmount] = useState(0);
  const [sections, setSections] = useState<EditableSection[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setAvailableQuotes(quotes);
  }, [quotes]);

  const quoteQuery = useQuery({
    enabled: Boolean(selectedQuoteId),
    initialData: undefined as QuoteRead | undefined,
    queryFn: async () => api.getQuote(selectedQuoteId ?? ""),
    queryKey: selectedQuoteId
      ? queryKeys.quote(selectedQuoteId)
      : ["quote", "none"],
  });

  const versionOptions = quoteQuery.data?.versions ?? [];

  const disciplineQuery = useQuery({
    initialData: { items: [] as DisciplineRead[] },
    queryFn: async () => api.listDisciplines(),
    queryKey: ["disciplines"],
  });

  useEffect(() => {
    if (!quoteQuery.data) {
      return;
    }

    const { currentVersionId } = quoteQuery.data;

    setQuoteNumber(quoteQuery.data.quoteNumber ?? "");
    setQuoteTitle(quoteQuery.data.title ?? "");
    setSelectedVersionId(
      (current) => current ?? currentVersionId ?? versionOptions[0]?.id ?? null,
    );
  }, [quoteQuery.data, versionOptions]);

  const versionQuery = useQuery({
    enabled: Boolean(selectedVersionId),
    initialData: undefined as QuoteVersionRead | undefined,
    queryFn: async () => api.getQuoteVersion(selectedVersionId ?? ""),
    queryKey: selectedVersionId
      ? queryKeys.quoteVersion(selectedVersionId)
      : ["quote-version", "none"],
  });

  const predictiveGuidanceQuery = useQuery({
    enabled: Boolean(selectedVersionId),
    initialData:
      selectedVersionId && selectedVersionId === initialSelectedVersionId
        ? (initialPredictiveGuidance ?? undefined)
        : undefined,
    queryFn: async () =>
      api.getProjectPredictiveGuidance(projectId, {
        limit: 10,
        ...(selectedVersionId ? { quoteVersionId: selectedVersionId } : {}),
      }),
    queryKey: selectedVersionId
      ? queryKeys.projectPredictiveGuidance(projectId, {
          quoteVersionId: selectedVersionId,
          limit: 10,
        })
      : ["project-predictive-guidance", projectId, "none"],
  });
  const predictiveGuidance = predictiveGuidanceQuery.data ?? null;
  const advisorySpend = getExpectedScenarioSpend(predictiveGuidance);

  useEffect(() => {
    if (!versionQuery.data) {
      return;
    }

    setVersionTitle(versionQuery.data.title ?? "");
    setCurrencyCode(versionQuery.data.currencyCode);
    setSourceVersionLabel(versionQuery.data.sourceVersionLabel ?? "");
    setSourceDocumentDate(versionQuery.data.sourceDocumentDate ?? "");
    setClientFacingNotes(versionQuery.data.clientFacingNotes ?? "");
    setInternalNotes(versionQuery.data.internalNotes ?? "");
    setDiscountPercent(
      stringFromNumericContext(versionQuery.data.pricingContext?.discountPercent),
    );
    setMarginPercent(
      stringFromNumericContext(versionQuery.data.pricingContext?.marginPercent),
    );
    setThirdPartyCostPercent(
      stringFromNumericContext(
        versionQuery.data.pricingContext?.thirdPartyCostPercent,
      ),
    );
    setReviewCycleCount(
      stringFromNumericContext(versionQuery.data.pricingContext?.reviewCycleCount),
    );
    setExternalVendorUsage(
      versionQuery.data.pricingContext?.externalVendorUsage ? "yes" : "no",
    );
    setTaxAmount(versionQuery.data.taxAmount);
    setSections(normalizeSections(versionQuery.data));
  }, [versionQuery.data]);

  const computedSubtotal = sections.reduce(
    (sectionTotal, section) =>
      sectionTotal +
      section.lineItems.reduce(
        (lineTotal, lineItem) => lineTotal + lineItem.amount,
        0,
      ),
    0,
  );
  const computedTotal = computedSubtotal + taxAmount;
  const quoteByDiscipline = sections.reduce<Record<string, number>>((acc, section) => {
    section.lineItems.forEach((lineItem) => {
      if (!lineItem.disciplineId) {
        return;
      }
      acc[lineItem.disciplineId] = (acc[lineItem.disciplineId] ?? 0) + lineItem.amount;
    });
    return acc;
  }, {});
  const pricingContext = {
    discountPercent: discountPercent ? Number(discountPercent) : null,
    marginPercent: marginPercent ? Number(marginPercent) : null,
    thirdPartyCostPercent: thirdPartyCostPercent
      ? Number(thirdPartyCostPercent)
      : null,
    reviewCycleCount: reviewCycleCount ? Number(reviewCycleCount) : null,
    externalVendorUsage: externalVendorUsage === "yes",
  };

  const createQuoteMutation = useMutation({
    mutationFn: async () =>
      api.createQuote({
        projectId,
        quoteNumber: quoteNumber || null,
        title: quoteTitle || `${projectName} Quote`,
      }),
    onSuccess: async (quote) => {
      setAvailableQuotes((current) => {
        if (current.some((item) => item.id === quote.id)) {
          return current;
        }
        return [quote, ...current];
      });
      setSelectedQuoteId(quote.id);
      await queryClient.invalidateQueries({ queryKey: queryKeys.quotes });
    },
    onError: (caughtError: unknown) => {
      setError(
        caughtError instanceof ApiClientError
          ? caughtError.message
          : "Could not create the quote.",
      );
    },
  });

  const updateQuoteMutation = useMutation({
    mutationFn: async () => {
      if (!quoteQuery.data) {
        throw new Error("Quote is missing.");
      }

      return api.updateQuote(quoteQuery.data.id, {
        expectedUpdatedAt: quoteQuery.data.updatedAt,
        quoteNumber,
        title: quoteTitle,
      });
    },
    onSuccess: async (quote) => {
      setAvailableQuotes((current) =>
        current.map((item) => (item.id === quote.id ? quote : item)),
      );
      await queryClient.invalidateQueries({
        queryKey: queryKeys.quote(quote.id),
      });
      await queryClient.invalidateQueries({ queryKey: queryKeys.quotes });
    },
    onError: (caughtError: unknown) => {
      setError(
        caughtError instanceof ApiClientError
          ? caughtError.message
          : "Could not save the quote header.",
      );
    },
  });

  const updateVersionMutation = useMutation({
    mutationFn: async () => {
      if (!versionQuery.data) {
        throw new Error("Quote version is missing.");
      }

      return api.updateQuoteVersion(versionQuery.data.id, {
        expectedUpdatedAt: versionQuery.data.updatedAt,
        title: versionTitle,
        currencyCode,
        sourceVersionLabel: sourceVersionLabel || null,
        sourceDocumentDate: sourceDocumentDate || null,
        clientFacingNotes: clientFacingNotes || null,
        internalNotes: internalNotes || null,
        pricingContext,
        subtotalAmount: computedSubtotal,
        taxAmount,
        totalAmount: computedTotal,
        sections: sections.map((section) => ({
          name: section.name,
          sortOrder: section.sortOrder,
          subtotalAmount: section.lineItems.reduce(
            (total, lineItem) => total + lineItem.amount,
            0,
          ),
          lineItems: section.lineItems.map((lineItem) => ({
            sortOrder: lineItem.sortOrder,
            lineType: lineItem.lineType,
            disciplineId: lineItem.disciplineId || null,
            subcategoryKey: lineItem.subcategoryKey || null,
            revenueCategoryKey: lineItem.revenueCategoryKey || null,
            description: lineItem.description,
            quantity: lineItem.quantity,
            unit: lineItem.unit,
            rate: lineItem.rate,
            amount: lineItem.amount,
            notes: lineItem.notes || null,
          })),
        })),
      });
    },
    onSuccess: async (version) => {
      await queryClient.invalidateQueries({
        queryKey: queryKeys.quoteVersion(version.id),
      });
      if (quoteQuery.data) {
        await queryClient.invalidateQueries({
          queryKey: queryKeys.quote(quoteQuery.data.id),
        });
        await queryClient.invalidateQueries({
          queryKey: queryKeys.quoteVersions(quoteQuery.data.id),
        });
      }
    },
    onError: (caughtError: unknown) => {
      setError(
        caughtError instanceof ApiClientError
          ? caughtError.message
          : "Could not save the quote version.",
      );
    },
  });

  const createVersionMutation = useMutation({
    mutationFn: async () => {
      if (!quoteQuery.data || !versionQuery.data) {
        throw new Error("Quote context is missing.");
      }

      return api.createQuoteVersion(quoteQuery.data.id, {
        baseVersionId: versionQuery.data.id,
        title: versionTitle || `Version ${versionQuery.data.versionNumber + 1}`,
        currencyCode,
        sourceVersionLabel: sourceVersionLabel || null,
        sourceDocumentDate: sourceDocumentDate || null,
        clientFacingNotes: clientFacingNotes || null,
        internalNotes: internalNotes || null,
        pricingContext,
        subtotalAmount: computedSubtotal,
        taxAmount,
        totalAmount: computedTotal,
        sections: sections.map((section) => ({
          name: section.name,
          sortOrder: section.sortOrder,
          subtotalAmount: section.lineItems.reduce(
            (total, lineItem) => total + lineItem.amount,
            0,
          ),
          lineItems: section.lineItems.map((lineItem) => ({
            sortOrder: lineItem.sortOrder,
            lineType: lineItem.lineType,
            disciplineId: lineItem.disciplineId || null,
            subcategoryKey: lineItem.subcategoryKey || null,
            revenueCategoryKey: lineItem.revenueCategoryKey || null,
            description: lineItem.description,
            quantity: lineItem.quantity,
            unit: lineItem.unit,
            rate: lineItem.rate,
            amount: lineItem.amount,
            notes: lineItem.notes || null,
          })),
        })),
      });
    },
    onSuccess: async (version) => {
      setSelectedVersionId(version.id);
      if (quoteQuery.data) {
        await queryClient.invalidateQueries({
          queryKey: queryKeys.quote(quoteQuery.data.id),
        });
        await queryClient.invalidateQueries({
          queryKey: queryKeys.quoteVersions(quoteQuery.data.id),
        });
      }
    },
    onError: (caughtError: unknown) => {
      setError(
        caughtError instanceof ApiClientError
          ? caughtError.message
          : "Could not create a new quote version.",
      );
    },
  });

  const issueVersionMutation = useMutation({
    mutationFn: async () => {
      if (!versionQuery.data) {
        throw new Error("Quote version is missing.");
      }

      return api.issueQuoteVersion(versionQuery.data.id);
    },
    onSuccess: async (version) => {
      await queryClient.invalidateQueries({
        queryKey: queryKeys.quoteVersion(version.id),
      });
      if (quoteQuery.data) {
        await queryClient.invalidateQueries({
          queryKey: queryKeys.quote(quoteQuery.data.id),
        });
        await queryClient.invalidateQueries({
          queryKey: queryKeys.quoteVersions(quoteQuery.data.id),
        });
        setSelectedVersionId(version.id);
      }
    },
    onError: (caughtError: unknown) => {
      setError(
        caughtError instanceof ApiClientError
          ? caughtError.message
          : "Could not issue the quote version.",
      );
    },
  });

  const updateLine = (
    sectionIndex: number,
    lineIndex: number,
    field: keyof EditableLine,
    value: string,
  ) => {
    setSections((current) =>
      current.map((section, currentSectionIndex) => {
        if (currentSectionIndex !== sectionIndex) {
          return section;
        }

        return {
          ...section,
          lineItems: section.lineItems.map((lineItem, currentLineIndex) => {
            if (currentLineIndex !== lineIndex) {
              return lineItem;
            }

            const nextLine = {
              ...lineItem,
              [field]:
                field === "quantity" || field === "rate" || field === "amount"
                  ? Number(value)
                  : value,
            } as EditableLine;

            if (field === "quantity" || field === "rate") {
              nextLine.amount = Number(
                (nextLine.quantity * nextLine.rate).toFixed(2),
              );
            }

            return nextLine;
          }),
        };
      }),
    );
  };

  const updateSectionName = (sectionIndex: number, value: string) => {
    setSections((current) =>
      current.map((section, currentSectionIndex) =>
        currentSectionIndex === sectionIndex
          ? { ...section, name: value }
          : section,
      ),
    );
  };

  const addSection = () => {
    setSections((current) => [
      ...current,
      {
        name: `Section ${current.length + 1}`,
        sortOrder: current.length + 1,
        lineItems: [],
      },
    ]);
  };

  const addLineItem = (sectionIndex: number) => {
    setSections((current) =>
      current.map((section, currentSectionIndex) => {
        if (currentSectionIndex !== sectionIndex) {
          return section;
        }

        return {
          ...section,
          lineItems: [
            ...section.lineItems,
            {
              sortOrder: section.lineItems.length + 1,
              lineType: "service",
              description: "",
              unit: "day",
              quantity: 1,
              rate: 0,
              amount: 0,
              disciplineId: "",
              subcategoryKey: "",
              revenueCategoryKey: "",
              notes: "",
            },
          ],
        };
      }),
    );
  };

  return (
    <div className="space-y-6">
      {error ? (
        <ErrorState description={error} title="Quote action failed" />
      ) : null}
      <div className="grid gap-4 md:grid-cols-3">
        <SummaryStat
          hint="Current editable subtotal."
          label="Subtotal"
          value={formatCurrency(computedSubtotal, currencyCode)}
        />
        <SummaryStat
          hint="Current tax amount for the working version."
          label="Tax"
          value={formatCurrency(taxAmount, currencyCode)}
        />
        <SummaryStat
          hint="Subtotal plus tax."
          label="Total"
          value={formatCurrency(computedTotal, currencyCode)}
        />
      </div>

      <SectionCard
        title="Quote Selection"
        description="Select the project quote you want to edit or create a new one."
      >
        <div className="grid gap-4 md:grid-cols-[minmax(0,320px)_1fr]">
          <SelectField
            label="Quote"
            onChange={(event) => {
              setSelectedQuoteId(event.target.value || null);
              setSelectedVersionId(null);
            }}
            value={selectedQuoteId ?? ""}
          >
            {availableQuotes.length === 0 ? (
              <option value="">No quotes yet</option>
            ) : null}
            {availableQuotes.map((quote) => (
              <option key={quote.id} value={quote.id}>
                {quote.title ?? quote.quoteNumber ?? quote.id}
              </option>
            ))}
          </SelectField>
          <div className="flex flex-wrap gap-2 self-end">
            <Button
              onClick={() => {
                setError(null);
                createQuoteMutation.mutate();
              }}
              type="button"
              variant="primary"
            >
              {createQuoteMutation.isPending ? "Creating..." : "Create quote"}
            </Button>
          </div>
        </div>
      </SectionCard>

      {selectedQuoteId && quoteQuery.data ? (
        <>
          <SectionCard
            title="Quote Header"
            description="Core quote container values used across all versions."
          >
            <div className="grid gap-4 md:grid-cols-2">
              <TextInput
                label="Quote number"
                onChange={(event) => setQuoteNumber(event.target.value)}
                value={quoteNumber}
              />
              <TextInput
                label="Quote title"
                onChange={(event) => setQuoteTitle(event.target.value)}
                value={quoteTitle}
              />
            </div>
            <div className="mt-4">
              <InlineActionBar>
                <Button
                  onClick={() => {
                    setError(null);
                    updateQuoteMutation.mutate();
                  }}
                  type="button"
                  variant="primary"
                >
                  {updateQuoteMutation.isPending
                    ? "Saving..."
                    : "Save quote header"}
                </Button>
                {quoteQuery.data.currentVersionStatus ? (
                  <StatusBadge value={quoteQuery.data.currentVersionStatus} />
                ) : null}
              </InlineActionBar>
            </div>
          </SectionCard>

          <SectionCard
            title="Quote Version"
            description="Select and edit a specific quote version for this project."
          >
            <div className="grid gap-4 md:grid-cols-2">
              <SelectField
                label="Version"
                onChange={(event) => setSelectedVersionId(event.target.value)}
                value={selectedVersionId ?? ""}
              >
                {versionOptions.map((version) => (
                  <option key={version.id} value={version.id}>
                    V{version.versionNumber} ·{" "}
                    {formatStatusLabel(version.status)}
                  </option>
                ))}
              </SelectField>
              <div className="self-end text-sm text-slate-600">
                {versionQuery.data ? (
                  <>
                    Version status{" "}
                    <StatusBadge
                      className="ml-2"
                      value={versionQuery.data.status}
                    />
                  </>
                ) : (
                  "Select a version to edit."
                )}
              </div>
            </div>
          </SectionCard>
        </>
      ) : (
        <EmptyState
          description="Create the first quote for this project to begin building sections and line items."
          title="No quote selected"
        />
      )}

      {versionQuery.data ? (
        <>
          <SectionCard
            title="Version Metadata"
            description="Editable values that control the current quote version."
          >
            <div className="grid gap-4 md:grid-cols-2">
              <TextInput
                label="Version title"
                onChange={(event) => setVersionTitle(event.target.value)}
                value={versionTitle}
              />
              <TextInput
                label="Currency code"
                onChange={(event) =>
                  setCurrencyCode(event.target.value.toUpperCase())
                }
                value={currencyCode}
              />
              <TextInput
                label="Source version label"
                onChange={(event) => setSourceVersionLabel(event.target.value)}
                value={sourceVersionLabel}
              />
              <TextInput
                label="Source document date"
                onChange={(event) => setSourceDocumentDate(event.target.value)}
                type="date"
                value={sourceDocumentDate}
              />
              <TextInput
                label="Tax amount"
                onChange={(event) => setTaxAmount(Number(event.target.value))}
                step="0.01"
                type="number"
                value={String(taxAmount)}
              />
              <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
                <p>
                  Current version:{" "}
                  <strong>V{versionQuery.data.versionNumber}</strong>
                </p>
                <p>Issued at: {formatDate(versionQuery.data.issuedAt)}</p>
              </div>
            </div>
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              <TextAreaField
                label="Client-facing notes"
                onChange={(event) => setClientFacingNotes(event.target.value)}
                value={clientFacingNotes}
              />
              <TextAreaField
                label="Internal notes"
                onChange={(event) => setInternalNotes(event.target.value)}
                value={internalNotes}
              />
            </div>
            <div className="mt-6 rounded-lg border border-slate-200 bg-slate-50 p-4">
              <p className="text-sm font-semibold text-slate-900">
                Predictive pricing context
              </p>
              <p className="mt-1 text-sm text-slate-600">
                These structured commercial inputs improve quote recommendations, variance, and win-probability scoring without hiding user edits.
              </p>
              <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-5">
                <TextInput
                  label="Discount %"
                  onChange={(event) => setDiscountPercent(event.target.value)}
                  step="0.1"
                  type="number"
                  value={discountPercent}
                />
                <TextInput
                  label="Margin %"
                  onChange={(event) => setMarginPercent(event.target.value)}
                  step="0.1"
                  type="number"
                  value={marginPercent}
                />
                <TextInput
                  label="Third-party cost %"
                  onChange={(event) => setThirdPartyCostPercent(event.target.value)}
                  step="0.1"
                  type="number"
                  value={thirdPartyCostPercent}
                />
                <TextInput
                  label="Review cycles"
                  onChange={(event) => setReviewCycleCount(event.target.value)}
                  step="1"
                  type="number"
                  value={reviewCycleCount}
                />
                <SelectField
                  label="External vendor usage"
                  onChange={(event) => setExternalVendorUsage(event.target.value)}
                  value={externalVendorUsage}
                >
                  <option value="no">No</option>
                  <option value="yes">Yes</option>
                </SelectField>
              </div>

              <div className="mt-6 rounded-lg border border-slate-200 bg-white p-4">
                <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
                  <div>
                    <p className="text-sm font-semibold text-slate-900">
                      Comparable quote guidance
                    </p>
                    <p className="mt-1 text-sm text-slate-600">
                      Advisory only. Comparable evidence can inform this version, but quote sections and line items remain manual.
                    </p>
                  </div>
                  {predictiveGuidanceQuery.data ? (
                    <StatusBadge value={predictiveGuidanceQuery.data.fallbackTier} />
                  ) : null}
                </div>

                {predictiveGuidanceQuery.isLoading ? (
                  <p className="mt-4 text-sm text-slate-600">
                    Loading comparable guidance for this quote version.
                  </p>
                ) : predictiveGuidanceQuery.isError ? (
                  <p className="mt-4 text-sm text-amber-700">
                    Comparable guidance is currently unavailable for this quote version.
                  </p>
                ) : predictiveGuidance ? (
                  <>
                    <div className="mt-4 grid gap-4 md:grid-cols-3">
                      <SummaryStat
                        label="Likely quote median"
                        value={
                          predictiveGuidance.likelyQuoteRange
                            ? formatCurrency(
                                predictiveGuidance.likelyQuoteRange.median,
                                predictiveGuidance.likelyQuoteRange.currencyCode,
                              )
                            : "Not available"
                        }
                        hint={
                          predictiveGuidance.likelyQuoteRange
                            ? `${formatCurrency(
                                predictiveGuidance.likelyQuoteRange.low,
                                predictiveGuidance.likelyQuoteRange.currencyCode,
                              )} to ${formatCurrency(
                                predictiveGuidance.likelyQuoteRange.high,
                                predictiveGuidance.likelyQuoteRange.currencyCode,
                              )}`
                            : "Comparable quote history is still thin"
                        }
                      />
                      <SummaryStat
                        label="Top comparables"
                        value={predictiveGuidance.topComparables?.length ?? 0}
                        hint={`${predictiveGuidance.modelInfo.comparableProjectsUsed} comparable projects used`}
                      />
                      <SummaryStat
                        label="Feature readiness"
                        value={`${predictiveGuidance.featureReadinessScore.toFixed(0)}%`}
                        hint={`${predictiveGuidance.dataSufficiencyScore.toFixed(0)}% data sufficiency`}
                      />
                    </div>
                    <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-4">
                      <p className="text-sm font-semibold text-slate-900">
                        Advisory predicted spend comparison
                      </p>
                      <p className="mt-1 text-sm text-slate-600">
                        Predicted spend is advisory only. It does not write quote totals or change revenue forecasts.
                      </p>
                      <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                        <SummaryStat
                          label="Quote total"
                          value={formatCurrency(computedTotal, currencyCode)}
                        />
                        <SummaryStat
                          label="Predicted spend"
                          value={
                            advisorySpend?.predictedTotalCost != null
                              ? formatCurrency(advisorySpend.predictedTotalCost, currencyCode)
                              : "Not available"
                          }
                          hint={advisorySpend ? formatStatusLabel(advisorySpend.confidence) : "No spend scenario output"}
                        />
                        <SummaryStat
                          label="Gap (quote - predicted spend)"
                          value={
                            advisorySpend?.predictedTotalCost != null
                              ? formatCurrency(computedTotal - advisorySpend.predictedTotalCost, currencyCode)
                              : "Not available"
                          }
                        />
                        <SummaryStat
                          label="Implied margin (advisory)"
                          value={
                            advisorySpend?.impliedMarginPct != null
                              ? `${advisorySpend.impliedMarginPct.toFixed(1)}%`
                              : "Not available"
                          }
                          hint="Based on predicted spend, not final actuals"
                        />
                      </div>
                    </div>

                    {predictiveGuidance.disciplineUsage.length > 0 ? (
                      <div className="mt-4 overflow-x-auto">
                        <table className="min-w-full divide-y divide-slate-200 text-sm">
                          <thead>
                            <tr className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                              <th className="px-3 py-2">Discipline</th>
                              <th className="px-3 py-2">Likely share</th>
                              <th className="px-3 py-2">Likely amount</th>
                              <th className="px-3 py-2">Confidence</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-200">
                            {predictiveGuidance.disciplineUsage
                              .slice(0, 4)
                              .map((item) => (
                                <tr key={item.disciplineId}>
                                  <td className="px-3 py-2 font-medium text-slate-900">
                                    {item.disciplineName ??
                                      item.disciplineCode ??
                                      item.disciplineId}
                                  </td>
                                  <td className="px-3 py-2 text-slate-700">
                                    {item.predictedSharePct.toFixed(1)}%
                                  </td>
                                  <td className="px-3 py-2 text-slate-700">
                                    {item.predictedAmountMedian == null
                                      ? "Not available"
                                      : formatCurrency(
                                          item.predictedAmountMedian,
                                          predictiveGuidance.target.quoteCurrencyCode,
                                        )}
                                  </td>
                                  <td className="px-3 py-2">
                                    <StatusBadge value={item.confidence} />
                                  </td>
                                </tr>
                              ))}
                          </tbody>
                        </table>
                      </div>
                    ) : null}

                    {advisorySpend?.disciplineSpend?.length ? (
                      <div className="mt-4 overflow-x-auto">
                        <table className="min-w-full divide-y divide-slate-200 text-sm">
                          <thead>
                            <tr className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                              <th className="px-3 py-2">Discipline</th>
                              <th className="px-3 py-2">Quoted</th>
                              <th className="px-3 py-2">Predicted spend</th>
                              <th className="px-3 py-2">Gap</th>
                              <th className="px-3 py-2">Confidence</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-200">
                            {advisorySpend.disciplineSpend.map((item) => {
                              const quoted = quoteByDiscipline[item.disciplineId] ?? 0;
                              const predicted = item.predictedTotalCost ?? 0;
                              return (
                                <tr key={item.disciplineId}>
                                  <td className="px-3 py-2 font-medium text-slate-900">
                                    {item.disciplineName ?? item.disciplineCode ?? item.disciplineId}
                                  </td>
                                  <td className="px-3 py-2 text-slate-700">
                                    {formatCurrency(quoted, currencyCode)}
                                  </td>
                                  <td className="px-3 py-2 text-slate-700">
                                    {item.predictedTotalCost != null
                                      ? formatCurrency(item.predictedTotalCost, currencyCode)
                                      : "Not available"}
                                  </td>
                                  <td className="px-3 py-2 text-slate-700">
                                    {item.predictedTotalCost != null
                                      ? formatCurrency(quoted - predicted, currencyCode)
                                      : "Not available"}
                                  </td>
                                  <td className="px-3 py-2">
                                    <StatusBadge value={item.confidence} />
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    ) : null}
                  </>
                ) : (
                  <p className="mt-4 text-sm text-slate-600">
                    No comparable guidance is available for this quote version yet.
                  </p>
                )}
              </div>
            </div>
          </SectionCard>

          <SectionCard
            actions={
              <Button onClick={addSection} type="button" variant="secondary">
                Add section
              </Button>
            }
            title="Sections and Line Items"
            description="Edit the commercial structure of the quote version. Totals are recalculated from the line items below."
          >
            <div className="space-y-6">
              {sections.map((section, sectionIndex) => (
                <div
                  className="space-y-4 rounded-lg border border-slate-200 p-4"
                  key={section.sortOrder}
                >
                  <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                    <TextInput
                      className="md:max-w-md"
                      label={`Section ${section.sortOrder}`}
                      onChange={(event) =>
                        updateSectionName(sectionIndex, event.target.value)
                      }
                      value={section.name}
                    />
                    <Button
                      onClick={() => addLineItem(sectionIndex)}
                      type="button"
                      variant="ghost"
                    >
                      Add line item
                    </Button>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-slate-200 text-sm">
                      <thead>
                        <tr className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                          <th className="px-3 py-2">Discipline</th>
                          <th className="px-3 py-2">Subcategory</th>
                          <th className="px-3 py-2">Revenue category</th>
                          <th className="px-3 py-2">Description</th>
                          <th className="px-3 py-2">Unit</th>
                          <th className="px-3 py-2">Qty</th>
                          <th className="px-3 py-2">Rate</th>
                          <th className="px-3 py-2">Amount</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-200">
                        {section.lineItems.map((lineItem, lineIndex) => (
                          <tr
                            key={`${section.sortOrder}-${lineItem.sortOrder}`}
                          >
                            <td className="px-3 py-2">
                              <SelectField
                                label=""
                                onChange={(event) =>
                                  updateLine(
                                    sectionIndex,
                                    lineIndex,
                                    "disciplineId",
                                    event.target.value,
                                  )
                                }
                                value={lineItem.disciplineId}
                              >
                                <option value="">No discipline</option>
                                {disciplineQuery.data.items.map((discipline) => (
                                  <option key={discipline.id} value={discipline.id}>
                                    {discipline.name}
                                  </option>
                                ))}
                              </SelectField>
                            </td>
                            <td className="px-3 py-2">
                              <TextInput
                                onChange={(event) =>
                                  updateLine(
                                    sectionIndex,
                                    lineIndex,
                                    "subcategoryKey",
                                    event.target.value,
                                  )
                                }
                                value={lineItem.subcategoryKey}
                              />
                            </td>
                            <td className="px-3 py-2">
                              <TextInput
                                onChange={(event) =>
                                  updateLine(
                                    sectionIndex,
                                    lineIndex,
                                    "revenueCategoryKey",
                                    event.target.value,
                                  )
                                }
                                value={lineItem.revenueCategoryKey}
                              />
                            </td>
                            <td className="px-3 py-2">
                              <TextInput
                                onChange={(event) =>
                                  updateLine(
                                    sectionIndex,
                                    lineIndex,
                                    "description",
                                    event.target.value,
                                  )
                                }
                                value={lineItem.description}
                              />
                            </td>
                            <td className="px-3 py-2">
                              <TextInput
                                onChange={(event) =>
                                  updateLine(
                                    sectionIndex,
                                    lineIndex,
                                    "unit",
                                    event.target.value,
                                  )
                                }
                                value={lineItem.unit}
                              />
                            </td>
                            <td className="px-3 py-2">
                              <TextInput
                                onChange={(event) =>
                                  updateLine(
                                    sectionIndex,
                                    lineIndex,
                                    "quantity",
                                    event.target.value,
                                  )
                                }
                                step="0.01"
                                type="number"
                                value={String(lineItem.quantity)}
                              />
                            </td>
                            <td className="px-3 py-2">
                              <TextInput
                                onChange={(event) =>
                                  updateLine(
                                    sectionIndex,
                                    lineIndex,
                                    "rate",
                                    event.target.value,
                                  )
                                }
                                step="0.01"
                                type="number"
                                value={String(lineItem.rate)}
                              />
                            </td>
                            <td className="px-3 py-2 text-right font-medium text-slate-900">
                              {formatCurrency(lineItem.amount, currencyCode)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ))}
            </div>
          </SectionCard>

          <InlineActionBar sticky>
            <Button
              onClick={() => {
                setError(null);
                updateVersionMutation.mutate();
              }}
              type="button"
              variant="primary"
            >
              {updateVersionMutation.isPending
                ? "Saving version..."
                : "Save version"}
            </Button>
            <Button
              onClick={() => {
                setError(null);
                createVersionMutation.mutate();
              }}
              type="button"
            >
              {createVersionMutation.isPending
                ? "Creating version..."
                : "Create next version"}
            </Button>
            <Button
              onClick={() => {
                setError(null);
                issueVersionMutation.mutate();
              }}
              type="button"
              variant={
                versionQuery.data.status === ("issued" as QuoteVersionStatus)
                  ? "ghost"
                  : "secondary"
              }
            >
              {issueVersionMutation.isPending ? "Issuing..." : "Issue version"}
            </Button>
          </InlineActionBar>
        </>
      ) : null}
    </div>
  );
}
