import type { ReactNode } from "react";

/** **bold** and `code` inside a line. Nothing else is interpreted, and nothing is ever inserted as HTML. */
function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={i}>{part.slice(2, -2)}</strong>;
    if (part.startsWith("`") && part.endsWith("`")) return <code key={i} className="rounded bg-[var(--bg)] px-1 text-[0.85em]">{part.slice(1, -1)}</code>;
    return part;
  });
}

const cells = (line: string) => line.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
const isRule = (line: string) => /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(line);

/** The small part of Markdown an answer uses: paragraphs, headings, bullet and numbered lists, and tables. */
export function Markdown({ text }: { text: string }) {
  const lines = text.replace(/\r/g, "").split("\n");
  const out: ReactNode[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i++;
      continue;
    }
    if (line.includes("|") && i + 1 < lines.length && isRule(lines[i + 1])) {
      const head = cells(line);
      const rows: string[][] = [];
      i += 2;
      while (i < lines.length && lines[i].includes("|") && lines[i].trim()) rows.push(cells(lines[i++]));
      out.push(
        <div key={out.length} className="my-3 overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr>{head.map((h, k) => <th key={k} className="px-3 py-1.5 text-left text-xs font-semibold uppercase tracking-wide text-[var(--text-tertiary)]">{inline(h)}</th>)}</tr></thead>
            <tbody>{rows.map((r, k) => <tr key={k} className="border-t border-[var(--border)]">{r.map((c, j) => <td key={j} className="px-3 py-1.5 tabular-nums">{inline(c)}</td>)}</tr>)}</tbody>
          </table>
        </div>,
      );
      continue;
    }
    const heading = /^(#{1,4})\s+(.*)$/.exec(line);
    if (heading) {
      out.push(<h4 key={out.length} className="mt-4 text-sm font-bold">{inline(heading[2])}</h4>);
      i++;
      continue;
    }
    if (/^\s*[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) items.push(lines[i++].replace(/^\s*[-*]\s+/, ""));
      out.push(<ul key={out.length} className="my-2 list-disc space-y-1 pl-5">{items.map((t, k) => <li key={k}>{inline(t)}</li>)}</ul>);
      continue;
    }
    if (/^\s*\d+[.)]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) items.push(lines[i++].replace(/^\s*\d+[.)]\s+/, ""));
      out.push(<ol key={out.length} className="my-2 list-decimal space-y-1 pl-5">{items.map((t, k) => <li key={k}>{inline(t)}</li>)}</ol>);
      continue;
    }
    const para: string[] = [];
    while (i < lines.length && lines[i].trim() && !/^\s*([-*]|\d+[.)])\s+/.test(lines[i]) && !/^#{1,4}\s/.test(lines[i]) && !(lines[i].includes("|") && i + 1 < lines.length && isRule(lines[i + 1]))) para.push(lines[i++]);
    out.push(<p key={out.length} className="my-2">{inline(para.join(" "))}</p>);
  }
  return <div className="text-sm leading-relaxed">{out}</div>;
}
