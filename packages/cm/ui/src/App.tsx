import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import {
  fetchANames,
  fetchBNames,
  fetchMatches,
  fetchAutoMatch,
  createMatch,
  deleteMatch,
  finalizeMatches,
  type NameEntry,
  type ManualMatch,
  type AutoMatch,
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
  listItemAutoSelected: {
    background: '#fff8e8',
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
  badge: {
    padding: '2px 6px',
    borderRadius: '4px',
    fontSize: '10px',
    fontWeight: 'bold',
    marginLeft: '8px',
  } as React.CSSProperties,
  badgeCM: {
    background: '#0066cc',
    color: 'white',
  } as React.CSSProperties,
  badgeAM: {
    background: '#ff9900',
    color: 'white',
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
  // Search mode: unified or split
  const [splitSearch, setSplitSearch] = useState(false)
  const [search, setSearch] = useState('')
  const [searchA, setSearchA] = useState('')
  const [searchB, setSearchB] = useState('')
  const debouncedSearch = useDebounce(search, 200)
  const debouncedSearchA = useDebounce(searchA, 200)
  const debouncedSearchB = useDebounce(searchB, 200)

  const [aNames, setANames] = useState<string[]>([])
  const [bNames, setBNames] = useState<NameEntry[]>([])
  const [matches, setMatches] = useState<ManualMatch[]>([])

  const [selectedA, setSelectedA] = useState<Set<string>>(new Set())
  const [selectedB, setSelectedB] = useState<NameEntry | null>(null)
  const [editingMatchIndex, setEditingMatchIndex] = useState<number | null>(null)

  // For viewing automatic matches (read-only)
  const [viewingAutoMatch, setViewingAutoMatch] = useState<AutoMatch | null>(null)

  // Filter toggle for A names list
  const [showOnlyMatched, setShowOnlyMatched] = useState(false)
  const aListRef = useRef<HTMLDivElement>(null)
  const firstMatchRef = useRef<HTMLDivElement>(null)

  const [loading, setLoading] = useState(true)
  const [finalizeStatus, setFinalizeStatus] = useState<{
    message: string
    downloads?: { name: string; url: string }[]
  } | null>(null)

  // Effective search queries based on mode
  const effectiveSearchA = splitSearch ? debouncedSearchA : debouncedSearch
  const effectiveSearchB = splitSearch ? debouncedSearchB : debouncedSearch

  // Load data on search change
  useEffect(() => {
    const loadData = async () => {
      setLoading(true)
      try {
        const [a, b] = await Promise.all([
          fetchANames(effectiveSearchA),
          fetchBNames(effectiveSearchB),
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
  }, [effectiveSearchA, effectiveSearchB])

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

  const handleBSelect = useCallback(async (entry: NameEntry) => {
    // If clicking the same B name, deselect it
    if (selectedB?.name === entry.name) {
      setSelectedB(null)
      setSelectedA(new Set())
      setEditingMatchIndex(null)
      setViewingAutoMatch(null)
      return
    }

    // Select the B name
    setSelectedB(entry)
    setViewingAutoMatch(null)

    // Check if this B name has a manual match first
    const matchIndex = matches.findIndex((m) => m.b_name === entry.name)
    if (matchIndex !== -1) {
      // Load the A names from the existing manual match
      setSelectedA(new Set(matches[matchIndex].a_names))
      setEditingMatchIndex(matchIndex)
      return
    }

    // No manual match, check for automatic match
    setEditingMatchIndex(null)

    if (entry.match_type === 'AM') {
      // Fetch automatic match details and pre-select the A names for editing
      const autoMatch = await fetchAutoMatch(entry.name)
      if (autoMatch) {
        setViewingAutoMatch(autoMatch)
        setSelectedA(new Set(autoMatch.a_names))
      } else {
        setSelectedA(new Set())
      }
    } else {
      setSelectedA(new Set())
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
      const [newMatches, newBNames] = await Promise.all([
        fetchMatches(),
        fetchBNames(effectiveSearchB),
      ])
      setMatches(newMatches)
      setBNames(newBNames)
      setSelectedA(new Set())
      setSelectedB(null)
      setEditingMatchIndex(null)
      setViewingAutoMatch(null)
    } catch (err) {
      console.error('Failed to create match:', err)
    }
  }, [selectedA, selectedB, editingMatchIndex, effectiveSearchB])

  const handleDeleteMatch = useCallback(async (index: number) => {
    try {
      await deleteMatch(index)
      const [newMatches, newBNames] = await Promise.all([
        fetchMatches(),
        fetchBNames(effectiveSearchB),
      ])
      setMatches(newMatches)
      setBNames(newBNames)
      // Clear editing state if we deleted the match being edited
      if (editingMatchIndex === index) {
        setEditingMatchIndex(null)
        setSelectedA(new Set())
        setSelectedB(null)
      }
    } catch (err) {
      console.error('Failed to delete match:', err)
    }
  }, [editingMatchIndex, effectiveSearchB])

  const handleEditMatch = useCallback((match: ManualMatch, index: number) => {
    // Load the match into the selection state for editing
    setSelectedA(new Set(match.a_names))
    setSelectedB({ name: match.b_name, id: match.b_id, match_type: 'CM' })
    setEditingMatchIndex(index)
    setViewingAutoMatch(null)
  }, [])

  const handleFinalize = useCallback(async () => {
    setFinalizeStatus({ message: 'Generating...' })
    try {
      const result = await finalizeMatches()
      const getFilename = (path: string) => path.split('/').pop() || ''
      setFinalizeStatus({
        message: `${result.manual_matches_applied} manual matches applied`,
        downloads: [
          {
            name: 'Results',
            url: `/api/download/${encodeURIComponent(getFilename(result.output))}`,
          },
          {
            name: 'Top Matched',
            url: `/api/download/${encodeURIComponent(getFilename(result.top_matched))}`,
          },
          {
            name: 'CUP Matched',
            url: `/api/download/${encodeURIComponent(getFilename(result.cup_matched))}`,
          },
        ],
      })
    } catch (err) {
      console.error('Failed to finalize:', err)
      setFinalizeStatus({ message: 'Error: Failed to finalize matches' })
    }
  }, [])

  const canLink = selectedA.size > 0 && selectedB !== null

  // Get sets of already-matched names for visual indication
  const matchedANames = useMemo(() => {
    const set = new Set<string>()
    matches.forEach((m) => m.a_names.forEach((n) => set.add(n)))
    return set
  }, [matches])

  // A names that are part of the currently viewed auto match
  const autoMatchedANames = useMemo(() => {
    if (!viewingAutoMatch) return new Set<string>()
    return new Set(viewingAutoMatch.a_names)
  }, [viewingAutoMatch])

  // Combined set of relevant A names (selected or auto-matched)
  const relevantANames = useMemo(() => {
    const set = new Set<string>(selectedA)
    autoMatchedANames.forEach((n) => set.add(n))
    return set
  }, [selectedA, autoMatchedANames])

  // Filtered A names list - always include relevant names when there's a B selection
  const displayedANames = useMemo(() => {
    if (showOnlyMatched && relevantANames.size > 0) {
      // Filter mode: show only relevant names that exist in the current data
      return aNames.filter((n) => relevantANames.has(n))
    }
    if (relevantANames.size > 0) {
      // Normal mode with B selection: show search results + relevant names
      // Add relevant names that aren't already in the search results
      const searchResultSet = new Set(aNames)
      const additionalRelevant = Array.from(relevantANames).filter(
        (n) => !searchResultSet.has(n)
      )
      // Put relevant names first, then the rest of search results
      const relevantInResults = aNames.filter((n) => relevantANames.has(n))
      const nonRelevantInResults = aNames.filter((n) => !relevantANames.has(n))
      return [...relevantInResults, ...additionalRelevant, ...nonRelevantInResults]
    }
    return aNames
  }, [aNames, showOnlyMatched, relevantANames])

  // Auto-scroll to first match when showing full list
  useEffect(() => {
    if (!showOnlyMatched && relevantANames.size > 0 && firstMatchRef.current) {
      firstMatchRef.current.scrollIntoView({ block: 'start', behavior: 'auto' })
    }
  }, [showOnlyMatched, relevantANames])

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <div style={styles.logo}>CM</div>
        {splitSearch ? (
          <>
            <div style={styles.searchContainer}>
              <input
                type="text"
                placeholder="Search A names..."
                value={searchA}
                onChange={(e) => setSearchA(e.target.value)}
                style={styles.searchInput}
              />
            </div>
            <div style={styles.searchContainer}>
              <input
                type="text"
                placeholder="Search B names..."
                value={searchB}
                onChange={(e) => setSearchB(e.target.value)}
                style={styles.searchInput}
              />
            </div>
          </>
        ) : (
          <div style={styles.searchContainer}>
            <input
              type="text"
              placeholder="Search company names..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={styles.searchInput}
            />
          </div>
        )}
        <button
          onClick={() => {
            if (splitSearch) {
              // Switching to single: carry over B (right-hand side) value
              setSearch(searchB)
            } else {
              // Switching to split: copy single value to both
              setSearchA(search)
              setSearchB(search)
            }
            setSplitSearch(!splitSearch)
          }}
          style={{
            padding: '12px 16px',
            background: splitSearch ? '#0066cc' : '#f0f0f0',
            color: splitSearch ? 'white' : '#333',
            border: '1px solid #ddd',
            borderRadius: '8px',
            cursor: 'pointer',
            fontSize: '14px',
            whiteSpace: 'nowrap',
          }}
          title={splitSearch ? 'Use single search' : 'Use separate search bars'}
        >
          {splitSearch ? '1' : '2'}
        </button>
      </div>

      <div style={styles.columns}>
        <div style={styles.column}>
          <div style={styles.columnHeader}>
            <span>A Names</span>
            <span style={styles.selectionInfo}>
              {loading ? 'Loading...' : `${aNames.length} results`}
              {selectedA.size > 0 && ` | ${selectedA.size} selected`}
              {viewingAutoMatch && ` | viewing ${viewingAutoMatch.a_names.length} auto-matched`}
              {relevantANames.size > 0 && (
                <label style={{ marginLeft: '8px', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={showOnlyMatched}
                    onChange={(e) => setShowOnlyMatched(e.target.checked)}
                    style={{ marginRight: '4px', cursor: 'pointer' }}
                  />
                  Filter
                </label>
              )}
            </span>
          </div>
          <div style={styles.list} ref={aListRef}>
            {(() => {
              let firstMatchFound = false
              return displayedANames.map((name, idx) => {
                const isSelected = selectedA.has(name)
                const isAutoMatched = autoMatchedANames.has(name)
                const isManualMatched = matchedANames.has(name)
                const isRelevant = relevantANames.has(name)

                // Assign ref to first relevant item
                const isFirstMatch = isRelevant && !firstMatchFound
                if (isFirstMatch) firstMatchFound = true

                return (
                  <div
                    key={`a-${idx}-${name}`}
                    ref={isFirstMatch ? firstMatchRef : undefined}
                    style={{
                      ...styles.listItem,
                      ...(isSelected ? styles.listItemSelected : {}),
                      ...(isAutoMatched && !isSelected ? styles.listItemAutoSelected : {}),
                      opacity: isManualMatched && !isSelected && !isAutoMatched ? 0.5 : 1,
                    }}
                    onClick={() => handleAToggle(name)}
                >
                  <input
                    type="checkbox"
                    checked={isSelected}
                    readOnly
                    style={{ ...styles.checkbox, pointerEvents: 'none' }}
                  />
                  <span>{name}</span>
                  {isAutoMatched && !isSelected && (
                    <span style={{ ...styles.badge, ...styles.badgeAM }}>AM</span>
                  )}
                  {isManualMatched && !isAutoMatched && !isSelected && (
                    <span style={{ marginLeft: 'auto', fontSize: '11px', color: '#999' }}>
                      (matched)
                    </span>
                  )}
                  </div>
                )
              })
            })()}
            {displayedANames.length === 0 && !loading && (
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
                {entry.match_type && (
                  <span
                    style={{
                      ...styles.badge,
                      ...(entry.match_type === 'CM' ? styles.badgeCM : styles.badgeAM),
                    }}
                  >
                    {entry.match_type}
                  </span>
                )}
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
          ...(viewingAutoMatch && canLink ? { background: '#ff9900' } : {}),
        }}
        onClick={handleLink}
        disabled={!canLink}
      >
        {viewingAutoMatch
          ? `Override Auto Match (score: ${viewingAutoMatch.score.toFixed(4)}) with Custom Match`
          : editingMatchIndex !== null
          ? 'Update'
          : 'Link'}{' '}
        ({selectedA.size} A names to {selectedB?.name || '...'})
      </button>

      <div style={styles.matchesPanel}>
        <div style={styles.columnHeader}>
          <span>Manual Matches ({matches.length})</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            {finalizeStatus && (
              <span style={{ fontSize: '12px', color: finalizeStatus.message.startsWith('Error') ? '#ff4444' : '#28a745' }}>
                {finalizeStatus.message}
                {finalizeStatus.downloads && (
                  <>
                    {' - '}
                    {finalizeStatus.downloads.map((dl, idx) => (
                      <span key={dl.name}>
                        {idx > 0 && ' | '}
                        <a
                          href={dl.url}
                          download
                          style={{ color: '#0066cc', textDecoration: 'underline' }}
                        >
                          {dl.name}
                        </a>
                      </span>
                    ))}
                  </>
                )}
              </span>
            )}
            <button
              onClick={handleFinalize}
              style={{
                padding: '6px 12px',
                background: '#28a745',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer',
                fontSize: '12px',
                fontWeight: '600',
              }}
            >
              Finalize
            </button>
          </div>
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
