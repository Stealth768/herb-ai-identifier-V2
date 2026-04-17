// core/static/core/js/dashboard.js
function showKnowledgeBase() {
    const searchInput = document.querySelector('input[name="q"]');
    if (searchInput) {
        searchInput.focus();
        searchInput.placeholder = "Searching Knowledge Base...";
        // Visual cue: add a glow
        searchInput.classList.add('border-success');
        setTimeout(() => searchInput.classList.remove('border-success'), 2000);
    }
}