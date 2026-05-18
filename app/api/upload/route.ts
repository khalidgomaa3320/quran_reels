import { NextResponse } from "next/server"
import { writeFile, mkdir } from "node:fs/promises"
import path from "node:path"
import crypto from "node:crypto"
import { moderateImage, ALLOWED_IMAGE_TYPES, ALLOWED_VIDEO_TYPES, MAX_IMAGE_SIZE, MAX_VIDEO_SIZE } from "@/lib/moderation"

export const runtime = "nodejs"
export const dynamic = "force-dynamic"

const UPLOADS_DIR = path.join(process.cwd(), "outputs", "uploads")

async function ensureDir() {
  await mkdir(UPLOADS_DIR, { recursive: true })
}

export async function POST(req: Request) {
  try {
    await ensureDir()

    const formData = await req.formData()
    const file = formData.get("file") as File | null
    if (!file) {
      return NextResponse.json({ error: "لم يتم رفع أي ملف" }, { status: 400 })
    }

    const ext = path.extname(file.name).toLowerCase()
    const allowedExts = [".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4", ".mov", ".avi", ".webm"]
    if (!allowedExts.includes(ext)) {
      return NextResponse.json(
        { error: `نوع الملف غير مدعوم: ${ext}. الأنواع المدعومة: ${allowedExts.join("، ")}` },
        { status: 400 },
      )
    }

    const isImage = ALLOWED_IMAGE_TYPES.has(file.type)
    const isVideo = ALLOWED_VIDEO_TYPES.has(file.type)
    if (!isImage && !isVideo) {
      return NextResponse.json(
        { error: "يُرجى رفع صورة (jpg, png, webp, gif) أو فيديو (mp4, mov, avi, webm)" },
        { status: 400 },
      )
    }

    const maxSize = isImage ? MAX_IMAGE_SIZE : MAX_VIDEO_SIZE
    if (file.size > maxSize) {
      const maxMB = maxSize / 1024 / 1024
      return NextResponse.json(
        { error: `الملف كبير جداً. الحد الأقصى ${maxMB} ميغابايت` },
        { status: 400 },
      )
    }

    const buffer = Buffer.from(await file.arrayBuffer())

    if (isImage) {
      const modResult = await moderateImage(buffer)
      if (!modResult.approved) {
        return NextResponse.json(
          { error: modResult.reason || "المحتوى غير متوافق مع الضوابط الشرعية" },
          { status: 422 },
        )
      }
    }

    const uniqueName = `${crypto.randomUUID().replace(/-/g, "").slice(0, 12)}${ext}`
    const dest = path.join(UPLOADS_DIR, uniqueName)
    await writeFile(dest, buffer)

    return NextResponse.json({
      fileName: uniqueName,
      filePath: `/api/uploads/${uniqueName}`,
      serverPath: dest,
      url: `/api/uploads/${uniqueName}`,
      type: isImage ? "image" : "video",
    })
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : "فشل رفع الملف"
    console.error("[upload] error:", e)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
