# -*- coding: utf-8 -*-
"""self_test for invoice-field-validator — inherits v2 template four defenses.
NOTE: this validator contains NO tax rules; tests assert tax fields are ignored."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", newline="\n")

import invoice_field_validator as mod

TMP = tempfile.mkdtemp(prefix="ifv_selftest_")
_n = [0]


def write_doc(obj):
    _n[0] += 1
    path = os.path.join(TMP, "inv_%d.json" % _n[0])
    with open(path, "w", encoding="utf-8", newline="") as fh:
        json.dump(obj, fh, ensure_ascii=False)
    return path


def run_cli(argv):
    buf_out, buf_err = io.StringIO(), io.StringIO()
    code = 0
    try:
        with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
            code = mod.main(argv) or 0
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    except Exception as e:
        code = 1
        buf_err.write(repr(e))
    return code, buf_out.getvalue(), buf_err.getvalue()


def line(qty=2, price=50.0, amount=None, desc="item"):
    return {"description": desc, "quantity": qty, "unit_price": price,
            "amount": round(qty * price, 2) if amount is None else amount}


def invoice(**kw):
    base = {"invoice_id": "INV-001", "issue_date": "2026-03-15",
            "currency": "USD", "seller": {"name": "Seller Co"},
            "buyer": {"name": "Buyer Ltd"}, "lines": [line()],
            "subtotal": 100.0, "total": 100.0}
    base.update(kw)
    return base


class TestAFunctional(unittest.TestCase):
    def test_valid_invoice_exit0(self):
        p = write_doc(invoice())
        code, out, _ = run_cli([p])
        self.assertEqual(code, 0)
        self.assertIn("verdict: PASS", out)

    def test_json_format_parseable(self):
        _, out, _ = run_cli([write_doc(invoice()), "--format", "json"])
        self.assertEqual(json.loads(out)["errors"], 0)

    def test_line_amount_mismatch_is_error(self):
        code, out, _ = run_cli([write_doc(invoice(lines=[line(amount=999.0)]))])
        self.assertEqual(code, 1)
        self.assertIn("arithmetic-mismatch", out)

    def test_subtotal_mismatch_is_error(self):
        code, out, _ = run_cli([write_doc(invoice(subtotal=123.0))])
        self.assertEqual(code, 1)
        self.assertIn("subtotal-mismatch", out)

    def test_total_with_other_charges_ok(self):
        p = write_doc(invoice(other_charges=[{"label": "shipping", "amount": 20.0}],
                              total=120.0))
        code, _, _ = run_cli([p])
        self.assertEqual(code, 0)

    def test_total_without_charges_mismatch(self):
        p = write_doc(invoice(other_charges=[{"label": "handling", "amount": 5.0}],
                              total=100.0))
        code, out, _ = run_cli([p])
        self.assertEqual(code, 1)
        self.assertIn("total-mismatch", out)

    def test_multi_lines_subtotal_sums(self):
        p = write_doc(invoice(lines=[line(qty=1, price=30.0), line(qty=2, price=35.0)],
                              subtotal=100.0))
        code, _, _ = run_cli([p])
        self.assertEqual(code, 0)

    def test_rounding_tolerance_cents(self):
        p = write_doc(invoice(lines=[line(qty=3, price=19.99, amount=59.98)],
                              subtotal=59.98, total=59.98))
        code, _, _ = run_cli([p])
        self.assertEqual(code, 0)  # 3*19.99=59.97 vs 59.98 within 0.01

    def test_missing_required_field_listed(self):
        doc = invoice()
        del doc["invoice_id"]
        code, out, _ = run_cli([write_doc(doc)])
        self.assertEqual(code, 1)
        self.assertIn("invoice_id", out)

    def test_bad_date_shape(self):
        code, out, _ = run_cli([write_doc(invoice(issue_date="15/03/2026"))])
        self.assertEqual(code, 1)
        self.assertIn("bad-date-format", out)

    def test_impossible_calendar_date(self):
        code, out, _ = run_cli([write_doc(invoice(issue_date="2026-02-30"))])
        self.assertEqual(code, 1)
        self.assertIn("impossible-date", out)

    def test_leap_day_accepted(self):
        code, _, _ = run_cli([write_doc(invoice(issue_date="2024-02-29"))])
        self.assertEqual(code, 0)

    def test_bad_currency_lowercase(self):
        code, out, _ = run_cli([write_doc(invoice(currency="usd"))])
        self.assertEqual(code, 1)
        self.assertIn("bad-currency", out)

    def test_negative_quantity(self):
        code, out, _ = run_cli([write_doc(invoice(lines=[line(qty=-1, amount=0.0)]))])
        self.assertEqual(code, 1)
        self.assertIn("bad-quantity", out)

    def test_negative_unit_price(self):
        code, out, _ = run_cli([write_doc(invoice(lines=[line(price=-5, amount=0.0)]))])
        self.assertEqual(code, 1)
        self.assertIn("bad-unit-price", out)

    def test_tax_field_warns_not_errors(self):
        code, out, _ = run_cli([write_doc(invoice(tax={"rate": 0.19, "amount": 19.0},
                                                  total=119.0))])
        # total mismatch (119 != 100) is an error; the tax note is a warning
        self.assertEqual(code, 1)
        self.assertIn("tax-field-ignored", out)

    def test_seller_name_missing(self):
        code, out, _ = run_cli([write_doc(invoice(seller={"nam": "x"}))])
        self.assertEqual(code, 1)
        self.assertIn("seller", out)

    def test_empty_description(self):
        code, out, _ = run_cli([write_doc(invoice(lines=[line(desc="  ")]))])
        self.assertEqual(code, 1)
        self.assertIn("missing-description", out)

    def test_zero_price_line_valid(self):
        code, _, _ = run_cli([write_doc(invoice(lines=[line(qty=1, price=0.0, amount=0.0)],
                                                subtotal=0.0, total=0.0))])
        self.assertEqual(code, 0)

    def test_text_report_counts(self):
        _, out, _ = run_cli([write_doc(invoice(subtotal=999.0))])
        self.assertIn("2 error(s), 0 warning(s)", out)


class TestBErrors(unittest.TestCase):
    def test_missing_file_exit2(self):
        code, _, err = run_cli([os.path.join(TMP, "nope.json")])
        self.assertEqual(code, 2)
        self.assertIn("cannot read", err)

    def test_bad_json_exit2(self):
        _n[0] += 1
        p = os.path.join(TMP, "bad_%d.json" % _n[0])
        with open(p, "w", encoding="utf-8", newline="") as fh:
            fh.write("{,}")
        self.assertEqual(run_cli([p])[0], 2)

    def test_top_level_list_exit2_style(self):
        # list input -> validator returns not-object finding, exit 1 (not crash)
        p = write_doc([invoice()])
        code, _, _ = run_cli([p])
        self.assertEqual(code, 1)

    def test_empty_file_exit2(self):
        _n[0] += 1
        p = os.path.join(TMP, "empty_%d.json" % _n[0])
        open(p, "w", encoding="utf-8", newline="").close()
        self.assertEqual(run_cli([p])[0], 2)

    def test_directory_input_exit2(self):
        self.assertEqual(run_cli([TMP])[0], 2)

    def test_no_args_exit2(self):
        self.assertEqual(run_cli([])[0], 2)

    def test_unknown_format_exit2(self):
        p = write_doc(invoice())
        self.assertEqual(run_cli([p, "--format", "xml"])[0], 2)

    def test_lines_empty_array(self):
        code, out, _ = run_cli([write_doc(invoice(lines=[]))])
        self.assertEqual(code, 1)
        self.assertIn("no-lines", out)

    def test_lines_not_list(self):
        code, _, _ = run_cli([write_doc(invoice(lines="one"))])
        self.assertEqual(code, 1)

    def test_line_not_object(self):
        code, out, _ = run_cli([write_doc(invoice(lines=["flat"]))])
        self.assertEqual(code, 1)
        self.assertIn("not-object", out)

    def test_amount_not_number(self):
        code, out, _ = run_cli([write_doc(invoice(lines=[line(amount="100")]))])
        self.assertEqual(code, 1)
        self.assertIn("bad-amount", out)

    def test_quantity_bool_rejected(self):
        code, out, _ = run_cli([write_doc(invoice(lines=[line(qty=True, amount=1.0)]))])
        self.assertEqual(code, 1)
        self.assertIn("bad-quantity", out)

    def test_subtotal_string(self):
        code, out, _ = run_cli([write_doc(invoice(subtotal="100.0"))])
        self.assertEqual(code, 1)
        self.assertIn("bad-subtotal", out)

    def test_other_charges_not_list(self):
        code, out, _ = run_cli([write_doc(invoice(other_charges=5))])
        self.assertEqual(code, 1)
        self.assertIn("bad-charges", out)

    def test_charge_missing_label(self):
        code, out, _ = run_cli([write_doc(invoice(other_charges=[{"amount": 5.0}],
                                                 total=105.0))])
        self.assertEqual(code, 1)
        self.assertIn("bad-charge", out)


class TestCEdge(unittest.TestCase):
    def test_unicode_names(self):
        p = write_doc(invoice(seller={"name": "\u5356\u5bb6\u516c\u53f8"},
                              buyer={"name": "\u6ce2\u65af\u987f"}))
        code, out, _ = run_cli([p, "--format", "json"])
        self.assertEqual(code, 0)

    def test_very_long_description(self):
        p = write_doc(invoice(lines=[line(desc="d" * 50000)]))
        code, _, _ = run_cli([p])
        self.assertEqual(code, 0)

    def test_huge_quantity(self):
        p = write_doc(invoice(lines=[line(qty=10**9, price=0.01, amount=10**7)],
                              subtotal=10**7, total=10**7))
        code, _, _ = run_cli([p])
        self.assertEqual(code, 0)

    def test_many_lines(self):
        ls = [line(qty=1, price=1.0) for _ in range(500)]
        p = write_doc(invoice(lines=ls, subtotal=500.0, total=500.0))
        code, _, _ = run_cli([p])
        self.assertEqual(code, 0)

    def test_extra_fields_ignored(self):
        p = write_doc(invoice(notes="hello", meta={"a": [1, 2]}))
        code, _, _ = run_cli([p])
        self.assertEqual(code, 0)

    def test_negative_total_flagged(self):
        code, out, _ = run_cli([write_doc(invoice(subtotal=-50.0,
                                                  lines=[line(qty=1, price=-50.0, amount=-50.0)],
                                                  total=-50.0))])
        self.assertEqual(code, 1)
        self.assertIn("negative-total", out)

    def test_duplicate_invoice_id_not_checked(self):
        # single file = single invoice; no cross-file semantics
        code, _, _ = run_cli([write_doc(invoice(invoice_id="INV-001"))])
        self.assertEqual(code, 0)

    def test_date_with_time_rejected(self):
        code, out, _ = run_cli([write_doc(invoice(issue_date="2026-03-15T10:00:00"))])
        self.assertEqual(code, 1)
        self.assertIn("bad-date-format", out)

    def test_three_charge_lines_total(self):
        p = write_doc(invoice(lines=[line(qty=1, price=100.0)],
                              other_charges=[{"label": "a", "amount": 1.0},
                                             {"label": "b", "amount": 2.0},
                                             {"label": "c", "amount": 3.0}],
                              total=106.0))
        code, _, _ = run_cli([p])
        self.assertEqual(code, 0)

    def test_vat_rate_key_only_warns(self):
        code, out, _ = run_cli([write_doc(invoice(vat_rate=20))])
        self.assertEqual(code, 0)  # warning only, arithmetic still consistent
        self.assertIn("vat_rate", out)

    def test_no_tax_rate_logic_anywhere(self):
        src = open(mod.__file__, "r", encoding="utf-8").read()
        self.assertNotIn("0.19", src)
        self.assertNotIn("0.07", src)
        self.assertNotIn("20%", src)


CASES = [
    (invoice(), 0),
    (invoice(lines=[line(amount=1.0)]), 1),
    (invoice(subtotal=100.01), 0),   # within tolerance
    (invoice(subtotal=100.03), 1),   # beyond tolerance
    (invoice(total=100.01), 0),
    (invoice(total=100.5), 1),
    (invoice(lines=[line(qty=0, amount=0.0)]), 1),
    (invoice(lines=[line(price=0.0, amount=0.0)], subtotal=0.0, total=0.0), 0),
    (invoice(currency="US1"), 1),
    (invoice(currency="EU"), 1),
    (invoice(issue_date="2026-00-10"), 1),
    (invoice(issue_date="2026-12-31"), 0),
    (invoice(other_charges=[], total=100.0), 0),
    (invoice(other_charges=[{"label": "x", "amount": -5.0}], total=95.0), 0),
    (invoice(lines=[line(qty=7, price=13.333333, amount=93.33)], subtotal=93.33, total=93.33), 0),
]


def _mk(case):
    doc, want = case

    def test(self):
        code, _, _ = run_cli([write_doc(doc)])
        self.assertEqual(code, want)
    return test


for _i, _c in enumerate(CASES):
    setattr(TestCEdge, "test_table_%02d" % _i, _mk(_c))

if __name__ == "__main__":
    r = unittest.TextTestRunner(verbosity=0).run(
        unittest.defaultTestLoader.loadTestsFromModule(sys.modules["__main__"]))
    total, fails = r.testsRun, len(r.failures) + len(r.errors)
    print("SUMMARY: PASS %d/%d" % (total - fails, total))
    sys.exit(0 if fails == 0 else 1)
