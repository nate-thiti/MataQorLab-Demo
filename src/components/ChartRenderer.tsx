// @ts-nocheck
import { useState, useEffect, useMemo } from 'react';
import { 
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell, AreaChart, Area,
  ComposedChart, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer
} from 'recharts';
import { useTheme } from '../context/ThemeContext';
import { useLocaleRouting } from '../context/LocaleRoutingContext';
import { Maximize2, Minimize2 } from '@/components/icons';
import { getMessages, t } from '../utils/i18n.js';
import { buildParetoRows } from '../features/visualization/dashboardModel.js';

const ChartRenderer = ({
  data: chartData,
  embedded = false,
  hideTitle = false,
  onCategoryClick,
  selectedCategory,
}) => {
  const { theme } = useTheme();
  const { locale } = useLocaleRouting();
  const m = getMessages(locale);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [modalReady, setModalReady] = useState(false);
  const isDark = theme === 'dark';

  // จัดการหน่วงเวลาโหลดกราฟใน Modal เล็กน้อย เพื่อรอให้ความกว้าง/ความสูงของหน้าต่างคำนวณเสร็จสมบูรณ์ ป้องกันปัญหากราฟว่างเปล่า
  useEffect(() => {
    if (!isFullscreen) return undefined;
    const tId = setTimeout(() => setModalReady(true), 150);
    return () => {
      clearTimeout(tId);
      setModalReady(false);
    };
  }, [isFullscreen]);

  // จัดการการกดปุ่ม ESC เพื่อออกจาก Fullscreen
  useEffect(() => {
    const handleEsc = (e) => {
      if (e.key === 'Escape') setIsFullscreen(false);
    };
    if (isFullscreen) {
      window.addEventListener('keydown', handleEsc);
      // ป้องกันการ Scroll พื้นหลังเมื่อขยายกราฟ
      document.body.style.overflow = 'hidden';
    }
    return () => {
      window.removeEventListener('keydown', handleEsc);
      document.body.style.overflow = 'unset';
    };
  }, [isFullscreen]);

  const hasChartData = chartData?.data?.length > 0;
  const { chart_type, config = {}, data = [] } = chartData || {};
  const { title = '', xAxis = '', color = '', palette = [], xAxisLabel = '', yAxisLabel = '' } = config;

  // หาคีย์ที่แท้จริงใน data[0] ที่ตรงกับ xAxis (แบบไม่สนใจพิมพ์เล็ก-ใหญ่)
  const actualXAxisKey = useMemo(() => {
    if (!hasChartData) return xAxis || '';
    const keys = Object.keys(data[0] || {});
    const configured = keys.find(
      key => typeof key === 'string' && typeof xAxis === 'string' && key.toLowerCase() === xAxis.toLowerCase()
    );
    if (configured) return configured;
    const nameKey = keys.find((key) => key.toLowerCase() === 'name');
    if (nameKey) return nameKey;
    return keys.find((key) =>
      data.some((item) => {
        const value = item[key];
        return value !== null && value !== undefined && Number.isNaN(Number(value));
      }),
    ) || keys[0] || '';
  }, [hasChartData, data, xAxis]);

  // กรองคอลัมน์ที่เป็นซีรีส์ตัวเลขจริงเท่านั้น (เพื่อป้องกันไม่ให้เอาคอลัมน์ที่เป็นข้อความอื่นมาวาด)
  const seriesKeys = useMemo(() => {
    if (!hasChartData) return [];
    return Object.keys(data[0] || {}).filter(key => {
      if (typeof key === 'string' && typeof actualXAxisKey === 'string' && key.toLowerCase() === actualXAxisKey.toLowerCase()) return false;
      
      // ตรวจสอบว่าในข้อมูลทั้งหมด มีอย่างน้อย 1 แถวที่เป็นตัวเลขหรือสามารถแปลงเป็นตัวเลขได้
      return data.some(item => {
        const val = item[key];
        if (val === undefined || val === null) return false;
        if (typeof val === 'number') return true;
        if (typeof val === 'string') {
          const cleaned = val.replace(/[^0-9.-]/g, '');
          return cleaned !== '' && !isNaN(parseFloat(cleaned));
        }
        return false;
      });
    });
  }, [hasChartData, data, actualXAxisKey]);
  
  // ทำความสะอาดและแปลงข้อมูลให้เป็นตัวเลข เพื่อให้ Recharts วาดกราฟได้ถูกต้อง (โดยเฉพาะ Pie Chart)
  const formattedData = useMemo(() => {
    if (!hasChartData) return [];
    return data.map(item => {
      const newItem = { ...item };
      seriesKeys.forEach(key => {
        if (newItem[key] !== undefined && newItem[key] !== null) {
          if (typeof newItem[key] === 'string') {
            const cleanedVal = newItem[key].replace(/[^0-9.-]/g, '');
            const num = parseFloat(cleanedVal);
            newItem[key] = isNaN(num) ? 0 : num;
          } else if (typeof newItem[key] === 'number') {
            // ถูกต้องแล้ว
          } else {
            newItem[key] = 0;
          }
        }
      });
      return newItem;
    });
  }, [hasChartData, data, seriesKeys]);

  if (!hasChartData) return null;

  // กำหนดชุดสีสำหรับเปรียบเทียบ (ยอดขาย: เขียว/น้ำเงิน, ต้นทุน: ส้ม/แดง)
  const defaultColors = isDark
    ? ['#3b82f6', '#f59e0b', '#10b981', '#f43f5e', '#8b5e34'] 
    : ['#2563eb', '#d97706', '#059669', '#dc2626', '#8b5e34'];
  const configuredPalette = Array.isArray(palette) ? palette.filter((item) => /^#[0-9a-f]{6}$/i.test(item)) : [];
  const baseColors = configuredPalette.length ? configuredPalette : defaultColors;
  const colors = color ? [color, ...baseColors.filter((item) => item !== color)] : baseColors;

  const commonTooltipStyle = {
    backgroundColor: isDark ? '#3c3c3c' : '#ffffff',
    borderColor: isDark ? 'rgba(255,255,255,0.1)' : '#e2e8f0',
    borderRadius: '8px',
    fontSize: '12px',
    fontWeight: '500',
    boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)',
    color: isDark ? '#f1f5f9' : '#1e293b'
  };

  // Custom Tooltip Component สำหรับ Bar และ Line Chart
  const CustomTooltip = ({ active, payload, label }) => {
    if (active && payload && payload.length) {
      return (
        <div style={commonTooltipStyle} className="p-3 border">
          <p className="text-sm font-bold mb-1">{label}</p>
          {payload.map((entry, index) => (
            <p key={`item-${index}`} style={{ color: entry.color }} className="text-xs">
              {entry.name}: {entry.value.toLocaleString()}
            </p>
          ))}
        </div>
      );
    }
    return null;
  };

  const axisTick = isDark ? '#64748b' : '#94a3b8';
  const axisLabelStyle = { fill: axisTick, fontSize: 10 };
  const xAxisProps = {
    dataKey: actualXAxisKey,
    stroke: axisTick,
    fontSize: 10,
    tickLine: false,
    axisLine: false,
    dy: 10,
    label: xAxisLabel
      ? { value: xAxisLabel, position: 'insideBottom', offset: -2, style: axisLabelStyle }
      : undefined,
  };
  const yAxisProps = {
    stroke: axisTick,
    fontSize: 10,
    tickLine: false,
    axisLine: false,
    label: yAxisLabel
      ? { value: yAxisLabel, angle: -90, position: 'insideLeft', style: axisLabelStyle }
      : undefined,
  };

  const cartesianMargin = {
    top: 20,
    right: 10,
    left: yAxisLabel ? 18 : 0,
    bottom: xAxisLabel ? 18 : 0,
  };

  const renderChart = (chartDataSrc) => {
    switch (chart_type) {
      case 'bar':
        return (
          <BarChart
            data={chartDataSrc}
            margin={cartesianMargin}
            onClick={(state) => {
              if (state?.activeLabel != null) onCategoryClick?.(state.activeLabel);
            }}
            style={{ cursor: onCategoryClick ? 'pointer' : 'default' }}
          >
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={isDark ? '#525252' : '#f1f5f9'} />
            <XAxis {...xAxisProps} />
            <YAxis {...yAxisProps} tickFormatter={(value) => value.toLocaleString()} domain={['auto', 'auto']} />
            <Tooltip content={<CustomTooltip />} cursor={{fill: isDark ? '#525252' : '#f8fafc'}} />
            <Legend verticalAlign="top" align="right" iconType="circle" wrapperStyle={{ fontSize: '10px', paddingBottom: '20px' }} />
            {seriesKeys.map((key, index) => (
              <Bar key={key} dataKey={key} fill={colors[index % colors.length]} radius={[6, 6, 0, 0]} barSize={seriesKeys.length > 1 ? 15 : 30} />
            ))}
          </BarChart>
        );
      case 'line':
        return (
          <LineChart
            data={chartDataSrc}
            margin={cartesianMargin}
            onClick={(state) => {
              if (state?.activeLabel != null) onCategoryClick?.(state.activeLabel);
            }}
            style={{ cursor: onCategoryClick ? 'pointer' : 'default' }}
          >
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={isDark ? '#525252' : '#f1f5f9'} />
            <XAxis {...xAxisProps} />
            <YAxis {...yAxisProps} domain={['auto', 'auto']} />
            <Tooltip content={<CustomTooltip />} />
            <Legend verticalAlign="top" align="right" iconType="circle" wrapperStyle={{ fontSize: '10px', paddingBottom: '20px' }} />
            {seriesKeys.map((key, index) => (
              <Line key={key} type="monotone" dataKey={key} stroke={colors[index % colors.length]} strokeWidth={3} dot={{ r: 4, strokeWidth: 2, fill: isDark ? '#1a1a21' : '#fff' }} activeDot={{ r: 6, strokeWidth: 0 }} />
            ))}
          </LineChart>
        );
      case 'pie':
        return (
          <PieChart>
            <Pie
              data={chartDataSrc}
              cx="50%"
              cy="50%"
              innerRadius={60}
              outerRadius={80}
              paddingAngle={5}
              dataKey={seriesKeys[0]}
              nameKey={actualXAxisKey}
              onClick={(entry) => onCategoryClick?.(entry?.[actualXAxisKey])}
              style={{ cursor: onCategoryClick ? 'pointer' : 'default' }}
            >
              {chartDataSrc.map((entry, index) => (
                <Cell
                  key={`cell-${index}`}
                  fill={colors[index % colors.length]}
                  opacity={
                    selectedCategory == null
                    || String(entry?.[actualXAxisKey]) === String(selectedCategory)
                      ? 1
                      : 0.35
                  }
                />
              ))}
            </Pie>
            <Tooltip contentStyle={commonTooltipStyle} />
            <Legend verticalAlign="bottom" iconType="circle" wrapperStyle={{ fontSize: '10px', paddingTop: '20px' }} />
          </PieChart>
        );
      case 'area':
        return (
          <AreaChart
            data={chartDataSrc}
            margin={cartesianMargin}
            onClick={(state) => {
              if (state?.activeLabel != null) onCategoryClick?.(state.activeLabel);
            }}
            style={{ cursor: onCategoryClick ? 'pointer' : 'default' }}
          >
            <defs>
              {seriesKeys.map((key, index) => (
                <linearGradient key={`grad-${key}`} id={`grad-${key}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={colors[index % colors.length]} stopOpacity={0.4}/>
                  <stop offset="95%" stopColor={colors[index % colors.length]} stopOpacity={0}/>
                </linearGradient>
              ))}
            </defs>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={isDark ? '#525252' : '#f1f5f9'} />
            <XAxis {...xAxisProps} />
            <YAxis {...yAxisProps} domain={['auto', 'auto']} />
            <Tooltip content={<CustomTooltip />} />
            <Legend verticalAlign="top" align="right" iconType="circle" wrapperStyle={{ fontSize: '10px', paddingBottom: '20px' }} />
            {seriesKeys.map((key, index) => (
              <Area key={key} type="monotone" dataKey={key} stroke={colors[index % colors.length]} fill={`url(#grad-${key})`} strokeWidth={3} dot={{ r: 4, strokeWidth: 2, fill: isDark ? '#1a1a21' : '#fff' }} />
            ))}
          </AreaChart>
        );
      case 'pareto': {
        const valueKey = seriesKeys[0];
        const paretoData = buildParetoRows(chartDataSrc, valueKey);
        return (
          <ComposedChart data={paretoData} margin={{ top: 20, right: 16, left: yAxisLabel ? 18 : 0, bottom: xAxisLabel ? 18 : 0 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={isDark ? '#525252' : '#f1f5f9'} />
            <XAxis {...xAxisProps} />
            <YAxis yAxisId="value" {...yAxisProps} />
            <YAxis yAxisId="percent" orientation="right" domain={[0, 100]} tickFormatter={(value) => `${value}%`} stroke={isDark ? '#a78bfa' : '#7c3aed'} fontSize={10} tickLine={false} axisLine={false} />
            <Tooltip content={<CustomTooltip />} />
            <Legend verticalAlign="top" align="right" iconType="circle" wrapperStyle={{ fontSize: '10px', paddingBottom: '20px' }} />
            <Bar yAxisId="value" dataKey={valueKey} fill={colors[0]} radius={[5, 5, 0, 0]} barSize={24} />
            <Line yAxisId="percent" type="monotone" dataKey="cumulativePercentage" name="Cumulative %" stroke={isDark ? '#a78bfa' : '#7c3aed'} strokeWidth={2.5} dot={{ r: 3 }} />
          </ComposedChart>
        );
      }
      default:
        return null;
    }
  };

  return (
    <>
      {/* กราฟปกติแสดงผลบนหน้าจอ */}
      <div className={embedded ? 'relative overflow-hidden' : 'my-8 p-6 enterprise-panel overflow-hidden relative'}>
        <div className={`relative ${hideTitle ? 'mb-2' : 'mb-6 flex flex-col items-center'}`}>
          {hideTitle ? null : (
            <h4 className="font-semibold text-slate-900 dark:text-slate-100 text-center text-sm">
              {title}
            </h4>
          )}
          <button 
            onClick={() => setIsFullscreen(true)}
            className="absolute top-0 right-0 p-2 rounded-lg transition-colors text-slate-400 hover:text-slate-700 dark:hover:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"
            title={t(m, 'chat.expand_chart', 'ขยายขนาดกราฟ')}
          >
            <Maximize2 size={18} />
          </button>
        </div>

        <div className="h-[280px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            {renderChart(formattedData)}
          </ResponsiveContainer>
        </div>

        {(seriesKeys.length > 1) && (
          <div className="mt-4 pt-4 border-t border-slate-200 dark:border-slate-800">
            <p className="text-[10px] text-slate-400 text-center font-sans">
              {seriesKeys.includes('sales') && seriesKeys.includes('cost') 
                ? t(m, 'chat.automated_comparison', '💡 ระบบเปรียบเทียบสัดส่วนรายได้และต้นทุนให้อัตโนมัติ')
                : t(m, 'chat.multidim_comparison', '💡 แสดงผลการเปรียบเทียบข้อมูลหลายมิติ')}
            </p>
          </div>
        )}
      </div>

      {/* Premium Pop-up Modal สำหรับขยายขนาดกราฟ */}
      {isFullscreen && (
        <div className="fixed inset-0 z-[999] flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
          <div className="app-modal w-full max-w-4xl p-6 md:p-8 flex flex-col relative">
            
            <div className="flex flex-col items-center mb-6 relative w-full">
              <h4 className="font-semibold text-slate-900 dark:text-slate-100 text-center text-base md:text-lg">
                {title}
              </h4>
              
              <button 
                onClick={() => setIsFullscreen(false)}
                className="absolute top-0 right-0 p-2 rounded-lg transition-colors text-slate-400 hover:text-slate-700 dark:hover:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"
                title={t(m, 'chat.minimize_chart', 'ย่อขนาดกราฟ')}
              >
                <Minimize2 size={20} />
              </button>
            </div>

            <div className="h-[400px] md:h-[500px] w-full relative">
              {modalReady ? (
                <ResponsiveContainer width="100%" height="100%">
                  {renderChart(formattedData)}
                </ResponsiveContainer>
              ) : (
                <div className="absolute inset-0 flex items-center justify-center">
                  <div className="w-8 h-8 border-2 border-slate-300 border-t-slate-600 dark:border-slate-700 dark:border-t-slate-300 rounded-full animate-spin"></div>
                </div>
              )}
            </div>

            <div className="mt-4 pt-4 border-t border-slate-200 dark:border-slate-800">
              <p className="text-xs text-slate-400 text-center font-sans">
                {t(m, 'chat.close_popup_hint', '💡 กดปุ่ม ESC หรือเครื่องหมายกากบาทเพื่อปิดหน้าต่างป๊อปอัปนี้')}
              </p>
            </div>

          </div>
        </div>
      )}
    </>
  );
};

export default ChartRenderer;
