export interface NameEntry {
  name: string
  id: string | null
  match_type: 'CM' | 'AM' | 'RV' | null  // CM = Custom/Manual, AM = Automatic, RV = Review
}

export type MatchTypeFilter = 'ALL' | 'CM' | 'AM' | 'RV' | 'NM'  // NM = Not Matched

export interface ManualMatch {
  a_names: string[]
  b_name: string
  b_id: string | null
  created_at: string
  notes: string
}

export interface AutoMatch {
  a_names: string[]
  b_name: string
  b_id: string | null
  decision: string
  score: number
}

export async function fetchANames(query: string = ''): Promise<string[]> {
  const url = query ? `/api/names/a?q=${encodeURIComponent(query)}` : '/api/names/a'
  const res = await fetch(url)
  if (!res.ok) throw new Error('Failed to fetch A names')
  return res.json()
}

export async function fetchBNames(query: string = '', filter: MatchTypeFilter = 'ALL'): Promise<NameEntry[]> {
  const params = new URLSearchParams()
  if (query) params.set('q', query)
  if (filter && filter !== 'ALL') params.set('filter', filter)
  const url = params.toString() ? `/api/names/b?${params}` : '/api/names/b'
  const res = await fetch(url)
  if (!res.ok) throw new Error('Failed to fetch B names')
  return res.json()
}

export async function fetchMatches(): Promise<ManualMatch[]> {
  const res = await fetch('/api/matches')
  if (!res.ok) throw new Error('Failed to fetch matches')
  return res.json()
}

export async function fetchAutoMatch(bName: string): Promise<AutoMatch | null> {
  const res = await fetch(`/api/auto-matches/${encodeURIComponent(bName)}`)
  if (!res.ok) return null
  const data = await res.json()
  return data || null
}

export async function createMatch(
  a_names: string[],
  b_name: string,
  b_id: string | null,
  notes: string = ''
): Promise<ManualMatch> {
  const res = await fetch('/api/matches', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ a_names, b_name, b_id, notes }),
  })
  if (!res.ok) throw new Error('Failed to create match')
  return res.json()
}

export async function deleteMatch(index: number): Promise<void> {
  const res = await fetch(`/api/matches/${index}`, { method: 'DELETE' })
  if (!res.ok) throw new Error('Failed to delete match')
}

export interface FinalizeResult {
  success: boolean
  output: string
  top_matched: string
  cup_matched: string
  total_rows: number
  manual_matches_applied: number
}

export async function finalizeMatches(): Promise<FinalizeResult> {
  const res = await fetch('/api/finalize', { method: 'POST' })
  if (!res.ok) throw new Error('Failed to finalize matches')
  return res.json()
}

export async function fetchReviewANames(): Promise<string[]> {
  const res = await fetch('/api/review-a-names')
  if (!res.ok) throw new Error('Failed to fetch review A names')
  return res.json()
}
