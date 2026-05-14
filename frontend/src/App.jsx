import { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import './styles.css';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// ─── Logo ────────────────────────────────────────────────────────────────────

function Logo() {
  const letters = ['a','r','i','z','e'];
  // Each letter rises higher: translateY goes from 0 → -14px across the 5 letters
  // Font size shrinks slightly to give a vanishing-into-sky feeling
  return (
    <div style={{ display: 'inline-flex', alignItems: 'flex-end', lineHeight: 1, marginBottom: 32, userSelect: 'none' }}>
      {/* Sigma */}
      <span style={{
        fontSize: 50,
        fontWeight: 700,
        color: 'var(--accent)',
        letterSpacing: '-0.02em',
        lineHeight: 1,
        filter: 'drop-shadow(0 0 12px var(--accent-glow))',
      }}>Σ</span>

      {/* arize — each letter climbs */}
      <span style={{ display: 'inline-flex', alignItems: 'flex-end', marginLeft: 2 }}>
        {letters.map((ch, i) => {
          const rise    = -(i * 3.5);
          const size    = 52 - i * 2.2;
          const opacity = 1 - i * 0.055;
          // float: each letter bobs between its base rise and rise-4px
          const kf = `@keyframes lf${i}{from{transform:translateY(${rise}px)}to{transform:translateY(${rise - 4}px)}}`;
          return (
            <span key={ch}>
              <style>{kf}</style>
              <span style={{
                fontSize: size,
                fontWeight: 700,
                color: `rgba(245,245,250,${opacity})`,
                letterSpacing: '-0.02em',
                lineHeight: 1,
                display: 'inline-block',
                animation: `lf${i} 2.8s ease-in-out ${i * 0.12}s infinite alternate`,
              }}>{ch}</span>
            </span>
          );
        })}
      </span>
    </div>
  );
}

// ─── Helpers ────────────────────────────────────────────────────────────────

function useFadeUp(ref) {
  useEffect(() => {
    if (!ref.current) return;
    const el = ref.current;
    const obs = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) el.classList.add('visible'); },
      { threshold: 0.1 }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [ref]);
}

function FadeUp({ children, delay = 0 }) {
  const ref = useRef(null);
  useFadeUp(ref);
  return (
    <div ref={ref} className="fade-up" style={{ transitionDelay: `${delay}ms` }}>
      {children}
    </div>
  );
}

// ─── Accordion ──────────────────────────────────────────────────────────────

function Accordion({ title, icon, children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="accordion">
      <div className="accordion-header" onClick={() => setOpen(o => !o)}>
        <span className="accordion-title">{icon && <span>{icon}</span>}{title}</span>
        <span className={`accordion-chevron ${open ? 'open' : ''}`}>▼</span>
      </div>
      <div className={`accordion-body ${open ? 'open' : ''}`}>
        <div className="accordion-content">{children}</div>
      </div>
    </div>
  );
}

// ─── Flashcard ───────────────────────────────────────────────────────────────

function Flashcard({ num, title, insight, description }) {
  const [flipped, setFlipped] = useState(false);
  return (
    <div
      className={`flashcard-outer ${flipped ? 'flipped' : ''}`}
      onClick={() => setFlipped(f => !f)}
    >
      <div className="flashcard-inner">
        <div className="flashcard-face flashcard-front">
          <div>
            <div className="flashcard-num">Moment {num}</div>
            <div className="flashcard-title">{title}</div>
          </div>
          <div className="flashcard-hint">
            <span>↩</span> flip for insight
          </div>
        </div>
        <div className="flashcard-face flashcard-back">
          <div className="flashcard-back-label">Key Insight</div>
          <div className="flashcard-insight">{insight || description}</div>
        </div>
      </div>
    </div>
  );
}

// ─── Pipeline steps ──────────────────────────────────────────────────────────

const STEPS = [
  { id: 'audio',     label: 'Extracting audio',         icon: '🎵' },
  { id: 'transcribe',label: 'Transcribing speech',       icon: '📝' },
  { id: 'summarise', label: 'Summarising & scripting',   icon: '🧠' },
  { id: 'slides',    label: 'Building reference slides', icon: '📊' },
  { id: 'video',     label: 'Generating summary video',  icon: '🎬' },
];

// ─── Main App ────────────────────────────────────────────────────────────────

export default function App() {
  const [youtubeUrl, setYoutubeUrl]   = useState('');
  const [file, setFile]               = useState(null);
  const [subject, setSubject]         = useState('');
  const [loading, setLoading]         = useState(false);
  const [activeStep, setActiveStep]   = useState(-1);
  const [doneSteps, setDoneSteps]     = useState([]);
  const [error, setError]             = useState('');
  const [result, setResult]           = useState(null);
  const [scheduleEmail, setScheduleEmail] = useState('');
  const [scheduling, setScheduling]   = useState(false);
  const [scheduleStatus, setScheduleStatus] = useState('');
  const btnRef = useRef(null);

  // Simulate pipeline step progression while waiting
  useEffect(() => {
    if (!loading) return;
    setDoneSteps([]);
    setActiveStep(0);
    const delays = [0, 18000, 40000, 75000, 130000];
    const timers = delays.map((d, i) =>
      setTimeout(() => {
        setActiveStep(i);
        if (i > 0) setDoneSteps(prev => [...prev, i - 1]);
      }, d)
    );
    return () => timers.forEach(clearTimeout);
  }, [loading]);

  const addRipple = (e) => {
    const btn = btnRef.current;
    if (!btn) return;
    const rect = btn.getBoundingClientRect();
    const span = document.createElement('span');
    const size = Math.max(rect.width, rect.height);
    span.className = 'ripple';
    span.style.cssText = `width:${size}px;height:${size}px;left:${e.clientX - rect.left - size/2}px;top:${e.clientY - rect.top - size/2}px`;
    btn.appendChild(span);
    setTimeout(() => span.remove(), 600);
  };

  const scheduleAndOrganize = async () => {
    if (!scheduleEmail || !result) return;
    setScheduling(true);
    setScheduleStatus('');
    try {
      await axios.post(`${API}/api/organize`, {
        subject: subject || result.seo_metadata?.title || 'Lecture',
        topic: result.seo_metadata?.title || 'Lecture',
        email: scheduleEmail,
        summary: result.summaries?.executive,
        key_points: result.summaries?.key_points,
        files: {
          pdf: result.pdf_url,
          slides: result.slides_url,
          transcript: result.transcript_txt_url,
          summary_video: result.summary_video_url,
        },
        run_id: result.run_id,
      });
      setScheduleStatus('done');
    } catch (err) {
      setScheduleStatus('error');
    } finally {
      setScheduling(false);
    }
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!youtubeUrl && !file) return;
    setResult(null);
    setError('');
    setLoading(true);

    const formData = new FormData();
    if (youtubeUrl) formData.append('youtube_url', youtubeUrl);
    if (file) formData.append('file', file);
    formData.append('voice_style', 'friendly');
    if (subject) formData.append('subject', subject);

    try {
      const response = await axios.post(`${API}/api/process`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 25 * 60 * 1000,
      });
      setDoneSteps([0,1,2,3,4]);
      setActiveStep(-1);
      setResult(response.data);
    } catch (err) {
      setError(err?.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  };

  const stepState = (idx) => {
    if (doneSteps.includes(idx)) return 'done';
    if (activeStep === idx) return 'active';
    return '';
  };

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="page">

      {/* ── Hero / input ────────────────────────────────────────────────── */}
      <section className="hero">
        <Logo />
        <div className="hero-eyebrow">AI Video Summarizing Intelligence</div>
        <h1 className="hero-title">Every lecture,<br /><span>fully captured</span></h1>
        <p className="hero-subtitle">
          Paste a YouTube link or upload a video. Get a narrated summary, key moment clips, reference slides, and a full transcript.
        </p>

        <form onSubmit={(e) => { addRipple(e.nativeEvent); submit(e); }} style={{ width: '100%', maxWidth: 600 }}>
          <div className="input-card">
            <div className="url-input-wrap" style={{ marginBottom: 16 }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ position:'absolute', left:14, top:'50%', transform:'translateY(-50%)', opacity:0.4, pointerEvents:'none' }}>
                <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>
              </svg>
              <input
                className="url-input"
                value={subject}
                onChange={e => setSubject(e.target.value)}
                placeholder="Subject name (e.g. Machine Learning, Physics 101)"
                disabled={loading}
              />
            </div>
            <div className="url-input-wrap">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
                <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
              </svg>
              <input
                className="url-input"
                value={youtubeUrl}
                onChange={e => setYoutubeUrl(e.target.value)}
                placeholder="https://www.youtube.com/watch?v=..."
                disabled={loading}
              />
            </div>

            <div className="divider-row">or upload a file</div>

            <label className="file-label">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                <polyline points="17 8 12 3 7 8"/>
                <line x1="12" y1="3" x2="12" y2="15"/>
              </svg>
              {file ? file.name : 'Choose video file'}
              <input type="file" accept="video/*" onChange={e => setFile(e.target.files?.[0] || null)} disabled={loading} />
            </label>

            <button ref={btnRef} type="submit" className="submit-btn" disabled={loading || (!youtubeUrl && !file)}>
              {loading ? 'Processing…' : 'Process Video'}
            </button>
          </div>
        </form>

        {/* Pipeline progress */}
        {loading && (
          <div className="pipeline">
            {STEPS.map((step, i) => (
              <div key={step.id} className={`pipeline-step ${stepState(i)}`}>
                <div className="step-icon">
                  {doneSteps.includes(i) ? '✓' : step.icon}
                </div>
                {step.label}
                {activeStep === i && <span style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--accent)' }}>in progress…</span>}
              </div>
            ))}
          </div>
        )}

        {error && (
          <div style={{ marginTop: 20, color: 'var(--red)', fontSize: 13, maxWidth: 600, textAlign: 'center' }}>
            {error}
          </div>
        )}
      </section>

      {/* ── Results ─────────────────────────────────────────────────────── */}
      {result && (
        <div className="results-section">

          {/* Summary accordions */}
          <FadeUp delay={60}>
            <div className="section-heading">Summary</div>
            <Accordion title="Executive Summary" defaultOpen>
              <p style={{ lineHeight: 1.8 }}>{result.summaries?.executive}</p>
            </Accordion>
            <Accordion title="Key Takeaways">
              <ul className="key-points-list">
                {result.summaries?.key_points?.map((pt, i) => (
                  <li key={i} className="key-point-item">{pt}</li>
                ))}
              </ul>
            </Accordion>
            <Accordion title="Full Narration Script">
              <p style={{ lineHeight: 1.9, whiteSpace: 'pre-wrap' }}>{result.summaries?.detailed}</p>
            </Accordion>
          </FadeUp>

          {/* Key Moments — flashcard + clip side by side */}
          {result.publication_ready?.short_form_content?.length > 0 && (
            <>
              <FadeUp delay={100}>
                <div className="section-heading">Key Moments — click card to reveal insight</div>
              </FadeUp>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
                {result.publication_ready.short_form_content.map((clip, i) => (
                  <FadeUp key={i} delay={i * 80}>
                    <div className="moment-row">
                      <Flashcard
                        num={i + 1}
                        title={clip.title}
                        insight={clip.description}
                      />
                      {clip.download_url ? (
                        <div className="moment-video-wrap">
                          <video controls preload="none">
                            <source src={clip.download_url} type="video/mp4" />
                          </video>
                          <div className="moment-video-footer">
                            <span className="clip-overlay-tag">{clip.overlay}</span>
                            <a href={clip.download_url} download className="clip-download">
                              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                                <polyline points="7 10 12 15 17 10"/>
                                <line x1="12" y1="15" x2="12" y2="3"/>
                              </svg>
                              Download
                            </a>
                          </div>
                        </div>
                      ) : (
                        <div className="moment-video-wrap moment-video-placeholder">
                          <span style={{ color: 'var(--muted)', fontSize: 13 }}>No clip available</span>
                        </div>
                      )}
                    </div>
                  </FadeUp>
                ))}
              </div>
            </>
          )}

          {/* Summary video */}
          {result.summary_video_url && (
            <FadeUp delay={160}>
              <div className="section-heading">Narrated Summary Video</div>
              <div className="video-wrap hover-lift" style={{ marginBottom: 16 }}>
                <video controls>
                  <source src={result.summary_video_url} type="video/mp4" />
                </video>
              </div>
              <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                <a href={result.summary_video_url} download className="dl-btn">
                  Download video
                </a>
                {result.summary_narration_url && (
                  <a href={result.summary_narration_url} download className="dl-btn">
                    Download audio
                  </a>
                )}
              </div>
            </FadeUp>
          )}

          {/* SEO + Slides side by side */}
          <FadeUp delay={180}>
            <div className="section-heading">Publishing & Downloads</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              <div className="glass-card hover-lift">
                <div className="card-label">SEO Metadata</div>
                <div className="card-title">{result.seo_metadata?.title}</div>
                <p className="card-body">{result.seo_metadata?.description}</p>
                <div>{result.seo_metadata?.hashtags?.map((h, i) => <span key={i} className="tag">#{h}</span>)}</div>
              </div>
              <div className="glass-card hover-lift" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
                <div>
                  <div className="card-label">Slide Deck</div>
                  <p className="card-body" style={{ marginBottom: 16 }}>
                    Reference deck with concept explanations, formulas, derivations, and key takeaways per slide.
                  </p>
                </div>
                <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                  {result.slides_url && (
                    <a href={result.slides_url} download className="dl-btn">
                      Slides (.pptx)
                    </a>
                  )}
                  {result.pdf_url && (
                    <a href={result.pdf_url} download className="dl-btn">
                      Slides (.pdf)
                    </a>
                  )}
                </div>
              </div>
            </div>
          </FadeUp>

          {/* Transcript */}
          <FadeUp delay={200}>
            <Accordion title="Full Transcript">
              <div className="transcript-box">{result.transcript}</div>
              {result.transcript_txt_url && (
                <a href={result.transcript_txt_url} download className="dl-btn" style={{ marginTop: 14, width: 'fit-content' }}>
                  ↓ Download transcript (.txt)
                </a>
              )}
            </Accordion>
          </FadeUp>

          {/* Schedule & Organize */}
          <FadeUp delay={220}>
            <div className="section-heading" style={{ marginTop: 48 }}>Schedule & Organize</div>
            <div className="glass-card" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <p className="card-body">
                Ara will organize all files into <code style={{ color: 'var(--accent)', fontSize: 12 }}>~/Desktop/Ara/{subject || 'Subject'}/{result.seo_metadata?.title || 'Lecture'}/</code>,
                book a study block in your calendar, and send you a summary email with a 7-day review reminder.
              </p>
              <div className="url-input-wrap" style={{ marginBottom: 0 }}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ position:'absolute', left:14, top:'50%', transform:'translateY(-50%)', opacity:0.4, pointerEvents:'none' }}>
                  <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/>
                </svg>
                <input
                  className="url-input"
                  value={scheduleEmail}
                  onChange={e => setScheduleEmail(e.target.value)}
                  placeholder="Your email address"
                  disabled={scheduling}
                />
              </div>
              <button
                className="submit-btn"
                disabled={scheduling || !scheduleEmail || scheduleStatus === 'done'}
                onClick={scheduleAndOrganize}
                style={{ marginTop: 4 }}
              >
                {scheduling ? 'Organizing…' : scheduleStatus === 'done' ? 'Scheduled!' : scheduleStatus === 'error' ? 'Failed — retry' : 'Schedule & Organize with Ara'}
              </button>
            </div>
          </FadeUp>

        </div>
      )}
    </div>
  );
}
