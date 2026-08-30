/**
 * Reconciliation as a literal sorting gate: every transaction is a
 * particle that leaves its source node and either passes through the
 * gate (matched) or diverts to a holding cluster (exception) — rendered
 * directly from the matcher's real output.
 */
function initFlowScene(container, results) {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0a0d12);
  scene.fog = new THREE.FogExp2(0x0a0d12, 0.018);

  const camera = new THREE.PerspectiveCamera(50, container.clientWidth / container.clientHeight, 0.1, 200);
  camera.position.set(0, 7, 20);

  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setSize(container.clientWidth, container.clientHeight);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  container.appendChild(renderer.domElement);

  scene.add(new THREE.AmbientLight(0x8899aa, 0.6));
  const key = new THREE.PointLight(0xd8a857, 2.2, 60);
  key.position.set(0, 10, 10);
  scene.add(key);
  const rim = new THREE.PointLight(0x4fa8c9, 1.4, 60);
  rim.position.set(-14, 4, -6);
  scene.add(rim);

  const grid = new THREE.GridHelper(60, 40, 0x27313d, 0x161d26);
  grid.position.y = -3.2;
  scene.add(grid);

  function makeNode(color, x, y, z, size = 0.9) {
    const geo = new THREE.IcosahedronGeometry(size, 1);
    const mat = new THREE.MeshStandardMaterial({ color, emissive: color, emissiveIntensity: 0.55, roughness: 0.35, metalness: 0.4 });
    const mesh = new THREE.Mesh(geo, mat);
    mesh.position.set(x, y, z);
    scene.add(mesh);
    return mesh;
  }
  const bankNode = makeNode(0x4fa8c9, -13, 0, 0, 1.1);
  const gatewayNode = makeNode(0xd8a857, 13, 0, 0, 1.1);
  const exceptionNode = makeNode(0xe2665a, 0, 6.5, -5, 0.8);

  const gateGeo = new THREE.TorusGeometry(2.4, 0.06, 16, 64);
  const gateMat = new THREE.MeshStandardMaterial({ color: 0xe7ecf2, emissive: 0xe7ecf2, emissiveIntensity: 0.3, roughness: 0.2, metalness: 0.6 });
  const gate = new THREE.Mesh(gateGeo, gateMat);
  scene.add(gate);

  const MAX_PARTICLES = 140;
  const sample = results.length > MAX_PARTICLES
    ? results.filter((_, i) => i % Math.ceil(results.length / MAX_PARTICLES) === 0)
    : results;

  const particles = [];
  const particleGeo = new THREE.SphereGeometry(0.14, 10, 10);

  function colorFor(r) {
    if (r.match_type === 'exact') return 0xd8a857;
    if (r.match_type === 'fuzzy') return 0x4fae7d;
    return 0xe2665a;
  }

  for (const r of sample) {
    const fromBank = r.match_type !== 'unmatched_gateway';
    const start = fromBank ? bankNode.position : gatewayNode.position;
    const isException = r.match_type.startsWith('unmatched');
    const end = isException ? exceptionNode.position : (fromBank ? gatewayNode.position : bankNode.position);

    const mid = new THREE.Vector3(0, (Math.random() - 0.5) * 1.2, (Math.random() - 0.5) * 1.2);
    const curve = new THREE.QuadraticBezierCurve3(start.clone(), mid, end.clone());

    const c = colorFor(r);
    const mat = new THREE.MeshStandardMaterial({ color: c, emissive: c, emissiveIntensity: 0.8, roughness: 0.4 });
    const mesh = new THREE.Mesh(particleGeo, mat);
    scene.add(mesh);

    particles.push({ mesh, curve, duration: 3.2 + Math.random() * 1.6, offset: Math.random() * 6 });
  }

  const clock = new THREE.Clock();
  let raf;
  function animate() {
    raf = requestAnimationFrame(animate);
    const t = clock.getElapsedTime();
    gate.rotation.z = t * 0.15;
    bankNode.rotation.y = t * 0.3;
    gatewayNode.rotation.y = -t * 0.3;
    exceptionNode.rotation.y = t * 0.4;

    for (const p of particles) {
      const local = ((t + p.offset) % p.duration) / p.duration;
      p.mesh.position.copy(p.curve.getPoint(local));
      p.mesh.scale.setScalar(0.6 + 0.5 * Math.sin(local * Math.PI));
    }

    camera.position.x = Math.sin(t * 0.06) * 3;
    camera.lookAt(0, 1, 0);
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
    renderer.dispose();
    if (container.contains(renderer.domElement)) container.removeChild(renderer.domElement);
  };
}
