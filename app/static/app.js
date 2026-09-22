const $ = (id) => document.getElementById(id);
const nowLocalInput = () => {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 19);
};

async function api(path, options = {}) {
  const response = await fetch(path, {headers: {'Content-Type':'application/json', ...(options.headers||{})}, ...options});
  if (!response.ok) {
    const error = await response.json().catch(() => ({detail: response.statusText}));
    throw new Error(error.detail || 'Error de servidor');
  }
  return response.json();
}

function formatKg(v){ return v == null ? '—' : `${Number(v).toFixed(1)} kg`; }
function localDateKey(){ return nowLocalInput().slice(0,10); }
function metricLabel(entry){
  if (!entry || entry.value == null) return '—';
  return `${Number(entry.value).toFixed(1)} ${entry.unit || ''}`.trim();
}
function trendLabel(entry){
  const map={increasing:'Aumentando',decreasing:'Disminuyendo',stable:'Estable',insufficient:'Sin tendencia'};
  return entry ? `${map[entry.personal_trend] || 'Sin tendencia'} · ${entry.origin || 'sin fuente'}` : 'Sin datos';
}


async function refreshDashboard(){
  try{
    const d = await api('/api/dashboard');
    $('weight').textContent = formatKg(d.current_weight_kg);
    $('avg7').textContent = formatKg(d.moving_avg_7d_kg);
    $('weightDelta').textContent = d.change_from_baseline_kg == null ? 'Sin línea base' : `${d.change_from_baseline_kg > 0 ? '+' : ''}${d.change_from_baseline_kg.toFixed(1)} kg desde inicio`;
    $('day').textContent = d.day_number ? `${d.day_number}/130` : '—';
    $('remaining').textContent = d.days_remaining == null ? 'Inicio pendiente' : `${d.days_remaining} días restantes`;
    $('activity').textContent = `${d.activity_minutes_today} min`;
    $('integrated').textContent = `${d.integrated_minutes_today} min integrados`;
    $('sleep').textContent = d.latest_sleep_hours == null ? '—' : `${d.latest_sleep_hours} h`;
    $('nextReminder').textContent = d.next_reminder?.title || '—';
    $('nextReminderTime').textContent = d.next_reminder ? d.next_reminder.time_local : 'Sin recordatorios';
    $('quality').textContent = d.data_quality;
    $('message').textContent = d.operational_message;
    $('message').className = `message ${d.data_quality === 'attention' ? 'attention' : d.data_quality === 'ok' ? 'good' : 'insufficient'}`;
    $('alerts').innerHTML = d.alerts.length ? d.alerts.map(a => `<li>${a}</li>`).join('') : '<li>Sin alertas activas.</li>';
    const c=d.composition || {};
    $('bodyFat').textContent=metricLabel(c.body_fat_pct); $('bodyFatTrend').textContent=trendLabel(c.body_fat_pct);
    $('muscleMass').textContent=metricLabel(c.muscle_mass_kg); $('muscleTrend').textContent=trendLabel(c.muscle_mass_kg);
    $('bodyWater').textContent=metricLabel(c.body_water_pct); $('waterTrend').textContent=trendLabel(c.body_water_pct);
    $('visceralFat').textContent=metricLabel(c.visceral_fat_index); $('visceralTrend').textContent=trendLabel(c.visceral_fat_index);
    $('sync').textContent = `Actualizado ${new Date().toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}`;
  }catch(e){
    $('sync').textContent = 'Sin conexión';
    $('message').textContent = `No se pudo actualizar: ${e.message}`;
  }
}

document.querySelectorAll('.tab').forEach(btn => btn.addEventListener('click', () => {
  document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
  document.querySelectorAll('.quick-form').forEach(x => x.classList.remove('active'));
  btn.classList.add('active');
  $(btn.dataset.tab).classList.add('active');
}));

$('weightForm').addEventListener('submit', async e => {
  e.preventDefault(); const f = new FormData(e.target);
  await submit('/api/metrics', {
    captured_at: nowLocalInput(), metric_key:'weight_kg', value:Number(f.get('value')), unit:'kg',
    source:f.get('source'), origin:'measured', validation_status:'confirmed',
    evidence_ref:f.get('evidence_ref') || null,
    source_event_id:`weight:${localDateKey()}:${f.get('value')}`
  });
});

$('activityForm').addEventListener('submit', async e => {
  e.preventDefault(); const f = new FormData(e.target);
  const ts=nowLocalInput();
  await submit('/api/activities', {started_at:ts,activity_type:f.get('activity_type'),duration_min:Number(f.get('duration_min')),integrated:f.get('integrated')==='on',source_event_id:`activity:${ts}:${f.get('activity_type')}:${f.get('duration_min')}`});
});

$('strengthForm').addEventListener('submit', async e => {
  e.preventDefault(); const f = new FormData(e.target);
  const ts=nowLocalInput();
  await submit('/api/strength', {performed_at:ts,exercise_name:f.get('exercise_name'),load_kg:Number(f.get('load_kg')),reps:Number(f.get('reps')),set_number:Number(f.get('set_number')),source_event_id:`strength:${ts}:${f.get('exercise_name')}:${f.get('set_number')}`});
});

$('sleepForm').addEventListener('submit', async e => {
  e.preventDefault(); const f = new FormData(e.target);
  const payload={sleep_date:f.get('sleep_date'),duration_min:f.get('duration_min')?Number(f.get('duration_min')):null,energy_score:f.get('energy_score')?Number(f.get('energy_score')):null,fatigue_score:f.get('fatigue_score')?Number(f.get('fatigue_score')):null};
  await submit('/api/sleep', payload);
});

async function submit(path, payload){
  try{
    $('formStatus').textContent='Guardando…';
    await api(path,{method:'POST',body:JSON.stringify(payload)});
    $('formStatus').textContent='Guardado y auditado.';
    await refreshDashboard();
    const active=document.querySelector('.trend-window.active'); if(active) await loadWeightTrend(Number(active.dataset.days));
  }catch(e){ $('formStatus').textContent=`Error: ${e.message}`; }
}

async function loadWeightTrend(days=7){
  try{
    const data=await api(`/api/trends/weight_kg?days=${days}`);
    renderChart(data.points || []);
  }catch(e){ $('weightChart').innerHTML='<span>No se pudo cargar la tendencia.</span>'; }
}

function renderChart(points){
  const box=$('weightChart');
  if(points.length < 2){ box.innerHTML='<span>Se necesitan al menos 2 mediciones confirmadas.</span>'; return; }
  const values=points.map(p=>Number(p.value));
  const min=Math.min(...values), max=Math.max(...values), span=Math.max(max-min,0.5);
  const w=800,h=160,pad=18;
  const coords=points.map((p,i)=>{
    const x=pad+(i/(points.length-1))*(w-pad*2);
    const y=pad+((max-Number(p.value))/span)*(h-pad*2);
    return [x,y];
  });
  const path=coords.map((c,i)=>`${i?'L':'M'} ${c[0].toFixed(1)} ${c[1].toFixed(1)}`).join(' ');
  const dots=coords.map(c=>`<circle class="dot" cx="${c[0]}" cy="${c[1]}" r="3"></circle>`).join('');
  box.innerHTML=`<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Tendencia de peso"><line class="axis" x1="${pad}" y1="${h-pad}" x2="${w-pad}" y2="${h-pad}"></line><path class="line" d="${path}"></path>${dots}</svg>`;
}

document.querySelectorAll('.trend-window').forEach(btn=>btn.addEventListener('click',()=>{
  document.querySelectorAll('.trend-window').forEach(x=>x.classList.remove('active'));
  btn.classList.add('active');
  loadWeightTrend(Number(btn.dataset.days));
}));

const sleepDate = $('sleepForm').querySelector('[name=sleep_date]');
sleepDate.value = new Date().toISOString().slice(0,10);
refreshDashboard();
loadWeightTrend(7);
setInterval(refreshDashboard, 60000);
