import { ReelsGenerator } from "@/components/reels-generator"
import { BookOpen } from "lucide-react"

export default function HomePage() {
  return (
    <main className="min-h-screen w-full">
      <div className="mx-auto max-w-3xl px-4 py-10 sm:py-16">
        <header className="mb-10 text-center">
          <div className="mx-auto mb-5 inline-flex h-14 w-14 items-center justify-center rounded-2xl border border-primary/30 bg-primary/10 text-primary">
            <BookOpen className="h-7 w-7" />
          </div>
          <h1 className="font-serif text-4xl font-bold tracking-tight text-balance sm:text-5xl">
            مولّد ريلز القرآن الكريم
          </h1>
          <p className="mt-4 text-base leading-relaxed text-muted-foreground sm:text-lg text-pretty">
            اختر القارئ والسورة ونطاق الآيات، وسننشئ لك فيديو رأسي قصير
            <br className="hidden sm:block" />
            مع خلفية طبيعة وتلاوة القارئ ونص الآيات بالعربية.
          </p>
        </header>

        <ReelsGenerator />

        <footer className="mt-12 text-center text-xs text-muted-foreground">
          <p>
            البيانات من{" "}
            <span className="text-foreground/80">everyayah.com</span> و{" "}
            <span className="text-foreground/80">api.alquran.cloud</span>
          </p>
          <p className="mt-1">المعالجة محلياً عبر FFmpeg و ImageMagick</p>
        </footer>
      </div>
    </main>
  )
}
