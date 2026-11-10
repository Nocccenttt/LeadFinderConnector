'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const running = job => job && ['starting', 'queued', 'running'].includes(job.status);
  const keyOf = lead => `${lead.priority}::${encodeURIComponent(lead.client_id)}`;
  const sortModes = ['priority','score-desc','score-asc','name-asc','name-desc'];
  const state = {leads:[], selected:null, priority:'ALL', website:'ALL', workflow:'ALL', followup:'ALL', sort:'priority', jobs:new Map(), search:null,
    workspace:'', workspaceToken:'', capabilities:{}, device:innerWidth < 800 ? 'mobile' : 'desktop', connected:false, deleting:false, loadingLeads:false};
  let leadLoadEpoch = 0, pendingDelete = null;
  const watching = new Set();
  const preview = {key:null, url:null, status:'empty', token:0, controller:null, timeout:null};
  let rebuildKey = null;
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  const providers = ['deepseek','google','pexels'];
  let settingsToken = '', settingsEpoch = 0, settingsSaving = false, searchPending = false;
  function keyMessage(id, message, kind = '') {
    $(id).textContent = message;
    $(id).className = `key-test-result ${kind}`;
  }
  function renderKeyStatus(items) {
    for (const provider of providers) {
      const saved = items[provider];
      $(`key-status-${provider}`).textContent = saved?.configured ? saved.ending ? `Saved key ending in ${saved.ending}` : 'Saved key configured' : 'No saved key';
      $(`remove-${provider}`).disabled = settingsSaving || !saved?.configured;
    }
  }
  async function openSettings() {
    if (settingsSaving) return;
    if ($('find-dialog').open) $('find-dialog').close();
    const epoch = ++settingsEpoch;
    settingsToken = '';
    $('settings-form').reset();
    providers.forEach(provider => keyMessage(`key-result-${provider}`,''));
    keyMessage('settings-message','Loading saved key status…');
    $('save-settings').disabled = true;
    if (!$('settings-dialog').open) $('settings-dialog').showModal();
    try {
      const data = await api('/api-settings');
      if (epoch !== settingsEpoch) return;
      settingsToken = data.token; renderKeyStatus(data.providers);
      keyMessage('settings-message','Keys stay in this app’s local .env file. Testing does not save a replacement.');
      $('save-settings').disabled = false;
    } catch (error) { if (epoch === settingsEpoch) keyMessage('settings-message',error.message,'error'); }
  }
  $('settings-button').addEventListener('click',openSettings);
  $('job-settings-button').addEventListener('click',openSettings);
  $('search-settings-button').addEventListener('click',openSettings);
  $('settings-dialog').addEventListener('cancel',event=>{if(settingsSaving)event.preventDefault();});
  $('settings-dialog').addEventListener('close',()=>{
    settingsEpoch += 1; settingsToken = '';
    $('settings-form').reset();
    providers.forEach(provider => { $(`key-${provider}`).disabled = false; $(`test-${provider}`).disabled = false; $(`test-${provider}`).textContent = 'Test'; });
  });
  for (const provider of providers) {
    const input = $(`key-${provider}`), remove = $(`remove-${provider}`), button = $(`test-${provider}`);
    input.addEventListener('input',()=>keyMessage(`key-result-${provider}`,'Replacement not tested.'));
    remove.addEventListener('change',()=>{
      input.disabled = remove.checked; button.disabled = remove.checked;
      keyMessage(`key-result-${provider}`,remove.checked ? 'This key will be removed when you save.' : '');
    });
    button.addEventListener('click',async()=>{
      if (!settingsToken) return;
      const epoch = settingsEpoch, candidate = input.value.trim();
      button.disabled = true; button.textContent = 'Testing…';
      keyMessage(`key-result-${provider}`,'Checking authentication…');
      try {
        const result = await api('/api-settings',{method:'POST',headers:{'Content-Type':'application/json','X-Settings-Token':settingsToken},body:JSON.stringify({action:'test',provider,key:candidate})});
        if (epoch === settingsEpoch && input.value.trim() === candidate && !remove.checked)
          keyMessage(`key-result-${provider}`,result.message,result.ok ? 'success' : 'error');
      } catch (error) { if (epoch === settingsEpoch && input.value.trim() === candidate) keyMessage(`key-result-${provider}`,error.message,'error'); }
      finally { if (epoch === settingsEpoch) { button.textContent = 'Test'; button.disabled = remove.checked; } }
    });
  }
  $('settings-form').addEventListener('submit',async event=>{
    event.preventDefault();
    if (!settingsToken || settingsSaving) return;
    const keys = {};
    for (const provider of providers) {
      if ($(`remove-${provider}`).checked) keys[provider] = null;
      else if ($(`key-${provider}`).value.trim()) keys[provider] = $(`key-${provider}`).value.trim();
    }
    if (!Object.keys(keys).length) { keyMessage('settings-message','Enter a replacement key or choose Remove saved key.','error'); return; }
    const epoch = ++settingsEpoch;
    settingsSaving = true;
    providers.forEach(provider => { keyMessage(`key-result-${provider}`,''); $(`test-${provider}`).textContent = 'Test'; });
    const controls = [...$('settings-form').querySelectorAll('input,button')];
    controls.forEach(control => control.disabled = true);
    keyMessage('settings-message','Saving keys…');
    try {
      const result = await api('/api-settings',{method:'POST',headers:{'Content-Type':'application/json','X-Settings-Token':settingsToken},body:JSON.stringify({action:'save',keys})});
      if (epoch === settingsEpoch) {
        $('settings-form').reset();
        renderKeyStatus(result.providers);
        providers.forEach(provider => keyMessage(`key-result-${provider}`,''));
        keyMessage('settings-message',result.message,'success');
      }
      await readSession(false).catch(() => setConnection(false)); renderSelection();
    } catch (error) { if (epoch === settingsEpoch) keyMessage('settings-message',error.message,'error'); }
    finally {
      settingsSaving = false;
      if (epoch === settingsEpoch) {
        controls.forEach(control => control.disabled = false);
        providers.forEach(provider => { const remove = $(`remove-${provider}`); remove.disabled = $(`key-status-${provider}`).textContent === 'No saved key'; $(`key-${provider}`).disabled = remove.checked; $(`test-${provider}`).disabled = remove.checked; });
      }
    }
  });
  function node(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  }
  function selectedLead() { return state.leads.find(lead => keyOf(lead) === state.selected); }
  const workflowLabels = {NEW:'New',CONTACTED:'Contacted',FOLLOW_UP:'Follow-up',INTERESTED:'Interested',CLOSED:'Closed'};
  function workflowOf(lead) {
    const saved = lead?.workflow && typeof lead.workflow === 'object' ? lead.workflow : {};
    const status = workflowLabels[saved.status] ? saved.status : 'NEW';
    return {status,notes:String(saved.notes || ''),follow_up_date:String(saved.follow_up_date || '')};
  }
  function renderWorkflow(lead) {
    const workflow = workflowOf(lead);
    $('lead-workflow-status').value = workflow.status;
    $('lead-follow-up-date').value = workflow.follow_up_date;
    $('lead-notes').value = workflow.notes;
    $('lead-notes-count').textContent = workflow.notes.length + ' / 5000';
    $('workflow-save-state').textContent = '';
    $('save-lead-workflow').disabled = !state.connected || !state.workspaceToken;
  }
  function workflowChip(lead) {
    const workflow = workflowOf(lead);
    return node('span','workflow-chip workflow-' + workflow.status.toLowerCase(),workflowLabels[workflow.status]);
  }
  function localToday() {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), now.getDate());
  }
  function parseLocalDate(value) {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value || ''));
    if (!match) return null;
    const result = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
    return Number.isNaN(result.getTime()) ? null : result;
  }
  function followupInfo(lead) {
    const workflow = workflowOf(lead);
    if (!workflow.follow_up_date || workflow.status === 'CLOSED') return {kind:'NONE',days:null,label:'',date:null};
    const due = parseLocalDate(workflow.follow_up_date);
    if (!due) return {kind:'NONE',days:null,label:'',date:null};
    const days = Math.round((due - localToday()) / 86400000);
    if (days < 0) return {kind:'OVERDUE',days,label:Math.abs(days) === 1 ? '1 day overdue' : Math.abs(days) + ' days overdue',date:due};
    if (days === 0) return {kind:'TODAY',days,label:'Due today',date:due};
    if (days === 1) return {kind:'UPCOMING',days,label:'Tomorrow',date:due};
    return {kind:'UPCOMING',days,label:'In ' + days + ' days',date:due};
  }
  function followupRank(lead) {
    const info = followupInfo(lead);
    if (info.kind === 'OVERDUE') return info.days;
    if (info.kind === 'TODAY') return 0;
    if (info.kind === 'UPCOMING') return info.days;
    return Number.POSITIVE_INFINITY;
  }
  function followupBadge(lead) {
    const info = followupInfo(lead);
    if (info.kind === 'NONE') return null;
    return node('span','followup-badge followup-' + info.kind.toLowerCase(),info.label);
  }
  function renderFollowupSummary() {
    const counts = {ALL:state.leads.length,NEEDS:0,OVERDUE:0,TODAY:0,UPCOMING:0};
    for (const lead of state.leads) {
      const kind = followupInfo(lead).kind;
      if (kind !== 'NONE') { counts.NEEDS += 1; counts[kind] += 1; }
    }
    $('followup-all-count').textContent = counts.ALL;
    $('followup-needs-count').textContent = counts.NEEDS;
    $('followup-overdue-count').textContent = counts.OVERDUE;
    $('followup-today-count').textContent = counts.TODAY;
    $('followup-upcoming-count').textContent = counts.UPCOMING;
    document.querySelectorAll('[data-followup-filter]').forEach(button => {
      const active = button.dataset.followupFilter === state.followup;
      button.classList.toggle('active',active);
      button.setAttribute('aria-pressed',String(active));
    });
  }
  function readStorage(key, fallback) { try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; } }
  function saveStorage(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* Storage is optional in private/restricted browsers. */ } }
  function savePreferences() {
    if (!state.workspace) return;
    saveStorage(`leadfinder:${state.workspace}`, {selected:state.selected, device:state.device, sort:state.sort,
      jobs:[...state.jobs.values()].filter(running), search:running(state.search) ? state.search : null});
  }
  function setConnection(connected) {
    state.connected = connected;
    $('connection').classList.toggle('connected', connected);
    $('connection').textContent = connected ? 'Workspace connected' : 'Connection interrupted';
    renderDeletionControls(); renderWorkControls();
  }
  async function api(url, options = {}) {
    const signal = options.signal ? AbortSignal.any([options.signal, AbortSignal.timeout(15000)]) : AbortSignal.timeout(15000);
    const response = await fetch(url, {...options,signal});
    let data;
    try { data = await response.json(); } catch { throw new Error('The workspace returned an unreadable response. Try again.'); }
    if (!response.ok) {
      const error = new Error(data.error || data.message || `Request failed (${response.status}).`);
      error.status = response.status;
      throw error;
    }
    return data;
  }
  function workspaceError(message) {
    $('workspace-error-text').textContent = message;
    $('workspace-error').hidden = !message;
  }
  function websitesRunning() { return [...state.jobs.values()].some(running); }
  function renderWorkControls() {
    const searching = searchPending || running(state.search), building = websitesRunning();
    $('find-button').disabled = searching || building;
    $('search-submit').disabled = searching || building;
    $('find-button').title = building ? 'Finish website builds before starting a business search.' : searching ? 'A business search is already running.' : '';
    $('search-submit').title = building ? 'Finish website builds before starting a business search.' : '';
  }
  function compareLeads(a, b) {
    const score = lead => Number.isFinite(Number(lead.score)) ? Number(lead.score) : 0;
    const nameOrder = String(a.name || a.client_id).localeCompare(String(b.name || b.client_id), undefined, {sensitivity:'base',numeric:true});
    let order = 0;
    if (state.followup !== 'ALL') order = followupRank(a) - followupRank(b);
    else if (state.sort === 'name-asc' || state.sort === 'name-desc') order = nameOrder * (state.sort === 'name-desc' ? -1 : 1);
    else if (state.sort === 'score-asc' || state.sort === 'score-desc') order = (score(a) - score(b)) * (state.sort === 'score-desc' ? -1 : 1);
    else {
      const priority = {HIGH:0,MEDIUM:1,LOW:2};
      order = (priority[a.priority] ?? 3) - (priority[b.priority] ?? 3) || score(b) - score(a);
    }
    const aKey = keyOf(a), bKey = keyOf(b);
    return order || nameOrder || (aKey < bKey ? -1 : aKey > bKey ? 1 : 0);
  }
  function deletionBlocked(leads) {
    if (state.deleting) return 'Removing businesses…';
    if (!state.connected || !state.workspaceToken) return 'Refresh the workspace before deleting businesses.';
    if (state.loadingLeads) return 'Wait for the business list to finish refreshing.';
    if (!leads.length) return 'There are no businesses to remove.';
    if (running(state.search)) return 'Wait for the business search to finish before deleting businesses.';
    if (leads.some(lead => running(state.jobs.get(keyOf(lead))))) return 'Wait for the selected website builds to finish before deleting these businesses.';
    const savedKeys = new Set(state.leads.map(keyOf));
    if (leads.some(lead => !savedKeys.has(keyOf(lead)))) return 'The list has changed. Close this confirmation and select the businesses again.';
    return '';
  }
  function renderDeletionControls() {
    const selected = selectedLead();
    const selectedReason = deletionBlocked(selected ? [selected] : []);
    $('delete-business-button').disabled = Boolean(selectedReason);
    $('delete-business-button').title = selectedReason || 'Remove this business from the saved list.';

    const clearReason = state.deleting ? 'Removing businesses…' :
      !state.connected || !state.workspaceToken ? 'Refresh the workspace before deleting businesses.' :
      state.loadingLeads ? 'Wait for the business list to finish refreshing.' :
      running(state.search) ? 'Wait for the business search to finish before deleting businesses.' :
      !state.leads.length ? 'There are no businesses to remove.' : '';
    const clearButton = $('clear-list-button');
    clearButton.disabled = Boolean(clearReason);
    clearButton.title = clearReason || 'Choose High, Medium, Low, or All.';
    if (clearReason) {
      $('clear-menu-panel').hidden = true;
      clearButton.setAttribute('aria-expanded','false');
    }

    document.querySelectorAll('[data-clear-priority]').forEach(button => {
      const priority = button.dataset.clearPriority;
      const leads = priority === 'ALL' ? state.leads : state.leads.filter(lead => lead.priority === priority);
      const reason = clearReason || deletionBlocked(leads);
      button.disabled = Boolean(reason);
      button.title = reason || `Remove all ${priority === 'ALL' ? '' : priority.toLowerCase() + '-priority ' }saved businesses.`;
    });

    if (pendingDelete) {
      const reason = deletionBlocked(pendingDelete.leads);
      $('confirm-delete').disabled = Boolean(reason);
      $('confirm-delete').title = reason;
      $('confirm-delete').textContent = state.deleting ? 'Removing…' : pendingDelete.scope ? `Clear ${pendingDelete.scope === 'ALL' ? 'all' : pendingDelete.scope.toLowerCase()}` : 'Delete business';
    }
    document.querySelectorAll('[data-close="delete-dialog"]').forEach(button => button.disabled = state.deleting);
  }
  function openDeleteScope(scope = null) {
    const selected = selectedLead();
    const leads = scope ? (scope === 'ALL' ? [...state.leads] : state.leads.filter(lead => lead.priority === scope)) : selected ? [selected] : [];
    if (deletionBlocked(leads)) return;
    pendingDelete = {leads,scope};
    const scoped = Boolean(scope);
    const label = scope === 'ALL' ? 'all' : String(scope || '').toLowerCase();
    $('delete-title').textContent = scoped ? `Clear ${label} saved businesses?` : 'Delete this business?';
    $('delete-description').textContent = scoped
      ? `Remove ${leads.length} ${scope === 'ALL' ? '' : label + '-priority '}${leads.length === 1 ? 'business' : 'businesses'} from this workspace? Businesses outside this group will be kept. Saved files will remain in the deleted-leads archive.`
      : `Remove ${leads[0].name || 'this business'} from your saved list?`;
    $('delete-error').hidden = true;
    $('clear-menu-panel').hidden = true;
    $('clear-list-button').setAttribute('aria-expanded','false');
    renderDeletionControls();
    $('delete-dialog').showModal();
  }
  async function deleteBusinesses() {
    if (!pendingDelete || deletionBlocked(pendingDelete.leads)) return;
    const requested = pendingDelete.leads.map(lead => ({priority:lead.priority,name:lead.client_id}));
    state.deleting = true; leadLoadEpoch += 1;
    renderDeletionControls();
    $('delete-error').hidden = true;
    let refreshAfter = false;
    try {
      const result = await api('/delete-leads',{method:'POST',headers:{'Content-Type':'application/json','X-Workspace-Token':state.workspaceToken},body:JSON.stringify({leads:requested})});
      if (!Array.isArray(result.deleted)) throw new Error('The deletion result could not be read. Check the refreshed list before trying again.');
      const removed = new Set(result.deleted.map(lead => keyOf({priority:lead.priority,client_id:lead.name})));
      state.leads = state.leads.filter(lead => !removed.has(keyOf(lead)));
      for (const key of removed) state.jobs.delete(key);
      if (removed.has(state.selected)) state.selected = null;
      savePreferences(); renderList(); renderSelection();
      $('delete-dialog').close();
      pendingDelete = null;
      $('workspace-status-text').textContent = `${removed.size} ${removed.size === 1 ? 'business removed' : 'businesses removed'} from your saved list. Saved files were kept in the local archive.`;
      $('workspace-status').hidden = false;
      $('business-panel').focus({preventScroll:true});
      refreshAfter = true;
    } catch (error) {
      $('delete-error').textContent = error.message;
      $('delete-error').hidden = false;
      if (error.status === 403 || error.status === 409) await readSession(false).catch(() => {});
      refreshAfter = true;
    } finally {
      state.deleting = false;
      renderDeletionControls();
      if (refreshAfter) await loadLeads();
      if (pendingDelete) {
        const reason = deletionBlocked(pendingDelete.leads);
        if (reason) { $('delete-error').textContent = reason; $('delete-error').hidden = false; }
      }
    }
  }
  function filteredLeads() {
    const query = $('lead-search').value.trim().toLocaleLowerCase();
    return state.leads.filter(lead => {
      const searchable = [lead.name, lead.address, lead.category, lead.reason].join(' ').toLocaleLowerCase();
      const job = state.jobs.get(keyOf(lead));
      const status = running(job) ? 'working' : job?.status === 'error' ? 'failed' : lead.preview_state || (lead.demo_ready ? 'ready' : 'missing');
      const workflowStatus = workflowOf(lead).status;
      const followup = followupInfo(lead);
      const followupMatch = state.followup === 'ALL' || (state.followup === 'NEEDS' ? followup.kind !== 'NONE' : followup.kind === state.followup);
      return (!query || searchable.includes(query)) && (state.priority === 'ALL' || lead.priority === state.priority) &&
        (state.workflow === 'ALL' || state.workflow === workflowStatus) && followupMatch &&
        (state.website === 'ALL' || state.website === status || (state.website === 'missing' && status === 'incomplete'));
    }).sort(compareLeads);
  }
  function renderList() {
    renderDeletionControls(); renderWorkControls();
    const list = $('business-list');
    const focusedKey = list.contains(document.activeElement) ? document.activeElement.dataset.key : null;
    list.replaceChildren();
    list.setAttribute('aria-busy','false');
    renderFollowupSummary();
    const filtered = filteredLeads();
    $('visible-count').textContent = `${filtered.length} ${filtered.length === 1 ? 'business' : 'businesses'}`;
    $('saved-count').textContent = `${state.leads.length} saved · ${state.leads.filter(lead => lead.demo_ready).length} websites ready`;
    document.querySelectorAll('[data-priority]').forEach(button => {
      const active = button.dataset.priority === state.priority;
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', String(active));
    });
    document.querySelectorAll('[data-count]').forEach(count => {
      count.textContent = count.dataset.count === 'ALL' ? state.leads.length : state.leads.filter(lead => lead.priority === count.dataset.count).length;
    });
    if (!filtered.length) {
      const empty = node('div','list-empty');
      empty.append(node('h3','',state.leads.length ? 'No matching businesses.' : 'Your next client starts here.'),
        node('p','',state.leads.length ? 'Try another search or clear your filters.' : 'Find businesses to add them to this workspace.'));
      const action = node('button','button',state.leads.length ? 'Clear filters' : 'Find businesses');
      action.type = 'button';
      action.addEventListener('click', () => {
        if (!state.leads.length) return openSearch();
        $('lead-search').value = ''; $('website-filter').value = 'ALL'; $('workflow-filter').value = 'ALL'; state.website = 'ALL'; state.workflow = 'ALL'; state.followup = 'ALL'; state.priority = 'ALL'; renderList();
      });
      empty.append(action); list.append(empty); return;
    }
    const tabKey = filtered.some(lead => keyOf(lead) === state.selected) ? state.selected : keyOf(filtered[0]);
    filtered.forEach(lead => {
      const key = keyOf(lead), job = state.jobs.get(key), busy = running(job);
      const row = node('button','lead-row');
      row.type = 'button'; row.dataset.key = key; row.setAttribute('role','option');
      row.setAttribute('aria-selected', String(state.selected === key)); row.tabIndex = key === tabKey ? 0 : -1;
      const top = node('span','lead-row-top');
      top.append(node('span','lead-row-name',lead.name || 'Unnamed business'),node('span','lead-score',String(lead.score ?? '')));
      row.append(top,node('span','lead-location',lead.address || 'No address recorded'));
      const bottom = node('span','lead-row-bottom');
      const label = busy ? 'Building website…' : job?.status === 'error' || lead.preview_state === 'failed' ? 'Needs attention' : lead.demo_ready ? 'Website ready' : 'Not built yet';
      bottom.append(node('span',`priority-label ${lead.priority.toLowerCase()}`,lead.priority[0] + lead.priority.slice(1).toLowerCase()), workflowChip(lead));
      const dueBadge = followupBadge(lead);
      if (dueBadge) bottom.append(dueBadge);
      bottom.append(node('span',`row-website-status ${busy ? 'working' : lead.demo_ready ? 'ready' : ''}`,label));
      row.append(bottom);
      row.addEventListener('click', () => selectLead(key, true));
      row.addEventListener('keydown', event => {
        const keys = ['ArrowUp','ArrowDown','Home','End'];
        if (!keys.includes(event.key)) return;
        event.preventDefault();
        const index = filtered.findIndex(item => keyOf(item) === key);
        const next = event.key === 'Home' ? 0 : event.key === 'End' ? filtered.length - 1 : Math.max(0,Math.min(filtered.length - 1,index + (event.key === 'ArrowDown' ? 1 : -1)));
        selectLead(keyOf(filtered[next]), false);
      });
      list.append(row);
    });
    if (focusedKey) [...list.children].find(row => row.dataset.key === focusedKey)?.focus({preventScroll:true});
  }
  function selectLead(key, pointer) {
    if (!state.leads.some(lead => keyOf(lead) === key)) return;
    const changed = state.selected !== key;
    state.selected = key; savePreferences(); renderList(); renderSelection(changed);
    const row = [...$('business-list').children].find(element => element.dataset.key === key);
    row?.focus({preventScroll:true}); row?.scrollIntoView({block:'nearest'});
    if (pointer && innerWidth < 800) $('detail-panel').scrollIntoView({block:'start'});
  }
  async function loadLeads() {
    if (state.deleting) return false;
    const epoch = ++leadLoadEpoch;
    state.loadingLeads = true; renderDeletionControls();
    $('refresh-button').disabled = true;
    try {
      const data = await api('/leads');
      if (epoch !== leadLoadEpoch) return false;
      if (!Array.isArray(data.leads)) throw new Error('The business list could not be read. Try refreshing.');
      state.leads = data.leads;
      if (state.selected && !selectedLead()) state.selected = null;
      savePreferences();
      setConnection(true); workspaceError(''); renderList(); renderSelection();
      return true;
    } catch (error) {
      if (epoch !== leadLoadEpoch) return false;
      setConnection(false); workspaceError(`Could not load saved businesses. ${error.message}`);
      $('business-list').setAttribute('aria-busy','false');
      if (!state.leads.length) $('business-list').replaceChildren(node('div','list-empty','The business list is unavailable. Use Retry above to reconnect.'));
      return false;
    } finally {
      if (epoch === leadLoadEpoch) { state.loadingLeads = false; $('refresh-button').disabled = false; renderDeletionControls(); }
    }
  }
  function renderQuality(lead, busy) {
    const qa = lead?.qa && typeof lead.qa === 'object' ? lead.qa : {};
    const status = String(qa.status || 'NOT RUN').toUpperCase();
    const total = Number(qa.checks_total || 0), passed = Number(qa.checks_passed || 0);
    const issues = Array.isArray(qa.issues) ? qa.issues.filter(Boolean).slice(0,5) : [];
    const ready = Boolean(lead?.demo_ready) && status === 'PASS';
    const failed = status === 'FAILED' || status === 'NEEDS REVIEW' || lead?.preview_state === 'failed';

    $('qa-card').classList.toggle('ready', ready);
    $('qa-card').classList.toggle('attention', failed);
    $('qa-title').textContent = busy ? 'Quality check pending' : ready ? 'Ready to review' : failed ? 'Needs attention' : lead?.demo_ready ? 'Quality check unavailable' : 'Not checked yet';
    $('qa-badge').className = `qa-badge ${ready ? 'ready' : failed ? 'attention' : ''}`;
    $('qa-badge').textContent = busy ? 'Building' : ready ? 'Passed' : failed ? 'Review' : 'Pending';
    $('qa-summary').textContent = busy ? 'LeadFinder will run the website checks after the build finishes.' :
      total ? `${passed} of ${total} quality checks passed.` :
      lead?.demo_ready ? 'The website files are available, but no quality report was found.' :
      'Build a website to run the quality checks.';

    const issueBox = $('qa-issues');
    issueBox.replaceChildren();
    issueBox.hidden = !issues.length;
    if (issues.length) {
      issueBox.append(node('span','qa-issues-label','Check these items'));
      const list = node('ul','qa-issues-list');
      for (const issue of issues) list.append(node('li','',issue));
      issueBox.append(list);
    }

    const steps = {
      build: busy || lead?.demo_ready,
      qa: busy || status !== 'NOT RUN',
      ready,
    };
    for (const [name, complete] of Object.entries(steps)) {
      const element = $(`step-${name}`);
      element.classList.toggle('complete', Boolean(complete));
      element.classList.toggle('active', name === 'build' ? busy : name === 'qa' ? !busy && failed : name === 'ready' ? ready : false);
    }
  }

  function renderSelection(forcePreview = false) {
    const lead = selectedLead();
    renderDeletionControls();
    $('detail-panel').dataset.hasSelection = String(Boolean(lead));
    $('selection-empty').hidden = Boolean(lead); $('selected-workspace').hidden = !lead;
    if (!lead) { resetPreview(); return; }
    const job = state.jobs.get(state.selected), busy = running(job), searching = searchPending || running(state.search);
    $('selected-category').textContent = lead.category || 'Local business';
    $('selected-name').textContent = lead.name || 'Unnamed business';
    $('selected-address').textContent = lead.address || 'No address recorded';
    const reason = Array.isArray(lead.reason) ? lead.reason.join(' · ') : String(lead.reason || '');
    $('selected-reason').textContent = reason;
    $('selected-reason-card').hidden = !reason;
    $('selected-priority').className = `priority-label ${lead.priority.toLowerCase()}`;
    $('selected-priority').textContent = lead.priority[0] + lead.priority.slice(1).toLowerCase() + ' priority';
    $('selected-score').textContent = lead.score ? `Opportunity score ${lead.score}` : '';
    const contacts = $('contact-links'); contacts.replaceChildren();
    if (lead.phone) { const link = node('a','',lead.phone); link.href = `tel:${String(lead.phone).replace(/[^+\d]/g,'')}`; contacts.append(link); }
    if (lead.website) {
      try { const url = new URL(lead.website); if (['http:','https:'].includes(url.protocol)) { const link = node('a','','Original website ↗'); link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer'; contacts.append(link); } } catch { /* A missing/invalid source URL has no link. */ }
    }
    const ready = Boolean(lead.demo_ready);
    $('website-state').className = `state-label ${busy ? 'working' : ready ? 'ready' : ''}`;
    $('website-state').textContent = busy ? 'Building website' : job?.status === 'error' || lead.preview_state === 'failed' ? 'Last build needs attention' : ready ? 'Preview ready' : 'Not built yet';
    const configured = state.capabilities.website_configured !== false;
    $('build-message').textContent = busy ? job.message || 'Researching, writing and building. This can take a few minutes.' :
      searching ? 'Wait for the business search to finish before building or redesigning a website.' :
      !configured ? 'Website generation is not configured in this workspace.' : !lead.can_generate ? 'Website builds are available for high- and medium-priority businesses with a saved handoff.' :
      lead.preview_state === 'failed' ? lead.preview_message : job?.status === 'complete' ? 'Your website is ready to review and download.' : ready ? 'Redesign keeps the saved copy. Rebuild is available under more actions.' : 'Create a website to get a working preview and downloadable files.';
    $('build-button').hidden = ready; $('build-button').disabled = busy || searching || !lead.can_generate || !configured;
    $('build-button').textContent = busy ? 'Building…' : 'Build website';
    $('redesign-button').hidden = !ready || !lead.can_generate; $('redesign-button').disabled = busy || searching || !configured;
    $('download-button').hidden = !ready; $('download-button').disabled = busy || lead.preview_state === 'failed';
    $('more-actions').hidden = !ready || !lead.can_generate || busy; $('more-actions').open = false;
    $('rebuild-button').disabled = searching || !configured;
    $('job-error').hidden = job?.status !== 'error'; $('job-error').textContent = job?.status === 'error' ? job.message : '';
    $('job-settings-button').hidden = job?.status !== 'error' || !/api.key|401|authentication/i.test(job.message || '');
    $('open-preview').setAttribute('aria-disabled', String(!ready || busy));
    if (ready) $('open-preview').href = lead.demo_url; else $('open-preview').removeAttribute('href');
    $('retry-preview').disabled = !ready || busy;
    renderWorkflow(lead);
    renderQuality(lead, busy);
    document.querySelectorAll('[data-device]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.device === state.device)));
    if (forcePreview || preview.key !== state.selected || (ready && preview.url !== lead.demo_url && preview.status !== 'loading')) loadPreview(lead);
  }
  function resetPreview() {
    preview.controller?.abort(); clearTimeout(preview.timeout); preview.token += 1;
    preview.key = null; preview.url = null; preview.status = 'empty';
    $('preview-frame').onload = null; $('preview-frame').src = 'about:blank'; $('frame-stage').hidden = true;
  }
  function showPlaceholder(kind, title, description) {
    preview.status = kind;
    $('frame-stage').hidden = true; $('preview-placeholder').hidden = false;
    $('preview-title').textContent = title; $('preview-description').textContent = description;
    $('preview-indicator').classList.toggle('loading', kind === 'loading');
    $('preview-indicator').textContent = kind === 'loading' ? '' : kind === 'error' ? '!' : '↗';
    $('preview-retry-button').hidden = kind !== 'error';
    $('preview-canvas').setAttribute('aria-busy',String(kind === 'loading'));
  }
  function localPreviewURL(value) {
    const url = new URL(value, location.origin);
    if (url.origin !== location.origin || !url.pathname.startsWith('/demo/')) throw new Error('The preview address is invalid. Refresh this business and try again.');
    return url;
  }
  async function loadPreview(lead) {
    preview.controller?.abort(); clearTimeout(preview.timeout);
    const token = ++preview.token, key = keyOf(lead), controller = new AbortController();
    preview.controller = controller; preview.key = key; preview.url = lead.demo_url || null;
    $('preview-frame').onload = null; $('preview-frame').src = 'about:blank';
    showPlaceholder('loading','Checking the preview…','Making sure the website is available before opening it.');
    const current = () => token === preview.token && key === state.selected;
    try {
      const info = await api(`/preview-status?priority=${encodeURIComponent(lead.priority)}&name=${encodeURIComponent(lead.client_id)}`, {signal:controller.signal});
      if (!current()) return;
      if (info.qa) { lead.qa = info.qa; renderQuality(lead, running(state.jobs.get(state.selected))); }
      if (!info.available) {
        showPlaceholder('empty',info.state === 'missing' ? 'No website yet.' : 'This website needs a new build.',info.message || 'Build a website to see a complete preview here.');
        return;
      }
      const url = localPreviewURL(info.preview_url);
      url.searchParams.set('preview',String(Date.now()));
      const response = await fetch(url, {cache:'no-store',signal:AbortSignal.any([controller.signal,AbortSignal.timeout(15000)])});
      if (!response.ok) throw new Error(`The preview could not be opened (${response.status}). Try loading it again.`);
      const html = await response.text();
      if (!current()) return;
      const previewDocument = new DOMParser().parseFromString(html,'text/html');
      if (!previewDocument.body?.textContent.trim()) throw new Error('The generated page is empty. Rebuild it to create a complete preview.');
      preview.url = info.preview_url;
      const frame = node('iframe');
      frame.id = 'preview-frame'; frame.title = 'Generated website preview';
      frame.setAttribute('sandbox','allow-scripts');
      showPlaceholder('loading','Opening the website…','The preview will appear here in a moment.');
      frame.onload = () => {
        if (!current()) return;
        clearTimeout(preview.timeout); preview.status = 'ready';
        $('preview-placeholder').hidden = true; $('frame-stage').hidden = false;
        $('preview-canvas').setAttribute('aria-busy','false'); fitPreview();
      };
      frame.onerror = () => { if (current()) { clearTimeout(preview.timeout); showPlaceholder('error','Could not load the preview.','Try again, or open the website in a new tab.'); } };
      frame.src = url.href;
      preview.timeout = setTimeout(() => { if (current() && preview.status === 'loading') showPlaceholder('error','The preview is taking longer than expected.','Try loading it again, or open the website in a new tab.'); },15000);
      $('preview-frame').replaceWith(frame); fitPreview();
    } catch (error) {
      if (current() && error.name !== 'AbortError') showPlaceholder('error','Could not load the preview.',error.message);
    }
  }
  function fitPreview() {
    const canvas = $('preview-canvas'), frame = $('preview-frame'), stage = $('frame-stage');
    if (canvas.clientWidth <= 0) return;
    const width = state.device === 'mobile' ? 390 : 1440;
    const scale = Math.min(1,Math.max(.1,(canvas.clientWidth - 42) / width));
    const height = Math.min(state.device === 'mobile' ? 844 : 1800,Math.max(300,Math.round((canvas.clientHeight - 42) / scale)));
    frame.style.width = `${width}px`; frame.style.height = `${height}px`; frame.style.transform = `scale(${scale})`;
    stage.style.width = `${width * scale + 2}px`; stage.style.height = `${height * scale + 2}px`;
    stage.classList.toggle('mobile',state.device === 'mobile');
    $('preview-size').textContent = `${width}px · Fit ${Math.round(scale * 100)}%`;
  }
  async function saveLeadWorkflow() {
    const lead = selectedLead();
    if (!lead || !state.connected || !state.workspaceToken) return;
    const button = $('save-lead-workflow');
    const payload = {priority:lead.priority,name:lead.client_id,status:$('lead-workflow-status').value,follow_up_date:$('lead-follow-up-date').value,notes:$('lead-notes').value};
    button.disabled = true; button.textContent = 'Saving…'; $('workflow-save-state').textContent = 'Saving…';
    try {
      const result = await api('/lead-workflow',{method:'POST',headers:{'Content-Type':'application/json','X-Workspace-Token':state.workspaceToken},body:JSON.stringify(payload)});
      lead.workflow = result.workflow; $('workflow-save-state').textContent = 'Saved'; renderList();
      setTimeout(()=>{ if ($('workflow-save-state').textContent === 'Saved') $('workflow-save-state').textContent = ''; },1800);
    } catch (error) {
      $('workflow-save-state').textContent = error.message;
      if (error.status === 403 || error.status === 404) await loadLeads();
    } finally {
      button.textContent = 'Save follow-up'; button.disabled = !state.connected || !state.workspaceToken;
    }
  }

  function openSearch() {
    if (state.deleting) return;
    if (searchPending || running(state.search)) { $('search-progress').scrollIntoView({block:'start'}); return; }
    if (websitesRunning()) { workspaceError('Wait for website builds to finish before starting a business search.'); return; }
    $('search-form-error').hidden = true;
    $('find-dialog').showModal();
  }
  async function beginBuild(preserveContent) {
    const lead = selectedLead();
    if (!lead || state.deleting || searchPending || running(state.search) || running(state.jobs.get(state.selected))) return;
    const key = keyOf(lead), starting = {key,priority:lead.priority,client_id:lead.client_id,kind:'website',status:'starting',started_at:Date.now()/1000,message:'Starting the website build…'};
    state.jobs.set(key,starting); savePreferences(); renderList(); renderSelection();
    try {
      const result = await api('/generate-landing-page',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({priority:lead.priority,name:lead.client_id,preserve_content:preserveContent})});
      const job = {...starting,job_id:result.job_id,status:'queued'};
      state.jobs.set(key,job); savePreferences(); watchWebsite(job); renderList(); if (state.selected === key) renderSelection();
    } catch (error) {
      await readSession(false).catch(() => {});
      const recovered = state.jobs.get(key);
      if (!recovered?.job_id || !running(recovered)) state.jobs.set(key,{...starting,status:'error',message:error.message});
      savePreferences(); renderList(); if (state.selected === key) renderSelection();
    }
  }
  async function watchWebsite(job) {
    if (!job.job_id || watching.has(job.job_id)) return;
    watching.add(job.job_id);
    const current = () => state.jobs.get(job.key)?.job_id === job.job_id;
    try {
      while (current() && running(state.jobs.get(job.key))) {
        try {
          const update = await api(`/landing-page-status?job_id=${encodeURIComponent(job.job_id)}`);
          if (!current()) break;
          setConnection(true); Object.assign(job,update);
          state.jobs.set(job.key,job); savePreferences(); renderList();
          if (state.selected === job.key) renderSelection();
          if (!running(job)) {
            await loadLeads();
            if (!current()) break;
            if (state.selected === job.key && job.status === 'complete' && selectedLead()) await loadPreview(selectedLead());
            $('announcement').textContent = job.status === 'complete' ? `Website ready for ${state.leads.find(lead => keyOf(lead) === job.key)?.name || 'your business'}.` : 'A website build needs attention.';
            break;
          }
        } catch (error) {
          if (!current()) break;
          if (error.status === 404) {
            await loadLeads();
            if (!current()) break;
            const lead = state.leads.find(item => keyOf(item) === job.key);
            if (lead?.demo_ready) state.jobs.delete(job.key);
            else state.jobs.set(job.key,{...job,status:'error',message:'This build session is no longer available. Your saved businesses are still here; you can start the build again.'});
            savePreferences(); renderList(); if (state.selected === job.key) renderSelection(); break;
          }
          setConnection(false); job.message = 'Connection interrupted. The build may still be running; reconnecting…';
          if (state.selected === job.key) renderSelection();
        }
        await sleep(state.connected ? 1000 : 3000);
      }
    } finally { watching.delete(job.job_id); }
  }
  function renderSearch(job) {
    renderDeletionControls();
    $('search-progress').hidden = false;
    $('search-phase').textContent = job.status === 'error' ? 'Search needs attention' : job.phase || (job.status === 'complete' ? 'Search complete' : 'Finding businesses…');
    $('search-message').textContent = [job.message,job.current_business].filter(Boolean).join(' · ');
    $('search-settings-button').hidden = job.status !== 'error' || !/api.key|401|authentication/i.test(job.message || '');
    $('search-progress-bar').value = job.status === 'complete' ? 100 : Math.max(0,Math.min(100,Number(job.percent || 0)));
    $('search-count').textContent = job.total ? `${job.current_index || 0} of ${job.total} businesses checked` : job.status === 'complete' ? 'Your saved businesses are updated.' : 'Preparing the search…';
    $('search-counts').textContent = `${job.high || 0} high · ${job.medium || 0} medium · ${job.low || 0} low`;
    $('search-again').hidden = running(job);
    renderWorkControls(); renderSelection();
    $('activity-log').replaceChildren(...(job.log || []).map(line => node('div',`activity-line ${line.type === 'error' ? 'error' : ''}`,line.text)));
  }
  async function watchSearch(job) {
    if (!job?.job_id || watching.has(job.job_id)) return;
    watching.add(job.job_id);
    const current = () => state.search?.job_id === job.job_id;
    try {
      while (current() && running(state.search)) {
        try {
          const update = await api(`/job-status?job_id=${encodeURIComponent(job.job_id)}`);
          if (!current()) break;
          setConnection(true); Object.assign(job,update); state.search = job; savePreferences(); renderSearch(job);
          if (!running(job)) { await loadLeads(); break; }
        } catch (error) {
          if (!current()) break;
          if (error.status === 404) { state.search = job; job.status = 'error'; job.message = 'This search session has ended. Refresh your saved businesses, or start another search.'; renderSearch(job); savePreferences(); await loadLeads(); break; }
          setConnection(false); job.message = 'Connection interrupted. The search may still be running; reconnecting…'; renderSearch(job);
        }
        await sleep(state.connected ? 1000 : 3000);
      }
    } finally { watching.delete(job.job_id); }
  }
  async function readSession(restore) {
    const session = await api('/session');
    state.workspace = session.workspace_id; state.capabilities = session.capabilities || {};
    state.workspaceToken = typeof session.workspace_token === 'string' ? session.workspace_token : '';
    if (restore) {
      const saved = readStorage(`leadfinder:${state.workspace}`,{});
      state.selected = saved.selected || null;
      if (sortModes.includes(saved.sort)) state.sort = saved.sort;
      $('lead-sort').value = state.sort;
      if (['desktop','mobile'].includes(saved.device)) state.device = saved.device;
      for (const job of saved.jobs || []) if (job.key && job.job_id) state.jobs.set(job.key,job);
      if (saved.search?.job_id) state.search = saved.search;
    }
    for (const active of session.active_jobs || []) {
      if (active.kind === 'website' && active.client_id) {
        const job = {...active,key:keyOf(active)}; state.jobs.set(job.key,job);
      } else if (active.kind === 'leads') state.search = active;
    }
    setConnection(true);
    for (const job of state.jobs.values()) if (running(job)) watchWebsite(job);
    if (running(state.search)) { renderSearch(state.search); watchSearch(state.search); }
    return session;
  }
  $('lead-notes').addEventListener('input',()=>{$('lead-notes-count').textContent = $('lead-notes').value.length + ' / 5000'; $('workflow-save-state').textContent = '';});
  $('lead-workflow-status').addEventListener('change',()=>{$('workflow-save-state').textContent = '';});
  $('lead-follow-up-date').addEventListener('change',()=>{$('workflow-save-state').textContent = '';});
  $('save-lead-workflow').addEventListener('click',saveLeadWorkflow);
  $('find-button').addEventListener('click',openSearch);
  $('empty-find-button').addEventListener('click',openSearch);
  $('search-again').addEventListener('click',openSearch);
  document.querySelectorAll('[data-close]').forEach(button => button.addEventListener('click',() => $(button.dataset.close).close()));
  $('find-form').addEventListener('submit',async event => {
    event.preventDefault();
    const niche = $('niche').value.trim(), area = $('area').value.trim();
    if (!niche || !area || state.deleting || searchPending || running(state.search) || websitesRunning()) return;
    const starting = {kind:'leads',status:'starting',started_at:Date.now()/1000,message:`Starting the search for ${niche} in ${area}…`};
    searchPending = true; state.search = starting;
    savePreferences(); renderSearch(starting); $('search-form-error').hidden = true;
    try {
      const result = await api('/generate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({niche,area,max_results:Number($('max-results').value)})});
      const job = {...starting,job_id:result.job_id,status:'queued',message:`Searching for ${niche} in ${area}…`};
      state.search = job; savePreferences(); $('find-dialog').close(); renderSearch(job); watchSearch(job);
    } catch (error) {
      await readSession(false).catch(() => {});
      if (state.search?.job_id && running(state.search)) {
        $('find-dialog').close(); renderSearch(state.search);
      } else {
        state.search = {...starting,status:'error',message:error.message};
        savePreferences(); renderSearch(state.search);
        $('search-form-error').textContent = error.message; $('search-form-error').hidden = false;
      }
    } finally {
      searchPending = false; renderWorkControls(); renderSelection();
    }
  });
  document.querySelectorAll('[data-priority]').forEach(button => button.addEventListener('click',()=>{state.priority = button.dataset.priority;renderList();}));
  $('lead-search').addEventListener('input',renderList);
  document.querySelectorAll('[data-followup-filter]').forEach(button => button.addEventListener('click',()=>{
    state.followup = button.dataset.followupFilter;
    renderList();
  }));
  $('workflow-filter').addEventListener('change',()=>{state.workflow = $('workflow-filter').value;renderList();});
  $('website-filter').addEventListener('change',()=>{state.website = $('website-filter').value;renderList();});
  $('lead-sort').addEventListener('change',()=>{state.sort = sortModes.includes($('lead-sort').value) ? $('lead-sort').value : 'priority';savePreferences();renderList();});
  $('delete-business-button').addEventListener('click',()=>openDeleteScope());
  document.querySelectorAll('[data-clear-priority]').forEach(button => button.addEventListener('click',()=>openDeleteScope(button.dataset.clearPriority)));
  $('clear-list-button').addEventListener('click',()=>{
    if ($('clear-list-button').disabled) return;
    const panel = $('clear-menu-panel');
    panel.hidden = !panel.hidden;
    $('clear-list-button').setAttribute('aria-expanded',String(!panel.hidden));
  });
  document.addEventListener('click',event=>{
    if (!$('clear-menu').contains(event.target)) {
      $('clear-menu-panel').hidden = true;
      $('clear-list-button').setAttribute('aria-expanded','false');
    }
  });
  $('confirm-delete').addEventListener('click',deleteBusinesses);
  $('delete-dialog').addEventListener('cancel',event=>{if(state.deleting)event.preventDefault();});
  $('delete-dialog').addEventListener('close',()=>{pendingDelete = null;});
  $('dismiss-workspace-status').addEventListener('click',()=>{$('workspace-status').hidden = true;});
  async function refresh() { try { await readSession(false); } catch { /* loadLeads supplies the visible connection error. */ } await loadLeads(); }
  $('refresh-button').addEventListener('click',refresh); $('retry-workspace').addEventListener('click',refresh);
  $('export-button').addEventListener('click',()=>{location.href = '/export';});
  $('build-button').addEventListener('click',()=>beginBuild(false)); $('redesign-button').addEventListener('click',()=>beginBuild(true));
  $('rebuild-button').addEventListener('click',()=>{const lead = selectedLead();if(!lead)return;rebuildKey = state.selected;$('rebuild-name').textContent = lead.name;$('more-actions').open = false;$('rebuild-dialog').showModal();});
  $('confirm-rebuild').addEventListener('click',()=>{$('rebuild-dialog').close();if (rebuildKey === state.selected) beginBuild(false);});
  $('download-button').addEventListener('click',()=>{const lead = selectedLead();if (lead?.download_url && !running(state.jobs.get(state.selected))) location.href = lead.download_url;});
  $('retry-preview').addEventListener('click',()=>{const lead = selectedLead();if(lead)loadPreview(lead);});
  $('preview-retry-button').addEventListener('click',()=>{const lead = selectedLead();if(lead)loadPreview(lead);});
  $('open-preview').addEventListener('click',event=>{if($('open-preview').getAttribute('aria-disabled') === 'true')event.preventDefault();});
  document.querySelectorAll('[data-device]').forEach(button=>button.addEventListener('click',()=>{state.device = button.dataset.device;savePreferences();renderSelection();fitPreview();}));
  $('back-to-businesses').addEventListener('click',()=>{
    const previous = state.selected;
    state.selected = null; savePreferences(); renderList(); renderSelection();
    $('business-panel').scrollIntoView({block:'start'});
    [...$('business-list').children].find(row=>row.dataset.key === previous)?.focus({preventScroll:true});
  });
  new ResizeObserver(fitPreview).observe($('preview-canvas'));
  addEventListener('pointerdown',()=>document.body.dataset.input = 'pointer',{capture:true,passive:true});
  addEventListener('keydown',()=>document.body.dataset.input = 'keyboard',true);
  setInterval(()=>{
    if (state.search) { const seconds = Math.max(0,Math.floor(Date.now()/1000 - (state.search.started_at || Date.now()/1000))); if (running(state.search)) $('search-elapsed').textContent = seconds < 60 ? `${seconds}s` : `${Math.floor(seconds/60)}m ${seconds%60}s`; }
  },1000);
  (async()=>{
    try { await readSession(true); } catch { setConnection(false); }
    await loadLeads();
  })();
})();
