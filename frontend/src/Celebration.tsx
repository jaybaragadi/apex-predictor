import confetti from "canvas-confetti";
import { useEffect, useRef } from "react";

const GOLD = ["#E9C46A", "#D4A017", "#F6E7B0", "#B8860B", "#FFFFFF"];

/** 4-second fireworks + confetti burst, then a subtle drifting gold-spark field.
 * Fully disabled when the viewer prefers reduced motion or turns animations off. */
export function Celebration({ enabled, replayKey }: { enabled: boolean; replayKey: number }) {
  const burstRef = useRef<HTMLCanvasElement>(null);
  const ambientRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (!enabled || !burstRef.current) return;
    const fire = confetti.create(burstRef.current, { resize: true, useWorker: false });
    const end = Date.now() + 4000;
    fire({ particleCount: 140, spread: 100, startVelocity: 48, origin: { y: 0.55 }, colors: GOLD, scalar: 1.05 });
    const id = window.setInterval(() => {
      if (Date.now() > end) { window.clearInterval(id); return; }
      // fireworks: radial bursts at random points
      fire({ particleCount: 46, spread: 360, startVelocity: 26, ticks: 70, gravity: 0.7, decay: 0.92,
        origin: { x: 0.15 + Math.random() * 0.7, y: 0.15 + Math.random() * 0.35 }, colors: GOLD, shapes: ["circle"], scalar: 0.8 });
      fire({ particleCount: 6, angle: 60, spread: 55, origin: { x: 0, y: 0.8 }, colors: GOLD });
      fire({ particleCount: 6, angle: 120, spread: 55, origin: { x: 1, y: 0.8 }, colors: GOLD });
    }, 420);
    return () => { window.clearInterval(id); fire.reset(); };
  }, [enabled, replayKey]);

  useEffect(() => {
    const c = ambientRef.current;
    if (!enabled || !c) return;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    let raf = 0;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const resize = () => { c.width = c.clientWidth * dpr; c.height = c.clientHeight * dpr; };
    resize();
    window.addEventListener("resize", resize);
    const sparks = Array.from({ length: 38 }, () => ({ x: Math.random(), y: Math.random(), r: 0.6 + Math.random() * 1.6, v: 0.0004 + Math.random() * 0.0009, ph: Math.random() * 6.28 }));
    const tick = (t: number) => {
      ctx.clearRect(0, 0, c.width, c.height);
      for (const s of sparks) {
        s.y -= s.v; if (s.y < -0.02) { s.y = 1.02; s.x = Math.random(); }
        const a = 0.25 + 0.35 * Math.sin(t / 900 + s.ph);
        ctx.beginPath();
        ctx.fillStyle = `rgba(212,160,23,${Math.max(0, a)})`;
        ctx.arc(s.x * c.width, s.y * c.height, s.r * dpr, 0, Math.PI * 2);
        ctx.fill();
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => { cancelAnimationFrame(raf); window.removeEventListener("resize", resize); };
  }, [enabled]);

  return (
    <>
      <canvas ref={ambientRef} className="ambient-canvas" aria-hidden="true" hidden={!enabled} />
      <canvas ref={burstRef} className="burst-canvas" aria-hidden="true" hidden={!enabled} />
    </>
  );
}
