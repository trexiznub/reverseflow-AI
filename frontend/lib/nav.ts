import { Clock, Image as ImageIcon, PackageCheck as Restock, PauseCircle, Repeat, Route, Ruler, ScanSearch, SearchCheck, Shuffle, Truck as Van, Wrench } from "lucide-react";

import {
  BarChart3, Briefcase, Handshake, LayoutGrid, Network, PackageCheck, PackageOpen, Plug, RotateCcw, Scale, Settings2, ShieldCheck,
  ShoppingBag, Store, Target, TrendingUp, Truck, Warehouse, Workflow,
} from "lucide-react";

// Every page, with a plain name, an icon and the sidebar group it sits in.
export const NAV = [
  { id: "overview", href: "/", label: "Today", icon: LayoutGrid, group: "Work", desc: "What's happening and what needs you" },
  { id: "governance", href: "/governance", label: "Decisions", icon: ShieldCheck, group: "Work", desc: "Approve or decline suggested actions" },
  { id: "forecasting", href: "/forecasting", label: "Forecast", icon: TrendingUp, group: "Work", desc: "How many returns are coming, and where" },
  { id: "root-cause", href: "/root-cause", label: "Product issues", icon: Network, group: "Work", desc: "Why items come back, by product and seller" },
  { id: "recovery", href: "/recovery", label: "Resale", icon: RotateCcw, group: "Work", desc: "Get returned items back on sale" },
  { id: "case", href: "/case", label: "Why it matters", icon: Target, group: "Understand", desc: "The problem, the economics and the use of SAP" },
  { id: "analytics", href: "/analytics", label: "Reports", icon: BarChart3, group: "Understand", desc: "Key numbers and downloads" },
  { id: "agents", href: "/agents", label: "How it works", icon: Workflow, group: "Understand", desc: "See what each AI agent did" },
  { id: "customer", href: "/customer", label: "Customer app", icon: PackageOpen, group: "Apps", desc: "What a shopper sees" },
  { id: "partners", href: "/partners", label: "Partner app", icon: Handshake, group: "Apps", desc: "Sellers, delivery partners, warehouses" },
  { id: "sap", href: "/sap", label: "SAP", icon: Plug, group: "System", desc: "SAP connections, S/4HANA data and the outbox" },
  { id: "settings", href: "/settings", label: "Settings", icon: Settings2, group: "System", desc: "Assumptions, limits and demo reset" },
];
export const NAV_GROUPS = ["Work", "Understand", "Apps", "System"];

export const navFor = (path: string) =>
  NAV.find((n) => (n.href === "/" ? path === "/" : path.startsWith(n.href)));

/** Where each kind of person starts. */
export function homeFor(role?: string) {
  if (role === "customer") return "/customer";
  if (role && ["vendor", "logistics", "warehouse"].includes(role)) return "/partners";
  if (role === "dispute_reviewer") return "/governance";
  return "/";
}

export const ROLE_ICON: Record<string, any> = {
  ops_manager: Briefcase, vendor_quality_manager: ShieldCheck, warehouse_manager: Warehouse, dispute_reviewer: Scale,
  vendor: Store, logistics: Truck, warehouse: PackageCheck, customer: ShoppingBag,
};

/** One line on what each person does in the app. */
export const ROLE_DOES: Record<string, string> = {
  ops_manager: "Runs the returns network. Approves vans, routing and spend.",
  vendor_quality_manager: "Finds sellers and products that cause returns, and approves fixes.",
  warehouse_manager: "Plans inspection shifts and gets items back on sale.",
  dispute_reviewer: "Reviews returns that don't look right. Never refuses automatically.",
  vendor: "Sees only their own products, returns and fix requests.",
  logistics: "Collects returns from customers and records the pickup.",
  warehouse: "Receives, inspects and grades returned items.",
  customer: "Returns or exchanges an order and follows it to the refund.",
};

export const PERSON_GROUPS: { label: string; roles: string[] }[] = [
  { label: "Marketplace team", roles: ["ops_manager", "vendor_quality_manager", "warehouse_manager", "dispute_reviewer"] },
  { label: "Partners", roles: ["vendor", "logistics", "warehouse"] },
  { label: "Customers", roles: ["customer"] },
];

/** An icon for each kind of suggested action. */
export const KIND_ICON: Record<string, any> = {
  vendor_qc_hold: PauseCircle, pre_dispatch_qc: ScanSearch, size_chart_update: Ruler, listing_fix: ImageIcon, exchange_first: Repeat,
  reroute: Route, extra_pickup: Van, inspection_overtime: Clock, rapid_restock: Restock, refurbish_batch: Wrench, redistribute: Shuffle,
  integrity_inspection: SearchCheck,
};
