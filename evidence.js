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
function renderEvidence(agent, channel, info) {
  const section = document.createElement('section');
  section.style.marginTop = '20px';
  section.append(evidenceText('h3', 'Messages behind this signal'));
  section.append(evidenceText('p', 'Matched by exact event ID. The amount is that event’s contribution, not its remaining heat. Several channels can respond to the same event.', 'muted'));
  const goal = document.createElement('details');
  goal.append(evidenceText('summary', 'Assigned goal at the current snapshot'));
  const goalText = evidenceText('p', info?.goal || 'No assigned goal was available. An off-goal label cannot establish goal drift without that context.');
  goalText.style.whiteSpace = 'pre-wrap';
  goal.append(goalText); section.append(goal);
  const contributions = (info?.contributions || []).filter(r => r.channel === channel).slice(-5).reverse();
  if (!contributions.length) section.append(evidenceText('p', 'No recent matched contributions for this channel.', 'muted'));
  for (const r of contributions) {
    const source = info?.source_events?.[r.key];
    const delta = `${r.added >= 0 ? '+' : ''}${Number(r.added).toFixed(2)} heat`;
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
