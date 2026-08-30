/**
 * Forecast rendered as a real 3D bar chart, not a flat canvas line chart.
 * Gold bars = actual matched settlement volume. Cyan translucent bars =
 * the linear-trend projection. A raycast-driven hover tooltip makes exact
 * values readable per bar — a 3D chart is only an upgrade if you can
 * still get the numbers out of it, so this isn't decoration-only.
 */
function initForecastScene(container, history, forecast) {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0a0d12);
  scene.fog = new THREE.FogExp2(0x0a0d12, 0.012);

  const camera = new THREE.PerspectiveCamera(45, container.clientWidth / container.clientHeight, 0.1, 300);
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setSize(container.clientWidth, container.clientHeight);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  container.appendChild(renderer.domElement);

  scene.add(new THREE.AmbientLight(0x8899aa, 0.65));
  const key = new THREE.PointLight(0xd8a857, 1.8, 80);
  key.position.set(10, 14, 14);
  scene.add(key);
  const rim = new THREE.PointLight(0x4fa8c9, 1.2, 80);
  rim.position.set(-16, 8, -10);
  scene.add(rim);

  const allPoints = [...history.map((p) => ({ ...p, kind: 'actual' })), ...forecast.map((p) => ({ ...p, kind: 'forecast' }))];
  const n = allPoints.length;
  const BAR_SPACING = 1.1;
  const MAX_HEIGHT = 6.5;
  const totalWidth = (n - 1) * BAR_SPACING;
  const maxAmount = Math.max(1, ...allPoints.map((p) => p.amount));

  const grid = new THREE.GridHelper(Math.max(30, totalWidth + 10), 30, 0x27313d, 0x161d26);
  grid.position.y = 0;
  scene.add(grid);

  // "Today" divider between actual and forecast, if there's a forecast section
  if (history.length && forecast.length) {
    const dividerX = -totalWidth / 2 + (history.length - 0.5) * BAR_SPACING;
    const divGeo = new THREE.PlaneGeometry(0.02, MAX_HEIGHT + 1);
    const divMat = new THREE.MeshBasicMaterial({ color: 0xe7ecf2, transparent: true, opacity: 0.25, side: THREE.DoubleSide });
    const divider = new THREE.Mesh(divGeo, divMat);
    divider.position.set(dividerX, (MAX_HEIGHT + 1) / 2, 0);
    scene.add(divider);
  }

  const bars = [];
  const barGeo = new THREE.BoxGeometry(0.55, 1, 0.55);
  allPoints.forEach((p, i) => {
    const x = -totalWidth / 2 + i * BAR_SPACING;
    const targetHeight = Math.max(0.05, (p.amount / maxAmount) * MAX_HEIGHT);
    const isForecast = p.kind === 'forecast';
    const color = isForecast ? 0x4fa8c9 : 0xd8a857;

    const mat = new THREE.MeshStandardMaterial({
      color, emissive: color, emissiveIntensity: isForecast ? 0.35 : 0.5,
      roughness: 0.4, metalness: 0.3, transparent: isForecast, opacity: isForecast ? 0.62 : 1.0,
    });
    const mesh = new THREE.Mesh(barGeo, mat);
    mesh.position.set(x, 0, 0);
    mesh.scale.y = 0.001; // grown in on load
    mesh.userData = { point: p, targetHeight, x };
    scene.add(mesh);
    bars.push(mesh);
  });

  // Camera framed to fit the full bar range regardless of how many points there are
  const camDist = Math.max(14, totalWidth * 0.85);
  camera.position.set(0, MAX_HEIGHT * 1.15, camDist);
  camera.lookAt(0, MAX_HEIGHT * 0.25, 0);

  // ===== Hover tooltip via raycasting =====
  const tooltip = document.createElement('div');
  tooltip.style.cssText = `
    position: absolute; pointer-events: none; display: none; z-index: 5;
    background: rgba(16,21,28,0.95); border: 1px solid #232B36; border-radius: 8px;
    padding: 8px 12px; font-family: 'IBM Plex Mono', monospace; font-size: 12px;
    color: #E7ECF2; white-space: nowrap; transform: translate(-50%, -115%);
  `;
  container.style.position = container.style.position || 'relative';
  container.appendChild(tooltip);

  const raycaster = new THREE.Raycaster();
  const mouseNdc = new THREE.Vector2();
  let hovered = null;

  function fmtInr(v) { return '₹' + Number(v).toLocaleString('en-IN', { maximumFractionDigits: 0 }); }

  function onMouseMove(e) {
    const rect = container.getBoundingClientRect();
    mouseNdc.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
    mouseNdc.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
    raycaster.setFromCamera(mouseNdc, camera);
    const hits = raycaster.intersectObjects(bars);

    if (hits.length) {
      const mesh = hits[0].object;
      hovered = mesh;
      const p = mesh.userData.point;
      tooltip.style.display = 'block';
      tooltip.style.left = `${e.clientX - rect.left}px`;
      tooltip.style.top = `${e.clientY - rect.top}px`;
      tooltip.innerHTML = `<strong style="color:${p.kind === 'forecast' ? '#4FA8C9' : '#D8A857'}">${p.kind === 'forecast' ? 'Forecast' : 'Actual'}</strong><br>${p.date}<br>${fmtInr(p.amount)}`;
    } else {
      hovered = null;
      tooltip.style.display = 'none';
    }
  }
  container.addEventListener('mousemove', onMouseMove);
  container.addEventListener('mouseleave', () => { tooltip.style.display = 'none'; hovered = null; });

  const clock = new THREE.Clock();
  let raf;
  function animate() {
    raf = requestAnimationFrame(animate);
    const t = clock.getElapsedTime();

    bars.forEach((mesh, i) => {
      const target = mesh.userData.targetHeight;
      // staggered grow-in
      const growDelay = i * 0.02;
      const growProgress = Math.min(1, Math.max(0, (t - growDelay) / 0.6));
      const eased = 1 - Math.pow(1 - growProgress, 3);
      const h = Math.max(0.001, target * eased);
      mesh.scale.y = h;
      mesh.position.y = h / 2;

      const isHovered = mesh === hovered;
      const baseEmissive = mesh.userData.point.kind === 'forecast' ? 0.35 : 0.5;
      mesh.material.emissiveIntensity = isHovered ? baseEmissive + 0.5 : baseEmissive;
    });

    camera.position.x = Math.sin(t * 0.05) * Math.min(4, totalWidth * 0.06);
    camera.lookAt(0, MAX_HEIGHT * 0.25, 0);

    renderer.render(scene, camera);
  }
  animate();

  function onResize() {
    const w = container.clientWidth, h = container.clientHeight;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h);
  }
  window.addEventListener('resize', onResize);

  return function dispose() {
    cancelAnimationFrame(raf);
    window.removeEventListener('resize', onResize);
    container.removeEventListener('mousemove', onMouseMove);
    renderer.dispose();
    if (container.contains(tooltip)) container.removeChild(tooltip);
    if (container.contains(renderer.domElement)) container.removeChild(renderer.domElement);
  };
}
