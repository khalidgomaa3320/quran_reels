import { promises as fs } from "node:fs"
import path from "node:path"
import { VIDEO_DIR } from "@/lib/video-pipeline"

export const runtime = "nodejs"
export const dynamic = "force-dynamic"

export async function GET(_req: Request, ctx: { params: Promise<{ name: string }> }) {
  const { name } = await ctx.params
  const decoded = decodeURIComponent(name)
  // Prevent path traversal
  if (decoded.includes("..") || decoded.includes("/") || decoded.includes("\\")) {
    return new Response("forbidden", { status: 403 })
  }
  const full = path.join(VIDEO_DIR, decoded)
  try {
    const data = await fs.readFile(full)
    return new Response(new Uint8Array(data), {
      status: 200,
      headers: {
        "Content-Type": "video/mp4",
        "Content-Length": String(data.length),
        "Content-Disposition": `inline; filename="${decoded}"`,
        "Cache-Control": "no-store",
      },
    })
  } catch {
    return new Response("not found", { status: 404 })
  }
}
