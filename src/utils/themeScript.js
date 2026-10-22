/** Inline script for layout.tsx — prevents theme flash before React hydrates. */
export const themeInitScript = `
(function () {
  var explicit = localStorage.getItem('themeExplicit') === '1';
  var pref = localStorage.getItem('themePreference');
  var dark;
  if (explicit && pref === 'dark') {
    dark = true;
  } else if (explicit && pref === 'light') {
    dark = false;
  } else {
    dark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  }
  document.documentElement.classList.toggle('dark', dark);
})();
`;
