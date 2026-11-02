// recruit shared — fixed apply bar: keep the footer clear of the bar
// (same behaviour as index #sticky-apply: measure the bar height and
// pad the body by it).
(function () {
  function fit() {
    var b = document.querySelector('.sbar');
    if (b) document.body.style.paddingBottom = (b.offsetHeight + 8) + 'px';
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', fit);
  } else {
    fit();
  }
  window.addEventListener('resize', fit);
})();
