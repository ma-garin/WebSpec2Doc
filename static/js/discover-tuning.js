// discover-tuning.js
// Lightweight override for the screen discovery step.
// Keeps the existing wizard UI, but avoids the previous hard-coded depth=5/max_pages=300 request.

(function () {
  const DEFAULT_DISCOVER_DEPTH = '2';
  const DEFAULT_DISCOVER_MAX_PAGES = '30';

  function tunedDiscoverOptions() {
    return {
      depth: DEFAULT_DISCOVER_DEPTH,
      max_pages: DEFAULT_DISCOVER_MAX_PAGES,
    };
  }

  window.WebSpec2DocDiscoverTuning = {
    defaults: tunedDiscoverOptions,
  };
})();
