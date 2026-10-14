"""Regression tests – must ALL PASS before the tool is used on a project.
Run:  python -m pytest -q tests      (or)   python tests/test_engines.py
Reference values come from the CEDA skills (verified against the CEDA Excel sheets).
"""
import json, os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from ceda_fdn import pile_capacity as pc, cap_design as cd

VOCO_BH01 = {
    "project": "selftest VOCO", "slurry": "polymer", "cutoff": 1.0, "fs_soil": 2.5, "fc": 280, "qstr_coef": 0.29,
    "diameters": [1.0], "tip_depths": [15],
    "boreholes": [{"name": "BH01", "gwl": 1.55, "layers": [
        {"name": "GC", "type": "Clay", "top": 0, "bot": 3, "gamma": 1.36, "N": 0, "Su": 0},
        {"name": "CH", "type": "Clay", "top": 3, "bot": 7, "gamma": 1.82, "N": 0, "Su": 1.50667},
        {"name": "CH", "type": "Clay", "top": 7, "bot": 14.3, "gamma": 1.672, "N": 0, "Su": 1.89625},
        {"name": "CL", "type": "Clay", "top": 14.3, "bot": 15.3, "gamma": 2.16, "N": 0, "Su": 12.7},
        {"name": "CH", "type": "Clay", "top": 15.3, "bot": 26.5, "gamma": 2.0, "N": 30.75, "Su": 0},
        {"name": "CH", "type": "Clay", "top": 26.5, "bot": 30, "gamma": 2.05, "N": 0, "Su": 17.72},
        {"name": "SM", "type": "Sand", "top": 30, "bot": 35, "gamma": 2.0, "N": 37.333, "Su": 0}]}]}

CAP_BASE = {"project": "selftest", "code": "ACI318-19", "size_effect": False, "fc": 280, "fy": 5000, "cover": 7.5,
            "embed": 0, "pile": {"D": 80, "Qa": 215}, "factor": 1.55, "pedestal": [80, 80], "e": 10,
            "cap_weight": "factored"}


def test_step01_voco_bh01():
    r = pc.run(VOCO_BH01)["boreholes"][0]["rows"][0]
    assert abs(r["Qult"] - 159.69) < 0.01, r["Qult"]
    assert abs(r["Qs"] - 69.92) < 0.01 and abs(r["Qb"] - 89.77) < 0.01


def test_step01_excel_writes():
    res = pc.run(VOCO_BH01)
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "o.xlsx"); pc.to_excel(VOCO_BH01, res, p); assert os.path.getsize(p) > 0


def test_step02_s1_f4():
    r = cd.design(dict(CAP_BASE, types=[{"name": "F4", "n": 4, "h": 135, "bars": [28]}]))[0]
    X, P = r["checks"]["dir_x"], r["checks"]["punch_col"]
    assert abs(X["Mu_tm"] * 1000 - 487125.296) < 1
    assert abs(P["vu"] - 6.654) < 0.005 and abs(P["phi_vc"] - 13.303) < 0.005
    assert X["nbars"] == 20


def test_step02_s2_per_type_embed():
    s1 = cd.design(dict(CAP_BASE, types=[{"name": "F4", "n": 4, "h": 135, "bars": [28]}]))[0]
    q = {t["name"]: t for t in cd.design(dict(CAP_BASE, types=[{"name": "F1", "n": 1, "embed": 15},
                                                               {"name": "F4", "n": 4, "h": 135, "bars": [28]}]))}
    assert q["F1"]["embed"] == 15 and q["F4"]["embed"] == 0
    assert json.dumps(q["F4"]["checks"], sort_keys=True, default=str) == json.dumps(s1["checks"], sort_keys=True, default=str)


if __name__ == "__main__":
    ok = True
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try: fn(); print("PASS", name)
            except Exception as e: ok = False; print("FAIL", name, e)
    print("ALL PASS" if ok else "TEST FAILED - do not use the tool")
    sys.exit(0 if ok else 1)
