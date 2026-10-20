/* Progressive navigation for the instructor workspace. Normal URLs still work. */
(() => {
  const main = document.getElementById('main-content');
  const sidebar = document.getElementById('workspace-sidebar');
  if (!main || !sidebar) return;
  let controller;
  let dirty = false;
  let submitting = false;
  let currentUrl = location.href;

  function workspaceUrl(value) {
    const url = new URL(value, location.href);
    return url.origin === location.origin && url.pathname.startsWith('/instructor/') &&
      !url.pathname.includes('/export/') ? url : null;
  }

  function canLeave() {
    return !dirty || window.confirm('Leave this section and discard unsaved changes?');
  }

  async function navigate(url, { method = 'GET', body, historyMode = 'push' } = {}) {
    controller?.abort();
    controller = new AbortController();
    const activeController = controller;
    submitting = method !== 'GET';
    main.setAttribute('aria-busy', 'true');
    document.body.classList.add('workspace-loading');
    try {
      const response = await fetch(url, {
        method, body, signal: activeController.signal,
        credentials: 'same-origin', headers: { 'X-Requested-With': 'Workspace' },
      });
      if (!response.ok) throw new Error(`Request failed (${response.status})`);
      const page = new DOMParser().parseFromString(await response.text(), 'text/html');
      if (activeController.signal.aborted) return;
      const nextMain = page.getElementById('main-content');
      const nextSidebar = page.getElementById('workspace-sidebar');
      if (!nextMain || !nextSidebar || !workspaceUrl(response.url)) {
        dirty = false;
        location.assign(response.url);
        return;
      }
      main.replaceChildren(...nextMain.childNodes);
      sidebar.replaceChildren(...nextSidebar.childNodes);
      document.title = page.title;
      dirty = false;
      // Each page owns its form scripts. Isolate declarations on repeat visits,
      // and execute in place so document.currentScript keeps its proper parent.
      for (const oldScript of main.querySelectorAll('script')) {
        if (oldScript.type && oldScript.type !== 'text/javascript') continue;
        const script = document.createElement('script');
        if (oldScript.src) script.src = oldScript.src;
        else script.textContent = `(() => {\n${oldScript.textContent}\n})();`;
        oldScript.replaceWith(script);
      }
      if (historyMode === 'push' && response.url !== currentUrl) history.pushState({}, '', response.url);
      else if (historyMode === 'pop' && response.url !== location.href) history.replaceState({}, '', response.url);
      currentUrl = location.href;
      if (window.matchMedia('(max-width: 720px)').matches) {
        sidebar.querySelector('[aria-current="page"]')?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
      }
      main.focus({ preventScroll: true });
      window.scrollTo({ top: 0, behavior: 'instant' });
    } catch (error) {
      if (error.name === 'AbortError') return;
      const notice = document.createElement('div');
      notice.className = 'message error';
      notice.setAttribute('role', 'alert');
      notice.textContent = method === 'GET'
        ? 'This section could not be loaded. Check your connection and try again.'
        : 'The server response could not be confirmed. Reload this page to check whether your changes were saved before trying again.';
      main.prepend(notice);
      if (historyMode === 'pop') history.replaceState({}, '', currentUrl);
    } finally {
      if (controller === activeController) {
        submitting = false;
        main.removeAttribute('aria-busy');
        document.body.classList.remove('workspace-loading');
      }
    }
  }

  document.addEventListener('click', event => {
    const link = event.target.closest('a[href]');
    if (!link || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey ||
        event.shiftKey || event.altKey || link.target || link.hasAttribute('download')) return;
    const url = workspaceUrl(link.href);
    if (!url || url.hash) return;
    event.preventDefault();
    if (!submitting && canLeave()) navigate(url);
  });

  document.addEventListener('submit', event => {
    const form = event.target;
    if (event.defaultPrevented || !main.contains(form) || form.target) return;
    const url = workspaceUrl(form.action);
    if (!url) return;
    event.preventDefault();
    if (submitting) return;
    const data = new FormData(form);
    if (event.submitter?.name) data.append(event.submitter.name, event.submitter.value);
    if (form.method.toUpperCase() === 'GET') {
      url.search = new URLSearchParams(data).toString();
      if (canLeave()) navigate(url);
    } else navigate(url, { method: 'POST', body: data });
  });

  main.addEventListener('input', event => {
    if (event.target.closest('form')?.method.toUpperCase() === 'POST') dirty = true;
  });
  main.addEventListener('change', event => {
    if (event.target.closest('form')?.method.toUpperCase() === 'POST') dirty = true;
  });
  window.addEventListener('popstate', () => {
    if (submitting || !canLeave()) {
      history.pushState({}, '', currentUrl);
      return;
    }
    navigate(location.href, { historyMode: 'pop' });
  });
  window.addEventListener('beforeunload', event => {
    if (dirty && !submitting) { event.preventDefault(); event.returnValue = ''; }
  });
})();
