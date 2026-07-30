(() => {
  const nav = document.getElementById('navigation');
  if (!nav || nav.children.length || !window.NERA) return;

  nav.innerHTML = NERA.nav
    .map(([id, label]) => `<button type="button" data-page="${id}">${label}</button>`)
    .join('');

  nav.querySelectorAll('button').forEach((button) => {
    button.addEventListener('click', () => show(button.dataset.page));
  });

  const activePage = document.querySelector('.page.active')?.id || 'dashboard';
  const activeButton = nav.querySelector(`[data-page="${activePage}"]`);
  if (activeButton) activeButton.classList.add('active');
})();
