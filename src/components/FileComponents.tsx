// @ts-nocheck
import { useMemo, useRef, useState } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import {
  Check,
  Download,
  Eye,
  FolderOpen,
  LoaderCircle,
  Search,
  Trash2,
  Upload,
  X,
} from '@/components/icons';
import { formatFileBytes, getDisplayName, getFileExtensionLabel, getFileIcon } from '../utils/fileDisplay';

const VIEW_COPY = {
  files: {
    title: { en: 'Manage Data Files', th: 'จัดการไฟล์ข้อมูล' },
    subtitle: {
      en: 'Upload, preview, and organize datasets for analysis.',
      th: 'อัปโหลด ดูตัวอย่าง และจัดไฟล์ข้อมูลสำหรับวิเคราะห์',
    },
  },
  sql: {
    title: { en: 'SQL Databases', th: 'ฐานข้อมูล SQL' },
    subtitle: {
      en: 'Connect relational databases to analyze live tables.',
      th: 'เชื่อมต่อฐานข้อมูลเชิงสัมพันธ์เพื่อวิเคราะห์ตารางจริง',
    },
  },
  api: {
    title: { en: 'API Connections', th: 'เชื่อมต่อ API' },
    subtitle: {
      en: 'Pull JSON endpoints into your analysis workspace.',
      th: 'ดึงข้อมูลจาก API เข้าสู่พื้นที่วิเคราะห์',
    },
  },
  cloud: {
    title: { en: 'Cloud Files', th: 'ไฟล์ Cloud' },
    subtitle: {
      en: 'Sync datasets from connected cloud storage.',
      th: 'ซิงก์ชุดข้อมูลจากที่เก็บไฟล์บนคลาวด์',
    },
  },
  schedules: {
    title: { en: 'Scheduled ETL', th: 'ตั้งเวลา ETL' },
    subtitle: {
      en: 'Automate recurring data refresh jobs.',
      th: 'ตั้งเวลารีเฟรชข้อมูลแบบอัตโนมัติ',
    },
  },
};

const copy = (isEn, en, th) => (isEn ? en : th);

export const FileManagerHeader = ({
  isEn,
  handleFileChange,
  uploading,
  activeView = 'files',
}) => {
  const view = VIEW_COPY[activeView] || VIEW_COPY.files;
  const showUpload = activeView === 'files';

  return (
    <header className="app-toolbar px-5 md:px-8 py-4">
      <div className="app-page-frame mx-auto w-full max-w-[1180px] flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="min-w-0">
          <div className="app-page-kicker mb-2">DATA WORKSPACE</div>
          <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-100 tracking-tight">
            {copy(isEn, view.title.en, view.title.th)}
          </h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            {copy(isEn, view.subtitle.en, view.subtitle.th)}
          </p>
        </div>

        {showUpload && (
          <label className="cursor-pointer btn-primary px-4 py-2 text-sm inline-flex items-center gap-2 self-start lg:self-auto">
            <input
              type="file"
              className="hidden"
              onChange={handleFileChange}
              disabled={uploading}
              accept=".csv,.json,.xlsx,.xls,.parquet"
            />
            {uploading ? (
              <LoaderCircle className="h-4 w-4 text-white animate-spin" strokeWidth={1.5} />
            ) : (
              <Upload className="h-4 w-4" strokeWidth={1.75} />
            )}
            {uploading
              ? copy(isEn, 'Uploading...', 'กำลังอัปโหลด...')
              : copy(isEn, 'Upload file', 'อัปโหลดไฟล์')}
          </label>
        )}
      </div>
    </header>
  );
};

export const UploadProgressBar = ({ uploading, uploadProgress, isEn }) => {
  if (!uploading) return null;
  return (
    <div className="border-b border-slate-200/80 dark:border-white/10 bg-white/80 dark:bg-zinc-950/80 px-5 md:px-8 py-3">
      <div className="app-page-frame mx-auto w-full max-w-[1180px]">
        <div className="flex justify-between items-center mb-2">
          <span className="text-xs font-medium text-slate-700 dark:text-slate-300">
            {copy(isEn, 'Sending data...', 'กำลังส่งข้อมูลเข้าสู่ระบบ...')}
          </span>
          <span className="text-xs font-medium tabular-nums text-slate-500 dark:text-slate-400">{uploadProgress}%</span>
        </div>
        <div className="progress-track h-1.5">
          <div className="progress-fill-warning" style={{ width: `${uploadProgress}%` }} />
        </div>
      </div>
    </div>
  );
};

export const FileItem = ({ file, handlePreview, handleDownload, setDeleteConfirm, isPreviewLoading, isEn }) => {
  const fileInfo = getFileIcon(file.name);
  const displayName = getDisplayName(file.name);
  const created = file.created_at
    ? new Date(file.created_at).toLocaleDateString(isEn ? 'en-US' : 'th-TH', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      })
    : '—';

  return (
    <div className="flex items-center gap-3 px-4 py-3 hover:bg-slate-50/80 dark:hover:bg-zinc-800/40 transition-colors">
      <div className={`h-10 w-10 shrink-0 rounded-lg flex items-center justify-center ${fileInfo.bgColor} ${fileInfo.textColor}`}>
        {fileInfo.icon}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-slate-800 dark:text-slate-100 truncate" title={displayName}>
          {displayName}
        </p>
        <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
          {formatFileBytes(file.metadata?.size)} · {created}
        </p>
      </div>
      <span className="hidden sm:inline-flex shrink-0 rounded-md border border-slate-200 dark:border-white/10 px-2 py-0.5 text-[10px] font-semibold tracking-wide text-slate-500 dark:text-slate-400">
        {getFileExtensionLabel(file.name)}
      </span>
      <div className="flex items-center gap-0.5 shrink-0">
        <button
          onClick={() => handlePreview(file.name)}
          className="p-2 text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 rounded-lg transition-colors"
          title={copy(isEn, 'Preview', 'ดูตัวอย่างข้อมูล')}
          disabled={isPreviewLoading}
        >
          <Eye className="w-4 h-4" strokeWidth={1.6} />
        </button>
        <button
          onClick={() => handleDownload(file.name)}
          className="p-2 text-slate-400 hover:text-[#d97706] rounded-lg transition-colors"
          title={copy(isEn, 'Download', 'เปิดดู/ดาวน์โหลด')}
        >
          <Download className="w-4 h-4" strokeWidth={1.6} />
        </button>
        <button
          onClick={() => setDeleteConfirm({ show: true, fileName: file.name })}
          className="p-2 text-slate-400 hover:text-red-600 dark:hover:text-red-400 rounded-lg transition-colors"
          title={copy(isEn, 'Delete', 'ลบไฟล์')}
        >
          <Trash2 className="w-4 h-4" strokeWidth={1.6} />
        </button>
      </div>
    </div>
  );
};

const VirtualizedFileRows = ({
  files,
  handlePreview,
  handleDownload,
  setDeleteConfirm,
  isPreviewLoading,
  isEn,
}) => {
  const scrollRef = useRef(null);
  // TanStack Virtual keeps measurement functions outside React memoization.
  // eslint-disable-next-line react-hooks/incompatible-library
  const virtualizer = useVirtualizer({
    count: files.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => 72,
    overscan: 8,
  });

  return (
    <div ref={scrollRef} className="max-h-[65vh] overflow-y-auto no-scrollbar">
      <div className="relative" style={{ height: `${virtualizer.getTotalSize()}px` }}>
        {virtualizer.getVirtualItems().map((virtualRow) => {
          const file = files[virtualRow.index];
          return (
            <div
              key={file.id || file.name}
              ref={virtualizer.measureElement}
              data-index={virtualRow.index}
              className="absolute left-0 top-0 w-full border-b border-slate-100 dark:border-white/10 last:border-b-0"
              style={{ transform: `translateY(${virtualRow.start}px)` }}
            >
              <FileItem
                file={file}
                handlePreview={handlePreview}
                handleDownload={handleDownload}
                setDeleteConfirm={setDeleteConfirm}
                isPreviewLoading={isPreviewLoading}
                isEn={isEn}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
};

const FileToolbar = ({ isEn, query, setQuery, visibleCount }) => (
  <div className="mb-4 flex justify-end">
    <div className="relative w-full sm:w-64">
      <div className="flex items-center rounded-lg border border-slate-200/70 dark:border-white/10 bg-white/90 dark:bg-zinc-900/70 focus-within:border-slate-300 dark:focus-within:border-white/20">
        <Search className="pointer-events-none ml-2.5 h-4 w-4 shrink-0 text-slate-400" strokeWidth={1.75} />
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={copy(isEn, 'Search files', 'ค้นหาไฟล์')}
          className="w-full h-9 min-h-9 pl-2 pr-3 text-sm bg-transparent border-none shadow-none outline-none"
        />
      </div>
      {query && (
        <p className="mt-1 text-[11px] text-slate-400 text-right">
          {visibleCount} {copy(isEn, 'matches', 'รายการที่ตรง')}
        </p>
      )}
    </div>
  </div>
);

export const FileList = ({
  loading,
  files,
  filteredFiles,
  isDragging,
  filter,
  setFilter,
  onFilterChange,
  isEn,
  handlePreview,
  handleDownload,
  setDeleteConfirm,
  isPreviewLoading,
}) => {
  const [query, setQuery] = useState('');
  const changeFilter = onFilterChange || setFilter;
  const visibleFiles = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return filteredFiles;
    return filteredFiles.filter((file) => getDisplayName(file.name).toLowerCase().includes(needle));
  }, [filteredFiles, query]);

  if (loading) {
    return (
      <div className="enterprise-panel overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-100 dark:border-white/10">
          <div className="h-4 w-32 bg-slate-100 dark:bg-zinc-800 animate-pulse rounded" />
        </div>
        <div className="divide-y divide-slate-100 dark:divide-white/10">
          {[0, 1, 2, 3].map((key) => (
            <div key={key} className="flex items-center gap-3 px-4 py-3">
              <div className="h-10 w-10 rounded-lg bg-slate-100 dark:bg-zinc-800 animate-pulse" />
              <div className="flex-1 space-y-2">
                <div className="h-3.5 w-2/5 bg-slate-100 dark:bg-zinc-800 animate-pulse rounded" />
                <div className="h-3 w-1/4 bg-slate-100 dark:bg-zinc-800 animate-pulse rounded" />
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (files.length === 0) {
    return (
      <div
        className={`flex flex-col items-center justify-center text-center py-16 px-6 enterprise-panel border-dashed ${
          isDragging ? 'border-[#d97706]/50 bg-amber-50/40 dark:bg-amber-500/5' : ''
        }`}
      >
        <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-amber-50 dark:bg-amber-500/10 text-[#d97706] mb-4">
          {isDragging ? <Upload className="h-6 w-6" strokeWidth={1.6} /> : <FolderOpen className="h-6 w-6" strokeWidth={1.6} />}
        </div>
        <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">
          {copy(isEn, 'Drag files here to upload', 'ลากไฟล์มาวางเพื่ออัปโหลด')}
        </p>
        <p className="mt-1 text-xs text-slate-500 dark:text-slate-400 max-w-sm">
          {copy(
            isEn,
            'Or click Upload above. Supported: CSV, Excel, JSON, Parquet.',
            'หรือคลิกปุ่มอัปโหลดด้านบน รองรับ CSV, Excel, JSON และ Parquet',
          )}
        </p>
        {isDragging && (
          <div className="mt-4 inline-flex px-3 py-1.5 bg-slate-900 dark:bg-white text-white dark:text-slate-900 text-xs rounded-lg font-semibold">
            {copy(isEn, 'Drop to upload now', 'ปล่อยเพื่ออัปโหลดทันที')}
          </div>
        )}
      </div>
    );
  }

  const listBody = visibleFiles.length === 0 ? (
    <div className="py-14 px-6 text-center">
      <Search className="w-8 h-8 mx-auto text-slate-300 dark:text-slate-600 mb-3" strokeWidth={1.5} />
      <p className="text-sm text-slate-500 dark:text-slate-400">
        {copy(isEn, 'No matching files.', 'ไม่พบไฟล์ที่ตรงกับการค้นหา')}
      </p>
      <button
        type="button"
        onClick={() => {
          setQuery('');
          changeFilter('all');
        }}
        className="mt-3 text-[#d97706] text-sm font-semibold hover:underline"
      >
        {copy(isEn, 'View all files', 'กลับไปดูไฟล์ทั้งหมด')}
      </button>
    </div>
  ) : visibleFiles.length > 20 ? (
    <VirtualizedFileRows
      files={visibleFiles}
      handlePreview={handlePreview}
      handleDownload={handleDownload}
      setDeleteConfirm={setDeleteConfirm}
      isPreviewLoading={isPreviewLoading}
      isEn={isEn}
    />
  ) : (
    <div className="divide-y divide-slate-100 dark:divide-white/10">
      {visibleFiles.map((file) => (
        <FileItem
          key={file.id || file.name}
          file={file}
          handlePreview={handlePreview}
          handleDownload={handleDownload}
          setDeleteConfirm={setDeleteConfirm}
          isPreviewLoading={isPreviewLoading}
          isEn={isEn}
        />
      ))}
    </div>
  );

  return (
    <div>
      <FileToolbar
        isEn={isEn}
        query={query}
        setQuery={setQuery}
        visibleCount={visibleFiles.length}
      />
      <div className="enterprise-panel overflow-hidden">{listBody}</div>
    </div>
  );
};

const DataPreviewModalBody = ({ data, type, fileName, onClose, isEn }) => {
  const [currentPage, setCurrentPage] = useState(0);
  const rowsPerPage = 20;
  const fileInfo = getFileIcon(fileName);
  const totalRows = data?.length || 0;
  const totalPages = Math.ceil(totalRows / rowsPerPage);
  const startIndex = currentPage * rowsPerPage;
  const endIndex = startIndex + rowsPerPage;
  const currentRows = data?.slice(startIndex, endIndex) || [];

  return (
    <div className="fixed inset-0 z-[160] flex items-center justify-center p-4 md:p-8 bg-black/50 backdrop-blur-sm">
      <div className="bg-white dark:bg-zinc-950 w-full max-w-6xl max-h-[85vh] rounded-2xl border border-slate-200 dark:border-white/10 overflow-hidden flex flex-col">
        <header className="p-5 border-b border-slate-200 dark:border-white/10 flex justify-between items-center gap-4">
          <div className="flex items-center gap-3 min-w-0">
            <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${fileInfo.bgColor} ${fileInfo.textColor}`}>
              {fileInfo.icon}
            </div>
            <div className="min-w-0">
              <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100 truncate">{fileName}</h3>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                {copy(isEn, 'Preview · 20 rows per page', 'ตัวอย่างข้อมูล · แสดง 20 แถวต่อหน้า')}
              </p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-slate-100 dark:hover:bg-zinc-800 rounded-lg transition-colors">
            <X className="w-5 h-5 text-slate-400" strokeWidth={1.5} />
          </button>
        </header>

        <div className="flex-1 overflow-auto no-scrollbar p-5">
          {type === 'json' && data ? (
            <pre className="bg-slate-50 dark:bg-zinc-900 p-5 rounded-xl border border-slate-200 dark:border-white/10 font-mono text-sm overflow-auto text-slate-800 dark:text-slate-300 leading-relaxed">
              {JSON.stringify(data, null, 2)}
            </pre>
          ) : (
            <div className="relative overflow-x-auto border border-slate-200 dark:border-white/10 rounded-xl">
              <table className="w-full text-left border-collapse text-sm">
                <thead>
                  <tr className="bg-slate-50 dark:bg-zinc-900 border-b border-slate-200 dark:border-white/10">
                    {data && data.length > 0 && Object.keys(data[0] || {}).map((header) => (
                      <th key={header} className="px-4 py-3 font-medium text-slate-600 dark:text-slate-400 whitespace-nowrap">
                        {header}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-white/10">
                  {currentRows.map((row, i) => (
                    <tr key={i} className="hover:bg-slate-50 dark:hover:bg-zinc-800/50 transition-colors">
                      {Object.values(row).map((val, j) => (
                        <td key={j} className="px-4 py-3 text-slate-600 dark:text-slate-300 whitespace-nowrap max-w-[200px] truncate">
                          {typeof val === 'object' ? JSON.stringify(val) : String(val)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
              {totalRows > 0 && (
                <div className="p-3 bg-slate-50 dark:bg-zinc-900/60 text-center text-xs text-slate-500 border-t border-slate-200 dark:border-white/10">
                  {copy(
                    isEn,
                    `Rows ${startIndex + 1}–${Math.min(endIndex, totalRows)} of ${totalRows}`,
                    `แสดงแถวที่ ${startIndex + 1} - ${Math.min(endIndex, totalRows)} จากทั้งหมด ${totalRows} แถว`,
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        <footer className="p-4 bg-slate-50 dark:bg-zinc-900/70 border-t border-slate-200 dark:border-white/10 flex justify-between items-center">
          <button onClick={onClose} className="px-5 py-2 btn-secondary text-sm">
            {copy(isEn, 'Close', 'ปิดหน้าต่าง')}
          </button>
          {totalPages > 1 && (
            <div className="flex items-center gap-3">
              <button
                onClick={() => currentPage > 0 && setCurrentPage((prev) => prev - 1)}
                disabled={currentPage === 0}
                className="px-5 py-2 btn-secondary text-sm disabled:opacity-40"
              >
                {copy(isEn, 'Previous', 'ก่อนหน้า')}
              </button>
              <span className="text-xs font-medium tabular-nums text-slate-500 dark:text-slate-400">
                {copy(isEn, `Page ${currentPage + 1} / ${totalPages}`, `หน้า ${currentPage + 1} / ${totalPages}`)}
              </span>
              <button
                onClick={() => currentPage < totalPages - 1 && setCurrentPage((prev) => prev + 1)}
                disabled={currentPage === totalPages - 1}
                className="px-5 py-2 btn-primary text-sm disabled:opacity-40"
              >
                {copy(isEn, 'Next', 'ถัดไป')}
              </button>
            </div>
          )}
        </footer>
      </div>
    </div>
  );
};

export const DataPreviewModal = ({ show, data, type, fileName, onClose, isEn }) => {
  if (!show) return null;
  return (
    <DataPreviewModalBody
      key={fileName}
      data={data}
      type={type}
      fileName={fileName}
      onClose={onClose}
      isEn={isEn}
    />
  );
};

export const LoadingOverlay = ({ show, isEn }) => {
  if (!show) return null;
  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-white/70 dark:bg-black/50 backdrop-blur-sm">
      <div className="flex flex-col items-center gap-4">
        <div className="w-10 h-10 border-2 border-slate-200 border-t-slate-600 dark:border-slate-700 dark:border-t-slate-300 rounded-full animate-spin" />
        <p className="text-sm font-medium text-slate-700 dark:text-slate-300">
          {copy(isEn, 'Preparing data preview', 'กำลังจัดเตรียมข้อมูลตัวอย่าง')}
        </p>
      </div>
    </div>
  );
};

export const SuccessPopup = ({ show, isEn }) => {
  if (!show) return null;
  return (
    <div className="fixed top-10 left-1/2 -translate-x-1/2 z-[200]">
      <div className="bg-white dark:bg-zinc-900 border border-emerald-200 dark:border-emerald-900/40 py-3 px-5 rounded-xl flex items-center gap-3">
        <div className="w-5 h-5 bg-emerald-600 rounded-full flex items-center justify-center shrink-0">
          <Check className="w-3.5 h-3.5 text-white" strokeWidth={2.2} />
        </div>
        <span className="text-sm font-semibold text-slate-800 dark:text-slate-100">
          {copy(isEn, 'File uploaded successfully', 'อัปโหลดไฟล์สำเร็จเรียบร้อย')}
        </span>
      </div>
    </div>
  );
};
