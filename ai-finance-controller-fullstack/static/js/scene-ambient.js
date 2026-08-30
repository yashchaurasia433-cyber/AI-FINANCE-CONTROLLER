/**
 * Decorative particle field — used on Home / Register / Login / Forgot /
 * Reset pages where there's no real reconciliation data to visualize yet.
 * Unlike scene.js (the reconciliation gate), this never renders real data.
 */
function initAmbientScene(container, opts = {}) {
  const density = opts.density || 900;
  const colors = [0xd8a857, 0x4fae7d, 0x4fa8c9, 0x7c6ff0];

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(60, container.clientWidth / container.clientHeight, 0.1, 100);
  camera.position.z = 18;

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setSize(container.clientWidth, container.clientHeight);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  container.appendChild(renderer.domElement);

  const positions = new Float32Array(density * 3);
  const colorArr = new Float32Array(density * 3);
  const tmpColor = new THREE.Color();
  for (let i = 0; i < density; i++) {
    positions[i * 3] = (Math.random() - 0.5) * 40;
    positions[i * 3 + 1] = (Math.random() - 0.5) * 24;
    positions[i * 3 + 2] = (Math.random() - 0.5) * 30;
    tmpColor.set(colors[Math.floor(Math.random() * colors.length)]);
    colorArr[i * 3] = tmpColor.r;
    colorArr[i * 3 + 1] = tmpColor.g;
    colorArr[i * 3 + 2] = tmpColor.b;
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geo.setAttribute('color', new THREE.BufferAttribute(colorArr, 3));
  const mat = new THREE.PointsMaterial({ size: 0.12, vertexColors: true, transparent: true, opacity: 0.85 });
  const points = new THREE.Points(geo, mat);
  scene.add(points);

  const orbs = [];
  for (let i = 0; i < 4; i++) {
    const g = new THREE.IcosahedronGeometry(0.5 + Math.random() * 0.4, 1);
    const m = new THREE.MeshBasicMaterial({ color: colors[i % colors.length], transparent: true, opacity: 0.5 });
    const mesh = new THREE.Mesh(g, m);
    mesh.position.set((Math.random() - 0.5) * 20, (Math.random() - 0.5) * 12, (Math.random() - 0.5) * 10);
    scene.add(mesh);
    orbs.push({ mesh, speed: 0.05 + Math.random() * 0.08, offset: Math.random() * 10 });
  }

  let mouseX = 0, mouseY = 0;
  function onMouseMove(e) {
    const rect = container.getBoundingClientRect();
    mouseX = ((e.clientX - rect.left) / rect.width - 0.5) * 2;
    mouseY = ((e.clientY - rect.top) / rect.height - 0.5) * 2;
  }
  container.addEventListener('mousemove', onMouseMove);

  const clock = new THREE.Clock();
  let raf;
  function animate() {
    raf = requestAnimationFrame(animate);
    const t = clock.getElapsedTime();
    points.rotation.y = t * 0.02;
    points.rotation.x = t * 0.008;
    orbs.forEach((o) => {
      o.mesh.position.y += Math.sin(t * o.speed + o.offset) * 0.003;
      o.mesh.rotation.y = t * 0.15;
    });
    camera.position.x += (mouseX * 2 - camera.position.x) * 0.02;
    camera.position.y += (-mouseY * 1 - camera.position.y) * 0.02;
    camera.lookAt(0, 0, 0);
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
    if (container.contains(renderer.domElement)) container.removeChild(renderer.domElement);
  };
}
