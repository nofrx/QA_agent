// Shoe QA Frontend

var currentMode = 'auto'; // 'auto', 'url', 'file'

function showMode(mode) {
  currentMode = mode;
  var urlSection = document.getElementById('url-mode-section');
  var fileSection = document.getElementById('file-mode-section');
  if (urlSection) urlSection.style.display = mode === 'url' ? 'block' : 'none';
  if (fileSection) fileSection.style.display = mode === 'file' ? 'block' : 'none';
  if (mode === 'url') updateSnippet();
}

function updateFileLabel(input) {
  var nameSpan = input.nextElementSibling;
  if (nameSpan && input.files.length > 0) {
    var f = input.files[0];
    nameSpan.textContent = f.name + ' (' + (f.size / 1024 / 1024).toFixed(1) + ' MB)';
    nameSpan.style.color = 'var(--success)';
  }
}

function toggleUrlMode() {
  // Legacy compat — just show URL mode
  showMode('url');
}

function updateSnippet() {
  const sku = document.getElementById('sku-input').value.trim().toUpperCase() || 'YOUR-SKU-HERE';
  const code =
    "fetch('/api/assets?limit=1&where[sku][equals]=" + sku + "').then(r=>r.json()).then(d=>{" +
    "var a=d.docs&&d.docs[0];if(!a)return console.log('Not found');" +
    "var B='https://dj5e08oeu5ym4.cloudfront.net/3e/';" +
    "var cp=a.canonicalAsset||{};" +
    "var rfs=cp.referenceFiles||[];" +
    "var rawScan=(rfs[0]&&rfs[0].name)||'';" +
    "var vs=cp.versions||[],last=null;" +
    "for(var i=vs.length-1;i>=0&&!last;i--){var files=vs[i].files||[];" +
    "for(var j=0;j<files.length;j++){var f=files[j];" +
    "if(f.laterality==='left'&&f.type==='3d'&&f.task&&f.task.three&&f.task.three.method==='covision_scan_touch_up'){" +
    "var its=f.task.three.iterations||[];if(its.length){last=its[its.length-1];break;}}}}" +
    "if(!last)return console.log('No touch-up');" +
    "console.log(JSON.stringify({sku:'" + sku + "'," +
    "raw:B+rawScan,source:B+(last.sourceFilename||''),optimised:B+(last.previewFilename||'')," +
    "autoshadow:B+(last.autoShadowFilename||''),brand:cp.brand||'',color:cp.color||'',silhouette:cp.silhouette||''},null,2))})";
  const pre = document.getElementById('snippet-code');
  if (pre) pre.textContent = code;
}

function copySnippet() {
  const code = document.getElementById('snippet-code').textContent;
  navigator.clipboard.writeText(code).then(() => {
    const btn = event.target;
    btn.textContent = 'Copied!';
    setTimeout(() => btn.textContent = 'Copy', 1500);
  });
}

function parseJsonPaste() {
  const textarea = document.getElementById('json-paste');
  try {
    const data = JSON.parse(textarea.value.trim());
    if (data.sku) document.getElementById('sku-input').value = data.sku;
    if (data.raw) document.getElementById('raw-url').value = data.raw;
    if (data.source) document.getElementById('source-url').value = data.source;
    if (data.optimised) document.getElementById('optimised-url').value = data.optimised;
    if (data.autoshadow) document.getElementById('autoshadow-url').value = data.autoshadow;
    textarea.style.borderColor = '#4ecca3';
    setTimeout(() => textarea.style.borderColor = '', 2000);
  } catch (e) {
    textarea.style.borderColor = '#e94560';
    setTimeout(() => textarea.style.borderColor = '', 2000);
  }
}

function timestamp() {
  return new Date().toLocaleTimeString('en-GB', {hour:'2-digit', minute:'2-digit', second:'2-digit'});
}

function addProgressMsg(feed, msg, isError) {
  const div = document.createElement('div');
  div.className = 'progress-msg' + (isError ? ' error' : '');
  div.innerHTML = '<span class="progress-time">' + timestamp() + '</span> ' + escapeHtml(msg);
  feed.appendChild(div);
  feed.scrollTop = feed.scrollHeight;
}

function humanizeError(msg) {
  // Strip Python tracebacks and technical details
  if (msg.startsWith('Error: ')) msg = msg.substring(7);
  if (msg.includes('API lookup failed:')) {
    const reason = msg.split('API lookup failed:')[1].trim();
    if (reason.includes('No scan found')) return 'SKU not found on dashboard. Try URL mode.';
    if (reason.includes('No dashboard.shopar.ai tab')) return 'Open the ShopAR dashboard in Chrome first.';
    return 'Dashboard API error: ' + reason.split('.')[0];
  }
  if (msg.includes('Failed to download')) return msg.split(':').slice(0, 2).join(':');
  if (msg.includes('Decryption failed')) return 'Downloaded file could not be decrypted — may not be a valid GLB.';
  if (msg.includes('Blender script')) return 'Blender analysis failed — the model may be corrupted or unsupported.';
  return msg.length > 200 ? msg.substring(0, 200) + '...' : msg;
}

function analyzeSku() {
  const input = document.getElementById('sku-input');
  const sku = input.value.trim();
  if (!sku) { input.focus(); return; }

  const btn = document.getElementById('analyze-btn');
  const progressSection = document.getElementById('progress-section');
  const progressFeed = document.getElementById('progress-feed');
  const progressHeader = document.getElementById('progress-header');
  const resultSection = document.getElementById('result-section');
  const errorCard = document.getElementById('error-card');

  btn.disabled = true;
  progressFeed.innerHTML = '';
  resultSection.classList.remove('active');
  errorCard.classList.remove('active');
  progressSection.classList.add('active');
  progressHeader.innerHTML = '<div class="spinner"></div><span>Analyzing ' + escapeHtml(sku.toUpperCase()) + '...</span>';

  let fetchPromise;
  if (currentMode === 'url') {
    const rawUrl = document.getElementById('raw-url').value.trim();
    const sourceUrl = document.getElementById('source-url').value.trim();
    const optimisedUrl = document.getElementById('optimised-url').value.trim();
    const autoshadowUrl = document.getElementById('autoshadow-url').value.trim();

    if (!rawUrl) {
      btn.disabled = false;
      progressSection.classList.remove('active');
      errorCard.querySelector('p').textContent = 'Please provide the raw scan GLB URL.';
      errorCard.classList.add('active');
      return;
    }

    fetchPromise = fetch('/api/analyze-urls', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        sku,
        raw_url: rawUrl,
        source_url: sourceUrl,
        optimised_url: optimisedUrl,
        autoshadow_url: autoshadowUrl
      })
    });
  } else if (currentMode === 'file') {
    const rawFile = document.getElementById('raw-file').files[0];
    const sourceFile = document.getElementById('source-file').files[0];
    const optimisedFile = document.getElementById('optimised-file').files[0];
    const autoshadowFile = document.getElementById('autoshadow-file').files[0];

    if (!rawFile) {
      btn.disabled = false;
      progressSection.classList.remove('active');
      errorCard.querySelector('p').textContent = 'Please select the raw scan GLB file.';
      errorCard.classList.add('active');
      return;
    }

    const formData = new FormData();
    formData.append('sku', sku);
    formData.append('raw_file', rawFile);
    if (sourceFile) formData.append('source_file', sourceFile);
    if (optimisedFile) formData.append('optimised_file', optimisedFile);
    if (autoshadowFile) formData.append('autoshadow_file', autoshadowFile);

    fetchPromise = fetch('/api/analyze-files', { method: 'POST', body: formData });
  } else {
    fetchPromise = fetch('/api/analyze/' + encodeURIComponent(sku), { method: 'POST' });
  }

  fetchPromise
    .then(res => {
      if (!res.ok) return res.json().then(d => { throw new Error(d.detail || 'Failed to start'); });
      const evtSource = new EventSource('/api/status/' + encodeURIComponent(sku.toUpperCase()));

      evtSource.onmessage = function(event) {
        const data = JSON.parse(event.data);
        if (data.type === 'progress') {
          addProgressMsg(progressFeed, data.message, false);
        } else if (data.type === 'complete') {
          evtSource.close();
          btn.disabled = false;
          progressHeader.innerHTML = '<span style="color:var(--success)">Analysis complete</span>';
          const reportUrl = '/api/reports/' + encodeURIComponent(data.sku) + '/' + encodeURIComponent(data.session) + '/report.html';
          resultSection.innerHTML =
            '<div class="result-card">' +
            '<h3>Report Ready</h3>' +
            '<p>QA analysis for <strong>' + escapeHtml(data.sku) + '</strong> is complete.</p>' +
            '<a href="' + reportUrl + '" target="_blank">View Report</a>' +
            '</div>';
          resultSection.classList.add('active');
        } else if (data.type === 'error') {
          evtSource.close();
          btn.disabled = false;
          progressHeader.innerHTML = '<span style="color:var(--danger)">Analysis failed</span>';
          addProgressMsg(progressFeed, data.message, true);
          var errMsg = humanizeError(data.message);
          errorCard.querySelector('p').textContent = errMsg;
          errorCard.classList.add('active');
          // Show URL/file mode as fallback if auto-lookup failed
          if (errMsg.indexOf('not found') >= 0 || errMsg.indexOf('URL mode') >= 0 || errMsg.indexOf('dashboard') >= 0) {
            showMode('url');
          }
        }
      };

      evtSource.onerror = function() {
        evtSource.close();
        btn.disabled = false;
        progressHeader.innerHTML = '<span>Connection lost</span>';
        errorCard.querySelector('p').textContent = 'Lost connection to server.';
        errorCard.classList.add('active');
      };
    })
    .catch(err => {
      btn.disabled = false;
      progressSection.classList.remove('active');
      errorCard.querySelector('p').textContent = humanizeError(err.message);
      errorCard.classList.add('active');
    });
}

function loadReports() {
  const container = document.getElementById('reports-container');
  container.innerHTML = '<div class="empty-state"><div class="spinner" style="margin:0 auto 12px;width:24px;height:24px;"></div><p>Loading reports...</p></div>';

  fetch('/api/reports')
    .then(res => res.json())
    .then(reports => {
      if (!reports || reports.length === 0) {
        container.innerHTML = '<div class="empty-state"><p>No reports yet</p><small>Run an analysis from the main page to generate your first report.</small></div>';
        return;
      }

      // Filter out incomplete/stuck sessions
      const valid = reports.filter(r => r.status === 'complete' && r.has_report);

      if (valid.length === 0) {
        container.innerHTML = '<div class="empty-state"><p>No completed reports</p><small>Run an analysis from the main page.</small></div>';
        return;
      }

      const grouped = {};
      valid.forEach(r => {
        if (!grouped[r.sku]) grouped[r.sku] = [];
        grouped[r.sku].push(r);
      });

      let html = '';
      Object.keys(grouped).sort().forEach(sku => {
        html += '<div class="report-group-title">' + escapeHtml(sku) + '</div>';
        grouped[sku].forEach(report => {
          const url = '/api/reports/' + encodeURIComponent(report.sku) + '/' + encodeURIComponent(report.session) + '/report.html';
          const brand = report.brand && report.brand !== 'Unknown' ? report.brand : '';
          const color = report.color && report.color !== 'Unknown' ? report.color : '';
          const date = report.created_at || report.session || '';
          const issues = report.total_issues;

          let badges = '';
          if (typeof issues === 'number' && issues > 0) {
            badges += '<span class="badge badge-issues">' + issues + ' issue' + (issues !== 1 ? 's' : '') + '</span>';
          } else {
            badges += '<span class="badge badge-clean">Clean</span>';
          }

          const meta = [brand, color].filter(Boolean).join(' / ');
          const deleteBtn = '<button class="btn-delete" onclick="event.preventDefault();event.stopPropagation();deleteReport(\'' + escapeHtml(report.sku) + '\',\'' + escapeHtml(report.session) + '\')" title="Delete">&times;</button>';
          html +=
            '<a class="report-card" href="' + url + '" target="_blank">' +
            '<div class="report-info">' +
            '<div class="report-sku">' + escapeHtml(sku) + '</div>' +
            '<div class="report-meta">' +
            (meta ? '<span>' + escapeHtml(meta) + '</span>' : '') +
            '<span>' + escapeHtml(formatDate(date)) + '</span>' +
            '</div>' +
            '</div>' +
            '<div style="display:flex;align-items:center;gap:8px;">' + badges + deleteBtn + '</div>' +
            '</a>';
        });
      });
      container.innerHTML = html;
    })
    .catch(err => {
      container.innerHTML = '<div class="empty-state"><p>Failed to load reports</p><small>' + escapeHtml(err.message) + '</small></div>';
    });
}

function deleteReport(sku, session) {
  if (!confirm('Delete report for ' + sku + '?')) return;
  fetch('/api/reports/' + encodeURIComponent(sku) + '/' + encodeURIComponent(session), {method: 'DELETE'})
    .then(res => { if (res.ok) loadReports(); })
    .catch(() => {});
}

function formatDate(dateStr) {
  if (!dateStr) return '';
  // Handle "2026-04-03_211448_296438" format
  const match = dateStr.match(/(\d{4})-(\d{2})-(\d{2})_(\d{2})(\d{2})(\d{2})/);
  if (match) {
    return match[1] + '-' + match[2] + '-' + match[3] + ' ' + match[4] + ':' + match[5];
  }
  // Handle ISO format
  try {
    const d = new Date(dateStr);
    if (!isNaN(d)) return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'});
  } catch(e) {}
  return dateStr;
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

document.addEventListener('DOMContentLoaded', function() {
  const input = document.getElementById('sku-input');
  if (input) {
    input.addEventListener('keydown', function(e) { if (e.key === 'Enter') analyzeSku(); });
    input.addEventListener('input', function() { updateSnippet(); });
  }
  if (document.getElementById('reports-container')) loadReports();
});
