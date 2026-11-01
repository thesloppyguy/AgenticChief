import type { Metadata } from "next";
import { Suspense } from "react";
import "./globals.css";
import AppShell from "@/components/AppShell";
import { ThemeProvider } from "@/components/ThemeProvider";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { DM_Sans } from "next/font/google";

const dmSans = DM_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-dm-sans",
});

export const metadata: Metadata = {
  title: "Lokibots | CHRO Copilot",
  description: "Lokibots | CHRO Copilot",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={dmSans.variable} suppressHydrationWarning>
      <head>
        <link
          rel="icon"
          href="https://cdn.prod.website-files.com/5f83f66bf4e71b5523030f96/601a469a2da74a06a22d3a07_32x32.png"
          sizes="any"
        />
      </head>
      <body className="font-sans antialiased">
        <ThemeProvider
          attribute="class"
          defaultTheme="light"
          disableTransitionOnChange
        >
          <TooltipProvider>
            <Suspense fallback={null}>
              <AppShell>{children}</AppShell>
            </Suspense>
          </TooltipProvider>
          <Toaster />
        </ThemeProvider>
      </body>
    </html>
  );
}
