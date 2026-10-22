'use client';

import * as React from 'react';
import { motion } from 'motion/react';
import * as Lucide from 'lucide-react';

import { Activity as ActivityBase } from '@/components/animate-ui/icons/activity';
import { ArrowLeft as ArrowLeftBase } from '@/components/animate-ui/icons/arrow-left';
import { ArrowRight as ArrowRightBase } from '@/components/animate-ui/icons/arrow-right';
import { ArrowUp as ArrowUpBase } from '@/components/animate-ui/icons/arrow-up';
import { BadgeCheck as BadgeCheckBase } from '@/components/animate-ui/icons/badge-check';
import { Bot as BotBase } from '@/components/animate-ui/icons/bot';
import { Check as CheckBase } from '@/components/animate-ui/icons/check';
import { ChevronDown as ChevronDownBase } from '@/components/animate-ui/icons/chevron-down';
import { ChevronLeft as ChevronLeftBase } from '@/components/animate-ui/icons/chevron-left';
import { ChevronRight as ChevronRightBase } from '@/components/animate-ui/icons/chevron-right';
import { Clock3 as Clock3Base } from '@/components/animate-ui/icons/clock-3';
import { CloudUpload as CloudUploadBase } from '@/components/animate-ui/icons/cloud-upload';
import { Copy as CopyBase } from '@/components/animate-ui/icons/copy';
import { Download as DownloadBase } from '@/components/animate-ui/icons/download';
import { ExternalLink as ExternalLinkBase } from '@/components/animate-ui/icons/external-link';
import { Gauge as GaugeBase } from '@/components/animate-ui/icons/gauge';
import { LayoutDashboard as LayoutDashboardBase } from '@/components/animate-ui/icons/layout-dashboard';
import { Lightbulb as LightbulbBase } from '@/components/animate-ui/icons/lightbulb';
import { Link2 as Link2Base } from '@/components/animate-ui/icons/link-2';
import { LoaderCircle as LoaderCircleBase } from '@/components/animate-ui/icons/loader-circle';
import { Lock as LockBase } from '@/components/animate-ui/icons/lock';
import { LockKeyhole as LockKeyholeBase } from '@/components/animate-ui/icons/lock-keyhole';
import { LogOut as LogOutBase } from '@/components/animate-ui/icons/log-out';
import { MessageCircle as MessageCircleBase } from '@/components/animate-ui/icons/message-circle';
import { MessageSquare as MessageSquareBase } from '@/components/animate-ui/icons/message-square';
import { MessageSquarePlus as MessageSquarePlusBase } from '@/components/animate-ui/icons/message-square-plus';
import { MessageSquareText as MessageSquareTextBase } from '@/components/animate-ui/icons/message-square-text';
import { PanelLeftClose as PanelLeftCloseBase } from '@/components/animate-ui/icons/panel-left-close';
import { PanelLeftOpen as PanelLeftOpenBase } from '@/components/animate-ui/icons/panel-left-open';
import { Paperclip as PaperclipBase } from '@/components/animate-ui/icons/paperclip';
import { Pause as PauseBase } from '@/components/animate-ui/icons/pause';
import { Pin as PinBase } from '@/components/animate-ui/icons/pin';
import { Play as PlayBase } from '@/components/animate-ui/icons/play';
import { Plus as PlusBase } from '@/components/animate-ui/icons/plus';
import { RefreshCw as RefreshCwBase } from '@/components/animate-ui/icons/refresh-cw';
import { Search as SearchBase } from '@/components/animate-ui/icons/search';
import { Send as SendBase } from '@/components/animate-ui/icons/send';
import { Settings as SettingsBase } from '@/components/animate-ui/icons/settings';
import { SlidersHorizontal as SlidersHorizontalBase } from '@/components/animate-ui/icons/sliders-horizontal';
import { Sparkles as SparklesBase } from '@/components/animate-ui/icons/sparkles';
import { SunMoon as SunMoonBase } from '@/components/animate-ui/icons/sun-moon';
import { ThumbsDown as ThumbsDownBase } from '@/components/animate-ui/icons/thumbs-down';
import { ThumbsUp as ThumbsUpBase } from '@/components/animate-ui/icons/thumbs-up';
import { Trash2 as Trash2Base } from '@/components/animate-ui/icons/trash-2';
import { Upload as UploadBase } from '@/components/animate-ui/icons/upload';
import { User as UserBase } from '@/components/animate-ui/icons/user';
import { X as XBase } from '@/components/animate-ui/icons/x';
import {
  IconWrapper,
  useAnimateIconContext,
  type IconProps,
} from '@/components/animate-ui/icons/icon';

type SystemIconProps = IconProps<string>;
type SystemIcon = React.ComponentType<SystemIconProps>;

function withSystemMotion(Icon: React.ComponentType<never>, name: string) {
  function AnimatedSystemIcon({
    animateOnHover = true,
    animateOnTap = true,
    ...props
  }: SystemIconProps) {
    const Component = Icon as unknown as SystemIcon;
    return (
      <Component
        animateOnHover={animateOnHover}
        animateOnTap={animateOnTap}
        {...props}
      />
    );
  }

  AnimatedSystemIcon.displayName = name;
  return AnimatedSystemIcon;
}

const fallbackVariants = {
  initial: { scale: 1, rotate: 0 },
  animate: {
    scale: [1, 0.88, 1.06, 1],
    rotate: [0, -4, 4, 0],
    transition: { duration: 0.42, ease: 'easeInOut' as const },
  },
};

function createFallbackIcon(Icon: Lucide.LucideIcon, name: string) {
  const MotionIcon = motion.create(Icon);
  const AnimatedLucide = MotionIcon as unknown as React.ComponentType<
    Record<string, unknown>
  >;

  function IconComponent({ size = 28, ...props }: SystemIconProps) {
    const { controls } = useAnimateIconContext();
    return (
      <AnimatedLucide
        size={size}
        {...props}
        variants={fallbackVariants}
        initial="initial"
        animate={controls}
      />
    );
  }

  function FallbackIcon(props: SystemIconProps) {
    return <IconWrapper icon={IconComponent} {...props} />;
  }

  FallbackIcon.displayName = `${name}AnimateUiFallback`;
  return withSystemMotion(
    FallbackIcon as unknown as React.ComponentType<never>,
    name,
  );
}

export const Activity = withSystemMotion(ActivityBase as never, 'Activity');
export const ArrowLeft = withSystemMotion(ArrowLeftBase as never, 'ArrowLeft');
export const ArrowRight = withSystemMotion(ArrowRightBase as never, 'ArrowRight');
export const ArrowUp = withSystemMotion(ArrowUpBase as never, 'ArrowUp');
export const ArrowDown = createFallbackIcon(Lucide.ArrowDown, 'ArrowDown');
export const BadgeCheck = withSystemMotion(BadgeCheckBase as never, 'BadgeCheck');
export const Bot = withSystemMotion(BotBase as never, 'Bot');
export const Check = withSystemMotion(CheckBase as never, 'Check');
export const ChevronDown = withSystemMotion(ChevronDownBase as never, 'ChevronDown');
export const ChevronLeft = withSystemMotion(ChevronLeftBase as never, 'ChevronLeft');
export const ChevronRight = withSystemMotion(ChevronRightBase as never, 'ChevronRight');
export const Clock3 = withSystemMotion(Clock3Base as never, 'Clock3');
export const CloudUpload = withSystemMotion(CloudUploadBase as never, 'CloudUpload');
export const Copy = withSystemMotion(CopyBase as never, 'Copy');
export const Download = withSystemMotion(DownloadBase as never, 'Download');
export const ExternalLink = withSystemMotion(ExternalLinkBase as never, 'ExternalLink');
export const Gauge = withSystemMotion(GaugeBase as never, 'Gauge');
export const LayoutDashboard = withSystemMotion(LayoutDashboardBase as never, 'LayoutDashboard');
export const Lightbulb = withSystemMotion(LightbulbBase as never, 'Lightbulb');
export const Link2 = withSystemMotion(Link2Base as never, 'Link2');
export const LoaderCircle = withSystemMotion(LoaderCircleBase as never, 'LoaderCircle');
export const Lock = withSystemMotion(LockBase as never, 'Lock');
export const LockKeyhole = withSystemMotion(LockKeyholeBase as never, 'LockKeyhole');
export const LogOut = withSystemMotion(LogOutBase as never, 'LogOut');
export const MessageCircle = withSystemMotion(MessageCircleBase as never, 'MessageCircle');
export const MessageSquare = withSystemMotion(MessageSquareBase as never, 'MessageSquare');
export const MessageSquarePlus = withSystemMotion(MessageSquarePlusBase as never, 'MessageSquarePlus');
export const MessageSquareText = withSystemMotion(MessageSquareTextBase as never, 'MessageSquareText');
export const PanelLeftClose = withSystemMotion(PanelLeftCloseBase as never, 'PanelLeftClose');
export const PanelLeftOpen = withSystemMotion(PanelLeftOpenBase as never, 'PanelLeftOpen');
export const Paperclip = withSystemMotion(PaperclipBase as never, 'Paperclip');
export const Pause = withSystemMotion(PauseBase as never, 'Pause');
export const Pin = withSystemMotion(PinBase as never, 'Pin');
export const Play = withSystemMotion(PlayBase as never, 'Play');
export const Plus = withSystemMotion(PlusBase as never, 'Plus');
export const RefreshCw = withSystemMotion(RefreshCwBase as never, 'RefreshCw');
export const Search = withSystemMotion(SearchBase as never, 'Search');
export const Send = withSystemMotion(SendBase as never, 'Send');
export const Settings = withSystemMotion(SettingsBase as never, 'Settings');
export const SlidersHorizontal = withSystemMotion(SlidersHorizontalBase as never, 'SlidersHorizontal');
export const Sparkles = withSystemMotion(SparklesBase as never, 'Sparkles');
export const SunMoon = withSystemMotion(SunMoonBase as never, 'SunMoon');
export const ThumbsDown = withSystemMotion(ThumbsDownBase as never, 'ThumbsDown');
export const ThumbsUp = withSystemMotion(ThumbsUpBase as never, 'ThumbsUp');
export const Trash2 = withSystemMotion(Trash2Base as never, 'Trash2');
export const Upload = withSystemMotion(UploadBase as never, 'Upload');
export const User = withSystemMotion(UserBase as never, 'User');
export const X = withSystemMotion(XBase as never, 'X');
export const Volume2 = createFallbackIcon(Lucide.Volume2, 'Volume2');
export const VolumeX = createFallbackIcon(Lucide.VolumeX, 'VolumeX');

export const AlertTriangle = createFallbackIcon(Lucide.AlertTriangle, 'AlertTriangle');
export const AreaChart = createFallbackIcon(Lucide.AreaChart, 'AreaChart');
export const ArrowUpRight = withSystemMotion(ExternalLinkBase as never, 'ArrowUpRight');
export const BarChart3 = createFallbackIcon(Lucide.BarChart3, 'BarChart3');
export const BookOpen = createFallbackIcon(Lucide.BookOpen, 'BookOpen');
export const Boxes = createFallbackIcon(Lucide.Boxes, 'Boxes');
export const Braces = createFallbackIcon(Lucide.Braces, 'Braces');
export const Brain = createFallbackIcon(Lucide.Brain, 'Brain');
export const BrainCircuit = createFallbackIcon(Lucide.BrainCircuit, 'BrainCircuit');
export const Building2 = createFallbackIcon(Lucide.Building2, 'Building2');
export const Calculator = createFallbackIcon(Lucide.Calculator, 'Calculator');
export const Calendar = createFallbackIcon(Lucide.Calendar, 'Calendar');
export const CalendarClock = withSystemMotion(Clock3Base as never, 'CalendarClock');
export const Camera = createFallbackIcon(Lucide.Camera, 'Camera');
export const ChartNoAxesCombined = createFallbackIcon(Lucide.ChartNoAxesCombined, 'ChartNoAxesCombined');
export const CheckCircle = withSystemMotion(BadgeCheckBase as never, 'CheckCircle');
export const CheckCircle2 = withSystemMotion(BadgeCheckBase as never, 'CheckCircle2');
export const CircleAlert = createFallbackIcon(Lucide.CircleAlert, 'CircleAlert');
export const CircleHelp = createFallbackIcon(Lucide.CircleHelp, 'CircleHelp');
export const Cloud = createFallbackIcon(Lucide.Cloud, 'Cloud');
export const Cookie = createFallbackIcon(Lucide.Cookie, 'Cookie');
export const Cpu = createFallbackIcon(Lucide.Cpu, 'Cpu');
export const CreditCard = createFallbackIcon(Lucide.CreditCard, 'CreditCard');
export const Database = createFallbackIcon(Lucide.Database, 'Database');
export const Edit2 = createFallbackIcon(Lucide.Edit2, 'Edit2');
export const Eye = createFallbackIcon(Lucide.Eye, 'Eye');
export const EyeOff = createFallbackIcon(Lucide.EyeOff, 'EyeOff');
export const Factory = createFallbackIcon(Lucide.Factory, 'Factory');
export const FileArchive = createFallbackIcon(Lucide.FileArchive, 'FileArchive');
export const FileDown = withSystemMotion(DownloadBase as never, 'FileDown');
export const FileOutput = createFallbackIcon(Lucide.FileOutput, 'FileOutput');
export const FilePlus2 = withSystemMotion(PlusBase as never, 'FilePlus2');
export const FileSearch = withSystemMotion(SearchBase as never, 'FileSearch');
export const FileSpreadsheet = createFallbackIcon(Lucide.FileSpreadsheet, 'FileSpreadsheet');
export const FileText = createFallbackIcon(Lucide.FileText, 'FileText');
export const FileUp = withSystemMotion(UploadBase as never, 'FileUp');
export const Filter = withSystemMotion(SlidersHorizontalBase as never, 'Filter');
export const FolderOpen = createFallbackIcon(Lucide.FolderOpen, 'FolderOpen');
export const GitBranch = createFallbackIcon(Lucide.GitBranch, 'GitBranch');
export const Globe = createFallbackIcon(Lucide.Globe, 'Globe');
export const GripVertical = createFallbackIcon(Lucide.GripVertical, 'GripVertical');
export const KeyRound = withSystemMotion(LockKeyholeBase as never, 'KeyRound');
export const Layers3 = createFallbackIcon(Lucide.Layers3, 'Layers3');
export const LineChart = createFallbackIcon(Lucide.LineChart, 'LineChart');
export const Loader2 = withSystemMotion(LoaderCircleBase as never, 'Loader2');
export const Mail = createFallbackIcon(Lucide.Mail, 'Mail');
export const Maximize2 = createFallbackIcon(Lucide.Maximize2, 'Maximize2');
export const Megaphone = createFallbackIcon(Lucide.Megaphone, 'Megaphone');
export const Mic = createFallbackIcon(Lucide.Mic, 'Mic');
export const MicOff = createFallbackIcon(Lucide.MicOff, 'MicOff');
export const Minimize2 = createFallbackIcon(Lucide.Minimize2, 'Minimize2');
export const MoreVertical = createFallbackIcon(Lucide.MoreVertical, 'MoreVertical');
export const Network = withSystemMotion(Link2Base as never, 'Network');
export const PackageOpen = createFallbackIcon(Lucide.PackageOpen, 'PackageOpen');
export const Pencil = createFallbackIcon(Lucide.Pencil, 'Pencil');
export const PencilLine = createFallbackIcon(Lucide.PencilLine, 'PencilLine');
export const Phone = createFallbackIcon(Lucide.Phone, 'Phone');
export const PieChart = createFallbackIcon(Lucide.PieChart, 'PieChart');
export const Rows3 = createFallbackIcon(Lucide.Rows3, 'Rows3');
export const Save = createFallbackIcon(Lucide.Save, 'Save');
export const SearchCheck = withSystemMotion(BadgeCheckBase as never, 'SearchCheck');
export const SearchX = createFallbackIcon(Lucide.SearchX, 'SearchX');
export const Server = createFallbackIcon(Lucide.Server, 'Server');
export const Shield = withSystemMotion(LockBase as never, 'Shield');
export const ShieldAlert = createFallbackIcon(Lucide.ShieldAlert, 'ShieldAlert');
export const ShieldCheck = withSystemMotion(BadgeCheckBase as never, 'ShieldCheck');
export const ShoppingBag = createFallbackIcon(Lucide.ShoppingBag, 'ShoppingBag');
export const Square = createFallbackIcon(Lucide.Square, 'Square');
export const Table = createFallbackIcon(Lucide.Table, 'Table');
export const Table2 = createFallbackIcon(Lucide.Table2, 'Table2');
export const TriangleAlert = createFallbackIcon(Lucide.TriangleAlert, 'TriangleAlert');
export const Workflow = withSystemMotion(Link2Base as never, 'Workflow');
export const Zap = createFallbackIcon(Lucide.Zap, 'Zap');

export type { SystemIcon, SystemIconProps };
