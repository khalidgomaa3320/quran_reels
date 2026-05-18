import { spawn } from "node:child_process"
import { promises as fs } from "node:fs"
import { existsSync } from "node:fs"
import path from "node:path"
import { setJob } from "./jobs"
import { SURAHS, FONTS, TRANSLATIONS } from "./quran-data"
import ffprobeStatic from "ffprobe-static"

// ---------------------------------------------------------------------------
// Project paths
// ---------------------------------------------------------------------------
const PROJECT_ROOT = process.cwd()
export const OUTPUTS_DIR = path.join(PROJECT_ROOT, "outputs")
export const VIDEO_DIR = path.join(OUTPUTS_DIR, "video")
export const AUDIO_DIR = path.join(OUTPUTS_DIR, "audio")
export const TMP_AUDIO_DIR = path.join(OUTPUTS_DIR, "tmp_audio")
export const TMP_FRAMES_DIR = path.join(OUTPUTS_DIR, "tmp_frames")
export const BACKGROUNDS_DIR = path.join(OUTPUTS_DIR, "backgrounds")
const FONTS_DIR = path.join(PROJECT_ROOT, "assets", "fonts")
const UPLOADS_DIR = path.join(PROJECT_ROOT, "outputs", "uploads")

const FFMPEG = "ffmpeg"
const FFPROBE = ffprobeStatic.path || "ffprobe"

// ---------------------------------------------------------------------------
// Font management — download on demand
// ---------------------------------------------------------------------------
async function ensureFont(fontId: string): Promise<{ family: string; file: string }> {
  const f = FONTS.find((x) => x.id === fontId) || FONTS[0]
  await fs.mkdir(FONTS_DIR, { recursive: true })
  const dest = path.join(FONTS_DIR, f.file)
  if (!existsSync(dest)) {
    console.log("[v0] downloading font:", f.name)
    const r = await fetch(f.url)
    if (!r.ok) throw new Error(`فشل تحميل الخط ${f.name} (${r.status})`)
    const buf = Buffer.from(await r.arrayBuffer())
    await fs.writeFile(dest, buf)
  }
  return { family: f.family, file: dest }
}

async function ensureDirs() {
  for (const d of [OUTPUTS_DIR, VIDEO_DIR, AUDIO_DIR, TMP_AUDIO_DIR, TMP_FRAMES_DIR, BACKGROUNDS_DIR]) {
    await fs.mkdir(d, { recursive: true })
  }
}

function run(cmd: string, args: string[]): Promise<{ stdout: string; stderr: string }> {
  return new Promise((resolve, reject) => {
    console.log("[v0] $", cmd, args.slice(0, 8).join(" "), args.length > 8 ? "..." : "")
    const p = spawn(cmd, args, { stdio: ["ignore", "pipe", "pipe"] })
    let stdout = ""
    let stderr = ""
    p.stdout.on("data", (d) => (stdout += d.toString()))
    p.stderr.on("data", (d) => (stderr += d.toString()))
    p.on("error", reject)
    p.on("close", (code) => {
      if (code === 0) resolve({ stdout, stderr })
      else reject(new Error(`Command failed (${cmd}): ${stderr.slice(-500) || stdout.slice(-500)}`))
    })
  })
}

function safeName(s: string) {
  return s.replace(/[^A-Za-z0-9_-]+/g, "_").slice(0, 40)
}

async function ffprobeDuration(file: string): Promise<number> {
  const { stdout } = await run(FFPROBE, [
    "-v", "error",
    "-show_entries", "format=duration",
    "-of", "default=noprint_wrappers=1:nokey=1",
    file,
  ])
  return Number.parseFloat(stdout.trim() || "0") || 0
}

// ---------------------------------------------------------------------------
// Data fetching: arabic + optional translation
// ---------------------------------------------------------------------------
async function fetchAyahTexts(surah: number, frm: number, to: number): Promise<string[]> {
  const url = `https://api.alquran.cloud/v1/surah/${surah}/quran-uthmani`
  const r = await fetch(url, { cache: "no-store" })
  if (!r.ok) throw new Error(`فشل جلب نصوص الآيات (${r.status})`)
  const j = await r.json()
  const ayahs = j?.data?.ayahs as Array<{ text: string; numberInSurah: number }>
  return ayahs.filter((a) => a.numberInSurah >= frm && a.numberInSurah <= to).map((a) => a.text)
}

async function fetchTranslation(surah: number, frm: number, to: number, edition: string): Promise<string[]> {
  if (!edition || edition === "none") return []
  const url = `https://api.alquran.cloud/v1/surah/${surah}/${edition}`
  const r = await fetch(url, { cache: "no-store" })
  if (!r.ok) throw new Error(`فشل جلب الترجمة (${r.status})`)
  const j = await r.json()
  const ayahs = j?.data?.ayahs as Array<{ text: string; numberInSurah: number }>
  return ayahs.filter((a) => a.numberInSurah >= frm && a.numberInSurah <= to).map((a) => a.text)
}

async function downloadAyahAudio(reciterId: string, surah: number, ayah: number): Promise<string> {
  const fname = `${String(surah).padStart(3, "0")}${String(ayah).padStart(3, "0")}.mp3`
  // reciterId may include subfolder (e.g. "warsh/Yassin..."). Flatten for local cache name.
  const flatId = reciterId.replace(/\//g, "__")
  const out = path.join(AUDIO_DIR, `${flatId}_${fname}`)
  if (existsSync(out)) {
    const stat = await fs.stat(out)
    if (stat.size > 0) return out
  }
  const url = `https://everyayah.com/data/${reciterId}/${fname}`
  const r = await fetch(url)
  if (!r.ok) throw new Error(`فشل تحميل ${url} (${r.status})`)
  const buf = Buffer.from(await r.arrayBuffer())
  await fs.writeFile(out, buf)
  return out
}

// ---------------------------------------------------------------------------
// Color helpers — convert "#RRGGBB" / "rgb(...)" to ASS "&HAABBGGRR"
// ---------------------------------------------------------------------------
function toAssColor(input: string, alpha = 0): string {
  let r = 255, g = 255, b = 255
  const s = (input || "").trim()
  const hex = s.match(/^#?([0-9a-fA-F]{6})$/)
  if (hex) {
    const v = hex[1]
    r = parseInt(v.slice(0, 2), 16)
    g = parseInt(v.slice(2, 4), 16)
    b = parseInt(v.slice(4, 6), 16)
  } else {
    const m = s.match(/rgb\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/i)
    if (m) {
      r = parseInt(m[1], 10); g = parseInt(m[2], 10); b = parseInt(m[3], 10)
    }
  }
  const aa = Math.max(0, Math.min(255, alpha)).toString(16).padStart(2, "0").toUpperCase()
  const rr = r.toString(16).padStart(2, "0").toUpperCase()
  const gg = g.toString(16).padStart(2, "0").toUpperCase()
  const bb = b.toString(16).padStart(2, "0").toUpperCase()
  return `&H${aa}${bb}${gg}${rr}`
}

// ---------------------------------------------------------------------------
// ASS subtitle generation
// ---------------------------------------------------------------------------
function fmtTime(seconds: number): string {
  const total = Math.max(0, seconds)
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total - h * 3600 - m * 60
  return `${h}:${String(m).padStart(2, "0")}:${s.toFixed(2).padStart(5, "0")}`
}

function escapeAssText(t: string): string {
  return t.replace(/\\/g, "\\\\").replace(/\{/g, "\\{").replace(/\}/g, "\\}").replace(/\r?\n/g, "\\N")
}

type StyleOpts = {
  fontFamily: string
  fontSize: number
  textColor: string
  outlineColor: string
}

function buildStyle(name: string, opts: StyleOpts, alignment: number) {
  return [
    name,
    opts.fontFamily,
    String(opts.fontSize),
    toAssColor(opts.textColor),
    "&H000000FF",
    toAssColor(opts.outlineColor),
    "&H80000000",
    "1", "0", "0", "0",
    "100", "100", "0", "0",
    "1", // BorderStyle outline+shadow
    "8", // Outline
    "3", // Shadow
    String(alignment),
    "120", "120", "120",
    "1",
  ].join(",")
}

function toArabicNum(n: number): string {
  const digits = "٠١٢٣٤٥٦٧٨٩"
  return String(n).split("").map((d) => digits[parseInt(d, 10)]).join("")
}

function fitFontSize(text: string, baseSize: number, maxHeight: number, availWidth: number): number {
  const charEst = baseSize * 0.4
  const colsPerLine = Math.max(1, Math.floor(availWidth / charEst))
  const lines = Math.max(1, Math.ceil(text.length / colsPerLine))
  const needed = lines * baseSize * 1.3
  if (needed <= maxHeight) return baseSize
  const scale = Math.max(0.5, maxHeight / needed)
  return Math.max(Math.round(baseSize * 0.5), Math.round(baseSize * scale))
}

function fitLines(text: string, targetLines: number, maxSize: number, minSize: number, availWidth: number): number {
  let size = maxSize
  while (size >= minSize) {
    const cpl = Math.max(1, Math.floor(availWidth / (size * 0.45)))
    const lines = Math.ceil(text.length / cpl)
    if (lines <= targetLines) return size
    size -= 4
  }
  return minSize
}

async function buildAssFile(
  outPath: string,
  ayahs: string[],
  translations: string[],
  durations: number[],
  ayahNums: number[],
  surahName: string,
  arabic: StyleOpts,
  translation: StyleOpts | null,
  width = 1080,
  height = 1920,
) {
  const marginH = 120
  const availW = width - marginH * 2
  const arabicMaxH = height * 0.65
  const transMaxH = height * 0.30

  const arabicStyle = buildStyle("Arabic", arabic, 5)
  const transStyle = translation ? buildStyle("Trans", translation, 8) : null

  let cursor = 0
  const events: string[] = []
  for (let i = 0; i < ayahs.length; i++) {
    const start = cursor
    const end = cursor + durations[i]
    cursor = end

    const escSurah = escapeAssText(surahName)
    const num = toArabicNum(ayahNums[i])
    events.push(`Dialogue: 0,${fmtTime(start)},${fmtTime(end)},Arabic,,0,0,60,,{\\an8\\q2}{\\fs120}${escSurah}\\N{\\fs90}الآية ${num}`)

    const arText = escapeAssText(ayahs[i])
    const arFs = fitFontSize(arText, arabic.fontSize, arabicMaxH, availW)
    events.push(`Dialogue: 0,${fmtTime(start)},${fmtTime(end)},Arabic,,0,0,0,,{\\an5\\q2}{\\fs${arFs}}${arText}`)

    if (translation && translations[i]) {
      const trText = escapeAssText(translations[i])
      const trFs = fitLines(trText, 2, translation.fontSize, 34, availW)
      events.push(`Dialogue: 0,${fmtTime(start)},${fmtTime(end)},Trans,,0,0,1150,,{\\an8\\q2}{\\fs${trFs}}${trText}`)
    }
  }

  const styles = [arabicStyle, transStyle].filter(Boolean).map((s) => `Style: ${s}`).join("\n")

  const ass = `[Script Info]
ScriptType: v4.00+
PlayResX: ${width}
PlayResY: ${height}
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
${styles}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
${events.join("\n")}
`
  await fs.writeFile(outPath, ass, "utf8")
}

function relPath(absPath: string): string {
  const rel = path.relative(PROJECT_ROOT, absPath)
  return rel.replace(/\\/g, "/")
}

// ---------------------------------------------------------------------------
// Background — generated procedurally (Islamically safe: no figures/animals)
// ---------------------------------------------------------------------------
type BgOpts = {
  type: "gradient" | "solid" | "animated" | "noise" | "file"
  color1: string // hex
  color2: string // hex
  filePath?: string // uploaded file path (for "file" type)
}

function hexNum(c: string): string {
  const m = c.match(/^#?([0-9a-fA-F]{6})$/)
  return "0x" + (m ? m[1] : "0b3d2e")
}

async function makeBackground(
  bgOpts: BgOpts,
  durationSec: number,
  width = 1080,
  height = 1920,
): Promise<string> {
  await fs.mkdir(BACKGROUNDS_DIR, { recursive: true })
  const c1 = hexNum(bgOpts.color1)
  const c2 = hexNum(bgOpts.color2)
  const dur = Math.max(durationSec, 5).toFixed(2)
  const fname = `bg_${bgOpts.type}_${c1.slice(2)}_${c2.slice(2)}_${Math.ceil(durationSec)}s.mp4`
  const out = path.join(BACKGROUNDS_DIR, fname)
  if (existsSync(out)) return out

  if (bgOpts.type === "file" && bgOpts.filePath) {
    const src = bgOpts.filePath
    const ext = path.extname(src).toLowerCase()
    const isVideo = [".mp4", ".mov", ".avi", ".webm"].includes(ext)

    if (isVideo) {
      await run(FFMPEG, [
        "-y",
        "-stream_loop", "-1",
        "-i", src,
        "-vf", `scale=${width}:${height}:force_original_aspect_ratio=increase,crop=${width}:${height}`,
        "-t", dur,
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "veryfast",
        out,
      ])
    } else {
      await run(FFMPEG, [
        "-y",
        "-loop", "1",
        "-i", src,
        "-vf", `scale=${width}:${height}:force_original_aspect_ratio=increase,crop=${width}:${height}`,
        "-t", dur,
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "veryfast",
        out,
      ])
    }
    return out
  }

  let lavfi = ""
  if (bgOpts.type === "solid") {
    lavfi = `color=c=${c1}:s=${width}x${height}:r=30`
  } else if (bgOpts.type === "gradient") {
    lavfi =
      `color=c=${c1}:s=${width}x${height}:r=30,` +
      `geq=` +
      `r='(${parseInt(c1.slice(2, 4), 16)}*(H-Y)+${parseInt(c2.slice(2, 4), 16)}*Y)/H':` +
      `g='(${parseInt(c1.slice(4, 6), 16)}*(H-Y)+${parseInt(c2.slice(4, 6), 16)}*Y)/H':` +
      `b='(${parseInt(c1.slice(6, 8), 16)}*(H-Y)+${parseInt(c2.slice(6, 8), 16)}*Y)/H'`
  } else if (bgOpts.type === "noise") {
    lavfi = `color=c=${c1}:s=${width}x${height}:r=30,noise=alls=12:allf=t+u`
  } else {
    lavfi = `gradients=s=${width}x${height}:c0=${c1}:c1=${c2}:c2=${c1}:c3=${c2}:duration=20:speed=0.02:rate=30`
  }

  try {
    await run(FFMPEG, [
      "-y",
      "-f", "lavfi",
      "-i", lavfi,
      "-t", dur,
      "-c:v", "libx264",
      "-pix_fmt", "yuv420p",
      "-preset", "veryfast",
      out,
    ])
  } catch {
    await run(FFMPEG, [
      "-y",
      "-f", "lavfi",
      "-i", `color=c=${c1}:s=${width}x${height}:r=30`,
      "-t", dur,
      "-c:v", "libx264",
      "-pix_fmt", "yuv420p",
      out,
    ])
  }
  return out
}

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------
export type GenerateOpts = {
  reciter: string
  surah: number
  from: number
  to: number
  fontId: string
  fontSize: number
  textColor: string // arabic
  outlineColor: string
  translation: string // edition id or "none"
  translationColor: string
  translationOutline: string
  translationFontId: string
  background: BgOpts
}

// ---------------------------------------------------------------------------
// Main pipeline
// ---------------------------------------------------------------------------
export async function generateVideo(jobId: string, opts: GenerateOpts) {
  try {
    await ensureDirs()
    setJob(jobId, { status: "running", step: "تحميل الخطوط", progress: 3 })
    const arFont = await ensureFont(opts.fontId)
    const trFont = opts.translation !== "none" ? await ensureFont(opts.translationFontId) : null

    setJob(jobId, { step: "جلب نصوص الآيات", progress: 8 })
    const texts = await fetchAyahTexts(opts.surah, opts.from, opts.to)
    if (texts.length === 0) throw new Error("لا توجد آيات في النطاق المحدد")
    const ayahNumbers = Array.from({ length: texts.length }, (_, i) => opts.from + i)

    let translations: string[] = []
    if (opts.translation !== "none") {
      setJob(jobId, { step: "جلب الترجمة", progress: 12 })
      translations = await fetchTranslation(opts.surah, opts.from, opts.to, opts.translation)
    }

    setJob(jobId, { step: "تحميل ملفات الصوت", progress: 18 })
    const audioPaths: string[] = []
    for (let i = 0; i < ayahNumbers.length; i++) {
      audioPaths.push(await downloadAyahAudio(opts.reciter, opts.surah, ayahNumbers[i]))
      setJob(jobId, { progress: 18 + Math.floor((25 * (i + 1)) / ayahNumbers.length) })
    }

    setJob(jobId, { step: "قياس مدة كل آية", progress: 48 })
    const durations: number[] = []
    for (const p of audioPaths) durations.push(await ffprobeDuration(p))
    const total = durations.reduce((a, b) => a + b, 0)

    setJob(jobId, { step: "دمج صوت التلاوة", progress: 58 })
    const concatList = path.join(TMP_AUDIO_DIR, `list_${jobId}.txt`)
    await fs.writeFile(
      concatList,
      audioPaths.map((p) => `file '${p.replace(/'/g, "'\\''")}'`).join("\n"),
      "utf8",
    )
    const mergedAudio = path.join(TMP_AUDIO_DIR, `merged_${jobId}.mp3`)
    await run(FFMPEG, ["-y", "-f", "concat", "-safe", "0", "-i", concatList, "-c", "copy", mergedAudio])

    setJob(jobId, { step: "تجهيز نصوص الآيات", progress: 68 })
    const assPath = path.join(TMP_FRAMES_DIR, `subs_${jobId}.ass`)
    const surahObj = SURAHS[opts.surah - 1]
    const surahName = surahObj?.name || ""
    await buildAssFile(
      assPath,
      texts,
      translations,
      durations,
      ayahNumbers,
      surahName,
      {
        fontFamily: arFont.family,
        fontSize: opts.fontSize,
        textColor: opts.textColor,
        outlineColor: opts.outlineColor,
      },
      trFont
        ? {
            fontFamily: trFont.family,
            fontSize: Math.min(48, Math.max(20, Math.round(opts.fontSize * 0.2))),
            textColor: opts.translationColor,
            outlineColor: opts.translationOutline,
          }
        : null,
    )

    setJob(jobId, { step: "تجهيز الخلفية", progress: 76 })
    const bg = await makeBackground(opts.background, total)

    setJob(jobId, { step: "تركيب الفيديو النهائي", progress: 86 })
    const outName = `surah${String(opts.surah).padStart(3, "0")}_ayah${opts.from}-${opts.to}_${safeName(opts.reciter)}_${jobId.slice(0, 8)}.mp4`
    const outPath = path.join(VIDEO_DIR, outName)

    const assArg = `${relPath(assPath)}:fontsdir=${relPath(FONTS_DIR)}`
    const filterComplex = [
      "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,format=yuv420p[bg]",
      `[bg]ass=${assArg}[v]`,
    ].join(";")

    const cmd = [
      "-y",
      "-stream_loop", "-1",
      "-i", bg,
      "-i", mergedAudio,
      "-filter_complex", filterComplex,
      "-map", "[v]",
      "-map", "1:a:0",
      "-shortest",
      "-c:v", "libx264",
      "-pix_fmt", "yuv420p",
      "-preset", "veryfast",
      "-crf", "22",
      "-c:a", "aac",
      "-b:a", "192k",
      "-r", "30",
      outPath,
    ]
    await run(FFMPEG, cmd)
    try { await fs.unlink(concatList) } catch {}

    setJob(jobId, {
      status: "done",
      step: "اكتمل",
      progress: 100,
      videoUrl: `/api/video/${encodeURIComponent(outName)}`,
      filename: outName,
    })
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : "خطأ غير متوقع"
    console.error("[v0] generate error:", e)
    setJob(jobId, { status: "error", error: msg })
  }
}

export function validateRequest(opts: Partial<GenerateOpts>): string | null {
  const { reciter, surah, from, to, translation, fontId } = opts
  if (!reciter) return "القارئ غير محدد"
  if (!Number.isInteger(surah) || (surah as number) < 1 || (surah as number) > 114) return "رقم السورة غير صحيح"
  const max = SURAHS[(surah as number) - 1].ayahs
  if (
    !Number.isInteger(from) ||
    !Number.isInteger(to) ||
    (from as number) < 1 ||
    (to as number) < (from as number) ||
    (to as number) > max
  ) {
    return `نطاق الآيات يجب أن يكون بين 1 و ${max}`
  }
  if (((to as number) - (from as number) + 1) > 30) return "الحد الأقصى 30 آية لكل فيديو"
  if (fontId && !FONTS.find((f) => f.id === fontId)) return "الخط غير معروف"
  if (translation && translation !== "none" && !TRANSLATIONS.find((t) => t.id === translation)) {
    return "الترجمة غير معروفة"
  }
  return null
}
