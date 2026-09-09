/* Local bank catalogue shared by the picker and existing account logos. */
(() => {
  const form = document.querySelector('#account-form');
  const input = form.elements.bank_code;
  const field = document.createElement('div');
  field.className = 'bank-picker-field';
  field.innerHTML = `<span id="bank-picker-label"></span><details class="bank-picker">
    <summary aria-labelledby="bank-picker-label bank-picker-value"><span id="bank-picker-value"></span><span aria-hidden="true">⌄</span></summary>
    <div class="bank-picker-panel"><input type="search" class="bank-picker-search" autocomplete="off">
    <div class="bank-picker-options"></div><p class="bank-picker-status" role="status"></p>
    <button type="button" class="bank-picker-retry" hidden></button></div></details>`;
  input.closest('label').replaceWith(field);
  input.type = 'hidden';
  input.value = '';
  field.append(input);
  const details = field.querySelector('details');
  const summary = field.querySelector('summary');
  const search = field.querySelector('input[type="search"]');
  const options = field.querySelector('.bank-picker-options');
  const status = field.querySelector('.bank-picker-status');
  const retry = field.querySelector('.bank-picker-retry');
  let banks = [], loading = false, failed = false;
  const copy = () => window.I18n.language === 'en'
    ? {label:'Bank', choose:'Choose a bank', search:'Search bank name or code', loading:'Loading banks…', error:'Could not load banks.', retry:'Retry', empty:'No matching bank', required:'Please choose a bank.'}
    : {label:'Ngân hàng', choose:'Chọn ngân hàng', search:'Tìm tên hoặc mã ngân hàng', loading:'Đang tải ngân hàng…', error:'Không tải được danh sách ngân hàng.', retry:'Thử lại', empty:'Không tìm thấy ngân hàng', required:'Vui lòng chọn ngân hàng.'};
  const normalize = value => value.normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/đ/g,'d').replace(/Đ/g,'D').toUpperCase().replace(/[^A-Z0-9]/g,'');
  function render() {
    const c = copy(), selected = banks.find(bank => bank.code === input.value);
    field.querySelector('#bank-picker-label').textContent = c.label;
    field.querySelector('#bank-picker-value').innerHTML = selected ? `${bankLogo({bank_code:selected.code})}<span>${esc(selected.shortName || selected.code)}</span>` : esc(c.choose);
    search.placeholder = c.search;
    search.setAttribute('aria-label', c.search);
    const query = normalize(search.value);
    const matches = banks.filter(bank => normalize(`${bank.code} ${bank.shortName} ${bank.name}`).includes(query));
    options.innerHTML = matches.map(bank => `<button type="button" class="bank-picker-option" data-bank="${esc(bank.code)}" aria-pressed="${bank.code === input.value}">${bankLogo({bank_code:bank.code})}<span><b>${esc(bank.shortName || bank.code)}</b><small>${esc(bank.name)}</small></span></button>`).join('');
    status.textContent = loading ? c.loading : failed ? c.error : matches.length ? '' : c.empty;
    retry.hidden = !failed;
    retry.textContent = c.retry;
  }
  async function load() {
    loading = true; failed = false; render();
    try {
      const response = await fetch('/assets/bank-logos/manifest.json');
      if (!response.ok) throw new Error('Catalogue unavailable');
      const manifest = await response.json();
      banks = Object.entries(manifest.banks).filter(([code]) => /^[A-Z0-9_-]+$/.test(code)).map(([code,bank]) => ({...bank,code}));
      if (!banks.length) throw new Error('Empty catalogue');
      banks.sort((a,b) => (a.shortName || a.code).localeCompare(b.shortName || b.code, 'vi'));
      // Also recognise saved accounts entered with a bank's short name.
      banks.forEach(bank => { bankCodeAliases[normalize(bank.shortName || bank.code)] = bank.code; });
      renderAccounts();
    } catch { failed = true; }
    finally { loading = false; render(); }
  }
  options.addEventListener('click', event => {
    const button = event.target.closest('[data-bank]');
    if (!button) return;
    input.value = button.dataset.bank;
    search.value = '';
    formError(form);
    render(); details.open = false; summary.focus();
  });
  search.addEventListener('input', render);
  search.addEventListener('keydown', event => { if (event.key === 'Enter') event.preventDefault(); });
  details.addEventListener('toggle', () => { if (details.open) search.focus(); });
  details.addEventListener('keydown', event => { if (event.key === 'Escape' && details.open) { event.preventDefault(); event.stopPropagation(); details.open = false; summary.focus(); } });
  document.addEventListener('click', event => { if (!field.contains(event.target)) details.open = false; });
  form.addEventListener('submit', event => {
    if (banks.some(bank => bank.code === input.value)) return;
    event.preventDefault(); event.stopImmediatePropagation();
    formError(form, copy().required); details.open = true; search.focus();
  }, true);
  form.addEventListener('reset', () => { input.value = ''; search.value = ''; details.open = false; render(); });
  retry.addEventListener('click', load);
  window.addEventListener('languagechange', render);
  load();
})();
