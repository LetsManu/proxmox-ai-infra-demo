// Apply the saved theme before first paint (no flash). Light is the default.
try {
  if (localStorage.getItem('theme') === 'dark') document.documentElement.dataset.theme = 'dark'
} catch (e) {
  /* storage blocked: stay light */
}
