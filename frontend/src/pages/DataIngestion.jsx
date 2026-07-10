
// CSV upload page with column validation, preview table, and ingestion status.
import { useRef, useState, useEffect, useCallback } from 'react';
import api from '../services/api';

const IconCloud = () => (
  <svg width="52" height="52" viewBox="0 0 24 24" fill="none" stroke="currentColor"
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

function Spinner() {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center' }}>
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
        strokeWidth="2.5" style={{ animation: 'spin 0.8s linear infinite', marginRight: 8 }}>
        <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
      </svg>
      Processing…
    </span>
  );
}

export default function DataIngestion() {
  const fileRef = useRef(null);

  const [dragging,     setDragging]     = useState(false);
  const [fileName,     setFileName]     = useState(null);
  const [fileSize,     setFileSize]     = useState(null);
  const [file,         setFile]         = useState(null);
  const [status,       setStatus]       = useState('IDLE');   // IDLE | PROCESSING | DONE | ERROR
  const [parseError,   setParseError]   = useState(null);
  const [uploadError,  setUploadError]  = useState(null);
  const [rowCount,     setRowCount]     = useState(null);

  // Preview state
  const [previewData,    setPreviewData]    = useState([]);
  const [previewTotal,   setPreviewTotal]   = useState(0);
  const [totalPages,     setTotalPages]     = useState(0);
  const [previewPage,    setPreviewPage]    = useState(1);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError,   setPreviewError]   = useState(null);
  const PAGE_SIZE = 50;

  const fmtSize = bytes => {
    if (bytes < 1024)       return `${bytes} B`;
    if (bytes < 1024*1024)  return `${(bytes/1024).toFixed(1)} KB`;
    return `${(bytes/(1024*1024)).toFixed(1)} MB`;
  };

  const pickFile = useCallback(f => {
    if (!f) return;
    const ext = f.name.split('.').pop().toLowerCase();
    if (ext !== 'csv') {
      setParseError('Unsupported file type. Only .csv files are accepted.');
      return;
    }
    if (f.size > 50 * 1024 * 1024) {
      setParseError('File exceeds the 50 MB limit.');
      return;
    }
    setParseError(null);
    setUploadError(null);
    setFileName(f.name);
    setFileSize(fmtSize(f.size));
    setFile(f);
    setStatus('IDLE');
    setPreviewData([]);
    setPreviewTotal(0);
    setTotalPages(0);
    setPreviewPage(1);
    setPreviewError(null);
    setRowCount(null);
  }, []);

  const onDragOver  = e => { e.preventDefault(); setDragging(true); };
  const onDragLeave = ()  => setDragging(false);
  const onDrop      = e  => { e.preventDefault(); setDragging(false); pickFile(e.dataTransfer.files[0]); };
  const onInput     = e  => pickFile(e.target.files[0]);

  useEffect(() => { fetchPreview(1); }, []); // eslint-disable-line

  const fetchPreview = async (page = 1) => {
    setPreviewLoading(true);
    setPreviewError(null);
    try {
      const res = await api.get('/api/ingest/preview', { params: { page, page_size: PAGE_SIZE } });
      setPreviewData(res.data.data ?? []);
      setPreviewTotal(res.data.total ?? 0);
      setTotalPages(res.data.total_pages ?? 0);
      setPreviewPage(page);
    } catch (err) {
      setPreviewError(err.response?.data?.detail || 'Could not load preview. Is the backend running?');
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleProcess = async () => {
    if (!file) return;
    setStatus('PROCESSING');
    setUploadError(null);
    setPreviewData([]);
    try {
      const form = new FormData();
      form.append('file', file);
      const res = await api.post('/api/ingest', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setRowCount(res.data.row_count);
      setStatus('DONE');
      await fetchPreview(1);
    } catch (err) {
      setUploadError(err.response?.data?.detail || 'Upload failed. Please try again.');
      setStatus('ERROR');
    }
  };

  useEffect(() => {
    if (status === 'DONE') fetchPreview(previewPage);
  }, [previewPage]); // eslint-disable-line

  const handleReset = () => {
    setFileName(null); setFileSize(null); setFile(null);
    setStatus('IDLE'); setParseError(null); setUploadError(null);
    setRowCount(null); setPreviewData([]); setPreviewTotal(0); setTotalPages(0); setPreviewPage(1); setPreviewError(null);
    if (fileRef.current) fileRef.current.value = '';
  };

  const rowStart = previewData.length > 0 ? (previewPage - 1) * PAGE_SIZE + 1 : 0;
  const rowEnd   = previewData.length > 0 ? Math.min(previewPage * PAGE_SIZE, previewTotal) : 0;

  const ST_BADGE = {
    IDLE:       { bg: '#EFF6FF', color: '#3B82F6', border: '#BFDBFE', label: 'IDLE' },
    PROCESSING: { bg: '#FFFBEB', color: '#D97706', border: '#FDE68A', label: 'PROCESSING' },
    DONE:       { bg: '#ECFDF5', color: '#059669', border: '#A7F3D0', label: 'DONE' },
    ERROR:      { bg: '#FCEBEB', color: '#DC2626', border: '#F09595', label: 'ERROR' },
  };
  const st = ST_BADGE[status];

  return (
    <div>
      {/* ── Header ── */}
      <div style={s.pageHeader}>
        <h1 style={s.pageTitle}>Data Ingestion</h1>
        <p style={s.pageSub}>Upload and process student dataset</p>
      </div>

      {/* ── Drop zone ── */}
      <div
        style={{ ...s.dropZone, ...(dragging ? s.dropActive : {}) }}
        onDragOver={onDragOver} onDragLeave={onDragLeave} onDrop={onDrop}
        onClick={() => fileRef.current?.click()}
      >
        <input ref={fileRef} type="file" accept=".csv" style={{ display: 'none' }} onChange={onInput} />
        <div style={{ color: dragging ? '#fff' : 'rgba(255,255,255,0.85)', marginBottom: 12 }}>
          <IconCloud />
        </div>
        <p style={s.dropTitle}>
          {fileName ? fileName : 'Drag and drop your CSV file here'}
        </p>
        {fileSize
          ? <p style={s.dropSub}>{fileSize} · ready to process</p>
          : <p style={s.dropSub}>Supported format: .csv — Maximum size: 50MB</p>
        }
        {!fileName && (
          <button
            style={s.browseBtn}
            onClick={e => { e.stopPropagation(); fileRef.current?.click(); }}
          >
            Browse File
          </button>
        )}
        {parseError && <p style={s.dropError}>{parseError}</p>}
      </div>

      {/* ── Status cards ── */}
      <div style={s.cardRow}>
        <div style={s.statCard}>
          <p style={s.cardLabel}>Row Count</p>
          <p style={s.cardValue}>{rowCount != null ? rowCount.toLocaleString() : '— — —'}</p>
        </div>
        <div style={s.statCard}>
          <p style={s.cardLabel}>Anonymized</p>
          <span style={{ ...s.pill, background: '#E1F5EE', color: '#0F6E56' }}>True</span>
        </div>
        <div style={s.statCard}>
          <p style={s.cardLabel}>Status</p>
          <span style={{ ...s.pill, background: st.bg, color: st.color, borderColor: st.border }}>
            {st.label}
          </span>
        </div>
      </div>

      {/* ── Error ── */}
      {uploadError && (
        <div style={s.errorBanner}><span>⚠</span> {uploadError}</div>
      )}

      {/* ── Success ── */}
      {status === 'DONE' && rowCount != null && (
        <div style={s.successBanner}>
          <span style={s.successIcon}><IconCheck /></span>
          <strong>{rowCount.toLocaleString()} rows successfully loaded</strong>
        </div>
      )}

      {/* ── Actions ── */}
      <div style={s.actions}>
        <button
          style={{ ...s.btnPrimary, opacity: (!file || status === 'PROCESSING') ? 0.5 : 1 }}
          disabled={!file || status === 'PROCESSING'}
          onClick={handleProcess}
        >
          {status === 'PROCESSING' ? <Spinner /> : 'Process Dataset'}
        </button>
        <button style={s.btnSecondary} onClick={handleReset}>Reset</button>
      </div>

      {/* ── Preview table ── */}
      {previewData.length > 0 && (
        <div style={{ marginTop: 8 }}>
          <div style={s.previewHeader}>
            <div>
              <h3 style={s.previewTitle}>Dataset Preview</h3>
              {!previewLoading && previewData.length > 0 && (
                <p style={s.previewSub}>
                  Showing rows {rowStart.toLocaleString()}–{rowEnd.toLocaleString()} of{' '}
                  {previewTotal.toLocaleString()} total records
                </p>
              )}
            </div>
          </div>

          {previewError && (
            <div style={s.previewErrorBanner}>⚠ {previewError}</div>
          )}

          <div style={s.tableWrapper}>
            {previewLoading ? (
              <div style={{ textAlign: 'center', padding: '40px 20px', color: '#5A7A8A' }}>
                Loading preview…
              </div>
            ) : previewData.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '40px 20px', color: '#94A3B8', fontSize: 13 }}>
                No preview data available.
              </div>
            ) : (
              <table style={s.table}>
                <thead>
                  <tr>
                    {Object.keys(previewData[0] || {}).map(col => (
                      <th key={col} style={s.th}>{col}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {previewData.map((row, i) => (
                    <tr key={i} style={{ background: i % 2 === 0 ? '#fff' : '#F8FAFC' }}>
                      {Object.keys(previewData[0] || {}).map(col => (
                        <td key={col} style={s.td}>
                          {row[col] === '' || row[col] == null ? '—' : String(row[col])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* Pagination */}
          {!previewLoading && totalPages > 1 && (
            <div style={s.pagination}>
              <PagBtn label="« First" disabled={previewPage === 1}          onClick={() => fetchPreview(1)} />
              <PagBtn label="‹ Prev"  disabled={previewPage === 1}          onClick={() => fetchPreview(previewPage - 1)} />
              <span style={s.pageInfo}>Page {previewPage} of {totalPages}</span>
              <PagBtn label="Next ›"  disabled={previewPage === totalPages}  onClick={() => fetchPreview(previewPage + 1)} />
              <PagBtn label="Last »"  disabled={previewPage === totalPages}  onClick={() => fetchPreview(totalPages)} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function PagBtn({ label, disabled, onClick }) {
  return (
    <button
      style={{ ...s.pagBtn, opacity: disabled ? 0.4 : 1, cursor: disabled ? 'default' : 'pointer' }}
      disabled={disabled}
      onClick={onClick}
    >
      {label}
    </button>
  );
}

const s = {
  pageHeader: { marginBottom: 24 },
  pageTitle:  { margin: '0 0 4px', fontSize: 24, fontWeight: 500, color: '#1A2E40' },
  pageSub:    { margin: 0, fontSize: 13, color: '#5A7A8A' },

  dropZone: {
    background: '#2E6E8E', border: '2px dashed rgba(255,255,255,0.35)', borderRadius: 14,
    padding: '52px 32px', display: 'flex', flexDirection: 'column', alignItems: 'center',
    gap: 8, cursor: 'pointer', transition: 'all 0.2s', marginBottom: 28, userSelect: 'none',
  },
  dropActive:  { background: '#235a74', borderColor: 'rgba(255,255,255,0.7)' },
  dropTitle:   { margin: 0, fontSize: 17, fontWeight: 600, color: '#fff' },
  dropSub:     { margin: 0, fontSize: 13, color: 'rgba(255,255,255,0.7)' },
  browseBtn:   {
    marginTop: 10, padding: '10px 32px', background: '#fff', color: '#2E6E8E',
    border: 'none', borderRadius: 8, fontSize: 14, fontWeight: 600, cursor: 'pointer',
  },
  dropError: {
    margin: '8px 0 0', fontSize: 13, color: '#FCA5A5',
    background: 'rgba(0,0,0,0.2)', padding: '6px 14px', borderRadius: 6,
  },

  cardRow:   { display: 'flex', gap: 16, marginBottom: 20 },
  statCard:  {
    flex: 1, background: '#fff', border: '0.5px solid #DDE4EA',
    borderRadius: 10, padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 10,
  },
  cardLabel: { margin: 0, fontSize: 11, fontWeight: 700, color: '#94A3B8', textTransform: 'uppercase', letterSpacing: 0.5 },
  cardValue: { margin: 0, fontSize: 28, fontWeight: 700, color: '#1A2E40', letterSpacing: -0.5 },
  pill: {
    display: 'inline-block', padding: '5px 14px', borderRadius: 20,
    border: '1px solid', fontSize: 13, fontWeight: 600, alignSelf: 'flex-start',
  },

  errorBanner: {
    display: 'flex', alignItems: 'center', gap: 8,
    background: 'rgba(220,38,38,0.08)', border: '1px solid rgba(220,38,38,0.25)',
    color: '#DC2626', borderRadius: 8, padding: '10px 16px', fontSize: 13, marginBottom: 16,
  },
  successBanner: {
    display: 'flex', alignItems: 'center', gap: 12,
    background: '#ECFDF5', border: '1px solid #A7F3D0', color: '#065F46',
    borderRadius: 10, padding: '14px 20px', fontSize: 14, fontWeight: 500, marginBottom: 20,
  },
  successIcon: {
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    width: 24, height: 24, borderRadius: '50%', background: '#059669', color: '#fff', flexShrink: 0,
  },

  actions:      { display: 'flex', gap: 12, marginBottom: 28 },
  btnPrimary:   {
    padding: '12px 32px', background: '#2E6E8E', color: '#fff',
    border: 'none', borderRadius: 8, fontSize: 14, fontWeight: 600,
    cursor: 'pointer', transition: 'opacity 0.15s', minWidth: 160,
  },
  btnSecondary: {
    padding: '12px 28px', background: '#fff', color: '#2E6E8E',
    border: '1.5px solid #2E6E8E', borderRadius: 8, fontSize: 14, fontWeight: 600, cursor: 'pointer',
  },

  previewHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 10 },
  previewTitle:  { margin: '0 0 2px', fontSize: 15, fontWeight: 600, color: '#1A2E40' },
  previewSub:    { margin: 0, fontSize: 12, color: '#5A7A8A' },
  previewErrorBanner: {
    display: 'flex', alignItems: 'center', gap: 8,
    background: 'rgba(220,38,38,0.07)', border: '1px solid rgba(220,38,38,0.2)',
    color: '#DC2626', borderRadius: 8, padding: '10px 14px', fontSize: 13, marginBottom: 10,
  },

  tableWrapper: {
    background: '#fff', border: '0.5px solid #DDE4EA', borderRadius: 10,
    overflow: 'auto', maxHeight: 420,
  },
  table: { minWidth: '100%', width: 'max-content', borderCollapse: 'collapse', fontSize: 12 },
  th: {
    padding: '10px 14px', textAlign: 'left', fontSize: 11, fontWeight: 700,
    color: '#94A3B8', textTransform: 'uppercase', letterSpacing: 0.5,
    background: '#F8FAFC', borderBottom: '1px solid #E2E8F0',
    whiteSpace: 'nowrap', position: 'sticky', top: 0,
  },
  td: {
    padding: '9px 14px', color: '#334155', borderBottom: '1px solid #F1F5F9',
    whiteSpace: 'nowrap', fontFamily: "'SF Mono','Fira Code',monospace",
  },

  pagination: { display: 'flex', alignItems: 'center', gap: 6, marginTop: 14, justifyContent: 'center' },
  pagBtn: {
    padding: '7px 14px', borderRadius: 7, border: '0.5px solid #C5D2DC',
    background: '#fff', color: '#1A2E40', fontSize: 12, fontWeight: 500,
    transition: 'opacity 0.15s',
  },
  pageInfo: { fontSize: 13, color: '#5A7A8A', padding: '0 8px', whiteSpace: 'nowrap' },
};
