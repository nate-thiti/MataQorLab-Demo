"""Column profiling helpers (shared by dataset_engine and analytics)."""
from typing import List

import pandas as pd


def build_column_profile(df: pd.DataFrame, max_categorical_top: int = 5) -> str:
    """Token-efficient column profiling over the full dataset."""
    lines: List[str] = []
    for col in df.columns:
        series = df[col]
        dtype = str(series.dtype)
        null_pct = series.isnull().mean() * 100
        unique = series.nunique()
        numeric = pd.to_numeric(series, errors="coerce")
        valid_ratio = numeric.notna().sum() / max(series.notna().sum(), 1)

        if valid_ratio >= 0.7 and numeric.notna().any():
            lines.append(
                f"- {col} (numeric): {unique} unique, null {null_pct:.1f}%, "
                f"range [{numeric.min():,.4g} – {numeric.max():,.4g}], mean {numeric.mean():,.4g}"
            )
        else:
            top = series.astype(str).value_counts().head(max_categorical_top)
            top_str = ", ".join(f"{k}({v})" for k, v in top.items())
            lines.append(
                f"- {col} ({dtype}): {unique} unique, null {null_pct:.1f}%, top: {top_str}"
            )
    return "\n".join(lines)
