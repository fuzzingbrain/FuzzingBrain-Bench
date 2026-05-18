// Shared site helpers. Loaded by pages that render bugs.json.

async function loadBugs() {
  const res = await fetch('bugs.json', { cache: 'no-cache' });
  if (!res.ok) throw new Error('Failed to load bugs.json: ' + res.status);
  return await res.json();
}

function badge(status) {
  return `<span class="badge ${status}">${status}</span>`;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
}

function renderTable(bugs, target) {
  const rows = bugs.map(b => `
    <tr data-status="${b.status}" data-class="${b.bug_class}" data-project="${b.project.toLowerCase()}">
      <td class="project">${escapeHtml(b.project)}</td>
      <td class="title">${escapeHtml(b.title)}</td>
      <td class="class"><code>${escapeHtml(b.bug_class)}</code></td>
      <td class="status">${badge(b.status)}</td>
      <td class="report"><a href="${b.report}" target="_blank" rel="noopener">report &rarr;</a></td>
    </tr>
  `).join('');
  target.innerHTML = `
    <table class="bugs">
      <thead>
        <tr>
          <th>Project</th>
          <th>Title</th>
          <th class="class">Class</th>
          <th>Status</th>
          <th>Report</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

function attachFilters(allBugs, countEl) {
  const search = document.getElementById('search');
  const statusSel = document.getElementById('f-status');
  const classSel = document.getElementById('f-class');

  function apply() {
    const q = (search.value || '').trim().toLowerCase();
    const s = statusSel.value;
    const c = classSel.value;
    let shown = 0;
    document.querySelectorAll('table.bugs tbody tr').forEach(tr => {
      const matchS = !s || tr.dataset.status === s;
      const matchC = !c || tr.dataset.class === c;
      const text = (tr.dataset.project + ' ' + tr.querySelector('td.title').textContent).toLowerCase();
      const matchQ = !q || text.includes(q);
      const ok = matchS && matchC && matchQ;
      tr.style.display = ok ? '' : 'none';
      if (ok) shown++;
    });
    countEl.textContent = `Showing ${shown} of ${allBugs.length}`;
  }

  // Populate class filter from data
  const classes = Array.from(new Set(allBugs.map(b => b.bug_class))).sort();
  classes.forEach(c => {
    const opt = document.createElement('option');
    opt.value = c;
    opt.textContent = c;
    classSel.appendChild(opt);
  });

  search.addEventListener('input', apply);
  statusSel.addEventListener('change', apply);
  classSel.addEventListener('change', apply);
  apply();
}
