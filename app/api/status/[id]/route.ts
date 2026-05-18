import { NextResponse } from "next/server"
import { getJob } from "@/lib/jobs"

export const runtime = "nodejs"
export const dynamic = "force-dynamic"

export async function GET(_req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params
  const job = getJob(id)
  if (!job) return NextResponse.json({ error: "غير موجود" }, { status: 404 })
  return NextResponse.json(job)
}
