/**
 * Quote a CSV field: wrap when it contains a delimiter, quote, or newline.
 *
 * A string that starts with = + - @ (or a tab or carriage return) is read as
 * a formula by Excel and Sheets. Keywords, page paths, prompts and group names
 * all come from third parties, so such a cell would run on whoever opens the
 * export. It is prefixed with an apostrophe, which spreadsheets treat as
 * "this is text". Numbers are left alone, so -3 stays a number.
 */
export function csvCell(value: unknown): string {
  if (value === null || value === undefined) return "";
  let text = String(value);
  if (typeof value === "string" && /^[=+\-@\t\r]/.test(text)) text = `'${text}`;
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
