// Display policy only; keep the complete evidence and stored detections intact.
window.isVisibleVehicleDetection = function (vehicle) {
  if (!vehicle) return false;
  const plate = String(vehicle.plate_number || vehicle.final_plate || vehicle.normalized_plate || vehicle.display_plate || '').trim().toUpperCase();
  const displayPlate = String(vehicle.display_plate || '').toUpperCase();
  if (!plate || /UNREADABLE|UNKNOWN|NO\s*PLATE|NOT\s*DETECTED/.test(plate + ' ' + displayPlate)) return false;
  const raw = vehicle.confidence ?? vehicle.final_confidence ?? vehicle.ocr_confidence;
  if (raw === null || raw === undefined || raw === '') return false;
  let confidence = Number(raw);
  if (vehicle.confidence == null && vehicle.final_confidence != null && confidence <= 1) confidence *= 100;
  return Number.isFinite(confidence) && confidence > 80;
};
document.addEventListener('DOMContentLoaded', () => {
 let isFetchingUnifiedLiveFeed = false;
  const navDashboardBtn = document.getElementById('navDashboardBtn');
  const navMasterDbBtn = document.getElementById('navMasterDbBtn');
  const navVehicleDbBtn = document.getElementById('navVehicleDbBtn');
  const navMasterTrailBtn = document.getElementById('navMasterTrailBtn');
  const navVehicleTrailBtn = document.getElementById('navVehicleTrailBtn');
  const navAlertAuditBtn = document.getElementById('navAlertAuditBtn');
  const navVehicleSearchBtn = document.getElementById('navVehicleSearchBtn');
  const viewDashboard = document.getElementById('viewDashboard');
  const viewAlertAudit = document.getElementById('viewAlertAudit');
  const viewVehicleSearch = document.getElementById('viewVehicleSearch');
  const viewUserMgmt = document.getElementById('viewUserMgmt');
  const navUserMgmtBtn = document.getElementById('navUserMgmtBtn');
  let currentUser = null;
  let currentDistrict = "All Haryana (State HQ)";
  let currentAlertsCache = [];
  let _lastToastText = '';
  let _lastToastTime = 0;
  window.showToastAlert = (message, type = 'info', title = null, durationMs = 2600) => {
    const now = Date.now();
    if (message && message === _lastToastText && now - _lastToastTime < 750) {
      return;
    }
    _lastToastText = message;
    _lastToastTime = now;
    let container = document.getElementById('toastNotificationContainer');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toastNotificationContainer';
      document.body.appendChild(container);
    }
    const existingToasts = container.querySelectorAll('.toast-card');
    existingToasts.forEach(oldCard => {
      oldCard.remove();
    });
    const validTypes = ['error', 'warning', 'success', 'info'];
    const toastType = validTypes.includes(type) ? type : 'info';
    let defaultTitle = 'Notification';
    let iconSvg = '';
    if (toastType === 'error') {
      defaultTitle = title || 'Processing Error';
      iconSvg = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`;
    } else if (toastType === 'warning') {
      defaultTitle = title || 'System Warning';
      iconSvg = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`;
    } else if (toastType === 'success') {
      defaultTitle = title || 'Success';
      iconSvg = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>`;
    } else {
      defaultTitle = title || 'System Update';
      iconSvg = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#0369a1" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>`;
    }
    const safeStr = str => String(str || '').replace(/[&<>"']/g, m => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;'
    })[m]);
    const card = document.createElement('div');
    card.className = `toast-card toast-${toastType}`;
    card.innerHTML = `
            <div class="toast-icon">${iconSvg}</div>
            <div class="toast-body">
                <div class="toast-title">${safeStr(defaultTitle)}</div>
                <div class="toast-message">${safeStr(message)}</div>
            </div>
            <button class="toast-close-btn" title="Dismiss">&times;</button>
        `;
    const closeBtn = card.querySelector('.toast-close-btn');
    let dismissTimer = null;
    const dismiss = () => {
      if (card.classList.contains('toast-hiding')) return;
      card.classList.add('toast-hiding');
      if (dismissTimer) clearTimeout(dismissTimer);
      setTimeout(() => {
        if (card.parentNode) card.remove();
      }, 200);
    };
    if (closeBtn) closeBtn.addEventListener('click', e => {
      e.stopPropagation();
      dismiss();
    });
    card.addEventListener('click', dismiss);
    container.appendChild(card);
    if (durationMs > 0) {
      dismissTimer = setTimeout(dismiss, durationMs);
    }
  };
  window.showToast = window.showToastAlert;
  async function initAuthSession() {
    let authOk = false;
    try {
      const res = await fetch('/api/auth/me');
      if (!res.ok) {
        if (res.status === 401) {
          window.location.href = '/login';
        }
        return;
      }
      currentUser = await res.json();
      window.currentUser = currentUser;
      authOk = true;
    } catch (e) {
      console.error('Auth verification network failed:', e);
      return;
    }
    if (authOk && currentUser) {
      try {
        applyRbacPermissions(currentUser);
      } catch (e) {
        console.error('RBAC init error:', e);
      }
      try {
        fetchAndRenderVehicleDb();
      } catch (e) {
        console.error('Vehicle DB init error:', e);
      }
      try {
        fetchAndRenderVehicleTrail();
      } catch (e) {
        console.error('Vehicle Trail init error:', e);
      }
      try {} catch (e) {
        null;
      }
      try {} catch (e) {
        null;
      }
      try {
        fetchAndRenderCapturedDb();
      } catch (e) {
        console.error('Captured DB init error:', e);
      }
      try {
        fetchAndRenderResults();
      } catch (e) {
        console.error('Results init error:', e);
      }
      try {} catch (e) {
        null;
      }
      try {
        fetchAndRenderUnifiedLiveFeed();
      } catch (e) {
        console.error('Live Feed init error:', e);
      }
    }
  }
  function applyRbacPermissions(user) {
    if (!user) return;
    const sidebarOfficerName = document.getElementById('sidebarOfficerName');
    const sidebarBeltNumber = document.getElementById('sidebarBeltNumber');
    const sidebarRoleBadge = document.getElementById('sidebarRoleBadge');
    const sidebarDistrictBadge = document.getElementById('sidebarDistrictBadge');
    const sidebarAvatarInitial = document.getElementById('sidebarAvatarInitial');
    const sidebarAvatarCircle = document.getElementById('sidebarAvatarCircle');
    const modalOfficerName = document.getElementById('modalOfficerName');
    const modalBeltNumber = document.getElementById('modalBeltNumber');
    const modalRoleBadge = document.getElementById('modalRoleBadge');
    const modalDistrictBadge = document.getElementById('modalDistrictBadge');
    const modalStation = document.getElementById('modalStation');
    const modalAvatarInitial = document.getElementById('modalAvatarInitial');
    const modalAvatarCircle = document.getElementById('modalAvatarCircle');
    const btnModalManageAccounts = document.getElementById('btnModalManageAccounts');
    const headerOfficerName = document.getElementById('headerOfficerName');
    const headerBeltNumber = document.getElementById('headerBeltNumber');
    const headerRoleBadge = document.getElementById('headerRoleBadge');
    const headerDistrictBadge = document.getElementById('headerDistrictBadge');
    const fullName = user.full_name || user.username || 'Officer';
    const beltNo = user.belt_number ? `(${user.belt_number})` : '';
    const initial = (fullName.trim()[0] || 'O').toUpperCase();
    if (sidebarOfficerName) sidebarOfficerName.innerText = fullName;
    if (sidebarBeltNumber) sidebarBeltNumber.innerText = beltNo;
    if (sidebarAvatarInitial) sidebarAvatarInitial.innerText = initial;
    if (modalOfficerName) modalOfficerName.innerText = fullName;
    if (modalBeltNumber) modalBeltNumber.innerText = user.belt_number || 'N/A';
    if (modalAvatarInitial) modalAvatarInitial.innerText = initial;
    if (modalStation) modalStation.innerText = user.police_station || user.station || (user.role === 'STATE_ADMIN' || user.role === 'DEVELOPER_ADMIN' ? 'State Police HQ / All Nakas' : `${user.district || 'District'} Station`);
    if (headerOfficerName) headerOfficerName.innerText = fullName;
    if (headerBeltNumber) headerBeltNumber.innerText = beltNo;
    let roleText = 'OPERATOR';
    let roleClass = 'role-badge-operator';
    let avatarGradient = 'linear-gradient(135deg, #10b981 0%, #059669 100%)';
    if (user.role === 'DEVELOPER_ADMIN') {
      roleText = 'DEVELOPER ADMIN';
      roleClass = 'role-badge-dev';
      avatarGradient = 'linear-gradient(135deg, #ec4899 0%, #8b5cf6 100%)';
    } else if (user.role === 'STATE_ADMIN') {
      roleText = 'STATE ADMIN';
      roleClass = 'role-badge-state';
      avatarGradient = 'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)';
    } else if (user.role === 'DISTRICT_ADMIN') {
      roleText = 'DISTRICT ADMIN';
      roleClass = 'role-badge-district';
      avatarGradient = 'linear-gradient(135deg, #6366f1 0%, #4f46e5 100%)';
    }
    if (sidebarRoleBadge) {
      sidebarRoleBadge.innerText = roleText;
      sidebarRoleBadge.className = `sidebar-role-badge ${roleClass}`;
    }
    if (modalRoleBadge) {
      modalRoleBadge.innerText = roleText;
      modalRoleBadge.className = `sidebar-role-badge ${roleClass}`;
    }
    if (sidebarAvatarCircle) sidebarAvatarCircle.style.background = avatarGradient;
    if (modalAvatarCircle) modalAvatarCircle.style.background = avatarGradient;
    if (headerRoleBadge) {
      headerRoleBadge.innerText = roleText;
      headerRoleBadge.className = `header-role-badge ${roleClass}`;
    }
    const headerAvatarCircle = document.getElementById('headerAvatarCircle');
    const headerAvatarInitial = document.getElementById('headerAvatarInitial');
    const headerDropdownOfficerName = document.getElementById('headerDropdownOfficerName');
    const headerDropdownBeltNumber = document.getElementById('headerDropdownBeltNumber');
    const headerDropdownDistrict = document.getElementById('headerDropdownDistrict');
    const headerDropdownAvatarCircle = document.getElementById('headerDropdownAvatarCircle');
    const headerDropdownAvatarInitial = document.getElementById('headerDropdownAvatarInitial');
    const headerBtnManageAccounts = document.getElementById('headerBtnManageAccounts');
    if (headerAvatarCircle) headerAvatarCircle.style.background = avatarGradient;
    if (headerAvatarInitial) headerAvatarInitial.innerText = initial;
    if (headerDropdownAvatarCircle) headerDropdownAvatarCircle.style.background = avatarGradient;
    if (headerDropdownAvatarInitial) headerDropdownAvatarInitial.innerText = initial;
    if (headerDropdownOfficerName) headerDropdownOfficerName.innerText = fullName;
    let distText = '';
    if (user.role === 'DEVELOPER_ADMIN') {
      distText = 'Benchmark Sandbox';
    } else {
      distText = user.role === 'STATE_ADMIN' ? 'State HQ (All Haryana)' : `${user.district} District`;
    }
    if (headerDropdownBeltNumber) headerDropdownBeltNumber.innerText = user.belt_number || 'DEV-001';
    if (headerDropdownDistrict) headerDropdownDistrict.innerText = distText;
    if (headerBtnManageAccounts) {
      headerBtnManageAccounts.style.display = user.role === 'OPERATOR' ? 'none' : 'flex';
    }
    if (sidebarDistrictBadge) sidebarDistrictBadge.innerText = distText;
    if (modalDistrictBadge) modalDistrictBadge.innerText = distText;
    if (headerDistrictBadge) headerDistrictBadge.innerText = distText;
    if (btnModalManageAccounts) {
      btnModalManageAccounts.style.display = user.role === 'OPERATOR' ? 'none' : 'flex';
    }
    const isSuperAdmin = user.role === 'STATE_ADMIN' || user.role === 'DEVELOPER_ADMIN';
    if (user.district && !isSuperAdmin) {
      currentDistrict = user.district;
      const headerDistrictLabel = document.getElementById('headerDistrictLabel');
      if (headerDistrictLabel) {
        headerDistrictLabel.innerText = `${user.district} Active`;
      }
    }
    const vehicleDbDistrictWrap = document.getElementById('vehicleDbDistrictWrap');
    if (isSuperAdmin) {
      if (vehicleDbDistrictWrap) vehicleDbDistrictWrap.style.display = 'flex';
      if (typeof initSearchableDistrictDropdowns === 'function') {
        initSearchableDistrictDropdowns();
      }
    } else {
      if (vehicleDbDistrictWrap) vehicleDbDistrictWrap.style.display = 'none';
    }
    const isDistrictAdmin = user.role === 'DISTRICT_ADMIN';
    const isOperator = user.role === 'OPERATOR';
    const distFilterDisplay = isSuperAdmin ? 'flex' : 'none';
    const opFilterDisplay = isOperator ? 'none' : 'flex';
    ['vehScopeFilterDistrictWrap', 'trailVehDistrictWrap'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.style.display = distFilterDisplay;
    });
    ['vehScopeFilterOperatorWrap', 'trailVehOperatorWrap'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.style.display = opFilterDisplay;
    });
    document.body.classList.remove('role-state-admin', 'role-district-admin', 'role-operator');
    if (user.role === 'OPERATOR') {
      document.body.classList.add('role-operator');
    } else if (user.role === 'DISTRICT_ADMIN') {
      document.body.classList.add('role-district-admin');
    } else if (isSuperAdmin) {
      document.body.classList.add('role-state-admin');
    }
    if (navUserMgmtBtn) {
      navUserMgmtBtn.style.display = 'flex';
    }
    if (navAlertAuditBtn) {
      if (user.role === 'OPERATOR') {
        navAlertAuditBtn.style.display = 'none';
        if (viewAlertAudit) viewAlertAudit.style.display = 'none';
      } else {
        navAlertAuditBtn.style.display = 'flex';
      }
    }
    if (!isSuperAdmin && user.district) {
      const auditDistFilter = document.getElementById('auditDistrictFilter');
      if (auditDistFilter) {
        auditDistFilter.value = user.district;
        auditDistFilter.disabled = true;
      }
    }
    const viewport = document.getElementById('anprInspectionViewport');
    if (viewport) viewport.style.display = 'none';
    const inspectionContent = document.getElementById('anprInspectionContent');
    if (inspectionContent) inspectionContent.innerHTML = '';
    const dlBtn = document.getElementById('btnDownloadAnnotatedMedia');
    if (dlBtn) dlBtn.style.display = 'none';
    currentResults = null;
    if (verifiedCardsContainer) {
      verifiedCardsContainer.innerHTML = `



                <div class="empty-state">



                    <p>No verified vehicles met the promotion criteria.</p>



                </div>



            `;
    }
    if (reviewCardsContainer) {
      reviewCardsContainer.innerHTML = `



                <div class="empty-state">



                    <p>No vehicles flagged for operator review.</p>



                </div>



            `;
    }
    if (kpiVerifiedCount) kpiVerifiedCount.innerText = '0';
    if (kpiReviewCount) kpiReviewCount.innerText = '0';
    if (kpiTracksMerged) kpiTracksMerged.innerText = '0';
    if (kpiByteTrackIds) kpiByteTrackIds.innerText = '0';
    if (kpiCropsRejected) kpiCropsRejected.innerText = '0';
    if (verifiedCountBadge) verifiedCountBadge.innerText = '0 Verified';
    if (reviewCountBadge) reviewCountBadge.innerText = '0 In Review';
    if (user.role === 'STATE_ADMIN' || user.role === 'DISTRICT_ADMIN' || user.role === 'DEVELOPER_ADMIN') {
      const kpiVeh = document.getElementById('kpiUnifiedVehicles');
      if (kpiVeh) kpiVeh.innerText = '0';
      const kpiStolen = document.getElementById('kpiUnifiedStolen');
      if (kpiStolen) kpiStolen.innerText = '0';
      const kpiPeople = document.getElementById('kpiUnifiedPeople');
      if (kpiPeople) kpiPeople.innerText = '0';
      const kpiPeopleSub = document.getElementById('kpiUnifiedPeopleSub');
      if (kpiPeopleSub) kpiPeopleSub.innerText = '0 currently visible';
      const kpiSuspect = document.getElementById('kpiUnifiedSuspects');
      if (kpiSuspect) kpiSuspect.innerText = '0';
      const navVehBadge = document.getElementById('navDrawerVehiclesCount');
      if (navVehBadge) navVehBadge.innerText = '0';
      const btnVehBadge = document.getElementById('btnVehiclesCountBadge');
      if (btnVehBadge) btnVehBadge.innerText = '0';
      const liveVehCount = document.getElementById('liveVehiclesFreshCount');
      if (liveVehCount) liveVehCount.innerText = '0 / 15 Fresh';
      const freshVehContainer = document.getElementById('liveFreshVehiclesContainer');
      if (freshVehContainer) {
        freshVehContainer.innerHTML = '<div class="empty-state" style="padding: 24px 12px; color: var(--text-muted); font-size: 0.9125rem; text-align: center;">Administrative Console Clean &bull; Operational stream active on Operator Desk.</div>';
      }
    } else {
      const freshVehContainer = document.getElementById('liveFreshVehiclesContainer');
      if (freshVehContainer) {
        freshVehContainer.innerHTML = '<div class="empty-state" style="padding: 24px 12px; color: var(--text-muted); font-size: 0.9125rem; text-align: center;">Loading operator live stream...</div>';
      }
    }
    if (user.role === 'STATE_ADMIN' || user.role === 'DEVELOPER_ADMIN') {
      if (alertBellBadge) {
        alertBellBadge.innerText = '0';
        alertBellBadge.style.display = 'none';
      }
      if (navAlertAuditCountBadge) {
        navAlertAuditCountBadge.innerText = '0';
      }
      if (floatingAlertContainer) {
        floatingAlertContainer.innerHTML = '';
      }
      updateCameraAlertGlow([]);
    }
    initScopeFilters();
  }
  let globalScopeFilters = null;
  async function initScopeFilters() {
    try {
      const res = await fetch('/api/auth/scope-filters');
      if (!res.ok) return;
      const data = await res.json();
      globalScopeFilters = data;
      const role = data.role || 'OPERATOR';
      const districts = data.districts || [];
      const operators = data.operators || [];
      const selectedDist = data.selected_district || 'ALL';
      const selectedOp = data.selected_operator || 'ALL';
      const pairs = [{
        distId: 'filterVehiclesDistrict',
        opId: 'filterVehiclesOperator',
        distWrapId: 'vehScopeFilterDistrictWrap',
        opWrapId: 'vehScopeFilterOperatorWrap'
      }, {}, {
        distId: 'filterTrailDistrict',
        opId: 'filterTrailOperator',
        distWrapId: 'trailVehDistrictWrap',
        opWrapId: 'trailVehOperatorWrap'
      }, {}];
      const isSuperAdminRole = role === 'STATE_ADMIN' || role === 'DEVELOPER_ADMIN';
      const isOperatorRole = role === 'OPERATOR';
      pairs.forEach(p => {
        const distWrap = document.getElementById(p.distWrapId);
        const opWrap = document.getElementById(p.opWrapId);
        if (distWrap) {
          distWrap.style.display = isSuperAdminRole ? 'flex' : 'none';
        }
        if (opWrap) {
          opWrap.style.display = isOperatorRole ? 'none' : 'flex';
        }
        const distEl = document.getElementById(p.distId);
        const opEl = document.getElementById(p.opId);
        if (distEl) {
          distEl.innerHTML = districts.map(d => {
            const label = d === 'ALL' ? 'All Haryana (State HQ)' : `${d} District`;
            return `<option value="${escapeHtml(d)}" ${d === selectedDist ? 'selected' : ''}>${escapeHtml(label)}</option>`;
          }).join('');
          if (role === 'OPERATOR' || role === 'DISTRICT_ADMIN') {
            distEl.disabled = true;
          } else {
            distEl.disabled = false;
          }
        }
        if (opEl) {
          populateOperatorOptions(opEl, operators, selectedDist, selectedOp, role);
        }
      });
    } catch (e) {
      console.error("Failed to load scope filters:", e);
    }
  }
  function populateOperatorOptions(opEl, allOperators, selectedDistrict, selectedOp, role) {
    if (!opEl) return;
    let filteredOps = allOperators || [];
    if (selectedDistrict && selectedDistrict !== 'ALL') {
      filteredOps = filteredOps.filter(o => o.username === 'ALL' || o.district && o.district.toLowerCase() === selectedDistrict.toLowerCase());
    }
    opEl.innerHTML = filteredOps.map(o => {
      const isSel = o.username === selectedOp;
      return `<option value="${escapeHtml(o.username)}" ${isSel ? 'selected' : ''}>${escapeHtml(o.label || o.username)}</option>`;
    }).join('');
    if (role === 'OPERATOR') {
      opEl.disabled = true;
    } else {
      opEl.disabled = false;
    }
  }
  window.onVehiclesScopeFilterChange = function (isDistrictChange) {
    if (isDistrictChange && globalScopeFilters) {
      const distVal = document.getElementById('filterVehiclesDistrict')?.value || 'ALL';
      populateOperatorOptions(document.getElementById('filterVehiclesOperator'), globalScopeFilters.operators, distVal, 'ALL', globalScopeFilters.role);
    }
    if (typeof fetchAndRenderDrawerVehicles === 'function') {
      fetchAndRenderDrawerVehicles();
    }
  };
  window.onTrailScopeFilterChange = function (isDistrictChange) {
    if (isDistrictChange && globalScopeFilters) {
      const distVal = document.getElementById('filterTrailDistrict')?.value || 'ALL';
      populateOperatorOptions(document.getElementById('filterTrailOperator'), globalScopeFilters.operators, distVal, 'ALL', globalScopeFilters.role);
    }
    if (typeof fetchAndRenderVehicleTrail === 'function') {
      fetchAndRenderVehicleTrail();
    }
  };
  initAuthSession();
  const viewMasterDb = document.getElementById('viewMasterDb');
  const subviewVehicleDb = document.getElementById('subviewVehicleDb');
  const viewVehicleDb = subviewVehicleDb;
  const subtabVehicleDbBtn = document.getElementById('subtabVehicleDbBtn');
  const masterRegVehiclesCountBadge = document.getElementById('masterRegVehiclesCountBadge');
  const masterRegTotalCountBadge = document.getElementById('masterRegTotalCountBadge');
  const navMasterDbCountBadge = document.getElementById('navMasterDbCountBadge');
  let currentMasterDbSubtab = 'vehicle';
  let totalRegisteredVehiclesCount = 0;
  function updateMasterRegTotal() {
    const total = totalRegisteredVehiclesCount + 0;
    if (masterRegTotalCountBadge) {
      masterRegTotalCountBadge.innerText = `${total} Total Records`;
    }
    if (navMasterDbCountBadge) {
      navMasterDbCountBadge.innerText = `${total}`;
    }
  }
  window.switchMasterDbTab = subtab => {
    currentMasterDbSubtab = subtab;
    if (subtab === 'vehicle') {
      if (subtabVehicleDbBtn) {
        subtabVehicleDbBtn.classList.add('active');
        subtabVehicleDbBtn.style.border = '1px solid rgba(16, 185, 129, 0.4)';
        subtabVehicleDbBtn.style.background = 'rgba(16, 185, 129, 0.2)';
        subtabVehicleDbBtn.style.color = '#fff';
      }
      if (subviewVehicleDb) subviewVehicleDb.style.display = 'block';
      fetchAndRenderVehicleDb();
    } else {
      if (subtabVehicleDbBtn) {
        subtabVehicleDbBtn.classList.remove('active');
        subtabVehicleDbBtn.style.border = '1px solid var(--border-color)';
        subtabVehicleDbBtn.style.background = 'rgba(241,245,249,0.5)';
        subtabVehicleDbBtn.style.color = 'var(--text-secondary)';
      }
      if (subviewVehicleDb) subviewVehicleDb.style.display = 'none';
    }
  };
  window.refreshMasterDb = () => {
    fetchAndRenderVehicleDb();
  };
  const viewMasterTrail = document.getElementById('viewMasterTrail');
  const subviewVehicleTrail = document.getElementById('subviewVehicleTrail');
  const viewVehicleTrail = subviewVehicleTrail;
  const navDbCountBadge = document.getElementById('navDbCountBadge');
  const navMasterTrailBadge = document.getElementById('navMasterTrailBadge');
  const subtabVehicleTrailBtn = document.getElementById('subtabVehicleTrailBtn');
  const masterVehiclesCountBadge = document.getElementById('masterVehiclesCountBadge');
  const masterTotalSightingsBadge = document.getElementById('masterTotalSightingsBadge');
  let currentMasterTrailSubtab = 'vehicle';
  let totalVehicleSightingsCount = 0;
  function updateMasterTotalSightings() {
    const total = totalVehicleSightingsCount + 0;
    if (masterTotalSightingsBadge) {
      masterTotalSightingsBadge.innerText = `${total} Total Sightings`;
    }
    if (navMasterTrailBadge && !window.vehicleTrailReviewMode) {
      navMasterTrailBadge.innerText = `${totalVehicleSightingsCount}`;
    }
  }
  window.switchMasterTrailTab = subtab => {
    currentMasterTrailSubtab = subtab;
    if (subtab === 'vehicle') {
      if (subtabVehicleTrailBtn) {
        subtabVehicleTrailBtn.classList.add('active');
        subtabVehicleTrailBtn.style.border = '1px solid rgba(99, 102, 241, 0.4)';
        subtabVehicleTrailBtn.style.background = 'rgba(99, 102, 241, 0.2)';
        subtabVehicleTrailBtn.style.color = '#fff';
      }
      if (subviewVehicleTrail) subviewVehicleTrail.style.display = 'block';
      fetchAndRenderVehicleTrail();
    } else {
      if (subtabVehicleTrailBtn) {
        subtabVehicleTrailBtn.classList.remove('active');
        subtabVehicleTrailBtn.style.border = '1px solid var(--border-color)';
        subtabVehicleTrailBtn.style.background = 'rgba(241,245,249,0.5)';
        subtabVehicleTrailBtn.style.color = 'var(--text-secondary)';
      }
      if (subviewVehicleTrail) subviewVehicleTrail.style.display = 'none';
    }
  };
  window.refreshMasterTrail = () => {
    fetchAndRenderVehicleTrail();
  };
  window.selectedUploadFps = 5;
  window.setUploadFps = function (fps) {
    const val = parseInt(fps);
    window.selectedUploadFps = isNaN(val) ? 5 : val;
    [5, 10, 20, 0].forEach(f => {
      const btn = document.getElementById(f === 0 ? 'fpsBtnAll' : 'fpsBtn' + f);
      if (btn) {
        if (f === window.selectedUploadFps) {
          btn.classList.add('active');
          btn.style.background = '#3b82f6';
          btn.style.color = '#ffffff';
          btn.style.borderColor = '#3b82f6';
        } else {
          btn.classList.remove('active');
          btn.style.background = 'rgba(241,245,249,0.8)';
          btn.style.color = '#475569';
          btn.style.borderColor = 'rgba(148, 163, 184, 0.3)';
        }
      }
    });
  };
  const videoFileInput = document.getElementById('videoFileInput');
  const btnRunDemo = document.getElementById('btnRunDemo');
  const progressContainer = document.getElementById('progressContainer');
  const progressBar = document.getElementById('progressBar');
  const progressStatus = document.getElementById('progressStatus');
  const progressPercent = document.getElementById('progressPercent');
  const progressFrames = document.getElementById('progressFrames');
  const kpiVerifiedCount = document.getElementById('kpiVerifiedCount');
  const kpiReviewCount = document.getElementById('kpiReviewCount');
  const kpiTracksMerged = document.getElementById('kpiTracksMerged');
  const kpiByteTrackIds = document.getElementById('kpiByteTrackIds');
  const kpiCropsRejected = document.getElementById('kpiCropsRejected');
  const verifiedCardsContainer = document.getElementById('verifiedCardsContainer');
  const reviewCardsContainer = document.getElementById('reviewCardsContainer');
  const verifiedCountBadge = document.getElementById('verifiedCountBadge');
  const reviewCountBadge = document.getElementById('reviewCountBadge');
  const evidenceModal = document.getElementById('evidenceModal');
  const modalCloseBtn = document.getElementById('modalCloseBtn');
  const modalTitle = document.getElementById('modalTitle');
  const modalEvidenceList = document.getElementById('modalEvidenceList');
  const imageFileInput = document.getElementById('imageFileInput');
  const captureDetailModal = document.getElementById('captureDetailModal');
  const closeCaptureDetailModalBtn = document.getElementById('closeCaptureDetailModalBtn');
  const capModalRankBadge = document.getElementById('capModalRankBadge');
  const capModalPlateText = document.getElementById('capModalPlateText');
  const capModalFormatBadge = document.getElementById('capModalFormatBadge');
  const capModalSubtitle = document.getElementById('capModalSubtitle');
  const capModalBody = document.getElementById('capModalBody');
  const btnOpenRegisterModal = document.getElementById('btnOpenRegisterModal');
  const registerVehicleModal = document.getElementById('registerVehicleModal');
  const closeRegisterModalBtn = document.getElementById('closeRegisterModalBtn');
  const cancelRegisterModalBtn = document.getElementById('cancelRegisterModalBtn');
  const registerVehicleForm = document.getElementById('registerVehicleForm');
  const dbSearchInput = document.getElementById('dbSearchInput');
  const filterBtns = document.querySelectorAll('#subviewVehicleDb .filter-btn');
  const dbVehicleContainer = document.getElementById('dbVehicleContainer');
  const subFormCase = document.getElementById('subFormCase');
  const subFormLost = document.getElementById('subFormLost');
  const radioCaseYes = document.querySelector('input[name="involvedInCase"][value="yes"]');
  const radioCaseNo = document.querySelector('input[name="involvedInCase"][value="no"]');
  const vehicleDetailModal = document.getElementById('vehicleDetailModal');
  const closeDetailModalBtn = document.getElementById('closeDetailModalBtn');
  const detailPlateTitle = document.getElementById('detailPlateTitle');
  const detailModalBody = document.getElementById('detailModalBody');
  let pollInterval = null;
  let currentResults = null;
  let currentDbFilter = 'all';
  let dbSearchDebounce = null;
  const viewVerified = document.getElementById('viewVerified');
  const viewReview = document.getElementById('viewReview');
  const viewTracks = document.getElementById('viewTracks');
  const viewFalseCrops = document.getElementById('viewFalseCrops');
  const viewCapturedVehicles = document.getElementById('viewCapturedVehicles');
  const navVerifiedMetric = document.getElementById('navVerifiedMetric');
  const navReviewMetric = document.getElementById('navReviewMetric');
  const navTracksMetric = document.getElementById('navTracksMetric');
  const navByteTrackMetric = document.getElementById('navByteTrackMetric');
  const navCropsMetric = document.getElementById('navCropsMetric');
  const navOpenVehiclesDrawerBtn = document.getElementById('navOpenVehiclesDrawerBtn');
  const kpiTracksMergedDetail = document.getElementById('kpiTracksMergedDetail');
  const kpiByteTrackIdsDetail = document.getElementById('kpiByteTrackIdsDetail');
  const kpiCropsRejectedDetail = document.getElementById('kpiCropsRejectedDetail');
  window.switchFeedMode = mode => {
    const livePanel = document.getElementById('liveFeedPanel') || document.querySelector('.live-feed-panel');
    const uploadPanel = document.getElementById('uploadHubPanel') || document.querySelector('.upload-hub-panel');
    const liveAct = document.getElementById('liveActivitySection');
    const uploadAct = document.getElementById('uploadActivitySection');
    const btnLive = document.getElementById('toggleModeLive');
    const btnUpload = document.getElementById('toggleModeUpload');
    const grid = document.getElementById('dualFeedGrid') || document.querySelector('.dual-feed-grid');
    if (mode === 'upload') {
      if (livePanel) livePanel.style.display = 'none';
      if (uploadPanel) uploadPanel.style.display = 'flex';
      if (liveAct) liveAct.style.display = 'none';
      if (uploadAct) uploadAct.style.display = 'block';
      if (grid) grid.style.gridTemplateColumns = '1fr';
      btnLive?.classList.remove('active');
      btnUpload?.classList.add('active');
      if (typeof window.switchModelTarget === 'function') {
        window.switchModelTarget('upload');
      }
      if (typeof window.fetchAndRenderUploadActivityFeed === 'function') {
        window.fetchAndRenderUploadActivityFeed();
      }
      if (typeof window.fetchAndRenderUploadSessionsFeed === 'function') {
        window.fetchAndRenderUploadSessionsFeed();
      }
    } else {
      if (livePanel) livePanel.style.display = 'flex';
      if (uploadPanel) uploadPanel.style.display = 'none';
      if (liveAct) liveAct.style.display = 'block';
      if (uploadAct) uploadAct.style.display = 'none';
      if (grid) grid.style.gridTemplateColumns = '1fr';
      btnUpload?.classList.remove('active');
      btnLive?.classList.add('active');
      if (typeof window.switchModelTarget === 'function') {
        window.switchModelTarget('live');
      }
      if (typeof window.refreshUnifiedLiveFeed === 'function') {
        window.refreshUnifiedLiveFeed();
      }
    }
  };
  window.openOfficerAccountModal = function () {
    const modal = document.getElementById('officerAccountModal');
    if (modal) modal.style.display = 'flex';
  };
  window.closeOfficerAccountModal = function () {
    const modal = document.getElementById('officerAccountModal');
    if (modal) modal.style.display = 'none';
  };
  window.handleSidebarAccountClick = function () {
    if (!currentUser) return;
    if (currentUser.role === 'OPERATOR') {
      window.openOfficerAccountModal();
    } else {
      window.switchTab('user-mgmt');
    }
  };
  window.toggleMobileSidebar = function (forceOpen) {
    const sidebar = document.querySelector('.app-sidebar');
    if (!sidebar) return;
    const shouldOpen = typeof forceOpen === 'boolean' ? forceOpen : !sidebar.classList.contains('mobile-open');
    if (shouldOpen) {
      sidebar.classList.add('mobile-open');
      let backdrop = document.getElementById('mobileSidebarBackdrop');
      if (!backdrop) {
        backdrop = document.createElement('div');
        backdrop.id = 'mobileSidebarBackdrop';
        backdrop.className = 'mobile-sidebar-backdrop';
        backdrop.onclick = () => window.toggleMobileSidebar(false);
        document.body.appendChild(backdrop);
      }
      backdrop.style.display = 'block';
      document.body.style.overflow = 'hidden';
    } else {
      sidebar.classList.remove('mobile-open');
      const backdrop = document.getElementById('mobileSidebarBackdrop');
      if (backdrop) backdrop.style.display = 'none';
      document.body.style.overflow = '';
    }
  };
  window.closeMobileSidebar = () => window.toggleMobileSidebar(false);
  window.switchTab = tab => {
    if (window.innerWidth <= 768) {
      window.toggleMobileSidebar(false);
    }
    document.getElementById('navViolatorsBtn')?.classList.remove('active');
    navDashboardBtn?.classList.remove('active');
    navMasterDbBtn?.classList.remove('active');
    navVehicleDbBtn?.classList.remove('active');
    null;
    navMasterTrailBtn?.classList.remove('active');
    navVehicleTrailBtn?.classList.remove('active');
    null;
    null;
    navAlertAuditBtn?.classList.remove('active');
    navVehicleSearchBtn?.classList.remove('active');
    navUserMgmtBtn?.classList.remove('active');
    navOpenVehiclesDrawerBtn?.classList.remove('active');
    null;
    navVerifiedMetric?.classList.remove('active');
    navReviewMetric?.classList.remove('active');
    navTracksMetric?.classList.remove('active');
    navByteTrackMetric?.classList.remove('active');
    navCropsMetric?.classList.remove('active');
    document.querySelectorAll('.view-panel').forEach(p => p.style.display = 'none');
    const headerViewTitle = document.getElementById('headerViewTitle');
    const viewTitles = {
      'violators': '🚨 Traffic Violators Registry (Triple Riding & Helmet)',
      'dashboard': 'Live Surveillance Hub',
      'master-db': 'Master DB Registry',
      'vehicle-db': 'Master DB (Vehicles)',
      'master-trail': 'Master Trail Corridor',
      'vehicle-trail': 'Vehicle Movement Trail',
      'captured-vehicles': 'Captured Vehicles Database',
      'alert-audit': 'Alert Audit Trail',
      'vehicle-search': 'Vehicle Forensics Search',
      'user-mgmt': 'Officer Accounts Administration'
    };
    if (headerViewTitle && viewTitles[tab]) {
      headerViewTitle.innerText = viewTitles[tab];
    }
    window.scrollTo({
      top: 0,
      behavior: 'smooth'
    });
    if (tab === 'violators') {
      document.getElementById('navViolatorsBtn')?.classList.add('active');
      const vView = document.getElementById('viewViolators');
      if (vView) vView.style.display = 'block';
      window.fetchAndRenderViolators();
      return;
    } else if (tab === 'dashboard') {
      navDashboardBtn?.classList.add('active');
      if (viewDashboard) viewDashboard.style.display = 'block';
    } else if (tab === 'master-db') {
      navMasterDbBtn?.classList.add('active');
      if (viewMasterDb) viewMasterDb.style.display = 'block';
      window.switchMasterDbTab(currentMasterDbSubtab || 'vehicle');
      fetchAndRenderVehicleDb();
    } else if (tab === 'vehicle-db') {
      navMasterDbBtn?.classList.add('active');
      if (viewMasterDb) viewMasterDb.style.display = 'block';
      window.switchMasterDbTab('vehicle');
    } else if (tab === 'master-trail') {
      navMasterTrailBtn?.classList.add('active');
      if (viewMasterTrail) viewMasterTrail.style.display = 'block';
      window.switchMasterTrailTab(currentMasterTrailSubtab || 'vehicle');
      fetchAndRenderVehicleTrail();
    } else if (tab === 'vehicle-trail') {
      navMasterTrailBtn?.classList.add('active');
      if (viewMasterTrail) viewMasterTrail.style.display = 'block';
      window.switchMasterTrailTab('vehicle');
    } else if (tab === 'captured-vehicles') {
      navOpenVehiclesDrawerBtn?.classList.add('active');
      if (viewCapturedVehicles) viewCapturedVehicles.style.display = 'block';
      fetchAndRenderDrawerVehicles();
    } else if (tab === 'alert-audit') {
      if (currentUser && currentUser.role === 'OPERATOR') {
        alert("Access Denied: Operators do not have permission to view Alert Audit Trails.");
        switchTab('dashboard');
        return;
      }
      navAlertAuditBtn?.classList.add('active');
      if (viewAlertAudit) viewAlertAudit.style.display = 'block';
      window.renderAlertAuditHierarchy();
    } else if (tab === 'vehicle-search') {
      navVehicleSearchBtn?.classList.add('active');
      if (viewVehicleSearch) viewVehicleSearch.style.display = 'block';
    } else if (tab === 'user-mgmt') {
      navUserMgmtBtn?.classList.add('active');
      if (viewUserMgmt) viewUserMgmt.style.display = 'block';
      window.fetchAndRenderUsersList();
    } else if (tab === 'verified') {
      navVerifiedMetric?.classList.add('active');
      if (viewVerified) viewVerified.style.display = 'block';
    } else if (tab === 'review') {
      navReviewMetric?.classList.add('active');
      if (viewReview) viewReview.style.display = 'block';
    } else if (tab === 'tracks') {
      navTracksMetric?.classList.add('active');
      navByteTrackMetric?.classList.add('active');
      if (viewTracks) viewTracks.style.display = 'block';
    } else if (tab === 'false-crops') {
      navCropsMetric?.classList.add('active');
      if (viewFalseCrops) viewFalseCrops.style.display = 'block';
    }
  };
  if (navDashboardBtn) navDashboardBtn.addEventListener('click', () => switchTab('dashboard'));
  if (navMasterDbBtn) navMasterDbBtn.addEventListener('click', () => switchTab('master-db'));
  if (navVehicleDbBtn) navVehicleDbBtn.addEventListener('click', () => switchTab('master-db'));
  if (navMasterTrailBtn) navMasterTrailBtn.addEventListener('click', () => switchTab('master-trail'));
  if (navVehicleTrailBtn) navVehicleTrailBtn.addEventListener('click', () => switchTab('master-trail'));
  if (navOpenVehiclesDrawerBtn) navOpenVehiclesDrawerBtn.addEventListener('click', () => switchTab('captured-vehicles'));
  if (navAlertAuditBtn) navAlertAuditBtn.addEventListener('click', () => switchTab('alert-audit'));
  if (navVehicleSearchBtn) navVehicleSearchBtn.addEventListener('click', () => switchTab('vehicle-search'));
  if (navUserMgmtBtn) navUserMgmtBtn.addEventListener('click', () => switchTab('user-mgmt'));
  if (navVerifiedMetric) navVerifiedMetric.addEventListener('click', () => switchTab('verified'));
  if (navReviewMetric) navReviewMetric.addEventListener('click', () => switchTab('review'));
  if (navTracksMetric) navTracksMetric.addEventListener('click', () => switchTab('tracks'));
  if (navByteTrackMetric) navByteTrackMetric.addEventListener('click', () => switchTab('tracks'));
  if (navCropsMetric) navCropsMetric.addEventListener('click', () => switchTab('false-crops'));
  if (btnRunDemo) {
    btnRunDemo.addEventListener('click', async () => {
      try {
        btnRunDemo.disabled = true;
        btnRunDemo.innerText = "Launching Demo...";
        showProgress("Initializing demo scenario...", 0);
        const res = await fetch('/api/run_demo', {
          method: 'POST'
        });
        if (res.ok) {
          startPolling();
          showToastAlert("Demo video scenario initiated successfully.", "info", "Demo Started");
        } else {
          const err = await res.json().catch(() => ({}));
          showToastAlert(err.detail || "Failed to start demo video.", "error", "Demo Launch Error");
        }
      } catch (err) {
        console.error(err);
        showToastAlert("Error running demo: " + err.message, "error", "Demo Error");
      } finally {
        btnRunDemo.disabled = false;
        btnRunDemo.innerHTML = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg> Run Demo Scenario`;
      }
    });
  }
  if (videoFileInput) {
    videoFileInput.addEventListener('change', async e => {
      const file = e.target.files[0];
      if (!file) return;
      const formData = new FormData();
      formData.append('file', file);
      formData.append('fps', window.selectedUploadFps !== undefined ? window.selectedUploadFps : 5);
      const chkSave = document.getElementById('chkSaveAnnotatedVideo');
      formData.append('save_annotated_video', chkSave ? chkSave.checked ? 'true' : 'false' : 'true');
      try {
        startSmoothProgressTicker('video');
        const res = await fetch('/api/upload', {
          method: 'POST',
          body: formData
        });
        if (res.ok) {
          startPolling();
          showToastAlert(`Video "${file.name}" uploaded. Processing frames with active models...`, "info", "Video Upload Started");
        } else {
          hideProgress();
          const err = await res.json().catch(() => ({}));
          showToastAlert(err.detail || "Video upload failed. Check format or codec compatibility.", "error", "Upload Failed");
        }
      } catch (err) {
        hideProgress();
        console.error(err);
        showToastAlert("Upload error: " + err.message, "error", "Network / Upload Error");
      }
    });
  }
  if (imageFileInput) {
    imageFileInput.addEventListener('change', async e => {
      const file = e.target.files[0];
      if (!file) return;
      const formData = new FormData();
      formData.append('file', file);
      try {
        startSmoothProgressTicker('image');
        const res = await fetch('/api/upload_image', {
          method: 'POST',
          body: formData
        });
        if (res.ok) {
          const data = await res.json();
          await finishSmoothProgressTicker();
          await fetchAndRenderCapturedDb();
          await fetchAndRenderResults();
          if (typeof fetchActiveAlerts === 'function') {
            fetchActiveAlerts();
          }
          showAnprPhotoInspection(data, file.name);
          showToastAlert(`Photo "${file.name}" processed successfully. Detected ${data.plate_number || 'No Plate'}`, "success", "ANPR Success");
        } else {
          hideProgress();
          const err = await res.json().catch(() => ({}));
          showToastAlert(err.detail || "Image analysis failed.", "error", "Analysis Failed");
        }
      } catch (err) {
        hideProgress();
        console.error(err);
        showToastAlert("Error analyzing image: " + err.message, "error", "Image Analysis Error");
      } finally {
        hideProgress();
        imageFileInput.value = '';
      }
    });
  }
  window.renderHotlistBannerHtml = renderHotlistBannerHtml;
  function renderHotlistBannerHtml(match) {
    if (!match) return '';
    const isCase = match.involved_in_case;
    const bannerClass = isCase ? 'hotlist-alert-case' : 'hotlist-alert-lost';
    const titleText = isCase ? `POLICE HOTLIST HIT: ${match.offence_type || 'WANTED VEHICLE'}` : `LOST / MISSING VEHICLE REPORT`;
    const detailsText = isCase ? `FIR No: <strong>${match.fir_number || 'N/A'}</strong> &bull; PS: <strong>${match.police_station || 'N/A'}</strong> &bull; IO: <strong>${match.io_number || 'N/A'}</strong>` : `Lost from: <strong>${match.lost_location || 'Location not recorded'}</strong>`;
    const hasOwner = match.owner_name || match.owner_father_name || match.owner_mobile || match.owner_address;
    const ownerSnippet = hasOwner ? `



            <div style="margin-top: 6px; padding-top: 6px; border-top: 1px solid rgba(255,255,255,0.15); font-size: 0.875rem; display: flex; flex-wrap: wrap; gap: 10px; align-items: center;">



                <span style="color: #1d4ed8; font-weight: 700;">👤 OWNER:</span>



                ${match.owner_name ? `<span><strong>${escapeHtml(match.owner_name)}</strong></span>` : ''}



                ${match.owner_father_name ? `<span>(S/o ${escapeHtml(match.owner_father_name)})</span>` : ''}



                ${match.owner_mobile ? `<span style="color: #0369a1;">📞 <strong>${escapeHtml(match.owner_mobile)}</strong></span>` : ''}



                ${match.owner_address ? `<span style="color: #475569;">📍 ${escapeHtml(match.owner_address)}</span>` : ''}



            </div>



        ` : '';
    return `



            <div class="hotlist-alert-banner ${bannerClass}">



                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" style="flex-shrink: 0; margin-top: 1px;">



                    <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>



                    <line x1="12" y1="9" x2="12" y2="13"/>



                    <line x1="12" y1="17" x2="12.01" y2="17"/>



                </svg>



                <div style="flex: 1;">



                    <span class="hotlist-alert-title">${titleText}</span>



                    <div style="font-size: 0.875rem; line-height: 1.4; opacity: 0.95;">${detailsText}</div>



                    ${match.case_summary ? `<div style="font-size: 0.875rem; margin-top: 2px; font-style: italic; opacity: 0.85;">Summary: ${escapeHtml(match.case_summary)}</div>` : ''}



                    ${ownerSnippet}



                </div>



            </div>



        `;
  }
  function showAnprPhotoInspection(data, originalFileName) {
    const detections = (data.detections || []).filter(window.isVisibleVehicleDetection);
    data = {...data, detections, detections_count: detections.length};
    const viewport = document.getElementById('anprInspectionViewport');
    const content = document.getElementById('anprInspectionContent');
    const badge = document.getElementById('anprInspectionTypeBadge');
    const subtext = document.getElementById('anprInspectionSubtext');
    const dlBtn = document.getElementById('btnDownloadAnnotatedMedia');
    const dlText = document.getElementById('downloadBtnText');
    const dropzone = document.getElementById('unifiedUploadDropzone');
    if (!viewport || !content) return;
    if (window.switchFeedMode) window.switchFeedMode('upload');
    if (dropzone) dropzone.style.display = 'none';
    if (badge) {
      badge.innerText = "PHOTO INSPECTION";
      badge.style.background = "rgba(16, 185, 129, 0.2)";
      badge.style.color = "#10b981";
    }
    if (subtext) subtext.innerText = `${data.detections_count || 0} vehicle/plate(s) identified`;
    if (dlBtn) {
      dlBtn.style.display = 'inline-flex';
      if (dlText) dlText.innerText = "Download Annotated Photo";
      dlBtn.href = data.download_url || (data.annotated_image_base64 ? `data:image/jpeg;base64,${data.annotated_image_base64}` : '#');
      dlBtn.setAttribute('download', data.annotated_photo_filename || 'annotated_vehicle_photo.jpg');
    }
    let detectionsHtml = '';
    if (!data.detections || data.detections.length === 0) {
      detectionsHtml = `



                <div style="padding: 12px; background: rgba(241,245,249,0.6); border: 1px solid var(--border-color); border-radius: 6px; text-align: center; color: var(--text-secondary); font-size: 0.9125rem;">



                    No vehicle plate detected with confidence above 80%.



                </div>



            `;
    } else {
      detectionsHtml = data.detections.map(d => {
        const isHotlist = !!d.hotlist_match;
        const hotlistBadge = isHotlist ? `<span style="font-size: 0.875rem; padding: 2px 6px; border-radius: 4px; background: rgba(239, 68, 68, 0.25); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.5); font-weight: 600;">POLICE HOTLIST HIT</span>` : `<span style="font-size: 0.875rem; padding: 2px 6px; border-radius: 4px; background: rgba(16, 185, 129, 0.2); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.4); font-weight: 600;">CLEAN VEHICLE</span>`;
        const plateCropSrc = d.crop_base64 ? `data:image/jpeg;base64,${d.crop_base64}` : '';
        return `



                    <div style="background: rgba(241,245,249,0.8); border: 1px solid var(--border-color); border-radius: 8px; padding: 12px; margin-bottom: 10px;">



                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; flex-wrap: wrap; gap: 8px;">



                            <div class="hsrp-plate" style="margin: 0;">



                                <div class="hsrp-ind-strip">



                                    <span>IND</span>



                                </div>



                                <div class="hsrp-plate-text">${escapeHtml(d.display_plate || d.normalized_plate || 'UNKNOWN')}</div>



                            </div>



                            ${hotlistBadge}



                        </div>



                        <div style="display: flex; gap: 12px; align-items: center; flex-wrap: wrap;">



                            ${plateCropSrc ? `



                                <div style="border: 1px solid var(--border-color); border-radius: 6px; overflow: hidden; background: #000; flex-shrink: 0;">



                                    <img src="${plateCropSrc}" alt="Cleaned Plate Crop" style="max-height: 48px; max-width: 140px; display: block; object-fit: contain;">



                                </div>



                            ` : ''}



                            <div style="flex: 1; min-width: 160px; font-size: 0.875rem; color: var(--text-secondary); display: grid; grid-template-columns: 1fr 1fr; gap: 4px 10px;">



                                <div>OCR Conf: <strong style="color: #10b981;">${d.ocr_confidence}%</strong></div>



                                <div>Det Conf: <strong style="color: #0369a1;">${d.detection_confidence}%</strong></div>



                                <div>Format: <strong style="color: #fff;">${escapeHtml(d.format_type || 'Standard')}</strong></div>



                                <div>Blur Score: <strong style="color: #fff;">${d.blur_score || 0}</strong></div>



                            </div>



                        </div>



                        ${isHotlist ? renderHotlistBannerHtml(d.hotlist_match) : ''}



                    </div>



                `;
      }).join('');
    }
    const sceneSrc = data.annotated_image_base64 ? `data:image/jpeg;base64,${data.annotated_image_base64}` : data.annotated_photo_url || '';
    content.innerHTML = `



            <div>



                <!-- Annotated Scene Image -->



                <div style="position: relative; border-radius: 8px; overflow: hidden; border: 1px solid var(--border-color); margin-bottom: 12px; background: #000; text-align: center;">



                    <img src="${sceneSrc}" alt="Annotated Vehicle Scene" style="max-width: 100%; max-height: 320px; object-fit: contain; display: inline-block;">



                </div>



                <!-- Cleaned Plate Crops and Quality Analysis -->



                <div style="margin-top: 10px;">



                    <h5 style="color: #ffffff; font-size: 0.9425rem; margin: 0 0 8px 0; display: flex; align-items: center; gap: 6px;">



                        <span>Cleaned Plate Crops & Optical Character Recognition</span>



                    </h5>



                    ${detectionsHtml}



                </div>



            </div>



        `;
    viewport.style.display = 'block';
  }
  function showAnprVideoInspection(results) {
    results = {...results, vehicles: (results.vehicles || []).filter(window.isVisibleVehicleDetection)};
    if (results.verified_vehicles) results.verified_vehicles = results.verified_vehicles.filter(window.isVisibleVehicleDetection);
    if (results.needs_review) results.needs_review = results.needs_review.filter(window.isVisibleVehicleDetection);
    const viewport = document.getElementById('anprInspectionViewport');
    const content = document.getElementById('anprInspectionContent');
    const badge = document.getElementById('anprInspectionTypeBadge');
    const subtext = document.getElementById('anprInspectionSubtext');
    const dlBtn = document.getElementById('btnDownloadAnnotatedMedia');
    const dlText = document.getElementById('downloadBtnText');
    const dropzone = document.getElementById('unifiedUploadDropzone');
    if (!viewport || !content) return;
    if (window.switchFeedMode) window.switchFeedMode('upload');
    if (dropzone) dropzone.style.display = 'none';
    if (badge) {
      badge.innerText = "VIDEO PROCESSED";
      badge.style.background = "rgba(99, 102, 241, 0.25)";
      badge.style.color = "#818cf8";
    }
    const stats = results.stats || ({});
    const verifiedVehicles = results.verified_vehicles || (results.vehicles || []).filter(v => v.is_verified);
    const verifiedCount = verifiedVehicles.length;
    const reviewCount = (results.needs_review || (results.vehicles || []).filter(v => !v.is_verified)).length;
    if (subtext) subtext.innerText = `${stats.total_vehicles ?? (results.vehicles || []).length} vehicle(s) • ${verifiedCount} verified plate(s) • ${reviewCount} need review`;
    if (dlBtn) {
      if (results.annotated_video_url || results.output_video_url) {
        dlBtn.style.display = 'inline-flex';
        if (dlText) dlText.innerText = "Download Annotated Video";
        dlBtn.href = results.download_url || results.annotated_video_url || results.output_video_url;
        dlBtn.setAttribute('download', results.annotated_video_filename || 'annotated-video.mp4');
      } else {
        dlBtn.style.display = 'none';
      }
    }
    const videoUrl = results.annotated_video_url || results.output_video_url;
    let verifiedPlatesHtml = '';
    if (verifiedVehicles.length > 0) {
      verifiedPlatesHtml = `



                <div style="margin-top: 14px;">



                    <h5 style="color: #ffffff; font-size: 0.9125rem; margin: 0 0 8px 0;">Top Verified Plate Identities</h5>



                    <div style="display: flex; gap: 8px; flex-wrap: wrap;">



                        ${verifiedVehicles.slice(0, 4).map(v => `



                            <div style="display: flex; align-items: center; gap: 6px; background: rgba(241,245,249,0.7); border: 1px solid var(--border-color); border-radius: 6px; padding: 4px 8px;">



                                <div class="hsrp-plate" style="margin: 0; transform: scale(0.85); transform-origin: left center;">



                                    <div class="hsrp-ind-strip"><span>IND</span></div>



                                    <div class="hsrp-plate-text">${escapeHtml(v.display_plate)}</div>



                                </div>



                                <span style="font-size: 0.875rem; color: #10b981; font-weight: 600;">${v.final_confidence ?? v.confidence ?? 0}%</span>



                            </div>



                        `).join('')}



                    </div>



                </div>



            `;
    }
    const diagNotice = results.diagnostic_notice;
    let noticeHtml = '';
    if (diagNotice) {
      noticeHtml = `



                <div style="margin-top: 12px; padding: 10px 14px; background: rgba(245, 158, 11, 0.12); border: 1px solid rgba(245, 158, 11, 0.35); border-radius: 6px; font-size: 0.8825rem; color: #92400e; line-height: 1.45;">



                    <div style="font-weight: 600; margin-bottom: 2px; display: flex; align-items: center; gap: 6px;">



                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>



                        <span>Captured DB Information:</span>



                    </div>



                    <span>${escapeHtml(diagNotice)}</span>



                </div>



            `;
    }
    content.innerHTML = `



            <div>



                <!-- Annotated Video Player -->



                ${videoUrl ? `



                    <div style="position: relative; border-radius: 8px; overflow: hidden; border: 1px solid var(--border-color); margin-bottom: 12px; background: #000;">



                        <video controls autoplay loop playsinline muted preload="auto" style="width: 100%; max-height: 320px; display: block; object-fit: contain;">



                            <source src="${videoUrl}?t=${Date.now()}" type="video/mp4">



                            Your browser does not support HTML5 video tag.



                        </video>



                    </div>



                ` : `



                    <div style="padding: 24px; text-align: center; color: #475569; background: rgba(241,245,249,0.4); border: 1px dashed rgba(148, 163, 184, 0.3); border-radius: 8px; margin-bottom: 12px;">



                        <div style="font-size: 1.0125rem; font-weight: 600; color: #0369a1; margin-bottom: 4px; display: flex; align-items: center; justify-content: center; gap: 6px;">



                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>



                            <span>Fast Processing Mode: Video File Writing Skipped</span>



                        </div>



                        <div style="font-size: 0.875rem; color: #52647c;">Annotated video encoding was disabled. All plates, track consensus, and audit logs were captured with maximum performance.</div>



                    </div>



                `}



                <!-- Processing Summary Grid -->



                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 8px; margin-top: 10px;">



                    <div style="background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 6px; padding: 10px; text-align: center;">



                        <div style="font-size: 1.2rem; font-weight: 700; color: #10b981;">${verifiedCount}</div>



                        <div style="font-size: 0.875rem; color: #52647c; text-transform: uppercase;">Verified Vehicles</div>



                    </div>



                    <div style="background: rgba(245, 158, 11, 0.1); border: 1px solid rgba(245, 158, 11, 0.3); border-radius: 6px; padding: 10px; text-align: center;">



                        <div style="font-size: 1.2rem; font-weight: 700; color: #92400e;">${reviewCount}</div>



                        <div style="font-size: 0.875rem; color: #52647c; text-transform: uppercase;">In Review</div>



                    </div>



                    <div style="background: rgba(99, 102, 241, 0.1); border: 1px solid rgba(99, 102, 241, 0.3); border-radius: 6px; padding: 10px; text-align: center;">



                        <div style="font-size: 1.2rem; font-weight: 700; color: #818cf8;">${stats.tracks_merged_into_vehicles || 0}</div>



                        <div style="font-size: 0.875rem; color: #52647c; text-transform: uppercase;">Tracks Unified</div>



                    </div>



                    <div style="background: rgba(148, 163, 184, 0.1); border: 1px solid rgba(148, 163, 184, 0.3); border-radius: 6px; padding: 10px; text-align: center;">



                        <div style="font-size: 1.2rem; font-weight: 700; color: #52647c;">${stats.crops_rejected_quality || 0}</div>



                        <div style="font-size: 0.875rem; color: #52647c; text-transform: uppercase;">False Crops Filtered</div>



                    </div>



                </div>



                ${noticeHtml}



                ${verifiedPlatesHtml}



            </div>



        `;
    viewport.style.display = 'block';
  }
  function closeAnprInspection() {
    const viewport = document.getElementById('anprInspectionViewport');
    const dlBtn = document.getElementById('btnDownloadAnnotatedMedia');
    const dropzone = document.getElementById('unifiedUploadDropzone');
    const content = document.getElementById('anprInspectionContent');
    if (viewport) {
      const vids = viewport.querySelectorAll('video');
      vids.forEach(v => {
        try {
          v.pause();
          v.removeAttribute('src');
          v.load();
        } catch (e) {}
      });
      viewport.style.display = 'none';
    }
    if (content) content.innerHTML = '';
    if (dlBtn) dlBtn.style.display = 'none';
    if (dropzone) dropzone.style.display = 'block';
    const unifiedMediaInput = document.getElementById('unifiedMediaInput');
    const cameraSnapInput = document.getElementById('cameraSnapInput');
    const videoFileInput = document.getElementById('videoFileInput');
    const imageFileInput = document.getElementById('imageFileInput');
    if (unifiedMediaInput) unifiedMediaInput.value = '';
    if (cameraSnapInput) cameraSnapInput.value = '';
    if (videoFileInput) videoFileInput.value = '';
    if (imageFileInput) imageFileInput.value = '';
  }
  const btnCloseInspection = document.getElementById('btnCloseInspection');
  if (btnCloseInspection) {
    btnCloseInspection.addEventListener('click', closeAnprInspection);
  }
  let progressTickerTimer = null;
  let currentTickerPct = 0;
  function showProgress(text, pct, frameInfo = null) {
    if (!progressContainer) return;
    progressContainer.style.display = 'block';
    if (text && progressStatus) progressStatus.innerText = text;
    const clamped = Math.max(0, Math.min(100, Math.round(pct)));
    currentTickerPct = clamped;
    if (progressPercent) progressPercent.innerText = `${clamped}%`;
    if (progressBar) progressBar.style.width = `${clamped}%`;
    if (progressFrames) {
      if (frameInfo) {
        progressFrames.style.display = 'inline-block';
        progressFrames.innerText = frameInfo;
      } else if (!progressFrames.innerText || progressFrames.innerText === 'Frames: 0 / 0') {
        progressFrames.style.display = 'none';
      }
    }
  }
  function hideProgress() {
    if (progressTickerTimer) {
      clearTimeout(progressTickerTimer);
      clearInterval(progressTickerTimer);
      progressTickerTimer = null;
    }
    if (progressContainer) progressContainer.style.display = 'none';
    currentTickerPct = 0;
    if (progressFrames) {
      progressFrames.innerText = 'Frames: 0 / 0';
    }
  }
  function startSmoothProgressTicker(mediaType = 'video') {
    if (progressTickerTimer) {
      clearTimeout(progressTickerTimer);
      clearInterval(progressTickerTimer);
      progressTickerTimer = null;
    }
    currentTickerPct = 1;
    showProgress("Initializing stream ingestion...", 1);
    const isVideo = mediaType === 'video';
    const videoMilestones = [{
      pct: 15,
      text: "Uploading & validating video stream..."
    }, {
      pct: 30,
      text: "Decoding frames & calibrating neural engines..."
    }, {
      pct: 50
    }, {
      pct: 70,
      text: "Extracting plate crops & running Awiros ANPR-OCR..."
    }, {
      pct: 85,
      text: "Evaluating temporal consensus & biometric matching..."
    }, {
      pct: 92,
      text: "Cross-referencing wanted registry & MoRTH rules..."
    }, {
      pct: 96,
      text: "Generating forensic audit trails & compliance logs..."
    }, {
      pct: 99,
      text: "Assembling forensic evidence & packaging results..."
    }];
    const imageMilestones = [{
      pct: 20,
      text: "Uploading surveillance image..."
    }, {
      pct: 40,
      text: "Detecting vehicles & human targets..."
    }, {
      pct: 65,
      text: "Running Awiros ANPR-OCR & facial feature extraction..."
    }, {
      pct: 82,
      text: "Validating MoRTH syntax & plate geometry..."
    }, {
      pct: 92,
      text: "Checking police hotlist & wanted databases..."
    }, {
      pct: 96,
      text: "Writing forensic audit log & verification hashes..."
    }, {
      pct: 99,
      text: "Finalizing multi-modal detection summary..."
    }];
    const milestones = isVideo ? videoMilestones : imageMilestones;
    const lateHeartbeatTexts = ["Cross-referencing police wanted & FIR databases...", "Synthesizing multi-frame temporal voting consensus...", "Validating MoRTH High Security Plate compliance...", "Compiling tamper-proof forensic audit record..."];
    let heartbeatIdx = 0;
    function getMilestoneText(pct) {
      for (const m of milestones) {
        if (pct <= m.pct) return m.text;
      }
      return isVideo ? "Finalizing video analysis package..." : "Finalizing detection summary...";
    }
    function getTickDelay(pct) {
      if (isVideo) {
        if (pct < 20) return 350;
        if (pct < 45) return 550;
        if (pct < 70) return 850;
        if (pct < 85) return 1200;
        if (pct < 93) return 1800;
        if (pct < 97) return 2500;
        return 3500;
      } else {
        if (pct < 25) return 160;
        if (pct < 50) return 240;
        if (pct < 75) return 360;
        if (pct < 88) return 550;
        if (pct < 95) return 900;
        if (pct < 98) return 1500;
        return 2200;
      }
    }
    function tick() {
      if (currentTickerPct < 99) {
        currentTickerPct += 1;
        const statusText = getMilestoneText(currentTickerPct);
        showProgress(statusText, currentTickerPct);
      } else {
        const statusText = lateHeartbeatTexts[heartbeatIdx % lateHeartbeatTexts.length];
        heartbeatIdx++;
        showProgress(statusText, 99);
      }
      const nextDelay = getTickDelay(currentTickerPct);
      progressTickerTimer = setTimeout(tick, nextDelay);
    }
    progressTickerTimer = setTimeout(tick, getTickDelay(1));
  }
  function finishSmoothProgressTicker(frameInfo = null) {
    return new Promise(resolve => {
      if (progressTickerTimer) {
        clearTimeout(progressTickerTimer);
        clearInterval(progressTickerTimer);
        progressTickerTimer = null;
      }
      let finishPct = currentTickerPct;
      showProgress("Analysis complete! Finalizing output...", finishPct, frameInfo);
      const finishTimer = setInterval(() => {
        const remaining = 100 - finishPct;
        if (remaining <= 0) {
          clearInterval(finishTimer);
          showProgress("Analysis complete! Finalizing output...", 100, frameInfo);
          setTimeout(() => {
            hideProgress();
            resolve();
          }, 350);
          return;
        }
        const step = Math.max(1, Math.ceil(remaining / 4));
        finishPct = Math.min(100, finishPct + step);
        showProgress("Analysis complete! Finalizing output...", finishPct, frameInfo);
      }, 30);
    });
  }
  window.startSmoothProgressTicker = startSmoothProgressTicker;
  window.finishSmoothProgressTicker = finishSmoothProgressTicker;
  window.showAnprPhotoInspection = showAnprPhotoInspection;
  window.showAnprVideoInspection = showAnprVideoInspection;
  window.showProgress = showProgress;
  window.hideProgress = hideProgress;
  function startPolling() {
    if (progressTickerTimer) {
      clearTimeout(progressTickerTimer);
      clearInterval(progressTickerTimer);
      progressTickerTimer = null;
    }
    if (pollInterval) clearInterval(pollInterval);
    pollInterval = setInterval(async () => {
      try {
        const res = await fetch('/api/status');
        const data = await res.json();
        if (data.is_processing) {
          let statusText = `Processing frame ${data.current_frame} of ${data.total_frames}...`;
          if (data.progress >= 85 && data.progress < 93) {
            statusText = "Transcoding web video & optimizing streaming playback...";
          } else if (data.progress >= 93) {
            statusText = "Finalizing vehicle identity, consensus voting & hotlist cross-match...";
          }
          const frameLabel = data.total_frames ? `Frames: ${data.current_frame || 0} / ${data.total_frames}` : null;
          showProgress(statusText, data.progress || 0, frameLabel);
        } else if (data.has_results) {
          clearInterval(pollInterval);
          pollInterval = null;
          const finalFrameLabel = data.total_frames ? `Frames: ${data.total_frames} / ${data.total_frames}` : null;
          showProgress("Finalizing vehicle identity & voting...", 100, finalFrameLabel);
          setTimeout(async () => {
            hideProgress();
            await fetchAndRenderResults();
            try {
              const resResults = await fetch('/api/results');
              const resultsData = await resResults.json();
              if (resultsData.annotated_video_url) {
                showAnprVideoInspection(resultsData);
              }
            } catch (inspectErr) {
              console.error("Error loading video inspection:", inspectErr);
            }
          }, 500);
        }
      } catch (err) {
        console.error("Polling error:", err);
      }
    }, 800);
  }
  async function fetchAndRenderResults() {
    try {
      const res = await fetch('/api/results');
      const data = await res.json();
      if (data.status === 'no_results_yet') {
        currentResults = null;
        const viewport = document.getElementById('anprInspectionViewport');
        if (viewport) viewport.style.display = 'none';
        const inspectionContent = document.getElementById('anprInspectionContent');
        if (inspectionContent) inspectionContent.innerHTML = '';
        const dlBtn = document.getElementById('btnDownloadAnnotatedMedia');
        if (dlBtn) dlBtn.style.display = 'none';
        if (kpiVerifiedCount) kpiVerifiedCount.innerText = '0';
        if (kpiReviewCount) kpiReviewCount.innerText = '0';
        if (kpiTracksMerged) kpiTracksMerged.innerText = '0';
        if (kpiByteTrackIds) kpiByteTrackIds.innerText = '0';
        if (kpiCropsRejected) kpiCropsRejected.innerText = '0';
        if (verifiedCountBadge) verifiedCountBadge.innerText = '0 Verified';
        if (reviewCountBadge) reviewCountBadge.innerText = '0 In Review';
        renderVerifiedCards([]);
        renderReviewCards([]);
        return;
      }
      currentResults = data;
      const stats = data.stats || ({});
      if (kpiVerifiedCount) kpiVerifiedCount.innerText = stats.verified_total || 0;
      if (kpiReviewCount) kpiReviewCount.innerText = stats.needs_review_total || 0;
      if (kpiTracksMerged) kpiTracksMerged.innerText = stats.tracks_merged_into_vehicles || 0;
      if (kpiByteTrackIds) kpiByteTrackIds.innerText = stats.total_bytetrack_ids || 0;
      if (kpiCropsRejected) kpiCropsRejected.innerText = stats.crops_rejected_quality || 0;
      if (kpiTracksMergedDetail) kpiTracksMergedDetail.innerText = stats.tracks_merged_into_vehicles || 0;
      if (kpiByteTrackIdsDetail) kpiByteTrackIdsDetail.innerText = stats.total_bytetrack_ids || 0;
      if (kpiCropsRejectedDetail) kpiCropsRejectedDetail.innerText = stats.crops_rejected_quality || 0;
      verifiedCountBadge.innerText = `${stats.verified_total || 0} Verified`;
      reviewCountBadge.innerText = `${stats.needs_review_total || 0} In Review`;
      renderVerifiedCards(data.verified_vehicles || []);
      renderReviewCards(data.needs_review || []);
      await fetchAndRenderCapturedDb();
    } catch (err) {
      console.error("Error fetching results:", err);
    }
  }
  function renderVerifiedCards(vehicles) {
    if (!vehicles || vehicles.length === 0) {
      verifiedCardsContainer.innerHTML = `



                <div class="empty-state">



                    <p>No verified vehicles met the promotion criteria.</p>



                </div>



            `;
      return;
    }
    verifiedCardsContainer.innerHTML = vehicles.map((v, idx) => {
      const trackList = (v.linked_track_ids || []).map(id => `#${id}`).join(', ');
      const cropSrc = v.best_crop_base64 ? `data:image/jpeg;base64,${v.best_crop_base64}` : '';
      const hotlistBanner = renderHotlistBannerHtml(v.hotlist_match);
      return `



                <div class="vehicle-card">



                    ${hotlistBanner}



                    <div style="display: flex; justify-content: space-between; align-items: flex-start;">



                        <div class="hsrp-plate">



                            <div class="hsrp-ind-strip">



                                <span>IND</span>



                            </div>



                            <div class="hsrp-plate-text">${v.display_plate}</div>



                        </div>



                        <span class="conf-pill">${v.final_confidence}% Conf</span>



                    </div>



                    <div class="card-meta-row">



                        <div>Linked Tracks: <span class="meta-pill">${trackList}</span></div>



                        <div>Frames: <strong>${v.first_frame} &rarr; ${v.last_frame}</strong></div>



                    </div>



                    ${cropSrc ? `



                        <div class="crop-preview-box">



                            <img src="${cropSrc}" alt="Best Plate Crop">



                        </div>



                    ` : ''}



                    <div class="card-footer-actions">



                        <span>Supporting Frames: ${v.supporting_frames_count}</span>



                        <button class="btn-evidence" onclick="openEvidenceModal(${idx})">



                            Evidence (${v.evidence_frames.length})



                        </button>



                    </div>



                </div>



            `;
    }).join('');
  }
  function renderReviewCards(vehicles) {
    if (!vehicles || vehicles.length === 0) {
      reviewCardsContainer.innerHTML = `



                <div class="empty-state">



                    <p>No uncertain items in review.</p>



                </div>



            `;
      return;
    }
    reviewCardsContainer.innerHTML = vehicles.map(v => {
      const trackList = (v.linked_track_ids || []).map(id => `#${id}`).join(', ');
      const cropSrc = v.best_crop_base64 ? `data:image/jpeg;base64,${v.best_crop_base64}` : '';
      const hotlistBanner = renderHotlistBannerHtml(v.hotlist_match);
      return `



                <div class="vehicle-card review-card">



                    ${hotlistBanner}



                    <div style="display: flex; justify-content: space-between; align-items: flex-start;">



                        <div>



                            <div style="font-family: var(--font-mono); font-size: 1.1rem; font-weight: 700; color: #475569;">



                                ${v.final_plate || "UNREADABLE / PARTIAL"}



                            </div>



                            <div style="font-size: 0.875rem; color: var(--text-muted); margin-top: 2px;">



                                Candidate Reading



                            </div>



                        </div>



                        <span class="conf-pill conf-low">${v.final_confidence}% Conf</span>



                    </div>



                    <div>



                        <span class="reason-tag">${v.review_reason || "Uncertain Reading"}</span>



                    </div>



                    <div class="card-meta-row">



                        <div>Track: <span class="meta-pill">${trackList}</span></div>



                        <div>Frames: <strong>${v.first_frame} &rarr; ${v.last_frame}</strong></div>



                    </div>



                    ${cropSrc ? `



                        <div class="crop-preview-box">



                            <img src="${cropSrc}" alt="Plate Crop">



                        </div>



                    ` : ''}



                    <div class="card-footer-actions" style="margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--border-color); display: flex; justify-content: space-between; align-items: center;">



                        <span style="font-size: 0.875rem; color: var(--text-muted);">Human Review Required</span>



                        <button class="btn btn-primary" style="padding: 5px 12px; font-size: 0.875rem; background: #6366f1;" onclick="confirmReviewVehicle('${escapeHtml(v.final_plate || '')}', '${v.best_crop_base64 || ''}', '${v.best_vehicle_crop_base64 || ''}', ${v.final_confidence || 0}, '${v.best_annotated_frame_base64 || ''}')">



                            Confirm &amp; Log Sighting



                        </button>



                    </div>



                </div>



            `;
    }).join('');
  }
  window.openEvidenceModal = index => {
    if (!currentResults || !currentResults.verified_vehicles[index]) return;
    const vehicle = currentResults.verified_vehicles[index];
    const sortedFrames = (vehicle.evidence_frames || []).slice().sort((a, b) => (b.confidence || 0) - (a.confidence || 0));
    modalTitle.innerText = `Evidence for ${vehicle.display_plate} (Peak: ${vehicle.final_confidence}%)`;
    modalEvidenceList.innerHTML = sortedFrames.map(ef => `



            <div class="evidence-row">



                <img src="data:image/jpeg;base64,${ef.crop_base64}" alt="Frame Crop">



                <div>



                    <div style="font-family: var(--font-mono); font-weight: 700;">${ef.text}</div>



                    <div style="font-size: 0.875rem; color: var(--text-secondary);">



                        Frame ${ef.frame_idx} • Track #${ef.track_id}



                    </div>



                </div>



                <div class="conf-pill" style="font-weight: 700;">${ef.confidence}%</div>



            </div>



        `).join('');
    evidenceModal.style.display = 'flex';
  };
  if (modalCloseBtn) {
    modalCloseBtn.addEventListener('click', () => {
      evidenceModal.style.display = 'none';
    });
  }
  const capturedListContainer = document.getElementById('capturedListContainer') || document.getElementById('capturedCardsContainer');
  const capturedCountBadge = document.getElementById('capturedCountBadge');
  const capturedSearchInput = document.getElementById('capturedSearchInput');
  const btnRefreshCaptured = document.getElementById('btnRefreshCaptured');
  const btnClearCaptured = document.getElementById('btnClearCaptured');
  const capFilterBtns = document.querySelectorAll('[data-capfilter]');
  let currentCapturedFilter = 'all';
  let capturedSearchDebounce = null;
  function updateLiveOsdClock() {
    const osdEl = document.getElementById('liveTimestamp');
    if (osdEl) {
      const now = new Date();
      const dateStr = now.toISOString().replace('T', ' ').substring(0, 19);
      osdEl.innerText = `${dateStr} IST`;
    }
  }
  setInterval(updateLiveOsdClock, 1000);
  updateLiveOsdClock();
  let isFetchingCapturedDb = false;
  async function fetchAndRenderCapturedDb() {
    if (isFetchingCapturedDb) return;
    isFetchingCapturedDb = true;
    try {
      if (typeof fetchAndRenderDrawerVehicles === 'function') {
        try {
          fetchAndRenderDrawerVehicles();
        } catch (_) {}
      }
      if (!currentUser || !capturedListContainer) return;
      const query = capturedSearchInput ? capturedSearchInput.value.trim() : '';
      const isHotlistOnly = currentCapturedFilter === 'hotlist';
      let url = `/api/captured?limit=100&hotlist_only=${isHotlistOnly}`;
      if (query) {
        url += `&search=${encodeURIComponent(query)}`;
      }
      const res = await fetch(url);
      const data = await res.json();
      const items = (data.captured || []).filter(window.isVisibleVehicleDetection);
      if (capturedCountBadge) {
        capturedCountBadge.innerText = `${items.length} Captures · >80%`;
      }
      if (items.length === 0) {
        if (capturedListContainer.dataset.lastSig !== 'empty') {
          capturedListContainer.dataset.lastSig = 'empty';
          capturedListContainer.innerHTML = `



                    <div class="empty-state" style="padding: 40px 16px;">



                        <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">



                            <rect x="3" y="4" width="18" height="16" rx="2"/>



                            <line x1="16" y1="2" x2="16" y2="6"/>



                            <line x1="8" y1="2" x2="8" y2="6"/>



                            <line x1="3" y1="10" x2="21" y2="10"/>



                        </svg>



                        <p style="margin-top: 10px; font-size: 1.0125rem; color: var(--text-primary);">No vehicles captured in database yet.</p>



                        <p style="font-size: 0.875rem; color: var(--text-secondary);">Upload a video, run the demo scenario, or upload a photo to log recent captures here.</p>



                    </div>
                `;
        }
        return;
      }
      const capDbSig = items.map(c => `${c.id}_${c.captured_at}_${c.confidence}_${c.plate_number}`).join('|');
      if (capturedListContainer.dataset.lastSig === capDbSig) return;
      capturedListContainer.dataset.lastSig = capDbSig;
      capturedListContainer.innerHTML = items.map((c, idx) => {
        const posNum = idx + 1;
        const isHit = c.is_hotlist_hit;
        const dateStr = c.captured_at || 'N/A';
        const isUnreadable = c.plate_number === 'UNREADABLE' || c.display_plate && c.display_plate.includes('UNREADABLE');
        const plateText = escapeHtml(c.display_plate || c.plate_number || 'UNKNOWN');
        const ocrConf = c.ocr_confidence ? c.ocr_confidence : c.confidence;
        const thumbSrc = c.plate_pic_path || c.vehicle_pic_path || '';
        const hotlistTag = isHit ? `



                    <span class="cap-hotlist-tag">



                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>



                        HOTLIST ALERT



                    </span>



                ` : '';
        let evCount = 1;
        if (c.evidence_json) {
          try {
            const parsed = JSON.parse(c.evidence_json);
            if (Array.isArray(parsed) && parsed.length > 0) evCount = parsed.length;
          } catch (e) {}
        }
        const plateBadgeHtml = isUnreadable ? `



                    <div class="hsrp-plate unreadable-plate" style="transform: scale(0.88); transform-origin: left center; background: #e2e8f0; border: 1px solid #475569;">



                        <div class="hsrp-ind-strip" style="background: #334155;">



                            <span style="color: #52647c; font-weight: 700;">?</span>



                        </div>



                        <div class="hsrp-plate-text" style="color: #475569; font-weight: 600; font-size: 0.875rem; letter-spacing: 0.5px;">UNREADABLE</div>



                    </div>



                ` : `



                    <div class="hsrp-plate" style="transform: scale(0.88); transform-origin: left center;">



                        <div class="hsrp-ind-strip">



                            <span>IND</span>



                        </div>



                        <div class="hsrp-plate-text">${plateText}</div>



                    </div>



                `;
        const confPillHtml = isUnreadable ? `<span class="meta-pill" style="font-size: 0.875rem; background: rgba(148,163,184,0.15); color: #52647c; border-color: rgba(148,163,184,0.3);" title="Plate detected (${c.det_confidence || c.confidence}% det) but text illegible">UNREADABLE</span>` : `<span class="conf-pill" style="font-size: 0.875rem;">OCR: ${ocrConf}%</span>`;
        return `



                    <div class="captured-list-row ${isHit ? 'is-hotlist' : ''}" onclick="openCaptureDetailModal(${c.id})">



                        <!-- Left: Rank + Thumbnail + Plate -->



                        <div class="captured-list-left">



                            <span class="cap-rank-badge ${posNum === 1 ? 'newest' : ''}">



                                #${posNum} ${posNum === 1 ? '<span style="font-size:0.875rem; display:block;">NEW</span>' : ''}



                            </span>



                            <div class="cap-row-thumb">



                                ${thumbSrc ? `<img src="${thumbSrc}" alt="Plate" onerror="this.onerror=null; this.parentElement.innerHTML='<span style=\\'font-size:0.875rem;color:var(--text-muted);display:flex;align-items:center;justify-content:center;height:100%;\\'>No Crop</span>';">` : `<span style="font-size: 0.875rem; color: var(--text-muted);">No crop</span>`}



                            </div>



                            ${plateBadgeHtml}



                        </div>



                        <!-- Mid: Meta info (Timestamp, Location, Source, Hotlist note) -->



                        <div class="captured-list-mid">



                            <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">



                                ${hotlistTag}



                                <span style="font-size: 0.875rem; font-weight: 600; color: var(--text-primary);">${escapeHtml(c.location || 'Surveillance Gate')}</span>



                                <span style="font-size: 0.875rem; color: var(--text-muted);">&bull; ${c.source_type === 'image_upload' ? 'Photo Upload' : 'Video Feed'}</span>



                            </div>



                            <div class="cap-mid-meta">



                                <span>${dateStr}</span>



                                ${isHit && c.hotlist_info ? `<span style="color: #ef4444; font-size: 0.875rem;">${escapeHtml(c.hotlist_info)}</span>` : ''}



                            </div>



                        </div>



                        <!-- Right: Quality Pills, Inspect Button, Delete Button -->



                        <div class="captured-list-right">



                            ${confPillHtml}



                            ${evCount > 1 ? `<span class="meta-pill" style="font-size: 0.875rem; color: #818cf8; border-color: rgba(99,102,241,0.3); background: rgba(99,102,241,0.08);" title="${evCount} supporting AI frames">Evidence (${evCount})</span>` : ''}



                            ${c.blur_score ? `<span class="meta-pill" style="font-size: 0.875rem;">Blur: ${c.blur_score}</span>` : ''}



                            <button class="cap-inspect-btn" title="Inspect Vehicle & Technical Diagnostics" onclick="event.stopPropagation(); openCaptureDetailModal(${c.id})">



                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><line x1="11" y1="8" x2="11" y2="14"/><line x1="8" y1="11" x2="14" y2="11"/></svg>



                                Inspect



                            </button>



                            <button class="btn-danger" style="padding: 4px 8px; font-size: 0.875rem;" title="Delete Capture" onclick="event.stopPropagation(); deleteCapture(${c.id}, '${escapeHtml(c.plate_number)}')">



                                &times;



                            </button>



                        </div>



                    </div>



                `;
      }).join('');
    } catch (err) {
      console.error("Error fetching Captured DB:", err);
    } finally {
      isFetchingCapturedDb = false;
    }
  }
  const INDIAN_STATE_CODES = {
    'AP': 'Andhra Pradesh',
    'AR': 'Arunachal Pradesh',
    'AS': 'Assam',
    'BR': 'Bihar',
    'CG': 'Chhattisgarh',
    'CH': 'Chandigarh',
    'DD': 'Daman & Diu',
    'DL': 'Delhi',
    'DN': 'Dadra & Nagar Haveli',
    'GA': 'Goa',
    'GJ': 'Gujarat',
    'HP': 'Himachal Pradesh',
    'HR': 'Haryana',
    'JH': 'Jharkhand',
    'JK': 'Jammu & Kashmir',
    'KA': 'Karnataka',
    'KL': 'Kerala',
    'LA': 'Ladakh',
    'LD': 'Lakshadweep',
    'MH': 'Maharashtra',
    'ML': 'Meghalaya',
    'MN': 'Manipur',
    'MP': 'Madhya Pradesh',
    'MZ': 'Mizoram',
    'NL': 'Nagaland',
    'OD': 'Odisha',
    'PB': 'Punjab',
    'PY': 'Puducherry',
    'RJ': 'Rajasthan',
    'SK': 'Sikkim',
    'TN': 'Tamil Nadu',
    'TR': 'Tripura',
    'TS': 'Telangana',
    'UK': 'Uttarakhand',
    'UP': 'Uttar Pradesh',
    'WB': 'West Bengal'
  };
  let activeModalCapture = null;
  let currentPipeStepIndex = 1;
  let currentPipeViewMode = 'stepper';
  window.setPrepModalView = mode => {
    const sideViews = document.querySelectorAll('.prep-side-by-side');
    const slideViews = document.querySelectorAll('.prep-slider-view');
    const btnSides = document.querySelectorAll('.prep-btn-side');
    const btnSlides = document.querySelectorAll('.prep-btn-slide');
    if (mode === 'side') {
      sideViews.forEach(el => el.style.display = 'grid');
      slideViews.forEach(el => el.style.display = 'none');
      btnSides.forEach(btn => btn.classList.add('active'));
      btnSlides.forEach(btn => btn.classList.remove('active'));
    } else {
      sideViews.forEach(el => el.style.display = 'none');
      slideViews.forEach(el => el.style.display = 'flex');
      btnSides.forEach(btn => btn.classList.remove('active'));
      btnSlides.forEach(btn => btn.classList.add('active'));
    }
  };
  window.updatePrepSlider = val => {
    const afterLayers = document.querySelectorAll('.prep-slider-after-layer');
    const dividers = document.querySelectorAll('.prep-divider-line');
    afterLayers.forEach(el => el.style.clipPath = `inset(0 0 0 ${val}%)`);
    dividers.forEach(el => el.style.left = `${val}%`);
  };
  window.setPipeModalMode = mode => {
    currentPipeViewMode = mode;
    const panoramicWrap = document.getElementById('pipePanoramicViewWrap') || document.getElementById('pipeStepperViewWrap');
    const matrixWrap = document.getElementById('pipeMatrixViewWrap');
    const btnPanoramic = document.getElementById('btnModePanoramic') || document.getElementById('btnModeStepper');
    const btnMatrix = document.getElementById('btnModeMatrix');
    if (mode === 'panoramic' || mode === 'stepper') {
      if (panoramicWrap) panoramicWrap.style.display = 'flex';
      if (matrixWrap) matrixWrap.style.display = 'none';
      if (btnPanoramic) btnPanoramic.classList.add('active');
      if (btnMatrix) btnMatrix.classList.remove('active');
    } else {
      if (panoramicWrap) panoramicWrap.style.display = 'none';
      if (matrixWrap) matrixWrap.style.display = 'block';
      if (btnPanoramic) btnPanoramic.classList.remove('active');
      if (btnMatrix) btnMatrix.classList.add('active');
    }
  };
  window.setPipeStep = step => {
    currentPipeStepIndex = Math.max(1, Math.min(5, step));
    window.renderPipelineStepperModal(currentPipeStepIndex);
  };
  window.nextPipeStep = () => {
    if (currentPipeStepIndex < 5) {
      currentPipeStepIndex++;
      window.renderPipelineStepperModal(currentPipeStepIndex);
    }
  };
  window.prevPipeStep = () => {
    if (currentPipeStepIndex > 1) {
      currentPipeStepIndex--;
      window.renderPipelineStepperModal(currentPipeStepIndex);
    }
  };
  window.renderPipelineStepperModal = stepIndex => {
    const c = activeModalCapture;
    if (!c) return;
    currentPipeStepIndex = stepIndex;
    const stepProgress = document.getElementById('pipeStepProgress');
    if (stepProgress) {
      stepProgress.style.width = `${(stepIndex - 1) / 4 * 100}%`;
    }
    for (let i = 1; i <= 5; i++) {
      const node = document.getElementById(`pipeNodeStep${i}`);
      if (!node) continue;
      node.classList.remove('active', 'completed');
      if (i === stepIndex) {
        node.classList.add('active');
      } else if (i < stepIndex) {
        node.classList.add('completed');
      }
    }
    const stageCard = document.getElementById('pipeStageCard');
    if (!stageCard) return;
    const isHit = c.is_hotlist_hit;
    const isUnreadable = c.plate_number === 'UNREADABLE' || c.display_plate && c.display_plate.includes('UNREADABLE');
    const plateText = escapeHtml(c.display_plate || c.plate_number || 'UNKNOWN');
    const evFrames = c.evidence_frames || [];
    let peakOcr = c.ocr_confidence || c.confidence || 0;
    let peakDet = c.det_confidence || 0;
    if (evFrames && evFrames.length > 0) {
      for (const ef of evFrames) {
        if (ef.confidence && ef.confidence > peakOcr) peakOcr = ef.confidence;
      }
    }
    const ocrConf = peakOcr;
    const detConf = peakDet ? `${peakDet}%` : c.det_confidence ? `${c.det_confidence}%` : 'N/A';
    const blurVal = c.blur_score ? `${c.blur_score}` : 'N/A';
    const blurQuality = c.blur_score ? c.blur_score >= 100 ? 'Sharp (>100.0)' : 'Soft / Low Contrast' : 'N/A';
    const aspectVal = c.aspect_ratio ? `${c.aspect_ratio}` : 'N/A';
    const fmtType = c.format_type ? escapeHtml(c.format_type) : 'Standard Indian MoRTH';
    const dateStr = c.captured_at || 'N/A';
    const sceneImgSrc = c.annotated_pic_path || c.vehicle_pic_path || c.plate_pic_path || '';
    const plateCropSrc = c.plate_pic_path || '';
    const vehicleCropSrc = c.vehicle_pic_path || '';
    const cleanPlate = (c.plate_number || '').replace(/[^A-Za-z0-9]/g, '').toUpperCase();
    const stCode = cleanPlate.substring(0, 2);
    const rtoCode = cleanPlate.substring(2, 4);
    const stateName = typeof INDIAN_STATE_CODES !== 'undefined' && INDIAN_STATE_CODES[stCode] ? INDIAN_STATE_CODES[stCode] : 'MoRTH State Jurisdiction';
    let stageTitle = '';
    let stageBadge = '';
    let stageBadgeStyle = '';
    let stageDesc = '';
    let stageVisualHtml = '';
    let metricsHtml = '';
    if (stepIndex === 1) {
      stageTitle = 'Stage 01: Raw Uncut Surveillance Frame';
      stageBadge = 'CCTV Sensor Feed';
      stageBadgeStyle = 'background: rgba(59, 130, 246, 0.2); color: #1d4ed8; border: 1px solid rgba(59, 130, 246, 0.4);';
      stageDesc = 'Original high-resolution camera sensor frame captured directly from the video feed before any neural bounding boxes or crops.';
      stageVisualHtml = sceneImgSrc ? `



                <div style="position: relative; width: 100%; display: flex; justify-content: center; background: #000;">



                    <img src="${sceneImgSrc}" alt="Raw Scene" style="max-height: 280px; width: 100%; object-fit: contain;">



                    <div style="position: absolute; bottom: 8px; left: 8px; background: rgba(0,0,0,0.75); border: 1px solid rgba(255,255,255,0.15); padding: 3px 8px; border-radius: 4px; font-size: 0.875rem; font-family: var(--font-mono); color: #475569;">



                        Sensor: ${escapeHtml(c.location || 'Surveillance Gate')} &bull; ${dateStr}



                    </div>



                </div>



            ` : '<div style="padding: 40px; color: var(--text-muted); font-size: 0.9125rem;">No scene image available</div>';
      metricsHtml = `



                <div class="pipe-metric-box">



                    <span class="pipe-metric-lbl">Ingestion Source</span>



                    <span class="pipe-metric-val">${escapeHtml(c.source_type || 'Surveillance Video Feed')}</span>



                </div>



                <div class="pipe-metric-box">



                    <span class="pipe-metric-lbl">Camera Location</span>



                    <span class="pipe-metric-val">${escapeHtml(c.location || 'Surveillance Gate')}</span>



                </div>



                <div class="pipe-metric-box">



                    <span class="pipe-metric-lbl">Sensor Timestamp</span>



                    <span class="pipe-metric-val" style="font-size: 0.875rem;">${dateStr}</span>



                </div>



                <div class="pipe-metric-box">



                    <span class="pipe-metric-lbl">Capture ID</span>



                    <span class="pipe-metric-val">#${c.id}</span>



                </div>



            `;
    } else if (stepIndex === 2) {
      stageTitle = 'Stage 02: Vehicle Localization & Tracking';
      stageBadge = 'Vehicle Detector';
      stageBadgeStyle = 'background: rgba(245, 158, 11, 0.2); color: #92400e; border: 1px solid rgba(245, 158, 11, 0.4);';
      stageDesc = 'Vehicle detector localized the automobile body and linked consecutive frames into a stable trajectory.';
      stageVisualHtml = vehicleCropSrc ? `



                <div style="position: relative; width: 100%; display: flex; justify-content: center; background: #000;">



                    <img src="${vehicleCropSrc}" alt="Vehicle Crop" style="max-height: 260px; width: 100%; object-fit: contain;">



                    <div style="position: absolute; top: 8px; left: 8px; background: rgba(245, 158, 11, 0.9); color: #000; padding: 2px 8px; border-radius: 4px; font-size: 0.875rem; font-weight: 700; font-family: var(--font-mono);">



                        ${escapeHtml((c.vehicle_class || 'car').toUpperCase())} &bull; ${detConf}



                    </div>



                </div>



            ` : sceneImgSrc ? `



                <div style="position: relative; width: 100%; display: flex; justify-content: center; background: #000;">



                    <img src="${sceneImgSrc}" alt="Vehicle Scene" style="max-height: 260px; width: 100%; object-fit: contain;">



                </div>



            ` : '<div style="padding: 40px; color: var(--text-muted); font-size: 0.9125rem;">No vehicle crop available</div>';
      metricsHtml = `



                <div class="pipe-metric-box">



                    <span class="pipe-metric-lbl">Vehicle Category</span>



                    <span class="pipe-metric-val" style="color: #92400e;">${escapeHtml((c.vehicle_class || 'car').toUpperCase())}</span>



                </div>



                <div class="pipe-metric-box">



                    <span class="pipe-metric-lbl">Trajectory Track ID</span>



                    <span class="pipe-metric-val font-mono">Track #${c.track_id || c.id}</span>



                </div>



                <div class="pipe-metric-box">



                    <span class="pipe-metric-lbl">Detection Confidence</span>



                    <span class="pipe-metric-val" style="color: #0369a1;">${detConf}</span>



                </div>



                <div class="pipe-metric-box">



                    <span class="pipe-metric-lbl">Temporal Sightings</span>



                    <span class="pipe-metric-val">${evFrames.length > 0 ? `${evFrames.length} Frames Tracked` : 'Single Sighting'}</span>



                </div>



            `;
    } else if (stepIndex === 3) {
      stageTitle = 'Stage 03: License Plate Localization';
      stageBadge = 'Plate Localization';
      stageBadgeStyle = 'background: rgba(99, 102, 241, 0.2); color: #4338ca; border: 1px solid rgba(99, 102, 241, 0.4);';
      stageDesc = 'Specialized high-precision plate detector isolated the exact Indian registration plate geometry from the vehicle bounding box.';
      stageVisualHtml = plateCropSrc ? `



                <div style="position: relative; width: 100%; display: flex; justify-content: center; align-items: center; padding: 20px; background: #000;">



                    <img src="${plateCropSrc}" alt="Plate Crop" style="max-height: 120px; max-width: 90%; object-fit: contain; border: 2px solid #6366f1; border-radius: 6px; box-shadow: 0 0 20px rgba(99, 102, 241, 0.3);">



                </div>



            ` : '<div style="padding: 40px; color: var(--text-muted); font-size: 0.9125rem;">No plate crop available</div>';
      metricsHtml = `



                <div class="pipe-metric-box">



                    <span class="pipe-metric-lbl">Plate Det Confidence</span>



                    <span class="pipe-metric-val" style="color: #4338ca;">${detConf}</span>



                </div>



                <div class="pipe-metric-box">



                    <span class="pipe-metric-lbl">Aspect Ratio (W/H)</span>



                    <span class="pipe-metric-val">${aspectVal}</span>



                </div>



                <div class="pipe-metric-box">



                    <span class="pipe-metric-lbl">Crop Quality Gate</span>



                    <span class="pipe-metric-val" style="color: ${c.quality_gate_passed ? '#10b981' : '#ef4444'};">



                        ${c.quality_gate_passed ? 'ACCEPTED FOR OCR' : 'FLAGGED'}



                    </span>



                </div>



            `;
    } else if (stepIndex === 4) {
      stageTitle = 'Stage 04: Character Recognition & Temporal Consensus';
      stageBadge = 'Deep ANPR-OCR Engine';
      stageBadgeStyle = 'background: rgba(168, 85, 247, 0.2); color: #7e22ce; border: 1px solid rgba(168, 85, 247, 0.4);';
      stageDesc = 'Neural character recognition predicts alphanumeric glyphs across multi-frame readings and votes on the final consensus string.';
      let evCardsHtml = '';
      if (evFrames && evFrames.length > 0) {
        evCardsHtml = `



                    <div style="margin-top: 14px; width: 100%;">



                        <div style="font-size: 0.875rem; font-weight: 700; color: #475569; margin-bottom: 8px; display: flex; align-items: center; justify-content: space-between;">



                            <span>Temporal Voting Frame Consensus (${evFrames.length} Frames)</span>



                            <span style="color: #4338ca; font-family: var(--font-mono); font-size: 0.875rem;">Consensus Plate: ${plateText}</span>



                        </div>



                        <div class="evidence-scroll-row">



                            ${evFrames.map(ef => `



                                <div class="evidence-card" style="min-width: 150px; padding: 8px;">



                                    <div style="height: 50px; background: #000; border-radius: 4px; overflow: hidden; display: flex; align-items: center; justify-content: center;">



                                        ${ef.crop_base64 ? `<img src="data:image/jpeg;base64,${ef.crop_base64}" alt="Frame ${ef.frame_idx}" style="max-height: 100%; max-width: 100%; object-fit: contain;">` : plateCropSrc ? `<img src="${plateCropSrc}" style="max-height:100%; object-fit:contain;">` : ''}



                                    </div>



                                    <div style="font-family: var(--font-mono); font-size: 0.875rem; font-weight: 700; color: #172033; text-align: center; margin-top: 4px;">



                                        ${escapeHtml(ef.text || c.plate_number)}



                                    </div>



                                    <div style="display: flex; justify-content: space-between; font-size: 0.875rem; color: var(--text-muted); margin-top: 2px;">



                                        <span>Frame #${ef.frame_idx}</span>



                                        <span class="conf-pill" style="font-size: 0.875rem; padding: 1px 5px;">${ef.confidence}%</span>



                                    </div>



                                </div>



                            `).join('')}



                        </div>



                    </div>



                `;
      }
      stageVisualHtml = `



                <div style="width: 100%; padding: 16px; display: flex; flex-direction: column; align-items: center; gap: 14px;">



                    <div style="display: flex; flex-direction: column; align-items: center; gap: 8px;">



                        <span style="font-size: 0.875rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px; font-weight: 600;">Recognized Plate Output</span>



                        <div class="hsrp-plate" style="transform: scale(1.1); margin: 6px 0;">



                            <div class="hsrp-ind-strip"><span>IND</span></div>



                            <div class="hsrp-plate-text">${plateText}</div>



                        </div>



                    </div>



                    ${evCardsHtml}



                </div>



            `;
      metricsHtml = `



                <div class="pipe-metric-box">



                    <span class="pipe-metric-lbl">Peak OCR Confidence</span>



                    <span class="pipe-metric-val" style="color: #10b981;">${ocrConf}%</span>



                </div>



                <div class="pipe-metric-box">



                    <span class="pipe-metric-lbl">Temporal Frame Consensus</span>



                    <span class="pipe-metric-val" style="color: #818cf8;">${evFrames.length > 0 ? `${evFrames.length} Frames Voted` : 'Single Frame'}</span>



                </div>



                <div class="pipe-metric-box">



                    <span class="pipe-metric-lbl">Raw Character String</span>



                    <span class="pipe-metric-val" style="letter-spacing: 1px;">${escapeHtml(c.plate_number)}</span>



                </div>



                <div class="pipe-metric-box">



                    <span class="pipe-metric-lbl">Glyph Segmentation</span>



                    <span class="pipe-metric-val" style="color: #0369a1;">${isUnreadable ? 'FAILED' : 'SUCCESSFUL'}</span>



                </div>



            `;
    } else if (stepIndex === 5) {
      stageTitle = 'Stage 05: MoRTH Syntax & Police Hotlist Gate';
      stageBadge = isHit ? 'HOTLIST POLICE ALERT' : 'MoRTH Rule Engine';
      stageBadgeStyle = isHit ? 'background: rgba(239, 68, 68, 0.2); color: #b91c1c; border: 1px solid rgba(239, 68, 68, 0.4);' : 'background: rgba(16, 185, 129, 0.2); color: #047857; border: 1px solid rgba(16, 185, 129, 0.4);';
      stageDesc = 'Final compliance gate validates the 10-character Indian High Security Registration Plate format and queries the stolen vehicle database.';
      stageVisualHtml = `



                <div style="width: 100%; padding: 20px; display: flex; flex-direction: column; gap: 14px;">



                    <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; background: rgba(241,245,249,0.7); border: 1px solid rgba(255,255,255,0.08); padding: 14px 18px; border-radius: 8px;">



                        <div style="display: flex; align-items: center; gap: 14px;">



                            <div style="width: 42px; height: 42px; border-radius: 50%; background: ${c.quality_gate_passed ? 'rgba(16,185,129,0.15)' : 'rgba(239,68,68,0.15)'}; border: 1px solid ${c.quality_gate_passed ? '#10b981' : '#ef4444'}; color: ${c.quality_gate_passed ? '#10b981' : '#ef4444'}; display: flex; align-items: center; justify-content: center; font-size: 1.2rem; font-weight: bold;">



                                ${c.quality_gate_passed ? '&check;' : '&times;'}



                            </div>



                            <div>



                                <h4 style="margin: 0; font-size: 1.0125rem; color: #ffffff;">



                                    ${c.quality_gate_passed ? 'MoRTH Format Verified &amp; Legitimate' : 'MoRTH Format Unverified / Review Required'}



                                </h4>



                                <p style="margin: 2px 0 0 0; font-size: 0.875rem; color: var(--text-muted);">



                                    Syntax Type: ${fmtType} &bull; Jurisdiction: <strong>${stateName}</strong>



                                </p>



                            </div>



                        </div>



                        <div class="hsrp-plate" style="transform: scale(0.9); transform-origin: right center;">



                            <div class="hsrp-ind-strip"><span>IND</span></div>



                            <div class="hsrp-plate-text">${plateText}</div>



                        </div>



                    </div>



                    ${isHit ? `



                        <div class="hotlist-alert-banner hotlist-alert-case" style="margin: 0;">



                            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" style="flex-shrink: 0; margin-top: 1px;">



                                <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>



                                <line x1="12" y1="9" x2="12" y2="13"/>



                                <line x1="12" y1="17" x2="12.01" y2="17"/>



                            </svg>



                            <div style="flex: 1;">



                                <span class="hotlist-alert-title">HOTLIST ALERT MATCH (WANTED / POLICE WATCHLIST)</span>



                                <div style="font-size: 0.875rem; line-height: 1.4; margin-top: 2px;">



                                    ${escapeHtml(c.hotlist_info || 'Cross-matched against police records / stolen vehicle registry')}



                                </div>



                            </div>



                        </div>



                    ` : `



                        <div style="background: rgba(16, 185, 129, 0.08); border: 1px solid rgba(16, 185, 129, 0.25); border-radius: 6px; padding: 10px 14px; display: flex; align-items: center; gap: 10px;">



                            <span style="color: #10b981; font-weight: 700; font-size: 0.9625rem;">&check;</span>



                            <span style="font-size: 0.875rem; color: #166534;">Security Hotlist Check: <strong>CLEAN</strong> (No active stolen FIR or police watch warrant)</span>



                        </div>



                    `}



                </div>



            `;
      metricsHtml = `



                <div class="pipe-metric-box">



                    <span class="pipe-metric-lbl">State Code</span>



                    <span class="pipe-metric-val" style="color: #0369a1;">${stCode || 'N/A'} (${stateName})</span>



                </div>



                <div class="pipe-metric-box">



                    <span class="pipe-metric-lbl">RTO District Code</span>



                    <span class="pipe-metric-val">${rtoCode || 'N/A'}</span>



                </div>



                <div class="pipe-metric-box">



                    <span class="pipe-metric-lbl">Compliance Gate</span>



                    <span class="pipe-metric-val" style="color: ${c.quality_gate_passed ? '#10b981' : '#ef4444'};">



                        ${c.quality_gate_passed ? 'PASSED &amp; LOGGED' : 'REJECTED / REVIEW'}



                    </span>



                </div>



                <div class="pipe-metric-box">



                    <span class="pipe-metric-lbl">Security Registry</span>



                    <span class="pipe-metric-val" style="color: ${isHit ? '#ef4444' : '#10b981'};">



                        ${isHit ? 'ALERT HIT' : 'CLEAN'}



                    </span>



                </div>



            `;
    }
    stageCard.innerHTML = `



            <div class="pipe-stage-header">



                <div class="pipe-stage-title-wrap">



                    <div class="pipe-stage-headline">



                        <span>${stageTitle}</span>



                        <span class="pipe-stage-badge" style="${stageBadgeStyle}">${stageBadge}</span>



                    </div>



                    <p class="pipe-stage-desc">${stageDesc}</p>



                </div>



                <div style="text-align: right; flex-shrink: 0;">



                    <span style="font-size: 0.875rem; color: var(--text-muted); font-family: var(--font-mono); display: block;">AUDIT STAGE</span>



                    <span style="font-size: 0.875rem; font-weight: 700; color: #0369a1; font-family: var(--font-mono);">${stepIndex} / 5 VERIFIED</span>



                </div>



            </div>



            <div class="pipe-stage-visual">



                ${stageVisualHtml}



            </div>



            <div class="pipe-stage-metrics-grid">



                ${metricsHtml}



            </div>



            <!-- Stepper Navigation Footer -->



            <div class="pipe-nav-footer">



                <button type="button" class="btn btn-secondary" style="padding: 6px 14px; font-size: 0.875rem;" onclick="prevPipeStep()" ${stepIndex === 1 ? 'disabled style="opacity:0.4; cursor:not-allowed;"' : ''}>



                    &larr; Previous Step



                </button>



                <span style="font-size: 0.875rem; color: var(--text-muted); font-family: var(--font-mono);">



                    Viewing Stage ${stepIndex} of 5 &bull; <strong style="color: #1e293b;">${stageTitle.split(':')[1] || stageTitle}</strong>



                </span>



                <button type="button" class="btn btn-primary" style="padding: 6px 14px; font-size: 0.875rem; background: #3b82f6;" onclick="nextPipeStep()" ${stepIndex === 5 ? 'disabled style="opacity:0.4; cursor:not-allowed;"' : ''}>



                    Next Step &rarr;



                </button>



            </div>



        `;
  };
  window.openCaptureDetailModal = async captureId => {
    try {
      const numId = Number(captureId);
      const cachedV = window._freshVehiclesCache ? window._freshVehiclesCache.get(numId) : null;
      if (cachedV && typeof captureDetailModal !== 'undefined' && captureDetailModal) {
        if (typeof capModalRankBadge !== 'undefined' && capModalRankBadge) capModalRankBadge.innerText = `Capture #${cachedV.id}`;
        if (typeof capModalPlateText !== 'undefined' && capModalPlateText) capModalPlateText.innerText = escapeHtml(cachedV.display_plate || cachedV.plate_number || 'UNKNOWN');
        captureDetailModal.style.display = 'flex';
      }
      const res = await fetch(`/api/captured/${captureId}`);
      if (!res.ok) {
        alert("Capture record not found.");
        return;
      }
      const data = await res.json();
      const c = data.capture;
      if (!c) return;
      activeModalCapture = c;
      currentPipeStepIndex = 1;
      currentPipeViewMode = 'stepper';
      const isHit = c.is_hotlist_hit;
      const isUnreadable = c.plate_number === 'UNREADABLE' || c.display_plate && c.display_plate.includes('UNREADABLE');
      const plateText = escapeHtml(c.display_plate || c.plate_number || 'UNKNOWN');
      const evFrames = c.evidence_frames || [];
      let peakOcr = c.ocr_confidence || c.confidence || 0;
      let peakDet = c.det_confidence || 0;
      if (evFrames && evFrames.length > 0) {
        for (const ef of evFrames) {
          if (ef.confidence && ef.confidence > peakOcr) {
            peakOcr = ef.confidence;
          }
        }
      }
      const ocrConf = peakOcr;
      const detConf = peakDet ? `${peakDet}%` : c.det_confidence ? `${c.det_confidence}%` : 'N/A';
      const blurVal = c.blur_score ? `${c.blur_score}` : 'N/A';
      const blurQuality = c.blur_score ? c.blur_score >= 100 ? 'Sharp (>100.0)' : 'Soft / Low Contrast' : 'N/A';
      const aspectVal = c.aspect_ratio ? `${c.aspect_ratio}` : 'N/A';
      const fmtType = c.format_type ? escapeHtml(c.format_type) : 'Standard Indian MoRTH';
      const dateStr = c.captured_at || 'N/A';
      if (capModalRankBadge) capModalRankBadge.innerText = `Capture #${c.id}`;
      if (capModalPlateText) capModalPlateText.innerText = isUnreadable ? 'UNREADABLE (LOW EVIDENCE)' : plateText;
      if (capModalFormatBadge) {
        if (isUnreadable) {
          capModalFormatBadge.className = 'badge-review';
          capModalFormatBadge.innerText = 'Unreadable / Distant Crop';
          capModalFormatBadge.style.background = 'rgba(100, 116, 139, 0.2)';
          capModalFormatBadge.style.color = '#52647c';
          capModalFormatBadge.style.borderColor = 'rgba(100, 116, 139, 0.35)';
        } else {
          capModalFormatBadge.style.background = '';
          capModalFormatBadge.style.color = '';
          capModalFormatBadge.style.borderColor = '';
          capModalFormatBadge.className = c.quality_gate_passed ? 'badge-verified' : 'badge-review';
          capModalFormatBadge.innerText = c.quality_gate_passed ? 'Format Verified' : 'Format Unverified / Review';
        }
      }
      let violBtn = document.getElementById('capModalViolationDossierBtn');
      const isTrafficViolation = Boolean(c.is_traffic_violation || c.violation_type || c.notes && c.notes.includes('traffic_violation'));
      if (isTrafficViolation) {
        if (!violBtn) {
          violBtn = document.createElement('button');
          violBtn.id = 'capModalViolationDossierBtn';
          violBtn.type = 'button';
          const titleContainer = document.getElementById('capModalPlateTitle');
          if (titleContainer) titleContainer.appendChild(violBtn);
        }
        violBtn.onclick = () => {
          const m = document.getElementById('captureDetailModal');
          if (m) m.style.display = 'none';
          if (typeof window.openSplitViolationModal === 'function') {
            window.openSplitViolationModal(c.id);
          }
        };
        violBtn.style.display = 'inline-flex';
        violBtn.style.alignItems = 'center';
        violBtn.style.gap = '6px';
        violBtn.style.marginLeft = '10px';
        violBtn.style.padding = '4px 12px';
        violBtn.style.fontSize = '0.75rem';
        violBtn.style.fontWeight = '700';
        violBtn.style.background = 'rgba(245, 158, 11, 0.15)';
        violBtn.style.border = '1.5px solid #f59e0b';
        violBtn.style.color = '#92400e';
        violBtn.style.borderRadius = '6px';
        violBtn.style.cursor = 'pointer';
        violBtn.innerHTML = '<span>⚖️</span> Violation Dossier';
      } else if (violBtn) {
        violBtn.style.display = 'none';
      }
      if (capModalSubtitle) {
        capModalSubtitle.innerHTML = `Captured at <strong>${dateStr}</strong> &bull; Location: <strong>${escapeHtml(c.location || 'Surveillance Gate')}</strong>`;
      }
      let hotlistBannerHtml = '';
      if (isHit) {
        hotlistBannerHtml = `



                    <div class="hotlist-alert-banner hotlist-alert-case" style="margin-bottom: 16px;">



                        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" style="flex-shrink: 0; margin-top: 1px;">



                            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>



                            <line x1="12" y1="9" x2="12" y2="13"/>



                            <line x1="12" y1="17" x2="12.01" y2="17"/>



                        </svg>



                        <div style="flex: 1;">



                            <span class="hotlist-alert-title">HOTLIST ALERT MATCH (WANTED / POLICE WATCHLIST)</span>



                            <div style="font-size: 0.875rem; line-height: 1.4; margin-top: 2px;">



                                ${escapeHtml(c.hotlist_info || 'Cross-matched against police records / lost registry')}



                            </div>



                        </div>



                    </div>



                `;
      }
      const sceneImgSrc = c.annotated_pic_path || c.vehicle_pic_path || c.plate_pic_path || '';
      const plateCropSrc = c.plate_pic_path || '';
      const vehicleCropSrc = c.vehicle_pic_path || '';
      const cleanPlate = (c.plate_number || '').replace(/[^A-Za-z0-9]/g, '').toUpperCase();
      const stCode = cleanPlate.substring(0, 2);
      const rtoCode = cleanPlate.substring(2, 4);
      const stateName = typeof INDIAN_STATE_CODES !== 'undefined' && INDIAN_STATE_CODES[stCode] ? INDIAN_STATE_CODES[stCode] : 'MoRTH Jurisdiction';
      const plateSectionHtml = `



                <div class="cap-subcrop-box">



                    <label>Plate Crop Snapshot</label>



                    <div class="cap-subcrop-img-wrap">



                        ${plateCropSrc ? `<img src="${plateCropSrc}" alt="Plate Crop">` : '<span style="font-size: 0.875rem; color: var(--text-muted);">No crop</span>'}



                    </div>



                </div>



            `;
      let evidenceSectionHtml = '';
      if (evFrames && evFrames.length > 0) {
        evidenceSectionHtml = `



                    <div class="cap-evidence-section">



                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">



                            <span style="font-size: 0.9425rem; font-weight: 700; color: var(--text-primary); display: flex; align-items: center; gap: 8px;">



                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#6366f1" stroke-width="2.2">



                                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>



                                    <polyline points="14 2 14 8 20 8"></polyline>



                                    <line x1="16" y1="13" x2="8" y2="13"></line>



                                    <line x1="16" y1="17" x2="8" y2="17"></line>



                                    <polyline points="10 9 9 9 8 9"></polyline>



                                </svg>



                                Supporting Evidence Frames (${evFrames.length})



                            </span>



                            <span style="font-size: 0.875rem; background: rgba(99, 102, 241, 0.15); color: #4338ca; padding: 3px 10px; border-radius: 4px; font-weight: 600; border: 1px solid rgba(99, 102, 241, 0.3);">



                                ${evFrames.length > 1 ? `${evFrames.length}-Frame Temporal Consensus` : 'Single Frame Sighting'}



                            </span>



                        </div>



                        <div class="evidence-scroll-row">



                            ${evFrames.map(ef => `



                                <div class="evidence-card">



                                    <div style="height: 64px; background: #000; border-radius: 4px; overflow: hidden; display: flex; align-items: center; justify-content: center;">



                                        ${ef.crop_base64 ? `<img src="data:image/jpeg;base64,${ef.crop_base64}" alt="Evidence Frame ${ef.frame_idx}" style="max-height: 100%; max-width: 100%; object-fit: contain;">` : '<span style="font-size:0.875rem; color:var(--text-muted);">No crop</span>'}



                                    </div>



                                    <div style="font-family: var(--font-mono); font-size: 0.875rem; font-weight: 700; color: #475569; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">



                                        ${escapeHtml(ef.text || c.plate_number)}



                                    </div>



                                    <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.875rem; color: var(--text-muted);">



                                        <span>Frame #${ef.frame_idx}</span>



                                        <span class="conf-pill" style="font-size: 0.875rem; padding: 1px 6px;">${ef.confidence}%</span>



                                    </div>



                                </div>



                            `).join('')}



                        </div>



                    </div>



                `;
      }
      const evidenceClipHtml = c.evidence_video_path ? `



                <div class="cap-evidence-clip-box" style="margin-bottom: 14px; background: rgba(241,245,249,0.95); border: 1.5px solid #ef4444; border-radius: 8px; padding: 12px; box-shadow: 0 0 15px rgba(239, 68, 68, 0.25);">



                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">



                        <span style="font-size: 0.875rem; font-weight: 800; color: #b91c1c; display: flex; align-items: center; gap: 6px;">



                            <span style="display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #ef4444;"></span>



                            INCIDENT FORENSIC VIDEO CLIP (POLICE EVIDENCE PRESERVED)



                        </span>



                        <span style="font-size: 0.875rem; color: #52647c; font-family: var(--font-mono);">Sec 65B Preserved Clip</span>



                    </div>



                    <video src="${c.evidence_video_path}" controls autoplay loop style="width: 100%; max-height: 260px; border-radius: 6px; background: #000; border: 1px solid rgba(255,255,255,0.1);"></video>



                </div>



            ` : '';
      capModalBody.innerHTML = `



                ${hotlistBannerHtml}



                ${evidenceClipHtml}



                <div class="pipe-view-nav-tabs">



                    <div class="pipe-tab-group">



                        <button type="button" id="btnModePanoramic" class="pipe-tab-btn active" onclick="setPipeModalMode('panoramic')">



                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">



                                <rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect>



                                <line x1="8" y1="21" x2="16" y2="21"></line>



                                <line x1="12" y1="17" x2="12" y2="21"></line>



                            </svg>



                            Zero-Scroll Panoramic Belt (All 5 Stages)



                        </button>



                        <button type="button" id="btnModeMatrix" class="pipe-tab-btn" onclick="setPipeModalMode('matrix')">



                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">



                                <rect x="3" y="3" width="7" height="7"></rect>



                                <rect x="14" y="3" width="7" height="7"></rect>



                                <rect x="14" y="14" width="7" height="7"></rect>



                                <rect x="3" y="14" width="7" height="7"></rect>



                            </svg>



                            Comprehensive Forensic Matrix



                        </button>



                    </div>



                    <div style="font-size: 0.875rem; color: #10b981; font-family: var(--font-mono); font-weight: 700; display: flex; align-items: center; gap: 6px;">



                        <span style="display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: #f8fafc;"></span>



                        100% AUDITABLE PIPELINE



                    </div>



                </div>



                <!-- 1. ZERO-SCROLL PANORAMIC 5-STAGE AUDIT BELT (DEFAULT ACTIVE) -->



                <div id="pipePanoramicViewWrap" class="pipe-panoramic-container" style="display: flex;">







                    <!-- Top Compact Summary Row -->



                    <div class="pipe-panoramic-summary">



                        <div style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap;">



                            <div class="hsrp-plate" style="transform: scale(0.85); transform-origin: left center;">



                                <div class="hsrp-ind-strip"><span>IND</span></div>



                                <div class="hsrp-plate-text">${plateText}</div>



                            </div>



                            <span class="badge ${c.quality_gate_passed ? 'badge-verified' : 'badge-unverified'}" style="font-size: 0.875rem; padding: 2px 8px;">



                                ${c.quality_gate_passed ? 'MoRTH FORMAT VALID' : 'FORMAT REVIEW'}



                            </span>



                            <span class="badge" style="font-size: 0.875rem; padding: 2px 8px; ${isHit ? 'background: rgba(239, 68, 68, 0.2); color: #b91c1c; border: 1px solid rgba(239, 68, 68, 0.4);' : 'background: rgba(16, 185, 129, 0.15); color: #047857; border: 1px solid rgba(16, 185, 129, 0.3);'}">



                                ${isHit ? 'HOTLIST POLICE HIT' : 'HOTLIST CLEAN'}



                            </span>



                            <span style="font-size: 0.875rem; color: var(--text-muted);">



                                ${escapeHtml(c.location || 'Surveillance Gate')} &bull; ${dateStr}



                            </span>



                        </div>



                        <div style="display: flex; align-items: center; gap: 14px; font-family: var(--font-mono); font-size: 0.875rem;">



                            <div><span style="color: var(--text-muted);">Track:</span> <strong style="color: #92400e;">#${c.track_id || c.id}</strong></div>



                            <div><span style="color: var(--text-muted);">Peak OCR:</span> <strong style="color: #0369a1;">${ocrConf}%</strong></div>



                        </div>



                    </div>



                    ${""}



                    <!-- ZERO-SCROLL 5-STAGE HORIZONTAL PIPELINE BELT -->



                    <div class="pipe-panoramic-belt">







                        <!-- STAGE 1: CCTV Scene -->



                        <div class="pipe-stage-col" style="border-top: 2px solid #3b82f6;">



                            <div>



                                <div class="pipe-stage-col-head">



                                    <span class="pipe-stage-col-tag" style="color: #1d4ed8;">



                                        <span class="pipe-stage-col-num" style="background: #2563eb;">1</span>



                                        CCTV SCENE



                                    </span>



                                    <span class="pipe-stage-col-sub">1080p</span>



                                </div>



                                <div class="pipe-stage-col-imgbox">



                                    ${sceneImgSrc ? `<img src="${sceneImgSrc}" alt="Raw Scene">` : '<span style="font-size:0.875rem; color:var(--text-muted);">No scene frame</span>'}



                                </div>



                            </div>



                            <div class="pipe-stage-col-metrics">



                                <div class="pipe-stage-col-row">



                                    <span class="pipe-stage-col-lbl">Source</span>



                                    <span class="pipe-stage-col-val" style="font-size: 0.875rem;">${escapeHtml(c.source_type || 'Feed')}</span>



                                </div>



                                <div class="pipe-stage-col-row">



                                    <span class="pipe-stage-col-lbl">Location</span>



                                    <span class="pipe-stage-col-val" style="font-size: 0.875rem; max-width: 90px; text-overflow: ellipsis; overflow: hidden; white-space: nowrap;">${escapeHtml(c.location || 'Gate 1')}</span>



                                </div>



                            </div>



                            <div class="pipe-connector-arrow">&rarr;</div>



                        </div>



                        <!-- STAGE 2: Vehicle Detector -->



                        <div class="pipe-stage-col" style="border-top: 2px solid #f59e0b;">



                            <div>



                                <div class="pipe-stage-col-head">



                                    <span class="pipe-stage-col-tag" style="color: #92400e;">



                                        <span class="pipe-stage-col-num" style="background: #d97706; color: #000;">2</span>



                                        VEHICLE DET



                                    </span>



                                    <span class="pipe-stage-col-sub" style="color: #92400e;">${detConf}</span>



                                </div>



                                <div class="pipe-stage-col-imgbox">



                                    ${vehicleCropSrc ? `<img src="${vehicleCropSrc}" alt="Vehicle Crop">` : sceneImgSrc ? `<img src="${sceneImgSrc}" alt="Scene Context">` : '<span style="font-size:0.875rem; color:var(--text-muted);">No vehicle crop</span>'}



                                </div>



                            </div>



                            <div class="pipe-stage-col-metrics">



                                <div class="pipe-stage-col-row">



                                    <span class="pipe-stage-col-lbl">Category</span>



                                    <span class="pipe-stage-col-val" style="color: #92400e;">${escapeHtml((c.vehicle_class || 'car').toUpperCase())}</span>



                                </div>



                                <div class="pipe-stage-col-row">



                                    <span class="pipe-stage-col-lbl">Track ID</span>



                                    <span class="pipe-stage-col-val font-mono">#${c.track_id || c.id}</span>



                                </div>



                            </div>



                            <div class="pipe-connector-arrow">&rarr;</div>



                        </div>



                        <!-- STAGE 3: Plate Crop -->



                        <div class="pipe-stage-col" style="border-top: 2px solid #6366f1;">



                            <div>



                                <div class="pipe-stage-col-head">



                                    <span class="pipe-stage-col-tag" style="color: #4338ca;">



                                        <span class="pipe-stage-col-num" style="background: #4f46e5;">3</span>



                                        PLATE CROP



                                    </span>



                                    <span class="pipe-stage-col-sub" style="color: #047857;">&check; Gate</span>



                                </div>



                                <div class="pipe-stage-col-imgbox">



                                    ${plateCropSrc ? `<img src="${plateCropSrc}" alt="Plate Crop" style="border: 1px solid #4f46e5; border-radius: 4px; padding: 1px;">` : '<span style="font-size:0.875rem; color:var(--text-muted);">No plate crop</span>'}



                                </div>



                            </div>



                            <div class="pipe-stage-col-metrics">



                                <div class="pipe-stage-col-row">



                                    <span class="pipe-stage-col-lbl">Blur Variance</span>



                                    <span class="pipe-stage-col-val" style="color: #047857;">${blurVal}</span>



                                </div>



                                <div class="pipe-stage-col-row">



                                    <span class="pipe-stage-col-lbl">Aspect W/H</span>



                                    <span class="pipe-stage-col-val font-mono">${aspectVal}</span>



                                </div>



                            </div>



                            <div class="pipe-connector-arrow">&rarr;</div>



                        </div>



                        <!-- STAGE 4: OCR Recognition & Voting -->



                        <div class="pipe-stage-col" style="border-top: 2px solid #a855f7;">



                            <div>



                                <div class="pipe-stage-col-head">



                                    <span class="pipe-stage-col-tag" style="color: #7e22ce;">



                                        <span class="pipe-stage-col-num" style="background: #9333ea;">4</span>



                                        OCR VOTING



                                    </span>



                                    <span class="pipe-stage-col-sub" style="color: #047857;">${ocrConf}%</span>



                                </div>



                                <div class="pipe-stage-col-imgbox" style="flex-direction: column; gap: 2px; padding: 4px; font-family: var(--font-mono); font-size: 0.875rem;">



                                    ${evFrames && evFrames.length > 0 ? evFrames.slice(0, 3).map(ef => `



                                        <div style="width: 100%; display: flex; justify-content: space-between; background: rgba(241,245,249,0.6); padding: 2px 4px; border-radius: 3px;">



                                            <span style="color: var(--text-muted);">F#${ef.frame_idx}</span>



                                            <span style="font-weight: 700; color: #fff;">${escapeHtml(ef.text || c.plate_number)}</span>



                                            <span style="color: #047857;">${ef.confidence}%</span>



                                        </div>



                                    `).join('') : `



                                        <div class="hsrp-plate" style="transform: scale(0.72); margin: 0;">



                                            <div class="hsrp-ind-strip"><span>IND</span></div>



                                            <div class="hsrp-plate-text">${plateText}</div>



                                        </div>



                                        <span style="color: #4338ca; font-size: 0.875rem;">Direct Awiros Read</span>



                                    `}



                                </div>



                            </div>



                            <div class="pipe-stage-col-metrics">



                                <div class="pipe-stage-col-row">



                                    <span class="pipe-stage-col-lbl">Consensus</span>



                                    <span class="pipe-stage-col-val" style="color: #7e22ce;">${evFrames.length > 0 ? `${evFrames.length} Frames` : '1 Frame'}</span>



                                </div>



                                <div class="pipe-stage-col-row">



                                    <span class="pipe-stage-col-lbl">Confidence</span>



                                    <span class="pipe-stage-col-val" style="color: #047857;">${ocrConf}%</span>



                                </div>



                            </div>



                            <div class="pipe-connector-arrow">&rarr;</div>



                        </div>



                        <!-- STAGE 5: MoRTH & Police Gate -->



                        <div class="pipe-stage-col" style="border-top: 2px solid ${isHit ? '#ef4444' : '#10b981'};">



                            <div>



                                <div class="pipe-stage-col-head">



                                    <span class="pipe-stage-col-tag" style="color: ${isHit ? '#b91c1c' : '#047857'};">



                                        <span class="pipe-stage-col-num" style="background: ${isHit ? '#dc2626' : '#059669'};">5</span>



                                        POLICE GATE



                                    </span>



                                    <span class="pipe-stage-col-sub" style="color: ${isHit ? '#b91c1c' : '#047857'};">${isHit ? 'ALERT' : 'CLEAN'}</span>



                                </div>



                                <div class="pipe-stage-col-imgbox" style="flex-direction: column; gap: 4px; padding: 6px;">



                                    <div style="width: 100%; display: flex; align-items: center; gap: 4px; background: rgba(16, 185, 129, 0.12); border: 1px solid rgba(16, 185, 129, 0.25); border-radius: 4px; padding: 3px 6px; font-size: 0.875rem; color: #166534;">



                                        <span style="color: #10b981; font-weight: bold;">&check;</span>



                                        <span>MoRTH Format Valid</span>



                                    </div>



                                    <div style="width: 100%; display: flex; align-items: center; gap: 4px; background: ${isHit ? 'rgba(239, 68, 68, 0.15)' : 'rgba(59, 130, 246, 0.12)'}; border: 1px solid ${isHit ? 'rgba(239, 68, 68, 0.3)' : 'rgba(59, 130, 246, 0.25)'}; border-radius: 4px; padding: 3px 6px; font-size: 0.875rem; color: ${isHit ? '#fca5a5' : '#bfdbfe'};">



                                        <span style="font-weight: bold; color: ${isHit ? '#ef4444' : '#1d4ed8'};">${isHit ? '&times;' : '&check;'}</span>



                                        <span>${isHit ? 'WANTED ALERT MATCH' : 'FIR Watch: Clean'}</span>



                                    </div>



                                </div>



                            </div>



                            <div class="pipe-stage-col-metrics">



                                <div class="pipe-stage-col-row">



                                    <span class="pipe-stage-col-lbl">Jurisdiction</span>



                                    <span class="pipe-stage-col-val" style="font-size: 0.875rem; max-width: 90px; text-overflow: ellipsis; overflow: hidden; white-space: nowrap;">${stCode || 'IND'} (${stateName})</span>



                                </div>



                                <div class="pipe-stage-col-row">



                                    <span class="pipe-stage-col-lbl">Status</span>



                                    <span class="pipe-stage-col-val" style="color: ${isHit ? '#b91c1c' : '#047857'};">${isHit ? 'ALERT HIT' : 'VERIFIED'}</span>



                                </div>



                            </div>



                        </div>



                    </div>



                    <!-- Action Footer -->



                    <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 8px; padding-top: 6px; border-top: 1px solid rgba(255, 255, 255, 0.08);">



                        <div style="display: flex; align-items: center; gap: 6px; font-size: 0.875rem; color: var(--text-muted);">



                            <span style="display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: #f8fafc;"></span>



                            <span>Zero-Scroll Panoramic Audit &bull; All 5 stages visible simultaneously on one screen</span>



                        </div>



                        <div style="display: flex; gap: 8px;">



                            <button class="btn-danger" style="padding: 5px 12px; font-size: 0.875rem;" onclick="deleteCaptureModal(${c.id}, '${escapeHtml(c.plate_number)}')">



                                Delete Capture Record



                            </button>



                            <button class="btn btn-secondary" style="padding: 5px 12px; font-size: 0.875rem;" onclick="captureDetailModal.style.display = 'none';">



                                Close Inspection



                            </button>



                        </div>



                    </div>



                </div>



                <!-- 2. COMPREHENSIVE MATRIX VIEW (OPTIONAL EXPANDED VIEW) -->



                <div id="pipeMatrixViewWrap" style="display: none;">



                    <div class="cap-modal-layout">



                        <!-- Left Column: Visual Evidence -->



                        <div class="cap-modal-scene-col">



                            <div class="cap-modal-scene-card">



                                <div class="cap-modal-scene-head">



                                    <span>Annotated Detection Scene</span>



                                    <span style="font-family: var(--font-mono); color: #10b981;">Detection Consensus</span>



                                </div>



                                ${sceneImgSrc ? `



                                    <img class="cap-modal-scene-img" src="${sceneImgSrc}" alt="Annotated Capture Scene">



                                ` : `



                                    <div style="padding: 40px; text-align: center; color: var(--text-muted); font-size: 0.9125rem;">



                                        No full-frame image available



                                    </div>



                                `}



                            </div>



                            <div class="cap-modal-crops-grid">



                                <div class="cap-subcrop-box">



                                    <label>Vehicle Context Snapshot</label>



                                    <div class="cap-subcrop-img-wrap">



                                        ${vehicleCropSrc ? `<img src="${vehicleCropSrc}" alt="Vehicle Crop">` : '<span style="font-size: 0.875rem; color: var(--text-muted);">No vehicle context</span>'}



                                    </div>



                                </div>



                                ${plateSectionHtml}



                            </div>



                        </div>



                        <!-- Right Column: Technical Quality Metrics & Surveillance Data -->



                        <div class="cap-diag-col">



                            <div class="cap-diag-card">



                                <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border-color); padding-bottom: 10px;">



                                    <span style="font-size: 0.875rem; font-weight: 700; text-transform: uppercase; color: var(--text-muted);">Technical Quality Metrics</span>



                                    <div class="hsrp-plate" style="transform: scale(0.85); transform-origin: right center;">



                                        <div class="hsrp-ind-strip"><span>IND</span></div>



                                        <div class="hsrp-plate-text">${plateText}</div>



                                    </div>



                                </div>



                                <div class="cap-diag-table">



                                    <div class="cap-diag-row">



                                        <span class="cap-diag-label">OCR Confidence (Best Frame)</span>



                                        <span class="cap-diag-val" style="color: #10b981; font-weight: 700;">${ocrConf}%</span>



                                    </div>



                                    <div class="cap-diag-row">



                                        <span class="cap-diag-label">Detection Confidence (Peak)</span>



                                        <span class="cap-diag-val" style="color: #3b82f6; font-weight: 700;">${detConf}</span>



                                    </div>



                                    <div class="cap-diag-row">



                                        <span class="cap-diag-label">Aspect Ratio (W/H)</span>



                                        <span class="cap-diag-val">${aspectVal}</span>



                                    </div>



                                    <div class="cap-diag-row">



                                        <span class="cap-diag-label">Plate Format Type</span>



                                        <span class="cap-diag-val" style="font-size: 0.875rem;">${fmtType}</span>



                                    </div>



                                    <div class="cap-diag-row">



                                        <span class="cap-diag-label">Quality Filter Gate</span>



                                        <span class="cap-diag-val" style="color: ${c.quality_gate_passed ? '#10b981' : '#ef4444'};">



                                            ${c.quality_gate_passed ? 'PASSED' : 'REJECTED'}



                                        </span>



                                    </div>



                                    <div class="cap-diag-row">



                                        <span class="cap-diag-label">Gate Reason</span>



                                        <span class="cap-diag-val" style="font-size: 0.875rem;">${escapeHtml(c.quality_reason || 'Valid plate crop')}</span>



                                    </div>



                                    <div class="cap-diag-row">



                                        <span class="cap-diag-label">Ingestion Source</span>



                                        <span class="cap-diag-val" style="font-size: 0.875rem;">${escapeHtml(c.source_type || 'Feed')}</span>



                                    </div>



                                    <div class="cap-diag-row">



                                        <span class="cap-diag-label">Capture Point / Location</span>



                                        <span class="cap-diag-val" style="font-size: 0.875rem;">${escapeHtml(c.location || 'Main Gate')}</span>



                                    </div>



                                    <div class="cap-diag-row">



                                        <span class="cap-diag-label">Timestamp</span>



                                        <span class="cap-diag-val" style="font-size: 0.875rem;">${dateStr}</span>



                                    </div>



                                </div>



                                <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 8px;">



                                    <button class="btn-danger" style="padding: 6px 14px; font-size: 0.875rem;" onclick="deleteCaptureModal(${c.id}, '${escapeHtml(c.plate_number)}')">



                                        Delete Capture



                                    </button>



                                    <button class="btn btn-secondary" style="padding: 6px 14px; font-size: 0.875rem;" onclick="captureDetailModal.style.display = 'none';">



                                        Close Inspection



                                    </button>



                                </div>



                            </div>



                        </div>



                    </div>



                    ${evidenceSectionHtml}



                </div>



            `;
      window.setPipeModalMode('panoramic');
      captureDetailModal.style.display = 'flex';
    } catch (err) {
      console.error("Error loading capture detail:", err);
      alert("Error loading capture details: " + err.message);
    }
  };
  window.deleteCaptureModal = async (id, plate) => {
    if (!confirm(`Delete capture record for "${plate}"?`)) return;
    try {
      const res = await fetch(`/api/captured/${id}`, {
        method: 'DELETE'
      });
      if (res.ok) {
        if (captureDetailModal) captureDetailModal.style.display = 'none';
        if (typeof fetchAndRenderDrawerVehicles === 'function') {
          await fetchAndRenderDrawerVehicles();
        }
        if (typeof fetchAndRenderUnifiedLiveFeed === 'function') {
          await fetchAndRenderUnifiedLiveFeed();
        }
        if (typeof fetchAndRenderCapturedDb === 'function') {
          await fetchAndRenderCapturedDb();
        }
      } else {
        alert("Failed to delete capture.");
      }
    } catch (err) {
      console.error(err);
      alert("Error: " + err.message);
    }
  };
  window.deleteCaptureRecord = async function (id, plate) {
    if (!confirm(`Delete capture record #${id} ("${plate}")?`)) return;
    try {
      const res = await fetch(`/api/captured/${id}`, {
        method: 'DELETE'
      });
      if (res.ok) {
        if (typeof fetchAndRenderDrawerVehicles === 'function') {
          await fetchAndRenderDrawerVehicles();
        }
        if (typeof fetchAndRenderUnifiedLiveFeed === 'function') {
          await fetchAndRenderUnifiedLiveFeed();
        }
        if (typeof fetchAndRenderCapturedDb === 'function') {
          await fetchAndRenderCapturedDb();
        }
      } else {
        alert("Failed to delete capture record.");
      }
    } catch (err) {
      console.error(err);
      alert("Error deleting record: " + err.message);
    }
  };
  if (closeCaptureDetailModalBtn) {
    closeCaptureDetailModalBtn.addEventListener('click', () => {
      captureDetailModal.style.display = 'none';
    });
  }
  if (capturedSearchInput) {
    capturedSearchInput.addEventListener('input', () => {
      if (capturedSearchDebounce) clearTimeout(capturedSearchDebounce);
      capturedSearchDebounce = setTimeout(() => {
        fetchAndRenderCapturedDb();
      }, 300);
    });
  }
  capFilterBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      capFilterBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentCapturedFilter = btn.dataset.capfilter || 'all';
      fetchAndRenderCapturedDb();
    });
  });
  if (btnRefreshCaptured) {
    btnRefreshCaptured.addEventListener('click', () => {
      fetchAndRenderCapturedDb();
    });
  }
  if (btnClearCaptured) {
    btnClearCaptured.addEventListener('click', async () => {
      if (!confirm("Are you sure you want to clear all capture history from Captured DB?")) {
        return;
      }
      try {
        const res = await fetch('/api/captured', {
          method: 'DELETE'
        });
        if (res.ok) {
          if (typeof fetchAndRenderDrawerVehicles === 'function') {
            await fetchAndRenderDrawerVehicles();
          }
          if (typeof fetchAndRenderUnifiedLiveFeed === 'function') {
            await fetchAndRenderUnifiedLiveFeed();
          }
          if (typeof fetchAndRenderCapturedDb === 'function') {
            await fetchAndRenderCapturedDb();
          }
        } else {
          alert("Failed to clear captures.");
        }
      } catch (err) {
        console.error(err);
        alert("Error clearing captures: " + err.message);
      }
    });
  }
  window.deleteCapture = async (id, plate) => {
    if (!confirm(`Delete capture record for "${plate}"?`)) return;
    try {
      const res = await fetch(`/api/captured/${id}`, {
        method: 'DELETE'
      });
      if (res.ok) {
        if (typeof fetchAndRenderDrawerVehicles === 'function') {
          await fetchAndRenderDrawerVehicles();
        }
        if (typeof fetchAndRenderUnifiedLiveFeed === 'function') {
          await fetchAndRenderUnifiedLiveFeed();
        }
        if (typeof fetchAndRenderCapturedDb === 'function') {
          await fetchAndRenderCapturedDb();
        }
      } else {
        alert("Failed to delete capture.");
      }
    } catch (err) {
      console.error(err);
      alert("Error: " + err.message);
    }
  };
  async function fetchAndRenderVehicleDb() {
    try {
      const query = dbSearchInput ? dbSearchInput.value.trim() : '';
      let url = `/api/vehicles?filter=${encodeURIComponent(currentDbFilter)}`;
      let dist = 'All';
      if (currentUser && (currentUser.role === 'STATE_ADMIN' || currentUser.role === 'DEVELOPER_ADMIN')) {
        dist = document.getElementById('vehicleDbDistrictFilter')?.value || 'All';
      } else if (currentUser && currentUser.district && !currentUser.district.includes('All')) {
        dist = currentUser.district;
      }
      if (dist && !dist.includes('All')) {
        url += `&district=${encodeURIComponent(dist)}`;
      }
      if (query) {
        url += `&search=${encodeURIComponent(query)}`;
      }
      const res = await fetch(url);
      const data = await res.json();
      const vehicles = data.vehicles || [];
      totalRegisteredVehiclesCount = data.total !== undefined ? data.total : vehicles.length;
      if (navDbCountBadge) {
        navDbCountBadge.innerText = `${totalRegisteredVehiclesCount}`;
      }
      if (masterRegVehiclesCountBadge) {
        masterRegVehiclesCountBadge.innerText = totalRegisteredVehiclesCount;
      }
      updateMasterRegTotal();
      if (vehicles.length === 0) {
        dbVehicleContainer.innerHTML = `



                    <div class="empty-state" style="grid-column: 1 / -1; padding: 40px 20px;">



                        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">



                            <rect x="3" y="4" width="18" height="16" rx="2"/>



                            <line x1="16" y1="2" x2="16" y2="6"/>



                            <line x1="8" y1="2" x2="8" y2="6"/>



                            <line x1="3" y1="10" x2="21" y2="10"/>



                        </svg>



                        <p style="margin-top: 12px; font-size: 1.0625rem; color: var(--text-primary);">No vehicles found in Vehicle DB for selected district.</p>



                        <p style="font-size: 0.9125rem; color: var(--text-secondary);">Click "Register New Vehicle" above to register police cases or lost vehicles.</p>



                    </div>



                `;
        return;
      }
      dbVehicleContainer.innerHTML = vehicles.map(v => {
        const isCase = v.involved_in_case;
        const statusBadge = isCase ? `<span class="badge-case-active" style="font-size: 0.875rem; padding: 2px 7px;">${escapeHtml(v.offence_type || 'POLICE RECORD')}</span>` : `<span class="badge-lost-active" style="font-size: 0.875rem; padding: 2px 7px;">LOST</span>`;
        const dateStr = v.registered_at ? v.registered_at.split(' ')[0] : 'N/A';
        const firOrLoc = isCase ? v.fir_number || (v.police_station ? 'PS ' + v.police_station : 'FIR: N/A') : v.lost_location || 'Lost Record';
        return `



                    <div class="db-card" onclick="showVehicleDetails(${v.id})" title="Click to view full case details & history">



                        <!-- Top Row: HSRP Plate + Status Badge -->



                        <div style="display: flex; justify-content: space-between; align-items: center; gap: 6px;">



                            <div class="hsrp-plate" style="height: 24px;">



                                <div class="hsrp-ind-strip" style="font-size: 0.875rem; padding: 0 4px;">



                                    <span>IND</span>



                                </div>



                                <div class="hsrp-plate-text" style="font-size: 0.875rem; padding: 0 6px;">



                                    ${escapeHtml(v.display_plate || v.vehicle_number)}



                                </div>



                            </div>



                            ${statusBadge}



                        </div>



                        <!-- Mid Row: Vehicle Type • Colour + District -->



                        <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.875rem; color: #475569; margin-top: 2px;">



                            <span><strong>${escapeHtml(v.vehicle_type || 'Car')}</strong> &bull; ${escapeHtml(v.vehicle_color || 'N/A')}</span>



                            <span class="badge-district-tag" style="font-size: 0.875rem; padding: 1px 6px; border-radius: 4px; background: rgba(59, 130, 246, 0.15); color: #1d4ed8; border: 1px solid rgba(59, 130, 246, 0.3); font-weight: 600;">${escapeHtml(v.district_name || 'Panipat')}</span>



                        </div>



                        ${v.owner_name ? `



                        <!-- Owner Info Snippet -->



                        <div style="display: flex; align-items: center; gap: 6px; font-size: 0.875rem; color: #52647c; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; background: rgba(59, 130, 246, 0.08); padding: 3px 8px; border-radius: 4px; border: 1px solid rgba(59, 130, 246, 0.2);">



                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#1d4ed8" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>



                            <span style="color: #334155; font-weight: 600;">${escapeHtml(v.owner_name)}</span>



                            ${v.owner_mobile ? `<span style="color: #64748b;">&bull;</span><span style="color: #0369a1; font-family: var(--font-mono);">${escapeHtml(v.owner_mobile)}</span>` : ''}



                        </div>



                        ` : ''}



                        <!-- Case / FIR Snippet Box -->



                        <div class="db-card-case-meta" style="display: flex; justify-content: space-between; align-items: center; font-size: 0.875rem; color: var(--text-muted); background: #f1f5f9; padding: 5px 8px; border-radius: 4px; border: 1px solid var(--border-color);">



                            <span style="font-family: var(--font-mono); color: #1d4ed8; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 165px;" title="${escapeHtml(firOrLoc)}">



                                ${escapeHtml(firOrLoc)}



                            </span>



                            <span style="font-size: 0.875rem;">${dateStr}</span>



                        </div>



                        <!-- Compact Actions Footer -->



                        <div class="db-card-actions" style="margin-top: 2px; padding-top: 6px; border-top: 1px solid var(--border-color); display: flex; justify-content: space-between; align-items: center;" onclick="event.stopPropagation()">



                            <button class="btn btn-secondary" style="padding: 3px 9px; font-size: 0.875rem; border-radius: 4px;" onclick="showVehicleDetails(${v.id})">



                                Details



                            </button>



                            ${currentUser && currentUser.role === 'OPERATOR' ? '' : `



                            <button class="btn-danger" style="padding: 3px 8px; font-size: 0.875rem; border-radius: 4px;" onclick="deleteVehicle(${v.id}, '${escapeHtml(v.vehicle_number)}')">



                                Delete



                            </button>



                            `}



                        </div>



                    </div>



                `;
      }).join('');
    } catch (err) {
      console.error("Error fetching Vehicle DB:", err);
      dbVehicleContainer.innerHTML = `



                <div class="empty-state" style="grid-column: 1 / -1; color: #ef4444;">



                    <p>Failed to load Vehicle DB records. Please check backend connection.</p>



                </div>



            `;
    }
  }
  if (dbSearchInput) {
    dbSearchInput.addEventListener('input', () => {
      if (dbSearchDebounce) clearTimeout(dbSearchDebounce);
      dbSearchDebounce = setTimeout(() => {
        fetchAndRenderVehicleDb();
      }, 300);
    });
  }
  filterBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      filterBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentDbFilter = btn.dataset.filter || 'all';
      fetchAndRenderVehicleDb();
    });
  });
  function handleCaseRadioChange() {
    const isCase = radioCaseYes && radioCaseYes.checked;
    if (isCase) {
      subFormCase.style.display = 'flex';
      subFormLost.style.display = 'none';
    } else {
      subFormCase.style.display = 'none';
      subFormLost.style.display = 'flex';
    }
  }
  if (radioCaseYes) {
    radioCaseYes.addEventListener('change', handleCaseRadioChange);
  }
  if (radioCaseNo) {
    radioCaseNo.addEventListener('change', handleCaseRadioChange);
  }
  if (btnOpenRegisterModal) {
    btnOpenRegisterModal.addEventListener('click', () => {
      registerVehicleForm.reset();
      if (radioCaseYes) radioCaseYes.checked = true;
      handleCaseRadioChange();
      registerVehicleModal.style.display = 'flex';
    });
  }
  function closeRegisterModal() {
    registerVehicleModal.style.display = 'none';
    registerVehicleForm.reset();
  }
  if (closeRegisterModalBtn) {
    closeRegisterModalBtn.addEventListener('click', closeRegisterModal);
  }
  if (cancelRegisterModalBtn) {
    cancelRegisterModalBtn.addEventListener('click', closeRegisterModal);
  }
  if (registerVehicleForm) {
    registerVehicleForm.addEventListener('submit', async e => {
      e.preventDefault();
      const plate = document.getElementById('regPlate').value.trim();
      const type = document.getElementById('regType').value;
      const color = document.getElementById('regColor').value.trim();
      const location = document.getElementById('regLocation').value.trim();
      const isCase = radioCaseYes && radioCaseYes.checked;
      const finalPlate = plate || 'UNKNOWN';
      const finalType = type || 'Other';
      const finalColor = color || 'Unknown';
      const formData = new FormData();
      formData.append('vehicle_number', typeof finalPlate !== 'undefined' ? finalPlate : plate || 'UNKNOWN');
      formData.append('vehicle_type', typeof finalType !== 'undefined' ? finalType : type || 'Other');
      formData.append('vehicle_color', typeof finalColor !== 'undefined' ? finalColor : color || 'Unknown');
      formData.append('involved_in_case', isCase ? 'yes' : 'no');
      if (location) formData.append('manual_location', location);
      if (isCase) {
        const offence = document.getElementById('regOffenceType').value;
        const fir = document.getElementById('regFirNumber').value.trim();
        const ps = document.getElementById('regPoliceStation').value.trim();
        const io = document.getElementById('regIoNumber').value.trim();
        const summary = document.getElementById('regCaseSummary').value.trim();
        formData.append('offence_type', offence);
        if (fir) formData.append('fir_number', fir);
        if (ps) formData.append('police_station', ps);
        if (io) formData.append('io_number', io);
        if (summary) formData.append('case_summary', summary);
      } else {
        const lostLoc = document.getElementById('regLostLocation').value.trim();
        const lostDet = document.getElementById('regLostDetails').value.trim();
        if (lostLoc) formData.append('lost_location', lostLoc);
        if (lostDet) formData.append('lost_details', lostDet);
      }
      const ownerName = (document.getElementById('regOwnerName')?.value || '').trim();
      const ownerFatherName = (document.getElementById('regOwnerFatherName')?.value || '').trim();
      const ownerMobile = (document.getElementById('regOwnerMobile')?.value || '').trim();
      const ownerAddress = (document.getElementById('regOwnerAddress')?.value || '').trim();
      if (ownerName) formData.append('owner_name', ownerName);
      if (ownerFatherName) formData.append('owner_father_name', ownerFatherName);
      if (ownerMobile) formData.append('owner_mobile', ownerMobile);
      if (ownerAddress) formData.append('owner_address', ownerAddress);
      const photoInput = document.getElementById('regPhoto');
      if (photoInput && photoInput.files.length > 0) {
        formData.append('photo', photoInput.files[0]);
      }
      const saveBtn = document.getElementById('saveVehicleBtn');
      try {
        saveBtn.disabled = true;
        saveBtn.innerText = "Saving to Database...";
        const res = await fetch('/api/vehicles', {
          method: 'POST',
          body: formData
        });
        if (res.ok) {
          closeRegisterModal();
          await fetchAndRenderVehicleDb();
          alert(`Vehicle ${plate.toUpperCase()} registered successfully into Vehicle DB!`);
        } else {
          const err = await res.json();
          alert("Failed to register vehicle: " + (err.detail || "Server error"));
        }
      } catch (err) {
        console.error("Registration error:", err);
        alert("Error registering vehicle: " + err.message);
      } finally {
        saveBtn.disabled = false;
        saveBtn.innerText = "Save to Vehicle DB";
      }
    });
  }
  window.showVehicleDetails = async id => {
    try {
      const res = await fetch(`/api/vehicles/${id}`);
      if (!res.ok) {
        alert("Could not load vehicle details.");
        return;
      }
      const data = await res.json();
      const v = data.vehicle;
      detailPlateTitle.innerText = v.display_plate || v.vehicle_number;
      const isCase = v.involved_in_case;
      const regDate = v.registered_at ? new Date(v.registered_at).toLocaleString() : 'N/A';
      detailModalBody.innerHTML = `



                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">



                    ${isCase ? `<span class="badge-case-active" style="font-size: 0.9125rem; padding: 4px 12px;">CRIMINAL / POLICE CASE: ${escapeHtml(v.offence_type || 'WANTED')}</span>` : `<span class="badge-lost-active" style="font-size: 0.9125rem; padding: 4px 12px;">REPORTED LOST / MISSING</span>`}



                    <span style="font-size: 0.875rem; color: var(--text-muted);">ID: #${v.id}</span>



                </div>



                <div class="db-meta-grid" style="grid-template-columns: repeat(2, 1fr); margin-bottom: 12px;">



                    <div class="db-meta-item">



                        <label>Vehicle Type</label>



                        <span>${escapeHtml(v.vehicle_type)}</span>



                    </div>



                    <div class="db-meta-item">



                        <label>Colour</label>



                        <span>${escapeHtml(v.vehicle_color)}</span>



                    </div>



                    <div class="db-meta-item">



                        <label>Auto-Timestamp</label>



                        <span style="font-size: 0.875rem;">${regDate}</span>



                    </div>



                    <div class="db-meta-item">



                        <label>Manual Location</label>



                        <span>${escapeHtml(v.manual_location || 'None')}</span>



                    </div>



                </div>



                ${v.owner_name || v.owner_father_name || v.owner_mobile || v.owner_address ? `



                    <div class="conditional-box" style="margin-bottom: 12px; border-left: 3px solid #3b82f6; background: rgba(59, 130, 246, 0.05); padding: 10px 14px; border-radius: var(--radius-sm); border-top: 1px solid rgba(59, 130, 246, 0.2); border-right: 1px solid rgba(59, 130, 246, 0.2); border-bottom: 1px solid rgba(59, 130, 246, 0.2);">



                        <div class="conditional-header" style="color: #1d4ed8; display: flex; align-items: center; gap: 6px; font-weight: 700; font-size: 0.9125rem; margin-bottom: 8px;">



                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>



                            Registered Owner &amp; Contact Details



                        </div>



                        <div class="db-meta-grid" style="background: transparent; border: none; padding: 0; grid-template-columns: repeat(2, 1fr); gap: 8px;">



                            <div class="db-meta-item">



                                <label>Owner Name (वाहन मालिक)</label>



                                <span style="font-weight: 700; color: #ffffff;">${escapeHtml(v.owner_name || 'N/A')}</span>



                            </div>



                            <div class="db-meta-item">



                                <label>Father's Name (पिता/अभिभावक)</label>



                                <span style="color: #334155;">${escapeHtml(v.owner_father_name || 'N/A')}</span>



                            </div>



                            <div class="db-meta-item">



                                <label>Mobile Number (संपर्क नंबर)</label>



                                <span style="color: #0369a1; font-weight: 700; font-family: var(--font-mono);">${escapeHtml(v.owner_mobile || 'N/A')}</span>



                            </div>



                            <div class="db-meta-item">



                                <label>Registered Address (पता)</label>



                                <span style="color: #475569; font-size: 0.875rem; line-height: 1.3;">${escapeHtml(v.owner_address || 'N/A')}</span>



                            </div>



                        </div>



                    </div>



                ` : ''}



                ${isCase ? `



                    <div class="conditional-box box-case" style="margin-bottom: 12px;">



                        <div class="conditional-header">



                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>



                            Police / FIR Case Record



                        </div>



                        <div class="db-meta-grid" style="background: transparent; border: none; padding: 0;">



                            <div class="db-meta-item">



                                <label>FIR Number</label>



                                <span style="font-weight: 700; color: #b91c1c;">${escapeHtml(v.fir_number || 'N/A')}</span>



                            </div>



                            <div class="db-meta-item">



                                <label>Police Station</label>



                                <span>${escapeHtml(v.police_station || 'N/A')}</span>



                            </div>



                            <div class="db-meta-item">



                                <label>IO Contact / ID</label>



                                <span>${escapeHtml(v.io_number || 'N/A')}</span>



                            </div>



                            <div class="db-meta-item">



                                <label>Offence Category</label>



                                <span>${escapeHtml(v.offence_type || 'N/A')}</span>



                            </div>



                        </div>



                        ${v.case_summary ? `



                            <div style="margin-top: 8px;">



                                <label style="font-size: 0.875rem; color: var(--text-muted); text-transform: uppercase;">Case Summary</label>



                                <p style="font-size: 0.9125rem; color: var(--text-primary); margin-top: 2px; line-height: 1.4;">${escapeHtml(v.case_summary)}</p>



                            </div>



                        ` : ''}



                    </div>



                ` : `



                    <div class="conditional-box box-lost" style="margin-bottom: 12px;">



                        <div class="conditional-header">



                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>



                            Lost / Stolen Details



                        </div>



                        <div style="font-size: 0.9125rem;">



                            <label style="font-size: 0.875rem; color: var(--text-muted); text-transform: uppercase;">Lost from Location</label>



                            <div style="color: #92400e; font-weight: 600; margin-top: 2px;">${escapeHtml(v.lost_location || 'Not specified')}</div>



                        </div>



                        ${v.lost_details ? `



                            <div style="margin-top: 8px;">



                                <label style="font-size: 0.875rem; color: var(--text-muted); text-transform: uppercase;">Circumstances / Owner Notes</label>



                                <p style="font-size: 0.9125rem; color: var(--text-primary); margin-top: 2px; line-height: 1.4;">${escapeHtml(v.lost_details)}</p>



                            </div>



                        ` : ''}



                    </div>



                `}



                ${v.photo_url ? `



                    <div style="margin-top: 8px;">



                        <label style="font-size: 0.875rem; color: var(--text-muted); text-transform: uppercase; margin-bottom: 4px; display: block;">Registered Photo</label>



                        <div style="border-radius: var(--radius-sm); overflow: hidden; border: 1px solid var(--border-color); max-height: 260px; background: #000; display: flex; justify-content: center;">



                            <img src="${v.photo_url}" alt="Vehicle Photo" style="max-height: 260px; max-width: 100%; object-fit: contain;">



                        </div>



                    </div>



                ` : ''}



            `;
      vehicleDetailModal.style.display = 'flex';
    } catch (err) {
      console.error("Error opening vehicle detail:", err);
      alert("Error: " + err.message);
    }
  };
  if (closeDetailModalBtn) {
    closeDetailModalBtn.addEventListener('click', () => {
      vehicleDetailModal.style.display = 'none';
    });
  }
  window.deleteVehicle = (id, plate) => {
    if (currentUser && currentUser.role === 'OPERATOR') {
      alert("Operators do not have permission to delete database entries.");
      return;
    }
    window.openDeleteModal('VEHICLE', id, plate);
  };
  const trailCardsContainer = document.getElementById('trailCardsContainer');
  const trailVehiclesCountBadge = document.getElementById('trailVehiclesCountBadge');
  const trailSightingsCountBadge = document.getElementById('trailSightingsCountBadge');
  const trailSearchInput = document.getElementById('trailSearchInput');
  const btnRefreshTrail = document.getElementById('btnRefreshTrail');
  const trailHistoryModal = document.getElementById('trailHistoryModal');
  const closeTrailHistoryModalBtn = document.getElementById('closeTrailHistoryModalBtn');
  const trailModalPlateText = document.getElementById('trailModalPlateText');
  const trailModalHistoryBody = document.getElementById('trailModalHistoryBody');
  const trailFilterStartDate = document.getElementById('trailFilterStartDate');
  const trailFilterEndDate = document.getElementById('trailFilterEndDate');
  const trailFilterCamera = document.getElementById('trailFilterCamera');
  const trailFilterLocation = document.getElementById('trailFilterLocation');
  const btnApplyTrailFilters = document.getElementById('btnApplyTrailFilters');
  const btnResetTrailFilters = document.getElementById('btnResetTrailFilters');
  const btnOpenTrailNarrativeModal = document.getElementById('btnOpenTrailNarrativeModal');
  const trailNarrativeModal = document.getElementById('trailNarrativeModal');
  const closeTrailNarrativeModalBtn = document.getElementById('closeTrailNarrativeModalBtn');
  const trailNarrativeModalPlateText = document.getElementById('trailNarrativeModalPlateText');
  const trailNarrativeModalBody = document.getElementById('trailNarrativeModalBody');
  let activeTrailVehicleId = null;
  let activeTrailDisplayNumber = '';
  let trailSearchDebounce = null;
  async function fetchAndRenderVehicleTrail() {
    try {
      const query = trailSearchInput ? trailSearchInput.value.trim() : '';
      const distSelect = document.getElementById('filterTrailDistrict');
      const opSelect = document.getElementById('filterTrailOperator');
      const selectedDist = distSelect ? distSelect.value : 'ALL';
      const selectedOp = opSelect ? opSelect.value : 'ALL';
      const params = new URLSearchParams();
      if (query) params.append('search', query);
      if (selectedDist && selectedDist !== 'ALL') params.append('district', selectedDist);
      if (selectedOp && selectedOp !== 'ALL') params.append('operator', selectedOp);
      const qs = params.toString();
      const url = qs ? `/api/trails?${qs}` : '/api/trails';
      const res = await fetch(url);
      const data = await res.json();
      totalVehicleSightingsCount = data.total_sightings || 0;
      if (trailVehiclesCountBadge && !window.vehicleTrailReviewMode) trailVehiclesCountBadge.innerText = `${data.total_vehicles_tracked || 0} Vehicles`;
      if (masterVehiclesCountBadge) masterVehiclesCountBadge.innerText = `${data.total_vehicles_tracked || 0}`;
      if (trailSightingsCountBadge) trailSightingsCountBadge.innerText = `${data.total_sightings || 0} Total Sightings`;
      updateMasterTotalSightings();
      const trails = data.trails || [];
      if (trails.length === 0) {
        trailCardsContainer.innerHTML = `



                    <div class="empty-state">



                        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="6" cy="19" r="3"/><path d="M9 19h8.5a3.5 3.5 0 0 0 0-7h-11a3.5 3.5 0 0 1 0-7H15"/><circle cx="18" cy="5" r="3"/></svg>



                        <p>No vehicle trail sightings recorded yet.<br>When a watchlisted vehicle matches Vehicle DB, passages will automatically record here.</p>



                    </div>



                `;
        return;
      }
      trailCardsContainer.innerHTML = trails.map(t => {
        const isCase = t.involved_in_case;
        const statusBadge = isCase ? `<span class="badge-review" style="background: rgba(239, 68, 68, 0.15); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.3);">POLICE CASE</span>` : `<span class="badge-verified" style="background: rgba(245, 158, 11, 0.15); color: #92400e; border: 1px solid rgba(245, 158, 11, 0.3);">LOST / STOLEN</span>`;
        const photoPreview = t.latest_plate_photo || t.db_photo_path;
        return `



                    <div class="vehicle-card" style="border: 1px solid var(--border-color); background: var(--bg-card); display: flex; flex-direction: column; justify-content: space-between;">



                        <div>



                            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px;">



                                <div class="hsrp-plate">



                                    <div class="hsrp-ind-strip"><span>IND</span></div>



                                    <div class="hsrp-plate-text">${escapeHtml(t.display_number)}</div>



                                </div>



                                <span class="conf-pill" style="background: rgba(99, 102, 241, 0.2); color: #818cf8; border-color: rgba(99, 102, 241, 0.4); font-weight: 700;">



                                    ${t.sighting_count} ${t.sighting_count === 1 ? 'Sighting' : 'Sightings'}



                                </span>



                            </div>



                            <div style="margin-bottom: 12px; display: flex; gap: 8px; align-items: center;">



                                ${statusBadge}



                                <span style="font-size: 0.875rem; color: var(--text-secondary);">${escapeHtml(t.vehicle_type || 'Vehicle')} • ${escapeHtml(t.vehicle_color || 'Color')}</span>



                            </div>



                            ${t.involved_in_case && t.fir_number ? `



                                <div style="font-size: 0.875rem; color: #991b1b; margin-bottom: 10px; background: rgba(239, 68, 68, 0.08); padding: 4px 8px; border-radius: 4px;">



                                    <strong>FIR:</strong> ${escapeHtml(t.fir_number)} | <strong>PS:</strong> ${escapeHtml(t.police_station || 'N/A')}



                                </div>



                            ` : ''}



                            <div class="card-meta-row" style="margin-top: 6px; padding: 10px; background: rgba(241,245,249,0.5); border-radius: var(--radius-sm);">



                                <div>



                                    <strong style="color: var(--text-muted); font-size: 0.875rem; display: block;">LAST SEEN POST</strong>



                                    <span style="color: #ffffff; font-size: 0.8825rem;">📍 ${escapeHtml(t.last_seen_location)}</span>



                                    ${t.last_seen_gps ? `<small style="display: block; font-family: var(--font-mono); color: #818cf8; font-size: 0.875rem; margin-top: 2px;">🌐 GPS: ${escapeHtml(t.last_seen_gps)}</small>` : ''}



                                </div>



                                <div><strong style="color: var(--text-muted); font-size: 0.875rem; display: block;">LAST CAMERA</strong><span class="meta-pill">${escapeHtml(t.last_seen_camera)}</span></div>



                            </div>



                            <div style="font-size: 0.875rem; color: var(--text-muted); margin-top: 8px;">



                                Last captured: <span style="color: #475569; font-family: var(--font-mono);">${formatIsoTimestamp(t.last_seen_time)}</span>



                            </div>



                        </div>



                        <div class="card-footer-actions" style="margin-top: 16px; padding-top: 12px; border-top: 1px solid var(--border-color); display: flex; gap: 8px;">



                            <button class="btn btn-primary" style="flex: 1.3; justify-content: center; background: #4f46e5; font-size: 0.875rem; padding: 7px 10px;" onclick="openTrailHistoryModal(${t.vehicle_id}, '${escapeHtml(t.display_number)}')">



                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>



                                Passage History (${t.sighting_count})



                            </button>



                            <button class="btn btn-secondary" style="flex: 1; justify-content: center; font-size: 0.875rem; padding: 7px 8px; border-color: rgba(129, 140, 248, 0.4); background: rgba(99, 102, 241, 0.12); color: #4338ca; font-weight: 600;" onclick="openTrailNarrativeDirect(${t.vehicle_id}, '${escapeHtml(t.display_number)}')">



                                <span>🧭 Story (AI)</span>



                            </button>



                            <button type="button" class="btn btn-secondary btn-delete-trail" style="flex: 0 0 36px; justify-content: center; font-size: 0.875rem; padding: 7px 8px; border-color: rgba(239, 68, 68, 0.4); background: rgba(239, 68, 68, 0.12); color: #b91c1c; cursor: pointer;" onclick="event.stopPropagation(); window.deleteVehicleTrail(${t.vehicle_id}, '${escapeHtml(t.display_number)}')" title="Delete Entire Trail for ${escapeHtml(t.display_number)}">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                            </button>



                        </div>



                    </div>



                `;
      }).join('');
    } catch (err) {
      console.error("Error loading vehicle trail:", err);
    }
  }
  window.openTrailHistoryModal = async (vehicleId, displayNumber) => {
    activeTrailVehicleId = vehicleId;
    activeTrailDisplayNumber = displayNumber || `Vehicle #${vehicleId}`;
    if (trailModalPlateText) trailModalPlateText.innerText = activeTrailDisplayNumber;
    if (trailFilterStartDate) trailFilterStartDate.value = '';
    if (trailFilterEndDate) trailFilterEndDate.value = '';
    if (trailFilterCamera) trailFilterCamera.value = '';
    if (trailFilterLocation) trailFilterLocation.value = '';
    if (trailHistoryModal) trailHistoryModal.style.display = 'flex';
    await loadTrailHistoryData();
  };
  async function loadTrailHistoryData() {
    if (!activeTrailVehicleId) return;
    try {
      trailModalHistoryBody.innerHTML = '<div style="text-align: center; padding: 40px; color: var(--text-muted);">Loading passage timeline...</div>';
      const params = new URLSearchParams();
      if (trailFilterStartDate?.value) params.append('start_date', trailFilterStartDate.value);
      if (trailFilterEndDate?.value) params.append('end_date', trailFilterEndDate.value);
      if (trailFilterCamera?.value.trim()) params.append('camera_id', trailFilterCamera.value.trim());
      if (trailFilterLocation?.value.trim()) params.append('location', trailFilterLocation.value.trim());
      const res = await fetch(`/api/trails/${activeTrailVehicleId}?${params.toString()}`);
      if (!res.ok) {
        trailModalHistoryBody.innerHTML = '<div class="empty-state"><p>Could not load vehicle history.</p></div>';
        return;
      }
      const data = await res.json();
      const history = data.history || [];
      window.karnalCameraRegistry?.renderTrailMap(history);
      currentTrailHistoryData = history;
      if (history.length === 0) {
        trailModalHistoryBody.innerHTML = `



                    <div class="empty-state">



                        <p>No sightings match the current filter criteria.</p>



                    </div>



                `;
        return;
      }
      trailModalHistoryBody.innerHTML = `



                <div style="background: linear-gradient(135deg, rgba(79, 70, 229, 0.18) 0%, rgba(124, 58, 237, 0.18) 100%); border: 1px solid rgba(129, 140, 248, 0.35); border-radius: 8px; padding: 12px 18px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap;">



                    <div style="display: flex; align-items: center; gap: 10px;">



                        <span style="font-size: 1.3rem;">🧭</span>



                        <div>



                            <div style="font-size: 0.9425rem; font-weight: 700; color: #1e293b;">Movement Narrative & Route Summary Available</div>



                            <div style="font-size: 0.875rem; color: var(--text-muted);">AI Hinglish movement narrative & Export PDF report</div>



                        </div>



                    </div>



                    <button class="btn btn-primary" style="padding: 6px 14px; font-size: 0.875rem; background: #6366f1; border-radius: 6px; display: flex; align-items: center; gap: 6px; cursor: pointer;" onclick="openTrailNarrativePopup()">



                        <span>✨ View Route Story</span>



                    </button>



                </div>



                <div class="timeline-container" style="position: relative; padding-left: 20px; border-left: 2px solid rgba(99, 102, 241, 0.4);">



                    ${history.map((s, idx) => {
        const platePic = s.plate_photo_path ? `<div style="flex: 1;"><label style="font-size: 0.875rem; color: var(--text-muted); display: block; margin-bottom: 4px;">PLATE EVIDENCE</label><img src="${s.plate_photo_path}" style="width: 100%; max-height: 90px; object-fit: contain; background: #000; border-radius: 4px; border: 1px solid var(--border-color);"></div>` : '';
        const vehPic = s.vehicle_photo_path ? `<div style="flex: 1;"><label style="font-size: 0.875rem; color: var(--text-muted); display: block; margin-bottom: 4px;">VEHICLE CONTEXT</label><img src="${s.vehicle_photo_path}" style="width: 100%; max-height: 90px; object-fit: contain; background: #000; border-radius: 4px; border: 1px solid var(--border-color);"></div>` : '';
        return `



                            <div class="timeline-item" style="position: relative; margin-bottom: 24px;">



                                <div style="position: absolute; left: -27px; top: 4px; width: 12px; height: 12px; border-radius: 50%; background: #6366f1; border: 2px solid #ffffff;"></div>



                                <div style="background: var(--bg-card); border: 1px solid var(--border-color); border-radius: var(--radius-md); padding: 16px;">



                                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; border-bottom: 1px solid var(--border-color); padding-bottom: 8px;">



                                        <div>



                                            <span style="font-weight: 700; color: #818cf8; font-size: 0.9125rem;">Passage #${idx + 1}</span>



                                            <span style="margin-left: 8px; font-family: var(--font-mono); font-size: 0.875rem; color: #ffffff;">${formatIsoTimestamp(s.captured_at)}</span>



                                        </div>



                                        <div style="display: flex; gap: 8px; align-items: center;">



                                            <span class="meta-pill" style="font-size: 0.875rem;">📹 ${escapeHtml(s.camera_id)}</span>



                                            <span class="conf-pill" style="font-size: 0.875rem;">${s.confidence}% Conf</span>



                                            <button type="button" class="btn btn-sm btn-secondary" style="padding: 2px 7px; font-size: 0.875rem; color: #ef4444; border-color: rgba(239, 68, 68, 0.4); background: rgba(239, 68, 68, 0.1); cursor: pointer; border-radius: 4px;" onclick="window.deleteTrailSighting(${s.id})" title="Delete this passage sighting">
                                                🗑️ Delete
                                            </button>



                                        </div>



                                    </div>



                                    <div style="margin-bottom: 12px; font-size: 0.9125rem; color: var(--text-secondary); display: flex; flex-wrap: wrap; gap: 14px; align-items: center;">



                                        <div>📍 <strong>Checkpoint / Post:</strong> <span style="color: #ffffff;">${escapeHtml(s.location)}</span></div>



                                        ${s.gps_coords ? `<div style="font-family: var(--font-mono); font-size: 0.875rem; background: rgba(99, 102, 241, 0.12); color: #818cf8; padding: 2px 8px; border-radius: 4px; border: 1px solid rgba(99, 102, 241, 0.3);">🌐 GPS: ${escapeHtml(s.gps_coords)}</div>` : ''}



                                    </div>



                                    ${platePic || vehPic ? `



                                        <div style="display: flex; gap: 12px; margin-top: 10px;">



                                            ${platePic}



                                            ${vehPic}



                                        </div>



                                    ` : ''}



                                </div>



                            </div>



                        `;
      }).join('')}



                </div>



                <div style="text-align: center; padding: 16px 0 6px 0; margin-top: 10px; border-top: 1px dashed rgba(255, 255, 255, 0.1);">



                    <button class="btn btn-secondary" style="background: rgba(99, 102, 241, 0.15); border-color: rgba(99, 102, 241, 0.4); color: #4338ca; padding: 8px 20px; font-size: 0.8825rem; border-radius: 8px; cursor: pointer; display: inline-flex; align-items: center; gap: 8px;" onclick="openTrailNarrativePopup()">



                        <span>🧭</span>



                        <span>Open Complete Route Summary Popup (AI Story)</span>



                    </button>



                </div>



            `;
    } catch (err) {
      console.error(err);
      trailModalHistoryBody.innerHTML = '<div class="empty-state"><p>Error loading history data.</p></div>';
    }
  }
  let currentTrailNarrativeLang = 'hinglish';
  let currentTrailHistoryData = [];
  window.switchTrailNarrativeLang = lang => {
    currentTrailNarrativeLang = lang;
    if (trailNarrativeModalBody && currentTrailHistoryData && currentTrailHistoryData.length > 0) {
      trailNarrativeModalBody.innerHTML = renderTrailNarrativeHtml(currentTrailHistoryData, currentTrailNarrativeLang);
    }
  };
  window.openTrailNarrativePopup = () => {
    if (!currentTrailHistoryData || currentTrailHistoryData.length === 0) {
      showToast('No passage sightings available for route summary', 'warning');
      return;
    }
    if (trailNarrativeModalPlateText) {
      trailNarrativeModalPlateText.innerText = activeTrailDisplayNumber || (trailModalPlateText ? trailModalPlateText.innerText : 'Vehicle');
    }
    if (trailNarrativeModalBody) {
      trailNarrativeModalBody.innerHTML = renderTrailNarrativeHtml(currentTrailHistoryData, currentTrailNarrativeLang);
    }
    if (trailNarrativeModal) {
      trailNarrativeModal.style.display = 'flex';
    }
  };
  window.openTrailNarrativeDirect = async (vehicleId, displayNumber) => {
    activeTrailVehicleId = vehicleId;
    activeTrailDisplayNumber = displayNumber || `Vehicle #${vehicleId}`;
    if (trailNarrativeModalPlateText) {
      trailNarrativeModalPlateText.innerText = activeTrailDisplayNumber;
    }
    if (trailNarrativeModalBody) {
      trailNarrativeModalBody.innerHTML = '<div style="text-align: center; padding: 40px; color: var(--text-muted);"><div class="spinner" style="margin: 0 auto 12px auto;"></div>Generating route movement story...</div>';
    }
    if (trailNarrativeModal) {
      trailNarrativeModal.style.display = 'flex';
    }
    try {
      const res = await fetch(`/api/trails/${vehicleId}`);
      if (!res.ok) {
        trailNarrativeModalBody.innerHTML = '<div class="empty-state"><p>Could not load route history.</p></div>';
        return;
      }
      const data = await res.json();
      currentTrailHistoryData = data.history || [];
      if (currentTrailHistoryData.length === 0) {
        trailNarrativeModalBody.innerHTML = '<div class="empty-state"><p>No recorded sightings for this vehicle yet.</p></div>';
        return;
      }
      trailNarrativeModalBody.innerHTML = renderTrailNarrativeHtml(currentTrailHistoryData, currentTrailNarrativeLang);
    } catch (e) {
      console.error(e);
      trailNarrativeModalBody.innerHTML = '<div class="empty-state"><p>Error generating summary.</p></div>';
    }
  };
  function renderTrailNarrativeHtml(history, lang = 'hinglish') {
    if (!history || history.length === 0) return '';
    const chronological = [...history].sort((a, b) => {
      const tA = a.captured_epoch != null ? a.captured_epoch : new Date(a.captured_at).getTime() / 1000 || 0;
      const tB = b.captured_epoch != null ? b.captured_epoch : new Date(b.captured_at).getTime() / 1000 || 0;
      return tA - tB;
    });
    const N = chronological.length;
    function formatNarrativeTime(dateObj, l) {
      if (!dateObj || isNaN(dateObj.getTime())) return 'Unknown time';
      const hours = dateObj.getHours();
      const minutes = String(dateObj.getMinutes()).padStart(2, '0');
      const ampm = hours >= 12 ? 'PM' : 'AM';
      const h12 = hours % 12 || 12;
      const time12 = `${String(h12).padStart(2, '0')}:${minutes} ${ampm}`;
      if (l === 'english') return time12;
      let period = '';
      if (hours >= 4 && hours < 12) {
        period = l === 'hindi' ? 'सुबह' : 'subah';
      } else if (hours >= 12 && hours < 16) {
        period = l === 'hindi' ? 'दोपहर' : 'dopahar';
      } else if (hours >= 16 && hours < 20) {
        period = l === 'hindi' ? 'शाम' : 'shaam';
      } else {
        period = l === 'hindi' ? 'रात' : 'raat';
      }
      if (l === 'hindi') {
        return `${period} ${String(h12).padStart(2, '0')}:${minutes} बजे (${ampm})`;
      }
      return `${period} ${String(h12).padStart(2, '0')}:${minutes} ${ampm}`;
    }
    function formatNarrativeDate(dateObj, l) {
      if (!dateObj || isNaN(dateObj.getTime())) return '';
      const day = dateObj.getDate();
      const year = dateObj.getFullYear();
      const monthsEng = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
      const monthsHi = ['जनवरी', 'फरवरी', 'मार्च', 'अप्रैल', 'मई', 'जून', 'जुलाई', 'अगस्त', 'सितंबर', 'अक्टूबर', 'नवंबर', 'दिसंबर'];
      if (l === 'hindi') return `${day} ${monthsHi[dateObj.getMonth()]} ${year}`;
      return `${day} ${monthsEng[dateObj.getMonth()]} ${year}`;
    }
    function formatTransitDuration(sec, l) {
      if (sec < 60) {
        if (l === 'hindi') return '1 मिनट से कम';
        if (l === 'hinglish') return '1 minute se kam';
        return '< 1 min';
      }
      const mins = Math.round(sec / 60);
      if (mins < 60) {
        if (l === 'hindi') return `${mins} मिनट`;
        if (l === 'hinglish') return `${mins} minute`;
        return `${mins} mins`;
      }
      const hours = Math.floor(mins / 60);
      const remMins = mins % 60;
      if (hours < 24) {
        if (remMins === 0) {
          if (l === 'hindi') return `${hours} घंटे`;
          if (l === 'hinglish') return `${hours} ghante`;
          return `${hours} hrs`;
        }
        if (l === 'hindi') return `${hours} घंटे ${remMins} मिनट`;
        if (l === 'hinglish') return `${hours} ghante ${remMins} minute`;
        return `${hours}h ${remMins}m`;
      }
      const days = Math.floor(hours / 24);
      const remHours = hours % 24;
      if (l === 'hindi') return `${days} दिन ${remHours} घंटे`;
      if (l === 'hinglish') return `${days} din ${remHours} ghante`;
      return `${days}d ${remHours}h`;
    }
    const legs = [];
    for (let i = 0; i < chronological.length; i++) {
      const item = chronological[i];
      const d = new Date(item.captured_at);
      const dateKey = d.toDateString();
      const locKey = (item.location || 'Unknown').trim().toLowerCase();
      if (legs.length > 0) {
        const prevLeg = legs[legs.length - 1];
        if (prevLeg.locKey === locKey && prevLeg.dateKey === dateKey) {
          prevLeg.count += 1;
          prevLeg.endItem = item;
          prevLeg.endD = d;
          continue;
        }
      }
      legs.push({
        locKey,
        dateKey,
        location: item.location || 'Unknown Checkpoint',
        camera_id: item.camera_id || '',
        gps_coords: item.gps_coords || '',
        startItem: item,
        startD: d,
        endItem: item,
        endD: d,
        count: 1
      });
    }
    let story = '';
    if (lang === 'hindi') {
      const parts = [];
      for (let i = 0; i < legs.length; i++) {
        const leg = legs[i];
        const dateStr = formatNarrativeDate(leg.startD, 'hindi');
        const startTimeStr = formatNarrativeTime(leg.startD, 'hindi');
        const endTimeStr = formatNarrativeTime(leg.endD, 'hindi');
        const loc = `<strong style="color: #4338ca;">${escapeHtml(leg.location)}</strong>`;
        const cam = leg.camera_id ? `(${escapeHtml(leg.camera_id)})` : '';
        const prevDateKey = i > 0 ? legs[i - 1].dateKey : null;
        const isNewDate = leg.dateKey !== prevDateKey;
        const datePrefix = i === 0 || isNewDate ? `<strong style="color: #fde047;">${dateStr}</strong> को ` : '';
        const seenBefore = legs.slice(0, i).some(l => l.locKey === leg.locKey);
        if (i === 0) {
          if (leg.count > 1) {
            parts.push(`यह वाहन सबसे पहले ${datePrefix}<strong style="color: #0369a1;">${startTimeStr}</strong> से <strong style="color: #0369a1;">${endTimeStr}</strong> के बीच ${loc} ${cam} पर कुल ${leg.count} बार देखा गया`);
          } else {
            parts.push(`यह वाहन सबसे पहले ${datePrefix}<strong style="color: #0369a1;">${startTimeStr}</strong> ${loc} ${cam} पर देखा गया`);
          }
        } else if (i === legs.length - 1) {
          const verb = seenBefore ? `वापस ${loc} पर आया` : `${loc} पर गया`;
          if (leg.count > 1) {
            parts.push(`और अंत में ${datePrefix}<strong style="color: #0369a1;">${startTimeStr}</strong> से <strong style="color: #0369a1;">${endTimeStr}</strong> तक ${verb}`);
          } else {
            parts.push(`और अंत में ${datePrefix}<strong style="color: #0369a1;">${startTimeStr}</strong> ${verb}`);
          }
        } else {
          const connector = isNewDate ? 'फिर' : i % 2 === 1 ? 'फिर' : 'इसके बाद';
          const repeatWord = seenBefore ? 'दोबारा ' : '';
          if (leg.count > 1) {
            parts.push(`${connector} ${datePrefix}<strong style="color: #0369a1;">${startTimeStr}</strong> से <strong style="color: #0369a1;">${endTimeStr}</strong> के दौरान ${repeatWord}${loc} पर ${leg.count} बार दिखा`);
          } else {
            parts.push(`${connector} ${datePrefix}<strong style="color: #0369a1;">${startTimeStr}</strong> ${repeatWord}${loc} पर दिखा`);
          }
        }
      }
      story = parts.join('. ') + '।';
    } else if (lang === 'english') {
      const parts = [];
      for (let i = 0; i < legs.length; i++) {
        const leg = legs[i];
        const dateStr = formatNarrativeDate(leg.startD, 'english');
        const startTimeStr = formatNarrativeTime(leg.startD, 'english');
        const endTimeStr = formatNarrativeTime(leg.endD, 'english');
        const loc = `<strong style="color: #4338ca;">${escapeHtml(leg.location)}</strong>`;
        const cam = leg.camera_id ? `(${escapeHtml(leg.camera_id)})` : '';
        const prevDateKey = i > 0 ? legs[i - 1].dateKey : null;
        const isNewDate = leg.dateKey !== prevDateKey;
        const datePrefix = i === 0 || isNewDate ? `on <strong style="color: #fde047;">${dateStr}</strong> at ` : 'at ';
        const seenBefore = legs.slice(0, i).some(l => l.locKey === leg.locKey);
        if (i === 0) {
          if (leg.count > 1) {
            parts.push(`This vehicle was first spotted ${datePrefix}<strong style="color: #0369a1;">${startTimeStr}</strong> to <strong style="color: #0369a1;">${endTimeStr}</strong> at ${loc} ${cam} (${leg.count} sightings)`);
          } else {
            parts.push(`This vehicle was first spotted ${datePrefix}<strong style="color: #0369a1;">${startTimeStr}</strong> at ${loc} ${cam}`);
          }
        } else if (i === legs.length - 1) {
          const verb = seenBefore ? `returned to ${loc}` : `arrived at ${loc}`;
          if (leg.count > 1) {
            parts.push(`and finally ${verb} ${datePrefix}<strong style="color: #0369a1;">${startTimeStr}</strong> to <strong style="color: #0369a1;">${endTimeStr}</strong>`);
          } else {
            parts.push(`and finally ${verb} ${datePrefix}<strong style="color: #0369a1;">${startTimeStr}</strong>`);
          }
        } else {
          const connector = isNewDate ? 'Then' : i % 2 === 1 ? 'Then' : 'Afterwards,';
          const repeatWord = seenBefore ? 'again ' : '';
          if (leg.count > 1) {
            parts.push(`${connector} ${datePrefix}<strong style="color: #0369a1;">${startTimeStr}</strong> to <strong style="color: #0369a1;">${endTimeStr}</strong>, it was recorded ${repeatWord}${leg.count} times at ${loc}`);
          } else {
            parts.push(`${connector} ${datePrefix}<strong style="color: #0369a1;">${startTimeStr}</strong>, it was seen ${repeatWord}at ${loc}`);
          }
        }
      }
      story = parts.join('. ') + '.';
    } else {
      const parts = [];
      for (let i = 0; i < legs.length; i++) {
        const leg = legs[i];
        const dateStr = formatNarrativeDate(leg.startD, 'hinglish');
        const startTimeStr = formatNarrativeTime(leg.startD, 'hinglish');
        const endTimeStr = formatNarrativeTime(leg.endD, 'hinglish');
        const loc = `<strong style="color: #4338ca;">${escapeHtml(leg.location)}</strong>`;
        const cam = leg.camera_id ? `(${escapeHtml(leg.camera_id)})` : '';
        const prevDateKey = i > 0 ? legs[i - 1].dateKey : null;
        const isNewDate = leg.dateKey !== prevDateKey;
        const datePrefix = i === 0 || isNewDate ? `<strong style="color: #fde047;">${dateStr}</strong> ko ` : '';
        const seenBefore = legs.slice(0, i).some(l => l.locKey === leg.locKey);
        if (i === 0) {
          if (leg.count > 1) {
            parts.push(`Yeh gaadi sabse pehle ${datePrefix}<strong style="color: #0369a1;">${startTimeStr}</strong> se <strong style="color: #0369a1;">${endTimeStr}</strong> ke dauran ${loc} ${cam} par kul ${leg.count} baar dekhi gayi`);
          } else {
            parts.push(`Yeh gaadi sabse pehle ${datePrefix}<strong style="color: #0369a1;">${startTimeStr}</strong> par ${loc} ${cam} par dekhi gayi`);
          }
        } else if (i === legs.length - 1) {
          const verb = seenBefore ? `wapas ${loc} par aayi` : `${loc} par gayi`;
          if (leg.count > 1) {
            parts.push(`aur aakhir me ${datePrefix}<strong style="color: #0369a1;">${startTimeStr}</strong> se <strong style="color: #0369a1;">${endTimeStr}</strong> tak ${verb}`);
          } else {
            parts.push(`aur aakhir me ${datePrefix}<strong style="color: #0369a1;">${startTimeStr}</strong> par ${verb}`);
          }
        } else {
          const connector = isNewDate ? 'Fir' : i % 2 === 1 ? 'Fir' : 'Uske baad';
          const repeatWord = seenBefore ? 'dobara ' : '';
          if (leg.count > 1) {
            parts.push(`${connector} ${datePrefix}<strong style="color: #0369a1;">${startTimeStr}</strong> se <strong style="color: #0369a1;">${endTimeStr}</strong> ke beech ${repeatWord}${loc} par ${leg.count} baar dikhi`);
          } else {
            parts.push(`${connector} ${datePrefix}<strong style="color: #0369a1;">${startTimeStr}</strong> par ${repeatWord}${loc} par aayi`);
          }
        }
      }
      story = parts.join('. ') + '.';
    }
    const tEpoch0 = chronological[0].captured_epoch || new Date(chronological[0].captured_at).getTime() / 1000 || 0;
    const tEpochN = chronological[N - 1].captured_epoch || new Date(chronological[N - 1].captured_at).getTime() / 1000 || 0;
    const transitSec = Math.max(0, tEpochN - tEpoch0);
    const durationStr = formatTransitDuration(transitSec, lang);
    const startLoc = chronological[0].location || 'Origin';
    const endLoc = chronological[N - 1].location || 'Destination';
    let storyHeading = 'Route Movement Narrative (सफ़र का पूरा विवरण)';
    let timeLabel = 'Total Transit Span';
    let checkLabel = 'Passages Recorded';
    let corrLabel = 'Primary Corridor';
    if (lang === 'hindi') {
      storyHeading = 'वाहन यात्रा का संपूर्ण विवरण (Movement Story)';
      timeLabel = 'कुल यात्रा समय';
      checkLabel = 'कुल गतिविधियां';
      corrLabel = 'मुख्य मार्ग गलियारा';
    } else if (lang === 'english') {
      storyHeading = 'Full Chronological Journey Narrative';
      timeLabel = 'Total Transit Time';
      checkLabel = 'Sightings Recorded';
      corrLabel = 'Primary Corridor';
    }
    return `



            <div class="trail-narrative-container" id="trailNarrativeBox" style="display: flex; flex-direction: column; gap: 14px;">



                <!-- THE HERO: Natural Language Journey Story -->



                <div class="trail-narrative-hero-card" style="background: linear-gradient(135deg, rgba(30, 27, 75, 0.6) 0%, rgba(241,245,249,0.95) 100%); border: 1px solid rgba(129, 140, 248, 0.45); border-left: 5px solid #6366f1; border-radius: 10px; padding: 20px 22px; box-shadow: 0 6px 24px rgba(0, 0, 0, 0.35);">



                    <div style="font-size: 0.875rem; font-weight: 700; color: #818cf8; text-transform: uppercase; letter-spacing: 0.6px; margin-bottom: 12px; display: flex; align-items: center; gap: 8px;">



                        <span>📖</span>



                        <span>${storyHeading}</span>



                        <span class="trail-narrative-badge" style="margin-left: auto;">AI Story Narrative</span>



                    </div>



                    <div class="trail-narrative-body" style="font-size: 1.1125rem; line-height: 1.85; color: #172033; background: transparent; padding: 0; border: none; box-shadow: none;">



                        "${story}"



                    </div>



                </div>



                <!-- 3. Key Transit Stats Bar -->



                <div style="display: flex; flex-wrap: wrap; gap: 10px;">



                    <div style="flex: 1; min-width: 140px; background: rgba(241,245,249,0.7); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px; padding: 10px 14px;">



                        <div style="font-size: 0.875rem; color: var(--text-muted); text-transform: uppercase; font-weight: 600;">⏱️ ${timeLabel}</div>



                        <div style="font-size: 1.0125rem; font-weight: 700; color: #0369a1; margin-top: 3px;">${durationStr}</div>



                    </div>



                    <div style="flex: 1; min-width: 140px; background: rgba(241,245,249,0.7); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px; padding: 10px 14px;">



                        <div style="font-size: 0.875rem; color: var(--text-muted); text-transform: uppercase; font-weight: 600;">📍 ${checkLabel}</div>



                        <div style="font-size: 1.0125rem; font-weight: 700; color: #4338ca; margin-top: 3px;">${N} sightings (${legs.length} movements)</div>



                    </div>



                    <div style="flex: 1.5; min-width: 200px; background: rgba(241,245,249,0.7); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px; padding: 10px 14px;">



                        <div style="font-size: 0.875rem; color: var(--text-muted); text-transform: uppercase; font-weight: 600;">🚗 ${corrLabel}</div>



                        <div style="font-size: 0.9825rem; font-weight: 700; color: #ffffff; margin-top: 3px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">



                            ${escapeHtml(startLoc)} ➔ ${escapeHtml(endLoc)}



                        </div>



                    </div>



                </div>



                <!-- 4. Step-by-Step Chronological Passage Log Table -->



                <div style="margin-top: 6px; border-top: 1px solid rgba(255, 255, 255, 0.08); padding-top: 14px;">



                    <div style="font-size: 0.875rem; font-weight: 700; color: #52647c; text-transform: uppercase; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center;">



                        <span>📋 Passage Evidence Log (${N} Sightings)</span>



                        <span style="font-size: 0.875rem; color: var(--text-muted); font-weight: 500;">Oldest ➔ Newest</span>



                    </div>



                    <div style="max-height: 240px; overflow-y: auto; border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 6px;">



                        <table style="width: 100%; border-collapse: collapse; font-size: 0.875rem; text-align: left;">



                            <thead>



                                <tr style="background: rgba(241,245,249,0.85); color: #475569; border-bottom: 1px solid rgba(255, 255, 255, 0.08); position: sticky; top: 0;">



                                    <th style="padding: 7px 10px;">#</th>



                                    <th style="padding: 7px 10px;">Date & Time</th>



                                    <th style="padding: 7px 10px;">Location / Post</th>



                                    <th style="padding: 7px 10px;">Camera</th>



                                    <th style="padding: 7px 10px;">Conf</th>



                                </tr>



                            </thead>



                            <tbody>



                                ${chronological.map((s, idx) => {
      const d = new Date(s.captured_at);
      const dtStr = d.toLocaleString('en-IN', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        hour12: true
      });
      return `



                                        <tr style="border-bottom: 1px solid rgba(255, 255, 255, 0.04); background: ${idx % 2 === 0 ? 'transparent' : 'rgba(241,245,249,0.35)'};">



                                            <td style="padding: 6px 10px; color: #818cf8; font-weight: 700;">#${idx + 1}</td>



                                            <td style="padding: 6px 10px; font-family: var(--font-mono); color: #0369a1;">${dtStr}</td>



                                            <td style="padding: 6px 10px; color: #ffffff; font-weight: 600;">${escapeHtml(s.location || 'Unknown')}</td>



                                            <td style="padding: 6px 10px;"><span class="meta-pill" style="font-size: 0.875rem;">${escapeHtml(s.camera_id || 'CAM')}</span></td>



                                            <td style="padding: 6px 10px; color: #10b981; font-weight: 600;">${s.confidence}%</td>



                                        </tr>



                                    `;
    }).join('')}



                            </tbody>



                        </table>



                    </div>



                </div>



            </div>



        `;
  }
  window.exportTrailNarrativePdf = () => {
    if (!currentTrailHistoryData || currentTrailHistoryData.length === 0) {
      showToast('No trail data available to export', 'warning');
      return;
    }
    const plate = activeTrailDisplayNumber || (trailModalPlateText ? trailModalPlateText.innerText : 'Vehicle');
    const chronological = [...currentTrailHistoryData].sort((a, b) => {
      const tA = a.captured_epoch != null ? a.captured_epoch : new Date(a.captured_at).getTime() / 1000 || 0;
      const tB = b.captured_epoch != null ? b.captured_epoch : new Date(b.captured_at).getTime() / 1000 || 0;
      return tA - tB;
    });
    const N = chronological.length;
    const tEpoch0 = chronological[0].captured_epoch || new Date(chronological[0].captured_at).getTime() / 1000 || 0;
    const tEpochN = chronological[N - 1].captured_epoch || new Date(chronological[N - 1].captured_at).getTime() / 1000 || 0;
    const transitSec = Math.max(0, tEpochN - tEpoch0);
    let durationStr = '< 1 min';
    if (transitSec >= 60) {
      const mins = Math.round(transitSec / 60);
      if (mins < 60) durationStr = `${mins} minute`; else {
        const hours = Math.floor(mins / 60);
        const remMins = mins % 60;
        durationStr = `${hours} ghante ${remMins} minute`;
      }
    }
    const startLoc = chronological[0].location || 'Checkpoint';
    const endLoc = chronological[N - 1].location || 'Checkpoint';
    const storyCard = document.querySelector('.trail-narrative-body');
    const storyHtml = storyCard ? storyCard.innerHTML : '';
    const now = new Date();
    const genTime = now.toLocaleString('en-IN', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: true
    });
    const printWindow = window.open('', '_blank');
    if (!printWindow) {
      alert('Please allow popups in your browser to download/print the PDF report.');
      return;
    }
    printWindow.document.write(`



            <!DOCTYPE html>



            <html>



            <head>



                <meta charset="UTF-8">



                <title>Vehicle_Trail_Report_${plate.replace(/\\s+/g, '_')}</title>



                <style>



                    @page { size: A4 portrait; margin: 12mm 15mm; }



                    @media print {



                        body { -webkit-print-color-adjust: exact; print-color-adjust: exact; padding: 0; }



                        .no-print { display: none !important; }



                    }



                    * { box-sizing: border-box; }



                    body {



                        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;



                        color: #ffffff;



                        background: #ffffff;



                        line-height: 1.6;



                        margin: 0;



                        padding: 24px;



                    }



                    .no-print-bar {



                        background: #f8fafc;



                        color: #ffffff;



                        padding: 12px 20px;



                        border-radius: 8px;



                        margin-bottom: 24px;



                        display: flex;



                        justify-content: space-between;



                        align-items: center;



                        box-shadow: 0 4px 12px rgba(0,0,0,0.15);



                    }



                    .btn-save-pdf {



                        background: #f8fafc;



                        color: #ffffff;



                        border: none;



                        padding: 8px 20px;



                        border-radius: 6px;



                        font-weight: 700;



                        font-size: 15px;



                        cursor: pointer;



                    }



                    .report-header {



                        display: flex;



                        justify-content: space-between;



                        align-items: center;



                        border-bottom: 3px solid #4f46e5;



                        padding-bottom: 14px;



                        margin-bottom: 20px;



                    }



                    .brand-name {



                        font-size: 18px;



                        font-weight: 800;



                        color: #1e1b4b;



                        letter-spacing: 0.5px;



                        text-transform: uppercase;



                    }



                    .brand-sub {



                        font-size: 14px;



                        color: #64748b;



                        margin-top: 2px;



                    }



                    .hsrp-box {



                        display: inline-flex;



                        align-items: center;



                        border: 2px solid #000;



                        border-radius: 6px;



                        overflow: hidden;



                        background: #fff;



                    }



                    .hsrp-strip {



                        background: #f8fafc;



                        color: #fff;



                        font-size: 14px;



                        font-weight: bold;



                        padding: 6px 4px;



                        writing-mode: vertical-lr;



                        text-align: center;



                    }



                    .hsrp-num {



                        font-family: monospace;



                        font-size: 20px;



                        font-weight: 900;



                        padding: 4px 14px;



                        letter-spacing: 2px;



                        color: #000;



                    }



                    .story-box {



                        background: #f8fafc;



                        border: 1px solid #475569;



                        border-left: 6px solid #4f46e5;



                        border-radius: 8px;



                        padding: 16px 20px;



                        margin-bottom: 20px;



                    }



                    .story-title {



                        font-size: 14px;



                        font-weight: 800;



                        text-transform: uppercase;



                        color: #4338ca;



                        margin-bottom: 8px;



                        letter-spacing: 0.5px;



                    }



                    .story-content {



                        font-size: 14.5px;



                        line-height: 1.8;



                        color: #e2e8f0;



                    }



                    .story-content strong {



                        color: #ffffff;



                    }



                    .stats-bar {



                        display: flex;



                        gap: 12px;



                        margin-bottom: 22px;



                    }



                    .stat-item {



                        flex: 1;



                        background: #f8fafc;



                        border: 1px solid #334155;



                        border-radius: 6px;



                        padding: 10px 14px;



                    }



                    .stat-label {



                        font-size: 14px;



                        font-weight: 700;



                        text-transform: uppercase;



                        color: #64748b;



                    }



                    .stat-val {



                        font-size: 15px;



                        font-weight: 800;



                        color: #e2e8f0;



                        margin-top: 2px;



                    }



                    table {



                        width: 100%;



                        border-collapse: collapse;



                        font-size: 14px;



                        margin-top: 10px;



                    }



                    th {



                        background: #e2e8f0;



                        color: #ffffff;



                        padding: 8px 10px;



                        text-align: left;



                        font-weight: 700;



                        font-size: 14px;



                        text-transform: uppercase;



                    }



                    td {



                        padding: 7px 10px;



                        border-bottom: 1px solid #334155;



                        color: #334155;



                    }



                    tr:nth-child(even) td {



                        background: #f8fafc;



                    }



                    .footer-note {



                        margin-top: 24px;



                        padding-top: 12px;



                        border-top: 1px solid #334155;



                        display: flex;



                        justify-content: space-between;



                        font-size: 14px;



                        color: #52647c;



                    }



                </style>



            </head>



            <body>



                <div class="no-print-bar no-print">



                    <div>



                        <strong style="font-size: 16px;">Vehicle Movement Trail Investigation Report</strong>



                        <div style="font-size: 14px; opacity: 0.85;">Click below to Save as PDF or Print document</div>



                    </div>



                    <button class="btn-save-pdf" onclick="window.print()">🖨️ Save as PDF / Print</button>



                </div>



                <div class="report-header">



                    <div>



                        <div class="brand-name">Smart ANPR Vehicle Surveillance System</div>



                        <div class="brand-sub">Official Chronological Trail & Movement Narrative Report</div>



                    </div>



                    <div class="hsrp-box">



                        <div class="hsrp-strip">IND</div>



                        <div class="hsrp-num">${escapeHtml(plate)}</div>



                    </div>



                </div>



                <div class="story-box">



                    <div class="story-title">📖 Vehicle Journey Movement Narrative (सफ़र का पूरा विवरण)</div>



                    <div class="story-content">${storyHtml}</div>



                </div>



                <div class="stats-bar">



                    <div class="stat-item">



                        <div class="stat-label">Total Transit Span</div>



                        <div class="stat-val">${durationStr}</div>



                    </div>



                    <div class="stat-item">



                        <div class="stat-label">Passages Recorded</div>



                        <div class="stat-val">${N} Sightings</div>



                    </div>



                    <div class="stat-item">



                        <div class="stat-label">Primary Corridor</div>



                        <div class="stat-val">${escapeHtml(startLoc)} ➔ ${escapeHtml(endLoc)}</div>



                    </div>



                </div>



                <div>



                    <div style="font-size: 14px; font-weight: 800; text-transform: uppercase; color: #1e1b4b; margin-bottom: 6px;">



                        📋 Chronological Passage Evidence Log (${N} Records)



                    </div>



                    <table>



                        <thead>



                            <tr>



                                <th>#</th>



                                <th>Date & Time</th>



                                <th>Location / Post</th>



                                <th>Camera</th>



                                <th>Conf</th>



                            </tr>



                        </thead>



                        <tbody>



                            ${chronological.map((s, idx) => {
      const d = new Date(s.captured_at);
      const dtStr = d.toLocaleString('en-IN', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        hour12: true
      });
      return `



                                    <tr>



                                        <td style="font-weight: bold; color: #4338ca;">#${idx + 1}</td>



                                        <td style="font-family: monospace; font-weight: bold;">${dtStr}</td>



                                        <td style="font-weight: bold;">${escapeHtml(s.location || 'Unknown')}</td>



                                        <td>${escapeHtml(s.camera_id || 'CAM-01')}</td>



                                        <td>${s.confidence}%</td>



                                    </tr>



                                `;
    }).join('')}



                        </tbody>



                    </table>



                </div>



                <div class="footer-note">



                    <span>Generated by ANPR Neural Core Intelligence Engine</span>



                    <span>Report Time: ${genTime} &bull; Page 1 of 1</span>



                </div>



                <script>



                    window.onload = function() {



                        setTimeout(function() {



                            window.print();



                        }, 400);



                    };



                </script>



            </body>



            </html>



        `);
    printWindow.document.close();
  };
  function formatIsoTimestamp(iso) {
    if (!iso) return 'Unknown';
    try {
      const d = new Date(iso);
      return d.toLocaleString('en-IN', {
        hour12: false,
        timeZoneName: 'short'
      });
    } catch (e) {
      return iso;
    }
  }
  if (closeTrailHistoryModalBtn) {
    closeTrailHistoryModalBtn.addEventListener('click', () => {
      if (trailHistoryModal) trailHistoryModal.style.display = 'none';
    });
  }
  if (closeTrailNarrativeModalBtn) {
    closeTrailNarrativeModalBtn.addEventListener('click', () => {
      if (trailNarrativeModal) trailNarrativeModal.style.display = 'none';
    });
  }
  if (btnOpenTrailNarrativeModal) {
    btnOpenTrailNarrativeModal.addEventListener('click', () => {
      window.openTrailNarrativePopup();
    });
  }
  if (btnApplyTrailFilters) btnApplyTrailFilters.addEventListener('click', loadTrailHistoryData);
  if (btnResetTrailFilters) {
    btnResetTrailFilters.addEventListener('click', () => {
      if (trailFilterStartDate) trailFilterStartDate.value = '';
      if (trailFilterEndDate) trailFilterEndDate.value = '';
      if (trailFilterCamera) trailFilterCamera.value = '';
      if (trailFilterLocation) trailFilterLocation.value = '';
      loadTrailHistoryData();
    });
  }
  if (btnRefreshTrail) btnRefreshTrail.addEventListener('click', fetchAndRenderVehicleTrail);
  if (trailSearchInput) {
    trailSearchInput.addEventListener('input', () => {
      clearTimeout(trailSearchDebounce);
      trailSearchDebounce = setTimeout(fetchAndRenderVehicleTrail, 300);
    });
  }
  window.confirmReviewVehicle = async (plate, plateCropB64, vehCropB64, conf, annotatedCropB64) => {
    const input = prompt(`Confirm / Correct vehicle plate reading:`, plate || '');
    if (!input || !input.trim()) return;
    try {
      const formData = new FormData();
      formData.append('plate_number', input.trim());
      formData.append('original_plate', (plate || '').trim());
      const reviewCamera = await window.karnalCameraRegistry.chooseCamera();
      if (!reviewCamera) return;
      formData.append('camera_id', reviewCamera.id);
      formData.append('location', reviewCamera.name);
      formData.append('confidence', conf || 90.0);
      if (plateCropB64) formData.append('plate_crop_base64', plateCropB64);
      if (vehCropB64) formData.append('vehicle_crop_base64', vehCropB64);
      if (annotatedCropB64) formData.append('annotated_crop_base64', annotatedCropB64);
      const res = await fetch('/api/review/confirm', {
        method: 'POST',
        body: formData
      });
      const data = await res.json();
      if (data.status === 'success') {
        alert(`Vehicle plate confirmed as "${data.display_plate || data.confirmed_plate}" and successfully recorded in Captured DB!`);
        if (typeof fetchAndRenderCapturedDb === 'function') {
          fetchAndRenderCapturedDb();
        }
        if (typeof fetchAndRenderVehicleTrail === 'function') {
          fetchAndRenderVehicleTrail();
        }
      } else {
        alert("Confirmation failed: " + (data.detail || "Unknown error"));
      }
    } catch (err) {
      console.error("Confirmation error:", err);
      alert("Error confirming vehicle: " + err.message);
    }
  };
  const btnOpenConnectModal = document.getElementById('btnOpenConnectModal');
  const btnDisconnectStream = document.getElementById('btnDisconnectStream');
  const connectCameraModal = document.getElementById('connectCameraModal');
  const closeConnectModalBtn = document.getElementById('closeConnectModalBtn');
  const btnCancelConnectModal = document.getElementById('btnCancelConnectModal');
  const connectCameraForm = document.getElementById('connectCameraForm');
  const feedActiveTab = document.getElementById('feedActiveTab');
  const feedSourceType = document.getElementById('feedSourceType');
  const feedWebcamIndex = document.getElementById('feedWebcamIndex');
  const feedStreamUrl = document.getElementById('feedStreamUrl');
  const feedRtspUrl = document.getElementById('feedRtspUrl');
  const feedHttpUrl = document.getElementById('feedHttpUrl');
  const feedCameraId = document.getElementById('feedCameraId');
  const feedLocation = document.getElementById('feedLocation');
  const feedGpsCoords = document.getElementById('feedGpsCoords');
  const btnDetectGps = document.getElementById('btnDetectGps');
  const grpWebcamInput = document.getElementById('grpWebcamInput');
  const grpRtspInput = document.getElementById('grpRtspInput');
  const grpHttpInput = document.getElementById('grpHttpInput');
  const panelSourceUpload = document.getElementById('panelSourceUpload');
  const panelSourceDemo = document.getElementById('panelSourceDemo');
  const panelSourceCamera = document.getElementById('panelSourceCamera');
  const feedMainTabs = document.querySelectorAll('.feed-main-tab');
  const camSubTabs = document.querySelectorAll('.cam-sub-tab');
  const feedTypeTabs = document.querySelectorAll('.feed-type-tab');
  if (btnDetectGps && !window.KARNAL_CAMERA_MODE) {
    btnDetectGps.addEventListener('click', async () => {
      btnDetectGps.disabled = true;
      btnDetectGps.innerText = "⏳ Detecting GPS...";
      const currentSlot = (feedCameraSlot ? feedCameraSlot.value : "CAM-01") || "CAM-01";
      const applyDetectedGps = (coords, locName, sourceTag = "") => {
        if (feedGpsCoords) {
          feedGpsCoords.value = coords;
          feedGpsCoords.classList.add('pulse-highlight');
          setTimeout(() => feedGpsCoords.classList.remove('pulse-highlight'), 1200);
        }
        if (feedLocation && (!feedLocation.value || feedLocation.value === "North Gate" || feedLocation.value === "Surveillance Post")) {
          if (locName) feedLocation.value = locName;
        }
        btnDetectGps.innerText = "📍 GPS Captured";
        btnDetectGps.style.borderColor = "#10b981";
        btnDetectGps.style.color = "#10b981";
        setTimeout(() => {
          btnDetectGps.innerText = "📍 Auto-Detect GPS";
          btnDetectGps.style.borderColor = "";
          btnDetectGps.style.color = "";
          btnDetectGps.disabled = false;
        }, 2500);
      };
      let resolved = false;
      if (navigator.geolocation && (window.isSecureContext || window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')) {
        try {
          const pos = await new Promise((resolve, reject) => {
            navigator.geolocation.getCurrentPosition(resolve, reject, {
              timeout: 2500,
              enableHighAccuracy: false
            });
          });
          if (pos && pos.coords) {
            const lat = pos.coords.latitude.toFixed(6);
            const lon = pos.coords.longitude.toFixed(6);
            applyDetectedGps(`${lat}, ${lon}`, null, "browser");
            resolved = true;
            try {
              fetch(`https://nominatim.openstreetmap.org/reverse?format=json&lat=${lat}&lon=${lon}&zoom=16&addressdetails=1`, {
                headers: {
                  'Accept': 'application/json'
                },
                signal: AbortSignal.timeout(2000)
              }).then(r => r.json()).then(revData => {
                const addr = revData.address || ({});
                const placeName = addr.road || addr.suburb || addr.city_district || addr.city || revData.display_name?.split(',')[0];
                if (placeName && feedLocation && (!feedLocation.value || feedLocation.value === "North Gate")) {
                  feedLocation.value = placeName.trim();
                }
              }).catch(() => {});
            } catch (e) {}
            return;
          }
        } catch (bErr) {
          console.log("Browser geolocation unavailable on Test VM/network, using server resolver:", bErr.message);
        }
      }
      try {
        const res = await fetch(`/api/geo/auto-detect?camera_id=${encodeURIComponent(currentSlot)}`);
        if (res.ok) {
          const data = await res.json();
          if (data && data.gps_coords) {
            applyDetectedGps(data.gps_coords, data.location_name, data.source);
            resolved = true;
            return;
          }
        }
      } catch (netErr) {
        console.warn("Backend geo resolve error:", netErr);
      }
      applyDetectedGps("29.390940, 76.963500", "Panipat NH-44 Toll Plaza Checkpoint (North Gate)", "client_fallback");
    });
  }
  const btnView1x1 = document.getElementById('btnView1x1');
  const btnView2x2 = document.getElementById('btnView2x2');
  const singleCamViewport = document.getElementById('singleCamViewport');
  const gridCamViewport = document.getElementById('gridCamViewport');
  const activeCamCounter = document.getElementById('activeCamCounter');
  const liveFeedImg = document.getElementById('liveFeedImg');
  const screenCenterMsg = document.getElementById('screenCenterMsg');
  const camStatusBadge = document.getElementById('camStatusBadge');
  const camBadgeDot = document.getElementById('camBadgeDot');
  const camBadgeText = document.getElementById('camBadgeText');
  const camStatusPill = document.getElementById('camStatusPill');
  const liveRecDot = document.getElementById('liveRecDot');
  const osdFpsText = document.getElementById('osdFpsText');
  const osdLocationText = document.getElementById('osdLocationText');
  const osdResText = document.getElementById('osdResText');
  const btnStreamFullscreen = document.getElementById('btnStreamFullscreen');
  const surveillanceScreen = document.getElementById('surveillanceScreen');
  const feedCameraSlot = document.getElementById('feedCameraSlot');
  const CAMERA_SLOTS = ["CAM-01", "CAM-02", "CAM-03", "CAM-04"];
  const SLOT_DEFAULT_LOCATIONS = {
    "CAM-01": "North Gate",
    "CAM-02": "South Toll",
    "CAM-03": "West Lane",
    "CAM-04": "East Terminal"
  };
  let currentViewMode = localStorage.getItem('anpr_cam_view_mode') || 'grid';
  let focusedCameraId = "CAM-01";
  let streamStatusPoll = null;
  let cameraActiveStates = {};
  let streamStartTimes = {};
  function switchViewMode(mode) {
    currentViewMode = mode;
    localStorage.setItem('anpr_cam_view_mode', mode);
    const anprInspectionViewport = document.getElementById('anprInspectionViewport');
    if (anprInspectionViewport) anprInspectionViewport.style.display = 'none';
    const dlBtn = document.getElementById('btnDownloadAnnotatedMedia');
    if (dlBtn) dlBtn.style.display = 'none';
    const titleText = document.getElementById('livePanelTitleText');
    if (titleText) titleText.innerText = "SURVEILLANCE FEED";
    if (mode === 'grid') {
      if (btnView2x2) btnView2x2.classList.add('active');
      if (btnView1x1) btnView1x1.classList.remove('active');
      if (gridCamViewport) gridCamViewport.style.display = 'block';
      if (singleCamViewport) singleCamViewport.style.display = 'none';
      if (camStatusBadge) camStatusBadge.style.display = 'none';
      if (liveFeedImg) {
        liveFeedImg.src = '';
        liveFeedImg.style.display = 'none';
      }
      pollCameraStatuses();
      fetchAndRenderUnifiedLiveFeed();
    } else {
      if (btnView1x1) btnView1x1.classList.add('active');
      if (btnView2x2) btnView2x2.classList.remove('active');
      if (singleCamViewport) singleCamViewport.style.display = 'flex';
      if (gridCamViewport) gridCamViewport.style.display = 'none';
      if (camStatusBadge) camStatusBadge.style.display = 'inline-flex';
      CAMERA_SLOTS.forEach(cid => {
        const feedImg = document.getElementById(`tileFeedImg-${cid}`);
        if (feedImg) feedImg.src = '';
      });
      updateSingleFocusView();
      const hSelect = document.getElementById('hudCameraSelect');
      if (hSelect && hSelect.value !== 'ALL') {
        hSelect.value = focusedCameraId;
        if (window.syncHudLayersForCamera) window.syncHudLayersForCamera(focusedCameraId);
      }
    }
    if (typeof updateCameraAlertGlow === 'function') {
      updateCameraAlertGlow(currentAlertsCache);
    }
  }
  if (btnView1x1) {
    btnView1x1.addEventListener('click', () => switchViewMode('focus'));
  }
  if (btnView2x2) {
    btnView2x2.addEventListener('click', () => switchViewMode('grid'));
  }
  if (feedCameraSlot) {
    feedCameraSlot.addEventListener('change', () => {
      const slot = feedCameraSlot.value;
      if (feedCameraId) feedCameraId.value = slot;
      if (feedLocation) {
        feedLocation.value = SLOT_DEFAULT_LOCATIONS[slot] || "Surveillance Post";
      }
    });
  }
  let currentCamSub = 'webcam';
  function switchConnectMainTab(tabKey) {
    if (feedActiveTab) feedActiveTab.value = tabKey;
    if (feedMainTabs && feedMainTabs.length > 0) {
      feedMainTabs.forEach(t => {
        if (t.getAttribute('data-tab') === tabKey) {
          t.classList.add('active');
        } else {
          t.classList.remove('active');
        }
      });
    }
    if (panelSourceUpload) panelSourceUpload.style.display = tabKey === 'upload' ? 'block' : 'none';
    if (panelSourceDemo) panelSourceDemo.style.display = tabKey === 'demo' ? 'block' : 'none';
    if (panelSourceCamera) panelSourceCamera.style.display = tabKey === 'camera' ? 'block' : 'none';
    if (tabKey === 'upload' || tabKey === 'demo') {
      if (feedSourceType) feedSourceType.value = 'demo';
    } else if (tabKey === 'camera') {
      if (feedSourceType) feedSourceType.value = currentCamSub;
    }
    const errBox = document.getElementById('connectCameraErrorBox');
    if (errBox) errBox.style.display = 'none';
  }
  if (feedMainTabs && feedMainTabs.length > 0) {
    feedMainTabs.forEach(tab => {
      tab.addEventListener('click', () => {
        const tabKey = tab.getAttribute('data-tab');
        switchConnectMainTab(tabKey);
      });
    });
  }
  function switchCamSubTab(subKey) {
    currentCamSub = subKey;
    if (feedSourceType && feedActiveTab && feedActiveTab.value === 'camera') {
      feedSourceType.value = subKey;
    }
    if (camSubTabs && camSubTabs.length > 0) {
      camSubTabs.forEach(st => {
        if (st.getAttribute('data-camsub') === subKey) {
          st.classList.add('active');
        } else {
          st.classList.remove('active');
        }
      });
    }
    if (grpWebcamInput) grpWebcamInput.style.display = subKey === 'webcam' ? 'block' : 'none';
    if (grpRtspInput) grpRtspInput.style.display = subKey === 'rtsp' ? 'block' : 'none';
    if (grpHttpInput) grpHttpInput.style.display = subKey === 'http' ? 'block' : 'none';
    const errBox = document.getElementById('connectCameraErrorBox');
    if (errBox) errBox.style.display = 'none';
  }
  if (camSubTabs && camSubTabs.length > 0) {
    camSubTabs.forEach(tab => {
      tab.addEventListener('click', () => {
        const subKey = tab.getAttribute('data-camsub');
        switchCamSubTab(subKey);
      });
    });
  }
  const demoSampleVideoSelect = document.getElementById('demoSampleVideoSelect');
  if (demoSampleVideoSelect) {
    demoSampleVideoSelect.addEventListener('change', () => {
      const locMap = {
        'demo_1': 'North Gate Toll (Highway)',
        'demo_2': 'Sector 18 Chowk (Junction)',
        'demo_3': 'East Gate Checkpost'
      };
      if (feedLocation && locMap[demoSampleVideoSelect.value]) {
        feedLocation.value = locMap[demoSampleVideoSelect.value];
      }
    });
  }
  const demoVideoDropzone = document.getElementById('demoVideoDropzone');
  const feedCustomVideoInput = document.getElementById('feedCustomVideoInput');
  const customVideoSelectedBadge = document.getElementById('customVideoSelectedBadge');
  const customVideoFileName = document.getElementById('customVideoFileName');
  const btnClearCustomVideo = document.getElementById('btnClearCustomVideo');
  if (demoVideoDropzone && feedCustomVideoInput) {
    demoVideoDropzone.addEventListener('click', () => feedCustomVideoInput.click());
    demoVideoDropzone.addEventListener('dragover', e => {
      e.preventDefault();
      demoVideoDropzone.style.borderColor = '#047857';
      demoVideoDropzone.style.background = 'rgba(16, 185, 129, 0.1)';
    });
    demoVideoDropzone.addEventListener('dragleave', () => {
      demoVideoDropzone.style.borderColor = 'rgba(99, 102, 241, 0.45)';
      demoVideoDropzone.style.background = 'rgba(241,245,249,0.45)';
    });
    demoVideoDropzone.addEventListener('drop', e => {
      e.preventDefault();
      demoVideoDropzone.style.borderColor = 'rgba(99, 102, 241, 0.45)';
      demoVideoDropzone.style.background = 'rgba(241,245,249,0.45)';
      if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        feedCustomVideoInput.files = e.dataTransfer.files;
        handleSelectedCustomVideo(e.dataTransfer.files[0]);
      }
    });
    feedCustomVideoInput.addEventListener('change', e => {
      if (e.target.files && e.target.files.length > 0) {
        handleSelectedCustomVideo(e.target.files[0]);
      }
    });
  }
  function handleSelectedCustomVideo(file) {
    if (!file) return;
    const sizeMb = (file.size / (1024 * 1024)).toFixed(1);
    if (customVideoFileName) customVideoFileName.innerText = `${file.name} (${sizeMb} MB)`;
    if (customVideoSelectedBadge) customVideoSelectedBadge.style.display = 'flex';
    const errBox = document.getElementById('connectCameraErrorBox');
    if (errBox) errBox.style.display = 'none';
  }
  if (btnClearCustomVideo && feedCustomVideoInput) {
    btnClearCustomVideo.addEventListener('click', e => {
      e.stopPropagation();
      feedCustomVideoInput.value = '';
      if (customVideoSelectedBadge) customVideoSelectedBadge.style.display = 'none';
    });
  }
  function openConnectModalForCamera(camId) {
    const cid = camId || focusedCameraId || "CAM-01";
    if (feedCameraSlot) feedCameraSlot.value = cid;
    if (feedCameraId) feedCameraId.value = cid;
    if (feedLocation) feedLocation.value = SLOT_DEFAULT_LOCATIONS[cid] || "Surveillance Post";
    const errBox = document.getElementById('connectCameraErrorBox');
    if (errBox) errBox.style.display = 'none';
    const tfErr = document.getElementById('feedTargetFrameError');
    if (tfErr) tfErr.style.display = 'none';
    const tfInput = document.getElementById('feedTargetFrame');
    if (tfInput) {
      tfInput.style.borderColor = 'var(--border-color)';
      tfInput.style.boxShadow = 'none';
      if (!tfInput.value || isNaN(Number(tfInput.value)) || Number(tfInput.value) < 1 || Number(tfInput.value) > 20) {
        tfInput.value = '1';
      }
    }
    if (connectCameraModal) connectCameraModal.style.display = 'flex';
  }
  if (btnOpenConnectModal) {
    btnOpenConnectModal.addEventListener('click', () => {
      openConnectModalForCamera(currentViewMode === 'focus' ? focusedCameraId : 'CAM-01');
    });
  }
  const closeConnectModal = () => {
    if (connectCameraModal) connectCameraModal.style.display = 'none';
    const tfErr = document.getElementById('feedTargetFrameError');
    if (tfErr) tfErr.style.display = 'none';
    const tfInput = document.getElementById('feedTargetFrame');
    if (tfInput) {
      tfInput.style.borderColor = 'var(--border-color)';
      tfInput.style.boxShadow = 'none';
    }
  };
  if (closeConnectModalBtn) closeConnectModalBtn.addEventListener('click', closeConnectModal);
  if (btnCancelConnectModal) btnCancelConnectModal.addEventListener('click', closeConnectModal);
  const feedTargetFrameInput = document.getElementById('feedTargetFrame');
  const feedTargetFrameError = document.getElementById('feedTargetFrameError');
  function validateFeedTargetFrame() {
    const inp = document.getElementById('feedTargetFrame');
    const err = document.getElementById('feedTargetFrameError');
    if (!inp) return true;
    const valStr = inp.value.trim();
    const num = Number(valStr);
    const isValid = valStr !== '' && !isNaN(num) && Number.isInteger(num) && num >= 1 && num <= 20;
    if (!isValid) {
      if (err) err.style.display = 'flex';
      inp.style.borderColor = '#ef4444';
      inp.style.boxShadow = '0 0 0 2px rgba(239, 68, 68, 0.25)';
      return false;
    } else {
      if (err) err.style.display = 'none';
      inp.style.borderColor = 'var(--border-color)';
      inp.style.boxShadow = 'none';
      const eb = document.getElementById('connectCameraErrorBox');
      const em = document.getElementById('connectCameraErrorMsg');
      if (eb && em && em.innerText === "Please select in between 1-20") {
        eb.style.display = 'none';
      }
      return true;
    }
  }
  if (feedTargetFrameInput) {
    feedTargetFrameInput.addEventListener('input', validateFeedTargetFrame);
    feedTargetFrameInput.addEventListener('change', validateFeedTargetFrame);
    feedTargetFrameInput.addEventListener('blur', validateFeedTargetFrame);
  }
  if (connectCameraForm) {
    connectCameraForm.addEventListener('submit', async e => {
      e.preventDefault();
      const activeTab = feedActiveTab ? feedActiveTab.value : 'upload';
      const btnSubmit = document.getElementById('btnSubmitConnect');
      const errBox = document.getElementById('connectCameraErrorBox');
      const errMsg = document.getElementById('connectCameraErrorMsg');
      if (errBox) errBox.style.display = 'none';
      let type = "demo";
      let path = "0";
      let customVideoFile = null;
      if (activeTab === 'upload') {
        type = "demo";
        if (!feedCustomVideoInput || !feedCustomVideoInput.files || !feedCustomVideoInput.files[0]) {
          if (errBox && errMsg) {
            errMsg.innerText = "Please select or drop a local video file (MP4, AVI, MOV, MKV) to upload.";
            errBox.style.display = 'flex';
          } else {
            alert("Please select a video file to upload.");
          }
          return;
        }
        customVideoFile = feedCustomVideoInput.files[0];
        path = "custom";
      } else if (activeTab === 'demo') {
        type = "demo";
        const sel = document.getElementById('demoSampleVideoSelect');
        path = sel && sel.value ? sel.value : "demo_1";
      } else if (activeTab === 'camera') {
        type = currentCamSub;
        if (type === 'webcam') {
          path = feedWebcamIndex ? feedWebcamIndex.value : "0";
        } else if (type === 'rtsp') {
          path = (feedRtspUrl ? feedRtspUrl.value : '').trim();
          if (!path) {
            if (errBox && errMsg) {
              errMsg.innerText = "Please specify an RTSP stream URL (e.g. rtsp://192.168.1.100:554/ch0).";
              errBox.style.display = 'flex';
            } else {
              alert("Please specify an RTSP stream URL.");
            }
            return;
          }
        } else if (type === 'http') {
          path = (feedHttpUrl ? feedHttpUrl.value : '').trim();
          if (!path) {
            if (errBox && errMsg) {
              errMsg.innerText = "Please specify an HTTP / HTTPS stream URL.";
              errBox.style.display = 'flex';
            } else {
              alert("Please specify an HTTP / HTTPS stream URL.");
            }
            return;
          }
        }
      }
      const camId = (feedCameraSlot ? feedCameraSlot.value : feedCameraId ? feedCameraId.value : "CAM-01").trim().toUpperCase() || "CAM-01";
      const loc = feedLocation.value.trim() || SLOT_DEFAULT_LOCATIONS[camId] || "Surveillance Post";
      if (typeof validateFeedTargetFrame === 'function' && !validateFeedTargetFrame()) {
        const tfInp = document.getElementById('feedTargetFrame');
        if (tfInp) tfInp.focus();
        if (errBox && errMsg) {
          errMsg.innerText = "Please select in between 1-20";
          errBox.style.display = 'flex';
        }
        return;
      }
      btnSubmit.disabled = true;
      btnSubmit.innerText = customVideoFile ? "Uploading & Starting Feed..." : "Connecting...";
      try {
        const formData = new FormData();
        formData.append('source_type', type);
        formData.append('source_path', path);
        formData.append('camera_id', camId);
        const selectedCamera = window.karnalCameraRegistry?.getSelectedLiveCamera();
        if (!selectedCamera) throw new Error('Select the actual Karnal camera for this live feed.');
        formData.append('registered_camera_id', selectedCamera.id);
        formData.append('location', selectedCamera.name);
        if (feedGpsCoords && feedGpsCoords.value.trim()) {
          formData.append('gps_coords', feedGpsCoords.value.trim());
        }
        if (customVideoFile) {
          formData.append('custom_video', customVideoFile);
        }
        const feedTargetFrame = document.getElementById('feedTargetFrame');
        if (feedTargetFrame && feedTargetFrame.value) {
          const parsed = parseInt(feedTargetFrame.value, 10);
          if (isNaN(parsed) || parsed < 1 || parsed > 20) {
            const err = document.getElementById('feedTargetFrameError');
            if (err) err.style.display = 'flex';
            feedTargetFrame.focus();
            if (typeof showToast === 'function') showToast('Please select Target Frame between 1-20', 'warning');
            return;
          }
          formData.append('target_frame', String(parsed));
        }
        const res = await fetch('/api/camera/connect', {
          method: 'POST',
          body: formData
        });
        const data = await res.json();
        if (res.ok && data.status === 'success') {
          if (errBox) errBox.style.display = 'none';
          closeConnectModal();
          streamStartTimes[camId] = Date.now();
          cameraActiveStates[camId] = true;
          pollCameraStatuses();
        } else {
          const failDetail = data.detail || "Unable to open camera stream. Please verify IP address, port 554, and network route.";
          if (errBox && errMsg) {
            errMsg.innerText = failDetail;
            errBox.style.display = 'flex';
          } else {
            alert("Failed to connect feed: " + failDetail);
          }
        }
      } catch (err) {
        console.error("Connect error:", err);
        if (errBox && errMsg) {
          errMsg.innerText = "Network Error: " + err.message;
          errBox.style.display = 'flex';
        } else {
          alert("Connection failed: " + err.message);
        }
      } finally {
        btnSubmit.disabled = false;
        btnSubmit.innerText = "Connect & Start Live Feed";
      }
    });
  }
  CAMERA_SLOTS.forEach(cid => {
    const tile = document.getElementById(`tile-${cid}`);
    if (!tile) return;
    tile.addEventListener('dblclick', () => {
      focusedCameraId = cid;
      switchViewMode('focus');
    });
    const btnFocus = tile.querySelector('.btn-tile-focus');
    if (btnFocus) {
      btnFocus.addEventListener('click', e => {
        e.stopPropagation();
        focusedCameraId = cid;
        switchViewMode('focus');
      });
    }
    const btnConn = tile.querySelector('.btn-tile-connect');
    if (btnConn) {
      btnConn.addEventListener('click', e => {
        e.stopPropagation();
        openConnectModalForCamera(cid);
      });
    }
    const btnQuickConn = tile.querySelector('.btn-tile-quick-connect');
    if (btnQuickConn) {
      btnQuickConn.addEventListener('click', e => {
        e.stopPropagation();
        openConnectModalForCamera(cid);
      });
    }
    const btnDisc = tile.querySelector('.btn-tile-disconnect');
    if (btnDisc) {
      btnDisc.addEventListener('click', async e => {
        e.stopPropagation();
        try {
          const fd = new FormData();
          fd.append('camera_id', cid);
          await fetch('/api/camera/disconnect', {
            method: 'POST',
            body: fd
          });
          cameraActiveStates[cid] = false;
          pollCameraStatuses();
        } catch (err) {
          console.error("Disconnect error:", err);
        }
      });
    }
    const btnTilePause = tile.querySelector('.btn-tile-pause');
    if (btnTilePause) {
      btnTilePause.addEventListener('click', async e => {
        e.stopPropagation();
        try {
          const fd = new FormData();
          fd.append('camera_id', cid);
          await fetch('/api/camera/toggle_pause', {
            method: 'POST',
            body: fd
          });
          pollCameraStatuses();
        } catch (err) {
          console.error("Toggle pause error:", err);
        }
      });
    }
    const toggleAnpr = document.getElementById(`tileToggleAnpr-${cid}`);
    if (toggleAnpr) {
      toggleAnpr.addEventListener('change', async e => {
        e.stopPropagation();
        const isEnabled = toggleAnpr.checked;
        try {
          const fd = new FormData();
          fd.append('camera_id', cid);
          fd.append('enabled', isEnabled);
          const res = await fetch('/api/camera/toggle_anpr', {
            method: 'POST',
            body: fd
          });
          const d = await res.json();
          const lbl = document.getElementById(`tileAnprLbl-${cid}`);
          if (lbl) {
            lbl.innerText = d.anpr_enabled ? "ANPR: ON" : "ANPR: OFF";
            lbl.style.color = d.anpr_enabled ? "#10b981" : "#52647c";
          }
        } catch (err) {
          console.error("Toggle ANPR error:", err);
        }
      });
    }
  });
  function updateSingleFocusView() {
    CAMERA_SLOTS.forEach(slot => {
      const pill = document.getElementById(`mobPill-${slot}`);
      if (pill) {
        if (slot === focusedCameraId) pill.classList.add('active'); else pill.classList.remove('active');
      }
    });
    fetch(`/api/camera/status?camera_id=${focusedCameraId}`).then(r => r.json()).then(d => {
      const cam = d.camera;
      if (cam && cam.is_running) {
        if (!liveFeedImg.src || liveFeedImg.style.display === 'none' || !liveFeedImg.src.includes(focusedCameraId)) {
          liveFeedImg.src = `/api/camera/stream/${focusedCameraId}?t=${streamStartTimes[focusedCameraId] || Date.now()}`;
        }
        liveFeedImg.style.display = 'block';
        screenCenterMsg.style.display = 'none';
        btnOpenConnectModal.style.display = 'none';
        btnDisconnectStream.style.display = 'inline-flex';
        const btnTogglePauseStream = document.getElementById('btnTogglePauseStream');
        const lblTogglePauseStream = document.getElementById('lblTogglePauseStream');
        const svgPauseIcon = document.getElementById('svgPauseIcon');
        if (btnTogglePauseStream) {
          btnTogglePauseStream.style.display = 'inline-flex';
          if (cam.is_paused) {
            if (lblTogglePauseStream) lblTogglePauseStream.innerText = "Resume Feed";
            if (svgPauseIcon) svgPauseIcon.innerHTML = `<polygon points="5 3 19 12 5 21 5 3"/>`;
            btnTogglePauseStream.style.background = 'rgba(16, 185, 129, 0.2)';
            btnTogglePauseStream.style.borderColor = 'rgba(16, 185, 129, 0.5)';
            btnTogglePauseStream.style.color = '#047857';
            camBadgeText.innerText = `${focusedCameraId} [PAUSED]`;
            camBadgeDot.style.background = '#f59e0b';
            const osdRecTag = document.getElementById('osdRecTag');
            if (osdRecTag) osdRecTag.innerHTML = `PAUSED &#10074;&#10074;`;
          } else {
            if (lblTogglePauseStream) lblTogglePauseStream.innerText = "Pause Feed";
            if (svgPauseIcon) svgPauseIcon.innerHTML = `<rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/>`;
            btnTogglePauseStream.style.background = 'rgba(245, 158, 11, 0.2)';
            btnTogglePauseStream.borderColor = 'rgba(245, 158, 11, 0.5)';
            btnTogglePauseStream.style.color = '#fbbf24';
            camBadgeText.innerText = `${focusedCameraId} [LIVE]`;
            camBadgeDot.style.background = '#10b981';
            const osdRecTag = document.getElementById('osdRecTag');
            if (osdRecTag) osdRecTag.innerHTML = `REC &#9679;`;
          }
        }
        if (cam.connection_status === 'RECONNECTING') {
          camBadgeText.innerText = `${focusedCameraId} [RECONNECTING ${cam.reconnect_attempt || 1}]`;
          camBadgeDot.style.background = '#f97316';
          camStatusPill.innerText = `⚠️ CCTV Auto-Healing (Attempt ${cam.reconnect_attempt || 1})...`;
          camStatusPill.style.color = '#f97316';
        } else {
          camStatusPill.innerText = `● Stream Active: ${cam.source_type.toUpperCase()} (${focusedCameraId})`;
          camStatusPill.style.color = cam.is_paused ? '#f59e0b' : '#10b981';
        }
        osdLocationText.innerText = `${focusedCameraId}: ${cam.location.toUpperCase()}`;
        osdResText.innerText = cam.resolution || "1080P WDR";
        osdFpsText.innerText = `FPS: ${cam.fps}`;
      } else {
        liveFeedImg.src = '';
        liveFeedImg.style.display = 'none';
        screenCenterMsg.style.display = 'flex';
        btnOpenConnectModal.style.display = 'none';
        btnDisconnectStream.style.display = 'none';
        const btnTogglePauseStream = document.getElementById('btnTogglePauseStream');
        if (btnTogglePauseStream) btnTogglePauseStream.style.display = 'none';
        camBadgeText.innerText = `${focusedCameraId} [STANDBY]`;
        camBadgeDot.style.background = '#64748b';
        camStatusPill.innerText = `● Camera Engine Standby (${focusedCameraId})`;
        camStatusPill.style.color = 'var(--text-muted)';
        osdFpsText.innerText = `FPS: 0.0`;
        osdLocationText.innerText = `${focusedCameraId}: ${(SLOT_DEFAULT_LOCATIONS[focusedCameraId] || 'STANDBY').toUpperCase()}`;
      }
    }).catch(() => {});
  }
  window.selectFocusedCamera = function (cid) {
    focusedCameraId = cid;
    const hSelect = document.getElementById('hudCameraSelect');
    if (hSelect && hSelect.value !== 'ALL') {
      hSelect.value = cid;
      if (window.syncHudLayersForCamera) window.syncHudLayersForCamera(cid);
    }
    CAMERA_SLOTS.forEach(slot => {
      const pill = document.getElementById(`mobPill-${slot}`);
      if (pill) {
        if (slot === cid) pill.classList.add('active'); else pill.classList.remove('active');
      }
    });
    updateSingleFocusView();
  };
  window.switchMobileActivity = function (tab) {
    const btnV = document.getElementById('tabMobileVehicles');
    {
      null;
      document.body.classList.add('mobile-show-vehicles');
      if (btnV) btnV.classList.add('active');
      if (btnF) btnF.classList.remove('active');
    }
  };
  let isPollingCameraStatuses = false;
  async function pollCameraStatuses() {
    if (isPollingCameraStatuses) return;
    isPollingCameraStatuses = true;
    try {
      const res = await fetch('/api/camera/status');
      const data = await res.json();
      if (!data || !data.cameras) return;
      const cams = data.cameras;
      const activeCount = data.active_count || 0;
      if (activeCamCounter) {
        activeCamCounter.innerText = `${activeCount}/4 LIVE`;
        activeCamCounter.style.color = activeCount > 0 ? '#10b981' : '#52647c';
        activeCamCounter.style.borderColor = activeCount > 0 ? 'rgba(16, 185, 129, 0.4)' : 'var(--border-color)';
      }
      if (liveRecDot) {
        if (activeCount > 0) {
          liveRecDot.style.background = '#ef4444';
          liveRecDot.style.boxShadow = '0 0 8px #ef4444';
        } else {
          liveRecDot.style.background = '#64748b';
          liveRecDot.style.boxShadow = 'none';
        }
      }
      const btnTogglePauseStream = document.getElementById('btnTogglePauseStream');
      const lblTogglePauseStream = document.getElementById('lblTogglePauseStream');
      const svgPauseIcon = document.getElementById('svgPauseIcon');
      if (btnTogglePauseStream && currentViewMode !== 'focus') {
        if (activeCount > 0) {
          btnTogglePauseStream.style.display = 'inline-flex';
          const activeCams = Object.values(cams).filter(c => c.is_running);
          const allPaused = activeCams.length > 0 && activeCams.every(c => c.is_paused);
          if (allPaused) {
            if (lblTogglePauseStream) lblTogglePauseStream.innerText = "Resume Feeds";
            if (svgPauseIcon) svgPauseIcon.innerHTML = `<polygon points="5 3 19 12 5 21 5 3"/>`;
            btnTogglePauseStream.style.background = 'rgba(16, 185, 129, 0.2)';
            btnTogglePauseStream.style.borderColor = 'rgba(16, 185, 129, 0.5)';
            btnTogglePauseStream.style.color = '#047857';
          } else {
            if (lblTogglePauseStream) lblTogglePauseStream.innerText = "Pause Feeds";
            if (svgPauseIcon) svgPauseIcon.innerHTML = `<rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/>`;
            btnTogglePauseStream.style.background = 'rgba(245, 158, 11, 0.2)';
            btnTogglePauseStream.style.borderColor = 'rgba(245, 158, 11, 0.5)';
            btnTogglePauseStream.style.color = '#fbbf24';
          }
        } else {
          btnTogglePauseStream.style.display = 'none';
        }
      }
      CAMERA_SLOTS.forEach(cid => {
        const cam = cams[cid];
        const tile = document.getElementById(`tile-${cid}`);
        const feedImg = document.getElementById(`tileFeedImg-${cid}`);
        const standby = document.getElementById(`tileStandby-${cid}`);
        const recDot = document.getElementById(`tileRecDot-${cid}`);
        const badge = document.getElementById(`tileBadge-${cid}`);
        const loc = document.getElementById(`tileLoc-${cid}`);
        const fps = document.getElementById(`tileFps-${cid}`);
        const btnConn = tile ? tile.querySelector('.btn-tile-connect') : null;
        const btnDisc = tile ? tile.querySelector('.btn-tile-disconnect') : null;
        const btnPause = tile ? tile.querySelector('.btn-tile-pause') : null;
        const toggle = document.getElementById(`tileToggleAnpr-${cid}`);
        const anprLbl = document.getElementById(`tileAnprLbl-${cid}`);
        if (cam && cam.is_running) {
          if (tile) tile.classList.add('is-active');
          if (loc) loc.innerText = cam.location;
          if (fps) fps.innerText = `${cam.fps} FPS`;
          if (btnConn) btnConn.style.display = 'none';
          if (btnDisc) btnDisc.style.display = 'inline-flex';
          if (btnPause) {
            btnPause.style.display = 'inline-flex';
            if (cam.is_paused) {
              btnPause.title = "Resume Feed (Playback)";
              btnPause.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>`;
              btnPause.style.color = '#10b981';
            } else {
              btnPause.title = "Pause Feed (Freeze for Inspection)";
              btnPause.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>`;
              btnPause.style.color = '#fbbf24';
            }
          }
          if (cam.is_paused) {
            if (badge) {
              badge.innerText = "PAUSED";
              badge.classList.remove('live');
              badge.classList.add('paused');
              badge.style.background = 'rgba(245, 158, 11, 0.2)';
              badge.style.color = '#fbbf24';
              badge.style.borderColor = 'rgba(245, 158, 11, 0.5)';
            }
            if (recDot) {
              recDot.classList.add('active');
              recDot.style.background = '#f59e0b';
              recDot.style.boxShadow = '0 0 6px #f59e0b';
            }
          } else {
            if (badge) {
              badge.innerText = "LIVE";
              badge.classList.remove('paused');
              badge.classList.add('live');
              badge.style.background = '';
              badge.style.color = '';
              badge.style.borderColor = '';
            }
            if (recDot) {
              recDot.classList.add('active');
              recDot.style.background = '';
              recDot.style.boxShadow = '';
            }
          }
          if (toggle) toggle.checked = cam.anpr_enabled;
          if (anprLbl) {
            anprLbl.innerText = cam.anpr_enabled ? "ANPR: ON" : "ANPR: OFF";
            anprLbl.style.color = cam.anpr_enabled ? "#10b981" : "#52647c";
          }
          if (feedImg && standby) {
            if (currentViewMode === 'grid') {
              if (!streamStartTimes[cid]) streamStartTimes[cid] = Date.now();
              if (!feedImg.src || feedImg.style.display === 'none' || feedImg.src === window.location.href || !feedImg.src.includes(cid)) {
                feedImg.src = `/api/camera/stream/${cid}?t=${streamStartTimes[cid]}`;
              }
              feedImg.style.display = 'block';
              standby.style.display = 'none';
            } else {
              if (feedImg.src && feedImg.src !== '') {
                feedImg.src = '';
              }
            }
          }
        } else {
          if (tile) tile.classList.remove('is-active');
          if (recDot) {
            recDot.classList.remove('active');
            recDot.style.background = '';
            recDot.style.boxShadow = '';
          }
          if (badge) {
            badge.innerText = "STANDBY";
            badge.classList.remove('live', 'paused');
            badge.style.background = '';
            badge.style.color = '';
            badge.style.borderColor = '';
          }
          if (fps) fps.innerText = `0.0 FPS`;
          if (btnPause) btnPause.style.display = 'none';
          if (btnConn) btnConn.style.display = 'inline-flex';
          if (btnDisc) btnDisc.style.display = 'none';
          if (feedImg && standby) {
            feedImg.src = '';
            feedImg.style.display = 'none';
            standby.style.display = 'flex';
          }
          delete streamStartTimes[cid];
        }
      });
      if (currentViewMode === 'focus') {
        updateSingleFocusView();
      }
      const activeCam = typeof getSelectedHudCamera === 'function' ? getSelectedHudCamera() : 'CAM-01';
      const camData = cams[activeCam] || cams['CAM-01'];
      if (camData && camData.target_frame) {
        const mainSel = document.getElementById('mainHeaderTargetFrame');
        if (mainSel && document.activeElement !== mainSel) {
          mainSel.value = String(camData.target_frame);
        }
        const hudSel = document.getElementById('hudTargetFrame');
        if (hudSel && document.activeElement !== hudSel) {
          hudSel.value = String(camData.target_frame);
        }
      }
      const hasAnprLive = Object.values(cams).some(c => c.is_running && (c.anpr_enabled || null));
      if (hasAnprLive) {
        if (typeof fetchAndRenderUnifiedLiveFeed === 'function') {
          try {
            fetchAndRenderUnifiedLiveFeed();
          } catch (_) {}
        }
        const viewVehicles = document.getElementById('viewCapturedVehicles');
        if (viewVehicles && viewVehicles.style.display !== 'none' && typeof fetchAndRenderDrawerVehicles === 'function') {
          try {
            fetchAndRenderDrawerVehicles();
          } catch (_) {}
        }
        if (viewVehicles && viewVehicles.style.display !== 'none') {
          fetchAndRenderCapturedDb();
        }
      }
    } catch (err) {
      console.warn("Status poll error:", err);
    } finally {
      isPollingCameraStatuses = false;
    }
  }
  if (btnDisconnectStream) {
    btnDisconnectStream.addEventListener('click', async () => {
      try {
        const fd = new FormData();
        fd.append('camera_id', focusedCameraId);
        await fetch('/api/camera/disconnect', {
          method: 'POST',
          body: fd
        });
        cameraActiveStates[focusedCameraId] = false;
        pollCameraStatuses();
      } catch (e) {
        console.error("Disconnect error:", e);
      }
    });
  }
  if (btnTogglePauseStream) {
    btnTogglePauseStream.addEventListener('click', async () => {
      try {
        const targetCid = currentViewMode === 'focus' ? focusedCameraId : 'ALL';
        const fd = new FormData();
        fd.append('camera_id', targetCid);
        await fetch('/api/camera/toggle_pause', {
          method: 'POST',
          body: fd
        });
        pollCameraStatuses();
      } catch (e) {
        console.error("Toggle pause error:", e);
      }
    });
  }
  if (btnStreamFullscreen && surveillanceScreen) {
    btnStreamFullscreen.addEventListener('click', () => {
      if (!document.fullscreenElement) {
        surveillanceScreen.requestFullscreen().catch(err => {
          console.error("Fullscreen error:", err);
        });
      } else {
        document.exitFullscreen();
      }
    });
  }
  const selVehicleModel = document.getElementById('selVehicleModel');
  const selPlateModel = document.getElementById('selPlateModel');
  const selOcrModel = document.getElementById('selOcrModel');
  const selPersonModel = document.getElementById('selPersonModel');
  const modelStatusPill = document.getElementById('modelStatusPill');
  const modelStatusText = document.getElementById('modelStatusText');
  let cachedVehicleCatalog = {};
  const MODEL_SPECS = {
    paddleocr_v4_server: {
      name: "PP-OCRv4 Server (SOTA)",
      origin: "⚡ Baidu PaddlePaddle",
      size: "88.1 MB",
      fps: "45 FPS",
      latency: "22 ms",
      accuracy: "98.9% CTC",
      desc: "Highest accuracy recognition model under 100MB, fine-tuned for high-speed multi-character Indian plates."
    },
    awiros_anpr: {
      name: "Awiros ANPR Edge Engine",
      origin: "🇮🇳 Indian Standard",
      size: "22.4 MB",
      fps: "55 FPS",
      latency: "18 ms",
      accuracy: "96.4% Accuracy",
      desc: "Specialized OCR tuned for Indian high-security registration plates (HSRP) and diverse fonts."
    },
    uvh26_yolo11x: {
      name: "IISc UVH-26 (YOLOv11x)",
      origin: "🇮🇳 IISc Bangalore",
      size: "326.6 MB",
      fps: "14 FPS",
      latency: "71 ms",
      accuracy: "89.4% mAP",
      desc: "14 Indian vehicle classes: Auto, Tempo, Truck, Bus, etc. High accuracy benchmark."
    },
    driveindia_tihan_yolov10x: {
      name: "DriveIndia TiHAN 10x",
      origin: "🇮🇳 TiHAN Hyderabad",
      size: "122.3 MB",
      fps: "22 FPS",
      latency: "45 ms",
      accuracy: "91.8% mAP",
      desc: "Dual Vehicle + Pedestrian Indian benchmark with single-pass detection."
    },
    driveindia_tihan_yolov10m: {
      name: "DriveIndia TiHAN 10m",
      origin: "🇮🇳 TiHAN Hyderabad",
      size: "63.8 MB",
      fps: "36 FPS",
      latency: "28 ms",
      accuracy: "87.6% mAP",
      desc: "Balanced edge latency for Indian traffic and pedestrians."
    },
    yolo11n: {
      name: "YOLO11n Nano Baseline",
      origin: "🌐 Global Baseline",
      size: "5.6 MB",
      fps: "68 FPS",
      latency: "14 ms",
      accuracy: "78.2% mAP",
      desc: "Ultra-fast low-latency detector for edge devices and high-FPS streams."
    },
    yolo11l_cctv_ft: {
      name: "YOLO11l CCTV FT (Vehicle/Rider)",
      origin: "🇮🇳 AP-RTGS CCTV",
      size: "48.9 MB",
      fps: "28 FPS",
      latency: "36 ms",
      accuracy: "97.9% mAP@50",
      desc: "Fine-tuned on Indian CCTV traffic footage for motorcycle & rider/pedestrian surveillance."
    },
    rtdetrv2_x: {
      name: "RT-DETRv2-X Transformer",
      origin: "🇮🇳 SOTA Transformer",
      size: "129.5 MB",
      fps: "20 FPS",
      latency: "50 ms",
      accuracy: "94.2% mAP",
      desc: "Heavy real-time transformer for multi-scale vehicles & pedestrians."
    },
    rtdetrv2_x_plate: {
      name: "RT-DETRv2-X Transformer",
      origin: "🇮🇳 SOTA Transformer",
      size: "129.5 MB",
      fps: "20 FPS",
      latency: "50 ms",
      accuracy: "94.2% mAP",
      desc: "Heavy real-time transformer for multi-scale vehicles & pedestrians."
    },
    plate_yolo_l: {
      name: "YOLO11l Plate (CCTV Large)",
      origin: "🇮🇳 CCTV & Traffic",
      size: "48.8 MB",
      fps: "28 FPS",
      latency: "36 ms",
      accuracy: "94.6% mAP",
      desc: "25.3M parameter YOLO11l Large plate detector fine-tuned for Indian traffic & CCTV feeds."
    },
    tanish_yolo11s_plate: {
      name: "YOLO11s (TanishDevX)",
      origin: "🇮🇳 TanishDevX ALPR",
      size: "18.3 MB",
      fps: "46 FPS",
      latency: "22 ms",
      accuracy: "95.3% mAP@50",
      desc: "Production-grade YOLOv11s plate detector fine-tuned in 2 stages with 96.86% precision."
    },
    plate_yolo_ft: {
      name: "YOLO11l Night/CCTV FT",
      origin: "🇮🇳 CCTV & Night",
      size: "38.7 MB",
      fps: "30 FPS",
      latency: "33 ms",
      accuracy: "93.4% mAP",
      desc: "20.1M parameter CCTV fine-tuned model for low-light, night glare & highway plates."
    },
    subash_indian_plate: {
      name: "Indian LPR Combo",
      origin: "🇮🇳 subash9940 ALPR",
      size: "5.9 MB",
      fps: "64 FPS",
      latency: "16 ms",
      accuracy: "91.2% mAP",
      desc: "Lightweight 3.01M param Indian number plate detector with TrOCR and voting pipeline."
    },
    indian_lpr_combo: {
      name: "Indian_LPR Combo",
      origin: "🇮🇳 Indian Traffic",
      size: "34.7 MB",
      fps: "32 FPS",
      latency: "31 ms",
      accuracy: "92.5% mAP",
      desc: "Polygon segmentation for tilted, rickshaw, and two-wheeler plates."
    },
    yolov8_plate: {
      name: "YOLOv8 Plate Detector",
      origin: "⚡ Ultralytics v8",
      size: "6.0 MB",
      fps: "64 FPS",
      latency: "16 ms",
      accuracy: "92.8% mAP",
      desc: "Ultralytics YOLOv8 license plate detector for high-speed edge surveillance."
    },
    yolo11s_plate: {
      name: "YOLO11s Indian Diverse",
      origin: "🇮🇳 High Recall",
      size: "18.3 MB",
      fps: "48 FPS",
      latency: "21 ms",
      accuracy: "89.1% mAP",
      desc: "High recall across Indian font variations and multi-line number plates."
    },
    yolo11m_pose: {
      name: "YOLO11m-Pose Top-Down",
      origin: "🏆 Ultralytics 3D HUD",
      size: "42.5 MB",
      fps: "32 FPS",
      latency: "31 ms",
      accuracy: "98.2% Pose SOTA"
    }
  };
  window.toggleCustomDropdown = function (ddId) {
    const el = document.getElementById(ddId);
    if (!el) return;
    const wasOpen = el.classList.contains('open');
    window.hideModelSpecsTooltip();
    document.querySelectorAll('.custom-model-dd').forEach(d => d.classList.remove('open'));
    if (!wasOpen) {
      if (ddId === 'customDdPerson' && selPersonModel && selPersonModel.disabled) {
        window.handlePersonContainerClick();
        return;
      }
      el.classList.add('open');
    }
  };
  window.selectCustomModel = function (category, modelId) {
    let targetSelect = null;
    if (category === 'vehicle') targetSelect = selVehicleModel; else if (category === 'plate') targetSelect = selPlateModel; else if (category === 'ocr') targetSelect = selOcrModel; else if (category === 'person') targetSelect = selPersonModel;
    if (targetSelect) {
      targetSelect.value = modelId;
    }
    document.querySelectorAll('.custom-model-dd').forEach(d => d.classList.remove('open'));
    window.hideModelSpecsTooltip();
    if (typeof window.handleModelSelectionChange === 'function') {
      window.handleModelSelectionChange();
    }
    syncCustomDropdownUI();
  };
  window.showModelSpecsTooltip = function (event, modelId) {
    const card = document.getElementById('modelSpecsTooltipCard');
    const spec = MODEL_SPECS[modelId];
    if (!card || !spec) return;
    const parentDd = event.currentTarget.closest('.custom-model-dd');
    if (!parentDd || !parentDd.classList.contains('open')) return;
    const nameEl = document.getElementById('cardSpecName');
    const originEl = document.getElementById('cardSpecOrigin');
    const descEl = document.getElementById('cardSpecDesc');
    const sizeEl = document.getElementById('cardSpecSize');
    const fpsEl = document.getElementById('cardSpecFps');
    const accEl = document.getElementById('cardSpecAccuracy');
    const latEl = document.getElementById('cardSpecLatency');
    if (nameEl) nameEl.textContent = spec.name;
    if (originEl) originEl.textContent = spec.origin;
    if (descEl) descEl.textContent = spec.desc;
    if (sizeEl) sizeEl.textContent = spec.size;
    if (fpsEl) fpsEl.textContent = spec.fps;
    if (accEl) accEl.textContent = spec.accuracy;
    if (latEl) latEl.textContent = spec.latency;
    const rect = event.currentTarget.getBoundingClientRect();
    let left = rect.right + 10;
    let top = rect.top - 6;
    if (left + 300 > window.innerWidth) {
      left = rect.left - 296;
    }
    if (top + 220 > window.innerHeight) {
      top = window.innerHeight - 230;
    }
    if (top < 10) top = 10;
    card.style.left = left + 'px';
    card.style.top = top + 'px';
    card.classList.add('visible');
  };
  window.hideModelSpecsTooltip = function () {
    const card = document.getElementById('modelSpecsTooltipCard');
    if (card) {
      card.classList.remove('visible');
    }
  };
  document.addEventListener('click', e => {
    if (!e.target.closest('.custom-model-dd')) {
      document.querySelectorAll('.custom-model-dd').forEach(d => d.classList.remove('open'));
      window.hideModelSpecsTooltip();
    }
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      document.querySelectorAll('.custom-model-dd').forEach(d => d.classList.remove('open'));
      window.hideModelSpecsTooltip();
    }
  });
  function syncCustomDropdownUI() {
    const updateDropdownLabel = (selEl, labelElId, ddId, categoryTitle) => {
      const labelEl = document.getElementById(labelElId);
      const ddEl = document.getElementById(ddId);
      if (!selEl || !labelEl || !ddEl) return;
      const val = selEl.value;
      labelEl.textContent = selEl.selectedOptions[0]?.textContent || categoryTitle;
      selEl.disabled = true;
      const button = ddEl.querySelector('.custom-model-dd-btn');
      if (button) {
        button.disabled = true;
        button.title = 'Preselected model for Live and Upload';
        button.style.maxWidth = 'none';
      }
      ddEl.querySelectorAll('.custom-model-dd-item').forEach(item => {
        if (item.getAttribute('data-id') === val) {
          item.classList.add('selected');
        } else {
          item.classList.remove('selected');
        }
      });
    };
    updateDropdownLabel(selVehicleModel, 'labelVehicleModel', 'customDdVehicle', 'Vehicle Detector');
    updateDropdownLabel(selPlateModel, 'labelPlateModel', 'customDdPlate', 'Plate Detector');
    updateDropdownLabel(selOcrModel, 'labelOcrModel', 'customDdOcr', 'OCR Engine');
    null;
    null;
    const btnPerson = document.getElementById('btnPersonModel');
    const labelPerson = document.getElementById('labelPersonModel');
    const ddPerson = document.getElementById('customDdPerson');
    if (selPersonModel && btnPerson && labelPerson && ddPerson) {
      if (selPersonModel.disabled) {
        btnPerson.classList.add('disabled');
        labelPerson.textContent = 'Person (Shared)';
        btnPerson.title = "Vehicle model detects both Vehicle & Person in a single pass.";
      } else {
        btnPerson.classList.remove('disabled');
        labelPerson.textContent = 'Person Detector';
        btnPerson.title = "Select dedicated person detection model";
      }
      ddPerson.querySelectorAll('.custom-model-dd-item').forEach(item => {
        if (item.getAttribute('data-id') === selPersonModel.value) {
          item.classList.add('selected');
        } else {
          item.classList.remove('selected');
        }
      });
    }
    const liveVal = document.getElementById('liveEngineLatencyVal');
    if (liveVal) {
      const vLat = parseInt(MODEL_SPECS[selVehicleModel?.value]?.latency || "30", 10);
      const pLat = parseInt(MODEL_SPECS[selPlateModel?.value]?.latency || "25", 10);
      const fLat = parseInt(MODEL_SPECS[null]?.latency || "20", 10);
      const total = Math.round((vLat * 0.4 + pLat * 0.35 + fLat * 0.25) * 10) / 10;
      liveVal.textContent = (total || 41.8).toFixed(1) + ' ms';
    }
  }
  function syncPersonModelWithVehicle(targetVehId) {
    if (!selPersonModel) return;
    const badge = document.getElementById('personModelLockBadge');
    const vehMeta = cachedVehicleCatalog[targetVehId];
    const supportsPerson = vehMeta ? vehMeta.supports_person !== false : targetVehId !== 'uvh26_yolo11x';
    if (supportsPerson) {
      selPersonModel.value = targetVehId;
      selPersonModel.disabled = true;
      selPersonModel.style.opacity = '0.6';
      selPersonModel.style.cursor = 'not-allowed';
      selPersonModel.title = "Vehicle model detects both Vehicle & Person in a single pass. Person detector locked to prevent redundant GPU load.";
      if (badge) {
        badge.style.display = 'inline-flex';
        badge.style.background = 'rgba(99, 102, 241, 0.25)';
        badge.style.border = '1px solid rgba(99, 102, 241, 0.5)';
        badge.style.color = '#4338ca';
        badge.innerHTML = '🔒 Shared with Vehicle';
        badge.title = 'Vehicle model detects both Vehicle & Person in a single pass. Person detector locked to prevent redundant GPU load.';
      }
    } else {
      selPersonModel.disabled = false;
      selPersonModel.style.opacity = '1.0';
      selPersonModel.style.cursor = 'pointer';
      selPersonModel.title = "Select dedicated person detection model";
      if (badge) {
        badge.style.display = 'inline-flex';
        badge.style.background = 'rgba(16, 185, 129, 0.2)';
        badge.style.border = '1px solid rgba(16, 185, 129, 0.5)';
        badge.style.color = '#6ee7b7';
        badge.innerHTML = '🔓 Dedicated Person AI Active';
        badge.title = 'Active vehicle model only detects vehicles. You can choose any dedicated person detector.';
      }
      if (selPersonModel.value === targetVehId || cachedVehicleCatalog[selPersonModel.value] && cachedVehicleCatalog[selPersonModel.value].supports_person === false) {
        selPersonModel.value = 'driveindia_tihan_yolov10x';
      }
    }
  }
  window.handlePersonContainerClick = function (event) {
    if (selPersonModel && selPersonModel.disabled) {
      const vehName = cachedVehicleCatalog[selVehicleModel?.value]?.name || (selVehicleModel?.value || 'Active vehicle model').toUpperCase();
      if (typeof showToastAlert === 'function') {
        showToastAlert(`Selected Vehicle model (${vehName}) can already detect persons! Single-pass shared inference is active for maximum efficiency.`, "info", "Shared AI Pipeline");
      }
    }
  };
  window.currentModelTarget = 'live';
  window.switchModelTarget = function (target) {
    window.currentModelTarget = target === 'upload' ? 'upload' : 'live';
    const btnLive = document.getElementById('btnTargetLive');
    const btnUpload = document.getElementById('btnTargetUpload');
    if (window.currentModelTarget === 'upload') {
      btnLive?.classList.remove('active');
      btnUpload?.classList.add('active');
    } else {
      btnUpload?.classList.remove('active');
      btnLive?.classList.add('active');
    }
    loadModelCatalog(window.currentModelTarget);
  };
  window.revertModelDefaults = async function () {
    try {
      const fd = new FormData();
      fd.append('target', 'all');
      const res = await fetch('/api/models/revert', {
        method: 'POST',
        body: fd
      });
      const data = await res.json();
      if (res.ok) {
        await loadModelCatalog(window.currentModelTarget || 'live');
      } else {
        if (typeof showToastAlert === 'function') {
          showToastAlert("Failed to revert: " + (data.detail || "Error"), "error", "Revert Failed");
        }
      }
    } catch (e) {
      console.error("Error reverting models:", e);
    }
  };
  async function loadModelCatalog(target = window.currentModelTarget || 'live') {
    try {
      const res = await fetch(`/api/models/catalog?target=${target}`);
      if (!res.ok) return;
      const data = await res.json();
      if (data.vehicle_models) {
        data.vehicle_models.forEach(vm => {
          cachedVehicleCatalog[vm.id] = vm;
        });
      }
      function ensureOptions(selectEl, modelList, isPersonSelect = false) {
        if (!selectEl || !modelList) return;
        const existingValues = new Set(Array.from(selectEl.options).map(o => o.value));
        modelList.forEach(m => {
          if (!existingValues.has(m.id)) {
            const opt = document.createElement('option');
            opt.value = m.id;
            let label = m.name + (m.downloaded ? ' ✅' : ' ⬇️');
            if (isPersonSelect && m.supports_person === false) {
              opt.disabled = true;
              label = m.name + ' (Vehicle Only - No Person)';
            }
            opt.textContent = label;
            selectEl.appendChild(opt);
          } else if (isPersonSelect && m.supports_person === false) {
            const opt = Array.from(selectEl.options).find(o => o.value === m.id);
            if (opt) {
              opt.disabled = true;
              if (!opt.textContent.includes('Vehicle Only')) {
                opt.textContent += ' (Vehicle Only)';
              }
            }
          }
        });
      }
      ensureOptions(selVehicleModel, data.vehicle_models);
      ensureOptions(selPlateModel, data.plate_models);
      ensureOptions(selOcrModel, data.ocr_models);
      ensureOptions(selPersonModel, data.person_models, true);
      null;
      null;
      if (selVehicleModel && data.active_vehicle) {
        selVehicleModel.value = data.active_vehicle;
      }
      if (selPlateModel && data.active_plate) {
        selPlateModel.value = data.active_plate;
      }
      if (selOcrModel && data.active_ocr) {
        selOcrModel.value = data.active_ocr;
      }
      if (selPersonModel && data.active_person) {
        selPersonModel.value = data.active_person;
      }
      syncPersonModelWithVehicle(data.active_vehicle);
      updateModelStatusBadge(data.active_vehicle, data.active_plate, data.active_ocr, data.active_person, null, null, data.active_vehicle_supports_person, target);
      syncCustomDropdownUI();
    } catch (err) {
      console.error("Error loading model catalog:", err);
    }
  }
  function updateModelStatusBadge(veh, plt, ocr, per, unusedDetector, unusedEmbedder, vehSupportsPerson, target = window.currentModelTarget || 'live') {
    const summary = `${String(target).toUpperCase()} ANPR: ${veh || 'Vehicle'} + ${plt || 'Plate'} [OCR: ${ocr || 'PaddleOCR'}]`;
    const el = document.getElementById('liveModelStatusBadge');
    if (el) el.textContent = summary;
    if (modelStatusText) modelStatusText.textContent = summary;
    window.activePipelineModels = {
      vehicle: veh,
      plate: plt,
      ocr,
      person: per,
      summary
    };
  }
  window.handleModelSelectionChange = async function () {
    // Model selection is fixed for both scopes until model switching is enabled.
    if (selVehicleModel) selVehicleModel.value = 'uvh26_yolo11x';
    if (selPlateModel) selPlateModel.value = 'plate_yolo_l';
    if (selOcrModel) selOcrModel.value = 'awiros_anpr';
    if (selPersonModel) selPersonModel.value = 'uvh26_yolo11x';
    syncCustomDropdownUI();
    return;
  };
  window.applyQuickPipelinePreset = function (presetType) {
    if (presetType === 'fast' || presetType === 'sota') {
      if (selVehicleModel) selVehicleModel.value = 'uvh26_yolo11x';
      if (selPlateModel) selPlateModel.value = 'plate_yolo_l';
      if (selOcrModel) selOcrModel.value = 'awiros_anpr';
      if (selPersonModel) selPersonModel.value = 'uvh26_yolo11x';
    }
    return window.handleModelSelectionChange();
  };
  loadModelCatalog();
  let currentLiveInspectTarget = null;
  function showClickRipple(clientX, clientY) {
    const ripple = document.createElement('div');
    ripple.style.cssText = `position: fixed; left: ${clientX - 16}px; top: ${clientY - 16}px; width: 32px; height: 32px; border: 2px solid #0369a1; border-radius: 50%; pointer-events: none; z-index: 10040; box-shadow: 0 0 12px #0369a1; transition: transform 0.4s ease-out, opacity 0.4s ease-out;`;
    const container = document.fullscreenElement || document.webkitFullscreenElement || document.body;
    container.appendChild(ripple);
    requestAnimationFrame(() => {
      ripple.style.transform = 'scale(2.2)';
      ripple.style.opacity = '0';
    });
    setTimeout(() => ripple.remove(), 450);
  }
  function syncLiveInspectModalContainer() {
    const modal = document.getElementById('liveTargetInspectModal');
    if (!modal) return;
    const fsEl = document.fullscreenElement || document.webkitFullscreenElement || document.mozFullScreenElement;
    if (fsEl) {
      if (modal.parentElement !== fsEl) {
        fsEl.appendChild(modal);
      }
    } else {
      if (modal.parentElement !== document.body) {
        document.body.appendChild(modal);
      }
    }
  }
  document.addEventListener('fullscreenchange', syncLiveInspectModalContainer);
  document.addEventListener('webkitfullscreenchange', syncLiveInspectModalContainer);
  window.handleLiveViewportClick = async (event, cameraId) => {
    const img = event.currentTarget;
    if (!img || !img.src) return;
    const rect = img.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return;
    const clickX = event.clientX - rect.left;
    const clickY = event.clientY - rect.top;
    const normX = Math.max(0.0, Math.min(1.0, clickX / rect.width));
    const normY = Math.max(0.0, Math.min(1.0, clickY / rect.height));
    showClickRipple(event.clientX, event.clientY);
    try {
      const res = await fetch('/api/camera/inspect-click', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          camera_id: cameraId || focusedCameraId || 'CAM-01',
          norm_x: normX,
          norm_y: normY
        })
      });
      if (!res.ok) return;
      const data = await res.json();
      if (data.success && data.found && data.target) {
        window.openLiveTargetInspectModal(data.target);
      } else {
        window.showToast("No active vehicle or person at clicked spot. Click on a bounding box to inspect.", "info");
      }
    } catch (err) {
      console.error("Live inspect click error:", err);
    }
  };
  window.openLiveTargetInspectModal = target => {
    syncLiveInspectModalContainer();
    currentLiveInspectTarget = target;
    const modal = document.getElementById('liveTargetInspectModal');
    if (!modal) return;
    const isVeh = target.type === 'VEHICLE';
    const typeBadge = document.getElementById('liveTargetTypeBadge');
    if (typeBadge) {
      typeBadge.innerText = `${target.type} #${target.track_id}`;
      typeBadge.style.background = isVeh ? 'rgba(59, 130, 246, 0.25)' : 'rgba(16, 185, 129, 0.25)';
      typeBadge.style.color = isVeh ? '#1d4ed8' : '#047857';
      typeBadge.style.border = `1px solid ${isVeh ? 'rgba(59, 130, 246, 0.4)' : 'rgba(16, 185, 129, 0.4)'}`;
    }
    const subHeader = document.getElementById('liveTargetSubHeader');
    if (subHeader) {
      subHeader.innerHTML = `${escapeHtml(target.camera_id)}: ${escapeHtml(target.location)} &bull; Frame: #${target.frame_number} &bull; ${escapeHtml(target.timestamp)}`;
    }
    const alertBanner = document.getElementById('liveTargetAlertBanner');
    if (alertBanner) {
      if (target.alert_state === 'HOTLIST') {
        alertBanner.style.display = 'block';
        alertBanner.style.background = 'rgba(239, 68, 68, 0.15)';
        alertBanner.style.color = '#ef4444';
        alertBanner.style.border = '1px solid rgba(239, 68, 68, 0.4)';
        alertBanner.innerText = `EMERGENCY ALERT: ${target.alert_reason || 'HOTLIST FIR CASE DETECTED'}`;
      } else if (target.alert_state === 'SUSPECT' || target.category === 'SUSPECT' || target.category === 'MAYBE_SUSPECT') {
        alertBanner.style.display = 'block';
        alertBanner.style.background = 'rgba(245, 158, 11, 0.15)';
        alertBanner.style.color = '#f59e0b';
        alertBanner.style.border = '1px solid rgba(245, 158, 11, 0.4)';
        alertBanner.innerText = `WATCHLIST WARNING: ${target.alert_reason || 'TENTATIVE WATCHLIST MATCH'}`;
      } else {
        alertBanner.style.display = 'none';
      }
    }
    const sceneImg = document.getElementById('liveTargetSceneImg');
    if (sceneImg) sceneImg.src = target.raw_scene_base64 || '';
    const bodyImg = document.getElementById('liveTargetBodyImg');
    if (bodyImg) bodyImg.src = target.target_crop_base64 || '';
    const bodyLabel = document.getElementById('liveTargetBodyLabel');
    if (bodyLabel) bodyLabel.innerText = target.target_crop_label || (isVeh ? 'Vehicle Body Crop' : 'Person Body Crop');
    const subCard = document.getElementById('liveTargetSubCropCard');
    const subImg = document.getElementById('liveTargetSubCropImg');
    const subLabel = document.getElementById('liveTargetSubCropLabel');
    const subTag = document.getElementById('liveTargetSubCropTag');
    if (target.sub_crop_base64) {
      if (subCard) subCard.style.display = 'flex';
      if (subImg) subImg.src = target.sub_crop_base64;
      if (subLabel) subLabel.innerText = target.sub_crop_label || (isVeh ? 'License Plate Crop' : 'Facial Biometric Crop');
      if (subTag) {
        subTag.innerText = 'Plate';
        subTag.style.color = isVeh ? '#f59e0b' : '#10b981';
      }
    } else {
      if (subCard) subCard.style.display = 'none';
    }
    const identVal = document.getElementById('liveTargetIdentValue');
    if (identVal) {
      if (isVeh) {
        identVal.innerText = target.plate_number || 'UNREADABLE';
        identVal.style.color = target.plate_number && target.plate_number !== 'ANALYZING...' ? '#fbbf24' : '#52647c';
      } else {
        identVal.innerText = target.person_name || 'UNKNOWN';
        identVal.style.color = target.person_name && target.person_name !== 'UNKNOWN' ? '#047857' : '#52647c';
      }
    }
    const classVal = document.getElementById('liveTargetClassValue');
    if (classVal) {
      classVal.innerText = `${target.class_name || (isVeh ? 'Vehicle' : 'Person')} (#${target.track_id})`;
    }
    const scoreVal = document.getElementById('liveTargetScoreValue');
    if (scoreVal) {
      if (isVeh) {
        scoreVal.innerText = `OCR: ${target.ocr_confidence ? target.ocr_confidence + '%' : 'Processing'} (Det: ${target.confidence}%)`;
      } else {
        scoreVal.innerText = target.similarity_score > 0 ? `Similarity: ${target.similarity_score}%` : `Detection: ${target.confidence}%`;
      }
    }
    const frameVal = document.getElementById('liveTargetFrameValue');
    if (frameVal) {
      const timeOnly = target.timestamp && target.timestamp.includes(' ') ? target.timestamp.split(' ')[1] : target.timestamp;
      frameVal.innerText = `Frame #${target.frame_number} (${timeOnly})`;
    }
    const btnAudit = document.getElementById('btnLiveTargetAuditDb');
    if (btnAudit) {
      if (target.linked_capture_id) {
        btnAudit.style.display = 'inline-flex';
        btnAudit.onclick = () => {
          window.closeLiveTargetInspectModal();
          if (isVeh) {
            window.openCaptureDetailModal(target.linked_capture_id);
          } else {}
        };
      } else {
        btnAudit.style.display = 'none';
      }
    }
    modal.style.display = 'flex';
  };
  window.closeLiveTargetInspectModal = () => {
    const modal = document.getElementById('liveTargetInspectModal');
    if (modal) modal.style.display = 'none';
  };
  window.copyLiveTargetIdentity = () => {
    if (!currentLiveInspectTarget) return;
    const text = currentLiveInspectTarget.type === 'VEHICLE' ? `Plate: ${currentLiveInspectTarget.plate_number} (Track #${currentLiveInspectTarget.track_id}, Frame #${currentLiveInspectTarget.frame_number}, ${currentLiveInspectTarget.location})` : `Person: ${currentLiveInspectTarget.person_name} (${currentLiveInspectTarget.category}, Track #${currentLiveInspectTarget.track_id}, Frame #${currentLiveInspectTarget.frame_number}, ${currentLiveInspectTarget.location})`;
    navigator.clipboard.writeText(text).then(() => {
      window.showToast("Forensic evidence copied to clipboard!", "success");
    }).catch(() => {
      window.showToast("Could not copy to clipboard.", "info");
    });
  };
  if (liveFeedImg) {
    liveFeedImg.style.cursor = 'crosshair';
    liveFeedImg.title = "Click any bounding box to inspect live forensic details";
    liveFeedImg.addEventListener('click', e => window.handleLiveViewportClick(e, focusedCameraId || 'CAM-01'));
  }
  CAMERA_SLOTS.forEach(cid => {
    const feedImg = document.getElementById(`tileFeedImg-${cid}`);
    if (feedImg) {
      feedImg.style.cursor = 'crosshair';
      feedImg.title = `Click any bounding box on ${cid} to inspect forensic details`;
      feedImg.addEventListener('click', e => window.handleLiveViewportClick(e, cid));
    }
  });
  const liveTargetInspectModalEl = document.getElementById('liveTargetInspectModal');
  if (liveTargetInspectModalEl) {
    liveTargetInspectModalEl.addEventListener('click', e => {
      if (e.target === liveTargetInspectModalEl) {
        window.closeLiveTargetInspectModal();
      }
    });
  }
  window.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      const modal = document.getElementById('liveTargetInspectModal');
      if (modal && modal.style.display === 'flex') {
        window.closeLiveTargetInspectModal();
        e.stopPropagation();
      }
    }
  }, true);
  let liveOverlayState = {
    vehicle_box: true,
    bytetrack: true,
    plate_box: true,
    ocr_text: true,
    person_box: true,
    people_counter: true
  };
  function updateHudPillStyles() {
    const layers = ['vehicle_box', 'bytetrack', 'plate_box', 'ocr_text', 'person_box', 'people_counter'];
    const chkMap = {
      vehicle_box: 'layerToggleVehicle',
      bytetrack: 'layerToggleBytetrack',
      plate_box: 'layerTogglePlate',
      ocr_text: 'layerToggleOcr',
      person_box: 'layerTogglePerson',
      people_counter: 'layerToggleCounter'
    };
    layers.forEach(layer => {
      const pill = document.getElementById(`pill-${layer}`);
      const chkId = chkMap[layer];
      const chk = chkId ? document.getElementById(chkId) : null;
      if (chk) chk.checked = !!liveOverlayState[layer];
      if (pill) {
        if (liveOverlayState[layer]) {
          pill.classList.add('active');
        } else {
          pill.classList.remove('active');
        }
      }
    });
    const isAll = layers.every(l => !!liveOverlayState[l]);
    const isRaw = layers.every(l => !liveOverlayState[l]);
    const isPlateOnly = liveOverlayState.plate_box && liveOverlayState.ocr_text && !null && !null;
    const btnAll = document.getElementById('btnPresetAll');
    const btnRaw = document.getElementById('btnPresetRaw');
    const btnPlate = document.getElementById('btnPresetPlate');
    if (btnAll) btnAll.classList.toggle('active', isAll);
    if (btnRaw) btnRaw.classList.toggle('active', isRaw);
    if (btnPlate) btnPlate.classList.toggle('active', isPlateOnly);
  }
  const hudCamSelect = document.getElementById('hudCameraSelect');
  function getSelectedHudCamera() {
    if (hudCamSelect && hudCamSelect.value) {
      return hudCamSelect.value;
    }
    return focusedCameraId || 'CAM-01';
  }
  window.syncHudLayersForCamera = async function (cid) {
    try {
      const target = !cid || cid === 'ALL' ? focusedCameraId || 'CAM-01' : cid;
      const res = await fetch(`/api/camera/layers?camera_id=${target}`);
      const d = await res.json();
      if (d && d.overlay_layers) {
        Object.assign(liveOverlayState, d.overlay_layers);
        updateHudPillStyles();
      }
    } catch (err) {
      console.error('Failed to sync HUD layers for camera:', err);
    }
  };
  if (hudCamSelect) {
    hudCamSelect.addEventListener('change', async e => {
      const selectedCam = e.target.value;
      await window.syncHudLayersForCamera(selectedCam);
    });
  }
  window.toggleLiveLayer = async function (layerName, isChecked) {
    liveOverlayState[layerName] = !!isChecked;
    updateHudPillStyles();
    try {
      const targetCam = getSelectedHudCamera();
      const payload = {
        camera_id: targetCam,
        [layerName]: !!isChecked
      };
      const res = await fetch('/api/camera/layers', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (data && data.overlay_layers) {
        Object.assign(liveOverlayState, data.overlay_layers);
        updateHudPillStyles();
      }
    } catch (err) {
      console.error('Failed to toggle live layer:', err);
    }
  };
  window.setLiveTargetFrame = async function (targetVal) {
    const val = parseInt(targetVal, 10) || 1;
    const targetCam = typeof getSelectedHudCamera === 'function' ? getSelectedHudCamera() : 'CAM-01';
    const mainSel = document.getElementById('mainHeaderTargetFrame');
    if (mainSel) mainSel.value = String(val);
    const hudSel = document.getElementById('hudTargetFrame');
    if (hudSel) hudSel.value = String(val);
    const feedSel = document.getElementById('feedTargetFrame');
    if (feedSel) {
      feedSel.value = String(val);
      if (typeof validateFeedTargetFrame === 'function') validateFeedTargetFrame();
    }
    try {
      const res = await fetch('/api/camera/target-frame', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          camera_id: targetCam,
          target_frame: val
        })
      });
      const data = await res.json();
      if (data && data.status === 'success') {
        if (typeof showToast === 'function') {
          showToast(`🎯 Target Frame Cadence: Every ${data.target_frame} frame(s) (${targetCam})`, 'info');
        }
      }
    } catch (err) {
      console.error('Failed to update live target frame:', err);
    }
    try {
      await null;
    } catch (_) {}
  };
  window.setLiveLayerPreset = async function (preset) {
    if (preset === 'raw') {
      liveOverlayState = {
        vehicle_box: false,
        bytetrack: false,
        plate_box: false,
        ocr_text: false,
        person_box: false,
        people_counter: false
      };
    } else if (preset === 'plate_only') {
      liveOverlayState = {
        vehicle_box: true,
        bytetrack: true,
        plate_box: true,
        ocr_text: true,
        person_box: false,
        people_counter: false
      };
    } else if (preset === 'all') {
      liveOverlayState = {
        vehicle_box: true,
        bytetrack: true,
        plate_box: true,
        ocr_text: true,
        person_box: true,
        people_counter: true
      };
    }
    updateHudPillStyles();
    try {
      const targetCam = getSelectedHudCamera();
      const payload = {
        camera_id: targetCam,
        ...liveOverlayState
      };
      const res = await fetch('/api/camera/layers', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (data && data.overlay_layers) {
        Object.assign(liveOverlayState, data.overlay_layers);
        updateHudPillStyles();
      }
    } catch (err) {
      console.error('Failed to set live layer preset:', err);
    }
  };
  window.syncHudLayersForCamera(getSelectedHudCamera());
  if (window.innerWidth <= 768) {
    document.body.classList.add('mobile-show-vehicles');
    currentViewMode = 'focus';
  }
  switchViewMode(currentViewMode);
  pollCameraStatuses();
  clearInterval(streamStatusPoll);
  streamStatusPoll = setInterval(pollCameraStatuses, 500);
  window.addEventListener('click', e => {
    if (e.target === evidenceModal) evidenceModal.style.display = 'none';
    if (e.target === registerVehicleModal) closeRegisterModal();
    if (e.target === vehicleDetailModal) vehicleDetailModal.style.display = 'none';
    if (e.target === captureDetailModal) captureDetailModal.style.display = 'none';
    if (e.target === trailHistoryModal) trailHistoryModal.style.display = 'none';
    if (e.target === trailNarrativeModal) trailNarrativeModal.style.display = 'none';
    if (e.target === connectCameraModal) closeConnectModal();
  });
  function escapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
  }
  null;
  null;
  null;
  null;
  null;
  null;
  null;
  null;
  null;
  null;
  null;
  null;
  window.copyPermanentToCurrentAddress = function () {
    const perm = (null)?.value || '';
    if (curr) {
      curr.value = perm;
      curr.focus();
    }
  };
  null;
  null;
  null;
  null;
  null;
  null;
  null;
  null;
  (null)?.addEventListener('click', () => {
    if (modal) modal.style.display = 'none';
  });
  document.querySelectorAll('[data-trailcat]').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('[data-trailcat]').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
    });
  });
  window.playAlertSound = function () {
    try {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (!AudioContext) return;
      const ctx = new AudioContext();
      const now = ctx.currentTime;
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sawtooth';
      osc.frequency.setValueAtTime(880, now);
      osc.exponentialRampToValueAtTime(1320, now + 0.22);
      osc.exponentialRampToValueAtTime(880, now + 0.44);
      osc.exponentialRampToValueAtTime(1320, now + 0.66);
      osc.exponentialRampToValueAtTime(880, now + 0.88);
      gain.gain.setValueAtTime(0.3, now);
      gain.gain.exponentialRampToValueAtTime(0.01, now + 0.95);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(now);
      osc.stop(now + 0.95);
    } catch (e) {}
  };
  let currentReviewCaptureId = null;
  window.submitModalReview = async action => {
    if (!currentReviewCaptureId) return;
    const cid = currentReviewCaptureId;
    await null;
  };
  window.openFullInspectFromReviewModal = () => {
    if (!currentReviewCaptureId) return;
    const cid = currentReviewCaptureId;
  };
  let currentDrawerVehFilter = 'all';
  let drawerVehSearchDebounce = null;

  async function fetchAndRenderUnifiedLiveFeed() {
    if (isFetchingUnifiedLiveFeed) return;
    isFetchingUnifiedLiveFeed = true;
    try {
      const res = await fetch('/api/unified/live-feed?source=live&limit=15');
      if (!res.ok) return;
      const data = await res.json();
      if (!data.success) return;
      const kpiVeh = document.getElementById('kpiUnifiedVehicles');
      const kpiStolen = document.getElementById('kpiUnifiedStolen');
      const kpiPpl = document.getElementById('kpiUnifiedPeople');
      const kpiPplSub = document.getElementById('kpiUnifiedPeopleSub');
      const kpiSusp = document.getElementById('kpiUnifiedSuspects');
      const vehVal = String(data.kpi.vehicles_count ?? 0);
      if (kpiVeh && kpiVeh.innerText !== vehVal) kpiVeh.innerText = vehVal;
      const stolenVal = String(data.kpi.stolen_alerts ?? 0);
      if (kpiStolen && kpiStolen.innerText !== stolenVal) kpiStolen.innerText = stolenVal;
      const pplVal = String(data.kpi.total_people_seen ?? 0);
      if (kpiPpl && kpiPpl.innerText !== pplVal) kpiPpl.innerText = pplVal;
      if (kpiPplSub) {
        const pplSubVal = `${data.kpi.current_people ?? 0} currently visible`;
        if (kpiPplSub.innerText !== pplSubVal) kpiPplSub.innerText = pplSubVal;
      }
      const suspVal = String(data.kpi.suspect_alerts ?? 0);
      if (kpiSusp && kpiSusp.innerText !== suspVal) kpiSusp.innerText = suspVal;
      const sideVeh = document.getElementById('navDrawerVehiclesCount');
      const btnVeh = document.getElementById('btnVehiclesCountBadge');
      if (sideVeh && sideVeh.innerText !== vehVal) sideVeh.innerText = vehVal;
      if (btnVeh && btnVeh.innerText !== vehVal) btnVeh.innerText = vehVal;
      renderFreshVehicles(data.fresh_vehicles || [], 'live');
    } catch (err) {
      console.warn("Unified live feed polling error:", err);
    } finally {
      isFetchingUnifiedLiveFeed = false;
    }
  }
  window.refreshUnifiedLiveFeed = fetchAndRenderUnifiedLiveFeed;
  let isFetchingUploadActivityFeed = false;
  async function fetchAndRenderUploadActivityFeed() {
    if (isFetchingUploadActivityFeed) return;
    isFetchingUploadActivityFeed = true;
    try {
      const res = await fetch('/api/unified/live-feed?source=upload&limit=15');
      if (!res.ok) return;
      const data = await res.json();
      if (!data.success) return;
      const btnVeh = document.getElementById('btnUploadVehiclesCountBadge');
      const vehVal = String(data.kpi?.vehicles_count ?? 0);
      if (btnVeh && btnVeh.innerText !== vehVal) btnVeh.innerText = vehVal;
      renderFreshVehicles(data.fresh_vehicles || [], 'upload');
    } catch (err) {
      console.warn("Upload activity feed polling error:", err);
    } finally {
      isFetchingUploadActivityFeed = false;
    }
  }
  window.fetchAndRenderUploadActivityFeed = fetchAndRenderUploadActivityFeed;
  window.refreshUploadActivityFeed = fetchAndRenderUploadActivityFeed;
  function updateKeyedCardList(container, items, getItemKey, getItemSig, buildHtml, updateCardFn) {
    const activeKeys = new Set();
    const existingMap = new Map();
    Array.from(container.children).forEach(child => {
      const k = child.getAttribute('data-card-key');
      if (k) existingMap.set(k, child);
    });
    if (existingMap.size === 0 && container.children.length > 0) {
      container.innerHTML = '';
    }
    const elements = [];
    items.forEach((item, idx) => {
      const pos = idx + 1;
      const key = String(getItemKey(item));
      const sig = getItemSig(item);
      activeKeys.add(key);
      let el = existingMap.get(key);
      if (el && el.getAttribute('data-card-sig') === sig) {
        if (updateCardFn) updateCardFn(el, item, pos);
      } else {
        const temp = document.createElement('div');
        temp.innerHTML = buildHtml(item, pos, key, sig).trim();
        const newEl = temp.firstElementChild;
        if (el && el.parentNode) {
          el.parentNode.replaceChild(newEl, el);
        }
        el = newEl;
      }
      elements.push(el);
    });
    Array.from(container.children).forEach(child => {
      const k = child.getAttribute('data-card-key');
      if (k && !activeKeys.has(k)) {
        child.remove();
      }
    });
    elements.forEach((el, idx) => {
      if (container.children[idx] !== el) {
        container.insertBefore(el, container.children[idx] || null);
      }
    });
  }
  function buildFreshVehicleCardHtml(v, pos, key, sig) {
    const isHit = v.is_hotlist_hit;
    const plate = escapeHtml(v.display_plate || v.plate_number || 'UNREADABLE');
    const conf = v.confidence || 0;
    const timeStr = v.captured_at ? v.captured_at.includes('T') ? v.captured_at.split('T')[1].substring(0, 8) : v.captured_at.substring(11, 19) : 'Just now';
    const platePic = v.plate_pic_path || '';
    const vehPic = v.vehicle_pic_path || '';
    const thumb = platePic || vehPic || '';
    const altFallback = platePic && vehPic && platePic !== vehPic ? vehPic : '';
    const vIdBadge = `#${pos}`;
    const isTrafficViol = Boolean(v.is_traffic_violation || v.violation_type);
    const cardRowClass = isHit ? 'is-hotlist' : isTrafficViol ? 'is-traffic-violation' : '';
    const cardClickAction = isTrafficViol ? 'window.openSplitViolationModal(' + v.id + ')' : 'openCaptureDetailModal(' + v.id + ')';
    return `
            <div class="fresh-card-row ${cardRowClass}" data-card-key="${key}" data-card-sig="${sig}" onclick="${cardClickAction}" title="${isTrafficViol ? '⚠️ Traffic Violation Detected - Click for Side-by-Side Inspector' : 'Click to inspect vehicle evidence'}">
                <span class="cap-rank-badge ${pos === 1 ? 'newest' : ''}" style="${pos === 1 ? 'background: #f59e0b; color: #000; font-weight: 800;' : 'background: rgba(245, 158, 11, 0.2); color: #92400e;'}">${vIdBadge}</span>
                <div class="fresh-card-thumb" style="border-color: ${isHit ? '#ef4444' : 'var(--border-color)'};">
                    ${thumb ? `<img src="${thumb}" alt="Plate" style="object-fit: contain;" onerror="this.onerror=null; ${altFallback ? `this.src='${altFallback}'; this.onerror=function(){ this.parentElement.innerHTML='<span style=\'font-size:0.875rem; color:var(--text-muted);\'>No Crop</span>'; };` : `this.parentElement.innerHTML='<span style=\'font-size:0.875rem; color:var(--text-muted);\'>No Crop</span>';`}">` : '<span style="font-size:0.875rem; color:var(--text-muted);">No Crop</span>'}
                </div>
                <div class="fresh-card-body">
                    <div class="fresh-card-primary">
                        <span class="fresh-card-title">${plate}</span>
                        <span class="conf-pill" style="font-size: 0.875rem; padding: 2px 6px;">${conf}%</span>
                    </div>
                    <div class="fresh-card-meta">
                        <span style="color: #92400e; font-weight: 700;">VEHICLE</span>
                        ${v.driver_name && v.driver_name.toUpperCase() !== 'UNKNOWN' ? `
                            <span class="badge" style="background: ${['SUSPECT', 'WANTED', 'CRIMINAL'].includes((v.driver_category || '').toUpperCase()) ? 'rgba(239, 68, 68, 0.25)' : 'rgba(99, 102, 241, 0.25)'}; color: ${['SUSPECT', 'WANTED', 'CRIMINAL'].includes((v.driver_category || '').toUpperCase()) ? '#b91c1c' : '#4338ca'}; border: 1px solid ${['SUSPECT', 'WANTED', 'CRIMINAL'].includes((v.driver_category || '').toUpperCase()) ? 'rgba(239, 68, 68, 0.5)' : 'rgba(99, 102, 241, 0.4)'}; font-size: 0.875rem; padding: 1px 5px; border-radius: 4px;" title="Cross-Modal Linked Driver">
                                👤 ${escapeHtml(v.driver_name)} ${v.driver_similarity ? `(${Math.round(v.driver_similarity)}%)` : ''}
                            </span>
                        ` : ''}
                        <span>&bull;</span>
                        <span>${escapeHtml(v.location || 'CAM-01')}</span>
                        <span>&bull;</span>
                        <span>${timeStr}</span>
                        ${plate.includes('UNREADABLE') ? '<span style="color:#92400e; font-size:0.875rem; font-weight:600;">&bull; Distant Crop</span>' : ''}
                        ${isHit ? '<span style="color:#ef4444; font-weight:bold;">&bull; CASE ALERT</span>' : ''}
                    </div>
                </div>
            </div>
        `;
  }
  function renderFreshVehicles(vehicles, mode = 'live') {
    vehicles = (vehicles || []).filter(window.isVisibleVehicleDetection);
    window._freshVehiclesCache = window._freshVehiclesCache || new Map();
    if (Array.isArray(vehicles)) {
      vehicles.forEach(v => {
        if (v && v.id) window._freshVehiclesCache.set(Number(v.id), v);
      });
    }
    const containerId = mode === 'upload' ? 'uploadFreshVehiclesContainer' : 'liveFreshVehiclesContainer';
    const countBadgeId = mode === 'upload' ? 'uploadVehiclesFreshCount' : 'liveVehiclesFreshCount';
    const mobBadgeId = mode === 'upload' ? 'mobUploadVehiclesCountBadge' : 'mobVehiclesCountBadge';
    const emptyMsg = mode === 'upload' ? 'No uploaded vehicle captures yet. Upload photo or video above to analyze.' : 'No vehicle captures yet. Start stream or connect live camera.';
    const container = document.getElementById(containerId);
    if (!container) return;
    const countBadge = document.getElementById(countBadgeId);
    const mobVehBadge = document.getElementById(mobBadgeId);
    const cText = `${vehicles.length} / 15 Fresh`;
    const mText = `${vehicles.length} Fresh`;
    if (countBadge && countBadge.innerText !== cText) countBadge.innerText = cText;
    if (mobVehBadge && mobVehBadge.innerText !== mText) mobVehBadge.innerText = mText;
    if (vehicles.length === 0) {
      if (container.dataset.lastSig !== 'empty') {
        container.dataset.lastSig = 'empty';
        container.innerHTML = `
                    <div class="empty-state" style="padding: 24px 12px;">
                        <p style="color: var(--text-muted); font-size: 0.9125rem;">${emptyMsg}</p>
                    </div>
                `;
      }
      return;
    }
    const newSig = vehicles.map(v => `${v.id}_${v.captured_at}_${v.confidence}_${v.display_plate || v.plate_number}_${v.is_traffic_violation}_${v.is_hotlist_hit}_${v.driver_name || ''}`).join('|');
    if (container.dataset.lastSig === newSig) {
      return;
    }
    container.dataset.lastSig = newSig;
    updateKeyedCardList(container, vehicles, v => v.id, v => `${v.id}_${v.confidence}_${v.display_plate || v.plate_number}_${v.is_traffic_violation}_${v.is_hotlist_hit}_${v.driver_name || ''}`, buildFreshVehicleCardHtml, (el, v, pos) => {
      const rankBadge = el.querySelector('.cap-rank-badge');
      if (rankBadge) {
        const badgeText = `#${pos}`;
        if (rankBadge.innerText !== badgeText) rankBadge.innerText = badgeText;
        const expectedClass = `cap-rank-badge ${pos === 1 ? 'newest' : ''}`;
        if (rankBadge.className !== expectedClass) rankBadge.className = expectedClass;
        rankBadge.style.background = pos === 1 ? '#f59e0b' : 'rgba(245, 158, 11, 0.2)';
        rankBadge.style.color = pos === 1 ? '#000' : '#f59e0b';
        rankBadge.style.fontWeight = '800';
      }
    });
  }
  async function handleUnifiedUpload(file, options = null) {
    if (!file) return;
    const isVideo = file.type.startsWith('video/') || (/\.(mp4|mov|avi|mkv|webm)$/i).test(file.name);
    const taskId = 'task_' + Date.now() + '_' + Math.random().toString(36).substring(2, 8);
    let pollProgressTimer = null;
    let isUploadFinished = false;
    const targetRadio = document.querySelector('input[name="investigationTarget"]:checked');
    const currentTarget = (window.currentInvestigationTarget || (targetRadio ? targetRadio.value : 'both')).toLowerCase();
    let initialStatusText = "";
    if (isVideo) {
      if (currentTarget === 'vehicle') initialStatusText = "Uploading & initialising vehicle ANPR video stream..."; else initialStatusText = "Uploading & initialising video stream...";
    } else {
      if (currentTarget === 'vehicle') initialStatusText = "Uploading & analysing vehicle / plate..."; else initialStatusText = "Uploading & analysing photo...";
    }
    const initialFramesLabel = isVideo ? "Frames: 0 / 0" : "[Photo Mode: 1 / 1]";
    showProgress(initialStatusText, 2, initialFramesLabel);
    pollProgressTimer = setInterval(async () => {
      if (isUploadFinished) return;
      try {
        const pRes = await fetch(`/api/unified/upload-progress?task_id=${encodeURIComponent(taskId)}`);
        if (pRes.ok) {
          const pData = await pRes.json();
          if (pData && pData.status && pData.status !== 'waiting') {
            let framesLabel = '';
            if (pData.media_type === 'video' || isVideo) {
              const currF = pData.current_frame || 0;
              const totalF = Math.max(pData.total_frames || 0, currF);
              framesLabel = totalF > 0 ? `Frames: ${currF} / ${totalF}` : `Frames: ${currF}`;
            } else {
              framesLabel = `[Photo Mode: ${pData.current_frame || 1} / ${pData.total_frames || 1}]`;
            }
            showProgress(pData.status_text || "Processing media...", pData.pct || 15, framesLabel);
          }
        }
      } catch (pErr) {}
    }, 250);
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('fps', window.selectedUploadFps !== undefined ? window.selectedUploadFps : 5);
      formData.append('task_id', taskId);
      const chkSave = document.getElementById('chkSaveAnnotatedVideo');
      formData.append('save_annotated_video', chkSave ? chkSave.checked ? 'true' : 'false' : 'true');
      formData.append('target', currentTarget);
      const selectedCamera = window.karnalCameraRegistry?.getSelectedUploadCamera(options);
      if (selectedCamera) {
        formData.append('registered_camera_id', selectedCamera.id);
        formData.append('location', selectedCamera.name);
        formData.append('gps_coords', `${selectedCamera.lat}, ${selectedCamera.lng}`);
      }
      if (options && options.capturedAt) formData.append('captured_at', options.capturedAt);
      const res = await fetch(`/api/unified/upload?target=${encodeURIComponent(currentTarget)}`, {
        method: 'POST',
        body: formData
      });
      isUploadFinished = true;
      if (pollProgressTimer) {
        clearInterval(pollProgressTimer);
        pollProgressTimer = null;
      }
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Unified processing failed");
      }
      const data = await res.json();
      const finalFramesLabel = isVideo ? "Frames Complete" : "[Photo Mode: 1 / 1]";
      await finishSmoothProgressTicker(finalFramesLabel);
      if (typeof fetchActiveAlerts === 'function') {
        fetchActiveAlerts();
      }
      const viewport = document.getElementById('anprInspectionViewport');
      const content = document.getElementById('anprInspectionContent');
      const typeBadge = document.getElementById('anprInspectionTypeBadge');
      const subtext = document.getElementById('anprInspectionSubtext');
      const dlBtn = document.getElementById('btnDownloadAnnotatedMedia');
      const dropzone = document.getElementById('unifiedUploadDropzone');
      if (dropzone) dropzone.style.display = 'none';
      const analysisTarget = data.target || currentTarget || 'both';
      if (typeBadge) {
        if (analysisTarget === 'vehicle') {
          typeBadge.innerText = data.media_type === 'video' ? 'ANPR VEHICLE VIDEO ANALYSIS' : 'ANPR VEHICLE PHOTO ANALYSIS';
          typeBadge.style.background = 'rgba(245, 158, 11, 0.2)';
          typeBadge.style.color = '#fbbf24';
          typeBadge.style.borderColor = 'rgba(245, 158, 11, 0.4)';
        } else {
          typeBadge.innerText = data.media_type === 'video' ? 'UNIFIED VIDEO ANALYSIS' : 'UNIFIED PHOTO ANALYSIS';
          typeBadge.style.background = 'rgba(16, 185, 129, 0.2)';
          typeBadge.style.color = '#047857';
          typeBadge.style.borderColor = 'rgba(16, 185, 129, 0.4)';
        }
      }
      if (subtext) {
        if (analysisTarget === 'vehicle') {
          subtext.innerText = `ANPR Vehicle & Plate Forensics Only (${data.stats.total_vehicles} Vehicles Detected, ${data.stats.hotlist_vehicles || 0} Hotlist Hits)`;
        } else {
          subtext.innerText = `ANPR (${data.stats.total_vehicles} Vehicles, ${data.stats.people_count} People)`;
        }
      }
      if (dlBtn) {
        if (data.media_type === 'video' && data.output_video_url) {
          dlBtn.href = data.output_video_url;
          dlBtn.style.display = 'inline-flex';
        } else {
          dlBtn.style.display = 'none';
        }
      }
      if (data.correlation && data.correlation.linked_pairs) {
        const pairs = data.correlation.linked_pairs;
        pairs.forEach(pair => {
          const veh = pair.vehicle;
        });
      }
      let vehiclesHtml = '';
      if (data.vehicles && data.vehicles.length > 0) {
        vehiclesHtml = data.vehicles.filter(window.isVisibleVehicleDetection).map((v, idx) => {
          const plate = escapeHtml(v.display_plate || v.final_plate || 'UNREADABLE');
          const conf = v.confidence || 0;
          const isHit = v.is_hotlist_hit;
          const vIdTag = String(v.vehicle_id || `VEH-${v.track_id || idx + 1}`);
          return `



                        <div style="background: rgba(11, 15, 25, 0.7); border: 1px solid ${isHit ? 'rgba(239, 68, 68, 0.5)' : 'rgba(255, 255, 255, 0.08)'}; border-radius: 6px; padding: 10px; margin-bottom: 8px;">



                            <div style="display: flex; justify-content: space-between; align-items: center;">



                                <div style="display: flex; align-items: center; gap: 8px;">



                                    ${v.plate_crop_base64 ? `<img src="data:image/jpeg;base64,${v.plate_crop_base64}" style="height: 32px; border-radius: 4px; border: 1px solid var(--border-color); object-fit: contain;">` : ''}



                                    <div>



                                        <div style="font-weight: 700; color: #ffffff; font-family: var(--font-mono); font-size: 1.0125rem;">${plate}</div>



                                        </div>



                                </div>



                                <span class="conf-pill" style="font-size: 0.875rem;">${conf}%</span>



                            </div>



                            <div style="margin-top: 6px; display: flex; align-items: center; gap: 6px; flex-wrap: wrap;">



                                <span class="badge-verified" style="font-size: 0.875rem;">${v.cls_name || 'Vehicle'}</span>



                                ${isHit ? `<span style="background: rgba(239, 68, 68, 0.2); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.4); font-size: 0.875rem; padding: 2px 6px; border-radius: 4px; font-weight: bold;">STOLEN / CASE ALERT</span>` : ''}



                                ${v.final_plate === 'UNREADABLE' || plate.includes('UNREADABLE') ? `<span style="background: rgba(245, 158, 11, 0.15); color: #92400e; border: 1px solid rgba(245, 158, 11, 0.35); font-size: 0.875rem; padding: 2px 6px; border-radius: 4px; font-weight: 600;" title="Distant vehicle or low resolution crop">⚠️ Distant / Unreadable Crop</span>` : ''}



                                ${""}



                            </div>



                            ${isHit && (v.hotlist_match || v.hotlist_info) ? `



                                <div style="margin-top: 6px; padding: 6px 8px; background: rgba(239, 68, 68, 0.1); border-left: 2px solid #ef4444; border-radius: 4px; font-size: 0.875rem; color: #991b1b;">



                                    ${v.hotlist_match ? `



                                        <div><strong>Match:</strong> ${escapeHtml(v.hotlist_match.offence_type || v.hotlist_match.lost_location || 'Hotlist Record')}</div>



                                        ${v.hotlist_match.owner_name ? `



                                            <div style="color: #475569; margin-top: 2px;">



                                                👤 Owner: <strong>${escapeHtml(v.hotlist_match.owner_name)}</strong>



                                                ${v.hotlist_match.owner_mobile ? ` &bull; 📞 ${escapeHtml(v.hotlist_match.owner_mobile)}` : ''}



                                                ${v.hotlist_match.owner_address ? ` &bull; 📍 ${escapeHtml(v.hotlist_match.owner_address)}` : ''}



                                            </div>



                                        ` : ''}



                                    ` : `



                                        <div>${escapeHtml(v.hotlist_info)}</div>



                                    `}



                                </div>



                            ` : ''}



                        </div>



                    `;
        }).join('');
      } else {
        vehiclesHtml = `<p style="color: var(--text-muted); font-size: 0.875rem; text-align: center; padding: 16px 0;">No vehicles or license plates detected.</p>`;
      }
      if (analysisTarget === 'vehicle') {} else {}
      if (content) {
        content.innerHTML = `



                    <div>



                        <!-- Composite Visual Preview -->



                        <div style="margin-bottom: 14px; border-radius: 8px; overflow: hidden; border: 1px solid var(--border-color); background: #000; text-align: center;">



                            ${data.media_type === 'video' ? data.output_video_url ? `



                                <video id="unifiedResultVideo" src="${data.output_video_url}?t=${Date.now()}" controls autoplay loop playsinline muted preload="auto" style="width: 100%; max-height: 420px; object-fit: contain; background: #000; display: block; margin: 0 auto; border-radius: 6px;"></video>



                            ` : `



                                <div style="padding: 24px; text-align: center; color: #475569; background: rgba(241,245,249,0.4); border: 1px dashed rgba(148, 163, 184, 0.3); border-radius: 8px;">



                                    <div style="font-size: 1.0125rem; font-weight: 600; color: #0369a1; margin-bottom: 4px; display: flex; align-items: center; justify-content: center; gap: 6px;">



                                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon></svg>



                                        <span>Fast Processing Mode: Video File Writing Skipped</span>



                                    </div>



                                    <div style="font-size: 0.875rem; color: #52647c;">Annotated video encoding was disabled. All plates and vehicle telemetry were captured in ultra-fast mode.</div>



                                </div>



                            ` : `



                                <img src="data:image/jpeg;base64,${data.annotated_image_base64}" alt="Composite Inference" style="max-width: 100%; max-height: 420px; object-fit: contain; display: block; margin: 0 auto; border-radius: 6px;">



                            `}



                        </div>



                        <!-- Dual-Column Results Grid -->



                        <div class="unified-test-results-grid">



                            <!-- Left: Vehicles Column -->



                            <div class="unified-result-col">



                                <div class="unified-result-col-header">



                                    <span style="font-size: 0.9125rem; font-weight: 700; color: #92400e; display: flex; align-items: center; gap: 6px;">



                                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="1" y="5" width="22" height="14" rx="3"></rect></svg>



                                        Vehicles &amp; Plates ${""}



                                    </span>



                                </div>



                                <div>${vehiclesHtml}</div>



                            </div>











                        </div>



                    </div>



                `;
      }
      if (viewport) {
        if (window.switchFeedMode) window.switchFeedMode('upload');
        viewport.style.display = 'block';
        if (data.media_type === 'video' && data.output_video_url) {
          setTimeout(() => {
            const vid = document.getElementById('unifiedResultVideo');
            if (vid) {
              vid.load();
              vid.play().catch(e => console.log("Video auto-play suppressed, controls available:", e));
            }
          }, 80);
        }
        viewport.scrollIntoView({
          behavior: 'smooth',
          block: 'nearest'
        });
      }
      if (typeof fetchAndRenderUploadActivityFeed === 'function') {
        fetchAndRenderUploadActivityFeed();
      }
      fetchAndRenderUnifiedLiveFeed();
      try {
        fetchAndRenderCapturedDb();
      } catch (_) {}
      try {} catch (_) {}
      ;
      null;
    } catch (err) {
      isUploadFinished = true;
      if (pollProgressTimer) {
        clearInterval(pollProgressTimer);
        pollProgressTimer = null;
      }
      console.error("Unified upload error:", err);
      showToastAlert(err.message, "error", "Unified Upload Error");
    } finally {
      isUploadFinished = true;
      if (pollProgressTimer) {
        clearInterval(pollProgressTimer);
        pollProgressTimer = null;
      }
      hideProgress();
    }
  }
  window.currentInvestigationMode = 'photo';
  window.currentInvestigationTarget = 'both';
  let liveWebcamStream = null;
  let cameraFacingMode = 'environment';
  let mediaRecorder = null;
  let recordedChunks = [];
  let recTimerInterval = null;
  let recSeconds = 0;
  window.setInvestigationMediaType = function (mode) {
    window.currentInvestigationMode = mode;
    const btnPhoto = document.getElementById('btnModePhoto');
    const btnVideo = document.getElementById('btnModeVideo');
    const vidControls = document.getElementById('videoSpecificControlsBox');
    const mediaInput = document.getElementById('unifiedMediaInput');
    const btnSnap = document.getElementById('btnSnapFromCamera');
    const lblUpload = document.getElementById('lblUploadButtonText');
    const lblSnap = document.getElementById('lblCameraSnapText');
    if (mode === 'photo') {
      if (btnPhoto) {
        btnPhoto.style.background = '#6366f1';
        btnPhoto.style.color = '#ffffff';
      }
      if (btnVideo) {
        btnVideo.style.background = 'transparent';
        btnVideo.style.color = '#52647c';
      }
      if (vidControls) vidControls.style.display = 'none';
      if (mediaInput) mediaInput.accept = 'image/*';
      if (lblUpload) lblUpload.innerText = 'Upload Photo from File';
      if (lblSnap) lblSnap.innerText = 'Click from Camera';
    } else {
      if (btnVideo) {
        btnVideo.style.background = '#6366f1';
        btnVideo.style.color = '#ffffff';
      }
      if (btnPhoto) {
        btnPhoto.style.background = 'transparent';
        btnPhoto.style.color = '#52647c';
      }
      if (vidControls) vidControls.style.display = 'flex';
      if (mediaInput) mediaInput.accept = 'video/*';
      if (lblUpload) lblUpload.innerText = 'Upload Video from File';
      if (lblSnap) lblSnap.innerText = 'Record Video from Camera';
    }
  };
  window.setInvestigationTarget = function (target) {
    window.currentInvestigationTarget = target;
    const radio = document.querySelector(`input[name="investigationTarget"][value="${target}"]`);
    if (radio) radio.checked = true;
    const targets = ['both', 'vehicle'];
    targets.forEach(t => {
      const lbl = document.getElementById('lblTarget' + t.charAt(0).toUpperCase() + t.slice(1));
      if (lbl) {
        if (t === target) {
          const color = t === 'both' ? '#10b981' : '#fbbf24';
          lbl.style.background = t === 'both' ? 'rgba(16, 185, 129, 0.18)' : 'rgba(245, 158, 11, 0.18)';
          lbl.style.color = color;
          lbl.style.border = `1.5px solid ${color}`;
        } else {
          lbl.style.background = 'rgba(241,245,249,0.6)';
          lbl.style.color = '#475569';
          lbl.style.border = '1px solid rgba(148, 163, 184, 0.3)';
        }
      }
    });
  };
  window.currentUploadExperienceMode = localStorage.getItem('hp_upload_experience_mode') || 'simple';
  window.setUploadMode = function (mode) {
    window.currentUploadExperienceMode = mode;
    localStorage.setItem('hp_upload_experience_mode', mode);
    const btnSimple = document.getElementById('btnUploadSimpleMode');
    const btnAdv = document.getElementById('btnUploadAdvMode');
    const engineBar = document.getElementById('aiModelEngineBar');
    const simpleChip = document.getElementById('simplePipelineInfoChip');
    if (mode === 'simple') {
      if (btnSimple) btnSimple.classList.add('active');
      if (btnAdv) btnAdv.classList.remove('active');
      if (engineBar) engineBar.style.display = 'none';
      if (simpleChip) simpleChip.style.display = 'flex';
      if (typeof window.selectCustomModel === 'function') {
        window.selectCustomModel('vehicle', 'yolo11n');
        window.selectCustomModel('plate', 'plate_yolo_l');
        window.selectCustomModel('person', 'yolo11n');
        null;
        null;
      } else {
        const selVeh = document.getElementById('selVehicleModel');
        const selPlate = document.getElementById('selPlateModel');
        const selPerson = document.getElementById('selPersonModel');
        if (selVeh) selVeh.value = 'yolo11n';
        if (selPlate) selPlate.value = 'plate_yolo_l';
        if (selPerson) selPerson.value = 'yolo11n';
      }
    } else {
      if (btnSimple) btnSimple.classList.remove('active');
      if (btnAdv) btnAdv.classList.add('active');
      if (engineBar) engineBar.style.display = 'flex';
      if (simpleChip) simpleChip.style.display = 'none';
    }
  };
  const _origSwitchFeedMode = window.switchFeedMode;
  window.switchFeedMode = function (mode) {
    if (typeof _origSwitchFeedMode === 'function') {
      _origSwitchFeedMode(mode);
    }
    if (mode === 'upload') {
      const expMode = localStorage.getItem('hp_upload_experience_mode') || 'simple';
      window.setUploadMode(expMode);
    } else {
      const engineBar = document.getElementById('aiModelEngineBar');
      if (engineBar) engineBar.style.display = 'flex';
    }
  };
  window.triggerSnapCamera = async function () {
    const modal = document.getElementById('liveCameraCaptureModal');
    const modalTitle = document.getElementById('camModalTitle');
    const modalSub = document.getElementById('camModalSubtitle');
    const btnPhoto = document.getElementById('btnCapturePhotoNow');
    const btnStartRec = document.getElementById('btnStartVideoRec');
    const btnStopRec = document.getElementById('btnStopVideoRec');
    const recIndicator = document.getElementById('camRecIndicator');
    if (recIndicator) recIndicator.style.display = 'none';
    if (window.currentInvestigationMode === 'photo') {
      if (modalTitle) modalTitle.innerText = 'Live Camera Snapshot';
      if (modalSub) modalSub.innerText = 'Point at a vehicle number plate, then click Capture';
      if (btnPhoto) btnPhoto.style.display = 'inline-flex';
      if (btnStartRec) btnStartRec.style.display = 'none';
      if (btnStopRec) btnStopRec.style.display = 'none';
    } else {
      if (modalTitle) modalTitle.innerText = 'Live Camera Video Recorder';
      if (modalSub) modalSub.innerText = 'Record a surveillance video clip (3-15 seconds) for automated multi-frame AI analysis';
      if (btnPhoto) btnPhoto.style.display = 'none';
      if (btnStartRec) btnStartRec.style.display = 'inline-flex';
      if (btnStopRec) btnStopRec.style.display = 'none';
    }
    if (modal) modal.style.display = 'flex';
    await startDeviceCameraStream();
  };
  async function startDeviceCameraStream() {
    const video = document.getElementById('liveWebcamPreview');
    const statusText = document.getElementById('camStreamStatusText');
    if (liveWebcamStream) {
      liveWebcamStream.getTracks().forEach(track => track.stop());
      liveWebcamStream = null;
    }
    try {
      if (statusText) statusText.innerText = 'Requesting camera access...';
      const constraints = {
        video: {
          facingMode: cameraFacingMode,
          width: {
            ideal: 1280
          },
          height: {
            ideal: 720
          }
        },
        audio: false
      };
      const stream = await navigator.mediaDevices.getUserMedia(constraints);
      liveWebcamStream = stream;
      if (video) {
        video.srcObject = stream;
        await video.play().catch(e => console.log("Camera preview play caught:", e));
      }
      if (statusText) statusText.innerText = `Camera active (${cameraFacingMode === 'environment' ? 'Rear / Main' : 'Front'})`;
    } catch (err) {
      console.error("Camera access error:", err);
      if (statusText) statusText.innerHTML = `<span style="color:#b91c1c;">Camera permission denied or camera in use.</span>`;
      if (typeof showToastAlert === 'function') {
        showToastAlert("Please allow camera permission in your browser.", "warning", "Camera Permission");
      }
    }
  }
  window.flipCameraFacing = function () {
    cameraFacingMode = cameraFacingMode === 'environment' ? 'user' : 'environment';
    startDeviceCameraStream();
  };
  window.closeLiveCameraModal = function () {
    if (recTimerInterval) {
      clearInterval(recTimerInterval);
      recTimerInterval = null;
    }
    if (mediaRecorder && mediaRecorder.state === 'recording') {
      try {
        mediaRecorder.stop();
      } catch (e) {}
    }
    if (liveWebcamStream) {
      liveWebcamStream.getTracks().forEach(track => track.stop());
      liveWebcamStream = null;
    }
    const video = document.getElementById('liveWebcamPreview');
    if (video) video.srcObject = null;
    const modal = document.getElementById('liveCameraCaptureModal');
    if (modal) modal.style.display = 'none';
  };
  window.capturePhotoFromWebcam = function () {
    const video = document.getElementById('liveWebcamPreview');
    const canvas = document.getElementById('liveWebcamCanvas');
    if (!video || !canvas) return;
    const w = video.videoWidth || 1280;
    const h = video.videoHeight || 720;
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0, w, h);
    canvas.toBlob(blob => {
      if (!blob) return;
      const file = new File([blob], `live_camera_snap_${Date.now()}.jpg`, {
        type: 'image/jpeg'
      });
      window.closeLiveCameraModal();
      handleUnifiedUpload(file);
    }, 'image/jpeg', 0.95);
  };
  window.startVideoRecordingFromCam = function () {
    if (!liveWebcamStream) return;
    recordedChunks = [];
    recSeconds = 0;
    const btnStart = document.getElementById('btnStartVideoRec');
    const btnStop = document.getElementById('btnStopVideoRec');
    const indicator = document.getElementById('camRecIndicator');
    const timerText = document.getElementById('camRecTimerText');
    try {
      const mimeType = MediaRecorder.isTypeSupported('video/webm;codecs=vp9') ? 'video/webm;codecs=vp9' : 'video/webm';
      mediaRecorder = new MediaRecorder(liveWebcamStream, {
        mimeType
      });
      mediaRecorder.ondataavailable = function (e) {
        if (e.data && e.data.size > 0) {
          recordedChunks.push(e.data);
        }
      };
      mediaRecorder.onstop = function () {
        const blob = new Blob(recordedChunks, {
          type: 'video/webm'
        });
        const file = new File([blob], `camera_recorded_clip_${Date.now()}.webm`, {
          type: 'video/webm'
        });
        window.closeLiveCameraModal();
        handleUnifiedUpload(file);
      };
      mediaRecorder.start(250);
      if (btnStart) btnStart.style.display = 'none';
      if (btnStop) btnStop.style.display = 'inline-flex';
      if (indicator) indicator.style.display = 'inline-flex';
      recTimerInterval = setInterval(() => {
        recSeconds++;
        const mins = String(Math.floor(recSeconds / 60)).padStart(2, '0');
        const secs = String(recSeconds % 60).padStart(2, '0');
        if (timerText) timerText.innerText = `REC ${mins}:${secs}`;
      }, 1000);
    } catch (e) {
      console.error("Recording error:", e);
      alert("MediaRecorder not supported or failed: " + e.message);
    }
  };
  window.stopVideoRecordingFromCam = function () {
    if (recTimerInterval) {
      clearInterval(recTimerInterval);
      recTimerInterval = null;
    }
    if (mediaRecorder && mediaRecorder.state === 'recording') {
      mediaRecorder.stop();
    }
  };
  window.investigationSearchesCache = [];
  window.currentHistFilter = 'all';
  window.currentHistSearchQuery = '';
  window.openInvestigationHistoryModal = async function () {
    const modal = document.getElementById('investigationHistoryModal');
    if (modal) modal.style.display = 'flex';
    await window.fetchAndRenderInvestigationHistory();
  };
  window.closeInvestigationHistoryModal = function () {
    const modal = document.getElementById('investigationHistoryModal');
    if (modal) modal.style.display = 'none';
  };
  window.fetchAndRenderInvestigationHistory = async function () {
    const container = document.getElementById('investigationModalHistoryList');
    const navBadge = document.getElementById('historyNavCountBadge');
    const modalBadge = document.getElementById('historyNavCountBadgeModal');
    try {
      const res = await fetch('/api/investigation/history');
      if (res.ok) {
        const data = await res.json();
        window.investigationSearchesCache = data.searches || [];
      }
    } catch (err) {
      console.warn("Could not fetch remote investigation history, using cached:", err);
    }
    const totalCount = window.investigationSearchesCache.length;
    if (navBadge) navBadge.innerText = totalCount;
    if (modalBadge) modalBadge.innerText = `${totalCount} ${totalCount === 1 ? 'Search' : 'Searches'}`;
    window.renderInvestigationHistoryUI();
  };
  window.setHistFilter = function (filterType) {
    window.currentHistFilter = filterType;
    ['btnHistFilterAll', 'btnHistFilterVideo', 'btnHistFilterPhoto', 'btnHistFilterHits'].forEach(id => {
      const btn = document.getElementById(id);
      if (!btn) return;
      btn.classList.remove('active');
      if (filterType === 'all' && id === 'btnHistFilterAll' || filterType === 'video' && id === 'btnHistFilterVideo' || filterType === 'photo' && id === 'btnHistFilterPhoto' || filterType === 'hits' && id === 'btnHistFilterHits') {
        btn.classList.add('active');
      }
    });
    window.renderInvestigationHistoryUI();
  };
  window.filterInvestigationHistory = function (query) {
    window.currentHistSearchQuery = (query || '').toLowerCase().trim();
    window.renderInvestigationHistoryUI();
  };
  window.renderInvestigationHistoryUI = function () {
    const container = document.getElementById('investigationModalHistoryList');
    if (!container) return;
    let items = window.investigationSearchesCache || [];
    if (window.currentHistFilter === 'video') {
      items = items.filter(s => s.media_type === 'video');
    } else if (window.currentHistFilter === 'photo') {
      items = items.filter(s => s.media_type === 'photo');
    } else if (window.currentHistFilter === 'hits') {
      items = items.filter(s => (s.hotlist_hits || 0) > 0);
    }
    if (window.currentHistSearchQuery) {
      const q = window.currentHistSearchQuery;
      items = items.filter(s => {
        const fn = (s.filename || '').toLowerCase();
        const off = (s.officer_name || '').toLowerCase();
        const dist = (s.district || '').toLowerCase();
        const stn = (s.station || '').toLowerCase();
        const platesStr = (s.vehicles || []).map(v => v.final_plate || v.display_plate || '').join(' ').toLowerCase();
        return fn.includes(q) || off.includes(q) || dist.includes(q) || stn.includes(q) || platesStr.includes(q);
      });
    }
    if (items.length === 0) {
      container.innerHTML = `



                <div style="font-size: 0.9125rem; color: #64748b; padding: 40px 20px; text-align: center; background: rgba(241,245,249,0.5); border-radius: 8px; border: 1px dashed var(--border-color);">



                    <div style="font-size: 1.5rem; margin-bottom: 6px;">📂</div>



                    <div style="font-weight: 600; color: #475569;">No matching forensic investigation searches found.</div>



                    <div style="font-size: 0.875rem; color: #52647c; margin-top: 4px;">Upload media to run AI vehicle recognition to record new investigations.</div>



                </div>



            `;
      return;
    }
    container.innerHTML = items.map(s => {
      const isVideo = s.media_type === 'video';
      const hasHits = (s.hotlist_hits || 0) > 0;
      const cardClass = hasHits ? 'forensic-history-card has-hit' : 'forensic-history-card';
      const vehicles = s.vehicles || [];
      let platePillsHtml = '';
      if (vehicles.length > 0) {
        platePillsHtml = vehicles.map(v => {
          const p = escapeHtml(v.display_plate || v.final_plate || 'UNREADABLE');
          const isHit = v.is_hotlist_hit;
          const pillClass = isHit ? 'plate-pill-tag plate-pill-hit' : 'plate-pill-tag plate-pill-clean';
          const hitIcon = isHit ? '🚨' : '🚗';
          return `<span class="${pillClass}" title="${isHit ? escapeHtml(v.hotlist_reason || 'Hotlist Hit') : 'Verified Plate'}">${hitIcon} ${p}</span>`;
        }).join(' ');
      } else {
        platePillsHtml = `<span style="font-size: 0.875rem; color: #64748b; font-style: italic;">No license plates extracted</span>`;
      }
      return `



                <div class="${cardClass}">



                    <!-- Card Header Row -->



                    <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; border-bottom: 1px solid rgba(255, 255, 255, 0.06); padding-bottom: 8px;">



                        <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">



                            <span style="font-size: 0.875rem; font-weight: 800; padding: 2px 7px; border-radius: 4px; background: ${isVideo ? 'rgba(99, 102, 241, 0.25)' : 'rgba(56, 189, 248, 0.25)'}; color: ${isVideo ? '#4338ca' : '#0369a1'}; border: 1px solid ${isVideo ? 'rgba(99, 102, 241, 0.4)' : 'rgba(56, 189, 248, 0.4)'};">



                                ${isVideo ? '🎥 VIDEO' : '📸 PHOTO'}



                            </span>



                            <span style="font-size: 0.875rem; font-weight: 800; padding: 2px 7px; border-radius: 4px; background: rgba(168, 85, 247, 0.2); color: #7e22ce; border: 1px solid rgba(168, 85, 247, 0.4);">



                                ${""}



                            </span>



                            <span style="font-size: 0.875rem; color: #52647c; display: inline-flex; align-items: center; gap: 4px;">



                                <span>👮</span> <strong style="color: #ffffff;">${escapeHtml(s.officer_name || 'Officer')}</strong>



                                <span style="font-family: var(--font-mono); color: #64748b;">(${escapeHtml(s.belt_number || '--')})</span>



                                <span style="color: #64748b;">•</span>



                                <span style="color: #0369a1; font-weight: 600;">${escapeHtml(s.district || '')}</span>



                            </span>



                        </div>



                        <div style="font-size: 0.875rem; color: #64748b; font-family: var(--font-mono); font-weight: 600;">



                            ${escapeHtml(s.time_display || s.timestamp)}



                        </div>



                    </div>



                    <!-- Media & Pipeline Meta Row -->



                    <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 12px;">



                        <div>



                            <div style="font-size: 0.9225rem; font-weight: 700; color: #ffffff; display: flex; align-items: center; gap: 6px;">



                                <span>📁</span> <span>${escapeHtml(s.filename)}</span>



                            </div>



                            <div style="font-size: 0.875rem; color: #52647c; margin-top: 3px; display: flex; flex-wrap: wrap; gap: 8px;">



                                <span>AI Model: <strong style="color: #475569;">${escapeHtml(s.vehicle_model || 'UVH-26')}</strong></span>



                                <span>•</span>



                                <span>OCR: <strong style="color: #475569;">${escapeHtml(s.ocr_engine || 'PaddleOCR')}</strong></span>



                                <span>•</span>



                                <span>Thana: <strong style="color: #475569;">${escapeHtml(s.station || 'General Post')}</strong></span>



                            </div>



                        </div>



                        <!-- Metric Summary Badges -->



                        <div style="display: flex; align-items: center; gap: 6px; flex-wrap: wrap;">



                            <span style="padding: 3px 8px; border-radius: 5px; font-size: 0.875rem; font-weight: 700; background: rgba(241,245,249,0.8); border: 1px solid rgba(255, 255, 255, 0.1); color: #475569;">



                                🚗 ${s.total_vehicles || 0} Vehicles



                            </span>



                            <span style="padding: 3px 8px; border-radius: 5px; font-size: 0.875rem; font-weight: 700; background: rgba(241,245,249,0.8); border: 1px solid rgba(255, 255, 255, 0.1); color: #0369a1;">



                                🔢 ${s.total_plates || 0} Plates



                            </span>



                            ${hasHits ? `



                            <span style="padding: 3px 8px; border-radius: 5px; font-size: 0.875rem; font-weight: 800; background: rgba(239, 68, 68, 0.2); border: 1px solid rgba(239, 68, 68, 0.4); color: #b91c1c;">



                                🚨 ${s.hotlist_hits} Hotlist Hit(s)



                            </span>



                            ` : `



                            <span style="padding: 3px 8px; border-radius: 5px; font-size: 0.875rem; font-weight: 700; background: rgba(16, 185, 129, 0.15); border: 1px solid rgba(16, 185, 129, 0.3); color: #047857;">



                                ✅ Clean



                            </span>



                            `}



                        </div>



                    </div>



                    <!-- Extracted Plates & Action Footer Row -->



                    <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; margin-top: 2px;">



                        <div style="display: flex; align-items: center; gap: 6px; flex-wrap: wrap;">



                            ${platePillsHtml}



                        </div>



                        <button type="button" class="btn-view-operator-details" onclick="window.openForensicBreakdown('${escapeHtml(s.search_id)}')">



                            👁️ View Full Forensic Breakdown



                        </button>



                    </div>



                </div>



            `;
    }).join('');
  };
  window.openForensicBreakdown = function (searchId) {
    const item = (window.investigationSearchesCache || []).find(s => s.search_id === searchId);
    if (!item) return;
    const modal = document.getElementById('forensicBreakdownModal');
    const body = document.getElementById('forensicBreakdownBody');
    const footerId = document.getElementById('reportModalFooterId');
    if (footerId) footerId.innerText = `Audit Reference: ${item.search_id} • Status: ${item.status || 'VERIFIED'}`;
    if (!body) return;
    const vehicles = (item.vehicles || []).filter(window.isVisibleVehicleDetection);
    const hasHits = (item.hotlist_hits || 0) > 0;
    let vehiclesTableHtml = '';
    if (vehicles.length > 0) {
      vehiclesTableHtml = `



                <table class="audit-table" style="width: 100%; font-size: 0.875rem;">



                    <thead>



                        <tr>



                            <th>Vehicle ID / Category</th>



                            <th>Extracted Number Plate</th>



                            <th>Confidence</th>



                            <th>Watchlist / Hotlist Status</th>



                        </tr>



                    </thead>



                    <tbody>



                        ${vehicles.map((v, i) => {
        const plate = escapeHtml(v.display_plate || v.final_plate || 'UNREADABLE');
        const isHit = v.is_hotlist_hit;
        const conf = v.confidence ? `${v.confidence.toFixed(1)}%` : '--';
        const vType = v.vehicle_type || 'Vehicle';
        const vId = v.vehicle_id || `VEH-${i + 1}`;
        return `



                                <tr>



                                    <td>



                                        <div style="font-weight: 700; color: #ffffff;">${vType}</div>







                                    </td>



                                    <td>



                                        <span class="${isHit ? 'plate-pill-tag plate-pill-hit' : 'plate-pill-tag plate-pill-clean'}" style="font-size: 0.9025rem;">



                                            ${isHit ? '🚨' : '🚗'} ${plate}



                                        </span>



                                    </td>



                                    <td style="font-family: var(--font-mono); color: #047857; font-weight: 700;">${conf}</td>



                                    <td>



                                        ${isHit ? `



                                        <div style="color: #b91c1c; font-weight: 700; font-size: 0.875rem;">${escapeHtml(v.hotlist_reason || '🚨 Hotlist Flagged')}</div>



                                        <div style="font-size: 0.875rem; color: #991b1b;">Immediate Alert Dispatched</div>



                                        ` : `



                                        <span style="color: #047857; font-weight: 700; font-size: 0.875rem;">✅ Clean (No Active Record)</span>



                                        `}



                                    </td>



                                </tr>



                            `;
      }).join('')}



                    </tbody>



                </table>



            `;
    } else {
      vehiclesTableHtml = `<div style="padding: 16px; color: #64748b; font-size: 0.875rem; text-align: center;">No vehicles detected in this media.</div>`;
    }
    body.innerHTML = `



            <!-- Officer Profile Header Banner -->



            <div style="background: linear-gradient(135deg, rgba(241,245,249,0.95) 0%, rgba(30, 27, 75, 0.45) 100%); border: 1px solid rgba(99, 102, 241, 0.4); border-radius: 10px; padding: 14px 18px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;">



                <div style="display: flex; align-items: center; gap: 12px;">



                    <div style="width: 44px; height: 44px; border-radius: 10px; background: rgba(99, 102, 241, 0.2); border: 1px solid rgba(99, 102, 241, 0.4); display: flex; align-items: center; justify-content: center; font-size: 1.3rem;">



                        👮



                    </div>



                    <div>



                        <div style="font-size: 0.875rem; font-weight: 800; color: #818cf8; text-transform: uppercase;">Investigating Officer</div>



                        <div style="font-size: 1.1125rem; font-weight: 800; color: #ffffff; margin-top: 1px;">



                            ${escapeHtml(item.officer_name || 'Officer')}



                        </div>



                        <div style="font-size: 0.875rem; color: #52647c; display: flex; gap: 10px; margin-top: 2px;">



                            <span>Belt: <strong style="color: #334155; font-family: var(--font-mono);">${escapeHtml(item.belt_number || '--')}</strong></span>



                            <span>•</span>



                            <span>Jurisdiction: <strong style="color: #0369a1;">${escapeHtml(item.district || '')} District</strong></span>



                            <span>•</span>



                            <span>Posting: <strong style="color: #475569;">${escapeHtml(item.station || 'PHQ')}</strong></span>



                        </div>



                    </div>



                </div>



                <div style="text-align: right;">



                    <div style="font-size: 0.875rem; font-weight: 800; color: #64748b; text-transform: uppercase;">Timestamp of Query</div>



                    <div style="font-size: 0.9125rem; font-weight: 700; color: #ffffff; font-family: var(--font-mono); margin-top: 2px;">${escapeHtml(item.time_display || item.timestamp)}</div>



                    <span style="font-size: 0.875rem; font-weight: 800; padding: 2px 8px; border-radius: 4px; background: ${hasHits ? 'rgba(239, 68, 68, 0.2)' : 'rgba(16, 185, 129, 0.2)'}; color: ${hasHits ? '#b91c1c' : '#047857'}; border: 1px solid ${hasHits ? 'rgba(239, 68, 68, 0.4)' : 'rgba(16, 185, 129, 0.4)'}; display: inline-block; margin-top: 4px;">



                        ${hasHits ? '🚨 HOTLIST ALERT RECORDED' : '✅ CLEAN RECORD'}



                    </span>



                </div>



            </div>



            <!-- Parameters & Input Configuration Card -->



            <div style="background: rgba(241,245,249,0.7); border: 1px solid var(--border-color); border-radius: 10px; padding: 12px 16px;">



                <div style="font-size: 0.875rem; font-weight: 800; color: #475569; text-transform: uppercase; margin-bottom: 8px;">



                    ⚙️ Analysis Setup &amp; AI Pipeline Configuration



                </div>



                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; font-size: 0.875rem;">



                    <div>



                        <div style="font-size: 0.875rem; color: #64748b;">Uploaded Media File</div>



                        <div style="font-weight: 700; color: #ffffff; margin-top: 2px; word-break: break-all;">📁 ${escapeHtml(item.filename)}</div>



                    </div>



                    <div>



                        <div style="font-size: 0.875rem; color: #64748b;">Media Mode &amp; Sampling</div>



                        <div style="font-weight: 700; color: #0369a1; margin-top: 2px;">



                            ${item.media_type === 'video' ? `🎥 Video (${item.fps || 5} FPS Sampling)` : '📸 Single Photo Capture'}



                        </div>



                    </div>



                    <div>



                        <div style="font-size: 0.875rem; color: #64748b;">Vehicle Detector Model</div>



                        <div style="font-weight: 700; color: #475569; margin-top: 2px;">🤖 ${escapeHtml(item.vehicle_model || 'UVH-26 SOTA')}</div>



                    </div>



                    <div>



                        <div style="font-size: 0.875rem; color: #64748b;">License Plate OCR Engine</div>



                        <div style="font-weight: 700; color: #475569; margin-top: 2px;">🔤 ${escapeHtml(item.ocr_engine || 'PaddleOCR SOTA')}</div>



                    </div>



                </div>



            </div>



            <!-- Detection Breakdown Ledger -->



            <div style="background: rgba(241,245,249,0.7); border: 1px solid var(--border-color); border-radius: 10px; padding: 12px 16px;">



                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">



                    <div style="font-size: 0.875rem; font-weight: 800; color: #475569; text-transform: uppercase;">



                        🚗 Detected Vehicles &amp; Extracted Number Plates (${vehicles.length})



                    </div>



                    <div style="font-size: 0.875rem; font-family: var(--font-mono); color: #818cf8;">



                        Total Plates: <strong>${item.total_plates || vehicles.length}</strong>



                    </div>



                </div>



                ${vehiclesTableHtml}



            </div>



            ${""}



            <!-- Annotated Video Link (if available) -->



            ${item.output_media_url ? `



            <div style="display: flex; justify-content: flex-end; padding-top: 4px;">



                <a href="${item.output_media_url}" download class="btn btn-primary" style="padding: 7px 16px; font-size: 0.875rem; font-weight: 700; display: inline-flex; align-items: center; gap: 6px;">



                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>



                    Download Annotated Video Output



                </a>



            </div>



            ` : ''}



        `;
    if (modal) modal.style.display = 'flex';
  };
  window.closeForensicBreakdownModal = function () {
    const modal = document.getElementById('forensicBreakdownModal');
    if (modal) modal.style.display = 'none';
  };
  window.clearInvestigationHistory = async function () {
    if (!confirm("Are you sure you want to clear the investigation search audit history?")) {
      return;
    }
    try {
      const res = await fetch('/api/investigation/history/clear', {
        method: 'DELETE'
      });
      if (res.ok) {
        window.investigationSearchesCache = [];
        window.renderInvestigationHistoryUI();
        const navBadge = document.getElementById('historyNavCountBadge');
        const modalBadge = document.getElementById('historyNavCountBadgeModal');
        if (navBadge) navBadge.innerText = 0;
        if (modalBadge) modalBadge.innerText = '0 Searches';
      }
    } catch (err) {
      console.error("Error clearing search history:", err);
    }
  };
  const unifiedMediaInput = document.getElementById('unifiedMediaInput');
  const cameraSnapInput = document.getElementById('cameraSnapInput');
  const unifiedDropzone = document.getElementById('unifiedUploadDropzone');
  if (unifiedMediaInput) {
    unifiedMediaInput.addEventListener('change', e => {
      if (e.target.files && e.target.files.length > 0) {
        window.addFilesToBatchQueue(Array.from(e.target.files));
        unifiedMediaInput.value = '';
      }
    });
  }
  if (cameraSnapInput) {
    cameraSnapInput.addEventListener('change', e => {
      const file = e.target.files[0];
      if (file) {
        handleUnifiedUpload(file);
        cameraSnapInput.value = '';
      }
    });
  }
  setTimeout(window.fetchAndRenderInvestigationHistory, 500);
  if (unifiedDropzone) {
    ['dragenter', 'dragover'].forEach(eventName => {
      unifiedDropzone.addEventListener(eventName, e => {
        e.preventDefault();
        e.stopPropagation();
        unifiedDropzone.style.borderColor = '#6366f1';
        unifiedDropzone.style.background = 'rgba(99, 102, 241, 0.08)';
      });
    });
    ['dragleave', 'drop'].forEach(eventName => {
      unifiedDropzone.addEventListener(eventName, e => {
        e.preventDefault();
        e.stopPropagation();
        unifiedDropzone.style.borderColor = 'var(--border-color)';
        unifiedDropzone.style.background = 'transparent';
      });
    });
    unifiedDropzone.addEventListener('drop', e => {
      const dt = e.dataTransfer;
      const files = dt.files;
      if (files && files.length > 0) {
        window.addFilesToBatchQueue(Array.from(files));
      }
    });
  }
  window.openVehiclesDrawer = function (filter = 'all') {
    window.switchTab('captured-vehicles');
    if (filter) {
      currentDrawerVehFilter = filter;
      updateDrawerVehFilterPills();
    }
    fetchAndRenderDrawerVehicles();
  };
  window.closeVehiclesDrawer = function (e) {
    window.switchTab('dashboard');
  };
  function updateDrawerVehFilterPills() {
    const btnAll = document.getElementById('drawerVehFilterAll');
    const btnHot = document.getElementById('drawerVehFilterHotlist');
    if (btnAll) btnAll.classList.toggle('active', currentDrawerVehFilter === 'all');
    if (btnHot) btnHot.classList.toggle('active', currentDrawerVehFilter === 'hotlist');
  }
  window.setDrawerVehFilter = function (filter) {
    currentDrawerVehFilter = filter;
    updateDrawerVehFilterPills();
    fetchAndRenderDrawerVehicles();
  };
  window.filterDrawerVehicles = function () {
    clearTimeout(drawerVehSearchDebounce);
    drawerVehSearchDebounce = setTimeout(fetchAndRenderDrawerVehicles, 300);
  };
  window.refreshDrawerVehicles = fetchAndRenderDrawerVehicles;
  async function fetchAndRenderDrawerVehicles() {
    const container = document.getElementById('drawerVehiclesListContainer');
    if (!container) return;
    try {
      const searchInput = document.getElementById('drawerVehiclesSearchInput');
      const query = searchInput ? searchInput.value.trim() : '';
      const isHotlist = currentDrawerVehFilter === 'hotlist';
      const distSelect = document.getElementById('filterVehiclesDistrict');
      const opSelect = document.getElementById('filterVehiclesOperator');
      const selectedDist = distSelect ? distSelect.value : 'ALL';
      const selectedOp = opSelect ? opSelect.value : 'ALL';
      let url = `/api/unified/audit-vehicles?limit=100&hotlist_only=${isHotlist}`;
      if (query) url += `&search=${encodeURIComponent(query)}`;
      if (selectedDist && selectedDist !== 'ALL') url += `&district=${encodeURIComponent(selectedDist)}`;
      if (selectedOp && selectedOp !== 'ALL') url += `&operator=${encodeURIComponent(selectedOp)}`;
      const res = await fetch(url);
      const data = await res.json();
      const items = (data.vehicles || []).filter(window.isVisibleVehicleDetection);
      const totalCount = items.length;
      const navBadge = document.getElementById('navDrawerVehiclesCount');
      if (navBadge) navBadge.innerText = totalCount;
      const btnBadge = document.getElementById('btnVehiclesCountBadge');
      if (btnBadge) btnBadge.innerText = `${totalCount}`;
      const fullVehBadge = document.getElementById('fullVehiclesCountBadge');
      if (fullVehBadge) fullVehBadge.innerText = `${totalCount} Vehicles Captured`;
      const kpiVeh = document.getElementById('kpiUnifiedVehicles');
      if (kpiVeh) kpiVeh.innerText = totalCount;
      if (items.length === 0) {
        if (container.dataset.lastSig !== 'empty') {
          container.dataset.lastSig = 'empty';
          container.innerHTML = `



                    <div class="empty-state" style="padding: 40px 16px;">



                        <p style="color: var(--text-primary); font-size: 1.0125rem;">No captured vehicles found.</p>



                        <p style="color: var(--text-muted); font-size: 0.875rem;">Captured detections will appear here.</p>



                    </div>
                `;
        }
        return;
      }
      const drawerVehSig = items.map(v => `${v.id}_${v.captured_at}_${v.confidence}_${v.display_plate || v.plate_number}_${v.is_traffic_violation}_${v.is_hotlist_hit}`).join('|');
      if (container.dataset.lastSig === drawerVehSig) return;
      container.dataset.lastSig = drawerVehSig;
      container.innerHTML = items.map((v, idx) => {
        const pos = idx + 1;
        const isHit = v.is_hotlist_hit;
        const plate = escapeHtml(v.display_plate || v.plate_number || 'UNREADABLE');
        const conf = v.confidence || 0;
        const dateStr = v.captured_at || 'N/A';
        const thumb = v.plate_pic_path || v.vehicle_pic_path || '';
        const isTrafficViol = Boolean(v.is_traffic_violation || v.violation_type);
        const rowClass = isHit ? 'is-hotlist' : isTrafficViol ? 'is-traffic-violation' : '';
        const rowClickAction = isTrafficViol ? 'window.openSplitViolationModal(' + v.id + ')' : 'openCaptureDetailModal(' + v.id + ')';
        return `
                    <div class="captured-list-row ${rowClass}" onclick="${rowClickAction}" style="margin-bottom: 8px;">



                        <div class="captured-list-left">



                            <span class="cap-rank-badge ${pos === 1 ? 'newest' : ''}" style="${pos === 1 ? 'background: #f59e0b; color: #000;' : ''}">#${pos}</span>



                            <div class="cap-row-thumb" style="width: 52px; height: 52px; border-radius: 6px; overflow: hidden; border: 1.5px solid ${isHit ? '#ef4444' : 'var(--border-color)'};">



                                ${thumb ? `<img src="${thumb}" alt="Plate" style="width: 100%; height: 100%; object-fit: contain;">` : '<span style="font-size:0.875rem; color:var(--text-muted); display:flex; align-items:center; justify-content:center; height:100%;">No Crop</span>'}



                            </div>



                            <div style="margin-left: 6px;">



                                <div style="color: #ffffff; font-weight: 700; font-family: var(--font-mono); font-size: 1.0125rem;">${plate}</div>



                                <span class="badge-verified" style="font-size: 0.875rem; margin-top: 2px;">Verified</span>



                            </div>



                        </div>



                        <div class="captured-list-mid">



                            <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">



                                ${isHit ? '<span class="cap-hotlist-tag" style="font-size: 0.875rem; padding: 2px 6px;">CASE HIT</span>' : isTrafficViol ? `<span class="badge-amber-violation" style="font-size: 0.875rem; padding: 2px 6px;">⚠️ ${escapeHtml(v.violation_type || 'TRAFFIC VIOLATION')} (₹${v.violation_fine || 1000})</span>` : ''}



                                <span style="font-size: 0.875rem; font-weight: 600; color: var(--text-primary);">${escapeHtml(v.location || 'CAM-01')}</span>



                            </div>



                            <div class="cap-mid-meta">



                                <span>${dateStr}</span>



                            </div>



                        </div>



                        <div class="captured-list-right">



                            <span class="conf-pill" style="font-size: 0.875rem;">${conf}%</span>



                            <button class="cap-inspect-btn" onclick="event.stopPropagation(); openCaptureDetailModal(${v.id})">Inspect</button>



                            <button class="btn-danger" style="padding: 4px 8px; font-size: 0.875rem;" onclick="event.stopPropagation(); deleteCaptureRecord(${v.id}, '${plate}')">&times;</button>



                        </div>



                    </div>



                `;
      }).join('');
    } catch (err) {
      console.error("Error fetching vehicles drawer:", err);
    }
  }
  window.clearAllCapturedVehicles = async function () {
    try {
      const summaryRes = await fetch('/api/capture-clear-summary');
      if (!summaryRes.ok) throw new Error('Could not load the record count. Please retry.');
      const summary = await summaryRes.json();
      if (!summary.total_count) {
        alert('No captured vehicle data to clear.');
        return;
      }
      if (!confirm(`Clear all ${summary.total_count} captured vehicle records and their photos?\nThis includes hidden and low-confidence captures across all cameras and uploads.\nVehicle Registry and watchlist will stay unchanged.\nThis cannot be undone.`)) return;
      const res = await fetch('/api/captured', {
        method: 'DELETE'
      });
      if (!res.ok) throw new Error('Could not clear vehicle data. Please retry.');
      window._freshVehiclesCache?.clear();
      await fetchAndRenderDrawerVehicles();
      await fetchAndRenderUnifiedLiveFeed();
      await fetchAndRenderCapturedDb();
      alert('Captured vehicle data cleared.');
    } catch (err) {
      alert("Error clearing vehicle captures: " + err.message);
    }
  };
  currentDistrict = currentDistrict || "All Haryana (State HQ)";
  currentAlertsCache = currentAlertsCache || [];
  const notifiedAlertIds = new Set();
  let hasCompletedInitialAlertPoll = false;
  let currentAuditFilterType = "ALL";
  let currentAuditFilterStatus = "ALL";
  let auditSearchDebounce = null;
  let drawerAlertFilter = "all";
  const districtSelector = document.getElementById('districtSelector');
  const headerDistrictLabel = document.getElementById('headerDistrictLabel');
  const alertBellBadge = document.getElementById('alertBellBadge');
  const floatingAlertContainer = document.getElementById('floatingAlertContainer');
  const navAlertAuditCountBadge = document.getElementById('navAlertAuditCountBadge');
  const drawerAlertBackdrop = document.getElementById('drawerAlertBackdrop');
  const drawerAlertListContainer = document.getElementById('drawerAlertListContainer');
  const alertAcknowledgeModal = document.getElementById('alertAcknowledgeModal');
  function playAlertChime() {
    try {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (!AudioContext) return;
      const ctx = new AudioContext();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(880, ctx.currentTime);
      osc.frequency.setValueAtTime(1174.66, ctx.currentTime + 0.15);
      gain.gain.setValueAtTime(0.25, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.55);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.55);
    } catch (e) {}
  }
  window.handleDistrictChange = district => {
    currentDistrict = district || "All Haryana (State HQ)";
    if (headerDistrictLabel) {
      headerDistrictLabel.innerText = currentDistrict.includes("All") ? "Statewide Active" : `${currentDistrict} Active`;
    }
    if (districtSelector && districtSelector.value !== currentDistrict) {
      districtSelector.value = currentDistrict;
    }
    const distFilterInAudit = document.getElementById('auditDistrictFilter');
    if (distFilterInAudit) {
      distFilterInAudit.value = currentDistrict.includes("All") ? "All" : currentDistrict;
    }
    fetchAndRenderVehicleDb();
    fetchActiveAlerts();
    if (viewAlertAudit && viewAlertAudit.style.display !== 'none') {
      window.fetchAndRenderAlertAuditLog();
      window.fetchAndRenderAlertStats();
    }
  };
  let isFetchingActiveAlerts = false;
  async function fetchActiveAlerts() {
    if (isFetchingActiveAlerts) return;
    isFetchingActiveAlerts = true;
    try {
      if (currentUser && (currentUser.role === 'STATE_ADMIN' || currentUser.role === 'DEVELOPER_ADMIN')) {
        if (alertBellBadge && !window.vehicleTrailReviewMode) {
          alertBellBadge.innerText = '0';
          alertBellBadge.style.display = 'none';
        }
        if (navAlertAuditCountBadge) {
          navAlertAuditCountBadge.innerText = '0';
        }
        if (floatingAlertContainer) {
          floatingAlertContainer.innerHTML = '';
        }
        updateCameraAlertGlow([]);
        return;
      }
      const dist = currentDistrict && !currentDistrict.includes("All") ? currentDistrict : currentUser && currentUser.district && currentUser.role !== 'STATE_ADMIN' && currentUser.role !== 'DEVELOPER_ADMIN' ? currentUser.district : '';
      const distParam = dist ? `?district=${encodeURIComponent(dist)}` : '';
      const res = await fetch(`/api/alerts/active${distParam}`);
      if (!res.ok) return;
      const data = await res.json();
      const alerts = data.alerts || [];
      currentAlertsCache = alerts;
      const count = alerts.length;
      if (alertBellBadge && !window.vehicleTrailReviewMode) {
        alertBellBadge.innerText = `${count}`;
        alertBellBadge.style.display = count > 0 ? 'inline-block' : 'none';
      }
      if (navAlertAuditCountBadge) {
        navAlertAuditCountBadge.innerText = `${count}`;
      }
      const nowSec = Date.now() / 1000;
      alerts.forEach(alt => {
        if (alt.status === 'PENDING' && !notifiedAlertIds.has(alt.alert_id)) {
          notifiedAlertIds.add(alt.alert_id);
          let epoch = alt.detection_epoch;
          if (!epoch && alt.detection_timestamp) {
            epoch = new Date(alt.detection_timestamp).getTime() / 1000;
          }
          const isRecent = !epoch || nowSec - epoch < 300;
          if (hasCompletedInitialAlertPoll || isRecent) {
            window.refreshVehicleTrailReview?.();
          }
        }
      });
      hasCompletedInitialAlertPoll = true;
      updateCameraAlertGlow(alerts);
      if (drawerAlertBackdrop && drawerAlertBackdrop.classList.contains('active')) {
        renderDrawerAlerts(alerts);
      }
    } catch (err) {
      console.error("Error fetching active alerts:", err);
    } finally {
      isFetchingActiveAlerts = false;
    }
  }
  const dismissedLiveAlertIds = new Set();
  window.dismissedLiveAlertIds = dismissedLiveAlertIds;
  window.dismissLiveStreamBanner = function (alertId) {
    if (alertId) {
      dismissedLiveAlertIds.add(String(alertId));
    }
    if (window._currentLiveBannerAlertId) {
      dismissedLiveAlertIds.add(String(window._currentLiveBannerAlertId));
    }
    if (window._currentLiveBannerSigKey) {
      dismissedLiveAlertIds.add(String(window._currentLiveBannerSigKey));
    }
    const liveBanner = document.getElementById('liveStreamAlertBanner');
    if (liveBanner) {
      liveBanner.style.display = 'none';
    }
  };
  window.acknowledgeCurrentLiveBannerAlert = function () {
    const targetId = window._currentLiveBannerAlertId;
    window.dismissLiveStreamBanner();
    if (targetId && typeof window.openAlertAckModal === 'function') {
      window.openAlertAckModal(targetId);
    }
  };
  window.focusCurrentLiveBannerCam = function () {
    const camId = window._currentLiveBannerCamId;
    if (camId && typeof window.focusCameraTile === 'function') {
      window.focusCameraTile(camId);
    }
  };
  window.updateCameraAlertGlow = updateCameraAlertGlow;
  function updateCameraAlertGlow(alerts) {
    const LIVE_CAM_IDS = new Set(['CAM-01', 'CAM-02', 'CAM-03', 'CAM-04']);
    const pendingAlerts = (alerts || []).filter(a => a.status === 'PENDING');
    const nowSec = Date.now() / 1000;
    const activeLiveAlerts = pendingAlerts.filter(a => {
      const cid = (a.camera_id || '').trim().toUpperCase();
      if (!LIVE_CAM_IDS.has(cid)) return false;
      let epoch = a.detection_epoch;
      if (!epoch && a.detection_timestamp) {
        epoch = new Date(a.detection_timestamp).getTime() / 1000;
      }
      if (epoch && nowSec - epoch > 600) {
        return false;
      }
      return true;
    });
    const livePendingCams = new Set(activeLiveAlerts.map(a => (a.camera_id || '').trim().toUpperCase()));
    document.querySelectorAll('.cam-tile, .tile-cam').forEach(tile => {
      const rawId = tile.dataset.camid || tile.dataset.camId || tile.getAttribute('data-cam') || tile.id.replace('tile-', '') || '';
      const camId = rawId.trim().toUpperCase();
      if (camId && livePendingCams.has(camId)) {
        tile.classList.add('has-alert-glow');
      } else {
        tile.classList.remove('has-alert-glow');
      }
    });
    const singleViewport = document.getElementById('singleCamViewport');
    if (singleViewport) {
      const currentFocusCam = (focusedCameraId || 'CAM-01').trim().toUpperCase();
      if (currentViewMode === 'focus' && livePendingCams.has(currentFocusCam)) {
        singleViewport.classList.add('has-alert-glow');
      } else {
        singleViewport.classList.remove('has-alert-glow');
      }
    }
    const liveBanner = document.getElementById('liveStreamAlertBanner');
    const liveBannerText = document.getElementById('liveStreamAlertText');
    if (liveBanner) {
      const visibleLiveAlerts = activeLiveAlerts.filter(a => {
        const aid = a.alert_id ? String(a.alert_id) : '';
        const sigKey = `${(a.camera_id || '').trim().toUpperCase()}_${a.detection_epoch || a.detection_timestamp || ''}`;
        return !dismissedLiveAlertIds.has(aid) && !dismissedLiveAlertIds.has(sigKey);
      });
      if (visibleLiveAlerts.length > 0) {
        const topLiveAlt = visibleLiveAlerts[0];
        const aid = topLiveAlt.alert_id ? String(topLiveAlt.alert_id) : '';
        const sigKey = `${(topLiveAlt.camera_id || '').trim().toUpperCase()}_${topLiveAlt.detection_epoch || topLiveAlt.detection_timestamp || ''}`;
        window._currentLiveBannerAlertId = aid || sigKey;
        window._currentLiveBannerSigKey = sigKey;
        window._currentLiveBannerCamId = (topLiveAlt.camera_id || 'CAM-01').trim().toUpperCase();
        const camTag = topLiveAlt.camera_id ? `[${topLiveAlt.camera_id}] ` : '';
        const typeStr = topLiveAlt.alert_type === 'ANPR_HOTLIST' ? 'HOTLIST HIT' : 'SUSPECT SPOTTED';
        const idStr = topLiveAlt.display_name || topLiveAlt.entity_identifier || 'UNKNOWN';
        const distStr = topLiveAlt.spotting_district ? `(${topLiveAlt.spotting_district})` : '';
        if (liveBannerText) {
          liveBannerText.innerText = `${camTag}${typeStr}: ${idStr} ${distStr} - ${topLiveAlt.case_info || 'Realtime Camera Match'}`;
        }
        liveBanner.style.display = 'flex';
      } else {
        window._currentLiveBannerAlertId = null;
        window._currentLiveBannerSigKey = null;
        liveBanner.style.display = 'none';
      }
    }
  }
  window.showFloatingAlert = showFloatingAlert;
  function showFloatingAlert(alt) {
    window.refreshVehicleTrailReview?.();
    return;
    if (!floatingAlertContainer) return;
    const cardId = `floating-alert-${alt.alert_id}`;
    if (document.getElementById(cardId)) return;
    const isHotlist = alt.alert_type === 'ANPR_HOTLIST';
    const typeTitle = isHotlist ? 'VEHICLE HOTLIST HIT' : 'VEHICLE ALERT';
    const timeStr = alt.detection_timestamp ? new Date(alt.detection_timestamp).toLocaleTimeString() : 'Just now';
    const cid = (alt.camera_id || '').trim().toUpperCase();
    const isLiveCam = ['CAM-01', 'CAM-02', 'CAM-03', 'CAM-04'].includes(cid);
    const card = document.createElement('div');
    card.id = cardId;
    card.className = 'floating-alert-card';
    card.innerHTML = `



            <div class="floating-alert-header">



                <div style="display: flex; align-items: center; gap: 6px;">



                    <span class="alert-icon-pulse">🚨</span>



                    <span style="font-weight: 800; font-size: 0.875rem; color: #ef4444; letter-spacing: 0.5px;">${typeTitle}</span>



                </div>



                <div style="display: flex; align-items: center; gap: 8px;">



                    <span style="font-size: 0.875rem; color: #52647c; font-family: var(--font-mono);">${timeStr}</span>



                    <button type="button" class="floating-alert-close" onclick="window.dismissFloatingAlert('${alt.alert_id}')" title="Dismiss" style="background: none; border: none; color: #52647c; font-size: 1.2rem; cursor: pointer; line-height: 1;">&times;</button>



                </div>



            </div>



            <div class="floating-alert-body">



                <div class="floating-alert-target floating-alert-subject">${escapeHtml(alt.entity_identifier)}</div>



                <div class="floating-alert-details floating-alert-desc">${escapeHtml(alt.case_info || alt.display_name)}</div>



                <div class="floating-alert-location floating-alert-meta">



                    <span>${isLiveCam ? '📹 Live Feed' : '📁 Upload Analysis'}: ${escapeHtml(alt.camera_id)} (${escapeHtml(alt.spotting_district)})</span> &bull;



                    <span>🏛️ Origin: ${escapeHtml(alt.origin_district || 'All Haryana')}</span>



                </div>



            </div>



            <div class="floating-alert-actions">



                ${isLiveCam ? `



                <button type="button" class="btn-alert-focus" onclick="window.focusCameraTile('${alt.camera_id}')">



                    📹 Focus ${escapeHtml(alt.camera_id)}



                </button>



                ` : `



                <button type="button" class="btn-alert-focus" onclick="window.switchTab('alert-audit')">



                    📜 Audit Log



                </button>



                `}



                <button type="button" class="btn-alert-ack" onclick="window.openAlertAckModal('${alt.alert_id}')">



                    ⚡ Acknowledge &amp; Act



                </button>



            </div>



        `;
    floatingAlertContainer.prepend(card);
  }
  window.dismissFloatingAlert = alertId => {
    const el = document.getElementById(`floating-alert-${alertId}`);
    if (el) el.remove();
  };
  window.focusCameraTile = camId => {
    window.switchTab('dashboard');
    const cleanCamId = (camId || '').trim().toUpperCase();
    if (['CAM-01', 'CAM-02', 'CAM-03', 'CAM-04'].includes(cleanCamId)) {
      focusedCameraId = cleanCamId;
      if (currentViewMode === 'focus') {
        updateSingleFocusView();
      }
      updateCameraAlertGlow(currentAlertsCache);
      const tile = document.getElementById(`tile-${cleanCamId}`);
      if (tile) {
        tile.scrollIntoView({
          behavior: 'smooth',
          block: 'center'
        });
        tile.style.transition = 'transform 0.2s';
        tile.style.transform = 'scale(1.02)';
        setTimeout(() => {
          if (tile) tile.style.transform = '';
        }, 600);
      }
    } else {
      const camSection = document.getElementById('cameraGridSection') || document.querySelector('.camera-matrix') || document.getElementById('unifiedLivePlayer');
      if (camSection) {
        camSection.scrollIntoView({
          behavior: 'smooth',
          block: 'center'
        });
      }
    }
  };
  window.toggleAlertDrawer = () => {
    if (!drawerAlertBackdrop) return;
    if (drawerAlertBackdrop.classList.contains('active')) {
      window.closeAlertDrawer();
    } else {
      window.openAlertDrawer();
    }
  };
  window.openAlertDrawer = () => {
    if (!drawerAlertBackdrop) return;
    drawerAlertBackdrop.classList.add('active');
    drawerAlertBackdrop.style.display = 'flex';
    fetchActiveAlerts();
  };
  window.closeAlertDrawer = e => {
    if (e && e.target !== drawerAlertBackdrop && !e.target.classList.contains('side-drawer-close')) {
      return;
    }
    if (drawerAlertBackdrop) {
      drawerAlertBackdrop.classList.remove('active');
      setTimeout(() => {
        if (!drawerAlertBackdrop.classList.contains('active')) {
          drawerAlertBackdrop.style.display = 'none';
        }
      }, 250);
    }
  };
  window.refreshActiveAlerts = () => {
    fetchActiveAlerts();
  };
  window.setDrawerAlertFilter = filter => {
    drawerAlertFilter = filter;
    document.querySelectorAll('#drawerAlertBackdrop .filter-btn').forEach(btn => {
      btn.classList.remove('active');
    });
    const activeBtn = document.getElementById(filter === 'all' ? 'drawerAlertFilterAll' : filter === 'pending' ? 'drawerAlertFilterPending' : 'drawerAlertFilterAck');
    if (activeBtn) activeBtn.classList.add('active');
    renderDrawerAlerts(currentAlertsCache);
  };
  window.filterDrawerAlerts = () => {
    renderDrawerAlerts(currentAlertsCache);
  };
  function renderDrawerAlerts(alerts) {
    if (!drawerAlertListContainer) return;
    const search = (document.getElementById('drawerAlertSearchInput')?.value || '').toLowerCase().trim();
    let filtered = alerts || [];
    if (drawerAlertFilter === 'pending') {
      filtered = filtered.filter(a => a.status === 'PENDING');
    } else if (drawerAlertFilter === 'acknowledged') {
      filtered = filtered.filter(a => a.status !== 'PENDING');
    }
    if (search) {
      filtered = filtered.filter(a => (a.entity_identifier || '').toLowerCase().includes(search) || (a.case_info || '').toLowerCase().includes(search) || (a.origin_district || '').toLowerCase().includes(search) || (a.spotting_district || '').toLowerCase().includes(search));
    }
    if (filtered.length === 0) {
      drawerAlertListContainer.innerHTML = `



                <div class="empty-state" style="padding: 40px 20px; text-align: center; color: var(--text-secondary);">



                    <p>No alerts matching criteria.</p>



                </div>



            `;
      return;
    }
    drawerAlertListContainer.innerHTML = filtered.map(a => {
      const isPending = a.status === 'PENDING';
      const isHotlist = a.alert_type === 'ANPR_HOTLIST';
      const typeBadge = isHotlist ? '<span class="audit-status-badge pending">VEHICLE HOTLIST</span>' : '<span class="audit-status-badge intercepted">VEHICLE ALERT</span>';
      const statusBadge = isPending ? '<span class="audit-status-badge pending">PENDING</span>' : `<span class="audit-status-badge ${a.status.toLowerCase()}">${escapeHtml(a.status)}</span>`;
      const timeStr = a.detection_timestamp ? new Date(a.detection_timestamp).toLocaleString() : '--';
      return `



                <div class="captured-list-row ${isPending ? 'is-hotlist' : ''}" style="margin-bottom: 10px; padding: 12px; flex-direction: column; align-items: flex-start; gap: 8px;">



                    <div style="display: flex; justify-content: space-between; align-items: center; width: 100%;">



                        <div style="display: flex; align-items: center; gap: 8px;">



                            ${typeBadge}



                            <span style="font-size: 0.875rem; color: #52647c; font-family: var(--font-mono);">${escapeHtml(a.alert_id)}</span>



                        </div>



                        ${statusBadge}



                    </div>



                    <div style="display: flex; justify-content: space-between; align-items: center; width: 100%;">



                        <div style="font-size: 1.1125rem; font-weight: 800; color: #ffffff;">${escapeHtml(a.entity_identifier)}</div>



                        <div style="font-size: 0.875rem; color: #52647c;">${timeStr}</div>



                    </div>



                    <div style="font-size: 0.875rem; color: #475569;">${escapeHtml(a.case_info || a.display_name)}</div>



                    <div style="display: flex; justify-content: space-between; align-items: center; width: 100%; font-size: 0.875rem; color: #52647c; border-top: 1px solid rgba(255,255,255,0.06); padding-top: 6px;">



                        <span>📍 ${escapeHtml(a.camera_id)} (${escapeHtml(a.spotting_district)}) | Origin: ${escapeHtml(a.origin_district)}</span>



                        ${isPending ? `<button type="button" class="btn-alert-ack" style="padding: 4px 12px; font-size: 0.875rem;" onclick="window.openAlertAckModal('${a.alert_id}')">Acknowledge</button>` : `<span style="color: #10b981; font-weight: 600;">Signed by ${escapeHtml(a.officer_name || 'Officer')} (${a.response_latency_seconds || 0}s)</span>`}



                    </div>



                </div>



            `;
    }).join('');
  }
  window.openAlertAckModal = alertId => {
    let alertData = currentAlertsCache.find(a => a.alert_id === alertId);
    if (!alertData) {
      fetch(`/api/alerts/audit-log?search=${encodeURIComponent(alertId)}`).then(r => r.json()).then(d => {
        const found = (d.logs || []).find(x => x.alert_id === alertId);
        if (found) setupModalWithAlert(found);
      }).catch(() => {});
      return;
    }
    setupModalWithAlert(alertData);
  };
  function setupModalWithAlert(alt) {
    if (!alertAcknowledgeModal) return;
    const idInput = document.getElementById('ackAlertId');
    if (idInput) idInput.value = alt.alert_id;
    const idElem = document.getElementById('ackModalIdentifier');
    if (idElem) idElem.innerText = alt.entity_identifier;
    const caseElem = document.getElementById('ackModalCaseDetails');
    if (caseElem) caseElem.innerText = alt.case_info || alt.display_name || '--';
    const camElem = document.getElementById('ackModalCamera');
    if (camElem) camElem.innerText = alt.camera_id || 'CAM-01';
    const distElem = document.getElementById('ackModalDistrict');
    if (distElem) distElem.innerText = alt.spotting_district || 'Panipat';
    const timeElem = document.getElementById('ackModalTime');
    if (timeElem) timeElem.innerText = alt.detection_timestamp ? new Date(alt.detection_timestamp).toLocaleString() : '--';
    const typeBadge = document.getElementById('ackModalTypeBadge');
    if (typeBadge) {
      typeBadge.innerText = alt.alert_type === 'ANPR_HOTLIST' ? 'VEHICLE HOTLIST' : 'VEHICLE ALERT';
    }
    const distInput = document.getElementById('ackOfficerDistrict');
    if (distInput) {
      distInput.value = currentDistrict && !currentDistrict.includes("All") ? currentDistrict : alt.spotting_district || 'Panipat';
    }
    if (currentUser) {
      const nameInput = document.getElementById('ackOfficerName');
      if (nameInput) nameInput.value = currentUser.full_name || currentUser.username || '';
      const beltInput = document.getElementById('ackBeltNumber');
      if (beltInput) beltInput.value = currentUser.belt_number || (currentUser.username ? `BELT-${currentUser.username.toUpperCase()}` : '');
      if (distInput && currentUser.district && !currentUser.district.includes('All')) {
        distInput.value = currentUser.district;
      }
    }
    alertAcknowledgeModal.style.display = 'flex';
  }
  window.closeAlertAckModal = () => {
    if (alertAcknowledgeModal) alertAcknowledgeModal.style.display = 'none';
  };
  window.submitAlertAck = async event => {
    event.preventDefault();
    const btn = document.getElementById('btnSubmitAckModal');
    if (btn) {
      btn.disabled = true;
      btn.innerText = "Recording Chain of Custody...";
    }
    try {
      const formElem = document.getElementById('alertAckForm');
      const formData = new FormData(formElem);
      const res = await fetch('/api/alerts/acknowledge', {
        method: 'POST',
        body: formData
      });
      const result = await res.json();
      if (res.ok && result.success) {
        const alertId = formData.get('alert_id');
        window.dismissFloatingAlert(alertId);
        window.closeAlertAckModal();
        fetchActiveAlerts();
        if (viewAlertAudit && viewAlertAudit.style.display !== 'none') {
          window.fetchAndRenderAlertAuditLog();
          window.fetchAndRenderAlertStats();
        }
        alert(`Chain of custody recorded successfully! Response Latency: ${result.alert.response_latency_seconds}s.`);
      } else {
        alert(`Failed to acknowledge alert: ${result.detail || 'Server error'}`);
      }
    } catch (err) {
      alert(`Acknowledgment error: ${err.message}`);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerText = "Log Chain of Custody & Clear Alert";
      }
    }
  };
  let currentAuditCategory = 'ALL';
  let currentAuditAction = 'ALL';
  window.auditSelectedDistrict = 'All Haryana';
  window.auditSelectedOperator = 'ALL';
  window.selectAuditDistrictTab = dist => {
    window.auditSelectedDistrict = dist;
    window.auditSelectedOperator = 'ALL';
    document.querySelectorAll('#auditDistrictTabsList .district-tab-btn').forEach(btn => {
      const nameEl = btn.querySelector('.tab-dist-name');
      if (nameEl && nameEl.innerText.trim() === dist) {
        btn.classList.add('active');
      } else if (dist === 'All Haryana' && nameEl && nameEl.innerText.includes('All Haryana')) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    });
    window.renderAlertAuditDistrictCard();
    window.fetchAndRenderAlertAuditLog();
    window.fetchAndRenderAlertStats();
  };
  window.selectAuditOperatorPill = opIdentifier => {
    window.auditSelectedOperator = opIdentifier;
    document.querySelectorAll('#auditOperatorPills .filter-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.auditop === opIdentifier);
    });
    window.fetchAndRenderAlertAuditLog();
    window.fetchAndRenderAlertStats();
  };
  window.renderAlertAuditHierarchy = async () => {
    const activeUser = currentUser || window.currentUser;
    if (!activeUser) return;
    if (activeUser.role === 'OPERATOR') {
      if (viewAlertAudit) viewAlertAudit.style.display = 'none';
      return;
    }
    if (!window.cachedUsersData || window.cachedUsersData.length === 0) {
      try {
        const res = await fetch('/api/users');
        if (res.ok) {
          const d = await res.json();
          window.cachedUsersData = d.users || [];
        }
      } catch (_) {}
    }
    const isSuperAdmin = activeUser.role === 'STATE_ADMIN' || activeUser.role === 'DEVELOPER_ADMIN';
    const distTabsContainer = document.getElementById('auditDistrictTabsContainer');
    const distTabsList = document.getElementById('auditDistrictTabsList');
    if (!isSuperAdmin) {
      if (distTabsContainer) distTabsContainer.style.display = 'none';
      window.auditSelectedDistrict = activeUser.district || 'Panipat';
    } else {
      if (distTabsContainer) distTabsContainer.style.display = 'block';
      if (!window.auditSelectedDistrict) window.auditSelectedDistrict = 'All Haryana';
      if (distTabsList) {
        const statewideOpsCount = (window.cachedUsersData || []).filter(u => u.role === 'OPERATOR').length;
        const isStatewideActive = window.auditSelectedDistrict === 'All Haryana' || window.auditSelectedDistrict === 'All';
        let tabsHtml = `



                    <button type="button" class="district-tab-btn ${isStatewideActive ? 'active' : ''}" onclick="window.selectAuditDistrictTab('All Haryana')">



                        <div class="tab-top-row">



                            <span class="tab-dist-name">🏛️ All Haryana</span>



                            <span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:#818cf8;" title="Statewide HQ"></span>



                        </div>



                        <span class="tab-dist-ops">${statewideOpsCount} Total Field Units</span>



                    </button>



                `;
        tabsHtml += HARYANA_DISTRICTS.map(dist => {
          const opsCount = (window.cachedUsersData || []).filter(u => u.district === dist && u.role === 'OPERATOR').length;
          const hasAdmin = (window.cachedUsersData || []).some(u => u.district === dist && u.role === 'DISTRICT_ADMIN');
          const isActive = dist === window.auditSelectedDistrict;
          const dotColor = hasAdmin ? '#047857' : '#64748b';
          const activeClass = isActive ? 'active' : hasAdmin ? '' : 'has-no-admin';
          return `



                        <button type="button" class="district-tab-btn ${activeClass}" onclick="window.selectAuditDistrictTab('${escapeHtml(dist)}')">



                            <div class="tab-top-row">



                                <span class="tab-dist-name">${escapeHtml(dist)}</span>



                                <span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:${dotColor};" title="${hasAdmin ? 'District Admin Assigned' : 'Vacant'}"></span>



                            </div>



                            <span class="tab-dist-ops">${opsCount} ${opsCount === 1 ? 'Operator' : 'Operators'}</span>



                        </button>



                    `;
        }).join('');
        distTabsList.innerHTML = tabsHtml;
      }
    }
    window.renderAlertAuditDistrictCard();
    window.fetchAndRenderAlertAuditLog();
    window.fetchAndRenderAlertStats();
  };
  window.renderAlertAuditDistrictCard = () => {
    const users = window.cachedUsersData || [];
    const isAllHaryana = window.auditSelectedDistrict === 'All Haryana' || window.auditSelectedDistrict === 'All';
    const distName = isAllHaryana ? 'All Haryana' : window.auditSelectedDistrict;
    const badgeEl = document.getElementById('auditSelectedDistrictBadge');
    const countBadgeEl = document.getElementById('auditOperatorCountBadge');
    const titleEl = document.getElementById('auditSelectedDistrictTitle');
    const pillsContainer = document.getElementById('auditOperatorPills');
    if (badgeEl) {
      badgeEl.innerText = isAllHaryana ? 'ALL HARYANA STATEWIDE HQ' : `${distName.toUpperCase()} DISTRICT HQ`;
    }
    const relevantOps = isAllHaryana ? users.filter(u => u.role === 'OPERATOR') : users.filter(u => u.district === distName && u.role === 'OPERATOR');
    if (countBadgeEl) {
      countBadgeEl.innerText = `${relevantOps.length} Active Duty Officer${relevantOps.length === 1 ? '' : 's'}`;
    }
    if (titleEl) {
      titleEl.innerText = isAllHaryana ? 'Statewide Unified Duty Nakas & Field Officers Audit Archive' : `${distName} District Nakas & Duty Officers Audit Archive`;
    }
    if (pillsContainer) {
      const allActive = !window.auditSelectedOperator || window.auditSelectedOperator === 'ALL';
      let pillsHtml = `



                <button type="button" class="filter-btn ${allActive ? 'active' : ''}" data-auditop="ALL" onclick="window.selectAuditOperatorPill('ALL')">



                    👤 All ${isAllHaryana ? 'Statewide' : distName} Officers



                </button>



            `;
      relevantOps.forEach(op => {
        const identifier = op.full_name || op.username;
        const isSelected = window.auditSelectedOperator === identifier || window.auditSelectedOperator === op.username;
        const beltText = op.belt_number ? ` (${op.belt_number})` : '';
        pillsHtml += `



                    <button type="button" class="filter-btn ${isSelected ? 'active' : ''}" data-auditop="${escapeHtml(identifier)}" onclick="window.selectAuditOperatorPill('${escapeHtml(identifier)}')">



                        👮 ${escapeHtml(op.full_name || op.username)}${escapeHtml(beltText)}



                    </button>



                `;
      });
      pillsContainer.innerHTML = pillsHtml;
    }
  };
  window.setAuditCategoryFilter = cat => {
    currentAuditCategory = cat;
    document.querySelectorAll('#auditCategoryPills .filter-btn').forEach(b => {
      b.classList.toggle('active', b.dataset.auditcat === cat);
    });
    window.fetchAndRenderAlertAuditLog();
  };
  window.setAuditActionFilter = act => {
    currentAuditAction = act;
    document.querySelectorAll('#auditActionFilterPills .filter-btn').forEach(b => {
      b.classList.toggle('active', b.dataset.auditaction === act);
    });
    window.fetchAndRenderAlertAuditLog();
  };
  window.fetchAndRenderAlertAuditLog = async () => {
    const tableBody = document.getElementById('auditTableBody');
    if (!tableBody) return;
    try {
      const searchVal = document.getElementById('auditSearchInput')?.value.trim() || '';
      let distVal = window.auditSelectedDistrict || 'All Haryana';
      if (currentUser && currentUser.role === 'DISTRICT_ADMIN' && currentUser.district) {
        distVal = currentUser.district;
      }
      let url = `/api/alerts/audit-log?limit=150&category=${encodeURIComponent(currentAuditCategory || 'ALL')}`;
      if (distVal && distVal !== 'All' && !distVal.includes('All')) {
        url += `&district=${encodeURIComponent(distVal)}`;
      }
      if (window.auditSelectedOperator && window.auditSelectedOperator !== 'ALL') {
        url += `&operator=${encodeURIComponent(window.auditSelectedOperator)}`;
      }
      if (currentAuditAction && currentAuditAction !== 'ALL') {
        url += `&action_type=${encodeURIComponent(currentAuditAction)}`;
      }
      if (searchVal) {
        url += `&search=${encodeURIComponent(searchVal)}`;
      }
      const res = await fetch(url);
      if (res.status === 403) {
        tableBody.innerHTML = `



                    <tr>



                        <td colspan="10" style="text-align: center; padding: 36px; color: #ef4444; font-weight: bold;">



                            🚫 Access Denied: Operators do not have permission to view Alert Audit Trails.



                        </td>



                    </tr>



                `;
        return;
      }
      if (!res.ok) throw new Error("Failed to load audit trail");
      const data = await res.json();
      const logs = data.logs || [];
      if (data.stats) {
        renderAlertStats(data.stats);
      }
      const exportBtn = document.getElementById('btnExportAlertCsv');
      if (exportBtn) {
        const expParams = [];
        if (distVal && distVal !== 'All' && !distVal.includes('All')) {
          expParams.push(`district=${encodeURIComponent(distVal)}`);
        }
        if (window.auditSelectedOperator && window.auditSelectedOperator !== 'ALL') {
          expParams.push(`operator=${encodeURIComponent(window.auditSelectedOperator)}`);
        }
        exportBtn.href = expParams.length > 0 ? `/api/alerts/export-csv?${expParams.join('&')}` : '/api/alerts/export-csv';
      }
      if (logs.length === 0) {
        tableBody.innerHTML = `



                    <tr>



                        <td colspan="10" style="text-align: center; padding: 36px; color: var(--text-secondary);">



                            No audit logs recorded matching the selected filter criteria.



                        </td>



                    </tr>



                `;
        return;
      }
      tableBody.innerHTML = logs.map(l => {
        const isDbChange = l.audit_category === 'DB_CHANGE';
        const scopeBadge = isDbChange ? '<span class="audit-status-badge recorded">🛠️ DB CHANGE</span>' : '<span class="audit-status-badge pending">🚨 ALERT</span>';
        let actionBadge = '';
        const act = (l.action || '').toUpperCase();
        if (act === 'ADD') {
          actionBadge = '<span class="audit-status-badge added">ADD</span>';
        } else if (act === 'EDIT') {
          actionBadge = '<span class="audit-status-badge edited">EDIT</span>';
        } else if (act === 'DELETE') {
          actionBadge = '<span class="audit-status-badge deleted">DELETE</span>';
        } else if (act === 'PENDING') {
          actionBadge = '<span class="audit-status-badge pending">PENDING</span>';
        } else {
          actionBadge = '<span class="audit-status-badge acknowledged">ACK</span>';
        }
        const detTime = l.timestamp ? new Date(l.timestamp).toLocaleString() : '--';
        const officerInfo = l.officer_name ? `<strong style="color: #fff;">${escapeHtml(l.officer_name)}</strong><br><small style="color: #52647c; font-family: var(--font-mono);">${escapeHtml(l.officer_belt || '')}</small>` : '<span style="color: #64748b;">System / Auto</span>';
        const distInfo = `<span style="color: #0369a1;">${escapeHtml(l.origin_district || l.spotting_district || '--')}</span>`;
        const reasonNotes = escapeHtml(l.reason_remarks || l.action_taken || '--');
        let actionCol = '';
        if (!isDbChange && l.action === 'PENDING') {
          actionCol = `<button type="button" class="btn-alert-ack" style="padding: 4px 10px; font-size: 0.875rem;" onclick="window.openAlertAckModal('${l.id}')">Acknowledge</button>`;
        } else {
          actionCol = `<span style="font-size: 0.875rem; color: #10b981;">&check; Logged</span>`;
        }
        return `



                    <tr>



                        <td style="font-family: var(--font-mono); font-size: 0.875rem; color: #818cf8; font-weight: bold;">${escapeHtml(l.id)}</td>



                        <td style="font-size: 0.875rem; color: #475569; white-space: nowrap;">${detTime}</td>



                        <td>${scopeBadge}</td>



                        <td>${actionBadge}</td>



                        <td style="font-weight: 600; font-size: 0.875rem; color: #475569;">${escapeHtml(l.target_type || '--')}</td>



                        <td>



                            <strong style="color: #fff; font-size: 0.9425rem;">${escapeHtml(l.identifier)}</strong>



                            <div style="font-size: 0.875rem; color: #52647c;">${escapeHtml(l.details || '')}</div>



                        </td>



                        <td style="font-size: 0.875rem;">${officerInfo}</td>



                        <td style="font-size: 0.875rem;">${distInfo}</td>



                        <td style="font-size: 0.875rem; max-width: 220px; color: #475569;">${reasonNotes}</td>



                        <td>${actionCol}</td>



                    </tr>



                `;
      }).join('');
    } catch (err) {
      console.error("Error rendering audit log:", err);
    }
  };
  window.fetchAndRenderAlertStats = async () => {
    try {
      let distVal = window.auditSelectedDistrict || currentDistrict;
      if (currentUser && currentUser.role === 'DISTRICT_ADMIN' && currentUser.district) {
        distVal = currentUser.district;
      }
      const params = [];
      if (distVal && distVal !== 'All' && !distVal.includes('All')) {
        params.push(`district=${encodeURIComponent(distVal)}`);
      }
      if (window.auditSelectedOperator && window.auditSelectedOperator !== 'ALL') {
        params.push(`operator=${encodeURIComponent(window.auditSelectedOperator)}`);
      }
      const qStr = params.length > 0 ? `?${params.join('&')}` : '';
      const res = await fetch(`/api/alerts/stats${qStr}`);
      if (!res.ok) return;
      const stats = await res.json();
      renderAlertStats(stats);
    } catch (e) {}
  };
  function renderAlertStats(s) {
    if (!s) return;
    const statTotal = document.getElementById('auditStatTotal');
    const statPending = document.getElementById('auditStatPending');
    const statAck = document.getElementById('auditStatAck');
    const statLatency = document.getElementById('auditStatLatency');
    if (statTotal) statTotal.innerText = `${s.total_alerts || 0}`;
    if (statPending) statPending.innerText = `${s.pending_alerts || 0}`;
    if (statAck) statAck.innerText = `${s.acknowledged_alerts || 0}`;
    if (statLatency) statLatency.innerText = `${s.avg_response_latency_seconds || 0}s`;
  }
  window.debounceAuditSearch = () => {
    if (auditSearchDebounce) clearTimeout(auditSearchDebounce);
    auditSearchDebounce = setTimeout(() => {
      window.fetchAndRenderAlertAuditLog();
    }, 300);
  };
  window.filterAuditLog = () => {
    window.fetchAndRenderAlertAuditLog();
    window.fetchAndRenderAlertStats();
  };
  window.selectedDistrict = 'Panipat';
  window.cachedUsersData = [];
  const HARYANA_DISTRICTS = ['Ambala', 'Bhiwani', 'Charkhi Dadri', 'Faridabad', 'Fatehabad', 'Gurugram', 'Hisar', 'Jhajjar', 'Jind', 'Kaithal', 'Karnal', 'Kurukshetra', 'Mahendragarh', 'Nuh', 'Palwal', 'Panchkula', 'Panipat', 'Rewari', 'Rohtak', 'Sirsa', 'Sonipat', 'Yamunanagar'];
  window.fetchAndRenderUsersList = async () => {
    const tableBody = document.getElementById('userMgmtTableBody');
    const stateTabsContainer = document.getElementById('stateAdminDistrictTabsContainer');
    const tabsList = document.getElementById('districtTabsList');
    const pageTitle = document.getElementById('userMgmtTitle');
    const pageSubtitle = document.getElementById('userMgmtSubtitle');
    const btnCreateText = document.getElementById('btnCreateUserText');
    if (!currentUser) {
      try {
        const meRes = await fetch('/api/auth/me');
        if (meRes.ok) currentUser = await meRes.json();
      } catch (_) {}
    }
    const isStateAdmin = currentUser && (currentUser.role === 'STATE_ADMIN' || currentUser.role === 'DEVELOPER_ADMIN');
    const isDistrictAdmin = currentUser && currentUser.role === 'DISTRICT_ADMIN';
    if (isStateAdmin) {
      if (pageTitle) pageTitle.innerText = 'Haryana Police Officer Accounts Administration';
      if (pageSubtitle) if (pageSubtitle) pageSubtitle.style.display = 'none';
      if (btnCreateText) btnCreateText.innerText = '+ Create District Admin';
      if (stateTabsContainer) stateTabsContainer.style.display = 'block';
    } else if (isDistrictAdmin) {
      if (pageTitle) pageTitle.innerText = `${currentUser.district} District Accounts & Operators`;
      if (pageSubtitle) if (pageSubtitle) pageSubtitle.style.display = 'none';
      if (btnCreateText) btnCreateText.innerText = '+ Create Operator';
      if (stateTabsContainer) stateTabsContainer.style.display = 'none';
      window.selectedDistrict = currentUser.district;
    }
    try {
      const res = await fetch('/api/users/list');
      if (!res.ok) {
        if (res.status === 401) {
          window.location.href = '/login';
          return;
        }
        throw new Error('Failed to fetch officer accounts');
      }
      const data = await res.json();
      window.cachedUsersData = data.users || [];
      if (isStateAdmin && tabsList) {
        const districtsWithUsers = [...new Set(window.cachedUsersData.map(u => u.district).filter(Boolean))];
        if (!districtsWithUsers.includes(window.selectedDistrict) && districtsWithUsers.includes('Panipat')) {
          window.selectedDistrict = 'Panipat';
        } else if (!districtsWithUsers.includes(window.selectedDistrict) && districtsWithUsers.length > 0) {
          window.selectedDistrict = districtsWithUsers[0];
        }
        tabsList.innerHTML = HARYANA_DISTRICTS.map(dist => {
          const opsCount = window.cachedUsersData.filter(u => u.district === dist && u.role === 'OPERATOR').length;
          const hasAdmin = window.cachedUsersData.some(u => u.district === dist && u.role === 'DISTRICT_ADMIN');
          const isActive = dist === window.selectedDistrict;
          const dotColor = hasAdmin ? '#047857' : '#64748b';
          const activeClass = isActive ? 'active' : hasAdmin ? '' : 'has-no-admin';
          return `



                        <button type="button" class="district-tab-btn ${activeClass}" onclick="window.selectDistrictTab('${escapeHtml(dist)}')">



                            <div class="tab-top-row">



                                <span class="tab-dist-name">${escapeHtml(dist)}</span>



                                <span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:${dotColor};" title="${hasAdmin ? 'District Admin Assigned' : 'Vacant'}"></span>



                            </div>



                            <span class="tab-dist-ops">${opsCount} ${opsCount === 1 ? 'Operator' : 'Operators'}</span>



                        </button>



                    `;
        }).join('');
      }
      window.renderDistrictHierarchyView(window.selectedDistrict);
    } catch (err) {
      console.error("Error fetching users list:", err);
      if (tableBody) {
        tableBody.innerHTML = `



                    <tr>



                        <td colspan="5" style="text-align: center; padding: 28px; color: #ef4444;">



                            ${escapeHtml(err.message || 'Failed to load officer accounts.')}



                        </td>



                    </tr>



                `;
      }
    }
  };
  window.selectDistrictTab = districtName => {
    window.selectedDistrict = districtName;
    document.querySelectorAll('.district-tab-btn').forEach(btn => {
      const nameEl = btn.querySelector('.tab-dist-name');
      if (nameEl && nameEl.innerText.trim() === districtName) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    });
    window.renderDistrictHierarchyView(districtName);
  };
  window.renderDistrictHierarchyView = districtName => {
    const users = window.cachedUsersData || [];
    const activeUser = currentUser || window.currentUser;
    const isStateAdmin = activeUser && (activeUser.role === 'STATE_ADMIN' || activeUser.role === 'DEVELOPER_ADMIN');
    let distAdmin = users.find(u => u.district === districtName && u.role === 'DISTRICT_ADMIN');
    if (!distAdmin && activeUser && activeUser.role === 'DISTRICT_ADMIN' && activeUser.district === districtName) {
      distAdmin = activeUser;
    }
    const operators = users.filter(u => u.district === districtName && u.role === 'OPERATOR');
    const badgeEl = document.getElementById('cardDistrictBadge');
    const statusBadgeEl = document.getElementById('cardAdminStatusBadge');
    const nameEl = document.getElementById('cardAdminFullName');
    const beltEl = document.getElementById('cardAdminBelt');
    const userEl = document.getElementById('cardAdminUsername');
    const stationEl = document.getElementById('cardAdminStation');
    const nakasStatEl = document.getElementById('cardStatNakas');
    const opsStatEl = document.getElementById('cardStatOperators');
    const actionWrapEl = document.getElementById('cardAdminActionWrap');
    if (badgeEl) badgeEl.innerText = `${(districtName || 'Panipat').toUpperCase()} DISTRICT HQ`;
    const nakas = [...new Set(operators.map(o => o.station).filter(Boolean))];
    const nakaCount = nakas.length > 0 ? nakas.length : operators.length > 0 ? operators.length : 0;
    if (nakasStatEl) nakasStatEl.innerText = `${nakaCount} ${nakaCount === 1 ? 'Checkpoint' : 'Checkpoints'}`;
    if (opsStatEl) opsStatEl.innerText = `${operators.length} Assigned`;
    if (distAdmin) {
      if (statusBadgeEl) {
        statusBadgeEl.innerHTML = `<span style="display:inline-block;width:6px;height:6px;border-radius:50%;background:#f8fafc;"></span> Active In-Service`;
        statusBadgeEl.style.color = '#047857';
      }
      if (nameEl) nameEl.innerText = distAdmin.full_name;
      if (beltEl) beltEl.innerText = distAdmin.belt_number || 'N/A';
      if (userEl) userEl.innerText = distAdmin.username;
      if (stationEl) stationEl.innerText = distAdmin.station || `SP Office, ${districtName}`;
      if (actionWrapEl) {
        if (isStateAdmin) {
          actionWrapEl.innerHTML = `



                        <button type="button" class="btn btn-secondary" style="padding: 6px 12px; font-size: 0.875rem; color: #92400e; border-color: rgba(245, 158, 11, 0.4);" onclick="window.openResetPasswordModal('${escapeHtml(distAdmin.username)}', '${escapeHtml(distAdmin.full_name)}', 'District Admin')">



                            🔑 Reset Password



                        </button>



                    `;
        } else {
          actionWrapEl.innerHTML = ``;
        }
      }
    } else {
      if (statusBadgeEl) {
        statusBadgeEl.innerHTML = `<span style="display:inline-block;width:6px;height:6px;border-radius:50%;background:#f59e0b;"></span> Vacant / Not Assigned`;
        statusBadgeEl.style.color = '#f59e0b';
      }
      if (nameEl) nameEl.innerText = `No District Admin Registered`;
      if (beltEl) beltEl.innerText = `--`;
      if (userEl) userEl.innerText = `--`;
      if (stationEl) stationEl.innerText = `SP Office, ${districtName}`;
      if (actionWrapEl) {
        if (isStateAdmin) {
          actionWrapEl.innerHTML = `



                        <button type="button" class="btn btn-primary" style="padding: 6px 14px; font-size: 0.875rem; font-weight: 700; background: linear-gradient(135deg, #4f46e5 0%, #6366f1 100%);" onclick="window.openCreateUserModalForDistrict('${escapeHtml(districtName)}')">



                            + Create District Admin



                        </button>



                    `;
        } else {
          actionWrapEl.innerHTML = ``;
        }
      }
    }
    const tableBody = document.getElementById('userMgmtTableBody');
    const opsCountBadge = document.getElementById('operatorsTableCount');
    if (opsCountBadge) opsCountBadge.innerText = `${operators.length} ${operators.length === 1 ? 'Operator' : 'Operators'} Assigned`;
    if (!tableBody) return;
    if (operators.length === 0) {
      tableBody.innerHTML = `



                <tr>



                    <td colspan="5" style="text-align: center; padding: 36px 20px; color: var(--text-secondary);">



                        <div style="font-size: 1.3rem; margin-bottom: 6px;">👮‍♂️</div>



                        <div style="font-weight: 600; color: #475569; margin-bottom: 4px;">No ground operators registered for ${escapeHtml(districtName)} district yet.</div>



                        <div style="font-size: 0.875rem; color: #64748b; margin-bottom: 14px;">Operators created by the District Admin or State Admin will appear here with their assigned checkpoints.</div>



                        <button type="button" class="btn btn-secondary" style="padding: 6px 14px; font-size: 0.875rem;" onclick="window.openCreateUserModalForDistrict('${escapeHtml(districtName)}')">



                            + Create Operator for ${escapeHtml(districtName)}



                        </button>



                    </td>



                </tr>



            `;
      return;
    }
    tableBody.innerHTML = operators.map(op => {
      const canReset = currentUser?.role === 'STATE_ADMIN' || currentUser?.role === 'DEVELOPER_ADMIN' || currentUser?.role === 'DISTRICT_ADMIN' && currentUser.district === op.district;
      const opDataJson = JSON.stringify(op).replace(/"/g, '&quot;');
      return `



                <tr>



                    <td>



                        <div style="font-weight: 700; color: #ffffff; font-size: 0.9225rem;">${escapeHtml(op.full_name)}</div>



                        <div style="font-family: var(--font-mono); color: #818cf8; font-size: 0.875rem;">${escapeHtml(op.username)}</div>



                    </td>



                    <td>



                        <span class="operator-badge-naka">



                            <span>📍</span> <span>${escapeHtml(op.station || 'Assigned Naka Post')}</span>



                        </span>



                    </td>



                    <td>



                        <span style="font-family: var(--font-mono); color: #475569; font-weight: 600; font-size: 0.875rem;">${escapeHtml(op.belt_number || '--')}</span>



                    </td>



                    <td>



                        <span style="color: #047857; font-weight: 700; font-size: 0.875rem; display: inline-flex; align-items: center; gap: 4px;">



                            <span style="display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: #f8fafc;"></span> Active Shift



                        </span>



                    </td>



                    <td style="text-align: right;">



                        <div style="display: flex; align-items: center; justify-content: flex-end; gap: 8px;">



                            <button type="button" class="btn-view-operator-details" onclick="window.openOperatorDetailsModal(${opDataJson})">



                                👁️ View Details



                            </button>



                            ${canReset ? `



                            <button type="button" class="btn btn-secondary" style="padding: 4px 8px; font-size: 0.875rem; color: #92400e; border-color: rgba(245, 158, 11, 0.4);" title="Reset Password" onclick="window.openResetPasswordModal('${escapeHtml(op.username)}', '${escapeHtml(op.full_name)}', 'Operator')">



                                🔑



                            </button>



                            ` : ''}



                        </div>



                    </td>



                </tr>



            `;
    }).join('');
  };
  window.openOperatorDetailsModal = op => {
    if (!op) return;
    const modal = document.getElementById('operatorDetailsModal');
    const nameEl = document.getElementById('modalOpFullName');
    const roleSubEl = document.getElementById('modalOpRoleSub');
    const beltEl = document.getElementById('modalOpBelt');
    const distEl = document.getElementById('modalOpDistrict');
    const nakaTextEl = document.getElementById('modalOpNakaText');
    const camEl = document.getElementById('modalOpCam');
    const userEl = document.getElementById('modalOpUsername');
    const schedEl = document.getElementById('modalOpDutySchedule');
    if (nameEl) nameEl.innerText = op.full_name || 'Ground Officer';
    if (roleSubEl) roleSubEl.innerText = `Duty Officer • ${op.district || 'Haryana'} Police`;
    if (beltEl) beltEl.innerText = op.belt_number || 'N/A';
    if (distEl) distEl.innerText = `${op.district} District`;
    if (nakaTextEl) nakaTextEl.innerText = op.station || 'General Checkpoint / Thana';
    if (camEl) camEl.innerText = `Surveillance Node: Naka Live RTSP Feeds & Camera Channels Active`;
    if (userEl) userEl.innerText = op.username;
    if (schedEl) schedEl.innerText = 'Active Shift (08:00 - 16:00)';
    if (modal) modal.style.display = 'flex';
  };
  window.closeOperatorDetailsModal = () => {
    const modal = document.getElementById('operatorDetailsModal');
    if (modal) modal.style.display = 'none';
  };
  window.openCreateUserModalForDistrict = districtName => {
    window.selectedDistrict = districtName;
    window.openCreateUserModal();
  };
  window.openCreateUserModal = async () => {
    const modal = document.getElementById('createUserModal');
    const roleSelect = document.getElementById('createOfficerRole');
    const districtSelect = document.getElementById('createOfficerDistrict');
    const title = document.getElementById('createUserModalTitle');
    const errBox = document.getElementById('createUserErrorMsg');
    const form = document.getElementById('createUserForm');
    const stationInput = document.getElementById('createOfficerStation');
    if (form) form.reset();
    if (errBox) errBox.style.display = 'none';
    if (!currentUser) {
      try {
        const meRes = await fetch('/api/auth/me');
        if (meRes.ok) {
          currentUser = await meRes.json();
        }
      } catch (_) {}
    }
    const isDistrictAdmin = currentUser && currentUser.role === 'DISTRICT_ADMIN';
    if (roleSelect) {
      if (isDistrictAdmin) {
        roleSelect.innerHTML = `



                    <option value="OPERATOR" selected>Operator (Thana / Naka Post / Mobile PCR)</option>



                `;
        if (districtSelect) {
          districtSelect.value = currentUser.district;
          districtSelect.disabled = true;
        }
        if (title) title.innerText = `Create Operator Account (${currentUser.district} District)`;
        if (stationInput) stationInput.placeholder = 'e.g. Sector 18 Toll Plaza Naka, Panipat';
      } else {
        roleSelect.innerHTML = `



                    <option value="DISTRICT_ADMIN" selected>District Admin (SP Office / Control Room)</option>



                    <option value="OPERATOR">Operator (Duty Officer / Naka Post)</option>



                `;
        if (districtSelect) {
          districtSelect.disabled = false;
          if (window.selectedDistrict) {
            districtSelect.value = window.selectedDistrict;
          }
        }
        if (title) title.innerText = 'Create District Admin / Officer Account';
        if (stationInput) stationInput.placeholder = 'e.g. SP Office / District Police Headquarters';
      }
    }
    if (modal) modal.style.display = 'flex';
  };
  window.closeCreateUserModal = () => {
    const modal = document.getElementById('createUserModal');
    if (modal) modal.style.display = 'none';
  };
  window.handleCreateUserRoleChange = () => {};
  window.submitCreateUser = async e => {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    const fullName = document.getElementById('createOfficerFullName')?.value?.trim();
    const belt = document.getElementById('createOfficerBelt')?.value?.trim();
    const username = document.getElementById('createOfficerUsername')?.value?.trim();
    const password = document.getElementById('createOfficerPassword')?.value;
    const roleSelect = document.getElementById('createOfficerRole');
    const role = roleSelect?.value || (currentUser?.role === 'DISTRICT_ADMIN' ? 'OPERATOR' : 'DISTRICT_ADMIN');
    const districtSelect = document.getElementById('createOfficerDistrict');
    const district = currentUser?.role === 'DISTRICT_ADMIN' ? currentUser.district : districtSelect?.value || 'Panipat';
    const station = document.getElementById('createOfficerStation')?.value?.trim() || 'General Duty';
    const errBox = document.getElementById('createUserErrorMsg');
    const submitBtn = document.getElementById('btnSubmitCreateUser');
    if (!fullName || !belt || !username || !password) {
      if (errBox) {
        errBox.style.display = 'block';
        errBox.innerText = 'All marked fields are mandatory.';
      }
      return;
    }
    if (password.length < 4) {
      if (errBox) {
        errBox.style.display = 'block';
        errBox.innerText = 'Password must be at least 4 characters.';
      }
      return;
    }
    try {
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerText = 'Creating account...';
      }
      if (errBox) errBox.style.display = 'none';
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 15000);
      const res = await fetch('/api/users/create', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        signal: controller.signal,
        body: JSON.stringify({
          username,
          password,
          full_name: fullName,
          belt_number: belt,
          role,
          district,
          station
        })
      });
      clearTimeout(timeoutId);
      let data = {};
      try {
        data = await res.json();
      } catch (_) {
        data = {
          detail: `Server returned HTTP status ${res.status}`
        };
      }
      if (!res.ok) {
        throw new Error(data.detail || `Failed to create account (Status: ${res.status}).`);
      }
      window.closeCreateUserModal();
      const createdName = data.user?.full_name || fullName;
      const createdUser = data.user?.username || username;
      window.showToast(`Account for ${createdName} (${createdUser}) created successfully!`, 'success');
      await window.fetchAndRenderUsersList();
    } catch (err) {
      console.error("Error creating officer account:", err);
      if (errBox) {
        errBox.style.display = 'block';
        if (err.name === 'AbortError') {
          errBox.innerText = 'Server request timed out after 15 seconds. Please verify the backend is running.';
        } else {
          errBox.innerText = err.message || 'Error creating account.';
        }
      }
    } finally {
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.innerText = 'Save Officer Account';
      }
    }
  };
  window.openResetPasswordModal = (username, fullName, role) => {
    const modal = document.getElementById('resetPasswordModal');
    const targetInput = document.getElementById('resetTargetUsername');
    const displayInfo = document.getElementById('resetTargetDisplayInfo');
    const passInput = document.getElementById('resetNewPassword');
    const errBox = document.getElementById('resetPasswordErrorMsg');
    if (targetInput) targetInput.value = username;
    if (displayInfo) displayInfo.innerText = `${fullName} (${username}) - [${role}]`;
    if (passInput) passInput.value = '';
    if (errBox) errBox.style.display = 'none';
    if (modal) modal.style.display = 'flex';
  };
  window.closeResetPasswordModal = () => {
    const modal = document.getElementById('resetPasswordModal');
    if (modal) modal.style.display = 'none';
  };
  window.submitResetPassword = async e => {
    e.preventDefault();
    const targetUsername = document.getElementById('resetTargetUsername')?.value;
    const newPassword = document.getElementById('resetNewPassword')?.value;
    const errBox = document.getElementById('resetPasswordErrorMsg');
    if (!newPassword || newPassword.length < 6) {
      if (errBox) {
        errBox.style.display = 'block';
        errBox.innerText = 'Password must be at least 6 characters.';
      }
      return;
    }
    try {
      if (errBox) errBox.style.display = 'none';
      const res = await fetch('/api/users/reset-password', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          target_username: targetUsername,
          new_password: newPassword
        })
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Password reset failed.');
      }
      window.closeResetPasswordModal();
      alert(`Password for officer "${targetUsername}" has been reset successfully.`);
    } catch (err) {
      if (errBox) {
        errBox.style.display = 'block';
        errBox.innerText = err.message || 'Error resetting password.';
      }
    }
  };
  window.toggleHeaderAccountMenu = function (e) {
    if (e) e.stopPropagation();
    const menu = document.getElementById('headerAccountDropdownMenu');
    const btn = document.getElementById('headerAccountBtn');
    if (!menu) return;
    const isOpen = menu.style.display === 'block';
    if (isOpen) {
      menu.style.display = 'none';
      btn?.classList.remove('active');
      btn?.setAttribute('aria-expanded', 'false');
    } else {
      menu.style.display = 'block';
      btn?.classList.add('active');
      btn?.setAttribute('aria-expanded', 'true');
    }
  };
  window.closeHeaderAccountMenu = function () {
    const menu = document.getElementById('headerAccountDropdownMenu');
    const btn = document.getElementById('headerAccountBtn');
    if (menu) menu.style.display = 'none';
    if (btn) {
      btn.classList.remove('active');
      btn.setAttribute('aria-expanded', 'false');
    }
  };
  document.addEventListener('click', function (e) {
    const wrap = document.getElementById('headerAccountWrap');
    if (wrap && !wrap.contains(e.target)) {
      window.closeHeaderAccountMenu();
    }
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      window.closeHeaderAccountMenu();
    }
  });
  window.handleLogout = async () => {
    try {
      const viewport = document.getElementById('anprInspectionViewport');
      if (viewport) viewport.style.display = 'none';
      const inspectionContent = document.getElementById('anprInspectionContent');
      if (inspectionContent) inspectionContent.innerHTML = '';
      const dlBtn = document.getElementById('btnDownloadAnnotatedMedia');
      if (dlBtn) dlBtn.style.display = 'none';
      currentResults = null;
      currentUser = null;
      await fetch('/api/auth/logout', {
        method: 'POST'
      });
    } catch (e) {}
    window.location.href = '/login';
  };
  window.openDeleteModal = (type, id, identifier) => {
    const modal = document.getElementById('deleteReasonModal');
    const typeInput = document.getElementById('deleteTargetType');
    const idInput = document.getElementById('deleteTargetId');
    const infoBox = document.getElementById('deleteTargetInfo');
    const refInput = document.getElementById('deleteReferenceNumber');
    const notesInput = document.getElementById('deleteDetailedNotes');
    const errBox = document.getElementById('deleteModalError');
    if (typeInput) typeInput.value = type;
    if (idInput) idInput.value = id;
    if (infoBox) infoBox.innerText = `[${""}] ${identifier}`;
    if (refInput) refInput.value = '';
    if (notesInput) notesInput.value = '';
    if (errBox) errBox.style.display = 'none';
    if (modal) modal.style.display = 'flex';
  };
  window.closeDeleteReasonModal = () => {
    const modal = document.getElementById('deleteReasonModal');
    if (modal) modal.style.display = 'none';
  };
  window.submitDeleteWithReason = async e => {
    e.preventDefault();
    const type = document.getElementById('deleteTargetType')?.value;
    const id = document.getElementById('deleteTargetId')?.value;
    const category = document.getElementById('deleteReasonCategory')?.value || 'Official Purge';
    const refNum = document.getElementById('deleteReferenceNumber')?.value?.trim() || '';
    const notes = document.getElementById('deleteDetailedNotes')?.value?.trim() || '';
    const errBox = document.getElementById('deleteModalError');
    const submitBtn = document.getElementById('btnConfirmDeleteReason');
    if (!refNum) {
      if (errBox) {
        errBox.style.display = 'block';
        errBox.innerText = 'Case / FIR / Court Order Reference Number is mandatory.';
      }
      return;
    }
    const fullReason = `${category} | Ref: ${refNum}${notes ? ` | Notes: ${notes}` : ''}`;
    try {
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerText = 'Purging record...';
      }
      if (errBox) errBox.style.display = 'none';
      let url = '';
      if (type === 'VEHICLE') {
        url = `/api/vehicles/${id}?reason=${encodeURIComponent(fullReason)}`;
      }
      const res = await fetch(url, {
        method: 'DELETE'
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || 'Failed to delete record');
      }
      window.closeDeleteReasonModal();
      if (type === 'VEHICLE') {
        await fetchAndRenderVehicleDb();
      } else {
        await null;
      }
    } catch (err) {
      if (errBox) {
        errBox.style.display = 'block';
        errBox.innerText = err.message || 'Deletion error occurred.';
      }
    } finally {
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.innerText = 'Purge Record & Write Audit Log';
      }
    }
  };
  window.handleVehicleDbDistrictFilter = district => {
    fetchAndRenderVehicleDb();
  };
  function setupSearchableDistrictSelect(selectEl) {
    if (!selectEl || selectEl.dataset.sdsInitialized === 'true') return;
    selectEl.dataset.sdsInitialized = 'true';
    selectEl.style.display = 'none';
    const container = document.createElement('div');
    container.className = 'sds-container';
    container.tabIndex = 0;
    const trigger = document.createElement('div');
    trigger.className = 'sds-trigger';
    const labelSpan = document.createElement('span');
    labelSpan.className = 'sds-label-text';
    const selectedOpt = selectEl.options[selectEl.selectedIndex] || selectEl.options[0];
    labelSpan.textContent = selectedOpt ? selectedOpt.textContent : 'Select District';
    const arrow = document.createElement('span');
    arrow.className = 'sds-arrow';
    arrow.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"></polyline></svg>`;
    trigger.appendChild(labelSpan);
    trigger.appendChild(arrow);
    container.appendChild(trigger);
    const dropdown = document.createElement('div');
    dropdown.className = 'sds-dropdown';
    const optionsList = document.createElement('div');
    optionsList.className = 'sds-options-list';
    const noMatch = document.createElement('div');
    noMatch.className = 'sds-no-match';
    noMatch.style.display = 'none';
    noMatch.textContent = 'No matching districts';
    const optionElements = [];
    Array.from(selectEl.options).forEach(opt => {
      const item = document.createElement('div');
      item.className = 'sds-option' + (opt.selected ? ' selected' : '');
      item.dataset.value = opt.value;
      item.dataset.text = opt.textContent;
      item.textContent = opt.textContent;
      item.addEventListener('click', e => {
        e.stopPropagation();
        selectOption(opt.value, opt.textContent);
      });
      optionsList.appendChild(item);
      optionElements.push(item);
    });
    const originalOrder = [...optionElements];
    optionsList.appendChild(noMatch);
    dropdown.appendChild(optionsList);
    container.appendChild(dropdown);
    if (selectEl.parentNode) {
      selectEl.parentNode.insertBefore(container, selectEl.nextSibling);
    }
    let isOpen = false;
    let typeBuffer = '';
    let lastKeyTime = 0;
    let highlightedIndex = -1;
    function openDropdown() {
      if (isOpen) return;
      isOpen = true;
      clearFilter();
      const rect = trigger.getBoundingClientRect();
      const spaceBelow = window.innerHeight - rect.bottom;
      if (spaceBelow < 280 && rect.top > 280) {
        dropdown.style.top = 'auto';
        dropdown.style.bottom = 'calc(100% + 5px)';
      } else {
        dropdown.style.top = 'calc(100% + 5px)';
        dropdown.style.bottom = 'auto';
      }
      dropdown.classList.add('show');
      trigger.classList.add('open');
      container.focus();
    }
    function closeDropdown() {
      if (!isOpen) return;
      isOpen = false;
      dropdown.classList.remove('show');
      trigger.classList.remove('open');
      clearFilter();
    }
    function toggleDropdown() {
      if (isOpen) closeDropdown(); else openDropdown();
    }
    function selectOption(val, text) {
      selectEl.value = val;
      labelSpan.textContent = text;
      optionElements.forEach(el => {
        el.classList.toggle('selected', el.dataset.value === val);
      });
      closeDropdown();
      selectEl.dispatchEvent(new Event('change', {
        bubbles: true
      }));
      if (selectEl.id === 'vehicleDbDistrictFilter' && typeof window.handleVehicleDbDistrictFilter === 'function') {
        window.handleVehicleDbDistrictFilter(val);
      } else if (typeof selectEl.onchange === 'function') {
        selectEl.onchange();
      }
    }
    function clearFilter() {
      typeBuffer = '';
      noMatch.style.display = 'none';
      highlightedIndex = -1;
      originalOrder.forEach(el => {
        el.classList.remove('hidden', 'highlighted');
        el.textContent = el.dataset.text;
        optionsList.appendChild(el);
      });
      optionsList.appendChild(noMatch);
    }
    function applyFilter() {
      const buf = typeBuffer.toLowerCase().trim();
      if (!buf) {
        clearFilter();
        return;
      }
      const startsWith = [];
      const contains = [];
      optionElements.forEach(el => {
        const t = el.dataset.text.toLowerCase();
        const v = el.dataset.value.toLowerCase();
        if (t.startsWith(buf) || v.startsWith(buf)) {
          startsWith.push(el);
        } else if (t.includes(buf) || v.includes(buf)) {
          contains.push(el);
        }
      });
      const matchedList = startsWith.length > 0 ? startsWith : contains;
      const matchedSet = new Set(matchedList);
      optionElements.forEach(el => {
        if (matchedSet.has(el)) {
          el.classList.remove('hidden');
          el.textContent = el.dataset.text;
        } else {
          el.classList.add('hidden');
          el.classList.remove('highlighted');
        }
      });
      matchedList.forEach(el => optionsList.appendChild(el));
      optionElements.filter(el => !matchedSet.has(el)).forEach(el => optionsList.appendChild(el));
      optionsList.appendChild(noMatch);
      if (matchedList.length === 0) {
        noMatch.style.display = 'block';
        noMatch.textContent = `No matching districts`;
        highlightedIndex = -1;
      } else {
        noMatch.style.display = 'none';
        highlightedIndex = optionElements.indexOf(matchedList[0]);
        updateHighlight();
        optionsList.scrollTop = 0;
      }
    }
    function updateHighlight() {
      optionElements.forEach((el, idx) => {
        el.classList.toggle('highlighted', idx === highlightedIndex);
      });
    }
    trigger.addEventListener('click', e => {
      e.stopPropagation();
      toggleDropdown();
    });
    document.addEventListener('click', e => {
      if (!container.contains(e.target)) {
        closeDropdown();
      }
    });
    container.addEventListener('keydown', e => {
      const now = Date.now();
      if (e.key === 'Tab') {
        closeDropdown();
        return;
      }
      if (e.key === 'Escape') {
        closeDropdown();
        return;
      }
      if (e.key === 'Enter') {
        e.preventDefault();
        if (isOpen && highlightedIndex >= 0 && optionElements[highlightedIndex]) {
          const el = optionElements[highlightedIndex];
          selectOption(el.dataset.value, el.dataset.text);
        } else if (!isOpen) {
          openDropdown();
        }
        return;
      }
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        if (!isOpen) {
          openDropdown();
          return;
        }
        const visible = optionElements.map((el, i) => ({
          el,
          i
        })).filter(item => !item.el.classList.contains('hidden'));
        if (visible.length === 0) return;
        const currentPos = visible.findIndex(item => item.i === highlightedIndex);
        const nextPos = (currentPos + 1) % visible.length;
        highlightedIndex = visible[nextPos].i;
        updateHighlight();
        visible[nextPos].el.scrollIntoView({
          block: 'nearest'
        });
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        if (!isOpen) {
          openDropdown();
          return;
        }
        const visible = optionElements.map((el, i) => ({
          el,
          i
        })).filter(item => !item.el.classList.contains('hidden'));
        if (visible.length === 0) return;
        const currentPos = visible.findIndex(item => item.i === highlightedIndex);
        const prevPos = currentPos <= 0 ? visible.length - 1 : currentPos - 1;
        highlightedIndex = visible[prevPos].i;
        updateHighlight();
        visible[prevPos].el.scrollIntoView({
          block: 'nearest'
        });
        return;
      }
      if (e.key === 'Backspace') {
        if (typeBuffer.length > 0) {
          e.preventDefault();
          typeBuffer = typeBuffer.slice(0, -1);
          applyFilter();
        }
        return;
      }
      if (e.key.length === 1 && !e.ctrlKey && !e.altKey && !e.metaKey) {
        e.preventDefault();
        if (!isOpen) {
          openDropdown();
        }
        if (now - lastKeyTime > 2500) {
          typeBuffer = e.key;
        } else {
          typeBuffer += e.key;
        }
        lastKeyTime = now;
        applyFilter();
      }
    });
    selectEl.addEventListener('change', () => {
      const val = selectEl.value;
      const matchingOpt = Array.from(selectEl.options).find(o => o.value === val);
      if (matchingOpt) {
        labelSpan.textContent = matchingOpt.textContent;
        optionElements.forEach(el => {
          el.classList.toggle('selected', el.dataset.value === val);
        });
      }
    });
  }
  function initSearchableDistrictDropdowns() {
    document.querySelectorAll('.district-select-input').forEach(sel => {
      setupSearchableDistrictSelect(sel);
    });
  }
  window.initSearchableDistrictDropdowns = initSearchableDistrictDropdowns;
  let currentSearchForensicResults = [];
  let currentSearchActiveIndex = 0;
  let currentSearchActiveFrameIndex = 0;
  window.clearVehicleSearch = function () {
    const input = document.getElementById('vehicleSearchInput');
    if (input) input.value = '';
    currentSearchForensicResults = [];
    currentSearchActiveIndex = 0;
    currentSearchActiveFrameIndex = 0;
    const emptyState = document.getElementById('vehicleSearchEmptyState');
    const loadingState = document.getElementById('vehicleSearchLoadingState');
    const noResultsState = document.getElementById('vehicleSearchNoResultsState');
    const activeResults = document.getElementById('vehicleSearchActiveResults');
    if (emptyState) emptyState.style.display = 'block';
    if (loadingState) loadingState.style.display = 'none';
    if (noResultsState) noResultsState.style.display = 'none';
    if (activeResults) {
      activeResults.style.display = 'none';
      activeResults.innerHTML = '';
    }
  };
  window.executeVehicleSearch = async function () {
    const input = document.getElementById('vehicleSearchInput');
    if (!input) return;
    const query = input.value.trim();
    if (!query) {
      window.showToast("Please enter a vehicle plate number or tracking ID to search.", "info");
      return;
    }
    const emptyState = document.getElementById('vehicleSearchEmptyState');
    const loadingState = document.getElementById('vehicleSearchLoadingState');
    const noResultsState = document.getElementById('vehicleSearchNoResultsState');
    const activeResults = document.getElementById('vehicleSearchActiveResults');
    if (emptyState) emptyState.style.display = 'none';
    if (noResultsState) noResultsState.style.display = 'none';
    if (activeResults) activeResults.style.display = 'none';
    if (loadingState) loadingState.style.display = 'block';
    try {
      const resp = await fetch(`/api/vehicles/search-full?q=${encodeURIComponent(query)}`);
      if (!resp.ok) throw new Error(`HTTP error ${resp.status}`);
      const data = await resp.json();
      loadingState.style.display = 'none';
      if (!data.success || !data.results || data.results.length === 0) {
        if (noResultsState) {
          noResultsState.style.display = 'block';
          const msg = document.getElementById('vehicleSearchNoResultsMsg');
          if (msg) msg.textContent = `No vehicle captures or tracking sessions matched: "${query}"`;
        }
        return;
      }
      currentSearchForensicResults = data.results;
      currentSearchActiveIndex = 0;
      currentSearchActiveFrameIndex = 0;
      window.renderSearchActiveRecord();
    } catch (err) {
      console.error("Forensic vehicle search error:", err);
      if (loadingState) loadingState.style.display = 'none';
      if (noResultsState) {
        noResultsState.style.display = 'block';
        const msg = document.getElementById('vehicleSearchNoResultsMsg');
        if (msg) msg.textContent = `Search error occurred: ${err.message}`;
      }
    }
  };
  window.selectSearchRecord = function (index) {
    if (index < 0 || index >= currentSearchForensicResults.length) return;
    currentSearchActiveIndex = index;
    currentSearchActiveFrameIndex = 0;
    window.renderSearchActiveRecord();
  };
  window.selectSearchFrame = function (frameIndex) {
    currentSearchActiveFrameIndex = frameIndex;
    window.updateSearchFrameInspector();
  };
  window.formatSecondsToMmss = function (sec) {
    if (sec === undefined || sec === null || isNaN(sec) || sec < 0) return '00:00.0s';
    const m = Math.floor(sec / 60);
    const s = (sec % 60).toFixed(1);
    const mStr = String(m).padStart(2, '0');
    const sStr = String(s).padStart(4, '0');
    return `${mStr}:${sStr}s`;
  };
  window.resolveFrameVideoTime = function (ef, fallbackIdx) {
    if (!ef) return '00:00.0s';
    if (ef.video_time_str) return ef.video_time_str;
    if (ef.time_str) return ef.time_str;
    const ts = ef.video_timestamp !== undefined && ef.video_timestamp !== null ? Number(ef.video_timestamp) : ef.timestamp !== undefined && ef.timestamp !== null ? Number(ef.timestamp) : null;
    if (ts !== null && !isNaN(ts) && ts > 0) {
      return window.formatSecondsToMmss(ts);
    }
    const fIdx = ef.frame_idx || fallbackIdx;
    if (fIdx && !isNaN(fIdx) && Number(fIdx) > 0) {
      return window.formatSecondsToMmss(Number(fIdx) / 25.0);
    }
    return '00:00.0s';
  };
  window.renderSearchActiveRecord = function () {
    const activeResults = document.getElementById('vehicleSearchActiveResults');
    if (!activeResults || currentSearchForensicResults.length === 0) return;
    const record = currentSearchForensicResults[currentSearchActiveIndex];
    if (!record) return;
    let switcherHtml = '';
    if (currentSearchForensicResults.length > 1) {
      const pills = currentSearchForensicResults.map((r, idx) => {
        const isActive = idx === currentSearchActiveIndex;
        const plateText = r.display_plate || r.plate_number || 'UNKNOWN';
        const trackStr = r.track_id !== null && r.track_id !== undefined ? `#${r.track_id}` : 'No Track';
        return `<button class="btn ${isActive ? 'btn-primary' : 'btn-secondary'}"



                    style="padding: 6px 14px; font-size: 0.875rem; font-family: var(--font-mono); font-weight: 600;"



                    onclick="window.selectSearchRecord(${idx})">



                    [#${idx + 1}] ${plateText} (${trackStr}) - ${r.captured_at || ''}



                </button>`;
      }).join('');
      switcherHtml = `



                <div style="margin-bottom: 20px; padding: 14px; background: rgba(241,245,249,0.5); border: 1px solid var(--border-color); border-radius: 8px;">



                    <div style="font-size: 0.875rem; font-weight: 700; color: #52647c; text-transform: uppercase; margin-bottom: 8px;">



                        Multiple Matches Found (${currentSearchForensicResults.length} Captures) - Select Record to Inspect:



                    </div>



                    <div style="display: flex; gap: 8px; flex-wrap: wrap;">



                        ${pills}



                    </div>



                </div>



            `;
    }
    const isHotlist = !!record.is_hotlist_hit;
    const plateDisplay = record.display_plate || record.plate_number || 'UNREADABLE';
    const trackIdVal = record.track_id !== null && record.track_id !== undefined ? record.track_id : record.vehicle_id || 'N/A';
    const trackIdDisplay = trackIdVal !== 'N/A' ? String(trackIdVal).startsWith('#') ? trackIdVal : `#${trackIdVal}` : 'N/A';
    const linkedTracksVal = record.linked_tracks ? String(record.linked_tracks) : String(trackIdVal);
    const linkedTracksDisplay = linkedTracksVal.startsWith('#') ? linkedTracksVal : linkedTracksVal !== 'N/A' ? `#${linkedTracksVal}` : 'N/A';
    const vehicleIdVal = record.vehicle_id !== null && record.vehicle_id !== undefined ? record.vehicle_id : trackIdVal;
    const vehicleIdDisplay = vehicleIdVal !== 'N/A' ? String(vehicleIdVal).startsWith('#') ? String(vehicleIdVal) : `#${vehicleIdVal}` : 'N/A';
    const peakOcrPct = (record.ocr_confidence || record.confidence || 0).toFixed(1);
    const peakDetPct = (record.det_confidence || 0).toFixed(1);
    const ensurePath = p => {
      if (!p) return '';
      if (p.startsWith('http') || p.startsWith('data:')) return p;
      return p.startsWith('/') ? p : '/' + p;
    };
    const rawVehImg = ensurePath(record.vehicle_pic_path);
    const rawPlateImg = ensurePath(record.plate_pic_path);
    const rawSceneImg = ensurePath(record.annotated_pic_path || record.vehicle_pic_path);
    const evFrames = Array.isArray(record.evidence_frames) ? record.evidence_frames : [];
    let playbackWindowDisplay = record.video_window_str || record.video_time_str;
    if (!playbackWindowDisplay && evFrames.length > 0) {
      const times = evFrames.map((ef, i) => {
        const ts = ef.video_timestamp !== undefined && ef.video_timestamp !== null ? Number(ef.video_timestamp) : ef.timestamp !== undefined && ef.timestamp !== null ? Number(ef.timestamp) : ef.frame_idx ? Number(ef.frame_idx) / 25.0 : 0;
        return ts;
      }).filter(t => t > 0);
      if (times.length > 0) {
        const minT = Math.min(...times);
        const maxT = Math.max(...times);
        const minStr = window.formatSecondsToMmss(minT);
        const maxStr = window.formatSecondsToMmss(maxT);
        playbackWindowDisplay = minStr === maxStr ? minStr : `${minStr} – ${maxStr}`;
      }
    }
    let framesThumbnailsHtml = '';
    if (evFrames.length > 0) {
      framesThumbnailsHtml = evFrames.map((ef, fIdx) => {
        const isSelected = fIdx === currentSearchActiveFrameIndex;
        const thumbImg = ef.crop_base64 ? `data:image/jpeg;base64,${ef.crop_base64}` : rawPlateImg;
        const fConf = ef.ocr_confidence !== undefined && ef.ocr_confidence > 0 ? ef.ocr_confidence : ef.confidence;
        const fConfStr = fConf ? `${Number(fConf).toFixed(1)}%` : 'N/A';
        const fBorder = isSelected ? 'border: 2px solid #0369a1; box-shadow: 0 0 12px rgba(56, 189, 248, 0.6);' : 'border: 1px solid #334155; opacity: 0.85;';
        const fTrack = ef.track_id !== undefined && ef.track_id !== null ? ef.track_id : trackIdVal;
        const fTrackDisplay = fTrack !== 'N/A' ? String(fTrack).startsWith('#') ? fTrack : `#${fTrack}` : trackIdDisplay;
        const fTime = window.resolveFrameVideoTime(ef, fIdx + 1);
        return `



                    <div onclick="window.selectSearchFrame(${fIdx})" style="cursor: pointer; min-width: 140px; max-width: 155px; background: #ffffff; border-radius: 8px; padding: 8px; ${fBorder} transition: all 0.2s ease;">



                        <div style="font-size: 0.875rem; font-weight: 700; color: ${isSelected ? '#0369a1' : '#52647c'}; margin-bottom: 4px; display: flex; justify-content: space-between; align-items: center;">



                            <span>F#${ef.frame_idx || fIdx + 1}</span>



                            <span style="color: #06b6d4; font-family: var(--font-mono); font-size: 0.875rem; font-weight: 700;">⏱️ ${fTime}</span>



                        </div>



                        <div style="position: relative; height: 52px; background: #000; border-radius: 4px; overflow: hidden; display: flex; align-items: center; justify-content: center;">



                            <div style="position: absolute; top: 2px; left: 2px; background: rgba(0,0,0,0.85); border: 1px solid #0369a1; color: #0369a1; font-family: var(--font-mono); font-size: 0.875rem; font-weight: 800; padding: 1px 4px; border-radius: 3px; z-index: 2;">



                                ${fTrackDisplay}



                            </div>



                            ${thumbImg ? `<img src="${thumbImg}" style="max-height: 100%; max-width: 100%; object-fit: contain;">` : '<span style="color: #64748b; font-size: 0.875rem;">No Crop</span>'}



                        </div>



                        <div style="font-size: 0.875rem; color: #475569; font-family: var(--font-mono); margin-top: 4px; display: flex; justify-content: space-between; align-items: center;">



                            <span style="white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 80px;">${ef.text || ef.raw_text || 'Reading'}</span>



                            <span style="color: #92400e; font-size: 0.875rem; font-weight: 700;">${fConfStr}</span>



                        </div>



                    </div>



                `;
      }).join('');
    }
    const sightingList = Array.isArray(record.sighting_trail) ? record.sighting_trail : [];
    let trailTableHtml = '';
    if (sightingList.length > 0) {
      const rows = sightingList.map(s => {
        const sImg = ensurePath(s.plate_photo_path || s.vehicle_photo_path);
        return `



                    <tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">



                        <td style="padding: 10px 14px; font-family: var(--font-mono); font-size: 0.875rem; color: #52647c;">${s.captured_at || s.created_at || 'N/A'}</td>



                        <td style="padding: 10px 14px; font-weight: 700; color: #0369a1; font-size: 0.9125rem;">${s.camera_id || 'CAM-01'}</td>



                        <td style="padding: 10px 14px; color: #334155; font-size: 0.9125rem;">${s.location || 'Panipat Toll Barrier'}</td>



                        <td style="padding: 10px 14px; font-weight: 700; color: #92400e; font-size: 0.9125rem;">${s.confidence ? Number(s.confidence).toFixed(1) + '%' : 'N/A'}</td>



                        <td style="padding: 10px 14px;">



                            ${sImg ? `<img src="${sImg}" style="height: 36px; border-radius: 4px; border: 1px solid #334155;">` : '<span style="color: #64748b; font-size: 0.875rem;">None</span>'}



                        </td>



                    </tr>



                `;
      }).join('');
      trailTableHtml = `



                <div style="overflow-x: auto;">



                    <table style="width: 100%; border-collapse: collapse; text-align: left;">



                        <thead>



                            <tr style="background: rgba(241,245,249,0.9); border-bottom: 1px solid var(--border-color); font-size: 0.875rem; color: #52647c; text-transform: uppercase;">



                                <th style="padding: 10px 14px;">Timestamp</th>



                                <th style="padding: 10px 14px;">Camera ID</th>



                                <th style="padding: 10px 14px;">Station / Location</th>



                                <th style="padding: 10px 14px;">Confidence</th>



                                <th style="padding: 10px 14px;">Evidence Crop</th>



                            </tr>



                        </thead>



                        <tbody>${rows}</tbody>



                    </table>



                </div>



            `;
    } else {
      trailTableHtml = `



                <div style="padding: 16px; background: rgba(241,245,249,0.4); border-radius: 8px; color: #52647c; font-size: 0.9125rem; text-align: center;">



                    Single surveillance passage logged at ${record.location || 'Surveillance Feed'} (${record.captured_at || ''}). No prior cross-district transit logged.



                </div>



            `;
    }
    activeResults.innerHTML = `



            ${switcherHtml}



            <!-- 1. VEHICLE IDENTIFICATION & TRACKING BANNER -->



            <div class="card" style="margin-bottom: 20px; padding: 22px; background: rgba(241,245,249,0.85); border: 1px solid var(--border-color); border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.3);">



                <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 16px;">



                    <div>



                        <div style="display: flex; align-items: center; gap: 14px; margin-bottom: 8px; flex-wrap: wrap;">



                            <div style="font-size: 1.85rem; font-weight: 800; font-family: var(--font-mono); color: #ffffff; background: #000; padding: 6px 18px; border-radius: 8px; border: 2px solid ${isHotlist ? '#ef4444' : '#0369a1'}; letter-spacing: 1.5px; box-shadow: 0 2px 10px rgba(0,0,0,0.5);">



                                ${plateDisplay}



                            </div>



                            ${isHotlist ? `



                                <div style="display: inline-flex; align-items: center; gap: 6px; background: rgba(239, 68, 68, 0.15); border: 1px solid #ef4444; color: #ef4444; font-weight: 800; padding: 6px 14px; border-radius: 6px; font-size: 0.8825rem;">



                                    <span>POLICE WATCHLIST HIT</span>



                                </div>



                            ` : `



                                <div style="display: inline-flex; align-items: center; gap: 6px; background: rgba(16, 185, 129, 0.15); border: 1px solid #10b981; color: #10b981; font-weight: 700; padding: 6px 14px; border-radius: 6px; font-size: 0.8825rem;">



                                    <span>NORMAL / VERIFIED</span>



                                </div>



                            `}



                        </div>



                        ${record.hotlist_info ? `



                            <div style="color: #b91c1c; font-weight: 600; font-size: 0.9425rem; margin-top: 6px; background: rgba(239,68,68,0.1); border-left: 3px solid #ef4444; padding: 6px 12px; border-radius: 4px;">



                                ${record.hotlist_info}



                            </div>



                        ` : ''}



                        <div style="font-size: 0.875rem; color: #52647c; margin-top: 8px; line-height: 1.6;">



                            <span>Logged at: <strong style="color: #334155;">${record.captured_at || 'N/A'}</strong></span> &bull;



                            <span>Location: <strong style="color: #334155;">${record.location || 'Main Surveillance Feed'}</strong></span> &bull;



                            <span>Source: <strong style="color: #0369a1;">${record.source_type || 'video'}</strong></span>



                            ${playbackWindowDisplay ? ` &bull; <span>⏱️ Video Time: <strong style="color: #06b6d4; font-family: var(--font-mono); font-size: 0.9425rem; background: rgba(6, 182, 212, 0.15); border: 1px solid rgba(6, 182, 212, 0.35); padding: 2px 8px; border-radius: 4px;">${playbackWindowDisplay}</strong> (In Uploaded Footage)</span>` : ''}



                        </div>



                    </div>



                    <!-- Interactive Telemetry Action Buttons -->



                    <div style="display: flex; gap: 10px; flex-wrap: wrap;">



                        <!-- Video Playback Timestamp Pill -->



                        <div title="Video playback timestamp in uploaded footage (${playbackWindowDisplay || 'N/A'})"



                            style="background: rgba(241,245,249,0.85); border: 1.5px solid #06b6d4; padding: 10px 16px; border-radius: 8px; text-align: center; min-width: 115px; box-shadow: 0 2px 8px rgba(6, 182, 212, 0.15);">



                            <div style="font-size: 0.875rem; color: #52647c; text-transform: uppercase; font-weight: 700; letter-spacing: 0.5px;">Video Time</div>



                            <div style="font-size: 1.15rem; font-weight: 800; color: #06b6d4; font-family: var(--font-mono); margin-top: 2px;">${playbackWindowDisplay ? playbackWindowDisplay.split('–')[0].trim() : '00:00.0s'}</div>



                            <div style="font-size: 0.875rem; color: #06b6d4; margin-top: 2px; font-weight: 600;">In Footage</div>



                        </div>



                        <button type="button" onclick="window.filterSearchByTrack('${trackIdVal}')"



                            title="Click to view all photos &amp; frames stamped with ByteTrack ID #${trackIdVal}"



                            style="cursor: pointer; background: rgba(241,245,249,0.85); border: 1.5px solid #0369a1; padding: 10px 16px; border-radius: 8px; text-align: center; min-width: 110px; transition: all 0.2s ease; box-shadow: 0 2px 8px rgba(56, 189, 248, 0.15);"



                            onmouseover="this.style.background='rgba(56, 189, 248, 0.15)'; this.style.transform='translateY(-2px)';"



                            onmouseout="this.style.background='rgba(241,245,249,0.85)'; this.style.transform='none';">



                            <div style="font-size: 0.875rem; color: #52647c; text-transform: uppercase; font-weight: 700; letter-spacing: 0.5px;">ByteTrack ID</div>



                            <div style="font-size: 1.25rem; font-weight: 800; color: #0369a1; font-family: var(--font-mono); margin-top: 2px;">${trackIdDisplay}</div>



                            <div style="font-size: 0.875rem; color: #0369a1; margin-top: 2px; font-weight: 600;">View Photos &darr;</div>



                        </button>



                        <button type="button" onclick="window.filterSearchByTrack('${trackIdVal}')"



                            title="Click to view all photos for Linked Track #${linkedTracksDisplay}"



                            style="cursor: pointer; background: rgba(241,245,249,0.85); border: 1.5px solid #c084fc; padding: 10px 16px; border-radius: 8px; text-align: center; min-width: 115px; transition: all 0.2s ease; box-shadow: 0 2px 8px rgba(192, 132, 252, 0.15);"



                            onmouseover="this.style.background='rgba(192, 132, 252, 0.15)'; this.style.transform='translateY(-2px)';"



                            onmouseout="this.style.background='rgba(241,245,249,0.85)'; this.style.transform='none';">



                            <div style="font-size: 0.875rem; color: #52647c; text-transform: uppercase; font-weight: 700; letter-spacing: 0.5px;">Linked Tracks</div>



                            <div style="font-size: 1.25rem; font-weight: 800; color: #7e22ce; font-family: var(--font-mono); margin-top: 2px;">${linkedTracksDisplay}</div>



                            <div style="font-size: 0.875rem; color: #7e22ce; margin-top: 2px; font-weight: 600;">Sync Track &darr;</div>



                        </button>



                        <button type="button" onclick="window.filterSearchByTrack('${vehicleIdVal}')"



                            title="Click to view all photos for Vehicle ID #${vehicleIdDisplay}"



                            style="cursor: pointer; background: rgba(241,245,249,0.85); border: 1.5px solid #047857; padding: 10px 16px; border-radius: 8px; text-align: center; min-width: 110px; transition: all 0.2s ease; box-shadow: 0 2px 8px rgba(52, 211, 153, 0.15);"



                            onmouseover="this.style.background='rgba(52, 211, 153, 0.15)'; this.style.transform='translateY(-2px)';"



                            onmouseout="this.style.background='rgba(241,245,249,0.85)'; this.style.transform='none';">



                            <div style="font-size: 0.875rem; color: #52647c; text-transform: uppercase; font-weight: 700; letter-spacing: 0.5px;">Vehicle ID</div>



                            <div style="font-size: 1.25rem; font-weight: 800; color: #047857; font-family: var(--font-mono); margin-top: 2px;">${vehicleIdDisplay}</div>



                            <div style="font-size: 0.875rem; color: #047857; margin-top: 2px; font-weight: 600;">Match Track &darr;</div>



                        </button>



                        <button type="button" onclick="window.selectSearchBestOcrFrame()"



                            title="Click to jump to Best OCR Evidence Frame"



                            style="cursor: pointer; background: rgba(241,245,249,0.85); border: 1.5px solid #fbbf24; padding: 10px 16px; border-radius: 8px; text-align: center; min-width: 110px; transition: all 0.2s ease; box-shadow: 0 2px 8px rgba(251, 191, 36, 0.15);"



                            onmouseover="this.style.background='rgba(251, 191, 36, 0.15)'; this.style.transform='translateY(-2px)';"



                            onmouseout="this.style.background='rgba(241,245,249,0.85)'; this.style.transform='none';">



                            <div style="font-size: 0.875rem; color: #52647c; text-transform: uppercase; font-weight: 700; letter-spacing: 0.5px;">Peak OCR Conf</div>



                            <div style="font-size: 1.25rem; font-weight: 800; color: #92400e; margin-top: 2px;">${peakOcrPct}%</div>



                            <div style="font-size: 0.875rem; color: #92400e; margin-top: 2px; font-weight: 600;">Inspect Peak &darr;</div>



                        </button>



                        <button type="button" onclick="window.selectSearchBestDetFrame()"



                            title="Click to jump to Best Plate Detection Frame"



                            style="cursor: pointer; background: rgba(241,245,249,0.85); border: 1.5px solid #1d4ed8; padding: 10px 16px; border-radius: 8px; text-align: center; min-width: 110px; transition: all 0.2s ease; box-shadow: 0 2px 8px rgba(96, 165, 250, 0.15);"



                            onmouseover="this.style.background='rgba(96, 165, 250, 0.15)'; this.style.transform='translateY(-2px)';"



                            onmouseout="this.style.background='rgba(241,245,249,0.85)'; this.style.transform='none';">



                            <div style="font-size: 0.875rem; color: #52647c; text-transform: uppercase; font-weight: 700; letter-spacing: 0.5px;">Plate Det Conf</div>



                            <div style="font-size: 1.25rem; font-weight: 800; color: #1d4ed8; margin-top: 2px;">${peakDetPct}%</div>



                            <div style="font-size: 0.875rem; color: #1d4ed8; margin-top: 2px; font-weight: 600;">Inspect Det &darr;</div>



                        </button>



                    </div>



                </div>



            </div>



            <!-- 2. RAW IMAGERY FORENSICS GALLERY (WITH TRACKING ID WATERMARK OVERLAY) -->



            <div id="searchRawImagerySection" class="card" style="margin-bottom: 20px; padding: 22px; background: rgba(241,245,249,0.85); border: 1px solid var(--border-color); border-radius: 12px;">



                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 8px;">



                    <h3 style="font-size: 1.1125rem; color: #475569; margin: 0; font-weight: 700; display: flex; align-items: center; gap: 8px;">



                        <span>Raw Optical Imagery (Original Captures Stamped with Tracking ID)</span>



                    </h3>



                    <div id="searchTrackFilterBanner" style="display: inline-flex; align-items: center; gap: 6px; background: rgba(56, 189, 248, 0.12); border: 1px solid #0369a1; color: #0369a1; padding: 5px 12px; border-radius: 6px; font-size: 0.875rem; font-weight: 700; font-family: var(--font-mono);">



                        ALL PHOTOS STAMPED WITH TRACK ID: ${trackIdDisplay}



                    </div>



                </div>



                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px;">



                    <!-- Raw Vehicle Crop -->



                    <div style="background: rgba(241,245,249,0.6); border: 1px solid #334155; border-radius: 10px; overflow: hidden; padding: 14px;">



                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">



                            <span style="font-size: 0.875rem; font-weight: 700; color: #475569; text-transform: uppercase;">Raw Vehicle Crop</span>



                            <span style="font-size: 0.875rem; color: #0369a1; font-weight: 600;">Full Target</span>



                        </div>



                        <div style="position: relative; height: 200px; background: #000; border-radius: 8px; display: flex; align-items: center; justify-content: center; overflow: hidden; cursor: pointer;"



                             onclick="window.openSearchPhotoModal('${rawVehImg}', 'Raw Vehicle Crop', '${trackIdVal}', '', {'Type': 'Vehicle Target Crop', 'Plate': '${plateDisplay}', 'Track ID': '${trackIdDisplay}'})">



                            <div style="position: absolute; top: 8px; left: 8px; background: rgba(0,0,0,0.85); border: 1.5px solid #0369a1; color: #ffffff; font-family: var(--font-mono); font-size: 0.875rem; font-weight: 800; padding: 3px 8px; border-radius: 4px; z-index: 2; box-shadow: 0 2px 6px rgba(0,0,0,0.7);">



                                TRACK ID: ${trackIdDisplay}



                            </div>



                            ${rawVehImg ? `<img src="${rawVehImg}" style="max-height: 100%; max-width: 100%; object-fit: contain;">` : '<span style="color: #64748b; font-size: 0.875rem;">No Vehicle Crop Available</span>'}



                        </div>



                        <div style="font-size: 0.875rem; color: #64748b; margin-top: 8px; text-align: center;">Original vehicle frame segment tracked by ByteTrack (Click to expand)</div>



                    </div>



                    <!-- Raw License Plate Crop -->



                    <div style="background: rgba(241,245,249,0.6); border: 1px solid #334155; border-radius: 10px; overflow: hidden; padding: 14px;">



                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">



                            <span style="font-size: 0.875rem; font-weight: 700; color: #475569; text-transform: uppercase;">Raw License Plate Crop</span>



                            <span style="font-size: 0.875rem; color: #92400e; font-weight: 600;">Plate Detector</span>



                        </div>



                        <div style="position: relative; height: 200px; background: #000; border-radius: 8px; display: flex; align-items: center; justify-content: center; overflow: hidden; cursor: pointer;"



                             onclick="window.openSearchPhotoModal('${rawPlateImg}', 'Raw License Plate Crop', '${trackIdVal}', '', {'Type': 'License Plate Crop', 'Plate': '${plateDisplay}', 'Track ID': '${trackIdDisplay}'})">



                            <div style="position: absolute; top: 8px; left: 8px; background: rgba(0,0,0,0.85); border: 1.5px solid #fbbf24; color: #ffffff; font-family: var(--font-mono); font-size: 0.875rem; font-weight: 800; padding: 3px 8px; border-radius: 4px; z-index: 2; box-shadow: 0 2px 6px rgba(0,0,0,0.7);">



                                TRACK ID: ${trackIdDisplay}



                            </div>



                            ${rawPlateImg ? `<img src="${rawPlateImg}" style="max-height: 100%; max-width: 100%; object-fit: contain;">` : '<span style="color: #64748b; font-size: 0.875rem;">No Plate Crop Available</span>'}



                        </div>



                        <div style="font-size: 0.875rem; color: #64748b; margin-top: 8px; text-align: center;">Raw plate crop directly from YOLO plate detector (Click to expand)</div>



                    </div>



                    <!-- Full Scene Perspective -->



                    <div style="background: rgba(241,245,249,0.6); border: 1px solid #334155; border-radius: 10px; overflow: hidden; padding: 14px;">



                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">



                            <span style="font-size: 0.875rem; font-weight: 700; color: #475569; text-transform: uppercase;">Full Scene Perspective</span>



                            <span style="font-size: 0.875rem; color: #047857; font-weight: 600;">Camera Context</span>



                        </div>



                        <div style="position: relative; height: 200px; background: #000; border-radius: 8px; display: flex; align-items: center; justify-content: center; overflow: hidden; cursor: pointer;"



                             onclick="window.openSearchPhotoModal('${rawSceneImg}', 'Full Scene Perspective', '${trackIdVal}', '', {'Type': 'Full Scene Perspective', 'Plate': '${plateDisplay}', 'Track ID': '${trackIdDisplay}'})">



                            <div style="position: absolute; top: 8px; left: 8px; background: rgba(0,0,0,0.85); border: 1.5px solid #047857; color: #ffffff; font-family: var(--font-mono); font-size: 0.875rem; font-weight: 800; padding: 3px 8px; border-radius: 4px; z-index: 2; box-shadow: 0 2px 6px rgba(0,0,0,0.7);">



                                TRACK ID: ${trackIdDisplay}



                            </div>



                            ${rawSceneImg ? `<img src="${rawSceneImg}" style="max-height: 100%; max-width: 100%; object-fit: contain;">` : '<span style="color: #64748b; font-size: 0.875rem;">No Scene Frame Available</span>'}



                        </div>



                        <div style="font-size: 0.875rem; color: #64748b; margin-top: 8px; text-align: center;">Full field-of-view perspective with vehicle &amp; plate localization (Click to expand)</div>



                    </div>



                </div>



            </div>



            <!-- 3. MULTI-FRAME EVIDENCE INSPECTOR -->



            <div id="searchFramesSection" class="card" style="margin-bottom: 20px; padding: 22px; background: rgba(241,245,249,0.85); border: 1px solid var(--border-color); border-radius: 12px; transition: all 0.3s ease;">



                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; flex-wrap: wrap; gap: 8px;">



                    <div>



                        <h3 style="font-size: 1.1125rem; color: #475569; font-weight: 700; margin: 0;">



                            Captured Evidence Frames (${evFrames.length} Frames Evaluated)



                        </h3>



                        <div style="font-size: 0.875rem; color: #52647c; margin-top: 2px;">



                            Tracking ID #${trackIdDisplay} &bull; Click any thumbnail below to inspect individual telemetry or crops



                        </div>



                    </div>



                    <div style="display: flex; gap: 8px;">



                        <button type="button" class="btn btn-secondary" onclick="window.selectSearchBestOcrFrame()" style="padding: 4px 10px; font-size: 0.875rem; border-color: #fbbf24; color: #92400e;">



                            Jump to Best OCR Frame



                        </button>



                        <button type="button" class="btn btn-secondary" onclick="window.selectSearchBestDetFrame()" style="padding: 4px 10px; font-size: 0.875rem; border-color: #1d4ed8; color: #1d4ed8;">



                            Jump to Best Det Frame



                        </button>



                    </div>



                </div>



                <!-- Thumbnails Strip -->



                <div style="display: flex; gap: 10px; overflow-x: auto; padding-bottom: 12px; margin-bottom: 16px;">



                    ${framesThumbnailsHtml || '<div style="color: #64748b; font-size: 0.9125rem; padding: 10px;">No individual supporting frame thumbnails saved for this session.</div>'}



                </div>



                <!-- Dynamic Active Frame Inspector Container -->



                <div id="searchActiveFrameInspectorContainer"></div>



            </div>



            <!-- 4. STATEWIDE SIGHTINGS & PASSAGE TRAIL -->



            <div class="card" style="margin-bottom: 20px; padding: 22px; background: rgba(241,245,249,0.85); border: 1px solid var(--border-color); border-radius: 12px;">



                <h3 style="font-size: 1.1125rem; color: #475569; margin-bottom: 14px; font-weight: 700;">



                    Statewide Sightings &amp; Passage History (${sightingList.length} Sightings)



                </h3>



                ${trailTableHtml}



            </div>



        `;
    activeResults.style.display = 'block';
    window.updateSearchFrameInspector();
  };
  window.updateSearchFrameInspector = function () {
    const container = document.getElementById('searchActiveFrameInspectorContainer');
    if (!container || currentSearchForensicResults.length === 0) return;
    const record = currentSearchForensicResults[currentSearchActiveIndex];
    if (!record) return;
    const evFrames = Array.isArray(record.evidence_frames) ? record.evidence_frames : [];
    if (evFrames.length === 0) {
      container.innerHTML = `



                <div style="padding: 16px; background: rgba(241,245,249,0.4); border-radius: 8px; color: #52647c; font-size: 0.9125rem; text-align: center;">



                    Detailed per-frame telemetry is stored for recent video runs.



                </div>



            `;
      return;
    }
    const safeIdx = Math.min(Math.max(0, currentSearchActiveFrameIndex), evFrames.length - 1);
    const f = evFrames[safeIdx];
    if (!f) return;
    const activeResults = document.getElementById('vehicleSearchActiveResults');
    if (activeResults) {
      const thumbBoxes = activeResults.querySelectorAll('[onclick^="window.selectSearchFrame"]');
      thumbBoxes.forEach((tb, i) => {
        if (i === safeIdx) {
          tb.style.border = '2px solid #0369a1';
          tb.style.boxShadow = '0 0 12px rgba(56, 189, 248, 0.6)';
          tb.style.opacity = '1';
        } else {
          tb.style.border = '1px solid #334155';
          tb.style.boxShadow = 'none';
          tb.style.opacity = '0.85';
        }
      });
    }
    const activeFrameTime = window.resolveFrameVideoTime(f, safeIdx + 1);
    const frameOcrConf = f.ocr_confidence !== undefined && f.ocr_confidence > 0 ? Number(f.ocr_confidence).toFixed(1) : f.confidence ? Number(f.confidence).toFixed(1) : '0.0';
    const frameDetConf = f.det_confidence !== undefined && f.det_confidence > 0 ? Number(f.det_confidence).toFixed(1) : record.det_confidence ? Number(record.det_confidence).toFixed(1) : '90.0';
    const frameText = f.raw_text || f.text || record.plate_number || 'N/A';
    const rawTrack = f.track_id !== undefined && f.track_id !== null ? f.track_id : record.track_id;
    const frameTrackId = rawTrack !== null && rawTrack !== undefined ? String(rawTrack).startsWith('#') ? rawTrack : `#${rawTrack}` : 'N/A';
    const plateCropSrc = f.crop_base64 ? `data:image/jpeg;base64,${f.crop_base64}` : record.plate_pic_path ? record.plate_pic_path.startsWith('/') ? record.plate_pic_path : '/' + record.plate_pic_path : '';
    const vehCropSrc = f.vehicle_crop_base64 ? `data:image/jpeg;base64,${f.vehicle_crop_base64}` : record.vehicle_pic_path ? record.vehicle_pic_path.startsWith('/') ? record.vehicle_pic_path : '/' + record.vehicle_pic_path : '';
    container.innerHTML = `



            <div style="background: rgba(241,245,249,0.7); border: 1px solid #334155; border-radius: 10px; padding: 18px;">



                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; flex-wrap: wrap; gap: 10px;">



                    <div style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap;">



                        <span class="badge" style="background: #f8fafc; color: #ffffff; font-weight: 800; font-size: 0.9125rem; padding: 4px 10px; border-radius: 6px;">



                            Active Frame #${f.frame_idx || safeIdx + 1}



                        </span>



                        <span style="background: rgba(6, 182, 212, 0.15); border: 1px solid #06b6d4; color: #06b6d4; font-family: var(--font-mono); font-size: 0.8825rem; font-weight: 800; padding: 3px 10px; border-radius: 6px; display: inline-flex; align-items: center; gap: 4px;">



                            ⏱️ Video Time: ${activeFrameTime}



                        </span>



                        <span style="font-family: var(--font-mono); font-size: 0.9125rem; color: #475569; font-weight: 700;">



                            ByteTrack: <span style="color: #0369a1;">${frameTrackId}</span>



                        </span>



                    </div>



                    <div style="font-family: var(--font-mono); font-size: 1.1rem; font-weight: 800; color: #ffffff; background: #000; padding: 2px 12px; border-radius: 6px; border: 1px solid #64748b;">



                        Text: ${frameText}



                    </div>



                </div>



                <!-- Per-Frame Telemetry Metrics -->



                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; margin-bottom: 16px;">



                    <!-- Video Playback Seek Time -->



                    <div style="background: rgba(241,245,249,0.8); border: 1.5px solid #06b6d4; padding: 12px; border-radius: 8px; box-shadow: 0 2px 8px rgba(6, 182, 212, 0.15);">



                        <div style="display: flex; justify-content: space-between; font-size: 0.875rem; color: #52647c; font-weight: 700; margin-bottom: 6px;">



                            <span>Video Playback Time</span>



                            <span style="color: #06b6d4; font-family: var(--font-mono); font-size: 1.0125rem; font-weight: 800;">⏱️ ${activeFrameTime}</span>



                        </div>



                        <div style="height: 6px; background: #e2e8f0; border-radius: 3px; overflow: hidden; margin-bottom: 6px;">



                            <div style="height: 100%; width: 100%; background: linear-gradient(90deg, #0284c7, #06b6d4); border-radius: 3px;"></div>



                        </div>



                        <div style="font-size: 0.875rem; color: #52647c; display: flex; justify-content: space-between;">



                            <span>Frame #${f.frame_idx || safeIdx + 1}</span>



                            <span style="color: #06b6d4; font-weight: 600;">Seek Position in Video</span>



                        </div>



                    </div>



                    <!-- Plate Detection Confidence -->



                    <div style="background: rgba(241,245,249,0.8); border: 1px solid #334155; padding: 12px; border-radius: 8px;">



                        <div style="display: flex; justify-content: space-between; font-size: 0.875rem; color: #52647c; font-weight: 700; margin-bottom: 6px;">



                            <span>Plate Detector Conf</span>



                            <span style="color: #1d4ed8; font-size: 0.9125rem;">${frameDetConf}%</span>



                        </div>



                        <div style="height: 6px; background: #e2e8f0; border-radius: 3px; overflow: hidden;">



                            <div style="height: 100%; width: ${Math.min(100, frameDetConf)}%; background: linear-gradient(90deg, #3b82f6, #1d4ed8); border-radius: 3px;"></div>



                        </div>



                    </div>



                    <!-- OCR Confidence -->



                    <div style="background: rgba(241,245,249,0.8); border: 1px solid #334155; padding: 12px; border-radius: 8px;">



                        <div style="display: flex; justify-content: space-between; font-size: 0.875rem; color: #52647c; font-weight: 700; margin-bottom: 6px;">



                            <span>Awiros OCR Conf</span>



                            <span style="color: #92400e; font-size: 0.9125rem;">${frameOcrConf}%</span>



                        </div>



                        <div style="height: 6px; background: #e2e8f0; border-radius: 3px; overflow: hidden;">



                            <div style="height: 100%; width: ${Math.min(100, frameOcrConf)}%; background: linear-gradient(90deg, #f59e0b, #fbbf24); border-radius: 3px;"></div>



                        </div>



                    </div>



                </div>



                <!-- Per-Frame Crops Side-by-Side (Stamped with Tracking ID & Clickable) -->



                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 14px;">



                    <div style="background: #ffffff; border: 1px solid #334155; border-radius: 8px; padding: 10px;">



                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">



                            <span style="font-size: 0.875rem; color: #52647c; font-weight: 700; text-transform: uppercase;">Frame Plate Crop</span>



                            <span style="font-size: 0.875rem; color: #92400e; font-weight: 600;">Conf: ${frameOcrConf}%</span>



                        </div>



                        <div style="position: relative; height: 130px; background: #000; border-radius: 6px; display: flex; align-items: center; justify-content: center; overflow: hidden; cursor: pointer;"



                             onclick="window.openSearchPhotoModal('${plateCropSrc}', 'Evidence Frame Plate Crop', '${frameTrackId}', '${f.frame_idx || safeIdx + 1}', {'Frame': '${f.frame_idx || safeIdx + 1}', 'Video Timestamp': '${activeFrameTime}', 'OCR Confidence': '${frameOcrConf}%', 'Plate Text': '${frameText}', 'ByteTrack': '${frameTrackId}'})">



                            <div style="position: absolute; top: 6px; left: 6px; background: rgba(0,0,0,0.85); border: 1.5px solid #0369a1; color: #ffffff; font-family: var(--font-mono); font-size: 0.875rem; font-weight: 800; padding: 2px 6px; border-radius: 4px; z-index: 2;">



                                TRACK ID: ${frameTrackId}



                            </div>



                            ${plateCropSrc ? `<img src="${plateCropSrc}" style="max-height: 100%; max-width: 100%; object-fit: contain;">` : '<span style="color: #64748b; font-size: 0.875rem;">Crop Not Stored</span>'}



                        </div>



                        <div style="font-size: 0.875rem; color: #64748b; margin-top: 6px; text-align: center;">Click to inspect full photo with track stamp</div>



                    </div>



                    <div style="background: #ffffff; border: 1px solid #334155; border-radius: 8px; padding: 10px;">



                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">



                            <span style="font-size: 0.875rem; color: #52647c; font-weight: 700; text-transform: uppercase;">Frame Vehicle Perspective</span>



                            <span style="font-size: 0.875rem; color: #1d4ed8; font-weight: 600;">Det Conf: ${frameDetConf}%</span>



                        </div>



                        <div style="position: relative; height: 130px; background: #000; border-radius: 6px; display: flex; align-items: center; justify-content: center; overflow: hidden; cursor: pointer;"



                             onclick="window.openSearchPhotoModal('${vehCropSrc || rawVehImg}', 'Evidence Frame Vehicle Perspective', '${frameTrackId}', '${f.frame_idx || safeIdx + 1}', {'Frame': '${f.frame_idx || safeIdx + 1}', 'Video Timestamp': '${activeFrameTime}', 'Detection Confidence': '${frameDetConf}%', 'Plate Text': '${frameText}', 'ByteTrack': '${frameTrackId}'})">



                            <div style="position: absolute; top: 6px; left: 6px; background: rgba(0,0,0,0.85); border: 1.5px solid #0369a1; color: #ffffff; font-family: var(--font-mono); font-size: 0.875rem; font-weight: 800; padding: 2px 6px; border-radius: 4px; z-index: 2;">



                                TRACK ID: ${frameTrackId}



                            </div>



                            ${vehCropSrc || rawVehImg ? `<img src="${vehCropSrc || rawVehImg}" style="max-height: 100%; max-width: 100%; object-fit: contain;">` : '<span style="color: #64748b; font-size: 0.875rem;">Vehicle Crop Not Stored</span>'}



                        </div>



                        <div style="font-size: 0.875rem; color: #64748b; margin-top: 6px; text-align: center;">Click to inspect full photo with track stamp</div>



                    </div>



                </div>



            </div>



        `;
  };
  window.openSearchPhotoModal = function (imgSrc, title, trackId, frameIdx, extraMeta) {
    const modal = document.getElementById('searchPhotoModal');
    if (!modal) return;
    const imgEl = document.getElementById('searchPhotoModalImg');
    const trackBadge = document.getElementById('searchPhotoModalTrackBadge');
    const frameBadge = document.getElementById('searchPhotoModalFrameBadge');
    const timeBadge = document.getElementById('searchPhotoModalTimeBadge');
    const titleEl = document.getElementById('searchPhotoModalTitle');
    const overlayTag = document.getElementById('searchPhotoModalOverlayTag');
    const detailsEl = document.getElementById('searchPhotoModalDetails');
    if (imgEl) imgEl.src = imgSrc || '';
    if (titleEl) titleEl.textContent = title || 'Forensic Photo Inspection';
    const cleanTrack = trackId ? String(trackId).startsWith('#') ? trackId : `#${trackId}` : '';
    if (trackBadge) {
      trackBadge.textContent = cleanTrack ? `TRACK ${cleanTrack}` : 'TRACK N/A';
      trackBadge.style.display = cleanTrack ? 'inline-block' : 'none';
    }
    if (overlayTag) {
      overlayTag.textContent = cleanTrack ? `TRACK ID: ${cleanTrack}` : 'TRACK ID: N/A';
      overlayTag.style.display = 'block';
    }
    if (frameBadge) {
      if (frameIdx !== undefined && frameIdx !== null && frameIdx !== '') {
        frameBadge.textContent = `FRAME #${frameIdx}`;
        frameBadge.style.display = 'inline-block';
      } else {
        frameBadge.style.display = 'none';
      }
    }
    if (timeBadge) {
      const vTime = extraMeta && extraMeta['Video Timestamp'] ? extraMeta['Video Timestamp'] : extraMeta && extraMeta['Video Time'] ? extraMeta['Video Time'] : '';
      if (vTime) {
        timeBadge.textContent = String(vTime).startsWith('⏱️') ? vTime : `⏱️ ${vTime}`;
        timeBadge.style.display = 'inline-block';
      } else {
        timeBadge.style.display = 'none';
      }
    }
    if (detailsEl) {
      let metaHtml = '';
      if (extraMeta && typeof extraMeta === 'object') {
        metaHtml = Object.entries(extraMeta).map(([k, v]) => `



                    <div style="background: rgba(241,245,249,0.85); border: 1px solid #334155; padding: 6px 14px; border-radius: 6px; font-size: 0.875rem;">



                        <span style="color: #52647c; margin-right: 6px;">${k}:</span>



                        <strong style="color: #172033; font-family: var(--font-mono);">${v}</strong>



                    </div>



                `).join('');
      }
      detailsEl.innerHTML = metaHtml;
    }
    modal.style.display = 'flex';
  };
  window.closeSearchPhotoModal = function () {
    const modal = document.getElementById('searchPhotoModal');
    if (modal) modal.style.display = 'none';
  };
  const searchModalEl = document.getElementById('searchPhotoModal');
  if (searchModalEl) {
    searchModalEl.addEventListener('click', e => {
      if (e.target === searchModalEl) {
        window.closeSearchPhotoModal();
      }
    });
  }
  window.filterSearchByTrack = function (trackId) {
    if (!trackId || trackId === 'N/A') {
      window.showToast("No tracking ID available for this record.", "info");
      return;
    }
    const cleanTrack = String(trackId).replace(/^#/, '').trim();
    const framesSec = document.getElementById('searchFramesSection');
    const rawSec = document.getElementById('searchRawImagerySection');
    const filterBanner = document.getElementById('searchTrackFilterBanner');
    if (filterBanner) {
      filterBanner.style.background = 'rgba(56, 189, 248, 0.25)';
      filterBanner.style.border = '2px solid #0369a1';
      filterBanner.style.boxShadow = '0 0 15px rgba(56, 189, 248, 0.5)';
      filterBanner.innerHTML = `FILTERED: TRACK ID #${cleanTrack} &bull; ALL PHOTOS DISPLAYED`;
    }
    const record = currentSearchForensicResults[currentSearchActiveIndex];
    if (record && Array.isArray(record.evidence_frames) && record.evidence_frames.length > 0) {
      const matchingIdx = record.evidence_frames.findIndex(ef => String(ef.track_id) === cleanTrack);
      if (matchingIdx !== -1) {
        window.selectSearchFrame(matchingIdx);
      }
    }
    const targetSection = framesSec || rawSec;
    if (targetSection) {
      targetSection.scrollIntoView({
        behavior: 'smooth',
        block: 'start'
      });
      targetSection.style.transition = 'box-shadow 0.4s ease, border-color 0.4s ease';
      targetSection.style.boxShadow = '0 0 25px rgba(56, 189, 248, 0.4)';
      targetSection.style.borderColor = '#0369a1';
      setTimeout(() => {
        targetSection.style.boxShadow = '';
        targetSection.style.borderColor = 'var(--border-color)';
      }, 2200);
    }
    window.showToast(`Displaying all photos & evidence frames for Tracking ID #${cleanTrack}`, "info");
  };
  window.selectSearchBestOcrFrame = function () {
    const record = currentSearchForensicResults[currentSearchActiveIndex];
    if (!record) return;
    const evFrames = Array.isArray(record.evidence_frames) ? record.evidence_frames : [];
    if (evFrames.length === 0) {
      window.showToast(`Peak OCR Confidence: ${(record.ocr_confidence || record.confidence || 0).toFixed(1)}%`, "info");
      return;
    }
    let bestIdx = 0;
    let maxConf = -1;
    evFrames.forEach((ef, idx) => {
      const c = ef.ocr_confidence !== undefined && ef.ocr_confidence > 0 ? Number(ef.ocr_confidence) : ef.confidence ? Number(ef.confidence) : 0;
      if (c > maxConf) {
        maxConf = c;
        bestIdx = idx;
      }
    });
    window.selectSearchFrame(bestIdx);
    const inspector = document.getElementById('searchActiveFrameInspectorContainer');
    if (inspector) {
      inspector.scrollIntoView({
        behavior: 'smooth',
        block: 'center'
      });
    }
    const bestFrame = evFrames[bestIdx];
    window.showToast(`Selected Peak OCR Evidence Frame: Frame #${bestFrame.frame_idx || bestIdx + 1} (${maxConf.toFixed(1)}%)`, "info");
  };
  window.selectSearchBestDetFrame = function () {
    const record = currentSearchForensicResults[currentSearchActiveIndex];
    if (!record) return;
    const evFrames = Array.isArray(record.evidence_frames) ? record.evidence_frames : [];
    if (evFrames.length === 0) {
      window.showToast(`Peak Plate Detection Conf: ${(record.det_confidence || 0).toFixed(1)}%`, "info");
      return;
    }
    let bestIdx = 0;
    let maxDet = -1;
    evFrames.forEach((ef, idx) => {
      const c = ef.det_confidence !== undefined && ef.det_confidence > 0 ? Number(ef.det_confidence) : record.det_confidence || 0;
      if (c > maxDet) {
        maxDet = c;
        bestIdx = idx;
      }
    });
    window.selectSearchFrame(bestIdx);
    const inspector = document.getElementById('searchActiveFrameInspectorContainer');
    if (inspector) {
      inspector.scrollIntoView({
        behavior: 'smooth',
        block: 'center'
      });
    }
    const bestFrame = evFrames[bestIdx];
    window.showToast(`Selected Peak Plate Detector Frame: Frame #${bestFrame.frame_idx || bestIdx + 1} (${maxDet.toFixed(1)}%)`, "info");
  };
  let currentBenchmarkData = [];
  let currentBenchmarkRecommendations = null;
  let currentBenchmarkHardware = null;
  let currentBenchmarkFilter = 'all';
  window.openBenchmarkModal = function () {
    const modal = document.getElementById('benchmarkModal');
    if (modal) {
      modal.style.display = 'flex';
    }
    window.renderBenchmarkAdvisorCards();
    if (currentBenchmarkData && currentBenchmarkData.length > 0) {
      window.renderBenchmarkResults();
    } else {
      window.runBenchmark(false);
    }
  };
  window.closeBenchmarkModal = function () {
    const modal = document.getElementById('benchmarkModal');
    if (modal) {
      modal.style.display = 'none';
    }
  };
  window.applyBenchmarkProfile = async function (profileKey) {
    let targetVeh = 'yolo11n';
    let targetPlt = 'plate_yolo_l';
    let targetPer = 'yolo11n';
    let profileLabel = 'Recommended Setup';
    const recs = currentBenchmarkRecommendations && currentBenchmarkRecommendations.profiles ? currentBenchmarkRecommendations.profiles : null;
    if (recs && recs[profileKey]) {
      const p = recs[profileKey];
      targetVeh = p.vehicle_model || targetVeh;
      targetPlt = p.plate_model || targetPlt;
      targetPer = p.person_model || targetVeh;
      profileLabel = p.title || profileKey;
    } else if (profileKey === 'fast') {
      targetVeh = 'yolo11n';
      targetPlt = 'tanish_yolo11s_plate';
      targetPer = 'yolo11n';
      profileLabel = 'High Speed Setup (Live RTSP)';
    } else if (profileKey === 'accurate') {
      targetVeh = 'uvh26_yolo11x';
      targetPlt = 'plate_yolo_l';
      targetPer = 'uvh26_yolo11x';
      profileLabel = 'Best Accuracy (Forensics & SOTA)';
    } else {
      targetVeh = 'driveindia_tihan_yolov10x';
      targetPlt = 'plate_yolo_l';
      targetPer = 'driveindia_tihan_yolov10x';
      profileLabel = 'Balanced Setup (Recommended)';
    }
    const selVeh = document.getElementById('selVehicleModel');
    const selPlt = document.getElementById('selPlateModel');
    const selPer = document.getElementById('selPersonModel');
    if (selVeh) selVeh.value = targetVeh;
    if (selPlt) selPlt.value = targetPlt;
    if (selPer) selPer.value = targetPer;
    if (typeof window.handleModelSelectionChange === 'function') {
      await window.handleModelSelectionChange();
    }
    if (typeof syncCustomDropdownUI === 'function') {
      syncCustomDropdownUI();
    }
    window.renderBenchmarkAdvisorCards();
    if (typeof window.showToastAlert === 'function') {
      null;
    } else if (typeof window.showToast === 'function') {
      window.showToast(`Active Pipeline Applied: ${profileLabel}`, "success");
    }
  };
  window.renderBenchmarkAdvisorCards = function () {
    const grid = document.getElementById('benchmarkProfileCardsGrid');
    if (!grid) return;
    const selVeh = document.getElementById('selVehicleModel');
    const selPlt = document.getElementById('selPlateModel');
    const curVeh = selVeh ? selVeh.value : '';
    const curPlt = selPlt ? selPlt.value : '';
    const hwBadge = document.getElementById('benchmarkHwSummaryBadge');
    if (hwBadge) {
      if (currentBenchmarkHardware) {
        hwBadge.innerHTML = `<span style="color:#92400e; font-weight:700;">${escapeHtml(currentBenchmarkHardware.device_type)}:</span> ${escapeHtml(currentBenchmarkHardware.device_name)} • ${escapeHtml(currentBenchmarkHardware.acceleration)}`;
      } else {
        hwBadge.innerHTML = `Workstation Multi-Core CPU (PyTorch / OpenVINO CPU Provider)`;
      }
    }
    const hasMeasuredData = Boolean(currentBenchmarkData && currentBenchmarkData.length > 0);
    const recs = currentBenchmarkRecommendations && currentBenchmarkRecommendations.profiles ? currentBenchmarkRecommendations.profiles : null;
    let profiles = [];
    if (recs && recs.fast && recs.balanced && recs.accurate) {
      profiles = [{
        key: 'fast',
        title: recs.fast.title || 'High Speed (Live RTSP)',
        subtitle: 'Optimized for Real-Time Feeds',
        tag: recs.fast.tag || 'MAX THROUGHPUT',
        themeColor: '#0369a1',
        themeBg: 'rgba(56, 189, 248, 0.08)',
        themeBorder: 'rgba(56, 189, 248, 0.35)',
        vehKey: recs.fast.vehicle_model,
        vehName: recs.fast.vehicle_name,
        vehMs: recs.fast.vehicle_ms,
        pltKey: recs.fast.plate_model,
        pltName: recs.fast.plate_name,
        pltMs: recs.fast.plate_ms,
        totalMs: recs.fast.pipeline_latency_ms,
        fps: recs.fast.pipeline_fps,
        useCase: recs.fast.use_case || 'Multi-Camera RTSP Streams, Toll Plazas & Live Traffic',
        icon: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#0369a1" stroke-width="2.2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>`,
        badge: recs.fast.badge || 'FASTEST (LIVE READY)'
      }, {
        key: 'balanced',
        title: recs.balanced.title || 'Balanced (Sweet Spot)',
        subtitle: 'Standard Production Setup',
        tag: recs.balanced.tag || 'SYSTEM SWEET SPOT',
        themeColor: '#10b981',
        themeBg: 'rgba(16, 185, 129, 0.08)',
        themeBorder: 'rgba(16, 185, 129, 0.45)',
        vehKey: recs.balanced.vehicle_model,
        vehName: recs.balanced.vehicle_name,
        vehMs: recs.balanced.vehicle_ms,
        pltKey: recs.balanced.plate_model,
        pltName: recs.balanced.plate_name,
        pltMs: recs.balanced.plate_ms,
        totalMs: recs.balanced.pipeline_latency_ms,
        fps: recs.balanced.pipeline_fps,
        useCase: recs.balanced.use_case || 'Daily Police Checkposts & Patrol Operations',
        icon: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2.2"><path d="M12 3v18"/><path d="m3 7 9-4 9 4"/><path d="M3 7l3 8h6L9 7"/><path d="M15 7l3 8h6l-3-8"/></svg>`,
        badge: recs.balanced.badge || 'RECOMMENDED SWEET SPOT',
        isRecommended: true
      }, {
        key: 'accurate',
        title: recs.accurate.title || 'High Accuracy (Forensics)',
        subtitle: 'Deep Investigation Mode',
        tag: recs.accurate.tag || 'MAX RECALL',
        themeColor: '#f59e0b',
        themeBg: 'rgba(245, 158, 11, 0.08)',
        themeBorder: 'rgba(245, 158, 11, 0.35)',
        vehKey: recs.accurate.vehicle_model,
        vehName: recs.accurate.vehicle_name,
        vehMs: recs.accurate.vehicle_ms,
        pltKey: recs.accurate.plate_model,
        pltName: recs.accurate.plate_name,
        pltMs: recs.accurate.plate_ms,
        totalMs: recs.accurate.pipeline_latency_ms,
        fps: recs.accurate.pipeline_fps,
        useCase: recs.accurate.use_case || 'Recorded Evidence, Night Footage & Hit & Run Cases',
        icon: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" stroke-width="2.2"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/></svg>`,
        badge: recs.accurate.badge || 'HIGHEST RECALL'
      }];
    } else {
      const findModel = (needle, category) => {
        if (!hasMeasuredData) return null;
        return currentBenchmarkData.find(m => {
          if (category && m.category !== category) return false;
          const n = (m.name || '').toLowerCase();
          const f = (m.family || '').toLowerCase();
          const key = needle.replace('_', '-').toLowerCase();
          return n.includes(key) || n.includes(needle.toLowerCase()) || f.includes(key);
        });
      };
      const mVehFast = findModel('yolo11n', 'vehicle');
      const mPltFast = findModel('tanish', 'plate') || findModel('plate_yolo_ft', 'plate') || findModel('plate', 'plate');
      const fastVehMs = mVehFast && mVehFast.median_ms ? mVehFast.median_ms : 151.7;
      const fastPltMs = mPltFast && mPltFast.median_ms ? mPltFast.median_ms : 320.5;
      const fastTotalMs = (fastVehMs + fastPltMs).toFixed(1);
      const fastFps = (1000.0 / Math.max(parseFloat(fastTotalMs), 1)).toFixed(1);
      const mVehBal = findModel('uvh26', 'vehicle') || findModel('tihan', 'vehicle') || findModel('yolo11n', 'vehicle');
      const mPltBal = findModel('yolov8_plate', 'plate') || findModel('plate_yolo_l', 'plate') || findModel('plate', 'plate');
      const balVehMs = mVehBal && mVehBal.median_ms ? mVehBal.median_ms : 1811.1;
      const balPltMs = mPltBal && mPltBal.median_ms ? mPltBal.median_ms : 973.5;
      const balTotalMs = (balVehMs + balPltMs).toFixed(1);
      const balFps = (1000.0 / Math.max(parseFloat(balTotalMs), 1)).toFixed(1);
      const mVehAcc = findModel('rtdetrv2', 'vehicle') || findModel('uvh26', 'vehicle');
      const mPltAcc = findModel('plate_yolo_l', 'plate') || findModel('yolo11l', 'plate');
      const accVehMs = mVehAcc && mVehAcc.median_ms ? mVehAcc.median_ms : 4453.0;
      const accPltMs = mPltAcc && mPltAcc.median_ms ? mPltAcc.median_ms : 2172.1;
      const accTotalMs = (accVehMs + accPltMs).toFixed(1);
      const accFps = (1000.0 / Math.max(parseFloat(accTotalMs), 1)).toFixed(1);
      profiles = [{
        key: 'fast',
        title: 'High Speed (Live RTSP)',
        subtitle: 'Optimized for Real-Time Feeds',
        tag: 'MAX THROUGHPUT',
        themeColor: '#0369a1',
        themeBg: 'rgba(56, 189, 248, 0.08)',
        themeBorder: 'rgba(56, 189, 248, 0.35)',
        vehKey: 'yolo11n',
        vehName: mVehFast && mVehFast.name ? mVehFast.name : 'YOLO11n (Nano)',
        vehMs: fastVehMs,
        pltKey: mPltFast && mPltFast.model_id ? mPltFast.model_id : 'tanish_yolo11s_plate',
        pltName: mPltFast && mPltFast.name ? mPltFast.name : 'YOLO11s Plate (TanishDevX)',
        pltMs: fastPltMs,
        totalMs: fastTotalMs,
        fps: fastFps,
        useCase: 'Multi-Camera RTSP Streams, Toll Plazas & Live Traffic',
        icon: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#0369a1" stroke-width="2.2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>`,
        badge: 'FASTEST (LIVE READY)'
      }, {
        key: 'balanced',
        title: 'Balanced (Sweet Spot)',
        subtitle: 'Standard Production Setup',
        tag: 'SYSTEM SWEET SPOT',
        themeColor: '#10b981',
        themeBg: 'rgba(16, 185, 129, 0.08)',
        themeBorder: 'rgba(16, 185, 129, 0.45)',
        vehKey: 'uvh26_yolo11x',
        vehName: mVehBal && mVehBal.name ? mVehBal.name : 'IISc UVH-26 (SOTA)',
        vehMs: balVehMs,
        pltKey: mPltBal && mPltBal.model_id ? mPltBal.model_id : 'yolov8_plate',
        pltName: mPltBal && mPltBal.name ? mPltBal.name : 'YOLOv8 Plate Detector ⚡',
        pltMs: balPltMs,
        totalMs: balTotalMs,
        fps: balFps,
        useCase: 'Daily Police Checkposts & Patrol Operations',
        icon: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2.2"><path d="M12 3v18"/><path d="m3 7 9-4 9 4"/><path d="M3 7l3 8h6L9 7"/><path d="M15 7l3 8h6l-3-8"/></svg>`,
        badge: 'RECOMMENDED SWEET SPOT',
        isRecommended: true
      }, {
        key: 'accurate',
        title: 'High Accuracy (Forensics)',
        subtitle: 'Deep Investigation Mode',
        tag: 'MAX RECALL',
        themeColor: '#f59e0b',
        themeBg: 'rgba(245, 158, 11, 0.08)',
        themeBorder: 'rgba(245, 158, 11, 0.35)',
        vehKey: 'rtdetrv2_x',
        vehName: mVehAcc && mVehAcc.name ? mVehAcc.name : 'RT-DETRv2-X (Transformer SOTA)',
        vehMs: accVehMs,
        pltKey: mPltAcc && mPltAcc.model_id ? mPltAcc.model_id : 'plate_yolo_l',
        pltName: mPltAcc && mPltAcc.name ? mPltAcc.name : 'YOLO11l Plate (CCTV Large)',
        pltMs: accPltMs,
        totalMs: accTotalMs,
        fps: accFps,
        useCase: 'Recorded Evidence, Night Footage & Hit & Run Cases',
        icon: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" stroke-width="2.2"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/></svg>`,
        badge: 'HIGHEST RECALL'
      }];
    }
    grid.innerHTML = profiles.map(p => {
      const isActive = curVeh === p.vehKey && curPlt === p.pltKey && 0 === null;
      const borderStyle = isActive ? `2px solid #10b981` : `1px solid ${p.themeBorder}`;
      const glowStyle = isActive ? `box-shadow: 0 0 16px rgba(16, 185, 129, 0.3);` : p.isRecommended ? `box-shadow: 0 0 12px rgba(16, 185, 129, 0.15);` : ``;
      const cardBg = isActive ? `rgba(16, 185, 129, 0.06)` : p.themeBg;
      return `



            <div style="background: ${cardBg}; border: ${borderStyle}; ${glowStyle} border-radius: 8px; padding: 10px 12px; display: flex; flex-direction: column; justify-content: space-between; gap: 8px; position: relative;">



                <!-- Card Header -->



                <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 6px;">



                    <div style="display: flex; align-items: center; gap: 6px;">



                        ${p.icon}



                        <div>



                            <div style="font-size: 0.875rem; font-weight: 700; color: #ffffff; line-height: 1.2;">



                                ${escapeHtml(p.title)}



                            </div>



                            <div style="font-size: 0.875rem; color: ${p.themeColor}; font-weight: 600;">



                                ${escapeHtml(p.subtitle)}



                            </div>



                        </div>



                    </div>



                    <div style="display: flex; flex-direction: column; align-items: flex-end; gap: 2px;">



                        ${isActive ? `



                            <span style="display: inline-flex; align-items: center; gap: 4px; padding: 2px 7px; border-radius: 4px; font-size: 0.875rem; font-weight: 800; background: rgba(16, 185, 129, 0.2); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.5);">



                                <span style="width: 5px; height: 5px; border-radius: 50%; background: #f8fafc;"></span>



                                ACTIVE



                            </span>



                        ` : `



                            <span style="display: inline-block; padding: 2px 6px; border-radius: 4px; font-size: 0.875rem; font-weight: 700; background: rgba(255, 255, 255, 0.06); color: ${p.themeColor}; border: 1px solid ${p.themeBorder};">



                                ${escapeHtml(p.badge)}



                            </span>



                        `}



                        <span style="font-size: 0.875rem; color: ${hasMeasuredData ? '#10b981' : '#52647c'}; font-weight: 700;">



                            ${hasMeasuredData ? 'LIVE MEASURED' : 'ESTIMATED'}



                        </span>



                    </div>



                </div>



                <!-- Model Combination Specs -->



                <div style="background: rgba(241,245,249,0.65); border: 1px solid var(--border-color); border-radius: 6px; padding: 6px 8px; display: flex; flex-direction: column; gap: 4px; font-size: 0.875rem;">



                    <div style="display: flex; justify-content: space-between; align-items: center;">



                        <span style="color: #52647c;">Vehicle &amp; Person:</span>



                        <span style="font-weight: 600; color: #1e293b; font-family: var(--font-mono); font-size: 0.875rem;">${escapeHtml(p.vehName)}</span>



                    </div>



                    <div style="display: flex; justify-content: space-between; align-items: center;">



                        <span style="color: #52647c;">Number Plate:</span>



                        <span style="font-weight: 600; color: #1e293b; font-family: var(--font-mono); font-size: 0.875rem;">${escapeHtml(p.pltName)}</span>



                    </div>







                </div>



                <!-- Latency & Throughput Row -->



                <div style="display: flex; justify-content: space-between; align-items: center; padding: 5px 8px; background: rgba(241,245,249,0.4); border-radius: 4px; font-family: var(--font-mono); font-size: 0.875rem;">



                    <div style="display: flex; align-items: center; gap: 4px;">



                        <span style="color: #52647c;">Latency:</span>



                        <span style="font-weight: 700; color: #0369a1;">~${p.totalMs} ms</span>



                    </div>



                    <div style="display: flex; align-items: center; gap: 4px;">



                        <span style="color: #52647c;">Throughput:</span>



                        <span style="font-weight: 700; color: ${p.themeColor};">~${p.fps} fps</span>



                    </div>



                </div>



                <!-- Operational Guidance Advice -->



                <div style="font-size: 0.875rem; color: #475569; line-height: 1.35; padding: 0 2px;">



                    <div>${escapeHtml(p.useCase)}</div>



                </div>



                <!-- 1-Click Apply Button -->



                <button type="button" onclick="window.applyBenchmarkProfile('${p.key}')" __expr_18__="" style="width: 100%; padding: 6px 12px; font-size: 0.875rem; font-weight: 700; border-radius: 5px; cursor: ${isActive ? 'default' : 'pointer'}; display: flex; align-items: center; justify-content: center; gap: 6px; transition: all 0.15s; ${isActive ? 'background: rgba(16, 185, 129, 0.15); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.4);' : `background: ${p.themeColor}; color: #ffffff; border: 1px solid ${p.themeColor}; box-shadow: 0 2px 8px rgba(0,0,0,0.2);`}">



                    ${isActive ? `



                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>



                        Currently Active Setup



                    ` : `



                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><polygon points="5 3 19 12 5 21 5 3"/></svg>



                        Apply Setup (${p.title.split(' ')[0]})



                    `}



                </button>



            </div>



            `;
    }).join('');
  };
  window.filterBenchmarkTable = function (category) {
    currentBenchmarkFilter = category;
    document.querySelectorAll('.btn-bench-filter').forEach(btn => {
      btn.style.background = 'transparent';
      btn.style.color = '#52647c';
      btn.style.borderColor = 'var(--border-color)';
    });
    const activeBtn = document.getElementById('benchFilter' + (category === 'tracking-ocr' ? 'Ocr' : category.charAt(0).toUpperCase() + category.slice(1)));
    if (activeBtn) {
      activeBtn.style.background = 'rgba(56, 189, 248, 0.2)';
      activeBtn.style.color = '#0369a1';
      activeBtn.style.borderColor = 'rgba(56, 189, 248, 0.4)';
    }
    const scrollDiv = document.getElementById('benchmarkTableScrollDiv');
    if (scrollDiv) scrollDiv.scrollTop = 0;
    window.renderBenchmarkResults();
  };
  window.runBenchmark = async function (forceRefresh = true) {
    const btn = document.getElementById('btnRunBenchmark');
    const indicator = document.getElementById('benchmarkStatusIndicator');
    const statusText = document.getElementById('benchmarkStatusText');
    const tbody = document.getElementById('benchmarkTableBody');
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = `<span class="spinner-sm" style="display:inline-block; width:13px; height:13px; border:2px solid #fff; border-top-color:transparent; border-radius:50%; animation:spin 0.8s linear infinite;"></span> Measuring Hardware Latency...`;
    }
    if (indicator) indicator.style.background = '#f59e0b';
    if (statusText) statusText.textContent = 'Measuring hardware latency & throughput across all local AI models... Please wait.';
    if (tbody) {
      tbody.innerHTML = `



                <div style="display:flex; flex-direction:column; align-items:center; gap:10px;">



                    <div style="width:28px; height:28px; border:3px solid #f59e0b; border-top-color:transparent; border-radius:50%; animation:spin 0.8s linear infinite;"></div>



                    <span style="font-size:0.9225rem; font-weight:700; color:#1e293b;">Measuring hardware latency &amp; throughput...</span>



                    <span style="font-size:0.875rem; color:#52647c;">Testing vehicle detection, plate recognition and tracking on workstation CPU/GPU.</span>



                </div>



            `;
    }
    try {
      const url = forceRefresh ? '/api/benchmark?refresh=true' : '/api/benchmark';
      const res = await fetch(url);
      const data = await res.json();
      if (data.results && data.results.length > 0) {
        currentBenchmarkData = data.results;
        currentBenchmarkRecommendations = data.recommendations || null;
        currentBenchmarkHardware = data.hardware || null;
        window.renderBenchmarkResults();
        if (indicator) indicator.style.background = '#10b981';
        if (statusText) statusText.innerHTML = `✅ Benchmark analysis completed! <strong>${data.results.length} models</strong> measured. Recommendation profiles updated.`;
        if (typeof window.showToastAlert === 'function') {
          window.showToastAlert(`Hardware benchmark completed! Measured ${data.results.length} models on workstation.`, "success", "Benchmark Ready");
        } else if (typeof window.showToast === 'function') {
          window.showToast(`Hardware benchmark completed (${data.results.length} models measured)`, "success");
        }
      } else {
        throw new Error("No benchmark data returned from server.");
      }
    } catch (err) {
      console.error("Benchmark failed:", err);
      if (indicator) indicator.style.background = '#ef4444';
      if (statusText) statusText.textContent = `Benchmark failed: ${err.message}`;
      if (tbody && (!currentBenchmarkData || currentBenchmarkData.length === 0)) {
        tbody.innerHTML = `<tr><td colspan="8" style="padding: 20px; text-align: center; color: #ef4444;">Failed to execute benchmark: ${err.message}</td></tr>`;
      }
      if (typeof window.showToastAlert === 'function') {
        window.showToastAlert(`Benchmark error: ${err.message}`, "error", "Benchmark Error");
      } else if (typeof window.showToast === 'function') {
        window.showToast(`Benchmark error: ${err.message}`, "error");
      }
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M23 4v6h-6"/><path d="M1 20v-6h6"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg> <span>🔄 Re-run Benchmark Analysis</span>`;
      }
    }
  };
  window.renderBenchmarkResults = function () {
    window.renderBenchmarkAdvisorCards();
    const tbody = document.getElementById('benchmarkTableBody');
    if (!tbody) return;
    const results = currentBenchmarkData || [];
    if (!results || results.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" style="padding: 20px; text-align: center; color: #52647c;">No models found to benchmark.</td></tr>`;
      return;
    }
    const cntAll = results.filter(r => r.kind !== 'frame').length;
    const cntVehicle = results.filter(r => r.category === 'vehicle').length;
    const cntPlate = results.filter(r => r.category === 'plate').length;
    const cntOcr = results.filter(r => r.category === 'ocr' || r.category === 'tracking').length;
    const elAll = document.getElementById('benchCountAll');
    if (elAll) elAll.textContent = cntAll;
    const elVeh = document.getElementById('benchCountVehicle');
    if (elVeh) elVeh.textContent = cntVehicle;
    const elPlt = document.getElementById('benchCountPlate');
    if (elPlt) elPlt.textContent = cntPlate;
    const elOcr = document.getElementById('benchCountOcr');
    if (elOcr) elOcr.textContent = cntOcr;
    let filtered = results;
    if (currentBenchmarkFilter === 'vehicle') {
      filtered = results.filter(r => r.kind === 'frame' || r.category === 'vehicle');
    } else if (currentBenchmarkFilter === 'plate') {
      filtered = results.filter(r => r.kind === 'frame' || r.category === 'plate');
    } else if (currentBenchmarkFilter === 'tracking-ocr') {
      filtered = results.filter(r => r.kind === 'frame' || r.category === 'ocr' || r.category === 'tracking');
    }
    tbody.innerHTML = filtered.map(r => {
      if (r.kind === 'frame') {
        return `<tr style="background: rgba(241,245,249,0.4); border-bottom: 1px solid var(--border-color);">



                    <td style="padding: 9px 14px; font-weight: 700; color: #ffffff;">${escapeHtml(r.name)}</td>



                    <td style="padding: 9px 10px; color: #52647c;">${escapeHtml(r.family || 'Reference')}</td>



                    <td colspan="5" style="padding: 9px 10px; color: #64748b; font-family: var(--font-mono); text-align: right;">Standard Reference CCTV Camera Input</td>



                    <td style="padding: 9px 14px; text-align: center;"><span style="padding: 2px 8px; border-radius: 4px; font-size: 0.875rem; font-weight: 700; background: rgba(56, 189, 248, 0.15); color: #0369a1; border: 1px solid rgba(56, 189, 248, 0.3);">${escapeHtml(r.verdict ? r.verdict.label : '720p')}</span></td>



                </tr>`;
      }
      if (r.error) {
        return `<tr style="border-bottom: 1px solid var(--border-color);">



                    <td style="padding: 9px 14px; font-weight: 600; color: #b91c1c;">${escapeHtml(r.name)}</td>



                    <td style="padding: 9px 10px; color: #52647c;">${escapeHtml(r.family || r.kind)}</td>



                    <td colspan="6" style="padding: 9px 14px; color: #b91c1c; font-family: var(--font-mono);">${escapeHtml(r.error)}</td>



                </tr>`;
      }
      let badgeBg = 'rgba(16, 185, 129, 0.15)';
      let badgeColor = '#10b981';
      let badgeBorder = 'rgba(16, 185, 129, 0.4)';
      const vLabel = r.verdict && r.verdict.label ? r.verdict.label : r.max_fps >= 10 ? 'live-ready' : 'borderline';
      const vLevel = r.verdict && r.verdict.level ? r.verdict.level : 'good';
      if (vLevel === 'ok') {
        badgeBg = 'rgba(245, 158, 11, 0.15)';
        badgeColor = '#f59e0b';
        badgeBorder = 'rgba(245, 158, 11, 0.4)';
      } else if (vLevel === 'bad') {
        badgeBg = 'rgba(239, 68, 68, 0.15)';
        badgeColor = '#ef4444';
        badgeBorder = 'rgba(239, 68, 68, 0.4)';
      } else if (vLabel.includes('per-track') || vLabel.includes('best-crop')) {
        badgeBg = 'rgba(99, 102, 241, 0.15)';
        badgeColor = '#818cf8';
        badgeBorder = 'rgba(99, 102, 241, 0.4)';
      }
      const num = v => `<td style="padding: 9px 10px; text-align: right; font-family: var(--font-mono); color: #475569;">${v !== null && v !== undefined ? v + ' ms' : '—'}</td>`;
      return `<tr style="border-bottom: 1px solid var(--border-color); transition: background 0.15s;" onmouseover="this.style.background='rgba(241,245,249,0.3)'" onmouseout="this.style.background='transparent'">



                <td style="padding: 9px 14px; font-weight: 600; color: #ffffff;">${escapeHtml(r.name)}</td>



                <td style="padding: 9px 10px; color: #52647c; font-size: 0.875rem;">${escapeHtml(r.family || r.kind)}</td>



                ${num(r.min_ms)}



                ${num(r.median_ms)}



                ${num(r.mean_ms)}



                ${num(r.max_ms)}



                <td style="padding: 9px 12px; text-align: right; font-family: var(--font-mono); font-weight: 700; color: #0369a1;">${r.max_fps !== null && r.max_fps !== undefined ? r.max_fps + ' fps' : '—'}</td>



                <td style="padding: 9px 14px; text-align: center;">



                    <span style="display: inline-block; padding: 2px 10px; border-radius: 4px; font-size: 0.875rem; font-weight: 700; text-transform: uppercase; background: ${badgeBg}; color: ${badgeColor}; border: 1px solid ${badgeBorder};">



                        ${escapeHtml(vLabel)}



                    </span>



                </td>



            </tr>`;
    }).join('');
  };
  window.openActivePipelineModal = function () {
    const modal = document.getElementById('activePipelineModal');
    if (!modal) return;
    const target = window.currentModelTarget || 'live';
    const targetBadge = document.getElementById('activePipeTargetBadge');
    if (targetBadge) {
      targetBadge.innerText = target === 'upload' ? '📁 MEDIA UPLOAD' : '🎥 LIVE FEED';
      targetBadge.style.background = target === 'upload' ? 'rgba(168, 85, 247, 0.2)' : 'rgba(16, 185, 129, 0.15)';
      targetBadge.style.color = target === 'upload' ? '#d8b4fe' : '#047857';
      targetBadge.style.borderColor = target === 'upload' ? 'rgba(168, 85, 247, 0.4)' : 'rgba(16, 185, 129, 0.35)';
    }
    const selVeh = document.getElementById('selVehicleModel');
    const selPlt = document.getElementById('selPlateModel');
    const selPer = document.getElementById('selPersonModel');
    const vKey = selVeh ? selVeh.value : 'uvh26_yolo11x';
    const pKey = selPlt ? selPlt.value : 'yolo11s_plate';
    const selOcr = document.getElementById('selOcrModel');
    const ocrKey = selOcr ? selOcr.value : 'paddleocr_v4_server';
    const ocrSpec = MODEL_SPECS[ocrKey] || ({
      name: ocrKey,
      origin: "PaddleOCR",
      fps: "45 FPS"
    });
    const isSharedPerson = selPersonModel && selPersonModel.disabled;
    const perKey = isSharedPerson ? vKey : selPer ? selPer.value : 'driveindia_tihan_yolov10x';
    const fKey = 'scrfd_10g';

    const vSpec = MODEL_SPECS[vKey] || ({
      name: vKey,
      origin: "Custom",
      fps: "14 FPS"
    });
    const pSpec = MODEL_SPECS[pKey] || ({
      name: pKey,
      origin: "Custom",
      fps: "48 FPS"
    });
    const perSpec = isSharedPerson ? {
      name: `${vSpec.name} (Shared Dual-Head)`,
      origin: "⚡ Zero Extra Load",
      fps: "Single-Pass"
    } : MODEL_SPECS[perKey] || ({
      name: perKey,
      origin: "Custom",
      fps: "22 FPS"
    });
    const fSpec = MODEL_SPECS[fKey] || ({
      name: fKey,
      origin: "Custom",
      fps: "52 FPS"
    });
    const eSpec = MODEL_SPECS[eKey] || ({
      name: eKey,
      origin: "512-D Vectors",
      fps: "45 FPS"
    });
    function renderCompactModelRow(roleTitle, roleIcon, modelName, specOrigin, speedStr) {
      return `



            <div style="background: rgba(241,245,249,0.75); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px; padding: 8px 12px; display: flex; justify-content: space-between; align-items: center; gap: 10px;">



                <div style="display: flex; align-items: center; gap: 10px; min-width: 0;">



                    <span style="font-size: 1.1rem; flex-shrink: 0;">${roleIcon}</span>



                    <div style="min-width: 0;">



                        <div style="font-size: 0.875rem; color: #52647c; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;">${roleTitle}</div>



                        <div style="font-size: 0.9025rem; color: #ffffff; font-weight: 700; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(modelName)}</div>



                    </div>



                </div>



                <div style="display: flex; align-items: center; gap: 6px; flex-shrink: 0;">



                    ${speedStr ? `<span style="font-size: 0.875rem; color: #047857; font-family: monospace; font-weight: 700; background: rgba(16, 185, 129, 0.12); border: 1px solid rgba(16, 185, 129, 0.3); padding: 2px 6px; border-radius: 4px;">${speedStr}</span>` : ''}



                    <span style="font-size: 0.875rem; color: #0369a1; font-weight: 700; background: rgba(56, 189, 248, 0.12); border: 1px solid rgba(56, 189, 248, 0.3); padding: 2px 6px; border-radius: 4px;">${escapeHtml(specOrigin)}</span>



                </div>



            </div>`;
    }
    const anprContainer = document.getElementById('activePipeAnprList');
    if (anprContainer) {
      anprContainer.innerHTML = [renderCompactModelRow("Vehicle Detector", "🚗", vSpec.name, vSpec.origin, vSpec.fps), renderCompactModelRow("Plate Localizer", "🔍", pSpec.name, pSpec.origin, pSpec.fps), renderCompactModelRow("OCR Recognition Engine", "🔤", ocrSpec.name, ocrSpec.origin, ocrSpec.fps)].join('');
    }
    modal.style.setProperty('display', 'flex', 'important');
  };
  window.closeActivePipelineModal = function () {
    const modal = document.getElementById('activePipelineModal');
    if (modal) modal.style.setProperty('display', 'none', 'important');
  };
  window.addEventListener('click', e => {
    const benchModal = document.getElementById('benchmarkModal');
    if (benchModal && e.target === benchModal) {
      window.closeBenchmarkModal();
    }
    const pipeModal = document.getElementById('activePipelineModal');
    if (pipeModal && e.target === pipeModal) {
      window.closeActivePipelineModal();
    }
  });
  initSearchableDistrictDropdowns();
  fetchAndRenderUnifiedLiveFeed();
  setInterval(fetchAndRenderUnifiedLiveFeed, 500);
  fetchAndRenderCapturedDb();
  fetchAndRenderResults();
  fetchAndRenderVehicleDb();
  fetchAndRenderVehicleTrail();
  fetchActiveAlerts();
  setInterval(fetchActiveAlerts, 500);
});
function escapeHtml(str) {
  if (!str) return '';
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}
window.escapeHtml = escapeHtml;
window.openImageZoomModal = (imgSrc, caption) => {
  const modal = document.getElementById('globalImageZoomModal');
  const img = document.getElementById('globalZoomModalImg');
  const cap = document.getElementById('globalZoomModalCaption');
  if (!modal || !img) return;
  img.src = imgSrc || '/static/icons/default-avatar.png';
  if (cap) cap.innerText = caption || 'High-Resolution Target View';
  modal.style.display = 'flex';
};
window.closeImageZoomModal = e => {
  if (e && e.stopPropagation) e.stopPropagation();
  const modal = document.getElementById('globalImageZoomModal');
  if (modal) modal.style.display = 'none';
};
window.ALL_MV_SECTIONS = [{
  code: "Sec 129 r/w 194D",
  title: "Riding Without Helmet / Headgear",
  fine: 1000,
  keywords: "helmet head headgear bare safety"
}, {
  code: "Sec 128 r/w 194C",
  title: "Overloading Two-Wheeler / Triple Riding",
  fine: 1000,
  keywords: "triple riding overload passenger bike scooter"
}, {
  code: "Sec 184(c)",
  title: "Dangerous / Reckless / Rash Driving",
  fine: 5000,
  keywords: "rash dangerous reckless speed zigzag drive"
}, {
  code: "Sec 184(f)",
  title: "Using Handheld Mobile Phone While Driving",
  fine: 5000,
  keywords: "mobile phone call talking texting cell"
}, {
  code: "Sec 119 r/w 177",
  title: "Jumping Red Light / Traffic Signal Disobedience",
  fine: 1000,
  keywords: "red light signal jumping zebra cross stop"
}, {
  code: "Sec 183(1)",
  title: "Over-speeding (Light Motor Vehicle / Bike / Car)",
  fine: 2000,
  keywords: "overspeeding speed limit fast racing"
}, {
  code: "Sec 185",
  title: "Drunk & Drive / Driving Under Influence of Alcohol",
  fine: 10000,
  keywords: "drunk alcohol booze beer wine drug dwi dui"
}, {
  code: "Sec 190(2)",
  title: "Pollution Violation / Without Valid PUC Certificate",
  fine: 10000,
  keywords: "puc pollution smoke emission certificate"
}, {
  code: "Sec 181",
  title: "Driving Without Valid Driving Licence (DL)",
  fine: 5000,
  keywords: "licence license dl without expired no dl"
}, {
  code: "Sec 180",
  title: "Allowing Unauthorized Person / Minor to Drive Vehicle",
  fine: 5000,
  keywords: "minor child unauthorized person allow"
}, {
  code: "Sec 199A",
  title: "Offences by Juveniles / Minors",
  fine: 25000,
  keywords: "juvenile minor student kid school"
}, {
  code: "Sec 196",
  title: "Driving Uninsured Vehicle (Without Insurance)",
  fine: 2000,
  keywords: "insurance uninsured third party policy"
}, {
  code: "Sec 194E",
  title: "Blocking Emergency Vehicles (Ambulance / Fire Brigade)",
  fine: 10000,
  keywords: "ambulance emergency fire brigade hospital block"
}, {
  code: "Sec 194B(1)",
  title: "Driving Without Wearing Safety Seatbelt",
  fine: 1000,
  keywords: "seatbelt belt seat buckle"
}, {
  code: "Sec 177A",
  title: "Wrong-Side Driving / Driving Against One-Way",
  fine: 1000,
  keywords: "wrong side one way opposite direction"
}, {
  code: "Sec 39 r/w 192",
  title: "Driving Without Number Plate / Unregistered Vehicle",
  fine: 5000,
  keywords: "no plate number plate unregistered rc"
}, {
  code: "Sec 50 r/w 177",
  title: "Defective, Fancy, Obscured, or Illegal Number Plate",
  fine: 1000,
  keywords: "fancy plate defective font obscure illegal plate"
}, {
  code: "Sec 194F(b)",
  title: "Use of Modified Loud Silencer / Pressure Horn",
  fine: 2000,
  keywords: "silencer modified bullet noise pressure horn loud"
}, {
  code: "Sec 194F(a)",
  title: "Unnecessary Honking in Silent / Hospital Zone",
  fine: 1000,
  keywords: "horn honking silent zone hospital sound"
}, {
  code: "Sec 100 r/w 177",
  title: "Using Tinted / Dark Black Glass Film on Vehicle",
  fine: 1000,
  keywords: "tinted glass black film window dark"
}, {
  code: "Sec 192A",
  title: "Using Vehicle Without Valid Route Permit",
  fine: 10000,
  keywords: "permit commercial route taxi bus auto"
}, {
  code: "Sec 189",
  title: "Illegal Street Racing / Speed Trials on Public Road",
  fine: 5000,
  keywords: "racing race stunts stunt trial wheelie"
}, {
  code: "Sec 179(1)",
  title: "Disobedience of Orders of Lawful Traffic Authority",
  fine: 2000,
  keywords: "police disobey stop refuse order authority"
}, {
  code: "Sec 177",
  title: "General Traffic Violation (Default)",
  fine: 500,
  keywords: "general default rules regulation other"
}];
window._activeViolFilter = 'ALL';
window._cachedViolations = [];
let _violSearchDebounce = null;
window.refreshViolatorsList = function () {
  window.fetchAndRenderViolators();
};
window.filterViolations = function (filterType) {
  window._activeViolFilter = filterType;
  document.getElementById('violFilterCardAll')?.classList.toggle('active', filterType === 'ALL');
  document.getElementById('violFilterCardTriple')?.classList.toggle('active', filterType === 'TRIPLE');
  document.getElementById('violFilterCardHelmet')?.classList.toggle('active', filterType === 'HELMET');
  window.renderViolationsTable();
};
window.debounceViolSearch = function () {
  clearTimeout(_violSearchDebounce);
  _violSearchDebounce = setTimeout(() => {
    window.renderViolationsTable();
  }, 250);
};
window.fetchAndRenderViolators = async function () {
  try {
    const [violRes, statsRes] = await Promise.all([fetch('/api/violations?limit=200'), fetch('/api/violations/stats')]);
    if (violRes.ok) {
      const data = await violRes.json();
      window._cachedViolations = data.violations || [];
    }
    if (statsRes.ok) {
      const sData = await statsRes.json();
      const s = sData.stats || ({});
      const totalCount = s.total_violations || window._cachedViolations.length;
      const tripleCount = s.triple_riding_count || 0;
      const helmetCount = s.without_helmet_count || 0;
      const fineTotal = s.total_penalty_assessed || 0;
      const badge = document.getElementById('navViolatorsCountBadge');
      if (badge) badge.innerText = totalCount;
      const statTot = document.getElementById('statTotalViol');
      if (statTot) statTot.innerText = totalCount;
      const statTrip = document.getElementById('statTripleCount');
      if (statTrip) statTrip.innerText = tripleCount;
      const statHelm = document.getElementById('statHelmetCount');
      if (statHelm) statHelm.innerText = helmetCount;
      const statPen = document.getElementById('statTotalPenalty');
      if (statPen) statPen.innerText = `₹${fineTotal.toLocaleString('en-IN')}`;
    }
    window.renderViolationsTable();
  } catch (err) {
    console.error('Error fetching traffic violations:', err);
  }
};
window.renderViolationsTable = function () {
  const tbody = document.getElementById('violTableBody');
  if (!tbody) return;
  const query = (document.getElementById('violSearchInput')?.value || '').trim().toUpperCase();
  const filter = window._activeViolFilter;
  let items = window._cachedViolations.filter(v => {
    const pNum = (v.plate_number || '').toUpperCase();
    const vType = (v.violation_type || '').toUpperCase();
    const loc = (v.camera_location || '').toUpperCase();
    if (query && !pNum.includes(query) && !vType.includes(query) && !loc.includes(query)) {
      return false;
    }
    if (filter === 'TRIPLE') {
      return vType.includes('TRIPLE');
    } else if (filter === 'HELMET') {
      return vType.includes('HELMET') || vType.includes('WITHOUT');
    }
    return true;
  });
  const counter = document.getElementById('violCountIndicator');
  if (counter) counter.innerText = `Showing ${items.length} of ${window._cachedViolations.length} records`;
  if (items.length === 0) {
    tbody.innerHTML = `
            <tr>
                <td colspan="7" style="padding: 40px; text-align: center; color: #52647c;">
                    No traffic violations matching the current filter criteria.
                </td>
            </tr>
        `;
    return;
  }
  tbody.innerHTML = items.map(v => {
    const vId = v.id;
    const plate = escapeHtml(v.plate_number || 'UNKNOWN');
    const vType = escapeHtml(v.violation_type || 'TRAFFIC VIOLATION');
    const loc = escapeHtml(v.camera_location || 'Surveillance Gate');
    const timeStr = v.timestamp ? v.timestamp.includes('T') ? v.timestamp.replace('T', ' ').substring(0, 19) : v.timestamp : 'Recent';
    const unhelmeted = v.unhelmeted_count || 1;
    const fine = v.total_fine || 1000;
    const sections = Array.isArray(v.applied_sections) ? v.applied_sections : [];
    const isTriple = vType.toUpperCase().includes('TRIPLE');
    const sectionBadges = sections.map((sec, idx) => `
            <span style="background: rgba(56, 189, 248, 0.15); border: 1px solid rgba(56, 189, 248, 0.4); color: #0369a1; font-size: 0.875rem; padding: 2px 6px; border-radius: 4px; display: inline-flex; align-items: center; gap: 4px; margin: 2px;">
                <strong>${escapeHtml(sec.code)}</strong>: ₹${sec.fine}
                <button type="button" onclick="window.removeViolCustomSection('${vId}', ${idx})" style="background: transparent; border: none; color: #52647c; font-size: 14px; cursor: pointer; padding: 0 2px;">&times;</button>
            </span>
        `).join('');
    return `
            <tr style="border-bottom: 1px solid rgba(255, 255, 255, 0.05); transition: background 0.15s;" onmouseover="this.style.background='rgba(255,255,255,0.02)'" onmouseout="this.style.background='transparent'">
                <td style="padding: 14px 18px;">
                    <div style="font-weight: 700; color: #fff; font-family: monospace; font-size: 0.8825rem;">${escapeHtml(vId)}</div>
                    <div style="font-size: 0.875rem; color: #52647c; margin-top: 2px;">📍 ${loc} &bull; 🕒 ${timeStr}</div>
                </td>
                <td style="padding: 14px 18px;">
                    <div style="background: #000; border: 1.5px solid #f59e0b; color: #92400e; font-family: monospace; font-weight: 800; font-size: 1.0125rem; padding: 3px 8px; border-radius: 4px; display: inline-block;">${plate}</div>
                    <div style="font-size: 0.875rem; color: #64748b; margin-top: 4px;">Two-Wheeler</div>
                </td>
                <td style="padding: 14px 18px;">
                    <span style="background: rgba(245, 158, 11, 0.2); border: 1px solid #f59e0b; color: #92400e; font-size: 0.875rem; font-weight: 700; padding: 3px 8px; border-radius: 4px; display: inline-block;">
                        ⚠️ ${vType}
                    </span>
                    <div style="font-size: 0.875rem; color: #52647c; margin-top: 4px;">Riders: ${v.rider_count || (isTriple ? 3 : 1)} Seated</div>
                </td>
                <td style="padding: 14px 18px;">
                    <div style="display: flex; align-items: center; gap: 6px;">
                        <button onclick="window.adjustViolHelmet('${vId}', -1)" style="width: 24px; height: 24px; background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.15); color: #fff; border-radius: 4px; cursor: pointer; font-weight: 800;">−</button>
                        <span style="font-family: monospace; font-size: 0.8825rem; color: #facc15; font-weight: 700; min-width: 65px; text-align: center;">${unhelmeted} Rider${unhelmeted !== 1 ? 's' : ''}</span>
                        <button onclick="window.adjustViolHelmet('${vId}', 1)" style="width: 24px; height: 24px; background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.15); color: #fff; border-radius: 4px; cursor: pointer; font-weight: 800;">+</button>
                    </div>
                </td>
                <td style="padding: 14px 18px;">
                    <div style="display: flex; flex-wrap: wrap; gap: 4px; align-items: center;">
                        ${isTriple ? '<span style="background: rgba(245, 158, 11, 0.15); border: 1px solid rgba(245, 158, 11, 0.4); color: #92400e; font-size: 0.875rem; padding: 2px 6px; border-radius: 4px;">Sec 128 (₹1,000)</span>' : ''}
                        <span style="background: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.4); color: #991b1b; font-size: 0.875rem; padding: 2px 6px; border-radius: 4px;">Sec 129 (&times; ₹1,000)</span>
                        ${sectionBadges}
                        <div style="position: relative; display: inline-block;">
                            <button type="button" onclick="window.toggleViolMvMenu('${vId}', event)" style="background: rgba(59, 130, 246, 0.15); border: 1px solid #3b82f6; color: #1d4ed8; font-size: 0.875rem; font-weight: 700; padding: 2px 8px; border-radius: 4px; cursor: pointer;">
                                ➕ Add Section
                            </button>
                            <div class="mv-sections-popover" id="popover-${vId}" style="position: absolute; top: calc(100% + 4px); left: 0; width: 340px; max-height: 280px; background: #f4f7fb; border: 1px solid #3b82f6; border-radius: 8px; box-shadow: 0 10px 30px rgba(0,0,0,0.8); z-index: 1000; display: none; flex-direction: column; overflow: hidden;" onclick="event.stopPropagation()">
                                <div style="padding: 8px; background: #e2e8f0; border-bottom: 1px solid rgba(255,255,255,0.1);">
                                    <input type="text" placeholder="Search section or keyword..." oninput="window.filterViolMvList(this, 'list-${vId}', '${vId}')" style="width: 100%; background: #f8fafc; border: 1px solid rgba(255,255,255,0.2); border-radius: 6px; padding: 6px 10px; color: #fff; font-size: 0.875rem; outline: none;">
                                </div>
                                <div id="list-${vId}" style="overflow-y: auto; max-height: 220px; padding: 4px;"></div>
                            </div>
                        </div>
                    </div>
                </td>
                <td style="padding: 14px 18px; text-align: right;">
                    <div style="font-size: 1.15rem; font-weight: 800; color: #10b981; font-family: monospace;">₹${fine.toLocaleString('en-IN')}</div>
                    <div style="font-size: 0.875rem; color: #6ee7b7;">Assessed Fine</div>
                </td>
                <td style="padding: 14px 18px; text-align: center;">
                    <button onclick="window.openSplitViolationModal('${vId}')" style="background: rgba(245, 158, 11, 0.15); border: 1px solid #f59e0b; color: #92400e; font-size: 0.875rem; font-weight: 700; padding: 6px 12px; border-radius: 6px; cursor: pointer;">
                        🔍 Inspect
                    </button>
                </td>
            </tr>
        `;
  }).join('');
};
window.adjustViolHelmet = async function (violId, delta) {
  const record = window._cachedViolations.find(v => v.id === violId);
  if (!record) return;
  const currentCount = record.unhelmeted_count || 1;
  const newCount = Math.max(0, Math.min(3, currentCount + delta));
  if (newCount === currentCount) return;
  record.unhelmeted_count = newCount;
  const tripleFine = (record.violation_type || '').toUpperCase().includes('TRIPLE') ? 1000 : 0;
  const customFine = (record.applied_sections || []).reduce((acc, s) => acc + (s.fine || 0), 0);
  record.total_fine = newCount * 1000 + tripleFine + customFine;
  window.renderViolationsTable();
  try {
    await fetch(`/api/violations/${violId}/update`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        unhelmeted_count: newCount,
        applied_sections: record.applied_sections || [],
        total_fine: record.total_fine
      })
    });
  } catch (e) {
    console.error('Failed to sync updated fine:', e);
  }
};
window.addViolCustomSection = async function (violId, section) {
  const record = window._cachedViolations.find(v => v.id === violId);
  if (!record) return;
  if (!Array.isArray(record.applied_sections)) record.applied_sections = [];
  const exists = record.applied_sections.some(s => s.code === section.code);
  if (exists) {
    alert(`Section ${section.code} is already added!`);
    return;
  }
  record.applied_sections.push(section);
  const unhelmeted = record.unhelmeted_count || 1;
  const tripleFine = (record.violation_type || '').toUpperCase().includes('TRIPLE') ? 1000 : 0;
  const customFine = record.applied_sections.reduce((acc, s) => acc + (s.fine || 0), 0);
  record.total_fine = unhelmeted * 1000 + tripleFine + customFine;
  window.closeAllMvMenus();
  window.renderViolationsTable();
  try {
    await fetch(`/api/violations/${violId}/update`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        unhelmeted_count: unhelmeted,
        applied_sections: record.applied_sections,
        total_fine: record.total_fine
      })
    });
  } catch (e) {
    console.error('Failed to sync section update:', e);
  }
};
window.removeViolCustomSection = async function (violId, index) {
  const record = window._cachedViolations.find(v => v.id === violId);
  if (!record || !Array.isArray(record.applied_sections)) return;
  record.applied_sections.splice(index, 1);
  const unhelmeted = record.unhelmeted_count || 1;
  const tripleFine = (record.violation_type || '').toUpperCase().includes('TRIPLE') ? 1000 : 0;
  const customFine = record.applied_sections.reduce((acc, s) => acc + (s.fine || 0), 0);
  record.total_fine = unhelmeted * 1000 + tripleFine + customFine;
  window.renderViolationsTable();
  try {
    await fetch(`/api/violations/${violId}/update`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        unhelmeted_count: unhelmeted,
        applied_sections: record.applied_sections,
        total_fine: record.total_fine
      })
    });
  } catch (e) {
    console.error('Failed to sync section deletion:', e);
  }
};
window.toggleViolMvMenu = function (violId, event) {
  if (event) event.stopPropagation();
  const pop = document.getElementById(`popover-${violId}`);
  if (!pop) return;
  const isOpen = pop.style.display === 'flex';
  window.closeAllMvMenus();
  if (!isOpen) {
    pop.style.display = 'flex';
    const listContainer = document.getElementById(`list-${violId}`);
    if (listContainer) {
      window.renderViolMvList(listContainer, window.ALL_MV_SECTIONS, violId);
    }
  }
};
window.filterViolMvList = function (input, listId, violId) {
  const q = (input.value || '').toLowerCase().trim();
  const container = document.getElementById(listId);
  if (!container) return;
  const filtered = window.ALL_MV_SECTIONS.filter(s => {
    return s.code.toLowerCase().includes(q) || s.title.toLowerCase().includes(q) || s.keywords.toLowerCase().includes(q);
  });
  window.renderViolMvList(container, filtered, violId);
};
window.renderViolMvList = function (container, sections, violId) {
  if (sections.length === 0) {
    container.innerHTML = '<div style="padding: 10px; font-size: 0.875rem; color: #64748b; text-align: center;">No matching MV Act sections found.</div>';
    return;
  }
  container.innerHTML = sections.map(sec => `
        <div onclick="window.addViolCustomSection('${violId}', ${JSON.stringify(sec).replace(/"/g, '&quot;')})" style="padding: 6px 8px; border-radius: 6px; cursor: pointer; border-bottom: 1px solid rgba(255,255,255,0.04); display: flex; justify-content: space-between; align-items: center; transition: background 0.15s;" onmouseover="this.style.background='rgba(59,130,246,0.2)'" onmouseout="this.style.background='transparent'">
            <div>
                <div style="color: #0369a1; font-weight: 700; font-family: monospace; font-size: 0.875rem;">${escapeHtml(sec.code)}</div>
                <div style="font-size: 0.875rem; color: #475569; line-height: 1.2;">${escapeHtml(sec.title)}</div>
            </div>
            <div style="color: #4ade80; font-weight: 700; font-family: monospace; font-size: 0.875rem; margin-left: 8px;">₹${sec.fine}</div>
        </div>
    `).join('');
};
window.closeAllMvMenus = function () {
  document.querySelectorAll('.mv-sections-popover').forEach(p => p.style.display = 'none');
};
document.addEventListener('click', () => {
  window.closeAllMvMenus();
});
window._activeSplitViolationTarget = null;
window._activeSplitViolationCaptureId = null;
window.launchOriginalVerifiableModal = function () {
  let capId = window._activeSplitViolationCaptureId;
  if (!capId && window._activeSplitViolationTarget) {
    if (typeof window._activeSplitViolationTarget.id === 'number') {
      capId = window._activeSplitViolationTarget.id;
    } else if (window._activeSplitViolationTarget.capture_id) {
      capId = window._activeSplitViolationTarget.capture_id;
    } else if (window._activeSplitViolationTarget.plate_number === 'HR20BE1054') {
      capId = 77;
    }
  }
  if (typeof capId === 'string' && capId.startsWith('VIOL_')) {
    const plate = window._activeSplitViolationTarget ? window._activeSplitViolationTarget.plate_number : null;
    if (plate === 'HR20BE1054') {
      capId = 77;
    } else if (window._activeSplitViolationTarget && window._activeSplitViolationTarget.capture_id) {
      capId = window._activeSplitViolationTarget.capture_id;
    }
  }
  if (!capId) {
    alert('Capture reference not found for verifiable steps.');
    return;
  }
  window.closeSplitViolationModal();
  if (typeof window.openCaptureDetailModal === 'function') {
    window.openCaptureDetailModal(capId);
  }
};
window.openSplitViolationModal = async function (vehicleOrId) {
  let target = null;
  if (typeof vehicleOrId === 'object' && vehicleOrId !== null) {
    target = vehicleOrId;
  } else if (typeof vehicleOrId === 'number' || typeof vehicleOrId === 'string' && (/^\d+$/).test(vehicleOrId)) {
    const numId = Number(vehicleOrId);
    if (window._freshVehiclesCache && window._freshVehiclesCache.has(numId)) {
      target = window._freshVehiclesCache.get(numId);
    } else {
      try {
        const res = await fetch(`/api/captured/${vehicleOrId}`);
        if (res.ok) {
          const data = await res.json();
          target = data.capture;
        }
      } catch (e) {
        console.error('Error fetching capture for split modal:', e);
      }
    }
  } else if (typeof vehicleOrId === 'string') {
    target = window._cachedViolations ? window._cachedViolations.find(v => v.id === vehicleOrId || v.plate_number === vehicleOrId) : null;
  }
  if (!target) {
    alert('Violation record could not be loaded.');
    return;
  }
  window._activeSplitViolationTarget = target;
  window._activeSplitViolationCaptureId = target.id || null;
  const modal = document.getElementById('modalSplitViolation');
  if (!modal) return;
  const plate = target.display_plate || target.plate_number || 'UNKNOWN';
  const loc = target.camera_location || target.location || 'Surveillance Gate (Cam-02)';
  const timeStr = target.timestamp || target.captured_at || 'Just now';
  const vType = target.violation_type || (target.is_traffic_violation ? 'TRAFFIC VIOLATION' : 'SOLO DRIVER WITHOUT HELMET');
  const fine = target.total_fine || target.violation_fine || 1000;
  const unhelmeted = target.unhelmeted_count || 1;
  const isTriple = vType.toUpperCase().includes('TRIPLE') || target.notes && target.notes.toLowerCase().includes('triple');
  const rankBadge = document.getElementById('splitModalRankBadge');
  if (rankBadge) rankBadge.innerText = `#${target.id || 77}`;
  const plateElem = document.getElementById('splitModalPlateText');
  if (plateElem) plateElem.innerText = plate;
  const subElem = document.getElementById('splitModalSubtitle');
  if (subElem) subElem.innerHTML = `Captured at <strong>${escapeHtml(timeStr)}</strong> &bull; Location: <strong>${escapeHtml(loc)}</strong>`;
  const vTitle = document.getElementById('splitModalViolationTitle');
  if (vTitle) vTitle.innerText = vType.toUpperCase();
  const vDesc = document.getElementById('splitModalViolationDesc');
  const lawTag = document.getElementById('splitModalLawTag');
  const bFine = document.getElementById('splitModalBannerFine');
  if (bFine) bFine.innerText = `₹${Number(fine).toLocaleString('en-IN')}`;
  if (isTriple) {
    if (vDesc) vDesc.innerText = 'Compound Offense: Triple Riding detected under Sec 128/194C + Protective headgear compliance under Sec 129/194D.';
    if (lawTag) lawTag.innerText = 'MV Act Sec 128/194C & 129/194D';
  } else {
    if (vDesc) vDesc.innerText = 'Statutory violation under Motor Vehicles Act detected via High-Accuracy YOLO Vision Specialist.';
    if (lawTag) lawTag.innerText = 'MV Act Sec 129 r/w 194D';
  }
  let rawImgUrl = '';
  let annotImgUrl = '';
  if (target.evidence_image) {
    rawImgUrl = target.evidence_image;
    annotImgUrl = target.evidence_image;
  } else if (target.plate_number === 'HR20BE1054' || target.id == 77) {
    rawImgUrl = '/static/raw_scene_HR20BE1054.jpg';
    annotImgUrl = '/static/test_result_model5_rahul.jpg';
  } else if (target.plate_number === 'DL08AB4421') {
    rawImgUrl = target.vehicle_pic_path || '/static/annotated_scenario_1_triple_riding.jpg';
    annotImgUrl = '/static/annotated_scenario_1_triple_riding.jpg';
  } else {
    rawImgUrl = target.vehicle_pic_path || target.annotated_pic_path || '/static/raw_scene_HR20BE1054.jpg';
    annotImgUrl = target.annotated_pic_path || target.vehicle_pic_path || '/static/test_result_model5_rahul.jpg';
  }
  const rawElem = document.getElementById('splitModalRawImg');
  if (rawElem) rawElem.src = rawImgUrl;
  const annotElem = document.getElementById('splitModalAnnotatedImg');
  if (annotElem) annotElem.src = annotImgUrl;
  const camLocTag = document.getElementById('splitModalCamLoc');
  if (camLocTag) camLocTag.innerText = loc;
  const detTag = document.getElementById('splitModalDetectionTag');
  if (detTag) detTag.innerText = isTriple ? 'triple_riding: 3 occupants' : 'without_helmet: 82%';
  const cardRule = document.getElementById('splitModalCardRule');
  if (cardRule) cardRule.innerText = isTriple ? 'Sec 128 & 129' : 'Sec 129 / 194D';
  const cardConf = document.getElementById('splitModalCardConf');
  if (cardConf) cardConf.innerText = isTriple ? '91.4%' : '82.2%';
  const cardMult = document.getElementById('splitModalCardMultiplier');
  if (cardMult) cardMult.innerText = `${unhelmeted} Rider${unhelmeted !== 1 ? 's' : ''}`;
  const cardFine = document.getElementById('splitModalCardFine');
  if (cardFine) cardFine.innerText = `₹${Number(fine).toLocaleString('en-IN')}`;
  modal.style.display = 'flex';
};
window.closeSplitViolationModal = function () {
  const modal = document.getElementById('modalSplitViolation');
  if (modal) modal.style.display = 'none';
};
window.batchUploadQueue = [];
window.recentUploadBatchDetections = [];
window.currentBatchViewMode = 'all';
window.activeLocationPickerFileId = null;
let locationPickerLeafletMap = null;
let locationPickerMarker = null;
let routeLeafletMap = null;
let routeMapLayers = [];
let nominatimSearchTimer = null;
const PANIPAT_NAKA_PRESETS = [{
  name: 'Panipat Toll Plaza (GT Road)',
  lat: 29.3909,
  lng: 76.9635
}, {
  name: 'Sanjay Chowk Flyover Naka',
  lat: 29.3980,
  lng: 76.9720
}, {
  name: 'Assandh Road Checkpoint',
  lat: 29.4012,
  lng: 76.9511
}, {
  name: 'Gohana Road Naka Exit',
  lat: 29.3850,
  lng: 76.9550
}, {
  name: 'Model Town Panipat Post',
  lat: 29.3890,
  lng: 76.9780
}, {
  name: 'Sector 12 HUDA Ground Checkpoint',
  lat: 29.3950,
  lng: 76.9850
}];
function formatFileSize(bytes) {
  if (!bytes || bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}
window.addFilesToBatchQueue = function (files) {
  if (!files || files.length === 0) return;
  const now = new Date();
  const pad = n => String(n).padStart(2, '0');
  const defaultIso = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}`;
  files.forEach((f, idx) => {
    const preset = {name:'Uploaded media',lat:null,lng:null};
    let capturedAt = defaultIso;
    const nameMatch = f.name.match(/(\d{4})[-_]?(\d{2})[-_]?(\d{2})[-_]?(\d{2})[-_]?(\d{2})/);
    if (nameMatch) {
      try {
        capturedAt = `${nameMatch[1]}-${nameMatch[2]}-${nameMatch[3]}T${nameMatch[4]}:${nameMatch[5]}`;
      } catch (e) {}
    }
    const defaultCam = (window.karnalCameraRegistry && typeof window.karnalCameraRegistry.getDefaultCamera === 'function') ? window.karnalCameraRegistry.getDefaultCamera() : null;
    const initialCamId = defaultCam ? defaultCam.id : (preset.name === 'Namastey Chowk 1' ? 'KNL-ICCC-036-C01' : null);
    const initialLocName = defaultCam ? defaultCam.name : (preset.name || 'Namastey Chowk 1');
    const initialLat = defaultCam ? defaultCam.lat : null;
    const initialLng = defaultCam ? defaultCam.lng : null;
    window.batchUploadQueue.push({
      id: 'batch_' + Date.now() + '_' + Math.random().toString(36).substring(2, 7),
      file: f,
      name: f.name,
      size: f.size,
      isVideo: f.type.startsWith('video/') || (/\.(mp4|mov|avi|mkv|webm)$/i).test(f.name),
      locationName: initialLocName,
      cameraId: initialCamId,
      lat: initialLat,
      lng: initialLng,
      capturedAt: capturedAt,
      status: 'ready'
    });
  });
  window.renderBatchQueueUI();
  if (typeof showToastAlert === 'function') {
    showToastAlert(`Added ${files.length} file(s) to Forensic Staging Queue.`, "info", "Batch Queue Updated");
  }
};
window.removeFileFromBatchQueue = function (id) {
  window.batchUploadQueue = window.batchUploadQueue.filter(item => item.id !== id);
  window.renderBatchQueueUI();
};
window.clearBatchQueue = function () {
  window.batchUploadQueue = [];
  window.renderBatchQueueUI();
};
window.updateBatchFileTime = function (id, newTime) {
  const item = window.batchUploadQueue.find(i => i.id === id);
  if (item) item.capturedAt = newTime;
};
window.renderBatchQueueUI = function () {
  const queueSec = document.getElementById('batchUploadQueueSection');
  const queueList = document.getElementById('batchQueueList');
  const badge = document.getElementById('batchQueueCountBadge');
  if (!queueSec || !queueList) return;
  if (window.batchUploadQueue.length === 0) {
    queueSec.style.display = 'none';
    return;
  }
  queueSec.style.display = 'block';
  if (badge) badge.innerText = `${window.batchUploadQueue.length} File${window.batchUploadQueue.length > 1 ? 's' : ''}`;
  queueList.innerHTML = window.batchUploadQueue.map((item, idx) => {
    const isVid = item.isVideo;
    const icon = isVid ? '🎬' : '📸';
    const typeBadge = isVid ? '<span style="font-size:0.875rem; background:#3b82f6; color:#fff; padding:1px 5px; border-radius:3px;">VIDEO</span>' : '<span style="font-size:0.875rem; background:#f8fafc; color:#fff; padding:1px 5px; border-radius:3px;">PHOTO</span>';
    let statusHtml = '<span style="color:#52647c; font-size:0.875rem;">Ready</span>';
    if (item.status === 'processing') {
      statusHtml = '<span style="color:#0369a1; font-size:0.875rem; font-weight:700;">Analyzing... ⏳</span>';
    } else if (item.status === 'completed') {
      statusHtml = '<span style="color:#10b981; font-size:0.875rem; font-weight:700;">Analyzed ✓</span>';
    } else if (item.status === 'error') {
      statusHtml = '<span style="color:#ef4444; font-size:0.875rem; font-weight:700;">Failed ✕' + (item.error ? '<br><small>' + escapeHtml(item.error) + '</small>' : '') + '</span>';
    }
    return `
            <div style="display:flex; align-items:center; justify-content:space-between; gap:10px; padding:10px 14px; background:rgba(241,245,249,0.7); border:1px solid rgba(255,255,255,0.08); border-radius:8px; flex-wrap:wrap;">
                <div style="display:flex; align-items:center; gap:10px; min-width:220px; flex:1;">
                    <span style="font-size:1.3rem;">${icon}</span>
                    <div>
                        <div style="display:flex; align-items:center; gap:6px;">
                            <span style="font-weight:700; color:#172033; font-size:0.9025rem;">#${idx + 1}. ${escapeHtml(item.name)}</span>
                            ${typeBadge}
                        </div>
                        <span style="font-size:0.875rem; color:#64748b;">${formatFileSize(item.size)}</span>
                    </div>
                </div>

                <!-- Location Selector Button -->
                <div style="display:flex; align-items:center; gap:6px;">
                    <button type="button" class="btn btn-secondary" onclick="window.openLocationPickerModal('${item.id}')" style="padding:5px 12px; font-size:0.875rem; background:rgba(99, 102, 241, 0.15); color:#4338ca; border:1px solid rgba(99, 102, 241, 0.4); display:flex; align-items:center; gap:5px; cursor:pointer;" title="Click to view/select checkpoint on map">
                        <span>📍</span>
                        <span style="max-width:180px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${escapeHtml(item.locationName)}</span>
                    </button>
                </div>

                <!-- Date & Time Input -->
                <div style="display:flex; align-items:center; gap:6px;">
                    <span style="font-size:0.875rem; color:#52647c;">🕒</span>
                    <input type="datetime-local" value="${item.capturedAt}" onchange="window.updateBatchFileTime('${item.id}', this.value)" style="padding:4px 8px; font-size:0.875rem; border-radius:6px; background:#f8fafc; border:1px solid rgba(255,255,255,0.15); color:#fff; outline:none;" title="Forensic incident time">
                </div>

                <!-- Status & Remove -->
                <div style="display:flex; align-items:center; gap:10px;">
                    ${statusHtml}
                    <button type="button" onclick="window.removeFileFromBatchQueue('${item.id}')" style="background:transparent; border:none; color:#52647c; font-size:1.1rem; cursor:pointer; padding:2px;" title="Remove from batch queue">✕</button>
                </div>
            </div>
        `;
  }).join('');
};
window.openLocationPickerModal = function (fileId) {
  window.activeLocationPickerFileId = fileId;
  const item = window.batchUploadQueue.find(i => i.id === fileId);
  if (!item) return;
  const modal = document.getElementById('modalLocationPicker');
  if (!modal) return;
  modal.style.display = 'flex';
  document.getElementById('locPickerTargetFileName').innerText = `For file: ${item.name}`;
  document.getElementById('locPickerDisplayLocationName').innerText = item.locationName;
  document.getElementById('locPickerDisplayCoords').innerText = item.lat == null ? 'Select a registered camera' : `${item.lat}, ${item.lng}`;
  const targetCoords = item.lat == null ? [29.69,76.99] : [item.lat,item.lng];
  setTimeout(() => {
    if (!locationPickerLeafletMap) {
      locationPickerLeafletMap = L.map('locationPickerMap').setView(targetCoords, 13);
      L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors | Haryana Police GIS'
      }).addTo(locationPickerLeafletMap);
      locationPickerMarker = L.marker(targetCoords, {
        draggable: true
      }).addTo(locationPickerLeafletMap);
      locationPickerMarker.on('dragend', function (e) {
        const pos = e.target.getLatLng();
        const lat = Number(pos.lat.toFixed(5));
        const lng = Number(pos.lng.toFixed(5));
        document.getElementById('locPickerDisplayCoords').innerText = `${lat}, ${lng}`;
        document.getElementById('locPickerDisplayLocationName').innerText = `Custom Spot (${lat}, ${lng})`;
      });
      locationPickerLeafletMap.on('click', function (e) {
        const lat = Number(e.latlng.lat.toFixed(5));
        const lng = Number(e.latlng.lng.toFixed(5));
        locationPickerMarker.setLatLng([lat, lng]);
        document.getElementById('locPickerDisplayCoords').innerText = `${lat}, ${lng}`;
        document.getElementById('locPickerDisplayLocationName').innerText = `Custom Spot (${lat}, ${lng})`;
      });
    } else {
      locationPickerLeafletMap.invalidateSize();
      locationPickerLeafletMap.setView(targetCoords, 13);
      if (locationPickerMarker) locationPickerMarker.setLatLng(targetCoords);
    }
  }, 20);
};
window.closeLocationPickerModal = function () {
  const modal = document.getElementById('modalLocationPicker');
  if (modal) modal.style.display = 'none';
};
window.debounceNominatimSearch = function (query) {
  if (nominatimSearchTimer) clearTimeout(nominatimSearchTimer);
  const resultsContainer = document.getElementById('locPickerSearchResults');
  if (!query || query.trim().length < 3) {
    if (resultsContainer) resultsContainer.style.display = 'none';
    return;
  }
  nominatimSearchTimer = setTimeout(async () => {
    try {
      const url = `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(query)}&countrycodes=in&limit=5`;
      const res = await fetch(url, {
        headers: {
          'Accept-Language': 'en'
        }
      });
      if (!res.ok) return;
      const data = await res.json();
      if (data && data.length > 0) {
        resultsContainer.style.display = 'block';
        resultsContainer.innerHTML = data.map(place => {
          const cleanName = place.display_name.split(',').slice(0, 3).join(',');
          return `
                        <div class="loc-search-item" onclick="window.selectNominatimPlace('${escapeHtml(cleanName).replace(/'/g, "\\'")}', ${place.lat}, ${place.lon})">
                            📍 <strong>${escapeHtml(cleanName)}</strong>
                            <small style="display:block; color:#52647c; font-size:0.875rem;">${escapeHtml(place.display_name)}</small>
                        </div>
                    `;
        }).join('');
      } else {
        resultsContainer.style.display = 'none';
      }
    } catch (e) {
      console.error("Nominatim search error:", e);
    }
  }, 350);
};
window.selectNominatimPlace = function (displayName, lat, lon) {
  const resultsContainer = document.getElementById('locPickerSearchResults');
  if (resultsContainer) resultsContainer.style.display = 'none';
  document.getElementById('locPickerSearchInput').value = displayName;
  document.getElementById('locPickerDisplayLocationName').innerText = displayName;
  document.getElementById('locPickerDisplayCoords').innerText = `${Number(lat).toFixed(4)}, ${Number(lon).toFixed(4)}`;
  if (locationPickerLeafletMap && locationPickerMarker) {
    const coords = [Number(lat), Number(lon)];
    locationPickerLeafletMap.flyTo(coords, 15);
    locationPickerMarker.setLatLng(coords);
  }
};
window.selectNakaPreset = function (name, lat, lon) {
  document.getElementById('locPickerDisplayLocationName').innerText = name;
  document.getElementById('locPickerDisplayCoords').innerText = `${lat.toFixed(4)}, ${lon.toFixed(4)}`;
  if (locationPickerLeafletMap && locationPickerMarker) {
    const coords = [lat, lon];
    locationPickerLeafletMap.flyTo(coords, 15);
    locationPickerMarker.setLatLng(coords);
  }
};
window.confirmLocationSelection = function () {
  if (!window.activeLocationPickerFileId) return;
  const item = window.batchUploadQueue.find(i => i.id === window.activeLocationPickerFileId);
  if (item && locationPickerMarker) {
    const pos = locationPickerMarker.getLatLng();
    item.lat = Number(pos.lat.toFixed(5));
    item.lng = Number(pos.lng.toFixed(5));
    item.locationName = document.getElementById('locPickerDisplayLocationName').innerText || 'Panipat Checkpoint';
  }
  window.closeLocationPickerModal();
  window.renderBatchQueueUI();
};
window.formatEvidenceImageSrc = function (src, fallback = '/static/benchmark_sample.jpg') {
  if (!src) return fallback;
  if (typeof src !== 'string') return fallback;
  src = src.trim();
  if (!src) return fallback;
  if (src.startsWith('data:image/') || src.startsWith('blob:') || src.startsWith('http://') || src.startsWith('https://')) {
    return src;
  }
  if (src.startsWith('/9j/') || src.startsWith('9j/') || src.startsWith('iVBORw0KGgo') || !src.includes('/') && src.length > 50 || src.startsWith('/') && src.length > 250 && !src.includes(' ') && !src.includes('.')) {
    return `data:image/jpeg;base64,${src}`;
  }
  if (src.startsWith('/')) {
    return src;
  }
  return '/' + src;
};
window.startBatchAnalysis = async function () {
  if (window.batchUploadQueue.length === 0) {
    if (typeof showToastAlert === 'function') showToastAlert("Please add at least one photo or video to analyze.", "warning");
    return;
  }
  const btnStart = document.getElementById('btnStartBatchAnalysis');
  if (btnStart) {
    btnStart.disabled = true;
    btnStart.innerText = "Analyzing files...";
  }
  window.recentUploadBatchDetections = [];
  const total = window.batchUploadQueue.length;
  for (let i = 0; i < total; i++) {
    const item = window.batchUploadQueue[i];
    item.status = 'processing';
    item.error = '';
    window.renderBatchQueueUI();
    showProgress(`Processing file ${i + 1} of ${total}: ${item.name}...`, Math.round(i / total * 100), `Batch: ${i + 1}/${total}`);
    try {
      const formData = new FormData();
      formData.append('file', item.file);
      formData.append('fps', window.selectedUploadFps !== undefined ? window.selectedUploadFps : 5);
      formData.append('save_annotated_video', document.getElementById('chkSaveAnnotatedVideo')?.checked === false ? 'false' : 'true');
      formData.append('location', item.locationName);
      if (item.cameraId) formData.append('registered_camera_id', item.cameraId);
      formData.append('gps_coords', item.lat && item.lng ? `${item.lat},${item.lng}` : '');
      formData.append('captured_at', item.capturedAt || '');
      const targetRadio = document.querySelector('input[name="investigationTarget"]:checked');
      const currentTarget = (window.currentInvestigationTarget || (targetRadio ? targetRadio.value : 'both')).toLowerCase();
      formData.append('target', currentTarget);
      const taskId = 'batch_' + Date.now() + '_' + Math.random().toString(36).substring(2, 7);
      formData.append('task_id', taskId);
      formData.append('background', 'true');
      let batchPollTimer = null;
      let isBatchItemDone = false;
      batchPollTimer = setInterval(async () => {
        if (isBatchItemDone) return;
        try {
          const pRes = await fetch('/api/unified/upload-progress?task_id=' + encodeURIComponent(taskId));
          if (pRes.ok) {
            const pData = await pRes.json();
            if (isBatchItemDone) return;
            if (pData && pData.status && pData.status !== 'waiting') {
              const currF = pData.current_frame || 0;
              const totalF = Math.max(pData.total_frames || 0, currF);
              const framesLabel = totalF > 0 ? ('Frames: ' + currF + ' / ' + totalF) : ('Frames: ' + currF);
              const pctOverall = Math.round((i / total) * 100 + (pData.pct || 0) / total);
              showProgress(item.name + ': ' + (pData.status_text || pData.message || 'Analyzing...'), pctOverall, framesLabel);
            }
          }
        } catch (_) {}
      }, 500);

      let res;
      try {
        res = await fetch('/api/unified/upload', {
          method: 'POST',
          body: formData
        });
        if (res.status === 202) {
          const accepted = await res.json();
          const deadline = Date.now() + 60 * 60 * 1000;
          let failures = 0;
          while (true) {
            if (Date.now() > deadline) throw new Error('Analysis timed out. Check server status before retrying.');
            await new Promise(resolve => setTimeout(resolve, 1000));
            let state;
            try {
              const poll = await fetch('/api/unified/upload-progress?task_id=' + encodeURIComponent(accepted.task_id));
              if (!poll.ok) throw new Error('Progress request failed');
              state = await poll.json();
              failures = 0;
            } catch (error) {
              if (++failures >= 10) throw new Error('Server connection lost. Reconnect and check analysis results before retrying.');
              continue;
            }
            if (state.status === 'error') throw new Error(state.status_text || 'Analysis failed');
            if (state.status === 'completed' && state.result) {
              res = {ok: true, json: async () => state.result};
              break;
            }
          }
        }
      } finally {
        isBatchItemDone = true;
        if (batchPollTimer) {
          clearInterval(batchPollTimer);
          batchPollTimer = null;
        }
      }
      if (res.ok) {
        const data = await res.json();
        if (data.success === false) throw new Error(data.error || data.detail || 'Analysis failed');
        item.status = 'completed';
        if (data.vehicles && data.vehicles.length > 0) {
          data.vehicles.forEach(v => {
            window.recentUploadBatchDetections.push({
              ...v,
              plate_number: v.plate_number || v.final_plate || 'UNREADABLE',
              final_plate: v.final_plate || v.plate_number || 'UNREADABLE',
              source_file: item.name,
              location: item.locationName || 'Panipat Checkpoint',
              gps_coords: item.lat && item.lng ? `${item.lat},${item.lng}` : '',
              captured_at: item.capturedAt || new Date().toISOString(),
              raw_scene_image: data.annotated_image_base64 ? `data:image/jpeg;base64,${data.annotated_image_base64}` : v.annotated_pic_path || ''
            });
          });
        }
        if (i === total - 1) {
          try {
            if (item.isVideo && typeof showAnprVideoInspection === 'function') {
              showAnprVideoInspection(data);
            } else if (!item.isVideo && typeof showAnprPhotoInspection === 'function') {
              showAnprPhotoInspection(data, item.name);
            }
          } catch (displayError) {
            console.error('Analysis completed; result preview failed:', displayError);
            if (typeof showToastAlert === 'function') showToastAlert('Analysis completed, but the preview could not be displayed. Results are available below.', 'warning');
          }
        }
      } else {
        item.status = 'error';
        let errText = `HTTP ${res.status}`;
        try {
          const errJson = await res.json();
          if (errJson && errJson.detail) {
            errText = typeof errJson.detail === 'string' ? errJson.detail : JSON.stringify(errJson.detail);
          }
        } catch (e) {
          try {
            const raw = await res.text();
            if (raw) errText = raw.substring(0, 150);
          } catch (e2) {}
        }
        console.error(`Batch item analysis error [${item.name}]:`, errText);
        item.error = errText;
        if (typeof showToastAlert === 'function') {
          showToastAlert(`Analysis failed for "${item.name}": ${errText}`, "error", "Media Processing Error");
        }
      }
    } catch (err) {
      console.error("Batch processing error on file:", item.name, err);
      item.status = 'error';
      item.error = err.message || String(err);
      if (typeof showToastAlert === 'function') {
        showToastAlert(`Analysis error on "${item.name}": ${err.message || err}`, "error");
      }
    }
    window.renderBatchQueueUI();
  }
  hideProgress();
  if (btnStart) {
    btnStart.disabled = false;
    btnStart.innerText = "Analyze files";
  }
  if (typeof fetchAndRenderCapturedDb === 'function') fetchAndRenderCapturedDb();
  if (typeof fetchAndRenderResults === 'function') fetchAndRenderResults();
  if (typeof fetchActiveAlerts === 'function') fetchActiveAlerts();
  const totalVehs = window.recentUploadBatchDetections.length;
  if (typeof showToastAlert === 'function') {
    null;
  }
  try {
    const batchFiles = window.batchUploadQueue || [];
    const batchSessTitle = `Batch Surveillance (${batchFiles.length} Checkpoints • ${totalVehs} Vehicles)`;
    fetch('/api/unified/sessions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        session_title: batchSessTitle,
        total_files: batchFiles.length,
        total_vehicles: totalVehs,
        files: batchFiles.map(f => ({
          name: f.name,
          location: f.locationName || 'Panipat Checkpoint',
          gps_coords: f.lat && f.lng ? `${f.lat},${f.lng}` : '',
          captured_at: f.capturedAt || new Date().toISOString(),
          status: f.status
        })),
        vehicles: window.recentUploadBatchDetections
      })
    }).then(res => res.json()).then(data => {
      if (typeof window.fetchAndRenderUploadSessionsFeed === 'function') {
        window.fetchAndRenderUploadSessionsFeed();
      }
    }).catch(err => console.warn("Failed to persist batch session:", err));
  } catch (sessErr) {
    console.warn("Session persist error:", sessErr);
  }
  window.renderRecentUploadResults();
  if (typeof window.fetchAndRenderUploadSessionsFeed === 'function') {
    window.fetchAndRenderUploadSessionsFeed();
  }
};
window.renderRecentUploadResults = function (filterQuery = '') {
  const sec = document.getElementById('recentUploadsSection');
  const grid = document.getElementById('recentUploadResultsGrid');
  const badge = document.getElementById('recentUploadStatsBadge');
  const pillsContainer = document.getElementById('recentUploadPlatePills');
  if (!sec || !grid) return;
  const allVehicles = (window.recentUploadBatchDetections || []).filter(window.isVisibleVehicleDetection);
  sec.style.display = 'block';
  const qClean = (filterQuery || '').trim().toUpperCase();
  const currentMode = window.currentBatchViewMode || 'all';
  const linkedPairsCount = allVehicles.filter(v => v.driver_name && v.driver_name.toUpperCase() !== 'UNKNOWN').length;
  const countAllEl = document.getElementById('batchCountAll');
  const countVehEl = document.getElementById('batchCountVehicles');
  const countPairsEl = document.getElementById('batchCountPairs');
  if (countAllEl) countAllEl.innerText = allVehicles.length;
  if (countVehEl) countVehEl.innerText = allVehicles.length;
  if (countPairsEl) countPairsEl.innerText = linkedPairsCount;
  const uniquePlates = [...new Set(allVehicles.map(v => v.plate_number || v.final_plate))].filter(p => p && p !== 'UNREADABLE');
  const unreadableVehicles = allVehicles.filter(v => (v.plate_number || v.final_plate) === 'UNREADABLE');
  const uniquePersons = [...new Set(null)].filter(n => n && n.toUpperCase() !== 'UNKNOWN');
  if (pillsContainer) {
    let pillsHtml = '';
    uniquePlates.forEach(p => {
      const count = allVehicles.filter(v => (v.plate_number || v.final_plate) === p).length;
      pillsHtml += `
                <button type="button" class="badge" onclick="document.getElementById('recentUploadSearchInput').value='${p}'; window.filterRecentUploadResults('${p}');" style="cursor:pointer; background:rgba(56, 189, 248, 0.15); color:#0369a1; border:1px solid rgba(56, 189, 248, 0.35); padding:4px 10px; border-radius:6px; font-weight:700;">
                    🚗 ${p} <span style="font-size:0.875rem; opacity:0.8;">(${count})</span>
                </button>
            `;
    });
    uniquePersons.forEach(name => {
      const isSuspect = null;
      const count = null;
      pillsHtml += `
                <button type="button" class="badge" onclick="document.getElementById('recentUploadSearchInput').value='${name}'; window.filterRecentUploadResults('${name}');" style="cursor:pointer; background:${isSuspect ? 'rgba(239, 68, 68, 0.2)' : 'rgba(16, 185, 129, 0.2)'}; color:${isSuspect ? '#b91c1c' : '#10b981'}; border:1px solid ${isSuspect ? 'rgba(239, 68, 68, 0.45)' : 'rgba(16, 185, 129, 0.45)'}; padding:4px 10px; border-radius:6px; font-weight:700;">
                    👤 ${name} ${isSuspect ? '⚠️' : ''} <span style="font-size:0.875rem; opacity:0.8;">(${count})</span>
                </button>
            `;
    });
    if (unreadableVehicles.length > 0) {
      pillsHtml += `
                <button type="button" class="badge" onclick="document.getElementById('recentUploadSearchInput').value='UNREADABLE'; window.filterRecentUploadResults('UNREADABLE');" style="cursor:pointer; background:rgba(239, 68, 68, 0.2); color:#b91c1c; border:1px solid rgba(239, 68, 68, 0.45); padding:4px 10px; border-radius:6px; font-weight:700;">
                    ⚠️ Needs Review (${unreadableVehicles.length} Unreadable)
                </button>
            `;
    }
    pillsContainer.innerHTML = pillsHtml;
  }
  const filteredVehicles = allVehicles.filter(v => {
    if (!qClean) return true;
    const pNum = (v.plate_number || v.final_plate || '').toUpperCase();
    const loc = (v.location || '').toUpperCase();
    const fn = (v.source_file || '').toUpperCase();
    const dName = (v.driver_name || '').toUpperCase();
    return pNum.includes(qClean) || loc.includes(qClean) || fn.includes(qClean) || dName.includes(qClean);
  });
  if (badge) {
    badge.textContent = `${allVehicles.length} Sightings`;
  }
  let cardsHtml = '';
  if (currentMode === 'all' || currentMode === 'vehicles') {
    filteredVehicles.forEach((v, idx) => {
      const plate = v.display_plate || v.plate_number || v.final_plate || 'UNKNOWN';
      const cleanPlate = v.plate_number || v.final_plate || plate;
      const conf = Math.round(v.confidence || v.ocr_confidence || 95.0);
      const isUnreadable = cleanPlate === 'UNREADABLE';
      const cropImg = v.plate_crop_base64 ? `data:image/jpeg;base64,${v.plate_crop_base64}` : v.vehicle_crop_base64 ? `data:image/jpeg;base64,${v.vehicle_crop_base64}` : v.crop_base64 ? `data:image/jpeg;base64,${v.crop_base64}` : v.plate_crop_url || v.plate_pic_path || v.vehicle_pic_path || '/static/benchmark_sample.jpg';
      let driverStripHtml = '';
      const hasDriver = Boolean(v.driver_name && v.driver_name.toUpperCase() !== 'UNKNOWN' || null || null || v.driver_captured_id || 0);
      if (hasDriver) {
        const dName = v.driver_name && v.driver_name.toUpperCase() !== 'UNKNOWN' ? v.driver_name : 'Occupant Sighted';
        const dCat = v.driver_category || 'OCCUPANT';
        const isSuspect = ['SUSPECT', 'WANTED', 'CRIMINAL'].includes(dCat.toUpperCase());
        const rawDCrop = null || null;
        const dCrop = window.formatEvidenceImageSrc(rawDCrop);
        const dSim = v.driver_similarity ? Math.round(v.driver_similarity) : null;
        driverStripHtml = `
                    <div style="background:rgba(241,245,249,0.7); border:1px solid ${isSuspect ? 'rgba(239, 68, 68, 0.4)' : 'rgba(16, 185, 129, 0.35)'}; border-radius:6px; padding:6px 10px; margin:8px 0; display:flex; align-items:center; justify-content:space-between; gap:8px;">
                        <div style="display:flex; align-items:center; gap:8px;">
                            <img src="${dCrop}" alt="Occupant" style="width:32px; height:32px; border-radius:50%; object-fit:cover; border:1.5px solid ${isSuspect ? '#ef4444' : '#10b981'}; background:#000;">
                            <div>
                                <div style="font-size:0.875rem; font-weight:700; color:${isSuspect ? '#b91c1c' : '#172033'};">
                                    👤 ${escapeHtml(dName)} ${isSuspect ? '<span style="color:#ef4444; font-size:0.875rem;">[SUSPECT]</span>' : ''}
                                </div>
                                <div style="font-size:0.875rem; color:#52647c;">
                                    ${escapeHtml(dCat)} ${dSim ? `• ${dSim}% Match` : ''}
                                </div>
                            </div>
                        </div>

                    </div>
                `;
      }
      cardsHtml += `
                <div class="vehicle-card interactive-upload-card" onclick="window.openUploadVehicleDetailModal(${idx})" title="Click to inspect complete vehicle forensics & raw scene photo" style="cursor:pointer; background:#ffffff; border:1px solid ${isUnreadable ? 'rgba(239, 68, 68, 0.35)' : 'rgba(56, 189, 248, 0.28)'}; border-radius:8px; padding:12px; display:flex; flex-direction:column; justify-content:space-between; transition:transform 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease;">
                    <div>
                        <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:10px;">
                            <div class="hsrp-plate">
                                <div class="hsrp-ind-strip"><span>IND</span></div>
                                <div class="hsrp-plate-text" style="${isUnreadable ? 'color:#b91c1c;' : ''}">${isUnreadable ? '⚠️ UNREADABLE' : escapeHtml(plate)}</div>
                            </div>
                            <span class="conf-pill" style="background:${isUnreadable ? 'rgba(239, 68, 68, 0.18)' : 'rgba(56, 189, 248, 0.2)'}; color:${isUnreadable ? '#b91c1c' : '#0369a1'}; border-color:${isUnreadable ? 'rgba(239, 68, 68, 0.4)' : 'rgba(56, 189, 248, 0.4)'}; font-size:0.875rem; font-weight:700;">
                                ${isUnreadable ? 'Review' : `${conf}% OCR`}
                            </span>
                        </div>

                        <div style="display:flex; gap:10px; margin-bottom:8px;">
                            <img src="${cropImg}" alt="Crop" style="width:110px; height:52px; object-fit:contain; background:#000; border-radius:4px; border:1px solid rgba(255,255,255,0.12);">
                            <div style="font-size:0.875rem; color:#52647c; display:flex; flex-direction:column; justify-content:center; gap:3px;">
                                <div>📹 <strong style="color:#172033;">${escapeHtml(v.source_file || 'Media')}</strong></div>
                                <div>📍 ${escapeHtml(v.location || 'Panipat')}</div>
                                <div>🕒 ${v.captured_at ? v.captured_at.replace('T', ' ') : 'Just Now'}</div>
                            </div>
                        </div>

                        ${driverStripHtml}
                    </div>

                    <div style="margin-top:8px; padding-top:8px; border-top:1px solid rgba(255,255,255,0.06); display:flex; justify-content:space-between; align-items:center;">
                        <span style="font-size:0.875rem; color:#64748b;">GPS: ${v.gps_coords || 'N/A'}</span>
                        <div style="display:flex; gap:6px;">
                            <button type="button" class="btn btn-secondary" onclick="event.stopPropagation(); window.openUploadVehicleDetailModal(${idx})" style="padding:4px 8px; font-size:0.875rem; background:rgba(56, 189, 248, 0.15); color:#0369a1; border:1px solid rgba(56, 189, 248, 0.35); cursor:pointer; border-radius:4px;">
                                🔍 Inspect
                            </button>
                            <button type="button" class="btn btn-secondary" onclick="event.stopPropagation(); window.renderTacticalRouteMap('${escapeHtml(cleanPlate)}')" style="padding:4px 8px; font-size:0.875rem; background:rgba(99, 102, 241, 0.2); color:#4338ca; border:1px solid rgba(99, 102, 241, 0.4); cursor:pointer; border-radius:4px;">
                                🗺️ Route
                            </button>
                        </div>
                    </div>
                </div>
            `;
    });
  }
  grid.innerHTML = cardsHtml || '<p style="padding:16px;color:#52647c;">' + (allVehicles.length ? 'No detections match this search.' : 'Analysis completed. No vehicles were detected in these files. Try a clearer video or a higher processing FPS.') + '</p>';
  if (qClean && uniquePlates.includes(qClean)) {
    window.renderTacticalRouteMap(qClean);
  }
};
window.switchBatchViewMode = function (mode) {
  window.currentBatchViewMode = mode;
  const tabAll = document.getElementById('btnBatchTabAll');
  const tabVeh = document.getElementById('btnBatchTabVehicles');
  const tabPairs = document.getElementById('btnBatchTabPairs');
  const resetTab = el => {
    if (!el) return;
    el.className = 'btn btn-sm btn-secondary';
    el.style.background = 'rgba(255, 255, 255, 0.05)';
    el.style.color = '#52647c';
    el.style.borderColor = 'rgba(255, 255, 255, 0.15)';
  };
  const activeTab = (el, bg, col, border) => {
    if (!el) return;
    el.className = 'btn btn-sm btn-primary';
    el.style.background = bg;
    el.style.color = col;
    el.style.borderColor = border;
  };
  resetTab(tabAll);
  resetTab(tabVeh);
  null;
  resetTab(tabPairs);
  if (mode === 'vehicles') activeTab(tabVeh, 'rgba(56, 189, 248, 0.25)', '#0369a1', 'rgba(56, 189, 248, 0.5)'); else activeTab(tabAll, 'rgba(56, 189, 248, 0.25)', '#0369a1', 'rgba(56, 189, 248, 0.5)');
  const searchInput = document.getElementById('recentUploadSearchInput');
  window.renderRecentUploadResults(searchInput ? searchInput.value : '');
};
window.openUploadVehicleDetailModalById = function (vehId) {
  if (typeof window.openCaptureDetailModal === 'function') {
    window.openCaptureDetailModal(vehId);
    return;
  }
  if (window.recentUploadBatchDetections) {
    const idx = window.recentUploadBatchDetections.findIndex(v => v.captured_id == vehId || v.id == vehId);
    if (idx !== -1) {
      window.openUploadVehicleDetailModal(idx);
    }
  }
};
window.filterRecentUploadResults = function (query) {
  window.renderRecentUploadResults(query);
};
window.renderTacticalRouteMap = async function (plateNumber, userIncludeUnreadables = false) {
  const sec = document.getElementById('uploadRouteMapSection');
  const mapCanvas = document.getElementById('uploadRouteMap');
  const badge = document.getElementById('routeMapPlateBadge');
  const metrics = document.getElementById('routeMapMetrics');
  const timeline = document.getElementById('routeTimelineBar');
  if (!sec || !mapCanvas) return;
  sec.style.display = 'block';
  const isUnreadableTarget = (plateNumber || '').toUpperCase() === 'UNREADABLE';
  if (badge) {
    badge.innerHTML = `
            <span>${escapeHtml(plateNumber || 'SUSPECT VEHICLE')}</span>
            ${!isUnreadableTarget ? `
                <label style="cursor:pointer; display:inline-flex; align-items:center; gap:5px; font-size:0.875rem; color:#92400e; background:rgba(245, 158, 11, 0.12); border:1px solid rgba(245, 158, 11, 0.3); padding:2px 8px; border-radius:4px; margin-left:8px; font-weight:500;" title="Manish's Rule: Do NOT auto-connect unreadables, let user decide">
                    <input type="checkbox" id="chkIncludeUnreadableInRoute" onchange="window.renderTacticalRouteMap('${escapeHtml(plateNumber)}', this.checked)" ${userIncludeUnreadables ? 'checked' : ''} style="cursor:pointer;">
                    <span>Include Unreadables</span>
                </label>
            ` : ''}
        `;
  }
  let sightings = window.recentUploadBatchDetections.filter(v => {
    const p = (v.plate_number || v.final_plate || '').toUpperCase();
    return p === (plateNumber || '').toUpperCase();
  });
  const unreadableSuspects = userIncludeUnreadables && plateNumber && !isUnreadableTarget ? window.recentUploadBatchDetections.filter(v => {
    const p = (v.plate_number || v.final_plate || '').toUpperCase();
    return (p === 'UNREADABLE' || !p) && v.gps_coords && v.gps_coords.includes(',');
  }) : [];
  if (sightings.length === 0) {
    sightings = window.recentUploadBatchDetections;
  }
  const pts = [];
  sightings.forEach(s => {
    if (s.gps_coords && s.gps_coords.includes(',')) {
      const parts = s.gps_coords.split(',').map(n => Number(n.trim()));
      if (!isNaN(parts[0]) && !isNaN(parts[1])) {
        pts.push({
          lat: parts[0],
          lng: parts[1],
          location: s.location || 'Checkpoint',
          time: s.captured_at || new Date().toISOString(),
          crop: s.plate_crop_base64 ? `data:image/jpeg;base64,${s.plate_crop_base64}` : s.vehicle_crop_base64 ? `data:image/jpeg;base64,${s.vehicle_crop_base64}` : s.crop_base64 ? `data:image/jpeg;base64,${s.crop_base64}` : s.plate_pic_path || s.vehicle_pic_path || '',
          conf: Math.round(s.confidence || 95),
          isProvisional: false
        });
      }
    }
  });
  if (unreadableSuspects && unreadableSuspects.length > 0) {
    unreadableSuspects.forEach(u => {
      const parts = u.gps_coords.split(',').map(n => Number(n.trim()));
      if (!isNaN(parts[0]) && !isNaN(parts[1])) {
        if (!pts.some(p => Math.abs(p.lat - parts[0]) < 0.0001 && Math.abs(p.lng - parts[1]) < 0.0001)) {
          pts.push({
            lat: parts[0],
            lng: parts[1],
            location: u.location || 'Panipat Naka Checkpoint',
            time: u.captured_at || new Date().toISOString(),
            crop: u.vehicle_crop_base64 ? `data:image/jpeg;base64,${u.vehicle_crop_base64}` : u.vehicle_pic_path || '',
            conf: 0,
            isProvisional: true
          });
        }
      }
    });
  }
  pts.sort((a, b) => new Date(a.time) - new Date(b.time));
  if (timeline) {
    timeline.innerHTML = pts.map((p, idx) => {
      const isFirst = idx === 0;
      const isLast = idx === pts.length - 1 && pts.length > 1;
      const bg = isFirst ? 'rgba(16, 185, 129, 0.15)' : isLast ? 'rgba(239, 68, 68, 0.15)' : 'rgba(245, 158, 11, 0.15)';
      const col = isFirst ? '#10b981' : isLast ? '#ef4444' : '#f59e0b';
      const label = isFirst ? 'Pin ① First Seen' : isLast ? `Pin 🏁 Last Seen` : `Pin #${idx + 1} In Transit`;
      return `
                <div style="background:${bg}; border:1px solid ${col}; border-radius:6px; padding:6px 12px; min-width:160px; font-size:0.875rem; flex-shrink:0;">
                    <div style="font-weight:700; color:${col}; margin-bottom:2px;">${label}</div>
                    <div style="font-weight:600; color:#172033; font-size:0.875rem;">${escapeHtml(p.location)}</div>
                    <div style="color:#52647c; font-size:0.875rem;">🕒 ${p.time.replace('T', ' ')}</div>
                </div>
            `;
    }).join('');
  }
  sec.scrollIntoView({
    behavior: 'smooth',
    block: 'nearest'
  });
  setTimeout(async () => {
    if (!routeLeafletMap) {
      routeLeafletMap = L.map('uploadRouteMap').setView([29.69, 76.99], 13);
      L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors | Haryana Police GIS'
      }).addTo(routeLeafletMap);
    } else {
      routeLeafletMap.invalidateSize();
    }
    routeMapLayers.forEach(l => routeLeafletMap.removeLayer(l));
    routeMapLayers = [];
    if (pts.length === 0) {
      if (metrics) metrics.innerHTML = '<span>No GPS coordinates associated with this vehicle.</span>';
      return;
    }
    const latLngBounds = [];
    pts.forEach((p, idx) => {
      latLngBounds.push([p.lat, p.lng]);
      const isFirst = idx === 0;
      const isLast = idx === pts.length - 1 && pts.length > 1;
      const isProvisional = p.isProvisional;
      const pinClass = isProvisional ? 'police-pin-provisional' : isFirst ? 'police-pin-start' : isLast ? 'police-pin-end' : 'police-pin-mid';
      const pinNum = isProvisional ? '❓' : isLast ? '🏁' : idx + 1;
      const borderStyle = isProvisional ? 'border: 2px dashed #f59e0b; background: rgba(245, 158, 11, 0.85);' : '';
      const iconHtml = `<div class="police-map-pin ${pinClass}" style="width:28px; height:28px; font-size:0.875rem; ${borderStyle}">${pinNum}</div>`;
      const customIcon = L.divIcon({
        html: iconHtml,
        className: '',
        iconSize: [28, 28],
        iconAnchor: [14, 14]
      });
      const marker = L.marker([p.lat, p.lng], {
        icon: customIcon
      }).addTo(routeLeafletMap);
      const popupHtml = `
                <div style="font-family:sans-serif; min-width:160px; font-size:0.875rem;">
                    <div style="font-weight:800; color:#ffffff; margin-bottom:4px;">Checkpoint #${idx + 1}: ${escapeHtml(p.location)}</div>
                    <div style="color:#64748b; font-size:0.875rem;">🕒 ${p.time.replace('T', ' ')}</div>
                    <div style="color:#0284c7; font-weight:700; margin-top:2px;">Confidence: ${p.conf}% OCR</div>
                    ${p.crop ? `<img src="${p.crop}" style="width:100%; height:45px; object-fit:contain; background:#000; border-radius:4px; margin-top:6px;">` : ''}
                </div>
            `;
      marker.bindPopup(popupHtml);
      routeMapLayers.push(marker);
    });
    if (pts.length >= 2) {
      try {
        const osrmCoords = pts.map(p => `${p.lng},${p.lat}`).join(';');
        const osrmUrl = `https://router.project-osrm.org/route/v1/driving/${osrmCoords}?overview=full&geometries=geojson`;
        const rRes = await fetch(osrmUrl);
        if (rRes.ok) {
          const rData = await rRes.json();
          if (rData.routes && rData.routes.length > 0) {
            const routeGeoJson = rData.routes[0].geometry;
            const distKm = (rData.routes[0].distance / 1000).toFixed(1);
            const durMin = Math.round(rData.routes[0].duration / 60);
            const routeLine = L.geoJSON(routeGeoJson, {
              style: {
                color: '#0369a1',
                weight: 5,
                opacity: 0.85
              }
            }).addTo(routeLeafletMap);
            routeMapLayers.push(routeLine);
            if (metrics) {
              metrics.innerHTML = `
                                <span>🛣️ Road Distance: <strong>${distKm} km</strong></span>
                                <span>⏱️ Est. Driving Time: <strong>${durMin} mins</strong></span>
                                <span>📍 Sightings: <strong>${pts.length} Checkpoints</strong></span>
                            `;
            }
          } else {
            throw new Error("No OSRM route geometry");
          }
        } else {
          throw new Error("OSRM service status not OK");
        }
      } catch (routeErr) {
        console.warn("OSRM routing unavailable, using direct trajectory polyline:", routeErr);
        const directLine = L.polyline(latLngBounds, {
          color: '#0369a1',
          weight: 4,
          dashArray: '6, 8',
          opacity: 0.85
        }).addTo(routeLeafletMap);
        routeMapLayers.push(directLine);
        if (metrics) {
          metrics.innerHTML = `<span>📍 Sightings: <strong>${pts.length} Checkpoints</strong> (Corridor Plotted)</span>`;
        }
      }
    } else {
      if (metrics) metrics.innerHTML = `<span>📍 Single Checkpoint Spotting (First Sighting)</span>`;
    }
    if (latLngBounds.length > 0) {
      routeLeafletMap.fitBounds(latLngBounds, {
        padding: [50, 50]
      });
    }
  }, 200);
};
window.toggleRouteMapVisibility = function () {
  const sec = document.getElementById('uploadRouteMapSection');
  if (!sec) return;
  if (sec.style.display === 'none' || sec.style.display === '') {
    const uniquePlates = [...new Set(window.recentUploadBatchDetections.map(v => v.plate_number || v.final_plate))].filter(p => p && p !== 'UNREADABLE');
    window.renderTacticalRouteMap(uniquePlates[0] || '');
  } else {
    sec.style.display = 'none';
  }
};
window.renderSearchActiveRecord = function () {
  const activeResults = document.getElementById('vehicleSearchActiveResults');
  if (!activeResults || currentSearchForensicResults.length === 0) return;
  const record = currentSearchForensicResults[currentSearchActiveIndex];
  if (!record) return;
  const queryPlate = record.plate_number || record.display_plate || 'VEHICLE';
  let html = `
        <div style="background:linear-gradient(135deg, rgba(241,245,249,0.8) 0%, rgba(241,245,249,0.9) 100%); border:1px solid rgba(56, 189, 248, 0.4); border-radius:12px; padding:18px; margin-bottom:20px; box-shadow:0 8px 24px rgba(0,0,0,0.4);">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px; border-bottom:1px solid rgba(255,255,255,0.08); padding-bottom:14px; margin-bottom:16px;">
                <div style="display:flex; align-items:center; gap:12px;">
                    <div class="hsrp-plate" style="transform:scale(1.05);">
                        <div class="hsrp-ind-strip"><span>IND</span></div>
                        <div class="hsrp-plate-text">${escapeHtml(record.display_plate || record.plate_number)}</div>
                    </div>
                    <span class="conf-pill" style="background:rgba(16, 185, 129, 0.2); color:#10b981; border:1px solid rgba(16, 185, 129, 0.4); font-size:0.875rem; font-weight:700;">
                        ${Math.round(record.confidence || 95)}% OCR Consensus
                    </span>
                    ${record.hotlist_match ? `<span style="background:rgba(239, 68, 68, 0.2); color:#ef4444; border:1px solid #ef4444; padding:3px 8px; border-radius:4px; font-weight:800; font-size:0.875rem;">🚨 WATCHLIST ALERT</span>` : ''}
                </div>

                <div style="display:flex; gap:10px;">
                    <button type="button" class="btn btn-primary" onclick="window.launchSidebarRouteMapModal('${escapeHtml(queryPlate)}')" style="padding:8px 16px; font-size:0.8825rem; font-weight:700; background:#4f46e5; display:flex; align-items:center; gap:6px;">
                        <span>🗺️</span> <span>View map</span>
                    </button>
                </div>
            </div>

            <div style="font-size:0.9225rem; color:#475569; font-weight:700; margin-bottom:12px; display:flex; align-items:center; gap:6px;">
                <span>📑</span> <span>Multi-Clip Forensic Sightings Timeline (${currentSearchForensicResults.length} Matched Sessions):</span>
            </div>

            <!-- Vertical Multi-Clip Breakdown List -->
            <div style="display:flex; flex-direction:column; gap:14px;">
    `;
  currentSearchForensicResults.forEach((cap, cIdx) => {
    const evFrames = cap.evidence_frames || [];
    const topFrame = evFrames[0] || ({});
    const frameIdx = topFrame.frame_idx || 1;
    const videoTime = topFrame.video_time_str || topFrame.time_str || (cap.captured_at ? cap.captured_at.split(' ')[1] : '00:00.0s');
    const clipTitle = cap.clip_name || cap.source_file || `CCTV Video Clip #${cIdx + 1}`;
    const loc = cap.location || 'Surveillance Post';
    const plateImg = cap.plate_pic_path || (topFrame.crop_base64 ? `data:image/jpeg;base64,${topFrame.crop_base64}` : '/static/benchmark_sample.jpg');
    const vehImg = cap.vehicle_pic_path || (topFrame.vehicle_crop_base64 ? `data:image/jpeg;base64,${topFrame.vehicle_crop_base64}` : cap.annotated_pic_path);
    html += `
            <div style="background:rgba(241,245,249,0.85); border:1px solid rgba(99, 102, 241, 0.3); border-radius:10px; padding:16px;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; border-bottom:1px solid rgba(255,255,255,0.06); padding-bottom:10px; flex-wrap:wrap; gap:8px;">
                    <div style="display:flex; align-items:center; gap:8px;">
                        <span style="font-size:1.1rem;">📹</span>
                        <strong style="color:#172033; font-size:0.9625rem;">Clip #${cIdx + 1}: ${escapeHtml(clipTitle)}</strong>
                        <span style="font-size:0.875rem; color:#818cf8; background:rgba(99, 102, 241, 0.15); border:1px solid rgba(99, 102, 241, 0.3); padding:2px 6px; border-radius:4px;">📍 ${escapeHtml(loc)}</span>
                    </div>
                    <div style="font-size:0.875rem; color:#52647c; font-family:var(--font-mono);">
                        🕒 Captured: <strong style="color:#475569;">${escapeHtml(cap.captured_at || 'Recorded Sighting')}</strong>
                    </div>
                </div>

                <!-- Frame & Sighting Telemetry Details -->
                <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(200px, 1fr)); gap:12px; margin-bottom:14px; background:rgba(241,245,249,0.4); padding:10px 14px; border-radius:6px;">
                    <div>
                        <span style="font-size:0.875rem; color:#64748b; text-transform:uppercase; display:block; font-weight:700;">Video Detection Frame</span>
                        <span style="font-size:0.9125rem; font-weight:700; color:#0369a1; font-family:var(--font-mono);">🎯 Frame #${frameIdx}</span>
                    </div>
                    <div>
                        <span style="font-size:0.875rem; color:#64748b; text-transform:uppercase; display:block; font-weight:700;">Playback Timestamp</span>
                        <span style="font-size:0.9125rem; font-weight:700; color:#4338ca; font-family:var(--font-mono);">⏱️ ${videoTime}</span>
                    </div>
                    <div>
                        <span style="font-size:0.875rem; color:#64748b; text-transform:uppercase; display:block; font-weight:700;">Camera Geolocation</span>
                        <span style="font-size:0.9125rem; font-weight:700; color:#475569; font-family:var(--font-mono);">🌐 ${cap.gps_coords || '29.3909, 76.9635'}</span>
                    </div>
                    <div>
                        <span style="font-size:0.875rem; color:#64748b; text-transform:uppercase; display:block; font-weight:700;">Track ID</span>
                        <span style="font-size:0.9125rem; font-weight:700; color:#0369a1; font-family:var(--font-mono);">#${cap.track_id !== null && cap.track_id !== undefined ? cap.track_id : cIdx + 1}</span>
                    </div>
                </div>

                <!-- Visual Evidence Crops Row -->
                <div style="display:flex; gap:14px; flex-wrap:wrap; align-items:center;">
                    <div>
                        <span style="font-size:0.875rem; color:#52647c; display:block; margin-bottom:4px; font-weight:600;">Number Plate Snapshot:</span>
                        <img src="${plateImg}" alt="Plate Crop" style="width:140px; height:50px; object-fit:contain; background:#000; border-radius:6px; border:1px solid rgba(255,255,255,0.15);">
                    </div>
                    ${vehImg ? `
                        <div>
                            <span style="font-size:0.875rem; color:#52647c; display:block; margin-bottom:4px; font-weight:600;">Vehicle Context Snapshot:</span>
                            <img src="${vehImg}" alt="Vehicle Crop" style="width:140px; height:70px; object-fit:cover; background:#000; border-radius:6px; border:1px solid rgba(255,255,255,0.15);">
                        </div>
                    ` : ''}
                </div>
            </div>
        `;
  });
  html += `
            </div>
        </div>
    `;
  activeResults.innerHTML = html;
  activeResults.style.display = 'block';
};
window.launchSidebarRouteMapModal = function (plate) {
  window.switchTab('upload');
  const uPanel = document.getElementById('uploadHubPanel');
  if (uPanel) uPanel.style.display = 'block';
  const lPanel = document.getElementById('liveFeedPanel');
  if (lPanel) lPanel.style.display = 'none';
  setTimeout(() => {
    window.renderTacticalRouteMap(plate);
  }, 250);
};
console.log("[Forensics] Multi-Upload, Tactical Route Map & Multi-Clip Search Module loaded successfully.");
window.fetchAndRenderUploadSessionsFeed = async function () {
  const sec = document.getElementById('uploadActivitySection');
  const cont = document.getElementById('uploadSessionsFeedContainer');
  const badge = document.getElementById('uploadSessionsCountBadge');
  if (!cont) return;
  if (sec) sec.style.display = 'block';
  try {
    const res = await fetch('/api/unified/sessions?limit=25');
    if (!res.ok) return;
    const data = await res.json();
    const sessions = data.sessions || [];
    const role = (data.user_role || 'STATE_ADMIN').toUpperCase();
    let scopeBadgeText = '';
    if (role === 'STATE_ADMIN' || role === 'DEVELOPER_ADMIN') {
      scopeBadgeText = `<span style="font-size:0.875rem; color:#4338ca; background:rgba(99, 102, 241, 0.2); padding:2px 8px; border-radius:10px; border:1px solid rgba(99,102,241,0.4);">🌐 State HQ: All 22 Districts & All Operators</span>`;
    } else if (role === 'DISTRICT_ADMIN') {
      scopeBadgeText = `<span style="font-size:0.875rem; color:#0369a1; background:rgba(56, 189, 248, 0.2); padding:2px 8px; border-radius:10px; border:1px solid rgba(56,189,248,0.4);">🏢 District Scope: ${escapeHtml(data.scoped_district || 'Panipat')} (All Operators)</span>`;
    } else {
      scopeBadgeText = `<span style="font-size:0.875rem; color:#10b981; background:rgba(16, 185, 129, 0.2); padding:2px 8px; border-radius:10px; border:1px solid rgba(16,185,129,0.4);">👮 Operator Scope: ${escapeHtml(data.scoped_operator || 'My Uploads')}</span>`;
    }
    if (badge) badge.innerHTML = `${sessions.length} Session${sessions.length !== 1 ? 's' : ''} &nbsp; ${scopeBadgeText}`;
    if (sessions.length === 0) {
      cont.innerHTML = `
                <div class="empty-state" style="padding: 24px 12px; text-align: center; color: #52647c; background: rgba(241,245,249,0.5); border-radius: 8px;">
                    <p>No upload sessions found for the current RBAC scope (${role}: ${escapeHtml(data.scoped_district || 'Panipat')}).</p>
                </div>
            `;
      return;
    }
    cont.innerHTML = sessions.map((s, sIdx) => {
      const isFirst = sIdx === 0;
      const vehList = (s.vehicles || []).filter(window.isVisibleVehicleDetection);
      const fileList = s.files || [];
      return `
                <div class="upload-session-card ${isFirst ? 'expanded' : ''}" id="session_card_${s.session_id}">
                    <div class="session-card-header" onclick="window.toggleSessionExpand('${s.session_id}')">
                        <div class="session-title-block">
                            <div class="session-badge-strip">
                                <span class="session-id-pill">SESSION #${s.id}</span>
                                <span style="font-size:0.875rem; color:#64748b;">${escapeHtml(s.session_id)}</span>
                            </div>
                            <h3 class="session-title-text">${escapeHtml(s.session_title)}</h3>
                            <div class="session-meta-row">
                                <span class="session-meta-item">🕒 ${escapeHtml(s.time_display || s.timestamp)}</span>
                                <span class="session-meta-item">📍 ${escapeHtml(s.district || 'Panipat')} (${escapeHtml(s.station || 'PHQ')})</span>
                                <span class="session-meta-item">👮 ${escapeHtml(s.officer_name || 'Duty Officer')} <strong style="color:#64748b; font-weight:500;">(${escapeHtml(s.username || 'op')})</strong></span>
                                <span class="badge" style="font-size:0.875rem; background:rgba(99,102,241,0.2); color:#4338ca; border:1px solid rgba(99,102,241,0.35); padding:1px 6px;">${escapeHtml(s.role || 'OPERATOR')}</span>
                            </div>
                        </div>
                        <div class="session-kpi-controls">
                            <span class="kpi-stat-badge files">📁 ${s.total_files || fileList.length} Files</span>
                            <span class="kpi-stat-badge vehicles">🚗 ${s.total_vehicles || vehList.length} Vehicles</span>

                            <button type="button" class="btn btn-primary" onclick="event.stopPropagation(); window.loadSessionToMap('${s.session_id}')" style="padding:5px 12px; font-size:0.875rem; background:rgba(99, 102, 241, 0.25); color:#4338ca; border:1px solid rgba(99, 102, 241, 0.5); cursor:pointer; border-radius:6px;">
                                🗺️ View Route
                            </button>
                            <button type="button" class="btn btn-secondary" onclick="event.stopPropagation(); window.deleteUploadSession('${s.session_id}')" style="padding:5px 8px; font-size:0.875rem; background:rgba(239, 68, 68, 0.15); color:#b91c1c; border:1px solid rgba(239, 68, 68, 0.35); cursor:pointer; border-radius:6px;" title="Delete this session record">
                                🗑️
                            </button>
                            <span class="session-expand-chevron">▼</span>
                        </div>
                    </div>

                    <div class="session-card-body" id="session_body_${s.session_id}" style="display: ${isFirst ? 'block' : 'none'};">
                        <!-- Files Strip -->
                        <div class="session-files-bar">
                            <div class="session-files-bar-title">Uploaded Media Files in this Session:</div>
                            <div class="session-files-chips-row">
                                ${fileList.map(f => `
                                    <div class="session-file-chip-item">
                                        <span>📹 <strong>${escapeHtml(f.name)}</strong></span>
                                        <span class="session-file-chip-loc">📍 ${escapeHtml(f.location || 'Checkpoint')}</span>
                                        <span style="color:#64748b; font-size:0.875rem;">🕒 ${(f.captured_at || '').replace('T', ' ')}</span>
                                    </div>
                                `).join('')}
                            </div>
                        </div>


                        <div class="session-inner-columns">
                            <!-- Vehicles Column -->
                            <div class="session-inner-col">
                                <div class="session-col-title">
                                    <span>🚗 Detected Vehicles (${vehList.length})</span>
                                    <span style="font-size:0.875rem; color:#52647c;">${vehList.filter(v => v.plate_number !== 'UNREADABLE').length} Verified</span>
                                </div>
                                <div class="session-items-scroll">
                                    ${vehList.length === 0 ? '<div style="color:#64748b; font-size:0.875rem; text-align:center; padding:15px;">No vehicles detected in this session.</div>' : vehList.map(v => {
        const plate = v.display_plate || v.plate_number || v.final_plate || 'UNREADABLE';
        const cleanPlate = v.plate_number || v.final_plate || plate;
        const isUnreadable = cleanPlate === 'UNREADABLE';
        const conf = Math.round(v.confidence || 90);
        const plateCrop = v.plate_crop_base64 ? `data:image/jpeg;base64,${v.plate_crop_base64}` : v.plate_pic_path || '';
        const vehCrop = v.vehicle_crop_base64 ? `data:image/jpeg;base64,${v.vehicle_crop_base64}` : v.crop_base64 ? `data:image/jpeg;base64,${v.crop_base64}` : v.vehicle_pic_path || '';
        const cropImg = plateCrop || vehCrop || '/static/benchmark_sample.jpg';
        const fallbackCrop = plateCrop && vehCrop && plateCrop !== vehCrop ? vehCrop : '/static/benchmark_sample.jpg';
        return `
                                            <div style="background:#ffffff; border:1px solid ${isUnreadable ? 'rgba(239, 68, 68, 0.3)' : 'rgba(56, 189, 248, 0.25)'}; border-radius:6px; padding:10px; display:flex; justify-content:space-between; align-items:center; gap:10px;">
                                                <div style="display:flex; align-items:center; gap:10px;">
                                                    <img src="${cropImg}" alt="Crop" onerror="this.onerror=null; if ('${fallbackCrop}' && this.src !== '${fallbackCrop}') { this.src='${fallbackCrop}'; } else { this.parentElement.innerHTML='<span style=\'display:flex;align-items:center;justify-content:center;width:75px;height:40px;background:#e2e8f0;border-radius:4px;color:#52647c;font-size:0.875rem;font-weight:600;\'>No Crop</span>'; }" style="width:75px; height:40px; object-fit:contain; background:#e2e8f0; border-radius:4px; border:1px solid rgba(255,255,255,0.1);">
                                                    <div>
                                                        <div style="font-weight:700; color:${isUnreadable ? '#b91c1c' : '#0369a1'}; font-size:0.9125rem;">
                                                            ${isUnreadable ? '⚠️ UNREADABLE' : escapeHtml(plate)}
                                                        </div>
                                                        <div style="font-size:0.875rem; color:#52647c;">
                                                            📍 ${escapeHtml(v.location || 'Panipat')} • 🕒 ${(v.captured_at || '').replace('T', ' ')}
                                                        </div>
                                                    </div>
                                                </div>
                                                <div style="text-align:right;">
                                                    <span class="badge" style="font-size:0.875rem; background:${isUnreadable ? 'rgba(239, 68, 68, 0.15)' : 'rgba(16, 185, 129, 0.15)'}; color:${isUnreadable ? '#b91c1c' : '#10b981'};">
                                                        ${isUnreadable ? 'Review' : `${conf}% Conf`}
                                                    </span>
                                                    ${!isUnreadable ? `
                                                        <div style="margin-top:4px;">
                                                            <button type="button" class="btn btn-sm btn-secondary" onclick="window.renderTacticalRouteMap('${escapeHtml(cleanPlate)}')" style="padding:2px 8px; font-size:0.875rem; cursor:pointer;">
                                                                Map
                                                            </button>
                                                        </div>
                                                    ` : ''}
                                                </div>
                                            </div>
                                        `;
      }).join('')}
                                </div>
                            </div>



                        </div>
                    </div>
                </div>
            `;
    }).join('');
  } catch (e) {
    console.warn("Failed to load upload sessions:", e);
  }
};
window.deleteUploadSession = async function (sessionId) {
  if (!confirm(`Are you sure you want to delete this upload & analysis session (${sessionId})?\n\nThis will remove the session timeline and map route.`)) return;
  try {
    const res = await fetch(`/api/unified/sessions/${encodeURIComponent(sessionId)}`, {
      method: 'DELETE'
    });
    const data = await res.json();
    if (res.ok && data.success) {
      if (typeof showToastAlert === 'function') showToastAlert("Upload session deleted successfully", "success");
      window.fetchAndRenderUploadSessionsFeed();
    } else {
      alert(data.detail || "Failed to delete session. Check your access permissions.");
    }
  } catch (e) {
    console.error("Delete session error:", e);
    alert("Error deleting upload session.");
  }
};
window.toggleSessionExpand = function (sessionId) {
  const card = document.getElementById(`session_card_${sessionId}`);
  const body = document.getElementById(`session_body_${sessionId}`);
  if (!body || !card) return;
  const isHidden = body.style.display === 'none';
  body.style.display = isHidden ? 'block' : 'none';
  if (isHidden) {
    card.classList.add('expanded');
  } else {
    card.classList.remove('expanded');
  }
};
window.loadSessionToMap = async function (sessionId) {
  try {
    const res = await fetch(`/api/unified/sessions/${encodeURIComponent(sessionId)}`);
    if (!res.ok) return;
    const data = await res.json();
    const s = data.session;
    if (!s) return;
    window.recentUploadBatchDetections = (s.vehicles || []).map(v => ({
      ...v,
      plate_number: v.plate_number || v.final_plate || 'UNREADABLE',
      final_plate: v.final_plate || v.plate_number || 'UNREADABLE',
      source_file: v.source_file || 'Session File',
      location: v.location || 'Panipat Checkpoint',
      gps_coords: v.gps_coords || '',
      captured_at: v.captured_at || s.timestamp
    }));
    const verifiedVeh = (s.vehicles || []).find(v => v.plate_number && v.plate_number !== 'UNREADABLE');
    const targetPlate = verifiedVeh ? verifiedVeh.plate_number || verifiedVeh.final_plate : '';
    window.renderRecentUploadResults(targetPlate);
    window.renderTacticalRouteMap(targetPlate);
  } catch (e) {
    console.error("Error loading session to map:", e);
  }
};
window.openUploadVehicleDetailModal = function (idx) {
  const v = window.recentUploadBatchDetections && window.recentUploadBatchDetections[idx] ? window.recentUploadBatchDetections[idx] : null;
  if (!v) return;
  if ((v.captured_id || v.id) && typeof window.openCaptureDetailModal === 'function') {
    window.openCaptureDetailModal(v.captured_id || v.id);
    return;
  }
  const modal = document.getElementById('captureDetailModal');
  if (modal) {
    const cleanP = v.plate_number || v.final_plate || 'UNREADABLE';
    const isUnreadable = cleanP === 'UNREADABLE';
    const plateEl = document.getElementById('capModalPlateText');
    const locEl = document.getElementById('capModalLocation');
    const timeEl = document.getElementById('capModalTime');
    const gpsEl = document.getElementById('capModalGps');
    const plateImg = document.getElementById('capModalPlateImg');
    const vehImg = document.getElementById('capModalVehicleImg');
    const rankBadge = document.getElementById('capModalRankBadge');
    const confBadge = document.getElementById('capModalOcrConfBadge');
    if (plateEl) plateEl.innerText = v.display_plate || cleanP;
    if (locEl) locEl.innerText = v.location || 'Panipat Checkpoint';
    if (timeEl) timeEl.innerText = (v.captured_at || '').replace('T', ' ');
    if (gpsEl) gpsEl.innerText = v.gps_coords || 'N/A';
    if (rankBadge) rankBadge.innerText = `Uploaded Checkpoint #${idx + 1}`;
    if (confBadge) confBadge.innerText = isUnreadable ? 'Unreadable' : `${Math.round(v.confidence || 90)}% OCR`;
    const pSrc = window.formatEvidenceImageSrc(v.plate_crop_base64 || v.plate_pic_path);
    const vSrc = window.formatEvidenceImageSrc(v.vehicle_crop_base64 || v.vehicle_pic_path || v.raw_scene_image);
    if (plateImg) plateImg.src = pSrc;
    if (vehImg) vehImg.src = vSrc;
    modal.style.display = 'flex';
  }
};
window.deleteVehicleTrail = async function (vehicleId, displayNumber) {
  const label = displayNumber || `Vehicle #${vehicleId}`;
  if (!confirm(`Are you sure you want to delete all trail passage records for ${label}?\n\nThis will remove all passage checkpoints and camera sightings from the Master Trail database.`)) {
    return;
  }
  try {
    const res = await fetch(`/api/trails/vehicle/${vehicleId}`, {
      method: 'DELETE'
    });
    const data = await res.json();
    if (res.ok) {
      alert(`Trail for ${label} deleted successfully (${data.deleted_sightings || 0} sightings removed).`);
      if (typeof window.refreshMasterTrail === 'function') {
        window.refreshMasterTrail();
      }
    } else {
      alert(data.detail || 'Failed to delete vehicle trail.');
    }
  } catch (e) {
    console.error('Error deleting vehicle trail:', e);
    alert('An error occurred while deleting the vehicle trail.');
  }
};
window.deleteTrailSighting = async function (sightingId) {
  if (!confirm(`Are you sure you want to delete this specific passage checkpoint (#${sightingId})?`)) {
    return;
  }
  try {
    const res = await fetch(`/api/trails/sightings/${sightingId}`, {
      method: 'DELETE'
    });
    const data = await res.json();
    if (res.ok) {
      if (typeof loadTrailHistoryData === 'function') {
        await loadTrailHistoryData();
      }
      if (typeof window.refreshMasterTrail === 'function') {
        window.refreshMasterTrail();
      }
    } else {
      alert(data.detail || 'Failed to delete sighting record.');
    }
  } catch (e) {
    console.error('Error deleting trail sighting:', e);
    alert('An error occurred while deleting the sighting record.');
  }
};
