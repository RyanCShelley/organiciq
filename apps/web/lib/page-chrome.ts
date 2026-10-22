/** Page title + description for the sticky app top bar. */
export function resolvePageChrome(pathname: string): { title: string; description: string } {
  if (pathname === "/clients") {
    return {
      title: "All clients",
      description: "Open a workspace to connect integrations and configure conversions.",
    };
  }

  if (pathname.startsWith("/clients/")) {
    for (const [segment, title, description] of [
      ["setup", "Client setup", "Connect, configure and review the first assessment."],
      ["keyword-map", "Pages & Keywords", "Page ownership, stages and conversion destinations."],
      ["competitors", "Competitors", "The sites competing for this client’s customers."],
      ["advanced", "Advanced Settings", "Source scope, crawl settings and engine exclusions."],
      ["team", "Team Access", "Manage this client’s team."],
    ]) { if (pathname.endsWith(`/${segment}`)) return { title, description }; }
    if (pathname.includes("/conversions")) {
      return { title: "Conversions & Goals", description: "Saved lead definitions, destinations and growth targets." };
    }
    if (pathname.includes("/integrations")) {
      return { title: "Connections", description: "Connect sources and select client properties." };
    }
    if (pathname.includes("/data-health")) {
      return {
        title: "Data health",
        description: "Source freshness and validation coverage for this client.",
      };
    }
    if (pathname.includes("/jobs")) {
      return { title: "Sync jobs", description: "Sync jobs for this client workspace." };
    }
    return {
      title: "Client settings",
      description:
        "General information and growth engine configuration.",
    };
  }

  if (pathname === "/platform/data-health") {
    return {
      title: "Data health",
      description:
        "Freshness and validation for every client and source. Never treat stale data as current.",
    };
  }
  if (pathname === "/platform/jobs") {
    return {
      title: "Sync jobs",
      description:
        "Recent ingestion jobs across all clients. Enqueue new jobs from a client workspace.",
    };
  }
  if (pathname === "/platform/settings") {
    return {
      title: "Platform settings",
      description:
        "Global tiers and channel rules. Client-specific conversion definitions live in each client workspace.",
    };
  }
  if (pathname === "/platform") {
    return {
      title: "Platform",
      description:
        "Cross-client operations: integration status, sync health, and jobs. Open a client workspace to connect OAuth, map properties, and configure conversions.",
    };
  }

  const parts = pathname.split("/").filter(Boolean);
  const tool = parts.length >= 2 ? parts[1] : parts[0];

  switch (tool) {
    case "dashboard":
      return {
        title: "Dashboard",
        description: "Conversions → Visibility → Traffic from validated facts only.",
      };
    case "watch-list":
      return {
        title: "Watch List",
        description: "Search keywords and AI prompts from SE Ranking.",
      };
    case "content-opp":
      return {
        title: "Content Opp",
        description: "The month's content plan: pages to refresh and pages to write.",
      };
    case "decision-engine":
      return {
        title: "Decision Engine",
        description: "Review the evidence, choose the focus, and approve this month’s actions.",
      };
    case "annotations":
      return {
        title: "Work & Results",
        description: "Follow approved work, record completion and review observed results.",
      };
    default:
      return { title: "Organic IQ", description: "" };
  }
}
