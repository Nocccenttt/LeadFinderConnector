'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const running = job => job && ['starting', 'queued', 'running'].includes(job.status);
  const keyOf = lead => `${lead.priority}::${encodeURIComponent(lead.client_id)}`;
  const sortModes = ['priority','score-desc','score-asc','name-asc','name-desc'];
  const state = {leads:[], selected:null, priority:'ALL', website:'ALL', workflow:'ALL', followup:'ALL', sort:'priority', jobs:new Map(), socialJobs:new Map(), search:null,
    workspace:'', workspaceToken:'', capabilities:{}, device:innerWidth < 800 ? 'mobile' : 'desktop', connected:false, deleting:false, loadingLeads:false};
  let leadLoadEpoch = 0, pendingDelete = null;
  const watching = new Set();
  const preview = {key:null, url:null, status:'empty', token:0, controller:null, timeout:null};
  let rebuildKey = null;
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  const providers = ['deepseek','google','pexels'];
  let settingsToken = '', settingsEpoch = 0, settingsSaving = false, searchPending = false;
  // Progress is owned by this script so a previously served page can load it too.
  const buildStage = document.createElement('p');
  buildStage.id = 'build-stage'; buildStage.className = 'build-message'; buildStage.hidden = true;
  $('build-message').after(buildStage);
  const workflowDrafts = new Map();
  const websiteRequests = new Map();
  let reviewTarget = null;
  let workflowSaveEpoch = 0;
  function websiteFacts(lead) {
    const facts = lead.website_status || {available:Boolean(lead.demo_ready),state:lead.demo_ready ? 'draft' : 'missing',label:lead.demo_ready ? 'Draft — QA not verified' : 'Not built',qa:{status:'NOT RUN'},qa_passed:false,approved:false};
    const job = state.jobs.get(keyOf(lead)), pending = websiteRequests.get(keyOf(lead));
    if (running(job) || pending?.action === 'validate') return {...facts,state:'building',label:pending?.action === 'validate' ? 'Checking QA' : 'Building website',qa_passed:false,approved:false,can_download_draft:false,can_review:false};
    return facts;
  }
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
  function sameWorkflow(a, b) {
    return Boolean(a && b) && a.status === b.status && a.notes === b.notes && a.follow_up_date === b.follow_up_date;
  }
  function newWorkflowDraft(values, baseline = null) {
    return {values,baseline,saving:false,submitted:null,requiresSave:false,error:'',saved:false,savedEpoch:0};
  }
  function workflowDirty(draft) {
    return draft.requiresSave || !sameWorkflow(draft.values,draft.baseline);
  }
  function workflowDraftFor(lead) {
    const key = keyOf(lead);
    if (!workflowDrafts.has(key)) {
      const saved = workflowOf(lead);
      workflowDrafts.set(key,newWorkflowDraft({...saved},saved));
    }
    return workflowDrafts.get(key);
  }
  function persistWorkflowDrafts() {
    if (!state.workspace) return;
    const drafts = [...workflowDrafts].filter(([,draft]) => draft.saving || draft.error || workflowDirty(draft))
      .map(([key,draft]) => [key,draft.values,draft.requiresSave]);
    try { sessionStorage.setItem(`leadfinder:${state.workspace}:workflow-drafts`,JSON.stringify(drafts)); }
    catch { /* Drafts remain available in this tab when browser storage is unavailable. */ }
  }
  function restoreWorkflowDrafts(keepCurrent = false) {
    if (!keepCurrent) workflowDrafts.clear();
    try {
      const drafts = JSON.parse(sessionStorage.getItem(`leadfinder:${state.workspace}:workflow-drafts`) || '[]');
      if (!Array.isArray(drafts)) return;
      for (const entry of drafts) {
        if (!Array.isArray(entry) || entry.length < 2) continue;
        const [key,values] = entry;
        if (typeof key !== 'string' || !values || !Object.hasOwn(workflowLabels,values.status) ||
            typeof values.notes !== 'string' || values.notes.length > 5000 || typeof values.follow_up_date !== 'string') continue;
        if (!workflowDrafts.has(key)) {
          const draft = newWorkflowDraft({status:values.status,notes:values.notes,follow_up_date:values.follow_up_date});
          draft.requiresSave = entry[2] === true;
          workflowDrafts.set(key,draft);
        }
      }
    } catch { /* Browser storage is optional. */ }
  }
  function reconcileWorkflowDrafts(leads, saveEpoch) {
    for (const lead of leads) {
      const draft = workflowDrafts.get(keyOf(lead));
      if (!draft) continue;
      // A list requested before a save must not replace that save's newer result.
      if (draft.savedEpoch > saveEpoch) lead.workflow = {...draft.baseline};
      if (draft.saving) continue;
      const saved = workflowOf(lead), dirty = workflowDirty(draft);
      if (!dirty) draft.values = {...saved};
      draft.baseline = saved;
      if (dirty && !draft.requiresSave && sameWorkflow(draft.values,saved)) { draft.saved = true; draft.error = ''; }
    }
    persistWorkflowDrafts();
  }
  function renderWorkflowState(lead = selectedLead()) {
    if (!lead) return;
    const draft = workflowDraftFor(lead), dirty = workflowDirty(draft);
    const status = $('workflow-save-state'), button = $('save-lead-workflow');
    status.textContent = draft.saving ? 'Saving…' : draft.error ? `${draft.error} Your changes are unsaved.` : dirty ? 'Unsaved changes' : draft.saved ? 'Saved' : '';
    status.dataset.state = draft.saving ? 'saving' : draft.error ? 'error' : dirty ? 'dirty' : draft.saved ? 'saved' : '';
    button.textContent = draft.saving ? 'Saving…' : draft.error ? 'Retry save' : 'Save follow-up';
    button.disabled = draft.saving || state.deleting || !state.connected || !state.workspaceToken;
    $('lead-notes-count').textContent = draft.values.notes.length + ' / 5000';
  }
  function updateWorkflowDraft() {
    const lead = selectedLead();
    if (!lead) return;
    const draft = workflowDraftFor(lead);
    draft.values = {status:$('lead-workflow-status').value,follow_up_date:$('lead-follow-up-date').value,notes:$('lead-notes').value};
    // A reload may happen before the older submitted values reach the server.
    if (draft.saving && !sameWorkflow(draft.values,draft.submitted)) draft.requiresSave = true;
    draft.error = ''; draft.saved = false;
    persistWorkflowDrafts(); renderWorkflowState(lead);
  }
  function renderWorkflow(lead) {
    const workflow = workflowDraftFor(lead).values;
    for (const [id,value] of [['lead-workflow-status',workflow.status],['lead-follow-up-date',workflow.follow_up_date],['lead-notes',workflow.notes]]) {
      if ($(id).value !== value) $(id).value = value;
    }
    renderWorkflowState(lead);
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
      jobs:[...state.jobs.values()].filter(running), socialJobs:[...state.socialJobs.values()].filter(running), search:running(state.search) ? state.search : null});
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
  function websiteActionsRunning() { return [...websiteRequests.values()].some(item=>item.action); }
  function socialsRunning() { return [...state.socialJobs.values()].some(running); }
  function renderWorkControls() {
    const searching = searchPending || running(state.search), building = websitesRunning() || websiteActionsRunning(), scanning = socialsRunning();
    $('find-button').disabled = searching || building || scanning;
    $('search-submit').disabled = searching || building || scanning;
    $('find-button').title = building ? 'Finish website builds before starting a business search.' : scanning ? 'Finish social scans before starting a business search.' : searching ? 'A business search is already running.' : '';
    $('search-submit').title = $('find-button').title;
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
    if (leads.some(lead => workflowDrafts.get(keyOf(lead))?.saving)) return 'Wait for the selected follow-up saves to finish before deleting these businesses.';
    if (leads.some(lead => websiteRequests.get(keyOf(lead))?.action)) return 'Wait for website checks, review saves, or downloads to finish before deleting.';
    if (leads.some(lead => running(state.socialJobs.get(keyOf(lead))))) return 'Wait for the selected social scans to finish before deleting these businesses.';
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
    renderWorkflowState();
    renderSocials();
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
      for (const key of removed) { state.jobs.delete(key); state.socialJobs.delete(key); workflowDrafts.delete(key); websiteRequests.delete(key); }
      persistWorkflowDrafts();
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
      const facts = websiteFacts(lead), status = facts.state;
      const workflowStatus = workflowOf(lead).status;
      const followup = followupInfo(lead);
      const followupMatch = state.followup === 'ALL' || (state.followup === 'NEEDS' ? followup.kind !== 'NONE' : followup.kind === state.followup);
      return (!query || searchable.includes(query)) && (state.priority === 'ALL' || lead.priority === state.priority) &&
        (state.workflow === 'ALL' || state.workflow === workflowStatus) && followupMatch &&
        (state.website === 'ALL' || state.website === status || state.website === 'qa_passed' && facts.qa_passed || state.website === 'missing' && status === 'incomplete');
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
    const activeFilters = [state.priority !== 'ALL',state.website !== 'ALL',state.workflow !== 'ALL',state.followup !== 'ALL',Boolean($('lead-search').value.trim())].filter(Boolean).length;
    $('filter-count').textContent = String(activeFilters); $('filter-count').hidden = !activeFilters;
    $('visible-count').textContent = `${filtered.length} ${filtered.length === 1 ? 'business' : 'businesses'}`;
    $('saved-count').textContent = `${state.leads.length} saved · ${state.leads.filter(lead => websiteFacts(lead).qa_passed).length} QA passed · ${state.leads.filter(lead => websiteFacts(lead).approved).length} reviewed`;
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
        clearListFilters();
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
      const facts = websiteFacts(lead), label = facts.label;
      bottom.append(node('span',`priority-label ${lead.priority.toLowerCase()}`,lead.priority[0] + lead.priority.slice(1).toLowerCase()), workflowChip(lead));
      const dueBadge = followupBadge(lead);
      if (dueBadge) bottom.append(dueBadge);
      bottom.append(node('span',`row-website-status ${facts.state === 'building' ? 'working' : facts.approved ? 'ready' : facts.state}`,label));
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
    const epoch = ++leadLoadEpoch, saveEpoch = workflowSaveEpoch;
    state.loadingLeads = true; renderDeletionControls();
    $('refresh-button').disabled = true;
    try {
      const data = await api('/leads');
      if (epoch !== leadLoadEpoch) return false;
      if (!Array.isArray(data.leads)) throw new Error('The business list could not be read. Try refreshing.');
      reconcileWorkflowDrafts(data.leads,saveEpoch);
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
  function renderQuality(lead) {
    const facts = websiteFacts(lead), qa = facts.qa || {}, busy = facts.state === 'building';
    const failed = facts.state === 'needs_attention', total = Number(qa.checks_total || 0), passed = Number(qa.checks_passed || 0);
    $('qa-card').classList.toggle('ready',facts.qa_passed);
    $('qa-card').classList.toggle('attention',failed);
    $('qa-title').textContent = busy ? 'Check pending' : facts.qa_passed ? 'Passed for current files' : failed ? 'Needs attention' : facts.available ? 'Not verified for current files' : 'Not checked yet';
    $('qa-badge').className = `qa-badge ${facts.qa_passed ? 'ready' : failed ? 'attention' : ''}`;
    $('qa-badge').textContent = busy ? 'Pending' : facts.qa_passed ? 'Passed' : failed ? 'Review' : 'Pending';
    $('qa-summary').textContent = busy ? 'Checks must finish before delivery review.' : facts.message || 'Build a website to run QA.';
    if (!busy && total) $('qa-summary').textContent += ` Saved report: ${passed} of ${total} checks passed${['STALE','UNVERIFIED'].includes(qa.status) ? '; not verified for the current files' : ''}.`;
    const issues = Array.isArray(qa.issues) ? qa.issues.filter(Boolean).slice(0,5) : [];
    const box = $('qa-issues'); box.replaceChildren(); box.hidden = !issues.length;
    if (issues.length) {
      const list = node('ul','qa-issues-list');
      for (const issue of issues) list.append(node('li','',issue));
      box.append(node('span','qa-issues-label','Check these items'),list);
    }
    const validating = busy && ['validation','packaging'].includes(state.jobs.get(keyOf(lead))?.phase);
    const steps = {build:validating || facts.available && !busy,qa:facts.qa_passed,ready:facts.approved};
    for (const [name,complete] of Object.entries(steps)) {
      const element = $(`step-${name}`);
      element.classList.toggle('complete',Boolean(complete));
      element.classList.toggle('active',name === 'build' ? busy && !validating : name === 'qa' ? validating || !busy && facts.available && !facts.qa_passed : facts.qa_passed && !facts.approved);
    }
  }

  const socialLabels = {facebook:'Facebook',instagram:'Instagram',linkedin:'LinkedIn',youtube:'YouTube',tiktok:'TikTok',x:'X',pinterest:'Pinterest',threads:'Threads',bluesky:'Bluesky'};
  function safeSocialLink(profile) {
    try {
      const url = new URL(profile.url);
      const hosts = {facebook:['facebook.com'],instagram:['instagram.com'],linkedin:['linkedin.com'],youtube:['youtube.com'],tiktok:['tiktok.com'],x:['x.com','twitter.com'],pinterest:['pinterest.com'],threads:['threads.net','threads.com'],bluesky:['bsky.app']};
      const host = url.hostname.toLowerCase().replace(/^(www|m|mobile|mbasic)\./,'');
      return url.protocol === 'https:' && !url.username && !url.password && (hosts[profile.platform] || []).includes(host) ? url.href : '';
    } catch { return ''; }
  }
  function renderSocials(lead = selectedLead()) {
    if (!lead) return;
    const key = keyOf(lead), job = state.socialJobs.get(key), busy = running(job);
    const button = $('scan-socials'), status = $('social-scan-state'), container = $('social-profiles');
    button.disabled = busy || Boolean(websiteRequests.get(key)?.action) || running(state.jobs.get(key)) || searchPending || running(state.search) || state.deleting || !state.connected || !state.workspaceToken;
    button.textContent = busy ? 'Scanning…' : 'Scan socials';
    const profiles = (Array.isArray(lead.social_profiles) ? lead.social_profiles : []).filter(profile => profile && safeSocialLink(profile));
    const checked = lead.social_scan?.checked_at;
    status.textContent = job?.message || lead.social_scan?.note || (profiles.length ? 'Linked profiles found. Scan to check their public bios and contact details.' : 'Scan the business website and saved profiles for public social information.');
    if (!busy && checked) status.textContent += ` Last checked ${new Date(checked).toLocaleString()}.`;
    status.classList.toggle('error',job?.status === 'error');
    $('social-summary').textContent = busy ? 'Scanning…' : job?.status === 'error' ? 'Needs attention' : profiles.length ? `${profiles.length} linked` : checked ? 'Scanned' : 'Not scanned';
    $('social-results').hidden = !profiles.length;
    $('social-results-label').textContent = `View ${profiles.length} social ${profiles.length === 1 ? 'profile' : 'profiles'}`;
    const signature = JSON.stringify(profiles);
    if (container.dataset.key === key && container.dataset.signature === signature) return;
    if (container.dataset.key !== key) $('social-results').open = false;
    container.dataset.key = key; container.dataset.signature = signature; container.replaceChildren();
    for (const profile of profiles) {
      const card = node('details','social-profile'), summary = node('summary');
      const profileURL = new URL(safeSocialLink(profile));
      const handle = profileURL.searchParams.get('id') || profileURL.pathname.split('/').filter(Boolean).pop();
      const link = node('a','',`${socialLabels[profile.platform]} · ${handle} ↗`);
      link.href = safeSocialLink(profile); link.target = '_blank'; link.rel = 'noopener noreferrer';
      const labels = {public:'Public details found',blocked:'Access limited',unavailable:'Unavailable',not_checked:'Not checked'};
      summary.append(link,node('span','social-profile-status',labels[profile.status] || 'Linked profile'));
      const body = node('div','social-profile-body'), details = profile.details && typeof profile.details === 'object' ? profile.details : {};
      if (details.name) body.append(node('strong','',String(details.name)));
      if (details.description) body.append(node('p','',String(details.description)));
      if (details.address) body.append(node('p','',String(details.address)));
      for (const email of Array.isArray(details.emails) ? details.emails : []) {
        if (typeof email !== 'string' || !/^[\w.%+\-]+@[\w.\-]+\.[A-Za-z]{2,}$/.test(email)) continue;
        const contact = node('a','',email); contact.href = `mailto:${email}`; body.append(contact);
      }
      for (const phone of Array.isArray(details.phones) ? details.phones : []) {
        const contact = node('a','',String(phone)); contact.href = `tel:${String(phone).replace(/[^+\d]/g,'')}`; body.append(contact);
      }
      if (profile.note) body.append(node('p','',String(profile.note)));
      if (profile.source_url) {
        try {
          const url = new URL(profile.source_url);
          if (['https:','http:'].includes(url.protocol) && !url.username && !url.password) {
            const source = node('a','','Discovery source ↗'); source.href = url.href; source.target = '_blank'; source.rel = 'noopener noreferrer'; body.append(source);
          }
        } catch { /* Invalid saved source URLs have no navigation. */ }
      }
      if (profile.observed_at) body.append(node('span','',`Public details observed ${new Date(profile.observed_at).toLocaleString()}.`));
      card.append(summary,body); container.append(card);
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
    $('reason-shortcut').hidden = !reason;
    $('selected-priority').className = `priority-label ${lead.priority.toLowerCase()}`;
    $('selected-priority').textContent = lead.priority[0] + lead.priority.slice(1).toLowerCase() + ' priority';
    $('selected-score').textContent = lead.score ? `Opportunity score ${lead.score}` : '';
    const contacts = $('contact-links'); contacts.replaceChildren();
    if (lead.phone) { const link = node('a','',lead.phone); link.href = `tel:${String(lead.phone).replace(/[^+\d]/g,'')}`; contacts.append(link); }
    if (typeof lead.email === 'string' && /^[\w.%+\-]+@[\w.\-]+\.[A-Za-z]{2,}$/.test(lead.email)) { const link = node('a','',lead.email); link.href = `mailto:${lead.email}`; contacts.append(link); }
    if (lead.website) {
      try { const url = new URL(lead.website); if (['http:','https:'].includes(url.protocol)) { const link = node('a','','Original website ↗'); link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer'; contacts.append(link); } } catch { /* A missing/invalid source URL has no link. */ }
    }
    const facts = websiteFacts(lead), ready = facts.available, scanning = running(state.socialJobs.get(state.selected));
    const pending = websiteRequests.get(state.selected), locked = busy || Boolean(pending?.action);
    $('website-state').className = `state-label ${facts.state === 'building' ? 'working' : facts.approved ? 'ready' : facts.state}`;
    $('website-state').textContent = facts.label;
    const configured = state.capabilities.website_configured !== false;
    $('build-message').textContent = busy ? job.message || 'Building the website. QA and delivery review are pending.' :
      pending?.action === 'validate' ? 'Checking the current files locally. No generation credits are used.' :
      searching ? 'Wait for the business search to finish before building or redesigning a website.' :
      scanning ? 'Wait for this social scan to finish before building or redesigning.' :
      !ready && !configured ? 'Website generation is not configured in this workspace.' :
      !ready && !lead.can_generate ? 'Website builds are available for high- and medium-priority businesses with a saved handoff.' : facts.message;
    $('build-button').hidden = ready; $('build-button').disabled = locked || searching || scanning || !lead.can_generate || !configured;
    $('build-button').textContent = busy ? 'Building…' : 'Build website';
    $('build-stage').hidden = !job?.started_at;
    renderBuildElapsed();
    $('redesign-button').hidden = !ready || !lead.can_generate; $('redesign-button').disabled = locked || searching || scanning || !configured;
    $('check-website').hidden = !ready || facts.qa_passed || busy;
    $('check-website').disabled = locked || searching || scanning || !state.connected || !state.workspaceToken;
    $('check-website').textContent = pending?.action === 'validate' ? 'Checking QA…' : 'Recheck QA';
    $('review-website').hidden = !facts.can_review;
    $('review-website').disabled = locked || searching || scanning || !state.connected || !state.workspaceToken;
    $('review-website').textContent = facts.approved ? 'Revoke review' : 'Review for delivery';
    $('review-website').className = facts.approved ? 'button quiet' : 'button primary';
    $('download-button').hidden = !ready;
    $('download-button').disabled = locked || !facts.can_download_draft;
    $('download-button').textContent = pending?.action === 'download' ? 'Preparing ZIP…' : facts.approved ? 'Download reviewed ZIP' : 'Download draft ZIP';
    $('download-button').className = facts.approved ? 'button primary' : 'button';
    $('more-actions').hidden = !ready || !lead.can_generate || locked;
    $('rebuild-button').disabled = searching || scanning || !configured;
    $('website-action-error').hidden = !pending?.error; $('website-action-error').textContent = pending?.error || '';
    $('job-error').hidden = job?.status !== 'error'; $('job-error').textContent = job?.status === 'error' ? `${job.message} ${/api.key|401|authentication/i.test(job.message || '') ? 'Change or test the API key, then retry the build.' : /validat|quality/i.test(job.message || '') ? 'Open Quality checks, then recheck QA or rebuild after correcting the reported issues.' : 'Check your connection and retry with Build website or Redesign. Any available files remain a draft.'}` : '';
    $('job-settings-button').hidden = job?.status !== 'error' || !/api.key|401|authentication/i.test(job.message || '');
    $('open-preview').setAttribute('aria-disabled',String(!ready || busy));
    if (ready) $('open-preview').href = lead.demo_url; else $('open-preview').removeAttribute('href');
    $('retry-preview').disabled = !ready || busy;
    renderWorkflow(lead);
    renderSocials(lead);
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
      applyWebsiteInfo(lead,info); renderList(); renderSelection();
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
    if (!lead || state.deleting || !state.connected || !state.workspaceToken) return;
    const key = keyOf(lead), workspace = state.workspace, draft = workflowDraftFor(lead);
    if (draft.saving) return;
    const submitted = {...draft.values}, payload = {priority:lead.priority,name:lead.client_id,...submitted};
    const current = () => state.workspace === workspace && workflowDrafts.get(key) === draft;
    draft.saving = true; draft.submitted = submitted; draft.error = ''; draft.saved = false;
    persistWorkflowDrafts();
    renderWorkflowState(lead); renderDeletionControls();
    try {
      const result = await api('/lead-workflow',{method:'POST',headers:{'Content-Type':'application/json','X-Workspace-Token':state.workspaceToken},body:JSON.stringify(payload)});
      if (!current()) return;
      const saved = workflowOf({workflow:result.workflow});
      draft.baseline = saved; draft.savedEpoch = ++workflowSaveEpoch;
      draft.requiresSave = false;
      if (sameWorkflow(draft.values,submitted)) draft.values = {...saved};
      draft.saved = sameWorkflow(draft.values,saved);
      const latest = state.leads.find(item => keyOf(item) === key);
      if (latest) latest.workflow = saved;
      renderList();
    } catch (error) {
      if (!current()) return;
      draft.error = error.message;
      if (error.status === 403) await readSession(false).catch(() => setConnection(false));
      if (error.status === 403 || error.status === 404) await loadLeads();
    } finally {
      if (current()) {
        draft.saving = false; draft.submitted = null; persistWorkflowDrafts();
        if (state.selected === key) renderWorkflow(state.leads.find(item => keyOf(item) === key) || lead);
        renderDeletionControls();
      }
    }
  }

  function applyWebsiteInfo(lead,info) {
    lead.website_status = info; lead.preview_state = info.state; lead.qa = info.qa;
    lead.demo_ready = info.available; lead.demo_url = info.preview_url;
    lead.download_url = info.download_url; lead.approved_download_url = info.approved_download_url;
  }
  async function runWebsiteAction(lead,action,review = {}) {
    const key = keyOf(lead);
    if (websiteRequests.get(key)?.action || running(state.jobs.get(key)) || state.deleting) return;
    const pending = {action,error:''}; websiteRequests.set(key,pending);
    renderWorkControls(); renderList(); if (state.selected === key) renderSelection();
    try {
      if (action === 'download') {
        const facts = websiteFacts(lead), kind = facts.approved ? 'reviewed' : 'draft';
        const url = facts.approved ? lead.approved_download_url : lead.download_url;
        const response = await fetch(url,{signal:AbortSignal.timeout(30000)});
        if (!response.ok) {
          const error = await response.json().catch(()=>({}));
          throw new Error(error.error || 'Could not prepare the ZIP. Refresh and try again.');
        }
        const objectURL = URL.createObjectURL(await response.blob()), link = document.createElement('a');
        link.href = objectURL; link.download = `${lead.client_id}-${kind === 'reviewed' ? 'reviewed' : 'DRAFT'}-website.zip`;
        document.body.append(link); link.click(); link.remove(); setTimeout(()=>URL.revokeObjectURL(objectURL),1000);
      } else {
        const result = await api(action === 'validate' ? '/validate-website' : '/delivery-review',{
          method:'POST',headers:{'Content-Type':'application/json','X-Workspace-Token':state.workspaceToken},
          body:JSON.stringify({priority:lead.priority,name:lead.client_id,action,...review})});
        const latest = state.leads.find(item=>keyOf(item) === key);
        if (latest) applyWebsiteInfo(latest,result);
      }
    } catch (error) {
      pending.error = `${error.message} ${action === 'download' ? 'Use the download button to retry; refresh if the website changed.' : action === 'validate' ? 'Use Recheck QA to retry.' : 'Refresh the current website before trying delivery review again.'}`;
      if (error.status === 403) await readSession(false).catch(()=>{});
      await loadLeads();
    } finally {
      pending.action = ''; renderWorkControls(); renderList(); if (state.selected === key) renderSelection();
    }
  }
  $('check-website').addEventListener('click',()=>{ const lead = selectedLead(); if (lead) runWebsiteAction(lead,'validate'); });
  $('review-website').addEventListener('click',()=>{
    const lead = selectedLead(); if (!lead) return;
    const facts = websiteFacts(lead);
    if (facts.approved) return runWebsiteAction(lead,'revoke');
    reviewTarget = {key:keyOf(lead),fingerprint:facts.fingerprint,qa_report_hash:facts.qa_report_hash};
    $('review-name').textContent = lead.name; $('review-dialog').showModal();
  });
  $('confirm-review').addEventListener('click',()=>{
    const target = reviewTarget; $('review-dialog').close();
    const lead = state.leads.find(item=>keyOf(item) === target?.key);
    if (lead) runWebsiteAction(lead,'approve',{fingerprint:target.fingerprint,qa_report_hash:target.qa_report_hash});
  });
  $('review-dialog').addEventListener('close',()=>{ reviewTarget = null; });
  async function beginSocialScan() {
    const lead = selectedLead();
    if (!lead || state.deleting || !state.connected || !state.workspaceToken || searchPending || running(state.search) ||
        websiteRequests.get(state.selected)?.action || running(state.jobs.get(state.selected)) || running(state.socialJobs.get(state.selected))) return;
    const key = keyOf(lead), starting = {kind:'social',key,priority:lead.priority,client_id:lead.client_id,status:'starting',message:'Starting the social scan…'};
    state.socialJobs.set(key,starting); savePreferences(); renderList(); renderSelection();
    try {
      const result = await api('/social-discovery',{method:'POST',headers:{'Content-Type':'application/json','X-Workspace-Token':state.workspaceToken},body:JSON.stringify({priority:lead.priority,name:lead.client_id})});
      const job = {...starting,job_id:result.job_id,status:'queued'};
      state.socialJobs.set(key,job); savePreferences(); watchSocial(job); renderList(); if (state.selected === key) renderSelection();
    } catch (error) {
      await readSession(false).catch(() => {});
      if (!running(state.socialJobs.get(key)) || !state.socialJobs.get(key)?.job_id) state.socialJobs.set(key,{...starting,status:'error',message:error.message});
      savePreferences(); renderList(); if (state.selected === key) renderSelection();
    }
  }
  async function watchSocial(job) {
    if (!job.job_id || watching.has(job.job_id)) return;
    watching.add(job.job_id);
    const current = () => state.socialJobs.get(job.key)?.job_id === job.job_id;
    try {
      while (current() && running(state.socialJobs.get(job.key))) {
        try {
          const update = await api(`/job-status?job_id=${encodeURIComponent(job.job_id)}`);
          if (!current()) break;
          Object.assign(job,update); state.socialJobs.set(job.key,job); setConnection(true); savePreferences(); renderList();
          if (state.selected === job.key) renderSelection();
          if (!running(job)) {
            await loadLeads();
            if (current()) $('announcement').textContent = job.message;
            break;
          }
        } catch (error) {
          if (!current()) break;
          if (error.status === 404) {
            state.socialJobs.set(job.key,{...job,status:'error',message:'This social scan session has ended. Scan again to refresh the public information.'});
            savePreferences(); await loadLeads(); break;
          }
          setConnection(false); job.message = 'Connection interrupted. Reconnecting to the social scan…';
          if (state.selected === job.key) renderSocials();
        }
        await sleep(state.connected ? 1000 : 3000);
      }
    } finally { watching.delete(job.job_id); }
  }
  function openSearch() {
    if (state.deleting) return;
    if (searchPending || running(state.search)) { $('search-progress').scrollIntoView({block:'start'}); return; }
    if (websitesRunning()) { workspaceError('Wait for website builds to finish before starting a business search.'); return; }
    if (socialsRunning()) { workspaceError('Wait for social scans to finish before starting a business search.'); return; }
    $('search-form-error').hidden = true;
    $('find-dialog').showModal();
  }
  async function beginBuild(preserveContent) {
    const lead = selectedLead();
    if (!lead || websiteRequests.get(state.selected)?.action || state.deleting || searchPending || running(state.search) || running(state.jobs.get(state.selected)) || running(state.socialJobs.get(state.selected))) return;
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
    $('workspace-installation').textContent = session.version ? `Version ${session.version} · Saved files: ${session.data_folder || 'this workspace'}` : '';
    const previousWorkspace = state.workspace;
    state.workspace = session.workspace_id; state.capabilities = session.capabilities || {};
    if (state.workspace !== previousWorkspace) {
      restoreWorkflowDrafts(!previousWorkspace);
      persistWorkflowDrafts();
    }
    state.workspaceToken = typeof session.workspace_token === 'string' ? session.workspace_token : '';
    if (restore) {
      const saved = readStorage(`leadfinder:${state.workspace}`,{});
      state.selected = saved.selected || null;
      if (sortModes.includes(saved.sort)) state.sort = saved.sort;
      $('lead-sort').value = state.sort;
      if (['desktop','mobile'].includes(saved.device)) state.device = saved.device;
      for (const job of saved.jobs || []) if (job.key && job.job_id) state.jobs.set(job.key,job);
      for (const job of saved.socialJobs || []) if (job.key && job.job_id) state.socialJobs.set(job.key,job);
      if (saved.search?.job_id) state.search = saved.search;
    }
    for (const active of [...(session.interrupted_jobs || []),...(session.active_jobs || [])]) {
      const previous = active.kind === 'website' ? state.jobs.get(keyOf(active)) : active.kind === 'social' ? state.socialJobs.get(keyOf(active)) : state.search;
      if (active.interrupted && previous && Number(previous.started_at || 0) > Number(active.started_at || 0)) continue;
      if (active.kind === 'website' && active.client_id) {
        const job = {...active,key:keyOf(active)}; state.jobs.set(job.key,job);
      } else if (active.kind === 'social' && active.client_id) {
        const job = {...active,key:keyOf(active)}; state.socialJobs.set(job.key,job);
      } else if (active.kind === 'leads') state.search = active;
    }
    setConnection(true);
    for (const job of state.jobs.values()) if (running(job)) watchWebsite(job);
    for (const job of state.socialJobs.values()) if (running(job)) watchSocial(job);
    if (running(state.search)) { renderSearch(state.search); watchSearch(state.search); }
    else if (state.search?.interrupted) renderSearch(state.search);
    return session;
  }
  function clearListFilters() {
    $('lead-search').value = ''; $('website-filter').value = 'ALL'; $('workflow-filter').value = 'ALL';
    state.website = 'ALL'; state.workflow = 'ALL'; state.followup = 'ALL'; state.priority = 'ALL'; renderList();
  }
  $('clear-list-filters').addEventListener('click',clearListFilters);
  document.querySelectorAll('[data-open-section]').forEach(button => button.addEventListener('click',()=>{
    const section = $(button.dataset.openSection);
    if (!section || section.hidden) return;
    section.open = true;
    section.scrollIntoView({block:'start'});
    section.querySelector('summary').focus({preventScroll:true});
  }));
  $('lead-notes').addEventListener('input',updateWorkflowDraft);
  $('lead-workflow-status').addEventListener('change',updateWorkflowDraft);
  $('lead-follow-up-date').addEventListener('input',updateWorkflowDraft);
  $('save-lead-workflow').addEventListener('click',saveLeadWorkflow);
  $('scan-socials').addEventListener('click',beginSocialScan);
  $('find-button').addEventListener('click',openSearch);
  $('empty-find-button').addEventListener('click',openSearch);
  $('search-again').addEventListener('click',openSearch);
  document.querySelectorAll('[data-close]').forEach(button => button.addEventListener('click',() => $(button.dataset.close).close()));
  $('find-form').addEventListener('submit',async event => {
    event.preventDefault();
    const niche = $('niche').value.trim(), area = $('area').value.trim();
    if (!niche || !area || state.deleting || searchPending || running(state.search) || websitesRunning() || websiteActionsRunning() || socialsRunning()) return;
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
    if (!panel.hidden) panel.querySelector('[role=menuitem]:not(:disabled)')?.focus();
  });
  $('clear-menu').addEventListener('keydown',event=>{
    const panel = $('clear-menu-panel');
    if (panel.hidden) {
      if (['ArrowDown','ArrowUp'].includes(event.key)) { event.preventDefault(); $('clear-list-button').click(); }
      return;
    }
    const items = [...panel.querySelectorAll('[role=menuitem]:not(:disabled)')];
    if (event.key === 'Escape') {
      event.preventDefault(); panel.hidden = true; $('clear-list-button').setAttribute('aria-expanded','false'); $('clear-list-button').focus();
    } else if (['ArrowDown','ArrowUp','Home','End'].includes(event.key)) {
      event.preventDefault();
      const index = items.indexOf(document.activeElement);
      items[event.key === 'Home' ? 0 : event.key === 'End' ? items.length-1 : (index + (event.key === 'ArrowDown' ? 1 : -1) + items.length)%items.length]?.focus();
    } else if (event.key === 'Tab') {
      panel.hidden = true; $('clear-list-button').setAttribute('aria-expanded','false'); $('clear-list-button').focus();
    }
  });
  $('more-actions').addEventListener('keydown',event=>{
    if (event.key === 'Escape' && $('more-actions').open) {
      event.preventDefault(); $('more-actions').open = false; $('more-actions').querySelector('summary').focus();
    }
  });
  $('delete-dialog').addEventListener('close',()=>{
    if ($('clear-menu-panel').hidden && !$('clear-list-button').disabled && !document.activeElement?.closest('#detail-panel')) $('clear-list-button').focus();
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
  $('download-button').addEventListener('click',()=>{const lead = selectedLead();if (lead && websiteFacts(lead).can_download_draft && !running(state.jobs.get(state.selected))) runWebsiteAction(lead,'download');});
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
  function renderBuildElapsed() {
    const job = state.jobs.get(state.selected);
    if (!job?.started_at) return;
    const seconds = Math.max(0,Math.floor((job.finished_at || (running(job) ? Date.now()/1000 : job.started_at)) - job.started_at));
    const labels = {preparing:'Preparing',research:'Research',copy:'Copy',design:'Design',rendering:'Rendering',validation:'Validation',packaging:'Packaging',complete:'Complete'};
    $('build-stage').textContent = `${labels[job.phase] || (running(job) ? 'Starting' : 'Stopped')} · ${Math.floor(seconds/60)}m ${seconds%60}s elapsed${job.status === 'error' ? ' · needs attention' : ''}`;
  }
  setInterval(()=>{
    renderBuildElapsed();
    if (state.search) { const seconds = Math.max(0,Math.floor(Date.now()/1000 - (state.search.started_at || Date.now()/1000))); if (running(state.search)) $('search-elapsed').textContent = seconds < 60 ? `${seconds}s` : `${Math.floor(seconds/60)}m ${seconds%60}s`; }
  },1000);
  (async()=>{
    try { await readSession(true); } catch { setConnection(false); }
    await loadLeads();
  })();
})();
