/** Page title + description for the sticky app top bar. */
export function resolvePageChrome(pathname: string): { title: string; description: string } {
  if (pathname === "/clients") {
    return {
      title: "All clients",
      description: "Open a workspace to connect integrations and configure conversions.",
    };
  }

  if (pathname.startsWith("/clients/")) {
    if (pathname.includes("/conversions")) {
      return { title: "Conversions", description: "GA4 events that count as a lead." };
    }
    if (pathname.includes("/integrations")) {
      return { title: "Integrations", description: "Property mapping per data source." };
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
        "Account record for tier allowances, contract date, lead goal, conversions, and strategy sheet.",
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
        description: "Striking-distance content opportunities from Search Console.",
      };
    case "decision-engine":
      return {
        title: "Decision Engine",
        description: "Hard recommendations, suggestions, and findings for review.",
      };
    case "annotations":
      return {
        title: "Annotations",
        description: "Causal history for the account — changes and measured impact.",
      };
    default:
      return { title: "Organic IQ", description: "" };
  }
}
