export interface NameEntry {
  name: string
  id: string | null
}

export interface ManualMatch {
  a_names: string[]
  b_name: string
  b_id: string | null
  created_at: string
  notes: string
}

export async function fetchANames(query: string = ''): Promise<string[]> {
  const url = query ? `/api/names/a?q=${encodeURIComponent(query)}` : '/api/names/a'
  const res = await fetch(url)
  if (!res.ok) throw new Error('Failed to fetch A names')
  return res.json()
}

export async function fetchBNames(query: string = ''): Promise<NameEntry[]> {
  const url = query ? `/api/names/b?q=${encodeURIComponent(query)}` : '/api/names/b'
  const res = await fetch(url)
  if (!res.ok) throw new Error('Failed to fetch B names')
  return res.json()
}

export async function fetchMatches(): Promise<ManualMatch[]> {
  const res = await fetch('/api/matches')
  if (!res.ok) throw new Error('Failed to fetch matches')
  return res.json()
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
