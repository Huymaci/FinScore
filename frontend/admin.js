/* Admin console.
 *
 * The operator surface is its own shell rather than a page inside the member
 * app: an admin never records a transaction, and the member navigation used to
 * be rendered and then hidden item by item, which left a stripped-down husk.
 * This module owns everything under #admin-console and app.js only starts and
 * stops it.
 *
 * FR-51 / NFR-09: nothing rendered here is identified financial data. Every
 * figure is a count, a rate or an operational status. Statement filenames,
 * account names, amounts and alert text are deliberately never requested.
 *
 * CSP forbids inline styles (see talisman config in app/__init__.py), so bar
 * and column sizes are applied through the CSSOM in applySizes(), never with a
 * style="" attribute.
 */
(() => {
  'use strict';

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const t = (key, params) => window.I18n.t(key, params);
  // I18n.t() echoes the key back when it is missing, so a key built at runtime
  // needs an explicit miss check before it can fall back to the raw value.
  const tryT = (key, fallback) => (t(key) === key ? fallback : t(key));

  // Views a delegated SUPPORT_ADMIN may open. Everything else is guarded by
  // primary_admin_required on the server; hiding it here only keeps the rail
  // honest about what the account can actually do.
  const NAV = [
    { id: 'dashboard', key: 'adm_nav_dashboard', icon: '▤', primaryOnly: true },
    { id: 'users', key: 'adm_nav_users', icon: '◍', primaryOnly: false },
    { id: 'transactions', key: 'adm_nav_transactions', icon: '⇄', primaryOnly: true },
    { id: 'imports', key: 'adm_nav_imports', icon: '⇧', primaryOnly: true },
    { id: 'alerts', key: 'adm_nav_alerts', icon: '◔', primaryOnly: true },
    { id: 'logs', key: 'adm_nav_logs', icon: '≡', primaryOnly: true },
    { id: 'settings', key: 'adm_nav_settings', icon: '⚙', primaryOnly: true },
  ];

  const LOG_TABS = ['ALL', 'AUTH', 'ADMIN', 'DATA', 'JOB', 'ERRORS'];

  let bridge = null;
  let profile = null;
  let view = 'dashboard';
  let status = null;
  let usersTab = 'users';
  let logsTab = 'ALL';
  let searchTimer = null;
  const page = { users: 1, supportAdmins: 1, reports: 1, logs: 1, batches: 1 };

  const api = (path, options) => bridge.api(path, options);
  const esc = value => bridge.esc(value);
  const toast = (title, detail) => bridge.toast(title, detail);
  const isPrimary = () => profile && profile.role === 'ADMIN';
  const locale = () => (window.I18n.language === 'en' ? 'en-US' : 'vi-VN');
  const num = value => new Intl.NumberFormat(locale()).format(Number(value || 0));

  function dateTime(value) {
    if (!value) return '—';
    return new Date(value).toLocaleString(locale(), {
      day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
    });
  }

  function dateOnly(value) {
    return value ? new Date(value).toLocaleDateString(locale()) : '—';
  }

  function clock(value) {
    return value ? new Date(value).toLocaleTimeString(locale(), { hour: '2-digit', minute: '2-digit' }) : '—';
  }

  function duration(seconds) {
    const total = Math.max(0, Number(seconds || 0));
    const days = Math.floor(total / 86400);
    const hours = Math.floor((total % 86400) / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    if (days) return t('adm_uptime_days', { days, hours });
    if (hours) return t('adm_uptime_hours', { hours, minutes });
    return t('adm_uptime_minutes', { minutes });
  }

  function bytes(value) {
    if (value === null || value === undefined) return '—';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let size = Number(value);
    let unit = 0;
    while (size >= 1024 && unit < units.length - 1) { size /= 1024; unit += 1; }
    return `${size >= 100 || unit === 0 ? Math.round(size) : size.toFixed(1)} ${units[unit]}`;
  }

  // scripts/nightly.py records NIGHTLY_JOB:SUCCESS / :FAILED, so "SUCCESS" is
  // the healthy value. A run that succeeded days ago is not healthy either:
  // the job is meant to be nightly, so anything past 36 hours reads as stale.
  const STALE_AFTER_MS = 36 * 60 * 60 * 1000;

  function jobHealth(job) {
    if (job.status === 'FAILED') return { tone: 'bad', ok: false, label: t('adm_job_failed') };
    if (!job.last_run || job.status === 'NEVER_RUN') return { tone: 'warn', ok: false, label: t('adm_never_run') };
    if (Date.now() - new Date(job.last_run).getTime() > STALE_AFTER_MS) {
      return { tone: 'warn', ok: false, label: t('adm_job_stale') };
    }
    return { tone: 'ok', ok: true, label: t('adm_job_ok') };
  }

  const dot = (tone, label) => `<span class="adm-dot ${tone}">${esc(label)}</span>`;
  const pill = (tone, label) => `<span class="adm-pill ${tone}">${esc(label)}</span>`;
  const emptyRow = (span, title, detail) =>
    `<tr><td colspan="${span}"><div class="adm-empty"><b>${esc(title)}</b><span>${esc(detail)}</span></div></td></tr>`;
  const noSource = (title, detail) =>
    `<div class="adm-nosource"><b>${esc(title)}</b>${esc(detail)}</div>`;

  /* Sizes that CSP will not let us put in a style attribute. */
  function applySizes(root = document) {
    $$('[data-width]', root).forEach(node => {
      node.style.setProperty('width', `${Math.max(0, Math.min(100, Number(node.dataset.width) || 0))}%`);
    });
    $$('[data-height]', root).forEach(node => {
      node.style.setProperty('height', `${Math.max(1, Math.min(100, Number(node.dataset.height) || 0))}%`);
    });
  }

  function tile({ label, icon, iconTone = 'blue', value, detail, state, muted }) {
    return `<article class="adm-tile${muted ? ' is-muted' : ''}">
      <div class="adm-tile-head">
        <span class="adm-tile-label">${esc(label)}</span>
        <span class="adm-tile-icon ${iconTone}" aria-hidden="true">${icon}</span>
      </div>
      ${state ? `<div>${state}</div>` : ''}
      <strong>${esc(value)}</strong>
      <small>${esc(detail)}</small>
    </article>`;
  }

  /* ---------------------------------------------------------------- shell */

  function buildShell() {
    const root = $('#admin-console');
    root.innerHTML = `
      <nav class="adm-rail" id="adm-rail" aria-label="${esc(t('adm_nav_aria'))}">
        <span class="adm-rail-brand">
          <span class="brand-mark" aria-hidden="true">S</span>
          <span><b>SmartFinance</b><small>${esc(t('adm_console_label'))}</small></span>
        </span>
        <div class="adm-nav" id="adm-nav"></div>
        <div class="adm-rail-note">
          <span aria-hidden="true">!</span>
          <span><b>${esc(t('adm_privacy_title'))}</b><p>${esc(t('adm_privacy_note'))}</p></span>
        </div>
        <div class="adm-rail-user">
          <span class="avatar profile-avatar" aria-hidden="true"></span>
          <span><b id="adm-user-name"></b><small id="adm-user-role"></small></span>
        </div>
      </nav>
      <div class="adm-main">
        <header class="adm-topbar">
          <button class="icon-btn adm-menu-toggle" type="button" id="adm-menu-toggle"
                  aria-controls="adm-rail" aria-expanded="false" aria-label="${esc(t('open_menu'))}">☰</button>
          <p class="adm-crumb">${esc(t('admin_console'))} › <b id="adm-crumb"></b></p>
          <div class="adm-topbar-actions">
            <div class="language-switcher" role="group" aria-label="${esc(t('language'))}">
              <button type="button" data-language="vi">VI</button><span>|</span><button type="button" data-language="en">EN</button>
            </div>
            <button class="icon-btn theme-toggle" type="button" data-theme-toggle aria-pressed="false"
                    aria-label="${esc(t('dark_mode'))}"><span data-theme-icon aria-hidden="true">☾</span></button>
            <button class="secondary-btn" type="button" id="adm-logout">${esc(t('logout'))}</button>
          </div>
        </header>
        ${NAV.map(item => `<section class="adm-view" id="adm-view-${item.id}" tabindex="-1"></section>`).join('')}
      </div>`;

    $('#adm-nav').innerHTML = NAV
      .filter(item => isPrimary() || !item.primaryOnly)
      .map(item => `<a href="#admin/${item.id}" data-adm-view="${item.id}">
          <span class="adm-nav-icon" aria-hidden="true">${item.icon}</span>
          <span>${esc(t(item.key))}</span>
          <b class="adm-nav-badge hidden" data-adm-badge="${item.id}">0</b>
        </a>`).join('');

    $('#adm-user-name').textContent = profile.full_name || '';
    $('#adm-user-role').textContent = isPrimary() ? t('adm_role_primary') : t('support_admin');
    $('.adm-rail-user .avatar').textContent = (profile.full_name || '?')
      .split(/\s+/).slice(-2).map(part => part[0] || '').join('').toUpperCase();

    $('#adm-menu-toggle').addEventListener('click', () => {
      const rail = $('#adm-rail');
      const open = rail.classList.toggle('open');
      $('#adm-menu-toggle').setAttribute('aria-expanded', String(open));
    });
    $('#adm-logout').addEventListener('click', () => bridge.logout());
    window.Theme.refreshControls();
    window.I18n.applyLanguage();
    root.addEventListener('click', onConsoleClick);
    root.addEventListener('change', onConsoleChange);
    root.addEventListener('input', onConsoleInput);
  }

  function navigate(id) {
    const allowed = NAV.filter(item => isPrimary() || !item.primaryOnly).map(item => item.id);
    view = allowed.includes(id) ? id : allowed[0];
    $$('.adm-view').forEach(section => section.classList.toggle('active', section.id === `adm-view-${view}`));
    $$('#adm-nav a').forEach(link => link.classList.toggle('active', link.dataset.admView === view));
    $('#adm-crumb').textContent = t(NAV.find(item => item.id === view).key);
    $('#adm-rail').classList.remove('open');
    $('#adm-menu-toggle').setAttribute('aria-expanded', 'false');
    if (location.hash !== `#admin/${view}`) history.replaceState(null, '', `#admin/${view}`);
    window.scrollTo({ top: 0 });
    render(view);
  }

  function render(id) {
    const target = $(`#adm-view-${id}`);
    if (!target.dataset.ready) {
      target.innerHTML = `<div class="adm-empty">${esc(t('loading'))}</div>`;
    }
    const loaders = {
      dashboard: renderDashboard, users: renderUsers, transactions: renderTransactions,
      imports: renderImports, alerts: renderAlerts, logs: renderLogs, settings: renderSettings,
    };
    loaders[id](target).catch(error => {
      if (error && error.status === 401) return;
      target.innerHTML = `<div class="adm-empty"><b>${esc(t('load_failed'))}</b><span>${esc(error.message || '')}</span></div>`;
    });
  }

  const heading = (kicker, title, note, actions = '') => `
    <div class="adm-heading adm-heading-row">
      <div><p class="eyebrow">${esc(kicker)}</p><h1>${esc(title)}</h1>${note ? `<p>${esc(note)}</p>` : ''}</div>
      ${actions ? `<div class="heading-actions">${actions}</div>` : ''}
    </div>`;

  async function systemStatus(force = false) {
    if (!status || force) status = await api('/admin/system-status');
    return status;
  }

  /* ------------------------------------------------------------ dashboard */

  async function renderDashboard(target) {
    const data = await systemStatus(true);
    const requests = data.requests;
    const database = data.database;
    const auth = data.auth;
    const openErrors = requests.error_groups.filter(group => !group.handled).length;
    const job = data.jobs.nightly_alerts;
    const health = jobHealth(job);
    const jobStale = !health.ok;
    const services = [database.connected, health.ok].filter(Boolean).length;

    const errorTone = requests.error_rate >= 5 ? 'bad' : requests.error_rate >= 1 ? 'warn' : 'ok';
    const dbTone = !database.connected ? 'bad' : (database.response_ms || 0) > 200 ? 'warn' : 'ok';

    const banner = jobStale ? `
      <div class="adm-banner warn">
        <span class="adm-banner-mark" aria-hidden="true">!</span>
        <div>
          <b>${esc(t('adm_job_degraded_title'))}</b>
          <p>${esc(t('adm_job_degraded_note', { status: health.label, at: job.last_run ? dateTime(job.last_run) : t('adm_never_run') }))}</p>
          <div class="adm-banner-actions"><button class="secondary-btn" type="button" data-adm-go="alerts">${esc(t('adm_view_alerts'))}</button></div>
        </div>
      </div>` : '';

    const suppressed = data.users.suppressed;
    const suppressedNote = suppressed ? `
      <div class="adm-banner info">
        <span class="adm-banner-mark" aria-hidden="true">i</span>
        <div><b>${esc(t('adm_suppressed_title'))}</b><p>${esc(t('adm_suppressed_note'))}</p></div>
      </div>` : '';

    target.innerHTML = heading(
      t('adm_dashboard_kicker'), t('adm_dashboard_title'), t('adm_dashboard_note'),
      `<button class="secondary-btn" type="button" data-adm-refresh>${esc(t('adm_refresh'))}</button>`) +
      banner + suppressedNote + `
      <div class="adm-tiles">
        ${tile({ label: t('adm_tile_server'), icon: '♥', iconTone: 'mint', state: dot(services === 2 ? 'ok' : 'warn', services === 2 ? t('adm_state_ok') : t('adm_state_degraded')), value: duration(requests.uptime_seconds), detail: requests.p95_ms === null ? t('adm_no_traffic_yet') : t('adm_p95', { ms: num(requests.p95_ms) }) })}
        ${tile({ label: t('adm_tile_requests'), icon: '▦', iconTone: 'blue', value: num(requests.requests_24h), detail: t('adm_requests_since', { at: clock(requests.since) }) })}
        ${tile({ label: t('adm_tile_services'), icon: '▣', iconTone: 'violet', state: dot(services === 2 ? 'ok' : 'warn', `${services}/2`), value: `${services}/2`, detail: jobStale ? t('adm_service_job_down') : t('adm_service_all_up') })}
        ${tile({ label: t('adm_tile_alerts'), icon: '◔', iconTone: openErrors ? 'coral' : 'mint', state: dot(openErrors ? 'bad' : 'ok', openErrors ? t('adm_open_count', { count: openErrors }) : t('adm_state_clear')), value: num(openErrors), detail: t('adm_tile_alerts_detail') })}
      </div>
      <div class="adm-tiles">
        ${tile({ label: t('adm_tile_active_users'), icon: '◍', iconTone: 'mint', muted: suppressed, value: suppressed ? '—' : num(data.users.active_30d), detail: suppressed ? t('adm_suppressed_short') : t('last_30_days') })}
        ${tile({ label: t('adm_tile_error_rate'), icon: '!', iconTone: 'coral', state: dot(errorTone, `${requests.error_rate}%`), value: `${requests.error_rate}%`, detail: t('adm_errors_count', { count: num(requests.errors_24h) }) })}
        ${tile({ label: t('adm_tile_database'), icon: '▤', iconTone: 'blue', state: dot(dbTone, database.connected ? t('adm_state_connected') : t('adm_state_down')), value: bytes(database.size_bytes), detail: t('adm_db_detail', { ms: database.response_ms ?? '—', rows: num(database.rows) }) })}
        ${tile({ label: t('adm_tile_failed_logins'), icon: '⚿', iconTone: auth.failed_logins_24h ? 'coral' : 'mint', state: auth.locked_now ? dot('warn', t('adm_locked_now', { count: auth.locked_now })) : '', value: num(auth.failed_logins_24h), detail: t('adm_lockouts_24h', { count: num(auth.lockouts_24h) }) })}
      </div>
      <article class="adm-panel">
        <div class="adm-panel-head">
          <div><h2>${esc(t('adm_traffic_title'))}</h2><p>${esc(t('adm_traffic_note'))}</p></div>
        </div>
        <div class="adm-panel-body">${trafficChart(requests.traffic)}</div>
      </article>
      <div class="adm-grid-2">
        <article class="adm-panel">
          <div class="adm-panel-head"><div><h2>${esc(t('adm_recent_errors'))}</h2></div>
            <button class="text-btn" type="button" data-adm-go="logs">${esc(t('view_all'))}</button></div>
          <div class="adm-feed" id="adm-recent-errors"></div>
        </article>
        <article class="adm-panel">
          <div class="adm-panel-head"><div><h2>${esc(t('adm_recent_admin'))}</h2></div>
            <button class="text-btn" type="button" data-adm-go="logs">${esc(t('view_all'))}</button></div>
          <div class="adm-feed" id="adm-recent-admin"></div>
        </article>
      </div>`;

    $('#adm-recent-errors').innerHTML = requests.error_groups.slice(0, 5).map(group => `
      <div class="adm-feed-item">
        <time>${esc(dateTime(group.last_seen))}</time>
        ${pill(group.status >= 500 ? 'bad' : 'warn', String(group.status))}
        ${group.handled ? pill('neutral', t('adm_error_handled')) : pill('info', t('adm_error_open'))}
        <b>${esc(group.method)} ${esc(group.rule)}</b>
        <p>${esc(group.message || t('adm_no_message'))} · ${esc(t('adm_times', { count: group.count }))}</p>
      </div>`).join('') ||
      `<div class="adm-empty"><b>${esc(t('adm_no_errors'))}</b><span>${esc(t('adm_no_errors_detail'))}</span></div>`;

    const audit = await api('/admin/audit-logs');
    $('#adm-recent-admin').innerHTML = audit.items.slice(0, 6).map(row => `
      <div class="adm-feed-item">
        <time>${esc(dateTime(row.created_at))}</time>
        <b>${esc(describeAction(row.action))}</b>
        <p>${esc(row.action)}</p>
      </div>`).join('') ||
      `<div class="adm-empty"><b>${esc(t('no_audit_logs'))}</b><span>${esc(t('no_audit_logs_detail'))}</span></div>`;

    applySizes(target);
  }

  function trafficChart(traffic) {
    const peak = Math.max(1, ...traffic.map(hour => hour.total));
    if (!traffic.some(hour => hour.total)) {
      return noSource(t('adm_no_traffic_yet'), t('adm_no_traffic_detail'));
    }
    const columns = traffic.map(hour => `
      <span class="adm-spark-col" title="${esc(dateTime(hour.hour))}: ${esc(num(hour.total))}">
        <i class="adm-spark-bar${hour.errors ? ' has-errors' : ''}" data-height="${Math.round((hour.total / peak) * 100)}"></i>
      </span>`).join('');
    const total = traffic.reduce((sum, hour) => sum + hour.total, 0);
    const errors = traffic.reduce((sum, hour) => sum + hour.errors, 0);
    return `<div class="adm-spark" role="img" aria-label="${esc(t('adm_traffic_aria', { total: num(total) }))}">${columns}</div>
      <div class="adm-spark-axis"><span>-24h</span><span>-18h</span><span>-12h</span><span>-6h</span><span>${esc(t('adm_now'))}</span></div>
      <div class="adm-legend"><span>${esc(t('adm_requests_total'))}: <b>${esc(num(total))}</b></span>
        <span>${esc(t('adm_server_errors'))}: <b>${esc(num(errors))}</b></span></div>`;
  }

  function describeAction(action) {
    if (action.startsWith('LOGIN_FAILED:')) return t('adm_act_login_failed');
    if (action.startsWith('ADMIN_LOCK_USER:')) return t('adm_act_lock');
    if (action.startsWith('ADMIN_UNLOCK_USER:')) return t('adm_act_unlock');
    if (action.startsWith('ADMIN_RESET_PASSWORD:')) return t('adm_act_reset');
    if (action.startsWith('ADMIN_CHANGE_ROLE:')) return t('adm_act_role');
    if (action.startsWith('ADMIN_SUPPORT_REPORT_')) return t('adm_act_report');
    if (action.startsWith('ACCOUNT_DELETED:')) return t('adm_act_erased');
    if (action.startsWith('NIGHTLY_JOB:')) return t('adm_act_job');
    return t('adm_act_other');
  }

  /* ---------------------------------------------------------------- users */

  async function renderUsers(target) {
    const tabs = [
      ['users', t('adm_tab_users')],
      ...(isPrimary() ? [['support-admins', t('adm_tab_support_admins')]] : []),
      ['reports', t('support_reports_title')],
    ];
    if (!tabs.some(([id]) => id === usersTab)) usersTab = 'users';

    target.innerHTML = heading(t('manage_users_kicker'), t('manage_users'), t('adm_users_note')) + `
      <div class="adm-tabs" role="tablist">
        ${tabs.map(([id, label]) => `<button type="button" role="tab" data-adm-users-tab="${id}"
            aria-selected="${id === usersTab}" class="${id === usersTab ? 'active' : ''}">${esc(label)}</button>`).join('')}
      </div>
      <div id="adm-users-panel"></div>`;
    target.dataset.ready = '1';
    await renderUsersTab();
  }

  async function renderUsersTab() {
    const panel = $('#adm-users-panel');
    if (usersTab === 'users') {
      panel.innerHTML = `
        <div class="adm-filters">
          <div class="search-box"><span aria-hidden="true">⌕</span>
            <input id="admin-user-search" type="search" placeholder="${esc(t('admin_user_search_placeholder'))}"
                   aria-label="${esc(t('admin_user_search_aria'))}"></div>
          <select id="admin-user-status" aria-label="${esc(t('admin_user_status_aria'))}">
            <option value="ALL">${esc(t('all_statuses'))}</option>
            <option value="ACTIVE">${esc(t('active'))}</option>
            <option value="LOCKED">${esc(t('locked'))}</option>
          </select>
        </div>
        <article class="adm-panel"><div class="adm-table-wrap"><table class="adm-table">
          <thead><tr><th>${esc(t('col_user'))}</th><th>${esc(t('col_status'))}</th>
            <th>${esc(t('col_registered'))}</th><th>${esc(t('col_last_login'))}</th><th></th></tr></thead>
          <tbody id="admin-user-rows"></tbody></table></div>
          <div class="adm-pagination"><span id="admin-user-page-info">—</span><div id="admin-user-page-buttons"></div></div>
        </article>`;
      await loadUsers();
    } else if (usersTab === 'support-admins') {
      panel.innerHTML = `
        <div class="adm-filters">
          <div class="search-box"><span aria-hidden="true">⌕</span>
            <input id="support-admin-search" type="search" placeholder="${esc(t('admin_user_search_placeholder'))}"
                   aria-label="${esc(t('support_admin_search_aria'))}"></div>
        </div>
        <article class="adm-panel">
          <div class="adm-panel-head"><div><h2>${esc(t('adm_tab_support_admins'))}</h2>
            <p>${esc(t('support_admin_list_intro'))}</p></div></div>
          <div class="adm-table-wrap"><table class="adm-table">
            <thead><tr><th>${esc(t('col_user'))}</th><th>${esc(t('col_status'))}</th>
              <th>${esc(t('col_registered'))}</th><th>${esc(t('col_last_login'))}</th><th></th></tr></thead>
            <tbody id="support-admin-rows"></tbody></table></div>
          <div class="adm-pagination" id="support-admin-pagination"></div>
        </article>`;
      await loadSupportAdmins();
    } else {
      panel.innerHTML = `
        <div class="adm-filters">
          <select id="support-report-status" aria-label="${esc(t('support_status_filter_aria'))}">
            <option value="ALL">${esc(t('all_statuses'))}</option>
            <option value="OPEN">${esc(t('support_status_open'))}</option>
            <option value="RESOLVED">${esc(t('support_status_resolved'))}</option>
          </select>
        </div>
        <article class="adm-panel" id="support-report-panel">
          <div class="adm-panel-head"><div><h2>${esc(t('support_reports_title'))}</h2>
            <p>${esc(t('support_reports_intro'))}</p></div></div>
          <div class="adm-table-wrap"><table class="adm-table">
            <thead><tr><th>${esc(t('col_user'))}</th><th>${esc(t('col_subject'))}</th>
              <th>${esc(t('col_sent_at'))}</th><th>${esc(t('col_status'))}</th><th></th></tr></thead>
            <tbody id="support-report-rows"></tbody></table></div>
          <div class="adm-pagination" id="support-report-admin-pagination"></div>
        </article>`;
      await loadReports();
    }
  }

  const statusPill = user => (user.status === 'LOCKED' ? pill('bad', t('locked')) : pill('ok', t('active')));

  async function loadUsers(query = null, next = null) {
    const body = $('#admin-user-rows');
    if (!body) return;
    const search = query === null ? ($('#admin-user-search')?.value.trim() || '') : query;
    if (next !== null) page.users = next;
    try {
      const params = new URLSearchParams({
        q: search, page: String(page.users), per_page: '10',
        status: $('#admin-user-status').value, role: 'USER',
      });
      const data = await api(`/admin/users?${params}`);
      if (page.users > 1 && page.users > Math.max(data.pages, 1)) return loadUsers(search, Math.max(data.pages, 1));
      page.users = data.page;
      cacheUsers(data.items);
      body.innerHTML = data.items.length ? data.items.map(user => `<tr>
        <td><b class="adm-cell-strong">${esc(user.full_name)}</b><span class="adm-cell-sub">${esc(user.email)}</span></td>
        <td>${statusPill(user)}${user.role === 'SUPPORT_ADMIN' ? pill('info', t('support_admin')) : ''}${user.deletion_requested ? pill('warn', t('deletion_requested')) : ''}</td>
        <td class="adm-num">${esc(dateOnly(user.registration_date))}</td>
        <td class="adm-num">${esc(dateOnly(user.last_login))}</td>
        <td><button class="adm-row-menu" type="button" data-adm-user="${user.id}"
              aria-label="${esc(t('adm_open_user', { name: user.full_name }))}">⋮</button></td>
      </tr>`).join('') : emptyRow(5, t('no_users'), t('no_users_detail'));
      const pages = Math.max(data.pages, 1);
      $('#admin-user-page-info').textContent = t('admin_user_count', { total: data.total, page: data.page, pages });
      $('#admin-user-page-buttons').innerHTML = pager('admin-page', data.page, pages);
    } catch (error) {
      body.innerHTML = emptyRow(5, t('load_failed'), error.message);
    }
  }

  const userCache = new Map();
  const cacheUsers = items => items.forEach(user => userCache.set(String(user.id), user));

  function pager(attribute, current, pages) {
    return `<button data-${attribute}="${Math.max(1, current - 1)}" ${current <= 1 ? 'disabled' : ''}
              aria-label="${esc(t('previous_page'))}">‹</button>
            <button class="active" aria-current="page">${current}</button>
            <button data-${attribute}="${Math.min(pages, current + 1)}" ${current >= pages ? 'disabled' : ''}
              aria-label="${esc(t('next_page'))}">›</button>`;
  }

  async function loadSupportAdmins(next = null) {
    const body = $('#support-admin-rows');
    if (!body) return;
    if (next !== null) page.supportAdmins = next;
    try {
      const params = new URLSearchParams({
        q: $('#support-admin-search')?.value.trim() || '', role: 'SUPPORT_ADMIN',
        page: String(page.supportAdmins), per_page: '10',
      });
      const data = await api(`/admin/users?${params}`);
      page.supportAdmins = data.page;
      cacheUsers(data.items);
      const pages = Math.max(data.pages, 1);
      body.innerHTML = data.items.length ? data.items.map(user => `<tr>
        <td><b class="adm-cell-strong">${esc(user.full_name)}</b><span class="adm-cell-sub">${esc(user.email)}</span></td>
        <td>${statusPill(user)}</td>
        <td class="adm-num">${esc(dateOnly(user.registration_date))}</td>
        <td class="adm-num">${esc(dateOnly(user.last_login))}</td>
        <td><button class="adm-row-menu" type="button" data-adm-user="${user.id}"
              aria-label="${esc(t('adm_open_user', { name: user.full_name }))}">⋮</button></td>
      </tr>`).join('') : emptyRow(5, t('no_users'), t('no_users_detail'));
      $('#support-admin-pagination').innerHTML =
        `<span>${esc(t('admin_user_count', { total: data.total, page: data.page, pages }))}</span><div>${pager('support-page', data.page, pages)}</div>`;
    } catch (error) {
      body.innerHTML = emptyRow(5, t('load_failed'), error.message);
    }
  }

  async function loadReports(next = null) {
    const body = $('#support-report-rows');
    if (!body) return;
    if (next !== null) page.reports = next;
    try {
      const params = new URLSearchParams({
        status: $('#support-report-status')?.value || 'ALL',
        page: String(page.reports), per_page: '10',
      });
      const data = await api(`/admin/support-reports?${params}`);
      page.reports = data.page;
      reportCache.clear();
      data.items.forEach(item => reportCache.set(String(item.id), item));
      const pages = Math.max(data.pages, 1);
      body.innerHTML = data.items.length ? data.items.map(item => `<tr>
        <td><b class="adm-cell-strong">${esc(item.user?.full_name || '—')}</b>
            <span class="adm-cell-sub">${esc(item.user?.email || '')}</span></td>
        <td><b class="adm-cell-strong">${esc(item.subject)}</b></td>
        <td class="adm-num">${esc(dateTime(item.created_at))}</td>
        <td>${item.status === 'RESOLVED' ? pill('ok', t('support_status_resolved')) : pill('warn', t('support_status_open'))}</td>
        <td><button class="adm-row-menu" type="button" data-adm-report="${item.id}"
              aria-label="${esc(t('adm_open_report'))}">⋮</button></td>
      </tr>`).join('') : emptyRow(5, t('no_admin_support_reports'), t('no_admin_support_reports_detail'));
      $('#support-report-admin-pagination').innerHTML =
        `<span>${esc(t('support_report_count', { total: data.total, page: data.page, pages }))}</span><div>${pager('report-page', data.page, pages)}</div>`;
    } catch (error) {
      body.innerHTML = emptyRow(5, t('load_failed'), error.message);
    }
  }

  const reportCache = new Map();

  /* --------------------------------------------------------------- drawer */

  function openDrawer(title, subtitle, sections) {
    closeDrawer();
    const backdrop = document.createElement('div');
    backdrop.className = 'adm-drawer-backdrop';
    backdrop.id = 'adm-drawer-backdrop';
    const drawer = document.createElement('aside');
    drawer.className = 'adm-drawer';
    drawer.id = 'adm-drawer';
    drawer.setAttribute('role', 'dialog');
    drawer.setAttribute('aria-modal', 'true');
    drawer.setAttribute('aria-label', title);
    drawer.innerHTML = `
      <div class="adm-drawer-head">
        <div><h2>${esc(title)}</h2>${subtitle ? `<small>${esc(subtitle)}</small>` : ''}</div>
        <button class="close-btn" type="button" data-adm-drawer-close aria-label="${esc(t('close'))}">×</button>
      </div>${sections}`;
    document.body.append(backdrop, drawer);
    applySizes(drawer);
    backdrop.addEventListener('click', closeDrawer);
    document.addEventListener('keydown', escapeDrawer);
    (drawer.querySelector('button:not([data-adm-drawer-close])') || drawer.querySelector('[data-adm-drawer-close]')).focus();
  }

  function escapeDrawer(event) {
    if (event.key === 'Escape') closeDrawer();
  }

  function closeDrawer() {
    $('#adm-drawer')?.remove();
    $('#adm-drawer-backdrop')?.remove();
    document.removeEventListener('keydown', escapeDrawer);
  }

  function openUserDrawer(id) {
    const user = userCache.get(String(id));
    if (!user) return;
    const canErase = Boolean(user.deletion_requested);
    const primary = isPrimary();
    const facts = [
      [t('col_status'), user.status === 'LOCKED' ? t('locked') : t('active')],
      [t('adm_role'), user.role === 'SUPPORT_ADMIN' ? t('support_admin') : t('adm_role_user')],
      [t('col_registered'), dateOnly(user.registration_date)],
      [t('col_last_login'), user.last_login ? dateTime(user.last_login) : t('adm_never_logged_in')],
      [t('adm_deletion_requested'), user.deletion_requested ? dateOnly(user.deletion_requested) : t('adm_no')],
    ];
    openDrawer(user.full_name, `${user.email} · #${user.id}`, `
      <div class="adm-drawer-section">
        <dl class="adm-kv">${facts.map(([label, value]) =>
          `<div class="adm-kv-row"><dt>${esc(label)}</dt><dd>${esc(value)}</dd></div>`).join('')}</dl>
      </div>
      ${user.role === 'USER' ? `<div class="adm-drawer-section">
        <h3>${esc(t('adm_support_actions'))}</h3>
        <div class="adm-drawer-actions">
          <button type="button" data-adm-action="${user.status === 'LOCKED' ? 'unlock' : 'lock'}" data-adm-id="${user.id}">
            ${esc(user.status === 'LOCKED' ? t('unlock') : t('lock'))}</button>
          <button type="button" data-adm-action="reset" data-adm-id="${user.id}">${esc(t('reset_password'))}</button>
        </div>
      </div>` : ''}
      ${primary ? `<div class="adm-drawer-section">
        <h3>${esc(t('adm_admin_actions'))}</h3>
        <div class="adm-drawer-actions">
          ${user.can_manage_role ? `<button type="button" data-adm-action="role" data-adm-id="${user.id}"
              data-adm-role="${user.role === 'SUPPORT_ADMIN' ? 'USER' : 'SUPPORT_ADMIN'}">
              ${esc(user.role === 'SUPPORT_ADMIN' ? t('revoke_admin') : t('grant_support_admin'))}</button>` : ''}
          ${user.role === 'USER' ? `
            <button type="button" class="danger" data-adm-action="erase" data-adm-id="${user.id}" ${canErase ? '' : 'disabled'}>
              ${esc(t('execute_erasure'))}</button>
            ${canErase ? '' : `<p class="adm-action-why">${esc(t('adm_erase_needs_request'))}</p>`}
            <button type="button" class="danger" data-adm-action="violation-delete" data-adm-id="${user.id}">
              ${esc(t('delete_violation'))}</button>` : ''}
        </div>
      </div>` : ''}
      <div class="adm-drawer-section">
        ${noSource(t('adm_privacy_title'), t('adm_privacy_note'))}
      </div>`);
  }

  function openReportDrawer(id) {
    const report = reportCache.get(String(id));
    if (!report) return;
    const resolved = report.status === 'RESOLVED';
    openDrawer(report.subject, `${report.user?.full_name || ''} · ${dateTime(report.created_at)}`, `
      <div class="adm-drawer-section">
        <dl class="adm-kv">
          <div class="adm-kv-row"><dt>${esc(t('col_status'))}</dt>
            <dd>${resolved ? pill('ok', t('support_status_resolved')) : pill('warn', t('support_status_open'))}</dd></div>
          <div class="adm-kv-row"><dt>${esc(t('col_sent_at'))}</dt><dd>${esc(dateTime(report.created_at))}</dd></div>
        </dl>
      </div>
      <div class="adm-drawer-section">
        <h3>${esc(t('col_message'))}</h3>
        <p class="adm-drawer-msg">${esc(report.message)}</p>
      </div>
      <div class="adm-drawer-section">
        <div class="adm-drawer-actions">
          <button type="button" data-adm-action="report-status" data-adm-id="${report.id}"
                  data-adm-next="${resolved ? 'OPEN' : 'RESOLVED'}">
            ${esc(resolved ? t('reopen_report') : t('mark_resolved'))}</button>
        </div>
      </div>`);
  }

  /* ------------------------------------------------------------- confirms */

  function confirmDialog({ title, message, action, phrase = '', danger = true }) {
    return new Promise(resolve => {
      const dialog = $('#adm-confirm-dialog');
      $('#adm-confirm-title').textContent = title;
      $('#adm-confirm-message').textContent = message;
      const field = $('#adm-confirm-field');
      const input = $('#adm-confirm-input');
      const submit = $('#adm-confirm-submit');
      field.classList.toggle('hidden', !phrase);
      $('#adm-confirm-phrase').textContent = phrase;
      input.value = '';
      submit.textContent = action;
      submit.className = danger ? 'danger-btn' : 'primary-btn';
      submit.disabled = Boolean(phrase);
      const onInput = () => { submit.disabled = input.value.trim() !== phrase; };
      if (phrase) input.addEventListener('input', onInput);
      dialog.showModal();
      dialog.addEventListener('close', () => {
        if (phrase) input.removeEventListener('input', onInput);
        resolve(dialog.returnValue === 'confirm');
      }, { once: true });
    });
  }

  function showSecret(title, note, secret) {
    const dialog = $('#adm-secret-dialog');
    $('#adm-secret-title').textContent = title;
    $('#adm-secret-note').textContent = note;
    $('#adm-secret-value').textContent = secret;
    dialog.showModal();
  }

  async function runUserAction(kind, id, extra) {
    const user = userCache.get(String(id));
    const name = user ? user.full_name : '';
    if (kind === 'erase' && !await confirmDialog({
      title: t('adm_confirm_erase_title'), message: t('confirm_erasure', { name }),
      action: t('execute_erasure'), phrase: t('adm_confirm_phrase_erase'),
    })) return;
    if (kind === 'violation-delete' && !await confirmDialog({
      title: t('adm_confirm_violation_title'), message: t('confirm_violation_delete', { name }),
      action: t('delete_violation'), phrase: t('adm_confirm_phrase_erase'),
    })) return;
    try {
      if (kind === 'lock' || kind === 'unlock') {
        await api(`/admin/users/${id}/${kind}`, { method: 'POST' });
        toast(kind === 'lock' ? t('user_locked') : t('user_unlocked'));
      } else if (kind === 'reset') {
        const data = await api(`/admin/users/${id}/reset-password`, { method: 'POST' });
        showSecret(t('temporary_password'), t('adm_temp_password_note', { name }), data.temporary_password);
      } else if (kind === 'erase') {
        await api(`/admin/users/${id}`, { method: 'DELETE' });
        toast(t('erasure_done'));
      } else if (kind === 'role') {
        await api(`/admin/users/${id}/role`, { method: 'PATCH', body: JSON.stringify({ role: extra }) });
        toast(t(extra === 'SUPPORT_ADMIN' ? 'admin_granted' : 'admin_revoked'));
      } else if (kind === 'violation-delete') {
        await api(`/admin/users/${id}/violation`, { method: 'DELETE' });
        toast(t('violation_deleted'));
      }
      closeDrawer();
      await (usersTab === 'support-admins' ? loadSupportAdmins() : loadUsers());
    } catch (error) {
      toast(t('action_failed'), error.message);
    }
  }

  /* --------------------------------------------------------- transactions */

  async function renderTransactions(target) {
    const data = await systemStatus();
    const transactions = data.transactions;
    const imports = data.imports;
    const manual = transactions.total - transactions.from_import;
    const share = total => (transactions.total ? Math.round((total / transactions.total) * 100) : 0);

    target.innerHTML = heading(t('adm_tx_kicker'), t('adm_tx_title'), t('adm_tx_note')) + `
      <div class="adm-banner info">
        <span class="adm-banner-mark" aria-hidden="true">i</span>
        <div><b>${esc(t('adm_tx_privacy_title'))}</b><p>${esc(t('adm_tx_privacy_note'))}</p></div>
      </div>
      <div class="adm-tiles">
        ${tile({ label: t('adm_tx_total'), icon: '⇄', iconTone: 'blue', value: num(transactions.total), detail: t('adm_tx_total_detail') })}
        ${tile({ label: t('adm_tx_from_import'), icon: '⇧', iconTone: 'violet', value: `${share(transactions.from_import)}%`, detail: t('adm_tx_rows', { count: num(transactions.from_import) }) })}
        ${tile({ label: t('adm_tx_manual'), icon: '✎', iconTone: 'mint', value: `${share(manual)}%`, detail: t('adm_tx_rows', { count: num(manual) }) })}
        ${tile({ label: t('adm_tx_uncategorised'), icon: '?', iconTone: 'coral', value: num(transactions.uncategorised), detail: t('adm_tx_uncategorised_detail') })}
      </div>
      <div class="adm-grid-2">
        <article class="adm-panel">
          <div class="adm-panel-head"><div><h2>${esc(t('adm_tx_by_source'))}</h2></div></div>
          <div class="adm-panel-body">${barList(transactions.by_source, transactions.total)}</div>
        </article>
        <article class="adm-panel">
          <div class="adm-panel-head"><div><h2>${esc(t('adm_tx_integrity'))}</h2></div></div>
          <div class="adm-panel-body">
            <dl class="adm-kv">
              <div class="adm-kv-row"><dt>${esc(t('adm_import_error_rows'))}</dt><dd>${esc(num(imports.error_rows))}</dd></div>
              <div class="adm-kv-row"><dt>${esc(t('adm_batches_24h'))}</dt><dd>${esc(num(imports.batches_24h))}</dd></div>
              ${Object.entries(imports.batches_by_status).map(([key, value]) =>
                `<div class="adm-kv-row"><dt>${esc(tryT('adm_batch_status_' + key.toLowerCase(), key))}</dt><dd>${esc(num(value))}</dd></div>`).join('')}
            </dl>
          </div>
        </article>
      </div>
      <div class="adm-panel"><div class="adm-panel-body">
        ${noSource(t('adm_tx_no_series_title'), t('adm_tx_no_series_note'))}
      </div></div>`;
    applySizes(target);
    target.dataset.ready = '1';
  }

  function barList(mapping, total, toneFor = null) {
    const entries = Object.entries(mapping || {});
    if (!entries.length) return `<div class="adm-empty"><b>${esc(t('adm_no_data'))}</b><span>${esc(t('adm_no_data_detail'))}</span></div>`;
    const max = Math.max(1, total || Math.max(...entries.map(([, value]) => value)));
    return `<div class="adm-bars">${entries.map(([label, value]) => `
      <div class="adm-bar">
        <span>${esc(label)}</span>
        <span class="adm-bar-track"><i class="adm-bar-fill${toneFor ? ' ' + toneFor(label) : ''}" data-width="${Math.round((value / max) * 100)}"></i></span>
        <span class="adm-bar-value">${esc(num(value))}</span>
      </div>`).join('')}</div>`;
  }

  /* -------------------------------------------------------------- imports */

  async function renderImports(target) {
    target.innerHTML = heading(t('adm_imports_kicker'), t('adm_imports_title'), t('adm_imports_note')) + `
      <div class="adm-tabs" role="tablist">
        <button type="button" role="tab" class="active" data-adm-imports-tab="batches" aria-selected="true">${esc(t('adm_tab_batches'))}</button>
        <button type="button" role="tab" data-adm-imports-tab="config" aria-selected="false">${esc(t('adm_tab_import_config'))}</button>
      </div>
      <div id="adm-imports-panel"></div>`;
    target.dataset.ready = '1';
    await renderBatches();
  }

  async function renderBatches(next = null) {
    if (next !== null) page.batches = next;
    const panel = $('#adm-imports-panel');
    panel.innerHTML = `<article class="adm-panel">
      <div class="adm-panel-head"><div><h2>${esc(t('adm_tab_batches'))}</h2><p>${esc(t('adm_batches_note'))}</p></div></div>
      <div class="adm-table-wrap"><table class="adm-table">
        <thead><tr><th>${esc(t('adm_batch_id'))}</th><th>${esc(t('bank_template'))}</th>
          <th>${esc(t('error_rows'))}</th><th>${esc(t('col_status'))}</th><th>${esc(t('imported_at'))}</th></tr></thead>
        <tbody id="adm-batch-rows"></tbody></table></div>
      <div class="adm-pagination" id="adm-batch-pagination"></div></article>`;
    try {
      const data = await api(`/admin/import-batches?page=${page.batches}`);
      page.batches = data.page;
      const tone = { COMMITTED: 'ok', PREVIEW: 'info', REVERTED: 'neutral', FAILED: 'bad' };
      $('#adm-batch-rows').innerHTML = data.items.length ? data.items.map(batch => `<tr>
        <td class="adm-num">#${batch.id}</td>
        <td><b class="adm-cell-strong">${esc(batch.bank_code)}</b></td>
        <td class="adm-num">${batch.error_rows ? pill('warn', num(batch.error_rows)) : num(0)}</td>
        <td>${pill(tone[batch.status] || 'neutral', tryT('adm_batch_status_' + batch.status.toLowerCase(), batch.status))}
            ${batch.reverted_at ? `<span class="adm-cell-sub">${esc(dateTime(batch.reverted_at))}</span>` : ''}</td>
        <td class="adm-num">${esc(dateTime(batch.created_at))}</td>
      </tr>`).join('') : emptyRow(5, t('no_import_history'), t('no_import_history_detail'));
      const pages = Math.max(data.pages, 1);
      $('#adm-batch-pagination').innerHTML =
        `<span>${esc(t('import_history_count', { total: data.total, page: data.page, pages }))}</span><div>${pager('batch-page', data.page, pages)}</div>`;
    } catch (error) {
      $('#adm-batch-rows').innerHTML = emptyRow(5, t('load_failed'), error.message);
    }
  }

  async function renderImportConfig() {
    const panel = $('#adm-imports-panel');
    panel.innerHTML = `<article class="adm-panel">
      <div class="adm-panel-head"><div><h2>${esc(t('import_config_title'))}</h2>
        <p>${esc(t('adm_import_config_note'))}</p></div></div>
      <div class="adm-table-wrap"><table class="adm-table">
        <thead><tr><th>${esc(t('col_config_item'))}</th><th>${esc(t('col_config_detail'))}</th><th>${esc(t('col_status'))}</th></tr></thead>
        <tbody id="admin-import-rows"></tbody></table></div></article>`;
    try {
      const data = await api('/admin/import-config');
      const rows = [
        ...data.templates.map(item => ({ kind: 'template', id: item.id, label: `${item.bank_code} — ${item.name}`, detail: t('bank_template'), active: item.active })),
        ...data.rules.map(item => ({ kind: 'rule', id: item.id, label: t('adm_rule_priority', { priority: item.priority }), detail: item.pattern, active: item.active })),
      ];
      $('#admin-import-rows').innerHTML = rows.length ? rows.map(row => `<tr>
        <td><b class="adm-cell-strong">${esc(row.label)}</b></td>
        <td><span class="adm-cell-sub">${esc(row.detail)}</span></td>
        <td><button class="secondary-btn" type="button" data-admin-toggle="${row.kind}" data-admin-id="${row.id}"
              data-admin-active="${row.active ? '1' : '0'}">${esc(row.active ? t('on') : t('off'))}</button></td>
      </tr>`).join('') : emptyRow(3, t('no_template'), t('adm_import_config_note'));
    } catch (error) {
      $('#admin-import-rows').innerHTML = emptyRow(3, t('load_failed'), error.message);
    }
  }

  /* --------------------------------------------------------------- alerts */

  async function renderAlerts(target) {
    const data = await systemStatus();
    const alerts = data.alerts;
    const job = data.jobs.nightly_alerts;
    const health = jobHealth(job);
    const stale = !health.ok;

    target.innerHTML = heading(t('adm_alerts_kicker'), t('adm_alerts_title'), t('adm_alerts_note')) +
      (stale ? `<div class="adm-banner warn">
        <span class="adm-banner-mark" aria-hidden="true">!</span>
        <div><b>${esc(t('adm_job_degraded_title'))}</b>
          <p>${esc(t('adm_job_degraded_note', { status: health.label, at: job.last_run ? dateTime(job.last_run) : t('adm_never_run') }))}</p></div>
      </div>` : '') + `
      <div class="adm-tiles">
        ${tile({ label: t('adm_alerts_total'), icon: '◔', iconTone: 'blue', value: num(alerts.total), detail: t('adm_alerts_total_detail') })}
        ${tile({ label: t('adm_alerts_24h'), icon: '+', iconTone: 'violet', value: num(alerts.last_24h), detail: t('adm_alerts_24h_detail') })}
        ${tile({ label: t('adm_alerts_unread'), icon: '●', iconTone: 'coral', value: num(alerts.by_status.UNREAD || 0), detail: t('adm_alerts_unread_detail') })}
        ${tile({ label: t('nightly_job'), icon: '↻', iconTone: stale ? 'coral' : 'mint', state: dot(health.tone, health.label), value: job.last_run ? dateTime(job.last_run) : t('adm_never_run'), detail: t('last_run') })}
      </div>
      <div class="adm-grid-2">
        <article class="adm-panel">
          <div class="adm-panel-head"><div><h2>${esc(t('adm_alerts_by_kind'))}</h2>
            <p>${esc(t('adm_alerts_thresholds'))}</p></div></div>
          <div class="adm-panel-body">${barList(alerts.by_kind, alerts.total)}</div>
        </article>
        <article class="adm-panel">
          <div class="adm-panel-head"><div><h2>${esc(t('adm_alerts_by_status'))}</h2></div></div>
          <div class="adm-panel-body">${barList(alerts.by_status, alerts.total)}
            <div class="adm-legend"><span>${esc(t('adm_alerts_privacy'))}</span></div></div>
        </article>
      </div>`;
    applySizes(target);
    target.dataset.ready = '1';
  }

  /* ----------------------------------------------------------------- logs */

  async function renderLogs(target) {
    target.innerHTML = heading(t('adm_logs_kicker'), t('adm_logs_title'), t('adm_logs_note'),
      '') + `
      <div class="adm-tabs" role="tablist">
        ${LOG_TABS.map(tab => `<button type="button" role="tab" data-adm-log-tab="${tab}"
            aria-selected="${tab === logsTab}" class="${tab === logsTab ? 'active' : ''}">${esc(t('adm_log_tab_' + tab.toLowerCase()))}</button>`).join('')}
      </div>
      <div id="adm-logs-panel"></div>`;
    target.dataset.ready = '1';
    await renderLogsPanel();
  }

  async function renderLogsPanel(next = null) {
    const panel = $('#adm-logs-panel');
    if (logsTab === 'ERRORS') return renderErrorMonitor(panel);
    if (next !== null) page.logs = next;
    panel.innerHTML = `
      <div class="adm-filters">
        <div class="search-box"><span aria-hidden="true">⌕</span>
          <input id="adm-log-search" type="search" placeholder="${esc(t('adm_log_search_placeholder'))}"
                 aria-label="${esc(t('adm_log_search_placeholder'))}"></div>
        <select id="adm-log-severity" aria-label="${esc(t('adm_severity'))}">
          <option value="ALL">${esc(t('adm_severity_all'))}</option>
          <option value="CRITICAL">${esc(t('critical'))}</option>
          <option value="WARNING">${esc(t('warning'))}</option>
          <option value="INFO">${esc(t('adm_severity_info'))}</option>
        </select>
        <select id="adm-log-window" aria-label="${esc(t('adm_time_window'))}">
          <option value="">${esc(t('adm_window_all'))}</option>
          <option value="24">${esc(t('adm_window_24h'))}</option>
          <option value="168">${esc(t('adm_window_7d'))}</option>
        </select>
      </div>
      <article class="adm-panel"><div class="adm-table-wrap"><table class="adm-table">
        <thead><tr><th>${esc(t('adm_log_time'))}</th><th>${esc(t('adm_severity'))}</th>
          <th>${esc(t('adm_log_category'))}</th><th>${esc(t('adm_log_event'))}</th></tr></thead>
        <tbody id="adm-log-rows"></tbody></table></div>
        <div class="adm-pagination" id="adm-log-pagination"></div></article>`;
    await loadLogs();
  }

  const severityPill = severity => pill(
    severity === 'CRITICAL' ? 'bad' : severity === 'WARNING' ? 'warn' : 'neutral',
    severity === 'CRITICAL' ? t('critical') : severity === 'WARNING' ? t('warning') : t('adm_severity_info'));

  async function loadLogs() {
    const body = $('#adm-log-rows');
    if (!body) return;
    try {
      const params = new URLSearchParams({
        page: String(page.logs), per_page: '25', category: logsTab,
        severity: $('#adm-log-severity')?.value || 'ALL',
        q: $('#adm-log-search')?.value.trim() || '',
      });
      const window_ = $('#adm-log-window')?.value;
      if (window_) params.set('hours', window_);
      const data = await api(`/admin/system-logs?${params}`);
      page.logs = data.page;
      body.innerHTML = data.items.length ? data.items.map(row => `<tr>
        <td class="adm-num">${esc(dateTime(row.created_at))}</td>
        <td>${severityPill(row.severity)}</td>
        <td>${pill('neutral', tryT('adm_log_tab_' + row.category.toLowerCase(), row.category))}</td>
        <td><b class="adm-cell-strong">${esc(describeAction(row.action))}</b>
            <span class="adm-cell-sub">${esc(row.action)}</span></td>
      </tr>`).join('') : emptyRow(4, t('no_audit_logs'), t('no_audit_logs_detail'));
      const pages = Math.max(data.pages, 1);
      $('#adm-log-pagination').innerHTML =
        `<span>${esc(t('adm_log_count', { total: data.total, page: data.page, pages }))}</span><div>${pager('log-page', data.page, pages)}</div>`;
    } catch (error) {
      body.innerHTML = emptyRow(4, t('load_failed'), error.message);
    }
  }

  async function renderErrorMonitor(panel) {
    panel.innerHTML = `
      <div class="adm-filters">
        <select id="adm-error-state" aria-label="${esc(t('col_status'))}">
          <option value="ALL">${esc(t('all_statuses'))}</option>
          <option value="OPEN">${esc(t('adm_error_open'))}</option>
          <option value="HANDLED">${esc(t('adm_error_handled'))}</option>
        </select>
      </div>
      <article class="adm-panel">
        <div class="adm-panel-head"><div><h2>${esc(t('adm_error_monitor'))}</h2>
          <p id="adm-error-note"></p></div></div>
        <div class="adm-table-wrap"><table class="adm-table">
          <thead><tr><th>${esc(t('adm_log_time'))}</th><th>${esc(t('adm_http_code'))}</th>
            <th>${esc(t('adm_endpoint'))}</th><th>${esc(t('adm_occurrences'))}</th>
            <th>${esc(t('col_status'))}</th><th></th></tr></thead>
          <tbody id="adm-error-rows"></tbody></table></div>
      </article>`;
    await loadErrors();
  }

  async function loadErrors() {
    const body = $('#adm-error-rows');
    if (!body) return;
    try {
      const data = await api(`/admin/errors?handled=${$('#adm-error-state')?.value || 'ALL'}`);
      $('#adm-error-note').textContent = t('adm_error_scope', { at: dateTime(data.since) });
      body.innerHTML = data.items.length ? data.items.map(group => `<tr>
        <td class="adm-num">${esc(dateTime(group.last_seen))}</td>
        <td>${pill(group.status >= 500 ? 'bad' : 'warn', String(group.status))}</td>
        <td><b class="adm-cell-strong">${esc(group.method)} ${esc(group.rule)}</b>
            <span class="adm-cell-sub">${esc(group.message || t('adm_no_message'))}</span></td>
        <td class="adm-num">${esc(num(group.count))}</td>
        <td>${group.handled ? pill('neutral', t('adm_error_handled')) : pill('info', t('adm_error_open'))}</td>
        <td><button class="secondary-btn" type="button" data-adm-error-toggle
              data-adm-method="${esc(group.method)}" data-adm-rule="${esc(group.rule)}"
              data-adm-status="${group.status}" data-adm-handled="${group.handled ? '0' : '1'}">
              ${esc(group.handled ? t('adm_mark_open') : t('adm_mark_handled'))}</button></td>
      </tr>`).join('') : emptyRow(6, t('adm_no_errors'), t('adm_no_errors_detail'));
    } catch (error) {
      body.innerHTML = emptyRow(6, t('load_failed'), error.message);
    }
  }

  /* ------------------------------------------------------------- settings */

  async function renderSettings(target) {
    const data = await systemStatus(true);
    const database = data.database;

    target.innerHTML = heading(t('adm_settings_kicker'), t('adm_settings_title'), t('adm_settings_note')) + `
      <div class="adm-banner info">
        <span class="adm-banner-mark" aria-hidden="true">i</span>
        <div><b>${esc(t('adm_settings_readonly_title'))}</b><p>${esc(t('adm_settings_readonly_note'))}</p></div>
      </div>
      <article class="adm-panel">
        <div class="adm-panel-head"><div><h2>${esc(t('adm_settings_limits'))}</h2></div></div>
        <div class="adm-panel-body">
          ${settingRow(t('adm_setting_upload'), t('adm_setting_upload_note'), '5 MB')}
          ${settingRow(t('adm_setting_avatar'), 'NFR-07', '2 MB')}
          ${settingRow(t('adm_setting_formats'), t('adm_setting_formats_note'), '.csv · .xlsx')}
          ${settingRow(t('adm_setting_auth_rate'), 'NFR-04', t('adm_per_minute', { count: 10 }))}
          ${settingRow(t('adm_setting_session'), 'NFR-03', t('adm_minutes', { count: 30 }))}
        </div>
      </article>
      <div class="adm-grid-2">
        <article class="adm-panel">
          <div class="adm-panel-head"><div><h2>${esc(t('adm_db_status'))}</h2></div>
            <button class="secondary-btn" type="button" data-adm-refresh>${esc(t('adm_check_connection'))}</button></div>
          <div class="adm-panel-body">
            <dl class="adm-kv">
              <div class="adm-kv-row"><dt>${esc(t('adm_db_connection'))}</dt>
                <dd>${dot(database.connected ? 'ok' : 'bad', database.connected ? t('adm_state_connected') : t('adm_state_down'))}</dd></div>
              <div class="adm-kv-row"><dt>${esc(t('adm_db_engine'))}</dt><dd>${esc(database.version || database.dialect || '—')}</dd></div>
              <div class="adm-kv-row"><dt>${esc(t('adm_db_size'))}</dt><dd>${esc(bytes(database.size_bytes))}</dd></div>
              <div class="adm-kv-row"><dt>${esc(t('adm_db_rows'))}</dt><dd>${esc(num(database.rows))}</dd></div>
              <div class="adm-kv-row"><dt>${esc(t('adm_db_response'))}</dt><dd>${esc(database.response_ms ?? '—')} ms</dd></div>
            </dl>
          </div>
        </article>
        <article class="adm-panel">
          <div class="adm-panel-head"><div><h2>${esc(t('adm_db_tables'))}</h2></div></div>
          <div class="adm-panel-body"><dl class="adm-kv">
            ${database.tables.map(table => `<div class="adm-kv-row"><dt>${esc(table.name)}</dt><dd>${esc(num(table.rows))}</dd></div>`).join('')}
          </dl></div>
        </article>
      </div>
      <article class="adm-panel"><div class="adm-panel-body">
        ${noSource(t('adm_backup_title'), t('adm_backup_note'))}
      </div></article>`;
    target.dataset.ready = '1';
  }

  const settingRow = (label, note, value) => `
    <div class="adm-field">
      <span class="adm-field-label"><b>${esc(label)}</b><small>${esc(note)}</small></span>
      <span class="adm-field-note">${esc(value)}</span>
    </div>`;

  /* -------------------------------------------------------------- events */

  function onConsoleClick(event) {
    const link = event.target.closest('[data-adm-view]');
    if (link) { event.preventDefault(); navigate(link.dataset.admView); return; }

    const go = event.target.closest('[data-adm-go]');
    if (go) { navigate(go.dataset.admGo); return; }

    if (event.target.closest('[data-adm-refresh]')) { status = null; render(view); return; }

    const usersTabButton = event.target.closest('[data-adm-users-tab]');
    if (usersTabButton) {
      usersTab = usersTabButton.dataset.admUsersTab;
      $$('[data-adm-users-tab]').forEach(button => {
        const active = button === usersTabButton;
        button.classList.toggle('active', active);
        button.setAttribute('aria-selected', String(active));
      });
      renderUsersTab();
      return;
    }

    const importsTabButton = event.target.closest('[data-adm-imports-tab]');
    if (importsTabButton) {
      $$('[data-adm-imports-tab]').forEach(button => {
        const active = button === importsTabButton;
        button.classList.toggle('active', active);
        button.setAttribute('aria-selected', String(active));
      });
      if (importsTabButton.dataset.admImportsTab === 'config') renderImportConfig(); else renderBatches(1);
      return;
    }

    const logTabButton = event.target.closest('[data-adm-log-tab]');
    if (logTabButton) {
      logsTab = logTabButton.dataset.admLogTab;
      page.logs = 1;
      $$('[data-adm-log-tab]').forEach(button => {
        const active = button === logTabButton;
        button.classList.toggle('active', active);
        button.setAttribute('aria-selected', String(active));
      });
      renderLogsPanel();
      return;
    }

    const userButton = event.target.closest('[data-adm-user]');
    if (userButton) { openUserDrawer(userButton.dataset.admUser); return; }

    const reportButton = event.target.closest('[data-adm-report]');
    if (reportButton) { openReportDrawer(reportButton.dataset.admReport); return; }

    const paged = event.target.closest('[data-admin-page],[data-support-page],[data-report-page],[data-log-page],[data-batch-page]');
    if (paged) {
      const set = paged.dataset;
      if (set.adminPage) loadUsers(null, Number(set.adminPage));
      else if (set.supportPage) loadSupportAdmins(Number(set.supportPage));
      else if (set.reportPage) loadReports(Number(set.reportPage));
      else if (set.logPage) { page.logs = Number(set.logPage); loadLogs(); }
      else if (set.batchPage) renderBatches(Number(set.batchPage));
      return;
    }

    const toggle = event.target.closest('[data-admin-toggle]');
    if (toggle) { toggleImportConfig(toggle); return; }

    const errorToggle = event.target.closest('[data-adm-error-toggle]');
    if (errorToggle) { toggleErrorState(errorToggle); return; }
  }

  function onConsoleChange(event) {
    if (event.target.id === 'admin-user-status') { page.users = 1; loadUsers(); }
    if (event.target.id === 'support-report-status') { page.reports = 1; loadReports(); }
    if (event.target.id === 'adm-log-severity' || event.target.id === 'adm-log-window') { page.logs = 1; loadLogs(); }
    if (event.target.id === 'adm-error-state') loadErrors();
  }

  function onConsoleInput(event) {
    const debounce = handler => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(handler, 250);
    };
    if (event.target.id === 'admin-user-search') debounce(() => loadUsers(event.target.value.trim(), 1));
    if (event.target.id === 'support-admin-search') debounce(() => loadSupportAdmins(1));
    if (event.target.id === 'adm-log-search') debounce(() => { page.logs = 1; loadLogs(); });
  }

  async function toggleImportConfig(button) {
    button.disabled = true;
    try {
      await api(`/admin/import-config/${button.dataset.adminToggle}/${button.dataset.adminId}`, {
        method: 'PATCH', body: JSON.stringify({ active: button.dataset.adminActive !== '1' }),
      });
      await renderImportConfig();
    } catch (error) {
      toast(t('update_failed'), error.message);
      button.disabled = false;
    }
  }

  async function toggleErrorState(button) {
    try {
      await api('/admin/errors', {
        method: 'PATCH',
        body: JSON.stringify({
          method: button.dataset.admMethod, rule: button.dataset.admRule,
          status: Number(button.dataset.admStatus), handled: button.dataset.admHandled === '1',
        }),
      });
      await loadErrors();
    } catch (error) {
      toast(t('update_failed'), error.message);
    }
  }

  document.addEventListener('click', async event => {
    if (event.target.closest('[data-adm-drawer-close]')) { closeDrawer(); return; }
    const action = event.target.closest('[data-adm-action]');
    if (!action) return;
    const kind = action.dataset.admAction;
    if (kind === 'report-status') {
      try {
        await api(`/admin/support-reports/${action.dataset.admId}`, {
          method: 'PATCH', body: JSON.stringify({ status: action.dataset.admNext }),
        });
        toast(t(action.dataset.admNext === 'RESOLVED' ? 'support_report_resolved' : 'support_report_reopened'));
        closeDrawer();
        await loadReports();
      } catch (error) {
        toast(t('support_report_update_failed'), error.message);
      }
      return;
    }
    await runUserAction(kind, action.dataset.admId, action.dataset.admRole);
  });

  window.addEventListener('languagechange', () => {
    if (!profile) return;
    buildShell();
    navigate(view);
  });

  window.addEventListener('hashchange', () => {
    if (!profile) return;
    const id = (location.hash.match(/^#admin\/(\w[\w-]*)/) || [])[1];
    if (id && id !== view) navigate(id);
  });

  window.AdminConsole = {
    start(app, currentProfile) {
      bridge = app;
      profile = currentProfile;
      status = null;
      userCache.clear();
      reportCache.clear();
      document.body.classList.add('admin-mode');
      $('#admin-console').classList.remove('hidden');
      buildShell();
      const requested = (location.hash.match(/^#admin\/(\w[\w-]*)/) || [])[1];
      navigate(requested || 'dashboard');
    },
    stop() {
      profile = null;
      status = null;
      closeDrawer();
      document.body.classList.remove('admin-mode');
      const root = $('#admin-console');
      root.classList.add('hidden');
      root.innerHTML = '';
      $$('.adm-view').forEach(section => delete section.dataset.ready);
    },
    refresh() {
      if (profile) { status = null; render(view); }
    },
    get active() { return Boolean(profile); },
  };
})();
