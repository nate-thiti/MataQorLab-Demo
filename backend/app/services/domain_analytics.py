"""
Domain-specific KPI computation and semantic role inference from column names.
Works across sales, inventory, HR, manufacturing, marketing, finance, and more.
"""
import re
from typing import Dict, List, Optional

import pandas as pd

# Canonical role -> substrings matched in normalized column names (EN + TH)
ROLE_SIGNATURES: Dict[str, List[str]] = {
    "gross_amount": ["gross_amount", "gross_amt", "gross_total", "ยอดรวม"],
    "net_amount": ["net_amount", "net_amt", "net_total", "ยอดสุทธิ"],
    "sales": ["sales", "revenue", "ยอดขาย", "รายได้", "gmv", "total_amount", "income"],
    "cost": ["cost", "cogs", "ต้นทุน", "expense", "spend"],
    "profit": ["profit", "gross_profit", "net_profit", "ebit", "ebitda"],
    "margin": ["margin", "gross_margin", "contribution_margin"],
    "price": ["price", "unit_price", "average_selling_price", "asp"],
    "quantity": ["qty", "quantity", "units", "จำนวน", "volume", "pieces"],
    "date": ["date", "วันที่", "timestamp", "created_at", "order_date", "documentdate", "doc_date"],
    "branch": ["branch", "สาขา", "store", "outlet", "location"],
    "region": ["region", "territory", "geo", "area"],
    "country": ["country", "country_code", "nation"],
    "market": ["market", "marketplace"],
    "channel": ["channel", "sales_channel", "acquisition_channel", "source"],
    "customer_id": ["customer_id", "client_id", "account_id", "user_id", "member_id"],
    "customer": ["customer", "client", "account", "buyer"],
    "product": ["product", "สินค้า", "sku", "item", "item_name"],
    "category": ["category", "หมวด", "segment"],
    "supplier": ["supplier", "vendor", "ผู้จัดจำหน่าย"],
    "stock_level": ["stock", "inventory", "on_hand", "คงคลัง", "สต็อก"],
    "stock_in": ["stock_in", "inbound", "received", "รับเข้า"],
    "stock_out": ["stock_out", "outbound", "shipped", "จ่ายออก"],
    "department": ["department", "dept", "แผนก", "division"],
    "employee": ["employee", "staff", "worker", "พนักงาน", "emp_id"],
    "salary": ["salary", "payroll", "wage", "เงินเดือน", "compensation"],
    "tenure": ["tenure", "years_of_service", "อายุงาน", "service_years"],
    "status": ["status", "employment_status", "สถานะ", "active", "terminated"],
    "defects": ["defect", "scrap", "reject", "ของเสีย", "defects"],
    "output": ["output", "produced", "good_units", "yield_units", "ผลผลิต"],
    "downtime": ["downtime", "down_time", "เวลาหยุด"],
    "ad_spend": ["ad_spend", "ad_cost", "marketing_spend", "ค่าโฆษณา"],
    "clicks": ["clicks", "click", "คลิก"],
    "impressions": ["impressions", "impression", "การแสดงผล"],
    "satisfaction_score": ["nps", "csat", "satisfaction", "rating", "คะแนน"],
    "resolution_time": ["resolution_time", "resolve_time", "เวลาแก้ไข", "handle_time"],
    "lead_time": ["lead_time", "delivery_time", "ระยะเวลาส่ง"],
    "order_id": ["order_id", "order_no", "transaction_id", "เลขที่ออเดอร์", "so_no", "sono"],
    "document_no": ["documentno", "document_no", "doc_no", "เลขที่เอกสาร"],
    "invoice_id": ["invoice_id", "invoice_no", "inv_no"],
    "line_id": ["line_id", "line_no", "row_id", "rowid", "row1id"],
    "company_code": ["companycode", "company_code", "comp_code"],
    "credit_term": ["creditterm", "credit_term", "payment_term"],
    "currency": ["currency", "curr_code"],
    "exchange_rate": ["exchange_rate", "fx_rate"],
    "payment_status": ["payment_status", "paid_status", "สถานะชำระ"],
    "discount": ["discount", "ส่วนลด"],
    "tax": ["tax", "vat", "ภาษี"],
    "due_date": ["due_date", "duedate", "payment_due"],
    "warehouse": ["warehouse", "wh_code", "คลัง"],
    "unit": ["unit", "uom", "unit_of_measure"],
    "year": ["year", "ปี", "docyear", "doc_year"],
    "month": ["month", "เดือน", "docmonth", "doc_month"],
}


def _normalize_col(name: str) -> str:
    return re.sub(r"[^a-z0-9\u0e00-\u0e7f]+", "_", (name or "").strip().lower()).strip("_")


def _match_role(col_name: str) -> Optional[str]:
    norm = _normalize_col(col_name)
    for role, signatures in ROLE_SIGNATURES.items():
        for sig in signatures:
            if sig in norm or norm in sig:
                return role
    return None


def _roles_from_mapping(column_mapping: Dict[str, str]) -> Dict[str, str]:
    """Map user-defined column mapping to canonical roles (same rules as ChatService)."""
    role_to_col: Dict[str, str] = {}
    alias_map = {
        "sales": "sales",
        "revenue": "sales",
        "income": "sales",
        "gmv": "sales",
        "qty": "quantity",
        "quantity": "quantity",
        "date": "date",
        "timestamp": "timestamp",
        "branch": "branch",
        "product": "product",
        "category": "category",
        "cost": "cost",
        "expenses": "cost",
        "expense": "cost",
        "cogs": "cost",
        "supplier": "supplier",
        "stock_in": "stock_in",
        "stock_out": "stock_out",
        "stock_level": "stock_level",
        "inventory_level": "stock_level",
        "inventory": "stock_level",
        "department": "department",
        "employee": "employee",
        "salary": "salary",
        "tenure": "tenure",
        "status": "status",
        "defects": "defects",
        "defect": "defects",
        "output": "output",
        "downtime": "downtime",
        "ad_spend": "ad_spend",
        "clicks": "clicks",
        "impressions": "impressions",
        "satisfaction_score": "satisfaction_score",
        "nps": "satisfaction_score",
        "csat": "satisfaction_score",
        "resolution_time": "resolution_time",
        "lead_time": "lead_time",
        "order_id": "order_id",
        "customer": "customer",
    }
    for col_name, mapped_name in (column_mapping or {}).items():
        val = (mapped_name or "").strip().lower()
        if not val:
            continue
        role = alias_map.get(val, val)
        role_to_col[role] = col_name
    return role_to_col


def infer_semantic_roles(df: pd.DataFrame, column_mapping: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """
    Merge user column mapping with auto-detected roles from column names.
    Returns canonical_role -> original_column_name.
    """
    role_to_col = _roles_from_mapping(column_mapping or {})
    used_cols = set(role_to_col.values())

    for col in df.columns:
        if col in used_cols:
            continue
        detected = _match_role(str(col))
        if detected and detected not in role_to_col:
            role_to_col[detected] = col
            used_cols.add(col)

    return role_to_col


def infer_dataset_type(role_to_col: Dict[str, str]) -> str:
    """Suggest dataset classification from detected semantic roles."""
    roles = set(role_to_col.keys())
    if roles & {"defects", "output", "downtime"}:
        return "production_manufacturing"
    if roles & {"stock_level"} or ("stock_in" in roles and "stock_out" in roles):
        if "stock_in" in roles and "stock_out" in roles:
            return "warehouse_movement"
        return "inventory_snapshot"
    if roles & {"department", "salary", "tenure", "employee"}:
        return "human_resources"
    if roles & {"ad_spend", "clicks", "impressions"}:
        return "marketing_campaign"
    if roles & {"satisfaction_score", "resolution_time"}:
        return "customer_experience"
    if roles & {"supplier", "lead_time"} and "cost" in roles:
        return "procurement_purchasing"
    revenue_roles = {"sales", "gross_amount", "net_amount"}
    if "branch" in roles and roles & revenue_roles:
        return "branch_performance"
    if roles & (revenue_roles | {"cost"}) and not roles & {"ad_spend"}:
        if "cost" in roles:
            return "financial_accounting"
        return "sales_report"
    if roles & revenue_roles:
        return "sales_report"
    return "general_business_data"


def column_series(df: pd.DataFrame, col: Optional[str]) -> Optional[pd.Series]:
    """Return a 1-D series for a column (handles duplicate column labels in messy exports)."""
    if not col or col not in df.columns:
        return None
    data = df[col]
    if isinstance(data, pd.DataFrame):
        data = data.iloc[:, 0]
    return data


def _num_series(df: pd.DataFrame, col: Optional[str]) -> Optional[pd.Series]:
    series = column_series(df, col)
    if series is None:
        return None
    return pd.to_numeric(series, errors="coerce")


def compute_domain_kpis(df: pd.DataFrame, role_to_col: Dict[str, str]) -> List[str]:
    """Compute domain-specific KPIs when matching columns/roles are present."""
    notes: List[str] = []
    roles = role_to_col

    def col(role: str) -> Optional[str]:
        return roles.get(role)

    # --- Sales & Revenue ---
    sales_s = _num_series(df, col("sales"))
    qty_s = _num_series(df, col("quantity"))
    if sales_s is not None and qty_s is not None:
        total_sales = sales_s.sum()
        total_qty = qty_s.sum()
        if total_qty > 0:
            notes.append(f"- **AOV (Avg Order Value)**: {total_sales / total_qty:,.2f} (sales / quantity)")
    order_col = col("order_id")
    if sales_s is not None and order_col and order_col in df.columns:
        order_series = column_series(df, order_col)
        n_orders = order_series.nunique() if order_series is not None else 0
        if n_orders > 0:
            notes.append(f"- **Avg Sales per Order**: {sales_s.sum() / n_orders:,.2f} ({n_orders} unique orders)")

    # --- Financial ---
    cost_s = _num_series(df, col("cost"))
    if sales_s is not None and cost_s is not None:
        total_sales = sales_s.sum()
        total_cost = cost_s.sum()
        profit = total_sales - total_cost
        margin = (profit / total_sales * 100) if total_sales else 0
        notes.append(f"- **Gross Profit**: {profit:,.2f} | **Margin**: {margin:.2f}%")

    # --- Inventory ---
    stock_s = _num_series(df, col("stock_level"))
    if stock_s is not None and sales_s is not None:
        avg_stock = stock_s.mean()
        total_sales = sales_s.sum()
        if avg_stock > 0:
            notes.append(f"- **Inventory Turnover (approx)**: {total_sales / avg_stock:,.2f} (sales / avg stock)")
    stock_in_s = _num_series(df, col("stock_in"))
    stock_out_s = _num_series(df, col("stock_out"))
    if stock_in_s is not None and stock_out_s is not None:
        net = stock_in_s.sum() - stock_out_s.sum()
        notes.append(
            f"- **Warehouse Net Movement**: {net:,.2f} (in: {stock_in_s.sum():,.2f}, out: {stock_out_s.sum():,.2f})"
        )

    # --- HR ---
    dept_col = col("department")
    status_col = col("status")
    salary_s = _num_series(df, col("salary"))
    tenure_s = _num_series(df, col("tenure"))
    if dept_col and dept_col in df.columns:
        if salary_s is not None:
            by_dept = df.groupby(dept_col)[col("salary")].apply(lambda x: pd.to_numeric(x, errors="coerce").mean())
            top = by_dept.idxmax()
            notes.append(f"- **Avg Salary by Dept**: highest in **{top}** ({by_dept[top]:,.2f})")
        if tenure_s is not None:
            avg_tenure = tenure_s.mean()
            notes.append(f"- **Avg Tenure**: {avg_tenure:.2f} years/units")
        if status_col and status_col in df.columns:
            status_lower = df[status_col].astype(str).str.lower()
            left_mask = status_lower.str.contains(r"leave|left|terminated|resigned|ลาออก|พ้นสภาพ", regex=True)
            if left_mask.any():
                turnover = left_mask.sum() / len(df) * 100
                notes.append(f"- **Turnover Rate (row-based)**: {turnover:.2f}% ({left_mask.sum()} of {len(df)} records)")

    # --- Manufacturing ---
    defect_s = _num_series(df, col("defects"))
    output_s = _num_series(df, col("output"))
    if defect_s is not None and output_s is not None:
        total_out = output_s.sum()
        total_def = defect_s.sum()
        if total_out > 0:
            defect_rate = total_def / total_out * 100
            yield_rate = (total_out - total_def) / total_out * 100 if total_out >= total_def else 0
            notes.append(f"- **Defect Rate**: {defect_rate:.2f}% | **Yield Rate**: {yield_rate:.2f}%")
    downtime_s = _num_series(df, col("downtime"))
    if downtime_s is not None:
        notes.append(f"- **Total Downtime**: {downtime_s.sum():,.2f} | **Avg Downtime**: {downtime_s.mean():,.2f}")

    # --- Marketing ---
    ad_s = _num_series(df, col("ad_spend"))
    if ad_s is not None and sales_s is not None:
        spend = ad_s.sum()
        revenue = sales_s.sum()
        if spend > 0:
            notes.append(f"- **ROAS**: {revenue / spend:,.2f}x (revenue / ad spend)")
    clicks_s = _num_series(df, col("clicks"))
    imp_s = _num_series(df, col("impressions"))
    if clicks_s is not None and imp_s is not None:
        impressions = imp_s.sum()
        if impressions > 0:
            ctr = clicks_s.sum() / impressions * 100
            notes.append(f"- **CTR**: {ctr:.2f}% ({clicks_s.sum():,.0f} clicks / {impressions:,.0f} impressions)")

    # --- Customer Experience ---
    sat_s = _num_series(df, col("satisfaction_score"))
    if sat_s is not None:
        notes.append(f"- **Avg Satisfaction/NPS**: {sat_s.mean():.2f} (min {sat_s.min():.2f}, max {sat_s.max():.2f})")
    res_s = _num_series(df, col("resolution_time"))
    if res_s is not None:
        notes.append(f"- **Avg Resolution Time**: {res_s.mean():,.2f}")

    # --- Procurement ---
    sup_col = col("supplier")
    if sup_col and sup_col in df.columns and cost_s is not None:
        by_sup = df.groupby(sup_col)[col("cost")].apply(lambda x: pd.to_numeric(x, errors="coerce").sum())
        if not by_sup.empty:
            top_sup = by_sup.idxmax()
            notes.append(f"- **Top Supplier (by spend)**: **{top_sup}** ({by_sup[top_sup]:,.2f})")
    lead_s = _num_series(df, col("lead_time"))
    if lead_s is not None and sup_col and sup_col in df.columns:
        avg_lead = df.groupby(sup_col)[col("lead_time")].apply(lambda x: pd.to_numeric(x, errors="coerce").mean())
        if not avg_lead.empty:
            slowest = avg_lead.idxmax()
            notes.append(f"- **Slowest Supplier (lead time)**: **{slowest}** ({avg_lead[slowest]:,.2f})")

    return notes


def compute_domain_kpis_duckdb(handle: "DatasetHandle", role_to_col: Dict[str, str]) -> List[str]:
    """Compute domain KPIs on full dataset via DuckDB SQL (for large tables)."""
    from app.services.dataset_engine import DatasetHandle, _quote_ident

    if not isinstance(handle, DatasetHandle):
        return compute_domain_kpis(handle, role_to_col)

    notes: List[str] = []
    table = handle._table
    con = handle._con

    def col(role: str) -> Optional[str]:
        return role_to_col.get(role)

    def q(role: str) -> Optional[str]:
        c = col(role)
        return _quote_ident(c) if c else None

    def scalar(sql: str) -> Optional[float]:
        try:
            v = con.execute(sql).fetchone()[0]
            return float(v) if v is not None else None
        except Exception:
            return None

    sum_exprs: List[str] = []

    def add_sum(role: str, alias: str) -> None:
        col = q(role)
        if col:
            sum_exprs.append(f"SUM({col}) AS {alias}")

    for role, alias in (
        ("sales", "s_sales"),
        ("quantity", "s_qty"),
        ("cost", "s_cost"),
        ("stock_in", "s_stock_in"),
        ("stock_out", "s_stock_out"),
        ("defects", "s_defects"),
        ("output", "s_output"),
        ("downtime", "s_downtime"),
        ("ad_spend", "s_ad_spend"),
        ("clicks", "s_clicks"),
        ("impressions", "s_impressions"),
    ):
        add_sum(role, alias)

    order_q = q("order_id")
    if order_q:
        sum_exprs.append(f"COUNT(DISTINCT {order_q}) AS n_orders")

    stock_q = q("stock_level")
    if stock_q:
        sum_exprs.append(f"AVG({stock_q}) AS avg_stock")

    tenure_q = q("tenure")
    if tenure_q:
        sum_exprs.append(f"AVG({tenure_q}) AS avg_tenure")

    sat_q = q("satisfaction_score")
    if sat_q:
        sum_exprs.extend(
            [
                f"AVG({sat_q}) AS avg_sat",
                f"MIN({sat_q}) AS min_sat",
                f"MAX({sat_q}) AS max_sat",
            ]
        )

    res_q = q("resolution_time")
    if res_q:
        sum_exprs.append(f"AVG({res_q}) AS avg_res")

    downtime_q = q("downtime")
    if downtime_q:
        sum_exprs.append(f"AVG({downtime_q}) AS avg_downtime")

    agg: Dict[str, Optional[float]] = {}
    if sum_exprs:
        try:
            row = con.execute(f"SELECT {', '.join(sum_exprs)} FROM {table}").fetchone()
            cols = [part.split(" AS ")[-1] for part in sum_exprs]
            agg = {
                cols[i]: (float(row[i]) if row[i] is not None else None)
                for i in range(len(cols))
            }
        except Exception as e:
            print(f"Domain KPI batch aggregate failed: {e}")

    def agg_val(key: str) -> Optional[float]:
        return agg.get(key)

    sales_q, qty_q = q("sales"), q("quantity")
    if sales_q and qty_q:
        total_sales = agg_val("s_sales")
        total_qty = agg_val("s_qty")
        if total_sales is not None and total_qty and total_qty > 0:
            notes.append(f"- **AOV (Avg Order Value)**: {total_sales / total_qty:,.2f} (full dataset)")

    if sales_q and order_q:
        n_orders = agg_val("n_orders")
        total_sales = agg_val("s_sales")
        if n_orders and n_orders > 0 and total_sales is not None:
            notes.append(
                f"- **Avg Sales per Order**: {total_sales / n_orders:,.2f} ({int(n_orders)} unique orders, full dataset)"
            )

    cost_q = q("cost")
    if sales_q and cost_q:
        total_sales = agg_val("s_sales")
        total_cost = agg_val("s_cost")
        if total_sales is not None and total_cost is not None:
            profit = total_sales - total_cost
            margin = (profit / total_sales * 100) if total_sales else 0
            notes.append(f"- **Gross Profit**: {profit:,.2f} | **Margin**: {margin:.2f}% (full dataset)")

    if stock_q and sales_q:
        avg_stock = agg_val("avg_stock")
        total_sales = agg_val("s_sales")
        if avg_stock and avg_stock > 0 and total_sales is not None:
            notes.append(f"- **Inventory Turnover (approx)**: {total_sales / avg_stock:,.2f} (full dataset)")

    stock_in_q, stock_out_q = q("stock_in"), q("stock_out")
    if stock_in_q and stock_out_q:
        in_sum = agg_val("s_stock_in") or 0
        out_sum = agg_val("s_stock_out") or 0
        notes.append(f"- **Warehouse Net Movement**: {in_sum - out_sum:,.2f} (in: {in_sum:,.2f}, out: {out_sum:,.2f})")

    dept_q, salary_q, tenure_q, status_q = q("department"), q("salary"), q("tenure"), q("status")
    if dept_q and salary_q:
        row = con.execute(
            f"SELECT {dept_q}, AVG({salary_q}) AS avg_sal FROM {table} GROUP BY {dept_q} ORDER BY avg_sal DESC LIMIT 1"
        ).fetchone()
        if row:
            notes.append(f"- **Avg Salary by Dept**: highest in **{row[0]}** ({float(row[1]):,.2f}, full dataset)")

    if tenure_q:
        avg_t = agg_val("avg_tenure")
        if avg_t is not None:
            notes.append(f"- **Avg Tenure**: {avg_t:.2f} (full dataset)")

    if status_q:
        total = handle.row_count()
        left = scalar(
            f"SELECT COUNT(*) FROM {table} WHERE regexp_matches(CAST({status_q} AS VARCHAR), "
            f"'leave|left|terminated|resigned|ลาออก|พ้นสภาพ', 'i')"
        )
        if left and total:
            notes.append(f"- **Turnover Rate (row-based)**: {left / total * 100:.2f}% (full dataset)")

    defect_q, output_q = q("defects"), q("output")
    if defect_q and output_q:
        total_out = agg_val("s_output") or 0
        total_def = agg_val("s_defects") or 0
        if total_out > 0:
            defect_rate = total_def / total_out * 100
            yield_rate = (total_out - total_def) / total_out * 100 if total_out >= total_def else 0
            notes.append(f"- **Defect Rate**: {defect_rate:.2f}% | **Yield Rate**: {yield_rate:.2f}% (full dataset)")

    downtime_q = q("downtime")
    if downtime_q:
        total_dt = agg_val("s_downtime")
        avg_dt = agg_val("avg_downtime")
        if total_dt is not None and avg_dt is not None:
            notes.append(f"- **Total Downtime**: {total_dt:,.2f} | **Avg**: {avg_dt:,.2f} (full dataset)")

    ad_q = q("ad_spend")
    if ad_q and sales_q:
        spend = agg_val("s_ad_spend")
        revenue = agg_val("s_sales")
        if spend and spend > 0 and revenue is not None:
            notes.append(f"- **ROAS**: {revenue / spend:,.2f}x (full dataset)")

    clicks_q, imp_q = q("clicks"), q("impressions")
    if clicks_q and imp_q:
        clicks = agg_val("s_clicks") or 0
        impressions = agg_val("s_impressions") or 0
        if impressions > 0:
            notes.append(f"- **CTR**: {clicks / impressions * 100:.2f}% (full dataset)")

    sat_q = q("satisfaction_score")
    if sat_q:
        avg_sat = agg_val("avg_sat")
        min_sat = agg_val("min_sat")
        max_sat = agg_val("max_sat")
        if avg_sat is not None:
            notes.append(
                f"- **Avg Satisfaction/NPS**: {avg_sat:.2f} "
                f"(min {min_sat:.2f}, max {max_sat:.2f}, full dataset)"
            )

    res_q = q("resolution_time")
    if res_q:
        avg_res = agg_val("avg_res")
        if avg_res is not None:
            notes.append(f"- **Avg Resolution Time**: {avg_res:,.2f} (full dataset)")

    sup_q = q("supplier")
    if sup_q and cost_q:
        row = con.execute(
            f"SELECT {sup_q}, SUM({cost_q}) AS spend FROM {table} GROUP BY {sup_q} ORDER BY spend DESC LIMIT 1"
        ).fetchone()
        if row:
            notes.append(f"- **Top Supplier (by spend)**: **{row[0]}** ({float(row[1]):,.2f}, full dataset)")

    lead_q = q("lead_time")
    if lead_q and sup_q:
        row = con.execute(
            f"SELECT {sup_q}, AVG({lead_q}) AS avg_lead FROM {table} GROUP BY {sup_q} ORDER BY avg_lead DESC LIMIT 1"
        ).fetchone()
        if row:
            notes.append(f"- **Slowest Supplier (lead time)**: **{row[0]}** ({float(row[1]):,.2f}, full dataset)")

    return notes
