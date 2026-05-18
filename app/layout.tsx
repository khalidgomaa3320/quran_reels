import type { Metadata } from "next"
import { Amiri, Noto_Naskh_Arabic } from "next/font/google"
import { Analytics } from "@vercel/analytics/next"
import { Toaster } from "@/components/ui/sonner"
import "./globals.css"

const amiri = Amiri({
  subsets: ["arabic"],
  weight: ["400", "700"],
  variable: "--font-amiri",
})

const notoArabic = Noto_Naskh_Arabic({
  subsets: ["arabic"],
  weight: ["400", "500", "700"],
  variable: "--font-noto-arabic",
})

export const metadata: Metadata = {
  title: "مولّد ريلز القرآن الكريم",
  description: "أنشئ فيديوهات قصيرة لآيات القرآن الكريم مع تلاوة القارئ والنص العربي",
  generator: "v0.app",
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="ar" dir="rtl" className="bg-background">
      <body className={`${notoArabic.variable} ${amiri.variable} font-sans antialiased`}>
        {children}
        <footer className="pb-4 pt-8 text-center text-xs text-muted-foreground/50">
          صنع بواسطة خالد جمعة ❤️
        </footer>
        <Toaster richColors position="top-center" />
        {process.env.NODE_ENV === "production" && <Analytics />}
      </body>
    </html>
  )
}
