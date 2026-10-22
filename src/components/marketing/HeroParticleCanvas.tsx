// @ts-nocheck
import { useEffect, useRef } from 'react';
import { useTheme } from '../../context/ThemeContext';
import Image from 'next/image';
import MQLogo from '../../assets/MQ.svg';

const PALETTE = {
  light: {
    bg: 'linear-gradient(145deg, #fffdf8 0%, #f7f1e8 52%, #edf3f6 100%)',
    gridLine: 'rgba(120, 83, 39, 0.12)',
  },
  dark: {
    bg: 'linear-gradient(145deg, #17171d 0%, #1d1b1c 52%, #171b20 100%)',
    gridLine: 'rgba(255, 196, 105, 0.09)',
  },
};

const gridStyle = (line) => ({
  backgroundImage: [
    `linear-gradient(${line} 1px, transparent 1px)`,
    `linear-gradient(90deg, ${line} 1px, transparent 1px)`,
  ].join(', '),
  backgroundSize: '40px 40px',
});

const DataBars = () => (
  <div className="hero-3d-bars">
    {[34, 54, 43, 76, 62, 91, 72].map((height, index) => (
      <span key={index} style={{ '--bar-height': `${height}%`, '--bar-delay': `${index * 0.12}s` }} />
    ))}
  </div>
);

const HeroParticleCanvas = () => {
  const { theme } = useTheme();
  const fieldRef = useRef(null);
  const mode = theme === 'dark' ? 'dark' : 'light';
  const colors = PALETTE[mode];

  useEffect(() => {
    let frame = null;
    const updatePointer = (event) => {
      if (frame) return;
      frame = requestAnimationFrame(() => {
        frame = null;
        if (!fieldRef.current) return;
        const x = (event.clientX / window.innerWidth - 0.5) * 2;
        const y = (event.clientY / window.innerHeight - 0.5) * 2;
        fieldRef.current.style.setProperty('--hero-shift-x', `${x * 14}px`);
        fieldRef.current.style.setProperty('--hero-shift-y', `${y * 10}px`);
        fieldRef.current.style.setProperty('--hero-tilt-x', `${y * -3.5}deg`);
        fieldRef.current.style.setProperty('--hero-tilt-y', `${x * 5}deg`);
        fieldRef.current.style.setProperty('--hero-light-x', `${50 + x * 18}%`);
        fieldRef.current.style.setProperty('--hero-light-y', `${44 + y * 15}%`);
      });
    };
    window.addEventListener('pointermove', updatePointer, { passive: true });
    return () => {
      if (frame) cancelAnimationFrame(frame);
      window.removeEventListener('pointermove', updatePointer);
    };
  }, []);

  return (
    <div ref={fieldRef} className="hero-particle-field" style={{ background: colors.bg }} aria-hidden="true">
      <div className="hero-ambient hero-ambient-one" />
      <div className="hero-ambient hero-ambient-two" />
      <div className="hero-particle-grid" style={gridStyle(colors.gridLine)} />
      <div className="hero-energy-beam hero-energy-beam-one" />
      <div className="hero-energy-beam hero-energy-beam-two" />
      <div className="hero-data-particles">
        {Array.from({ length: 16 }).map((_, index) => <i key={index} />)}
      </div>

      <div className="hero-3d-stage">
        <div className="hero-stage-flare" />
        <div className="hero-energy-ring hero-energy-ring-one" />
        <div className="hero-energy-ring hero-energy-ring-two" />
        <div className="hero-3d-orbit hero-3d-orbit-outer" />
        <div className="hero-3d-orbit hero-3d-orbit-inner" />

        <div className="hero-3d-card hero-3d-card-query">
          <div className="hero-3d-card-top"><i /> LIVE QUERY</div>
          <div className="hero-query-line hero-query-line-long" />
          <div className="hero-query-line" />
          <div className="hero-query-line hero-query-line-accent" />
        </div>

        <div className="hero-3d-card hero-3d-card-insight">
          <div className="hero-3d-card-top"><i /> VERIFIED</div>
          <DataBars />
          <div className="hero-insight-value">+28.4%</div>
        </div>

        <div className="hero-3d-stack">
          <div className="hero-stack-layer hero-stack-layer-3"><span>INSIGHT</span></div>
          <div className="hero-stack-layer hero-stack-layer-2"><span>LOGIC</span></div>
          <div className="hero-stack-layer hero-stack-layer-1"><span>DATA</span></div>
          <div className="hero-3d-core">
            <div className="hero-core-face hero-core-front">
              <Image src={MQLogo} alt="" width={76} height={76} priority />
            </div>
            <div className="hero-core-face hero-core-side" />
            <div className="hero-core-face hero-core-top" />
          </div>
        </div>

        <div className="hero-3d-node hero-node-1" />
        <div className="hero-3d-node hero-node-2" />
        <div className="hero-3d-node hero-node-3" />
        <div className="hero-3d-status"><i /> 16-STAGE LIFECYCLE</div>
        <div className="hero-stage-shadow" />
      </div>
    </div>
  );
};

export default HeroParticleCanvas;
