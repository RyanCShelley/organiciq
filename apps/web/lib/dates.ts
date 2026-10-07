export function defaultDateRange(days = 90): { from: string; to: string } {
  const to = new Date();
  const from = new Date();
  from.setUTCDate(to.getUTCDate() - (days - 1));
  return {
    from: from.toISOString().slice(0, 10),
    to: to.toISOString().slice(0, 10),
  };
}

/** Inclusive UTC window for sync job APIs (`start_date` / `end_date`). */
export function syncJobWindow(days: number): { start_date: string; end_date: string } {
  const { from, to } = defaultDateRange(days);
  return { start_date: from, end_date: to };
}

