export const inr = (v: number | null | undefined, compact = false) => {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  if (compact) {
    const a = Math.abs(v);
    if (a >= 1e7) return `₹${(v / 1e7).toFixed(2)} Cr`;
    if (a >= 1e5) return `₹${(v / 1e5).toFixed(2)} L`;
    if (a >= 1e3) return `₹${(v / 1e3).toFixed(1)}k`;
  }
  return "₹" + Math.round(v).toLocaleString("en-IN");
};
export const num = (v: number | null | undefined, d = 0) =>
  v === null || v === undefined || Number.isNaN(v) ? "—" : Number(v).toLocaleString("en-IN", { maximumFractionDigits: d, minimumFractionDigits: d });
export const pct = (v: number | null | undefined, d = 0) => (v === null || v === undefined || Number.isNaN(v) ? "—" : `${(v * 100).toFixed(d)}%`);
export const mult = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${v.toFixed(2)}×`);
export const day = (iso?: string | null) => {
  if (!iso) return "—";
  const d = new Date(iso.length <= 10 ? iso + "T00:00:00" : iso);
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short" });
};
export const dayTime = (iso?: string | null) => {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
};
export const titleCase = (s: string) => s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

export const AGENT_LABEL: Record<string, string> = {
  prediction: "Forecast agent",
  intelligence: "Product insights agent",
  prevention: "Prevention agent",
  logistics: "Pickup & warehouse agent",
  recovery: "Resale agent",
  governance: "Safety-check agent",
  orchestrator: "Coordinator",
};
export const AGENT_SHORT: Record<string, string> = {
  prediction: "Forecast", intelligence: "Insights", prevention: "Prevention", logistics: "Pickup & warehouse",
  recovery: "Resale", governance: "Safety checks", orchestrator: "Coordinator",
};
/** One-line description of each agent's job, in plain words. */
export const AGENT_JOB: Record<string, string> = {
  prediction: "Predicts how many returns will arrive in each city, day by day.",
  intelligence: "Reads why customers return things and spots products or sellers with a real problem.",
  prevention: "Suggests fixes that stop avoidable returns, like a corrected size chart.",
  logistics: "Checks whether pickup vans and warehouses can cope, and suggests where to send returns.",
  recovery: "Decides which returned items to check first so they can be resold before they lose value.",
  governance: "Checks every suggestion against the rules and sends important ones to a person to approve.",
};
export const AGENT_NO: Record<string, string> = { prediction: "01", intelligence: "02", prevention: "03", logistics: "04", recovery: "05", governance: "06" };

export const ROLE_LABEL: Record<string, string> = {
  ops_manager: "Operations Manager", vendor_quality_manager: "Seller Quality Manager", warehouse_manager: "Warehouse Manager",
  dispute_reviewer: "Return Checks", vendor: "Seller", logistics: "Delivery Partner", warehouse: "Inspection Team", customer: "Customer",
};

/** Plain names for the kinds of action the system can suggest. */
export const KIND_LABEL: Record<string, string> = {
  vendor_qc_hold: "Pause a seller for quality checks", pre_dispatch_qc: "Check items before they ship", size_chart_update: "Fix a size chart",
  listing_fix: "Fix product photos or description", exchange_first: "Offer a size swap before a refund", reroute: "Send returns to another warehouse",
  extra_pickup: "Add pickup vans", inspection_overtime: "Add an extra inspection shift", rapid_restock: "Put items back on sale quickly",
  refurbish_batch: "Repair and resell", redistribute: "Move stock to where it sells", integrity_inspection: "Double-check a return",
};

export const REASON_LABEL: Record<string, string> = {
  SIZE_SMALL: "Too small", SIZE_LARGE: "Too big", STITCHING: "Stitching problem", COLOUR_MISMATCH: "Colour looks different",
  FABRIC_QUALITY: "Fabric quality", NOT_AS_DESCRIBED: "Not as described", DAMAGED_IN_TRANSIT: "Damaged in delivery",
  CHANGED_MIND: "Changed mind", LATE_DELIVERY: "Arrived late",
};
export const reasonLabel = (r?: string) => (r ? REASON_LABEL[r] || r.replace(/_/g, " ").toLowerCase() : "");
