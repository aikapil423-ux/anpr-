/* Shared Karnal camera selection: live slots, evidence uploads and vehicle trails. */
window.KARNAL_CAMERA_MODE = true;
(() => {
    'use strict';
    let registry = null;
    let cameraMap = null;
    let pickerMarker = null;
    let pickerFile = null;
    let trailMap = null;
    let trailLayers = [];
    let cameraChoice = null;
    const liveAssignments = {};
    const byId = id => registry?.cameras.find(c => c.id === id);
    const byName = name => registry?.cameras.find(c => c.name.toLowerCase() === String(name || '').trim().toLowerCase());
    const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
    const gps = c => `${c.lat}, ${c.lng}`;

    function picker(id, title, onChange) {
        const group = document.createElement('div');
        group.className = 'knl-picker';
        group.innerHTML = `<label id="${id}Label">${esc(title)}</label><div class="knl-combo"><button type="button" class="knl-combo-trigger" aria-labelledby="${id}Label ${id}Value" aria-expanded="false" aria-controls="${id}Panel"><span id="${id}Value">Select Karnal camera…</span><span aria-hidden="true">▾</span></button><div class="knl-combo-panel" id="${id}Panel" hidden><input type="search" aria-label="Search ${esc(title)}" placeholder="Search camera / location…" autocomplete="off"><select id="${id}" size="7" required aria-label="${esc(title)}"></select></div></div><span class="knl-coords">Choose the actual camera; no location is assigned automatically.</span>`;
        const search = group.querySelector('input');
        const select = group.querySelector('select');
        const trigger = group.querySelector('.knl-combo-trigger');
        const panel = group.querySelector('.knl-combo-panel');
        const valueLabel = group.querySelector(`#${id}Value`);
        const close = () => {panel.hidden=true;trigger.setAttribute('aria-expanded','false');};
        trigger.addEventListener('click', () => {
            const opening=panel.hidden;panel.hidden=!opening;trigger.setAttribute('aria-expanded',String(opening));
            if(opening){search.value='';populate();search.focus();}
        });
        group.addEventListener('keydown',event=>{
            if(event.key==='Escape'){close();trigger.focus();}
            if(event.key==='ArrowDown'&&event.target===search){event.preventDefault();select.focus();}
            if(event.key==='Enter'&&event.target===select){event.preventDefault();select.dispatchEvent(new Event('change'));trigger.focus();}
        });
        document.addEventListener('click',event=>{if(!group.contains(event.target))close();});
        let previewButton = null;
        if (id !== 'knlMapCamera') {
            previewButton = document.createElement('button');
            previewButton.type = 'button';
            previewButton.className = 'knl-map-button';
            previewButton.textContent = 'Map par dekhein';
            previewButton.disabled = true;
            previewButton.style.justifySelf = 'start';
            previewButton.onclick = () => openMap(null, false, select.value);
            group.append(previewButton);
        }
        function populate() {
            const selected = select.value;
            const term = search.value.trim().toLowerCase();
            const cameras = registry.cameras.filter(c => `${c.name} ${c.id}`.toLowerCase().includes(term) || c.id === selected);
            select.innerHTML = '<option value="">Select Karnal camera…</option>' + cameras.map(c => `<option value="${esc(c.id)}">${esc(c.name)} · ${esc(c.id)}</option>`).join('');
            select.value = selected;
        }
        search.addEventListener('input', populate);
        select.addEventListener('change', () => {
            const camera = byId(select.value);
            valueLabel.textContent=camera ? `${camera.name} · ${camera.id}` : 'Select Karnal camera…';
            close();
            if (previewButton) previewButton.disabled = !camera;
            group.querySelector('.knl-coords').textContent = camera ? `${gps(camera)} · ICCC, Karnal · Shared site GPS` : 'Choose the actual camera.';
            onChange?.(camera);
        });
        populate();
        return group;
    }

    function selectedUpload(options) {
        return byId(options?.cameraId) || byName(options?.location) || byId(document.getElementById('knlUploadCamera')?.value);
    }
    function selectedLive() {
        return byId(document.getElementById('knlLiveCamera')?.value);
    }
    function applyLive(camera) {
        const loc = document.getElementById('feedLocation');
        const coords = document.getElementById('feedGpsCoords');
        if (loc) loc.value = camera?.name || '';
        if (coords) coords.value = camera ? gps(camera) : '';
    }

    function selectMapCamera(camera) {
        const select = document.getElementById('knlMapCamera');
        const search = select.closest('.knl-picker').querySelector('input');
        search.value = '';
        search.dispatchEvent(new Event('input'));
        select.value = camera.id;
        select.dispatchEvent(new Event('change'));
    }

    function openMap(fileId = null, choose = false, focusCameraId = null) {
        pickerFile = fileId ? window.batchUploadQueue.find(f => f.id === fileId) : null;
        const dialog = document.getElementById('knlCameraDialog');
        dialog.showModal();
        const focusCamera = byId(focusCameraId);
        document.getElementById('knlCameraDialogTitle').textContent = focusCamera ? `${focusCamera.name} · Camera position` : (pickerFile ? `Select camera · ${pickerFile.name}` : 'Karnal camera locations');
        document.getElementById('knlConfirmCamera').hidden = !pickerFile && !choose;
        document.getElementById('knlConfirmCamera').textContent = pickerFile ? 'Use this camera for file' : 'Use this source camera';
        const select = document.getElementById('knlMapCamera');
        const mapSearch = select.closest('.knl-picker').querySelector('input');
        mapSearch.value = '';
        mapSearch.dispatchEvent(new Event('input'));
        select.value = focusCamera?.id || pickerFile?.cameraId || '';
        if (!cameraMap) {
            cameraMap = L.map('knlSiteMap').setView([29.695, 76.985], 13);
            L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom:19, attribution:'© OpenStreetMap contributors'}).addTo(cameraMap);
            registry.sites.forEach(site => {
                const marker = L.circleMarker([site.lat, site.lng], {radius:7, color:'#2563eb', fillOpacity:0.8}).addTo(cameraMap);
                marker.bindTooltip(`${site.name} · ${site.installed_cameras} cameras`);
                const content = document.createElement('div');
                content.className = 'knl-site-popup';
                const title = document.createElement('strong');
                title.textContent = `${site.name} · ${site.installed_cameras} cameras`;
                content.append(title);
                registry.cameras.filter(c => c.site_id === site.id).forEach(camera => {
                    const button = document.createElement('button');
                    button.type = 'button';
                    button.textContent = camera.name;
                    button.onclick = () => { selectMapCamera(camera); cameraMap.closePopup(); };
                    content.append(button);
                });
                marker.bindPopup(content);
            });
            cameraMap.fitBounds(registry.sites.map(s => [s.lat, s.lng]), {padding:[20,20]});
        }
        cameraMap.invalidateSize();
        if (select.value) select.dispatchEvent(new Event('change'));
    }

    function renderTrailMap(history) {
        const host = document.getElementById('knlTrailMapSection');
        if (!host || !registry) return;
        const sorted = [...history].sort((a,b) => Number(a.captured_epoch) - Number(b.captured_epoch));
        const points = sorted.map(row => {
            const camera = byId(row.camera_id) || byName(row.location);
            if (!camera) return null;
            return {...row, camera};
        }).filter(Boolean);
        host.hidden = !points.length;
        if (!points.length) return;
        document.getElementById('knlTrailMapCaption').textContent = `${points.length} registered-camera sightings · Lines show detection order, not an observed road route. Cameras at the same site share a pin.`;
        if (!trailMap) {
            trailMap = L.map('knlTrailMap').setView([29.695,76.985],13);
            L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom:19,attribution:'© OpenStreetMap contributors'}).addTo(trailMap);
        }
        trailLayers.forEach(layer => trailMap.removeLayer(layer));
        trailLayers = [];
        const grouped = new Map();
        points.forEach((point, index) => {
            const key = point.camera.site_id;
            if (!grouped.has(key)) grouped.set(key, []);
            grouped.get(key).push({...point, sequence:index + 1});
        });
        grouped.forEach(group => {
            const camera = group[0].camera;
            const marker = L.circleMarker([camera.lat,camera.lng], {radius:9,color:'#2563eb',fillOpacity:0.85}).addTo(trailMap);
            marker.bindTooltip(group.map(p => `${p.sequence}. ${p.camera.name}`).join(' · '));
            marker.bindPopup(group.map(p => `<strong>${p.sequence}. ${esc(p.camera.name)}</strong><br>${esc(p.captured_at)}<br>${esc(p.camera.id)}`).join('<hr>'));
            trailLayers.push(marker);
        });
        trailLayers.push(L.polyline(points.map(p => [p.camera.lat,p.camera.lng]), {color:'#2563eb',weight:3,dashArray:'7 7'}).addTo(trailMap));
        document.getElementById('knlTrailMapOrder').textContent = points.map(p => p.camera.name).join(' → ');
        setTimeout(() => {trailMap.invalidateSize(); trailMap.fitBounds(points.map(p => [p.camera.lat,p.camera.lng]), {padding:[24,24],maxZoom:16});}, 100);
    }

    async function init() {
        const style = document.createElement('style');
        style.textContent = `.knl-combo{position:relative;min-width:0}.knl-combo-trigger{display:flex;justify-content:space-between;align-items:center;gap:10px;width:100%;min-height:44px;text-align:left!important;background:#fff!important;color:#172033!important;border:1px solid #b8c6d8!important}.knl-combo-panel{position:relative;z-index:20;background:#fff;border:1px solid #b8c6d8;border-radius:8px;box-shadow:0 8px 24px #17203318;padding:8px;margin-top:5px}.knl-combo-panel[hidden]{display:none!important}.knl-combo-panel input{margin-bottom:6px}.knl-combo-panel select{height:205px!important}.knl-combo-panel option{padding:8px}.knl-picker>label{margin-bottom:0}.knl-picker{display:grid;gap:8px;margin:12px 0;min-width:0}.knl-picker label{font-weight:600;color:#334155}.knl-picker input,.knl-picker select{box-sizing:border-box;width:100%;min-width:0;background:#fff;color:#172033;border:1px solid #465773;padding:9px;border-radius:7px;font:inherit}.knl-coords,.knl-caption{font-size:14px;color:#52647c}.knl-map-dialog{background:#fff;color:#172033;border:1px solid #465773;border-radius:12px;padding:18px;width:min(900px,94vw);max-height:92vh;overflow:auto}.knl-map-dialog::backdrop{background:#000b}.knl-map-dialog header{display:flex;justify-content:space-between;gap:12px;align-items:center}.knl-map-dialog button,.knl-map-button{background:#245fcd;color:white;border:0;border-radius:7px;padding:9px 12px;cursor:pointer}.knl-site-popup{display:grid;gap:5px;max-height:230px;overflow:auto}.knl-site-popup button{background:#edf3fe;border:1px solid #acbfdf;border-radius:5px;padding:6px;color:#182b4a;text-align:left;cursor:pointer}#knlTrailMapSection{padding:12px 0}#knlTrailMapSection[hidden]{display:none}#knlTrailMap{height:300px;border-radius:8px;margin-top:8px}#knlTrailMapOrder{font-size:14px;color:#475569;margin-top:8px;overflow-wrap:anywhere}#knlSiteMap{height:340px;min-height:230px;margin:12px 0;border-radius:8px}`;
        document.head.append(style);
        try {
            const response = await fetch('/api/cameras/registry');
            if (!response.ok) throw new Error('Camera registry unavailable');
            registry = await response.json();
        } catch (error) {
            console.error('Karnal camera registry:', error);
            const warning = document.createElement('div');
            warning.setAttribute('role','alert');
            warning.textContent = 'Camera locations could not load. Reload before starting a feed or upload.';
            document.getElementById('viewDashboard')?.prepend(warning);
            return;
        }

        const liveLocation = document.getElementById('feedLocation');
        if (liveLocation) {
            liveLocation.before(picker('knlLiveCamera', 'Karnal source camera', applyLive));
            liveLocation.readOnly = true;
            document.getElementById('feedGpsCoords').readOnly = true;
            applyLive(null);
            document.getElementById('btnDetectGps')?.remove();
            const form = document.getElementById('connectCameraForm');
            form.addEventListener('submit', event => {
                const camera = selectedLive();
                if (!camera) {event.preventDefault();event.stopImmediatePropagation();alert('Select the actual Karnal source camera.');return;}
                applyLive(camera);
                liveAssignments[document.getElementById('feedCameraSlot').value] = camera.id;
            }, true);
            function restoreLiveSlot() {
                const slot = document.getElementById('feedCameraSlot').value;
                document.getElementById('knlLiveCamera').value = liveAssignments[slot] || '';
                document.getElementById('knlLiveCamera').dispatchEvent(new Event('change'));
            }
            document.getElementById('feedCameraSlot')?.addEventListener('change', restoreLiveSlot);
            const modal = document.getElementById('connectCameraModal');
            if (modal) new MutationObserver(() => {if (modal.style.display !== 'none') restoreLiveSlot();}).observe(modal, {attributes:true,attributeFilter:['style']});
        }

        const upload = document.getElementById('unifiedUploadDropzone');
        if (upload) upload.before(picker('knlUploadCamera', 'Source camera for image / video', () => {}));

        const dialog = document.createElement('dialog');
        dialog.id = 'knlCameraDialog';
        dialog.className = 'knl-map-dialog';
        dialog.innerHTML = `<header><h3 id="knlCameraDialogTitle">Karnal camera locations</h3><button type="button" id="knlCloseMap" aria-label="Close camera map">Close</button></header><p class="knl-caption">${registry.site_count} locations · ${registry.count} numbered cameras · ICCC-KNL<br>Names and site GPS imported from your Google My Maps. Camera numbering is local; individual GPS/direction and live-feed URLs were not supplied.</p><div id="knlMapPickerHost"></div><div id="knlSiteMap"></div><p class="knl-caption">Select a camera in the list or click a site pin. No camera or location is chosen automatically.</p><button type="button" id="knlConfirmCamera">Use this camera for file</button>`;
        document.body.append(dialog);
        document.getElementById('knlMapPickerHost').append(picker('knlMapCamera','Registered Karnal camera', camera => {
            if (!camera || !cameraMap) return;
            cameraMap.setView([camera.lat,camera.lng],16);
            if (pickerMarker) cameraMap.removeLayer(pickerMarker);
            pickerMarker = L.circleMarker([camera.lat,camera.lng],{radius:12,color:'#f59e0b',fillOpacity:0.3}).addTo(cameraMap).bindTooltip(camera.name,{permanent:true}).openTooltip();
        }));
        document.getElementById('knlCloseMap').onclick = () => dialog.close();
        dialog.addEventListener('close', () => { if (cameraChoice) {cameraChoice(null); cameraChoice = null;} });
        document.getElementById('knlConfirmCamera').onclick = () => {
            const camera = byId(document.getElementById('knlMapCamera').value);
            if (!camera) {alert('Choose a registered camera first.');return;}
            if (pickerFile) Object.assign(pickerFile,{cameraId:camera.id,locationName:camera.name,lat:camera.lat,lng:camera.lng});
            if (cameraChoice) {cameraChoice(camera);cameraChoice = null;}
            dialog.close();
            window.renderBatchQueueUI();
        };
        window.openLocationPickerModal = fileId => openMap(fileId);
        window.closeLocationPickerModal = () => dialog.close();

        const nav = document.getElementById('navMasterTrailBtn');
        const mapButton = document.createElement('button');
        mapButton.type = 'button';mapButton.className = 'sidebar-nav-item';mapButton.id = 'knlCameraMapButton';
        mapButton.textContent = `Camera Map · ${registry.count}`;
        mapButton.onclick = () => openMap();
        nav?.after(mapButton);

        const history = document.getElementById('trailModalHistoryBody');
        if (history) {
            const section = document.createElement('section');
            section.id='knlTrailMapSection';section.hidden=true;
            section.innerHTML='<strong>Karnal camera trail</strong><div id="knlTrailMapCaption" class="knl-caption"></div><div id="knlTrailMap"></div><div id="knlTrailMapOrder"></div>';
            history.before(section);
        }
        // The history filter uses exactly the same numbered camera IDs.
        const filter = document.getElementById('trailFilterCamera');
        if (filter) {
            const list = document.createElement('datalist');list.id='knlCameraFilterOptions';
            list.innerHTML=registry.cameras.map(c=>`<option value="${esc(c.id)}">${esc(c.name)}</option>`).join('');
            filter.setAttribute('list',list.id);filter.placeholder='Select / type Karnal camera ID';filter.after(list);
            const preview = document.createElement('button');
            preview.type = 'button';
            preview.className = 'knl-map-button';
            preview.textContent = 'Map par dekhein';
            preview.disabled = true;
            filter.after(preview);
            const selectedFilterCamera = () => byId(filter.value.trim()) || byName(filter.value);
            const updateFilterPreview = () => {preview.disabled = !selectedFilterCamera();};
            filter.addEventListener('input', updateFilterPreview);
            filter.addEventListener('change', updateFilterPreview);
            preview.onclick = () => {
                const camera = selectedFilterCamera();
                if (camera) openMap(null, false, camera.id);
            };
            document.getElementById('btnResetTrailFilters')?.addEventListener('click', () => {preview.disabled = true;});
        }
        ['filterTrailDistrict'].forEach(id => {
            const select = document.getElementById(id);
            if (select && !Array.from(select.options).some(option => option.value.toLowerCase() === 'karnal')) {
                select.add(new Option('Karnal District', 'Karnal'));
            }
        });
        document.dispatchEvent(new Event('camera-registry:ready'));
    }
    function chooseCamera() {return new Promise(resolve => {cameraChoice=resolve;openMap(null,true);});}
    window.karnalCameraRegistry = {getSelectedUploadCamera:selectedUpload,getSelectedLiveCamera:selectedLive,renderTrailMap,openMap,byId,chooseCamera};
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded',init); else init();
})();
