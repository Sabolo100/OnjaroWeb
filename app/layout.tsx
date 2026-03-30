import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Onjaro – Magyar Kerékpársport Portál",
  description:
    "Magyar kerékpársport-portál 45-60 éves férfiak számára. Edzéstervek, felszerelés-tanácsok, tippek országúti kerékpározáshoz, MTB-hez és ciklokrosszhoz.",
  keywords: [
    "kerékpározás",
    "mountain bike",
    "MTB",
    "ciklokrossz",
    "országúti kerékpár",
    "edzésterv",
    "felszerelés",
  ],
  authors: [{ name: "Onjaro" }],
  openGraph: {
    title: "Onjaro – Magyar Kerékpársport Portál",
    description:
      "Hasznos tartalmak, edzéstervek és közösség 45-60 éves kerékpárosoknak.",
    locale: "hu_HU",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="hu">
      <body className="bg-gray-50 text-gray-900 antialiased">{children}</body>
    </html>
  );
}
