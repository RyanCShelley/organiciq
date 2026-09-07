export const BRAND = {
  productName: "Organic IQ",
  logoWordmark: "OrganicIQ",
  companyName: "SMA Marketing",
  tagline: "Operating system for predictable organic growth",
  hostedDomain: "smamarketing.net",
  styleGuideUrl: "https://smamarketing.com/style-guide/",
  logoPath: "/brand/sma-marketing-logo.svg",
  colors: {
    brandDark: "#0a0c0f",
    brandDark2: "#171a22",
    brandDark3: "#223540",
    brandTeal: "#00a99d",
    brandTealHover: "#008077",
    brandLime: "#aae437",
    brandTealSoft: "#c8f2ec",
    brandLimeSoft: "#e7fedc",
    textSecondary: "#6a6d75",
    textTertiary: "#9ca3af",
    border: "#e5e7eb",
    background: "#f8f9fb",
    surface: "#ffffff",
  },
  typography: {
    body: "Inter",
    headline: "Inter Tight",
  },
  layout: {
    sidebarWidth: "14rem",
    maxContentWidth: "80rem",
  },
} as const;

/** CSS variable names for programmatic use (charts, etc.) */
export const CSS_VARS = {
  brandTeal: "var(--brand-teal)",
  brandLime: "var(--brand-lime)",
  textPrimary: "var(--text-primary)",
  textSecondary: "var(--text-secondary)",
  border: "var(--border)",
  surface: "var(--surface)",
  success: "var(--success)",
  danger: "var(--danger)",
} as const;
