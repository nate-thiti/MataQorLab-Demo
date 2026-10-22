// @ts-nocheck
import { Activity, BarChart3, Lock, Server, ShieldCheck } from '@/components/icons';

const TrustBar = ({ title, items = [] }) => {
  if (!items.length) return null;

  return (
    <section className="marketing-trust-bar px-6">
      <div className="trust-control-strip max-w-6xl mx-auto" data-reveal>
        <div className="trust-control-header">
          <div className="trust-control-kicker">
            <Activity className="w-3.5 h-3.5" strokeWidth={1.5} />
            <span>TRUST &amp; CONTROL</span>
            <i />
          </div>
          {title && <p>{title}</p>}
        </div>

        <div className="trust-control-modules">
          <div className="trust-control-signal" aria-hidden="true"><span /></div>
          {items.map((item, i) => (
            <div
              key={i}
              className="trust-control-module"
              data-spotlight
              style={{ '--trust-delay': `${i * 0.35}s` }}
            >
              <div className="trust-module-top">
                <span className="trust-module-index">0{i + 1}</span>
                <span className="trust-module-status"><i />ACTIVE</span>
              </div>
              <div className="trust-module-main">
                <div className="trust-module-icon">
                  {item.icon === 'shield' && <ShieldCheck strokeWidth={1.5} />}
                  {item.icon === 'lock' && <Lock strokeWidth={1.5} />}
                  {item.icon === 'server' && <Server strokeWidth={1.5} />}
                  {item.icon === 'chart' && <BarChart3 strokeWidth={1.5} />}
                </div>
                <span>{item.label}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default TrustBar;
