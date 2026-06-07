document.addEventListener("DOMContentLoaded", () => {
  if (window.lucide) {
    window.lucide.createIcons({ strokeWidth: 1.8 });
  }

  if (document.body.dataset.autorefresh === "true") {
    window.setTimeout(() => window.location.reload(), 4000);
  }

  const typeSelect = document.querySelector("select[name='target_type']");
  const searchField = document.querySelector("[data-search-subreddit]");
  const updateSearchField = () => {
    if (!typeSelect || !searchField) return;
    searchField.classList.toggle("is-hidden", typeSelect.value !== "search");
  };

  updateSearchField();
  if (typeSelect) {
    typeSelect.addEventListener("change", updateSearchField);
  }
});
