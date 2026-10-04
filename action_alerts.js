/* All source-derived fields use textContent, never HTML. */
(() => {
  let latest, view = 'live';
  const el = id => document.getElementById(id);
  const text = (tag, value, cls) => {
    const node = document.createElement(tag); node.textContent = value;
    if (cls) node.className = cls;
    return node;
  };
  const date = value => value ? new Date(value).toLocaleString() : 'not available';
  window.renderActionAlerts = bundle => {
    latest = bundle;
    if (!bundle) { el('actionStatus').textContent = 'Action feed not available'; return; }
    const s = bundle.status || {}, c = bundle.coverage || {};
    const phases = {starting:'Loading action history', warming_up:'Warming up', monitoring:'Monitoring new actions', history_incomplete:'Monitoring · history incomplete', feed_error:'Latest action feed unavailable'};
    const stale = !!s.last_success && Date.now() - Date.parse(s.last_success) > 15 * 60 * 1000;
    el('actionStatus').textContent = (stale ? 'Stale action snapshot' : phases[s.phase] || s.phase || 'Waiting') +
      (s.polling ? s.fetching_kind === 'history' ? ` · backfilling ${s.fetching_day || ''} (${s.bootstrap_days_loaded || 0}/${s.bootstrap_days_requested || 14} dates)` : ' · fetching recent actions' : '');
    el('actionStatus').className = 'pill' + (s.phase === 'feed_error' || s.phase === 'history_incomplete' || stale ? ' actionWarning' : '');
    el('actionCoverage').textContent = `Live detector ${bundle.detector || "unknown"} · ${c.rows == null ? 'No evaluated' : c.rows.toLocaleString()} tool turns · ${c.observed_days || 0} observed days · ${c.agents_ready || 0}/${c.agents_observed || 0} agents with 7 prior observed days. U3 sending rules require village history; other rules may fire sooner. ` +
      `Latest action: ${date(c.last_turn)}. Last successful recent-action fetch: ${date(s.last_success)}. ` +
      (s.monitoring_since ? `Monitoring since ${date(s.monitoring_since)}. ` : 'Startup history is being replayed before monitoring begins. ') +
      (s.error || '') + (s.failed_dates?.length ? ' Failed source dates: ' + s.failed_dates.join(', ') + '.' : '') +
      (c.missing_bootstrap_dates?.length ? ' Missing startup source dates: ' + c.missing_bootstrap_dates.join(', ') + '.' : '');
    el('actionNotice').textContent = (bundle.notice || '') + ' Discord: ' + (bundle.notifications?.detection_enabled ? 'silent detections enabled' : 'action detections off') + '; ' + (bundle.notifications?.urgent_enabled ? 'urgent webhook enabled' : 'urgent delivery off') + '.';
    const select = el('actionDataset');
    if (!select.options.length) {
      for (const [id, title] of [['live','Newly observed alerts'],['startup','Startup history replay'], ...(bundle.recorded_replays || []).map(r => [r.id,r.title])]) {
        const option = text('option',title); option.value = id; select.append(option);
      }
      select.onchange = () => { view = select.value; el('actionList').scrollTop = 0; window.renderActionAlerts(latest); };
    }
    let alerts, description;
    if (view === 'live') {
      alerts = bundle.live_alerts || [];
      description = `${bundle.live_alert_count || 0} candidates with event times after monitoring began. Older events discovered at startup are shown separately. Action feed polls every 5 minutes; alerts may be observed after the event.`;
    } else if (view === 'startup') {
      alerts = bundle.startup_replay || [];
      description = `${bundle.startup_replay_count || 0} candidates replayed from collected history before monitoring began. These are not new live alerts; showing the latest 50.`;
    } else {
      const replay = (bundle.recorded_replays || []).find(r => r.id === view);
      alerts = replay?.alerts || [];
      description = (replay?.note || '') + ` Detector ${replay?.summary?.detector || ''}.`;
    }
    el('actionDatasetNote').textContent = description;
    const list = el('actionList'), scroll = list.scrollTop; list.replaceChildren();
    for (const a of [...alerts].reverse()) {
      const card = text('article','', 'actionCard');
      card.append(text('span', a.origin === 'live' ? 'NEWLY OBSERVED · REVIEW CANDIDATE' : 'RECORDED REPLAY · REVIEW CANDIDATE', 'eyebrow'));
      card.append(text('h3', (a.tier ? (a.tier === 'urgent' ? 'URGENT CANDIDATE · ' : 'Detection · ') : '') + (a.label || a.signal)));
      card.append(text('strong', a.domain || a.target || (a.targets || []).join(', ') || 'Target unspecified', 'actionDomain'));
      card.append(text('div', (a.agents || []).map(agent => agent.name).join(', ')));
      let details = `Event: ${date(a.time)}`;
      if (a.first_observed_at && a.origin === 'live') details += ` · First observed: ${date(a.first_observed_at)}`;
      if (a.detail) card.append(text('div', Object.entries(a.detail).map(([k,v]) => k.replaceAll('_',' ') + ': ' + (Array.isArray(v) ? v.join(', ') : v)).join(' · '), 'muted'));
      if (a.turns != null) details += ` · ${a.turns} target-bearing tool turns`;
      if (a.blocked_turns != null) details += ` · ${a.blocked_turns} prior failed tool turns`;
      if (a.first_contact) details += ` · First observed contact: ${date(a.first_contact)}`;
      card.append(text('div', details, 'muted'));
      card.append(text('small', `${a.signal} · ${a.detector}`));
      list.append(card);
    }
    if (!alerts.length) list.append(text('div', view === 'live' ?
      'No new candidates recorded. Check coverage and feed status above; this does not establish that activity is safe.' :
      'No replay candidates available for this dataset.', 'empty'));
    list.scrollTop = scroll;
  };
})();
