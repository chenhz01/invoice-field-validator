# -*- coding: utf-8 -*-
"""invoice-field-validator — structural and arithmetic checks for invoice JSON.

Pure standard library. Validates required fields, date/currency formats, and
the amount arithmetic (line amounts = quantity x unit price; subtotal = sum of
lines; total = subtotal + other charges). Deliberately contains NO tax rules,
NO tax rates, and NO jurisdiction logic of any kind.
Exit codes: 0 = no errors, 1 = errors found, 2 = input error.
"""
import argparse
import json
import re
import sys
from datetime import date as _date

_REQUIRED_TOP = ("invoice_id", "issue_date", "currency", "seller", "buyer",
                 "lines", "subtotal", "total")
_CURRENCY = re.compile(r"^[A-Z]{3}$")
_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")

TOLERANCE = 0.01


def _is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _round2(x):
    return round(float(x) + 0.0, 2)


def _close(a, b):
    return abs(float(a) - float(b)) <= TOLERANCE + 1e-6


def validate_invoice(doc):
    """Return findings list; each finding {severity, field, code, message}."""
    findings = []

    def err(field, code, msg):
        findings.append({"severity": "error", "field": field, "code": code,
                         "message": msg})

    def warn(field, code, msg):
        findings.append({"severity": "warning", "field": field, "code": code,
                         "message": msg})

    if not isinstance(doc, dict):
        err("", "not-object", "top-level JSON must be an object")
        return findings

    for key in _REQUIRED_TOP:
        if key not in doc or doc[key] in (None, ""):
            err(key, "missing-required", "required field %r is missing or empty" % key)
    if any(f["code"] == "missing-required" for f in findings):
        return findings

    for party in ("seller", "buyer"):
        if not isinstance(doc[party], dict) or not str(doc[party].get("name", "")).strip():
            err(party, "missing-party-name", "%s must be an object with non-empty 'name'" % party)

    m = _DATE.match(str(doc["issue_date"]))
    if not m:
        err("issue_date", "bad-date-format", "issue_date must be YYYY-MM-DD")
    else:
        y, mo, d = (int(g) for g in m.groups())
        try:
            _date(y, mo, d)
        except ValueError:
            err("issue_date", "impossible-date", "issue_date %r is not a calendar date" % doc["issue_date"])

    if not _CURRENCY.match(str(doc["currency"])):
        err("currency", "bad-currency", "currency must be a 3-letter ISO-4217-style code (upper case)")

    lines = doc["lines"]
    if not isinstance(lines, list) or not lines:
        err("lines", "no-lines", "lines must be a non-empty array")
        return findings

    line_sum = 0.0
    for i, ln in enumerate(lines):
        field = "lines[%d]" % i
        if not isinstance(ln, dict):
            err(field, "not-object", "line must be an object")
            continue
        if not str(ln.get("description", "")).strip():
            err(field + ".description", "missing-description", "line description required")
        qty, price, amount = ln.get("quantity"), ln.get("unit_price"), ln.get("amount")
        if not _is_number(qty) or qty <= 0:
            err(field + ".quantity", "bad-quantity", "quantity must be a number > 0")
        if not _is_number(price) or price < 0:
            err(field + ".unit_price", "bad-unit-price", "unit_price must be a number >= 0")
        if not _is_number(amount):
            err(field + ".amount", "bad-amount", "amount must be a number")
            continue
        if _is_number(qty) and _is_number(price) and qty > 0 and price >= 0:
            expected = _round2(float(qty) * float(price))
            if not _close(_round2(amount), expected):
                err(field + ".amount", "arithmetic-mismatch",
                    "amount %.2f != quantity x unit_price %.2f" % (float(amount), expected))
        line_sum += float(amount)

    subtotal = doc["subtotal"]
    if _is_number(subtotal):
        if not _close(_round2(subtotal), _round2(line_sum)):
            err("subtotal", "subtotal-mismatch",
                "subtotal %.2f != sum of line amounts %.2f" % (float(subtotal), _round2(line_sum)))
    else:
        err("subtotal", "bad-subtotal", "subtotal must be a number")

    charges_sum = 0.0
    charges = doc.get("other_charges")
    if charges is not None:
        if not isinstance(charges, list):
            err("other_charges", "bad-charges", "other_charges must be an array")
        else:
            for i, ch in enumerate(charges):
                if not isinstance(ch, dict) or not str(ch.get("label", "")).strip():
                    err("other_charges[%d]" % i, "bad-charge",
                        "each charge needs a non-empty 'label'")
                if not _is_number(ch.get("amount") if isinstance(ch, dict) else None):
                    err("other_charges[%d].amount" % i, "bad-charge-amount",
                        "charge amount must be a number")
                elif isinstance(ch, dict):
                    charges_sum += float(ch["amount"])

    total = doc["total"]
    if _is_number(total):
        if float(total) < 0:
            err("total", "negative-total", "total must be >= 0")
        if _is_number(subtotal) and not _close(_round2(total),
                                               _round2(float(subtotal) + charges_sum)):
            err("total", "total-mismatch",
                "total %.2f != subtotal + other charges %.2f"
                % (float(total), _round2(float(subtotal) + charges_sum)))
    else:
        err("total", "bad-total", "total must be a number")

    for tax_key in ("tax", "vat", "gst", "tax_rate", "vat_rate"):
        if tax_key in doc:
            warn(tax_key, "tax-field-ignored",
                 "%r present but ignored: this validator contains no tax rules by design" % tax_key)
    return findings


def render_text(findings):
    lines = ["invoice-field-validator report", "=" * 30]
    errors = 0
    for f in findings:
        marker = "ERROR" if f["severity"] == "error" else "warn "
        if f["severity"] == "error":
            errors += 1
        lines.append("%s %-24s %-20s %s" % (marker, f["field"], f["code"], f["message"]))
    lines.append("verdict: %s (%d error(s), %d warning(s))"
                 % ("FAIL" if errors else "PASS", errors, len(findings) - errors))
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="invoice-field-validator",
        description="Structural + arithmetic checks for invoice JSON (no tax rules).")
    parser.add_argument("file", help="invoice JSON path")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    try:
        with open(args.file, "r", encoding="utf-8-sig") as fh:
            doc = json.load(fh)
    except OSError as exc:
        print("error: cannot read %s: %s" % (args.file, exc), file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print("error: invalid JSON in %s: %s" % (args.file, exc), file=sys.stderr)
        return 2

    findings = validate_invoice(doc)
    errors = sum(1 for f in findings if f["severity"] == "error")
    if args.format == "json":
        print(json.dumps({"tool": "invoice-field-validator", "errors": errors,
                          "warnings": len(findings) - errors, "findings": findings},
                         ensure_ascii=False, indent=2))
    else:
        print(render_text(findings))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
