// Admin student explorer with demographic filters, pagination, and CSV export.
import { useState, useEffect, useCallback, useRef } from 'react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, BarChart, Bar,
} from 'recharts';
import api from '../services/api';

const PAGE_SIZE = 50;

function SearchableSelect({ value, onChange, options, placeholder }) {
  const [open,  setOpen]  = useState(false);
  const [query, setQuery] = useState('');
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    const close = (e) => { if (ref.current && !ref.current.contains(e.target)) { setOpen(false); setQuery(''); } };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, [open]);

  const filtered = query
    ? options.filter(o => o.toLowerCase().includes(query.toLowerCase()))
    : options;

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button
        type="button"
        onClick={() => { setOpen(v => !v); setQuery(''); }}
        style={{
          border: '0.5px solid #C5D2DC', borderRadius: 8, padding: '8px 28px 8px 12px',
          fontSize: 13, color: value ? '#1E293B' : '#94A3B8', background: '#fff',
          outline: 'none', cursor: 'pointer', textAlign: 'left', minWidth: 130,
        }}
      >
        {value || placeholder}
      </button>
      {open && (
        <div style={{
          position: 'absolute', top: 'calc(100% + 4px)', left: 0, zIndex: 200,
          background: '#fff', border: '1px solid #DDE4EA', borderRadius: 8,
          boxShadow: '0 4px 16px rgba(0,0,0,0.10)', minWidth: 180,
        }}>
          <div style={{ padding: '8px 8px 4px' }}>
            <input
              autoFocus
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Search…"
              style={{
                width: '100%', padding: '6px 10px', border: '1px solid #E2E8F0',
                borderRadius: 6, fontSize: 12, color: '#1E293B', outline: 'none',
                boxSizing: 'border-box', background: '#F8FAFC',
              }}
            />
          </div>
          <div style={{ maxHeight: 200, overflowY: 'auto' }}>
            <div
              onClick={() => { onChange(''); setOpen(false); setQuery(''); }}
              style={{ padding: '8px 12px', fontSize: 13, cursor: 'pointer', color: '#64748B' }}
              onMouseEnter={e => e.currentTarget.style.background = '#F0F4F8'}
              onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
            >
              {placeholder}
            </div>
            {filtered.map(opt => (
              <div
                key={opt}
                onClick={() => { onChange(opt); setOpen(false); setQuery(''); }}
                style={{
                  padding: '8px 12px', fontSize: 13, cursor: 'pointer',
                  color: '#1E293B', fontWeight: value === opt ? 600 : 400,
                  background: value === opt ? '#EFF6FF' : 'transparent',
                }}
                onMouseEnter={e => { if (value !== opt) e.currentTarget.style.background = '#F0F4F8'; }}
                onMouseLeave={e => { if (value !== opt) e.currentTarget.style.background = 'transparent'; }}
              >
                {opt}
              </div>
            ))}
            {filtered.length === 0 && (
              <div style={{ padding: '8px 12px', fontSize: 12, color: '#94A3B8' }}>No matches</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function PassBadge({ passed }) {
  return (
    <span style={{
      fontSize: 11, fontWeight: 600, padding: '2px 8px', borderRadius: 20,
      background: passed ? '#DCFCE7' : '#FEE2E2',
      color:      passed ? '#166534' : '#991B1B',
    }}>
      {passed ? 'Pass' : 'Fail'}
    </span>
  );
}

function StudentDetail({ studentId, onClose }) {
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get(`/api/explorer/student/${encodeURIComponent(studentId)}`)
      .then(r => setDetail(r.data))
      .catch(() => setDetail(null))
      .finally(() => setLoading(false));
  }, [studentId]);

  const peerData = detail ? [
    { label: 'This Student', value: detail.peer_comparison?.student_avg },
    { label: 'Class Avg',    value: detail.peer_comparison?.class_avg },
    { label: 'Institution',  value: detail.peer_comparison?.institution_avg },
  ].filter(d => d.value != null) : [];

  return (
    <div style={s.detailPanel}>
      <div style={s.detailHeader}>
        <h3 style={s.detailTitle}>Student: {studentId}</h3>
        <button style={s.closeBtn} onClick={onClose}>✕</button>
      </div>
      {loading && <p style={s.muted}>Loading…</p>}
      {!loading && !detail && <p style={s.muted}>Student data unavailable.</p>}
      {detail && (
        <>
          <div style={s.detailKpiRow}>
            <div style={s.detailKpi}>
              <p style={s.kpiLabel}>Avg Mark</p>
              <p style={{ ...s.kpiVal, color: detail.overall_passed ? '#059669' : '#DC2626' }}>
                {detail.avg_mark != null ? `${detail.avg_mark}%` : '—'}
              </p>
            </div>
            <div style={s.detailKpi}>
              <p style={s.kpiLabel}>Overall Result</p>
              <PassBadge passed={detail.overall_passed} />
            </div>
            <div style={s.detailKpi}>
              <p style={s.kpiLabel}>Records</p>
              <p style={s.kpiVal}>{detail.records?.length ?? 0}</p>
            </div>
          </div>

          {detail.trend?.length > 0 && (
            <div style={{ marginBottom: 16 }}>
              <p style={s.sectionLabel}>Performance Trend</p>
              <ResponsiveContainer width="100%" height={160}>
                <LineChart data={detail.trend}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#EEF0F4" vertical={false} />
                  <XAxis dataKey="period" tick={{ fontSize: 10, fill: '#64748B' }} />
                  <YAxis tick={{ fontSize: 10, fill: '#64748B' }} domain={[0, 100]} unit="%" />
                  <Tooltip formatter={v => `${v}%`} />
                  <Line type="monotone" dataKey="mark" name="Mark"
                    stroke="#2E6E8E" strokeWidth={2} dot={{ r: 3 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}

          {peerData.length > 0 && (
            <div>
              <p style={s.sectionLabel}>Peer Comparison</p>
              <ResponsiveContainer width="100%" height={120}>
                <BarChart data={peerData} layout="vertical" barCategoryGap="25%">
                  <CartesianGrid strokeDasharray="3 3" stroke="#EEF0F4" horizontal={false} />
                  <XAxis type="number" tick={{ fontSize: 10, fill: '#64748B' }} domain={[0, 100]} unit="%" />
                  <YAxis dataKey="label" type="category" tick={{ fontSize: 11, fill: '#475569' }} width={90} />
                  <Tooltip formatter={v => `${v}%`} />
                  <Bar dataKey="value" name="Avg Mark" fill="#2E6E8E" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default function AdminExplorer() {
  const [filters,    setFilters]    = useState({ subjects: [], assessment_types: [], trimesters: [], countries: [], genders: [], age_groups: [] });
  const [search,     setSearch]     = useState('');
  const [subject,    setSubject]    = useState('');
  const [trimester,  setTrimester]  = useState('');
  const [country,    setCountry]    = useState('');
  const [gender,     setGender]     = useState('');
  const [passed,     setPassed]     = useState('');
  const [records,    setRecords]    = useState([]);
  const [total,      setTotal]      = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [page,       setPage]       = useState(1);
  const [loading,    setLoading]    = useState(false);
  const [selectedId, setSelectedId] = useState(null);

  useEffect(() => {
    api.get('/api/explorer/filters').then(r => setFilters(r.data)).catch(() => {});
  }, []);

  const fetchRecords = useCallback(async (pg = 1) => {
    setLoading(true);
    try {
      const params = { page: pg, page_size: PAGE_SIZE };
      if (search)   params.search   = search;
      if (subject)  params.subject  = subject;
      if (trimester) params.trimester = trimester;
      if (country)  params.country  = country;
      if (gender)   params.gender   = gender;
      if (passed)   params.passed   = passed;
      const res = await api.get('/api/explorer/records', { params });
      setRecords(res.data.data ?? []);
      setTotal(res.data.total ?? 0);
      setTotalPages(res.data.total_pages ?? 0);
      setPage(pg);
    } catch {
      setRecords([]);
    } finally {
      setLoading(false);
    }
  }, [search, subject, trimester, country, gender, passed]);

  useEffect(() => { fetchRecords(1); }, [fetchRecords]);

  const handleSearch = e => { e.preventDefault(); fetchRecords(1); };

  const colStyle = { fontSize: 12, color: '#475569', padding: '10px 12px', borderBottom: '0.5px solid #F0F4F8', whiteSpace: 'nowrap' };
  const thStyle  = { fontSize: 11, fontWeight: 600, color: '#94A3B8', padding: '10px 12px', borderBottom: '1px solid #E2E8F0', textTransform: 'uppercase', letterSpacing: 0.5, background: '#F8FAFC', whiteSpace: 'nowrap' };

  return (
    <div style={s.page}>
      {/* Header */}
      <div style={s.pageHeader}>
        <div>
          <h1 style={s.pageTitle}>Student Analytics</h1>
          <p style={s.pageSub}>Explore individual student records and drill into performance detail</p>
        </div>
        <span style={s.countBadge}>{total.toLocaleString()} records</span>
      </div>

      {/* Filters */}
      <div style={s.card}>
        <form onSubmit={handleSearch} style={s.filterRow}>
          <input
            style={s.searchInput}
            placeholder="Search student ID…"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
          <SearchableSelect
            value={subject}
            onChange={setSubject}
            options={filters.subjects}
            placeholder="All subjects"
          />
          <select style={s.select} value={trimester} onChange={e => setTrimester(e.target.value)}>
            <option value="">All trimesters</option>
            {filters.trimesters.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
          {filters.countries.length > 0 && (
            <SearchableSelect
              value={country}
              onChange={setCountry}
              options={filters.countries}
              placeholder="All countries"
            />
          )}
          {filters.genders.length > 0 && (
            <select style={s.select} value={gender} onChange={e => setGender(e.target.value)}>
              <option value="">All genders</option>
              {filters.genders.map(g => <option key={g} value={g}>{g}</option>)}
            </select>
          )}
          <select style={s.select} value={passed} onChange={e => setPassed(e.target.value)}>
            <option value="">Pass / Fail</option>
            <option value="true">Pass only</option>
            <option value="false">Fail only</option>
          </select>
          <button type="submit" style={s.filterBtn}>Search</button>
          <button type="button" style={s.clearBtn} onClick={() => {
            setSearch(''); setSubject(''); setTrimester('');
            setCountry(''); setGender(''); setPassed('');
          }}>Clear</button>
        </form>
      </div>

      <div style={{ display: 'flex', gap: 20, alignItems: 'flex-start' }}>
        {/* Table */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={s.tableCard}>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 700 }}>
                <thead>
                  <tr>
                    <th style={thStyle}>Student ID</th>
                    <th style={thStyle}>Subject</th>
                    <th style={thStyle}>Assessment</th>
                    <th style={thStyle}>Mark %</th>
                    <th style={thStyle}>Result</th>
                    <th style={thStyle}>Period</th>
                    <th style={thStyle}>Country</th>
                    <th style={thStyle}></th>
                  </tr>
                </thead>
                <tbody>
                  {loading && (
                    <tr><td colSpan={8} style={{ ...colStyle, textAlign: 'center', padding: 32, color: '#94A3B8' }}>Loading…</td></tr>
                  )}
                  {!loading && records.length === 0 && (
                    <tr><td colSpan={8} style={{ ...colStyle, textAlign: 'center', padding: 32, color: '#94A3B8' }}>No records found.</td></tr>
                  )}
                  {!loading && records.map((rec, i) => (
                    <tr
                      key={i}
                      style={{ background: selectedId === rec.student_id ? '#EFF6FF' : (i % 2 === 0 ? '#fff' : '#FAFBFC') }}
                    >
                      <td style={{ ...colStyle, fontWeight: 600, color: '#1E293B' }}>{rec.student_id}</td>
                      <td style={colStyle}>{rec.subject ?? '—'}</td>
                      <td style={colStyle}>{rec.assessment_type ?? '—'}</td>
                      <td style={{ ...colStyle, fontWeight: 600, color: rec.mark_percent != null && rec.mark_percent < 50 ? '#DC2626' : '#059669' }}>
                        {rec.mark_percent != null ? `${rec.mark_percent}%` : '—'}
                      </td>
                      <td style={colStyle}><PassBadge passed={rec.passed} /></td>
                      <td style={colStyle}>{rec.study_period ?? '—'}</td>
                      <td style={colStyle}>{rec.country ?? '—'}</td>
                      <td style={{ ...colStyle, textAlign: 'right' }}>
                        <button
                          style={{ ...s.viewBtn, background: selectedId === rec.student_id ? '#2E6E8E' : '#F0F4F8', color: selectedId === rec.student_id ? '#fff' : '#2E6E8E' }}
                          onClick={() => setSelectedId(id => id === rec.student_id ? null : rec.student_id)}
                        >
                          {selectedId === rec.student_id ? 'Close' : 'View'}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div style={s.pagination}>
                <button style={s.pageBtn} disabled={page <= 1} onClick={() => fetchRecords(page - 1)}>← Prev</button>
                <span style={s.pageInfo}>Page {page} of {totalPages}</span>
                <button style={s.pageBtn} disabled={page >= totalPages} onClick={() => fetchRecords(page + 1)}>Next →</button>
              </div>
            )}
          </div>
        </div>

        {/* Student detail panel */}
        {selectedId && (
          <div style={{ width: 360, flexShrink: 0 }}>
            <StudentDetail studentId={selectedId} onClose={() => setSelectedId(null)} />
          </div>
        )}
      </div>
    </div>
  );
}

const s = {
  page:       { padding: '28px 32px', background: '#F0F4F8', minHeight: '100vh', boxSizing: 'border-box' },
  pageHeader: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 },
  pageTitle:  { margin: 0, fontSize: 20, fontWeight: 700, color: '#1A2E40' },
  pageSub:    { margin: '4px 0 0', fontSize: 13, color: '#64748B' },
  countBadge: { fontSize: 13, fontWeight: 600, color: '#2E6E8E', background: '#EFF6FF', padding: '6px 14px', borderRadius: 20 },

  card:      { background: '#fff', border: '0.5px solid #DDE4EA', borderRadius: 10, padding: '16px 20px', marginBottom: 16 },
  filterRow: { display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 10 },
  searchInput: {
    border: '0.5px solid #C5D2DC', borderRadius: 8, padding: '8px 12px',
    fontSize: 13, color: '#1E293B', outline: 'none', minWidth: 180,
  },
  select: {
    border: '0.5px solid #C5D2DC', borderRadius: 8, padding: '8px 12px',
    fontSize: 13, color: '#1E293B', background: '#fff', outline: 'none', cursor: 'pointer',
  },
  filterBtn: {
    padding: '8px 18px', borderRadius: 8, border: 'none',
    background: '#2E6E8E', color: '#fff', fontSize: 13, fontWeight: 600, cursor: 'pointer',
  },
  clearBtn: {
    padding: '8px 14px', borderRadius: 8, border: '0.5px solid #C5D2DC',
    background: '#fff', color: '#64748B', fontSize: 13, cursor: 'pointer',
  },

  tableCard: { background: '#fff', border: '0.5px solid #DDE4EA', borderRadius: 10, overflow: 'hidden' },
  viewBtn: { padding: '4px 12px', borderRadius: 6, border: 'none', fontSize: 12, fontWeight: 600, cursor: 'pointer' },
  pagination: { display: 'flex', alignItems: 'center', gap: 16, padding: '12px 16px', borderTop: '0.5px solid #F0F4F8' },
  pageBtn: {
    padding: '6px 14px', borderRadius: 7, border: '0.5px solid #C5D2DC',
    background: '#fff', color: '#2E6E8E', fontSize: 13, fontWeight: 600, cursor: 'pointer',
  },
  pageInfo: { fontSize: 12, color: '#94A3B8', flex: 1, textAlign: 'center' },

  detailPanel: {
    background: '#fff', border: '0.5px solid #DDE4EA', borderRadius: 10,
    padding: '20px', position: 'sticky', top: 20,
  },
  detailHeader: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 },
  detailTitle:  { margin: 0, fontSize: 14, fontWeight: 700, color: '#1A2E40' },
  closeBtn: { background: 'none', border: 'none', cursor: 'pointer', fontSize: 16, color: '#94A3B8', padding: 4 },
  detailKpiRow: { display: 'flex', gap: 12, marginBottom: 16 },
  detailKpi: { flex: 1, background: '#F8FAFC', borderRadius: 8, padding: '10px 12px' },
  kpiLabel: { margin: 0, fontSize: 10, fontWeight: 600, color: '#94A3B8', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6 },
  kpiVal: { margin: 0, fontSize: 18, fontWeight: 700, color: '#1E293B' },
  sectionLabel: { margin: '0 0 8px', fontSize: 12, fontWeight: 600, color: '#475569' },
  muted: { color: '#94A3B8', fontSize: 13 },
};
