/* WebSpec2Doc — 共通スクリプト */

document.addEventListener("DOMContentLoaded", () => {
  initActiveNav();
  initSmoothScroll();
  setCurrentDate();
});

function initActiveNav() {
  const navLinks = document.querySelectorAll(".vs-sidebar__nav a");
  const sections = document.querySelectorAll("[data-section]");

  if (!sections.length || !navLinks.length) return;

  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          const id = entry.target.getAttribute("data-section");
          navLinks.forEach((link) => {
            const isActive = link.getAttribute("href") === `#${id}`;
            link.classList.toggle("active", isActive);
          });
        }
      });
    },
    { rootMargin: "-20% 0px -70% 0px" }
  );

  sections.forEach((section) => observer.observe(section));
}

function initSmoothScroll() {
  document.querySelectorAll('a[href^="#"]').forEach((anchor) => {
    anchor.addEventListener("click", (e) => {
      const target = document.querySelector(anchor.getAttribute("href"));
      if (!target) return;
      e.preventDefault();
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });
}

function setCurrentDate() {
  const el = document.getElementById("current-date");
  if (!el) return;
  const now = new Date();
  el.textContent = `${now.getFullYear()}年${now.getMonth() + 1}月${now.getDate()}日`;
}

function printDoc() {
  window.print();
}
