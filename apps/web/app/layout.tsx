import type { Metadata } from "next";
import type { PropsWithChildren } from "react";

import { workspaceConfig } from "@/lib/workspace-config";

import "./globals.css";

export const metadata: Metadata = {
  title: workspaceConfig.appDisplayName,
  description: workspaceConfig.productDescription
};

export default function RootLayout({ children }: PropsWithChildren) {
  return (
    <html lang="en">
      <body className="bg-slate-100 text-slate-900 antialiased">{children}</body>
    </html>
  );
}
