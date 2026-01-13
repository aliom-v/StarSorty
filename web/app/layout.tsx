import "./globals.css";
import type { Metadata } from "next";
import Providers from "./providers";

export const metadata: Metadata = {
  title: "StarSorty",
  description: "Organize starred repositories with clarity and control."
};

const themeScript = `
(() => {
  try {
    const storageKey = "starsorty.theme";
    const stored = window.localStorage.getItem(storageKey);
    const system = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    const theme = stored === "light" || stored === "dark" ? stored : system;
    const root = document.documentElement;
    root.classList.toggle("dark", theme === "dark");
    root.style.colorScheme = theme;
  } catch {}
})();
`;

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="font-body text-ink">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
