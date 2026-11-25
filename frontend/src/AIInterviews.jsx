import React, { useEffect, useRef, useState } from 'react';
import { AlertCircle, Bot, CheckCircle2, Copy, Mic, Plus, RefreshCw, Volume2 } from 'lucide-react';
import './ai-interviews.css';
import './ai-report.css';

export function AIInterviews({ request, candidates, jobs }) {
  const [sessions, setSessions] = useState([]);
  const [candidateId, setCandidateId] = useState('');
  const [jobId, setJobId] = useState('');
  const [shareUrl, setShareUrl] = useState('');
  const [report, setReport] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  async function loadSessions() {
    try { setSessions(await request('/ai-interviews')); }
    catch (e) { setError(e.message); }
  }
  useEffect(() => { loadSessions(); }, []);

  async function createInterview(e) {
    e.preventDefault(); setBusy(true); setError(''); setNotice('');
    try {
      const session = await request('/ai-interviews', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ candidate_id: Number(candidateId), job_id: Number(jobId) }),
      });
      setShareUrl(`${window.location.origin}/interview#${session.share_token}`);
      setCandidateId('');
      setJobId('');
      setNotice('Interview created. Copy the private candidate link below.');
      await loadSessions();
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  async function copyInvite(id) {
    setError(''); setNotice('');
    try {
      const result = await request(`/ai-interviews/${id}/invite`, { method: 'POST' });
      setShareUrl(`${window.location.origin}/interview#${result.share_token}`);
      setNotice('A new private interview link is ready. The previous link has been revoked.');
    } catch (e) { setError(e.message); }
  }

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(shareUrl);
      setNotice('Candidate link copied to clipboard.');
    } catch {
      setError('Could not access the clipboard. Select and copy the interview link manually.');
    }
  }

  async function openReport(id) {
    setError('');
    try { setReport(await request(`/ai-interviews/${id}/report`)); }
    catch (e) { setError(e.message); }
  }

  return <section className="panel ai-interviews">
    <div className="panel-head">
      <div><h2>AI-assisted interviews</h2><p>Role-specific questions, consent-based text or voice transcription, and recruiter-reviewed evidence.</p></div>
      <button className="text-btn" onClick={loadSessions}><RefreshCw size={14}/> Refresh</button>
    </div>
    {error && <div className="alert" role="alert"><AlertCircle size={16}/>{error}</div>}
    {notice && <div className="toast"><CheckCircle2 size={16}/>{notice}</div>}

    <form className="form ai-create-form" onSubmit={createInterview}>
      <h3><Plus size={16}/> Create an interview</h3>
      <div className="form-row">
        <label>Candidate<select required value={candidateId} onChange={e => setCandidateId(e.target.value)}>
          <option value="">Select candidate</option>{candidates.map(c => <option key={c.id} value={c.id}>{c.full_name}</option>)}
        </select></label>
        <label>Job<select required value={jobId} onChange={e => setJobId(e.target.value)}>
          <option value="">Select job</option>{jobs.map(j => <option key={j.id} value={j.id}>{j.title}</option>)}
        </select></label>
      </div>
      <button className="primary-btn" disabled={busy || !candidates.length || !jobs.length}><Bot size={15}/>{busy ? 'Creating…' : 'Create interview link'}</button>
      {(!candidates.length || !jobs.length) && <small>Add a candidate and a job before creating an interview.</small>}
    </form>

    {shareUrl && <div className="ai-invite-link"><b>Private candidate link</b><div><input readOnly aria-label="Candidate interview link" value={shareUrl}/><button className="primary-btn" onClick={copyLink}><Copy size={14}/> Copy link</button></div><small>Share only with the selected candidate. The one-time token is not shown again.</small></div>}

    <div className="ai-session-list">
      <h3>Interview sessions</h3>
      {!sessions.length ? <p className="muted">No AI interviews yet.</p> : sessions.map(s => <article className="ai-session-card" key={s.id}>
        <div><b>{s.candidate_name}</b><small>{s.job_title} · {s.candidate_email || 'No email on file'}</small><small>{s.progress}/{s.question_count} questions · {s.status}</small></div>
        <div className="ai-session-actions">
          {s.status === 'Completed' && <button className="text-btn" onClick={() => openReport(s.id)}>Review report</button>}
          {s.status === 'Invited' && <button className="text-btn" onClick={() => copyInvite(s.id)}><Copy size={14}/> New link</button>}
        </div>
      </article>)}
    </div>

    {report && <div className="ai-report">
      <div className="panel-head"><div><h3>Interview evidence report</h3><p>{report.candidate_name} · {report.job_title} · {report.modality} · consent recorded {report.consented_at ? new Date(report.consented_at).toLocaleString() : ''}</p></div><button className="text-btn" onClick={() => setReport(null)}>Close</button></div>
      <div className="match-disclaimer"><AlertCircle size={16}/>{report.report.assessment} {report.report.method}</div>
      {report.report.coverage_score !== null && <p className="ai-coverage">Role-concept coverage: <b>{report.report.coverage_score}%</b> <small>(descriptive rubric only, not a candidate ranking)</small></p>}
      {report.report.coding_review_required && <p className="muted">Coding responses and sample tests were saved, not executed. Review code manually before drawing conclusions.</p>}
      <div className="ai-report-highlights"><article><h4>Observed strengths</h4>{report.report.strengths.length ? report.report.strengths.map((item, index) => <p key={index}><b>{item.covered_concepts.join(', ')}</b><br/>{item.evidence}</p>) : <p>No expected role concepts were detected by the local rubric.</p>}</article><article><h4>Areas to explore</h4>{report.report.improvement_areas.length ? report.report.improvement_areas.map((item, index) => <p key={index}><b>{item.focus.join(', ') || 'Ask for additional role-specific detail'}</b><br/>{item.evidence}</p>) : <p>No missing expected concepts were flagged by the local rubric.</p>}</article></div>
      <div className="ai-evaluations">{report.report.evaluations.map((item, index) => <article className="ai-evaluation" key={`${index}-${item.type}`}>
        <b>{index + 1}. {item.question}</b><small>{item.type}{item.skill ? ` · ${item.skill}` : ''}{item.score !== null ? ` · concept coverage ${item.score}%` : ' · manual review required'}</small>
        <p>{item.feedback}</p><blockquote>{item.evidence}</blockquote>
        {item.expected_concepts?.length > 0 && <small>Role concepts: {item.expected_concepts.join(', ')}</small>}
      </article>)}</div>
      <h3>Saved transcript</h3>
      {report.transcript.map((turn, index) => <article className="ai-transcript-turn" key={index}><b>{turn.question}</b><p>{turn.answer}</p>{turn.code && <pre>{turn.language}: {turn.code}</pre>}</article>)}
    </div>}
    <p className="ai-footnote">The interview generator and report use a transparent local rubric, not a third-party language model. Reports are decision support only; recruiters make all hiring decisions.</p>
  </section>;
}

export function CandidateInterviewRoom() {
  const token = window.location.hash.slice(1);
  const api = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';
  const [session, setSession] = useState(null);
  const [consent, setConsent] = useState(false);
  const [modality, setModality] = useState('voice');
  const [answer, setAnswer] = useState('');
  const [code, setCode] = useState('');
  const [language, setLanguage] = useState('javascript');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [voiceMessage, setVoiceMessage] = useState('');
  const recognition = useRef(null);

  async function publicRequest(path, body) {
    const response = await fetch(`${api}${path}`, {
      method: body ? 'POST' : 'GET',
      headers: { 'X-Interview-Token': token, ...(body ? { 'Content-Type': 'application/json' } : {}) },
      ...(body ? { body: JSON.stringify(body) } : {}),
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.detail || `Request failed (${response.status})`);
    return result;
  }

  async function loadSession() {
    if (!token) { setError('This interview link is missing its access token. Ask the recruiter for a new link.'); return; }
    try { setSession(await publicRequest('/public/ai-interviews/session')); }
    catch (e) { setError(e.message); }
  }
  useEffect(() => { loadSession(); }, []);
  useEffect(() => () => { recognition.current?.abort(); window.speechSynthesis?.cancel(); }, []);

  async function beginInterview() {
    setBusy(true); setError('');
    try {
      const result = await publicRequest('/public/ai-interviews/consent', { consent: true, modality });
      setSession(current => ({ ...current, consented: true, status: 'In Progress', question: result.question, progress: result.progress }));
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  async function submitAnswer(e) {
    e.preventDefault(); setBusy(true); setError('');
    try {
      const result = await publicRequest('/public/ai-interviews/answer', { answer, code, language });
      setAnswer(''); setCode('');
      setSession(current => ({ ...current, status: result.status, progress: result.progress, question: result.question }));
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  function startVoiceInput() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) { setVoiceMessage('Voice recognition is not available in this browser. You can type your answer instead.'); return; }
    const instance = new SpeechRecognition();
    recognition.current = instance;
    instance.lang = navigator.language || 'en-US';
    instance.interimResults = true;
    instance.onresult = event => {
      const text = Array.from(event.results).map(result => result[0].transcript).join('');
      setAnswer(text);
    };
    instance.onerror = event => setVoiceMessage(`Microphone transcription failed: ${event.error}. You can type your answer instead.`);
    instance.onend = () => { if (!voiceMessage) setVoiceMessage('Transcription stopped. Review or edit the text before submitting.'); };
    setVoiceMessage('Listening… browser speech recognition may process audio under your browser provider’s policies.');
    try { instance.start(); }
    catch { setVoiceMessage('Could not start microphone recognition. Check permission or type your answer instead.'); }
  }

  function speakQuestion() {
    if (!session?.question || !window.speechSynthesis) { setVoiceMessage('Speech playback is not available in this browser.'); return; }
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(new SpeechSynthesisUtterance(session.question.prompt));
  }

  if (!session && !error) return <div className="candidate-interview-shell"><section className="candidate-interview-card"><Bot/><h1>Loading interview…</h1></section></div>;
  return <div className="candidate-interview-shell"><section className="candidate-interview-card">
    <div className="candidate-interview-brand"><div className="brand-icon"><Bot size={20}/></div><b>HireSwift 360 · Candidate interview</b></div>
    {error && !session && <div className="alert" role="alert">{error}</div>}
    {session && <>
      <p className="muted">{session.company_name} · {session.job_title}</p>
      <h1>Hello, {session.candidate_name}</h1>
      {session.status === 'Completed' ? <div className="ai-complete"><CheckCircle2/><h2>Thank you. Your interview is complete.</h2><p>Your answers have been saved for the hiring team to review.</p></div>
        : !session.consented ? <>
          <h2>Before we begin</h2><p>{session.disclosure}</p>
          <label className="ai-mode-label">Interview format<select value={modality} onChange={e => setModality(e.target.value)}><option value="voice">Voice with text transcript</option><option value="text">Text only</option></select></label>
          <label className="ai-consent"><input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)}/><span>I have read the disclosure and consent to saving my interview answers and transcript for the hiring team.</span></label>
          <button className="primary-btn" disabled={!consent || busy} onClick={beginInterview}>{busy ? 'Starting…' : 'Consent and start interview'}</button>
        </> : session.question ? <>
          <div className="ai-progress">Question {session.progress + 1} of {session.question_count}</div>
          <article className="ai-current-question"><small>{session.question.type}{session.question.is_followup ? ' · follow-up' : ''}{session.question.skill ? ` · ${session.question.skill}` : ''}</small><h2>{session.question.prompt}</h2></article>
          <div className="ai-voice-controls">
            <button type="button" className="text-btn" onClick={speakQuestion}><Volume2 size={15}/> Read question aloud</button>
            {modality === 'voice' && session.question.type !== 'coding' && <button type="button" className="text-btn" onClick={startVoiceInput}><Mic size={15}/> Start microphone transcription</button>}
          </div>
          {voiceMessage && <small className="muted">{voiceMessage}</small>}
          <form className="form" onSubmit={submitAnswer}>
            {session.question.type === 'coding' && <>
              <p>Use the editor to write your solution. Sample tests are for discussion and are not executed in this interview room.</p>
              <div className="ai-test-cases"><b>Sample test cases</b>{session.question.test_cases.map((test, index) => <code key={index}>Input: {test.input} → Expected: {test.expected_output}</code>)}</div>
              <label>Language<select value={language} onChange={e => setLanguage(e.target.value)}>{['javascript','python','typescript','java','c++','sql'].map(item => <option key={item}>{item}</option>)}</select></label>
              <label>Code submission<textarea className="ai-code-editor" required rows="12" value={code} onChange={e => setCode(e.target.value)} spellCheck="false" placeholder="// Write your solution here"/></label>
              <label>Explain your approach<textarea rows="3" value={answer} onChange={e => setAnswer(e.target.value)} placeholder="Describe your approach and trade-offs"/></label>
            </>}
            {session.question.type !== 'coding' && <label>Your answer<textarea required rows="7" maxLength="12000" value={answer} onChange={e => setAnswer(e.target.value)} placeholder="Type your response, or use microphone transcription above."/></label>}
            {error && <div className="alert" role="alert">{error}</div>}
            <button className="primary-btn" disabled={busy}>{busy ? 'Saving…' : 'Submit answer'}</button>
          </form>
        </> : <div className="ai-complete"><CheckCircle2/><h2>Thank you. Your interview is complete.</h2><p>Your answers have been saved for the hiring team to review.</p></div>}
    </>}
  </section></div>;
}
