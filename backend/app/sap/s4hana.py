"""SAP S/4HANA adapters (read-only), using SAP's published OData V2 APIs.

Each entity maps to an API from the SAP Business Accelerator Hub:

    sales_orders      API_SALES_ORDER_SRV/A_SalesOrder
    customer_returns  API_CUSTOMER_RETURN_SRV/A_CustomerReturn
    products          API_PRODUCT_SRV/A_Product
    suppliers         API_BUSINESS_PARTNER/A_Supplier
    stock             API_MATERIAL_STOCK_SRV/A_MatlStkInAcctMod
    deliveries        API_OUTBOUND_DELIVERY_SRV;v=0002/A_OutbDeliveryHeader

How to connect (checked in this order):
  * SAP_S4_URL, the host part before /sap/opu/odata/sap/, for example
    https://my000000-api.s4hana.ondemand.com or, for the Business Accelerator Hub
    sandbox, https://sandbox.api.sap.com/s4hanacloud. Sign in with
    SAP_S4_API_KEY (Hub sandbox), SAP_S4_USER / SAP_S4_PASSWORD (communication
    user), or SAP_S4_TOKEN_URL / _CLIENT_ID / _CLIENT_SECRET (OAuth).
  * The SAP BTP Destination service, destination "reverseflow-s4".

When neither is set, the same calls are answered by a sandbox built from the
app's synthetic data, in the same OData shape. Every sandbox answer is marked
"source": "sandbox" and is never shown as data from S/4HANA.
"""
from __future__ import annotations

import os
import urllib.parse
from datetime import date, datetime, time

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as m
from . import btp, destinations

SYSTEM = "s4"
ODATA = "/sap/opu/odata/sap/"
ENTITIES = {
    "sales_orders": {"service": "API_SALES_ORDER_SRV", "set": "A_SalesOrder", "label": "Sales orders"},
    "customer_returns": {"service": "API_CUSTOMER_RETURN_SRV", "set": "A_CustomerReturn", "label": "Customer returns"},
    "products": {"service": "API_PRODUCT_SRV", "set": "A_Product", "label": "Products (materials)"},
    "suppliers": {"service": "API_BUSINESS_PARTNER", "set": "A_Supplier", "label": "Suppliers (sellers)"},
    "stock": {"service": "API_MATERIAL_STOCK_SRV", "set": "A_MatlStkInAcctMod", "label": "Stock by plant"},
    "deliveries": {"service": "API_OUTBOUND_DELIVERY_SRV;v=0002", "set": "A_OutbDeliveryHeader", "label": "Outbound deliveries"},
}
SANDBOX_LABEL = "Synthetic sandbox data in the S/4HANA API format. Not from an SAP S/4HANA system."


def configured() -> str | None:
    return destinations.configured(SYSTEM)


def sandbox_enabled() -> bool:
    return os.getenv("REVERSEFLOW_S4_SANDBOX", "1") == "1"


def path(entity: str) -> str:
    e = ENTITIES[entity]
    return f"{ODATA}{e['service']}/{e['set']}"


def fetch(db: Session, entity: str, top: int = 20, skip: int = 0) -> dict:
    """Records for one entity, from S/4HANA when connected, else from the sandbox."""
    if entity not in ENTITIES:
        raise KeyError(entity)
    top = max(1, min(top, 200))
    conn = destinations.resolve(SYSTEM) if configured() else None
    if conn:
        qs = urllib.parse.urlencode({"$top": top, "$skip": skip, "$format": "json"})
        code, body = btp.http_json("GET", conn.url.rstrip("/") + path(entity) + "?" + qs, headers=conn.headers, timeout=20)
        if code != 200 or not isinstance(body, dict):
            return {"entity": entity, "source": "s4hana", "ok": False, "http_status": code,
                    "error": body if isinstance(body, str) else (body or {}).get("error", body), "records": []}
        recs = (body.get("d") or {}).get("results", [])
        return {"entity": entity, "source": "s4hana", "ok": True, "via": conn.source, "api": path(entity), "records": recs}
    if not sandbox_enabled():
        return {"entity": entity, "source": "none", "ok": False, "records": [],
                "error": "S/4HANA is not connected and the sandbox is switched off (REVERSEFLOW_S4_SANDBOX=0)."}
    recs = sandbox_records(db, entity, top, skip)
    return {"entity": entity, "source": "sandbox", "ok": True, "label": SANDBOX_LABEL, "api": path(entity), "records": recs}


# ---------------- sandbox: synthetic data in the OData V2 shape ----------------
def _d(v) -> str | None:
    """OData V2 JSON date: /Date(ms since epoch)/."""
    if v is None:
        return None
    if isinstance(v, date) and not isinstance(v, datetime):
        v = datetime.combine(v, time())
    return f"/Date({int(v.timestamp() * 1000)})/"


def _amt(x) -> str:
    return f"{float(x or 0):.2f}"


def _meta(entity: str, key: str) -> dict:
    e = ENTITIES[entity]
    return {"__metadata": {"type": f"{e['service'].split(';')[0]}.{e['set']}Type", "uri": f"{path(entity)}('{key}')"}}


def sandbox_records(db: Session, entity: str, top: int = 20, skip: int = 0) -> list[dict]:
    if entity == "sales_orders":
        rows = db.scalars(select(m.Order).order_by(m.Order.order_date.desc(), m.Order.id).offset(skip).limit(top)).all()
        return [{**_meta(entity, o.id), "SalesOrder": o.id, "SalesOrderType": "OR", "SalesOrganization": "IN01",
                 "DistributionChannel": "10", "SoldToParty": o.customer_id, "SalesOrderDate": _d(o.order_date),
                 "TotalNetAmount": _amt(o.price), "TransactionCurrency": "INR",
                 "OverallSDProcessStatus": "C" if o.delivered_date else "A",
                 "OverallTotalDeliveryStatus": "C" if o.delivered_date else "A"} for o in rows]
    if entity == "customer_returns":
        rows = db.scalars(select(m.Return).order_by(m.Return.request_date.desc(), m.Return.id).offset(skip).limit(top)).all()
        return [{**_meta(entity, r.id), "CustomerReturn": r.id, "CustomerReturnType": "CBAR", "SalesOrganization": "IN01",
                 "SoldToParty": r.customer_id, "CustomerReturnDate": _d(r.request_date), "ReferenceSDDocument": r.order_id,
                 "SDDocumentReason": (r.verified_reason or r.predicted_reason or r.reason_category or "")[:3].upper(),
                 "TotalNetAmount": _amt(r.price), "TransactionCurrency": "INR"} for r in rows]
    if entity == "products":
        rows = db.scalars(select(m.Product).order_by(m.Product.sku).offset(skip).limit(top)).all()
        return [{**_meta(entity, p.sku), "Product": p.sku, "ProductType": "HAWA", "ProductGroup": p.category[:9].upper(),
                 "BaseUnit": "PC", "Division": "10", "IsMarkedForDeletion": False,
                 "to_Description": {"results": [{"Product": p.sku, "Language": "EN", "ProductDescription": p.name[:40]}]}} for p in rows]
    if entity == "suppliers":
        rows = db.scalars(select(m.Vendor).order_by(m.Vendor.id).offset(skip).limit(top)).all()
        return [{**_meta(entity, v.id), "Supplier": v.id, "SupplierName": v.name, "CreationDate": _d(v.onboarded),
                 "PurchasingIsBlocked": bool(v.qc_hold), "PostingIsBlocked": False} for v in rows]
    if entity == "stock":
        # Returned items by warehouse (plant): restocked = unrestricted (01), received but not yet inspected = quality inspection (02).
        q = (select(m.Return.sku, m.Return.facility_id, m.Return.restock_date.is_not(None), func.count())
             .where(m.Return.facility_id.is_not(None), m.Return.received_date.is_not(None))
             .group_by(m.Return.sku, m.Return.facility_id, m.Return.restock_date.is_not(None))
             .order_by(m.Return.facility_id, m.Return.sku).offset(skip).limit(top))
        return [{**_meta(entity, f"{sku}-{fac}-{'01' if done else '02'}"), "Material": sku, "Plant": fac, "StorageLocation": "RET1",
                 "InventoryStockType": "01" if done else "02", "MaterialBaseUnit": "PC",
                 "MatlWrhsStkQtyInMatlBaseUnit": f"{n:.3f}"} for sku, fac, done, n in db.execute(q).all()]
    if entity == "deliveries":
        rows = db.scalars(select(m.Order).where(m.Order.delivered_date.is_not(None))
                          .order_by(m.Order.delivered_date.desc(), m.Order.id).offset(skip).limit(top)).all()
        return [{**_meta(entity, "8" + o.id[-9:]), "DeliveryDocument": "8" + o.id[-9:], "DeliveryDocumentType": "LF",
                 "SoldToParty": o.customer_id, "ShipToParty": o.customer_id, "ShippingPoint": o.cluster_id,
                 "ActualGoodsMovementDate": _d(o.delivered_date), "OverallGoodsMovementStatus": "C",
                 "ReferenceSDDocument": o.id} for o in rows]
    raise KeyError(entity)
