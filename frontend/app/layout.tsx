import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "拾光 ShiGuang — 校园失物招领",
  description: "AI 智能匹配的校园失物招领平台",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
