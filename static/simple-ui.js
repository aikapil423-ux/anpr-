/* Organize existing controls; no detection, navigation, form or API behavior changes. */
(() => {
    const text=(node,value)=>{if(node)node.textContent=value;};
    const navNames={navDashboardBtn:'Live Monitor',navMasterDbBtn:'Registry',navMasterTrailBtn:'Vehicle Trails',navOpenVehiclesDrawerBtn:'Captured Vehicles',navViolatorsBtn:'Traffic Violations',navAlertAuditBtn:'Alert History',navVehicleSearchBtn:'Search',navBenchmarkBtn:'System Benchmark'};
    function disclosure(element,id,title) {
        if (!element || document.getElementById(id)) return;
        const details=document.createElement('details');details.id=id;details.className='ui-settings';
        const summary=document.createElement('summary');summary.textContent=title;
        element.before(details);details.append(summary,element);
    }
    function cameraPresentation() {
        const picker=document.getElementById('knlLiveCamera')?.closest('.knl-picker');
        const location=document.getElementById('feedLocation')?.closest('.form-group');
        if (picker && location?.contains(picker)) location.before(picker);
        if (picker && location) location.hidden=true;
        const gps=document.getElementById('feedGpsCoords')?.closest('.form-group');
        if (picker && gps) gps.hidden=true; // exact same GPS remains visible below the camera picker
        text(picker?.querySelector('label'),'Camera location');
        text(document.getElementById('knlUploadCamera')?.closest('.knl-picker')?.querySelector('label'),'Source camera');
        const nav=document.getElementById('knlCameraMapButton');
        if (nav && !nav.querySelector('.nav-label')) {
            const icon=document.createElement('span');icon.className='nav-icon-box';icon.textContent='⌖';icon.setAttribute('aria-hidden','true');icon.style.fontSize='24px';
            const label=document.createElement('span');label.className='nav-label';label.textContent='Camera Map';
            const badge=document.createElement('span');badge.className='nav-badge';badge.textContent=nav.textContent.match(/\d+/)?.[0] || '';
            nav.replaceChildren(icon,label,badge);nav.setAttribute('aria-label','Camera Map');nav.title='Camera locations and routes';
        }
        const note=document.querySelector('#knlCameraDialog .knl-caption');
        const counts=note?.textContent.match(/(\d+) locations.*?(\d+) numbered cameras/);
        if(counts)text(note,`Karnal · ${counts[1]} locations · ${counts[2]} cameras. Cameras at one location share its GPS point.`);
        const modal=document.getElementById('knlCameraDialog');
        if (modal) {
            const hint=Array.from(modal.querySelectorAll('p')).find(p=>p.textContent.includes('No camera or location is chosen automatically'));
            text(hint,'Choose a camera from the list or select a location pin.');
        }
    }
    function init() {
        document.body.classList.add('ui-simple');
        for (const [id,name] of Object.entries(navNames)) text(document.getElementById(id)?.querySelector('.nav-label'),name);
        text(document.getElementById('toggleModeLive')?.querySelector('span:last-child'),'Live Camera');
        text(document.getElementById('toggleModeUpload')?.querySelector('span'),'Upload & Analyze');
        disclosure(document.getElementById('aiModelEngineBar'),'uiModelSettings','AI model settings');
        disclosure(document.getElementById('hudLayersBar'),'uiVideoOverlays','Video display options');
        const cadence=document.getElementById('feedTargetFrame');
        disclosure(cadence?.closest('.form-group'),'uiProcessingSettings','Advanced processing');
        const form=document.getElementById('connectCameraForm');
        const footer=form?.querySelector('.modal-footer');
        if (form && footer && !document.getElementById('uiConnectFields')) {
            const fields=document.createElement('div');fields.id='uiConnectFields';
            Array.from(form.children).filter(child=>child!==footer).forEach(child=>fields.append(child));
            form.prepend(fields);
        }
        text(document.querySelector('#connectCameraModal .modal-header h2, #connectCameraModal .modal-header h3'),'Connect camera');
        text(footer?.querySelector('button[type="submit"]'),'Connect camera');
        document.querySelectorAll('.feed-main-tab').forEach(button=>{
            const names={'Upload':'Upload video','Demo':'Sample video','Camera Options':'Live camera'};
            for (const node of button.childNodes) if(node.nodeType===Node.TEXT_NODE && names[node.textContent.trim()])node.textContent=' '+names[node.textContent.trim()];
        });
        const feed=document.getElementById('liveFeedPanel');
        if (feed) {
            const walker=document.createTreeWalker(feed,NodeFilter.SHOW_TEXT);
            while(walker.nextNode())if(walker.currentNode.textContent.trim()==='SURVEILLANCE FEED')walker.currentNode.textContent='Camera feed';
        }
        const label=document.querySelector('label[for="feedTargetFrame"]');
        if (label) {text(label.querySelector('span'),'Analyze every Nth frame (1–20)');text(label.querySelector('span:last-child'),'');}
        text(cadence?.closest('.form-group')?.querySelector('small'),'1 analyzes every frame. Higher values reduce processing load.');
        text(document.querySelector('label[for="feedCameraSlot"]'),'Preview window');
        const header=document.getElementById('headerViewTitle');
        const titleNames={'Live Surveillance Hub':'Live Monitor','Master Trail Corridor':'Vehicle Trails','Master DB Registry':'Registry'};
        function title(){if(header && titleNames[header.textContent.trim()])text(header,titleNames[header.textContent.trim()]);}
        title();if(header)new MutationObserver(title).observe(header,{childList:true,subtree:true});
        cameraPresentation();
    }
    document.addEventListener('camera-registry:ready',cameraPresentation);
    if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
