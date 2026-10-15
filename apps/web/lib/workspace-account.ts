/**
 * SMA Workspace login domains — keep in sync with login page copy.
 *
 * Both are accepted through the .com migration: staff accounts and Workspace
 * aliases are still on .net. Override with SMA_GOOGLE_HOSTED_DOMAIN
 * (comma-separated) to change this without a deploy.
 */
export const HOSTED_DOMAINS = (
  process.env.SMA_GOOGLE_HOSTED_DOMAIN || "smamarketing.com,smamarketing.net"
)
  .split(",")
  .map((d) => d.trim().toLowerCase().replace(/^@/, ""))
  .filter(Boolean);

/**
 * Whether Google vouches that this is a Workspace account on one of our
 * domains. Both halves matter: the email domain says which, and `hd` says that
 * a Workspace owns it. An email address alone proves nothing — a consumer
 * Google account can be registered with a retired @smamarketing address and
 * carries no `hd`.
 *
 * SMA_ALLOW_ACCOUNTS_WITHOUT_HD=true restores the old email-only rule, as a
 * way back in if a legitimate staff account turns out not to carry `hd`.
 */
export function isSmaWorkspaceAccount(email: string, hd?: string | null): boolean {
  const domain = email.trim().toLowerCase().split("@").pop() ?? "";
  if (!HOSTED_DOMAINS.includes(domain)) return false;
  if (process.env.SMA_ALLOW_ACCOUNTS_WITHOUT_HD === "true") return true;
  return HOSTED_DOMAINS.includes((hd ?? "").toLowerCase());
}

