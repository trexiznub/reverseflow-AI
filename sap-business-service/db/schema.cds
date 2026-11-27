// ReverseFlow tables, as created by the FastAPI backend (backend/app/models.py).
//
// CAP reads and writes the SAME tables as the backend (SQLite locally, the same
// SAP HANA Cloud schema on BTP), so no data is copied and no business rule is
// written twice. @cds.persistence.exists tells CAP not to create or drop them.
// Entity names deliberately match the table names (no namespace), and element
// names match the column names.

type Id : String(24);

@cds.persistence.exists
entity vendors {
  key id           : String(16);
      name         : String(120);
      city         : String(60);
      onboarded    : Date;
      specialty    : String(60);
      qc_hold      : Boolean;
      is_synthetic : Boolean;
}

@cds.persistence.exists
entity products {
  key sku                : String(24);
      name               : String(160);
      category           : String(40);
      vendor_id          : String(16);
      vendor             : Association to vendors on vendor.id = vendor_id;
      price              : Double;
      fabric             : String(40);
      colour             : String(40);
      season             : String(40);
      size_chart_version : Integer;
      pre_dispatch_qc    : Boolean;
      exchange_first     : Boolean;
      is_synthetic       : Boolean;
}

@cds.persistence.exists
entity pin_clusters {
  key id                    : String(16);
      city                  : String(60);
      state                 : String(60);
      pin_prefix            : String(8);
      lat                   : Double;
      lon                   : Double;
      network_daily_returns : Integer;
      default_facility_id   : String(16);
      is_synthetic          : Boolean;
}

@cds.persistence.exists
entity facilities {
  key id                  : String(16);
      name                : String(120);
      city                : String(60);
      lat                 : Double;
      lon                 : Double;
      kind                : String(30);
      inspection_capacity : Integer;
      storage_capacity    : Integer;
      normal_load         : Integer;
      handling_cost       : Double;
      is_synthetic        : Boolean;
}

@cds.persistence.exists
entity facility_daily {
  key id          : Integer;
      facility_id : String(16);
      day         : Date;
      inbound     : Integer;
      processed   : Integer;
      backlog     : Integer;
      utilisation : Double;
}

@cds.persistence.exists
entity logistics_providers {
  key id                  : String(16);
      name                : String(120);
      vehicles            : Integer;
      pickups_per_vehicle : Integer;
      cost_per_pickup     : Double;
      sla_hours           : Integer;
      is_synthetic        : Boolean;
}

@cds.persistence.exists
entity orders {
  key id             : String(20);
      customer_id    : String(16);
      sku            : String(24);
      product        : Association to products on product.sku = sku;
      size           : String(8);
      price          : Double;
      order_date     : Date;
      delivered_date : Date;
      cluster_id     : String(16);
      festival_tag   : String(30);
      is_synthetic   : Boolean;
}

@cds.persistence.exists
entity ![returns] {
  key id                : String(20);
      order_id          : String(20);
      customer_id       : String(16);
      sku               : String(24);
      vendor_id         : String(16);
      product           : Association to products on product.sku = sku;
      vendor            : Association to vendors on vendor.id = vendor_id;
      cluster_id        : String(16);
      size              : String(8);
      price             : Double;
      request_date      : Date;
      reason_category   : String(30);
      reason_text       : LargeString;
      verified_reason   : String(30);
      predicted_reason  : String(30);
      reason_confidence : Double;
      resolution        : String(20);
      status            : String(30);
      pickup_date       : Date;
      received_date     : Date;
      inspected_date    : Date;
      facility_id       : String(16);
      provider_id       : String(16);
      grade             : String(2);
      recovery_action   : String(30);
      recovered_value   : Double;
      refund_amount     : Double;
      restock_date      : Date;
      pickup_sla_met    : Boolean;
      pickup_cost       : Double;
      integrity_flag    : Boolean;
      is_synthetic      : Boolean;
}

@cds.persistence.exists
entity recommendations {
  key id                 : Id;
      run_id             : Id;
      agent              : String(40);
      kind               : String(40);
      title              : String(200);
      rationale          : LargeString;
      entity_type        : String(20);
      entity_id          : String(40);
      impact_inr         : Double;
      cost_inr           : Double;
      confidence         : Double;
      priority           : String(10);
      requires_approval  : Boolean;
      approver_role      : String(30);
      status             : String(20);
      applied            : Boolean;
      explanation_source : String(40);
      created_at         : Timestamp;
      updated_at         : Timestamp;
}

@cds.persistence.exists
entity decision_log {
  key id                : Integer;
      recommendation_id : Id;
      user_id           : String(24);
      user_name         : String(80);
      role              : String(30);
      ts                : Timestamp;
      action            : String(20);
      reason            : LargeString;
      previous_status   : String(20);
      new_status        : String(20);
}

@cds.persistence.exists
entity audit_log {
  key id          : Integer;
      ts          : Timestamp;
      actor       : String(80);
      actor_type  : String(20);
      action      : String(60);
      entity_type : String(30);
      entity_id   : String(40);
}
