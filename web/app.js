/* Native, zero-build Cloudflare-compatible UI; all numerical predictions come from the API. */
'use strict';
const BASE = (window.FOOTBALL_API_URL || '').replace(/\/$/, '');
const $ = id => document.getElementById(id);
const clean = x => String(x ?? '').replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = x => Number.isFinite(Number(x)) ? (Number(x)*100).toFixed(1)+'%' : '—';
const pct = x => Math.min(100,Math.max(0,Number(x)*100));
const thaiTime = x => new Date(x).toLocaleString('th-TH',{timeZone:'Asia/Bangkok',dateStyle:'medium',timeStyle:'short'});
const localTomorrow = () => { const d = new Date();d.setDate(d.getDate()+1);return new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Bangkok',year:'numeric',month:'2-digit',day:'2-digit'}).format(d) };
const state = {page:'today',meta:null,fixtures:[],league:'',home:'',away:'',matchDate:localTomorrow(),marketTab:'overview',predict:null,performance:null,oddsResult:null,error:'',loading:false};
async function api(path,options={}) {
  const response=await fetch(BASE+'/api'+path,options);
  let data;try{data=await response.json()}catch{throw Error('เซิร์ฟเวอร์ไม่ส่งข้อมูล JSON')}
  if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'ไม่สามารถอ่านข้อมูลได้');
  return data;
}
const noData = (title,message) => `<div class="empty-state"><div class="empty-icon">◉</div><h3>${clean(title)}</h3><p>${clean(message)}</p></div>`;
const alertBar=(message,kind='info')=>`<div class="alert ${kind}">${clean(message)}</div>`;
const panel=(title,content,extra='')=>`<section class="panel"><div class="panel-header"><h2>${title}</h2>${extra}</div><div class="panel-body">${content}</div></section>`;
const badgeMode=()=>state.meta?.data_mode==='demo_only'?'demo':state.meta?.data_mode==='real_or_mixed'?'real':'empty';
function setPage(page){state.page=page;state.error='';render();if(page==='performance')loadPerformance()}
function headers(){const h={today:'บอลวันนี้',analysis:'วิเคราะห์คู่บอล',performance:'ประสิทธิภาพ AI',settings:'ข้อมูลและการตั้งค่า'};$('page-caption').textContent=h[state.page]||'บอลวันนี้';document.querySelectorAll('[data-page]').forEach(el=>el.classList.toggle('active',el.dataset.page===state.page));}
function modeHeader(){const el=$('modeBadge');if(!state.meta){el.className='pill muted';el.textContent='API ออฟไลน์';return}if(badgeMode()==='demo'){el.className='pill demo';el.textContent='สถิติจำลอง DEMO'}else if(badgeMode()==='real'){el.className='pill';el.textContent='มีสถิตินำเข้า'}else{el.className='pill muted';el.textContent='ยังไม่มีสถิติสำหรับวิเคราะห์'}$('sidebar-status').textContent=state.meta?'ระบบ API พร้อมใช้งาน':'ยังไม่เชื่อมต่อ API';}
function title(t,sub){return `<div class="intro"><div><h1>${t}</h1><p>${sub}</p></div></div>`}
function fixturesArea(){if(!state.fixtures.length)return noData('ยังไม่มีตารางแข่งที่ยืนยันแล้ว','ระบบจะไม่สร้างคู่บอลวันนี้ขึ้นมาเอง ให้นำเข้าไฟล์โปรแกรมแข่งจากแหล่งข้อมูลที่อนุญาต หรือเลือกทีมเพื่อวิเคราะห์คู่สมมติ');return `<div class="fixture-list">${state.fixtures.map(f=>`<div class="fixture-item"><div><strong>${clean(f.home)} <span class="muted">vs</span> ${clean(f.away)}</strong><small>${clean(f.league)} · ${clean(thaiTime(f.kickoff))}</small></div><button class="ghost-button" data-fixture="${clean(f.id)}">วิเคราะห์คู่นี้ →</button></div>`).join('')}</div>`}
function liveScoresPanel(){
  return panel('ผลบอลสดและโปรแกรมแข่ง', `
    <iframe class="live-scores-frame" title="ผลบอลสดจาก Football Mania"
      src="https://football-mania.com/widget?lang=th&amp;theme=light&amp;limit=30&amp;tz=Asia%2FBangkok"
      sandbox="allow-scripts allow-popups allow-popups-to-escape-sandbox" referrerpolicy="no-referrer"></iframe>
    <a class="live-scores-source" href="https://football-mania.com/th/" target="_blank" rel="noopener noreferrer">ดูทุกคู่ที่ Football Mania ↗</a>`);
}
function liveFixtureCard(fixture) {
  const {home, away, league, country, status, minute, extra, home_goals, away_goals, probabilities} = fixture;
  const statusLabels = {
    HT: 'พักครึ่ง', ET: 'ต่อเวลา', BT: 'พักก่อนต่อเวลา', P: 'ดวลจุดโทษ',
    SUSP: 'ระงับการแข่งขัน', INT: 'หยุดชั่วคราว',
  };
  const clock = statusLabels[status] || (minute == null ? 'กำลังแข่ง' : `นาที ${minute}${extra > 0 ? `+${extra}` : ''}`);
  const reds = fixture.red_cards || {};
  const confirmedCards = [[home, reds.home], [away, reds.away]]
    .filter(([, count]) => count > 0).map(([team, count]) => `${team} ใบแดง ${count} ใบ`);
  const score = home_goals == null || away_goals == null ? '–' : `${home_goals}–${away_goals}`;
  let forecast = '<small>ช่วงนี้ไม่มีเปอร์เซ็นต์ผลเวลา 90 นาที</small>';
  if (probabilities) {
    const outcomes = [[home, probabilities.home], ['เสมอ', probabilities.draw], [away, probabilities.away]];
    const highest = Math.max(...outcomes.map(([, probability]) => probability));
    const likely = outcomes.filter(([, probability]) => probability === highest);
    const summary = likely.length === 1 ? `แนวโน้มสูงสุด: ${likely[0][0]}` : 'โอกาสสูงสุดสูสีกัน';
    const basis = fixture.basis === 'team_history' ? 'สกอร์ เวลา และสถิติย้อนหลังของสองทีม' : 'สกอร์และเวลา โดยตั้งอัตราทำประตูเริ่มต้นเท่ากัน';
    forecast = `<div class="forecast-lead"><span>${clean(summary)}</span><strong>${fmt(highest)}</strong></div>
      <small>${clean(basis)}${confirmedCards.length ? ' · ปรับตามใบแดง' : ''}</small><dl class="live-probabilities">${outcomes.map(([label, probability]) => `
      <div class="${probability === highest ? 'leading' : ''}"><dt>${clean(label)}</dt><dd>${fmt(probability)}</dd></div>`).join('')}</dl>`;
  }
  return `<article class="fixture-item live-analysis-card"><div>
    <small>${clean([country, league, clock].filter(Boolean).join(' · '))}</small>
    <strong>${clean(home)} <span class="live-score">${clean(score)}</span> ${clean(away)}</strong>
    ${confirmedCards.length ? `<small>${clean(confirmedCards.join(' · '))}</small>` : ''}
    ${forecast}</div></article>`;
}

async function loadUpcomingAnalysis() {
  const target = $('upcoming-analysis');
  if (!target) return;
  try {
    const data = await api('/upcoming-analysis');
    if (!$('upcoming-analysis')) return;
    const cards = data.fixtures.map(f => {
      const outcomes = f.probabilities && [[f.home, f.probabilities.home], ['เสมอ', f.probabilities.draw], [f.away, f.probabilities.away]];
      const highest = outcomes ? Math.max(...outcomes.map(([, value]) => value)) : null;
      const leaders = outcomes ? outcomes.filter(([, value]) => value === highest) : [];
      const stale = f.last_result && (Date.now() - Date.parse(f.last_result + 'T00:00:00Z')) > 21 * 86400000;
      const forecast = outcomes ? `${stale ? '<p class="alert warning">สถิติย้อนหลังเก่ากว่า 21 วัน ผลประเมินอาจคลาดเคลื่อนมาก</p>' : ''}<div class="forecast-lead"><span>${leaders.length === 1 ? `โอกาสสูงสุด · ${clean(leaders[0][0])}` : 'โอกาสสูงสุดสูสีกัน'}</span><strong>${fmt(highest)}</strong></div>
        <dl class="live-probabilities">${outcomes.map(([name,value]) => `<div class="${value === highest ? 'leading' : ''}"><dt>${clean(name)}</dt><dd>${fmt(value)}</dd></div>`).join('')}</dl>
        <small>ผลย้อนหลังล่าสุด ${clean(f.last_result)} · ใช้ข้อมูล ${f.samples.training_matches} นัด</small>` : '<small>ข้อมูลย้อนหลังของคู่นี้ยังไม่เพียงพอสำหรับคำนวณ</small>';
      return `<article class="fixture-item live-analysis-card"><div><small>${clean(f.league)} · ${clean(f.date)}</small><strong>${clean(f.home)} <span class="muted">vs</span> ${clean(f.away)}</strong>${forecast}</div></article>`;
    });
    const failures = data.failed_leagues.length ? `<p class="alert warning">โหลดบางลีกไม่ได้: ${clean(data.failed_leagues.join(', '))}</p>` : '';
    $('upcoming-analysis').innerHTML = `${failures}<p class="helper">ข้อมูลจาก OpenFootball อัปเดต ${clean(thaiTime(data.updated_at))} · วันแข่งขันอาจเปลี่ยนแปลง · ผลวิเคราะห์ใช้เฉพาะผลย้อนหลัง</p>${cards.length ? `<div class="fixture-list">${cards.join('')}</div>` : noData('ยังไม่มีคู่ในช่วง 14 วัน','ตรวจสอบวันที่แข่งขันจากแหล่งข้อมูลอีกครั้ง')}`;
  } catch {
    if ($('upcoming-analysis')) $('upcoming-analysis').textContent = 'ไม่สามารถโหลดโปรแกรมแข่งได้ในขณะนี้';
  }
}

let liveAnalysisPending = false;
let liveAuditCheckedAt = 0;
async function loadLiveAudit() {
  const target = $('live-audit');
  if (!target) return;
  liveAuditCheckedAt = Date.now();
  try {
    const data = await api('/live-performance', {cache: 'no-store'});
    if (!target.isConnected) return;
    const wins = data.samples.find(sample => sample.sample === 'win_70');
    const summary = wins?.settled ? `ถูก ${wins.correct}/${wins.settled} คู่ที่ยืนยันผลแล้ว · รอผล ${wins.recorded - wins.settled} คู่`
      : `รอผล ${wins?.recorded || 0} คู่ · ยังไม่มีผลที่ยืนยันแล้ว`;
    const rows = data.recent.map(match => {
      const team = match.pick === 'home' ? match.home : match.away;
      const clock = `${match.minute}′${match.extra ? ` +${match.extra}` : ''}`;
      const correct = match.pick === 'home' ? match.final_home > match.final_away : match.final_away > match.final_home;
      const result = match.confirmed_at ? `${match.final_home}–${match.final_away} · ${correct ? 'ทายถูก' : 'ทายผิด'}` : 'รอผล';
      return `<div class="fixture-item"><div><strong>${clean(match.home)} · ${clean(match.away)}</strong>
        <small>${clean(thaiTime(match.observed_at))} · ${clock} · ทาย ${clean(team)} ${fmt(match.pick_p)}</small></div><span>${result}</span></div>`;
    });
    const wasOpen = target.querySelector('details')?.open;
    target.innerHTML = `<p><strong>${summary}</strong></p>
      <p class="helper">นับคำทายทีมชนะครั้งแรกที่ถึง 70% ต่อคู่ในช่วง ${data.window_days} วัน เทียบผลครบ 90 นาทีรวมทดเจ็บจาก Football Mania</p>
      ${rows.length ? `<details ${wasOpen ? 'open' : ''}><summary>ดูคำทายล่าสุด</summary><div class="fixture-list">${rows.join('')}</div></details>` : ''}`;
  } catch {
    if (target.isConnected) target.textContent = 'ยังโหลดผลตรวจคำทายสดไม่ได้';
  }
}

async function loadLiveAnalysis() {
  if (!$('live-analysis') || liveAnalysisPending) return;
  liveAnalysisPending = true;
  try {
    const data = await api('/live-fixtures', {cache: 'no-store'});
    const target = $('live-analysis');
    if (!target) return;
    switch (data.state) {
      case 'ready':
        const source = data.source === 'football_mania'
          ? '<a href="https://football-mania.com/" target="_blank" rel="noopener">Football Mania</a>'
          : 'API-Football';
        const updated = new Date(data.updated_at).toLocaleTimeString('th-TH', {timeZone:'Asia/Bangkok', hour:'2-digit', minute:'2-digit', second:'2-digit'});
        const age = Math.max(0, Math.floor((Date.now() - Date.parse(data.updated_at)) / 1000));
        const stale = age > 60;
        const feedStatus = `<p class="helper">${data.fixtures.length} คู่กำลังแข่ง · ดึงข้อมูลจาก ${source} เมื่อ ${clean(updated)} น. · ${age} วินาทีที่แล้ว</p>
          ${stale ? alertBar('ข้อมูลล่าสุดเกิน 1 นาที ซ่อนเปอร์เซ็นต์จนกว่าจะได้รับข้อมูลใหม่', 'warning') : ''}`;
        if (data.fixtures.length) {
          target.innerHTML = `${feedStatus}
            <div class="fixture-list">${data.fixtures.map(fixture => liveFixtureCard(stale ? {...fixture, probabilities: null} : fixture)).join('')}</div>`;
        } else {
          target.innerHTML = `${feedStatus}<p>ขณะนี้ฟีดไม่มีคู่ที่กำลังแข่ง</p>`;
        }
        break;
      case 'unconfigured':
        target.innerHTML = `<div class="connection-card">
          <div class="connection-heading"><span class="connection-icon" aria-hidden="true">↗</span><div><span class="connection-status">ยังไม่ได้เชื่อมต่อ</span><h3>เปิดใช้งานวิเคราะห์สด</h3><p>เชื่อม API-Football เพื่อแสดงคู่ที่กำลังแข่งและโอกาสชนะในหน้านี้</p></div></div>
          <ol class="connection-steps">
            <li><strong>รับ API key</strong><span>เข้าสู่ระบบหรือสมัครบัญชีที่ API-Football</span></li>
            <li><strong>ใส่คีย์ในไฟล์ตั้งค่า</strong><span>เปิดไฟล์ <code>.env</code> ในโฟลเดอร์โปรเจกต์ แล้วใส่คีย์หลัง <code>API_FOOTBALL_KEY=</code></span></li>
            <li><strong>เริ่มเซิร์ฟเวอร์ใหม่</strong><span>จากนั้นรีเฟรชหน้านี้เพื่อตรวจสอบการเชื่อมต่อ</span></li>
          </ol>
          <div class="connection-actions"><a class="primary-button connection-link" href="https://dashboard.api-football.com/" target="_blank" rel="noopener noreferrer">เปิด API-Football Dashboard ↗</a><span>ข้อมูลสดจะตรวจสอบทุก 15 นาที</span></div>
        </div>`;
        break;
      default:
        target.textContent = 'ฟีดสกอร์สดไม่พร้อมใช้งาน ระบบจะลองใหม่เมื่ออัปเดตรอบถัดไป';
    }
  } catch {
    const target = $('live-analysis');
    if (target) target.textContent = 'เชื่อมต่อระบบวิเคราะห์สดไม่ได้';
  } finally {
    liveAnalysisPending = false;
  }
}

function renderToday(){
  const matchCount = state.meta?.match_count || 0;
  const leagueCount = state.meta?.leagues?.length || 0;
  const demoWarning = badgeMode() === 'demo'
    ? alertBar('สถิติที่ใช้วิเคราะห์เป็นข้อมูลจำลองสำหรับทดสอบระบบ', 'warning')
    : '';
  return title('ฟุตบอลวันนี้', 'ดูสกอร์สด ผลการแข่งขัน และเวลาเริ่มแข่งตามเวลาไทย')
    + panel('วิเคราะห์คู่ที่กำลังแข่ง', `<p class="helper">โอกาสชนะหรือเสมอใน 90 นาทีรวมทดเจ็บ ใช้สกอร์และนาทีแข่ง ร่วมกับใบแดงและสถิติทีมเมื่อมีข้อมูล</p>
      <div id="live-analysis" aria-live="polite">กำลังตรวจคู่ที่กำลังแข่ง…</div>`,
      '<a class="live-scores-source" href="https://www.365scores.com/th/football/live" target="_blank" rel="noopener noreferrer">เปิดรายการสด 365Scores ↗</a>')
    + panel('ตรวจผลคำทายสด 70% ขึ้นไป', `<div id="live-audit">กำลังโหลดผลตรวจคำทาย…</div>`)
    + panel('โปรแกรมแข่งและโอกาสชนะ 14 วัน', `<div id="upcoming-analysis" aria-live="polite">กำลังโหลดโปรแกรมและวิเคราะห์...</div>`)
    + liveScoresPanel()
    + demoWarning
    + `<div class="cards">
        <div class="summary-card"><span class="small">ข้อมูลผลย้อนหลัง</span><strong>${matchCount.toLocaleString('th-TH')}</strong><small>นัดที่นำเข้า</small></div>
        <div class="summary-card"><span class="small">ลีกที่มีสถิติ</span><strong>${leagueCount}</strong><small>ลีก</small></div>
        <div class="summary-card"><span class="small">ตารางแข่งที่นำเข้า</span><strong>${state.fixtures.length}</strong><small>คู่</small></div>
      </div>`
    + panel('ตารางแข่งที่นำเข้าสำหรับวิเคราะห์', fixturesArea(), `<button class="ghost-button" id="goAnalysis">เลือกทีมวิเคราะห์ →</button>`)
    + panel('เริ่มต้นใช้งาน', `<div class="helper">นำเข้าผลการแข่งขันย้อนหลังตามวิธีใน README เพื่อเปิดใช้งานการวิเคราะห์คู่บอล</div>`);
}
function matchForm(){const leagues=state.meta?.leagues||[], active=leagues.find(l=>l.code===state.league), teams=active?.teams||[];return `<form id="matchForm" class="form-row"><div class="field"><label for="league">ลีก</label><select id="league" name="league" required>${leagues.map(l=>`<option value="${clean(l.code)}" ${l.code===state.league?'selected':''}>${clean(l.code)} (${l.matches} นัด)</option>`).join('')}</select></div><div class="field"><label for="home">เจ้าบ้าน</label><select id="home" name="home" required>${teams.map(x=>`<option value="${clean(x)}" ${x===state.home?'selected':''}>${clean(x)}</option>`).join('')}</select></div><div class="field"><label for="away">ทีมเยือน</label><select id="away" name="away" required>${teams.map(x=>`<option value="${clean(x)}" ${x===state.away?'selected':''}>${clean(x)}</option>`).join('')}</select></div><div class="field"><label for="matchDate">วันที่ประเมิน</label><input type="date" id="matchDate" name="matchDate" required value="${clean(state.matchDate)}"/></div><button class="primary-button" type="submit" ${state.loading?'disabled':''}>${state.loading?'กำลังคำนวณ...':'วิเคราะห์ →'}</button></form>`}
function renderAnalysis(){let block=title('วิเคราะห์คู่บอล','เลือกลีกและสองทีมเพื่อคำนวณโอกาสจากผลการแข่งขันย้อนหลัง');if(!state.meta?.leagues?.length)return block+alertBar('ยังไม่มีฐานข้อมูลการแข่งขันจริง — ให้รันสคริปต์นำเข้า CSV ก่อน','warning')+panel('เริ่มต้นนำเข้าข้อมูล',`<div class="helper"><span class="kbd">python scripts/import_csv.py history.csv</span><br>ดู README.md สำหรับรายละเอียด</div>`);
const latest=state.meta.leagues.find(league=>league.code===state.league)?.last_match;
if(latest) block+=alertBar(`ผลย้อนหลังล่าสุดของลีกนี้ ${latest} · ตรวจสอบความใหม่ของข้อมูลก่อนใช้ผลวิเคราะห์`, 'info');
block+=panel('เลือกคู่แข่งขัน',matchForm());if(state.error)block+=alertBar(state.error,'error');if(state.loading)return block+`<div class="panel"><div class="panel-body"><span class="loader"></span> กำลังคำนวณผล...</div></div>`;if(state.predict)block+=predictCard(state.predict);else block+=panel('ผลการวิเคราะห์',noData('เลือกทีมเพื่อเริ่มต้น','ระบบต้องมีผลการแข่งขันย้อนหลังเพียงพอก่อนจึงจะคำนวณเปอร์เซ็นต์ได้'));return block}
function predictCard(p){const x=p.markets.one_x_two, ex=p.expected_goals, m=p.markets;
 let warning = p.data_mode==='demo_only'?alertBar('สถิติจำลอง: ตัวเลขทุกตัวด้านล่างมาจากข้อมูลสมมติสำหรับทดสอบโปรแกรม ไม่ใช่คำทำนายบอลจริง','warning'):'';
 if(!p.match.is_scheduled_fixture)warning+=alertBar('การจับคู่สมมติ: ยังไม่พบแมตช์นี้ในตารางแข่งขันที่นำเข้า การวิเคราะห์ไม่ได้ยืนยันว่าจะมีการแข่งขันเกิดขึ้น','info');
 const header=`<div class="prediction-header"><div><div class="match-title">${clean(p.match.home)} <span class="muted">vs</span> ${clean(p.match.away)}</div><div class="match-date">${clean(p.match.league)} · ${clean(p.match.date)} · ${clean(p.model)}</div></div><span class="pill ${p.data_mode==='demo_only'?'demo':'muted'}">${p.data_mode==='demo_only'?'DEMO':'PRE-MATCH'}</span></div>`;
 const tabs=[['overview','ภาพรวม'],['handicap','ต่อ–รอง'],['totals','สูง–ต่ำ'],['scores','สกอร์'],['half','ครึ่งแรก'],['extras','เตะมุม / ใบ']];
 let inside = `<div class="tabs" role="tablist" aria-label="หมวดวิเคราะห์">${tabs.map(([id,name])=>`<button role="tab" aria-selected="${state.marketTab===id}" class="tab ${state.marketTab===id?'active':''}" data-market="${id}">${name}</button>`).join('')}</div><div class="panel-body">`;
 if(state.marketTab==='overview'){
 const outcomes = [[p.match.home,x.home],['เสมอ',x.draw],[p.match.away,x.away]];
 const highest = Math.max(...outcomes.map(([,probability])=>probability));
 const leaders = outcomes.filter(([,probability])=>probability===highest);
 inside+=`<div class="forecast-lead"><span>${leaders.length===1 ? `โอกาสสูงสุด · ${clean(leaders[0][0])}` : 'โอกาสสูงสุดสูสีกัน'}</span><strong>${fmt(highest)}</strong></div>`;
 inside+=`<div class="prob-grid"><div class="prob-cell"><span>เจ้าบ้านชนะ</span><strong>${fmt(x.home)}</strong></div><div class="prob-cell"><span>เสมอ</span><strong>${fmt(x.draw)}</strong></div><div class="prob-cell"><span>ทีมเยือนชนะ</span><strong>${fmt(x.away)}</strong></div></div><div class="prob-bar" aria-label="สัดส่วนความน่าจะเป็น"><div class="home" style="width:${pct(x.home)}%"></div><div class="draw" style="width:${pct(x.draw)}%"></div><div class="away" style="width:${pct(x.away)}%"></div></div><div class="mini-metrics"><div class="metric"><span>ประตูคาดหมายเจ้าบ้าน</span><strong>${ex.home.toFixed(2)}</strong></div><div class="metric"><span>ประตูคาดหมายทีมเยือน</span><strong>${ex.away.toFixed(2)}</strong></div><div class="metric"><span>สูงกว่า 2.5 ประตู</span><strong>${fmt(m.totals['2.5'].over)}</strong></div><div class="metric"><span>ทั้งสองทีมยิงประตู</span><strong>${fmt(m.btts.yes)}</strong></div></div>`;
 } else if(state.marketTab==='totals'){
 inside+=`<div class="market-list">${Object.entries(m.totals).map(([line,val])=>`<div class="market-row"><span>สูงกว่า ${line} ประตู</span><strong>${fmt(val.over)}</strong><span>ต่ำกว่า ${fmt(val.under)}</span></div>`).join('')}</div>`;
 } else if(state.marketTab==='scores'){
 inside+=`<div class="scores">${m.top_scores.map(item=>`<div class="score"><strong>${clean(item.score)}</strong><span>${fmt(item.p)}</span></div>`).join('')}</div><p class="helper">สกอร์คือความน่าจะเป็นของผลต่าง ๆ ไม่ใช่สกอร์ที่รับประกันว่าจะเกิดขึ้น</p>`;
 } else if(state.marketTab==='half'){
 inside+=m.first_half?`<div class="prob-grid">${['home','draw','away'].map((k,i)=>`<div class="prob-cell"><span>${['เจ้าบ้าน','เสมอ','ทีมเยือน'][i]}</span><strong>${fmt(m.first_half.one_x_two[k])}</strong></div>`).join('')}</div><p class="helper">โมเดลครึ่งแรกแบบ Poisson ที่ยังต้องผ่านการประเมินแยก</p>`:noData('ยังไม่มีข้อมูลครึ่งแรกมากพอ','โปรดนำเข้า CSV ที่มีคอลัมน์ HTHG และ HTAG');
 } else if(state.marketTab==='extras'){
 const xs=Object.entries(p.experimental||{});inside+=xs.length?xs.map(([k,v])=>`<div class="market-row"><span>${k==='corners'?'เตะมุม':'ใบเหลือง'} (ทดลอง ไม่ผ่านการยืนยันความแม่นยำ)</span><strong>${v.expected_home} : ${v.expected_away}</strong></div>`).join(''):noData('ยังไม่เปิดคาดการณ์เตะมุม/ใบเหลือง','ข้อมูลที่มีไม่เพียงพอสำหรับโมเดลเฉพาะตลาด ระบบจึงไม่สร้างตัวเลขขึ้นมาเอง');
 } else if(state.marketTab==='handicap'){
 inside+=`<p class="helper">เลือกฝั่งและราคาต่อรองด้านล่างเพื่อคำนวณโอกาสชนะเต็ม ชนะครึ่ง คืนทุน และแพ้ครึ่งตามผลสกอร์ทุกแบบ</p>`;
 }
 inside+='</div>';
 const oddsContent=`<form id="oddsForm" class="form-row"><div class="field"><label for="kind">ตลาด</label><select id="kind"><option value="handicap">ต่อ–รอง</option><option value="total">สูง–ต่ำ</option></select></div><div class="field"><label for="selection">ฝั่ง</label><select id="selection"><option value="home">เจ้าบ้าน</option><option value="away">ทีมเยือน</option></select></div><div class="field"><label for="line">แต้มต่อ / เส้น</label><input id="line" type="number" min="-10" max="15" step="0.25" value="-0.5"/></div><div class="field"><label for="odds">ราคา Decimal</label><input id="odds" type="number" min="1.01" max="1000" step="0.01" value="1.90"/></div><button type="submit" class="primary-button">คำนวณ EV</button></form><div id="oddsOutput">${state.oddsResult?evMarkup(state.oddsResult):'<p class="helper">ผลการคำนวณราคาจะปรากฏตรงนี้ · ไม่ได้ส่งเดิมพัน</p>'}</div>`;
 return warning+`<section class="panel"><div class="panel-body">${header}</div>${inside}</section>`+panel('เปรียบเทียบราคาต่อรอง',oddsContent)+panel('คุณภาพของข้อมูล',`<div class="mini-metrics"><div class="metric"><span>ผลย้อนหลังที่โมเดลใช้</span><strong>${p.samples.training_matches}</strong></div><div class="metric"><span>ข้อมูลเหย้า / เยือน</span><strong>${p.samples.home_samples} / ${p.samples.away_samples}</strong></div></div><p class="helper">ตัวเลขทั้งหมดเป็นการประมาณจากสถิติผลย้อนหลังที่มีอยู่ก่อนวันที่เลือก ไม่ใช่ผลรับประกัน · หากมีข้อมูลแมตช์จริงต้องตรวจสอบเวลาเริ่มแข่งและข้อมูลล่าสุดอีกครั้ง</p>`);
}
function evMarkup(x){if(x.error)return alertBar(x.error,'error');const r=x.results;return `<div class="mini-metrics"><div class="metric"><span>ราคาเสมอตัวตามโมเดล</span><strong>${r.fair_odds??'—'}</strong></div><div class="metric"><span>EV โดยประมาณต่อ 1 หน่วย</span><strong class="${r.ev>=0?'good':'bad'}">${r.ev>=0?'+':''}${(r.ev*100).toFixed(2)}%</strong></div></div><div class="market-list" style="margin-top:12px"><div class="market-row"><span>ชนะเต็ม</span><strong>${fmt(r.full_win)}</strong></div><div class="market-row"><span>ชนะครึ่ง</span><strong>${fmt(r.half_win)}</strong></div><div class="market-row"><span>คืนทุน</span><strong>${fmt(r.push)}</strong></div><div class="market-row"><span>แพ้ครึ่ง</span><strong>${fmt(r.half_loss)}</strong></div><div class="market-row"><span>แพ้เต็ม</span><strong>${fmt(r.full_loss)}</strong></div></div><p class="helper">EV เป็นการคาดหมายจากโมเดลที่อาจคลาดเคลื่อน ไม่ใช่ข้อแนะนำให้เดิมพัน</p>`}
function renderPerformance(){let body=title('ประสิทธิภาพของ AI','แสดงผลทดสอบตามลำดับเวลา ไม่ใช้ข้อมูลผลแข่งขันจากอนาคต');if(badgeMode()==='demo')body+=alertBar('ข้อมูลเป็น DEMO — ผลทดสอบด้านล่างไม่ได้บอกความแม่นยำของฟุตบอลจริง','warning');if(!state.meta?.leagues?.length)return body+panel('การทดสอบ',noData('ยังไม่มีข้อมูลย้อนหลัง','นำเข้าไฟล์ผลการแข่งขันก่อน'));
 const item=state.performance;if(!item) return body+panel('การประเมิน',`<div class="empty-state"><span class="loader"></span><p>กำลังประเมินโมเดลย้อนหลัง...</p></div>`);if(item.error)return body+panel('การประเมิน',alertBar(item.error,'error'));
 if(item.status!=='evaluated')return body+panel('ข้อมูลไม่พอ',noData('ต้องการข้อมูลย้อนหลังเพิ่ม',item.reason||'ยังไม่ผ่านเกณฑ์ขั้นต่ำ'));
 return body+`<div class="cards"><div class="summary-card"><span class="small">แมตช์ที่ทดสอบได้</span><strong>${item.sample_size}</strong><small>นัดนอกช่วงฝึกของแต่ละวัน</small></div><div class="summary-card"><span class="small">ทายผล 1X2 ตรง</span><strong>${fmt(item.accuracy)}</strong><small>ไม่บ่งบอกความแม่นของเปอร์เซ็นต์</small></div><div class="summary-card"><span class="small">Multiclass Log Loss</span><strong>${item.log_loss}</strong><small>ยิ่งต่ำยิ่งดี</small></div></div>`+panel('รายงานการทดสอบ',`<div class="market-list"><div class="market-row"><span>Multiclass Brier Score (ยิ่งต่ำยิ่งดี)</span><strong>${item.brier_multiclass}</strong></div><div class="market-row"><span>ข้ามข้อมูลไม่พอ</span><strong>${item.skipped} นัด</strong></div><div class="market-row"><span>Baseline Log Loss (ความถี่ลีกย้อนหลัง)</span><strong>${item.baseline_log_loss}</strong></div><div class="market-row"><span>ดีกว่า Baseline ตาม Log Loss</span><strong class="${item.beats_frequency_baseline?'good':'bad'}">${item.beats_frequency_baseline?'ใช่':'ยังไม่ผ่าน'}</strong></div><div class="market-row"><span>โมเดล</span><strong>${clean(item.model)}</strong></div></div><p class="helper">${clean(item.method)} · ยังไม่มีการทดสอบเปรียบเทียบกับราคาตลาดหรือรับรองผลกำไร</p>`);
}
function renderSettings(){return title('ข้อมูลและวิธีใช้งาน','สถิติที่ใช้มาจากแหล่งข้อมูลที่คุณนำเข้า ไม่มีการแสดงผลบอลสดปลอม')+panel('สถานะระบบ',`<div class="market-list"><div class="market-row"><span>API</span><strong class="good">${state.meta?'ออนไลน์':'ออฟไลน์'}</strong></div><div class="market-row"><span>ประเภทข้อมูล</span><strong>${badgeMode()==='demo'?'DEMO':badgeMode()==='real'?'นำเข้าเอง':'ยังไม่มีข้อมูล'}</strong></div><div class="market-row"><span>โมเดล</span><strong>${clean(state.meta?.model||'—')}</strong></div><div class="market-row"><span>จำนวนลีก</span><strong>${state.meta?.leagues?.length??0}</strong></div></div>`)+panel('คู่มือเริ่มต้น',`<div class="helper"><strong>เปิดเว็บ:</strong> <span class="kbd">uvicorn football_ai.api:app --app-dir api --port 8000</span><br><strong>นำเข้าไฟล์ CSV:</strong> <span class="kbd">PYTHONPATH=api python scripts/import_csv.py E0.csv</span><br><strong>โหลดข้อมูลจากแหล่ง:</strong> <a href="https://www.football-data.co.uk/data.php" target="_blank" rel="noopener noreferrer">Football-Data.co.uk</a><br><strong>Deploy:</strong> โฮสต์ web/ บน Cloudflare Pages และ API Python บนโฮสต์ที่รัน Python ได้ พร้อมตั้งค่า URL ใน web/config.js<br><br>อ่าน README.md ภายใน ZIP เพื่อดูขั้นตอนโดยละเอียด</div>`)+panel('ขอบเขตการวิเคราะห์',`<div class="helper">✓ 1X2, สูง–ต่ำ, BTTS, สกอร์, คำนวณ EV สำหรับต่อ–รองและควบลูก<br>△ ครึ่งแรก เตะมุม ใบเหลือง จะแสดงเฉพาะเมื่อมีข้อมูลพอ และส่วนทดลองยังไม่ได้ยืนยันผลทดสอบ<br>✕ ยังไม่เชื่อมข้อมูลบอลสดแบบเรียลไทม์ ไม่มีระบบแทงบอลอัตโนมัติ และไม่มีการรับประกันผล</div>`)}
function render(){headers();modeHeader();$('page').innerHTML=state.page==='today'?renderToday():state.page==='analysis'?renderAnalysis():state.page==='performance'?renderPerformance():renderSettings();if(state.page==='today'){loadLiveAnalysis();loadUpcomingAnalysis();loadLiveAudit()}}
async function load(){try{const [meta,fixtures]=await Promise.all([api('/meta'),api('/fixtures')]);state.meta=meta;state.fixtures=fixtures.fixtures||[];const first=meta.leagues?.[0];state.league=first?.code||'';state.home=first?.teams?.[0]||'';state.away=first?.teams?.[1]||'';render();}catch(err){state.meta=null;if(state.page==='today'){render()}else{$('page').innerHTML=title('ไม่สามารถเชื่อมต่อเซิร์ฟเวอร์','เปิดเว็บไซต์ผ่าน FastAPI หรือกำหนด URL API ที่ถูกต้อง')+alertBar(err.message,'error');modeHeader()}}}
setInterval(() => {
  if (document.hidden) return;
  loadLiveAnalysis();
  if (Date.now() - liveAuditCheckedAt >= 60000) loadLiveAudit();
}, 20000);
document.addEventListener('visibilitychange', () => {
  if (!document.hidden) {
    loadLiveAnalysis();
    if (Date.now() - liveAuditCheckedAt >= 60000) loadLiveAudit();
  }
});
async function loadPerformance(){if(!state.league)return;state.performance=null;render();try{state.performance=await api('/performance?league='+encodeURIComponent(state.league)+'&last_n=100')}catch(err){state.performance={error:err.message}}render()}
async function requestPrediction(){state.loading=true;state.predict=null;state.oddsResult=null;state.error='';render();try{const qs=new URLSearchParams({league:state.league,home:state.home,away:state.away,match_date:state.matchDate});state.predict=await api('/predict?'+qs)}catch(err){state.error=err.message}state.loading=false;render()}
document.addEventListener('click',e=>{const btn=e.target.closest('[data-page]');if(btn){setPage(btn.dataset.page);return}const tab=e.target.closest('[data-market]');if(tab){state.marketTab=tab.dataset.market;render();return}if(e.target.closest('#goAnalysis')){setPage('analysis');return}const fixture=e.target.closest('[data-fixture]');if(fixture){const f=state.fixtures.find(x=>x.id===fixture.dataset.fixture);if(f){state.league=f.league;state.home=f.home;state.away=f.away;state.matchDate=f.kickoff.slice(0,10);state.predict=null;setPage('analysis');requestPrediction()}}});
document.addEventListener('change',e=>{if(e.target.id==='league'){state.league=e.target.value;const active=state.meta?.leagues?.find(l=>l.code===state.league);state.home=active?.teams?.[0]||'';state.away=active?.teams?.[1]||'';state.predict=null;render();return}if(e.target.id==='home')state.home=e.target.value;if(e.target.id==='away')state.away=e.target.value;if(e.target.id==='matchDate')state.matchDate=e.target.value;if(e.target.id==='kind'){const isTotal=e.target.value==='total';const select=$('selection');select.innerHTML=isTotal?'<option value="over">สูงกว่า</option><option value="under">ต่ำกว่า</option>':'<option value="home">เจ้าบ้าน</option><option value="away">ทีมเยือน</option>';$('line').value=isTotal?'2.5':'-0.5'}});
document.addEventListener('submit',async e=>{if(e.target.id==='matchForm'){e.preventDefault();const form=e.target;state.league=form.league.value;state.home=form.home.value;state.away=form.away.value;state.matchDate=form.matchDate.value;if(state.home===state.away){state.error='ต้องเลือกคนละทีม';render();return}await requestPrediction()}if(e.target.id==='oddsForm'){e.preventDefault();if(!state.predict)return;const data={league:state.league,home:state.home,away:state.away,match_date:state.matchDate,kind:$('kind').value,selection:$('selection').value,line:Number($('line').value),odds:Number($('odds').value)};try{state.oddsResult=await api('/odds/estimate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)})}catch(err){state.oddsResult={error:err.message}}$('oddsOutput').innerHTML=evMarkup(state.oddsResult)}});
$('todayLabel').textContent=new Intl.DateTimeFormat('th-TH',{timeZone:'Asia/Bangkok',dateStyle:'medium'}).format(new Date());
load();
