import Link from "next/link";
import { type CSSProperties, type ReactNode } from "react";
import { useTheme } from "../../context/ThemeContext";

const BASE_CLASS =
  "marketing-btn inline-flex items-center justify-center rounded-lg font-semibold no-underline transition-colors";

const PALETTE = {
  primary: {
    light: {
      backgroundColor: "#d97706",
      color: "#ffffff",
      border: "1px solid #d97706",
    },
    dark: {
      backgroundColor: "#d97706",
      color: "#ffffff",
      border: "1px solid #d97706",
    },
  },
  secondary: {
    light: {
      backgroundColor: "#1d1d1f",
      color: "#ffffff",
      border: "1px solid #1d1d1f",
    },
    dark: {
      backgroundColor: "#ffffff",
      color: "#1a1a21",
      border: "1px solid #ffffff",
    },
  },
} as const;

type MarketingButtonProps = {
  variant?: keyof typeof PALETTE;
  to?: string;
  href?: string;
  className?: string;
  children: ReactNode;
  type?: "button" | "submit" | "reset";
  style?: CSSProperties;
};

const MarketingButton = ({
  variant = "primary",
  to,
  href,
  className = "",
  children,
  type = "button",
  style,
  ...rest
}: MarketingButtonProps) => {
  const { theme } = useTheme();
  const mode = theme === "dark" ? "dark" : "light";
  const palette = PALETTE[variant] ?? PALETTE.primary;

  const cn = [
    BASE_CLASS,
    variant === "primary" ? "marketing-btn-primary" : "marketing-btn-secondary",
    `marketing-btn-${mode}`,
    className,
  ]
    .filter(Boolean)
    .join(" ");

  const btnStyle: CSSProperties = {
    ...palette[mode],
    ...style,
  };

  if (to) {
    return (
      <Link href={to} className={cn} style={btnStyle} {...rest}>
        {children}
      </Link>
    );
  }

  if (href) {
    return (
      <a href={href} className={cn} style={btnStyle} {...rest}>
        {children}
      </a>
    );
  }

  return (
    <button type={type} className={cn} style={btnStyle} {...rest}>
      {children}
    </button>
  );
};

export default MarketingButton;
