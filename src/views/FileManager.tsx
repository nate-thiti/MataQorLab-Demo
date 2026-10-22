// @ts-nocheck
'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { supabase } from '../utils/supabaseClient.js';
import { useRouter, usePathname, useParams, useSearchParams } from 'next/navigation';
import Papa from 'papaparse';
import readXlsxFile from 'read-excel-file/browser';
import { useLocaleRouting } from '../context/LocaleRoutingContext';
import { buildFilesPath, parseFilesRoute } from '../utils/dashboardRoutes.js';
import { localePath } from '../utils/locale.js';
import { getMessages, t } from '../utils/i18n.js';
import DashboardSidebar from '../components/DashboardSidebar';
import { useFileManagerCache } from '../context/FileManagerCacheContext';
import { useAppSidebar } from '../context/AppSidebarContext';
import { DeleteConfirmationModal } from '../components/ChatModals';
import DatabaseConnectView from '../components/DatabaseConnectView';
import ApiConnectView from '../components/ApiConnectView';
import CloudDatasetView from '../components/CloudDatasetView';
import ScheduledEtlView from '../components/ScheduledEtlView';
import { getDisplayName } from '../utils/fileDisplay';
import { getE2eMockUser } from '../utils/e2eAuth.js';
import { authFetch, getAuthHeaders } from '../utils/authFetch.js';
import { getPublicApiUrl } from '../utils/env.js';
import { fetchFilePage } from '../utils/fileListApi.js';
import {
  FileManagerHeader,
  UploadProgressBar,
  FileList,
  DataPreviewModal,
  LoadingOverlay,
  SuccessPopup
} from '../components/FileComponents';

// Helper function to sanitize file names for storage while preserving multilingual names.
const sanitizeFileName = (fileName) => {
  const lastDotIndex = fileName.lastIndexOf('.');
  const namePart = lastDotIndex !== -1 ? fileName.substring(0, lastDotIndex) : fileName;
  const extPart = lastDotIndex !== -1 ? fileName.substring(lastDotIndex) : '';

  const cleanName = namePart.trim()
    .normalize('NFC') 
    .replace(/\s+/g, '_')
    .replace(/[^\p{L}\p{M}\p{N}.\-_]/gu, '')
    .replace(/_{2,}/g, '_')
    .replace(/^[._-]+|[._-]+$/g, '');

  return `${cleanName || 'file'}${extPart}`;
};

const scoreExcelHeaderRow = (row, nextRow) => {
  const values = (row || []).filter((value) => value !== null && value !== undefined && String(value).trim());
  if (!values.length) return -1;
  const labels = values.map((value) => String(value).trim());
  const uniqueRatio = new Set(labels).size / labels.length;
  const textRatio = labels.filter((value) => /[\p{L}_]/u.test(value)).length / labels.length;
  const nextValues = (nextRow || []).filter((value) => value !== null && value !== undefined && String(value).trim());
  return labels.length * 2 + uniqueRatio * 3 + textRatio * 2 + (nextValues.length >= Math.max(1, Math.floor(labels.length / 2)) ? 2 : 0);
};

const detectExcelHeaderRow = (rows) => {
  let bestIdx = 0;
  let bestScore = -1;
  (rows || []).slice(0, 25).forEach((row, idx) => {
    const score = scoreExcelHeaderRow(row, rows[idx + 1]);
    if (score > bestScore) {
      bestScore = score;
      bestIdx = idx;
    }
  });
  return bestIdx;
};

const scoreExcelSheet = (matrix) => {
  const rows = (matrix || []).filter((row) =>
    (row || []).some((value) => value !== null && value !== undefined && String(value).trim())
  );
  if (!rows.length) return -1;
  const headerRow = detectExcelHeaderRow(matrix);
  const nonEmptyCells = rows.reduce(
    (count, row) => count + row.filter((value) => value !== null && value !== undefined && String(value).trim()).length,
    0
  );
  return scoreExcelHeaderRow(matrix[headerRow], matrix[headerRow + 1]) + Math.min(rows.length, 10) * 2 + Math.min(nonEmptyCells, 80) * 0.1;
};

const selectWorkbookSheet = (workbook) => {
  let bestSheet = workbook[0];
  let bestScore = -1;
  workbook.forEach((sheet) => {
    const score = scoreExcelSheet(sheet.data);
    if (score > bestScore) {
      bestScore = score;
      bestSheet = sheet;
    }
  });
  return bestSheet;
};

const rowsFromExcelMatrix = (matrix, headerRow) => {
  const headers = (matrix?.[headerRow] || []).map((value, index) => (
    value !== null && value !== undefined && String(value).trim()
      ? String(value).trim()
      : `col_${index}`
  ));
  return (matrix || []).slice(headerRow + 1).map((row) => Object.fromEntries(
    headers.map((header, index) => [header, row?.[index] ?? null]),
  ));
};

const DEFAULT_FILE_PLAN = { name: 'Free', storage_limit_mb: 1 };

const FileManager = () => {
  const [files, setFiles] = useState<any[]>([]);
  const [nextFileOffset, setNextFileOffset] = useState<number | null>(null);
  const [loadingMoreFiles, setLoadingMoreFiles] = useState(false);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [user, setUser] = useState<any>(null);
  const router = useRouter();
  const fileManagerCache = useFileManagerCache();
  const pathname = usePathname();
  const params = useParams();
  const searchParams = useSearchParams();
  const routing = useLocaleRouting();
  const previewFromUrlRef = useRef(null);
  const internalFilesNavigationRef = useRef(false);
  const isEn = routing.locale === 'en';
  const m = getMessages(routing.locale);
  const { isOpen: isSidebarOpen, setIsOpen: setIsSidebarOpen } = useAppSidebar();
  const [plan, setPlan] = useState<any>(null);
  const [isPlanLoading, setIsPlanLoading] = useState(true);
  const [totalSize, setTotalSize] = useState(0); // เก็บขนาดไฟล์รวมทั้งหมด
  const [activeView, setActiveView] = useState('files');
  const [filter, setFilter] = useState('all');

  // States สำหรับ Custom Popups
  const [deleteModal, setDeleteConfirm] = useState({ show: false, fileName: null });
  const [showSuccess, setShowSuccess] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [errorMessage, setErrorMessage] = useState("");
  const [isDragging, setIsDragging] = useState(false);

  // States สำหรับ Data Preview
  const [previewModal, setPreviewModal] = useState({ show: false, data: null, type: null, fileName: null });
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  const effectivePlan = plan || DEFAULT_FILE_PLAN;

  const fetchPlanInfo = useCallback(async (userId, { showLoading = true } = {}) => {
    if (showLoading) setIsPlanLoading(true);
    try {
      const { data: profileData } = await supabase
        .from('profiles')
        .select(`plans ( name, storage_limit_mb )`)
        .eq('id', userId)
        .single();
  
      if (profileData?.plans) {
        const planData = Array.isArray(profileData.plans) ? profileData.plans[0] : profileData.plans;
        const nextPlan = planData || DEFAULT_FILE_PLAN;
        setPlan(nextPlan);
        fileManagerCache.setPlan(userId, { plan: nextPlan });
      } else {
        setPlan(DEFAULT_FILE_PLAN);
        fileManagerCache.setPlan(userId, { plan: DEFAULT_FILE_PLAN });
      }
    } catch (err: any) {
      console.error('Error fetching plan info:', err);
      setPlan(DEFAULT_FILE_PLAN);
      fileManagerCache.setPlan(userId, { plan: DEFAULT_FILE_PLAN });
    } finally {
      setIsPlanLoading(false);
    }
  }, [fileManagerCache]);

  const fetchFiles = useCallback(async (userId, { showLoading = true } = {}) => {
    if (showLoading) setLoading(true);
    try {
      if (!userId) {
        setLoading(false);
        return;
      }
      const [filePage, usageResponse] = await Promise.all([
        fetchFilePage({ limit: 100 }),
        authFetch(`${getPublicApiUrl()}/api/v1/files/storage-usage`, { method: 'GET' }),
      ]);

      setFiles(filePage.files);
      setNextFileOffset(filePage.nextOffset);

      const usage = usageResponse.ok ? await usageResponse.json() : {};
      const size = Number(usage.used_bytes || 0);
      setTotalSize(size);
      fileManagerCache.setFiles(userId, {
        files: filePage.files,
        totalSize: size,
        nextOffset: filePage.nextOffset,
      });

    } catch (error: any) {
      if (showLoading) setFiles([]);
      console.error('Error fetching files:', error.message);
    } finally {
      setLoading(false);
    }
  }, [fileManagerCache]);

  const loadMoreFiles = useCallback(async () => {
    if (nextFileOffset === null || loadingMoreFiles) return;
    setLoadingMoreFiles(true);
    try {
      const page = await fetchFilePage({ limit: 100, offset: nextFileOffset });
      setFiles((current) => {
        const known = new Set(current.map((file) => file.name));
        const merged = [...current, ...page.files.filter((file) => !known.has(file.name))];
        if (user?.id) {
          fileManagerCache.setFiles(user.id, {
            files: merged,
            totalSize,
            nextOffset: page.nextOffset,
          });
        }
        return merged;
      });
      setNextFileOffset(page.nextOffset);
    } catch (error: any) {
      setErrorMessage(error.message);
    } finally {
      setLoadingMoreFiles(false);
    }
  }, [fileManagerCache, loadingMoreFiles, nextFileOffset, totalSize, user]);

  useEffect(() => {
    let cancelled = false;

    const checkUser = async () => {
      const e2eUser = getE2eMockUser();
      if (e2eUser) {
        if (!cancelled) setUser(e2eUser);
        return;
      }
      const cachedAuth = fileManagerCache.getAuthUser();
      if (cachedAuth?.user) {
        setUser(cachedAuth.user);
        if (cachedAuth.isFresh) return;
      }
      const { data: { user } } = await supabase.auth.getUser();
      if (cancelled) return;
      if (!user) {
        router.push(localePath('/login', routing));
        return;
      }
      setUser(user);
      fileManagerCache.setAuthUser(user);
    };

    checkUser();
    return () => {
      cancelled = true;
    };
  }, [fileManagerCache, router, routing]);

  useEffect(() => {
    if (!user?.id) return undefined;

    const userId = user.id;
    let cancelled = false;
    const cachedFiles = fileManagerCache.getFiles(userId);
    const cachedPlan = fileManagerCache.getPlan(userId);

    if (cachedFiles) {
      setFiles(cachedFiles.files || []);
      setTotalSize(cachedFiles.totalSize || 0);
      setNextFileOffset(cachedFiles.nextOffset ?? null);
      setLoading(false);
    } else {
      setFiles([]);
      setTotalSize(0);
      setLoading(true);
    }

    if (cachedPlan) {
      setPlan(cachedPlan.plan || DEFAULT_FILE_PLAN);
      setIsPlanLoading(false);
    } else {
      setPlan(null);
      setIsPlanLoading(true);
    }

    void (async () => {
      if (!cachedFiles || !cachedFiles.isFresh) {
        await fetchFiles(userId, { showLoading: !cachedFiles });
      }
      if (cancelled) return;
      if (!cachedPlan || !cachedPlan.isFresh) {
        await fetchPlanInfo(userId, { showLoading: !cachedPlan });
      }
    })();

    const channelName = `file-manager-plan-${userId}`;
    supabase
      .getChannels()
      .filter((ch) => ch.topic === `realtime:${channelName}`)
      .forEach((ch) => {
        supabase.removeChannel(ch);
      });

    const channel = supabase
      .channel(channelName)
      .on(
        'postgres_changes',
        {
          event: 'UPDATE',
          schema: 'public',
          table: 'profiles',
          filter: `id=eq.${userId}`,
        },
        () => fetchPlanInfo(userId, { showLoading: false }),
      )
      .subscribe();

    return () => {
      cancelled = true;
      supabase.removeChannel(channel);
    };
  }, [user?.id, fetchFiles, fetchPlanInfo, fileManagerCache]);

  const uploadFile = async (file) => {
    const maxStorageBytes = effectivePlan.storage_limit_mb * 1024 * 1024;
    const maxExcelBytes = 25 * 1024 * 1024;
    const maxUploadBytes = 500 * 1024 * 1024;

    try {
      setUploading(true);
      setUploadProgress(0);
      setErrorMessage("");

      if (file.size > maxUploadBytes) {
        throw new Error(t(m, 'file_manager.upload_too_large'));
      }

      if (file.name.toLowerCase().endsWith('.parquet') && (effectivePlan?.name === 'Free' || !effectivePlan?.name)) {
        throw new Error(t(m, 'file_manager.parquet_locked'));
      }

      const lowerName = file.name.toLowerCase();
      if ((lowerName.endsWith('.xlsx') || lowerName.endsWith('.xls')) && file.size > maxExcelBytes) {
        throw new Error(t(m, 'file_manager.excel_too_large'));
      }

      if (effectivePlan && totalSize + file.size > maxStorageBytes) {
        throw new Error(t(m, 'file_manager.insufficient_storage'));
      }

      const isDuplicate = files.some(f => {
        const existingName = getDisplayName(f.name).normalize('NFC');
        const currentName = file.name.normalize('NFC');
        return existingName === currentName;
      });

      if (isDuplicate) {
        throw new Error(t(
          m,
          'file_manager.duplicate_file',
          'A file named "{file}" already exists. Delete the existing file before uploading a new version.',
          { file: file.name },
        ));
      }

      const backendUrl = getPublicApiUrl();
      const form = new FormData();
      form.append('file', file, sanitizeFileName(file.name));
      const headers = await getAuthHeaders();
      delete headers['Content-Type'];
      setUploadProgress(35);
      const uploadResponse = await fetch(`${backendUrl}/api/v1/files/upload`, {
        method: 'POST',
        headers,
        body: form,
      });
      const uploadPayload = await uploadResponse.json().catch(() => ({}));
      if (!uploadResponse.ok) {
        throw new Error(uploadPayload.detail || t(m, 'file_manager.upload_rejected'));
      }
      setUploadProgress(100);
      const storageFileName = uploadPayload.file_name;
      authFetch(`${backendUrl}/api/v1/files/warm-ingest-cache`, {
        body: { user_id: user.id, file_name: storageFileName, size_bytes: file.size },
      }).catch(() => {});

      fetchFiles(user.id, { showLoading: false });
      setShowSuccess(true);
      setTimeout(() => setShowSuccess(false), 3000);
    } catch (error: any) {
      setErrorMessage(error.message);
    } finally {
      setUploading(false);
      setUploadProgress(0);
    }
  };

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (file) uploadFile(file);
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const file = e.dataTransfer.files[0];
      const fileName = file.name.toLowerCase();
      if (fileName.endsWith('.csv') || fileName.endsWith('.json') || fileName.endsWith('.xlsx') || fileName.endsWith('.xls') || fileName.endsWith('.parquet')) {
        uploadFile(file);
      } else {
        setErrorMessage(isEn ? "Only .csv, .json, .xlsx, .xls and .parquet are supported." : "รองรับเฉพาะไฟล์ .csv, .json, .xlsx, .xls และ .parquet เท่านั้น");
      }
    }
  };

  const handleDownload = async (fileName) => {
    try {
      if (!user?.id) {
        setErrorMessage(isEn ? "User session not found. Please sign in again." : "ไม่พบข้อมูลผู้ใช้งาน กรุณาเข้าสู่ระบบใหม่");
        return;
      }

      const { data, error } = await supabase.storage
        .from('business-data')
        .createSignedUrl(`${user.id}/${fileName}`, 600);

      if (error) throw error;

      window.open(data.signedUrl, '_blank');
    } catch (error: any) {
      setErrorMessage("สร้างลิงก์สำหรับเข้าถึงไฟล์ไม่สำเร็จ: " + error.message);
    }
  };
  
  const parseFileContent = useCallback(async (fileName) => {
    try {
      setIsPreviewLoading(true);
      setErrorMessage("");
      
      const { data: signedData, error: signedError } = await supabase.storage
        .from('business-data')
        .createSignedUrl(`${user.id}/${fileName}`, 600);

      if (signedError) throw signedError;
  
      const ext = fileName.split('.').pop().toLowerCase();
      let parsedData = null;

      if (ext === 'json') {
        const response = await fetch(signedData.signedUrl);
        if (!response.ok) throw new Error("ไม่สามารถดาวน์โหลดเนื้อหาไฟล์ได้");
        parsedData = await response.json();
      } else if (ext === 'csv') {
        const response = await fetch(signedData.signedUrl);
        if (!response.ok) throw new Error("ไม่สามารถดาวน์โหลดเนื้อหาไฟล์ได้");
        const arrayBuffer = await response.arrayBuffer();
        let decoder = new TextDecoder('utf-8');
        let text = decoder.decode(arrayBuffer);
        
        if (text.includes('')) {
          decoder = new TextDecoder('windows-874');
          text = decoder.decode(arrayBuffer);
        }

        const result = Papa.parse(text, { header: true, skipEmptyLines: true });
        parsedData = result.data;
      } else if (ext === 'xlsx' || ext === 'xls') {
        const response = await fetch(signedData.signedUrl);
        if (!response.ok) throw new Error("ไม่สามารถดาวน์โหลดเนื้อหาไฟล์ได้");
        const arrayBuffer = await response.arrayBuffer();
        const workbook = await readXlsxFile(arrayBuffer);
        const worksheet = selectWorkbookSheet(workbook);
        if (!worksheet) throw new Error("ไม่พบชีตในไฟล์ Excel");
        const matrix = worksheet.data;
        parsedData = rowsFromExcelMatrix(matrix, detectExcelHeaderRow(matrix));
      } else if (ext === 'parquet') {
        const backendUrl = getPublicApiUrl();

        const res = await authFetch(`${backendUrl}/api/preview-parquet`, {
          body: { url: signedData.signedUrl },
        });
        
        if (!res.ok) {
          throw new Error(isEn ? "Failed to parse Parquet on server." : "เซิร์ฟเวอร์ไม่สามารถแปลงไฟล์ Parquet ได้");
        }
        const jsonRes = await res.json();
        parsedData = jsonRes.data;
      }

      return { data: parsedData, type: ext, displayName: getDisplayName(fileName) };
    } catch (err: any) {
      console.error("Error parsing file content:", err);
      throw new Error(`ไม่สามารถดึงข้อมูลตัวอย่างได้: ${err.message}`, { cause: err });
    } finally {
      setIsPreviewLoading(false);
    }
  }, [user, isEn]);

  const handlePreview = useCallback(async (fileName, { updateUrl = true } = {}) => {
    try {
      if (updateUrl) {
        router.push(buildFilesPath(routing, { view: 'files', filter, previewFile: fileName }));
      }
      const { data, type, displayName } = await parseFileContent(fileName);
      setPreviewModal({ show: true, data, type, fileName: displayName, storageName: fileName });
    } catch (error: any) {
      console.error("Preview error:", error);
      setErrorMessage(error.message);
    }
  }, [filter, router, parseFileContent, routing]);

  const closePreview = useCallback(() => {
    setPreviewModal({ show: false, data: null, type: null, fileName: null, storageName: null });
    previewFromUrlRef.current = null;
    router.replace(buildFilesPath(routing, { view: activeView, filter }));
  }, [router, routing, activeView, filter]);

  const syncFilesUrl = useCallback(
    ({ view, filter: nextFilter, previewFile } = {}) => {
      const nextUrl = buildFilesPath(routing, {
        view: view ?? activeView,
        filter: nextFilter ?? filter,
        previewFile,
      });

      if (typeof window !== 'undefined') {
        window.history.replaceState(window.history.state, '', nextUrl);
        return;
      }

      router.replace(nextUrl);
    },
    [router, routing, activeView, filter],
  );

  const applyFilesNavigation = useCallback(
    (view, nextFilter) => {
      internalFilesNavigationRef.current = true;
      setActiveView(view);
      setFilter(nextFilter);
      syncFilesUrl({ view, filter: nextFilter, previewFile: null });
    },
    [syncFilesUrl],
  );

  useEffect(() => {
    if (internalFilesNavigationRef.current) {
      internalFilesNavigationRef.current = false;
      return;
    }

    const parsed = parseFilesRoute(pathname, routing.localePrefix);
    const urlFilter = searchParams.get('filter') || parsed.filter || 'all';

    if (parsed.view === 'cloud') setActiveView('cloud');
    else if (parsed.view === 'schedules') setActiveView('schedules');
    else if (parsed.view === 'sql') setActiveView('sql');
    else if (parsed.view === 'api') setActiveView('api');
    else setActiveView('files');

    setFilter(urlFilter);

    const previewName = params.fileName
      ? decodeURIComponent(params.fileName)
      : parsed.previewFile;
    if (previewName && user && previewFromUrlRef.current !== previewName) {
      previewFromUrlRef.current = previewName;
      void handlePreview(previewName, { updateUrl: false });
    }
  }, [handlePreview, pathname, params.fileName, searchParams, routing.localePrefix, user]);

  const filteredFiles = filter === 'all' 
    ? files 
    : files.filter(file => {
        const fileName = file.name.toLowerCase();
        if (filter === 'excel') {
          return fileName.endsWith('.xlsx') || fileName.endsWith('.xls');
        }
        return fileName.endsWith(`.${filter}`);
      });

  const confirmDelete = useCallback(async () => {
    const fileName = deleteModal.fileName;
    try {
      const { error } = await supabase.storage
        .from('business-data')
        .remove([`${user.id}/${fileName}`]);

      if (error) throw error;

      const nextFiles = files.filter(f => f.name !== fileName);
      const nextTotalSize = nextFiles.reduce((acc, file) => acc + (file.metadata?.size || 0), 0);
      setFiles(nextFiles);
      setTotalSize(nextTotalSize);
      fileManagerCache.setFiles(user.id, { files: nextFiles, totalSize: nextTotalSize });
      setDeleteConfirm({ show: false, fileName: null });
      fetchFiles(user.id, { showLoading: false });
    } catch (error: any) {
      setErrorMessage(error.message);
      setDeleteConfirm({ show: false, fileName: null });
    }
  }, [deleteModal.fileName, user, files, fetchFiles, fileManagerCache]);

  return (
    <div className="app-shell icon-motion-scope relative flex h-[100svh] overflow-hidden bg-slate-50 text-slate-700 dark:bg-zinc-950 dark:text-zinc-300 font-sans">
      {/* Mobile Backdrop */}
      {isSidebarOpen && (
        <div 
          className="fixed inset-0 bg-black/20 dark:bg-black/60 backdrop-blur-sm z-40 md:hidden"
          onClick={() => setIsSidebarOpen(false)}
        />
      )}

      <DashboardSidebar
        isOpen={isSidebarOpen}
        setIsOpen={setIsSidebarOpen}
        user={user}
        plan={effectivePlan}
        routing={routing}
        isEn={isEn}
        onLogout={async () => {
          if (user?.id) fileManagerCache.clearUser(user.id);
          fileManagerCache.clearAuthUser();
          await supabase.auth.signOut();
          router.replace(localePath('/login', routing));
        }}
        fileMenu={{
          filter,
          activeView,
          filesCount: files.length,
          totalSize,
          plan: effectivePlan,
          setFilter: applyFilesNavigation,
          setActiveView: (view) => applyFilesNavigation(view, filter),
        }}
      />

      {/* Main Content */}
      <main className="min-w-0 flex-1 flex flex-col overflow-hidden">
        <FileManagerHeader
          isEn={isEn}
          handleFileChange={handleFileChange}
          uploading={uploading}
          activeView={activeView}
        />

        <UploadProgressBar
          uploading={uploading}
          uploadProgress={uploadProgress}
          isEn={isEn}
        />

        {errorMessage && (
          <div className="border-b border-red-200 dark:border-red-900/30 bg-red-50 dark:bg-red-950/20 px-5 md:px-8 py-3">
            <div className="app-page-frame mx-auto w-full max-w-[1180px] flex items-start justify-between gap-3">
              <p className="text-sm text-red-600 dark:text-red-400">{errorMessage}</p>
              <button
                type="button"
                onClick={() => setErrorMessage('')}
                className="shrink-0 p-1 rounded-md text-red-400 hover:text-red-600 dark:hover:text-red-300"
                aria-label={isEn ? 'Dismiss error' : 'ปิดข้อความผิดพลาด'}
              >
                <span className="text-lg leading-none">×</span>
              </button>
            </div>
          </div>
        )}

        <div
          className={`relative flex-1 overflow-y-auto no-scrollbar p-5 md:p-8 transition-colors duration-200 ${
            isDragging && activeView === 'files' ? 'bg-amber-50/40 dark:bg-amber-500/5' : ''
          }`}
          onDragOver={activeView === 'files' ? handleDragOver : undefined}
          onDragLeave={activeView === 'files' ? handleDragLeave : undefined}
          onDrop={activeView === 'files' ? handleDrop : undefined}
        >
          {isDragging && activeView === 'files' && (
            <div className="pointer-events-none absolute inset-4 z-10 rounded-2xl border-2 border-dashed border-[#d97706]/50 bg-amber-50/70 dark:bg-amber-500/10 flex items-center justify-center">
              <p className="text-sm font-semibold text-[#d97706]">
                {isEn ? 'Drop to upload now' : 'ปล่อยเพื่ออัปโหลดทันที'}
              </p>
            </div>
          )}
          <div className="app-page-frame mx-auto w-full max-w-[1180px]">
            {activeView === 'files' && (
              <>
                <FileList
                  loading={loading}
                  files={files}
                  filteredFiles={filteredFiles}
                  isDragging={isDragging}
                  filter={filter}
                  setFilter={(nextFilter) => applyFilesNavigation('files', nextFilter)}
                  isEn={isEn}
                  handlePreview={handlePreview}
                  handleDownload={handleDownload}
                  setDeleteConfirm={setDeleteConfirm}
                  isPreviewLoading={isPreviewLoading}
                />
                {nextFileOffset !== null && (
                  <div className="mt-5 flex justify-center">
                    <button
                      type="button"
                      onClick={loadMoreFiles}
                      disabled={loadingMoreFiles}
                      className="btn-secondary px-5 py-2 text-sm disabled:opacity-50"
                    >
                      {loadingMoreFiles
                        ? (isEn ? 'Loading…' : 'กำลังโหลด…')
                        : (isEn ? 'Load more files' : 'โหลดไฟล์เพิ่มเติม')}
                    </button>
                  </div>
                )}
              </>
            )}
            {activeView === 'sql' && (
              <DatabaseConnectView isEn={isEn} user={user} m={m} plan={effectivePlan} isPlanLoading={isPlanLoading} onSyncSuccess={() => fetchFiles(user.id, { showLoading: false })} />
            )}
            {activeView === 'cloud' && (
              <CloudDatasetView isEn={isEn} user={user} onSyncSuccess={() => fetchFiles(user.id, { showLoading: false })} />
            )}
            {activeView === 'api' && (
              <ApiConnectView isEn={isEn} user={user} m={m} plan={effectivePlan} isPlanLoading={isPlanLoading} onSyncSuccess={() => fetchFiles(user.id, { showLoading: false })} />
            )}
            {activeView === 'schedules' && (
              <ScheduledEtlView isEn={isEn} user={user} />
            )}
          </div>
        </div>
      </main>

      {/* Data Preview Modal */}
      <DataPreviewModal
        show={previewModal.show}
        data={previewModal.data}
        type={previewModal.type}
        fileName={previewModal.fileName}
        onClose={closePreview}
        isEn={isEn}
      />

      <LoadingOverlay show={isPreviewLoading} isEn={isEn} />

      <SuccessPopup show={showSuccess} isEn={isEn} />

      <DeleteConfirmationModal
        isOpen={deleteModal.show}
        onClose={() => setDeleteConfirm({ show: false, fileName: null })}
        onConfirm={confirmDelete}
        title={isEn ? 'Delete this file?' : 'ลบไฟล์นี้หรือไม่?'}
        subject={getDisplayName(deleteModal.fileName)}
        message={isEn
          ? 'This file will be permanently deleted and cannot be recovered.'
          : 'ไฟล์นี้จะถูกลบอย่างถาวร และกู้คืนไม่ได้'}
        confirmButtonText={isEn ? 'Delete file' : 'ลบไฟล์'}
        cancelButtonText={isEn ? 'Cancel' : 'ยกเลิก'}
      />
    </div>
  );
};

export default FileManager;
