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
    const active=document.querySelector('.trend-window.active'); if(active) await loadProjectChart(Number(active.dataset.days));
  }catch(e){ $('formStatus').textContent=`Error: ${e.message}`; }
}

const SERIES = [
  {key:'weight_kg', label:'Peso', unit:'kg', desired:'down'},
  {key:'body_fat_pct', label:'Grasa corporal', unit:'%', desired:'down'},
  {key:'muscle_mass_kg', label:'Masa muscular', unit:'kg', desired:'stable'},
  {key:'body_water_pct', label:'Agua corporal', unit:'%', desired:'stable'},
  {key:'visceral_fat_index', label:'Grasa visceral', unit:'índice', desired:'down'},
  {key:'sleep_hours', label:'Sueño', unit:'h', desired:'stable'},
  {key:'activity_minutes', label:'Actividad', unit:'min', desired:'context'}
];

function dateKey(v){ return String(v).slice(0,10); }
function statusWord(delta, desired){
  if (Math.abs(delta) < 0.25) return 'estable';
  if (desired === 'down') return delta < 0 ? 'mejorando' : 'subiendo';
  if (desired === 'stable') return Math.abs(delta) <= 2 ? 'estable' : 'cambió';
  return delta > 0 ? 'más' : 'menos';
}
function actualText(v, unit){
  if(v == null || Number.isNaN(Number(v))) return 'sin dato';
  const n=Number(v);
  return `${n.toFixed(unit==='min'||unit==='índice'?0:1)} ${unit}`;
}
function metricPoints(data,key){
  if(key==='sleep_hours') return Object.entries(data.sleep_hours||{}).map(([d,v])=>({date:d,value:Number(v)}));
  if(key==='activity_minutes') return Object.entries(data.activity_minutes||{}).map(([d,v])=>({date:d,value:Number(v)}));
  return (data.metrics?.[key]||[]).map(p=>({date:dateKey(p.captured_at),value:Number(p.value)}));
}
function normalize(points){
  if(!points.length) return [];
  const base=points[0].value || 1;
  return points.map(p=>({...p,index:(p.value/base)*100}));
}

async function loadProjectChart(days=14){
  try{
    const data=await api(`/api/project-series?days=${days}`);
    renderProjectChart(data);
  }catch(e){
    $('projectChart').innerHTML=`<span>No se pudo cargar el mapa del proyecto: ${e.message}</span>`;
  }
}

function renderProjectChart(data){
  const box=$('projectChart');
  const all=SERIES.map(meta=>({meta,points:normalize(metricPoints(data,meta.key))})).filter(x=>x.points.length);
  if(!all.length){ box.innerHTML='<span>Aún no hay datos suficientes.</span>'; return; }

  const dates=[...new Set(all.flatMap(s=>s.points.map(p=>p.date)))].sort();
  if(dates.length<2){ box.innerHTML='<span>Se necesitan al menos dos días para comparar.</span>'; return; }
  const w=1100,h=360,left=54,right=28,top=28,bottom=48;
  const indexVals=all.flatMap(s=>s.points.map(p=>p.index));
  let min=Math.min(...indexVals,96), max=Math.max(...indexVals,104);
  const margin=Math.max((max-min)*0.18,1.2); min-=margin; max+=margin;
  const x=d=>left+(dates.indexOf(d)/(dates.length-1))*(w-left-right);
  const y=v=>top+((max-v)/(max-min))*(h-top-bottom);
  const palette=['#1565c0','#c62828','#2e7d32','#00838f','#6a1b9a','#ef6c00','#455a64'];

  let svg=`<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Mapa general de evolución del Proyecto 130">`;
  [0,.25,.5,.75,1].forEach(t=>{
    const yy=top+t*(h-top-bottom); const val=max-t*(max-min);
    svg+=`<line class="gridline" x1="${left}" y1="${yy}" x2="${w-right}" y2="${yy}"></line><text class="axis-label" x="${left-8}" y="${yy+4}" text-anchor="end">${val.toFixed(1)}</text>`;
  });
  const baseY=y(100);
  svg+=`<line class="baseline" x1="${left}" y1="${baseY}" x2="${w-right}" y2="${baseY}"></line><text class="baseline-label" x="${w-right}" y="${baseY-6}" text-anchor="end">Punto de partida = 100</text>`;

  all.forEach((series,i)=>{
    const pts=series.points;
    const path=pts.map((p,j)=>`${j?'L':'M'} ${x(p.date).toFixed(1)} ${y(p.index).toFixed(1)}`).join(' ');
    svg+=`<path class="series-line" data-series="${series.meta.key}" d="${path}" style="stroke:${palette[i%palette.length]}"></path>`;
    pts.forEach(p=>{
      svg+=`<circle class="series-dot" data-series="${series.meta.key}" cx="${x(p.date)}" cy="${y(p.index)}" r="4" style="fill:${palette[i%palette.length]}"><title>${series.meta.label}: ${actualText(p.value,series.meta.unit)} · ${p.date}</title></circle>`;
    });
  });
  const labelDates=[dates[0],dates[Math.floor((dates.length-1)/2)],dates[dates.length-1]];
  labelDates.forEach(d=>svg+=`<text class="date-label" x="${x(d)}" y="${h-15}" text-anchor="middle">${new Date(d+'T12:00:00').toLocaleDateString('es-CO',{day:'numeric',month:'short'})}</text>`);
  svg+='</svg>';
  box.innerHTML=svg;

  const summaries=all.map(({meta,points})=>{
    const first=points[0],last=points[points.length-1],delta=last.index-first.index;
    return {meta,first,last,delta,color:palette[all.findIndex(x=>x.meta.key===meta.key)%palette.length]};
  });
  $('projectLegend').innerHTML=summaries.map(s=>`<button class="legend-item" data-series="${s.meta.key}"><i style="background:${s.color}"></i><span>${s.meta.label}</span><strong>${actualText(s.last.value,s.meta.unit)}</strong></button>`).join('');

  const weight=summaries.find(s=>s.meta.key==='weight_kg');
  const fat=summaries.find(s=>s.meta.key==='body_fat_pct');
  const muscle=summaries.find(s=>s.meta.key==='muscle_mass_kg');
  const sleep=summaries.find(s=>s.meta.key==='sleep_hours');
  const messages=[];
  if(weight) messages.push(`Peso: ${actualText(weight.first.value,'kg')} → ${actualText(weight.last.value,'kg')} (${(weight.last.value-weight.first.value).toFixed(1)} kg).`);
  if(fat) messages.push(`Grasa estimada: ${actualText(fat.first.value,'%')} → ${actualText(fat.last.value,'%')}.`);
  if(muscle) messages.push(`Músculo estimado: ${actualText(muscle.last.value,'kg')}, ${statusWord(muscle.delta,'stable')}.`);
  if(sleep) messages.push(`Sueño reciente: ${actualText(sleep.last.value,'h')}.`);
  $('projectSummary').innerHTML=messages.map(m=>`<span>${m}</span>`).join('');

  document.querySelectorAll('.legend-item').forEach(btn=>btn.addEventListener('click',()=>{
    const key=btn.dataset.series;
    const off=btn.classList.toggle('muted');
    document.querySelectorAll(`[data-series="${key}"]`).forEach(el=>{ if(el!==btn) el.classList.toggle('hidden-series',off); });
  }));
}

document.querySelectorAll('.trend-window').forEach(btn=>btn.addEventListener('click',()=>{
  document.querySelectorAll('.trend-window').forEach(x=>x.classList.remove('active'));
  btn.classList.add('active');
  loadProjectChart(Number(btn.dataset.days));
}));

const sleepDate = $('sleepForm').querySelector('[name=sleep_date]');
sleepDate.value = new Date().toISOString().slice(0,10);
refreshDashboard();
loadProjectChart(14);
setInterval(refreshDashboard, 60000);
