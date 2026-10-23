// docs-src/design/tokens/index.ts
var sizeInput = document.querySelector("#reading-size");
var sizeOutput = document.querySelector("#reading-value");
function syncReadingSize() {
  if (!sizeInput || !sizeOutput) return;
  const actual = parseFloat(getComputedStyle(document.documentElement).fontSize);
  sizeInput.value = actual.toFixed(1);
  sizeOutput.value = `${actual.toFixed(1)}px`;
}
syncReadingSize();
sizeInput?.addEventListener("input", () => {
  document.documentElement.style.fontSize = `${sizeInput.value}px`;
  if (sizeOutput) sizeOutput.value = `${sizeInput.value}px`;
});
document.querySelector("#reset-size")?.addEventListener("click", () => {
  document.documentElement.style.removeProperty("font-size");
  syncReadingSize();
});
window.addEventListener("resize", () => {
  if (!document.documentElement.style.fontSize) syncReadingSize();
});
document.querySelector("#copy-code")?.addEventListener("click", async (event) => {
  const button = event.currentTarget;
  const status = document.querySelector("#copy-status");
  const example = document.querySelector("#payload-code");
  if (!status || !example) return;
  try {
    await navigator.clipboard.writeText(example.textContent ?? "");
    button.textContent = "Copied";
    status.textContent = "Code copied to clipboard.";
  } catch {
    status.textContent = "Copy unavailable. Select the code to copy manually.";
  }
});
var liftSection = document.querySelector("#lift");
var liftRange = document.querySelector("#lift-level");
var liftBorders = document.querySelector("#lift-borders");
var liftOutput = document.querySelector("#lift-value");
var liftLive = document.querySelector("#lift-live-surface");
var liftShape = document.querySelector("#lift-shape");
var liftRecipe = document.querySelector("#lift-active-recipe");
var liftStatus = document.querySelector("#lift-status");
var liftFilters = new Map(
  [...document.querySelectorAll("[data-lift-level]")].map((element) => [
    element.dataset.liftLevel ?? "",
    element.dataset.liftFilter ?? "none"
  ])
);
function updateLift(notify) {
  if (!liftSection || !liftRange || !liftBorders || !liftOutput || !liftLive || !liftShape) return;
  const filter = liftFilters.get(liftRange.value);
  if (!filter) return;
  liftLive.style.filter = filter;
  liftShape.style.filter = filter;
  liftOutput.value = liftRange.value;
  liftSection.classList.toggle("lift-no-borders", !liftBorders.checked);
  if (liftRecipe) liftRecipe.textContent = `filter: ${filter};`;
  if (notify && liftStatus) {
    liftStatus.textContent = `Reviewing lift ${liftRange.value}${liftBorders.checked ? " with borders" : " without borders"}.`;
  }
}
liftRange?.addEventListener("input", () => updateLift(true));
liftBorders?.addEventListener("change", () => updateLift(true));
updateLift(false);
if ("IntersectionObserver" in window) {
  const observer = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      document.querySelectorAll("nav a").forEach((link) => {
        const current = link.getAttribute("href") === `#${entry.target.id}`;
        link.setAttribute("aria-current", String(current));
      });
    }
  }, { rootMargin: "-15% 0px -65% 0px" });
  document.querySelectorAll("main section").forEach((section) => observer.observe(section));
}
