// @ts-nocheck
import { useState, useEffect, useMemo, useRef } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { supabase } from '../utils/supabaseClient.js';
import MappingRoleSelect from './MappingRoleSelect';
import { useLocaleRouting } from '../context/LocaleRoutingContext';
import { getMessages, t } from '../utils/i18n.js';
import { buildFilesPath } from '../utils/dashboardRoutes.js';
import { CircleAlert, FileText, Loader2, Trash2, TriangleAlert, X } from '@/components/icons';
import { authFetch } from '../utils/authFetch.js';
import { getPublicApiUrl } from '../utils/env.js';
import {
  buildMappingOptionGroups,
  SEMANTIC_ROLE_VALUES,
  suggestSemanticRole,
  countMappedColumns,
} from '../features/chat/columnMappingOptions.js';

const createDefaultRecipe = () => ({
  apply: true,
  rules: {
    drop_empty_rows: true,
    drop_empty_columns: true,
    dedupe: true,
    ffill: true,
    coerce_dates: true,
    strip_currency: true,
  },
  imputations: [],
  outliers: [],
  transformations: [],
  quality_rules: [],
  data_contract: {
    contract_version: '2.0',
    data_owner: '',
    data_steward: '',
    owner_contact: '',
    business_purpose: '',
    decisions_supported: [],
    row_grain: '',
    primary_keys: [],
    metric_definition: '',
    metric_definitions: [],
    causal_design: {
      date_column: '',
      outcome_column: '',
      intervention_date: '',
      treatment_column: '',
      treatment_value: '',
      control_value: '',
      group_column: '',
      predictor_columns: [],
      known_confounders: [],
    },
    cancellation_policy: '',
    null_policy: '',
    duplicate_policy: '',
    period_status: 'unknown',
    reporting_start: '',
    reporting_end: '',
    as_of_date: '',
    update_frequency: 'unknown',
    freshness_sla: '',
    timezone: 'Asia/Bangkok',
    currency: '',
    data_classification: 'internal',
    retention_policy: '',
    inclusions: [],
    exclusions: [],
    known_caveats: [],
    context_notes: '',
    column_contracts: {},
    enforcement_mode: 'warn',
    mapping_confirmed: false,
    business_context_reviewed: false,
    reviewed_by: '',
    reviewed_at: '',
  },
});

const buildContractSuggestions = (rows = [], mapping = {}, fileName = '', isEn = false) => {
  const entries = Object.entries(mapping).filter(([, role]) => role);
  const columnFor = (...roles) => entries.find(([, role]) => roles.includes(role))?.[0] || '';
  const metricColumn = columnFor('revenue', 'sales', 'profit', 'cost', 'quantity', 'output');
  const metricRole = entries.find(([column]) => column === metricColumn)?.[1] || 'metric';
  const keyCandidates = entries
    .filter(([, role]) => ['line_id', 'order_id', 'invoice_id', 'customer_id', 'id'].includes(role))
    .map(([column]) => column);
  const uniqueKeys = keyCandidates.filter((column) => {
    const values = rows.map((row) => row?.[column]).filter((value) => value !== null && value !== undefined && value !== '');
    return values.length > 0 && new Set(values.map(String)).size === values.length;
  });
  const grainRole = entries.find(([, role]) => ['line_id', 'order_id', 'invoice_id', 'customer_id'].includes(role));
  const dateColumn = columnFor('date', 'timestamp');
  const validDates = dateColumn
    ? rows.map((row) => new Date(row?.[dateColumn])).filter((date) => !Number.isNaN(date.getTime()))
    : [];
  const isoDate = (date) => date?.toISOString?.().slice(0, 10) || '';
  const datasetLabel = fileName?.split('_').slice(1).join(' ') || fileName || 'this dataset';
  return {
    business_purpose: metricColumn
      ? (isEn
        ? `Analyze ${metricRole} performance from ${datasetLabel}`
        : `วิเคราะห์ประสิทธิภาพ ${metricRole} จาก ${datasetLabel}`)
      : (isEn
        ? `Analyze business performance from ${datasetLabel}`
        : `วิเคราะห์ผลการดำเนินงานจาก ${datasetLabel}`),
    row_grain: grainRole
      ? (isEn
        ? `One row per ${String(grainRole[1]).replaceAll('_', ' ')}`
        : `หนึ่งแถวต่อ ${String(grainRole[1]).replaceAll('_', ' ')}`)
      : (isEn ? 'One row per source record' : 'หนึ่งแถวต่อหนึ่งรายการในข้อมูลต้นทาง'),
    metric_definition: metricColumn
      ? `Total ${metricRole} = SUM(${metricColumn})`
      : '',
    primary_keys: uniqueKeys.slice(0, 2),
    reporting_start: validDates.length ? isoDate(new Date(Math.min(...validDates.map(Number)))) : '',
    reporting_end: validDates.length ? isoDate(new Date(Math.max(...validDates.map(Number)))) : '',
    as_of_date: validDates.length ? isoDate(new Date(Math.max(...validDates.map(Number)))) : '',
    causal_design: {
      date_column: dateColumn,
      outcome_column: metricColumn,
    },
  };
};

export const FileSelectionModal = ({ showFileModal, setShowFileModal, isFilesLoading, availableFiles, hasMoreFiles = false, loadMoreFiles, setSelectedFile, getDisplayName, navigate, routing }) => {
  const { locale } = useLocaleRouting();
  const m = getMessages(locale);
  const scrollRef = useRef(null);
  // TanStack Virtual manages mutable measurements outside React memoization.
  // eslint-disable-next-line react-hooks/incompatible-library
  const fileVirtualizer = useVirtualizer({
    count: availableFiles.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => 62,
    overscan: 8,
  });

  if (!showFileModal) return null;
  return (
    <div className="fixed inset-0 z-[150] flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <div className="app-modal w-full max-w-md overflow-hidden flex flex-col max-h-[70vh]">
        <div className="p-5 border-b border-slate-200 dark:border-slate-800 flex justify-between items-center">
          <h3 className="font-semibold text-lg text-slate-900 dark:text-slate-100">
            {t(m, 'chat.mapping.file_modal_title', 'Select a file to analyze')}
          </h3>
          <button onClick={() => setShowFileModal(false)} className="p-2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg transition-colors">
            <X className="w-5 h-5" strokeWidth={1.5} />
          </button>
        </div>
        <div ref={scrollRef} className="flex-1 overflow-y-auto p-4">
          {isFilesLoading && availableFiles.length === 0 ? (
            <div className="text-center py-10 text-slate-400 dark:text-slate-500 text-sm font-sans">
              {t(m, 'chat.mapping.file_modal_loading', 'Loading file list...')}
            </div>
          ) : availableFiles.length === 0 ? (
            <div className="text-center py-10">
              <p className="text-slate-500 dark:text-slate-400 text-sm font-sans mb-4">
                {t(m, 'chat.mapping.file_modal_empty', 'No files found in your account')}
              </p>
              <button onClick={() => navigate(buildFilesPath(routing, {}))} className="text-[#d97706] text-xs font-medium hover:underline">
                {t(m, 'chat.mapping.file_modal_upload_link', 'Go to file management to upload →')}
              </button>
            </div>
          ) : (
            <>
              <div
                className="relative"
                style={{ height: `${fileVirtualizer.getTotalSize()}px` }}
              >
                {fileVirtualizer.getVirtualItems().map((virtualRow) => {
                  const file = availableFiles[virtualRow.index];
                  return (
                    <div
                      key={file.id || file.name}
                      className="absolute left-0 top-0 w-full pb-2"
                      style={{ transform: `translateY(${virtualRow.start}px)` }}
                    >
                      <button onClick={() => { setSelectedFile(file); setShowFileModal(false); }} className="w-full text-left p-3 rounded-lg border border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-600 hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors flex items-center gap-3 group">
                        <div className="w-8 h-8 bg-slate-100 dark:bg-slate-800 rounded-lg flex items-center justify-center text-slate-600 dark:text-slate-400">
                          <FileText className="w-4 h-4" strokeWidth={1.5} />
                        </div>
                        <span className="min-w-0 flex-1 truncate text-sm font-sans font-medium text-slate-700 dark:text-slate-300">
                          {file.display_name || getDisplayName(file.name)}
                        </span>
                        {file.is_etl_dataset && (
                          <span className="shrink-0 rounded-md bg-amber-50 px-2 py-1 text-[9px] font-semibold uppercase text-amber-700 dark:bg-amber-950/30 dark:text-amber-400">
                            ETL
                          </span>
                        )}
                      </button>
                    </div>
                  );
                })}
              </div>
              {hasMoreFiles && (
                <button
                  type="button"
                  onClick={loadMoreFiles}
                  disabled={isFilesLoading}
                  className="w-full rounded-lg px-3 py-2 text-xs font-semibold text-amber-700 hover:bg-amber-50 disabled:opacity-50 dark:text-amber-300 dark:hover:bg-amber-950/30"
                >
                  {isFilesLoading
                    ? t(m, 'common.loading', 'Loading…')
                    : t(m, 'chat.mapping.file_modal_load_more', 'Load more files')}
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
};

// --- Layer 3 & 5: Schema Detection (Rule-based) & User Confirmation ---
export const ColumnMappingModal = ({ isOpen, onClose, onConfirm, parsedData, fileName, storageFileName, datasetKey = null, userId, cleaningProfile = 'standard', onCleaningProfileChange, initialMapping = null, initialRecipe = null, jsonPaths = [], selectedJsonPath = null, onJsonPathChange }) => {
  const { locale } = useLocaleRouting();
  const m = getMessages(locale);
  const [mapping, setMapping] = useState<Record<string, any>>({});
  const [preview, setPreview] = useState<any>(null);
  const [previewing, setPreviewing] = useState(false);
  const [previewError, setPreviewError] = useState('');
  const [recipe, setRecipe] = useState<any>(() => createDefaultRecipe());
  const headers = useMemo(
    () => (parsedData && parsedData.length > 0 ? Object.keys(parsedData[0]) : []),
    [parsedData],
  );
  const options = buildMappingOptionGroups(m);
  const mappedCount = countMappedColumns(mapping);
  const progressPct = headers.length ? Math.round((mappedCount / headers.length) * 100) : 0;
  const contractSuggestions = useMemo(
    () => buildContractSuggestions(parsedData || [], mapping, fileName, locale === 'en'),
    [parsedData, mapping, fileName, locale],
  );
  const contractReadiness = useMemo(() => {
    const contract = recipe.data_contract || {};
    const checks = {
      mapping: mappedCount > 0,
      purpose: Boolean(contract.business_purpose?.trim()),
      grain: Boolean(contract.row_grain?.trim()),
      metric: Boolean(
        contract.metric_definition?.trim() || contract.metric_definitions?.length,
      ),
    };
    const weights = {
      mapping: 25, purpose: 25, grain: 25, metric: 25,
    };
    const score = Object.entries(checks).reduce(
      (total, [key, passed]) => total + (passed ? weights[key] : 0),
      0,
    );
    const missing = Object.entries(checks)
      .filter(([, passed]) => !passed)
      .map(([key]) => key);
    const invalidKeys = (contract.primary_keys || []).filter((column) => !headers.includes(column));
    return {
      score,
      missing,
      invalidKeys,
      ready: score === 100 && invalidKeys.length === 0,
      blocking: mappedCount === 0
        || invalidKeys.length > 0,
    };
  }, [headers, mappedCount, recipe.data_contract]);

  const getSelectValue = (header, currentValue, isChecked) => {
    if (isChecked) return '__original__';
    if (!currentValue) return '__none__';
    if (SEMANTIC_ROLE_VALUES.includes(currentValue)) return currentValue;
    return '__custom__';
  };

  const handleRoleSelect = (header, val, formattedHeader) => {
    if (val === '__original__') {
      setMapping({ ...mapping, [header]: formattedHeader });
      return;
    }
    if (val === '__none__') {
      setMapping({ ...mapping, [header]: '' });
      return;
    }
    if (val === '__custom__') {
      const prev = mapping[header] || '';
      const custom = SEMANTIC_ROLE_VALUES.includes(prev) ? '' : prev;
      setMapping({ ...mapping, [header]: custom });
      return;
    }
    setMapping({ ...mapping, [header]: val });
  };
  useEffect(() => {
    const initMapping = async () => {
      if (!headers.length) return;
      
      const detected = {};
      headers.forEach((header) => {
        detected[header] = suggestSemanticRole(header);
      });

      // Dataset-scoped memory is authoritative; legacy global memory is fallback only.
      if (userId) {
        try {
          let memoryData = null;
          if (datasetKey) {
            const scoped = await supabase
              .from('dataset_mapping_memory')
              .select('original_column, mapped_semantic, column_contract')
              .eq('user_id', userId)
              .eq('dataset_key', datasetKey);
            if (!scoped.error) {
              memoryData = scoped.data;
              const scopedContracts = {};
              (scoped.data || []).forEach((item) => {
                if (item.column_contract && Object.keys(item.column_contract).length) {
                  scopedContracts[item.original_column] = item.column_contract;
                }
              });
              if (Object.keys(scopedContracts).length) {
                setRecipe((current) => ({
                  ...current,
                  data_contract: {
                    ...current.data_contract,
                    column_contracts: {
                      ...(current.data_contract?.column_contracts || {}),
                      ...scopedContracts,
                    },
                  },
                }));
              }
            }
          }
          if (!memoryData?.length) {
            const legacy = await supabase
              .from('column_mappings_memory')
              .select('original_column, mapped_semantic')
              .eq('user_id', userId);
            memoryData = legacy.data;
          }
          
          if (memoryData) {
            memoryData.forEach(item => {
              if (headers.includes(item.original_column)) {
                detected[item.original_column] = item.mapped_semantic;
              }
            });
          }
        } catch (err: any) {
          console.error("Layer 12 Recall Error:", err);
        }
      }
      
      if (initialMapping) {
        Object.entries(initialMapping).forEach(([col, val]) => {
          if (headers.includes(col) && val) {
            detected[col] = val;
          }
        });
      }
      
      setMapping(detected);
    };

    if (isOpen) initMapping();
  }, [isOpen, parsedData, userId, initialMapping, headers, datasetKey]);

  useEffect(() => {
    if (!isOpen) {
      setPreview(null);
      setPreviewError('');
    } else {
      const defaults = createDefaultRecipe();
      setRecipe({
        ...defaults,
        ...(initialRecipe || {}),
        rules: { ...defaults.rules, ...(initialRecipe?.rules || {}) },
        data_contract: {
          ...defaults.data_contract,
          ...(initialRecipe?.data_contract || {}),
          column_contracts: {
            ...defaults.data_contract.column_contracts,
            ...(initialRecipe?.data_contract?.column_contracts || {}),
          },
        },
      });
    }
  }, [isOpen, initialRecipe]);

  useEffect(() => {
    if (!isOpen || !mappedCount) return;
    setRecipe((current) => {
      const contract = current.data_contract || {};
      const next = { ...contract };
      Object.entries(contractSuggestions).forEach(([key, suggestion]) => {
        if (key === 'causal_design') {
          next.causal_design = { ...(next.causal_design || {}) };
          Object.entries(suggestion || {}).forEach(([causalKey, causalSuggestion]) => {
            if (!next.causal_design[causalKey] && causalSuggestion) {
              next.causal_design[causalKey] = causalSuggestion;
            }
          });
          return;
        }
        const empty = Array.isArray(next[key]) ? next[key].length === 0 : !String(next[key] || '').trim();
        if (empty && (Array.isArray(suggestion) ? suggestion.length : suggestion)) {
          next[key] = suggestion;
        }
      });
      return JSON.stringify(next) === JSON.stringify(contract)
        ? current
        : { ...current, data_contract: next };
    });
  }, [contractSuggestions, isOpen, mappedCount]);

  if (!isOpen) return null;

  const handleConfirm = async () => {
    const finalMapping = {};
    Object.entries(mapping).forEach(([col, englishName]) => {
      const cleanName = (englishName || '').trim();
      if (cleanName) {
        finalMapping[col] = cleanName;
      }
    });
    const reviewed = Boolean(recipe.data_contract?.business_context_reviewed);
    const approvedRecipe = {
      ...recipe,
      cleaning_profile: cleaningProfile,
      column_mapping: finalMapping,
      data_contract: {
        ...(recipe.data_contract || {}),
        mapping_confirmed: true,
        reviewed_at: reviewed ? new Date().toISOString() : '',
      },
    };
    if (contractReadiness.blocking) return;
    const recipeDatasetKey = datasetKey || storageFileName;
    if (userId && recipeDatasetKey) {
      const columnContracts = approvedRecipe.data_contract?.column_contracts || {};
      const scopedMemory = Object.entries(finalMapping).map(([originalColumn, semantic]) => ({
        user_id: userId,
        dataset_key: recipeDatasetKey,
        original_column: originalColumn,
        mapped_semantic: semantic,
        column_contract: columnContracts[originalColumn] || {},
        mapping_source: 'user',
        confirmed_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      }));
      if (scopedMemory.length) {
        const { error } = await supabase
          .from('dataset_mapping_memory')
          .upsert(scopedMemory, { onConflict: 'user_id,dataset_key,original_column' });
        if (error && error.code !== 'PGRST205' && error.code !== '42P01') {
          console.warn('Could not save dataset-scoped mapping memory:', error);
        }
      }
    }
    if (userId && recipeDatasetKey) {
      try {
        await authFetch(`${getPublicApiUrl()}/api/v1/etl/recipes`, {
          body: {
            user_id: userId,
            dataset_key: recipeDatasetKey,
            name: `${fileName || recipeDatasetKey} cleaning`,
            recipe: approvedRecipe,
          },
        });
      } catch (error) {
        console.warn('Could not version ETL recipe:', error);
      }
    }
    onConfirm(finalMapping, approvedRecipe);
  };

  const updateDataContract = (key, value) => {
    setRecipe((current) => ({
      ...current,
      data_contract: {
        ...(current.data_contract || {}),
        [key]: value,
      },
    }));
  };

  const updateColumnContract = (column, key, value) => {
    setRecipe((current) => ({
      ...current,
      data_contract: {
        ...(current.data_contract || {}),
        column_contracts: {
          ...(current.data_contract?.column_contracts || {}),
          [column]: {
            ...(current.data_contract?.column_contracts?.[column] || {}),
            [key]: value,
          },
        },
      },
    }));
  };

  const runCleaningPreview = async (profileOverride = cleaningProfile) => {
    if (!storageFileName || !userId) return;
    setPreviewing(true);
    setPreviewError('');
    try {
      const response = await authFetch(`${getPublicApiUrl()}/api/v1/etl/preview`, {
        body: {
          user_id: userId,
          file_name: storageFileName,
          column_mapping: mapping,
          cleaning_profile: profileOverride,
          recipe,
        },
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => ({}));
        throw new Error(detail.detail || 'Preview failed');
      }
      setPreview(await response.json());
    } catch (error: any) {
      setPreviewError(error?.message || 'Preview failed');
    } finally {
      setPreviewing(false);
    }
  };

  const toggleImputation = (item) => {
    if (item.recommended_method === 'review') return;
    setRecipe((current) => {
      const exists = current.imputations.some((entry) => entry.column === item.column);
      return {
        ...current,
        imputations: exists
          ? current.imputations.filter((entry) => entry.column !== item.column)
          : [...current.imputations, {
              column: item.column,
              method: item.recommended_method,
              confirmed: !item.critical,
            }],
      };
    });
  };

  const setOutlierAction = (column, action) => {
    setRecipe((current) => ({
      ...current,
      outliers: [
        ...current.outliers.filter((entry) => entry.column !== column),
        ...(action === 'keep' ? [] : [{ column, action }]),
      ],
    }));
  };

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <div className="app-modal w-full max-w-2xl overflow-hidden flex flex-col max-h-[85vh]">
        <header className="p-5 border-b border-slate-200 dark:border-slate-800">
          <div className="flex justify-between items-start gap-4">
            <div className="min-w-0">
              <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
                {t(m, 'chat.mapping.modal_title', 'Map column data')}
              </h3>
              <p className="text-xs text-slate-500 font-sans mt-1 truncate">
                {t(m, 'chat.mapping.modal_file_label', 'File: {file}', { file: fileName })}
              </p>
              <div className="mt-3 flex items-center gap-3">
                <div className="flex-1 h-1.5 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden max-w-xs">
                  <div
                    className="h-full rounded-full bg-[#d97706] transition-all duration-300"
                    style={{ width: `${progressPct}%` }}
                  />
                </div>
                <span className="text-[11px] font-medium text-slate-500 dark:text-slate-400 tabular-nums shrink-0">
                  {t(m, 'chat.mapping.progress', '{mapped} / {total} mapped', {
                    mapped: mappedCount,
                    total: headers.length,
                  })}
                </span>
              </div>
            </div>
            <button onClick={onClose} className="p-2 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg transition-colors shrink-0">
              <X className="w-5 h-5 text-slate-400" strokeWidth={1.5} />
            </button>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto p-5 app-main-scroll">
          <section className="mb-5 rounded-xl border border-amber-200 dark:border-amber-900/60 bg-amber-50/50 dark:bg-amber-950/10 p-4 space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-200 mb-2">
                {locale === 'en' ? 'Cleaning profile' : 'รูปแบบการทำความสะอาดข้อมูล'}
              </label>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                {[
                  ['standard', t(m, 'chat.cleaning_profile_standard', 'Standard'), t(m, 'chat.cleaning_profile_standard_desc', 'Trim, remove empty rows/columns, dedupe, fill merged gaps, and parse mapped dates/currency.')],
                  ['financial', t(m, 'chat.cleaning_profile_financial', 'Financial'), t(m, 'chat.cleaning_profile_financial_desc', 'Accounting-safe: keep duplicates and merged gaps.')],
                  ['conservative', t(m, 'chat.cleaning_profile_careful', 'Careful'), t(m, 'chat.cleaning_profile_careful_desc', 'Minimal: trim and empty→null only.')],
                  ['aggressive', t(m, 'chat.cleaning_profile_deep_clean', 'Deep Clean'), t(m, 'chat.cleaning_profile_deep_clean_desc', 'Maximum cleanup with type inference and mostly-empty-row removal.')],
                ].map(([value, label, description]) => (
                  <div key={value} className="group relative">
                    <button type="button" onClick={() => {
                      onCleaningProfileChange?.(value);
                      setRecipe((current) => ({ ...current, rules: {} }));
                      if (preview) runCleaningPreview(value);
                    }} aria-describedby={`cleaning-profile-${value}`} className={`w-full rounded-lg border px-2 py-2 text-xs font-semibold transition-colors ${cleaningProfile === value ? 'border-[#d97706] bg-[#d97706] text-white' : 'border-slate-200 bg-white text-slate-600 hover:border-amber-300 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300'}`}>
                      {label}
                    </button>
                    <div id={`cleaning-profile-${value}`} role="tooltip" className="pointer-events-none absolute bottom-[calc(100%+8px)] left-1/2 z-50 hidden w-56 -translate-x-1/2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-left text-xs leading-snug text-slate-600 shadow-xl group-hover:block group-focus-within:block dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300">
                      {description}
                    </div>
                  </div>
                ))}
              </div>
              <p className="mt-1.5 text-[11px] text-slate-500">
                {locale === 'en' ? 'Changing the profile refreshes an existing preview.' : 'เมื่อเปลี่ยน profile ระบบจะ refresh Preview เดิมตามที่เลือก'}
              </p>
            </div>
            {jsonPaths.length > 0 && (
              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-200 mb-1">
                  {locale === 'en' ? 'JSON record path' : 'JSON path สำหรับรายการข้อมูล'}
                </label>
                <select
                  value={selectedJsonPath || ''}
                  onChange={async (event) => {
                    try {
                      await onJsonPathChange?.(event.target.value);
                    } catch (error) {
                      setPreviewError(error?.message || 'Could not load JSON path');
                    }
                  }}
                  className="w-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg px-3 py-2 text-xs"
                >
                  {jsonPaths.map((path) => <option key={path} value={path}>{path}</option>)}
                </select>
                <p className="mt-1 text-[11px] text-slate-500">
                  {locale === 'en' ? 'Select the array of objects to use as table rows.' : 'เลือก array ของ object ที่ต้องการใช้เป็นแถวข้อมูล'}
                </p>
              </div>
            )}
            <div className="flex items-start justify-between gap-3">
              <div>
                <h4 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                  {locale === 'en' ? '1. Cleaning preview' : '1. ตรวจสอบ Cleaning ก่อน Mapping'}
                </h4>
                <p className="text-[11px] text-slate-500 mt-1">
                  {locale === 'en' ? 'The source file is never overwritten.' : 'ระบบไม่เขียนทับไฟล์ต้นฉบับ'}
                </p>
              </div>
              <button type="button" onClick={() => runCleaningPreview()} disabled={previewing || !storageFileName} className="btn-secondary px-3 py-2 text-xs disabled:opacity-50">
                {previewing ? (locale === 'en' ? 'Checking…' : 'กำลังตรวจ…') : 'Preview'}
              </button>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
              {[
                ['drop_empty_rows', locale === 'en' ? 'Drop empty rows' : 'ลบแถวว่าง'],
                ['drop_empty_columns', locale === 'en' ? 'Drop empty columns' : 'ลบคอลัมน์ว่าง'],
                ['dedupe', locale === 'en' ? 'Remove duplicates' : 'ลบข้อมูลซ้ำ'],
                ['ffill', locale === 'en' ? 'Fill merged gaps' : 'เติมช่อง merged'],
                ['coerce_dates', locale === 'en' ? 'Parse dates' : 'แปลงวันที่'],
                ['strip_currency', locale === 'en' ? 'Parse currency' : 'แปลงสกุลเงิน'],
              ].map(([key, label]) => (
                <label key={key} className="flex items-center gap-2 text-xs text-slate-700 dark:text-slate-300">
                  <input
                    type="checkbox"
                    checked={recipe.rules[key] !== false}
                    onChange={(event) => setRecipe((current) => ({
                      ...current,
                      rules: { ...current.rules, [key]: event.target.checked },
                    }))}
                    className="accent-[#d97706]"
                  />
                  {label}
                </label>
              ))}
            </div>

            {previewError && <p className="text-xs text-red-600">{previewError}</p>}
            {preview && (
              <div className="space-y-3">
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  {[
                    [locale === 'en' ? 'Rows' : 'แถวทั้งหมด', preview.total_rows],
                    [locale === 'en' ? 'After sample' : 'หลัง Clean (sample)', preview.rows_after],
                    [locale === 'en' ? 'Columns' : 'คอลัมน์ก่อน', preview.columns_before?.length],
                    [locale === 'en' ? 'After' : 'คอลัมน์หลัง', preview.columns_after?.length],
                  ].map(([label, value]) => (
                    <div key={label} className="rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-2">
                      <div className="text-[10px] text-slate-500">{label}</div>
                      <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">{Number(value || 0).toLocaleString()}</div>
                    </div>
                  ))}
                </div>

                {!!preview.missing_recommendations?.length && (
                  <div>
                    <div className="text-xs font-semibold text-slate-700 dark:text-slate-200 mb-1">
                      {locale === 'en' ? 'Missing values — click to approve' : 'ค่าว่าง — คลิกเพื่ออนุมัติการเติม'}
                    </div>
                    <div className="max-h-28 overflow-y-auto space-y-1">
                      {preview.missing_recommendations.map((item) => {
                        const selected = recipe.imputations.some((entry) => entry.column === item.column);
                        return (
                          <button key={item.column} type="button" disabled={item.recommended_method === 'review'} onClick={() => toggleImputation(item)}
                            className={`w-full flex justify-between gap-3 rounded px-2 py-1.5 text-left text-xs border ${selected ? 'border-amber-500 bg-amber-100/70 dark:bg-amber-950/30' : 'border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900'} disabled:opacity-60`}>
                            <span className="truncate">{item.column} · {(item.missing_rate * 100).toFixed(1)}%</span>
                            <span>{item.recommended_method === 'review' ? (locale === 'en' ? 'Review required' : 'ต้องตรวจเอง') : item.recommended_method}</span>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}

                {!!preview.outlier_candidates?.length && (
                  <div>
                    <div className="text-xs font-semibold text-slate-700 dark:text-slate-200 mb-1">
                      {locale === 'en' ? 'Outliers (kept by default)' : 'Outlier (ค่าเริ่มต้นเก็บไว้)'}
                    </div>
                    <div className="space-y-1">
                      {preview.outlier_candidates.slice(0, 8).map((item) => (
                        <div key={item.column} className="flex items-center justify-between gap-2 text-xs">
                          <span className="truncate">{item.column} · {item.count}</span>
                          <select value={recipe.outliers.find((entry) => entry.column === item.column)?.action || 'keep'} onChange={(event) => setOutlierAction(item.column, event.target.value)}
                            className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded px-2 py-1">
                            <option value="keep">{locale === 'en' ? 'Keep' : 'เก็บไว้'}</option>
                            <option value="flag">{locale === 'en' ? 'Flag' : 'ติดธง'}</option>
                            <option value="winsorize">Winsorize</option>
                            <option value="exclude">{locale === 'en' ? 'Exclude' : 'ไม่นำมาวิเคราะห์'}</option>
                          </select>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {preview.contract_readiness && (
                  <div className={`rounded-lg border px-3 py-2 text-xs ${
                    preview.contract_readiness.status === 'ready'
                      ? 'border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-900/50 dark:bg-emerald-950/20 dark:text-emerald-200'
                      : 'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900/50 dark:bg-amber-950/20 dark:text-amber-200'
                  }`}>
                    <div className="font-semibold">
                      {locale === 'en' ? 'Contract readiness' : 'ความพร้อมของ Data Contract'}
                      {' · '}{preview.contract_readiness.score}%
                    </div>
                    {!!preview.contract_readiness.errors?.length && (
                      <ul className="mt-1 list-disc pl-4">
                        {preview.contract_readiness.errors.map((item) => (
                          <li key={item.code}>{item.message} {item.fields || ''}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
              </div>
            )}
          </section>

          <section className="mb-5 rounded-xl border border-cyan-200 bg-cyan-50/40 p-4 dark:border-cyan-900/60 dark:bg-cyan-950/10">
            <div className="mb-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h4 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                  {locale === 'en' ? '2. Data contract & business context' : '2. ข้อตกลงข้อมูลและบริบทธุรกิจ'}
                </h4>
                <span className={`rounded-full px-2.5 py-1 text-[10px] font-semibold ${
                  contractReadiness.ready
                    ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300'
                    : 'bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300'
                }`}>
                  {locale === 'en' ? 'Readiness' : 'ความพร้อม'} {contractReadiness.score}%
                </span>
              </div>
              <p className="mt-1 text-[11px] leading-relaxed text-slate-500">
                {locale === 'en'
                  ? 'Safe suggestions are filled from mapping and sample values. Review only the essentials; everything else is optional.'
                  : 'ระบบเติมคำแนะนำจาก Mapping และข้อมูลตัวอย่างให้อัตโนมัติ ตรวจเฉพาะข้อมูลจำเป็น ส่วนอื่นไม่บังคับ'}
              </p>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              {[
                ['business_purpose', locale === 'en' ? 'Decision / purpose' : 'ต้องการใช้ข้อมูลตัดสินใจเรื่องอะไร', locale === 'en' ? 'e.g. Daily sales review' : 'เช่น ตรวจยอดขายรายวัน'],
                ['row_grain', locale === 'en' ? 'One row represents' : 'หนึ่งแถวหมายถึง', locale === 'en' ? 'e.g. One order line' : 'เช่น หนึ่งรายการสินค้าในใบสั่งซื้อ'],
                ['metric_definition', locale === 'en' ? 'Primary metric definition' : 'นิยาม Metric หลัก', locale === 'en' ? 'e.g. Revenue excluding VAT' : 'เช่น ยอดขายไม่รวม VAT'],
              ].map(([key, label, placeholder]) => (
                <label key={key}>
                  <span className="mb-1 block text-[11px] font-semibold text-slate-700 dark:text-slate-200">{label}</span>
                  <input
                    type="text"
                    value={recipe.data_contract?.[key] || ''}
                    onChange={(event) => updateDataContract(key, event.target.value)}
                    placeholder={placeholder}
                    maxLength={1000}
                    className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-800 outline-none focus:border-cyan-500 focus:ring-2 focus:ring-cyan-500/20 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
                  />
                  {contractSuggestions[key] && recipe.data_contract?.[key] === contractSuggestions[key] && (
                    <span className="mt-1 block text-[9px] font-medium text-cyan-700 dark:text-cyan-300">
                      {locale === 'en' ? 'Suggested automatically — please review' : 'ระบบแนะนำอัตโนมัติ — กรุณาตรวจสอบ'}
                    </span>
                  )}
                </label>
              ))}

              <label>
                <span className="mb-1 block text-[11px] font-semibold text-slate-700 dark:text-slate-200">
                  {locale === 'en' ? 'Primary / natural keys' : 'คีย์หลักของข้อมูล'}
                </span>
                <select
                  multiple
                  value={recipe.data_contract?.primary_keys || []}
                  onChange={(event) => updateDataContract(
                    'primary_keys',
                    Array.from(event.target.selectedOptions, (option) => option.value),
                  )}
                  className="h-24 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs dark:border-slate-700 dark:bg-slate-900"
                >
                  {headers.map((header) => <option key={header} value={header}>{header}</option>)}
                </select>
                <span className="mt-1 block text-[10px] text-slate-500">
                  {locale === 'en' ? 'Use Ctrl/Cmd to select multiple columns.' : 'กด Ctrl/Cmd เพื่อเลือกหลายคอลัมน์'}
                </span>
              </label>

              <details className="sm:col-span-2 rounded-xl border border-slate-200 bg-white/70 p-3 dark:border-slate-700 dark:bg-slate-900/50">
                <summary className="cursor-pointer text-xs font-semibold text-slate-700 dark:text-slate-200">
                  {locale === 'en' ? 'Advanced contract settings (optional)' : 'การตั้งค่าขั้นสูง (ไม่บังคับ)'}
                </summary>
                <p className="mt-2 text-[10px] leading-relaxed text-slate-500">
                  {locale === 'en'
                    ? 'Use these only for governed scheduled ETL, compliance, or before/after intervention studies.'
                    : 'ใช้เฉพาะ Scheduled ETL ที่ต้องกำกับ, งาน Compliance หรือการวิเคราะห์ก่อน–หลังมาตรการ'}
                </p>
                <div className="mt-3 grid gap-3 sm:grid-cols-2">
              {[
                ['data_owner', locale === 'en' ? 'Data owner' : 'เจ้าของข้อมูล'],
                ['data_steward', locale === 'en' ? 'Data steward' : 'ผู้ดูแลคุณภาพข้อมูล'],
                ['owner_contact', locale === 'en' ? 'Owner contact' : 'ช่องทางติดต่อเจ้าของข้อมูล'],
                ['cancellation_policy', locale === 'en' ? 'Cancellation / return policy' : 'วิธีนับรายการยกเลิก/คืน'],
                ['null_policy', locale === 'en' ? 'Missing-value meaning' : 'ความหมายของค่าว่าง'],
                ['duplicate_policy', locale === 'en' ? 'Duplicate policy' : 'วิธีพิจารณาข้อมูลซ้ำ'],
              ].map(([key, label]) => (
                <label key={key}>
                  <span className="mb-1 block text-[11px] font-semibold text-slate-700 dark:text-slate-200">{label}</span>
                  <input
                    value={recipe.data_contract?.[key] || ''}
                    onChange={(event) => updateDataContract(key, event.target.value)}
                    className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs dark:border-slate-700 dark:bg-slate-900"
                  />
                </label>
              ))}
              <label>
                <span className="mb-1 block text-[11px] font-semibold text-slate-700 dark:text-slate-200">
                  {locale === 'en' ? 'Reporting period status' : 'สถานะงวดข้อมูล'}
                </span>
                <select
                  value={recipe.data_contract?.period_status || 'unknown'}
                  onChange={(event) => updateDataContract('period_status', event.target.value)}
                  className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs dark:border-slate-700 dark:bg-slate-900"
                >
                  <option value="unknown">{locale === 'en' ? 'Unknown / not checked' : 'ยังไม่ทราบ / ยังไม่ตรวจ'}</option>
                  <option value="in_progress">{locale === 'en' ? 'Still in progress' : 'งวดยังไม่ครบ'}</option>
                  <option value="complete">{locale === 'en' ? 'Complete / closed' : 'ข้อมูลครบ / ปิดงวดแล้ว'}</option>
                </select>
              </label>

              <label>
                <span className="mb-1 block text-[11px] font-semibold text-slate-700 dark:text-slate-200">
                  {locale === 'en' ? 'Update frequency' : 'ความถี่ในการอัปเดต'}
                </span>
                <select
                  value={recipe.data_contract?.update_frequency || 'unknown'}
                  onChange={(event) => updateDataContract('update_frequency', event.target.value)}
                  className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs dark:border-slate-700 dark:bg-slate-900"
                >
                  {['unknown', 'realtime', 'hourly', 'daily', 'weekly', 'monthly', 'quarterly', 'ad_hoc'].map((value) => (
                    <option key={value} value={value}>{value.replace('_', ' ')}</option>
                  ))}
                </select>
              </label>

              <label>
                <span className="mb-1 block text-[11px] font-semibold text-slate-700 dark:text-slate-200">
                  {locale === 'en' ? 'Timezone' : 'เขตเวลา'}
                </span>
                <input
                  value={recipe.data_contract?.timezone || ''}
                  onChange={(event) => updateDataContract('timezone', event.target.value)}
                  placeholder="Asia/Bangkok"
                  className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs dark:border-slate-700 dark:bg-slate-900"
                />
              </label>

              <label>
                <span className="mb-1 block text-[11px] font-semibold text-slate-700 dark:text-slate-200">
                  {locale === 'en' ? 'Currency' : 'สกุลเงิน'}
                </span>
                <input
                  value={recipe.data_contract?.currency || ''}
                  onChange={(event) => updateDataContract('currency', event.target.value.toUpperCase().replace(/[^A-Z]/g, '').slice(0, 3))}
                  placeholder="THB"
                  className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs uppercase dark:border-slate-700 dark:bg-slate-900"
                />
              </label>

              <label>
                <span className="mb-1 block text-[11px] font-semibold text-slate-700 dark:text-slate-200">
                  {locale === 'en' ? 'Data classification' : 'ชั้นความลับของข้อมูล'}
                </span>
                <select
                  value={recipe.data_contract?.data_classification || 'internal'}
                  onChange={(event) => updateDataContract('data_classification', event.target.value)}
                  className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs dark:border-slate-700 dark:bg-slate-900"
                >
                  {['public', 'internal', 'confidential', 'restricted'].map((value) => (
                    <option key={value} value={value}>{value}</option>
                  ))}
                </select>
              </label>

              {[
                ['reporting_start', locale === 'en' ? 'Reporting start' : 'วันเริ่มงวด'],
                ['reporting_end', locale === 'en' ? 'Reporting end' : 'วันสิ้นสุดงวด'],
                ['as_of_date', locale === 'en' ? 'Data as of' : 'ข้อมูล ณ วันที่'],
              ].map(([key, label]) => (
                <label key={key}>
                  <span className="mb-1 block text-[11px] font-semibold text-slate-700 dark:text-slate-200">{label}</span>
                  <input
                    type="date"
                    value={recipe.data_contract?.[key] || ''}
                    onChange={(event) => updateDataContract(key, event.target.value)}
                    className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs dark:border-slate-700 dark:bg-slate-900"
                  />
                </label>
              ))}

              <label>
                <span className="mb-1 block text-[11px] font-semibold text-slate-700 dark:text-slate-200">
                  {locale === 'en' ? 'Freshness SLA' : 'SLA ความสดใหม่'}
                </span>
                <input
                  value={recipe.data_contract?.freshness_sla || ''}
                  onChange={(event) => updateDataContract('freshness_sla', event.target.value)}
                  placeholder={locale === 'en' ? 'e.g. available by 08:00 next day' : 'เช่น พร้อมใช้ก่อน 08:00 ของวันถัดไป'}
                  className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs dark:border-slate-700 dark:bg-slate-900"
                />
              </label>

              <label>
                <span className="mb-1 block text-[11px] font-semibold text-slate-700 dark:text-slate-200">
                  {locale === 'en' ? 'Retention policy' : 'นโยบายการเก็บรักษา'}
                </span>
                <input
                  value={recipe.data_contract?.retention_policy || ''}
                  onChange={(event) => updateDataContract('retention_policy', event.target.value)}
                  placeholder={locale === 'en' ? 'e.g. retain 7 years' : 'เช่น เก็บรักษา 7 ปี'}
                  className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs dark:border-slate-700 dark:bg-slate-900"
                />
              </label>

              {[
                ['decisions_supported', locale === 'en' ? 'Decisions supported (one per line)' : 'การตัดสินใจที่รองรับ (หนึ่งข้อต่อบรรทัด)'],
                ['inclusions', locale === 'en' ? 'Included scope (one per line)' : 'ขอบเขตที่รวม (หนึ่งข้อต่อบรรทัด)'],
                ['exclusions', locale === 'en' ? 'Excluded scope (one per line)' : 'ขอบเขตที่ไม่รวม (หนึ่งข้อต่อบรรทัด)'],
              ].map(([key, label]) => (
                <label key={key} className="sm:col-span-2">
                  <span className="mb-1 block text-[11px] font-semibold text-slate-700 dark:text-slate-200">{label}</span>
                  <textarea
                    value={(recipe.data_contract?.[key] || []).join('\n')}
                    onChange={(event) => updateDataContract(
                      key,
                      event.target.value.split('\n').map((item) => item.trim()).filter(Boolean),
                    )}
                    rows={2}
                    className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs dark:border-slate-700 dark:bg-slate-900"
                  />
                </label>
              ))}

              <label className="sm:col-span-2">
                <span className="mb-1 block text-[11px] font-semibold text-slate-700 dark:text-slate-200">
                  {locale === 'en' ? 'Known caveats (one per line)' : 'ข้อจำกัดที่ทราบ (หนึ่งข้อต่อบรรทัด)'}
                </span>
                <textarea
                  value={(recipe.data_contract?.known_caveats || []).join('\n')}
                  onChange={(event) => updateDataContract(
                    'known_caveats',
                    event.target.value.split('\n').map((item) => item.trim()).filter(Boolean),
                  )}
                  rows={3}
                  className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs dark:border-slate-700 dark:bg-slate-900"
                />
              </label>

              <label>
                <span className="mb-1 block text-[11px] font-semibold text-slate-700 dark:text-slate-200">
                  {locale === 'en' ? 'Known context or exceptions' : 'บริบทหรือข้อยกเว้นที่ทราบ'}
                </span>
                <input
                  type="text"
                  value={recipe.data_contract?.context_notes || ''}
                  onChange={(event) => updateDataContract('context_notes', event.target.value)}
                  placeholder={locale === 'en' ? 'e.g. Branch A closed for two days' : 'เช่น สาขา A ปิดสองวัน'}
                  maxLength={1000}
                  className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-800 outline-none focus:border-cyan-500 focus:ring-2 focus:ring-cyan-500/20 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
                />
              </label>

              <details className="sm:col-span-2 rounded-xl border border-violet-200 bg-violet-50/40 p-3 dark:border-violet-900/60 dark:bg-violet-950/10">
                <summary className="cursor-pointer text-xs font-semibold text-violet-800 dark:text-violet-200">
                  {locale === 'en' ? 'Optional causal study design' : 'แบบการศึกษาความเป็นเหตุเป็นผล (ไม่บังคับ)'}
                </summary>
                <p className="mt-2 text-[11px] leading-relaxed text-slate-500">
                  {locale === 'en'
                    ? 'Only use this to test whether a known campaign, policy, price change, or rollout may have changed an outcome. Ordinary sales summaries and dashboards do not need it. Blank or incomplete designs never run.'
                    : 'ใช้เมื่อต้องการทดสอบว่าแคมเปญ นโยบาย การเปลี่ยนราคา หรือการเริ่มใช้มาตรการที่ทราบวันชัดเจน อาจทำให้ผลลัพธ์เปลี่ยนหรือไม่ การสรุปยอดขายและสร้าง Dashboard ปกติไม่ต้องกรอก ถ้าข้อมูลไม่ครบระบบจะไม่รัน'}
                </p>
                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  {[
                    ['date_column', locale === 'en' ? 'Date column' : 'คอลัมน์วันที่'],
                    ['outcome_column', locale === 'en' ? 'Outcome metric column' : 'คอลัมน์ผลลัพธ์'],
                    ['treatment_column', locale === 'en' ? 'Treatment indicator column' : 'คอลัมน์กลุ่มทดลอง'],
                    ['group_column', locale === 'en' ? 'Group / entity column' : 'คอลัมน์กลุ่ม / หน่วย'],
                    ['treatment_value', locale === 'en' ? 'Treated value' : 'ค่าที่หมายถึงกลุ่มทดลอง'],
                    ['control_value', locale === 'en' ? 'Control value' : 'ค่าที่หมายถึงกลุ่มควบคุม'],
                  ].map(([key, label]) => (
                    <label key={key}>
                      <span className="mb-1 block text-[11px] font-medium text-slate-700 dark:text-slate-300">{label}</span>
                      <input
                        value={recipe.data_contract?.causal_design?.[key] || ''}
                        onChange={(event) => updateDataContract('causal_design', {
                          ...(recipe.data_contract?.causal_design || {}),
                          [key]: event.target.value,
                        })}
                        className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs dark:border-slate-700 dark:bg-slate-900"
                      />
                    </label>
                  ))}
                  <label>
                    <span className="mb-1 block text-[11px] font-medium text-slate-700 dark:text-slate-300">
                      {locale === 'en' ? 'Intervention date' : 'วันที่เริ่มมาตรการ'}
                    </span>
                    <input
                      type="date"
                      value={recipe.data_contract?.causal_design?.intervention_date || ''}
                      onChange={(event) => updateDataContract('causal_design', {
                        ...(recipe.data_contract?.causal_design || {}),
                        intervention_date: event.target.value,
                      })}
                      className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs dark:border-slate-700 dark:bg-slate-900"
                    />
                  </label>
                  {[
                    ['predictor_columns', locale === 'en' ? 'Predictor columns (comma separated)' : 'คอลัมน์ตัวทำนาย (คั่นด้วยจุลภาค)'],
                    ['known_confounders', locale === 'en' ? 'Known confounders (comma separated)' : 'ปัจจัยกวนที่ทราบ (คั่นด้วยจุลภาค)'],
                  ].map(([key, label]) => (
                    <label key={key}>
                      <span className="mb-1 block text-[11px] font-medium text-slate-700 dark:text-slate-300">{label}</span>
                      <input
                        value={(recipe.data_contract?.causal_design?.[key] || []).join(', ')}
                        onChange={(event) => updateDataContract('causal_design', {
                          ...(recipe.data_contract?.causal_design || {}),
                          [key]: event.target.value.split(',').map((item) => item.trim()).filter(Boolean),
                        })}
                        className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs dark:border-slate-700 dark:bg-slate-900"
                      />
                    </label>
                  ))}
                </div>
              </details>
                </div>
              </details>
            </div>

            {contractReadiness.missing.length > 0 && (
              <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] text-amber-800 dark:border-amber-900/50 dark:bg-amber-950/20 dark:text-amber-200">
                {locale === 'en' ? 'Still required: ' : 'ยังขาด: '}
                {contractReadiness.missing.join(', ')}
              </div>
            )}

            <label className="mt-3 flex items-start gap-2 rounded-lg border border-slate-200 bg-white/70 p-3 text-xs text-slate-700 dark:border-slate-700 dark:bg-slate-900/70 dark:text-slate-300">
              <input
                type="checkbox"
                checked={(recipe.data_contract?.enforcement_mode || 'warn') === 'strict'}
                onChange={(event) => updateDataContract('enforcement_mode', event.target.checked ? 'strict' : 'warn')}
                className="mt-0.5 accent-cyan-600"
              />
              <span>
                {locale === 'en'
                  ? 'Strict scheduled ETL: stop a run when this contract is incomplete, invalid, or a critical quality rule fails.'
                  : 'Scheduled ETL แบบเข้มงวด: หยุดการรันเมื่อ Contract ไม่ครบ ไม่ถูกต้อง หรือผิดกฎคุณภาพระดับ critical'}
              </span>
            </label>

            <label className="mt-3 flex items-start gap-2 rounded-lg border border-cyan-200 bg-white/70 p-3 text-xs text-slate-700 dark:border-cyan-900/60 dark:bg-slate-900/70 dark:text-slate-300">
              <input
                type="checkbox"
                checked={Boolean(recipe.data_contract?.business_context_reviewed)}
                onChange={(event) => updateDataContract('business_context_reviewed', event.target.checked)}
                className="mt-0.5 accent-cyan-600"
              />
              <span>
                {locale === 'en'
                  ? 'I am the data owner or I have confirmed these definitions with the responsible owner.'
                  : 'ฉันเป็นเจ้าของข้อมูล หรือได้ยืนยันนิยามเหล่านี้กับผู้รับผิดชอบข้อมูลแล้ว'}
              </span>
            </label>
          </section>

          <h4 className="text-sm font-semibold text-slate-900 dark:text-slate-100 mb-2">
            {locale === 'en' ? '3. Semantic mapping' : '3. Mapping ความหมายคอลัมน์'}
          </h4>
          <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed font-sans mb-4 px-1">
            {t(m, 'chat.mapping.modal_desc', 'Map each column to a semantic role to unlock domain KPIs and question-aware analytics.')}
          </p>

          <div className="rounded-xl border border-slate-200 dark:border-slate-800">
            <div className="hidden sm:grid sm:grid-cols-[minmax(0,1fr)_minmax(0,1.25fr)] gap-3 px-4 py-2.5 bg-slate-50 dark:bg-slate-900/60 border-b border-slate-200 dark:border-slate-800 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
              <span>{t(m, 'chat.mapping.column_header', 'Source column')}</span>
              <span>{t(m, 'chat.mapping.role_header', 'Semantic role')}</span>
            </div>

            <div className="divide-y divide-slate-100 dark:divide-slate-800">
              {headers.map((header) => {
                const formattedHeader = header.trim().replace(/[^a-zA-Z0-9_-]/g, '_');
                const isChecked = mapping[header] === formattedHeader;
                const currentValue = mapping[header] || '';
                const selectValue = getSelectValue(header, currentValue, isChecked);
                const suggested = suggestSemanticRole(header);
                const showCustom = selectValue === '__custom__';

                return (
                  <div
                    key={header}
                    className="grid grid-cols-1 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.25fr)] gap-2 sm:gap-3 px-4 py-3.5 hover:bg-slate-50/80 dark:hover:bg-slate-800/30 transition-colors"
                  >
                    <div className="min-w-0">
                      <code className="text-sm font-mono font-medium text-slate-800 dark:text-slate-100 break-all">
                        {header}
                      </code>
                      {suggested && currentValue === suggested && (
                        <span className="mt-1 inline-flex items-center text-[10px] font-medium text-[#d97706] bg-[#d97706]/10 px-1.5 py-0.5 rounded">
                          {t(m, 'chat.mapping.auto_detected', 'Auto-detected')}
                        </span>
                      )}
                    </div>

                    <div className="flex flex-col gap-2 min-w-0">
                      <MappingRoleSelect
                        value={selectValue}
                        onChange={(val) => handleRoleSelect(header, val, formattedHeader)}
                        optionGroups={options}
                        m={m}
                      />

                      {showCustom && (
                        <input
                          type="text"
                          value={currentValue}
                          placeholder={t(m, 'chat.mapping.custom_input_placeholder', 'Enter custom English name')}
                          onChange={(e) => {
                            const val = e.target.value.replace(/[^a-zA-Z0-9_-]/g, '');
                            setMapping({ ...mapping, [header]: val });
                          }}
                          className="w-full px-3 py-2 bg-white dark:bg-slate-900 border border-dashed border-slate-300 dark:border-slate-600 focus:border-[#d97706] rounded-lg text-sm font-mono outline-none focus:ring-2 focus:ring-[#d97706]/20 text-slate-700 dark:text-slate-200"
                        />
                      )}

                      {currentValue && (
                        <details className="rounded-lg border border-slate-200 bg-slate-50/60 px-3 py-2 dark:border-slate-700 dark:bg-slate-950/30">
                          <summary className="cursor-pointer text-[10px] font-semibold text-slate-500">
                            {locale === 'en' ? 'Business definition & governance' : 'นิยามธุรกิจและการกำกับข้อมูล'}
                          </summary>
                          <div className="mt-3 grid gap-2 sm:grid-cols-2">
                            <input
                              value={recipe.data_contract?.column_contracts?.[header]?.business_name || ''}
                              onChange={(event) => updateColumnContract(header, 'business_name', event.target.value)}
                              placeholder={locale === 'en' ? 'Business name' : 'ชื่อที่ใช้ในธุรกิจ'}
                              maxLength={300}
                              className="rounded-md border border-slate-200 bg-white px-2.5 py-2 text-xs dark:border-slate-700 dark:bg-slate-900"
                            />
                            <input
                              value={recipe.data_contract?.column_contracts?.[header]?.unit || ''}
                              onChange={(event) => updateColumnContract(header, 'unit', event.target.value)}
                              placeholder={locale === 'en' ? 'Unit, e.g. THB' : 'หน่วย เช่น THB'}
                              maxLength={80}
                              className="rounded-md border border-slate-200 bg-white px-2.5 py-2 text-xs dark:border-slate-700 dark:bg-slate-900"
                            />
                            <textarea
                              value={recipe.data_contract?.column_contracts?.[header]?.description || ''}
                              onChange={(event) => updateColumnContract(header, 'description', event.target.value)}
                              placeholder={locale === 'en' ? 'Exact definition and calculation scope' : 'นิยามที่ชัดเจนและขอบเขตการคำนวณ'}
                              rows={2}
                              maxLength={1000}
                              className="sm:col-span-2 rounded-md border border-slate-200 bg-white px-2.5 py-2 text-xs dark:border-slate-700 dark:bg-slate-900"
                            />
                            <select
                              value={recipe.data_contract?.column_contracts?.[header]?.aggregation || 'none'}
                              onChange={(event) => updateColumnContract(header, 'aggregation', event.target.value)}
                              className="rounded-md border border-slate-200 bg-white px-2.5 py-2 text-xs dark:border-slate-700 dark:bg-slate-900"
                            >
                              <option value="none">{locale === 'en' ? 'No default aggregation' : 'ไม่กำหนดการรวม'}</option>
                              <option value="sum">SUM</option>
                              <option value="avg">AVERAGE</option>
                              <option value="min">MIN</option>
                              <option value="max">MAX</option>
                              <option value="count">COUNT</option>
                              <option value="count_distinct">COUNT DISTINCT</option>
                            </select>
                            <select
                              value={recipe.data_contract?.column_contracts?.[header]?.sensitivity || 'none'}
                              onChange={(event) => updateColumnContract(header, 'sensitivity', event.target.value)}
                              className="rounded-md border border-slate-200 bg-white px-2.5 py-2 text-xs dark:border-slate-700 dark:bg-slate-900"
                            >
                              <option value="none">{locale === 'en' ? 'Not sensitive' : 'ไม่ใช่ข้อมูลอ่อนไหว'}</option>
                              <option value="personal">{locale === 'en' ? 'Personal data' : 'ข้อมูลส่วนบุคคล'}</option>
                              <option value="sensitive">{locale === 'en' ? 'Sensitive data' : 'ข้อมูลอ่อนไหว'}</option>
                              <option value="restricted">{locale === 'en' ? 'Restricted' : 'จำกัดสิทธิ์สูงสุด'}</option>
                            </select>
                            <label className="flex items-center gap-2 text-[11px] text-slate-600 dark:text-slate-300">
                              <input
                                type="checkbox"
                                checked={Boolean(recipe.data_contract?.column_contracts?.[header]?.required)}
                                onChange={(event) => updateColumnContract(header, 'required', event.target.checked)}
                              />
                              {locale === 'en' ? 'Required / must not be null' : 'จำเป็น / ห้ามเป็นค่าว่าง'}
                            </label>
                            <label className="flex items-center gap-2 text-[11px] text-slate-600 dark:text-slate-300">
                              <input
                                type="checkbox"
                                checked={Boolean(recipe.data_contract?.column_contracts?.[header]?.unique)}
                                onChange={(event) => updateColumnContract(header, 'unique', event.target.checked)}
                              />
                              {locale === 'en' ? 'Expected unique' : 'คาดว่าต้องไม่ซ้ำ'}
                            </label>
                          </div>
                        </details>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        <footer className="p-6 bg-slate-50 dark:bg-slate-900/50 border-t border-slate-200 dark:border-slate-800 flex gap-3">
          <button
            onClick={onClose}
            className="flex-1 py-3 btn-secondary text-sm"
          >
            {t(m, 'chat.cancel', 'Cancel')}
          </button>
          <button
            onClick={handleConfirm}
            disabled={contractReadiness.blocking}
            title={contractReadiness.blocking
              ? (locale === 'en' ? 'Complete the required mapping and contract fields first.' : 'กรอก Mapping และ Contract ที่จำเป็นให้ครบก่อน')
              : undefined}
            className="flex-[2] py-3 btn-primary text-sm disabled:cursor-not-allowed disabled:opacity-50"
          >
            {t(m, 'chat.mapping.confirm', 'Confirm & start analysis')}
          </button>
        </footer>
      </div>
    </div>
  );
};

export const QuotaExceededModal = ({
  isOpen,
  onClose,
  onUpgrade,
  message,
  used,
  limit,
  resetAt,
  resetAtLabel,
  closeLabel,
  upgradeLabel,
  title,
}) => {
  if (!isOpen) return null;
  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center p-4">
      <div className="fixed inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />
      <div className="app-modal relative w-full max-w-md overflow-hidden p-8">
        <div className="flex flex-col items-center text-center">
          <div className="w-14 h-14 bg-amber-50 dark:bg-amber-950/20 text-[#d97706] rounded-lg flex items-center justify-center mb-6 border border-amber-200 dark:border-amber-900/40">
            <CircleAlert className="w-7 h-7" strokeWidth={1.5} />
          </div>
          <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100 mb-2">{title}</h3>
          <p className="text-sm text-slate-600 dark:text-slate-400 font-sans mb-4 leading-relaxed">{message}</p>
          {used != null && limit != null && (
            <p className="text-xs font-mono text-slate-500 dark:text-slate-400 mb-2 tabular-nums">
              {used.toLocaleString()} / {limit.toLocaleString()}
            </p>
          )}
          {resetAt ? (
            <p className="text-xs text-slate-500 dark:text-slate-400 mb-6">
              {resetAtLabel}: <span className="font-semibold text-slate-700 dark:text-slate-200">{resetAt}</span>
            </p>
          ) : (
            <div className="mb-6" />
          )}
          <div className="flex gap-3 w-full">
            <button onClick={onClose} className="flex-1 py-3 btn-secondary text-sm">
              {closeLabel}
            </button>
            <button onClick={onUpgrade} className="flex-1 py-3 btn-primary text-sm">
              {upgradeLabel}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export const DeleteConfirmationModal = ({
  isOpen,
  onClose,
  onConfirm,
  title,
  message,
  subject,
  confirmButtonText = 'Confirm',
  cancelButtonText = 'Cancel',
  isLoading = false,
  tone = 'danger',
  icon = 'trash',
}) => {
  const cancelRef = useRef(null);
  const isWarning = tone === 'warning';
  const Icon = icon === 'alert' ? TriangleAlert : Trash2;

  useEffect(() => {
    if (!isOpen) return undefined;
    const frame = window.requestAnimationFrame(() => cancelRef.current?.focus());
    const onKeyDown = (event) => {
      if (event.key === 'Escape' && !isLoading) onClose();
    };
    document.addEventListener('keydown', onKeyDown);
    return () => {
      window.cancelAnimationFrame(frame);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [isOpen, isLoading, onClose]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[1000] flex items-center justify-center p-4">
      <div
        className="fixed inset-0 bg-slate-950/30 dark:bg-black/55"
        onClick={() => !isLoading && onClose()}
        aria-hidden="true"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="delete-confirm-title"
        aria-describedby="delete-confirm-desc"
        className="app-modal relative z-10 w-full max-w-md overflow-hidden rounded-2xl border border-slate-200 bg-white p-5 shadow-[0_24px_64px_rgba(15,23,42,0.18)] sm:p-6 dark:border-slate-700 dark:bg-slate-900 dark:shadow-[0_24px_64px_rgba(2,6,23,0.5)]"
      >
        <div className="flex gap-3.5 text-left">
          <div
            className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${
              isWarning
                ? 'bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300'
                : 'bg-red-50 text-red-600 dark:bg-red-950/45 dark:text-red-400'
            }`}
          >
            <Icon className="h-5 w-5" strokeWidth={1.75} aria-hidden />
          </div>
          <div className="min-w-0 flex-1 pt-0.5">
            <h3
              id="delete-confirm-title"
              className="text-base font-semibold tracking-tight text-slate-900 dark:text-slate-100"
            >
              {title}
            </h3>
            {subject ? (
              <p
                className="mt-1 truncate text-sm font-semibold text-slate-800 dark:text-slate-200"
                title={subject}
              >
                “{subject}”
              </p>
            ) : null}
            <p
              id="delete-confirm-desc"
              className="mt-2 text-sm leading-relaxed text-slate-500 dark:text-slate-400"
            >
              {message}
            </p>
          </div>
        </div>

        <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end sm:gap-2.5">
          <button
            ref={cancelRef}
            type="button"
            onClick={onClose}
            disabled={isLoading}
            className="inline-flex min-h-10 items-center justify-center rounded-xl border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 transition-colors hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            {cancelButtonText}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={isLoading}
            className={`inline-flex min-h-10 items-center justify-center gap-2 rounded-xl px-4 text-sm font-semibold text-white transition-colors disabled:cursor-wait disabled:opacity-70 ${
              isWarning
                ? 'bg-amber-600 hover:bg-amber-700 dark:bg-amber-600 dark:hover:bg-amber-500'
                : 'bg-red-600 hover:bg-red-700 dark:bg-red-600 dark:hover:bg-red-500'
            }`}
          >
            {isLoading && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
            {confirmButtonText}
          </button>
        </div>
      </div>
    </div>
  );
};

const ChatModals = {
  FileSelectionModal,
  DeleteConfirmationModal
};

export default ChatModals;
