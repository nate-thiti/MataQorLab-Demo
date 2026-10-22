import io
from typing import Optional

import pandas as pd

_PREVIEW_SCAN_ROWS = 25
_HEADER_SCAN_ROWS = 25


def _estimate_csv_row_count(file_content: bytes) -> int:
    if not file_content:
        return 0
    return max(0, file_content.count(b"\n") - 1)


def _score_header_row(row: pd.Series, next_row: Optional[pd.Series] = None) -> float:
    values = [v for v in row.tolist() if pd.notna(v) and str(v).strip()]
    if not values:
        return -1.0
    labels = [str(v).strip() for v in values]
    unique_ratio = len(set(labels)) / max(len(labels), 1)
    text_ratio = sum(any(ch.isalpha() or ch == "_" for ch in label) for label in labels) / len(labels)
    unnamed_penalty = sum(label.lower().startswith("unnamed") for label in labels)
    score = len(labels) * 2.0 + unique_ratio * 3.0 + text_ratio * 2.0 - unnamed_penalty * 4.0
    if next_row is not None:
        next_values = [v for v in next_row.tolist() if pd.notna(v) and str(v).strip()]
        if len(next_values) >= max(1, len(labels) // 2):
            score += 2.0
    return score


def detect_header_row_from_frame(frame: pd.DataFrame) -> int:
    """Pick the most likely header row from a no-header preview frame."""
    if frame is None or frame.empty:
        return 0
    best_idx = 0
    best_score = -1.0
    for pos, (_, row) in enumerate(frame.iterrows()):
        next_row = frame.iloc[pos + 1] if pos + 1 < len(frame) else None
        score = _score_header_row(row, next_row)
        if score > best_score:
            best_score = score
            best_idx = pos
    return int(best_idx)


def _score_sheet_preview(frame: pd.DataFrame) -> float:
    """Score a sheet preview so empty cover sheets lose to real data sheets."""
    if frame is None or frame.empty:
        return -1.0
    non_empty = frame.dropna(how="all").dropna(axis=1, how="all")
    if non_empty.empty:
        return -1.0
    header_idx = detect_header_row_from_frame(frame)
    header_row = frame.iloc[header_idx] if header_idx < len(frame) else frame.iloc[0]
    next_row = frame.iloc[header_idx + 1] if header_idx + 1 < len(frame) else None
    data_rows = max(0, len(non_empty) - header_idx - 1)
    non_empty_cells = int(non_empty.count().sum())
    return (
        _score_header_row(header_row, next_row)
        + min(data_rows, 10) * 2.0
        + min(non_empty_cells, 80) * 0.1
    )


def select_excel_sheet_from_path(path: str) -> Optional[str]:
    """Return the sheet that most likely contains tabular data."""
    try:
        workbook = pd.ExcelFile(path)
        best_sheet = None
        best_score = -1.0
        for sheet_name in workbook.sheet_names:
            try:
                preview = pd.read_excel(
                    workbook,
                    sheet_name=sheet_name,
                    header=None,
                    nrows=_HEADER_SCAN_ROWS,
                )
            except Exception:
                continue
            score = _score_sheet_preview(preview)
            if score > best_score:
                best_score = score
                best_sheet = sheet_name
        return best_sheet
    except Exception:
        return None


def select_excel_sheet_from_bytes(file_content: bytes) -> Optional[str]:
    """Return the sheet that most likely contains tabular data."""
    try:
        workbook = pd.ExcelFile(io.BytesIO(file_content))
        best_sheet = None
        best_score = -1.0
        for sheet_name in workbook.sheet_names:
            try:
                preview = pd.read_excel(
                    workbook,
                    sheet_name=sheet_name,
                    header=None,
                    nrows=_HEADER_SCAN_ROWS,
                )
            except Exception:
                continue
            score = _score_sheet_preview(preview)
            if score > best_score:
                best_score = score
                best_sheet = sheet_name
        return best_sheet
    except Exception:
        return None


def detect_header_row_from_path(path: str, filename: str) -> int:
    ext = filename.split(".")[-1].lower()
    try:
        if ext in ["xlsx", "xls"]:
            preview = pd.read_excel(
                path,
                sheet_name=select_excel_sheet_from_path(path),
                header=None,
                nrows=_HEADER_SCAN_ROWS,
            )
        else:
            preview = pd.read_csv(path, header=None, nrows=_HEADER_SCAN_ROWS)
        return detect_header_row_from_frame(preview)
    except Exception:
        return 0


def detect_header_row_from_bytes(file_content: bytes, filename: str) -> int:
    file_ext = filename.split(".")[-1].lower()
    try:
        if file_ext in ["xlsx", "xls"]:
            preview = pd.read_excel(
                io.BytesIO(file_content),
                sheet_name=select_excel_sheet_from_bytes(file_content),
                header=None,
                nrows=_HEADER_SCAN_ROWS,
            )
        else:
            preview = pd.read_csv(io.BytesIO(file_content), header=None, nrows=_HEADER_SCAN_ROWS)
        return detect_header_row_from_frame(preview)
    except Exception:
        return 0


def detect_and_parse_table(file_content: bytes, filename: str):
    file_ext = filename.split(".")[-1].lower()

    if file_ext in ["xlsx", "xls"]:
        sheet_name = select_excel_sheet_from_bytes(file_content)
        df_raw = pd.read_excel(
            io.BytesIO(file_content),
            sheet_name=sheet_name,
            header=None,
            nrows=_PREVIEW_SCAN_ROWS,
        )
    else:
        sheet_name = None
        df_raw = pd.read_csv(io.BytesIO(file_content), header=None, nrows=_PREVIEW_SCAN_ROWS)

    header_idx = detect_header_row_from_frame(df_raw)

    if file_ext in ["xlsx", "xls"]:
        df = pd.read_excel(
            io.BytesIO(file_content),
            sheet_name=sheet_name,
            skiprows=header_idx,
            nrows=_PREVIEW_SCAN_ROWS,
        )
        row_estimate = len(df)
    else:
        df = pd.read_csv(io.BytesIO(file_content), skiprows=header_idx, nrows=_PREVIEW_SCAN_ROWS)
        row_estimate = _estimate_csv_row_count(file_content)

    df = df.dropna(how="all").dropna(axis=1, how="all")

    return {
        "header_row": header_idx,
        "columns": df.columns.tolist(),
        "preview": df.head(5).to_dict(orient="records"),
        "shape": (row_estimate, len(df.columns)),
    }


def handle_merged_cells(df):
    from app.services.data_cleaning import clean_dataframe

    _, cleaned = clean_dataframe(df)
    return cleaned
