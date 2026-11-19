import type { ShCheck, ShData, ShPageEntry, ShPageIssue, ShSignal } from "@/lib/site-health";

export type FixOwner = "Developer" | "Content" | "SEO";

export type FixScoreGain = {
  weight: number;
  score: number;
  gain: number;
};

export type FixGroupItem = {
  a: string;
  b?: string;
  c: string;
  href?: string;
};

export type FixGroup = {
  title: string;
  sub: string;
  link?: { label: string; href: string };
  items: FixGroupItem[];
  totalCount: number;
  csvRows: string[][];
};

export type UnifiedFix = {
  id: string;
  name: string;
  seo?: FixScoreGain;
  geo?: FixScoreGain;
  totalGain: number;
  affected: number;
  unit: string;
  owner: FixOwner;
  problem: string;
  steps: string[];
  note?: string;
  toolLink?: { label: string; href: string };
  groups: FixGroup[];
  change?: { newCount: number; fixedCount: number };
};

export type PassingFix = {
  id: string;
  name: string;
  tags: ("SEO" | "GEO")[];
};

export const gainOf = (weight: number, score: number): number =>
  +((weight * (100 - score)) / 100).toFixed(1);

const shortPath = (url: string) => url.replace(/^https?:\/\/[^/]+/, "") || "/";

function classifyTemplate(url: string): "Product template" | "Collection template" | "Blog article template" | "Other pages" {
  const path = shortPath(url).toLowerCase();
  if (path.includes("/product")) return "Product template";
  if (path.includes("/collection") || path.includes("/categor")) return "Collection template";
  if (path.includes("/blog") || path.includes("/article") || path.includes("/news")) return "Blog article template";
  return "Other pages";
}

function templateGroups(urls: string[]): FixGroup[] {
  if (urls.length === 0) return [];
  const buckets: Record<string, string[]> = {
    "Product template": [],
    "Collection template": [],
    "Blog article template": [],
    "Other pages": [],
  };
  for (const u of urls) {
    buckets[classifyTemplate(u)].push(u);
  }
  const items: FixGroupItem[] = Object.entries(buckets)
    .filter(([, list]) => list.length > 0)
    .sort((a, b) => b[1].length - a[1].length)
    .map(([name, list]) => ({
      a: name,
      b: list.slice(0, 2).map(shortPath).join(", "),
      c: `${list.length} ${list.length === 1 ? "page" : "pages"}`,
    }));

  return [
    {
      title: "By template",
      sub: "Fix the template and every page using it is covered",
      items,
      totalCount: items.length,
      csvRows: [["Template", "URL"], ...urls.map((u) => [classifyTemplate(u), u])],
    },
  ];
}

const OWNER_MAP: Record<string, FixOwner> = {
  schema: "Developer",
  indexation: "Developer",
  redirects: "Developer",
  canonicals: "Developer",
  site_files: "Developer",
  faq: "Developer",
  crawler: "Developer",
  citation: "Content",
  depth: "Content",
  attribution: "Content",
  titles: "SEO",
  dup_titles: "SEO",
  descriptions: "SEO",
  dup_descriptions: "SEO",
  entity: "SEO",
  graph: "SEO",
};

type CopySpec = {
  name: string;
  unit: string;
  problem: (affected: number, total?: number) => string;
  steps: string[];
  note?: string;
};

const SEO_COPY: Record<string, CopySpec> = {
  titles: {
    name: "Missing page titles",
    unit: "pages",
    problem: (n, t) => `${n}${t ? ` of ${t}` : ""} indexable pages have no <title> tag, leaving search engines to guess the headline.`,
    steps: [
      "Write a unique, descriptive <title> (50–60 characters) for each page below.",
      "Lead with the primary topic or product name and keep the brand name at the end.",
    ],
  },
  dup_titles: {
    name: "Duplicate page titles",
    unit: "pages",
    problem: (n) => `${n} pages share a title with at least one other page. Search engines can't tell which one should rank.`,
    steps: [
      "Start with the largest groups below.",
      "Give each page a title that leads with what makes it different (size, scent, location, or category).",
      "Keep the brand name at the end.",
    ],
  },
  descriptions: {
    name: "Missing meta descriptions",
    unit: "pages",
    problem: (n, t) => `${n}${t ? ` of ${t}` : ""} pages have no meta description, so search engines auto-generate snippets.`,
    steps: [
      "Write a 140–155 character meta description for each page below.",
      "Include one clear benefit and a reason to click.",
    ],
  },
  dup_descriptions: {
    name: "Duplicate meta descriptions",
    unit: "pages",
    problem: (n) => `${n} pages share a meta description. Search results look identical, which lowers click-through rate.`,
    steps: [
      "Write a unique 140–155 character description for each page, starting with the largest groups.",
      "Mention one specific benefit and one concrete fact.",
    ],
  },
  indexation: {
    name: "Broken pages & indexation errors",
    unit: "pages",
    problem: (n, t) => `${n}${t ? ` of ${t}` : ""} addresses return 4xx/5xx errors or unintended indexation blocks.`,
    steps: [
      "Redirect removed pages (404/410) to their closest live equivalent.",
      "Fix server errors (5xx) and remove unintended noindex directives.",
      "Update any internal links that point to broken URLs.",
    ],
  },
  canonicals: {
    name: "Missing or conflicting canonicals",
    unit: "pages",
    problem: (n) => `${n} indexable pages lack a clean self-referencing canonical URL, risking split ranking signals.`,
    steps: [
      "Add a self-referencing <link rel=\"canonical\"> tag to each affected template or page.",
      "Ensure parameter or trailing-slash variants point to the preferred URL.",
    ],
  },
  redirects: {
    name: "Redirect chains",
    unit: "pages",
    problem: (n) => `${n} addresses pass through multiple redirects before reaching a live page.`,
    steps: [
      "Point the initial redirect directly at the final destination URL.",
      "Update internal links to point straight to the final URL.",
    ],
  },
  site_files: {
    name: "robots.txt and sitemap",
    unit: "checks",
    problem: () => "Crawling or sitemap configuration has an issue that can block discovery of public pages.",
    steps: [
      "Verify robots.txt allows search engines to crawl public pages.",
      "Confirm the XML sitemap is reachable (HTTP 200) and lists canonical URLs.",
    ],
  },
};

const GEO_COPY: Record<string, CopySpec> = {
  citation: {
    name: "AI answers don't cite the site",
    unit: "questions",
    problem: (n) => `${n} high-value AI answer prompts don't cite your site. Strengthening existing pages or filling content gaps closes this.`,
    steps: [
      "For questions with an existing page: add a 2–3 sentence direct answer near the top of that page using the question's wording.",
      "Add concrete facts AI tools can quote: ingredients, sizes, pricing, and who it suits.",
      "For questions with no page: send them to Content gaps to plan new pages.",
    ],
  },
  faq: {
    name: "FAQ markup missing",
    unit: "top pages",
    problem: (n) => `${n} high-visibility pages lack FAQPage schema or structured Q&A, making their answers harder for AI tools to extract.`,
    steps: [
      "Add a short FAQ section (4–6 real customer questions) to each page below.",
      "Mark it up with FAQPage JSON-LD schema.",
      "Use questions people actually ask from People Also Ask and AI prompts.",
    ],
  },
  depth: {
    name: "Answers lack specific detail",
    unit: "pages",
    problem: (n) => `${n} key pages are thin on quotable facts, lowering how specifically AI answers describe the brand.`,
    steps: [
      "Add concrete facts to each page: specs, active ingredients, dimensions, pricing, and who it suits.",
      "Format key facts in a short list or table rather than burying them in paragraphs.",
      "Add a one-line summary near the top of each page.",
    ],
  },
  entity: {
    name: "Brand details unclear",
    unit: "pages",
    problem: (n) => `${n} pages or brand schema entries leave out clear brand, phone, or address details.`,
    steps: [
      "Add phone number, address, and social profiles to Organization schema on the homepage.",
      "Include the brand name consistently in page titles on key pages.",
    ],
  },
  attribution: {
    name: "Answers don't credit a source",
    unit: "answers",
    problem: (n) => `${n} AI answers lack source attribution because supporting pages have no author, date, or cited evidence.`,
    steps: [
      "Add an author with credentials and a 'last reviewed' date to editorial/blog templates.",
      "Cite studies, testing, or primary specifications on key product/service pages.",
    ],
  },
  crawler: {
    name: "AI crawlers blocked",
    unit: "checks",
    problem: () => "AI crawlers (GPTBot, ClaudeBot, PerplexityBot) are blocked in robots.txt or meta tags.",
    steps: [
      "Allow AI search crawlers in robots.txt unless intentionally restricted.",
    ],
  },
  graph: {
    name: "Knowledge-graph presence",
    unit: "checks",
    problem: () => "AI platforms show weak recognition of the brand as a distinct entity.",
    steps: [
      "Strengthen Organization schema with sameAs links (LinkedIn, Wikipedia/Wikidata, major profiles).",
      "Ensure consistent brand naming across homepage copy, About page, and schema.",
    ],
  },
};

function toolLinkFor(key: string, clientSlug: string): { label: string; href: string } | undefined {
  if (key === "schema") return { label: "Open Machine Readability", href: `/${clientSlug}/schema` };
  if (key === "titles" || key === "dup_titles" || key === "descriptions" || key === "dup_descriptions") {
    return { label: "Open CTR Optimizer", href: `/${clientSlug}/ctr` };
  }
  if (key === "citation") return { label: "Open Content gaps", href: `/${clientSlug}/content-gaps` };
  return undefined;
}

function buildSeoGroups(c: ShCheck): FixGroup[] {
  if (c.duplicate_groups && c.duplicate_groups.length > 0) {
    const sorted = [...c.duplicate_groups].sort((a, b) => b.count - a.count);
    return [
      {
        title: "Largest groups",
        sub: `${sorted.length} ${sorted.length === 1 ? "group" : "groups"} of pages sharing the same text`,
        items: sorted.map((g) => ({
          a: `“${g.text}”`,
          b: g.urls.slice(0, 2).map(shortPath).join(", "),
          c: `${g.count} ${g.count === 1 ? "page" : "pages"}`,
          href: g.urls[0],
        })),
        totalCount: sorted.length,
        csvRows: [
          ["Shared Text", "Page Count", "URL"],
          ...sorted.flatMap((g) => g.urls.map((u) => [g.text, String(g.count), u])),
        ],
      },
    ];
  }
  if (c.urls.length === 0) return [];
  return [
    {
      title: "Affected pages",
      sub: `${c.affected} ${c.affected === 1 ? "page" : "pages"}`,
      items: c.urls.map((u) => ({
        a: c.key === "site_files" ? u : shortPath(u),
        c: c.key === "site_files" ? "Check" : "Fix",
        href: c.key === "site_files" ? undefined : u,
      })),
      totalCount: c.affected,
      csvRows: [["URL"], ...c.urls.map((u) => [u])],
    },
  ];
}

function buildGeoGroups(s: ShSignal, clientSlug: string): FixGroup[] {
  if (s.items.length === 0) return [];
  if (s.key === "citation") {
    const withPage = s.items.filter((i) => Boolean(i.url));
    const withoutPage = s.items.filter((i) => !i.url);
    const groups: FixGroup[] = [];
    if (withPage.length > 0) {
      groups.push({
        title: "Strengthen an existing page",
        sub: `${withPage.length} ${withPage.length === 1 ? "question" : "questions"} · the page exists but isn't cited`,
        items: withPage.map((i) => ({
          a: i.subject || i.text,
          b: i.url ? shortPath(i.url) : undefined,
          c: "Content",
          href: i.url ?? undefined,
        })),
        totalCount: withPage.length,
        csvRows: [["Prompt / Question", "Target URL"], ...withPage.map((i) => [i.subject || i.text, i.url || ""])],
      });
    }
    if (withoutPage.length > 0) {
      groups.push({
        title: "No page answers this yet",
        sub: `${withoutPage.length} ${withoutPage.length === 1 ? "question" : "questions"} · needs a new page`,
        link: { label: "Send to Content gaps", href: `/${clientSlug}/content-gaps` },
        items: withoutPage.map((i) => ({
          a: i.subject || i.text,
          b: i.problem ?? undefined,
          c: "New page",
        })),
        totalCount: withoutPage.length,
        csvRows: [["Prompt / Question", "Details"], ...withoutPage.map((i) => [i.subject || i.text, i.problem || i.text])],
      });
    }
    return groups;
  }

  return [
    {
      title: s.key === "attribution" ? "Topics affected" : "Pages to update",
      sub: `${s.affected} ${s.affected === 1 ? "item" : "items"}`,
      items: s.items.map((i) => ({
        a: i.url ? shortPath(i.url) : i.subject || i.text,
        b: i.url ? i.problem || i.subject || undefined : i.problem || undefined,
        c: OWNER_MAP[s.key] ?? "Fix",
        href: i.url ?? undefined,
      })),
      totalCount: s.affected,
      csvRows: [
        ["URL / Subject", "Problem", "Fix"],
        ...s.items.map((i) => [i.url || i.subject || i.text, i.problem || i.text, i.fix || ""]),
      ],
    },
  ];
}

export function buildUnifiedFixes(
  data: ShData,
  clientSlug: string,
): { toFix: UnifiedFix[]; passing: PassingFix[]; totalSeoGain: number; totalGeoGain: number } {
  const changeByKey = new Map((data.changes ?? []).map((ch) => [ch.key, ch]));
  const toFix: UnifiedFix[] = [];
  const passing: PassingFix[] = [];

  const seoSchema = data.seo.checks.find((c) => c.key === "schema");
  const geoSchema = data.geo.signals.find((s) => s.key === "schema");

  if (seoSchema || geoSchema) {
    const seoGain = seoSchema ? { weight: seoSchema.weight, score: seoSchema.score, gain: gainOf(seoSchema.weight, seoSchema.score) } : undefined;
    const geoGain =
      geoSchema && geoSchema.measured && geoSchema.score != null
        ? { weight: geoSchema.weight, score: geoSchema.score, gain: gainOf(geoSchema.weight, geoSchema.score) }
        : undefined;
    const totalGain = +(((seoGain?.gain ?? 0) + (geoGain?.gain ?? 0))).toFixed(1);
    const affected = Math.max(seoSchema?.affected ?? 0, geoSchema?.affected ?? 0);

    if (totalGain > 0 || affected > 0) {
      const urls = seoSchema?.urls?.length ? seoSchema.urls : (geoSchema?.items.map((i) => i.url).filter((u): u is string => Boolean(u)) ?? []);
      const ch = changeByKey.get("schema");
      toFix.push({
        id: "schema",
        name: "Structured data missing",
        seo: seoGain && seoGain.gain > 0 ? seoGain : undefined,
        geo: geoGain && geoGain.gain > 0 ? geoGain : undefined,
        totalGain,
        affected,
        unit: "pages",
        owner: "Developer",
        problem: `${affected} of ${seoSchema?.total || data.crawl.pages} indexable pages carry no valid structured data, so neither Google nor AI tools can read entities, products, or articles reliably.`,
        steps: [
          "Add Product or Service schema (name, description, price/offers) to your primary commercial template.",
          "Add CollectionPage and BreadcrumbList to collection or category templates.",
          "Add Article schema with author and datePublished to blog templates.",
          "Add Organization schema (name, logo, phone, address) once on the homepage.",
        ],
        note: "These are template-level fixes—fixing 3–4 templates covers the entire site.",
        toolLink: toolLinkFor("schema", clientSlug),
        groups: templateGroups(urls),
        change: ch ? { newCount: ch.new_count, fixedCount: ch.fixed_count } : undefined,
      });
    } else {
      const tags: ("SEO" | "GEO")[] = [];
      if (seoSchema) tags.push("SEO");
      if (geoSchema?.measured) tags.push("GEO");
      passing.push({ id: "schema", name: "Structured data", tags });
    }
  }

  for (const c of data.seo.checks) {
    if (c.key === "schema") continue;
    const g = gainOf(c.weight, c.score);
    if (g > 0 || c.affected > 0) {
      const copy = SEO_COPY[c.key];
      const ch = changeByKey.get(c.key);
      toFix.push({
        id: `seo:${c.key}`,
        name: copy?.name ?? c.label,
        seo: { weight: c.weight, score: c.score, gain: g },
        totalGain: g,
        affected: c.affected,
        unit: copy?.unit ?? "pages",
        owner: OWNER_MAP[c.key] ?? "SEO",
        problem: copy ? copy.problem(c.affected, c.total) : c.detail,
        steps: copy?.steps ?? [c.detail],
        note: copy?.note,
        toolLink: toolLinkFor(c.key, clientSlug),
        groups: buildSeoGroups(c),
        change: ch ? { newCount: ch.new_count, fixedCount: ch.fixed_count } : undefined,
      });
    } else {
      passing.push({ id: `seo:${c.key}`, name: SEO_COPY[c.key]?.name ?? c.label, tags: ["SEO"] });
    }
  }

  for (const s of data.geo.signals) {
    if (s.key === "schema") continue;
    if (!s.measured || s.score == null) continue;
    const g = gainOf(s.weight, s.score);
    if (g > 0 || s.affected > 0) {
      const copy = GEO_COPY[s.key];
      toFix.push({
        id: `geo:${s.key}`,
        name: copy?.name ?? s.label,
        geo: { weight: s.weight, score: s.score, gain: g },
        totalGain: g,
        affected: s.affected,
        unit: copy?.unit ?? "items",
        owner: OWNER_MAP[s.key] ?? "Content",
        problem: copy ? copy.problem(s.affected) : s.summary || s.note,
        steps: copy?.steps ?? [s.note],
        note: s.note,
        toolLink: toolLinkFor(s.key, clientSlug),
        groups: buildGeoGroups(s, clientSlug),
      });
    } else {
      passing.push({ id: `geo:${s.key}`, name: GEO_COPY[s.key]?.name ?? s.label, tags: ["GEO"] });
    }
  }

  toFix.sort((a, b) => b.totalGain - a.totalGain || b.affected - a.affected);

  const totalSeoGain = +toFix.reduce((acc, f) => acc + (f.seo?.gain ?? 0), 0).toFixed(0);
  const totalGeoGain = +toFix.reduce((acc, f) => acc + (f.geo?.gain ?? 0), 0).toFixed(0);

  return { toFix, passing, totalSeoGain, totalGeoGain };
}

export function fixIdForPageIssue(issue: ShPageIssue): string {
  if (issue.key === "schema") return "schema";
  return `${issue.source}:${issue.key}`;
}

export function fixIdForSignal(source: "seo" | "geo", key: string): string {
  if (key === "schema") return "schema";
  return `${source}:${key}`;
}

export function chipLabelForIssue(issue: ShPageIssue): string {
  if (issue.key === "schema") return "Structured data";
  if (issue.key === "dup_titles") return "Duplicate titles";
  if (issue.key === "dup_descriptions") return "Duplicate meta";
  if (issue.key === "titles") return "Missing title";
  if (issue.key === "descriptions") return "Missing meta";
  return issue.label.replace(/ missing$/i, "");
}

export function filterPages(pages: ShPageEntry[], scope: "all" | "seo" | "geo", query: string): ShPageEntry[] {
  const q = query.trim().toLowerCase();
  return pages.filter((p) => {
    const hasScope = scope === "all" || p.issues.some((i) => i.source === scope);
    if (!hasScope) return false;
    if (!q) return true;
    return p.url.toLowerCase().includes(q) || p.issues.some((i) => i.label.toLowerCase().includes(q));
  });
}
