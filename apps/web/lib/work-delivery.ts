/** Run explicit work operations sequentially and preserve per-task failures. */
export async function runWorkBatch<T>(
  items: { key: string; title: string; alreadySent: boolean; value: T }[],
  send: boolean,
  operation: (value: T) => Promise<{ ok: boolean; error?: string }>,
) {
  const messages: string[] = [],
    deliveredKeys: string[] = [];
  for (const item of items) {
    if (send && item.alreadySent) {
      messages.push(`${item.title}: already delivered`);
      deliveredKeys.push(item.key);
      continue;
    }
    try {
      const result = await operation(item.value);
      if (send && result.ok) deliveredKeys.push(item.key);
      messages.push(
        `${item.title}: ${result.ok ? (send ? "sent to Teamwork" : "assignment saved") : result.error || "Operation failed"}`,
      );
    } catch (error) {
      messages.push(
        `${item.title}: ${error instanceof Error ? error.message : "Operation failed; check this task before retrying"}`,
      );
    }
  }
  return { messages, deliveredKeys };
}
