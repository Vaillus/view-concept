/* view-concept — the head of a section frame: written at the start of every HTML section
   the page, the published page or the vault note draws (frame.py). It tells the page
   around the frame the height of the section's content, so the frame takes that height.
   The page cannot read it: the frame has an origin of its own, so the height is posted. */
(function () {
  var root = document.documentElement;
  var last = -1;
  function post() {
    var height = Math.ceil(root.getBoundingClientRect().height);
    if (height === last) return;
    last = height;
    parent.postMessage({ viewConcept: "height", height: height }, "*");
  }
  if (window.ResizeObserver) new ResizeObserver(post).observe(root);
  addEventListener("load", post);
})();
