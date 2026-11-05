/* Vehicle Trails: exact matches, explicit near-match review, and camera-wise routes. */
(() => {
'use strict';
window.vehicleTrailReviewMode=true;
const esc = value => String(value ?? '').replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let rows=[], busy=false, filter='all', query='', selectedPlate=null, map=null, layers=[], routeVersion=0, lastRouteSignature='', lastListSignature='';
const matched = row => ['EXACT','SAME'].includes(row.status);
const status = row => ({EXACT:'Exact match · Auto added',PENDING:'Near match · Review needed',SAME:'Same · Confirmed',NOT_SAME:'Not Same · Normal detection',NORMAL:'Normal detection'}[row.status]||row.status);
const image = (url,label) => url ? `<img class="vtr-photo" src="${esc(url)}" alt="${esc(label)}" loading="lazy" role="button" tabindex="0" title="Click to enlarge image" aria-label="Enlarge ${esc(label)}">` : '<div class="vtr-no-photo">Photo unavailable</div>';
// Delegate so polling can replace review cards without losing zoom actions.
function enlargeReviewPhoto(event){
 const photo=event.target.closest?.('img.vtr-photo');
 if(!photo)return;
 if(event.type==='keydown'&&!['Enter',' '].includes(event.key))return;
 event.preventDefault();
 window.openImageZoomModal?.(photo.currentSrc||photo.src,photo.alt);
}
document.addEventListener('click',enlargeReviewPhoto);
document.addEventListener('keydown',enlargeReviewPhoto);
function render(){
 const host=document.getElementById('vtrList');if(!host)return;
 const pending=rows.filter(r=>r.status==='PENDING');
 const trailCount=new Set(rows.filter(r=>r.status!=='PENDING').map(r=>r.route_plate)).size;
 const trailBadge=document.getElementById('trailVehiclesCountBadge');if(trailBadge)trailBadge.textContent=`${trailCount} trails`;
 const navBadge=document.getElementById('navMasterTrailBadge');if(navBadge)navBadge.textContent=String(trailCount);
 document.getElementById('vtrPendingCount').textContent=String(pending.length);
 const bellBadge=document.getElementById('alertBellBadge');if(bellBadge){bellBadge.textContent=String(pending.length);bellBadge.style.display=pending.length?'inline-block':'none';}
 document.getElementById('vtrSummary').textContent=`${rows.filter(matched).length} matched sightings · ${pending.length} need review · ${rows.filter(r=>r.status==='NORMAL'||r.status==='NOT_SAME').length} normal sightings`;
 let visible=rows.filter(r=>(filter==='all'||filter==='pending'&&r.status==='PENDING'||filter==='matched'&&matched(r)||filter==='normal'&&['NORMAL','NOT_SAME'].includes(r.status))&&`${r.detected_plate} ${r.route_plate} ${r.location||''}`.toLowerCase().includes(query));
 const reviews=visible.filter(r=>r.status==='PENDING');
 const groups=new Map();visible.filter(r=>r.status!=='PENDING').forEach(r=>{if(!groups.has(r.route_plate))groups.set(r.route_plate,[]);groups.get(r.route_plate).push(r);});
 const nextHtml=reviews.map(r=>`<article class="vtr-card vtr-pending"><div class="vtr-card-head"><strong>Check if these are the same vehicle</strong><span class="vtr-badge">Review needed</span></div><div class="vtr-compare"><div><span class="vtr-label">Detected number</span><strong class="vtr-number">${esc(r.detected_plate)}</strong>${image(r.plate_photo,'Detected plate')}${image(r.vehicle_photo,'Detected vehicle')}</div><div><span class="vtr-label">Registered number</span><strong class="vtr-number">${esc(r.candidate_plate)}</strong>${image(r.candidate_photo,'Registered vehicle')}<p>Similarity: ${Math.round(r.similarity*100)}% · OCR: ${esc(r.confidence)}%</p></div></div><p>${esc(r.location||'Camera unavailable')} · ${esc(r.captured_at)}${r.camera_id?' · '+esc(r.camera_id):''}</p><div class="vtr-actions"><button type="button" class="btn btn-primary" data-decision="SAME" data-id="${r.id}">Same vehicle</button><button type="button" class="btn btn-secondary" data-decision="NOT_SAME" data-id="${r.id}">Different vehicle</button></div></article>`).join('')+
 [...groups.entries()].map(([plate,sightings])=>{const newest=sightings[0],cameras=new Set(sightings.map(r=>r.camera_id).filter(Boolean));return `<article class="vtr-card"><div class="vtr-card-head"><strong class="vtr-number">${esc(plate)}</strong><span class="vtr-badge ${sightings.some(matched)?'vtr-matched':''}">${sightings.some(matched)?'Watchlist vehicle':'Normal vehicle'}</span></div><p>${sightings.length} sightings · ${cameras.size} registered cameras · Latest: ${esc(newest.location||'Unknown location')}</p><p>${esc(status(newest))}</p><button class="btn btn-secondary" data-route="${esc(plate)}">View trail</button></article>`;}).join('')||'<p class="vtr-empty">No sightings in this view. Camera detections will appear here automatically.</p>';
 if(nextHtml!==lastListSignature){host.innerHTML=nextHtml;lastListSignature=nextHtml;}
 document.querySelectorAll('[data-vtr-filter]').forEach(b=>b.classList.toggle('active',b.dataset.vtrFilter===filter));
 if(selectedPlate){const signature=JSON.stringify(rows.filter(r=>r.route_plate===selectedPlate));if(signature!==lastRouteSignature){lastRouteSignature=signature;renderRoute(selectedPlate);}}
}
async function refresh(){
 if(busy)return;busy=true;
 try{const res=await fetch('/api/vehicle-trails/observations');if(!res.ok)throw new Error(res.status===401?'Sign in to view vehicle trails':'Could not load vehicle trails');const data=await res.json();rows=data.observations||[];render();document.getElementById('vtrError').textContent='';}
 catch(e){const error=document.getElementById('vtrError');if(error)error.textContent=e.message;}
 finally{busy=false;}
}
async function decide(id,decision,button){
 const card=button.closest('.vtr-card');card.querySelectorAll('button').forEach(b=>b.disabled=true);
 try{const res=await fetch(`/api/vehicle-trails/observations/${id}/decision`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({decision,detected_plate:rows.find(r=>r.id===id)?.detected_plate,candidate_plate:rows.find(r=>r.id===id)?.candidate_plate})});const data=await res.json();if(!res.ok)throw new Error(data.detail||'Review could not be saved');rows=rows.map(r=>r.id===id?data.observation:r);render();document.getElementById('vtrFeedback').textContent=decision==='SAME'?'Same confirmed. Added to the registered vehicle trail.':'Not Same saved. Kept as a normal detection with its own trail.';await refresh();}
 catch(e){document.getElementById('vtrError').textContent=e.message;card.querySelectorAll('button').forEach(b=>b.disabled=false);}
}
function addRouteArrows(linePts, count = 3) {
 if (!linePts || linePts.length < 2) return;
 let totalDist = 0, dists = [];
 for (let i = 0; i < linePts.length - 1; i++) {
  const d = Math.hypot(linePts[i + 1][0] - linePts[i][0], linePts[i + 1][1] - linePts[i][1]);
  dists.push(d);
  totalDist += d;
 }
 if (!totalDist) return;
 const targets = [];
 for (let k = 0; k < count; k++) targets.push(totalDist * (k + 1) / (count + 1));
 targets.forEach(target => {
  let cur = 0;
  for (let i = 0; i < dists.length; i++) {
   if (cur + dists[i] >= target || i === dists.length - 1) {
    const p1 = linePts[i], p2 = linePts[i + 1];
    const ratio = dists[i] > 0 ? Math.max(0, Math.min(1, (target - cur) / dists[i])) : 0.5;
    const lat = p1[0] + (p2[0] - p1[0]) * ratio, lng = p1[1] + (p2[1] - p1[1]) * ratio;
    const deg = Math.round(Math.atan2(p2[1] - p1[1], p2[0] - p1[0]) * 180 / Math.PI);
    const arrowIcon = L.divIcon({
     className: 'vtr-direction-arrow',
     html: `<div style="transform:rotate(${deg}deg);width:22px;height:22px;display:flex;align-items:center;justify-content:center;filter:drop-shadow(0 1px 3px rgba(0,0,0,0.45));"><svg width="18" height="18" viewBox="0 0 24 24"><polygon points="12,2 22,22 12,17 2,22" fill="#ef4444" stroke="#ffffff" stroke-width="1.8"/></svg></div>`,
     iconSize: [22, 22],
     iconAnchor: [11, 11]
    });
    layers.push(L.marker([lat, lng], { icon: arrowIcon, interactive: false }).addTo(map));
    break;
   }
   cur += dists[i];
  }
 });
}
async function renderRoute(plate){
 const version=++routeVersion,section=document.getElementById('vtrRoute');section.hidden=false;
 const sightings=rows.filter(r=>r.route_plate===plate&&r.status!=='PENDING').sort((a,b)=>a.epoch-b.epoch||a.id-b.id);
 document.getElementById('vtrRouteTitle').textContent=`Vehicle trail · ${plate}`;
 document.getElementById('vtrTimeline').innerHTML=sightings.map((r,i)=>`<li><strong>${i+1}. ${esc(r.location||'Location not registered')}</strong> · ${esc(r.captured_at)}<br><span>${esc(r.camera_id||'No registered camera')} · Detected: ${esc(r.detected_plate)} · ${esc(status(r))}</span></li>`).join('');
 const points=sightings.filter(r=>Number.isFinite(r.lat)&&Number.isFinite(r.lng));
 const caption=document.getElementById('vtrRouteCaption');
 if(!window.L){caption.textContent='Map could not load. The chronological sightings remain available below.';return;}
 if(!map){map=L.map('vtrMap').setView([29.695,76.985],13);L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© OpenStreetMap contributors'}).addTo(map);}
 layers.forEach(layer=>map.removeLayer(layer));layers=[];
 const locations=new Map();points.forEach((r,i)=>{const key=`${r.lat},${r.lng}`;if(!locations.has(key))locations.set(key,[]);locations.get(key).push({...r,order:i+1});});
 locations.forEach(group=>{
  const first=group[0];
  const isFirst=group.some(r=>r.order===1);
  const isLatest=group.some(r=>r.order===points.length);
  const markerColor=isLatest?'#ef4444':isFirst?'#10b981':'#2563eb';
  const marker=L.circleMarker([first.lat,first.lng],{radius:9,color:markerColor,fillColor:markerColor,fillOpacity:.85,weight:2}).addTo(map);
  marker.bindTooltip(group.map(r=>`${r.order}. ${r.location}`).join(' • '));
  marker.bindPopup(group.map(r=>`<strong>${r.order}. ${esc(r.location)}</strong><br>${esc(r.camera_id)}<br>${esc(r.captured_at)}`).join('<hr>'),{maxHeight:240,maxWidth:300,autoPanPadding:[24,24]});
  layers.push(marker);
 });
 const path=[];points.forEach(r=>{const point=[r.lat,r.lng];if(!path.length||String(path[path.length-1])!==String(point))path.push(point);});
 caption.textContent=points.length===0?'No registered camera coordinates for these sightings.':locations.size===1?'Vehicle seen at one camera location. No road route can be inferred from one location.':'Dashed line shows camera detection order. A suggested road route is loading; it is not proof of the actual travelled path.';
 if(path.length>1){
  layers.push(L.polyline(path,{color:'#64748b',weight:2,dashArray:'7 7'}).addTo(map));
  addRouteArrows(path, Math.min(path.length, 3));
 }
 requestAnimationFrame(()=>{map.invalidateSize();if(points.length)map.fitBounds(points.map(r=>[r.lat,r.lng]),{padding:[25,25],maxZoom:16});});
 if(path.length>1&&path.length<=25){
  try{const coords=path.map(p=>`${p[1]},${p[0]}`).join(';');const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),10000);let res;try{res=await fetch(`https://router.project-osrm.org/route/v1/driving/${coords}?overview=full&geometries=geojson&steps=false`,{signal:controller.signal});}finally{clearTimeout(timeout);}const data=await res.json();if(version!==routeVersion)return;const road=data.routes?.[0];if(!road)throw new Error('No road route');layers.push(L.geoJSON(road.geometry,{style:{color:'#2563eb',weight:4}}).addTo(map));
   if(road.geometry&&road.geometry.coordinates){
    const roadCoords=road.geometry.coordinates.map(c=>[c[1],c[0]]);
    addRouteArrows(roadCoords, Math.max(3, Math.min(8, path.length * 2)));
   }caption.textContent=`Suggested road route: ${(road.distance/1000).toFixed(1)} km. Pins are observed camera locations; the road path is estimated.`;}
  catch(e){if(version===routeVersion)caption.textContent='Camera pins and detection order are shown. Suggested road routing is unavailable; the dashed line is not an observed road path.';}
 }else if(path.length>25)caption.textContent='Camera pins and detection order are shown. Road routing supports up to 25 consecutive locations.';
}
function init(){
 const view=document.getElementById('subviewVehicleTrail');if(!view)return;
 const panel=document.createElement('section');panel.id='vehicleTrailReviewPanel';panel.innerHTML=`<div class="vtr-heading"><h3>Vehicle trails</h3><button type="button" class="btn btn-danger" id="vtrClear">Clear entries</button><button type="button" class="btn btn-secondary" id="vtrRefresh">Refresh</button></div><p id="vtrSummary">Loading camera sightings…</p><div class="vtr-toolbar"><input type="search" id="vtrSearch" aria-label="Search vehicle trails" placeholder="Search number or camera…"><button class="filter-btn active" data-vtr-filter="all">All trails</button><button class="filter-btn" data-vtr-filter="pending">Needs review <span id="vtrPendingCount">0</span></button><button class="filter-btn" data-vtr-filter="matched">Watchlist matched</button></div><p id="vtrError" role="status"></p><p id="vtrFeedback" role="status"></p><section id="vtrRoute" hidden><div class="vtr-heading"><h4 id="vtrRouteTitle"></h4><button class="btn btn-secondary" data-close-route>Close map</button></div><p id="vtrRouteCaption"></p><div id="vtrMap"></div><ol id="vtrTimeline"></ol></section><div id="vtrList"></div>`;
 // Keep the previous registered-vehicle history available below the new workflow.
 const legacy=document.createElement('details');legacy.className='vtr-legacy';legacy.innerHTML='<summary>Registered vehicle history & filters</summary>';while(view.firstChild)legacy.append(view.firstChild);view.append(panel,legacy);
 panel.addEventListener('click',e=>{const button=e.target.closest('button');if(!button)return;if(button.dataset.decision)decide(Number(button.dataset.id),button.dataset.decision,button);else if(button.dataset.route){selectedPlate=button.dataset.route;lastRouteSignature=JSON.stringify(rows.filter(r=>r.route_plate===selectedPlate));renderRoute(selectedPlate);document.getElementById('vtrRoute').scrollIntoView({behavior:'smooth',block:'start'});}else if(button.hasAttribute('data-close-route')){selectedPlate=null;routeVersion++;document.getElementById('vtrRoute').hidden=true;}else if(button.dataset.vtrFilter){filter=button.dataset.vtrFilter;render();}});
 document.getElementById('vtrSearch').addEventListener('input',e=>{query=e.target.value.trim().toLowerCase();render();});
 document.getElementById('vtrRefresh').addEventListener('click',refresh);
 document.getElementById('vtrClear').addEventListener('click',async e=>{
  if(busy)return;
  if(!rows.length){alert('No trail entries to clear.');return;}
  if(!confirm(`Clear all ${rows.length} vehicle trail and review entries in your account scope? This includes all filters. Registry and captured vehicles stay unchanged. This cannot be undone.`))return;
  const button=e.currentTarget;button.disabled=true;busy=true;
  try{
   const res=await fetch('/api/vehicle-trails/observations',{method:'DELETE'});
   if(!res.ok)throw new Error(res.status===405||res.status===404?'Clear entries is not active on the server. Restart the backend and refresh this page.':res.status===401?'Please sign in again to clear entries.':'Could not clear trail entries. Please retry.');
   const data=await res.json();rows=[];selectedPlate=null;routeVersion++;lastRouteSignature='';
   document.getElementById('vtrRoute').hidden=true;render();
   document.getElementById('vtrFeedback').textContent=`${data.deleted_count} entries cleared.`;
   document.getElementById('vtrError').textContent='';
  }catch(error){document.getElementById('vtrError').textContent=error.message;}
  finally{busy=false;button.disabled=false;}
 });
 const viewPanel=document.getElementById('viewMasterTrail');new MutationObserver(()=>{if(viewPanel.style.display!=='none')refresh();}).observe(viewPanel,{attributes:true,attributeFilter:['style']});
 document.getElementById('btnAlertBell')?.addEventListener('click',e=>{e.preventDefault();e.stopImmediatePropagation();filter='pending';window.switchTab?.('master-trail');refresh();render();},true);
 window.refreshVehicleTrailReview=refresh;
 setInterval(()=>{if(!document.hidden&&viewPanel.style.display!=='none')refresh();},5000);
 refresh();
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
