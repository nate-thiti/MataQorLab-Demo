// @ts-nocheck
"use client";

import { createContext, useContext, useMemo } from 'react';
import { createFileManagerCache } from '../utils/fileManagerCache.js';

const FileManagerCacheContext = createContext(null);

export function FileManagerCacheProvider({ children }) {
  const cache = useMemo(() => createFileManagerCache(), []);
  return (
    <FileManagerCacheContext.Provider value={cache}>
      {children}
    </FileManagerCacheContext.Provider>
  );
}

export function useFileManagerCache() {
  const cache = useContext(FileManagerCacheContext);
  if (!cache) {
    throw new Error('useFileManagerCache must be used within FileManagerCacheProvider');
  }
  return cache;
}
