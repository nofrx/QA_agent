// Shoe QA Frontend

function analyzeSku() {
  const input = document.getElementById('sku-input');
  const sku = input.value.trim();
  if (!sku) {
    input.focus();
    return;
  }

  const btn = document.getElementById('analyze-btn');
  const progressSection = document.getElementById('progress-section');
  const progressFeed = document.getElementById('progress-feed');
  const progressHeader = document.getElementById('progress-header');
  const resultSection = document.getElementById('result-section');
  const errorCard = document.getElementById('error-card');

  // Reset
  btn.disabled = true;
  progressFeed.innerHTML = '';
  resultSection.classList.remove('active');
  errorCard.classList.remove('active');
  progressSection.classList.add('active');
  progressHeader.innerHTML = '<div class="spinner"></div><span>Analyzing ' + escapeHtml(sku.toUpperCase()) + '...</span>';

  // Start analysis
  fetch('/api/analyze/' + encodeURIComponent(sku), { method: 'POST' })
    .then(res => {
      if (!res.ok) return res.json().then(d => { throw new Error(d.detail || 'Failed to start'); });
      // Open SSE for progress
      const evtSource = new EventSource('/api/status/' + encodeURIComponent(sku));

      evtSource.onmessage = function(event) {
        const data = JSON.parse(event.data);

        if (data.type === 'progress') {
          const msg = document.createElement('div');
          msg.className = 'progress-msg';
          msg.textContent = data.message;
          progressFeed.appendChild(msg);
          progressFeed.scrollTop = progressFeed.scrollHeight;
        }
        else if (data.type === 'complete') {
          evtSource.close();
          btn.disabled = false;
          progressHeader.innerHTML = '<span>Analysis complete</span>';

          const reportUrl = '/api/reports/' + encodeURIComponent(data.sku) + '/' + encodeURIComponent(data.session) + '/report.html';
          resultSection.innerHTML =
            '<div class="result-card">' +
            '<h3>Report Ready</h3>' +
            '<p>QA analysis for <strong>' + escapeHtml(data.sku) + '</strong> is complete.</p>' +
            '<a href="' + reportUrl + '" target="_blank">View Report</a>' +
            '</div>';
          resultSection.classList.add('active');
        }
        else if (data.type === 'error') {
          evtSource.close();
          btn.disabled = false;
          progressHeader.innerHTML = '<span>Analysis failed</span>';

          const msg = document.createElement('div');
          msg.className = 'progress-msg error';
          msg.textContent = data.message;
          progressFeed.appendChild(msg);

          errorCard.querySelector('p').textContent = data.message;
          errorCard.classList.add('active');
        }
      };

      evtSource.onerror = function() {
        evtSource.close();
        btn.disabled = false;
        progressHeader.innerHTML = '<span>Connection lost</span>';
        errorCard.querySelector('p').textContent = 'Lost connection to server. Check if the analysis is still running.';
        errorCard.classList.add('active');
      };
    })
    .catch(err => {
      btn.disabled = false;
      errorCard.querySelector('p').textContent = err.message;
      errorCard.classList.add('active');
    });
}

function loadReports() {
  const container = document.getElementById('reports-container');

  fetch('/api/reports')
    .then(res => res.json())
    .then(reports => {
      if (!reports || reports.length === 0) {
        container.innerHTML =
          '<div class="empty-state">' +
          '<p>No reports yet</p>' +
          '<small>Run an analysis from the main page to generate your first report.</small>' +
          '</div>';
        return;
      }

      // Group by SKU
      const grouped = {};
      reports.forEach(r => {
        if (!grouped[r.sku]) grouped[r.sku] = [];
        grouped[r.sku].push(r);
      });

      let html = '';
      Object.keys(grouped).sort().forEach(sku => {
        html += '<div class="report-group-title">' + escapeHtml(sku) + '</div>';
        grouped[sku].forEach(report => {
          const url = report.has_report
            ? '/api/reports/' + encodeURIComponent(report.sku) + '/' + encodeURIComponent(report.session) + '/report.html'
            : '#';
          const brand = report.brand || '';
          const date = report.created_at || report.session || '';
          const issues = report.total_issues;
          const status = report.status || 'unknown';

          let badges = '';
          if (status === 'complete') {
            badges += '<span class="badge badge-complete">Complete</span> ';
          }
          if (typeof issues === 'number' && issues > 0) {
            badges += '<span class="badge badge-issues">' + issues + ' issue' + (issues !== 1 ? 's' : '') + '</span>';
          } else if (status === 'complete') {
            badges += '<span class="badge badge-clean">Clean</span>';
          }

          html +=
            '<a class="report-card" href="' + url + '" target="_blank">' +
            '<div class="report-info">' +
            '<div class="report-sku">' + escapeHtml(sku) + '</div>' +
            '<div class="report-meta">' +
            (brand ? '<span>' + escapeHtml(brand) + '</span>' : '') +
            '<span>' + escapeHtml(date) + '</span>' +
            '</div>' +
            '</div>' +
            '<div>' + badges + '</div>' +
            '</a>';
        });
      });

      container.innerHTML = html;
    })
    .catch(err => {
      container.innerHTML =
        '<div class="empty-state">' +
        '<p>Failed to load reports</p>' +
        '<small>' + escapeHtml(err.message) + '</small>' +
        '</div>';
    });
}

function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// Enter key triggers analyze
document.addEventListener('DOMContentLoaded', function() {
  const input = document.getElementById('sku-input');
  if (input) {
    input.addEventListener('keydown', function(e) {
      if (e.key === 'Enter') analyzeSku();
    });
  }

  // Auto-load reports if on reports page
  if (document.getElementById('reports-container')) {
    loadReports();
  }
});
