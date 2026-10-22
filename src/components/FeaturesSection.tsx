// @ts-nocheck
import { t } from '../utils/i18n.js';
import { ArrowRight, BarChart3, Download, LineChart, MessageCircle } from '@/components/icons';

const FeaturesSection = ({ m }) => {
  return (
    <section id="platform" className="py-20 w-full px-6 marketing-section-divider">
      <div className="max-w-6xl mx-auto">
        <div className="grid lg:grid-cols-12 gap-12 items-center">
          
          {/* Left Column: Title, Description, Bullet Items */}
          <div className="lg:col-span-5 space-y-8 text-left" data-reveal>
            <div className="space-y-4">
              <h2 className="text-3xl md:text-4xl font-bold tracking-tight">
                {t(m, 'landing.chat_features.title')}
              </h2>
              <p className="marketing-subtext text-sm md:text-base leading-relaxed">
                {t(m, 'landing.chat_features.desc')}
              </p>
            </div>

            {/* Bullet List */}
            <div className="space-y-6">
              
              {/* Item 1 */}
              <div className="flex gap-4">
                <div className="w-10 h-10 rounded-lg bg-amber-600/10 flex items-center justify-center text-amber-700 dark:text-amber-400 shrink-0 mt-0.5">
                  <MessageCircle className="w-5 h-5" strokeWidth={1.5} />
                </div>
                <div>
                  <h4 className="text-sm font-semibold">{t(m, 'landing.chat_features.context_title')}</h4>
                  <p className="text-xs marketing-subtext mt-1 leading-relaxed">
                    {t(m, 'landing.chat_features.context_desc')}
                  </p>
                </div>
              </div>

              {/* Item 2 */}
              <div className="flex gap-4">
                <div className="w-10 h-10 rounded-lg bg-amber-600/10 flex items-center justify-center text-amber-700 dark:text-amber-400 shrink-0 mt-0.5">
                  <LineChart className="w-5 h-5" strokeWidth={1.5} />
                </div>
                <div>
                  <h4 className="text-sm font-semibold">{t(m, 'landing.chat_features.chart_title')}</h4>
                  <p className="text-xs marketing-subtext mt-1 leading-relaxed">
                    {t(m, 'landing.chat_features.chart_desc')}
                  </p>
                </div>
              </div>

            </div>
          </div>

          {/* Right Column: Premium Chat Mockup */}
          <div className="lg:col-span-7" data-reveal>
            <div className="marketing-card overflow-hidden font-sans" data-spotlight>
              
              {/* Mockup Header */}
              <div className="marketing-chat-mockup-header px-4 py-3 flex items-center justify-between text-xs">
                <span className="font-mono marketing-subtext">analysis-chat</span>
                <div className="flex items-center gap-1.5 text-emerald-600 dark:text-emerald-400 font-medium">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                  Pipeline active
                </div>
              </div>

              {/* Chat Viewport */}
              <div className="p-6 space-y-5 text-sm min-h-[300px]">
                
                {/* User Bubble */}
                <div className="flex justify-end">
                  <div className="bg-amber-600 text-white text-xs px-4 py-2.5 rounded-lg rounded-tr-none">
                    {t(m, 'landing.chat_features.mock_user_msg')}
                  </div>
                </div>

                {/* AI Bubble */}
                <div className="flex items-start gap-3">
                  {/* AI Logo Icon */}
                  <div className="w-7 h-7 rounded-md bg-amber-600 flex items-center justify-center text-white text-xs font-bold shrink-0 mt-0.5">
                    M
                  </div>
                  <div className="flex-1 space-y-3">
                    <div className="bg-slate-50 dark:bg-slate-800/60 text-slate-700 dark:text-slate-200 text-xs px-4 py-3.5 rounded-lg rounded-tl-none border border-slate-200/80 dark:border-slate-600/70 space-y-3">
                      <p className="font-semibold text-slate-800 dark:text-slate-100">
                        {t(m, 'landing.chat_features.mock_ai_greeting')}
                      </p>
                      
                      {/* Skeletons/Data Lines */}
                      <div className="space-y-2 pt-1">
                        <div className="flex items-center justify-between">
                          <span className="text-slate-500">{t(m, 'landing.chat_features.mock_central')}</span>
                          <span className="font-mono font-semibold text-slate-800 dark:text-slate-200">{t(m, 'landing.chat_features.mock_central_val')}</span>
                        </div>
                        <div className="w-full bg-slate-200 dark:bg-slate-700 h-1.5 rounded-full overflow-hidden">
                          <div className="bg-amber-600 h-full" style={{ width: '42%' }}></div>
                        </div>
                        
                        <div className="flex items-center justify-between pt-1">
                          <span className="text-slate-500">{t(m, 'landing.chat_features.mock_southern')}</span>
                          <span className="font-mono font-semibold text-slate-800 dark:text-slate-200">{t(m, 'landing.chat_features.mock_southern_val')}</span>
                        </div>
                        <div className="w-full bg-slate-200 dark:bg-slate-700 h-1.5 rounded-full overflow-hidden">
                          <div className="bg-amber-600 h-full" style={{ width: '30%' }}></div>
                        </div>
                      </div>

                      {/* Embed Action Buttons */}
                      <div className="flex items-center gap-2 pt-3">
                        <button className="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-amber-600/30 text-amber-700 dark:text-amber-400 hover:bg-amber-600/5 text-[10px] font-semibold transition-colors">
                          <BarChart3 className="w-3 h-3" strokeWidth={1.5} />
                          {t(m, 'landing.chat_features.mock_btn_bar')}
                        </button>
                        <button className="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-slate-300 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 text-[10px] font-semibold transition-colors">
                          <Download className="w-3 h-3" strokeWidth={1.5} />
                          {t(m, 'landing.chat_features.mock_btn_csv')}
                        </button>
                      </div>
                    </div>
                  </div>
                </div>

              </div>

              {/* Chat Input Mock */}
              <div className="marketing-chat-mockup-footer px-6 py-4 flex items-center justify-between gap-4">
                <input 
                  type="text" 
                  readOnly 
                  placeholder={t(m, 'landing.chat_features.mock_input_placeholder')} 
                  className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-600 rounded-lg px-4 py-2 text-xs w-full text-slate-500 dark:text-slate-300 outline-none"
                />
                <button className="w-8 h-8 rounded-lg bg-amber-600 flex items-center justify-center text-white shrink-0">
                  <ArrowRight className="w-4 h-4" strokeWidth={1.5} />
                </button>
              </div>

            </div>
          </div>

        </div>
      </div>
    </section>
  );
};

export default FeaturesSection;
