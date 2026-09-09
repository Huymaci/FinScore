// Guided tour for a first-time user: spotlight one control at a time and move
// on when they click it. Kept deliberately dumb — the blocker swallows every
// click, so no step can fire the real action, open a dialog over the popover
// and derail the walkthrough. Copy lives here in both languages, the same way
// challengeCopy() does in app.js, so i18n.js does not grow ~40 keys.
(() => {
  'use strict';

  const STORAGE_PREFIX = 'smartfinance-tour-v1';
  const $ = (selector, root = document) => root.querySelector(selector);

  const COPY = {
    vi: {
      skip: 'Bỏ qua',
      back: 'Quay lại',
      next: 'Tiếp theo',
      done: 'Xong',
      of: '{current}/{total}',
      steps: {
        nav: ['Thanh điều hướng', 'Năm khu vực chính của ứng dụng: Tổng quan, Giao dịch, Ngân sách, Thử thách và Thống kê.'],
        add: ['Ghi giao dịch', 'Thêm nhanh một khoản thu hoặc chi vừa phát sinh.'],
        import: ['Nhập sao kê', 'Tải file sao kê ngân hàng để ghi hàng loạt giao dịch cùng lúc.'],
        deck: ['Thẻ tài khoản', 'Số dư từng tài khoản. Bấm biểu tượng con mắt để hiện hoặc ẩn số tiền.'],
        month: ['Chọn tháng', 'Toàn bộ số liệu trên trang này đổi theo tháng anh chọn ở đây.'],
        chart: ['Biểu đồ thu chi', 'Mười hai tháng gần nhất. Rê chuột vào từng cột để xem số thu và số chi của tháng đó.'],
        spend: ['Bốn danh mục chi nhiều nhất', 'Xem ngay tiền tháng này đi về đâu, kèm mức tăng giảm so với tháng trước.'],
        budget: ['Ngân sách đã chi', 'Phần trăm đã tiêu trên tổng hạn mức tháng, kèm số tiền còn lại.'],
        bell: ['Cảnh báo', 'Ứng dụng báo khi một danh mục sắp chạm hoặc đã vượt hạn mức.'],
        profile: ['Hồ sơ và cài đặt', 'Đổi thông tin, giao diện sáng tối, ngôn ngữ và đăng xuất. Muốn xem lại hướng dẫn này thì vào đây.'],
      },
    },
    en: {
      skip: 'Skip',
      back: 'Back',
      next: 'Next',
      done: 'Done',
      of: '{current}/{total}',
      steps: {
        nav: ['Main navigation', 'The five areas of the app: Dashboard, Transactions, Budgets, Challenges and Statistics.'],
        add: ['Record a transaction', 'Quickly add money you just spent or received.'],
        import: ['Import a statement', 'Upload a bank statement file to record many transactions at once.'],
        deck: ['Account cards', 'The balance of each account. Use the eye button to show or hide the amount.'],
        month: ['Pick a month', 'Everything on this page follows the month you choose here.'],
        chart: ['Income and spending', 'The last twelve months. Hover a column to see that month’s income and expense.'],
        spend: ['Top four categories', 'Where this month’s money went, with the change against last month.'],
        budget: ['Budget used', 'How much of this month’s total limit is spent, and what is left.'],
        bell: ['Alerts', 'The app warns you when a category is close to, or already over, its limit.'],
        profile: ['Profile and settings', 'Your details, light or dark theme, language and sign out. Replay this tour from here.'],
      },
    },
  };

  // Order matters: this is the order a new user meets the app in.
  const STEPS = [
    { key: 'nav', selector: '.topnav' },
    { key: 'add', selector: '[data-action="add-transaction"]' },
    { key: 'import', selector: '[data-action="import"]' },
    { key: 'deck', selector: '#dash-card-deck' },
    { key: 'month', selector: '#dashboard .month-switch' },
    { key: 'chart', selector: '#overview-chart' },
    { key: 'spend', selector: '#dashboard-spend' },
    { key: 'budget', selector: '.budget-usage-card' },
    { key: 'bell', selector: '#notif-bell' },
    { key: 'profile', selector: '#profile-trigger' },
  ];

  const GAP = 12;          // space between the spotlight and the popover
  const PAD = 8;           // how far the spotlight bleeds past the element
  const EDGE = 12;         // keep the popover this far from the viewport edge

  let steps = [];          // the steps whose target actually exists right now
  let index = 0;
  let blocker = null;
  let spot = null;
  let pop = null;
  let target = null;

  const copy = () => COPY[window.I18n && window.I18n.language === 'en' ? 'en' : 'vi'];
  const storageKey = () => `${STORAGE_PREFIX}:${(window.__tourUserId ?? 'anon')}`;

  function seen() {
    try { return localStorage.getItem(storageKey()) === 'done'; } catch { return false; }
  }
  function markSeen() {
    try { localStorage.setItem(storageKey(), 'done'); } catch { /* private mode: tour simply runs again */ }
  }

  // A step is only worth showing if its element is in the DOM and rendered.
  // Skipping the rest keeps the tour honest for, say, an account-less user
  // whose card deck is empty.
  function visible(element) {
    if (!element) return false;
    const box = element.getBoundingClientRect();
    return box.width > 0 && box.height > 0;
  }

  function start() {
    stop();
    steps = STEPS.filter(step => visible($(step.selector)));
    if (!steps.length) return;
    index = 0;
    build();
    render();
  }

  function maybeStart() {
    if (seen()) return;
    start();
  }

  function build() {
    blocker = document.createElement('div');
    blocker.className = 'tour-blocker';
    blocker.addEventListener('click', onBlockerClick);

    spot = document.createElement('div');
    spot.className = 'tour-spot';

    pop = document.createElement('div');
    pop.className = 'tour-pop';
    pop.setAttribute('role', 'dialog');
    pop.setAttribute('aria-modal', 'true');
    pop.setAttribute('aria-labelledby', 'tour-title');

    document.body.append(blocker, spot, pop);
    window.addEventListener('resize', place);
    window.addEventListener('scroll', place, true);
    document.addEventListener('keydown', onKey, true);
    window.addEventListener('languagechange', render);
  }

  function stop() {
    if (!blocker) return;
    window.removeEventListener('resize', place);
    window.removeEventListener('scroll', place, true);
    document.removeEventListener('keydown', onKey, true);
    window.removeEventListener('languagechange', render);
    blocker.remove(); spot.remove(); pop.remove();
    blocker = spot = pop = target = null;
  }

  function finish() {
    markSeen();
    stop();
  }

  function go(delta) {
    const next = index + delta;
    if (next < 0) return;
    if (next >= steps.length) { finish(); return; }
    index = next;
    render();
  }

  function render() {
    if (!pop) return;
    const text = copy();
    const step = steps[index];
    const [title, body] = text.steps[step.key];
    const last = index === steps.length - 1;
    target = $(step.selector);
    if (!visible(target)) { steps.splice(index, 1); if (!steps.length) { finish(); return; } if (index >= steps.length) index = steps.length - 1; render(); return; }

    pop.innerHTML = '';
    const counter = document.createElement('span');
    counter.className = 'tour-step';
    counter.textContent = text.of.replace('{current}', index + 1).replace('{total}', steps.length);
    const heading = document.createElement('h3');
    heading.id = 'tour-title';
    heading.textContent = title;
    const paragraph = document.createElement('p');
    paragraph.textContent = body;
    const actions = document.createElement('div');
    actions.className = 'tour-actions';
    const skip = button('tour-skip', text.skip, finish);
    actions.append(skip);
    if (index > 0) actions.append(button('tour-back', text.back, () => go(-1)));
    const next = button('tour-next', last ? text.done : text.next, () => go(1));
    actions.append(next);

    pop.append(counter, heading, paragraph, actions);
    target.scrollIntoView({ block: 'center', behavior: 'smooth' });
    place();
    next.focus({ preventScroll: true });
  }

  function button(className, label, onClick) {
    const element = document.createElement('button');
    element.type = 'button';
    element.className = className;
    element.textContent = label;
    element.addEventListener('click', onClick);
    return element;
  }

  // The spotlight tracks the element in viewport coordinates; both it and the
  // popover are position:fixed, so a scroll only needs the rect re-read.
  function place() {
    if (!target || !spot) return;
    const box = target.getBoundingClientRect();
    spot.style.top = `${box.top - PAD}px`;
    spot.style.left = `${box.left - PAD}px`;
    spot.style.width = `${box.width + PAD * 2}px`;
    spot.style.height = `${box.height + PAD * 2}px`;

    const popBox = pop.getBoundingClientRect();
    const below = box.bottom + PAD + GAP;
    const above = box.top - PAD - GAP - popBox.height;
    const top = below + popBox.height + EDGE <= window.innerHeight || above < EDGE ? below : above;
    let left = box.left + box.width / 2 - popBox.width / 2;
    left = Math.max(EDGE, Math.min(left, window.innerWidth - popBox.width - EDGE));
    pop.style.top = `${Math.max(EDGE, Math.min(top, window.innerHeight - popBox.height - EDGE))}px`;
    pop.style.left = `${left}px`;
  }

  // Clicking the lit-up element is the intended way forward. A click anywhere
  // else is swallowed rather than ignored silently — the app stays frozen so
  // the walkthrough cannot be knocked off its rails.
  function onBlockerClick(event) {
    if (!target) return;
    const box = target.getBoundingClientRect();
    const inside = event.clientX >= box.left - PAD && event.clientX <= box.right + PAD
      && event.clientY >= box.top - PAD && event.clientY <= box.bottom + PAD;
    if (inside) go(1);
  }

  function onKey(event) {
    if (!blocker) return;
    if (event.key === 'Escape') { event.preventDefault(); finish(); return; }
    if (event.key === 'ArrowRight' || event.key === 'Enter') { event.preventDefault(); go(1); return; }
    if (event.key === 'ArrowLeft') { event.preventDefault(); go(-1); }
  }

  window.Tour = { start, maybeStart, stop, setUser(id) { window.__tourUserId = id; } };
})();
