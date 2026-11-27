using { vendors, products, facilities, facility_daily, logistics_providers, orders, ![returns], recommendations, decision_log, audit_log } from '../db/schema';

// Roles come from XSUAA scopes (xs-security.json) on BTP, and from the mocked
// users in package.json locally. "Internal" means the four ReverseFlow staff roles.
@path    : '/odata/v4/business'
@requires: 'authenticated-user'
service BusinessService {

  // ---------------- master and transaction data (read-only) ----------------
  @readonly
  @requires: ['OpsManager', 'VendorQuality', 'WarehouseManager', 'DisputeReviewer', 'Admin']
  entity Orders              as projection on orders excluding { is_synthetic };

  @readonly
  @restrict: [
    { grant: 'READ', to: ['OpsManager', 'VendorQuality', 'WarehouseManager', 'DisputeReviewer', 'Admin'] },
    { grant: 'READ', to: 'Vendor', where: 'vendor_id = $user.scope_id' }
  ]
  entity Returns             as projection on ![returns] {
    *, product : redirected to Products, vendor : redirected to Vendors
  } excluding { customer_id, is_synthetic };

  @readonly
  @restrict: [
    { grant: 'READ', to: ['OpsManager', 'VendorQuality', 'WarehouseManager', 'DisputeReviewer', 'Admin'] },
    { grant: 'READ', to: 'Vendor', where: 'id = $user.scope_id' }
  ]
  entity Vendors             as projection on vendors;

  @readonly
  @restrict: [
    { grant: 'READ', to: ['OpsManager', 'VendorQuality', 'WarehouseManager', 'DisputeReviewer', 'Admin'] },
    { grant: 'READ', to: 'Vendor', where: 'vendor_id = $user.scope_id' }
  ]
  entity Products            as projection on products { *, vendor : redirected to Vendors };

  @readonly
  @requires: ['OpsManager', 'WarehouseManager', 'Logistics', 'Admin']
  entity LogisticsPartners   as projection on logistics_providers;

  @readonly
  @requires: ['OpsManager', 'WarehouseManager', 'WarehousePartner', 'Admin']
  entity Warehouses          as projection on facilities;

  @readonly
  @requires: ['OpsManager', 'WarehouseManager', 'Admin']
  entity WarehouseLoad       as projection on facility_daily;

  // Returned stock by product and warehouse (computed in business-service.js).
  @readonly
  @cds.persistence.skip
  @requires: ['OpsManager', 'WarehouseManager', 'Admin']
  entity Inventory {
    key sku               : String(24);
    key facility_id       : String(16);
        received          : Integer;
        awaiting_check    : Integer;
        back_on_sale      : Integer;
        recovered_value   : Double;
  }

  // ---------------- decisions: approval goes through the FastAPI backend ----------------
  // The approval rules (who may approve what, money limits, audit, SAP outbox) live
  // in one place, the backend. These actions forward the signed-in user's request.
  @readonly
  @requires: ['OpsManager', 'VendorQuality', 'WarehouseManager', 'DisputeReviewer', 'Admin']
  entity Decisions           as projection on recommendations
    actions {
      action approve(reason : String) returns DecisionResult;
      action reject(reason : String)  returns DecisionResult;
      action escalate(reason : String) returns DecisionResult;
    };

  @readonly
  @requires: ['OpsManager', 'VendorQuality', 'Admin']
  entity CorrectiveActions   as projection on recommendations
    where kind in ('vendor_qc_hold', 'pre_dispatch_qc', 'size_chart_update', 'listing_fix');

  @readonly
  @requires: ['OpsManager', 'VendorQuality', 'WarehouseManager', 'DisputeReviewer', 'Admin']
  entity Approvals           as projection on decision_log;

  @readonly
  @requires: ['OpsManager', 'Admin']
  entity AuditLogs           as projection on audit_log;

  // ---------------- AI results, computed by the FastAPI backend ----------------
  type DecisionResult {
    id     : String;
    status : String;
    detail : String;
  }

  type VendorScore {
    vendor_id      : String;
    name           : String;
    city           : String;
    orders         : Integer;
    returns        : Integer;
    return_rate    : Double;
    defect_rate    : Double;
    avoidable_rate : Double;
    quality_score  : Double;
    qc_hold        : Boolean;
  }

  @requires: ['OpsManager', 'VendorQuality', 'Admin']
  function vendorPerformance(window : Integer) returns array of VendorScore;
}

// Resolve these projections at runtime (cds.features.runtime_views) instead of
// creating database views, so CAP adds nothing to the backend's schema.
annotate BusinessService.Orders            with @cds.persistence.skip;
annotate BusinessService.Returns           with @cds.persistence.skip;
annotate BusinessService.Vendors           with @cds.persistence.skip;
annotate BusinessService.Products          with @cds.persistence.skip;
annotate BusinessService.LogisticsPartners with @cds.persistence.skip;
annotate BusinessService.Warehouses        with @cds.persistence.skip;
annotate BusinessService.WarehouseLoad     with @cds.persistence.skip;
annotate BusinessService.Decisions         with @cds.persistence.skip;
annotate BusinessService.CorrectiveActions with @cds.persistence.skip;
annotate BusinessService.Approvals         with @cds.persistence.skip;
annotate BusinessService.AuditLogs         with @cds.persistence.skip;
