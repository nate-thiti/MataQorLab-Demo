// @ts-nocheck
import { Braces, FileArchive, FileSpreadsheet, FileText } from '@/components/icons';

const ICON_NEUTRAL = {
  bgColor: 'bg-slate-100 dark:bg-zinc-800',
  textColor: 'text-slate-600 dark:text-slate-300',
};

const ICON_ACCENT = {
  bgColor: 'bg-amber-50 dark:bg-amber-500/10',
  textColor: 'text-[#d97706]',
};

/** File icon styling for file lists (neutral enterprise style). */
export function getFileIcon(fileName) {
  const ext = (fileName || '').split('.').pop().toLowerCase();
  switch (ext) {
    case 'csv':
      return { ...ICON_NEUTRAL, icon: <FileSpreadsheet className="w-5 h-5" strokeWidth={1.6} /> };
    case 'xlsx':
    case 'xls':
      return { ...ICON_ACCENT, icon: <FileSpreadsheet className="w-5 h-5" strokeWidth={1.6} /> };
    case 'json':
      return { ...ICON_NEUTRAL, icon: <Braces className="w-5 h-5" strokeWidth={1.6} /> };
    case 'parquet':
      return { ...ICON_NEUTRAL, icon: <FileArchive className="w-5 h-5" strokeWidth={1.6} /> };
    default:
      return { ...ICON_NEUTRAL, icon: <FileText className="w-5 h-5" strokeWidth={1.6} /> };
  }
}

export function getFileExtensionLabel(fileName) {
  const ext = (fileName || '').split('.').pop();
  return ext ? ext.toUpperCase() : 'FILE';
}

/** Remove timestamp prefix from stored file names. */
export function getDisplayName(fileName) {
  return fileName ? (fileName.split('_').slice(1).join(' ') || fileName) : '';
}

export function formatFileBytes(bytes) {
  if (!bytes) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.min(sizes.length - 1, Math.floor(Math.log(bytes) / Math.log(k)));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
}
