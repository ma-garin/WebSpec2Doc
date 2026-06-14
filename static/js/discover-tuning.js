// discover-tuning.js
// Screen discovery tuning layer.
// This keeps the existing wizard implementation intact while preventing
// the previous hard-coded depth=5/max_pages=300 request from becoming the default path.

(function () {
  const DEFAULT_DISCOVER_DEPTH = '2';
  const DEFAULT_DISCOVER_MAX_PAGES = '30';
  const LARGE_DISCOVER_THRESHOLD = 100;

  function tunedDiscoverOptions() {
    return {
      depth: DEFAULT_DISCOVER_DEPTH,
      max_pages: DEFAULT_DISCOVER_MAX_PAGES,
    };
  }

  function tuneDiscoverBody(body) {
    if (!(body instanceof URLSearchParams)) return body;

    const tuned = new URLSearchParams(body);
    const requestedMaxPages = Number(tuned.get('max_pages') || DEFAULT_DISCOVER_MAX_PAGES);

    // Existing wizard.js used depth=5/max_pages=300 as a fixed default.
    // Treat that exact combination as an implicit default and downgrade it
    // to the practical standard profile: depth=2/max_pages=30.
    if (tuned.get('depth') === '5' && tuned.get('max_pages') === '300') {
      tuned.set('depth', DEFAULT_DISCOVER_DEPTH);
      tuned.set('max_pages', DEFAULT_DISCOVER_MAX_PAGES);
    }

    if (requestedMaxPages >= LARGE_DISCOVER_THRESHOLD) {
      console.warn('WebSpec2Doc: large discovery request may take time.', {
        max_pages: requestedMaxPages,
      });
    }

    return tuned;
  }

  const nativeFetch = window.fetch.bind(window);
  window.fetch = function tunedFetch(input, init) {
    const url = typeof input === 'string' ? input : input && input.url;
    if (url === '/api/discover-stream' || url === '/api/discover') {
      const nextInit = Object.assign({}, init || {});
      nextInit.body = tuneDiscoverBody(nextInit.body);
      return nativeFetch(input, nextInit);
    }
    return nativeFetch(input, init);
  };

  window.WebSpec2DocDiscoverTuning = {
    defaults: tunedDiscoverOptions,
    tuneDiscoverBody,
  };
})();
