// @ts-nocheck
"use client";

import { createContext, useContext, useEffect, useState } from 'react';

const APP_SIDEBAR_OPEN_STORAGE_KEY = 'app_sidebar_open';
const AppSidebarContext = createContext(null);

export function AppSidebarProvider({ children }) {
  const [isOpen, setIsOpen] = useState(() => {
    if (typeof window === 'undefined') return true;
    const saved = localStorage.getItem(APP_SIDEBAR_OPEN_STORAGE_KEY);
    return saved === null ? true : saved === 'true';
  });

  useEffect(() => {
    localStorage.setItem(APP_SIDEBAR_OPEN_STORAGE_KEY, String(isOpen));
  }, [isOpen]);

  return (
    <AppSidebarContext.Provider value={{ isOpen, setIsOpen }}>
      {children}
    </AppSidebarContext.Provider>
  );
}

export function useAppSidebar() {
  const value = useContext(AppSidebarContext);
  if (!value) {
    throw new Error('useAppSidebar must be used within AppSidebarProvider');
  }
  return value;
}
