/* Keep page gestures steady while leaving zoom inside the trip map available. */
(() => {
  const inMap = target => target instanceof Element && Boolean(target.closest('.leaflet-container'));
  const stopPageZoom = event => {
    if (!inMap(event.target)) event.preventDefault();
  };
  document.addEventListener('gesturestart', stopPageZoom, { passive: false });
  document.addEventListener('gesturechange', stopPageZoom, { passive: false });
  document.addEventListener('touchmove', event => {
    if (event.touches.length > 1) stopPageZoom(event);
  }, { passive: false });
})();
