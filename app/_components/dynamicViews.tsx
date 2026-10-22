"use client";

import dynamic from "next/dynamic";
import LandingPage from "@/src/views/LandingPage";
import PricingPage from "@/src/views/PricingPage";
import PlatformPage from "@/src/views/PlatformPage";
import SolutionsPage from "@/src/views/SolutionsPage";
import PrivacyPolicy from "@/src/views/PrivacyPolicy";
import TermsOfService from "@/src/views/TermsOfService";
import DocumentationPage from "@/src/views/DocumentationPage";

const loading = () => null;

export {
  LandingPage,
  PricingPage,
  PlatformPage,
  SolutionsPage,
  PrivacyPolicy,
  TermsOfService,
  DocumentationPage,
};

export const Login = dynamic(() => import("@/src/views/Login"), {
  ssr: false,
  loading,
});
export const Register = dynamic(() => import("@/src/views/Register"), {
  ssr: false,
  loading,
});
export const Dashboard = dynamic(() => import("@/src/views/Dashboard"), {
  ssr: false,
  loading,
});
export const CustomerCenter = dynamic(
  () => import("@/src/views/CustomerCenter"),
  { ssr: false, loading },
);
export const Visualization = dynamic(
  () => import("@/src/views/Visualization"),
  { ssr: false, loading },
);
export const FileManager = dynamic(
  () => import("@/src/views/FileManager"),
  { ssr: false, loading },
);
export const Chat = dynamic(() => import("@/src/views/Chat"), {
  ssr: false,
  loading,
});
export const PaymentHistory = dynamic(
  () => import("@/src/views/PaymentHistory"),
  { ssr: false, loading },
);
export const SettingsPage = dynamic(
  () => import("@/src/views/SettingsPage"),
  { ssr: false, loading },
);
export const ResetPassword = dynamic(
  () => import("@/src/views/ResetPassword"),
  { ssr: false, loading },
);
