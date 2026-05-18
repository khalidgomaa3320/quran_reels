import { NextResponse } from "next/server"
import { readFile } from "node:fs/promises"
import { existsSync } from "node:fs"
import path from "node:path"

export const runtime = "nodejs"
export const dynamic = "force-dynamic"

const UPLOADS_DIR = path.join(process.cwd(), "outputs", "uploads")

export async function GET(_req: Request, { params }: { params: Promise<{ name: string }> }) {
  const { name } = await params
  const safe = name.replace(/[^A-Za-z0-9._-]/g, "")
  const filePath = path.join(UPLOADS_DIR, safe)

  if (!existsSync(filePath)) {
    return NextResponse.json({ error: "الملف غير موجود" }, { status: 404 })
  }

  const ext = path.extname(safe).toLowerCase()
  const mimeMap: Record<string, string> = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
    ".webm": "video/webm",
  }
  const contentType = mimeMap[ext] || "application/octet-stream"

  const buffer = await readFile(filePath)
  return new NextResponse(buffer, {
    headers: {
      "Content-Type": contentType,
      "Cache-Control": "public, max-age=86400",
    },
  })
}
