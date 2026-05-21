import type { Metadata } from "next";
import { Chakra_Petch, Exo_2, JetBrains_Mono } from "next/font/google";
import { ThemeProvider } from "next-themes";

import { Providers } from "@/components/common/Providers";
import { StarField } from "@/components/common/StarField";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import "@/styles/globals.css";

// Display headings — Chakra Petch keeps the cyberpunk feel and ships
// full Vietnamese glyphs (Orbitron has Latin-only, so VN diacritics
// fell back to system fonts and broke the aesthetic).
const chakraPetch = Chakra_Petch({
  variable: "--font-orbitron",
  subsets: ["latin", "latin-ext", "vietnamese"],
  weight: ["300", "400", "500", "600", "700"],
  display: "swap",
});

// Body / UI text — Exo 2 already ships VN glyphs.
const exo2 = Exo_2({
  variable: "--font-exo2",
  subsets: ["latin", "latin-ext", "vietnamese"],
  weight: ["300", "400", "500", "600", "700"],
  display: "swap",
});

// Code-style numeric labels — JetBrains Mono replaces Space Mono so VN
// diacritics in mono surfaces (badges, stats) render correctly.
const jetbrainsMono = JetBrains_Mono({
  variable: "--font-space-mono",
  subsets: ["latin", "latin-ext", "vietnamese"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "AstroLearn",
  description: "Multi-agent astronomy & learning system",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning className="dark">
      <body
        className={`${chakraPetch.variable} ${exo2.variable} ${jetbrainsMono.variable} antialiased`}
      >
        <StarField />
        <ThemeProvider
          attribute="class"
          defaultTheme="dark"
          forcedTheme="dark"
          enableSystem={false}
          disableTransitionOnChange
        >
          <Providers>
            <TooltipProvider>
              <div className="relative z-10">{children}</div>
              <Toaster richColors closeButton theme="dark" />
            </TooltipProvider>
          </Providers>
        </ThemeProvider>
      </body>
    </html>
  );
}
