export type EventCandidate = {
  event_name: string;
  event_count: number;
  pages: number;
  last_seen: string | null;
  automatic: boolean;
  suggested: boolean;
  defined: boolean;
  conversion_name: string | null;
  conversion_type: string | null;
  is_primary: boolean | null;
  active: boolean | null;
};

export type ConversionDefinition = {
  event_name: string;
  conversion_name: string;
  conversion_type: string;
  is_primary: boolean;
  active: boolean;
};

export type ConversionPage = {
  normalized_url: string;
  label: string;
  stage: string | null;
  is_primary: boolean;
};

export const CONVERSION_TYPES = [
  { value: "lead", label: "Lead" },
  { value: "ecommerce", label: "Ecommerce" },
  { value: "engagement", label: "Engagement" },
] as const;
