import { useState, useEffect, useCallback, useMemo } from 'react'
import {
  fetchANames,
  fetchBNames,
  fetchMatches,
  createMatch,
  deleteMatch,
  type NameEntry,
  type ManualMatch,
} from './api'

const styles = {
  container: {
    maxWidth: '1400px',
    margin: '0 auto',
    padding: '20px',
    minHeight: '100vh',
  } as React.CSSProperties,
  header: {
    display: 'flex',
    alignItems: 'center',
    gap: '20px',
    marginBottom: '20px',
  } as React.CSSProperties,
  logo: {
    fontSize: '24px',
    fontWeight: 'bold',
    color: '#333',
  } as React.CSSProperties,
  searchContainer: {
    flex: 1,
  } as React.CSSProperties,
  searchInput: {
    width: '100%',
    padding: '12px 16px',
    fontSize: '16px',
    border: '1px solid #ddd',
    borderRadius: '8px',
    outline: 'none',
    transition: 'border-color 0.2s',
  } as React.CSSProperties,
  columns: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: '20px',
    marginBottom: '20px',
  } as React.CSSProperties,
  column: {
    background: 'white',
    borderRadius: '8px',
    border: '1px solid #ddd',
    overflow: 'hidden',
  } as React.CSSProperties,
  columnHeader: {
    padding: '12px 16px',
    borderBottom: '1px solid #ddd',
    fontWeight: '600',
    fontSize: '14px',
    color: '#666',
    display: 'flex',
    justifyContent: 'space-between',
  } as React.CSSProperties,
  list: {
    height: '400px',
    overflowY: 'auto',
  } as React.CSSProperties,
  listItem: {
    padding: '10px 16px',
    borderBottom: '1px solid #eee',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    fontFamily: 'monospace',
    fontSize: '13px',
  } as React.CSSProperties,
  listItemSelected: {
    background: '#e8f4ff',
  } as React.CSSProperties,
  checkbox: {
    width: '16px',
    height: '16px',
    cursor: 'pointer',
  } as React.CSSProperties,
  radio: {
    width: '16px',
    height: '16px',
    cursor: 'pointer',
  } as React.CSSProperties,
  linkButton: {
    width: '100%',
    padding: '12px',
    background: '#0066cc',
    color: 'white',
    border: 'none',
    borderRadius: '8px',
    fontSize: '14px',
    fontWeight: '600',
    cursor: 'pointer',
    marginBottom: '20px',
  } as React.CSSProperties,
  linkButtonDisabled: {
    background: '#ccc',
    cursor: 'not-allowed',
  } as React.CSSProperties,
  matchesPanel: {
    background: 'white',
    borderRadius: '8px',
    border: '1px solid #ddd',
    overflow: 'hidden',
  } as React.CSSProperties,
  matchItem: {
    padding: '12px 16px',
    borderBottom: '1px solid #eee',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    fontFamily: 'monospace',
    fontSize: '13px',
  } as React.CSSProperties,
  matchText: {
    flex: 1,
  } as React.CSSProperties,
  deleteButton: {
    padding: '4px 8px',
    background: '#ff4444',
    color: 'white',
    border: 'none',
    borderRadius: '4px',
    cursor: 'pointer',
    fontSize: '12px',
  } as React.CSSProperties,
  arrow: {
    color: '#666',
    margin: '0 8px',
  } as React.CSSProperties,
  emptyState: {
    padding: '40px',
    textAlign: 'center',
    color: '#999',
  } as React.CSSProperties,
  selectionInfo: {
    fontSize: '12px',
    color: '#666',
  } as React.CSSProperties,
}

function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value)

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedValue(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])

  return debouncedValue
}

export default function App() {
  const [search, setSearch] = useState('')
  const debouncedSearch = useDebounce(search, 200)

  const [aNames, setANames] = useState<string[]>([])
  const [bNames, setBNames] = useState<NameEntry[]>([])
  const [matches, setMatches] = useState<ManualMatch[]>([])

  const [selectedA, setSelectedA] = useState<Set<string>>(new Set())
  const [selectedB, setSelectedB] = useState<NameEntry | null>(null)
  const [editingMatchIndex, setEditingMatchIndex] = useState<number | null>(null)

  const [loading, setLoading] = useState(true)

  // Load data on search change
  useEffect(() => {
    const loadData = async () => {
      setLoading(true)
      try {
        const [a, b] = await Promise.all([
          fetchANames(debouncedSearch),
          fetchBNames(debouncedSearch),
        ])
        setANames(a)
        setBNames(b)
      } catch (err) {
        console.error('Failed to load data:', err)
      } finally {
        setLoading(false)
      }
    }
    loadData()
  }, [debouncedSearch])

  // Load matches on mount
  useEffect(() => {
    fetchMatches().then(setMatches).catch(console.error)
  }, [])

  const handleAToggle = useCallback((name: string) => {
    setSelectedA((prev) => {
      const next = new Set(prev)
      if (next.has(name)) {
        next.delete(name)
      } else {
        next.add(name)
      }
      return next
    })
  }, [])

  const handleBSelect = useCallback((entry: NameEntry) => {
    // If clicking the same B name, deselect it
    if (selectedB?.name === entry.name) {
      setSelectedB(null)
      setSelectedA(new Set())
      setEditingMatchIndex(null)
      return
    }

    // Select the B name
    setSelectedB(entry)

    // Check if this B name has an existing match
    const matchIndex = matches.findIndex((m) => m.b_name === entry.name)
    if (matchIndex !== -1) {
      // Load the A names from the existing match
      setSelectedA(new Set(matches[matchIndex].a_names))
      setEditingMatchIndex(matchIndex)
    } else {
      // No existing match, clear A selection
      setSelectedA(new Set())
      setEditingMatchIndex(null)
    }
  }, [selectedB, matches])

  const handleLink = useCallback(async () => {
    if (selectedA.size === 0 || !selectedB) return

    try {
      // If editing, delete the old match first
      if (editingMatchIndex !== null) {
        await deleteMatch(editingMatchIndex)
      }

      await createMatch(
        Array.from(selectedA),
        selectedB.name,
        selectedB.id
      )
      const newMatches = await fetchMatches()
      setMatches(newMatches)
      setSelectedA(new Set())
      setSelectedB(null)
      setEditingMatchIndex(null)
    } catch (err) {
      console.error('Failed to create match:', err)
    }
  }, [selectedA, selectedB, editingMatchIndex])

  const handleDeleteMatch = useCallback(async (index: number) => {
    try {
      await deleteMatch(index)
      const newMatches = await fetchMatches()
      setMatches(newMatches)
      // Clear editing state if we deleted the match being edited
      if (editingMatchIndex === index) {
        setEditingMatchIndex(null)
        setSelectedA(new Set())
        setSelectedB(null)
      }
    } catch (err) {
      console.error('Failed to delete match:', err)
    }
  }, [editingMatchIndex])

  const handleEditMatch = useCallback((match: ManualMatch, index: number) => {
    // Load the match into the selection state for editing
    setSelectedA(new Set(match.a_names))
    setSelectedB({ name: match.b_name, id: match.b_id })
    setEditingMatchIndex(index)
  }, [])

  const canLink = selectedA.size > 0 && selectedB !== null

  // Get sets of already-matched names for visual indication
  const matchedANames = useMemo(() => {
    const set = new Set<string>()
    matches.forEach((m) => m.a_names.forEach((n) => set.add(n)))
    return set
  }, [matches])

  const matchedBNames = useMemo(() => {
    return new Set(matches.map((m) => m.b_name))
  }, [matches])

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <div style={styles.logo}>CM</div>
        <div style={styles.searchContainer}>
          <input
            type="text"
            placeholder="Search company names..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={styles.searchInput}
          />
        </div>
      </div>

      <div style={styles.columns}>
        <div style={styles.column}>
          <div style={styles.columnHeader}>
            <span>A Names</span>
            <span style={styles.selectionInfo}>
              {loading ? 'Loading...' : `${aNames.length} results`}
              {selectedA.size > 0 && ` | ${selectedA.size} selected`}
            </span>
          </div>
          <div style={styles.list}>
            {aNames.map((name, idx) => (
              <div
                key={`a-${idx}-${name}`}
                style={{
                  ...styles.listItem,
                  ...(selectedA.has(name) ? styles.listItemSelected : {}),
                  opacity: matchedANames.has(name) ? 0.5 : 1,
                }}
                onClick={() => handleAToggle(name)}
              >
                <input
                  type="checkbox"
                  checked={selectedA.has(name)}
                  readOnly
                  style={{ ...styles.checkbox, pointerEvents: 'none' }}
                />
                <span>{name}</span>
                {matchedANames.has(name) && (
                  <span style={{ marginLeft: 'auto', fontSize: '11px', color: '#999' }}>
                    (matched)
                  </span>
                )}
              </div>
            ))}
            {aNames.length === 0 && !loading && (
              <div style={styles.emptyState}>No results</div>
            )}
          </div>
        </div>

        <div style={styles.column}>
          <div style={styles.columnHeader}>
            <span>B Names</span>
            <span style={styles.selectionInfo}>
              {loading ? 'Loading...' : `${bNames.length} results`}
              {selectedB && ' | 1 selected'}
            </span>
          </div>
          <div style={styles.list}>
            {bNames.map((entry, idx) => (
              <div
                key={`b-${idx}-${entry.name}`}
                style={{
                  ...styles.listItem,
                  ...(selectedB?.name === entry.name ? styles.listItemSelected : {}),
                  opacity: matchedBNames.has(entry.name) ? 0.5 : 1,
                }}
                onClick={() => handleBSelect(entry)}
              >
                <input
                  type="radio"
                  checked={selectedB?.name === entry.name}
                  readOnly
                  style={{ ...styles.radio, pointerEvents: 'none' }}
                />
                <span>{entry.name}</span>
                {entry.id !== null && (
                  <span style={{ marginLeft: 'auto', fontSize: '11px', color: '#999' }}>
                    #{entry.id}
                  </span>
                )}
              </div>
            ))}
            {bNames.length === 0 && !loading && (
              <div style={styles.emptyState}>No results</div>
            )}
          </div>
        </div>
      </div>

      <button
        style={{
          ...styles.linkButton,
          ...(canLink ? {} : styles.linkButtonDisabled),
        }}
        onClick={handleLink}
        disabled={!canLink}
      >
        {editingMatchIndex !== null ? 'Update' : 'Link'} Selected ({selectedA.size} A names to {selectedB?.name || '...'})
      </button>

      <div style={styles.matchesPanel}>
        <div style={styles.columnHeader}>
          <span>Manual Matches ({matches.length})</span>
        </div>
        {matches.length === 0 ? (
          <div style={styles.emptyState}>No manual matches yet</div>
        ) : (
          matches.map((match, index) => (
            <div
              key={index}
              style={{
                ...styles.matchItem,
                cursor: 'pointer',
                background: editingMatchIndex === index ? '#e8f4ff' : undefined,
              }}
              onClick={() => handleEditMatch(match, index)}
            >
              <div style={styles.matchText}>
                <span>{match.a_names.join(', ')}</span>
                <span style={styles.arrow}>&rarr;</span>
                <span>{match.b_name}</span>
                {match.b_id !== null && (
                  <span style={{ color: '#999', marginLeft: '8px' }}>
                    #{match.b_id}
                  </span>
                )}
              </div>
              <button
                style={styles.deleteButton}
                onClick={(e) => {
                  e.stopPropagation()
                  handleDeleteMatch(index)
                }}
              >
                x
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
