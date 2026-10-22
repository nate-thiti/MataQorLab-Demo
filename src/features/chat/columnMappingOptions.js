/**
 * Canonical semantic column roles aligned with backend domain_analytics.py
 * Values are sent as column_mapping and drive domain KPIs + question-aware analytics.
 */
import { t } from '../../utils/i18n.js';

export const SEMANTIC_ROLE_VALUES = [
  'sales', 'cost', 'quantity', 'price', 'discount', 'profit', 'tax', 'budget', 'expenses',
  'gross_amount', 'net_amount', 'margin', 'discount_rate', 'tax_rate',
  'qty', 'stock_in', 'stock_out', 'stock_level', 'weight', 'shipping_fee', 'lead_time',
  'warehouse', 'unit',
  'branch', 'product', 'category', 'supplier', 'customer', 'employee', 'department', 'project',
  'salary', 'tenure', 'status',
  'date', 'timestamp', 'year', 'month', 'quarter', 'due_date',
  'defects', 'output', 'downtime',
  'ad_spend', 'clicks', 'impressions',
  'satisfaction_score', 'resolution_time',
  'order_id', 'document_no', 'invoice_id', 'line_id', 'company_code',
  'credit_term', 'currency', 'exchange_rate', 'payment_status',
  'region', 'country', 'description', 'remark',
  'email', 'phone', 'created_by',
];

/** Substring signatures for auto-detect (mirrors backend ROLE_SIGNATURES) */
const ROLE_SIGNATURES = [
  { role: 'sales', signs: ['sales', 'revenue', 'ยอดขาย', 'รายได้', 'gmv', 'total_amount', 'income', 'amount'] },
  { role: 'gross_amount', signs: ['gross_amount', 'gross_amt', 'gross_total', 'ยอดรวม'] },
  { role: 'net_amount', signs: ['net_amount', 'net_amt', 'net_total', 'ยอดสุทธิ'] },
  { role: 'margin', signs: ['margin', 'profit_margin', 'กำไรขั้นต้น'] },
  { role: 'cost', signs: ['cost', 'cogs', 'ต้นทุน', 'expense', 'spend', 'expenses'] },
  { role: 'quantity', signs: ['qty', 'quantity', 'units', 'จำนวน', 'volume', 'pieces'] },
  { role: 'date', signs: ['date', 'วันที่', 'order_date', 'documentdate', 'doc_date'] },
  { role: 'due_date', signs: ['due_date', 'duedate', 'payment_due', 'วันครบกำหนด'] },
  { role: 'timestamp', signs: ['timestamp', 'created_at', 'datetime', 'updated_at'] },
  { role: 'document_no', signs: ['documentno', 'document_no', 'doc_no', 'เลขที่เอกสาร'] },
  { role: 'order_id', signs: ['order_id', 'order_no', 'transaction_id', 'เลขที่ออเดอร์', 'so_no', 'sono'] },
  { role: 'invoice_id', signs: ['invoice_id', 'invoice_no', 'inv_no', 'เลขที่ใบแจ้งหนี้'] },
  { role: 'line_id', signs: ['line_id', 'line_no', 'row_id', 'rowid', 'row1id'] },
  { role: 'company_code', signs: ['companycode', 'company_code', 'comp_code', 'รหัสบริษัท'] },
  { role: 'credit_term', signs: ['creditterm', 'credit_term', 'payment_term', 'เครดิตเทอม'] },
  { role: 'currency', signs: ['currency', 'curr_code', 'สกุลเงิน'] },
  { role: 'exchange_rate', signs: ['exchange_rate', 'fx_rate', 'rate', 'อัตราแลกเปลี่ยน'] },
  { role: 'payment_status', signs: ['payment_status', 'paid_status', 'สถานะชำระ'] },
  { role: 'branch', signs: ['branch', 'สาขา', 'store', 'outlet', 'location'] },
  { role: 'warehouse', signs: ['warehouse', 'wh_code', 'คลัง', 'storage'] },
  { role: 'product', signs: ['product', 'สินค้า', 'sku', 'item', 'item_name', 'material'] },
  { role: 'category', signs: ['category', 'หมวด', 'segment'] },
  { role: 'unit', signs: ['unit', 'uom', 'unit_of_measure', 'หน่วย'] },
  { role: 'supplier', signs: ['supplier', 'vendor', 'ผู้จัดจำหน่าย'] },
  { role: 'customer', signs: ['customer', 'client', 'ลูกค้า', 'cust_code', 'customer_code'] },
  { role: 'stock_level', signs: ['stock_level', 'inventory_level', 'inventory', 'on_hand', 'คงคลัง', 'สต็อก'] },
  { role: 'stock_in', signs: ['stock_in', 'inbound', 'received', 'รับเข้า'] },
  { role: 'stock_out', signs: ['stock_out', 'outbound', 'shipped', 'จ่ายออก'] },
  { role: 'department', signs: ['department', 'dept', 'แผนก', 'division'] },
  { role: 'employee', signs: ['employee', 'staff', 'worker', 'พนักงาน', 'emp_id'] },
  { role: 'salary', signs: ['salary', 'payroll', 'wage', 'เงินเดือน', 'compensation'] },
  { role: 'tenure', signs: ['tenure', 'years_of_service', 'อายุงาน', 'service_years'] },
  { role: 'status', signs: ['status', 'employment_status', 'สถานะ', 'doc_status'] },
  { role: 'defects', signs: ['defect', 'scrap', 'reject', 'ของเสีย', 'defects'] },
  { role: 'output', signs: ['output', 'produced', 'good_units', 'yield_units', 'ผลผลิต'] },
  { role: 'downtime', signs: ['downtime', 'down_time', 'เวลาหยุด'] },
  { role: 'ad_spend', signs: ['ad_spend', 'ad_cost', 'marketing_spend', 'ค่าโฆษณา'] },
  { role: 'clicks', signs: ['clicks', 'click', 'คลิก'] },
  { role: 'impressions', signs: ['impressions', 'impression', 'การแสดงผล'] },
  { role: 'satisfaction_score', signs: ['nps', 'csat', 'satisfaction', 'rating', 'คะแนน'] },
  { role: 'resolution_time', signs: ['resolution_time', 'resolve_time', 'เวลาแก้ไข', 'handle_time'] },
  { role: 'lead_time', signs: ['lead_time', 'delivery_time', 'ระยะเวลาส่ง'] },
  { role: 'price', signs: ['price', 'unit_price', 'ราคา'] },
  { role: 'year', signs: ['year', 'ปี', 'docyear', 'doc_year'] },
  { role: 'month', signs: ['month', 'เดือน', 'docmonth', 'doc_month'] },
  { role: 'quarter', signs: ['quarter', 'ไตรมาส'] },
  { role: 'region', signs: ['region', 'ภูมิภาค', 'zone'] },
  { role: 'country', signs: ['country', 'ประเทศ', 'nation'] },
  { role: 'description', signs: ['description', 'desc', 'รายละเอียด', 'item_desc'] },
  { role: 'remark', signs: ['remark', 'note', 'notes', 'comment', 'หมายเหตุ'] },
  { role: 'email', signs: ['email', 'e_mail', 'อีเมล'] },
  { role: 'phone', signs: ['phone', 'mobile', 'tel', 'โทรศัพท์'] },
  { role: 'created_by', signs: ['created_by', 'creator', 'ผู้สร้าง', 'user_id'] },
  { role: 'discount', signs: ['discount', 'ส่วนลด'] },
  { role: 'tax', signs: ['tax', 'vat', 'ภาษี'] },
];

function normalizeCol(name) {
  return (name || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9\u0e00-\u0e7f]+/g, '_')
    .replace(/^_+|_+$/g, '');
}

/** Suggest canonical semantic role from a file column header */
export function suggestSemanticRole(header) {
  const norm = normalizeCol(header);
  if (!norm) return '';
  for (const { role, signs } of ROLE_SIGNATURES) {
    for (const sig of signs) {
      if (norm.includes(sig) || sig.includes(norm)) {
        return role;
      }
    }
  }
  return '';
}

function roleLabel(messages, roleKey) {
  return t(messages, `chat.mapping.roles.${roleKey}`, roleKey);
}

function groupLabel(messages, groupKey, fallback) {
  return t(messages, `chat.mapping.groups.${groupKey}`, fallback);
}

export function buildMappingOptionGroups(messages) {
  return [
    {
      group: groupLabel(messages, 'identifiers', 'IDs & document keys'),
      items: [
        { value: 'order_id', label: roleLabel(messages, 'order_id') },
        { value: 'document_no', label: roleLabel(messages, 'document_no') },
        { value: 'invoice_id', label: roleLabel(messages, 'invoice_id') },
        { value: 'line_id', label: roleLabel(messages, 'line_id') },
        { value: 'company_code', label: roleLabel(messages, 'company_code') },
      ],
    },
    {
      group: groupLabel(messages, 'financials', 'Financials & Sales'),
      items: [
        { value: 'sales', label: roleLabel(messages, 'sales') },
        { value: 'gross_amount', label: roleLabel(messages, 'gross_amount') },
        { value: 'net_amount', label: roleLabel(messages, 'net_amount') },
        { value: 'cost', label: roleLabel(messages, 'cost') },
        { value: 'quantity', label: roleLabel(messages, 'quantity') },
        { value: 'price', label: roleLabel(messages, 'price') },
        { value: 'discount', label: roleLabel(messages, 'discount') },
        { value: 'discount_rate', label: roleLabel(messages, 'discount_rate') },
        { value: 'profit', label: roleLabel(messages, 'profit') },
        { value: 'margin', label: roleLabel(messages, 'margin') },
        { value: 'tax', label: roleLabel(messages, 'tax') },
        { value: 'tax_rate', label: roleLabel(messages, 'tax_rate') },
        { value: 'budget', label: roleLabel(messages, 'budget') },
        { value: 'expenses', label: roleLabel(messages, 'expenses') },
      ],
    },
    {
      group: groupLabel(messages, 'commerce', 'Commerce & payment'),
      items: [
        { value: 'credit_term', label: roleLabel(messages, 'credit_term') },
        { value: 'currency', label: roleLabel(messages, 'currency') },
        { value: 'exchange_rate', label: roleLabel(messages, 'exchange_rate') },
        { value: 'payment_status', label: roleLabel(messages, 'payment_status') },
        { value: 'due_date', label: roleLabel(messages, 'due_date') },
      ],
    },
    {
      group: groupLabel(messages, 'inventory', 'Inventory & Logistics'),
      items: [
        { value: 'stock_in', label: roleLabel(messages, 'stock_in') },
        { value: 'stock_out', label: roleLabel(messages, 'stock_out') },
        { value: 'stock_level', label: roleLabel(messages, 'stock_level') },
        { value: 'warehouse', label: roleLabel(messages, 'warehouse') },
        { value: 'unit', label: roleLabel(messages, 'unit') },
        { value: 'weight', label: roleLabel(messages, 'weight') },
        { value: 'shipping_fee', label: roleLabel(messages, 'shipping_fee') },
        { value: 'lead_time', label: roleLabel(messages, 'lead_time') },
      ],
    },
    {
      group: groupLabel(messages, 'hr', 'HR & People'),
      items: [
        { value: 'department', label: roleLabel(messages, 'department') },
        { value: 'employee', label: roleLabel(messages, 'employee') },
        { value: 'salary', label: roleLabel(messages, 'salary') },
        { value: 'tenure', label: roleLabel(messages, 'tenure') },
        { value: 'status', label: roleLabel(messages, 'status') },
      ],
    },
    {
      group: groupLabel(messages, 'manufacturing', 'Manufacturing & Quality'),
      items: [
        { value: 'defects', label: roleLabel(messages, 'defects') },
        { value: 'output', label: roleLabel(messages, 'output') },
        { value: 'downtime', label: roleLabel(messages, 'downtime') },
      ],
    },
    {
      group: groupLabel(messages, 'marketing', 'Marketing & Ads'),
      items: [
        { value: 'ad_spend', label: roleLabel(messages, 'ad_spend') },
        { value: 'clicks', label: roleLabel(messages, 'clicks') },
        { value: 'impressions', label: roleLabel(messages, 'impressions') },
      ],
    },
    {
      group: groupLabel(messages, 'customer_experience', 'Customer Experience'),
      items: [
        { value: 'satisfaction_score', label: roleLabel(messages, 'satisfaction_score') },
        { value: 'resolution_time', label: roleLabel(messages, 'resolution_time') },
      ],
    },
    {
      group: groupLabel(messages, 'entities', 'Entities & Organization'),
      items: [
        { value: 'branch', label: roleLabel(messages, 'branch') },
        { value: 'product', label: roleLabel(messages, 'product') },
        { value: 'category', label: roleLabel(messages, 'category') },
        { value: 'supplier', label: roleLabel(messages, 'supplier') },
        { value: 'customer', label: roleLabel(messages, 'customer') },
        { value: 'project', label: roleLabel(messages, 'project') },
        { value: 'region', label: roleLabel(messages, 'region') },
        { value: 'country', label: roleLabel(messages, 'country') },
      ],
    },
    {
      group: groupLabel(messages, 'contact', 'Contact & audit'),
      items: [
        { value: 'email', label: roleLabel(messages, 'email') },
        { value: 'phone', label: roleLabel(messages, 'phone') },
        { value: 'created_by', label: roleLabel(messages, 'created_by') },
      ],
    },
    {
      group: groupLabel(messages, 'text', 'Text & notes'),
      items: [
        { value: 'description', label: roleLabel(messages, 'description') },
        { value: 'remark', label: roleLabel(messages, 'remark') },
      ],
    },
    {
      group: groupLabel(messages, 'time', 'Time dimensions'),
      items: [
        { value: 'date', label: roleLabel(messages, 'date') },
        { value: 'timestamp', label: roleLabel(messages, 'timestamp') },
        { value: 'year', label: roleLabel(messages, 'year') },
        { value: 'month', label: roleLabel(messages, 'month') },
        { value: 'quarter', label: roleLabel(messages, 'quarter') },
      ],
    },
  ];
}

export function countMappedColumns(mapping) {
  if (!mapping) return 0;
  return Object.values(mapping).filter((v) => (v || '').trim()).length;
}
