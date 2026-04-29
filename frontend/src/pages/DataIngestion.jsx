import React, { useRef, useState, useCallback } from 'react';
import Papa from 'papaparse';
import api from '../services/api';

const IconCloud = () => (
  <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="16 16 12 12 8 16"/><line x1="12" y1="12" x2="12" y2="21"/>
    <path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3"/>
  </svg>
);

const IconCheck = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="20 6 9 17 4 12"/>
  </svg>
);

const STATUS_STYLE = {
  IDLE:       { bg: '#EFF6FF', color: '#3B82F6', border: '#BFDBFE' },
  PROCESSING: { bg: '#FFFBEB', color: '#D97706', border: '#FDE68A' },
  DONE:       { bg: '#ECFDF5', color: '#059669', border: '#A7F3D0' },
};

export default function DataIngestion() {
  const fileInputRef = useRef(null);

  const [dragging, setDragging]       = useState(false);
  const [fileName, setFileName]       = useState(null);
  const [file, setFile]               = useState(null);
  const [rowCount, setRowCount]       = useState(null);
  const [anonymized, setAnonymized]   = useState(true);
  const [status, setStatus]           = useState('IDLE');
  const [parseError, setParseError]   = useState(null);
  const [uploadError, setUploadError] = useState(null);
  const [result, setResult]           = useState(null);

  const parseFile = useCallback((f) => {
    if (!f) return;
    const ext = f.name.split('.').pop().toLowerCase();
    if (!['csv', 'xlsx', 'json'].includes(ext)) {
      setParseError('Unsupported file type. Please upload .csv, .xlsx, or .json.');
      return;
    }
    if (f.size > 50 * 1024 * 1024) {
      setParseError('File exceeds the 50 MB limit.');
      return;
    }

    setParseError(null); setUploadError(null);
    setFileName(f.name); setFile(f);
    setResult(null); setStatus('IDLE'); setRowCount(null);

    if (ext === 'csv') {
      Papa.parse(f, {
        header: true, skipEmptyLines: true,
        complete: (res) => setRowCount(res.data.length),
        error:   ()    => setParseError('Could not read CSV — file may be corrupt.'),
      });
    } else if (ext === 'json') {
      const reader = new FileReader();
      reader.onload = (e) => {
        try {
          const data = JSON.parse(e.target.result);
          setRowCount(Array.isArray(data) ? data.length : Object.keys(data).length);
        } catch {
          setParseError('Could not read JSON — file may be corrupt.');
        }
      };
      reader.readAsText(f);
    }
  }, []);

  const onDragOver  = (e) => { e.preventDefault(); setDragging(true); };
  const onDragLeave = ()  => setDragging(false);
  const onDrop      = (e) => { e.preventDefault(); setDragging(false); parseFile(e.dataTransfer.files[0]); };
  const onFileInput = (e) => parseFile(e.target.files[0]);

  const handleProcess = async () => {
    if (!file) return;
    setStatus('PROCESSING'); setUploadError(null); setResult(null);

    try {
      const form = new FormData();
      form.append('file', file);
      const res = await api.post('/api/ingest', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setResult(res.data);
      setRowCount(res.data.row_count);
      setStatus('DONE');
    } catch (err) {
      setUploadError(err.response?.data?.detail || 'Upload failed. Please try again.');
      setStatus('IDLE');
    }
  };

  const handleReset = () => {
    setFileName(null); setFile(null); setRowCount(null);
    setStatus('IDLE'); setParseError(null); setUploadError(null);
    setResult(null); setAnonymized(true);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const st = STATUS_STYLE[status];
  const canProcess = file && status !== 'PROCESSING';

  return (
    <div>
      <div style={s.pageHeader}>
        <h1 style={s.pageTitle}>Data Ingestion</h1>
        <p style={s.pageSubtitle}>Upload and anonymise student dataset</p>
      </div>

      <div
        style={{ ...s.dropZone, ...(dragging ? s.dropZoneActive : {}) }}
        onDragOver={onDragOver} onDragLeave={onDragLeave} onDrop={onDrop}
      >
        <div style={{ color: dragging ? '#fff' : 'rgba(255,255,255,0.85)' }}>
          <IconCloud />
        </div>
        <p style={s.dropTitle}>{fileName || 'Drag and drop dataset here'}</p>
        <p style={s.dropSubtitle}>Supports .csv, .xlsx, .json — max 50 MB</p>
        <input ref={fileInputRef} type="file" accept=".csv,.xlsx,.json"
          style={{ display: 'none' }} onChange={onFileInput} />
        <button style={s.browseBtn} onClick={() => fileInputRef.current?.click()}>
          Browse File
        </button>
        {parseError && <p style={s.dropError}>{parseError}</p>}
      </div>

      <div style={s.sectionHeader}>
        <h2 style={s.sectionTitle}>Anonymize Data</h2>
        <p style={s.sectionSubtitle}>Strips PII fields before processing</p>
      </div>

      <div style={s.cardRow}>
        <div style={s.statCard}>
          <p style={s.cardLabel}>Row Count</p>
          <p style={s.cardValue}>
            {rowCount !== null ? Number(rowCount).toLocaleString() : '— — — — —'}
          </p>
        </div>

        <div style={s.statCard}>
          <p style={s.cardLabel}>Anonymized</p>
          <button
            style={{ ...s.toggleBtn, background: anonymized ? '#2E6E8E' : '#E2E8F0', color: anonymized ? '#fff' : '#64748B' }}
            onClick={() => setAnonymized(v => !v)}
          >
            {anonymized ? 'True' : 'False'}
          </button>
        </div>

        <div style={s.statCard}>
          <p style={s.cardLabel}>Status</p>
          <span style={{ ...s.statusBadge, background: st.bg, color: st.color, borderColor: st.border }}>
            {status}
          </span>
        </div>
      </div>

      {uploadError && (
        <div style={s.errorBanner}>
          <span>⚠</span> {uploadError}
        </div>
      )}

      <div style={s.actions}>
        <button
          style={{ ...s.btnPrimary, opacity: canProcess ? 1 : 0.5, cursor: canProcess ? 'pointer' : 'not-allowed' }}
          disabled={!canProcess}
          onClick={handleProcess}
        >
          {status === 'PROCESSING' ? 'Processing…' : 'Process dataset'}
        </button>
        <button style={s.btnSecondary} onClick={handleReset}>Reset</button>
      </div>

      {result && (
        <div style={s.resultSection}>
          <div style={s.successBanner}>
            <span style={s.successIcon}><IconCheck /></span>
            Dataset processed successfully — <strong>{result.row_count.toLocaleString()}</strong> rows ingested
            {result.columns?.length > 0 && (
              <span style={s.colCount}> · {result.columns.length} columns</span>
            )}
          </div>

          {result.columns?.length > 0 && (
            <div style={s.columnChips}>
              {result.columns.map(col => (
                <span key={col} style={s.chip}>{col}</span>
              ))}
            </div>
          )}

          {result.preview?.length > 0 && (
            <>
              <h3 style={s.previewTitle}>Preview — first {result.preview.length} rows</h3>
              <div style={s.tableWrapper}>
                <table style={s.table}>
                  <thead>
                    <tr>
                      {result.columns.map(col => (
                        <th key={col} style={s.th}>{col}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {result.preview.map((row, i) => (
                      <tr key={i} style={i % 2 === 0 ? s.trEven : s.trOdd}>
                        {result.columns.map(col => (
                          <td key={col} style={s.td}>
                            {row[col] === '' || row[col] == null ? '—' : String(row[col])}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

const s = {
  pageHeader:   { marginBottom: 28 },
  pageTitle:    { margin: '0 0 6px', fontSize: 26, fontWeight: 700, color: '#1E293B' },
  pageSubtitle: { margin: 0, fontSize: 14, color: '#64748B' },

  dropZone: {
    background: '#2E6E8E', border: '2px dashed rgba(255,255,255,0.35)', borderRadius: 14,
    padding: '48px 32px', display: 'flex', flexDirection: 'column', alignItems: 'center',
    gap: 10, cursor: 'pointer', transition: 'border-color 0.2s, background 0.2s',
    marginBottom: 32, userSelect: 'none',
  },
  dropZoneActive: { background: '#235a74', borderColor: 'rgba(255,255,255,0.7)' },
  dropTitle:    { margin: 0, fontSize: 17, fontWeight: 600, color: '#fff' },
  dropSubtitle: { margin: 0, fontSize: 13, color: 'rgba(255,255,255,0.7)' },
  browseBtn:    { marginTop: 8, padding: '10px 28px', background: '#fff', color: '#2E6E8E', border: 'none', borderRadius: 8, fontSize: 14, fontWeight: 600, cursor: 'pointer' },
  dropError:    { margin: 0, fontSize: 13, color: '#FCA5A5', background: 'rgba(0,0,0,0.2)', padding: '6px 14px', borderRadius: 6 },

  sectionHeader:   { marginBottom: 16 },
  sectionTitle:    { margin: '0 0 4px', fontSize: 16, fontWeight: 600, color: '#1E293B' },
  sectionSubtitle: { margin: 0, fontSize: 13, color: '#64748B' },

  cardRow:    { display: 'flex', gap: 16, marginBottom: 24 },
  statCard:   { flex: 1, background: '#fff', border: '0.5px solid #DDE4EA', borderRadius: 10, padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 10 },
  cardLabel:  { margin: 0, fontSize: 12, fontWeight: 600, color: '#94A3B8', textTransform: 'uppercase', letterSpacing: 0.6 },
  cardValue:  { margin: 0, fontSize: 28, fontWeight: 700, color: '#1E293B', letterSpacing: -0.5 },
  toggleBtn:  { padding: '6px 20px', borderRadius: 20, border: 'none', fontSize: 14, fontWeight: 600, cursor: 'pointer', alignSelf: 'flex-start' },
  statusBadge: { display: 'inline-block', padding: '5px 14px', borderRadius: 20, border: '1px solid', fontSize: 13, fontWeight: 600, alignSelf: 'flex-start' },

  errorBanner: {
    display: 'flex', alignItems: 'center', gap: 8,
    background: 'rgba(220,38,38,0.08)', border: '1px solid rgba(220,38,38,0.25)',
    color: '#DC2626', borderRadius: 8, padding: '10px 16px',
    fontSize: 13, marginBottom: 16,
  },

  actions:      { display: 'flex', gap: 12, marginBottom: 32 },
  btnPrimary:   { padding: '12px 28px', background: '#2E6E8E', color: '#fff', border: 'none', borderRadius: 8, fontSize: 14, fontWeight: 600, transition: 'opacity 0.15s' },
  btnSecondary: { padding: '12px 28px', background: '#fff', color: '#2E6E8E', border: '1.5px solid #2E6E8E', borderRadius: 8, fontSize: 14, fontWeight: 600, cursor: 'pointer' },

  resultSection: { display: 'flex', flexDirection: 'column', gap: 16 },

  successBanner: {
    display: 'flex', alignItems: 'center', gap: 10,
    background: '#ECFDF5', border: '1px solid #A7F3D0',
    color: '#065F46', borderRadius: 10, padding: '14px 20px',
    fontSize: 14, fontWeight: 500,
  },
  successIcon: {
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    width: 24, height: 24, borderRadius: '50%',
    background: '#059669', color: '#fff', flexShrink: 0,
  },
  colCount: { color: '#047857', fontWeight: 400 },

  columnChips: { display: 'flex', flexWrap: 'wrap', gap: 6 },
  chip: {
    background: '#EFF6FF', border: '1px solid #BFDBFE',
    color: '#1D4ED8', borderRadius: 6, padding: '3px 10px',
    fontSize: 12, fontWeight: 500, fontFamily: "'SF Mono','Fira Code',monospace",
  },

  previewTitle: { margin: '8px 0 0', fontSize: 14, fontWeight: 600, color: '#1E293B' },
  tableWrapper: {
    background: '#fff', border: '0.5px solid #DDE4EA', borderRadius: 10, overflow: 'auto', maxHeight: 340,
  },
  table:  { width: '100%', borderCollapse: 'collapse', fontSize: 12 },
  th: {
    padding: '10px 14px', textAlign: 'left',
    fontSize: 11, fontWeight: 700, color: '#94A3B8',
    textTransform: 'uppercase', letterSpacing: 0.5,
    background: '#F8FAFC', borderBottom: '1px solid #E2E8F0',
    whiteSpace: 'nowrap', position: 'sticky', top: 0,
  },
  trEven: { background: '#fff' },
  trOdd:  { background: '#F8FAFC' },
  td: {
    padding: '9px 14px', color: '#334155',
    borderBottom: '1px solid #F1F5F9', whiteSpace: 'nowrap',
    fontFamily: "'SF Mono','Fira Code',monospace", fontSize: 12,
  },
};
