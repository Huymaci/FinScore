import re
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"


def _section(html, class_name):
    match = re.search(rf'<[^>]+class="[^"]*{class_name}[^"]*"[^>]*>(.*?)</(?:div|header)>', html, re.DOTALL)
    assert match, f"Missing section: {class_name}"
    return match.group(1)


def test_account_entry_and_preferences_are_consolidated_in_sidebar():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    topbar = _section(html, "top-actions")
    preferences_start = html.index('class="profile-preferences')
    preferences = html[preferences_start : html.index("</aside>", preferences_start)]

    assert 'data-action="accounts"' not in topbar
    assert "language-switcher" not in topbar
    assert "data-theme-toggle" not in topbar
    assert html.count('data-action="accounts"') == 1
    assert 'class="avatar profile-avatar"' in html
    assert 'class="profile-more"' in html
    assert preferences.count("data-theme-choice=") == 3
    assert set(re.findall(r'data-theme-choice="([^"]+)"', preferences)) == {"light", "dark", "system"}
    assert set(re.findall(r'data-language="([^"]+)"', preferences)) == {"vi", "en"}


def test_alerts_have_one_navigation_entry_only():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    app = (FRONTEND / "app.js").read_text(encoding="utf-8")

    assert html.count('data-view="alerts"') == 1
    assert 'class="icon-btn notification-btn"' not in html
    assert "$('.notification-btn" not in app


def test_logout_and_user_login_cannot_leave_admin_view_active():
    app = (FRONTEND / "app.js").read_text(encoding="utf-8")

    # Logout clears the active admin screen immediately, before the next account
    # authenticates. Bootstrap also validates a restored hash against the new role.
    assert "state.profile=null;applyAdminVisibility();navigate('dashboard')" in app
    assert "if(isAdmin()){navigate('admin');await loadAdmin();return}navigate(location.hash.slice(1)||'dashboard')" in app


def test_theme_controller_supports_and_tracks_system_preference():
    source = (FRONTEND / "theme.js").read_text(encoding="utf-8")

    assert "prefers-color-scheme: dark" in source
    assert "data-theme-choice" in source
    assert "get preference()" in source


def test_dynamic_api_content_uses_translation_helpers():
    app = (FRONTEND / "app.js").read_text(encoding="utf-8")
    i18n = (FRONTEND / "i18n.js").read_text(encoding="utf-8")

    assert "JSON không hợp lệ" not in app
    assert "displayCategoryName(category(x.category_id))" in app
    assert "displayCategoryText(item.category)" in app
    assert "const copy=alertCopy(x)" in app
    assert "#import-template" not in app
    assert "document.querySelectorAll(selector)" in i18n
    for key in (
        "invalid_json",
        "threshold_warning_explanation",
        "threshold_critical_explanation",
        "threshold_action",
        "burn_rate_explanation",
        "burn_rate_action",
        "template_vcb",
        "template_tcb",
        "template_mb",
    ):
        assert i18n.count(f"{key}:") == 2


def test_dashboard_header_and_data_refresh_in_realtime():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    app = (FRONTEND / "app.js").read_text(encoding="utf-8")
    i18n = (FRONTEND / "i18n.js").read_text(encoding="utf-8")

    assert 'id="dashboard-month-label"' in html
    assert html.count("data-month-step=") == 2
    assert "setInterval(renderLiveHeader,60000)" in app
    assert "setInterval(refreshRealtimeData,60000)" in app
    assert "document.hidden" in app
    assert "month:localMonthValue()" in app
    for key in ("greeting_morning", "greeting_afternoon", "greeting_evening", "previous_month", "next_month"):
        assert i18n.count(f"{key}:") == 2


def test_admin_user_list_is_paginated_and_search_resets_to_first_page():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    app = (FRONTEND / "app.js").read_text(encoding="utf-8")
    i18n = (FRONTEND / "i18n.js").read_text(encoding="utf-8")

    assert 'id="admin-user-page-info"' in html
    assert 'id="admin-user-page-buttons"' in html
    assert "per_page:'10'" in app
    assert "data-admin-page" in app
    assert "loadAdminUsers(value,1)" in app
    assert 'id="admin-user-status"' in html
    assert 'id="admin-user-role"' not in html
    assert 'id="support-admin-panel"' in html
    assert 'id="support-admin-search"' in html
    assert "role:'USER'" in app
    assert "role:'SUPPORT_ADMIN'" in app
    assert "status:$('#admin-user-status').value" in app
    assert "data-admin-action=\"violation-delete\"" in app
    for key in ("admin_user_count", "previous_page", "next_page"):
        assert i18n.count(f"{key}:") == 2


def test_import_history_calls_transaction_removal_by_clear_user_facing_name():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    app = (FRONTEND / "app.js").read_text(encoding="utf-8")
    i18n = (FRONTEND / "i18n.js").read_text(encoding="utf-8")

    assert 'id="remove-import-dialog" class="confirm-dialog"' in html
    assert 'id="remove-import-confirm" value="confirm"' in html
    assert "t('remove_imported_transactions')" in app
    assert "function confirmImportTransactionRemoval()" in app
    assert "await confirmImportTransactionRemoval()" in app
    assert "confirm(t('remove_import_confirm'))" not in app
    assert "t('remove_import_success')" in app
    assert "await Promise.all([refreshCore(),loadImportHistory()])" in app
    assert "data-delete-import-transactions" in app
    assert "api(`/imports/${button.dataset.deleteImportTransactions}/transactions`,{method:'DELETE'}" in app
    assert "undo_deadline" not in app
    assert "can_undo" not in app
    for key in (
        "remove_imported_transactions",
        "remove_import_title",
        "remove_import_action",
        "remove_import_confirm",
        "remove_import_success",
        "remove_import_failed",
        "import_transactions_removed",
    ):
        assert i18n.count(f"{key}:") == 2


def test_budget_deletion_asks_through_the_styled_dialog_not_a_browser_confirm():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    app = (FRONTEND / "app.js").read_text(encoding="utf-8")
    i18n = (FRONTEND / "i18n.js").read_text(encoding="utf-8")

    assert 'id="delete-budget-dialog" class="confirm-dialog"' in html
    assert 'id="delete-budget-confirm" value="confirm"' in html
    assert "function confirmBudgetDeletion(name)" in app
    assert "await confirmBudgetDeletion(removeBudget.dataset.budgetName)" in app
    # The browser confirm() the dialog replaces must not creep back in.
    assert "confirm(t('delete_budget_confirm'))" not in app
    assert "data-delete-budget" in app
    assert "api(`/budgets/${removeBudget.dataset.deleteBudget}`,{method:'DELETE'}" in app
    for key in ("delete_budget", "delete_budget_named", "delete_budget_title", "delete_budget_action", "delete_budget_confirm", "deleted_budget", "budget_delete_failed"):
        assert i18n.count(f"{key}:") == 2, key


def test_import_history_is_kept_until_the_user_deletes_it():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    app = (FRONTEND / "app.js").read_text(encoding="utf-8")
    i18n = (FRONTEND / "i18n.js").read_text(encoding="utf-8")

    # No automatic expiry is promised anywhere any more.
    assert "import_history_retention_note" not in i18n
    assert "remove_import_deadline" not in i18n
    assert "history_expires_at" not in app

    # Entries are ticked in the table and deleted from one button above it.
    assert 'id="delete-selected-history"' in html
    assert 'id="delete-history-dialog"' in html
    assert 'id="delete-history-keep" value="history"' in html
    assert 'id="delete-history-all" value="all"' in html
    assert "data-import-history-select" in app
    assert 'id="import-history-select-all"' in app
    assert "data-delete-import-history" not in app
    assert "/imports/history?ids=${ids.join(',')}" in app

    # The bulk delete must not wear the same colour as the row button that
    # removes imported transactions.
    assert 'class="ink-btn hidden" type="button" id="delete-selected-history"' in html
    assert 'class="danger-outline-btn" data-delete-import-transactions' in app

    for key in (
        "delete_import_history",
        "delete_import_history_title",
        "delete_selected_history",
        "delete_selected_history_count",
        "delete_selected_history_confirm",
        "delete_history_only",
        "delete_history_and_transactions",
        "import_history_deleted",
        "import_history_delete_failed",
    ):
        assert i18n.count(f"{key}:") == 2


def test_import_preview_has_per_row_approval_rejection_notes_and_reset():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    app = (FRONTEND / "app.js").read_text(encoding="utf-8")
    styles = (FRONTEND / "styles.css").read_text(encoding="utf-8")
    i18n = (FRONTEND / "i18n.js").read_text(encoding="utf-8")

    assert '<dialog class="preview-panel" id="import-preview"' in html
    assert "if(!box.open)box.showModal()" in app
    assert "if(preview.open)preview.close()" in app
    assert "importPreviewBox.addEventListener('cancel'" in app
    assert "event.target===importPreviewBox" in app
    assert "event.clientX<bounds.left" in app
    assert "$('#cancel-import-preview',importPreviewBox)?.click()" in app
    assert 'data-import-decision="${row.row_number}"' in app
    assert 'data-import-note="${row.row_number}"' in app
    assert "const errorEntries=(p.errors||[]).map" in app
    assert 'class="import-preview-row import-error-row"' in app
    assert "${t('cannot_import')}" in app
    assert "left.rowNumber-right.rowNumber" in app
    assert "async function loadImportPreviewPage(page)" in app
    assert "/preview?page=${page}&per_page=25" in app
    assert 'data-import-page="${review.page-1}"' in app
    assert "captureImportPageEdits()" in app
    assert "state.importReview.decisions" in app
    assert "fileTotal:state.importPreview.new+state.importPreview.duplicate+state.importPreview.error" in app
    assert "total:state.importReview.fileTotal" in app
    assert ".import-pagination" in styles
    assert 'id="reset-import-edits"' in app
    assert "state.importReview.decisions={}" in app
    assert "state.importReview.categoryOverrides={}" in app
    assert "state.importReview.notes={}" in app
    assert "decisionButton.dataset.decision==='KEEP'?'REJECT':'KEEP'" in app
    assert "category_overrides:categoryOverrides,notes" in app
    assert "decision-list" not in app
    assert ".import-decision-btn.accepted" in styles
    assert ".import-decision-btn.rejected" in styles
    for key in (
        "approve_import",
        "reject_import",
        "cannot_import",
        "invalid_row",
        "row_note",
        "cancel_edits",
        "edits_reset",
        "selected_for_import",
        "preview_page",
        "preview_page_failed",
    ):
        assert i18n.count(f"{key}:") == 2


def test_user_support_reports_are_wired_for_both_the_sender_and_the_admin_desk():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    app = (FRONTEND / "app.js").read_text(encoding="utf-8")
    i18n = (FRONTEND / "i18n.js").read_text(encoding="utf-8")
    styles = (FRONTEND / "styles.css").read_text(encoding="utf-8")

    # Sender side: one entry point in the profile menu, one dialog that both
    # posts a report and lists the reports this user already sent.
    assert html.count('data-action="support"') == 1
    assert 'id="support-dialog"' in html
    assert '<textarea name="message"' in html
    assert 'id="support-report-list"' in html
    assert "function openSupportDialog()" in app
    assert "api('/support-reports',{method:'POST'" in app
    assert "api(`/support-reports?page=${page}`)" in app
    assert "data-own-report-page" in app

    # Admin side: the panel sits outside the primary-admin-only block because
    # /admin/support-reports is admin_required, so SUPPORT_ADMIN reads it too.
    panel = html.index('id="support-report-panel"')
    assert panel < html.index('class="dashboard-grid primary-admin-only"')
    assert "primary-admin-only" not in html[panel : html.index("</article>", panel)]
    assert 'id="support-report-rows"' in html
    assert 'id="support-report-status"' in html
    assert "api(`/admin/support-reports?${params}`)" in app
    assert "api(`/admin/support-reports/${reportAction.dataset.reportId}`,{method:'PATCH'" in app
    assert "loadAdminSupportReports(adminReportPage)]" in app
    assert '[data-action="support"]\').forEach(node=>node.classList.toggle(\'hidden\',admin))' in app
    assert ".support-report-item" in styles

    for key in (
        "support_kicker",
        "support_dialog_title",
        "support_dialog_intro",
        "send_report",
        "my_reports",
        "col_subject",
        "col_message",
        "col_sent_at",
        "support_subject_placeholder",
        "support_message_placeholder",
        "support_sent",
        "support_send_failed",
        "no_support_reports",
        "no_support_reports_detail",
        "support_status_open",
        "support_status_resolved",
        "support_report_count",
        "support_reports_kicker",
        "support_reports_title",
        "support_reports_intro",
        "support_status_filter_aria",
        "mark_resolved",
        "reopen_report",
        "support_report_resolved",
        "support_report_reopened",
        "support_report_update_failed",
        "no_admin_support_reports",
    ):
        assert i18n.count(f"{key}:") == 2, key
