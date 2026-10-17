/* Mortgage Rates page: reads data/market.json (written by tools/update_market_data.py).
   Every number shown comes from that file; anything missing is simply not shown. */
(function () {
  var MON = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  var COL = { lehi: '#497db3', county: '#4d4d4d', utah: '#9fb3d3' };
  var $ = function (id) { return document.getElementById(id); };
  var esc = function (s) { return String(s).replace(/[&<>"]/g, function (c) { return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); };
  var money = function (v) { return '$' + Math.round(v).toLocaleString('en-US'); };
  var kmoney = function (v) { return v >= 1e6 ? '$' + (v / 1e6).toFixed(2) + 'M' : '$' + Math.round(v / 1000) + 'K'; };
  var int = function (v) { return Math.round(v).toLocaleString('en-US'); };
  var ym = function (s) { return MON[+s.slice(5, 7) - 1] + ' ' + s.slice(0, 4); };
  var day = function (s) { var d = new Date(s + 'T12:00:00'); return MON[d.getMonth()] + ' ' + d.getDate() + ', ' + d.getFullYear(); };
  var span = function (b, e) { return b.slice(0, 7) === e.slice(0, 7) ? ym(b) : (b.slice(0, 4) === e.slice(0, 4) ? MON[+b.slice(5, 7) - 1] + '–' + ym(e) : ym(b) + '–' + ym(e)); };
  var chg = function (v, unit, invert) {
    if (v === null || v === undefined) return '';
    var cls = v > 0 ? 'up' : (v < 0 ? 'down' : 'flat');
    var arrow = v > 0 ? '▲' : (v < 0 ? '▼' : '•');
    return '<span class="chg ' + cls + '">' + arrow + ' ' + (v > 0 ? '+' : '') + v + (unit || '%') + ' vs. a year ago</span>';
  };
  function srcTag(D, key, period) {
    var s = D.sources[key]; if (!s) return '';
    var short = { freddie: 'Freddie Mac' }[key];
    return '<a class="stag" href="' + esc(s.url) + '" target="_blank" rel="noopener">' + short + '</a>' + (period ? ' · ' + esc(period) : '');
  }

  function render(D) {
    var F = D.freddie;
    var gen = new Date(D.generated_at);
    $('updated').innerHTML = 'Updated ' + gen.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'America/Denver' }) +
      ' · Freddie Mac survey released ' + (F ? day(F.as_of) : '') + (D.stale && D.stale.length ? ' · some sources could not be refreshed and show their last available release' : '');

    // ---- rate band
        if (F && F.rate30 != null) {
      var h = '<div class="rate-main"><span class="eyebrow">30-year fixed, national average</span><b>' + F.rate30.toFixed(2) + '%</b>' +
        '<span class="src">' + srcTag(D, 'freddie', 'survey released ' + day(F.as_of)) + '</span></div><div class="rate-side">';
      if (F.rate15 != null) h += '<div><span>15-year fixed</span><b>' + F.rate15.toFixed(2) + '%</b></div>';
      if (F.rate30_prev_week != null) h += '<div><span>30-year, week before (' + day(F.prev_week_date) + ')</span><b>' + F.rate30_prev_week.toFixed(2) + '%</b></div>';
      if (F.rate30_year_ago != null) h += '<div><span>30-year, a year ago (' + day(F.year_ago_date) + ')</span><b>' + F.rate30_year_ago.toFixed(2) + '%</b></div>';
      $('rate').innerHTML = h + '</div>';
    } else { $('rate').parentNode.parentNode.style.display = 'none'; }

    // ---- charts
    var asDate = function (s) { return new Date(s.length === 7 ? s + '-15T12:00:00' : s + 'T12:00:00'); };
    if (F && F.series30) chart('c-rate', [{ name: '30-year fixed', color: COL.lehi, pts: F.series30.map(function (p) { return [asDate(p[0]), p[1]]; }) }],
      function (v) { return v.toFixed(1) + '%'; }, srcTag(D, 'freddie', 'through ' + day(F.as_of)), true);

    // ---- insights
    $('insights').innerHTML = (D.insights || []).map(function (i) {
      return '<article><h3>' + esc(i.title) + '</h3><p>' + esc(i.text) + '</p>' +
        (i.sources && i.sources.length ? '<p class="src">Based on ' + i.sources.map(function (s) { return srcTag(D, s); }).join(', ') + ' data.</p>' : '') + '</article>';
    }).join('') + '<article class="cta-card"><h3>Let’s talk it through</h3><p>I’ll walk you through what’s selling near you and what today’s numbers mean for your plans.</p><a class="btn" href="index.html#connect">Let’s Connect</a></article>';

    var through = { freddie: F ? 'weekly; latest ' + day(F.as_of) : null };
    $('sources').innerHTML = ['freddie'].filter(function (k) { return D[k]; }).map(function (k) {
      var s = D.sources[k];
      return '<li><a href="' + esc(s.url) + '" target="_blank" rel="noopener">' + esc(s.name) + '</a>: ' + esc(s.credit) +
        (through[k] ? ' <span class="src">(' + esc(through[k]) + ')</span>' : '') + (D.stale && D.stale.indexOf(k) > -1 ? ' <span class="src">Not refreshed this week.</span>' : '') + '</li>';
    }).join('');
  }

  // Minimal SVG line chart
  function chart(id, series, fmt, srcHtml, single) {
    var fig = $(id); if (!fig) return;
    series = series.filter(function (s) { return s.pts.length > 1; });
    if (!series.length) { fig.style.display = 'none'; return; }
    var W = 560, H = 260, m = { l: 64, r: 14, t: 14, b: 28 };
    var xs = [], ys = [];
    series.forEach(function (s) { s.pts.forEach(function (p) { xs.push(+p[0]); ys.push(p[1]); }); });
    var x0 = Math.min.apply(null, xs), x1 = Math.max.apply(null, xs);
    var y0 = Math.min.apply(null, ys), y1 = Math.max.apply(null, ys);
    var pad = (y1 - y0) * 0.08 || 1; y0 -= pad; y1 += pad; if (y0 < 0) y0 = 0;
    var step = niceStep((y1 - y0) / 4), ys0 = Math.floor(y0 / step) * step;
    var X = function (t) { return m.l + (t - x0) / (x1 - x0) * (W - m.l - m.r); };
    var Y = function (v) { return H - m.b - (v - ys0) / (y1 - ys0) * (H - m.t - m.b); };
    var svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="' + esc(fig.querySelector('b').textContent) + ' chart">';
    for (var v = ys0; v <= y1 + 1e-9; v += step) {
      svg += '<line x1="' + m.l + '" x2="' + (W - m.r) + '" y1="' + Y(v) + '" y2="' + Y(v) + '" class="grid"/><text x="' + (m.l - 8) + '" y="' + (Y(v) + 4) + '" class="yl">' + fmt(v) + '</text>';
    }
    var ya = new Date(x0).getFullYear() + 1, yb = new Date(x1).getFullYear(), every = (yb - ya) > 6 ? 2 : 1;
    for (var y = ya; y <= yb; y += every) {
      var t = +new Date(y, 0, 1); if (t < x0 || t > x1) continue;
      svg += '<line x1="' + X(t) + '" x2="' + X(t) + '" y1="' + (H - m.b) + '" y2="' + (H - m.b + 4) + '" class="tick"/><text x="' + X(t) + '" y="' + (H - 8) + '" class="xl">' + y + '</text>';
    }
    series.forEach(function (s) {
      var d = s.pts.map(function (p, i) { return (i ? 'L' : 'M') + X(+p[0]).toFixed(1) + ' ' + Y(p[1]).toFixed(1); }).join('');
      svg += '<path d="' + d + '" fill="none" stroke="' + s.color + '" stroke-width="' + (s.dash ? 2 : 2.4) + '"' + (s.dash ? ' stroke-dasharray="5 4"' : '') + ' stroke-linejoin="round"/>';
      var lp = s.pts[s.pts.length - 1];
      svg += '<circle cx="' + X(+lp[0]) + '" cy="' + Y(lp[1]) + '" r="3.5" fill="' + s.color + '"/>';
    });
    svg += '</svg>';
    var legend = single ? '' : '<div class="legend">' + series.map(function (s) {
      return '<span><i style="border-top:3px ' + (s.dash ? 'dashed' : 'solid') + ' ' + s.color + '"></i>' + esc(s.name) + '</span>';
    }).join('') + '</div>';
    var latest = series.map(function (s) { var p = s.pts[s.pts.length - 1]; return (single ? '' : esc(s.name) + ': ') + '<b>' + fmtFull(fmt, p[1]) + '</b>'; }).join(' · ');
    fig.querySelector('.plot').innerHTML = svg + legend + '<p class="latest">Latest: ' + latest + '</p>';
    fig.querySelector('.src').innerHTML = srcHtml;
  }
  function fmtFull(fmt, v) { return v > 10000 ? money(v) : (fmt(v).indexOf('%') > -1 ? v.toFixed(2) + '%' : fmt(v)); }
  function niceStep(raw) { var p = Math.pow(10, Math.floor(Math.log10(raw))), n = raw / p; return (n < 1.5 ? 1 : n < 3 ? 2 : n < 7 ? 5 : 10) * p; }

  fetch('data/market.json', { cache: 'no-cache' }).then(function (r) { if (!r.ok) throw 0; return r.json(); }).then(render).catch(function () {
    $('updated').textContent = 'Market data is temporarily unavailable. Please check back soon, or contact Millie for the latest numbers.';
    ['rate'].forEach(function (i) { $(i).innerHTML = ''; });
  });
})();
