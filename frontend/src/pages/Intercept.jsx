import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Radio, ShieldAlert, X } from 'lucide-react';
import { api } from '../api/client';
import { CATEGORIES } from '../categories';

const CLASSIFICATIONS = [
  ...CATEGORIES.map(category => ({
    code: category.apiKey,
    label: category.title,
    color: category.color,
  })),
  { code: 'other', label: 'Other', color: '#9ca3af' },
  { code: 'not_a_document', label: 'Not a Document', color: '#f59e0b' },
  { code: 'no_forgery_detected', label: 'Genuine / No Forgery', color: '#00ff66' },
];

function withDeadline(scan) {
  return {
    ...scan,
    deadline: Date.now() + Math.max(0, Number(scan.remaining_seconds || 0)) * 1000,
  };
}

function remainingSeconds(scan, now) {
  return Math.max(0, Math.ceil((scan.deadline - now) / 1000));
}

export default function Intercept() {
  const navigate = useNavigate();
  const [scans, setScans] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [imageUrl, setImageUrl] = useState('');
  const [now, setNow] = useState(Date.now());
  const [connection, setConnection] = useState('connecting');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const controllerRef = useRef(null);

  const selectedScan = useMemo(
    () => scans.find(scan => scan.id === selectedId) || null,
    [scans, selectedId],
  );

  useEffect(() => {
    const ticker = window.setInterval(() => setNow(Date.now()), 250);
    return () => window.clearInterval(ticker);
  }, []);

  useEffect(() => {
    let stopped = false;
    let retryTimer;

    function receiveEvent(event, data) {
      setConnection('live');
      setError('');
      if (event === 'snapshot') {
        setScans(data.scans.map(withDeadline));
        return;
      }
      if (event === 'scan_added') {
        const scan = withDeadline(data);
        setScans(current => [scan, ...current.filter(item => item.id !== scan.id)]);
        return;
      }
      if (event === 'scan_removed' || event === 'scan_decided' || event === 'scan_skipped') {
        setScans(current => current.filter(item => item.id !== data.id));
        setSelectedId(current => current === data.id ? null : current);
        return;
      }
      if (event === 'refresh') {
        controllerRef.current?.abort();
      }
    }

    async function connect() {
      while (!stopped) {
        const controller = new AbortController();
        controllerRef.current = controller;
        setConnection('connecting');
        try {
          await api.adminInterceptEvents(receiveEvent, controller.signal);
          if (!stopped) throw new Error('Live connection closed');
        } catch (err) {
          if (stopped) return;
          if (err.name !== 'AbortError') setError(err.message);
        }
        if (!stopped) {
          setConnection('reconnecting');
          await new Promise(resolve => {
            retryTimer = window.setTimeout(resolve, 900);
          });
        }
      }
    }

    connect();
    return () => {
      stopped = true;
      controllerRef.current?.abort();
      window.clearTimeout(retryTimer);
    };
  }, []);

  useEffect(() => {
    if (!selectedScan) {
      setImageUrl('');
      return undefined;
    }
    let active = true;
    let objectUrl = '';
    api.adminInterceptImage(selectedScan.id)
      .then(url => {
        objectUrl = url;
        if (active) setImageUrl(url);
        else URL.revokeObjectURL(url);
      })
      .catch(err => {
        if (active) setError(err.message);
      });
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      setImageUrl('');
    };
  }, [selectedScan?.id]);

  const liveScans = scans.filter(scan => remainingSeconds(scan, now) > 0);

  async function chooseCategory(category) {
    if (!selectedScan || busy) return;
    setBusy(true);
    setError('');
    try {
      await api.adminInterceptDecision(selectedScan.id, category);
      setScans(current => current.filter(scan => scan.id !== selectedScan.id));
      setSelectedId(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function skipScan() {
    if (!selectedScan || busy) return;
    setBusy(true);
    setError('');
    try {
      await api.adminInterceptSkip(selectedScan.id);
      setScans(current => current.filter(scan => scan.id !== selectedScan.id));
      setSelectedId(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main style={styles.page}>
      <style>{'@media (max-width: 760px) { .intercept-content { grid-template-columns: minmax(0, 1fr) !important; } }'}</style>
      <header style={styles.header}>
        <div>
          <div style={styles.eyebrow}><ShieldAlert size={14} /> ADMIN CLASSIFICATION GATE</div>
          <h1 style={styles.title}>Live Intercept</h1>
          <p style={styles.subtitle}>Select a classification within 30 seconds. Unclaimed scans continue automatically.</p>
        </div>
        <div style={styles.headerActions}>
          <div style={styles.connection}>
            <Radio size={15} color={connection === 'connecting' ? '#fbbf24' : '#00ff66'} />
            {connection === 'connecting' ? 'CONNECTING' : connection === 'reconnecting' ? 'RECONNECTING' : 'LIVE'}
          </div>
          <button type="button" style={styles.exit} onClick={() => navigate('/scan')}>
            <ArrowLeft size={15} /> Exit
          </button>
        </div>
      </header>

      {error && (
        <div role="alert" style={styles.error}>
          <span>{error}</span>
          <button type="button" style={styles.iconButton} onClick={() => setError('')} aria-label="Dismiss error">
            <X size={16} />
          </button>
        </div>
      )}

      <section className="intercept-content" style={styles.content}>
        <div style={styles.queueColumn}>
          <div style={styles.sectionHeading}>
            <span>WAITING SCANS</span>
            <span style={styles.count}>{liveScans.length}</span>
          </div>
          {liveScans.length === 0 ? (
            <div style={styles.empty}>
              <Radio size={24} color="#3f6e4a" />
              <strong>No scans waiting</strong>
              <span>New uploads will appear here immediately.</span>
            </div>
          ) : liveScans.map(scan => {
            const seconds = remainingSeconds(scan, now);
            const isSelected = scan.id === selectedId;
            return (
              <button
                type="button"
                key={scan.id}
                onClick={() => setSelectedId(scan.id)}
                style={{ ...styles.card, ...(isSelected ? styles.selectedCard : {}) }}
              >
                <div style={styles.cardTop}>
                  <strong style={styles.username}>{scan.username}</strong>
                  <span style={{ ...styles.timer, color: seconds <= 5 ? '#ff6677' : '#00ff66' }}>
                    {seconds}s
                  </span>
                </div>
                <span style={styles.filename}>{scan.filename}</span>
                <span style={styles.cardMeta}>{scan.email}{scan.document_type ? ` · ${scan.document_type}` : ''}</span>
                <div style={styles.progressTrack}>
                  <div style={{ ...styles.progress, width: `${Math.min(100, (seconds / 15) * 100)}%` }} />
                </div>
              </button>
            );
          })}
        </div>

        <div style={styles.detailColumn}>
          {!selectedScan ? (
            <div style={styles.detailEmpty}>Select a waiting scan to review and classify it.</div>
          ) : (
            <section style={styles.detailPanel}>
              <div style={styles.detailHeading}>
                <div>
                  <div style={styles.eyebrow}>CLASSIFYING FOR {selectedScan.username}</div>
                  <div style={styles.detailFilename}>{selectedScan.filename}</div>
                  <div style={styles.cardMeta}>{selectedScan.width} × {selectedScan.height}</div>
                </div>
                <button type="button" style={styles.iconButton} onClick={() => setSelectedId(null)} aria-label="Close scan">
                  <X size={18} />
                </button>
              </div>
              {imageUrl ? (
                <div style={styles.imageFrame}><img src={imageUrl} alt="Pending user scan" style={styles.image} /></div>
              ) : (
                <div style={styles.imageLoading}>Loading secure preview...</div>
              )}
              <div style={styles.optionHeading}>Choose the classification</div>
              <div style={styles.options}>
                {CLASSIFICATIONS.map(item => (
                  <button
                    type="button"
                    key={item.code}
                    disabled={busy || remainingSeconds(selectedScan, now) <= 0}
                    onClick={() => chooseCategory(item.code)}
                    style={{ ...styles.option, borderColor: `${item.color}77`, color: item.color }}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
              <button
                type="button"
                disabled={busy || remainingSeconds(selectedScan, now) <= 0}
                onClick={skipScan}
                style={styles.skip}
              >
                Skip and let the system classify
              </button>
              <div style={styles.note}>Gemini will explain the selected category. The selected code is enforced in the final result.</div>
            </section>
          )}
        </div>
      </section>
    </main>
  );
}

const styles = {
  page: {
    minHeight: '100vh',
    boxSizing: 'border-box',
    padding: 'clamp(18px, 4vw, 42px)',
    background: '#07100a',
    color: '#e5f5e9',
    fontFamily: 'Inter, system-ui, sans-serif',
  },
  header: {
    display: 'flex',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 20,
    borderBottom: '1px solid #183322',
    paddingBottom: 22,
    marginBottom: 26,
  },
  eyebrow: {
    display: 'flex',
    alignItems: 'center',
    gap: 7,
    color: '#00ff66',
    fontFamily: 'monospace',
    fontSize: 11,
    letterSpacing: 2,
  },
  title: { margin: '9px 0 5px', fontSize: 'clamp(26px, 4vw, 38px)', letterSpacing: 1 },
  subtitle: { margin: 0, color: '#89a390', fontSize: 13 },
  headerActions: { display: 'flex', alignItems: 'center', gap: 18 },
  connection: {
    display: 'flex',
    alignItems: 'center',
    gap: 7,
    color: '#a7c4ad',
    fontFamily: 'monospace',
    fontSize: 11,
    letterSpacing: 1,
  },
  exit: {
    display: 'flex',
    alignItems: 'center',
    gap: 7,
    padding: '9px 12px',
    color: '#d4e8d8',
    border: '1px solid #25432e',
    background: '#0c1a10',
    borderRadius: 4,
    cursor: 'pointer',
  },
  content: { display: 'grid', gridTemplateColumns: 'minmax(260px, 0.8fr) minmax(0, 1.5fr)', gap: 22 },
  queueColumn: { minWidth: 0 },
  sectionHeading: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    marginBottom: 12,
    color: '#90ae98',
    fontFamily: 'monospace',
    fontSize: 11,
    letterSpacing: 1.5,
  },
  count: { color: '#00ff66', fontWeight: 700 },
  empty: {
    minHeight: 180,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 11,
    color: '#78927e',
    border: '1px dashed #24432d',
    borderRadius: 6,
    fontSize: 13,
  },
  card: {
    width: '100%',
    display: 'flex',
    flexDirection: 'column',
    gap: 7,
    padding: 14,
    marginBottom: 9,
    color: '#dcebe0',
    textAlign: 'left',
    border: '1px solid #1b3825',
    borderRadius: 5,
    background: '#0b170e',
    cursor: 'pointer',
  },
  selectedCard: { borderColor: '#00ff66', boxShadow: '0 0 0 1px #00ff6644' },
  cardTop: { display: 'flex', justifyContent: 'space-between', gap: 10 },
  username: { fontSize: 14 },
  timer: { fontFamily: 'monospace', fontSize: 14, fontWeight: 700 },
  filename: { overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: 13 },
  cardMeta: { color: '#78927e', fontSize: 11, overflowWrap: 'anywhere' },
  progressTrack: { height: 3, background: '#1c2e21', marginTop: 3 },
  progress: { height: '100%', background: '#00ff66', transition: 'width 250ms linear' },
  detailColumn: { minWidth: 0 },
  detailEmpty: {
    minHeight: 280,
    display: 'grid',
    placeItems: 'center',
    color: '#78927e',
    border: '1px dashed #24432d',
    borderRadius: 6,
    fontSize: 13,
  },
  detailPanel: { border: '1px solid #1b3825', borderRadius: 6, background: '#0b170e', padding: 18 },
  detailHeading: { display: 'flex', justifyContent: 'space-between', gap: 12, marginBottom: 15 },
  detailFilename: { margin: '7px 0 4px', fontWeight: 700, overflowWrap: 'anywhere' },
  iconButton: {
    alignSelf: 'flex-start',
    padding: 6,
    color: '#9eb9a4',
    background: 'transparent',
    border: '1px solid #25432e',
    borderRadius: 4,
    cursor: 'pointer',
  },
  imageFrame: {
    maxHeight: 310,
    display: 'grid',
    placeItems: 'center',
    overflow: 'hidden',
    background: '#050906',
    border: '1px solid #183322',
    borderRadius: 4,
  },
  image: { maxWidth: '100%', maxHeight: 310, objectFit: 'contain' },
  imageLoading: { height: 140, display: 'grid', placeItems: 'center', color: '#78927e', fontSize: 12 },
  optionHeading: { margin: '18px 0 10px', fontSize: 13, fontWeight: 700 },
  options: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 7 },
  option: {
    minHeight: 39,
    padding: '8px 10px',
    textAlign: 'left',
    background: '#0e1d12',
    border: '1px solid',
    borderRadius: 4,
    fontSize: 12,
    cursor: 'pointer',
  },
  skip: {
    width: '100%',
    minHeight: 40,
    marginTop: 10,
    padding: '9px 12px',
    color: '#d4e8d8',
    background: '#152319',
    border: '1px solid #45634c',
    borderRadius: 4,
    fontSize: 12,
    cursor: 'pointer',
  },
  note: { marginTop: 12, color: '#78927e', fontSize: 11, lineHeight: 1.5 },
  error: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 12,
    padding: '10px 12px',
    marginBottom: 18,
    color: '#ffc4c9',
    background: '#351116',
    border: '1px solid #6d2832',
    borderRadius: 4,
    fontSize: 13,
  },
};
