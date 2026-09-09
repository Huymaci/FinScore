const $=(s,r=document)=>r.querySelector(s),$$=(s,r=document)=>[...r.querySelectorAll(s)];
const t=(key,params)=>window.I18n.t(key,params);
const localDateValue=()=>{const today=new Date();return `${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,'0')}-${String(today.getDate()).padStart(2,'0')}`};
const localMonthValue=()=>{const today=new Date();return `${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,'0')}`};
const monthDateRange=month=>{const [year,number]=month.split('-').map(Number),lastDay=new Date(year,number,0).getDate();return{dateFrom:`${month}-01`,dateTo:`${month}-${String(lastDay).padStart(2,'0')}`}};
const initialStatisticsRange=monthDateRange(localMonthValue());
const state={csrf:'',profile:null,accounts:[],archivedAccounts:[],categories:[],transactions:[],alerts:[],challenges:[],alertFilter:'ALL',selectedAlertIds:new Set(),alertDeleteBusy:false,month:localMonthValue(),importPreview:null,importReview:{page:1,pages:1,total:0,fileTotal:0,decisions:{},categoryOverrides:{},notes:{}},importHistory:[],importHistoryPage:1,selectedImportHistoryIds:new Set(),statisticsDateFrom:initialStatisticsRange.dateFrom,statisticsDateTo:initialStatisticsRange.dateTo,statisticsRenderedDateFrom:initialStatisticsRange.dateFrom,statisticsRenderedDateTo:initialStatisticsRange.dateTo,statisticsTrendThrough:localMonthValue(),statisticsTrend:[],statisticsBreakdownRequest:0,statisticsTrendRequest:0,realtimeRefresh:false,adminUserPage:1,dashCardActiveId:null,categoryLogos:{}};
let observedLocalMonth=localMonthValue();
const locale=()=>window.I18n.language==='en'?'en-US':'vi-VN';
const money=v=>`${new Intl.NumberFormat(locale()).format(Number(v||0))} ₫`,dateVi=v=>v?new Intl.DateTimeFormat(locale()).format(new Date(`${v.slice(0,10)}T00:00:00`)):'—';
const esc=v=>String(v??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
function applyFills(root=document){$$('[data-fill]',root).forEach(node=>{node.style.width=`${Math.max(0,Math.min(100,finiteNumber(node.dataset.fill)))}%`})}
const finiteNumber=value=>{const number=Number(value);return Number.isFinite(number)?number:0};
const ANALYSIS_MIN_DATE='1900-01-01',ANALYSIS_MAX_DATE='2999-12-31';
const TRANSACTIONS_PER_PAGE=10;
const statisticsMonthPattern=/^(\d{4})-(0[1-9]|1[0-2])$/;
const statisticsDatePattern=/^(\d{4})-(\d{2})-(\d{2})$/;
function formatStatisticsMonth(value){const match=statisticsMonthPattern.exec(value);return match?new Intl.DateTimeFormat(locale(),{month:'long',year:'numeric',timeZone:'UTC'}).format(new Date(Date.UTC(Number(match[1]),Number(match[2])-1,1))):'—'}
function isValidStatisticsDate(value){const match=statisticsDatePattern.exec(value);if(!match)return false;const year=Number(match[1]),month=Number(match[2]),day=Number(match[3]),parsed=new Date(Date.UTC(year,month-1,day));return parsed.getUTCFullYear()===year&&parsed.getUTCMonth()===month-1&&parsed.getUTCDate()===day}
function statisticsDateRange(dateFrom,dateTo){if(!isValidStatisticsDate(dateFrom)||!isValidStatisticsDate(dateTo)||dateFrom>dateTo)return null;const label=dateFrom===dateTo?dateVi(dateFrom):`${dateVi(dateFrom)} – ${dateVi(dateTo)}`,shortDate=value=>new Intl.DateTimeFormat(locale(),{day:'2-digit',month:'2-digit'}).format(new Date(`${value}T00:00:00`));return{dateFrom,dateTo,label,compactLabel:dateFrom===dateTo?shortDate(dateFrom):`${shortDate(dateFrom)}–${shortDate(dateTo)}`}}
function greetingKey(hour){return hour<12?'greeting_morning':hour<18?'greeting_afternoon':'greeting_evening'}
function renderLiveHeader(){const now=new Date(),currentMonth=localMonthValue(),followCurrentMonth=state.month===observedLocalMonth;if(currentMonth!==observedLocalMonth){observedLocalMonth=currentMonth;if(followCurrentMonth){state.month=currentMonth;if(state.profile)refreshRealtimeData()}}$('#dashboard-month-label').textContent=formatStatisticsMonth(state.month);if(state.profile)$('.welcome-row h1').innerHTML=`${esc(t(greetingKey(now.getHours()),{name:state.profile.full_name}))} <span>👋</span>`}
function applyDataMonth(month,syncStatistics=false){
  if(!statisticsMonthPattern.test(month))return false;
  state.month=month;
  // The transaction list is deliberately not bound to this month: it shows every
  // transaction until the user picks a date range themselves.
  const range=monthDateRange(month);
  if(syncStatistics){
    state.statisticsDateFrom=range.dateFrom;
    state.statisticsDateTo=range.dateTo;
    $('#statistics-date-from').value=range.dateFrom;
    $('#statistics-date-to').value=range.dateTo;
  }
  renderLiveHeader();
  return true;
}
async function applyLatestDataMonth(syncStatistics=true){
  const query=new URLSearchParams({per_page:'1',date_to:localDateValue()}),data=await api(`/transactions?${query}`),latestDate=String(data.items?.[0]?.date||'');
  return latestDate?applyDataMonth(latestDate.slice(0,7),syncStatistics):false;
}
function stepDashboardMonth(offset){const [year,month]=state.month.split('-').map(Number),next=new Date(year,month-1+offset,1),nextMonth=`${next.getFullYear()}-${String(next.getMonth()+1).padStart(2,'0')}`;applyDataMonth(nextMonth);if(state.profile)Promise.all([loadDashboard(),loadBudgets()]).catch(error=>toast(t('request_failed'),error.message))}
const category=id=>state.categories.find(x=>x.id===Number(id)),account=id=>state.accounts.find(x=>x.id===Number(id))||state.archivedAccounts.find(x=>x.id===Number(id));
const systemCategoryTranslationKeys=Object.freeze({'Thu nhập':'category_income','Nhà ở':'category_housing','Điện nước':'category_utilities','Ăn uống':'category_dining','Mua sắm':'category_shopping','Di chuyển':'category_transportation','Y tế':'category_healthcare','Học tập':'category_education','Viễn thông':'category_telecommunications','Chuyển khoản':'category_transfer','Khác':'category_other','Học phí':'category_tuition','Nhiên liệu':'category_fuel','Uncategorised':'uncategorized'});
function displayCategoryName(item){const fallback=String(item?.name||t('generic_category'));if(!item||item.custom!==false)return fallback;const key=systemCategoryTranslationKeys[fallback];return key?t(key):fallback}
function displayCategoryText(name){const fallback=String(name||t('uncategorized')),key=systemCategoryTranslationKeys[fallback];return key?t(key):fallback}
// Category icons downloaded into /assets/category-logos (see scripts/download_category_logos.ps1).
// Keyed by the canonical category name (and its English label) so a category
// object or a raw name string both resolve.
async function loadCategoryLogos(){
  try{
    const response=await fetch('/assets/category-logos/manifest.json');
    if(!response.ok)return;
    const manifest=await response.json(),map={};
    Object.values(manifest.categories||{}).forEach(entry=>{
      const meta={file:entry.file,color:entry.color};
      if(entry.name)map[entry.name]=meta;
      if(entry.en)map[entry.en]=meta;
    });
    state.categoryLogos=map;
  }catch{/* icons are cosmetic; fall back to the letter tile */}
}
function categoryLogo(nameOrItem,cls='cat-icon'){
  const name=typeof nameOrItem==='string'?nameOrItem:(nameOrItem&&nameOrItem.name)||'';
  const label=esc((String(name).trim()[0]||'?').toUpperCase());
  const meta=state.categoryLogos[name];
  if(!meta)return `<span class="${cls}">${label}</span>`;
  // NFR-17 again: the per-category tint cannot ride in the markup, so it travels
  // as data-tint and applyLogoTints() paints it through the CSSOM after insertion.
  return `<span class="${cls} has-logo" data-tint="${esc(meta.color)}"><img class="cat-logo" src="/assets/category-logos/${encodeURIComponent(meta.file)}" alt="" loading="lazy"><span class="cat-icon-fallback" hidden>${label}</span></span>`;
}
function applyLogoTints(root=document){$$('[data-tint]',root).forEach(node=>{
  const color=node.dataset.tint;
  node.style.background=`${color}1f`;
  const fallback=$('.cat-icon-fallback',node);
  if(fallback)fallback.style.color=color;
})}
function alertCopy(item){if(window.I18n.language!=='en')return{explanation:item.explanation,action:item.suggested_action};if(item.kind==='BURN_RATE')return{explanation:t('burn_rate_explanation'),action:t('burn_rate_action')};return{explanation:t(item.severity==='CRITICAL'?'threshold_critical_explanation':'threshold_warning_explanation'),action:t('threshold_action')}}
const accountName=x=>x?`${x.name}${x.last_four?` •••• ${x.last_four}`:''}`:t('accounts');
const bankCodeAliases={AGR:'VBA',AGRIBANK:'VBA',MBBANK:'MB',TECHCOMBANK:'TCB',VIETCOMBANK:'VCB',VIETINBANK:'ICB',VPBANK:'VPB',VTB:'ICB'};
const visibleAccountBalances=new Set();
// Dashboard hero card deck: which account card sits on top, and whether its
// balance is currently revealed. The balance is masked by default; the eye
// button reveals it for one second and then it hides itself again.
let heroBalanceRevealed=false,heroBalanceTimer=null;
function eyeSvg(revealed){return `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>${revealed?'':'<path d="m3 3 18 18"/>'}</svg>`}
function accountBalanceMarkup(x){
  const visible=visibleAccountBalances.has(x.id),en=window.I18n.language==='en';
  const label=visible?(en?'Hide balance':'Ẩn số dư'):(en?'Show balance':'Hiện số dư');
  return `<span class="account-balance"><span id="account-balance-${x.id}" aria-live="polite">${visible?money(x.current_balance):'••••••'}</span><button type="button" class="balance-visibility" data-toggle-balance="${x.id}" aria-controls="account-balance-${x.id}" aria-pressed="${visible}" aria-label="${esc(`${label}: ${accountName(x)}`)}" title="${label}"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>${visible?'':'<path d="m3 3 18 18"/>'}</svg></button></span>`;
}
function bankLogo(x){const raw=String(x?.bank_code||'').trim().toUpperCase(),code=bankCodeAliases[raw]||raw.replace(/[^A-Z0-9_-]/g,'');return code?`<span class="bank-logo-wrap"><img class="bank-logo" src="/assets/bank-logos/${encodeURIComponent(code)}.png" alt="" loading="lazy"><span class="bank-logo-fallback" hidden>▣</span></span>`:'<span class="metric-icon blue">▣</span>'}
class ApiError extends Error{constructor(message,status){super(message);this.status=status}}
const serverMessage=()=>window.I18n.language==='en'?'Cannot reach the API. Start Flask and open http://127.0.0.1:5000.':'Không kết nối được API. Hãy chạy Flask và mở http://127.0.0.1:5000.';
async function responseData(response){const type=response.headers.get('content-type')||'',body=await response.text();if(type.includes('json')){try{return body?JSON.parse(body):{}}catch{throw new ApiError(`${t('request_failed')}: ${t('invalid_json')}`,response.status)}}if(type.includes('text/html')||body.trimStart().toLowerCase().startsWith('<!doctype'))throw new ApiError(serverMessage(),response.status);return body}
async function getCsrf(){const r=await fetch('/auth/csrf',{credentials:'same-origin'}),d=await responseData(r);if(!r.ok)throw new ApiError(d?.error||`${t('request_failed')} (${r.status})`,r.status);if(!d.csrf_token)throw new ApiError(serverMessage(),r.status);state.csrf=d.csrf_token}
async function api(path,options={}){const method=options.method||'GET';if(method!=='GET'&&!state.csrf)await getCsrf();const headers=new Headers(options.headers||{});if(method!=='GET')headers.set('X-CSRFToken',state.csrf);if(options.body&&!(options.body instanceof FormData))headers.set('Content-Type','application/json');const r=await fetch(path,{...options,method,headers,credentials:'same-origin'});if(r.status===401){showAuth();throw new ApiError(t('session_expired'),401)}const data=await responseData(r);if(!r.ok)throw new ApiError(data?.error||`${t('request_failed')} (${r.status})`,r.status);return data}
const initials=name=>String(name||'').trim().split(/\s+/).slice(-2).map(part=>part[0]||'').join('').toLocaleUpperCase(locale())||'?';
function showAuth(mode='login'){$$('dialog[open]').forEach(d=>d.close());visibleAccountBalances.clear();renderAccounts();$('#auth-screen').classList.remove('hidden');$('#app-shell').classList.add('hidden');$('#login-form').classList.toggle('hidden',mode!=='login');$('#register-form').classList.toggle('hidden',mode!=='register')}
function showApp(){$('#auth-screen').classList.add('hidden');$('#app-shell').classList.remove('hidden')}
function renderProfileIdentity(){if(!state.profile)return;const name=state.profile.full_name||'',avatarUrl=state.profile.avatar_url||'',initialText=initials(name);$('.profile-mini b').textContent=name;$('.profile-mini small').textContent=state.profile.email.replace(/^(.{2}).*(@.*)$/,'$1***$2');$$('.profile-avatar,.profile-avatar-preview').forEach(element=>{element.textContent=avatarUrl?'':initialText;element.style.backgroundImage=avatarUrl?`url("${avatarUrl}")`:''})}
function closeProfileMenu(){const menu=$('.profile-preferences'),restoreFocus=menu.contains(document.activeElement);menu.classList.add('hidden');$('.profile-more').setAttribute('aria-expanded','false');if(restoreFocus)$('.profile-more').focus()}
function openProfileDialog(){const form=$('#profile-form');formError(form);form.elements.full_name.value=state.profile.full_name;form.elements.date_of_birth.value=state.profile.date_of_birth;form.elements.email.value=state.profile.email;form.elements.avatar.value='';renderProfileIdentity();closeProfileMenu();$('#profile-dialog').showModal()}
function openPasswordDialog(){const form=$('#password-form');form.reset();formError(form);closeProfileMenu();$('#password-dialog').showModal()}
function openSupportDialog(){const form=$('#support-form');form.reset();formError(form);closeProfileMenu();$('#support-dialog').showModal();loadOwnSupportReports(1)}
function toast(title=t('updated'),detail=''){const element=$('#toast');$('b',element).textContent=title;$('small',element).textContent=detail;element.classList.add('show');clearTimeout(window.toastTimer);window.toastTimer=setTimeout(()=>element.classList.remove('show'),3000)}
function busy(b,on,label=t('loading')){if(!b)return;if(!b.dataset.labelVi)b.dataset.labelVi=b.textContent;b.disabled=on;b.textContent=on?label:(b.dataset.i18nBusyKey?t(b.dataset.i18nBusyKey):b.dataset.labelVi)}
function formError(f,e=''){$('.form-error',f).textContent=e}
async function bootstrap(){try{state.profile=await api('/profile');showApp();renderProfileIdentity();renderLiveHeader();applyAdminVisibility();if(isAdmin()){navigate('admin');await loadAdmin();return}navigate(location.hash.slice(1)||'dashboard');applyDataMonth(localMonthValue(),true);await Promise.all([loadAccounts(),loadCategories(),loadCategoryLogos(),applyLatestDataMonth()]);populateSelects();await Promise.all([loadDashboard(),loadTransactions(),loadBudgets(),loadAlerts(),loadChallenges(),loadStatistics(),loadImportHistory()]);window.Tour?.setUser(state.profile?.id);window.Tour?.maybeStart()}catch(e){if(e.status!==401)toast(t('init_failed'),e.message)}}
async function loadAccounts(){const items=(await api('/accounts')).items;state.accounts=items.filter(x=>!x.archived);state.archivedAccounts=items.filter(x=>x.archived);renderAccounts()}
async function loadCategories(){state.categories=(await api('/categories')).items.filter(x=>x.nature)}
async function loadImportHistory(){try{state.importHistory=(await api('/imports/history')).items}catch{state.importHistory=[]}renderImportHistory()}
const IMPORT_HISTORY_PAGE_SIZE=5;
function importHistoryRow(item){return `<tr><td class="import-history-check"><input type="checkbox" data-import-history-select="${item.id}" ${state.selectedImportHistoryIds.has(item.id)?'checked':''} aria-label="${esc(item.filename)}"></td><td><b>${esc(item.filename)}</b><small>${item.status==='REVERTED'?t('import_reverted'):t('import_completed')}</small></td><td>${esc(accountName(account(item.account_id)))}</td><td>${new Date(item.created_at).toLocaleDateString(locale())}</td><td>${item.transaction_count}</td><td><div class="import-history-actions">${item.status==='REVERTED'?`<span class="pill neutral">${t('import_transactions_removed')}</span>`:`<button class="danger-outline-btn" data-delete-import-transactions="${item.id}">${t('remove_imported_transactions')}</button>`}</div></td></tr>`}
function renderImportHistory(){
  const box=$('#import-history'),items=state.importHistory;
  const known=new Set(items.map(item=>item.id));
  state.selectedImportHistoryIds=new Set([...state.selectedImportHistoryIds].filter(id=>known.has(id)));
  if(!items.length){state.importHistoryPage=1;box.innerHTML=empty(t('no_import_history'),t('no_import_history_detail'));updateImportHistorySelection();return}
  const pages=Math.ceil(items.length/IMPORT_HISTORY_PAGE_SIZE),page=Math.min(Math.max(1,state.importHistoryPage),pages),offset=(page-1)*IMPORT_HISTORY_PAGE_SIZE;
  state.importHistoryPage=page;
  const rows=items.slice(offset,offset+IMPORT_HISTORY_PAGE_SIZE).map(importHistoryRow).join('');
  const pager=pages>1?`<div class="import-pagination"><span>${t('import_history_count',{total:items.length,page,pages})}</span><div><button type="button" data-import-history-page="${page-1}" ${page<=1?'disabled':''}>‹ ${t('previous_page')}</button><button type="button" data-import-history-page="${page+1}" ${page>=pages?'disabled':''}>${t('next_page')} ›</button></div></div>`:'';
  box.innerHTML=`<div class="table-wrap"><table><thead><tr><th class="import-history-check"><input type="checkbox" id="import-history-select-all" aria-label="${t('select_all')}"></th><th>${t('import_file')}</th><th>${t('accounts')}</th><th>${t('imported_at')}</th><th>${t('imported_transactions')}</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>${pager}`;
  updateImportHistorySelection();
}
function populateSelects(){const opts=state.accounts.map(x=>`<option value="${x.id}">${esc(accountName(x))}</option>`).join('');$('#transaction-account').innerHTML=`<option value="">${t('all_accounts')}</option>${opts}`;$('#import-account').innerHTML=opts||`<option value="">${t('create_account_first_option')}</option>`;$('[name="account_id"]',$('#transaction-form')).innerHTML=opts;$('[name="category_id"]',$('#transaction-form')).innerHTML=state.categories.map(x=>`<option value="${x.id}">${esc(displayCategoryName(x))}</option>`).join('')}
function stepMonth(ym,delta){const [y,m]=String(ym).split('-').map(Number),d=new Date(y,m-1+delta,1);return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}`}
// Split the trailing currency unit off a formatted amount so the number reads
// bold and the "₫" sits quiet beside it, like the reference cards.
function moneyTwoTone(v){const s=money(v),cut=s.lastIndexOf(' ');return cut>0?`${esc(s.slice(0,cut))}<span class="unit">${esc(s.slice(cut))}</span>`:esc(s)}
function monthShort(ym){const m=/^(\d{4})-(\d{2})$/.exec(String(ym));return m?new Intl.DateTimeFormat(locale(),{month:'short'}).format(new Date(Number(m[1]),Number(m[2])-1,1)):String(ym)}
function deltaInfo(current,previous,{lowerIsBetter=false}={}){
  if(!Number.isFinite(previous)||previous===0)return null;
  const pct=(current-previous)/Math.abs(previous)*100,rising=pct>=0,good=lowerIsBetter?!rising:rising;
  return {text:`${rising?'↗':'↘'} ${Math.abs(pct).toFixed(2)}%`,cls:good?'up':'down'};
}
function setBarHeights(container){$$('.bar',container).forEach(bar=>{bar.firstElementChild.style.height=`${Math.max(3,Number(bar.dataset.barH)||0)}%`})}

// The account whose card is on top of the deck: the last one the user tapped,
// otherwise the first bank card, otherwise the first account of any kind.
function activeHeroAccount(){
  const accounts=state.accounts||[];
  return accounts.find(a=>a.id===state.dashCardActiveId)
    ||accounts.find(a=>a.type==='BANK'&&a.last_four)||accounts[0]||null;
}
const heroCardMask=x=>x&&x.last_four?`•••• ${esc(x.last_four)}`:'•••• ••••';
const heroCardBrand=x=>x&&x.type==='BANK'?bankLogo(x):`<span class="credit-card-brand">${window.I18n.language==='en'?'CASH':'TIỀN MẶT'}</span>`;
const heroFrontCard=()=>{const deck=$('#dash-card-deck');return deck?$('.credit-card.is-front',deck):null};

// Repaint only the balance line + eye button of the front card, without
// disturbing the deck (used by the toggle and its one-second auto-hide timer).
function applyHeroBalance(){
  const deck=$('#dash-card-deck');if(!deck)return;
  const front=heroFrontCard();if(!front)return;
  const account=activeHeroAccount();
  const span=$('.credit-card-balance',front);
  if(span)span.innerHTML=heroBalanceRevealed&&account?moneyTwoTone(account.current_balance):'<span class="masked">••••••</span>';
  $$('.credit-card:not(.is-front) .credit-card-balance',deck).forEach(s=>{s.innerHTML='<span class="masked">••••••</span>'});
  const button=$('.card-eye',front);if(!button)return;
  const en=window.I18n.language==='en';
  const label=heroBalanceRevealed?(en?'Hide balance':'Ẩn số dư'):(en?'Show balance':'Hiện số dư');
  button.setAttribute('aria-pressed',String(heroBalanceRevealed));
  button.setAttribute('aria-label',label);
  button.setAttribute('title',label);
  button.innerHTML=eyeSvg(heroBalanceRevealed);
}
function toggleHeroBalance(){
  clearTimeout(heroBalanceTimer);
  heroBalanceRevealed=!heroBalanceRevealed;
  applyHeroBalance();
  if(heroBalanceRevealed)heroBalanceTimer=setTimeout(()=>{heroBalanceRevealed=false;applyHeroBalance()},1000);
}
function selectHeroCard(id){
  if(!(state.accounts||[]).some(a=>a.id===id)||id===state.dashCardActiveId)return;
  state.dashCardActiveId=id;
  heroBalanceRevealed=false;clearTimeout(heroBalanceTimer);
  renderDashHero(state.dashboardData||{});
}
function heroCardMarkup(x,en){
  return `<div class="credit-card" data-select-hero-card="${x.id}">
      <div class="credit-card-row"><span class="credit-card-mask">${heroCardMask(x)}</span>${heroCardBrand(x)}</div>
      <b class="credit-card-holder">${esc(x.name)}</b>
      <strong class="credit-card-balance"><span class="masked">••••••</span></strong>
      <div class="credit-card-row">
        <span class="delta up"></span>
        <button type="button" class="card-eye" data-toggle-hero-balance aria-pressed="false" aria-label="${en?'Show balance':'Hiện số dư'}">${eyeSvg(false)}</button>
      </div>
    </div>`;
}

function renderDashHero(d){
  const deck=$('#dash-card-deck');if(!deck)return;
  const accounts=state.accounts||[],en=window.I18n.language==='en';
  if(!accounts.length){
    state.dashCardActiveId=null;deck.style.removeProperty('--deck-layers');deck.dataset.sig='';
    deck.innerHTML=`<div class="credit-card is-front is-empty"><p>${en?'No account yet':'Chưa có tài khoản'}</p><button type="button" class="hero-btn ghost" data-action="accounts"><span aria-hidden="true">＋</span><span>${en?'Add account':'Thêm tài khoản'}</span></button></div>`;
    return;
  }
  let activeIdx=accounts.findIndex(a=>a.id===state.dashCardActiveId);
  if(activeIdx<0)activeIdx=Math.max(0,accounts.findIndex(a=>a.type==='BANK'&&a.last_four));
  state.dashCardActiveId=accounts[activeIdx].id;
  const sig=accounts.map(a=>a.id).join(',')+'|'+en;
  if(deck.dataset.sig!==sig){
    deck.dataset.sig=sig;
    deck.innerHTML=accounts.map(x=>heroCardMarkup(x,en)).join('');
  }
  const cards=$$('.credit-card',deck),n=cards.length;
  cards.forEach((el,i)=>{
    const pos=(i-activeIdx+n)%n,front=pos===0;
    el.style.setProperty('--pos',pos);
    el.classList.toggle('is-front',front);
    el.removeAttribute('aria-hidden');
    if(front){el.removeAttribute('role');el.removeAttribute('tabindex');el.removeAttribute('aria-label')}
    else{
      el.setAttribute('role','button');el.setAttribute('tabindex','0');
      el.setAttribute('aria-label',`${en?'Switch to ':'Chuyển sang thẻ '}${accounts[i].name}`);
    }
  });
  const net=Number((d&&d.net)||0),front=heroFrontCard();
  if(front){
    const delta=$('.delta',front);
    if(delta){delta.className=`delta ${net>=0?'up':'down'}`;delta.textContent=`${net>=0?'↗':'↘'} ${money(Math.abs(net))} ${t('this_month')}`}
  }
  deck.style.setProperty('--deck-layers',Math.min(n-1,3));
  applyHeroBalance();
}
// /statistics/trend always returns 12 months; the slice is a defensive cap.
const OVERVIEW_MONTHS=12;
function renderOverview(d,trend){
  $('#overview-kicker').textContent=t('overview_kicker');
  $('#overview-total').innerHTML=moneyTwoTone(d.expense);
  $('#overview-sub').textContent=`${t('income')}: ${money(d.income)}`;
  const items=(trend||[]).slice(-OVERVIEW_MONTHS);
  const chart=$('#overview-chart');
  chart.classList.remove('is-loading');
  chart.removeAttribute('aria-busy');
  chart.dataset.ready='1';
  state.overviewTrend=items;
  // Empty state: /statistics/trend failed (loadDashboard falls back to []) or the
  // account has no history yet. Never leave the plot as a blank 200px band.
  if(!items.length){
    chart.classList.add('is-empty');
    chart.removeAttribute('aria-label');
    chart.innerHTML=empty(t('no_spending_data'),t('overview_trend_hint'));
    return;
  }
  chart.classList.remove('is-empty');
  chart.setAttribute('aria-label',t('overview_chart_aria',{count:items.length}));
  // Diverging XY chart. X = months on a zero axis down the middle: expense grows
  // up out of it, income grows down, the two meeting base to base so a month
  // reads as one column. One shared scale keeps the halves comparable; each
  // series stops at 44% of the plot so neither tip touches the card edge.
  const peak=Math.max(1,...items.flatMap(x=>[x.income||0,x.expense||0]));
  const bars=items.map(x=>{
    const selected=x.month===state.month;
    const incH=(x.income||0)/peak*44;
    const expH=(x.expense||0)/peak*44;
    const label=t('overview_bar_aria',{month:formatStatisticsMonth(x.month),expense:money(x.expense||0),income:money(x.income||0)});
    return `<button type="button" class="bar${selected?' active':''}" data-bar-month="${x.month}" data-bar-value="${x.expense||0}" data-bar-income="${x.income||0}"${selected?' aria-current="true"':''} aria-label="${esc(label)}"><span class="bar-col"><i class="bar-inc" data-bar-h="${incH.toFixed(2)}"></i><i class="bar-exp" data-bar-h="${expH.toFixed(2)}"></i></span></button>`;
  }).join('');
  // WCAG 1.4.1: the selected month must not be marked by hue alone — the
  // highlight band behind the column and this bolder axis label carry the same
  // meaning without relying on colour vision.
  const axis=items.map(x=>`<span${x.month===state.month?' class="is-selected"':''}>${esc(monthShort(x.month))}</span>`).join('');
  // Two series need naming: grey above and orange below are otherwise ambiguous.
  const legend=`<div class="bar-legend"><span><i class="is-expense"></i>${esc(t('expense'))}</span><span><i class="is-income"></i>${esc(t('income'))}</span></div>`;
  chart.innerHTML=`<div class="bar-plot">${bars}</div><div class="bar-axis">${axis}</div>${legend}`;
  // NFR-17: style-src is 'self' with no 'unsafe-inline', so an inline style
  // attribute in the markup above would be dropped and every segment would fall
  // back to its stub height. Set the ratio through the CSSOM, which CSP does
  // not gate.
  $$('.bar-inc,.bar-exp',chart).forEach(el=>{el.style.height=`${Number(el.dataset.barH)||0}%`});
}
// Loading state: skeleton columns while /statistics/trend is in flight, so the
// card keeps its height instead of collapsing and reflowing the dashboard.
function renderOverviewSkeleton(){
  const chart=$('#overview-chart');if(!chart||chart.dataset.ready==='1')return;
  chart.classList.add('is-loading');chart.classList.remove('is-empty');
  chart.setAttribute('aria-busy','true');
  chart.innerHTML=`<div class="bar-plot">${Array.from({length:OVERVIEW_MONTHS},()=>'<span class="bar" aria-hidden="true"><span class="bar-col"><i class="bar-inc"></i><i class="bar-exp"></i></span></span>').join('')}</div><div class="bar-axis"></div>`;
}
function renderSpendCards(d,previous){
  const before={};((previous&&previous.budget_progress)||[]).forEach(b=>{before[b.category_id]=b.spent});
  const rows=[...(d.budget_progress||[])].sort((a,b)=>b.spent-a.spent).slice(0,4),grid=$('#dashboard-spend');
  if(!rows.length){grid.innerHTML=empty(t('no_spending_data'),t('set_limit_hint'));return}
  grid.innerHTML=rows.map(row=>{
    const item=category(row.category_id),name=item?displayCategoryName(item):String(row.category||t('generic_category'));
    const delta=deltaInfo(row.spent,before[row.category_id],{lowerIsBetter:true});
    const foot=delta?`<small class="delta ${delta.cls}">${esc(delta.text)} ${esc(t('vs_last_month'))}</small>`:`<small class="delta">${row.percent}% ${esc(t('used'))}</small>`;
    return `<article class="spend-card"><div class="spend-card-head">${categoryLogo(item||row.category,'spend-icon')}<b>${esc(name)}</b></div><strong>${moneyTwoTone(row.spent)}</strong>${foot}</article>`;
  }).join('');
  applyLogoTints(grid);
}
// Budget usage: one figure for the whole month, summed from the per-category
// rows the dashboard payload already carries - no extra request. The status
// word next to the percentage carries the same meaning as the colour, so the
// card does not rely on hue alone (WCAG 1.4.1).
function renderBudgetUsage(d){
  const items=d.budget_progress||[],body=$('#budget-usage-body');
  $('#budget-usage-kicker').textContent=formatStatisticsMonth(state.month).toLocaleUpperCase(locale());
  if(!items.length){body.innerHTML=empty(t('no_budget_month'),t('set_limit_hint'));return}
  const total=items.reduce((sum,x)=>sum+x.budget,0),spent=items.reduce((sum,x)=>sum+x.spent,0);
  const raw=total?spent/total*100:0,pct=Math.round(raw),status=budgetStatus(raw),tone=budgetTone(status);
  body.innerHTML=`<div class="budget-usage-head"><strong class="${tone}-text">${pct}%</strong><span class="${tone}-text">${esc(budgetLabel(status))}</span></div>`
    +`<div class="progress large"><i class="${tone}" data-fill="${Math.min(pct,100)}"></i></div>`
    +`<p class="budget-usage-figures"><span>${money(spent)} <small>/ ${money(total)}</small></span><span><small>${esc(t('remaining'))}</small> <b>${money(Math.max(0,total-spent))}</b></span></p>`;
  applyFills(body);
}
function showOverviewChip(bar){
  const chip=$('#overview-chip'),expense=Number(bar.dataset.barValue),income=Number(bar.dataset.barIncome||0),month=bar.dataset.barMonth;
  chip.innerHTML=`<span class="chip-month">${esc(formatStatisticsMonth(month))}</span><span class="chip-row"><i class="chip-dot expense"></i><span>${esc(t('expense'))}</span><b>${esc(money(expense))}</b></span><span class="chip-row"><i class="chip-dot income"></i><span>${esc(t('income'))}</span><b>${esc(money(income))}</b></span>`;
  chip.classList.remove('hidden');
  const host=chip.offsetParent||$('#dashboard'),hostBox=host.getBoundingClientRect(),barBox=bar.getBoundingClientRect();
  const left=barBox.left-hostBox.left+barBox.width/2-chip.offsetWidth/2;
  chip.style.left=`${Math.max(6,Math.min(left,hostBox.width-chip.offsetWidth-6))}px`;
  chip.style.top=`${barBox.top-hostBox.top-chip.offsetHeight-10}px`;
}
function hideOverviewChip(){$('#overview-chip').classList.add('hidden')}
async function loadDashboard(){
  renderOverviewSkeleton();
  const previousMonth=stepMonth(state.month,-1);
  const [d,previous,trend]=await Promise.all([
    api(`/statistics/dashboard?month=${state.month}`),
    api(`/statistics/dashboard?month=${previousMonth}`).catch(()=>null),
    api(`/statistics/trend?through=${state.month}`).then(response=>response.items||response||[]).catch(()=>[]),
  ]);
  state.dashboardTrend=trend;state.dashboardData=d;
  renderDashHero(d);
  renderOverview(d,trend);
  renderSpendCards(d,previous);
  renderBudgetUsage(d);
}
function challengeCopy(){return window.I18n.language==='en'?{kicker:'BEHAVIOR CHALLENGE',title:'A small challenge for you',from:'Current habit',to:'This week’s goal',times:'times/week',accept:'Accept challenge',decline:'Not now',active:'In progress',done:'Completed',failed:'Try again',saved:'Saved',progress:'Progress',empty:'No challenge yet',emptyDetail:'Keep recording transactions so SmartFinance can detect a recurring spending habit.'}:{kicker:'THỬ THÁCH HÀNH VI',title:'Một thử thách nhỏ dành cho bạn',from:'Thói quen hiện tại',to:'Mục tiêu tuần này',times:'lần/tuần',accept:'Chấp nhận thử thách',decline:'Để sau',active:'Đang thực hiện',done:'Hoàn thành',failed:'Thử lại',saved:'Đã tiết kiệm',progress:'Tiến độ',empty:'Chưa có thử thách',emptyDetail:'Hãy tiếp tục ghi giao dịch để SmartFinance phát hiện một thói quen chi tiêu lặp lại.'}}
function renderChallenges(){const c=challengeCopy(),proposal=state.challenges.find(x=>x.status==='PROPOSED'),banner=$('#challenge-banner');banner.classList.toggle('hidden',!proposal);if(proposal)banner.innerHTML=`<div><p class="eyebrow">${c.kicker}</p><h2>${c.title}: ${esc(proposal.habit_name||proposal.category)}</h2><p>${c.from} <b>${proposal.baseline_count} ${c.times}</b> → ${c.to} <b>${proposal.target_count} ${c.times}</b></p></div><div class="challenge-actions"><button class="secondary-btn" data-challenge-action="DECLINE" data-challenge-id="${proposal.id}">${c.decline}</button><button class="primary-btn" data-challenge-action="ACCEPT" data-challenge-id="${proposal.id}">${c.accept}</button></div>`;const items=state.challenges.filter(x=>x.status!=='PROPOSED'&&x.status!=='DECLINED');$('#challenge-list').innerHTML=items.length?items.map(x=>{const percent=x.target_count?Math.min(100,Math.round((x.actual_count||0)/x.target_count*100)):0,label=x.status==='ACTIVE'?c.active:x.status==='COMPLETED'?c.done:c.failed;return `<article class="panel challenge-card"><div class="challenge-card-head"><div><span class="pill ${x.status==='COMPLETED'?'positive':x.status==='FAILED'?'negative':'neutral'}">${label}</span><h2>${esc(x.habit_name||x.category)}</h2><p>${x.baseline_count} → ${x.target_count} ${c.times}</p></div><strong>${x.status==='ACTIVE'?`${x.actual_count||0}/${x.target_count}`:money(x.saved_amount)}</strong></div><div class="progress"><i class="${x.status==='FAILED'?'danger':'good'}" data-fill="${percent}"></i></div><small>${x.status==='ACTIVE'?c.progress:c.saved}</small></article>`}).join(''):empty(c.empty,c.emptyDetail);applyFills($('#challenge-list'))}
async function loadChallenges(){state.challenges=(await api('/challenges')).items;renderChallenges()}
const budgetStatus=percent=>percent>100?'RED':percent>85?'AMBER':'GREEN';
const budgetTone=status=>status==='RED'?'danger':status==='AMBER'?'warning':'good';
const budgetLabel=status=>status==='RED'?t('over_budget'):status==='AMBER'?t('near_budget'):t('on_track');
const empty=(title,text)=>`<div class="empty-state"><b>${title}</b><span>${text}</span></div>`;
// Both inputs empty = no date filter (every transaction). A single bound is an
// open-ended filter. Only a reversed range (from > to) is rejected.
function selectedTransactionDateRange(){const dateFrom=$('#transaction-date-from').value,dateTo=$('#transaction-date-to').value;return !dateFrom||!dateTo||dateFrom<=dateTo?{dateFrom,dateTo}:null}
function transactionDateRangeLabel(range){return range.dateFrom&&range.dateTo?`${dateVi(range.dateFrom)} – ${dateVi(range.dateTo)}`:range.dateFrom?t('range_from_only',{date:dateVi(range.dateFrom)}):range.dateTo?t('range_to_only',{date:dateVi(range.dateTo)}):t('range_all_time')}
function renderTransactionDateFilterState(){const active=Boolean($('#transaction-date-from').value||$('#transaction-date-to').value);$('#clear-transaction-dates').classList.toggle('hidden',!active)}
function syncTransactionDateConstraints(){const dateFrom=$('#transaction-date-from'),dateTo=$('#transaction-date-to');dateFrom.max=dateTo.value;dateTo.min=dateFrom.value}
async function loadTransactions(page=1){const range=selectedTransactionDateRange();if(!range){toast(t('invalid_transaction_date_range'));return false}const p=new URLSearchParams({page,per_page:TRANSACTIONS_PER_PAGE});if(range.dateFrom)p.set('date_from',range.dateFrom);if(range.dateTo)p.set('date_to',range.dateTo);if($('#transaction-account').value)p.set('account_id',$('#transaction-account').value);if($('#transaction-direction').value)p.set('direction',$('#transaction-direction').value);const d=await api(`/transactions?${p}`);state.transactions=d.items;renderTransactions(d);$('#recent-transactions').innerHTML=transactionRows(d.items.slice(0,5),false);return true}
function transactionRows(items,controls=true){return items.length?items.map(x=>`<tr>${controls?'<td><input type="checkbox"></td>':''}<td>${dateVi(x.date)}</td><td class="amount ${x.direction==='IN'?'in':'out'}">${x.direction==='IN'?'+':'−'} ${money(x.amount)}</td><td><span class="tag">${esc(displayCategoryName(category(x.category_id)))}</span></td><td><span class="merchant-logo ${x.direction==='IN'?'green':''}">${x.direction==='IN'?'↗':'↘'}</span><b>${esc(x.description||t('no_description'))}</b></td><td>${esc(accountName(account(x.account_id)))}</td>${controls?`<td><button class="row-menu" data-delete-transaction="${x.id}">×</button></td>`:''}</tr>`).join(''):`<tr><td colspan="${controls?7:5}">${empty(t('no_transactions'),t('add_first_transaction'))}</td></tr>`}
function renderTransactions(d){const q=$('#transaction-search').value.toLowerCase(),items=d.items.filter(x=>(x.description||'').toLowerCase().includes(q));$('#transaction-rows').innerHTML=transactionRows(items);$('.pagination>span').textContent=t('transaction_count',{total:d.total,page:d.page,pages:Math.max(d.pages,1)});$('.pagination>div').innerHTML=`<button data-page="${Math.max(1,d.page-1)}" ${d.page<=1?'disabled':''}>‹</button><button class="active">${d.page}</button><button data-page="${Math.min(d.pages,d.page+1)}" ${d.page>=d.pages?'disabled':''}>›</button>`}
async function loadBudgets(){const [b,d]=await Promise.all([api(`/budgets?month=${state.month}`),api(`/statistics/dashboard?month=${state.month}`)]),total=b.items.reduce((s,x)=>s+x.amount,0),spent=d.expense,summary=$$('.budget-summary>div:not(.ring) strong'),rawPercent=total?spent/total*100:0,pct=Math.round(rawPercent),tone=budgetTone(budgetStatus(rawPercent)),ring=$('.ring');summary[0].textContent=money(total);summary[1].textContent=money(spent);summary[2].textContent=money(total-spent);summary[2].classList.remove('good-text','warning-text','danger-text');summary[2].classList.add(`${tone}-text`);ring.classList.remove('good','warning','danger');ring.classList.add(tone);ring.style.setProperty('--value',Math.min(pct,100));$('b',ring).textContent=`${pct}%`;const progress=Object.fromEntries(d.budget_progress.map(x=>[x.category_id,x]));$('#budget-cards').innerHTML=b.items.length?b.items.map(x=>{const c=category(x.category_id),name=displayCategoryName(c),p=progress[x.category_id]||{spent:0,percent:0,status:'GREEN'},tone=budgetTone(p.status),label=budgetLabel(p.status);return `<article class="category-card ${tone==='danger'?'danger-border':''}"><div>${categoryLogo(c)}<span><b>${esc(name)}</b><small>${natureLabel(c?.nature)}</small></span><button data-edit-budget="${x.category_id}" title="${esc(t('edit_budget'))}" aria-label="${esc(t('edit_budget_named',{name}))}">✎</button><button class="delete-budget" data-delete-budget="${x.id}" data-budget-name="${esc(name)}" title="${esc(t('delete_budget'))}" aria-label="${esc(t('delete_budget_named',{name}))}">🗑️</button></div><strong>${money(p.spent)} <small>/ ${money(x.amount)}</small></strong><div class="progress large"><i class="${tone}" data-fill="${Math.min(p.percent,100)}"></i></div><p><span class="${tone}-text">${label}</span><span>${p.percent}%</span></p></article>`}).join(''):empty(t('no_budget'),t('add_budget_hint'));applyFills($('#budget-cards'));applyLogoTints($('#budget-cards'));$('#budget-page-kicker').textContent=formatStatisticsMonth(state.month).toLocaleUpperCase(locale())}
const natureLabel=n=>({COMMITTED:t('committed'),SEMI_FIXED:t('semi_fixed'),DISCRETIONARY:t('discretionary')}[n]||t('generic_category'));
function filteredAlerts(){return state.alertFilter==='ALL'?state.alerts.filter(item=>item.status!=='DISMISSED'):state.alerts.filter(item=>item.status===state.alertFilter)}
function pruneAlertSelection(items=filteredAlerts()){const selectable=new Set(items.filter(item=>item.status!=='DISMISSED').map(item=>Number(item.id)));state.selectedAlertIds=new Set([...state.selectedAlertIds].filter(id=>selectable.has(id)))}
function renderAlertSelectionControls(){/* bulk-select UI removed with the standalone alerts page */}
function closeNotifications(){const panel=$('#notif-panel');if(!panel||panel.classList.contains('hidden'))return;panel.classList.add('hidden');$('#notif-bell')?.setAttribute('aria-expanded','false')}
function renderNotifications(active=state.alerts.filter(item=>item.status!=='DISMISSED')){
  const list=$('#notif-list');if(!list)return;
  const sorted=[...active].sort((a,b)=>new Date(b.triggered_at)-new Date(a.triggered_at));
  list.innerHTML=sorted.length?sorted.map(x=>{
    const copy=alertCopy(x),name=displayCategoryName(category(x.category_id)),critical=x.severity==='CRITICAL';
    return `<article class="notif-item ${x.status==='UNREAD'?'unread':''} ${critical?'critical':''}"><span class="notif-dot">${critical?'!':'↗'}</span><div class="notif-body"><div class="notif-meta"><span class="severity">${t(critical?'critical':'warning')}</span><small>${new Date(x.triggered_at).toLocaleString(locale())}</small></div><b>${esc(name)}</b><p>${esc(copy.explanation)}</p><div class="notif-item-actions"><button type="button" data-alert-status="READ" data-alert-id="${x.id}">${t('understood')}</button><button type="button" class="dismiss" data-alert-status="DISMISSED" data-alert-id="${x.id}">${t('dismiss')}</button></div></div></article>`;
  }).join(''):`<p class="notif-empty">${esc(t('no_alerts'))}</p>`;
}
function renderAlerts(){
  const activeAlerts=state.alerts.filter(item=>item.status!=='DISMISSED'),unread=activeAlerts.filter(item=>item.status==='UNREAD').length;
  const badge=$('#notif-badge');
  if(badge){badge.textContent=unread>99?'99+':String(unread);badge.classList.toggle('hidden',unread===0)}
  const markAll=$('#notif-mark-all');if(markAll)markAll.disabled=unread===0;
  renderNotifications(activeAlerts);
}
async function loadAlerts(filter=state.alertFilter){if(['ALL','UNREAD','DISMISSED'].includes(filter))state.alertFilter=filter;state.alerts=(await api('/alerts')).items;renderAlerts()}
function setAlertFilter(filter){if(!['ALL','UNREAD','DISMISSED'].includes(filter))return;state.alertFilter=filter;state.selectedAlertIds.clear();renderAlerts()}
function confirmAlertDeletion(count){const dialog=$('#delete-alerts-dialog');$('#delete-alerts-message').textContent=t('delete_alerts_message',{count});dialog.returnValue='cancel';dialog.showModal();return new Promise(resolve=>dialog.addEventListener('close',()=>resolve(dialog.returnValue==='confirm'),{once:true}))}
async function deleteSelectedAlerts(){
  const ids=[...state.selectedAlertIds];
  if(!ids.length||state.alertDeleteBusy||!await confirmAlertDeletion(ids.length))return;
  state.alertDeleteBusy=true;renderAlertSelectionControls();
  try{
    const results=await Promise.allSettled(ids.map(id=>api(`/alerts/${id}`,{method:'PATCH',body:JSON.stringify({status:'DISMISSED'})}))),succeeded=ids.filter((id,index)=>results[index].status==='fulfilled'),failed=results.filter(result=>result.status==='rejected'),succeededIds=new Set(succeeded);
    state.alerts=state.alerts.map(item=>succeededIds.has(Number(item.id))?{...item,status:'DISMISSED'}:item);
    succeeded.forEach(id=>state.selectedAlertIds.delete(id));
    try{await loadAlerts()}catch{renderAlerts()}
    if(!failed.length)toast(t('alerts_deleted'),t('alerts_deleted_detail',{count:succeeded.length}));
    else if(succeeded.length)toast(t('alerts_delete_partial'),t('alerts_delete_partial_detail',{success:succeeded.length,total:ids.length,failed:failed.length}));
    else toast(t('alerts_delete_failed'),failed[0]?.reason?.message||'');
  }finally{state.alertDeleteBusy=false;renderAlertSelectionControls()}
}
async function loadStatisticsBreakdown(){
  const selectedDateFrom=state.statisticsDateFrom,selectedDateTo=state.statisticsDateTo,range=statisticsDateRange(selectedDateFrom,selectedDateTo);
  if(!range)return false;
  const requestId=++state.statisticsBreakdownRequest;
  let breakdownData;
  const query=new URLSearchParams({date_from:range.dateFrom,date_to:range.dateTo});
  try{breakdownData=await api(`/statistics/breakdown?${query}`)}catch(error){if(requestId!==state.statisticsBreakdownRequest||selectedDateFrom!==state.statisticsDateFrom||selectedDateTo!==state.statisticsDateTo)return false;throw error}
  if(requestId!==state.statisticsBreakdownRequest||selectedDateFrom!==state.statisticsDateFrom||selectedDateTo!==state.statisticsDateTo)return false;
  const breakdownItems=(Array.isArray(breakdownData.items)?breakdownData.items:[])
    .map(item=>({category:item.category,amount:Math.max(0,finiteNumber(item.amount))}))
    .filter(item=>item.amount>0)
    .sort((left,right)=>right.amount-left.amount);
  const calculatedTotal=breakdownItems.reduce((sum,item)=>sum+item.amount,0),total=Math.max(0,finiteNumber(breakdownData.total_expense??calculatedTotal));
  const visibleItems=breakdownItems.length>5
    ? [...breakdownItems.slice(0,4),{category:t('other'),amount:breakdownItems.slice(4).reduce((sum,item)=>sum+item.amount,0)}]
    : breakdownItems.slice(0,5);
  $('#statistics-range-label').textContent=range.label;
  $('#statistics-total').textContent=money(total);
  const donut=$('.donut');
  donut.querySelector('b').textContent=new Intl.NumberFormat(locale(),{maximumFractionDigits:0}).format(total);
  donut.querySelector('small').textContent=`₫ · ${range.compactLabel}`;
  donut.title=money(total);
  donut.setAttribute('aria-label',`${t('total_expense')}: ${money(total)} — ${range.label}`);
  let cursor=0;
  const segments=visibleItems.map((item,index)=>{
    const percentage=total?item.amount/total*100:0,offset=-cursor;
    cursor+=percentage;
    return `<circle class="donut-segment c${index+1}" cx="21" cy="21" r="15.9155" pathLength="100" stroke-dasharray="${percentage.toFixed(4)} ${(100-percentage).toFixed(4)}" stroke-dashoffset="${offset.toFixed(4)}"></circle>`;
  }).join('');
  $('.donut-chart').innerHTML=`<circle class="donut-base" cx="21" cy="21" r="15.9155"></circle>${segments}`;
  const percentageFormatter=new Intl.NumberFormat(locale(),{minimumFractionDigits:1,maximumFractionDigits:1});
  $('.donut-wrap ul').innerHTML=visibleItems.length?visibleItems.map((item,index)=>{
    const percentage=total?item.amount/total*100:0;
    return `<li><i class="c${index+1}"></i><span>${esc(displayCategoryText(item.category))}</span><b>${percentageFormatter.format(percentage)}%</b></li>`;
  }).join(''):`<li class="statistics-empty">${t('no_spending_data')}</li>`;
  state.statisticsRenderedDateFrom=selectedDateFrom;
  state.statisticsRenderedDateTo=selectedDateTo;
  return true;
}
// The trend chart is anchored to the month containing the selected end date.
// Without this it kept whatever window was fetched at start-up, so applying a
// range moved the doughnut while the trend beside it silently kept describing
// a different period.
function trendAnchorMonth(){
  const dateTo=state.statisticsDateTo;
  return (typeof dateTo==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(dateTo))?dateTo.slice(0,7):localMonthValue();
}
async function loadStatisticsTrend(){
  const through=trendAnchorMonth(),requestId=++state.statisticsTrendRequest;
  let trendData;
  try{trendData=await api(`/statistics/trend?through=${through}`)}catch(error){if(requestId!==state.statisticsTrendRequest)return false;throw error}
  if(requestId!==state.statisticsTrendRequest)return false;
  state.statisticsTrendThrough=through;
  state.statisticsTrend=(Array.isArray(trendData.items)?trendData.items:[]).map(item=>({month:String(item.month||''),income:Math.max(0,finiteNumber(item.income)),expense:Math.max(0,finiteNumber(item.expense))}));
  renderTrend();
  return true;
}
async function loadStatistics(){await Promise.all([loadStatisticsBreakdown(),loadStatisticsTrend()])}
function niceAxisStep(value){
  const magnitude=10**Math.floor(Math.log10(value)),normalized=value/magnitude;
  return (normalized<=1?1:normalized<=2?2:normalized<=5?5:10)*magnitude;
}
function renderTrend(){
  const periodSelect=$('#statistics-period'),period=periodSelect.value==='6'?6:12,items=state.statisticsTrend.slice(-period),chart=$('.trend-chart');
  if(periodSelect.value!==String(period))periodSelect.value=String(period);
  const maximum=Math.max(0,...items.flatMap(item=>[item.income,item.expense]));
  const step=maximum>0?niceAxisStep(maximum/4):0,scaleMaximum=step*4||1;
  const points=key=>items.map((item,index)=>`${items.length===1?350:index*(700/(items.length-1))},${210-item[key]/scaleMaximum*180}`).join(' ');
  $('.income-line').setAttribute('points',points('income'));
  $('.expense-line').setAttribute('points',points('expense'));
  const axisFormatter=new Intl.NumberFormat(locale(),{notation:'compact',maximumFractionDigits:1});
  $('.y-labels').innerHTML=Array.from({length:5},(_,index)=>`<span>${step?axisFormatter.format(scaleMaximum-step*index):'0'}</span>`).join('');
  $('.x-labels').innerHTML=items.map(item=>{
    const match=/^(\d{4})-(\d{2})$/.exec(item.month);
    const label=match?new Intl.DateTimeFormat(locale(),{month:'short'}).format(new Date(Number(match[1]),Number(match[2])-1,1)):item.month;
    return `<span>${esc(label)}</span>`;
  }).join('');
  chart.setAttribute('aria-label',t('trend_chart_aria',{count:period,month:formatStatisticsMonth(state.statisticsTrendThrough)}));
}
const accountRow=(x,archived=false)=>`<div class="account-item ${archived?'archived':''}">${x.type==='BANK'?bankLogo(x):'<span class="metric-icon mint">●</span>'}<div><b>${esc(accountName(x))}</b><small>${t(x.type==='BANK'?'bank':'cash')} · ${window.I18n.language==='en'?'Current balance':'Số dư hiện tại'}: ${accountBalanceMarkup(x)}</small></div><div class="account-actions">${archived?`<button type="button" data-restore-account="${x.id}">${t('restore')}</button><button type="button" data-delete-account-permanently="${x.id}">${t('delete_forever')}</button>`:`<button type="button" data-archive-account="${x.id}">${t('archive')}</button>`}</div></div>`;
function renderAccounts(){const hasArchived=state.archivedAccounts.length>0;$('#account-list').innerHTML=state.accounts.length?state.accounts.map(x=>accountRow(x)).join(''):empty(t(hasArchived?'no_active_accounts':'no_accounts'),t(hasArchived?'restore_account_hint':'add_wallet_hint'));$('#archived-accounts').classList.toggle('hidden',!hasArchived);$('#archived-account-heading').textContent=t('archived_accounts',{count:state.archivedAccounts.length});$('#archived-account-list').innerHTML=state.archivedAccounts.map(x=>accountRow(x,true)).join('')}
function confirmAccountDeletion(permanent=false){const dialog=$('#delete-account-dialog');$('#delete-account-title').textContent=t(permanent?'permanent_delete_title':'archive');$('#delete-account-message').textContent=t(permanent?'permanent_delete_confirm':'archive_confirm');$('#delete-account-confirm').textContent=t(permanent?'delete_forever':'archive');dialog.returnValue='cancel';dialog.showModal();return new Promise(resolve=>dialog.addEventListener('close',()=>resolve(dialog.returnValue==='confirm'),{once:true}))}
function closeAccountDialogFromBackdrop(event){const dialog=event.currentTarget;if(event.target!==dialog)return;const rect=dialog.getBoundingClientRect(),outside=event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom;if(outside)dialog.close()}
function openImportModal(){if($('#app-shell').classList.contains('hidden'))return;const dialog=$('#import-modal');if(dialog.open)return;state.importHistoryPage=1;renderImportHistory();dialog.showModal()}
function navigate(id){if(isAdmin()&&id!=='admin')id='admin';else if(id==='admin'&&!isAdmin())id='dashboard';if(id==='import'){openImportModal();id='dashboard'}const target=document.getElementById(id)||$('#dashboard'),titles={dashboard:['dashboard','personal_finance'],transactions:['transactions','ledger'],import:['import_statement','safe_import'],budgets:['budgets','month_plan'],challenges:['challenges','behavior_change'],alerts:['alerts','finance_assistant'],statistics:['statistics','spending_analysis'],admin:['admin_console','system_operations']},labels=titles[target.id]||titles.dashboard;$$('.view').forEach(v=>v.classList.toggle('active',v===target));$$('.nav-item').forEach(l=>l.classList.toggle('active',l.dataset.view===target.id));$('#page-title').textContent=t(labels[0]);$('#page-kicker').textContent=t(labels[1]);$('#primary-nav').classList.remove('open');$('.menu-toggle')?.setAttribute('aria-expanded','false');window.scrollTo({top:0});if(location.hash!==`#${target.id}`)history.pushState(null,'',`#${target.id}`)}
document.addEventListener('click',async e=>{const preferences=$('.profile-preferences'),more=e.target.closest('.profile-more');if(more){const opening=preferences.classList.contains('hidden');preferences.classList.toggle('hidden',!opening);more.setAttribute('aria-expanded',String(opening));if(opening)closeNotifications();return}if(!e.target.closest('.profile-mini')&&!preferences.classList.contains('hidden'))closeProfileMenu();if(e.target.closest('[data-theme-choice],[data-language]')&&e.target.closest('.profile-preferences'))closeProfileMenu();const go=e.target.closest('[data-go],[data-view]');if(go){e.preventDefault();navigate(go.dataset.go||go.dataset.view);return}if(e.target.closest('.menu-toggle')){const nav=$('#primary-nav'),open=!nav.classList.contains('open');nav.classList.toggle('open',open);$('.menu-toggle').setAttribute('aria-expanded',String(open));return}if(e.target.closest('[data-action="edit-profile"]')){openProfileDialog();return}if(e.target.closest('[data-action="change-password"]')){openPasswordDialog();return}if(e.target.closest('[data-action="add-transaction"]')){if(!state.accounts.length)return toast(t('need_account'),t('add_account_first'));$('[name="date"]',$('#transaction-form')).value=new Date().toISOString().slice(0,10);$('#transaction-modal').showModal();return}if(e.target.closest('[data-action="accounts"]')){closeProfileMenu();$('#accounts-modal').showModal();return}if(e.target.closest('[data-action="support"]')){openSupportDialog();return}const ownReportPageButton=e.target.closest('[data-own-report-page]');if(ownReportPageButton&&!ownReportPageButton.disabled){loadOwnSupportReports(Number(ownReportPageButton.dataset.ownReportPage));return}if(e.target.closest('[data-action="import"]')){openImportModal();return}const del=e.target.closest('[data-delete-transaction]');if(del&&confirm(t('delete_transaction_confirm'))){try{await api(`/transactions/${del.dataset.deleteTransaction}`,{method:'DELETE'});await refreshCore();toast(t('deleted_transaction'))}catch(x){toast(t('delete_failed'),x.message)}return}const page=e.target.closest('[data-page]');if(page){loadTransactions(Number(page.dataset.page));return}const status=e.target.closest('[data-alert-status]');if(status){status.disabled=true;try{await api(`/alerts/${status.dataset.alertId}`,{method:'PATCH',body:JSON.stringify({status:status.dataset.alertStatus})});await loadAlerts()}catch(error){toast(t('alert_update_failed'),error.message)}finally{if(status.isConnected)status.disabled=false}return}const filter=e.target.closest('[data-alert-filter]');if(filter){setAlertFilter(filter.dataset.alertFilter);return}const edit=e.target.closest('[data-edit-budget]');if(edit){setBudget(Number(edit.dataset.editBudget));return}const removeBudget=e.target.closest('[data-delete-budget]');if(removeBudget&&await confirmBudgetDeletion(removeBudget.dataset.budgetName)){removeBudget.disabled=true;try{await api(`/budgets/${removeBudget.dataset.deleteBudget}`,{method:'DELETE'});await Promise.all([loadBudgets(),loadDashboard()]);toast(t('deleted_budget'))}catch(error){toast(t('budget_delete_failed'),error.message)}finally{if(removeBudget.isConnected)removeBudget.disabled=false}}});
document.addEventListener('error',event=>{const logo=event.target;if(!logo.matches?.('.bank-logo,.cat-logo'))return;logo.hidden=true;logo.nextElementSibling.hidden=false},true);
document.addEventListener('click',async event=>{const button=event.target.closest('[data-challenge-action]');if(!button)return;button.disabled=true;try{await api(`/challenges/${button.dataset.challengeId}/respond`,{method:'POST',body:JSON.stringify({action:button.dataset.challengeAction})});await loadChallenges();if(button.dataset.challengeAction==='ACCEPT')navigate('challenges')}catch(error){toast(t('request_failed'),error.message)}finally{if(button.isConnected)button.disabled=false}});
document.addEventListener('click',e=>{const more=e.target.closest('.profile-more');if(more?.getAttribute('aria-expanded')==='true')$('.account-menu-actions button',$('.profile-preferences')).focus()});
document.addEventListener('keydown',e=>{if(e.key!=='Escape')return;const preferences=$('.profile-preferences');if(!preferences.classList.contains('hidden')){preferences.classList.add('hidden');$('.profile-more').setAttribute('aria-expanded','false');$('.profile-more').focus()}const notif=$('#notif-panel');if(notif&&!notif.classList.contains('hidden')){closeNotifications();$('#notif-bell').focus()}});
$$('[data-month-step]').forEach(button=>button.addEventListener('click',()=>stepDashboardMonth(Number(button.dataset.monthStep))));
$$('[data-auth]').forEach(b=>b.addEventListener('click',()=>showAuth(b.dataset.auth)));
$$('[data-close-dialog]').forEach(b=>b.addEventListener('click',()=>b.closest('dialog').close()));
$('#accounts-modal').addEventListener('click',closeAccountDialogFromBackdrop);
$('#import-modal').addEventListener('click',closeAccountDialogFromBackdrop);
$('#accounts-modal').addEventListener('click',event=>{
  const button=event.target.closest('[data-toggle-balance]');
  if(!button)return;
  const id=Number(button.dataset.toggleBalance),item=account(id);
  if(!item)return;
  if(visibleAccountBalances.has(id))visibleAccountBalances.delete(id);else visibleAccountBalances.add(id);
  const container=button.closest('.account-balance');
  container.outerHTML=accountBalanceMarkup(item);
  $(`[data-toggle-balance="${id}"]`,$('#accounts-modal')).focus();
});
$('#accounts-modal').addEventListener('close',()=>{visibleAccountBalances.clear();renderAccounts()});
$('#dash-card-deck').addEventListener('keydown',event=>{
  if(event.key!=='Enter'&&event.key!==' ')return;
  const card=event.target.closest('.credit-card');
  if(!card||card.classList.contains('is-front')||!card.dataset.selectHeroCard)return;
  event.preventDefault();
  selectHeroCard(Number(card.dataset.selectHeroCard));
});
$('#dash-card-deck').addEventListener('click',event=>{
  const card=event.target.closest('.credit-card');
  if(event.target.closest('[data-toggle-hero-balance]')){if(card&&card.classList.contains('is-front'))toggleHeroBalance();return}
  if(card&&!card.classList.contains('is-front')&&card.dataset.selectHeroCard)selectHeroCard(Number(card.dataset.selectHeroCard));
});
$('#login-form').addEventListener('submit',async e=>{e.preventDefault();const f=e.currentTarget,b=$('[type="submit"]',f);formError(f);busy(b,true);try{await getCsrf();await api('/auth/login',{method:'POST',body:JSON.stringify(Object.fromEntries(new FormData(f)))});await getCsrf();await bootstrap()}catch(x){formError(f,x.message)}finally{busy(b,false)}});
$('#register-form').addEventListener('submit',async e=>{e.preventDefault();const f=e.currentTarget,b=$('[type="submit"]',f),d=Object.fromEntries(new FormData(f));d.consent=$('[name="consent"]',f).checked;formError(f);busy(b,true);try{await getCsrf();await api('/auth/register',{method:'POST',body:JSON.stringify(d)});await api('/auth/login',{method:'POST',body:JSON.stringify({email:d.email,password:d.password})});await getCsrf();await bootstrap()}catch(x){formError(f,x.message)}finally{busy(b,false)}});
$('#profile-form').addEventListener('submit',async event=>{event.preventDefault();const form=event.currentTarget,button=$('#save-profile'),avatar=form.elements.avatar.files[0];formError(form);busy(button,true);try{const data={full_name:form.elements.full_name.value,date_of_birth:form.elements.date_of_birth.value,email:form.elements.email.value};const updated=await api('/profile',{method:'PATCH',body:JSON.stringify(data)});state.profile=updated.profile;if(avatar){const body=new FormData();body.append('avatar',avatar);const uploaded=await api('/profile/avatar',{method:'POST',body});state.profile.avatar_url=uploaded.avatar_url}renderProfileIdentity();renderLiveHeader();$('#profile-dialog').close();toast(t('profile_updated'),t('profile_updated_detail'))}catch(error){formError(form,error.message)}finally{busy(button,false)}});
$('#password-form').addEventListener('submit',async event=>{event.preventDefault();const form=event.currentTarget,button=$('#save-password'),data=Object.fromEntries(new FormData(form));formError(form);if(data.new_password!==data.new_password_confirmation){formError(form,t('password_mismatch'));return}busy(button,true);try{await api('/profile/change-password',{method:'POST',body:JSON.stringify(data)});form.reset();$('#password-dialog').close();toast(t('password_changed'),t('password_changed_detail'))}catch(error){formError(form,error.message)}finally{busy(button,false)}});
$('#remove-profile-avatar').addEventListener('click',async event=>{const button=event.currentTarget;button.disabled=true;try{await api('/profile/avatar',{method:'DELETE'});state.profile.avatar_url=null;$('#profile-form').elements.avatar.value='';renderProfileIdentity();toast(t('avatar_removed'))}catch(error){formError($('#profile-form'),error.message)}finally{button.disabled=false}});
$('#profile-form').elements.avatar.addEventListener('change',event=>{const picture=event.currentTarget.files[0];if(!picture)return;const preview=$('.profile-avatar-preview'),url=URL.createObjectURL(picture);preview.textContent='';preview.style.backgroundImage=`url("${url}")`;preview.addEventListener('load',()=>URL.revokeObjectURL(url),{once:true})});
$('#transaction-form').addEventListener('submit',async e=>{e.preventDefault();const f=e.currentTarget,d=Object.fromEntries(new FormData(f)),b=$('#save-transaction');d.amount=String(d.amount).replace(/\D/g,'');busy(b,true);try{await api('/transactions',{method:'POST',body:JSON.stringify(d)});f.reset();$('#transaction-modal').close();await refreshCore();toast(t('saved_transaction'))}catch(x){toast(t('save_failed'),x.message)}finally{busy(b,false)}});
$('#account-form').addEventListener('submit',async e=>{e.preventDefault();const f=e.currentTarget,d=Object.fromEntries(new FormData(f)),b=$('#save-account');d.opening_balance=String(d.opening_balance).replace(/\D/g,'');busy(b,true);try{await api('/accounts',{method:'POST',body:JSON.stringify(d)});f.reset();await loadAccounts();populateSelects();toast(t('saved_account'))}catch(x){formError(f,x.message)}finally{busy(b,false)}});
$('#account-list').addEventListener('click',async e=>{const b=e.target.closest('[data-archive-account]');if(!b||!await confirmAccountDeletion())return;const id=Number(b.dataset.archiveAccount);b.disabled=true;try{await api(`/accounts/${id}`,{method:'DELETE'});await loadAccounts();populateSelects();toast(t('archived_account'))}catch(x){toast(t('archive_failed'),x.message)}finally{if(b.isConnected)b.disabled=false}});
$('#archived-account-list').addEventListener('click',async e=>{const restore=e.target.closest('[data-restore-account]');if(restore){restore.disabled=true;try{await api(`/accounts/${restore.dataset.restoreAccount}/restore`,{method:'POST'});await loadAccounts();populateSelects();toast(t('restored_account'))}catch(x){toast(t('restore_failed'),x.message)}finally{if(restore.isConnected)restore.disabled=false}return}const remove=e.target.closest('[data-delete-account-permanently]');if(!remove||!await confirmAccountDeletion(true))return;remove.disabled=true;try{await api(`/accounts/${remove.dataset.deleteAccountPermanently}/permanent`,{method:'DELETE'});state.importPreview=null;$('#import-preview').classList.add('hidden');file.value='';await loadAccounts();populateSelects();await refreshCore();toast(t('permanently_deleted_account'))}catch(x){toast(t('permanent_delete_failed'),x.message)}finally{if(remove.isConnected)remove.disabled=false}});
['#transaction-account','#transaction-direction'].forEach(s=>$(s).addEventListener('change',()=>loadTransactions()));['#transaction-date-from','#transaction-date-to'].forEach(s=>$(s).addEventListener('change',()=>{syncTransactionDateConstraints();renderTransactionDateFilterState();loadTransactions()}));$('#clear-transaction-dates').addEventListener('click',()=>{$('#transaction-date-from').value='';$('#transaction-date-to').value='';syncTransactionDateConstraints();renderTransactionDateFilterState();loadTransactions()});renderTransactionDateFilterState();$('#refresh-transactions').addEventListener('click',()=>loadTransactions());$('#transaction-search').addEventListener('input',()=>renderTransactions({items:state.transactions,total:state.transactions.length,page:1,pages:1}));
function syncTransactionIncomeFields(){
  const form=$('#transaction-form'),income=form.elements.direction.value==='IN';
  ['category_id','description'].forEach(name=>{const field=form.elements[name];field.disabled=income;field.closest('label').classList.toggle('hidden',income)});
  form.elements.category_id.required=!income;
}
$('#transaction-form').addEventListener('change',event=>{if(event.target.name==='direction')syncTransactionIncomeFields()});
$('#transaction-form').addEventListener('reset',()=>queueMicrotask(syncTransactionIncomeFields));
syncTransactionIncomeFields();
const analysisButton=document.createElement('button');
analysisButton.type='button';analysisButton.className='secondary-btn';analysisButton.textContent=t('spending_analysis_title');
$('#transactions .page-heading').append(analysisButton);
const analysisDialog=document.createElement('dialog');
analysisDialog.className='spending-analysis-dialog';document.body.append(analysisDialog);
analysisDialog.addEventListener('click',event=>{if(event.target.closest('[data-analysis-close]'))analysisDialog.close();else if(event.target===analysisDialog){const r=analysisDialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)analysisDialog.close()}});
analysisButton.addEventListener('click',async()=>{
  const range=selectedTransactionDateRange();if(!range)return toast(t('invalid_transaction_date_range'));
  analysisButton.disabled=true;
  try{
    // The endpoint always needs a bounded range, so an unset side falls back to
    // a bound wide enough to cover every transaction.
    const query=new URLSearchParams({date_from:range.dateFrom||ANALYSIS_MIN_DATE,date_to:range.dateTo||ANALYSIS_MAX_DATE});
    const data=await api(`/statistics/spending-analysis?${query}`);
    const advice=item=>item.status==='NO_BUDGET'?t('advice_no_budget'):item.status==='OVER'?t('advice_over',{amount:money(item.excess)}):item.status==='NEAR'?t('advice_near'):t('advice_within');
    analysisDialog.innerHTML=`<div class="panel-head"><h2>${t('spending_analysis_title')}</h2><button type="button" class="close-btn" data-analysis-close aria-label="${t('close')}">×</button></div><div class="analysis-content"><p>${esc(transactionDateRangeLabel(range))} · ${t('spending_analysis_scope')}</p><h3>${t('spending_analysis_total',{amount:money(data.total_expense)})}</h3><p>${t('spending_analysis_note')}</p>${data.comparisons.length?`<div class="table-wrap"><table><thead><tr><th>${t('col_month')}</th><th>${t('category')}</th><th>${t('col_spent_in_range')}</th><th>${t('col_monthly_budget')}</th><th>${t('col_suggestion')}</th></tr></thead><tbody>${data.comparisons.map(item=>`<tr><td>${esc(item.month)}</td><td>${esc(item.category)}</td><td>${money(item.amount)}</td><td>${item.budget===null?t('budget_not_set'):money(item.budget)}</td><td class="analysis-advice">${esc(advice(item))}</td></tr>`).join('')}</tbody></table></div>`:`<p>${t('spending_analysis_empty')}</p>`}</div>`;
    analysisDialog.showModal();
  }catch(error){toast(t('spending_analysis_failed'),error.message)}finally{analysisButton.disabled=false}
});
const file=$('#statement-file'),drop=$('#dropzone');
function updateImportAvailability(){const ready=file.files.length&&$('#import-account').value;$('#preview-import').disabled=!ready}
file.addEventListener('change',()=>{if(file.files.length){$('b',drop).textContent=file.files[0].name;$('p',drop).textContent=`${(file.files[0].size/1024).toFixed(1)} KB · ${t('ready')}`}updateImportAvailability()});
$('#import-account').addEventListener('change',updateImportAvailability);
['dragenter','dragover'].forEach(type=>drop.addEventListener(type,e=>{e.preventDefault();drop.classList.add('dragging')}));['dragleave','drop'].forEach(type=>drop.addEventListener(type,e=>{e.preventDefault();drop.classList.remove('dragging')}));drop.addEventListener('drop',e=>{if(e.dataTransfer.files.length){file.files=e.dataTransfer.files;file.dispatchEvent(new Event('change'))}});
$('#preview-import').addEventListener('click',async()=>{const b=$('#preview-import'),body=new FormData();body.append('file',file.files[0]);body.append('account_id',$('#import-account').value);busy(b,true,t('analyzing'));try{state.importPreview=await api('/imports/preview',{method:'POST',body});state.importReview={page:state.importPreview.page||1,pages:state.importPreview.pages||1,total:state.importPreview.preview_total||state.importPreview.new,fileTotal:state.importPreview.new+state.importPreview.duplicate+state.importPreview.error,decisions:{},categoryOverrides:{},notes:{}};renderImportPreview();if(state.importPreview.future_date_error)toast(t('future_date_alert'),t('future_date_warning',{count:state.importPreview.future_date_error}))}catch(x){toast(t('read_statement_failed'),x.message)}finally{busy(b,false)}});
function captureImportPageEdits(){if(!state.importPreview)return;$$('[data-import-decision]',$('#import-preview')).forEach(x=>state.importReview.decisions[x.dataset.importDecision]=x.dataset.decision);$$('[data-import-category]',$('#import-preview')).forEach(x=>state.importReview.categoryOverrides[x.dataset.importCategory]=x.value);$$('[data-import-note]',$('#import-preview')).forEach(x=>state.importReview.notes[x.dataset.importNote]=x.value)}
async function loadImportPreviewPage(page){if(!state.importPreview||page<1||page>state.importReview.pages||page===state.importReview.page)return;captureImportPageEdits();const pageData=await api(`/imports/${state.importPreview.batch_id}/preview?page=${page}&per_page=25`);Object.assign(state.importPreview,pageData);state.importReview.page=pageData.page;state.importReview.pages=pageData.pages;state.importReview.total=pageData.preview_total;renderImportPreview()}
function setImportDecision(button,decision){const accepted=decision==='KEEP',row=button.closest('[data-import-row]');button.dataset.decision=decision;state.importReview.decisions[button.dataset.importDecision]=decision;button.classList.toggle('accepted',accepted);button.classList.toggle('rejected',!accepted);button.setAttribute('aria-label',t(accepted?'approve_import':'reject_import'));$('.import-decision-icon',button).textContent=accepted?'✓':'×';$('.import-decision-label',button).textContent=t(accepted?'approve_import':'reject_import');row?.classList.toggle('rejected',!accepted)}
function updateImportDecisionSummary(){const rejected=Object.values(state.importReview.decisions).filter(decision=>decision==='REJECT').length,accepted=Math.max(0,(state.importPreview?.new||0)-rejected),confirm=$('#confirm-import');if(confirm){confirm.disabled=accepted===0;confirm.textContent=t('confirm_import',{count:accepted})}const summary=$('#import-selection-summary');if(summary)summary.textContent=t('selected_for_import',{count:accepted,total:state.importReview.fileTotal,duplicate:state.importPreview?.duplicate||0,invalid:state.importPreview?.error||0})}
function renderImportPreview(){
  const p=state.importPreview,review=state.importReview,rows=p.rows||p.sample||[],box=$('#import-preview'),detection=p.detection||{},futureErrors=(p.errors||[]).filter(x=>x.type==='FUTURE_DATE');
  const roleLabels={description:t('transaction_column'),date:t('transaction_date'),amount:t('amount'),debit:t('debit_column'),credit:t('credit_column'),direction:t('transaction_type'),ref_no:t('reference_column')};
  const columns=Object.entries(detection.columns||{}).map(([role,name])=>`${roleLabels[role]||role}: ${esc(name)}`).join(' · ');
  const categoryOptions=(selected)=>(p.categories||[]).map(category=>`<option value="${category.id}" ${Number(category.id)===Number(selected)?'selected':''}>${esc(displayCategoryText(category.name))}</option>`).join('');
  const validEntries=rows.map(row=>{const rowKey=String(row.row_number),decision=review.decisions[rowKey]||'KEEP',accepted=decision==='KEEP',selectedCategory=review.categoryOverrides[rowKey]||row.category_id,note=review.notes[rowKey]||'';return{rowNumber:row.row_number,html:`<tr class="import-preview-row ${accepted?'':'rejected'}" data-import-row="${row.row_number}">
    <td class="import-row-number">${row.row_number}</td>
    <td><button type="button" class="import-decision-btn ${accepted?'accepted':'rejected'}" data-import-decision="${row.row_number}" data-decision="${decision}" aria-label="${t(accepted?'approve_import':'reject_import')}"><span class="import-decision-icon">${accepted?'✓':'×'}</span><span class="import-decision-label">${t(accepted?'approve_import':'reject_import')}</span></button>${row.probable_duplicate_id?`<small class="duplicate-row-hint">${t('possible_duplicates')}</small>`:''}</td>
    <td>${dateVi(row.date)}</td>
    <td class="amount ${row.direction==='IN'?'in':'out'}">${row.direction==='IN'?'+':'−'} ${money(row.amount)}</td>
    <td><select data-import-category="${row.row_number}" data-original-category="${row.category_id}" aria-label="${t('category')}">${categoryOptions(selectedCategory)}</select>${Number(row.category_confidence)<.6?`<small class="category-hint">${t('category_review_hint')}</small>`:''}</td>
    <td class="import-description"><b>${esc(row.description||t('no_description'))}</b><small>${row.direction==='IN'?t('income_item'):t('expense_item')} · ${esc(row.ref_no||'—')}</small></td>
    <td>${esc(row.account_name||p.account?.name||'—')}</td>
    <td><input class="import-note-input" data-import-note="${row.row_number}" maxlength="500" value="${esc(note)}" placeholder="${t('row_note_placeholder')}" aria-label="${t('row_note')}"></td>
  </tr>`}});
  const errorEntries=(p.errors||[]).map(error=>({rowNumber:error.row_number,html:`<tr class="import-preview-row import-error-row">
    <td class="import-row-number">${error.row_number}</td>
    <td><span class="import-error-status"><span class="import-decision-icon">×</span>${t('cannot_import')}</span></td>
    <td colspan="6" class="import-error-detail"><b>${t('invalid_row')}</b><small>${esc(error.reason)}</small></td>
  </tr>`}));
  const tableRows=[...validEntries,...errorEntries].sort((left,right)=>left.rowNumber-right.rowNumber).map(entry=>entry.html).join('')||`<tr><td colspan="8">${t('no_importable_rows')}</td></tr>`;
  const pagination=review.pages>1?`<div class="import-pagination"><span>${t('preview_page',{page:review.page,pages:review.pages,total:review.total})}</span><div><button type="button" data-import-page="${review.page-1}" ${review.page<=1?'disabled':''}>‹ ${t('previous_page')}</button><button type="button" data-import-page="${review.page+1}" ${review.page>=review.pages?'disabled':''}>${t('next_page')} ›</button></div></div>`:'';
  box.innerHTML=`<div class="panel-head"><div><p class="eyebrow">${t('preview_result')}</p><h2 id="import-preview-title">${t('rows_analyzed',{count:p.new+p.duplicate+p.error})}</h2></div><span class="pill positive">${t('unsaved_data')}</span></div><div class="preview-stats"><div><strong>${p.new}</strong><span>${t('new_transactions')}</span></div><div class="warn"><strong>${p.duplicate}</strong><span>${t('exact_duplicates')}</span></div><div class="warn"><strong>${p.probable_duplicate}</strong><span>${t('possible_duplicates')}</span></div><div class="bad"><strong>${p.error}</strong><span>${t('error_rows')}</span></div></div>${p.duplicate?`<div class="import-warning"><b>${t('duplicate_warning',{count:p.duplicate})}</b><span>${t('duplicate_warning_detail')}</span></div>`:''}${futureErrors.length?`<div class="import-warning danger"><b>${t('future_date_warning',{count:futureErrors.length})}</b><span>${futureErrors.map(x=>t('future_date_row',{row:x.row_number,reason:x.reason})).join(' · ')}</span></div>`:''}<div class="detection-summary ${detection.needs_review?'review':''}"><b>${detection.needs_review?t('review_mapping'):t('columns_detected')}</b><span>${t('header_row',{row:detection.header_row||1})} · ${t('detection_confidence',{percent:Math.round(Number(detection.confidence||0)*100)})}${detection.balance_verified?` · ${t('balance_verified')}`:''}</span>${columns?`<small>${columns}</small>`:''}</div><div class="import-selection-summary" id="import-selection-summary"></div><div class="table-wrap import-review"><table><thead><tr><th>${t('import_row_number')}</th><th>${t('import_decision')}</th><th>${t('transaction_date')}</th><th>${t('amount')}</th><th>${t('category')}</th><th>${t('transaction_column')}</th><th>${t('accounts')}</th><th>${t('row_note')}</th></tr></thead><tbody>${tableRows}</tbody></table></div>${pagination}<div class="import-actions">${p.error?`<a class="secondary-btn" href="/imports/${p.batch_id}/errors.csv">${t('download_error_report')}</a>`:''}<button type="button" class="secondary-btn" id="cancel-import-preview">${t('cancel_import')}</button><button type="button" class="secondary-btn" id="reset-import-edits">↶ ${t('cancel_edits')}</button><button class="primary-btn" id="confirm-import">${t('confirm_import',{count:rows.length})}</button></div>`;
  $('#confirm-import').addEventListener('click',confirmImport);updateImportDecisionSummary();if(!box.open)box.showModal();
}
async function confirmImport(){captureImportPageEdits();const decisions=state.importReview.decisions,categoryOverrides=state.importReview.categoryOverrides,notes=state.importReview.notes,b=$('#confirm-import');busy(b,true);try{const d=await api(`/imports/${state.importPreview.batch_id}/confirm`,{method:'POST',body:JSON.stringify({decisions,category_overrides:categoryOverrides,notes})});toast(t('import_success'),t('imported_count',{count:d.imported}));state.importPreview=null;state.importReview={page:1,pages:1,total:0,fileTotal:0,decisions:{},categoryOverrides:{},notes:{}};const preview=$('#import-preview');if(preview.open)preview.close();preview.innerHTML='';file.value='';state.importHistoryPage=1;await applyLatestDataMonth();await Promise.all([refreshCore(),loadImportHistory()])}catch(x){toast(t('confirm_failed'),x.message)}finally{busy(b,false)}}
function confirmImportTransactionRemoval(){const dialog=$('#remove-import-dialog');$('#remove-import-title').textContent=t('remove_import_title');$('#remove-import-message').textContent=t('remove_import_confirm');$('#remove-import-cancel').textContent=t('cancel');$('#remove-import-confirm').textContent=t('remove_import_action');dialog.returnValue='cancel';dialog.showModal();return new Promise(resolve=>dialog.addEventListener('close',()=>resolve(dialog.returnValue==='confirm'),{once:true}))}
// Deleting history is metadata housekeeping, so the user says outright whether
// the transactions the import created go with it. An entry whose transactions
// are already gone only offers the plain delete.
function confirmHistoryDeletion(title,message,transactions){
  const dialog=$('#delete-history-dialog'),removable=transactions>0;
  $('#delete-history-title').textContent=title;
  $('#delete-history-message').textContent=message;
  $('#delete-history-keep').textContent=t(removable?'delete_history_only':'delete_import_history');
  $('#delete-history-all').classList.toggle('hidden',!removable);
  dialog.returnValue='cancel';
  dialog.showModal();
  return new Promise(resolve=>dialog.addEventListener('close',()=>resolve(dialog.returnValue),{once:true}));
}
async function deleteImportHistory(path,transactions,title,message){
  const choice=await confirmHistoryDeletion(title,message,transactions);
  if(choice!=='history'&&choice!=='all')return;
  try{
    const separator=path.includes('?')?'&':'?';
    const result=await api(choice==='all'?`${path}${separator}remove_transactions=1`:path,{method:'DELETE'});
    state.selectedImportHistoryIds.clear();
    await Promise.all([refreshCore(),loadImportHistory()]);
    toast(t('import_history_deleted'),result.removed_transactions
      ?t('import_history_deleted_removed',{deleted:result.deleted,removed:result.removed_transactions})
      :t('import_history_deleted_kept',{deleted:result.deleted}));
  }catch(error){toast(t('import_history_delete_failed'),error.message)}
}
function updateImportHistorySelection(){
  const button=$('#delete-selected-history'),count=state.selectedImportHistoryIds.size,total=state.importHistory.length;
  button.classList.toggle('hidden',!total);
  button.disabled=!count;
  button.textContent=count?t('delete_selected_history_count',{count}):t('delete_selected_history');
  const all=$('#import-history-select-all');
  // Ticking the header box takes the whole history, not just the page on screen,
  // so clearing everything stays one click away.
  if(all){all.checked=count>0&&count===total;all.indeterminate=count>0&&count<total}
}
$('#import-history').addEventListener('change',event=>{
  const box=event.target.closest('[data-import-history-select]');
  if(box){
    const id=Number(box.dataset.importHistorySelect);
    if(box.checked)state.selectedImportHistoryIds.add(id);else state.selectedImportHistoryIds.delete(id);
    updateImportHistorySelection();
    return;
  }
  if(event.target.id!=='import-history-select-all')return;
  if(event.target.checked)state.importHistory.forEach(item=>state.selectedImportHistoryIds.add(item.id));
  else state.selectedImportHistoryIds.clear();
  renderImportHistory();
});
$('#delete-selected-history').addEventListener('click',()=>{
  const ids=[...state.selectedImportHistoryIds];
  if(!ids.length)return;
  const selected=state.importHistory.filter(item=>state.selectedImportHistoryIds.has(item.id)),
    transactions=selected.reduce((total,item)=>total+item.transaction_count,0);
  deleteImportHistory(`/imports/history?ids=${ids.join(',')}`,transactions,t('delete_import_history_title'),
    t(transactions?'delete_selected_history_confirm':'delete_selected_history_confirm_empty',{count:ids.length,transactions}));
});
$('#import-history').addEventListener('click',async event=>{const pageButton=event.target.closest('[data-import-history-page]');if(pageButton){if(!pageButton.disabled){state.importHistoryPage=Number(pageButton.dataset.importHistoryPage);renderImportHistory()}return}const button=event.target.closest('[data-delete-import-transactions]');if(!button||button.disabled||!await confirmImportTransactionRemoval())return;button.disabled=true;try{const result=await api(`/imports/${button.dataset.deleteImportTransactions}/transactions`,{method:'DELETE'});await Promise.all([refreshCore(),loadImportHistory()]);toast(t('remove_import_success'),t('removed_imported_count',{count:result.removed}))}catch(error){toast(t('remove_import_failed'),error.message)}finally{if(button.isConnected)button.disabled=false}});
function renderBudgetDialogLanguage(){const form=$('#budget-form'),select=form.elements.category_id,selected=select.value;select.innerHTML=state.categories.map(item=>`<option value="${item.id}">${esc(displayCategoryName(item))}</option>`).join('');if(selected&&[...select.options].some(option=>option.value===selected))select.value=selected;$('#budget-dialog-month').textContent=formatStatisticsMonth(state.month)}
function confirmBudgetDeletion(name){const dialog=$('#delete-budget-dialog');$('#delete-budget-title').textContent=t('delete_budget_title');$('#delete-budget-message').textContent=t('delete_budget_confirm',{name});$('#delete-budget-cancel').textContent=t('cancel');$('#delete-budget-confirm').textContent=t('delete_budget_action');dialog.returnValue='cancel';dialog.showModal();return new Promise(resolve=>dialog.addEventListener('close',()=>resolve(dialog.returnValue==='confirm'),{once:true}))}
function setBudget(categoryId){const form=$('#budget-form');form.reset();formError(form);renderBudgetDialogLanguage();if(categoryId)form.elements.category_id.value=String(categoryId);$('#budget-dialog').showModal()}
$('#budget-form').addEventListener('submit',async event=>{event.preventDefault();const form=event.currentTarget,data=Object.fromEntries(new FormData(form)),button=$('#save-budget'),amount=String(data.amount).trim();if(!/^\d+$/.test(amount)){formError(form,t('budget_update_failed'));return}data.category_id=Number(data.category_id);data.amount=amount;data.month=state.month;button.disabled=true;button.setAttribute('aria-busy','true');try{await api('/budgets',{method:'PUT',body:JSON.stringify(data)});$('#budget-dialog').close();await Promise.all([loadBudgets(),loadDashboard()]);toast(t('budget_updated'))}catch(error){formError(form,error.message);toast(t('budget_update_failed'),error.message)}finally{button.disabled=false;button.removeAttribute('aria-busy')}});
$$('[data-action="tour"]').forEach(x=>x.addEventListener('click',()=>{closeProfileMenu();window.Tour?.start()}));
$$('[data-action="budget"]').forEach(x=>x.addEventListener('click',()=>setBudget()));$$('[data-action="toast"]').forEach(x=>x.addEventListener('click',async()=>{try{const d=await api('/budgets/copy',{method:'POST',body:JSON.stringify({month:state.month})});await Promise.all([loadBudgets(),loadDashboard()]);toast(t('copied_budget'),t('copied_categories',{count:d.copied}))}catch(e){toast(t('copy_failed'),e.message)}}));
document.addEventListener('click',e=>{
  const bell=$('#notif-bell'),panel=$('#notif-panel');if(!bell||!panel)return;
  if(e.target.closest('#notif-bell')||e.target.closest('[data-open-notifications]')){const willOpen=panel.classList.contains('hidden');closeProfileMenu();panel.classList.toggle('hidden',!willOpen);bell.setAttribute('aria-expanded',String(willOpen));return}
  if(!e.target.closest('#notif-panel')&&!e.target.closest('[data-alert-status]'))closeNotifications();
});
$('#notif-mark-all').addEventListener('click',async event=>{const button=event.currentTarget,items=state.alerts.filter(item=>item.status==='UNREAD');if(!items.length)return;button.disabled=true;button.setAttribute('aria-busy','true');try{const results=await Promise.allSettled(items.map(item=>api(`/alerts/${item.id}`,{method:'PATCH',body:JSON.stringify({status:'READ'})}))),failed=results.filter(result=>result.status==='rejected');await loadAlerts();if(failed.length)toast(t('alert_update_failed'),failed[0]?.reason?.message||'');else toast(t('all_alerts_read'))}catch(error){toast(t('alert_update_failed'),error.message)}finally{button.removeAttribute('aria-busy');button.disabled=!state.alerts.some(item=>item.status==='UNREAD')}});
$('#logout').addEventListener('click',async event=>{const button=event.currentTarget,preferences=$('.profile-preferences');button.disabled=true;preferences.classList.add('hidden');$('.profile-more').setAttribute('aria-expanded','false');try{await api('/auth/logout',{method:'POST'});state.csrf='';state.profile=null;applyAdminVisibility();navigate('dashboard');if($('#accounts-modal').open)$('#accounts-modal').close();showAuth()}catch(e){toast(t('logout_failed'),e.message)}finally{button.disabled=false}});

const isAdmin=()=>['ADMIN','SUPPORT_ADMIN'].includes(state.profile?.role);
const isPrimaryAdmin=()=>state.profile?.role==='ADMIN';
function adminStatusPill(status){return status==='LOCKED'?`<span class="pill negative">${t('locked')}</span>`:`<span class="pill positive">${t('active')}</span>`}
function adminDate(value){return value?new Date(value).toLocaleDateString(locale()):'—'}
async function loadAdminOperations(){
  const target=$('#admin-operations');
  try{
    const data=await api('/admin/operations');
    if(data.suppressed){target.innerHTML=`<article class="metric-card"><p>${t('metrics_suppressed')}</p><strong>${t('not_enough_users')}</strong><small>${esc(data.reason||'')}</small></article>`;return}
    const rates=Object.entries(data.import_success_rate_by_bank||{});
    target.innerHTML=`
      <article class="metric-card accent"><div class="metric-head"><span class="metric-icon mint">◎</span></div><p>${t('active_users_30d')}</p><strong>${data.active_users}</strong><small>${t('last_30_days')}</small></article>
      <article class="metric-card"><div class="metric-head"><span class="metric-icon blue">⇧</span></div><p>${t('import_success_rate')}</p><strong>${rates.length?`${rates[0][1]}%`:'—'}</strong><small>${esc(rates.map(([bank,rate])=>`${bank} ${rate}%`).join(' · '))||t('no_imports_yet')}</small></article>
      <article class="metric-card"><div class="metric-head"><span class="metric-icon coral">!</span></div><p>${t('import_error_rows')}</p><strong>${data.error_count}</strong><small>${t('all_batches')}</small></article>
      <article class="metric-card"><div class="metric-head"><span class="metric-icon violet">↻</span></div><p>${t('nightly_job')}</p><strong>${esc(data.nightly_job_status)}</strong><small>${t('last_run')}</small></article>`;
  }catch(error){target.innerHTML=empty(t('load_failed'),error.message)}
}
async function loadAdminUsers(query='',page=1){
  const body=$('#admin-user-rows');
  try{
    const params=new URLSearchParams({q:query,page:String(page),per_page:'10',status:$('#admin-user-status').value,role:'USER'}),data=await api(`/admin/users?${params}`);
    if(page>1&&page>Math.max(data.pages,1))return loadAdminUsers(query,Math.max(data.pages,1));
    state.adminUserPage=data.page;
    body.innerHTML=data.items.length?data.items.map(user=>`<tr>
      <td><b>${esc(user.full_name)}</b><br><small>${esc(user.email)}</small></td>
      <td>${adminStatusPill(user.status)} ${user.role==='SUPPORT_ADMIN'?`<span class="pill neutral">${t('support_admin')}</span>`:''}${user.deletion_requested?` <span class="pill neutral">${t('deletion_requested')}</span>`:''}</td>
      <td>${adminDate(user.registration_date)}</td><td>${adminDate(user.last_login)}</td>
      <td class="admin-actions-cell"><div class="admin-row-actions">
        ${user.role==='USER'?`<button class="secondary-btn" data-admin-action="${user.status==='LOCKED'?'unlock':'lock'}" data-admin-user="${user.id}">${user.status==='LOCKED'?t('unlock'):t('lock')}</button>
        <button class="secondary-btn" data-admin-action="reset" data-admin-user="${user.id}">${t('reset_password')}</button>
        ${user.deletion_requested?`<button class="secondary-btn" data-admin-action="erase" data-admin-user="${user.id}" data-admin-name="${esc(user.full_name)}">${t('execute_erasure')}</button>`:''}`:''}
        ${user.can_manage_role?`<button class="secondary-btn" data-admin-action="role" data-admin-role="${user.role==='SUPPORT_ADMIN'?'USER':'SUPPORT_ADMIN'}" data-admin-user="${user.id}">${t(user.role==='SUPPORT_ADMIN'?'revoke_admin':'grant_support_admin')}</button>${user.role==='USER'?`<button class="danger-outline-btn" data-admin-action="violation-delete" data-admin-user="${user.id}" data-admin-name="${esc(user.full_name)}">${t('delete_violation')}</button>`:''}`:''}
      </div></td></tr>`).join(''):`<tr><td colspan="5">${empty(t('no_users'),t('no_users_detail'))}</td></tr>`;
    const pages=Math.max(data.pages,1);
    $('#admin-user-page-info').textContent=t('admin_user_count',{total:data.total,page:data.page,pages});
    $('#admin-user-page-buttons').innerHTML=`<button data-admin-page="${Math.max(1,data.page-1)}" ${data.page<=1?'disabled':''} aria-label="${t('previous_page')}">‹</button><button class="active" aria-current="page">${data.page}</button><button data-admin-page="${Math.min(pages,data.page+1)}" ${data.page>=pages?'disabled':''} aria-label="${t('next_page')}">›</button>`;
  }catch(error){body.innerHTML=`<tr><td colspan="5">${empty(t('load_failed'),error.message)}</td></tr>`;$('#admin-user-page-info').textContent='—';$('#admin-user-page-buttons').innerHTML=''}
}
async function loadAdminImportConfig(){
  const body=$('#admin-import-rows');
  try{
    const data=await api('/admin/import-config');
    const rows=[...data.templates.map(item=>({kind:'template',id:item.id,label:`${item.bank_code} — ${item.name}`,detail:t('bank_template'),active:item.active})),
                ...data.rules.map(item=>({kind:'rule',id:item.id,label:`#${item.priority}`,detail:item.pattern,active:item.active}))];
    body.innerHTML=rows.map(row=>`<tr><td><b>${esc(row.label)}</b></td><td><small>${esc(row.detail)}</small></td>
      <td><button class="secondary-btn" data-admin-toggle="${row.kind}" data-admin-id="${row.id}" data-admin-active="${row.active?'1':'0'}">${row.active?t('on'):t('off')}</button></td></tr>`).join('');
  }catch(error){body.innerHTML=`<tr><td colspan="3">${empty(t('load_failed'),error.message)}</td></tr>`}
}
async function loadAdminAuditLogs(){
  const target=$('#admin-audit-list');
  try{
    const data=await api('/admin/audit-logs');
    target.innerHTML=data.items.length?data.items.slice(0,12).map(item=>`<div class="budget-row"><span class="cat-icon travel">≡</span><div><b>${esc(item.action)}</b><small>${new Date(item.created_at).toLocaleString(locale())}</small></div><span></span></div>`).join(''):empty(t('no_audit_logs'),t('no_audit_logs_detail'));
  }catch(error){target.innerHTML=empty(t('load_failed'),error.message)}
}
let supportAdminPage=1;
async function loadSupportAdmins(page=1){
  if(!isPrimaryAdmin())return;
  const body=$('#support-admin-rows'),pager=$('#support-admin-pagination');
  try{
    const params=new URLSearchParams({q:$('#support-admin-search').value.trim(),role:'SUPPORT_ADMIN',page:String(page),per_page:'10'});
    const data=await api(`/admin/users?${params}`),pages=Math.max(data.pages,1);
    if(page>pages)return loadSupportAdmins(pages);
    supportAdminPage=data.page;
    body.innerHTML=data.items.length?data.items.map(user=>`<tr><td><b>${esc(user.full_name)}</b><br><small>${esc(user.email)}</small></td><td>${adminStatusPill(user.status)}</td><td>${adminDate(user.registration_date)}</td><td>${adminDate(user.last_login)}</td><td>${user.can_manage_role?`<button class="secondary-btn" data-admin-action="role" data-admin-role="USER" data-admin-user="${user.id}">${t('revoke_admin')}</button>`:''}</td></tr>`).join(''):`<tr><td colspan="5">${empty(t('no_users'),t('no_users_detail'))}</td></tr>`;
    pager.innerHTML=`<span>${t('admin_user_count',{total:data.total,page:data.page,pages})}</span><div><button data-support-page="${page-1}" ${page<=1?'disabled':''} aria-label="${t('previous_page')}">‹</button><button class="active" aria-current="page">${page}</button><button data-support-page="${page+1}" ${page>=pages?'disabled':''} aria-label="${t('next_page')}">›</button></div>`;
  }catch(error){body.innerHTML=`<tr><td colspan="5">${empty(t('load_failed'),error.message)}</td></tr>`;pager.innerHTML=''}
}
// User-to-admin reports (FR support desk). The list a user sees is their own
// (/support-reports); the admin table is /admin/support-reports, which SUPPORT_ADMIN
// may also read — so the panel lives outside the primary-admin-only block.
const supportStatusPill=status=>status==='RESOLVED'?`<span class="pill positive">${t('support_status_resolved')}</span>`:`<span class="pill neutral">${t('support_status_open')}</span>`;
const supportDateTime=value=>value?new Date(value).toLocaleString(locale()):'—';
function pagerButtons(page,pages,attribute){return `<div><button type="button" data-${attribute}="${page-1}" ${page<=1?'disabled':''} aria-label="${t('previous_page')}">‹</button><button type="button" class="active" aria-current="page">${page}</button><button type="button" data-${attribute}="${page+1}" ${page>=pages?'disabled':''} aria-label="${t('next_page')}">›</button></div>`}
let ownReportPage=1;
async function loadOwnSupportReports(page=1){
  const body=$('#support-report-list'),pager=$('#support-report-pagination');
  try{
    const data=await api(`/support-reports?page=${page}`),pages=Math.max(data.pages,1);
    if(page>pages)return loadOwnSupportReports(pages);
    ownReportPage=data.page;
    body.innerHTML=data.items.length?data.items.map(item=>`<article class="support-report-item"><div><b>${esc(item.subject)}</b>${supportStatusPill(item.status)}</div><p>${esc(item.message)}</p><small>${supportDateTime(item.created_at)}</small></article>`).join(''):empty(t('no_support_reports'),t('no_support_reports_detail'));
    pager.innerHTML=data.total?`<span>${t('support_report_count',{total:data.total,page:data.page,pages})}</span>${pagerButtons(data.page,pages,'own-report-page')}`:'';
  }catch(error){body.innerHTML=empty(t('load_failed'),error.message);pager.innerHTML=''}
}
let adminReportPage=1;
async function loadAdminSupportReports(page=1){
  if(!isAdmin())return;
  const body=$('#support-report-rows'),pager=$('#support-report-admin-pagination');
  try{
    const params=new URLSearchParams({status:$('#support-report-status').value,page:String(page),per_page:'10'});
    const data=await api(`/admin/support-reports?${params}`),pages=Math.max(data.pages,1);
    if(page>pages)return loadAdminSupportReports(pages);
    adminReportPage=data.page;
    body.innerHTML=data.items.length?data.items.map(item=>`<tr>
      <td><b>${esc(item.user.full_name)}</b><br><small>${esc(item.user.email)}</small></td>
      <td>${esc(item.subject)}</td>
      <td class="support-message-cell">${esc(item.message)}</td>
      <td>${supportDateTime(item.created_at)}</td>
      <td>${supportStatusPill(item.status)}</td>
      <td><button class="secondary-btn" data-report-action data-report-id="${item.id}" data-report-status="${item.status==='RESOLVED'?'OPEN':'RESOLVED'}">${t(item.status==='RESOLVED'?'reopen_report':'mark_resolved')}</button></td></tr>`).join(''):`<tr><td colspan="6">${empty(t('no_admin_support_reports'),t('no_admin_support_reports_detail'))}</td></tr>`;
    pager.innerHTML=`<span>${t('support_report_count',{total:data.total,page:data.page,pages})}</span>${pagerButtons(data.page,pages,'report-page')}`;
  }catch(error){body.innerHTML=`<tr><td colspan="6">${empty(t('load_failed'),error.message)}</td></tr>`;pager.innerHTML=''}
}
$('#support-report-status').addEventListener('change',()=>loadAdminSupportReports(1));
$('#support-form').addEventListener('submit',async event=>{
  event.preventDefault();
  const form=event.currentTarget,button=$('#send-support-report'),data=Object.fromEntries(new FormData(form));
  formError(form);
  button.disabled=true;button.setAttribute('aria-busy','true');
  try{
    await api('/support-reports',{method:'POST',body:JSON.stringify({subject:String(data.subject||'').trim(),message:String(data.message||'').trim()})});
    form.reset();
    await loadOwnSupportReports(1);
    toast(t('support_sent'),t('support_sent_detail'));
  }catch(error){formError(form,error.message);toast(t('support_send_failed'),error.message)}
  finally{button.disabled=false;button.removeAttribute('aria-busy')}
});
async function loadAdmin(){if(!isAdmin())return;const tasks=[loadAdminUsers($('#admin-user-search').value.trim()),loadAdminSupportReports(adminReportPage)];if(isPrimaryAdmin())tasks.push(loadSupportAdmins(),loadAdminOperations(),loadAdminImportConfig(),loadAdminAuditLogs());await Promise.all(tasks)}
function applyAdminVisibility(){const admin=isAdmin();$$('.admin-only').forEach(node=>node.classList.toggle('hidden',!admin));$$('.primary-admin-only').forEach(node=>node.classList.toggle('hidden',!isPrimaryAdmin()));$$('.nav-item:not(.admin-only),.view:not(#admin),[data-action="add-transaction"],[data-action="accounts"],[data-action="import"],[data-action="support"]').forEach(node=>node.classList.toggle('hidden',admin))}

async function refreshCore(){await Promise.all([loadAccounts(),loadTransactions(),loadDashboard(),loadBudgets(),loadAlerts(),loadChallenges(),loadStatistics()])}
$('#statistics-period').addEventListener('change',renderTrend);
$('#overview-chart').addEventListener('pointerover',event=>{const bar=event.target.closest('.bar');if(bar)showOverviewChip(bar)});
$('#overview-chart').addEventListener('focusin',event=>{const bar=event.target.closest('.bar');if(bar)showOverviewChip(bar)});
$('#overview-chart').addEventListener('pointerleave',hideOverviewChip);
$('#overview-chart').addEventListener('focusout',hideOverviewChip);
function clearStatisticsDateValidity(){$('#statistics-date-from').setCustomValidity('');$('#statistics-date-to').setCustomValidity('')}
function restoreStatisticsBreakdownSelection(){const dateFrom=$('#statistics-date-from'),dateTo=$('#statistics-date-to');dateFrom.value=state.statisticsRenderedDateFrom;dateTo.value=state.statisticsRenderedDateTo;clearStatisticsDateValidity();state.statisticsDateFrom=state.statisticsRenderedDateFrom;state.statisticsDateTo=state.statisticsRenderedDateTo}
$('#statistics-range-form').addEventListener('submit',async event=>{event.preventDefault();const dateFromInput=$('#statistics-date-from'),dateToInput=$('#statistics-date-to'),selectedDateFrom=dateFromInput.value,selectedDateTo=dateToInput.value,range=statisticsDateRange(selectedDateFrom,selectedDateTo),button=$('#apply-statistics-range');clearStatisticsDateValidity();if(!range){state.statisticsBreakdownRequest+=1;state.statisticsDateFrom=state.statisticsRenderedDateFrom;state.statisticsDateTo=state.statisticsRenderedDateTo;dateToInput.setCustomValidity(t('invalid_statistics_date_range'));dateToInput.reportValidity();toast(t('invalid_statistics_date_range'));return}state.statisticsDateFrom=selectedDateFrom;state.statisticsDateTo=selectedDateTo;busy(button,true);try{await Promise.all([loadStatisticsBreakdown(),loadStatisticsTrend()])}catch(error){if(state.statisticsDateFrom===selectedDateFrom&&state.statisticsDateTo===selectedDateTo){restoreStatisticsBreakdownSelection();toast(t('statistics_load_failed'),error.message)}}finally{busy(button,false)}});
['#statistics-date-from','#statistics-date-to'].forEach(selector=>$(selector).addEventListener('input',clearStatisticsDateValidity));
window.addEventListener('languagechange',async()=>{clearStatisticsDateValidity();navigate(location.hash.slice(1)||'dashboard');renderLiveHeader();populateSelects();renderAccounts();renderChallenges();analysisButton.textContent=t('spending_analysis_title');if($('#budget-dialog').open)renderBudgetDialogLanguage();if(file.files.length)file.dispatchEvent(new Event('change'));if(state.importPreview)renderImportPreview();renderImportHistory();if($('#support-dialog').open)await loadOwnSupportReports(ownReportPage);if(isAdmin()){await loadAdmin();return}if(state.profile)await Promise.all([loadDashboard(),loadTransactions(),loadBudgets(),loadAlerts(),loadChallenges(),loadStatistics()])});
async function refreshRealtimeData(){if(!state.profile||document.hidden||state.realtimeRefresh)return;if(isAdmin()){await Promise.all([loadAdminOperations(),loadAdminSupportReports(adminReportPage)]);return}state.realtimeRefresh=true;try{await Promise.all([loadAccounts(),loadDashboard(),loadTransactions(),loadBudgets(),loadAlerts(),loadChallenges()])}catch(error){if(error.status===401)state.profile=null}finally{state.realtimeRefresh=false}}
setInterval(renderLiveHeader,60000);setInterval(refreshRealtimeData,60000);document.addEventListener('visibilitychange',()=>{renderLiveHeader();if(!document.hidden)refreshRealtimeData()});

async function adminConfirm(message){const dialog=$('#admin-confirm-dialog');$('#admin-confirm-message').textContent=message;dialog.showModal();return new Promise(resolve=>dialog.addEventListener('close',()=>resolve(dialog.returnValue==='confirm'),{once:true}))}
document.addEventListener('click',async event=>{
  const supportPageButton=event.target.closest('[data-support-page]');
  if(supportPageButton&&!supportPageButton.disabled){await loadSupportAdmins(Number(supportPageButton.dataset.supportPage));return}
  const pageButton=event.target.closest('[data-admin-page]');
  if(pageButton){await loadAdminUsers($('#admin-user-search').value.trim(),Number(pageButton.dataset.adminPage));return}
  const reportPageButton=event.target.closest('[data-report-page]');
  if(reportPageButton&&!reportPageButton.disabled){await loadAdminSupportReports(Number(reportPageButton.dataset.reportPage));return}
  const reportAction=event.target.closest('[data-report-action]');
  if(reportAction){
    const nextStatus=reportAction.dataset.reportStatus;
    reportAction.disabled=true;
    try{await api(`/admin/support-reports/${reportAction.dataset.reportId}`,{method:'PATCH',body:JSON.stringify({status:nextStatus})});await loadAdminSupportReports(adminReportPage);toast(t(nextStatus==='RESOLVED'?'support_report_resolved':'support_report_reopened'))}
    catch(error){toast(t('support_report_update_failed'),error.message);if(reportAction.isConnected)reportAction.disabled=false}
    return;
  }
  const toggle=event.target.closest('[data-admin-toggle]');
  if(toggle){
    toggle.disabled=true;
    try{await api(`/admin/import-config/${toggle.dataset.adminToggle}/${toggle.dataset.adminId}`,{method:'PATCH',body:JSON.stringify({active:toggle.dataset.adminActive!=='1'})});await loadAdminImportConfig()}
    catch(error){toast(t('update_failed'),error.message);if(toggle.isConnected)toggle.disabled=false}
    return;
  }
  const action=event.target.closest('[data-admin-action]');
  if(!action)return;
  const userId=action.dataset.adminUser,kind=action.dataset.adminAction;
  if(kind==='erase'&&!await adminConfirm(t('confirm_erasure',{name:action.dataset.adminName||''})))return;
  if(kind==='violation-delete'&&!await adminConfirm(t('confirm_violation_delete',{name:action.dataset.adminName||''})))return;
  action.disabled=true;
  try{
    if(kind==='lock'||kind==='unlock'){await api(`/admin/users/${userId}/${kind}`,{method:'POST'});toast(kind==='lock'?t('user_locked'):t('user_unlocked'))}
    else if(kind==='reset'){const data=await api(`/admin/users/${userId}/reset-password`,{method:'POST'});toast(t('temporary_password'),data.temporary_password)}
    else if(kind==='erase'){await api(`/admin/users/${userId}`,{method:'DELETE'});toast(t('erasure_done'))}
    else if(kind==='role'){await api(`/admin/users/${userId}/role`,{method:'PATCH',body:JSON.stringify({role:action.dataset.adminRole})});toast(t(action.dataset.adminRole==='SUPPORT_ADMIN'?'admin_granted':'admin_revoked'))}
    else if(kind==='violation-delete'){await api(`/admin/users/${userId}/violation`,{method:'DELETE'});toast(t('violation_deleted'))}
    await loadAdminUsers($('#admin-user-search').value.trim(),state.adminUserPage);
    if(kind==='role')await loadSupportAdmins(supportAdminPage);
  }catch(error){toast(t('action_failed'),error.message)}
  finally{if(action.isConnected)action.disabled=false}
});
let adminSearchTimer;
$('#admin-user-search').addEventListener('input',event=>{clearTimeout(adminSearchTimer);const value=event.target.value.trim();adminSearchTimer=setTimeout(()=>loadAdminUsers(value,1),250)});
$('#admin-user-status').addEventListener('change',()=>loadAdminUsers($('#admin-user-search').value.trim(),1));
let supportSearchTimer;
$('#support-admin-search').addEventListener('input',()=>{clearTimeout(supportSearchTimer);supportSearchTimer=setTimeout(()=>loadSupportAdmins(1),250)});
const importPreviewBox=$('#import-preview');
importPreviewBox.addEventListener('click',async event=>{
  if(event.target===importPreviewBox){
    const bounds=importPreviewBox.getBoundingClientRect();
    const outside=event.clientX<bounds.left||event.clientX>bounds.right||event.clientY<bounds.top||event.clientY>bounds.bottom;
    if(outside){$('#cancel-import-preview',importPreviewBox)?.click();return}
  }
  const decisionButton=event.target.closest('[data-import-decision]');
  if(decisionButton){setImportDecision(decisionButton,decisionButton.dataset.decision==='KEEP'?'REJECT':'KEEP');updateImportDecisionSummary();return}
  const pageButton=event.target.closest('[data-import-page]');
  if(pageButton&&!pageButton.disabled){pageButton.disabled=true;try{await loadImportPreviewPage(Number(pageButton.dataset.importPage))}catch(error){pageButton.disabled=false;toast(t('preview_page_failed'),error.message)}return}
  const resetButton=event.target.closest('#reset-import-edits');
  if(resetButton){state.importReview.decisions={};state.importReview.categoryOverrides={};state.importReview.notes={};renderImportPreview();toast(t('edits_reset'));return}
  const cancelButton=event.target.closest('#cancel-import-preview');
  if(!cancelButton||!state.importPreview)return;
  const batchId=state.importPreview.batch_id;busy(cancelButton,true);
  try{await api(`/imports/${batchId}/preview`,{method:'DELETE'})}catch(error){console.warn('Unable to remove rejected import preview from server',error)}finally{state.importPreview=null;state.importReview={page:1,pages:1,total:0,fileTotal:0,decisions:{},categoryOverrides:{},notes:{}};if(importPreviewBox.open)importPreviewBox.close();importPreviewBox.innerHTML='';file.value='';file.dispatchEvent(new Event('change'));toast(t('import_cancelled'))}
});
importPreviewBox.addEventListener('cancel',event=>{event.preventDefault();$('#cancel-import-preview',importPreviewBox)?.click()});
window.addEventListener('popstate',()=>navigate(location.hash.slice(1)||'dashboard'));applyDataMonth(state.month,true);navigate(location.hash.slice(1)||'dashboard');bootstrap();
