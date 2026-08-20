// Shared between Sidebar.jsx (badge) and DataIngestion.jsx (marks jobs seen) —
// kept as a standalone module rather than one importing from the other, since
// they're a layout component and a page respectively, not naturally coupled.
//
// Ingestion confirm returns immediately and finishes later in the background
// (see backend/app/main.py's IngestJob) — "seen" tracks which finished jobs
// this browser has already been shown, so the sidebar badge only counts
// genuinely new completions. It's a personal, client-side read-marker, not
// shared ingestion state, so localStorage is the right place for it, not the DB.
export const INGEST_LAST_SEEN_KEY = 'edapt_ingest_last_seen_job_id';
export const INGEST_JOBS_SEEN_EVENT = 'edapt:ingest-jobs-seen';

// Call after fetching the jobs list on the Data Ingestion page, so the
// sidebar badge clears immediately instead of waiting for its next poll tick.
export function markIngestJobsSeen(jobs) {
  if (!jobs || jobs.length === 0) return;
  const maxId = Math.max(...jobs.map(j => j.id));
  const prev = Number(localStorage.getItem(INGEST_LAST_SEEN_KEY) || 0);
  if (maxId <= prev) return;
  localStorage.setItem(INGEST_LAST_SEEN_KEY, String(maxId));
  window.dispatchEvent(new Event(INGEST_JOBS_SEEN_EVENT));
}
