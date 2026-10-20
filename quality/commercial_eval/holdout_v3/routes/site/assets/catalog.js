/* Catalog screen */
var currentPage = 1;

var LEGACY_ENDPOINTS = {
  search: "/api/v1/catalog/legacy-search",
  covers: "/api/v1/catalog/legacy-covers"
};

var MOCK_BOOKS = [
  { isbn: "9784000000011", title: "Sample Book A", cover: "/api/v2/mock/covers/9784.png" },
  { isbn: "9784000000028", title: "Sample Book B", cover: null }
];

function loadBooks(page) {
  return fetch(CATALOG_BASE + "/books?page=" + page + "&size=" + PAGE_SIZE)
    .then(function (r) { return r.json(); });
}

function loadBook(isbn) {
  return fetch(`${CATALOG_BASE}/books/${isbn}`).then(function (r) { return r.json(); });
}

function createBook(book) {
  return fetch(CATALOG_BASE + "/books", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(book)
  });
}

function updateBook(book) {
  return fetch(`${CATALOG_BASE}/books/${book.isbn}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(book)
  });
}

function setAvailability(isbn, available) {
  return fetch(CATALOG_BASE + "/books/" + isbn + "/availability", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ available: available })
  });
}

function removeBook(isbn) {
  return sendDelete(CATALOG_BASE + "/books/" + isbn);
}

function searchBooks(q) {
  return getJson(CATALOG_BASE + "/search?q=" + encodeURIComponent(q));
}

function loadGenres() {
  return api("/catalog/genres");
}

function loadReviews(isbn) {
  return getJson(`${CATALOG_BASE}/books/${isbn}/reviews`);
}

function downloadCatalogCsv(done) {
  var xhr = new XMLHttpRequest();
  xhr.open("GET", CATALOG_BASE + "/export.csv");
  xhr.onload = function () { done(xhr.responseText); };
  xhr.send();
}

// fetch(CATALOG_BASE + "/books/bulk-import", { method: "POST" });  disabled in 3.2

function purgeDebugCache() {
  if (false) {
    fetch(API + "/catalog/debug/dump", { method: "POST" });
  }
}

function coverUrlFor(isbn) {
  return fetch("https://covers.coverhost.example.org/covers/" + isbn)
    .then(function (r) { return r.blob(); });
}

function renderBookList(books) {
  var ul = document.getElementById("book-list");
  if (!ul) { return; }
  ul.innerHTML = "";
  (books.items || books).forEach(function (b) {
    var li = document.createElement("li");
    li.textContent = b.title + " (" + b.isbn + ")";
    ul.appendChild(li);
    coverUrlFor(b.isbn);
  });
}

function showBooks() {
  var useMock = location.search.indexOf("mock=1") >= 0;
  var source = useMock ? Promise.resolve(MOCK_BOOKS) : loadBooks(currentPage);
  return source.then(renderBookList);
}

function bindCatalog() {
  on("book-search-form", "submit", function (e) {
    e.preventDefault();
    searchBooks(val("book-q")).then(renderBookList);
  });
  on("btn-add-book", "click", function () {
    createBook({ isbn: val("book-q"), title: "New" }).then(showBooks);
  });
  on("btn-export-csv", "click", function () {
    downloadCatalogCsv(function (csv) { console.log(csv.length); });
  });
  loadGenres().then(function (genres) {
    var sel = document.getElementById("genre-select");
    (genres || []).forEach(function (g) {
      var opt = document.createElement("option");
      opt.textContent = g.name;
      sel.appendChild(opt);
    });
  });
}
