// @ts-nocheck
import { useState } from 'react';
import { ChevronDown, Search, X } from '@/components/icons';
import { t } from '../utils/i18n.js';
import faqs from '../content/faqs.json';

const FaqSection = ({ m, isEn }) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [openFaq, setOpenFaq] = useState<any>(null);

  const toggleFaq = (id) => {
    setOpenFaq(openFaq === id ? null : id);
  };

  const translatedFaqs = faqs.map(faq => ({
    ...faq,
    displayQuestion: t(m, `landing.faq.q.${faq.id}`, faq.question),
    displayAnswer: t(m, `landing.faq.a.${faq.id}`, faq.answer)
  }));

  const filteredFaqs = translatedFaqs.filter(faq =>
    faq.displayQuestion.toLowerCase().includes(searchTerm.toLowerCase()) ||
    faq.displayAnswer.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const groupedFaqs = filteredFaqs.reduce((acc, faq) => {
    const category = faq.category || t(m, 'landing.faq_cat_general', isEn ? 'General' : 'ทั่วไป');
    if (!acc[category]) acc[category] = [];
    acc[category].push(faq);
    return acc;
  }, {});

  return (
    <section className="py-20 w-full px-6 marketing-section-divider">
      <div className="max-w-3xl mx-auto">
        <div className="text-center mb-12 space-y-3">
          <h2 className="text-3xl md:text-4xl font-bold">{t(m, 'landing.faq_title')}</h2>
          <p className="marketing-subtext">{t(m, 'landing.faq_desc')}</p>
        </div>

        <div className="relative mb-10">
          <div className="absolute inset-y-0 left-4 flex items-center pointer-events-none marketing-subtext opacity-60">
            <Search className="w-5 h-5" strokeWidth={1.5} />
          </div>
          <input
            type="text"
            placeholder={t(m, 'landing.faq_search_placeholder', 'ค้นหาหัวข้อที่ต้องการ (เช่น โควตา, ความปลอดภัย)...')}
            className="w-full pl-12 pr-12 py-4 marketing-card focus:outline-none focus:ring-2 focus:ring-amber-600/25 text-base"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
          {searchTerm && (
            <button
              onClick={() => setSearchTerm('')}
              className="absolute inset-y-0 right-4 flex items-center marketing-subtext opacity-60 hover:opacity-100 transition-opacity"
            >
              <X className="w-5 h-5" strokeWidth={1.5} />
            </button>
          )}
        </div>

        <div className="space-y-10">
          {Object.keys(groupedFaqs).length > 0 ? (
            Object.entries(groupedFaqs).map(([category, items]) => (
              <div key={category}>
                <h3 className="text-[11px] font-bold marketing-accent uppercase tracking-widest mb-4">
                  {category === 'General' || category === t(m, 'landing.faq_cat_general', 'ทั่วไป')
                    ? t(m, 'landing.faq_cat_general', category)
                    : t(m, `landing.faq_cat_${category.toLowerCase()}`, category)}
                </h3>
                <div className="space-y-2">
                  {items.map((faq, index) => (
                    <div
                      key={`${category}-${index}`}
                      className={`marketing-card overflow-hidden transition-colors ${openFaq === faq.id ? 'ring-1 ring-amber-600/30' : ''}`}
                    >
                      <button onClick={() => toggleFaq(faq.id)} className="w-full flex justify-between items-center text-left px-5 py-4 focus:outline-none">
                        <span className={`text-sm md:text-base font-medium transition-colors ${openFaq === faq.id ? 'marketing-accent' : ''}`}>{faq.displayQuestion}</span>
                        <ChevronDown className={`w-5 h-5 shrink-0 ml-4 transition-transform marketing-subtext ${openFaq === faq.id ? 'rotate-180' : ''}`} strokeWidth={1.5} />
                      </button>
                      <div className={`overflow-hidden transition-all duration-300 ${openFaq === faq.id ? 'max-h-60 opacity-100 border-t border-slate-200/80 dark:border-slate-600/60' : 'max-h-0 opacity-0'}`}>
                        <p className="px-5 pb-5 marketing-subtext leading-relaxed text-sm">{faq.displayAnswer}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))
          ) : (
            <div className="text-center py-12 marketing-card border-dashed">
              <p className="marketing-subtext text-sm">{t(m, 'landing.faq_empty')}</p>
            </div>
          )}
        </div>
      </div>
    </section>
  );
};

export default FaqSection;
