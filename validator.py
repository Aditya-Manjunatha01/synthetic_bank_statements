#!/usr/bin/env python3
"""Load, compute and validate one synthetic customer (metadata.json + transactions.csv).

Usage:  python validator.py data/cust_0001
"""
import csv
import json
import re
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

TXN_TYPES = {"UPI", "NEFT", "RTGS", "IMPS", "ATM", "POS", "CHEQUE", "NACH", "INTEREST", "CHARGES"}
CSV_COLUMNS = ["date", "value_date", "txn_type", "narration", "ref_no", "withdrawal", "deposit"]

# Only these fake IFSC prefixes are allowed anywhere (account IFSC and IFSC-like tokens in narrations).
ALLOWED_FAKE_IFSC_PREFIXES = {"TOYB", "ZBNK", "DEMO", "FAKE", "TEST", "XYZB"}

# Real names / handles that must never appear in synthetic data (word-boundary, case-insensitive).
REAL_NAME_BLOCKLIST = [
    "HDFC", "ICICI", "SBI", "STATE BANK", "AXIS", "KOTAK", "PUNJAB NATIONAL", "BANK OF BARODA",
    "CANARA", "UNION BANK", "YES BANK", "IDFC", "INDUSIND", "FEDERAL BANK", "BANDHAN", "IDBI",
    "INDIAN BANK", "BANK OF INDIA", "CENTRAL BANK", "RBL", "AU SMALL", "PAYTM", "PHONEPE",
    "GOOGLE PAY", "GPAY", "BHIM", "AMAZON PAY",
]
REAL_VPA_HANDLES = {
    "ybl", "ibl", "axl", "okhdfcbank", "okicici", "oksbi", "okaxis", "paytm", "upi", "apl",
    "sbi", "icici", "hdfcbank", "axisbank", "kotak", "yesbank", "pnb", "barodampay", "cnrb",
    "indus", "federal", "idfcbank", "airtel", "jio", "postbank",
}

IFSC_RE = re.compile(r"\b([A-Z]{4})0[A-Z0-9]{6}\b")
VPA_RE = re.compile(r"@([A-Za-z0-9]+)")


def _dec(value, where):
    try:
        return Decimal(value)
    except InvalidOperation:
        raise ValueError(f"{where}: not a decimal: {value!r}")


def load(data_dir):
    """Return (metadata dict, rows list). Rows have typed fields; amounts are Decimal or None."""
    data_dir = Path(data_dir)
    meta = json.loads((data_dir / "metadata.json").read_text(encoding="utf-8"))
    rows = []
    with open(data_dir / "transactions.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = [c for c in CSV_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"transactions.csv missing columns: {missing}")
        for i, r in enumerate(reader, start=2):  # line 1 is the header
            wd = r["withdrawal"].strip()
            dp = r["deposit"].strip()
            rows.append({
                "line": i,
                "date": date.fromisoformat(r["date"]),
                "value_date": date.fromisoformat(r["value_date"]),
                "txn_type": r["txn_type"].strip(),
                "narration": r["narration"],
                "ref_no": r["ref_no"].strip(),
                "withdrawal": _dec(wd, f"line {i} withdrawal") if wd else None,
                "deposit": _dec(dp, f"line {i} deposit") if dp else None,
            })
    return meta, rows


def compute(meta, rows):
    """Add a running 'balance' to each row and return the summary dict (all Decimal / int)."""
    bal = Decimal(str(meta["statement"]["opening_balance"]))
    opening = bal
    debits = credits = Decimal("0")
    dr = cr = 0
    for r in rows:
        if r["withdrawal"] is not None:
            bal -= r["withdrawal"]; debits += r["withdrawal"]; dr += 1
        if r["deposit"] is not None:
            bal += r["deposit"]; credits += r["deposit"]; cr += 1
        r["balance"] = bal
    return {"opening_balance": opening, "dr_count": dr, "cr_count": cr,
            "debits": debits, "credits": credits, "closing_balance": bal}


def _all_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _all_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _all_strings(v)


def validate(meta, rows):
    """Return a list of error strings (empty list means valid). Also fills row['balance']."""
    errs = []

    # --- metadata ---
    if meta.get("synthetic") is not True:
        errs.append('metadata: "synthetic" must be true')
    required = {
        "bank": ["name", "tagline", "logo_path", "legal_name", "registered_office",
                 "gst_state_account_branch_gstn", "gst_info_url"],
        "branch": ["name", "address_lines", "city", "state", "pincode", "phones", "branch_code", "ifsc", "micr"],
        "account": ["account_no", "account_variant", "cust_id", "open_date", "status", "type", "type_code",
                    "currency", "od_limit", "email", "nomination"],
        "customer": ["title", "name", "address_lines", "joint_holders"],
        "statement": ["title", "period_from", "period_to", "opening_balance", "generated_on",
                      "generated_by", "requesting_branch_code"],
        "footer": ["closing_balance_note", "disclaimer", "computer_generated_note"],
    }
    for section, keys in required.items():
        if section not in meta:
            errs.append(f"metadata: missing section {section!r}")
            continue
        for k in keys:
            if k not in meta[section]:
                errs.append(f"metadata: missing {section}.{k}")
    if errs:
        return errs  # structure is broken, later checks would just crash

    ifsc = meta["branch"]["ifsc"]
    if not re.fullmatch(r"[A-Z]{4}0[A-Z0-9]{6}", ifsc):
        errs.append(f"metadata: branch.ifsc {ifsc!r} is not a valid IFSC shape")
    elif ifsc[:4] not in ALLOWED_FAKE_IFSC_PREFIXES:
        errs.append(f"metadata: branch.ifsc prefix {ifsc[:4]!r} not in allowed fake prefixes")
    if not re.fullmatch(r"\d{9}", meta["branch"]["micr"]):
        errs.append("metadata: branch.micr must be 9 digits")
    if not meta["account"]["email"].lower().endswith("@example.com"):
        errs.append("metadata: account.email must use the example.com domain")

    try:
        p_from = date.fromisoformat(meta["statement"]["period_from"])
        p_to = date.fromisoformat(meta["statement"]["period_to"])
        date.fromisoformat(meta["account"]["open_date"])
        datetime.strptime(meta["statement"]["generated_on"], "%Y-%m-%d %H:%M")
    except ValueError as e:
        return errs + [f"metadata: bad date format ({e})"]
    if p_from > p_to:
        errs.append("metadata: period_from is after period_to")
    od_limit = Decimal(str(meta["account"]["od_limit"]))

    # real-bank names anywhere in metadata or narrations
    texts = list(_all_strings(meta)) + [r["narration"] for r in rows]
    for t in texts:
        for word in REAL_NAME_BLOCKLIST:
            if re.search(rf"\b{re.escape(word)}\b", t, re.IGNORECASE):
                errs.append(f"blocklist: real bank/app name {word!r} found in {t[:60]!r}")
    for r in rows:
        for m in IFSC_RE.finditer(r["narration"]):
            if m.group(1) not in ALLOWED_FAKE_IFSC_PREFIXES:
                errs.append(f"line {r['line']}: IFSC-like token with real/unknown prefix {m.group(0)!r}")
        for m in VPA_RE.finditer(r["narration"]):
            if m.group(1).lower() in REAL_VPA_HANDLES:
                errs.append(f"line {r['line']}: real UPI handle @{m.group(1)}")

    # --- transactions ---
    if not rows:
        errs.append("transactions.csv has no rows")
    prev = None
    for r in rows:
        ln = r["line"]
        if r["txn_type"] not in TXN_TYPES:
            errs.append(f"line {ln}: txn_type {r['txn_type']!r} not in enum")
        if not (p_from <= r["date"] <= p_to):
            errs.append(f"line {ln}: date {r['date']} outside statement period")
        if r["value_date"] < r["date"]:
            errs.append(f"line {ln}: value_date earlier than date")
        if prev is not None and r["date"] < prev:
            errs.append(f"line {ln}: rows not sorted by date")
        prev = r["date"]
        if not re.fullmatch(r"\d{16}", r["ref_no"]):
            errs.append(f"line {ln}: ref_no {r['ref_no']!r} is not 16 digits")
        filled = [x for x in (r["withdrawal"], r["deposit"]) if x is not None]
        if len(filled) != 1:
            errs.append(f"line {ln}: exactly one of withdrawal/deposit must be filled")
        for x in filled:
            if x < 0:
                errs.append(f"line {ln}: negative amount")
            if x.as_tuple().exponent < -2:
                errs.append(f"line {ln}: more than 2 decimal places")
        if not r["narration"].strip():
            errs.append(f"line {ln}: empty narration")

    # --- balances ---
    summary = compute(meta, rows)
    for r in rows:
        if r["balance"] < -od_limit:
            errs.append(f"line {r['line']}: balance {r['balance']} below -od_limit")
    expected = summary["opening_balance"] - summary["debits"] + summary["credits"]
    if expected != summary["closing_balance"]:
        errs.append("closing balance does not equal opening - debits + credits")
    if summary["dr_count"] + summary["cr_count"] != len(rows):
        errs.append("Dr count + Cr count does not equal number of rows")
    return errs


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: python validator.py <customer_dir>")
    meta, rows = load(sys.argv[1])
    errs = validate(meta, rows)
    if errs:
        print(f"INVALID ({len(errs)} problems):")
        for e in errs:
            print("  -", e)
        sys.exit(1)
    s = compute(meta, rows)
    print(f"OK: {len(rows)} rows, Dr {s['dr_count']}, Cr {s['cr_count']}, "
          f"opening {s['opening_balance']:,.2f}, closing {s['closing_balance']:,.2f}")


if __name__ == "__main__":
    main()