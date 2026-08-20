// Data Ingestion — two independent upload slots (capstone assessment data,
// attendance data), each analyzed (parsed + column-classified) as soon as a
// file is picked, with nothing committed to the live dataset until
// "Confirm and Ingest" is pressed. Column classification (Kept/Skipped/New)
// is shared across both slots in one panel, tagged by source dataset.
import { useRef, useState, useCallback } from 'react';
import api from '../services/api';

const IconCloud = () => (
  <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="16 16 12 12 8 16"/>
    <line x1="12" y1="12" x2="12" y2="21"/>
    <path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3"/>
  </svg>
);

const IconCheck = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="20 6 9 17 4 12"/>
  </svg>
);

function Spinner({ label = 'Processing…' }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center' }}>
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
        strokeWidth="2.5" style={{ animation: 'spin 0.8s linear infinite', marginRight: 8 }}>
        <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
      </svg>
      {label}
    </span>
  );
}

// ── One upload card — capstone or attendance, fully independent state ────────

function UploadCard({ kind, title, hint, maxSizeMB, analyzeUrl, onAnalyzed, onCleared, committed }) {
  const fileRef = useRef(null);
  const [dragging, setDragging] = useState(false);
  const [file,     setFile]     = useState(null);
  const [status,   setStatus]   = useState('IDLE'); // IDLE | ANALYZING | ANALYZED | ERROR
  const [error,    setError]    = useState(null);
  const [analysis, setAnalysis] = useState(null);

  const fmtSize = bytes => {
    if (bytes < 1024)      return `${bytes} B`;
    if (bytes < 1024*1024) return `${(bytes/1024).toFixed(1)} KB`;
    return `${(bytes/(1024*1024)).toFixed(1)} MB`;
  };

  const analyze = useCallback(async (f) => {
    setStatus('ANALYZING');
    setError(null);
    try {
      const form = new FormData();
      form.append('file', f);
      // Override the client's global 30s timeout for this call specifically —
      // a real, found-and-fixed bug: a large multipart upload (attendance
      // files run up to 200MB) can legitimately take longer than 30s to
      // serialize and transmit client-side, well before the server sees
      // anything. Confirmed via CDP network inspection on a real 34MB
      // upload: the request was aborted client-side ("canceled: true",
      // net::ERR_ABORTED) at exactly the 30s mark, even though the
      // server itself processes the same file in ~1s once it arrives —
      // this was the browser's own axios timeout firing, not a server or
      // network problem.
      const res = await api.post(analyzeUrl, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 600000,
      });
      setAnalysis(res.data);
      setStatus('ANALYZED');
      onAnalyzed(kind, res.data, f);
    } catch (err) {
      setError(err.response?.data?.detail || 'Analysis failed. Please try again.');
      setStatus('ERROR');
      onAnalyzed(kind, null, null);
    }
  }, [analyzeUrl, kind, onAnalyzed]);

  const pickFile = useCallback(f => {
    if (!f) return;
    const ext = f.name.split('.').pop().toLowerCase();
    if (ext !== 'csv') {
      setError('Unsupported file type. Only .csv files are accepted.');
      return;
    }
    if (f.size > maxSizeMB * 1024 * 1024) {
      setError(`File exceeds the ${maxSizeMB} MB limit.`);
      return;
    }
    setFile(f);
    setError(null);
    analyze(f);
  }, [maxSizeMB, analyze]);

  const onDragOver  = e => { e.preventDefault(); setDragging(true); };
  const onDragLeave = ()  => setDragging(false);
  const onDrop      = e  => { e.preventDefault(); setDragging(false); pickFile(e.dataTransfer.files[0]); };
  const onInput     = e  => pickFile(e.target.files[0]);

  const handleReset = () => {
    setFile(null); setStatus('IDLE'); setError(null); setAnalysis(null);
    if (fileRef.current) fileRef.current.value = '';
    onCleared(kind);
  };

  return (
    <div style={s.uploadCard}>
      <h3 style={s.uploadCardTitle}>{title}</h3>
      <div
        style={{ ...s.dropZone, ...(dragging ? s.dropActive : {}) }}
        onDragOver={onDragOver} onDragLeave={onDragLeave} onDrop={onDrop}
        onClick={() => !file && fileRef.current?.click()}
      >
        <input ref={fileRef} type="file" accept=".csv" style={{ display: 'none' }} onChange={onInput} />
        <div style={{ color: 'rgba(255,255,255,0.85)', marginBottom: 8 }}><IconCloud /></div>
        <p style={s.dropTitle}>{file ? file.name : 'Drag and drop, or browse'}</p>
        <p style={s.dropSub}>{file ? fmtSize(file.size) : hint}</p>
        {!file && (
          <button style={s.browseBtn} onClick={e => { e.stopPropagation(); fileRef.current?.click(); }}>
            Browse File
          </button>
        )}
      </div>

      {status === 'ANALYZING' && <p style={s.statusLine}><Spinner label="Analyzing…" /></p>}
      {error && <p style={s.errorLine}>⚠ {error}</p>}
      {status === 'ANALYZED' && analysis && (
        <div style={s.analyzedRow}>
          <span style={s.analyzedRowLabel}>Detected</span>
          <strong>{analysis.row_count.toLocaleString()} rows</strong>
          {analysis.subjects != null && <span style={s.analyzedSub}>· {analysis.subjects} subjects</span>}
        </div>
      )}
      {committed != null && (
        <div style={s.committedBanner}>
          <span style={s.committedIcon}><IconCheck /></span>
          Committed — {committed.row_count.toLocaleString()} rows live
        </div>
      )}

      {file && (
        <button style={s.resetBtn} onClick={handleReset}>Remove file</button>
      )}
    </div>
  );
}

// ── Column check panel ────────────────────────────────────────────────────────

function ColumnChip({ label, sourceKind, onClick, style }) {
  return (
    <button
      onClick={onClick}
      style={{ ...s.colChip, ...(onClick ? { cursor: 'pointer' } : { cursor: 'default' }), ...style }}
    >
      {label}
      <span style={s.colChipTag}>{sourceKind}</span>
    </button>
  );
}

function ColumnCheckPanel({ capstoneCols, attendanceCols, onDecide }) {
  const [showAllKept,    setShowAllKept]    = useState(false);
  const [reviewingNew,   setReviewingNew]   = useState(null); // {kind, column} | null
  const [hoveredSkip,    setHoveredSkip]    = useState(null); // "kind:column" | null

  if (!capstoneCols && !attendanceCols) return null;

  const kept = [
    ...(capstoneCols?.keep   ?? []).map(c => ({ column: c, kind: 'capstone' })),
    ...(attendanceCols?.keep ?? []).map(c => ({ column: c, kind: 'attendance' })),
  ];
  const skipped = [
    ...(capstoneCols?.skip   ?? []).map(s => ({ ...s, kind: 'capstone' })),
    ...(attendanceCols?.skip ?? []).map(s => ({ ...s, kind: 'attendance' })),
  ];
  const fresh = [
    ...(capstoneCols?.new   ?? []).map(c => ({ column: c, kind: 'capstone' })),
    ...(attendanceCols?.new ?? []).map(c => ({ column: c, kind: 'attendance' })),
  ];

  const keptVisible = showAllKept ? kept : kept.slice(0, 3);

  return (
    <div style={s.card}>
      <h3 style={s.cardTitle}>Column Check</h3>
      <div style={s.colGrid}>
        {/* Kept */}
        <div>
          <p style={{ ...s.colHeader, color: '#059669' }}>Kept ({kept.length})</p>
          <div style={s.colList}>
            {keptVisible.map((c, i) => (
              <ColumnChip key={`${c.kind}-${c.column}-${i}`} label={c.column} sourceKind={c.kind}
                style={{ background: '#ECFDF5', color: '#065F46', borderColor: '#A7F3D0' }} />
            ))}
            {kept.length === 0 && <p style={s.emptyNote}>None yet</p>}
          </div>
          {kept.length > 3 && (
            <button style={s.showMoreBtn} onClick={() => setShowAllKept(v => !v)}>
              {showAllKept ? 'Show fewer' : `+${kept.length - 3} more`}
            </button>
          )}
        </div>

        {/* Skipped */}
        <div>
          <p style={{ ...s.colHeader, color: '#D97706' }}>Skipped ({skipped.length})</p>
          <div style={s.colList}>
            {skipped.map((c, i) => {
              const key = `${c.kind}:${c.column}`;
              return (
                <div key={key} style={{ position: 'relative' }}>
                  <ColumnChip
                    label={c.column} sourceKind={c.kind}
                    onClick={() => setHoveredSkip(v => v === key ? null : key)}
                    style={{ background: '#FFFBEB', color: '#92400E', borderColor: '#FDE68A' }}
                  />
                  {hoveredSkip === key && (
                    <div style={s.reasonPopover}>{c.reason}</div>
                  )}
                </div>
              );
            })}
            {skipped.length === 0 && <p style={s.emptyNote}>None</p>}
          </div>
        </div>

        {/* New */}
        <div>
          <p style={{ ...s.colHeader, color: '#DC2626' }}>New ({fresh.length})</p>
          <div style={s.colList}>
            {fresh.map((c, i) => {
              const key = `${c.kind}:${c.column}`;
              const isReviewing = reviewingNew && reviewingNew.kind === c.kind && reviewingNew.column === c.column;
              return (
                <div key={key} style={{ position: 'relative' }}>
                  <ColumnChip
                    label={c.column} sourceKind={c.kind}
                    onClick={() => setReviewingNew(v => isReviewing ? null : { kind: c.kind, column: c.column })}
                    style={{ background: '#FEF2F2', color: '#991B1B', borderColor: '#FCA5A5', fontWeight: 700 }}
                  />
                  {isReviewing && (
                    <div style={s.reviewPopover}>
                      <p style={s.reviewPopoverText}>Unrecognized column — decide once, applies to every future upload:</p>
                      <div style={{ display: 'flex', gap: 6 }}>
                        <button
                          style={s.reviewKeepBtn}
                          onClick={() => { onDecide(c.kind, c.column, 'keep'); setReviewingNew(null); }}
                        >
                          Keep
                        </button>
                        <button
                          style={s.reviewSkipBtn}
                          onClick={() => { onDecide(c.kind, c.column, 'permanently_skip'); setReviewingNew(null); }}
                        >
                          Permanently Skip
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
            {fresh.length === 0 && <p style={s.emptyNote}>None</p>}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────────

export default function DataIngestion() {
  const [capstoneAnalysis,   setCapstoneAnalysis]   = useState(null);
  const [capstoneFile,       setCapstoneFile]        = useState(null);
  const [attendanceAnalysis, setAttendanceAnalysis]  = useState(null);
  const [attendanceFile,     setAttendanceFile]      = useState(null);

  const [committing, setCommitting] = useState(false);
  const [commitError, setCommitError] = useState(null);
  const [capstoneResult,   setCapstoneResult]   = useState(null);
  const [attendanceResult, setAttendanceResult] = useState(null);

  const handleAnalyzed = (kind, data, file) => {
    if (kind === 'capstone') { setCapstoneAnalysis(data); setCapstoneFile(data ? file : null); }
    else                     { setAttendanceAnalysis(data); setAttendanceFile(data ? file : null); }
  };
  const handleCleared = (kind) => {
    if (kind === 'capstone') { setCapstoneAnalysis(null); setCapstoneFile(null); setCapstoneResult(null); }
    else                     { setAttendanceAnalysis(null); setAttendanceFile(null); setAttendanceResult(null); }
  };

  const reanalyze = async (kind) => {
    const file = kind === 'capstone' ? capstoneFile : attendanceFile;
    if (!file) return;
    const url = kind === 'capstone' ? '/api/ingest/capstone/analyze' : '/api/ingest/attendance/analyze';
    try {
      const form = new FormData();
      form.append('file', file);
      const res = await api.post(url, form, { headers: { 'Content-Type': 'multipart/form-data' } });
      if (kind === 'capstone') setCapstoneAnalysis(res.data);
      else setAttendanceAnalysis(res.data);
    } catch { /* leave prior analysis in place on failure */ }
  };

  const handleDecide = async (kind, column, decision) => {
    try {
      await api.post('/api/ingest/columns/decide', { kind, column, decision });
      await reanalyze(kind);
    } catch { /* surfaced implicitly — column stays in New if this fails */ }
  };

  const handleConfirm = async () => {
    setCommitting(true);
    setCommitError(null);
    try {
      if (capstoneAnalysis) {
        const res = await api.post('/api/ingest/capstone/confirm', { token: capstoneAnalysis.token });
        setCapstoneResult(res.data);
      }
      if (attendanceAnalysis) {
        const res = await api.post('/api/ingest/attendance/confirm', { token: attendanceAnalysis.token });
        setAttendanceResult(res.data);
      }
    } catch (err) {
      setCommitError(err.response?.data?.detail || 'Ingestion failed. Please try again.');
    } finally {
      setCommitting(false);
    }
  };

  const canConfirm = (capstoneAnalysis || attendanceAnalysis) && !committing;
  const hasResult  = capstoneResult || attendanceResult;

  return (
    <div>
      <div style={s.pageHeader}>
        <h1 style={s.pageTitle}>Data Ingestion</h1>
        <p style={s.pageSub}>Upload and process capstone and attendance datasets</p>
      </div>

      {/* ── Two upload cards side by side ── */}
      <div style={s.uploadRow}>
        <UploadCard
          kind="capstone"
          title="Capstone Data"
          hint="Supported: .csv — Max 50MB"
          maxSizeMB={50}
          analyzeUrl="/api/ingest/capstone/analyze"
          onAnalyzed={handleAnalyzed}
          onCleared={handleCleared}
          committed={capstoneResult}
        />
        <UploadCard
          kind="attendance"
          title="Attendance Data"
          hint="Supported: .csv — Max 200MB"
          maxSizeMB={200}
          analyzeUrl="/api/ingest/attendance/analyze"
          onAnalyzed={handleAnalyzed}
          onCleared={handleCleared}
          committed={attendanceResult}
        />
      </div>

      {/* ── Column check panel ── */}
      <ColumnCheckPanel
        capstoneCols={capstoneAnalysis?.columns}
        attendanceCols={attendanceAnalysis?.columns}
        onDecide={handleDecide}
      />

      {/* ── Summary metric cards (after commit) ── */}
      {hasResult && (
        <div style={s.cardRow}>
          <div style={s.statCard}>
            <p style={s.cardLabel}>Enrolments Processed</p>
            <p style={s.cardValue}>
              {capstoneResult ? capstoneResult.row_count.toLocaleString() : '— — —'}
            </p>
          </div>
          <div style={s.statCard}>
            <p style={s.cardLabel}>Attendance Match Rate</p>
            <p style={s.cardValue}>
              {attendanceResult?.match_rate != null ? `${attendanceResult.match_rate}%` : '— — —'}
            </p>
          </div>
          <div style={s.statCard}>
            <p style={s.cardLabel}>Subjects Reclassified</p>
            <p style={s.cardValue}>
              {capstoneResult ? capstoneResult.subjects_reclassified : '— — —'}
            </p>
          </div>
        </div>
      )}

      {/* ── Status bar (after commit) ── */}
      {capstoneResult && (
        <div style={s.statusBar}>
          <div style={{
            ...s.statusRow,
            background: capstoneResult.retrain.triggered ? '#EFF6FF' : '#F8FAFC',
            color:      capstoneResult.retrain.triggered ? '#1D4ED8' : '#5A7A8A',
          }}>
            {capstoneResult.retrain.triggered ? '🔄' : 'ℹ'} {capstoneResult.retrain.reason}
            {capstoneResult.retrain.triggered && capstoneResult.retrain.candidate_version && (
              <strong> — candidate {capstoneResult.retrain.candidate_version} registered</strong>
            )}
          </div>
          <div style={s.statusRowConstraint}>
            🔒 {capstoneResult.promotion_note}
          </div>
        </div>
      )}

      {commitError && <div style={s.errorBanner}>⚠ {commitError}</div>}

      {/* ── Confirm and ingest ── */}
      <div style={s.actions}>
        <button
          style={{ ...s.btnPrimary, opacity: canConfirm ? 1 : 0.5 }}
          disabled={!canConfirm}
          onClick={handleConfirm}
        >
          {committing ? <Spinner label="Ingesting…" /> : 'Confirm and Ingest'}
        </button>
      </div>
    </div>
  );
}

const s = {
  pageHeader: { marginBottom: 24 },
  pageTitle:  { margin: '0 0 4px', fontSize: 24, fontWeight: 500, color: '#1A2E40' },
  pageSub:    { margin: 0, fontSize: 13, color: '#5A7A8A' },

  uploadRow: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 20 },
  uploadCard: { background: '#fff', border: '0.5px solid #DDE4EA', borderRadius: 12, padding: '18px 20px' },
  uploadCardTitle: { margin: '0 0 12px', fontSize: 14, fontWeight: 600, color: '#1A2E40' },

  dropZone: {
    background: '#2E6E8E', border: '2px dashed rgba(255,255,255,0.35)', borderRadius: 12,
    padding: '28px 16px', display: 'flex', flexDirection: 'column', alignItems: 'center',
    gap: 4, cursor: 'pointer', transition: 'all 0.2s', userSelect: 'none',
  },
  dropActive: { background: '#235a74', borderColor: 'rgba(255,255,255,0.7)' },
  dropTitle:  { margin: '4px 0 0', fontSize: 14, fontWeight: 600, color: '#fff', textAlign: 'center' },
  dropSub:    { margin: 0, fontSize: 12, color: 'rgba(255,255,255,0.7)', textAlign: 'center' },
  browseBtn:  {
    marginTop: 8, padding: '7px 20px', background: '#fff', color: '#2E6E8E',
    border: 'none', borderRadius: 7, fontSize: 12, fontWeight: 600, cursor: 'pointer',
  },

  statusLine: { fontSize: 12, color: '#5A7A8A', margin: '10px 0 0' },
  errorLine:  { fontSize: 12, color: '#DC2626', margin: '10px 0 0' },
  analyzedRow: { display: 'flex', alignItems: 'center', gap: 6, marginTop: 10, fontSize: 13, color: '#1A2E40' },
  analyzedRowLabel: { fontSize: 11, fontWeight: 600, color: '#8BA5B8', textTransform: 'uppercase' },
  analyzedSub: { color: '#5A7A8A', fontSize: 12 },
  committedBanner: {
    display: 'flex', alignItems: 'center', gap: 8, marginTop: 10,
    fontSize: 12, fontWeight: 600, color: '#065F46', background: '#ECFDF5',
    border: '1px solid #A7F3D0', borderRadius: 8, padding: '8px 12px',
  },
  committedIcon: {
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    width: 18, height: 18, borderRadius: '50%', background: '#059669', color: '#fff', flexShrink: 0,
  },
  resetBtn: {
    marginTop: 10, padding: '6px 14px', borderRadius: 7, border: '0.5px solid #C5D2DC',
    background: '#fff', color: '#64748B', fontSize: 12, cursor: 'pointer',
  },

  card:      { background: '#fff', border: '0.5px solid #DDE4EA', borderRadius: 12, padding: '20px', marginBottom: 20 },
  cardTitle: { margin: '0 0 16px', fontSize: 14, fontWeight: 600, color: '#1A2E40' },
  colGrid:   { display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 20 },
  colHeader: { margin: '0 0 10px', fontSize: 12, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.4 },
  colList:   { display: 'flex', flexDirection: 'column', gap: 6 },
  emptyNote: { fontSize: 12, color: '#94A3B8', margin: 0 },
  colChip: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8,
    border: '1px solid', borderRadius: 7, padding: '6px 10px', fontSize: 12.5,
    fontFamily: "'SF Mono','Fira Code',monospace", textAlign: 'left', width: '100%',
  },
  colChipTag: {
    fontSize: 9.5, fontWeight: 700, textTransform: 'uppercase', opacity: 0.65,
    fontFamily: "-apple-system, sans-serif", flexShrink: 0,
  },
  showMoreBtn: {
    marginTop: 6, background: 'none', border: 'none', color: '#2E6E8E',
    fontSize: 12, fontWeight: 600, cursor: 'pointer', padding: 0,
  },
  reasonPopover: {
    position: 'absolute', top: 'calc(100% + 4px)', left: 0, zIndex: 50,
    background: '#1A2E40', color: '#fff', fontSize: 11.5, lineHeight: 1.5,
    borderRadius: 8, padding: '10px 12px', width: 260, boxShadow: '0 6px 18px rgba(0,0,0,0.18)',
  },
  reviewPopover: {
    position: 'absolute', top: 'calc(100% + 4px)', left: 0, zIndex: 50,
    background: '#fff', border: '1px solid #DDE4EA', borderRadius: 8, padding: '10px 12px',
    width: 240, boxShadow: '0 6px 18px rgba(0,0,0,0.14)',
  },
  reviewPopoverText: { margin: '0 0 8px', fontSize: 11.5, color: '#475569', lineHeight: 1.4 },
  reviewKeepBtn: {
    flex: 1, padding: '6px 0', borderRadius: 6, border: 'none',
    background: '#059669', color: '#fff', fontSize: 11.5, fontWeight: 600, cursor: 'pointer',
  },
  reviewSkipBtn: {
    flex: 1, padding: '6px 0', borderRadius: 6, border: 'none',
    background: '#DC2626', color: '#fff', fontSize: 11.5, fontWeight: 600, cursor: 'pointer',
  },

  cardRow:   { display: 'flex', gap: 16, marginBottom: 20 },
  statCard:  {
    flex: 1, background: '#fff', border: '0.5px solid #DDE4EA',
    borderRadius: 10, padding: '18px 22px', display: 'flex', flexDirection: 'column', gap: 8,
  },
  cardLabel: { margin: 0, fontSize: 11, fontWeight: 700, color: '#94A3B8', textTransform: 'uppercase', letterSpacing: 0.5 },
  cardValue: { margin: 0, fontSize: 26, fontWeight: 700, color: '#1A2E40', letterSpacing: -0.5 },

  statusBar: { display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 20 },
  statusRow: {
    borderRadius: 8, padding: '10px 16px', fontSize: 13, fontWeight: 500,
  },
  statusRowConstraint: {
    borderRadius: 8, padding: '10px 16px', fontSize: 13, fontWeight: 600,
    background: '#F1F5F9', color: '#334155', border: '0.5px solid #DDE4EA',
  },

  errorBanner: {
    background: 'rgba(220,38,38,0.08)', border: '1px solid rgba(220,38,38,0.25)',
    color: '#DC2626', borderRadius: 8, padding: '10px 16px', fontSize: 13, marginBottom: 16,
  },

  actions:    { display: 'flex', gap: 12, marginBottom: 28 },
  btnPrimary: {
    padding: '12px 32px', background: '#2E6E8E', color: '#fff',
    border: 'none', borderRadius: 8, fontSize: 14, fontWeight: 600,
    cursor: 'pointer', transition: 'opacity 0.15s', minWidth: 200,
  },
};
