import { SettingsFrame } from "@/components/layout/SettingsFrame";

export default async function SettingsLayout({ children, params }: { children: React.ReactNode; params: Promise<{ clientSlug: string }> }) {
  const { clientSlug } = await params;
  return <SettingsFrame slug={clientSlug}>{children}</SettingsFrame>;
}
