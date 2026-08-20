// Data Ingestion — two independent upload slots (capstone assessment data,
// attendance data), each analyzed (parsed + column-classified) as soon as a
// file is picked, with nothing committed to the live dataset until
// "Confirm and Ingest" is pressed. Column classification (Kept/Skipped/New)
// is shared across both slots in one panel, tagged by source dataset.
import { useRef, useState, useCallback, useEffect } from 'react';
import api from '../services/api';
import { markIngestJobsSeen } from '../utils/ingestNotifications';

const IconCloud = () => (
  <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="16 16 12 12 8 16"/>
    <line x1="12" y1="12" x2="12" y2="21"/>
    <path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3"/>
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

// ── Persistent per-kind status — "has this ever been ingested?" survives a
// refresh because it's derived from the server (GET /api/ingest/dataset-summary
// + the jobs list), not from React state that resets on page load. ──────────

function timeAgo(iso, nowMs) {
  if (!iso) return '';
  const diffSec = Math.max(0, Math.round((nowMs - new Date(iso).getTime()) / 1000));
  if (diffSec < 5) return 'just now';
  if (diffSec < 60) return `${diffSec}s ago`;
  const diffMin = Math.round(diffSec / 60);
  if (diffMin < 60) return `${diffMin} min ago`;
  return `${Math.round(diffMin / 60)}h ago`;
}

function DatasetStatusBadge({ summary, runningJob, nowMs }) {
  if (runningJob) {
    return (
      <span style={{ ...s.datasetStatus, ...s.datasetStatusRunning }}>
        <span style={{ ...s.jobDot, ...s.jobDotRunning }} /> Ingestion in progress…
      </span>
    );
  }
  if (!summary || !summary.has_data) {
    return <span style={{ ...s.datasetStatus, ...s.datasetStatusNone }}>Not yet ingested</span>;
  }
  return (
    <span style={{ ...s.datasetStatus, ...s.datasetStatusDone }}>
      <span style={{ ...s.jobDot, ...s.jobDotSuccess }} /> Ingested — {summary.row_count.toLocaleString()} rows
      {summary.last_ingested_at && <> · updated {timeAgo(summary.last_ingested_at, nowMs)}</>}
    </span>
  );
}

// ── One upload card — capstone or attendance, fully independent state ────────

function UploadCard({ kind, title, hint, maxSizeMB, analyzeUrl, onJobStarted, onCleared, analysis, restored, activeJob, datasetSummary, runningJob, nowMs }) {
  const fileRef = useRef(null);
  const [dragging, setDragging] = useState(false);
  const [file,     setFile]     = useState(null);
  const [error,    setError]    = useState(null); // immediate, synchronous rejection only (bad type/size, or the upload request itself failing)

  // activeJob comes from the parent — it's the SAME state whether this
  // analyze was just started in this browser tab or discovered still
  // running (or freshly failed) after a page refresh via
  // GET /api/ingest/{kind}/analyze-status, so both cases render identically.
  const isAnalyzing = activeJob?.status === 'running';
  const jobError     = activeJob?.status === 'failed' ? activeJob.error_detail : null;

  const fmtSize = bytes => {
    if (bytes < 1024)      return `${bytes} B`;
    if (bytes < 1024*1024) return `${(bytes/1024).toFixed(1)} KB`;
    return `${(bytes/(1024*1024)).toFixed(1)} MB`;
  };

  const analyze = useCallback(async (f) => {
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
      //
      // The upload itself still has to complete as one request/response —
      // that part of the browser sending bytes genuinely can't be made
      // resumable — but analyze now only returns a job id; the parent
      // polls GET /api/ingest/analyze-jobs/{job_id} to actually finish, so
      // once the upload has landed, a refresh no longer loses the analysis.
      const res = await api.post(analyzeUrl, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 600000,
      });
      onJobStarted(kind, res.data.job_id, f);
    } catch (err) {
      setError(err.response?.data?.detail || 'Analysis failed. Please try again.');
      setFile(null);
    }
  }, [analyzeUrl, kind, onJobStarted]);

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
    setFile(null); setError(null);
    if (fileRef.current) fileRef.current.value = '';
    onCleared(kind);
  };

  const displayFilename = file?.name || activeJob?.filename || restored?.filename || null;

  return (
    <div style={s.uploadCard}>
      <div style={s.uploadCardHeader}>
        <h3 style={s.uploadCardTitle}>{title}</h3>
        <DatasetStatusBadge summary={datasetSummary} runningJob={runningJob} nowMs={nowMs} />
      </div>
      <div
        style={{ ...s.dropZone, ...(dragging ? s.dropActive : {}) }}
        onDragOver={onDragOver} onDragLeave={onDragLeave} onDrop={onDrop}
        onClick={() => !file && !isAnalyzing && fileRef.current?.click()}
      >
        <input ref={fileRef} type="file" accept=".csv" style={{ display: 'none' }} onChange={onInput} />
        <div style={{ color: 'rgba(255,255,255,0.85)', marginBottom: 8 }}><IconCloud /></div>
        <p style={s.dropTitle}>{displayFilename || 'Drag and drop, or browse'}</p>
        <p style={s.dropSub}>
          {file ? fmtSize(file.size) : isAnalyzing ? 'Resuming analysis from before you left this page…' : hint}
        </p>
        {!file && !isAnalyzing && (
          <button style={s.browseBtn} onClick={e => { e.stopPropagation(); fileRef.current?.click(); }}>
            Browse File
          </button>
        )}
      </div>

      {isAnalyzing && <p style={s.statusLine}><Spinner label="Analyzing…" /></p>}
      {(error || jobError) && <p style={s.errorLine}>⚠ {error || jobError}</p>}
      {!isAnalyzing && analysis && !restored && (
        <div style={s.analyzedRow}>
          <span style={s.analyzedRowLabel}>Detected</span>
          <strong>{analysis.row_count.toLocaleString()} rows</strong>
          {analysis.subjects != null && <span style={s.analyzedSub}>· {analysis.subjects} subjects</span>}
        </div>
      )}
      {!file && !isAnalyzing && restored && (
        <div style={s.restoredBanner}>
          Resumed <strong>{restored.filename}</strong> — {restored.row_count.toLocaleString()} rows,
          analyzed earlier and still waiting to be confirmed. Expires in{' '}
          {Math.max(1, Math.round(restored.expires_in_seconds / 60))} min if not confirmed.
        </div>
      )}

      {(file || restored || isAnalyzing) && (
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

// ── Ingest jobs panel ──────────────────────────────────────────────────────────
// Confirm now returns immediately and the real work (parse/build features/
// retrain-check/commit) finishes later in the background (see IngestJob in
// backend/app/db/models.py). This panel is the real status readout — every
// number here comes from the server, not a client-side estimate: a "running"
// row's elapsed time is computed from the job's actual started_at, and a
// finished row's detail is the job's actual result payload.

const KIND_LABEL = { capstone: 'Capstone Data', attendance: 'Attendance Data' };

function formatElapsed(startedIso, nowMs) {
  const sec = Math.max(0, Math.round((nowMs - new Date(startedIso).getTime()) / 1000));
  const mm = String(Math.floor(sec / 60)).padStart(2, '0');
  const ss = String(sec % 60).padStart(2, '0');
  return `${mm}:${ss}`;
}

const PHASE_LABEL = { analyze: 'Analyze', confirm: 'Ingest' };

function IngestJobRow({ job, nowMs }) {
  const isRunning  = job.status === 'running';
  const isFailed   = job.status === 'failed';
  const isAnalyze  = job.phase === 'analyze';
  const dotStyle   = isRunning ? s.jobDotRunning : isFailed ? s.jobDotFailed : s.jobDotSuccess;
  const pillStyle  = isRunning ? s.jobStatusRunning : isFailed ? s.jobStatusFailed : s.jobStatusSuccess;

  return (
    <div style={s.jobRow}>
      <div style={s.jobRowTop}>
        <span style={{ ...s.jobDot, ...dotStyle }} />
        <span style={s.jobKind}>{KIND_LABEL[job.kind] || job.kind}</span>
        <span style={s.jobPhaseTag}>{PHASE_LABEL[job.phase] || job.phase}</span>
        <span style={s.jobFilename}>{job.filename}</span>
        <span style={{ ...s.jobStatusPill, ...pillStyle }}>
          {isRunning
            ? (isAnalyze ? 'Analyzing…' : 'Processing…')
            : isFailed ? 'Failed'
            : (isAnalyze ? 'Analyzed' : 'Completed')}
        </span>
      </div>
      <div style={s.jobRowMeta}>
        {isRunning
          ? isAnalyze
            ? <>Started by {job.started_by} — analyzing {formatElapsed(job.started_at, nowMs)}. Safe to navigate away — it'll be here waiting to confirm once done.</>
            : <>Started by {job.started_by} — running {formatElapsed(job.started_at, nowMs)}. You'll be notified here (and in the sidebar) once it finishes — feel free to navigate away.</>
          : <>Started by {job.started_by} · {timeAgo(job.finished_at || job.started_at, nowMs)}</>}
      </div>
      {isAnalyze && job.status === 'success' && job.result && (
        <div style={s.jobResult}>
          <span><strong>{job.result.row_count?.toLocaleString()}</strong> rows detected</span>
          <span>Waiting to be confirmed</span>
        </div>
      )}
      {!isAnalyze && job.status === 'success' && job.result && job.kind === 'capstone' && (
        <div style={s.jobResult}>
          <span><strong>{job.result.row_count?.toLocaleString()}</strong> rows</span>
          <span>Subjects reclassified: <strong>{job.result.subjects_reclassified}</strong></span>
          <span>
            {job.result.retrain?.triggered
              ? `🔄 Retrain candidate${job.result.retrain.candidate_version ? ` ${job.result.retrain.candidate_version}` : ''} registered`
              : `ℹ ${job.result.retrain?.reason}`}
          </span>
        </div>
      )}
      {!isAnalyze && job.status === 'success' && job.result && job.kind === 'attendance' && (
        <div style={s.jobResult}>
          <span><strong>{job.result.row_count?.toLocaleString()}</strong> enrolments</span>
          <span>Match rate: <strong>{job.result.match_rate}%</strong></span>
        </div>
      )}
      {!isAnalyze && job.status === 'success' && job.result?.merge_stats && (
        <div style={s.jobMergeStats}>
          Incremental merge — <strong>{job.result.merge_stats.new_rows.toLocaleString()}</strong> new,{' '}
          <strong>{job.result.merge_stats.updated_rows.toLocaleString()}</strong> updated,{' '}
          <strong>{job.result.merge_stats.redundant_rows.toLocaleString()}</strong> redundant rows found and skipped
        </div>
      )}
      {isFailed && <div style={s.jobError}>⚠ {job.error_detail || (isAnalyze ? 'Analysis failed.' : 'Ingestion failed.')}</div>}
    </div>
  );
}

function IngestJobsPanel({ jobs, nowMs }) {
  if (!jobs.length) return null;
  return (
    <div style={s.card}>
      <style>{`@keyframes ingestPulse { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.4; transform: scale(0.7); } }`}</style>
      <h3 style={s.cardTitle}>Ingestion Activity</h3>
      <div style={s.jobList}>
        {jobs.map(job => <IngestJobRow key={`${job.phase}-${job.id}`} job={job} nowMs={nowMs} />)}
      </div>
    </div>
  );
}

// ── Incremental vs. Override wizard ────────────────────────────────────────────
// Shown at confirm time only for a kind that already has live data — with
// nothing to merge into or replace yet, there's no real choice to make, so a
// first-time ingestion skips this entirely and goes straight through.

function IngestModeWizard({ pending, modes, onModeChange, onCancel, onConfirm }) {
  return (
    <div style={s.modalOverlay} role="dialog" aria-modal="true">
      <div style={s.modalCard}>
        <h3 style={s.modalTitle}>Choose how to ingest</h3>
        <p style={s.modalSub}>
          Live data already exists for the dataset{pending.length > 1 ? 's' : ''} below. Pick how this upload should be applied to each.
        </p>

        {pending.map(({ kind, filename, rowCount, existingRowCount }) => (
          <div key={kind} style={s.modalKindBlock}>
            <div style={s.modalKindHeader}>
              {KIND_LABEL[kind]} <span style={s.modalKindFile}>— {filename}</span>
            </div>
            <p style={s.modalKindMeta}>
              {rowCount.toLocaleString()} rows in this upload · {existingRowCount.toLocaleString()} rows currently live
            </p>
            <div style={s.modalOptions}>
              <label style={{ ...s.modalOption, ...(modes[kind] === 'incremental' ? s.modalOptionSelected : {}) }}>
                <input
                  type="radio" name={`mode-${kind}`} checked={modes[kind] === 'incremental'}
                  onChange={() => onModeChange(kind, 'incremental')}
                />
                <div>
                  <strong>Incremental Ingestion</strong>
                  <p style={s.modalOptionText}>
                    Merge new rows into the existing data. An exact-duplicate row is skipped; a row with
                    the same key (e.g. student + subject + period) but a different value is treated as a
                    correction and replaces the old one; a genuinely new row is added.
                  </p>
                </div>
              </label>
              <label style={{ ...s.modalOption, ...(modes[kind] === 'override' ? s.modalOptionSelected : {}) }}>
                <input
                  type="radio" name={`mode-${kind}`} checked={modes[kind] === 'override'}
                  onChange={() => onModeChange(kind, 'override')}
                />
                <div>
                  <strong>Override Previous Ingestion</strong>
                  <p style={s.modalOptionText}>Replace the existing data entirely with this upload.</p>
                </div>
              </label>
            </div>
          </div>
        ))}

        <div style={s.modalActions}>
          <button style={s.modalCancelBtn} onClick={onCancel}>Cancel</button>
          <button style={s.modalConfirmBtn} onClick={onConfirm}>Confirm and Ingest</button>
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

  // Info about a pending upload resumed from the server on page load (no
  // File object — the browser never held one this session). Kept separate
  // from *Analysis so the "Resumed …" banner can tell that case apart from
  // a freshly-analyzed local file.
  const [restoredCapstone,   setRestoredCapstone]   = useState(null);
  const [restoredAttendance, setRestoredAttendance] = useState(null);

  // Real ingestion job history/status (see IngestJob in backend/app/db/models.py)
  // — confirm now starts a background job instead of blocking, so this list,
  // not a synchronous response, is the actual source of truth for what
  // happened. nowMs ticks every second purely to keep running jobs' elapsed
  // timers live; jobs itself refreshes on its own slower poll.
  const [jobs, setJobs] = useState([]);
  const [nowMs, setNowMs] = useState(Date.now());

  const fetchJobs = useCallback(async () => {
    try {
      const res = await api.get('/api/ingest/jobs', { params: { limit: 20 } });
      setJobs(res.data.jobs);
      // Visiting this page IS acknowledging its ingestion activity — clears
      // the sidebar badge for anything already visible here.
      markIngestJobsSeen(res.data.jobs);
    } catch { /* history is best-effort; leave the prior list showing */ }
  }, []);

  // Analyze jobs (see AnalyzeJob in backend/app/db/models.py) merged into
  // the same Ingestion Activity timeline as confirm jobs, tagged by phase,
  // so the analyze step itself shows up in history too — not just confirm.
  const [analyzeJobsHistory, setAnalyzeJobsHistory] = useState([]);
  const fetchAnalyzeJobsHistory = useCallback(async () => {
    try {
      const res = await api.get('/api/ingest/analyze-jobs', { params: { limit: 20 } });
      setAnalyzeJobsHistory(res.data.jobs);
    } catch { /* history is best-effort; leave the prior list showing */ }
  }, []);

  useEffect(() => { fetchJobs(); fetchAnalyzeJobsHistory(); }, [fetchJobs, fetchAnalyzeJobsHistory]);
  useEffect(() => {
    const timer = setInterval(() => { fetchJobs(); fetchAnalyzeJobsHistory(); }, 5000);
    return () => clearInterval(timer);
  }, [fetchJobs, fetchAnalyzeJobsHistory]);
  useEffect(() => {
    const timer = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  const activity = [
    ...jobs.map(j => ({ ...j, phase: 'confirm' })),
    ...analyzeJobsHistory.map(j => ({ ...j, phase: 'analyze' })),
  ].sort((a, b) => new Date(b.started_at) - new Date(a.started_at));

  // Persistent per-kind status ("Ingested — 327,501 rows, updated 2 min ago"
  // vs "Not yet ingested") — server-derived (GET /api/ingest/dataset-summary),
  // so it survives a refresh instead of the page looking blank until
  // something new happens in this browser tab. Also what decides whether the
  // incremental-vs-override wizard even needs to appear at confirm time.
  const [datasetSummary, setDatasetSummary] = useState(null);
  const fetchDatasetSummary = useCallback(async () => {
    try {
      const res = await api.get('/api/ingest/dataset-summary');
      setDatasetSummary(res.data);
    } catch { /* status strip is best-effort; leave the prior summary showing */ }
  }, []);
  useEffect(() => { fetchDatasetSummary(); }, [fetchDatasetSummary]);
  useEffect(() => {
    const timer = setInterval(fetchDatasetSummary, 5000);
    return () => clearInterval(timer);
  }, [fetchDatasetSummary]);

  // Incremental-vs-override wizard — only shown for a kind that already has
  // live data to merge into or replace; wizardPending is null when the
  // modal isn't open.
  const [wizardPending, setWizardPending] = useState(null); // [{kind, filename, rowCount, existingRowCount}] | null
  const [wizardModes, setWizardModes] = useState({});

  // Analyze now runs as a background job too (see AnalyzeJob in
  // backend/app/db/models.py) — the same fix already applied to confirm,
  // extended to the earlier step, so a page refresh (or navigating to any
  // other menu item) while a large file is still being parsed doesn't lose
  // it. analyzeJobs[kind] is null once nothing is running/recently-failed;
  // {status:'running', job_id, filename} while a job is in flight (whether
  // started in this tab or discovered on mount); {status:'failed', ...}
  // once one finishes badly.
  const [analyzeJobs, setAnalyzeJobs] = useState({ capstone: null, attendance: null });
  const analyzePollTimers = useRef({ capstone: null, attendance: null });
  const mountedRef = useRef(true);
  useEffect(() => () => {
    mountedRef.current = false;
    Object.values(analyzePollTimers.current).forEach(t => t && clearTimeout(t));
  }, []);

  const kindSetters = (kind) => ({
    setAnalysis: kind === 'capstone' ? setCapstoneAnalysis   : setAttendanceAnalysis,
    setFile:     kind === 'capstone' ? setCapstoneFile       : setAttendanceFile,
    setRestored: kind === 'capstone' ? setRestoredCapstone   : setRestoredAttendance,
  });

  // Poll one analyze job to completion, updating analyzeJobs[kind] as it
  // goes, and resolving the result into *Analysis/*File/*Restored exactly
  // like the old synchronous analyze() response used to. `file` is the
  // local File object if this was picked in this tab, or null if it's
  // being resumed from a page refresh (no bytes held client-side).
  const pollAnalyzeJob = useCallback(async (kind, jobId, file) => {
    const { setAnalysis, setFile, setRestored } = kindSetters(kind);
    // eslint-disable-next-line no-constant-condition
    while (true) {
      let job;
      try {
        job = (await api.get(`/api/ingest/analyze-jobs/${jobId}`)).data;
      } catch {
        if (mountedRef.current) {
          setAnalyzeJobs(s => ({ ...s, [kind]: { status: 'failed', filename: file?.name, error_detail: 'Lost track of this analysis. Please try again.' } }));
        }
        return;
      }
      if (job.status === 'running') {
        await new Promise(resolve => {
          analyzePollTimers.current[kind] = setTimeout(resolve, 2000);
        });
        if (!mountedRef.current) return;
        continue;
      }
      if (!mountedRef.current) return;
      if (job.status === 'success') {
        setAnalysis(job.result);
        if (file) { setFile(file); setRestored(null); }
        else      { setFile(null); setRestored(job.result); }
        setAnalyzeJobs(s => ({ ...s, [kind]: null }));
      } else {
        setAnalyzeJobs(s => ({ ...s, [kind]: { status: 'failed', filename: job.filename, error_detail: job.error_detail || 'Analysis failed.' } }));
      }
      return;
    }
  }, []);

  const handleJobStarted = (kind, jobId, file) => {
    const { setAnalysis, setFile, setRestored } = kindSetters(kind);
    setAnalysis(null); setFile(null); setRestored(null);
    setAnalyzeJobs(s => ({ ...s, [kind]: { status: 'running', job_id: jobId, filename: file?.name } }));
    pollAnalyzeJob(kind, jobId, file);
  };

  // On mount: has an analyze from before a refresh (or from switching to
  // another menu item and back) left something running or freshly failed?
  // If not, fall back to checking for an already-analyzed, still-pending
  // upload — same PendingIngest / PENDING_INGEST_TTL_MINUTES restore this
  // page has always done, just no longer the only thing it checks.
  useEffect(() => {
    const checkResume = async (kind) => {
      const { setAnalysis, setRestored } = kindSetters(kind);
      try {
        const res = await api.get(`/api/ingest/${kind}/analyze-status`);
        if (!mountedRef.current) return;
        if (res.data.active) {
          setAnalyzeJobs(s => ({ ...s, [kind]: { status: res.data.status, job_id: res.data.job_id, filename: res.data.filename, error_detail: res.data.error_detail } }));
          if (res.data.status === 'running') pollAnalyzeJob(kind, res.data.job_id, null);
          return;
        }
      } catch { /* analyze-status check failed — fall through to the pending-upload check below */ }

      try {
        const res = await api.get(`/api/ingest/${kind}/status`);
        if (!mountedRef.current || !res.data.pending) return;
        setAnalysis(res.data);
        setRestored(res.data);
      } catch { /* nothing to resume, or the check itself failed — safe to ignore */ }
    };
    checkResume('capstone');
    checkResume('attendance');
  }, [pollAnalyzeJob]);

  const handleCleared = (kind) => {
    if (analyzePollTimers.current[kind]) { clearTimeout(analyzePollTimers.current[kind]); analyzePollTimers.current[kind] = null; }
    setAnalyzeJobs(s => ({ ...s, [kind]: null }));
    const { setAnalysis, setFile, setRestored } = kindSetters(kind);
    setAnalysis(null); setFile(null); setRestored(null);
  };

  const reanalyze = async (kind) => {
    const file = kind === 'capstone' ? capstoneFile : attendanceFile;
    const { setAnalysis } = kindSetters(kind);
    try {
      if (file) {
        const url = kind === 'capstone' ? '/api/ingest/capstone/analyze' : '/api/ingest/attendance/analyze';
        const form = new FormData();
        form.append('file', file);
        const jobRes = await api.post(url, form, { headers: { 'Content-Type': 'multipart/form-data' } });
        // eslint-disable-next-line no-constant-condition
        while (true) {
          const job = (await api.get(`/api/ingest/analyze-jobs/${jobRes.data.job_id}`)).data;
          if (job.status === 'running') { await new Promise(r => setTimeout(r, 1500)); continue; }
          if (job.status === 'success') setAnalysis(job.result);
          break;
        }
      } else {
        // No local File held for this kind — this upload was resumed from a
        // page refresh. Reclassify from the bytes the server already has
        // rather than asking the user to re-pick the file just to reflect
        // one column decision.
        const res = await api.get(`/api/ingest/${kind}/status`);
        if (!res.data.pending) return;
        setAnalysis(res.data);
      }
    } catch { /* leave prior analysis in place on failure */ }
  };

  const handleDecide = async (kind, column, decision) => {
    try {
      await api.post('/api/ingest/columns/decide', { kind, column, decision });
      await reanalyze(kind);
    } catch { /* surfaced implicitly — column stays in New if this fails */ }
  };

  // The actual confirm calls, run with each kind's chosen mode (defaults to
  // "override" for a kind the wizard never asked about — i.e. one with no
  // existing data to merge into or replace anyway).
  const runConfirm = async (modes) => {
    setCommitting(true);
    setCommitError(null);
    try {
      if (capstoneAnalysis) {
        await api.post('/api/ingest/capstone/confirm', {
          token: capstoneAnalysis.token, mode: modes.capstone || 'override',
        });
        // The server deletes this pending row the instant confirm is
        // accepted (one-shot per kind, not just once the background job
        // finishes) — clear it here too, or a stray extra click on
        // "Confirm and Ingest" would resubmit the same now-dead token and
        // 404 with "No matching pending upload".
        setCapstoneAnalysis(null);
        setCapstoneFile(null);
        setRestoredCapstone(null);
      }
      if (attendanceAnalysis) {
        await api.post('/api/ingest/attendance/confirm', {
          token: attendanceAnalysis.token, mode: modes.attendance || 'override',
        });
        setAttendanceAnalysis(null);
        setAttendanceFile(null);
        setRestoredAttendance(null);
      }
      // Confirm only accepts the job — pull the list (and the now-stale
      // dataset summary) immediately so the new "running" row and updated
      // status show up right away instead of waiting for the next poll tick.
      await Promise.all([fetchJobs(), fetchDatasetSummary()]);
    } catch (err) {
      setCommitError(err.response?.data?.detail || 'Could not start ingestion. Please try again.');
    } finally {
      setCommitting(false);
    }
  };

  const handleConfirm = () => {
    // Only offer a real choice for a kind that already has live data — a
    // first-time ingestion has nothing to merge into or replace, so it just
    // goes straight through as a plain load (mode is moot either way).
    const candidates = [
      capstoneAnalysis && { kind: 'capstone', analysis: capstoneAnalysis },
      attendanceAnalysis && { kind: 'attendance', analysis: attendanceAnalysis },
    ].filter(Boolean);

    const needsWizard = candidates.filter(({ kind }) => datasetSummary?.[kind]?.has_data);

    if (needsWizard.length === 0) {
      runConfirm({});
      return;
    }

    setWizardPending(needsWizard.map(({ kind, analysis }) => ({
      kind,
      filename: analysis.filename,
      rowCount: analysis.row_count,
      existingRowCount: datasetSummary[kind].row_count,
    })));
    setWizardModes(Object.fromEntries(needsWizard.map(({ kind }) => [kind, 'incremental'])));
  };

  const handleWizardConfirm = () => {
    const modes = wizardModes;
    setWizardPending(null);
    runConfirm(modes);
  };

  const canConfirm = (capstoneAnalysis || attendanceAnalysis) && !committing;

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
          onJobStarted={handleJobStarted}
          onCleared={handleCleared}
          analysis={capstoneAnalysis}
          restored={restoredCapstone}
          activeJob={analyzeJobs.capstone}
          datasetSummary={datasetSummary?.capstone}
          runningJob={jobs.find(j => j.kind === 'capstone' && j.status === 'running')}
          nowMs={nowMs}
        />
        <UploadCard
          kind="attendance"
          title="Attendance Data"
          hint="Supported: .csv — Max 200MB"
          maxSizeMB={200}
          analyzeUrl="/api/ingest/attendance/analyze"
          onJobStarted={handleJobStarted}
          onCleared={handleCleared}
          analysis={attendanceAnalysis}
          restored={restoredAttendance}
          activeJob={analyzeJobs.attendance}
          datasetSummary={datasetSummary?.attendance}
          runningJob={jobs.find(j => j.kind === 'attendance' && j.status === 'running')}
          nowMs={nowMs}
        />
      </div>

      {/* ── Column check panel ── */}
      <ColumnCheckPanel
        capstoneCols={capstoneAnalysis?.columns}
        attendanceCols={attendanceAnalysis?.columns}
        onDecide={handleDecide}
      />

      {commitError && <div style={s.errorBanner}>⚠ {commitError}</div>}

      {/* ── Confirm and ingest ── */}
      <div style={s.actions}>
        <button
          style={{ ...s.btnPrimary, opacity: canConfirm ? 1 : 0.5 }}
          disabled={!canConfirm}
          onClick={handleConfirm}
        >
          {committing ? <Spinner label="Starting…" /> : 'Confirm and Ingest'}
        </button>
      </div>

      {/* ── Ingestion activity — real background job status, not an estimate.
          Covers both phases: analyze (parse/classify) and confirm (commit). ── */}
      <IngestJobsPanel jobs={activity} nowMs={nowMs} />

      {wizardPending && (
        <IngestModeWizard
          pending={wizardPending}
          modes={wizardModes}
          onModeChange={(kind, mode) => setWizardModes(m => ({ ...m, [kind]: mode }))}
          onCancel={() => setWizardPending(null)}
          onConfirm={handleWizardConfirm}
        />
      )}
    </div>
  );
}

const s = {
  pageHeader: { marginBottom: 24 },
  pageTitle:  { margin: '0 0 4px', fontSize: 24, fontWeight: 500, color: '#1A2E40' },
  pageSub:    { margin: 0, fontSize: 13, color: '#5A7A8A' },

  uploadRow: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 20 },
  uploadCard: { background: '#fff', border: '0.5px solid #DDE4EA', borderRadius: 12, padding: '18px 20px' },
  uploadCardHeader: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    gap: 8, flexWrap: 'wrap', marginBottom: 12,
  },
  uploadCardTitle: { margin: 0, fontSize: 14, fontWeight: 600, color: '#1A2E40' },

  datasetStatus: {
    display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11.5, fontWeight: 600,
    borderRadius: 999, padding: '3px 10px', whiteSpace: 'nowrap',
  },
  datasetStatusNone:    { background: '#F1F5F9', color: '#64748B' },
  datasetStatusDone:    { background: '#ECFDF5', color: '#065F46' },
  datasetStatusRunning: { background: '#EFF6FF', color: '#1D4ED8' },

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
  restoredBanner: {
    marginTop: 10, fontSize: 12, lineHeight: 1.5, color: '#1D4ED8',
    background: '#EFF6FF', border: '1px solid #BFDBFE', borderRadius: 8, padding: '8px 12px',
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

  errorBanner: {
    background: 'rgba(220,38,38,0.08)', border: '1px solid rgba(220,38,38,0.25)',
    color: '#DC2626', borderRadius: 8, padding: '10px 16px', fontSize: 13, marginBottom: 16,
  },

  actions:    { display: 'flex', gap: 12, marginBottom: 28 },

  jobList: { display: 'flex', flexDirection: 'column', gap: 12 },
  jobRow: {
    border: '0.5px solid #DDE4EA', borderRadius: 10, padding: '12px 16px',
    display: 'flex', flexDirection: 'column', gap: 6,
  },
  jobRowTop: { display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' },
  jobDot: { width: 8, height: 8, borderRadius: '50%', flexShrink: 0 },
  jobDotRunning: { background: '#2E6E8E', animation: 'ingestPulse 1.1s ease-in-out infinite' },
  jobDotSuccess: { background: '#059669' },
  jobDotFailed:  { background: '#DC2626' },
  jobKind:     { fontSize: 13, fontWeight: 700, color: '#1A2E40' },
  jobPhaseTag: {
    fontSize: 10.5, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.3,
    color: '#8BA5B8', background: '#F1F5F9', borderRadius: 5, padding: '2px 7px',
  },
  jobFilename: { fontSize: 12.5, color: '#5A7A8A', fontFamily: "'SF Mono','Fira Code',monospace" },
  jobStatusPill: {
    marginLeft: 'auto', fontSize: 11, fontWeight: 700, borderRadius: 999,
    padding: '3px 10px', textTransform: 'uppercase', letterSpacing: 0.3,
  },
  jobStatusRunning: { background: '#EFF6FF', color: '#1D4ED8' },
  jobStatusSuccess: { background: '#ECFDF5', color: '#065F46' },
  jobStatusFailed:  { background: '#FEF2F2', color: '#991B1B' },
  jobRowMeta: { fontSize: 12, color: '#8BA5B8' },
  jobResult: { display: 'flex', gap: 16, flexWrap: 'wrap', fontSize: 12.5, color: '#334155' },
  jobMergeStats: {
    fontSize: 12, color: '#1D4ED8', background: '#EFF6FF',
    border: '1px solid #BFDBFE', borderRadius: 6, padding: '6px 10px',
  },
  jobError:  { fontSize: 12.5, color: '#DC2626' },
  btnPrimary: {
    padding: '12px 32px', background: '#2E6E8E', color: '#fff',
    border: 'none', borderRadius: 8, fontSize: 14, fontWeight: 600,
    cursor: 'pointer', transition: 'opacity 0.15s', minWidth: 200,
  },

  modalOverlay: {
    position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.45)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    padding: 20, zIndex: 100,
  },
  modalCard: {
    background: '#fff', borderRadius: 14, padding: '24px 28px', width: '100%',
    maxWidth: 520, maxHeight: '85vh', overflowY: 'auto',
    boxShadow: '0 20px 50px rgba(0,0,0,0.25)',
  },
  modalTitle: { margin: '0 0 6px', fontSize: 18, fontWeight: 700, color: '#1A2E40' },
  modalSub:   { margin: '0 0 18px', fontSize: 13, color: '#5A7A8A', lineHeight: 1.5 },
  modalKindBlock: {
    border: '0.5px solid #DDE4EA', borderRadius: 10, padding: '14px 16px', marginBottom: 14,
  },
  modalKindHeader: { fontSize: 13.5, fontWeight: 700, color: '#1A2E40', marginBottom: 4 },
  modalKindFile: { fontWeight: 400, color: '#5A7A8A', fontFamily: "'SF Mono','Fira Code',monospace", fontSize: 12 },
  modalKindMeta: { margin: '0 0 12px', fontSize: 12, color: '#8BA5B8' },
  modalOptions: { display: 'flex', flexDirection: 'column', gap: 8 },
  modalOption: {
    display: 'flex', alignItems: 'flex-start', gap: 10, cursor: 'pointer',
    border: '1px solid #DDE4EA', borderRadius: 8, padding: '10px 12px',
  },
  modalOptionSelected: { borderColor: '#2E6E8E', background: '#F0F7FA' },
  modalOptionText: { margin: '4px 0 0', fontSize: 12, color: '#5A7A8A', lineHeight: 1.5 },
  modalActions: {
    display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 20,
  },
  modalCancelBtn: {
    padding: '10px 20px', borderRadius: 8, border: '0.5px solid #C5D2DC',
    background: '#fff', color: '#64748B', fontSize: 13, fontWeight: 600, cursor: 'pointer',
  },
  modalConfirmBtn: {
    padding: '10px 20px', borderRadius: 8, border: 'none',
    background: '#2E6E8E', color: '#fff', fontSize: 13, fontWeight: 600, cursor: 'pointer',
  },
};
