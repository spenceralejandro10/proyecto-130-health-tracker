const $ = (id) => document.getElementById(id);

async function api(path) {
  const response = await fetch(path, {headers: {'Content-Type':'application/json'}});
  if (!response.ok) throw new Error((await response.json().catch(()=>({detail:response.statusText}))).detail || 'Error');
  return response.json();
}

const METRICS = {
  weight_kg: {label:'Peso', unit:'kg'},
  body_fat_pct: {label:'Grasa corporal', unit:'%'},
  muscle_mass_kg: {label:'Masa muscular', unit:'kg'},
  body_water_pct: {label:'Agua corporal', unit:'%'},
  visceral_fat_index: {label:'Grasa visceral', unit:'índice'},
  sleep_hours: {label:'Sueño', unit:'h'},
  activity_minutes: {label:'Actividad', unit:'min'}
};

const COLORS = {
  weight_kg:'#4f46e5',
  body_fat_pct:'#dc2626',
  muscle_mass_kg:'#16a34a',
  body_water_pct:'#0891b2',
  visceral_fat_index:'#9333ea',
  sleep_hours:'#ea580c',
  activity_minutes:'#475569'
};

const planByDay = {
  0:'Recuperación / caminata suave opcional',
  1:'Pecho + tríceps',
  2:'Espalda + bíceps',
  3:'Piernas + glúteos',
  4:'Pecho + hombros + tríceps',
  5:'Espalda + bíceps',
  6:'Piernas + cuerpo completo ligero'
};

function num(v, digits=1){ return v == null ? '—' : Number(v).toFixed(digits); }
function signed(v, digits=1, suffix=''){ if(v==null) return '—'; const n=Number(v); return `${n>0?'+':''}${n.toFixed(digits)}${suffix}`; }
function dateKey(v){ return String(v).slice(0,10); }
function todayKey(){ const d=new Date(); d.setMinutes(d.getMinutes()-d.getTimezoneOffset()); return d.toISOString().slice(0,10); }
function fmtDate(d){ return new Date(d+'T12:00:00').toLocaleDateString('es-CO',{day:'numeric',month:'short'}); }

function metricPoints(series, key){
  if(key==='sleep_hours') return Object.entries(series.sleep_hours||{}).map(([date,value])=>({date,value:Number(value)})).sort((a,b)=>a.date.localeCompare(b.date));
  if(key==='activity_minutes') return Object.entries(series.activity_minutes||{}).map(([date,value])=>({date,value:Number(value)})).sort((a,b)=>a.date.localeCompare(b.date));
  return (series.metrics?.[key]||[]).map(p=>({date:dateKey(p.captured_at),value:Number(p.value)})).sort((a,b)=>a.date.localeCompare(b.date));
}

function sparkline(el, points, options={}){
  if(!el) return;
  if(!points || points.length<2){ el.innerHTML='<span class="empty-chart">Sin historial suficiente</span>'; return; }
  const vals=points.map(p=>p.value), min=Math.min(...vals), max=Math.max(...vals), span=Math.max(max-min,0.01);
  const w=320,h=82,p=8;
  const coords=points.map((pt,i)=>[
    p+(i/(points.length-1))*(w-2*p),
    p+((max-pt.value)/span)*(h-2*p)
  ]);
  const path=coords.map((c,i)=>`${i?'L':'M'} ${c[0].toFixed(1)} ${c[1].toFixed(1)}`).join(' ');
  let extra='';
  if(options.targetMin!=null && options.targetMax!=null){
    const top=p+((max-options.targetMax)/span)*(h-2*p);
    const bottom=p+((max-options.targetMin)/span)*(h-2*p);
    const y=Math.min(top,bottom), height=Math.abs(bottom-top);
    if(Number.isFinite(y)&&Number.isFinite(height)) extra=`<rect class="target-zone" x="${p}" y="${y}" width="${w-2*p}" height="${height}"></rect>`;
  }
  el.innerHTML=`<svg viewBox="0 0 ${w} ${h}" aria-hidden="true">${extra}<path class="spark-line" d="${path}"></path>${coords.map((c,i)=>`<circle class="spark-dot" cx="${c[0]}" cy="${c[1]}" r="${i===coords.length-1?3.5:2}"><title>${fmtDate(points[i].date)}: ${points[i].value}</title></circle>`).join('')}</svg>`;
}

function renderResearchChart(series){
  const keys=['weight_kg','body_fat_pct','muscle_mass_kg','body_water_pct','visceral_fat_index','sleep_hours','activity_minutes'];
  const groups=keys.map(key=>({key,points:metricPoints(series,key)})).filter(g=>g.points.length>=2);
  if(!groups.length){ $('projectChart').innerHTML='<span>Sin datos suficientes.</span>'; return; }

  const dates=[...new Set(groups.flatMap(g=>g.points.map(p=>p.date)))].sort();
  const normalized=groups.map(g=>{
    const base=g.points[0].value || 1;
    return {...g, points:g.points.map(p=>({...p,change:((p.value/base)-1)*100}))};
  });
  const all=normalized.flatMap(g=>g.points.map(p=>p.change));
  let min=Math.min(...all,-5), max=Math.max(...all,5);
  const margin=Math.max((max-min)*0.12,1); min-=margin; max+=margin;

  const w=1120,h=390,l=60,r=24,t=26,b=48;
  const x=d=>l+(dates.indexOf(d)/(dates.length-1))*(w-l-r);
  const y=v=>t+((max-v)/(max-min))*(h-t-b);

  let svg=`<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Mapa comparativo del proyecto">`;
  for(let i=0;i<=4;i++){
    const val=max-(i/4)*(max-min), yy=y(val);
    svg+=`<line class="grid-line" x1="${l}" y1="${yy}" x2="${w-r}" y2="${yy}"></line><text class="axis-text" x="${l-8}" y="${yy+4}" text-anchor="end">${val.toFixed(1)}%</text>`;
  }
  const zero=y(0);
  svg+=`<line class="zero-line" x1="${l}" y1="${zero}" x2="${w-r}" y2="${zero}"></line><text class="zero-label" x="${w-r}" y="${zero-7}" text-anchor="end">Inicio = 0%</text>`;

  normalized.forEach(g=>{
    const color=COLORS[g.key], label=METRICS[g.key].label, unit=METRICS[g.key].unit;
    const d=g.points.map((p,i)=>`${i?'L':'M'} ${x(p.date).toFixed(1)} ${y(p.change).toFixed(1)}`).join(' ');
    svg+=`<path data-series="${g.key}" class="main-series" style="stroke:${color}" d="${d}"></path>`;
    g.points.forEach(p=>{
      svg+=`<circle data-series="${g.key}" class="main-dot" style="fill:${color}" cx="${x(p.date)}" cy="${y(p.change)}" r="4"><title>${label}: ${p.value.toFixed(unit==='min'||unit==='índice'?0:1)} ${unit} · ${fmtDate(p.date)} · cambio ${p.change.toFixed(1)}%</title></circle>`;
    });
  });

  [dates[0],dates[Math.floor((dates.length-1)/2)],dates[dates.length-1]].forEach(d=>svg+=`<text class="date-text" x="${x(d)}" y="${h-14}" text-anchor="middle">${fmtDate(d)}</text>`);
  svg+='</svg>';
  $('projectChart').innerHTML=svg;

  $('projectLegend').innerHTML=normalized.map(g=>{
    const latest=g.points[g.points.length-1], unit=METRICS[g.key].unit;
    return `<button class="legend-item" data-key="${g.key}"><i style="background:${COLORS[g.key]}"></i><span>${METRICS[g.key].label}</span><strong>${latest.value.toFixed(unit==='min'||unit==='índice'?0:1)} ${unit}</strong></button>`;
  }).join('');

  document.querySelectorAll('.legend-item').forEach(btn=>btn.addEventListener('click',()=>{
    const key=btn.dataset.key, hidden=btn.classList.toggle('muted');
    document.querySelectorAll(`[data-series="${key}"]`).forEach(el=>el.classList.toggle('series-hidden',hidden));
  }));

  const summaries=[];
  for(const key of ['weight_kg','body_fat_pct','muscle_mass_kg','sleep_hours']){
    const p=metricPoints(series,key); if(p.length<2) continue;
    const first=p[0].value,last=p[p.length-1].value,diff=last-first,unit=METRICS[key].unit;
    const label=METRICS[key].label;
    summaries.push(`<span><b>${label}</b> ${num(first)} → ${num(last)} ${unit} <em>(${signed(diff,1)})</em></span>`);
  }
  $('researchSummary').innerHTML=summaries.join('');
}

function renderComposition(series){
  const cfg=[
    ['body_fat_pct','bodyFat','bodyFatStart','bodyFatChange','bodyFatChart','bodyFatText','%','Si baja de forma sostenida mientras la fuerza se mantiene, la señal es favorable.'],
    ['muscle_mass_kg','muscleMass','muscleStart','muscleChange','muscleChart','muscleText','kg','Cambios pequeños pueden ser ruido de la báscula; se contrasta con fuerza y tendencia.'],
    ['body_water_pct','bodyWater','waterStart','waterChange','waterChart','waterText','%','Se sigue como tendencia. No indica por sí solo cuánto debes beber.'],
    ['visceral_fat_index','visceralFat','visceralStart','visceralChange','visceralChart','visceralText','índice','Se interpreta por tendencia del mismo dispositivo, no como medición clínica exacta.']
  ];
  cfg.forEach(([key,currentId,startId,changeId,chartId,textId,unit,text])=>{
    const p=metricPoints(series,key);
    if(!p.length) return;
    const first=p[0].value,last=p[p.length-1].value,diff=last-first;
    $(currentId).textContent=`${num(last)} ${unit}`;
    $(startId).textContent=`${num(first)} ${unit}`;
    $(changeId).textContent=signed(diff,1,unit==='%'?' puntos':' '+unit);
    $(textId).textContent=text;
    sparkline($(chartId),p);
  });
}

function renderSleep(series){
  const p=metricPoints(series,'sleep_hours');
  if(!p.length) return;
  const last=p[p.length-1].value;
  const recent=p.slice(-7), avg=recent.reduce((a,b)=>a+b.value,0)/recent.length;
  $('sleep').textContent=`${num(last)} h`;
  $('sleepAvg').textContent=`${num(avg)} h`;
  sparkline($('sleepMiniChart'),p,{targetMin:7,targetMax:9});
  if(avg<7) $('sleepInterpretation').textContent=`Promedio de 7 días: ${num(avg)} h. Está por debajo del objetivo configurado de 7–9 h.`;
  else if(avg<=9) $('sleepInterpretation').textContent=`Promedio de 7 días: ${num(avg)} h. Se mantiene dentro del objetivo configurado.`;
  else $('sleepInterpretation').textContent=`Promedio de 7 días: ${num(avg)} h. Está por encima del rango configurado; revisar contexto.`;
}

function renderWeight(d, series){
  $('weight').textContent=`${num(d.current_weight_kg)} kg`;
  $('weightStart').textContent=`${num(d.baseline_weight_kg)} kg`;
  $('weightChange').textContent=signed(d.change_from_baseline_kg,1,' kg');
  $('weightAvg').textContent=`${num(d.moving_avg_7d_kg)} kg`;
  $('goalWeight').textContent=`${num(d.goal_weight_kg)} kg`;

  const total=Math.max((d.baseline_weight_kg||0)-(d.goal_weight_kg||0),0.1);
  const done=Math.max((d.baseline_weight_kg||0)-(d.current_weight_kg||0),0);
  $('weightProgress').style.width=`${Math.min(100,Math.max(0,(done/total)*100))}%`;
  $('weightStatus').textContent=done>0?`${((done/total)*100).toFixed(0)}% del recorrido hacia la meta`:'Línea base';

  if(d.current_weight_kg!=null && d.moving_avg_7d_kg!=null){
    if(d.current_weight_kg<d.moving_avg_7d_kg) $('weightExplanation').textContent='El peso de hoy está por debajo del promedio de los últimos 7 días. El promedio es mayor porque incluye días anteriores con más peso; eso es coherente con una bajada reciente.';
    else if(d.current_weight_kg>d.moving_avg_7d_kg) $('weightExplanation').textContent='El peso de hoy está por encima del promedio de 7 días. Se observa la tendencia antes de concluir si es un cambio real.';
    else $('weightExplanation').textContent='El peso de hoy coincide aproximadamente con el promedio reciente.';
  }

  const p=metricPoints(series,'weight_kg');
  if(p.length>=2){
    const diff=p[p.length-1].value-p[0].value;
    $('weightStatus').textContent+=` · ${signed(diff,1,' kg')} en el período visible`;
  }
}

function renderStudy(d){
  $('day').textContent=d.day_number?`Día ${d.day_number} de 130`:'Inicio pendiente';
  $('remaining').textContent=d.days_remaining??'—';
  const startFeb=new Date('2027-02-01T00:00:00');
  const now=new Date(); const days=Math.max(0,Math.ceil((startFeb-now)/(1000*60*60*24)));
  $('tripNote').textContent=`Faltan aproximadamente ${days} días para comenzar febrero de 2027. La fecha exacta del vuelo aún no está configurada.`;
}

function renderActivity(activities, series){
  const today=todayKey();
  const todayRows=activities.filter(a=>dateKey(a.started_at)===today);
  const actual={};
  todayRows.forEach(a=>actual[a.activity_type]=(actual[a.activity_type]||0)+Number(a.duration_min));
  const weekday=new Date().getDay();
  const plan=[
    {key:'caminata_manana',label:'Caminata de la mañana',target:'60 min'},
    {key:'fuerza_gimnasio',label:`Gimnasio · ${planByDay[weekday]}`,target:weekday===0?'Opcional':'70–80 min'},
    {key:'funcional_tarde',label:'Ejercicio funcional de la tarde',target:weekday===0?'Descanso':'20–25 min'},
    {key:'caminata_noche',label:'Caminata suave de la noche',target:'30–40 min'}
  ];
  const required=weekday===0?plan.filter(x=>x.key==='caminata_manana'):plan;
  const done=required.filter(x=>actual[x.key]>0).length;
  $('todayCompletion').textContent=`${done} de ${required.length}`;
  $('todayTraining').textContent=planByDay[weekday];
  $('todayPlan').innerHTML=plan.map(item=>{
    const min=actual[item.key]||0;
    const state=min>0?'done':'pending';
    return `<div class="plan-item ${state}"><i></i><div><strong>${item.label}</strong><span>${min>0?`${Math.round(min)} min realizados`:item.target+' previstos'}</span></div></div>`;
  }).join('');

  const total=todayRows.reduce((a,b)=>a+Number(b.duration_min),0);
  $('activityTotal').textContent=`${Math.round(total)} min hoy`;
  $('activityTimeline').innerHTML=todayRows.length?todayRows.sort((a,b)=>String(a.started_at).localeCompare(String(b.started_at))).map(a=>{
    const labels={caminata_manana:'Caminata mañana',fuerza_gimnasio:`Fuerza · ${planByDay[weekday]}`,funcional_tarde:'Funcional tarde',caminata_noche:'Caminata noche'};
    return `<div class="activity-item"><span>${labels[a.activity_type]||a.activity_type}</span><strong>${Math.round(a.duration_min)} min</strong><small>${a.integrated?'Integrado con estudio/conversación':'Sesión dedicada'}</small></div>`;
  }).join(''):'<p class="plain-note">Todavía no hay actividad registrada hoy.</p>';

  sparkline($('activityMiniChart'),metricPoints(series,'activity_minutes'));
}

function renderAlerts(d){
  const map={ok:'Seguimiento normal',attention:'Revisar',insufficient:'Faltan datos'};
  $('quality').textContent=map[d.data_quality]||'Estado';
  const items=d.alerts?.length?d.alerts:['No hay señales relevantes que requieran atención en este momento.'];
  $('alerts').innerHTML=items.map(x=>`<div class="attention-item"><i></i><span>${x}</span></div>`).join('');
  $('nextReminder').textContent=d.next_reminder?.title||'Sin recordatorios pendientes';
  $('nextReminderTime').textContent=d.next_reminder?.time_local||'—';
}

async function load(days=14){
  try{
    $('sync').textContent='Actualizando…';
    const [dashboard,series,activities]=await Promise.all([
      api('/api/dashboard'),
      api(`/api/project-series?days=${days}`),
      api('/api/activities?limit=250')
    ]);
    renderWeight(dashboard,series);
    renderStudy(dashboard);
    renderActivity(activities,series);
    renderSleep(series);
    renderComposition(series);
    renderResearchChart(series);
    renderAlerts(dashboard);
    $('sync').textContent=`Actualizado ${new Date().toLocaleTimeString('es-CO',{hour:'2-digit',minute:'2-digit'})}`;
  }catch(e){
    $('sync').textContent='Sin conexión';
    $('projectChart').innerHTML=`<span>Error al cargar: ${e.message}</span>`;
  }
}

document.querySelectorAll('.range-btn').forEach(btn=>btn.addEventListener('click',()=>{
  document.querySelectorAll('.range-btn').forEach(x=>x.classList.remove('active'));
  btn.classList.add('active');
  load(Number(btn.dataset.days));
}));

load(14);
setInterval(()=>load(Number(document.querySelector('.range-btn.active')?.dataset.days||14)),60000);
