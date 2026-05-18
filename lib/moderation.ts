import { createHash } from "node:crypto"

export type ModerationResult = {
  approved: boolean
  reason?: string
}

const BLOCKED_WORDS = new Set([
  "person", "people", "man", "woman", "boy", "girl", "baby", "human", "crowd",
  "dog", "cat", "bird", "fish", "horse", "cow", "sheep", "pig",
  "chicken", "duck", "rabbit", "elephant", "lion", "tiger", "bear",
  "deer", "fox", "wolf", "monkey", "snake", "lizard", "frog",
  "insect", "spider", "butterfly", "bee", "ant",
  "whale", "dolphin", "shark", "octopus", "eagle", "hawk", "owl", "parrot",
  "weapon", "gun", "knife", "sword", "bomb", "alcohol", "wine", "beer",
  "cigarette", "cigar", "cross", "idol", "statue", "nudity",
  "sexual", "porn", "naked", "violence", "gore", "drug",
])

async function classifyImageHF(
  buffer: Buffer,
  apiKey: string,
  labels: string[],
): Promise<Record<string, number>> {
  const res = await fetch(
    "https://api-inference.huggingface.co/models/openai/clip-vit-base-patch32",
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        inputs: buffer.toString("base64"),
        parameters: { candidate_labels: labels.join(", ") },
      }),
    },
  )
  if (!res.ok) throw new Error(`HF API ${res.status}`)
  const data = await res.json()
  const scores: Record<string, number> = {}
  if (data.labels && data.scores) {
    for (let i = 0; i < data.labels.length; i++) {
      scores[data.labels[i]] = data.scores[i]
    }
  }
  return scores
}

async function moderateViaHF(buffer: Buffer): Promise<ModerationResult> {
  const apiKey = process.env.HUGGINGFACE_API_KEY
  if (!apiKey) return { approved: true }

  const labels = [
    "islamic geometric pattern", "abstract art", "nature landscape", "mountains",
    "ocean", "sky", "stars", "calligraphy", "gradient", "solid color",
    "person", "animal", "dog", "cat", "horse", "bird",
    "nudity", "sexual content", "violence", "weapon", "alcohol",
    "cross", "idol", "statue", "flag", "political symbol",
  ]

  try {
    const scores = await classifyImageHF(buffer, apiKey, labels)

    const blockedCategories = labels.filter(
      (l) => BLOCKED_WORDS.has(l) && (scores[l] || 0) > 0.3,
    )

    if (blockedCategories.length > 0) {
      return {
        approved: false,
        reason: `المحتوى غير متوافق: تم اكتشاف (${blockedCategories.join("، ")})`,
      }
    }

    return { approved: true }
  } catch (e) {
    console.warn("[moderation] HF API failed, allowing:", e)
    return { approved: true }
  }
}

export async function moderateImage(buffer: Buffer): Promise<ModerationResult> {
  const hash = createHash("sha256").update(buffer).digest("hex")

  if (!process.env.HUGGINGFACE_API_KEY) {
    return { approved: true }
  }

  return moderateViaHF(buffer)
}

export const ALLOWED_IMAGE_TYPES = new Set([
  "image/jpeg",
  "image/png",
  "image/webp",
  "image/gif",
])

export const ALLOWED_VIDEO_TYPES = new Set([
  "video/mp4",
  "video/quicktime",
  "video/x-msvideo",
  "video/webm",
])

export const MAX_IMAGE_SIZE = 10 * 1024 * 1024
export const MAX_VIDEO_SIZE = 100 * 1024 * 1024
