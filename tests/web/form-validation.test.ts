import { describe, expect, it } from "vitest";

import {
  MAX_CETA_EXPORT_SIZE_BYTES,
  MAX_QUOTE_PDF_SIZE_BYTES,
  validateCetaExportFile,
  validateLoginCredentials,
  validateProjectCreateForm,
  validateQuotePdfFile
} from "../../apps/web/lib/forms/validation";

describe("form validation helpers", () => {
  it("requires usable login credentials before submission", () => {
    expect(validateLoginCredentials("", "")).toBe("Email is required.");
    expect(validateLoginCredentials("user@example.com", "short")).toBe(
      "Password must be at least 12 characters."
    );
    expect(validateLoginCredentials("user@example.com", "long-enough-pass")).toBeNull();
  });

  it("rejects invalid quote PDF uploads early", () => {
    expect(validateQuotePdfFile(null)).toBe("Choose a PDF file before uploading.");
    expect(
      validateQuotePdfFile({
        name: "quote.txt",
        size: 128,
        type: "text/plain"
      })
    ).toBe("Quote ingestion only accepts PDF files.");
    expect(
      validateQuotePdfFile({
        name: "quote.pdf",
        size: MAX_QUOTE_PDF_SIZE_BYTES + 1,
        type: "application/pdf"
      })
    ).toBe("PDF uploads must be 25 MB or smaller.");
  });

  it("rejects invalid CETA imports before upload", () => {
    expect(validateCetaExportFile(null)).toBe("Choose a CETA export first.");
    expect(
      validateCetaExportFile({
        name: "actuals.pdf",
        size: 256,
        type: "application/pdf"
      })
    ).toBe("CETA imports require a .csv, .xls, or .xlsx export.");
    expect(
      validateCetaExportFile({
        name: "actuals.csv",
        size: MAX_CETA_EXPORT_SIZE_BYTES + 1,
        type: "text/csv"
      })
    ).toBe("CETA exports must be 10 MB or smaller.");
  });

  it("requires a usable manual project intake payload", () => {
    expect(
      validateProjectCreateForm({
        name: "",
        code: "",
        cadenceProfileType: "",
        description: "",
        status: "bid",
        quoteCurrencyCode: "",
        bidDueDate: "",
        estimatedExecutionEndDate: "",
        estimatedExecutionStartDate: "",
        revenueAllocationMethod: "cadence_profile",
        startDate: "",
        endDate: ""
      })
    ).toBe("Project name is required.");

    expect(
      validateProjectCreateForm({
        name: "Manual Intake",
        code: "",
        cadenceProfileType: "",
        description: "",
        status: "bid",
        quoteCurrencyCode: "GB",
        bidDueDate: "",
        estimatedExecutionEndDate: "",
        estimatedExecutionStartDate: "",
        revenueAllocationMethod: "cadence_profile",
        startDate: "",
        endDate: ""
      })
    ).toBe("Quote currency must be a 3-letter ISO currency code.");

    expect(
      validateProjectCreateForm({
        name: "Manual Intake",
        code: "",
        cadenceProfileType: "",
        description: "",
        status: "bid",
        quoteCurrencyCode: "GBP",
        bidDueDate: "",
        estimatedExecutionEndDate: "",
        estimatedExecutionStartDate: "",
        revenueAllocationMethod: "cadence_profile",
        startDate: "2026-04-10",
        endDate: "2026-04-01"
      })
    ).toBe("Project end date cannot be earlier than start date.");

    expect(
      validateProjectCreateForm({
        name: "Manual Intake",
        code: "",
        cadenceProfileType: "",
        description: "",
        status: "bid",
        quoteCurrencyCode: "GBP",
        bidDueDate: "",
        estimatedExecutionEndDate: "2026-05-01",
        estimatedExecutionStartDate: "2026-05-10",
        revenueAllocationMethod: "cadence_profile",
        startDate: "2026-04-01",
        endDate: "2026-04-10"
      })
    ).toBe(
      "Estimated execution end date cannot be earlier than estimated execution start date."
    );

    expect(
      validateProjectCreateForm({
        name: "Manual Intake",
        code: "",
        cadenceProfileType: "",
        description: "",
        status: "bid",
        quoteCurrencyCode: "GBP",
        bidDueDate: "",
        estimatedExecutionEndDate: "2026-05-10",
        estimatedExecutionStartDate: "2026-05-01",
        revenueAllocationMethod: "cadence_profile",
        startDate: "2026-04-01",
        endDate: "2026-04-10"
      })
    ).toBeNull();

    expect(
      validateProjectCreateForm({
        name: "Manual Intake",
        code: "",
        cadenceProfileType: "front_loaded",
        description: "",
        status: "bid",
        quoteCurrencyCode: "GBP",
        bidDueDate: "",
        estimatedExecutionEndDate: "2026-05-10",
        estimatedExecutionStartDate: "2026-05-01",
        revenueAllocationMethod: "cadence_profile",
        startDate: "2026-04-01",
        endDate: "2026-04-10"
      })
    ).toBeNull();
  });
});
