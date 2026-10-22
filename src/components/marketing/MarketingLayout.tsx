// @ts-nocheck
import { useState, useEffect } from 'react';
import Navbar from '../Navbar';
import Footer from '../Footer';
import { useLocaleRouting } from '../../context/LocaleRoutingContext';
import { getMessages } from '../../utils/i18n.js';

const MarketingLayout = ({ children, mainClassName = '' }) => {
  const routing = useLocaleRouting();
  const m = getMessages(routing.locale);
  const homePath = routing.localePrefix || '/';
  const [isScrolled, setIsScrolled] = useState(false);

  useEffect(() => {
    const handleScroll = () => {
      setIsScrolled(window.scrollY > 10);
    };
    handleScroll();
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-revealed');
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: '0px 0px -8% 0px' },
    );
    const observeRevealElements = (root = document) => {
      if (root.matches?.('[data-reveal]')) observer.observe(root);
      root.querySelectorAll?.('[data-reveal]').forEach((element) => observer.observe(element));
    };
    observeRevealElements();
    const mutationObserver = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => mutation.addedNodes.forEach((node) => {
        if (node.nodeType === Node.ELEMENT_NODE) observeRevealElements(node);
      }));
    });
    mutationObserver.observe(document.body, { childList: true, subtree: true });

    const handlePointerMove = (event) => {
      const target = event.target.closest?.('[data-spotlight]');
      if (!target) return;
      const rect = target.getBoundingClientRect();
      target.style.setProperty('--mouse-x', `${event.clientX - rect.left}px`);
      target.style.setProperty('--mouse-y', `${event.clientY - rect.top}px`);
    };
    document.addEventListener('pointermove', handlePointerMove, { passive: true });

    return () => {
      observer.disconnect();
      mutationObserver.disconnect();
      document.removeEventListener('pointermove', handlePointerMove);
    };
  }, [routing.locale]);

  return (
    <div className="marketing-page selection:bg-amber-200/50">
      <Navbar isScrolled={isScrolled} homePath={homePath} routing={routing} m={m} marketing />
      <main className={`relative ${mainClassName}`}>{children}</main>
      <Footer routing={routing} m={m} marketing />
    </div>
  );
};

export default MarketingLayout;
