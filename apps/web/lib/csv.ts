/** Quote a CSV field: wrap when it contains a delimiter, quote, or newline. */
export function csvCell(value: unknown): string {
  if (value === null || value === undefined) return "";
  const text = String(value);
  if (/[",\r\n]/.test(text)) {
    return `"${text.replaceAll('"', '""')}"`;
  }
  return text;
}

export function csvRow(cells: unknown[]): string {
  return cells.map(csvCell).join(",");
}

export type CsvSection = {
  /** Section banner written above the table. */
  title: string;
  headers: string[];
  rows: unknown[][];
};

/**
 * Render sections into one CSV file, separated by a blank line. Excel and
 * Sheets both read this as a single sheet with labelled blocks.
 */
export function renderCsvSections(sections: CsvSection[]): string {
  const lines: string[] = [];
  sections.forEach((section, index) => {
    if (index > 0) lines.push("");
    lines.push(csvRow([section.title]));
    lines.push(csvRow(section.headers));
    for (const row of section.rows) {
      lines.push(csvRow(row));
    }
  });
  // Leading BOM keeps Excel from mangling non-ASCII on open.
  return `﻿${lines.join("\r\n")}\r\n`;
}
