"use client"

import { useMemo, useState, useRef } from "react"
import { RECITERS, SURAHS, FONTS, TRANSLATIONS, BACKGROUND_TYPES } from "@/lib/quran-data"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Progress } from "@/components/ui/progress"
import { Card, CardContent } from "@/components/ui/card"
import { Slider } from "@/components/ui/slider"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Separator } from "@/components/ui/separator"
import { Loader2, Download, Play, Sparkles, AlertCircle, ShieldCheck, Upload, Image, Video, X } from "lucide-react"
import { toast } from "sonner"

type JobStatus = {
  status: "queued" | "running" | "done" | "error"
  step?: string
  progress?: number
  videoUrl?: string
  filename?: string
  error?: string
}

type BgType = "gradient" | "solid" | "animated" | "noise" | "file"

const PRESET_COLORS = [
  "#FFFFFF", "#FFE49B", "#FFD27A", "#F5E6C8",
  "#000000", "#0b3d2e", "#1f6f4a", "#2c5f3e",
  "#0c4a6e", "#5b3e2b", "#c9a227", "#a16207",
]

function ColorField({
  label,
  value,
  onChange,
}: {
  label: string
  value: string
  onChange: (v: string) => void
}) {
  return (
    <div className="grid gap-2">
      <Label className="text-xs text-muted-foreground">{label}</Label>
      <div className="flex items-center gap-2">
        <input
          type="color"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="h-10 w-12 cursor-pointer rounded-md border border-border bg-transparent"
          aria-label={label}
        />
        <Input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="h-10 flex-1 font-mono text-xs uppercase"
          spellCheck={false}
        />
      </div>
      <div className="flex flex-wrap gap-1.5">
        {PRESET_COLORS.map((c) => (
          <button
            key={c}
            type="button"
            onClick={() => onChange(c)}
            className="h-5 w-5 rounded-full border border-border ring-offset-background transition hover:scale-110 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
            style={{ backgroundColor: c }}
            aria-label={c}
          />
        ))}
      </div>
    </div>
  )
}

export function ReelsGenerator() {
  // Required
  const [reciter, setReciter] = useState(RECITERS[0].id)
  const [surahNum, setSurahNum] = useState<number>(1)
  const [fromAyah, setFromAyah] = useState<number>(1)
  const [toAyah, setToAyah] = useState<number>(3)

  // Arabic text styling
  const [fontId, setFontId] = useState("amiri")
  const [fontSize, setFontSize] = useState<number>(240)
  const [textColor, setTextColor] = useState("#FFFFFF")
  const [outlineColor, setOutlineColor] = useState("#000000")

  // Translation
  const [translation, setTranslation] = useState("none")
  const [translationFontId, setTranslationFontId] = useState("cairo")
  const [translationColor, setTranslationColor] = useState("#FFE49B")
  const [translationOutline, setTranslationOutline] = useState("#000000")

  // Background
  const [bgType, setBgType] = useState<BgType>("animated")
  const [bgColor1, setBgColor1] = useState("#0b3d2e")
  const [bgColor2, setBgColor2] = useState("#1f6f4a")
  const [bgFile, setBgFile] = useState<{ name: string; path: string; type: "image" | "video" } | null>(null)
  const [isUploading, setIsUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [busy, setBusy] = useState(false)
  const [job, setJob] = useState<JobStatus | null>(null)

  const surah = useMemo(() => SURAHS.find((s) => s.number === surahNum)!, [surahNum])

  // group reciters by reading
  const reciterGroups = useMemo(() => {
    const map = new Map<string, typeof RECITERS>()
    for (const r of RECITERS) {
      const k = r.reading
      if (!map.has(k)) map.set(k, [])
      map.get(k)!.push(r)
    }
    return Array.from(map.entries())
  }, [])

  function onSurahChange(v: string) {
    const n = Number.parseInt(v, 10)
    setSurahNum(n)
    const s = SURAHS.find((x) => x.number === n)!
    if (fromAyah > s.ayahs) setFromAyah(1)
    if (toAyah > s.ayahs) setToAyah(Math.min(s.ayahs, 3))
  }

  async function handleFileUpload(file: File) {
    setUploadError(null)
    setIsUploading(true)
    try {
      const formData = new FormData()
      formData.append("file", file)
      const r = await fetch("/api/upload", { method: "POST", body: formData })
      const data = await r.json()
      if (!r.ok) throw new Error(data.error || "فشل رفع الملف")
      setBgFile({ name: file.name, path: data.filePath, type: data.type })
      toast.success("تم رفع الملف بنجاح")
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "خطأ غير متوقع"
      setUploadError(msg)
      toast.error(msg)
    } finally {
      setIsUploading(false)
    }
  }

  function clearBgFile() {
    setBgFile(null)
    setUploadError(null)
    if (fileInputRef.current) fileInputRef.current.value = ""
  }

  async function pollJob(jobId: string) {
    const start = Date.now()
    while (Date.now() - start < 1000 * 60 * 15) {
      await new Promise((r) => setTimeout(r, 1500))
      try {
        const r = await fetch(`/api/status/${jobId}`, { cache: "no-store" })
        const j: JobStatus = await r.json()
        setJob(j)
        if (j.status === "done" || j.status === "error") return j
      } catch {
        // keep polling
      }
    }
    return { status: "error", error: "انتهت المهلة" } as JobStatus
  }

  async function generate() {
    if (toAyah < fromAyah) return toast.error("نطاق الآيات غير صحيح")
    if (toAyah - fromAyah + 1 > 30) return toast.error("الحد الأقصى 30 آية لكل فيديو")
    if (bgType === "file" && !bgFile) return toast.error("يُرجى رفع ملف خلفية أولاً")

    setBusy(true)
    setJob({ status: "queued", step: "إرسال الطلب...", progress: 0 })
    try {
      const r = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          reciter,
          surah: surahNum,
          from: fromAyah,
          to: toAyah,
          fontId,
          fontSize,
          textColor,
          outlineColor,
          translation,
          translationFontId,
          translationColor,
          translationOutline,
          background: { type: bgType, color1: bgColor1, color2: bgColor2, filePath: bgFile?.path },
        }),
      })
      const data = await r.json()
      if (!r.ok) throw new Error(data.error || "فشل بدء المهمة")
      const final = await pollJob(data.jobId)
      if (final.status === "done") toast.success("اكتمل توليد الفيديو")
      else if (final.status === "error") toast.error(final.error || "فشل التوليد")
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "خطأ غير متوقع"
      setJob({ status: "error", error: msg })
      toast.error(msg)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card className="border-border/60 bg-card/60 backdrop-blur shadow-2xl shadow-black/20">
      <CardContent className="p-6 sm:p-8">
        <div className="mb-5 flex items-start gap-3 rounded-lg border border-primary/20 bg-primary/5 p-3 text-xs text-primary/90">
          <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" />
          <p className="leading-relaxed">
            هذا التطبيق يلتزم بضوابط شرعية: لا يستخدم صوراً للبشر أو الحيوانات أو رموزاً
            تتعارض مع الإسلام. الخلفيات تُولَّد تلقائياً كألوان وتدرجات وزخارف هندسية فقط، وأي
            ملف خلفية محلي خارجي تتحمّل أنت مسؤولية توافقه.
          </p>
        </div>

        <Tabs defaultValue="basics" className="w-full">
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="basics">الأساسيات</TabsTrigger>
            <TabsTrigger value="text">النص والترجمة</TabsTrigger>
            <TabsTrigger value="background">الخلفية</TabsTrigger>
          </TabsList>

          {/* ===== Basics ===== */}
          <TabsContent value="basics" className="mt-6 grid gap-5">
            <div className="grid gap-2">
              <Label htmlFor="reciter" className="text-sm">القارئ والقراءة</Label>
              <Select value={reciter} onValueChange={setReciter}>
                <SelectTrigger id="reciter" className="h-11 w-full">
                  <SelectValue placeholder="اختر القارئ" />
                </SelectTrigger>
                <SelectContent className="max-h-[360px]">
                  {reciterGroups.map(([reading, list]) => (
                    <div key={reading}>
                      <div className="px-2 py-1.5 text-xs font-semibold text-muted-foreground">
                        {reading}
                      </div>
                      {list.map((r) => (
                        <SelectItem key={r.id} value={r.id}>
                          {r.name}
                        </SelectItem>
                      ))}
                      <Separator className="my-1" />
                    </div>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                {RECITERS.length} قارئاً عبر روايات متعددة (حفص، ورش، قالون، شعبة...)
              </p>
            </div>

            <div className="grid gap-2">
              <Label htmlFor="surah" className="text-sm">السورة</Label>
              <Select value={String(surahNum)} onValueChange={onSurahChange}>
                <SelectTrigger id="surah" className="h-11 w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="max-h-[320px]">
                  {SURAHS.map((s) => (
                    <SelectItem key={s.number} value={String(s.number)}>
                      {s.number}. {s.name} — {s.ayahs} آية
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="grid gap-2">
                <Label htmlFor="from" className="text-sm">من الآية</Label>
                <Input
                  id="from" type="number" min={1} max={surah.ayahs}
                  value={fromAyah}
                  onChange={(e) => setFromAyah(Math.max(1, Number(e.target.value) || 1))}
                  className="h-11"
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="to" className="text-sm">إلى الآية</Label>
                <Input
                  id="to" type="number" min={1} max={surah.ayahs}
                  value={toAyah}
                  onChange={(e) => setToAyah(Math.max(1, Number(e.target.value) || 1))}
                  className="h-11"
                />
              </div>
            </div>
            <p className="text-xs text-muted-foreground">الحد الأقصى 30 آية لكل فيديو.</p>
          </TabsContent>

          {/* ===== Text ===== */}
          <TabsContent value="text" className="mt-6 grid gap-6">
            <div className="grid gap-4">
              <h3 className="text-sm font-semibold">النص العربي</h3>
              <div className="grid gap-2">
                <Label className="text-xs text-muted-foreground">الخط</Label>
                <Select value={fontId} onValueChange={setFontId}>
                  <SelectTrigger className="h-11"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {FONTS.map((f) => (
                      <SelectItem key={f.id} value={f.id}>{f.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid gap-2">
                <Label className="flex items-center justify-between text-xs text-muted-foreground">
                  <span>حجم الخط</span>
                  <span className="font-mono tabular-nums text-foreground/80">{fontSize}px</span>
                </Label>
                <Slider
                  value={[fontSize]}
                  min={80} max={360} step={10}
                  onValueChange={(v) => setFontSize(v[0])}
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <ColorField label="لون النص" value={textColor} onChange={setTextColor} />
                <ColorField label="لون الحدود/الظل" value={outlineColor} onChange={setOutlineColor} />
              </div>
            </div>

            <Separator />

            <div className="grid gap-4">
              <h3 className="text-sm font-semibold">الترجمة (اختياري)</h3>
              <div className="grid gap-2">
                <Label className="text-xs text-muted-foreground">لغة الترجمة</Label>
                <Select value={translation} onValueChange={setTranslation}>
                  <SelectTrigger className="h-11"><SelectValue /></SelectTrigger>
                  <SelectContent className="max-h-[320px]">
                    {TRANSLATIONS.map((t) => (
                      <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {translation !== "none" && (
                <>
                  <div className="grid gap-2">
                    <Label className="text-xs text-muted-foreground">خط الترجمة</Label>
                    <Select value={translationFontId} onValueChange={setTranslationFontId}>
                      <SelectTrigger className="h-11"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {FONTS.map((f) => (
                          <SelectItem key={f.id} value={f.id}>{f.name}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <ColorField label="لون الترجمة" value={translationColor} onChange={setTranslationColor} />
                    <ColorField label="حدود الترجمة" value={translationOutline} onChange={setTranslationOutline} />
                  </div>
                </>
              )}
            </div>
          </TabsContent>

          {/* ===== Background ===== */}
          <TabsContent value="background" className="mt-6 grid gap-5">
            <div className="grid gap-2">
              <Label className="text-xs text-muted-foreground">نوع الخلفية</Label>
              <Select value={bgType} onValueChange={(v) => setBgType(v as BgType)}>
                <SelectTrigger className="h-11"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {BACKGROUND_TYPES.map((b) => (
                    <SelectItem key={b.id} value={b.id}>{b.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground leading-relaxed">
                {bgType === "file"
                  ? "ارفع صورة أو فيديو من جهازك. سيتم فحص المحتوى تلقائياً للتأكد من توافقه مع الضوابط الشرعية."
                  : "الخلفيات تُولَّد رياضياً (ألوان وتدرجات هندسية) ولا تحتوي على صور لذوات الأرواح."}
              </p>
            </div>

            {bgType === "file" ? (
              <div className="grid gap-4">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/jpeg,image/png,image/webp,image/gif,video/mp4,video/quicktime,video/webm"
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0]
                    if (f) handleFileUpload(f)
                  }}
                />
                {!bgFile ? (
                  <div
                    onClick={() => fileInputRef.current?.click()}
                    className="flex cursor-pointer flex-col items-center gap-3 rounded-lg border-2 border-dashed border-border bg-background/30 p-8 text-center transition hover:border-primary/50 hover:bg-background/50"
                  >
                    {isUploading ? (
                      <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                    ) : (
                      <Upload className="h-8 w-8 text-muted-foreground" />
                    )}
                    <div>
                      <p className="text-sm font-medium">
                        {isUploading ? "جاري الرفع والفحص..." : "اضغط لاختيار ملف"}
                      </p>
                      <p className="mt-1 text-xs text-muted-foreground">
                        صور: JPG, PNG, WebP, GIF (حد 10MB) — فيديو: MP4, MOV, WebM (حد 100MB)
                      </p>
                    </div>
                  </div>
                ) : (
                  <div className="rounded-lg border border-border bg-background/30 p-4">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        {bgFile.type === "image" ? (
                          <Image className="h-6 w-6 text-primary" />
                        ) : (
                          <Video className="h-6 w-6 text-primary" />
                        )}
                        <div>
                          <p className="text-sm font-medium truncate max-w-[200px]">{bgFile.name}</p>
                          <p className="text-xs text-muted-foreground">
                            {bgFile.type === "image" ? "صورة" : "فيديو"} — تم الفحص والموافقة
                          </p>
                        </div>
                      </div>
                      <Button variant="ghost" size="icon" onClick={clearBgFile} className="h-8 w-8">
                        <X className="h-4 w-4" />
                      </Button>
                    </div>
                    <div className="mt-3">
                      {bgFile.type === "image" ? (
                        <img
                          src={bgFile.path}
                          alt="background preview"
                          className="h-32 w-full rounded-md object-cover"
                        />
                      ) : (
                        <video
                          src={bgFile.path}
                          className="h-32 w-full rounded-md object-cover"
                          muted
                          autoPlay
                          loop
                          playsInline
                        />
                      )}
                    </div>
                  </div>
                )}
                {uploadError && (
                  <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
                    <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                    <span>{uploadError}</span>
                  </div>
                )}
              </div>
            ) : (
              <>
                <div className="grid grid-cols-2 gap-4">
                  <ColorField label="اللون الأساسي" value={bgColor1} onChange={setBgColor1} />
                  {bgType !== "solid" && bgType !== "noise" && (
                    <ColorField label="اللون الثانوي" value={bgColor2} onChange={setBgColor2} />
                  )}
                </div>
                <div className="grid gap-2">
                  <Label className="text-xs text-muted-foreground">معاينة</Label>
                  <div
                    className="h-24 w-full rounded-lg border border-border"
                    style={{
                      background:
                        bgType === "solid"
                          ? bgColor1
                          : bgType === "noise"
                            ? `${bgColor1}`
                            : `linear-gradient(180deg, ${bgColor1}, ${bgColor2})`,
                    }}
                  />
                </div>
              </>
            )}
          </TabsContent>
        </Tabs>

        <div className="mt-8 grid gap-4">
          <Button
            onClick={generate}
            disabled={busy}
            size="lg"
            className="h-12 w-full text-base font-semibold"
          >
            {busy ? (
              <>
                <Loader2 className="h-5 w-5 animate-spin" />
                جاري التوليد...
              </>
            ) : (
              <>
                <Sparkles className="h-5 w-5" />
                توليد الفيديو
              </>
            )}
          </Button>

          {job && job.status !== "done" && (
            <div className="rounded-lg border border-border/60 bg-background/40 p-4">
              <div className="mb-3 flex items-center justify-between">
                <span className="text-sm text-foreground/90">
                  {job.step || "جاري المعالجة..."}
                </span>
                <span className="text-xs text-muted-foreground tabular-nums">
                  {job.progress ?? 0}%
                </span>
              </div>
              <Progress value={job.progress ?? 0} className="h-2" />
              {job.status === "error" && (
                <div className="mt-3 flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                  <span>{job.error || "فشل التوليد"}</span>
                </div>
              )}
            </div>
          )}

          {job?.status === "done" && job.videoUrl && (
            <div className="grid gap-3 rounded-lg border border-primary/30 bg-primary/5 p-4">
              <div className="flex items-center gap-2 text-primary">
                <Play className="h-4 w-4" />
                <span className="text-sm font-medium">اكتمل التوليد</span>
              </div>
              <video
                src={job.videoUrl}
                controls
                playsInline
                className="aspect-[9/16] w-full max-w-sm self-center rounded-lg border border-border bg-black"
              />
              <a
                href={job.videoUrl}
                download={job.filename}
                className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-border bg-background/60 px-4 text-sm font-medium hover:bg-background"
              >
                <Download className="h-4 w-4" />
                تحميل الفيديو
              </a>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
