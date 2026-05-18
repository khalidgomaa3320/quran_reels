// In-memory job store. Module-level so it persists across requests in dev.
export type JobState = {
  status: "queued" | "running" | "done" | "error"
  step?: string
  progress?: number
  videoUrl?: string
  filename?: string
  error?: string
}

declare global {
  var __reelsJobs: Map<string, JobState> | undefined
}

export const jobs: Map<string, JobState> =
  global.__reelsJobs ?? (global.__reelsJobs = new Map())

export function setJob(id: string, patch: Partial<JobState>) {
  const prev = jobs.get(id) || { status: "queued" }
  jobs.set(id, { ...prev, ...patch })
}

export function getJob(id: string): JobState | undefined {
  return jobs.get(id)
}
