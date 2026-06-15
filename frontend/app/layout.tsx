import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import { ThemeProvider } from "../components/ThemeProvider";
import { ToastProvider } from "../components/Toast";
import { AuthGuard } from "../components/AuthGuard";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "Xeno AI Campaign Copilot",
  description: "AI-native CRM for retail and D2C lifecycle engagement. Autonomous campaign planning, audience segmentation, and multi-channel orchestration.",
  openGraph: {
    title: "Xeno AI Campaign Copilot",
    description: "AI-native CRM for retail and D2C lifecycle engagement",
    type: "website",
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#0A0E1A",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" data-theme="dark" className={inter.variable}>
      <body>
        <ThemeProvider>
          <ToastProvider>
            <AuthGuard>
              {children}
            </AuthGuard>
          </ToastProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}

