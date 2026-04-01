import type { ProjectStatus } from "@quotes4/contracts";

export interface SelectedFileLike {
  name: string;
  size: number;
  type: string;
}

export interface ProjectCreateFormValues {
  code: string;
  description: string;
  endDate: string;
  name: string;
  quoteCurrencyCode: string;
  startDate: string;
  status: ProjectStatus;
  bidDueDate: string;
}

export const MAX_QUOTE_PDF_SIZE_BYTES = 25 * 1024 * 1024;
export const MAX_CETA_EXPORT_SIZE_BYTES = 10 * 1024 * 1024;

const CETA_EXTENSIONS = new Set(["csv", "xls", "xlsx"]);
const CETA_TYPES = new Set([
  "",
  "application/vnd.ms-excel",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "text/csv",
  "text/plain"
]);
const PDF_TYPES = new Set(["", "application/pdf"]);
const ISO_CURRENCY_CODE_PATTERN = /^[A-Za-z]{3}$/;

function fileExtension(fileName: string): string {
  const parts = fileName.toLowerCase().split(".");
  return parts.length > 1 ? parts.at(-1) ?? "" : "";
}

export function validateLoginCredentials(email: string, password: string): string | null {
  if (!email.trim()) {
    return "Email is required.";
  }
  if (!password) {
    return "Password is required.";
  }
  if (password.length < 12) {
    return "Password must be at least 12 characters.";
  }
  return null;
}

export function validateQuotePdfFile(file: SelectedFileLike | null): string | null {
  if (!file) {
    return "Choose a PDF file before uploading.";
  }
  if (file.size <= 0) {
    return "The selected PDF file is empty.";
  }
  if (file.size > MAX_QUOTE_PDF_SIZE_BYTES) {
    return "PDF uploads must be 25 MB or smaller.";
  }
  if (fileExtension(file.name) !== "pdf" || !PDF_TYPES.has(file.type)) {
    return "Quote ingestion only accepts PDF files.";
  }
  return null;
}

export function validateCetaExportFile(file: SelectedFileLike | null): string | null {
  if (!file) {
    return "Choose a CETA export first.";
  }
  if (file.size <= 0) {
    return "The selected CETA export is empty.";
  }
  if (file.size > MAX_CETA_EXPORT_SIZE_BYTES) {
    return "CETA exports must be 10 MB or smaller.";
  }
  if (!CETA_EXTENSIONS.has(fileExtension(file.name)) || !CETA_TYPES.has(file.type)) {
    return "CETA imports require a .csv, .xls, or .xlsx export.";
  }
  return null;
}

export function validateProjectCreateForm(
  values: ProjectCreateFormValues
): string | null {
  if (!values.name.trim()) {
    return "Project name is required.";
  }

  const currencyCode = values.quoteCurrencyCode.trim();
  if (currencyCode && !ISO_CURRENCY_CODE_PATTERN.test(currencyCode)) {
    return "Quote currency must be a 3-letter ISO currency code.";
  }

  if (values.startDate && values.endDate && values.endDate < values.startDate) {
    return "Project end date cannot be earlier than start date.";
  }

  return null;
}
