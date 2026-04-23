import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "MEPIA — Copiloto Financiero",
  description: "Auditoría operativa y financiera para restaurantes",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body className="min-h-screen bg-zinc-900 text-zinc-100 font-sans antialiased">
        {children}
      </body>
    </html>
  );
}
