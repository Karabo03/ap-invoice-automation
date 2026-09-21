"""
Builds the underlying business records for Kalahari Components: the supplier
master file, purchase orders, goods received notes and the invoices that the
creditors clerk would find in the inbox.

Exceptions are planted deliberately and written to a ground truth file, so the
accuracy of the system can be measured later instead of claimed.
"""

from __future__ import annotations

import random
import sys
from dataclasses import dataclass, field, asdict
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd

import config as cfg

rng = random.Random(cfg.RANDOM_SEED)

PERIOD_START = date(2025, 10, 1)
PERIOD_END = date(2026, 9, 30)

N_SUPPLIERS = 45
N_POS = 520

# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------

SUPPLIER_STEMS = [
    ("Midrand Bearing Supplies", "Bearings and Drives"),
    ("Vaal Steel Merchants", "Steel and Metals"),
    ("Protea Hydraulics", "Hydraulics"),
    ("Sandton Electrical Wholesale", "Electrical"),
    ("Boksburg Fastener Co", "Fasteners"),
    ("Highveld Lubricants", "Lubricants"),
    ("Cape Conveyor Systems", "Conveyors"),
    ("Umgeni Valve and Pump", "Valves and Pumps"),
    ("Rand Safety Equipment", "Safety and PPE"),
    ("Germiston Tool Hire", "Tools"),
    ("Karoo Abrasives", "Abrasives"),
    ("Tshwane Pneumatics", "Pneumatics"),
    ("Isando Welding Supplies", "Welding"),
    ("Kempton Cable Works", "Electrical"),
    ("Alberton Seal and Gasket", "Seals"),
    ("Benoni Industrial Paints", "Paints and Coatings"),
    ("Roodepoort Motor Rewinds", "Motors"),
    ("Springs Gearbox Services", "Bearings and Drives"),
    ("Edenvale Filtration", "Filtration"),
    ("Krugersdorp Chain and Sprocket", "Bearings and Drives"),
    ("Witbank Belting", "Conveyors"),
    ("Nigel Compressor Services", "Pneumatics"),
    ("Modderfontein Chemicals", "Chemicals"),
    ("Randburg Instrumentation", "Instrumentation"),
    ("Sasolburg Pipe and Fittings", "Pipe and Fittings"),
    ("Brakpan Sheet Metal", "Steel and Metals"),
    ("Kya Sand Plastics", "Plastics"),
    ("Wadeville Hose and Coupling", "Hydraulics"),
    ("Jet Park Packaging", "Packaging"),
    ("Elandsfontein Rubber", "Seals"),
    ("Sebenza Workwear", "Safety and PPE"),
    ("Linbro Park Hardware", "General Hardware"),
    ("Aeroton Castors", "General Hardware"),
    ("Chamdor Forklift Spares", "Materials Handling"),
    ("Selby Scrap and Recovery", "Steel and Metals"),
    ("Booysens Battery Centre", "Electrical"),
    ("Denver Crane Services", "Materials Handling"),
    ("Cleveland Bolt Supplies", "Fasteners"),
    ("Robertsham Glass and Perspex", "Plastics"),
    ("Ophirton Hydraulic Rams", "Hydraulics"),
    ("City Deep Cold Storage Spares", "Refrigeration"),
    ("Crown Mines Motor Spares", "Motors"),
    ("New Centre Gas and Gear", "Welding"),
    ("Village Main Instruments", "Instrumentation"),
    ("Salt River Marine Fittings", "Pipe and Fittings"),
]

STREETS = [
    "Main Reef Road", "Barlow Road", "Herman Road", "Angus Crescent",
    "Kruger Street", "Dekema Road", "Rondebult Road", "North Rand Road",
    "Electron Avenue", "Commerce Crescent", "Bond Street", "Chilvers Street",
    "Vlakfontein Road", "Diesel Road", "Sam Green Road", "Landmarks Avenue",
]
TOWNS = [
    "Wadeville", "Isando", "Kempton Park", "Germiston", "Boksburg",
    "Roodepoort", "Midrand", "Alrode", "Spartan", "Chloorkop",
]

BANKS = [
    ("Standard Bank", "051001"),
    ("First National Bank", "250655"),
    ("Absa Bank", "632005"),
    ("Nedbank", "198765"),
    ("Capitec Business", "470010"),
    ("Investec", "580105"),
]

CATALOGUE = {
    "Bearings and Drives": [
        ("BRG-6205", "Deep groove ball bearing 6205 2RS", 148.00, 720.00),
        ("BRG-22216", "Spherical roller bearing 22216 E", 1980.00, 4250.00),
        ("DRV-SPB2120", "SPB section V belt 2120mm", 210.00, 460.00),
        ("DRV-TL2517", "Taper lock bush 2517 x 45mm", 320.00, 690.00),
    ],
    "Steel and Metals": [
        ("STL-PL6MS", "Mild steel plate 6mm 1000 x 2000", 1850.00, 3400.00),
        ("STL-SQ50", "Square tube 50 x 50 x 3mm 6m length", 620.00, 1180.00),
        ("STL-ANG40", "Equal angle 40 x 40 x 5mm 6m", 480.00, 910.00),
        ("STL-RD304", "Stainless round bar 304 20mm 6m", 1420.00, 2650.00),
    ],
    "Hydraulics": [
        ("HYD-2SN12", "Hydraulic hose 2SN 1/2 inch per metre", 165.00, 340.00),
        ("HYD-CYL80", "Hydraulic cylinder 80 bore 400 stroke", 6800.00, 12400.00),
        ("HYD-PMP45", "Gear pump 45cc SAE B", 4900.00, 9100.00),
        ("HYD-FIT12", "Swaged fitting 1/2 BSP male", 88.00, 190.00),
    ],
    "Electrical": [
        ("ELE-SWA4C", "SWA cable 4 core 16mm per metre", 210.00, 430.00),
        ("ELE-CB63", "Circuit breaker 63A triple pole", 640.00, 1280.00),
        ("ELE-CON40", "Contactor 40A 230V coil", 890.00, 1740.00),
        ("ELE-BAT100", "Deep cycle battery 100Ah", 2100.00, 3900.00),
    ],
    "Fasteners": [
        ("FST-M12X60", "Hex bolt M12 x 60 grade 8.8 box of 100", 780.00, 1450.00),
        ("FST-NUTM12", "Hex nut M12 grade 8 box of 200", 410.00, 820.00),
        ("FST-ANC12", "Chemical anchor stud M12 x 160", 46.00, 95.00),
    ],
    "Lubricants": [
        ("LUB-EP220", "Gear oil EP220 208 litre drum", 8900.00, 15200.00),
        ("LUB-GRS18", "Lithium complex grease EP2 18kg", 1650.00, 2980.00),
        ("LUB-HYD46", "Hydraulic oil ISO 46 20 litre", 890.00, 1620.00),
    ],
    "Conveyors": [
        ("CNV-BLT650", "Conveyor belting 650mm 3 ply per metre", 720.00, 1380.00),
        ("CNV-IDL152", "Trough idler set 152mm 650 belt", 1450.00, 2700.00),
        ("CNV-PUL400", "Drum pulley 400mm lagged", 7800.00, 13900.00),
    ],
    "Valves and Pumps": [
        ("VLV-BF100", "Butterfly valve 100mm lever operated", 1980.00, 3600.00),
        ("VLV-GT80", "Gate valve 80mm flanged", 2450.00, 4400.00),
        ("PMP-CEN55", "Centrifugal pump 5.5kW end suction", 18400.00, 31000.00),
    ],
    "Safety and PPE": [
        ("PPE-HRN01", "Full body safety harness double lanyard", 1480.00, 2650.00),
        ("PPE-BOOT8", "Safety boot steel toe size 8 pair", 420.00, 780.00),
        ("PPE-GLV10", "Cut resistant glove level 5 pair", 96.00, 185.00),
        ("PPE-HAT01", "Hard hat vented with ratchet", 88.00, 165.00),
    ],
    "Tools": [
        ("TLS-GRN230", "Angle grinder 230mm 2400W", 2100.00, 3850.00),
        ("TLS-TRQ34", "Torque wrench 3/4 drive 100 to 500Nm", 3400.00, 6200.00),
        ("TLS-DRL18", "Cordless drill 18V two battery kit", 2600.00, 4700.00),
    ],
    "Abrasives": [
        ("ABR-CUT230", "Cutting disc 230 x 3 x 22 box of 25", 640.00, 1180.00),
        ("ABR-FLP125", "Flap disc 125mm 60 grit box of 10", 380.00, 720.00),
    ],
    "Pneumatics": [
        ("PNU-CYL63", "Pneumatic cylinder 63 bore 200 stroke", 1780.00, 3200.00),
        ("PNU-FRL12", "Filter regulator lubricator 1/2 inch", 1240.00, 2300.00),
        ("PNU-CMP75", "Screw compressor service kit 7.5kW", 4600.00, 8300.00),
    ],
    "Welding": [
        ("WLD-E6013", "Welding electrode E6013 3.2mm 5kg", 320.00, 620.00),
        ("WLD-MIG08", "MIG wire 0.8mm 15kg spool", 780.00, 1420.00),
        ("WLD-HLM01", "Auto darkening welding helmet", 1150.00, 2100.00),
    ],
    "Seals": [
        ("SEL-ORK01", "O ring kit nitrile 382 piece", 890.00, 1650.00),
        ("SEL-GSK150", "Full face gasket 150mm rubber insertion", 145.00, 290.00),
        ("SEL-OIL45", "Oil seal 45 x 65 x 10 nitrile", 78.00, 160.00),
    ],
    "Paints and Coatings": [
        ("PNT-EPX20", "Two pack epoxy enamel 20 litre", 3200.00, 5800.00),
        ("PNT-PRM20", "Zinc phosphate primer 20 litre", 2100.00, 3900.00),
    ],
    "Motors": [
        ("MTR-55KW4", "Electric motor 5.5kW 4 pole foot mount", 6400.00, 11800.00),
        ("MTR-REW11", "Motor rewind 11kW including bearings", 7200.00, 13400.00),
    ],
    "Filtration": [
        ("FLT-HYD10", "Hydraulic return filter element 10 micron", 640.00, 1240.00),
        ("FLT-AIR01", "Compressor air filter element", 480.00, 920.00),
    ],
    "Chemicals": [
        ("CHM-DEG25", "Industrial degreaser 25 litre", 980.00, 1820.00),
        ("CHM-RUS05", "Rust converter 5 litre", 620.00, 1180.00),
    ],
    "Instrumentation": [
        ("INS-PRS16", "Pressure transmitter 0 to 16 bar 4 to 20mA", 4200.00, 7800.00),
        ("INS-TMP01", "PT100 temperature probe with head", 1180.00, 2200.00),
    ],
    "Pipe and Fittings": [
        ("PIP-GAL50", "Galvanised pipe 50mm medium 6m", 980.00, 1840.00),
        ("PIP-FLG80", "Slip on flange 80mm table D", 340.00, 660.00),
    ],
    "Plastics": [
        ("PLA-HDPE10", "HDPE sheet 10mm 1000 x 2000", 2400.00, 4400.00),
        ("PLA-PER06", "Perspex sheet 6mm 1000 x 2000", 1900.00, 3500.00),
    ],
    "Packaging": [
        ("PKG-STR48", "Strapping band 16mm x 1000m", 620.00, 1180.00),
        ("PKG-PLT12", "Pallet wrap 500mm 20 micron roll", 180.00, 340.00),
    ],
    "General Hardware": [
        ("HDW-CST100", "Swivel castor 100mm braked", 210.00, 420.00),
        ("HDW-PDL50", "Brass padlock 50mm keyed alike", 165.00, 320.00),
    ],
    "Materials Handling": [
        ("MHD-FRK25", "Forklift fork 2500kg pair class 2", 8900.00, 16200.00),
        ("MHD-SLG03", "Webbing sling 3 ton 4 metre", 780.00, 1480.00),
    ],
    "Refrigeration": [
        ("REF-CMP15", "Refrigeration compressor 15HP semi hermetic", 24000.00, 42000.00),
        ("REF-GAS404", "Refrigerant R404a 10kg cylinder", 4800.00, 8600.00),
    ],
}

DEPARTMENTS = [
    ("Production", "CC-100"),
    ("Maintenance", "CC-200"),
    ("Warehouse", "CC-300"),
    ("Engineering", "CC-400"),
    ("Quality", "CC-500"),
    ("Facilities", "CC-600"),
]

REQUESTERS = [
    "T. Mokoena", "S. Naidoo", "J. van Wyk", "P. Dlamini", "R. Botha",
    "N. Khumalo", "A. Petersen", "M. Fourie", "L. Nkosi", "D. Pillay",
    "C. Maree", "B. Sithole", "G. Coetzee", "F. Adams", "K. Mahlangu",
]

RECEIVERS = ["W. Mabaso", "E. du Plessis", "H. Ngobeni", "Z. Jacobs", "O. Mthembu"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def rand_date(start: date, end: date) -> date:
    return start + timedelta(days=rng.randint(0, (end - start).days))


def working_day(d: date) -> date:
    """Nudge weekend dates onto the following Monday."""
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def money(x: float) -> float:
    return round(float(x) + 1e-9, 2)


def vat_number() -> str:
    return "4" + "".join(str(rng.randint(0, 9)) for _ in range(9))


def account_number() -> str:
    return "".join(str(rng.randint(0, 9)) for _ in range(rng.choice([9, 10, 11])))


# ---------------------------------------------------------------------------
# Suppliers
# ---------------------------------------------------------------------------

def build_suppliers() -> pd.DataFrame:
    rows = []
    for i, (name, category) in enumerate(SUPPLIER_STEMS[:N_SUPPLIERS], start=1):
        bank, branch = rng.choice(BANKS)
        approved_on = PERIOD_START - timedelta(days=rng.randint(90, 2200))
        rows.append(
            {
                "supplier_id": f"SUP-{i:04d}",
                "supplier_name": f"{name} (Pty) Ltd",
                "category": category,
                "vat_number": vat_number(),
                "reg_number": f"{rng.randint(1998, 2021)}/{rng.randint(100000, 999999)}/07",
                "address": f"{rng.randint(1, 240)} {rng.choice(STREETS)}, {rng.choice(TOWNS)}",
                "contact_email": "accounts@" + name.lower().replace(" ", "").replace("'", "")[:18] + ".co.za",
                "bank_name": bank,
                "branch_code": branch,
                "account_number": account_number(),
                "payment_terms_days": rng.choice([30, 30, 30, 45, 60]),
                "approved": "Y",
                "date_approved": approved_on.isoformat(),
            }
        )
    df = pd.DataFrame(rows)

    # Three suppliers were never signed off by procurement. They still send
    # invoices, which is exactly the hole the vendor master control exists to
    # close.
    unapproved_ids = list(df.sample(3, random_state=7)["supplier_id"])
    df.loc[df["supplier_id"].isin(unapproved_ids), "approved"] = "N"
    df.loc[df["supplier_id"].isin(unapproved_ids), "date_approved"] = ""
    return df


# ---------------------------------------------------------------------------
# Purchase orders and goods received notes
# ---------------------------------------------------------------------------

def build_pos(suppliers: pd.DataFrame):
    approved = suppliers[suppliers["approved"] == "Y"].reset_index(drop=True)
    po_rows, line_rows = [], []

    for n in range(1, N_POS + 1):
        sup = approved.iloc[rng.randrange(len(approved))]
        items = CATALOGUE[sup["category"]]
        po_date = working_day(rand_date(PERIOD_START, PERIOD_END - timedelta(days=35)))
        dept, cc = rng.choice(DEPARTMENTS)
        po_number = f"PO-{po_date.year}-{n:05d}"

        n_lines = rng.choices([1, 2, 3, 4, 5], weights=[34, 28, 20, 12, 6])[0]
        chosen = rng.sample(items, k=min(n_lines, len(items)))
        total = 0.0
        for j, (code, desc, lo, hi) in enumerate(chosen, start=1):
            unit = money(rng.uniform(lo, hi))
            qty = rng.choices([1, 2, 3, 4, 5, 6, 8, 10, 12, 20, 25, 50],
                              weights=[18, 14, 12, 9, 8, 7, 6, 8, 5, 5, 4, 4])[0]
            line_total = money(unit * qty)
            total += line_total
            line_rows.append(
                {
                    "po_number": po_number,
                    "line_no": j,
                    "item_code": code,
                    "description": desc,
                    "qty_ordered": qty,
                    "unit_price_ex_vat": unit,
                    "line_total_ex_vat": line_total,
                }
            )

        po_rows.append(
            {
                "po_number": po_number,
                "supplier_id": sup["supplier_id"],
                "supplier_name": sup["supplier_name"],
                "po_date": po_date.isoformat(),
                "requester": rng.choice(REQUESTERS),
                "department": dept,
                "cost_centre": cc,
                "total_ex_vat": money(total),
                "approval_level": approval_level(total),
                "status": "Open",
            }
        )

    return pd.DataFrame(po_rows), pd.DataFrame(line_rows)


def approval_level(amount: float) -> str:
    for lo, hi, who in cfg.APPROVAL_BANDS:
        if lo <= amount < hi:
            return who
    return "Chief Financial Officer"


def build_grns(pos: pd.DataFrame, po_lines: pd.DataFrame):
    grn_rows, grn_line_rows = [], []
    lines_by_po = {k: v for k, v in po_lines.groupby("po_number")}

    n = 0
    for _, po in pos.iterrows():
        # A small share of orders are still outstanding at the reporting date.
        if rng.random() < 0.07:
            continue
        n += 1
        po_date = date.fromisoformat(po["po_date"])
        receipt = working_day(po_date + timedelta(days=rng.randint(3, 21)))
        grn_number = f"GRN-{receipt.year}-{n:05d}"
        grn_rows.append(
            {
                "grn_number": grn_number,
                "po_number": po["po_number"],
                "supplier_id": po["supplier_id"],
                "receipt_date": receipt.isoformat(),
                "received_by": rng.choice(RECEIVERS),
                "warehouse": rng.choice(["WH-A Sandton", "WH-B Wadeville"]),
            }
        )
        for _, ln in lines_by_po[po["po_number"]].iterrows():
            qty_rec = ln["qty_ordered"]
            # Short deliveries happen. The supplier sometimes still bills in full,
            # which is what the quantity control is looking for.
            if rng.random() < 0.10:
                qty_rec = max(1, int(ln["qty_ordered"] * rng.uniform(0.5, 0.9)))
            grn_line_rows.append(
                {
                    "grn_number": grn_number,
                    "po_number": po["po_number"],
                    "line_no": int(ln["line_no"]),
                    "item_code": ln["item_code"],
                    "qty_received": int(qty_rec),
                }
            )

    return pd.DataFrame(grn_rows), pd.DataFrame(grn_line_rows)


# ---------------------------------------------------------------------------
# Invoices
# ---------------------------------------------------------------------------

@dataclass
class Invoice:
    invoice_id: str
    invoice_number: str
    supplier_id: str
    supplier_name: str
    supplier_vat_number: str
    supplier_address: str
    supplier_email: str
    bank_name: str
    branch_code: str
    account_number: str
    po_number: str
    invoice_date: str
    due_date: str
    lines: list = field(default_factory=list)
    subtotal_ex_vat: float = 0.0
    vat_amount: float = 0.0
    total_incl_vat: float = 0.0
    layout: str = "A"
    is_scan: bool = False
    omit_particulars: list = field(default_factory=list)
    seeded_exceptions: list = field(default_factory=list)


def recompute(inv: Invoice, keep_vat: bool = False, keep_subtotal: bool = False):
    line_sum = money(sum(l["line_total"] for l in inv.lines))
    if not keep_subtotal:
        inv.subtotal_ex_vat = line_sum
    if not keep_vat:
        inv.vat_amount = money(inv.subtotal_ex_vat * cfg.VAT_RATE)
    inv.total_incl_vat = money(inv.subtotal_ex_vat + inv.vat_amount)


def build_invoices(suppliers: pd.DataFrame, pos: pd.DataFrame,
                   po_lines: pd.DataFrame, grns: pd.DataFrame,
                   grn_lines: pd.DataFrame):
    sup_by_id = suppliers.set_index("supplier_id").to_dict("index")
    lines_by_po = {k: v for k, v in po_lines.groupby("po_number")}
    grn_by_po = {r["po_number"]: r for _, r in grns.iterrows()}
    grnl_by_po = {k: v for k, v in grn_lines.groupby("po_number")}

    invoices: list[Invoice] = []
    seq = {}

    def next_invoice_number(sup_id: str, d: date) -> str:
        seq[sup_id] = seq.get(sup_id, rng.randint(1200, 8800)) + rng.randint(1, 4)
        prefix = rng.choice(["INV", "TI", "SI", ""])
        if prefix:
            return f"{prefix}{d.year % 100:02d}{seq[sup_id]:05d}"
        return f"{seq[sup_id]:06d}"

    # ---- the normal population: one invoice per received purchase order ----
    eligible = [p for p in pos["po_number"] if p in grn_by_po]
    rng.shuffle(eligible)
    chosen_pos = eligible[:240]

    for idx, po_number in enumerate(chosen_pos, start=1):
        po = pos[pos["po_number"] == po_number].iloc[0]
        sup = sup_by_id[po["supplier_id"]]
        grn = grn_by_po[po_number]
        receipt = date.fromisoformat(grn["receipt_date"])
        inv_date = working_day(receipt + timedelta(days=rng.randint(0, 9)))
        if inv_date > PERIOD_END:
            inv_date = PERIOD_END

        rec_qty = {int(r["line_no"]): int(r["qty_received"])
                   for _, r in grnl_by_po[po_number].iterrows()}

        lines = []
        for _, ln in lines_by_po[po_number].iterrows():
            qty = rec_qty.get(int(ln["line_no"]), int(ln["qty_ordered"]))
            lines.append(
                {
                    "line_no": int(ln["line_no"]),
                    "item_code": ln["item_code"],
                    "description": ln["description"],
                    "quantity": qty,
                    "unit_price": money(ln["unit_price_ex_vat"]),
                    "line_total": money(qty * ln["unit_price_ex_vat"]),
                }
            )

        inv = Invoice(
            invoice_id=f"INV-{idx:05d}",
            invoice_number=next_invoice_number(po["supplier_id"], inv_date),
            supplier_id=po["supplier_id"],
            supplier_name=sup["supplier_name"],
            supplier_vat_number=sup["vat_number"],
            supplier_address=sup["address"],
            supplier_email=sup["contact_email"],
            bank_name=sup["bank_name"],
            branch_code=sup["branch_code"],
            account_number=sup["account_number"],
            po_number=po_number,
            invoice_date=inv_date.isoformat(),
            due_date=(inv_date + timedelta(days=int(sup["payment_terms_days"]))).isoformat(),
            lines=lines,
            layout=rng.choices(["A", "B", "C", "D"], weights=[32, 27, 23, 18])[0],
            is_scan=rng.random() < 0.16,
        )
        recompute(inv)
        invoices.append(inv)

    return invoices, sup_by_id, lines_by_po, grn_by_po, grnl_by_po


# ---------------------------------------------------------------------------
# Planting the exceptions
# ---------------------------------------------------------------------------

def plant_exceptions(invoices, suppliers, sup_by_id, pos, po_lines,
                     lines_by_po, grn_by_po, grnl_by_po):
    """Mutates a controlled subset of invoices and records what was done."""
    pool = list(range(len(invoices)))
    rng.shuffle(pool)
    used: set[int] = set()

    def take(n: int) -> list[int]:
        out = []
        for i in pool:
            if i in used:
                continue
            out.append(i)
            used.add(i)
            if len(out) == n:
                break
        return out

    # E01 price above the purchase order -------------------------------------
    for i in take(18):
        inv = invoices[i]
        pol = lines_by_po[inv.po_number]
        ln = inv.lines[rng.randrange(len(inv.lines))]
        uplift = rng.uniform(0.06, 0.34)
        ln["unit_price"] = money(ln["unit_price"] * (1 + uplift))
        ln["line_total"] = money(ln["unit_price"] * ln["quantity"])
        recompute(inv)
        inv.seeded_exceptions.append("E01_PRICE_VARIANCE")

    # E02 billed for more than was received ----------------------------------
    for i in take(16):
        inv = invoices[i]
        ln = inv.lines[rng.randrange(len(inv.lines))]
        ln["quantity"] = ln["quantity"] + rng.randint(1, 4)
        ln["line_total"] = money(ln["unit_price"] * ln["quantity"])
        recompute(inv)
        inv.seeded_exceptions.append("E02_QTY_OVER_BILLED")

    # E05 VAT worked out wrongly ---------------------------------------------
    for i in take(14):
        inv = invoices[i]
        mode = rng.choice(["old_rate", "on_total", "rounding", "flat"])
        if mode == "old_rate":
            inv.vat_amount = money(inv.subtotal_ex_vat * 0.14)
        elif mode == "on_total":
            inv.vat_amount = money(inv.subtotal_ex_vat * cfg.VAT_RATE * 1.15)
        elif mode == "rounding":
            inv.vat_amount = money(inv.subtotal_ex_vat * cfg.VAT_RATE + rng.uniform(4, 60))
        else:
            inv.vat_amount = money(inv.subtotal_ex_vat * rng.uniform(0.155, 0.175))
        recompute(inv, keep_vat=True, keep_subtotal=True)
        inv.seeded_exceptions.append("E05_VAT_ERROR")

    # E06 banking details changed --------------------------------------------
    for i in take(9):
        inv = invoices[i]
        bank, branch = rng.choice(BANKS)
        inv.bank_name = bank
        inv.branch_code = branch
        inv.account_number = account_number()
        inv.seeded_exceptions.append("E06_BANK_CHANGE")

    # E08 the invoice does not add up ----------------------------------------
    for i in take(11):
        inv = invoices[i]
        drift = money(rng.choice([-1, 1]) * rng.uniform(90, 2400))
        inv.subtotal_ex_vat = money(inv.subtotal_ex_vat + drift)
        recompute(inv, keep_subtotal=True)
        inv.seeded_exceptions.append("E08_ARITHMETIC")

    # E09 dated before the order or before delivery --------------------------
    for i in take(10):
        inv = invoices[i]
        po_date = date.fromisoformat(
            pos[pos["po_number"] == inv.po_number].iloc[0]["po_date"])
        inv.invoice_date = (po_date - timedelta(days=rng.randint(2, 40))).isoformat()
        inv.due_date = (date.fromisoformat(inv.invoice_date) + timedelta(days=30)).isoformat()
        inv.seeded_exceptions.append("E09_DATE_ANOMALY")

    # E11 above R5 000 but missing a required particular ---------------------
    big = [i for i in pool if i not in used
           and invoices[i].total_incl_vat > cfg.FULL_TAX_INVOICE_THRESHOLD]
    for i in big[:13]:
        used.add(i)
        inv = invoices[i]
        inv.omit_particulars = [rng.choice(
            ["supplier_vat_number", "tax_invoice_wording", "invoice_date", "recipient_name"])]
        inv.seeded_exceptions.append("E11_INVALID_TAX_INVOICE")

    # E12 invoiced but nothing ever booked in --------------------------------
    open_pos = [p for p in pos["po_number"] if p not in grn_by_po]
    sup_of = pos.set_index("po_number")["supplier_id"].to_dict()
    next_id = len(invoices) + 1
    for po_number in open_pos[:8]:
        sup = sup_by_id[sup_of[po_number]]
        po = pos[pos["po_number"] == po_number].iloc[0]
        po_date = date.fromisoformat(po["po_date"])
        inv_date = working_day(po_date + timedelta(days=rng.randint(4, 18)))
        lines = [
            {
                "line_no": int(ln["line_no"]),
                "item_code": ln["item_code"],
                "description": ln["description"],
                "quantity": int(ln["qty_ordered"]),
                "unit_price": money(ln["unit_price_ex_vat"]),
                "line_total": money(ln["qty_ordered"] * ln["unit_price_ex_vat"]),
            }
            for _, ln in lines_by_po[po_number].iterrows()
        ]
        inv = Invoice(
            invoice_id=f"INV-{next_id:05d}",
            invoice_number=f"INV{inv_date.year % 100:02d}{rng.randint(10000, 99999)}",
            supplier_id=sup_of[po_number],
            supplier_name=sup["supplier_name"],
            supplier_vat_number=sup["vat_number"],
            supplier_address=sup["address"],
            supplier_email=sup["contact_email"],
            bank_name=sup["bank_name"],
            branch_code=sup["branch_code"],
            account_number=sup["account_number"],
            po_number=po_number,
            invoice_date=inv_date.isoformat(),
            due_date=(inv_date + timedelta(days=int(sup["payment_terms_days"]))).isoformat(),
            lines=lines,
            layout=rng.choice(["A", "B", "C", "D"]),
            is_scan=rng.random() < 0.16,
            seeded_exceptions=["E12_GOODS_NOT_RECEIVED"],
        )
        recompute(inv)
        invoices.append(inv)
        next_id += 1

    # E04 no purchase order at all -------------------------------------------
    approved_sups = suppliers[suppliers["approved"] == "Y"]
    for _ in range(12):
        sup = approved_sups.iloc[rng.randrange(len(approved_sups))].to_dict()
        items = CATALOGUE[sup["category"]]
        inv_date = working_day(rand_date(PERIOD_START, PERIOD_END))
        lines = []
        for j, (code, desc, lo, hi) in enumerate(rng.sample(items, k=min(2, len(items))), start=1):
            unit = money(rng.uniform(lo, hi))
            qty = rng.randint(1, 6)
            lines.append({"line_no": j, "item_code": code, "description": desc,
                          "quantity": qty, "unit_price": unit,
                          "line_total": money(unit * qty)})
        inv = Invoice(
            invoice_id=f"INV-{next_id:05d}",
            invoice_number=f"INV{inv_date.year % 100:02d}{rng.randint(10000, 99999)}",
            supplier_id=sup["supplier_id"], supplier_name=sup["supplier_name"],
            supplier_vat_number=sup["vat_number"], supplier_address=sup["address"],
            supplier_email=sup["contact_email"], bank_name=sup["bank_name"],
            branch_code=sup["branch_code"], account_number=sup["account_number"],
            po_number="" if rng.random() < 0.6 else f"PO-2026-{rng.randint(90000, 99999)}",
            invoice_date=inv_date.isoformat(),
            due_date=(inv_date + timedelta(days=30)).isoformat(),
            lines=lines,
            layout=rng.choice(["A", "B", "C", "D"]),
            is_scan=rng.random() < 0.16,
            seeded_exceptions=["E04_NO_PO"],
        )
        recompute(inv)
        invoices.append(inv)
        next_id += 1

    # E07 supplier never approved --------------------------------------------
    unapproved = suppliers[suppliers["approved"] == "N"]
    for _ in range(9):
        sup = unapproved.iloc[rng.randrange(len(unapproved))].to_dict()
        items = CATALOGUE[sup["category"]]
        inv_date = working_day(rand_date(PERIOD_START, PERIOD_END))
        lines = []
        for j, (code, desc, lo, hi) in enumerate(rng.sample(items, k=min(2, len(items))), start=1):
            unit = money(rng.uniform(lo, hi))
            qty = rng.randint(1, 8)
            lines.append({"line_no": j, "item_code": code, "description": desc,
                          "quantity": qty, "unit_price": unit,
                          "line_total": money(unit * qty)})
        inv = Invoice(
            invoice_id=f"INV-{next_id:05d}",
            invoice_number=f"INV{inv_date.year % 100:02d}{rng.randint(10000, 99999)}",
            supplier_id=sup["supplier_id"], supplier_name=sup["supplier_name"],
            supplier_vat_number=sup["vat_number"], supplier_address=sup["address"],
            supplier_email=sup["contact_email"], bank_name=sup["bank_name"],
            branch_code=sup["branch_code"], account_number=sup["account_number"],
            po_number="",
            invoice_date=inv_date.isoformat(),
            due_date=(inv_date + timedelta(days=30)).isoformat(),
            lines=lines,
            layout=rng.choice(["A", "B", "C", "D"]),
            is_scan=rng.random() < 0.16,
            seeded_exceptions=["E07_UNAPPROVED_SUPPLIER", "E04_NO_PO"],
        )
        recompute(inv)
        invoices.append(inv)
        next_id += 1

    # E10 a run of invoices sitting just under the R50 000 sign off limit ----
    split_sup = approved_sups.iloc[rng.randrange(len(approved_sups))].to_dict()
    base = working_day(date(2026, 5, 11))
    for k in range(4):
        items = CATALOGUE[split_sup["category"]]
        code, desc, lo, hi = rng.choice(items)
        target_incl = rng.uniform(47_200, 49_650)
        target_ex = target_incl / (1 + cfg.VAT_RATE)
        qty = rng.randint(3, 9)
        unit = money(target_ex / qty)
        inv_date = working_day(base + timedelta(days=k * 3))
        lines = [{"line_no": 1, "item_code": code, "description": desc,
                  "quantity": qty, "unit_price": unit,
                  "line_total": money(unit * qty)}]
        inv = Invoice(
            invoice_id=f"INV-{next_id:05d}",
            invoice_number=f"INV26{rng.randint(10000, 99999)}",
            supplier_id=split_sup["supplier_id"], supplier_name=split_sup["supplier_name"],
            supplier_vat_number=split_sup["vat_number"], supplier_address=split_sup["address"],
            supplier_email=split_sup["contact_email"], bank_name=split_sup["bank_name"],
            branch_code=split_sup["branch_code"], account_number=split_sup["account_number"],
            po_number="",
            invoice_date=inv_date.isoformat(),
            due_date=(inv_date + timedelta(days=30)).isoformat(),
            lines=lines,
            layout=rng.choice(["A", "B"]),
            is_scan=False,
            seeded_exceptions=["E10_THRESHOLD_SPLIT", "E04_NO_PO"],
        )
        recompute(inv)
        invoices.append(inv)
        next_id += 1

    # E03 duplicates ---------------------------------------------------------
    clean = [i for i in range(len(invoices)) if not invoices[i].seeded_exceptions]
    rng.shuffle(clean)
    for i in clean[:11]:
        src = invoices[i]
        dup = Invoice(**{**asdict(src)})
        dup.lines = [dict(l) for l in src.lines]
        dup.invoice_id = f"INV-{next_id:05d}"
        dup.seeded_exceptions = ["E03_DUPLICATE"]
        dup.layout = rng.choice(["A", "B", "C", "D"])
        dup.is_scan = rng.random() < 0.3
        style = rng.random()
        if style < 0.45:
            # resubmitted under a new number a few days later
            dup.invoice_number = src.invoice_number + rng.choice(["-R", "A", "/2"])
            d = date.fromisoformat(src.invoice_date) + timedelta(days=rng.randint(2, 9))
            dup.invoice_date = min(d, PERIOD_END).isoformat()
        # otherwise the identical invoice comes through twice
        recompute(dup, keep_vat=True, keep_subtotal=True)
        invoices.append(dup)
        next_id += 1

    return invoices


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    suppliers = build_suppliers()
    pos, po_lines = build_pos(suppliers)
    grns, grn_lines = build_grns(pos, po_lines)
    invoices, sup_by_id, lines_by_po, grn_by_po, grnl_by_po = build_invoices(
        suppliers, pos, po_lines, grns, grn_lines)
    invoices = plant_exceptions(invoices, suppliers, sup_by_id, pos, po_lines,
                                lines_by_po, grn_by_po, grnl_by_po)

    rng.shuffle(invoices)
    for n, inv in enumerate(invoices, start=1):
        inv.invoice_id = f"INV-{n:05d}"

    suppliers.to_csv(cfg.DATA / "suppliers.csv", index=False)
    pos.to_csv(cfg.DATA / "purchase_orders.csv", index=False)
    po_lines.to_csv(cfg.DATA / "po_lines.csv", index=False)
    grns.to_csv(cfg.DATA / "goods_received_notes.csv", index=False)
    grn_lines.to_csv(cfg.DATA / "grn_lines.csv", index=False)

    truth_rows, truth_lines = [], []
    for inv in invoices:
        truth_rows.append(
            {
                "invoice_id": inv.invoice_id,
                "pdf_file": f"{inv.invoice_id}.pdf",
                "invoice_number": inv.invoice_number,
                "supplier_id": inv.supplier_id,
                "supplier_name": inv.supplier_name,
                "supplier_vat_number": inv.supplier_vat_number,
                "po_number": inv.po_number,
                "invoice_date": inv.invoice_date,
                "due_date": inv.due_date,
                "bank_name": inv.bank_name,
                "branch_code": inv.branch_code,
                "account_number": inv.account_number,
                "subtotal_ex_vat": inv.subtotal_ex_vat,
                "vat_amount": inv.vat_amount,
                "total_incl_vat": inv.total_incl_vat,
                "line_count": len(inv.lines),
                "layout": inv.layout,
                "is_scan": int(inv.is_scan),
                "omitted_particulars": "|".join(inv.omit_particulars),
                "seeded_exceptions": "|".join(sorted(set(inv.seeded_exceptions))),
            }
        )
        for l in inv.lines:
            truth_lines.append({"invoice_id": inv.invoice_id, **l})

    pd.DataFrame(truth_rows).to_csv(cfg.GROUND_TRUTH_DIR / "invoice_truth.csv", index=False)
    pd.DataFrame(truth_lines).to_csv(cfg.GROUND_TRUTH_DIR / "invoice_line_truth.csv", index=False)

    print(f"suppliers            {len(suppliers):>5}")
    print(f"purchase orders      {len(pos):>5}")
    print(f"purchase order lines {len(po_lines):>5}")
    print(f"goods received notes {len(grns):>5}")
    print(f"invoices             {len(invoices):>5}")
    planted = sum(1 for i in invoices if i.seeded_exceptions)
    print(f"invoices with a planted exception {planted}")
    return invoices


if __name__ == "__main__":
    main()
