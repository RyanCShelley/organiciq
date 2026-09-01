import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Organic IQ",
  description: "SMA Marketing operating system for predictable organic growth",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
