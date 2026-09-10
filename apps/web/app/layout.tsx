import type { Metadata } from "next";
import { Inter, Nunito_Sans } from "next/font/google";

import { BRAND } from "@/lib/brand";

import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const nunitoSans = Nunito_Sans({
  subsets: ["latin"],
  weight: ["600", "700", "800", "900"],
  variable: "--font-nunito-sans",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: BRAND.productName,
    template: `%s · ${BRAND.productName}`,
  },
  description: `${BRAND.companyName} ${BRAND.tagline}`,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${nunitoSans.variable}`}>
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
