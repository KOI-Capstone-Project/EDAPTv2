import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer,
} from 'recharts';
import api from '../services/api';

// ── Shared sub-components ─────────────────────────────────────────────────────

function Spinner() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 200 }}>
      <div style={{ width: 32, height: 32, border: '3px solid #F0F4F8', borderTop: '3px solid #2E6E8E', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
    </div>
  );
}

function EmptyState() {
  return (
    <tr>
      <td colSpan={9} style={{ padding: 0, border: 'none' }}>
        <div style={{ textAlign: 'center', padding: '60px 20px', color: '#8BA5B8' }}>
          <div style={{ fontSize: 32, marginBottom: 12 }}>📭</div>
          <div style={{ fontSize: 14, fontWeight: 500, color: '#1A2E40', marginBottom: 4 }}>No records found</div>
          <div style={{ fontSize: 13 }}>Try adjusting your filters</div>
        </div>
      </td>
    </tr>
  );
}

function MarkBar({ value }) {
  const pct   = value ?? 0;
  const color = pct >= 50 ? '#1D9E75' : '#E24B4A';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={{ width: 80, background: '#F0F4F8', borderRadius: 3, height: 6 }}>
        <div style={{ width: `${Math.min(pct, 100)}%`, height: '100%', background: color, borderRadius: 3 }} />
      </div>
      <span style={{ fontSize: 12, color, width: 44, textAlign: 'right' }}>{pct.toFixed(1)}%</span>
    </div>
  );
}

const PassBadge = ({ passed }) => (
  <span style={{
    background: passed ? '#E1F5EE' : '#FCEBEB',
    color:      passed ? '#0F6E56' : '#A32D2D',
    borderRadius: 20, padding: '3px 10px', fontSize: 12, fontWeight: 500,
  }}>
    {passed ? 'Pass' : 'Fail'}
  </span>
);

const SubjectBadge = ({ subject }) => (
  <span style={{
    background: '#E6F1FB', color: '#185FA5',
    borderRadius: 20, padding: '3px 10px', fontSize: 12, fontWeight: 500,
  }}>
    {subject}
  </span>
);

function PillToggle({ value, onChange }) {
  return (
    <div style={{ display: 'flex', background: '#F0F4F8', borderRadius: 8, padding: 3, gap: 2 }}>
      {[{ v: 'All', l: 'All' }, { v: 'Pass', l: 'Pass' }, { v: 'Fail', l: 'Fail' }].map(o => (
        <button key={o.v} onClick={() => onChange(o.v)} style={{
          padding: '5px 12px', borderRadius: 6, border: 'none', cursor: 'pointer',
          fontSize: 12, fontWeight: 600,
          background: value === o.v ? '#fff'    : 'transparent',
          color:      value === o.v ? '#1A2E40' : '#5A7A8A',
          boxShadow:  value === o.v ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
        }}>{o.l}</button>
      ))}
    </div>
  );
}

// ── Admin Student Detail ──────────────────────────────────────────────────────

function AdminStudentDetail({ studentId, onBack }) {
  const [detail,  setDetail]  = useState(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    api.get(`/api/explorer/student/${encodeURIComponent(studentId)}`)
      .then(r => setDetail(r.data))
      .catch(() => setDetail(null))
      .finally(() => setLoading(false));
  }, [studentId]);

  if (loading) return <Spinner />;
  if (!detail) return (
    <div>
      <button onClick={onBack} style={s.backBtn}>← Back to Records</button>
      <div style={{ ...s.errorBox, marginTop: 16 }}>Student not found.</div>
    </div>
  );

  const uniqueSubjects = [...new Set(detail.records.map(r => r.subject).filter(Boolean))];
  const firstRecord    = detail.records[0] ?? {};

  const peerBars = [
    { label: 'This Student',    value: detail.peer_comparison?.student_avg,    color: '#2E6E8E' },
    { label: 'Class Average',   value: detail.peer_comparison?.class_avg,       color: '#4f8ef7' },
    { label: 'Institution Avg', value: detail.peer_comparison?.institution_avg, color: '#94A3B8' },
  ].filter(b => b.value != null);

  return (
    <div>
      <button onClick={onBack} style={s.backBtn}>← Back to Records</button>

      <div style={s.detailHeader}>
        <div>
          <h1 style={{ margin: '0 0 10px', fontSize: 22, fontWeight: 500, color: '#1A2E40' }}>{detail.student_id}</h1>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            {uniqueSubjects.map(sub => <SubjectBadge key={sub} subject={sub} />)}
            <PassBadge passed={detail.overall_passed} />
          </div>
          {(firstRecord.country || firstRecord.gender || firstRecord.age_group) && (
            <div style={{ display: 'flex', gap: 12, marginTop: 10 }}>
              {firstRecord.country   && <span style={s.demoBadge}>🌍 {firstRecord.country}</span>}
              {firstRecord.gender    && <span style={s.demoBadge}>👤 {firstRecord.gender}</span>}
              {firstRecord.age_group && <span style={s.demoBadge}>📅 {firstRecord.age_group}</span>}
            </div>
          )}
        </div>
        <div style={s.statBox}>
          <p style={s.statLabel}>Average Mark</p>
          <p style={s.statValue}>{detail.avg_mark != null ? `${detail.avg_mark.toFixed(1)}%` : '—'}</p>
        </div>
      </div>

      <div style={{ ...s.card, marginBottom: 20 }}>
        <h2 style={s.cardTitle}>Assessment History — All Subjects</h2>
        <div style={{ overflowX: 'auto' }}>
          <table style={s.table}>
            <thead>
              <tr style={s.thead}>
                <th style={s.th}>Subject</th>
                <th style={s.th}>Assessment Type</th>
                <th style={s.th}>Study Period</th>
                <th style={{ ...s.th, minWidth: 160 }}>Mark %</th>
                <th style={s.th}>Status</th>
                <th style={s.th}>Country</th>
                <th style={s.th}>Gender</th>
                <th style={s.th}>Age Group</th>
              </tr>
            </thead>
            <tbody>
              {detail.records.map((r, i) => (
                <tr key={i} style={{ background: i % 2 === 0 ? '#fff' : '#F8FAFB' }}>
                  <td style={s.td}><SubjectBadge subject={r.subject} /></td>
                  <td style={s.td}>{r.assessment_type}</td>
                  <td style={s.td}>{r.study_period}</td>
                  <td style={{ ...s.td, minWidth: 160 }}><MarkBar value={r.mark_percent} /></td>
                  <td style={s.td}><PassBadge passed={r.passed} /></td>
                  <td style={s.td}>{r.country   || '—'}</td>
                  <td style={s.td}>{r.gender    || '—'}</td>
                  <td style={s.td}>{r.age_group || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {detail.trend.length > 0 && (
        <div style={{ ...s.card, marginBottom: 20 }}>
          <h2 style={s.cardTitle}>Performance Trend</h2>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={detail.trend} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
              <XAxis dataKey="period" type="category" tick={{ fontSize: 11 }} />
              <YAxis domain={[0, 100]} unit="%" tick={{ fontSize: 11 }} />
              <Tooltip formatter={v => v != null ? `${Number(v).toFixed(1)}%` : 'N/A'} />
              <Line type="monotone" dataKey="mark" name="Mark %" stroke="#2E6E8E" strokeWidth={2} dot={{ r: 4 }} connectNulls />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      <div style={{ ...s.card, marginBottom: 20 }}>
        <h2 style={s.cardTitle}>Peer Comparison</h2>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {peerBars.map(b => (
            <div key={b.label} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <span style={{ minWidth: 140, fontSize: 13, color: '#5A7A8A' }}>{b.label}</span>
              <div style={{ flex: 1, background: '#F0F4F8', borderRadius: 4, height: 22, overflow: 'hidden' }}>
                <div style={{ width: `${Math.min(b.value ?? 0, 100)}%`, height: '100%', background: b.color, borderRadius: 4, transition: 'width 0.4s' }} />
              </div>
              <span style={{ minWidth: 50, fontSize: 13, fontWeight: 600, color: '#1A2E40', textAlign: 'right' }}>
                {b.value != null ? `${b.value.toFixed(1)}%` : '—'}
              </span>
            </div>
          ))}
        </div>
      </div>

      <button
        style={s.predictBtn}
        onClick={() => navigate(
          `/predictions?student_id=${encodeURIComponent(detail.student_id)}` +
          `&subject=${encodeURIComponent(firstRecord?.subject || '')}` +
          `&mark=${detail.avg_mark ?? ''}`
        )}
      >
        Predict Outcome →
      </button>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function AdminExplorer() {
  const [filterSubj,    setFilterSubj]    = useState('All');
  const [filterType,    setFilterType]    = useState('All');
  const [filterPassed,  setFilterPassed]  = useState('All');
  const [filterTrim,    setFilterTrim]    = useState('All');
  const [filterCountry, setFilterCountry] = useState('All');
  const [filterGender,  setFilterGender]  = useState('All');
  const [filterAge,     setFilterAge]     = useState('All');
  const [searchInput,   setSearchInput]   = useState('');
  const [searchQuery,   setSearchQuery]   = useState('');
  const [page,          setPage]          = useState(1);
  const [selectedId,    setSelectedId]    = useState(null);
  const [exporting,     setExporting]     = useState(false);

  const [filters,    setFilters]    = useState({ subjects: [], assessment_types: [], trimesters: [], countries: [], genders: [], age_groups: [] });
  const [records,    setRecords]    = useState([]);
  const [total,      setTotal]      = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [loading,    setLoading]    = useState(true);

  const debounceRef = useRef(null);

  const handleSearch = val => {
    setSearchInput(val);
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => { setSearchQuery(val); setPage(1); }, 300);
  };

  useEffect(() => {
    api.get('/api/explorer/filters').then(r => setFilters(r.data)).catch(() => {});
  }, []);

  const buildParams = () => {
    const p = { page, page_size: 50 };
    if (filterSubj   !== 'All')  p.subject         = filterSubj;
    if (filterType   !== 'All')  p.assessment_type = filterType;
    if (filterPassed === 'Pass') p.passed = 'true';
    if (filterPassed === 'Fail') p.passed = 'false';
    if (filterTrim   !== 'All')  p.trimester  = filterTrim;
    if (filterCountry!== 'All')  p.country    = filterCountry;
    if (filterGender !== 'All')  p.gender     = filterGender;
    if (filterAge    !== 'All')  p.age_group  = filterAge;
    if (searchQuery)             p.search     = searchQuery;
    return p;
  };

  useEffect(() => {
    setLoading(true);
    api.get('/api/explorer/records', { params: buildParams() })
      .then(r => {
        setRecords(r.data.data ?? []);
        setTotal(r.data.total ?? 0);
        setTotalPages(r.data.total_pages ?? 0);
      })
      .catch(() => setRecords([]))
      .finally(() => setLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, filterSubj, filterType, filterPassed, filterTrim, filterCountry, filterGender, filterAge, searchQuery]);

  const clearFilters = () => {
    setFilterSubj('All'); setFilterType('All'); setFilterPassed('All');
    setFilterTrim('All'); setFilterCountry('All'); setFilterGender('All');
    setFilterAge('All');  setSearchInput(''); setSearchQuery(''); setPage(1);
  };

  const handleExport = async () => {
    setExporting(true);
    try {
      const p = { ...buildParams() };
      delete p.page; delete p.page_size;
      const response = await api.get('/api/explorer/export', { params: p, responseType: 'blob' });
      const url  = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href  = url;
      link.setAttribute('download', `edapt_export_${Date.now()}.csv`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Export failed', err);
    } finally {
      setExporting(false);
    }
  };

  const startRow = total === 0 ? 0 : (page - 1) * 50 + 1;
  const endRow   = Math.min(page * 50, total);

  if (selectedId) {
    return <AdminStudentDetail studentId={selectedId} onBack={() => setSelectedId(null)} />;
  }

  return (
    <div>
      <div style={s.pageHeader}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
          <div>
            <h1 style={s.pageTitle}>Student Analytics</h1>
            <p style={s.pageSub}>Browse all student records across all subjects</p>
          </div>
          <button
            style={{ ...s.exportBtn, opacity: exporting ? 0.7 : 1 }}
            onClick={handleExport}
            disabled={exporting}
          >
            {exporting ? 'Exporting…' : '⬇ Export CSV'}
          </button>
        </div>
      </div>

      {/* ── Filter bar ──────────────────────────────────────────────── */}
      <div style={s.filterCard}>
        <div style={s.filterRow}>
          <div style={s.filterGroup}>
            <label style={s.filterLabel}>Subject</label>
            <select style={s.select} value={filterSubj} onChange={e => { setFilterSubj(e.target.value); setPage(1); }}>
              <option value="All">All Subjects</option>
              {filters.subjects.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <div style={s.filterGroup}>
            <label style={s.filterLabel}>Assessment Type</label>
            <select style={s.select} value={filterType} onChange={e => { setFilterType(e.target.value); setPage(1); }}>
              <option value="All">All Types</option>
              {filters.assessment_types.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <div style={s.filterGroup}>
            <label style={s.filterLabel}>Status</label>
            <PillToggle value={filterPassed} onChange={v => { setFilterPassed(v); setPage(1); }} />
          </div>
          <div style={s.filterGroup}>
            <label style={s.filterLabel}>Trimester</label>
            <select style={s.select} value={filterTrim} onChange={e => { setFilterTrim(e.target.value); setPage(1); }}>
              <option value="All">All Trimesters</option>
              {filters.trimesters.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
        </div>

        <div style={{ ...s.filterRow, marginTop: 10 }}>
          <div style={s.filterGroup}>
            <label style={s.filterLabel}>Country</label>
            <select style={s.select} value={filterCountry} onChange={e => { setFilterCountry(e.target.value); setPage(1); }}>
              <option value="All">All Countries</option>
              {filters.countries.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div style={s.filterGroup}>
            <label style={s.filterLabel}>Gender</label>
            <select style={s.select} value={filterGender} onChange={e => { setFilterGender(e.target.value); setPage(1); }}>
              <option value="All">All Genders</option>
              {filters.genders.map(g => <option key={g} value={g}>{g}</option>)}
            </select>
          </div>
          <div style={s.filterGroup}>
            <label style={s.filterLabel}>Age Group</label>
            <select style={s.select} value={filterAge} onChange={e => { setFilterAge(e.target.value); setPage(1); }}>
              <option value="All">All Ages</option>
              {filters.age_groups.map(a => <option key={a} value={a}>{a}</option>)}
            </select>
          </div>
          <div style={{ ...s.filterGroup, flex: 2 }}>
            <label style={s.filterLabel}>Search</label>
            <input
              style={s.searchInput}
              placeholder="Search by Student ID..."
              value={searchInput}
              onChange={e => handleSearch(e.target.value)}
            />
          </div>
          <div style={{ display: 'flex', alignItems: 'flex-end' }}>
            <button style={s.clearBtn} onClick={clearFilters}>Clear All</button>
          </div>
        </div>

        <p style={s.resultCount}>
          {loading ? 'Loading…' : total === 0
            ? 'No records found for selected filters'
            : `Showing ${startRow}–${endRow} of ${total.toLocaleString()} records`}
        </p>
      </div>

      {/* ── Table ───────────────────────────────────────────────────── */}
      <div style={s.tableWrapper}>
        <div style={{ overflowX: 'auto' }}>
          <table style={s.table}>
            <thead>
              <tr style={s.thead}>
                <th style={s.th}>Student ID</th>
                <th style={s.th}>Subject</th>
                <th style={s.th}>Assessment Type</th>
                <th style={s.th}>Study Period</th>
                <th style={{ ...s.th, minWidth: 160 }}>Mark %</th>
                <th style={s.th}>Status</th>
                <th style={s.th}>Country</th>
                <th style={s.th}>Gender</th>
                <th style={s.th}>Age Group</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={9} style={{ padding: 0, border: 'none' }}><Spinner /></td></tr>
              ) : records.length === 0 ? (
                <EmptyState />
              ) : records.map((r, i) => (
                <tr
                  key={i}
                  onClick={() => setSelectedId(r.student_id)}
                  style={{ background: i % 2 === 0 ? '#fff' : '#F8FAFB', cursor: 'pointer' }}
                  onMouseEnter={e => e.currentTarget.style.background = '#F0F9FF'}
                  onMouseLeave={e => e.currentTarget.style.background = i % 2 === 0 ? '#fff' : '#F8FAFB'}
                >
                  <td style={s.td}>{r.student_id}</td>
                  <td style={s.td}><SubjectBadge subject={r.subject} /></td>
                  <td style={s.td}>{r.assessment_type}</td>
                  <td style={s.td}>{r.study_period}</td>
                  <td style={{ ...s.td, minWidth: 160 }}><MarkBar value={r.mark_percent} /></td>
                  <td style={s.td}><PassBadge passed={r.passed} /></td>
                  <td style={s.td}>{r.country   || '—'}</td>
                  <td style={s.td}>{r.gender    || '—'}</td>
                  <td style={s.td}>{r.age_group || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* ── Pagination ──────────────────────────────────────────────── */}
      {totalPages > 1 && (
        <div style={s.pagination}>
          <button style={s.pageBtn} disabled={page === 1}          onClick={() => setPage(1)}>« First</button>
          <button style={s.pageBtn} disabled={page === 1}          onClick={() => setPage(p => p - 1)}>‹ Prev</button>
          <span style={s.pageInfo}>Page {page} of {totalPages}</span>
          <button style={s.pageBtn} disabled={page === totalPages} onClick={() => setPage(p => p + 1)}>Next ›</button>
          <button style={s.pageBtn} disabled={page === totalPages} onClick={() => setPage(totalPages)}>Last »</button>
        </div>
      )}
    </div>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const s = {
  pageHeader: { marginBottom: 20 },
  pageTitle:  { margin: '0 0 4px', fontSize: 24, fontWeight: 500, color: '#1A2E40' },
  pageSub:    { margin: 0, fontSize: 13, color: '#5A7A8A' },

  exportBtn: {
    padding: '9px 18px', borderRadius: 8, border: 'none', cursor: 'pointer',
    background: '#1A2E40', color: '#fff', fontSize: 13, fontWeight: 500, flexShrink: 0,
  },

  filterCard:  { background: '#fff', border: '0.5px solid #DDE4EA', borderRadius: 12, padding: '14px 16px', marginBottom: 20 },
  filterRow:   { display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end' },
  filterGroup: { display: 'flex', flexDirection: 'column', gap: 4 },
  filterLabel: { fontSize: 11, fontWeight: 600, color: '#8BA5B8', textTransform: 'uppercase', letterSpacing: 0.5 },
  select: {
    height: 36, padding: '0 12px', borderRadius: 8,
    border: '0.5px solid #C5D2DC', fontSize: 13, color: '#1A2E40',
    background: '#fff', cursor: 'pointer', minWidth: 130, outline: 'none',
  },
  searchInput: {
    height: 36, padding: '0 12px', borderRadius: 8,
    border: '0.5px solid #C5D2DC', fontSize: 13, color: '#1A2E40',
    outline: 'none', minWidth: 180, width: '100%',
  },
  clearBtn: {
    height: 36, padding: '0 14px', borderRadius: 8,
    border: '0.5px solid #C5D2DC', background: '#fff',
    fontSize: 12, fontWeight: 600, color: '#5A7A8A', cursor: 'pointer',
  },
  resultCount: { margin: '10px 0 0', fontSize: 12, color: '#8BA5B8' },

  tableWrapper: { background: '#fff', border: '0.5px solid #DDE4EA', borderRadius: 12, overflow: 'hidden', marginBottom: 16 },
  table:        { width: '100%', borderCollapse: 'collapse' },
  thead:        { background: '#F0F4F8' },
  th: {
    padding: '12px 16px', fontSize: 11, fontWeight: 500, color: '#5A7A8A',
    textTransform: 'uppercase', letterSpacing: 0.5, textAlign: 'left',
    borderBottom: '0.5px solid #F0F4F8', whiteSpace: 'nowrap',
  },
  td: { padding: '12px 16px', fontSize: 13, color: '#1A2E40', borderBottom: '0.5px solid #F0F4F8' },

  pagination: { display: 'flex', alignItems: 'center', gap: 8, justifyContent: 'center', padding: '8px 0 4px' },
  pageBtn: {
    padding: '6px 12px', borderRadius: 6, border: '0.5px solid #C5D2DC',
    background: '#fff', fontSize: 12, cursor: 'pointer', color: '#5A7A8A',
  },
  pageInfo: { fontSize: 13, color: '#5A7A8A', margin: '0 8px' },

  backBtn: {
    padding: '8px 16px', borderRadius: 8, border: '0.5px solid #C5D2DC',
    background: '#fff', fontSize: 13, cursor: 'pointer', color: '#5A7A8A',
    fontWeight: 500, marginBottom: 20, display: 'inline-block',
  },
  detailHeader: {
    display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
    gap: 16, marginBottom: 24,
  },
  demoBadge: {
    fontSize: 12, color: '#5A7A8A', background: '#F0F4F8',
    borderRadius: 6, padding: '3px 10px',
  },
  statBox: {
    background: 'linear-gradient(135deg, #1A2E40, #2E6E8E)',
    borderRadius: 12, padding: '14px 20px', color: '#fff', textAlign: 'center', flexShrink: 0,
  },
  statLabel: { margin: '0 0 4px', fontSize: 11, opacity: 0.75 },
  statValue: { margin: 0, fontSize: 22, fontWeight: 500 },

  card:      { background: '#fff', border: '0.5px solid #DDE4EA', borderRadius: 12, padding: '20px' },
  cardTitle: { margin: '0 0 14px', fontSize: 14, fontWeight: 500, color: '#1A2E40' },

  errorBox: {
    background: '#FCEBEB', border: '0.5px solid #F09595',
    color: '#A32D2D', borderRadius: 8, padding: '10px 16px', fontSize: 13,
  },

  predictBtn: {
    width: '100%', padding: '12px 0', borderRadius: 8, border: 'none',
    background: '#2E6E8E', color: '#fff', fontSize: 14, fontWeight: 500,
    cursor: 'pointer', letterSpacing: 0.3,
  },
};
