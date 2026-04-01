"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import type {
  QuoteSummary,
  QuoteVersionRead,
  QuoteVersionSummary,
} from "@quotes4/contracts";

import { getBrowserApiClient } from "@/lib/api/browser-client";
import { formatCurrency, formatDate, formatStatusLabel } from "@/lib/format";
import { queryKeys } from "@/lib/query/keys";

import { SelectField } from "@/components/forms/select-field";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { SectionCard } from "@/components/ui/section-card";
import { SummaryStat } from "@/components/ui/summary-stat";
import { StatusBadge } from "@/components/ui/status-badge";

function VersionPanel({ version }: { version: QuoteVersionRead }) {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <StatusBadge value={version.status} />
        <p className="text-sm text-slate-600">
          Issued: {formatDate(version.issuedAt)} · Total:{" "}
          {formatCurrency(version.totalAmount, version.currencyCode)}
        </p>
      </div>
      {version.sections.map((section) => (
        <div
          className="rounded-lg border border-slate-200 p-4"
          key={section.id}
        >
          <div className="flex items-center justify-between gap-3">
            <h3 className="text-sm font-semibold text-slate-900">
              {section.name}
            </h3>
            <span className="text-sm text-slate-600">
              {formatCurrency(section.subtotalAmount, version.currencyCode)}
            </span>
          </div>
          <div className="mt-3 overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead>
                <tr className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                  <th className="px-3 py-2">Description</th>
                  <th className="px-3 py-2">Qty</th>
                  <th className="px-3 py-2">Rate</th>
                  <th className="px-3 py-2">Amount</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200">
                {section.lineItems.map((lineItem) => (
                  <tr key={lineItem.id}>
                    <td className="px-3 py-2">{lineItem.description}</td>
                    <td className="px-3 py-2">
                      {lineItem.quantity} {lineItem.unit}
                    </td>
                    <td className="px-3 py-2">
                      {formatCurrency(lineItem.rate, version.currencyCode)}
                    </td>
                    <td className="px-3 py-2 font-medium text-slate-900">
                      {formatCurrency(lineItem.amount, version.currencyCode)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </div>
  );
}

export function QuoteVersionComparison({ quotes }: { quotes: QuoteSummary[] }) {
  const api = getBrowserApiClient();
  const [selectedQuoteId, setSelectedQuoteId] = useState(quotes[0]?.id ?? "");
  const versionsQuery = useQuery({
    enabled: Boolean(selectedQuoteId),
    queryFn: async () => api.listQuoteVersions(selectedQuoteId),
    queryKey: queryKeys.quoteVersions(selectedQuoteId || "none"),
  });

  const versions = versionsQuery.data ?? [];
  const [leftVersionId, setLeftVersionId] = useState("");
  const [rightVersionId, setRightVersionId] = useState("");

  useEffect(() => {
    if (versions.length === 0) {
      return;
    }

    setLeftVersionId(
      (current) => current || versions[versions.length - 1]?.id || "",
    );
    setRightVersionId(
      (current) =>
        current ||
        versions[Math.max(versions.length - 2, 0)]?.id ||
        versions[0]?.id ||
        "",
    );
  }, [versions]);

  const leftVersionQuery = useQuery({
    enabled: Boolean(leftVersionId),
    queryFn: async () => api.getQuoteVersion(leftVersionId),
    queryKey: queryKeys.quoteVersion(leftVersionId || "none"),
  });

  const rightVersionQuery = useQuery({
    enabled: Boolean(rightVersionId),
    queryFn: async () => api.getQuoteVersion(rightVersionId),
    queryKey: queryKeys.quoteVersion(rightVersionId || "none"),
  });

  if (quotes.length === 0) {
    return (
      <EmptyState
        description="Create a quote for this project before comparing versions."
        title="No quotes available"
      />
    );
  }

  if (versions.length < 2) {
    return (
      <EmptyState
        description="Create at least two quote versions before opening side-by-side comparison."
        title="Not enough versions"
      />
    );
  }

  const leftVersion = leftVersionQuery.data;
  const rightVersion = rightVersionQuery.data;
  const totalDelta =
    leftVersion && rightVersion
      ? leftVersion.totalAmount - rightVersion.totalAmount
      : null;

  return (
    <div className="space-y-6">
      <SectionCard
        title="Comparison Selection"
        description="Choose the quote and the two versions you want to compare."
      >
        <div className="grid gap-4 md:grid-cols-3">
          <SelectField
            label="Quote"
            onChange={(event) => setSelectedQuoteId(event.target.value)}
            value={selectedQuoteId}
          >
            {quotes.map((quote) => (
              <option key={quote.id} value={quote.id}>
                {quote.title ?? quote.quoteNumber ?? quote.id}
              </option>
            ))}
          </SelectField>
          <SelectField
            label="Left version"
            onChange={(event) => setLeftVersionId(event.target.value)}
            value={leftVersionId}
          >
            {versions.map((version: QuoteVersionSummary) => (
              <option key={version.id} value={version.id}>
                V{version.versionNumber} · {formatStatusLabel(version.status)}
              </option>
            ))}
          </SelectField>
          <SelectField
            label="Right version"
            onChange={(event) => setRightVersionId(event.target.value)}
            value={rightVersionId}
          >
            {versions.map((version: QuoteVersionSummary) => (
              <option key={version.id} value={version.id}>
                V{version.versionNumber} · {formatStatusLabel(version.status)}
              </option>
            ))}
          </SelectField>
        </div>
      </SectionCard>

      {leftVersion && rightVersion ? (
        <>
          <div className="grid gap-4 md:grid-cols-3">
            <SummaryStat
              label="Left total"
              value={formatCurrency(
                leftVersion.totalAmount,
                leftVersion.currencyCode,
              )}
            />
            <SummaryStat
              label="Right total"
              value={formatCurrency(
                rightVersion.totalAmount,
                rightVersion.currencyCode,
              )}
            />
            <SummaryStat
              hint="Left minus right."
              label="Total delta"
              value={formatCurrency(totalDelta ?? 0, leftVersion.currencyCode)}
            />
          </div>
          <div className="grid gap-6 xl:grid-cols-2">
            <SectionCard
              title={`Version ${leftVersion.versionNumber}`}
              description={leftVersion.title ?? "No title"}
            >
              <VersionPanel version={leftVersion} />
            </SectionCard>
            <SectionCard
              title={`Version ${rightVersion.versionNumber}`}
              description={rightVersion.title ?? "No title"}
            >
              <VersionPanel version={rightVersion} />
            </SectionCard>
          </div>
        </>
      ) : (
        <ErrorState
          description="Both quote versions must load before comparison can render."
          title="Comparison unavailable"
        />
      )}
    </div>
  );
}
