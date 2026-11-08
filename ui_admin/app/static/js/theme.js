// Apply the saved theme before the stylesheet is painted.
(function () {
  let theme = "auto";
  try {
    const stored = localStorage.getItem("sse-theme");
    if (["auto", "light", "dark"].includes(stored)) theme = stored;
  } catch (error) {
    // Keep the system theme when browser storage is unavailable.
  }
  document.documentElement.dataset.theme = theme;
})();
