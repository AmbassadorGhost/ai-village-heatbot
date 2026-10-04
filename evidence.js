// Public agent text is untrusted data. Always render it with textContent.
const expandedEvidence = new Set();
function evidenceText(tag, text, cls) {
  const node = document.createElement(tag);
  node.textContent = text;
  if (cls) node.className = cls;
  return node;
}
function evidenceCard(source, key, title) {
  const card = document.createElement('details');
  card.style.cssText = 'margin:10px 0;padding:10px;border:1px solid #314252;border-radius:8px';
  card.open = expandedEvidence.has(key);
  card.addEventListener('toggle', () => {
    if (card.open) expandedEvidence.add(key); else expandedEvidence.delete(key);
  });
  card.append(evidenceText('summary', title));
  const meta = `${source.action} · ${new Date(source.time).toLocaleString()}`;
  card.append(evidenceText('p', meta, 'muted'));
  const body = evidenceText('div', source.text ?? source.summary ?? 'No public message text available.');
  body.style.cssText = 'white-space:pre-wrap;overflow-wrap:anywhere;max-height:380px;overflow:auto;margin:10px 0';
  card.append(body);
  if (source.seconds != null) card.append(evidenceText('p', `Pause duration: ${source.seconds} seconds.`, 'muted'));
  if (source.truncated) card.append(evidenceText('p', 'Excerpt truncated at 12,000 characters.', 'muted'));
  card.append(evidenceText('small', `Source event: ${source.key}. URL paths and long tokens are blanked.`));
  return card;
}
// What currently makes up a channel's heat: each logged contribution decays with the
// same half-life as heat, so rank by what is STILL counting, not by recency.
function heatDrivers(info, channel) {
  const dash = (typeof data !== 'undefined' && data && data.dashboard) || {};
  const now = Date.parse(dash.generated_at || '') || Date.now();
  const hl = (dash.half_life_minutes || 42) * 60000;
  const rows = (info?.contributions || []).filter(r => (r.channel || r.c) === channel);
  const scored = rows.map(r => {
    const t = Date.parse((r.t || r.time || '').replace(/Z?$/, 'Z'));
    const remaining = Number(r.added) * Math.pow(0.5, Math.max(0, now - t) / hl);
    return Object.assign({}, r, {remaining});
  });
  const drivers = scored.filter(r => r.remaining >= 0.1).sort((x, y) => y.remaining - x.remaining).slice(0, 5);
  return {drivers, hidden: scored.length - drivers.length};
}
function renderEvidence(agent, channel, info) {
  const section = document.createElement('section');
  section.style.marginTop = '20px';
  section.append(evidenceText('h3', 'Messages behind this signal'));
  section.append(evidenceText('p', 'The events still making up most of this heat, largest first. Each shows what it added and how much of that still counts after decay. Matched by exact event ID; several channels can respond to the same event.', 'muted'));
  const goal = document.createElement('details');
  goal.append(evidenceText('summary', 'Assigned goal at the current snapshot'));
  const goalText = evidenceText('p', info?.goal || 'No assigned goal was available. An off-goal label cannot establish goal drift without that context.');
  goalText.style.whiteSpace = 'pre-wrap';
  goal.append(goalText); section.append(goal);
  const {drivers: contributions} = heatDrivers(info, channel);
  if (!contributions.length) section.append(evidenceText('p', 'No logged event is still contributing to this channel. Any remaining heat comes from older events beyond the stored log.', 'muted'));
  for (const r of contributions) {
    const source = info?.source_events?.[r.key];
    const delta = `+${Number(r.added).toFixed(2)} added, ${r.remaining.toFixed(1)} still counts${r.reason ? ' · ' + r.reason : ''}`;
    if (!source) {
      section.append(evidenceText('p', `${delta} · Source event is outside the fetched window or unavailable.`, 'muted'));
      continue;
    }
    const title = `${delta} · ${source.action === 'AGENT_TALK' ? 'Chat message' : source.action} · ${new Date(source.time).toLocaleTimeString()}`;
    section.append(evidenceCard(source, `${agent}|${channel}|${r.key}`, title));
  }
  section.append(evidenceText('h3', 'Recent chat for context'));
  section.append(evidenceText('p', 'These are nearby messages, not necessarily the events that raised this channel.', 'muted'));
  for (const source of [...(info?.recent_messages || [])].reverse()) {
    section.append(evidenceCard(source, `context|${agent}|${source.key}`, `${new Date(source.time).toLocaleTimeString()} · ${source.text.slice(0,85)}${source.text.length > 85 ? '…' : ''}`));
  }
  if (!info?.recent_messages?.length) section.append(evidenceText('p', 'No public chat observed in the fetched window.', 'muted'));
  document.getElementById('detail').append(section);
}
