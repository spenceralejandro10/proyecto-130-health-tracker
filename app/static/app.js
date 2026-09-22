const $ = (id) => document.getElementById(id);

async function api(path, options={}) {
  const response = await fetch(path, {
    ...options,
    headers: {'Content-Type':'application/json', ...(options.headers||{})}
  });
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

let selectedMetric = 'all';

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
function escapeHtml(value){ return String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c])); }
function naturalChange(key, previous, current, unit=''){
  if(previous==null || current==null) return 'Sin comparación';
  const a=Number(previous), b=Number(current);
  const verb=b>a?'Subió':b<a?'Bajó':'Sin cambio';
  if(key==='body_fat_pct' || key==='body_water_pct') return `${verb}: ${num(a,1)}% → ${num(b,1)}%`;
  if(key==='visceral_fat_index') return `${verb}: ${num(a,0)} → ${num(b,0)}`;
  return `${verb}: ${num(a,1)} → ${num(b,1)} ${unit}`.trim();
}

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

function renderResearchSummary(series){
  const analysis=series.analysis||{};
  const summaries=analysis.metric_summaries||{};
  const period=`${analysis.from_date||'—'} → ${analysis.to_date||'—'}`;
  $('trendPeriodLabel').textContent=`Período visible: ${period} · ${series.days} días`;

  if(selectedMetric!=='all' && summaries[selectedMetric]){
    const s=summaries[selectedMetric];
    $('researchSummary').innerHTML=`<div class="trend-readout">
      <strong>${escapeHtml(s.headline)}</strong>
      <span>${s.sample_count} registros · promedio ${num(s.average,1)} ${escapeHtml(s.unit)} · mínimo ${num(s.minimum,1)} · máximo ${num(s.maximum,1)}</span>
    </div>`;
    $('chartFocusNote').textContent=`${s.headline} · ${s.sample_count} registros en el período.`;
    return;
  }

  const findings=(analysis.findings||[]).slice(0,6);
  $('researchSummary').innerHTML=findings.length
    ? `<div class="trend-readout"><strong>Lectura del período</strong>${findings.map(x=>`<span>${escapeHtml(x)}</span>`).join('')}</div>`
    : '<div class="trend-readout"><strong>Sin cambios comparables suficientes en este período.</strong></div>';
  $('chartFocusNote').textContent=`${Object.keys(summaries).length} indicadores con datos en el período · lectura combinada automática.`;
}

function renderResearchChart(series){
  const keys=['weight_kg','body_fat_pct','muscle_mass_kg','body_water_pct','visceral_fat_index','sleep_hours','activity_minutes'];
  const allGroups=keys.map(key=>({key,points:metricPoints(series,key)})).filter(g=>g.points.length>=2);
  if(!allGroups.length){
    $('projectChart').innerHTML='<span>Sin datos suficientes.</span>';
    $('projectLegend').innerHTML='';
    renderResearchSummary(series);
    return;
  }

  if(selectedMetric!=='all' && !allGroups.some(g=>g.key===selectedMetric)) selectedMetric='all';
  const groups=selectedMetric==='all'?allGroups:allGroups.filter(g=>g.key===selectedMetric);
  const dates=[...new Set(groups.flatMap(g=>g.points.map(p=>p.date)))].sort();
  const normalized=groups.map(g=>{
    const base=g.points[0].value || 1;
    return {...g,points:g.points.map(p=>({...p,change:((p.value/base)-1)*100}))};
  });
  const all=normalized.flatMap(g=>g.points.map(p=>p.change));
  let min=Math.min(...all,-1),max=Math.max(...all,1);
  const margin=Math.max((max-min)*0.16,.5); min-=margin; max+=margin;

  const w=1120,h=390,l=60,r=24,t=26,b=48;
  const x=d=>dates.length===1?(w+l-r)/2:l+(dates.indexOf(d)/(dates.length-1))*(w-l-r);
  const y=v=>t+((max-v)/(max-min))*(h-t-b);

  let svg=`<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Mapa comparativo del proyecto">`;
  for(let i=0;i<=4;i++){
    const val=max-(i/4)*(max-min),yy=y(val);
    svg+=`<line class="grid-line" x1="${l}" y1="${yy}" x2="${w-r}" y2="${yy}"></line><text class="axis-text" x="${l-8}" y="${yy+4}" text-anchor="end">${val.toFixed(1)}%</text>`;
  }
  const zero=y(0);
  svg+=`<line class="zero-line" x1="${l}" y1="${zero}" x2="${w-r}" y2="${zero}"></line><text class="zero-label" x="${w-r}" y="${zero-7}" text-anchor="end">Inicio del período = 0%</text>`;

  normalized.forEach(g=>{
    const color=COLORS[g.key],label=METRICS[g.key].label,unit=METRICS[g.key].unit;
    const d=g.points.map((p,i)=>`${i?'L':'M'} ${x(p.date).toFixed(1)} ${y(p.change).toFixed(1)}`).join(' ');
    svg+=`<path data-series="${g.key}" class="main-series" style="stroke:${color}" d="${d}"></path>`;
    g.points.forEach(p=>{
      svg+=`<circle data-series="${g.key}" class="main-dot" style="fill:${color}" cx="${x(p.date)}" cy="${y(p.change)}" r="4"><title>${label}: ${p.value.toFixed(unit==='min'||unit==='índice'?0:1)} ${unit} · ${fmtDate(p.date)} · cambio ${p.change.toFixed(1)}%</title></circle>`;
    });
  });

  const labelDates=[dates[0],dates[Math.floor((dates.length-1)/2)],dates[dates.length-1]].filter((d,i,a)=>d&&a.indexOf(d)===i);
  labelDates.forEach(d=>svg+=`<text class="date-text" x="${x(d)}" y="${h-14}" text-anchor="middle">${fmtDate(d)}</text>`);
  svg+='</svg>';
  $('projectChart').innerHTML=svg;

  const allButton=`<button class="legend-item ${selectedMetric==='all'?'active':''}" data-key="all"><span>Todas</span></button>`;
  $('projectLegend').innerHTML=allButton+allGroups.map(g=>{
    const latest=g.points[g.points.length-1],unit=METRICS[g.key].unit;
    return `<button class="legend-item ${selectedMetric===g.key?'active':''}" data-key="${g.key}"><i style="background:${COLORS[g.key]}"></i><span>${METRICS[g.key].label}</span><strong>${latest.value.toFixed(unit==='min'||unit==='índice'?0:1)} ${unit}</strong></button>`;
  }).join('');

  document.querySelectorAll('.legend-item').forEach(btn=>btn.addEventListener('click',()=>{
    selectedMetric=btn.dataset.key||'all';
    renderResearchChart(series);
  }));

  renderResearchSummary(series);
}

function renderGoalPaceChart(pace){
  const el=$('goalPaceChart');
  if(!el) return;
  const points=(pace?.series||[]).filter(x=>x.required_kg_per_week!=null);
  if(points.length<2){
    el.innerHTML='<span class="empty-chart">La curva aparecerá cuando existan al menos dos pesajes.</span>';
    return;
  }
  const vals=points.map(p=>Number(p.required_kg_per_week));
  const min=Math.min(...vals), max=Math.max(...vals), span=Math.max(max-min,0.1);
  const w=1050,h=230,l=48,r=18,t=18,b=38;
  const x=i=>l+(i/(points.length-1))*(w-l-r);
  const y=v=>t+((max-v)/span)*(h-t-b);
  const path=points.map((p,i)=>`${i?'L':'M'} ${x(i).toFixed(1)} ${y(Number(p.required_kg_per_week)).toFixed(1)}`).join(' ');
  let svg=`<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Ritmo semanal requerido para llegar a 90 kg">`;
  for(let i=0;i<=3;i++){
    const value=max-(i/3)*span, yy=y(value);
    svg+=`<line class="grid-line" x1="${l}" y1="${yy}" x2="${w-r}" y2="${yy}"></line><text class="axis-text" x="${l-8}" y="${yy+4}" text-anchor="end">${value.toFixed(2)}</text>`;
  }
  svg+=`<path class="goal-pace-line" d="${path}"></path>`;
  points.forEach((p,i)=>svg+=`<circle class="goal-pace-dot" cx="${x(i)}" cy="${y(Number(p.required_kg_per_week))}" r="${i===points.length-1?5:3}"><title>${fmtDate(p.date)}: ${Number(p.required_kg_per_week).toFixed(2)} kg/semana requeridos · peso ${Number(p.weight_kg).toFixed(1)} kg</title></circle>`);
  const labels=[0,Math.floor((points.length-1)/2),points.length-1].filter((v,i,a)=>a.indexOf(v)===i);
  labels.forEach(i=>svg+=`<text class="date-text" x="${x(i)}" y="${h-12}" text-anchor="middle">${fmtDate(points[i].date)}</text>`);
  svg+='</svg>';
  el.innerHTML=svg;
}

function renderGoalPace(d){
  const p=d.goal_pace||{};
  const required=p.required_kg_per_week;
  const actual=p.actual_kg_per_week;
  const diff=p.difference_to_target_kg;
  $('requiredWeeklyLoss').textContent=required==null?'—':num(required,2);
  $('paceCurrentWeight').textContent=p.current_weight_kg==null?'—':`${num(p.current_weight_kg,1)} kg`;
  $('paceRemainingWeight').textContent=p.remaining_kg==null?'—':`${num(p.remaining_kg,1)} kg`;
  $('paceTargetToday').textContent=p.target_weight_today==null?'—':`${num(p.target_weight_today,1)} kg`;

  if(actual==null) $('paceActualWeekly').textContent='Aún sin ritmo';
  else if(actual>0) $('paceActualWeekly').textContent=`Bajando ${num(actual,2)} kg/sem`;
  else if(actual<0) $('paceActualWeekly').textContent=`Subiendo ${num(Math.abs(actual),2)} kg/sem`;
  else $('paceActualWeekly').textContent='Sin cambio';

  if(required!=null && p.current_weight_kg!=null){
    $('goalPaceSentence').textContent=`Con ${num(p.current_weight_kg,1)} kg y ${p.days_left} días restantes, faltan ${num(p.remaining_kg,1)} kg para 90 kg. El ritmo matemático requerido desde hoy es ${num(required,2)} kg por semana.`;
  } else $('goalPaceSentence').textContent='Aún no hay datos suficientes para calcular el ritmo hacia la meta.';

  if(p.status==='meta_alcanzada') $('goalPaceStatus').textContent='La meta de 90 kg ya fue alcanzada.';
  else if(diff!=null && diff>0.3) $('goalPaceStatus').textContent=`Hoy estás ${num(diff,1)} kg por encima de la ruta lineal hacia 90 kg. El ritmo requerido se ajustó a ${num(required,2)} kg/semana.`;
  else if(diff!=null && diff<-0.3) $('goalPaceStatus').textContent=`Hoy estás ${num(Math.abs(diff),1)} kg por debajo de la ruta lineal. El ritmo requerido bajó a ${num(required,2)} kg/semana.`;
  else if(required!=null) $('goalPaceStatus').textContent=`El peso está cerca de la ruta calculada. Ritmo requerido actual: ${num(required,2)} kg/semana.`;
  else $('goalPaceStatus').textContent='—';

  renderGoalPaceChart(p);
}

function renderEnergyHistory(series){
  const rows=series.energy_history||[];
  $('energyHistoryRange').textContent=`${series.days} días`;
  const el=$('energyChart');
  if(!rows.length){
    el.innerHTML='<span class="empty-chart">Sin historial energético.</span>';
    $('energyHistorySummary').textContent='Aún no hay datos suficientes.';
    return;
  }
  const usable=rows.filter(r=>r.accounted_expenditure_kcal!=null || r.intake_kcal!=null);
  if(!usable.length){
    el.innerHTML='<span class="empty-chart">Sin valores energéticos calculables.</span>';
    return;
  }

  const seriesDefs=[
    {key:'accounted_expenditure_kcal',label:'Gasto contabilizado',cls:'energy-line-spend'},
    {key:'intake_kcal',label:'Ingesta',cls:'energy-line-intake'}
  ];
  const values=usable.flatMap(r=>seriesDefs.map(s=>r[s.key]).filter(v=>v!=null).map(Number));
  const min=Math.max(0,Math.min(...values)-150),max=Math.max(...values)+150,span=Math.max(max-min,100);
  const w=1050,h=280,l=56,r=20,t=20,b=42;
  const x=i=>l+(usable.length===1?0.5:i/(usable.length-1))*(w-l-r);
  const y=v=>t+((max-v)/span)*(h-t-b);
  let svg=`<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Historial diario de calorías">`;
  for(let i=0;i<=4;i++){
    const value=max-(i/4)*span,yy=y(value);
    svg+=`<line class="grid-line" x1="${l}" y1="${yy}" x2="${w-r}" y2="${yy}"></line><text class="axis-text" x="${l-8}" y="${yy+4}" text-anchor="end">${Math.round(value)}</text>`;
  }
  seriesDefs.forEach(s=>{
    const pts=usable.map((row,i)=>({i,value:row[s.key]})).filter(p=>p.value!=null);
    if(!pts.length) return;
    const path=pts.map((p,j)=>`${j?'L':'M'} ${x(p.i).toFixed(1)} ${y(Number(p.value)).toFixed(1)}`).join(' ');
    svg+=`<path class="${s.cls}" d="${path}"></path>`;
    pts.forEach(p=>svg+=`<circle class="${s.cls}-dot" cx="${x(p.i)}" cy="${y(Number(p.value))}" r="3"><title>${s.label}: ${Math.round(Number(p.value))} kcal · ${fmtDate(usable[p.i].date)}</title></circle>`);
  });
  const labels=[0,Math.floor((usable.length-1)/2),usable.length-1].filter((v,i,a)=>a.indexOf(v)===i);
  labels.forEach(i=>svg+=`<text class="date-text" x="${x(i)}" y="${h-12}" text-anchor="middle">${fmtDate(usable[i].date)}</text>`);
  svg+='</svg>';
  el.innerHTML=svg;

  const last=usable[usable.length-1];
  const parts=[];
  if(last.accounted_expenditure_kcal!=null) parts.push(`Gasto contabilizado: ${Math.round(last.accounted_expenditure_kcal)} kcal`);
  if(last.intake_kcal!=null) parts.push(`ingesta: ${Math.round(last.intake_kcal)} kcal`);
  if(last.balance_kcal!=null) parts.push(`${last.balance_kcal<0?'déficit':'superávit'} parcial: ${Math.round(Math.abs(last.balance_kcal))} kcal`);
  $('energyHistorySummary').textContent=`${fmtDate(last.date)} · ${parts.join(' · ')}.`;
}

function renderEnergy(d){
  const e=d.interpretation?.energy||{};
  const resting=e.resting_kcal_day;
  const restingChange=e.resting_change_kcal_day;
  const activity=e.activity_kcal;
  const activityMin=e.activity_minutes;
  const accounted=e.accounted_expenditure_kcal;
  const intake=e.intake_kcal;
  const balance=e.partial_balance_kcal;

  $('restingEnergy').textContent=resting==null?'—':`${Math.round(resting)} kcal/día`;
  $('restingEnergyValue').textContent=resting==null?'—':`${Math.round(resting)} kcal/día`;
  $('restingEnergyChange').textContent=restingChange==null?'Primera estimación':`${restingChange>0?'+':''}${Math.round(restingChange)} kcal/día vs. medición anterior`;
  $('activityEnergy').textContent=activity==null?'Sin registro':`≈ ${Math.round(activity)} kcal`;
  $('activityEnergyMinutes').textContent=activityMin==null?'No hay actividad cargada ese día':`${Math.round(activityMin)} min registrados`;
  $('accountedEnergy').textContent=accounted==null?'—':`${Math.round(accounted)} kcal`;
  $('intakeEnergy').textContent=intake==null?'Sin registro':`${Math.round(intake)} kcal`;

  if(balance==null) $('energyBalance').textContent='Sin balance calculable';
  else if(balance<0) $('energyBalance').textContent=`Déficit parcial: ${Math.round(Math.abs(balance))} kcal`;
  else if(balance>0) $('energyBalance').textContent=`Superávit parcial: ${Math.round(balance)} kcal`;
  else $('energyBalance').textContent='Balance parcial: 0 kcal';

  const lean=e.lean_mass_est_kg;
  const method=e.resting_method;
  if($('metabolismMethod')) $('metabolismMethod').textContent=method==='mifflin_st_jeor'?'Peso + estatura + edad':'Composición corporal';
  const parts=[];
  if(resting!=null) parts.push(`Con la composición actual, el gasto en reposo estimado es ${Math.round(resting)} kcal/día`);
  if(restingChange!=null) parts.push(`cambió ${restingChange>0?'+':''}${Math.round(restingChange)} kcal/día desde la medición anterior`);
  if(lean!=null) parts.push(`masa libre de grasa estimada: ${num(lean,1)} kg`);
  if(activity!=null) parts.push(`actividad registrada: ≈${Math.round(activity)} kcal`);
  if(intake!=null) parts.push(`ingesta: ${Math.round(intake)} kcal`);
  if(balance!=null) parts.push(`${balance<0?'déficit':'superávit'} parcial: ${Math.round(Math.abs(balance))} kcal`);
  $('energySummary').textContent=parts.length?parts.join(' · ')+'.':'Sin datos suficientes para calcular el estado energético.';
}

function renderInterpretation(d){
  const a=d.interpretation;
  if(!a) return;
  const compared=a.confidence?.variables_compared??0;
  $('analysisConfidence').textContent=`${compared} variables cruzadas`;
  $('analysisPeriod').textContent=a.compared_with
    ? `Comparación: ${a.compared_with} → ${a.as_of}`
    : `Fecha de referencia: ${a.as_of||'sin datos'}`;
  $('analysisHeadline').textContent=a.headline||'Sin interpretación disponible.';
  $('analysisSummary').textContent=a.summary||'';

  const kindLabels={
    observado:'Dato observado',
    estimado_por_dispositivo:'Estimación de báscula',
    derivado:'Cálculo derivado'
  };
  const observations=a.observations||[];
  $('analysisObservations').innerHTML=observations.length?observations.map(o=>{
    const last=o.delta==null?'Sin comparación anterior':naturalChange(o.key,o.previous,o.current,o.unit);
    const base=(o.baseline==null || o.current==null || Number(o.baseline)===Number(o.previous))?'':` · Inicio ${num(o.baseline,1)} ${o.unit} → ahora ${num(o.current,1)} ${o.unit}`;
    return `<div class="analysis-observation">
      <span>${escapeHtml(o.label)}</span>
      <strong>${escapeHtml(num(o.current,2))} ${escapeHtml(o.unit)}</strong>
      <small>${escapeHtml(last+base)}</small>
      <small class="analysis-kind">${escapeHtml(kindLabels[o.kind]||o.kind)}</small>
    </div>`;
  }).join(''):'<p class="plain-note">Sin variables corporales comparables.</p>';

  const findings=a.hypotheses||[];
  $('analysisHypotheses').innerHTML=findings.length?findings.map(h=>`<div class="analysis-hypothesis">
    <div class="analysis-hypothesis-head">
      <strong>${escapeHtml(h.label)}</strong>
      <span class="analysis-confidence">Dato cruzado</span>
    </div>
    <p>${escapeHtml(h.explanation)}</p>
  </div>`).join(''):'<p class="plain-note">No hay un cambio corporal adicional que explicar todavía.</p>';

  const connections=a.connections||[];
  const fallback=a.context_findings||[];
  $('analysisContext').innerHTML=connections.length
    ? `<strong>Relaciones calculadas</strong>${connections.map(x=>`<span><b>${escapeHtml(x.label)}:</b> ${escapeHtml(x.explanation)}</span>`).join('')}`
    : fallback.length
      ? `<strong>Datos relacionados</strong>${fallback.map(x=>`<span>${escapeHtml(x)}</span>`).join('')}`
      : '';

  $('analysisDecisionNote').textContent=a.decision_note||'';
  $('analysisLimits').innerHTML=`<ul>${(a.limits||[]).map(x=>`<li>${escapeHtml(x)}</li>`).join('')}</ul>`;
}

function renderComposition(series, interpretation=null){
  const latestMessages=interpretation?.metric_messages||{};
  const rangeSummaries=series.analysis?.metric_summaries||{};
  const cfg=[
    ['body_fat_pct','bodyFat','bodyFatStart','bodyFatChange','bodyFatChart','bodyFatText','bodyFatPeriod','%'],
    ['muscle_mass_kg','muscleMass','muscleStart','muscleChange','muscleChart','muscleText','musclePeriod','kg'],
    ['body_water_pct','bodyWater','waterStart','waterChange','waterChart','waterText','waterPeriod','%'],
    ['visceral_fat_index','visceralFat','visceralStart','visceralChange','visceralChart','visceralText','visceralPeriod','índice']
  ];
  $('compositionPeriodNote').textContent=`Período visible: ${series.analysis?.from_date||'—'} → ${series.analysis?.to_date||'—'}`;

  cfg.forEach(([key,currentId,startId,changeId,chartId,textId,periodId,unit])=>{
    const p=metricPoints(series,key);
    if(!p.length){
      $(currentId).textContent='—';
      $(startId).textContent='—';
      $(changeId).textContent='—';
      $(periodId).textContent='Sin registros en el período.';
      $(textId).textContent='Sin comparación disponible.';
      sparkline($(chartId),[]);
      return;
    }
    const first=p[0].value,last=p[p.length-1].value,diff=last-first;
    $(currentId).textContent=`${num(last)} ${unit}`;
    $(startId).textContent=`${num(first)} ${unit}`;
    $(changeId).textContent=naturalChange(key,first,last,unit);
    $(periodId).textContent=latestMessages[key]||rangeSummaries[key]?.headline||`${METRICS[key].label}: ${num(last)} ${unit}.`;
    $(textId).textContent=rangeSummaries[key]?.headline||'Sin una segunda lectura en el período.';
    sparkline($(chartId),p);
  });
}

function renderSleep(series){
  const p=metricPoints(series,'sleep_hours');
  const summary=series.analysis?.metric_summaries?.sleep_hours;
  if(!p.length){
    $('sleep').textContent='—';
    $('sleepAvg').textContent='—';
    $('sleepInterpretation').textContent='Sin registros de sueño en el período.';
    sparkline($('sleepMiniChart'),[]);
    return;
  }
  const last=p[p.length-1].value;
  const recent=p.slice(-7),avg=recent.reduce((a,b)=>a+b.value,0)/recent.length;
  $('sleep').textContent=`${num(last)} h`;
  $('sleepAvg').textContent=`${num(avg)} h`;
  sparkline($('sleepMiniChart'),p,{targetMin:7,targetMax:9});
  $('sleepInterpretation').textContent=summary?.headline||`Sueño: ${num(last)} h en el último registro.`;
}

function renderWeight(d, series){
  $('weight').textContent=`${num(d.current_weight_kg)} kg`;
  $('weightStart').textContent=`${num(d.baseline_weight_kg)} kg`;
  $('weightChange').textContent=naturalChange('weight_kg',d.baseline_weight_kg,d.current_weight_kg,'kg');
  $('weightAvg').textContent=`${num(d.moving_avg_7d_kg)} kg`;
  $('goalWeight').textContent=`${num(d.goal_weight_kg)} kg`;

  const total=Math.max((d.baseline_weight_kg||0)-(d.goal_weight_kg||0),0.1);
  const done=Math.max((d.baseline_weight_kg||0)-(d.current_weight_kg||0),0);
  $('weightProgress').style.width=`${Math.min(100,Math.max(0,(done/total)*100))}%`;

  const rangeSummary=series.analysis?.metric_summaries?.weight_kg;
  $('weightStatus').textContent=rangeSummary?.sample_count>=2
    ? naturalChange('weight_kg',rangeSummary.first,rangeSummary.current,'kg')
    : 'Sin comparación suficiente';
  $('weightExplanation').textContent=rangeSummary?.headline
    || d.interpretation?.metric_messages?.weight_kg
    || 'Sin una medición anterior comparable.';
}

const PROJECT_START = new Date('2026-09-22T00:00:00-05:00');
const PROJECT_END = new Date('2027-02-01T00:00:00-05:00');
const PROJECT_TOTAL_DAYS = 132;

function updateCountdown(){
  const el=$('countdown'); if(!el) return;
  const ms=Math.max(0,PROJECT_END-new Date());
  const days=Math.floor(ms/86400000);
  const hours=Math.floor((ms%86400000)/3600000);
  const minutes=Math.floor((ms%3600000)/60000);
  const seconds=Math.floor((ms%60000)/1000);
  el.textContent=ms>0?`${days}d ${String(hours).padStart(2,'0')}h ${String(minutes).padStart(2,'0')}m ${String(seconds).padStart(2,'0')}s`:'META · 1 FEB 2027';
}

function renderStudy(d){
  const now=new Date();
  const elapsed=Math.max(0,Math.min(PROJECT_TOTAL_DAYS,Math.floor((now-PROJECT_START)/86400000)+1));
  const remaining=Math.max(0,Math.ceil((PROJECT_END-now)/86400000));
  $('day').textContent=`Día ${elapsed} de ${PROJECT_TOTAL_DAYS}`;
  $('remaining').textContent=remaining;
  $('tripNote').textContent='Fecha objetivo del proyecto: 1 de febrero de 2027.';
  updateCountdown();
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
    const [dashboard,series,activities,profile]=await Promise.all([
      api('/api/dashboard'),
      api(`/api/project-series?days=${days}`),
      api('/api/activities?limit=250'),
      api('/api/profile')
    ]);
    if(profile){
      if($('profileHeight')) $('profileHeight').value=profile.height_cm??'';
      if($('profileAge')) $('profileAge').value=profile.age_years??'';
      if($('profileSex')) $('profileSex').value=profile.sex??'';
    }
    renderWeight(dashboard,series);
    renderGoalPace(dashboard);
    renderStudy(dashboard);
    renderActivity(activities,series);
    renderSleep(series);
    renderComposition(series,dashboard.interpretation);
    renderResearchChart(series);
    renderInterpretation(dashboard);
    renderEnergy(dashboard);
    renderEnergyHistory(series);
    renderAlerts(dashboard);
    $('sync').textContent=`Actualizado ${new Date().toLocaleTimeString('es-CO',{hour:'2-digit',minute:'2-digit'})}`;
  }catch(e){
    $('sync').textContent='Sin conexión';
    $('projectChart').innerHTML=`<span>Error al cargar: ${e.message}</span>`;
  }
}

document.querySelectorAll('.workspace-tab').forEach(btn=>btn.addEventListener('click',()=>{
  const name=btn.dataset.tab;
  document.querySelectorAll('.workspace-tab').forEach(x=>x.classList.toggle('active',x===btn));
  document.querySelectorAll('.workspace-view').forEach(view=>{
    const active=view.id===`tab-${name}`;
    view.classList.toggle('active',active);
    view.hidden=!active;
  });
}));

const profileForm=$('profileForm');
if(profileForm) profileForm.addEventListener('submit',async event=>{
  event.preventDefault();
  const payload={
    height_cm:Number($('profileHeight').value),
    age_years:Number($('profileAge').value),
    sex:$('profileSex').value
  };
  try{
    $('profileStatus').textContent='Guardando…';
    await api('/api/profile',{method:'PUT',body:JSON.stringify(payload)});
    $('profileStatus').textContent='Perfil guardado. El gasto en reposo fue recalculado.';
    await load(Number(document.querySelector('.range-btn.active')?.dataset.days||14));
  }catch(e){
    $('profileStatus').textContent=`No se pudo guardar: ${e.message}`;
  }
});

const nutritionDate=$('nutritionDate');
if(nutritionDate) nutritionDate.value=todayKey();
const nutritionForm=$('nutritionForm');
if(nutritionForm) nutritionForm.addEventListener('submit',async event=>{
  event.preventDefault();
  const day=$('nutritionDate').value||todayKey();
  const read=id=>{const v=$(id).value;return v===''?null:Number(v);};
  const payload={
    nutrition_date:day,
    calories:read('nutritionCalories'),
    protein_g:read('nutritionProtein'),
    fat_g:read('nutritionFat'),
    carbs_g:read('nutritionCarbs'),
    source:'web'
  };
  try{
    $('nutritionStatus').textContent='Guardando…';
    await api(`/api/nutrition/${day}`,{method:'PUT',body:JSON.stringify(payload)});
    $('nutritionStatus').textContent='Día guardado. El balance fue recalculado.';
    await load(Number(document.querySelector('.range-btn.active')?.dataset.days||14));
  }catch(e){
    $('nutritionStatus').textContent=`No se pudo guardar: ${e.message}`;
  }
});

document.querySelectorAll('.range-btn').forEach(btn=>btn.addEventListener('click',()=>{
  document.querySelectorAll('.range-btn').forEach(x=>x.classList.remove('active'));
  btn.classList.add('active');
  load(Number(btn.dataset.days));
}));

load(14);
updateCountdown();
setInterval(updateCountdown,1000);
setInterval(()=>load(Number(document.querySelector('.range-btn.active')?.dataset.days||14)),60000);
