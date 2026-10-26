#!/usr/bin/env python3
"""Fill the statement template from metadata.json + transactions.csv and write a PDF.

Usage:
    python render_statement.py data/cust_0001                 # -> out/cust_0001.pdf
    python render_statement.py data/cust_0001 --out my.pdf
"""
import argparse
import sys
from datetime import date, datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

from validator import compute, load, validate

ROOT = Path(__file__).resolve().parent # synthetic_bank_statements


def money(d):
    return f"{d:,.2f}"


def resolve_logo(meta, data_dir):
    """logo_path is relative to the project root (next to this script); fall back to the customer dir."""
    p = Path(meta["bank"]["logo_path"])
    for base in (ROOT, data_dir):
        cand = p if p.is_absolute() else base / p
        if cand.exists():
            return cand.resolve()
    sys.exit(f"logo not found: {p} (looked in {ROOT} and {data_dir})")


def build_context(meta, rows, summary, logo_path):
    st = meta["statement"]
    out_rows = [{
        "date": r["date"].strftime("%d/%m/%y"),
        "value_date": r["value_date"].strftime("%d/%m/%y"),
        "narration": r["narration"],
        "ref_no": r["ref_no"],
        "withdrawal": money(r["withdrawal"]) if r["withdrawal"] is not None else "",
        "deposit": money(r["deposit"]) if r["deposit"] is not None else "",
        "balance": money(r["balance"]),
    } for r in rows]
    return {
        "bank": meta["bank"], "branch": meta["branch"], "account": meta["account"],
        "customer": meta["customer"], "statement": st, "footer": meta["footer"],
        "logo_uri": logo_path.as_uri(),
        "od_limit": money(__import__("decimal").Decimal(str(meta["account"]["od_limit"]))),
        "open_date": date.fromisoformat(meta["account"]["open_date"]).strftime("%d/%m/%Y"),
        "period_from": date.fromisoformat(st["period_from"]).strftime("%d/%m/%Y"),
        "period_to": date.fromisoformat(st["period_to"]).strftime("%d/%m/%Y"),
        "generated_on": datetime.strptime(st["generated_on"], "%Y-%m-%d %H:%M").strftime("%d-%b-%Y %H:%M"),
        "pdf_title": f"SYNTHETIC statement - {meta['customer']['name']} - {st['period_from']} to {st['period_to']}",
        "rows": out_rows,
        "summary": {
            "opening_balance": money(summary["opening_balance"]),
            "dr_count": summary["dr_count"], "cr_count": summary["cr_count"],
            "debits": money(summary["debits"]), "credits": money(summary["credits"]),
            "closing_balance": money(summary["closing_balance"]),
        },
    }


def render(data_dir, out_path, template_dir=ROOT / "templates", template_name="statement.html.j2"):
    data_dir = Path(data_dir)
    meta, rows = load(data_dir)
    errors = validate(meta, rows)
    if errors:
        print(f"validation failed for {data_dir} ({len(errors)} problems):", file=sys.stderr)
        for e in errors:
            print("  -", e, file=sys.stderr)
        sys.exit(1)
    summary = compute(meta, rows)
    ctx = build_context(meta, rows, summary, resolve_logo(meta, data_dir))
    env = Environment(loader=FileSystemLoader(str(template_dir)), autoescape=select_autoescape(["html", "j2"]))
    html = env.get_template(template_name).render(**ctx)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html, base_url=str(ROOT)).write_pdf(str(out_path))
    return out_path


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("data_dir", help="folder containing metadata.json and transactions.csv")
    ap.add_argument("--out", help="output PDF path (default: out/<folder name>.pdf)")
    args = ap.parse_args()
    out = args.out or ROOT / "out" / f"{Path(args.data_dir).resolve().name}.pdf"
    print("wrote", render(args.data_dir, out))


if __name__ == "__main__":
    main()