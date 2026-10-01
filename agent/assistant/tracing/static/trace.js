// Framework attributes are hidden by default: a span carrying every OTel key is
// no more readable than the JSON this page exists to replace.
document.addEventListener('click', (event) => {
  const button = event.target.closest('[data-toggle-noise]');
  if (!button) return;

  const hidden = document.querySelectorAll('.noise[hidden]').length > 0;
  for (const node of document.querySelectorAll('.noise')) {
    node.hidden = !hidden;
  }
  button.textContent = hidden ? 'Hide framework attributes' : 'Show all';
});
