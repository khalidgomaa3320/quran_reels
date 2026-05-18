import { NextResponse } from "next/server"
import crypto from "node:crypto"
import path from "node:path"
import { existsSync } from "node:fs"
import { setJob } from "@/lib/jobs"
import { generateVideo, validateRequest, type GenerateOpts } from "@/lib/video-pipeline"

export const runtime = "nodejs"
export const dynamic = "force-dynamic"

const UPLOADS_DIR = path.join(process.cwd(), "outputs", "uploads")

const validBgTypes = ["gradient", "solid", "animated", "noise", "file"] as const

function resolveFilePath(filePath: string): string {
  if (filePath.startsWith("/api/uploads/")) {
    const name = filePath.replace("/api/uploads/", "").replace(/[^A-Za-z0-9._-]/g, "")
    const resolved = path.join(UPLOADS_DIR, name)
    if (existsSync(resolved)) return resolved
  }
  return filePath
}

export async function POST(req: Request) {
  let body: Partial<GenerateOpts>
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ error: "بيانات غير صالحة" }, { status: 400 })
  }

  const bgType = (validBgTypes.includes(String(body.background?.type) as typeof validBgTypes[number])
    ? body.background!.type
    : "animated") as GenerateOpts["background"]["type"]

  const opts: GenerateOpts = {
    reciter: String(body.reciter || ""),
    surah: Number(body.surah),
    from: Number(body.from),
    to: Number(body.to),
    fontId: String(body.fontId || "amiri"),
    fontSize: Math.max(60, Math.min(360, Number(body.fontSize) || 240)),
    textColor: String(body.textColor || "#FFFFFF"),
    outlineColor: String(body.outlineColor || "#000000"),
    translation: String(body.translation || "none"),
    translationColor: String(body.translationColor || "#FFE49B"),
    translationOutline: String(body.translationOutline || "#000000"),
    translationFontId: String(body.translationFontId || "cairo"),
    background: {
      type: bgType,
      color1: String(body.background?.color1 || "#0b3d2e"),
      color2: String(body.background?.color2 || "#1f6f4a"),
      filePath: bgType === "file" ? resolveFilePath(String(body.background?.filePath || "")) : undefined,
    },
  }

  const err = validateRequest(opts)
  if (err) return NextResponse.json({ error: err }, { status: 400 })

  const jobId = crypto.randomUUID().replace(/-/g, "")
  setJob(jobId, { status: "queued", step: "بدء", progress: 0 })

  generateVideo(jobId, opts).catch((e) => {
    console.error("[v0] background error:", e)
  })

  return NextResponse.json({ jobId })
}
