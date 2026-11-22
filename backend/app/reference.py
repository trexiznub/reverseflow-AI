"""Reference data for the synthetic demonstration world.

Everything in this module is an ILLUSTRATIVE ASSUMPTION for the SAP Hackfest
demo. Vendor names, facilities and volumes are fictional; they are not real
marketplace data.
"""
from __future__ import annotations

from datetime import date

# Scenario clock: the day the demo "stands on". History ends here and the
# Return Prediction Agent forecasts forward from it. 20 Oct 2026 is
# Vijayadashami (end of Sharad Navratri 2026); the return wave peaks ~5-7 days later.
SCENARIO_DATE = date(2026, 10, 20)
HISTORY_START = date(2024, 6, 1)
SEED = 20261020

FESTIVALS = [
    # name, start, end, kind
    ("Navratri 2024", date(2024, 10, 3), date(2024, 10, 12), "festival"),
    ("Diwali 2024", date(2024, 10, 29), date(2024, 11, 2), "festival"),
    ("Wedding season 2024-25", date(2024, 11, 12), date(2025, 2, 28), "wedding-season"),
    ("Navratri 2025", date(2025, 9, 22), date(2025, 10, 2), "festival"),
    ("Diwali 2025", date(2025, 10, 18), date(2025, 10, 22), "festival"),
    ("Wedding season 2025-26", date(2025, 11, 1), date(2026, 2, 28), "wedding-season"),
    ("Navratri 2026", date(2026, 10, 11), date(2026, 10, 20), "festival"),
    ("Diwali 2026", date(2026, 11, 6), date(2026, 11, 10), "festival"),
    ("Wedding season 2026-27", date(2026, 11, 15), date(2027, 2, 28), "wedding-season"),
]

# id, city, state, pin prefix, lat, lon, network daily returns (normal weeks),
# default facility, navratri intensity, sample order base per day
CLUSTERS = [
    ("PNQ", "Pune", "Maharashtra", "411", 18.52, 73.86, 1500, "FAC-PUN", 0.85, 15),
    ("BOM", "Mumbai", "Maharashtra", "400", 19.08, 72.88, 1800, "FAC-BHW", 0.55, 18),
    ("AMD", "Ahmedabad", "Gujarat", "380", 23.02, 72.57, 1000, "FAC-AMD", 1.00, 11),
    ("JAI", "Jaipur", "Rajasthan", "302", 26.91, 75.79, 750, "FAC-JAI", 0.85, 9),
    ("DEL", "Delhi NCR", "Delhi", "110", 28.61, 77.21, 2000, "FAC-GGN", 0.35, 17),
    ("BLR", "Bengaluru", "Karnataka", "560", 12.97, 77.59, 1400, "FAC-BLR", 0.20, 12),
    ("HYD", "Hyderabad", "Telangana", "500", 17.39, 78.49, 900, "FAC-HYD", 0.20, 8),
    ("CCU", "Kolkata", "West Bengal", "700", 22.57, 88.36, 800, "FAC-CCU", 0.30, 8),
]

# id, name, city, lat, lon, kind, inspection cap/day, storage, normal load, handling INR/unit
FACILITIES = [
    ("FAC-BHW", "Bhiwandi West-zone Returns Hub", "Bhiwandi", 19.30, 73.06, "hub", 2400, 30000, 1800, 42.0),
    ("FAC-PUN", "Pune Chakan Returns Centre", "Pune", 18.76, 73.86, "returns-centre", 1500, 12000, 1500, 46.0),
    ("FAC-NSK", "Nashik Ambad Returns Centre", "Nashik", 19.95, 73.75, "returns-centre", 1100, 10000, 300, 38.0),
    ("FAC-AMD", "Ahmedabad Changodar Returns Centre", "Ahmedabad", 22.93, 72.44, "returns-centre", 1250, 10000, 1000, 44.0),
    ("FAC-JAI", "Jaipur Sitapura Returns Centre", "Jaipur", 26.78, 75.83, "returns-centre", 900, 8000, 750, 43.0),
    ("FAC-GGN", "Gurugram Returns Hub", "Gurugram", 28.46, 77.03, "hub", 2300, 26000, 2000, 45.0),
    ("FAC-BLR", "Bengaluru Hoskote Returns Centre", "Bengaluru", 13.07, 77.80, "returns-centre", 1600, 12000, 1400, 44.0),
    ("FAC-HYD", "Hyderabad Shamshabad Returns Centre", "Hyderabad", 17.24, 78.43, "returns-centre", 1000, 9000, 900, 42.0),
    ("FAC-CCU", "Kolkata Dankuni Returns Centre", "Kolkata", 22.68, 88.29, "returns-centre", 950, 8000, 800, 40.0),
]

# id, name, city, specialty, quality profile (hidden generator parameter)
VENDORS = [
    ("V01", "Banaras Loom Collective", "Varanasi", "Sarees", {}),
    ("V02", "Kutch Craft Studio", "Bhuj", "Lehengas", {}),
    ("V03", "Rangrez Textiles", "Surat", "Lehengas", {"stitching": 0.13}),
    ("V04", "Lucknowi Threadworks", "Lucknow", "Kurta sets", {}),
    ("V05", "Chanderi Weavers Guild", "Chanderi", "Sarees", {"fabric": 0.03}),
    ("V06", "Indigo Thread Co.", "Jaipur", "Kurta sets", {}),
    ("V07", "Mehrang Ethnic", "Ahmedabad", "Lehengas", {"size_small": 0.15}),
    ("V08", "Zari & Zardozi Atelier", "Delhi", "Indo-western", {}),
    ("V09", "Jaipur Bandhej House", "Jaipur", "Lehengas", {"colour": 0.03}),
    ("V10", "Ruhaani Fashions", "Mumbai", "Festive dresses", {}),
    ("V11", "Kanchi Silk Emporium", "Kanchipuram", "Sarees", {}),
    ("V12", "Navrang Garba Couture", "Vadodara", "Lehengas", {"stitching": 0.02}),
]

CATEGORIES = {
    # category: base return prob, price range, festive-wave eligible, sizes
    "Lehenga": (0.15, (2499, 14999), True),
    "Saree": (0.07, (1299, 11999), False),
    "Kurta set": (0.11, (999, 4499), False),
    "Indo-western": (0.13, (1999, 7999), True),
    "Festive dress": (0.12, (1499, 5999), True),
}

SIZES = ["XS", "S", "M", "L", "XL", "XXL"]
SIZE_WEIGHTS = [0.06, 0.19, 0.30, 0.24, 0.14, 0.07]

REASONS = {
    "SIZE_SMALL": "Size runs small",
    "SIZE_LARGE": "Size runs large",
    "STITCHING": "Loose / poor stitching",
    "COLOUR_MISMATCH": "Colour differs from listing",
    "FABRIC_QUALITY": "Fabric quality issue",
    "NOT_AS_DESCRIBED": "Not as described",
    "DAMAGED_IN_TRANSIT": "Damaged in transit",
    "CHANGED_MIND": "Changed mind / no longer needed",
    "LATE_DELIVERY": "Arrived too late for occasion",
}
REASON_CATEGORY = {
    "SIZE_SMALL": "Size & fit",
    "SIZE_LARGE": "Size & fit",
    "STITCHING": "Quality",
    "FABRIC_QUALITY": "Quality",
    "COLOUR_MISMATCH": "Listing mismatch",
    "NOT_AS_DESCRIBED": "Listing mismatch",
    "DAMAGED_IN_TRANSIT": "Damaged",
    "CHANGED_MIND": "Other",
    "LATE_DELIVERY": "Other",
}
AVOIDABLE_REASONS = {"SIZE_SMALL", "SIZE_LARGE", "STITCHING", "FABRIC_QUALITY", "COLOUR_MISMATCH", "NOT_AS_DESCRIBED"}

# 3PL partners: id, name, [(cluster, vehicles)], pickups/vehicle/day, INR/pickup
PROVIDERS = [
    ("LP-SWR", "SwiftReverse Logistics", [("PNQ", 48), ("BOM", 56)], 35, 78.0),
    ("LP-KSE", "Kesari Express", [("AMD", 32), ("JAI", 24)], 35, 72.0),
    ("LP-DKR", "DakRun Couriers", [("DEL", 62), ("CCU", 25)], 35, 70.0),
    ("LP-STH", "Southline Pickups", [("BLR", 44), ("HYD", 28)], 35, 74.0),
]

DEMO_USERS = [
    # id, name, role, title, scope, approval limit (INR)
    ("U-RAHUL", "Rahul Mehta", "ops_manager", "Reverse Logistics Operations Manager, West-zone hub (Bhiwandi)", None, 2500000),
    ("U-KAVYA", "Kavya Iyer", "vendor_quality_manager", "Vendor Quality Manager", None, 200000),
    ("U-SURESH", "Suresh Patil", "warehouse_manager", "Warehouse Manager, West zone", None, 150000),
    ("U-NEHA", "Neha Kapoor", "dispute_reviewer", "Dispute Review Lead", None, 50000),
    ("U-VEN-V03", "Imran Shaikh", "vendor", "Seller account, Rangrez Textiles", "V03", 0),
    ("U-VEN-V07", "Hetal Shah", "vendor", "Seller account, Mehrang Ethnic", "V07", 0),
    ("U-VEN-V02", "Dhruv Ahir", "vendor", "Seller account, Kutch Craft Studio", "V02", 0),
    ("U-3PL-SWR", "Vikram Joshi", "logistics", "Network planner, SwiftReverse Logistics", "LP-SWR", 0),
    ("U-3PL-KSE", "Farhan Qureshi", "logistics", "Network planner, Kesari Express", "LP-KSE", 0),
    ("U-WH-PUN", "Sneha Kulkarni", "warehouse", "Inspection lead, Pune Chakan Returns Centre", "FAC-PUN", 0),
    ("U-WH-BHW", "Arjun Nair", "warehouse", "Inspection lead, Bhiwandi West-zone Hub", "FAC-BHW", 0),
]

# Customer personas wired into the generator so the live demo has eligible orders.
DEMO_CUSTOMERS = [
    ("C-DEMO-01", "Priya Sharma", "PNQ", "411038", "V03", "Lehenga", "M"),
    ("C-DEMO-02", "Aditi Joshi", "AMD", "380015", "V07", "Lehenga", "M"),
    ("C-DEMO-03", "Meera Rathore", "JAI", "302017", "V09", "Lehenga", "L"),
]

FIRST_NAMES = (
    "Aarav Aditi Ananya Anika Arjun Avni Diya Esha Gauri Ira Ishaan Kabir Kavya Khushi Kiara Krish "
    "Lavanya Manav Meera Mira Myra Naina Neel Nidhi Nisha Ojas Pari Pooja Pranav Priya Rhea Riya Rohan "
    "Saanvi Sahil Sanya Shreya Siddharth Simran Sneha Tanvi Tara Trisha Vani Vedika Vihaan Yash Zoya "
    "Ayesha Farah Harleen Jasleen Mehak Payal Ritu Shalini Swati Tanya Komal Bhavna Deepa Hema Jyoti"
).split()
LAST_NAMES = (
    "Sharma Patel Shah Joshi Desai Mehta Iyer Nair Reddy Rao Kulkarni Deshpande Patil Gupta Agarwal "
    "Singh Kaur Bose Das Sen Banerjee Mukherjee Pillai Menon Rathore Chauhan Verma Mishra Pandey Jain "
    "Khanna Kapoor Malhotra Bhatt Trivedi Pandya Parikh Gill Sethi Naidu Gowda Hegde Shetty Kamat"
).split()
