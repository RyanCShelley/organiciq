import { SettingsFrame } from "@/components/layout/SettingsFrame";

// The watchlist is listed among the Settings tabs, so it keeps them.
export default async function WatchlistLayout({ children, params }: { children: React.ReactNode; params: Promise<{ clientSlug: string }> }) {
  const { clientSlug } = await params;
  return <SettingsFrame slug={clientSlug} width="max-w-6xl">{children}</SettingsFrame>;
}
