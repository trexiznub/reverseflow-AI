import type { Metadata } from "next";
import { Archivo, Geist_Mono } from "next/font/google";
import { Providers } from "@/components/providers";
import { Shell } from "@/components/Shell";
import "./globals.css";

const sans = Archivo({ subsets: ["latin"], weight: ["400", "500", "600", "700"], variable: "--font-sans" });
const display = Archivo({ subsets: ["latin"], weight: ["800", "900"], variable: "--font-display" });
const mono = Geist_Mono({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-mono" });

export const metadata: Metadata = {
  title: "ReverseFlow · Returns Control Tower",
  description: "Plan for festive return surges, fix the products that come back, and recover their value. Synthetic demonstration data.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${display.variable} ${mono.variable}`}>
      <body className="font-sans text-[13.5px]">
        <Providers>
          <Shell>{children}</Shell>
        </Providers>
      </body>
    </html>
  );
}
