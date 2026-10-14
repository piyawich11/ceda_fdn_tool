#!/usr/bin/env python3
"""CEDA pile-cap design engine.  Units inside: cm, kg, ksc.  Loads in config: t.
usage: python3 cap_design.py config.json out.xlsx   (writes config_result.json too)

config = {
 "project": "...", "code": "TH" | "ACI318-19", "size_effect": false,
 "fc": 320, "fy": 5000, "cover": 7.5, "embed": 5,            # embed = pile head into cap (cm) -> ASK, never assume
                                                              # a type may override it: {"name":"F1","n":1,"embed":15} (v2)
 "pile": {"D": 80, "Qa": 215}, "factor": 1.55,               # Pu/pile = factor*Qa (CEDA capacity design)
 "spacing_D": 2.5, "edge_D": 1.0,                             # s = spacing_D*D (rounded up 5 cm); pile centre->edge = edge_D*D
 "pedestal": [80, 80], "e": 10, "cap_weight": "factored",   # factored(1.4)|service(1.0)|none
 "h_start": 60, "h_step": 5, "bars": [20, 25, 28, 32], "s_min": 10, "s_max": 30, "temp_bar": 16,
 "types": [{"name": "F1", "n": 1}, {"name": "F4", "n": 4, "h": 135}, {"name": "FX", "coords": [[x,y],...]}]
}
"h" given -> check only;  no "h" -> smallest h (step h_step) that passes all checks.
"""
import json, math, sys
from shapely.geometry import Polygon, LineString, Point, MultiPoint, box

C5 = lambda v: math.ceil(v / 5 - 1e-9) * 5
clamp = lambda v: max(0.0, min(1.0, v))

def layout(n, s):
    r3 = math.sqrt(3)
    if n == 1: return [(0, 0)]
    if n == 2: return [(-s / 2, 0), (s / 2, 0)]
    if n == 3: return [(-s / 2, -s * r3 / 6), (s / 2, -s * r3 / 6), (0, s * r3 / 3)]
    if n == 4: return [(x, y) for y in (-s / 2, s / 2) for x in (-s / 2, s / 2)]
    if n == 5:
        a = C5(s / math.sqrt(2)); return [(0, 0)] + [(x, y) for y in (-a, a) for x in (-a, a)]
    if n == 6: return [(x, y) for y in (-s / 2, s / 2) for x in (-s, 0, s)]
    if n == 7: return [(0, 0), (-s, 0), (s, 0)] + [(x, y) for y in (-s * r3 / 2, s * r3 / 2) for x in (-s / 2, s / 2)]
    if n == 8:
        a = C5(s * r3 / 2); return [(x, y) for y in (-a, a) for x in (-s, 0, s)] + [(-s / 2, 0), (s / 2, 0)]
    if n == 9: return [(x, y) for y in (-s, 0, s) for x in (-s, 0, s)]
    cols = math.ceil(math.sqrt(n)); rows = math.ceil(n / cols)
    if cols * rows != n: raise ValueError(f"n={n}: no standard layout, give 'coords'")
    return [((i - (cols - 1) / 2) * s, (j - (rows - 1) / 2) * s) for j in range(rows) for i in range(cols)]

def cap_outline(pts, edge, n, D):
    if n == 1:
        a = C5(D / 2 + edge); return box(-a, -a, a, a)
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    if n == 3:   # triangular cap, corners bevelled (CEDA F3 shape)
        return MultiPoint(pts).convex_hull.buffer(edge, join_style=2, mitre_limit=1.0)
    return box(min(xs) - edge, min(ys) - edge, max(xs) + edge, max(ys) + edge)

def cut_width(poly, axis, u):
    """length of the cap cut by line axis=u (axis 'x': line x=u, width measured in y)."""
    minx, miny, maxx, maxy = poly.bounds
    L = LineString([(u, miny - 1), (u, maxy + 1)]) if axis == "x" else LineString([(minx - 1, u), (maxx + 1, u)])
    return poly.intersection(L).length

def code_par(cfg):
    if cfg.get("code", "TH").upper().startswith("ACI"):
        return dict(code="ACI 318-19", phib=0.90, phiv=0.75)
    return dict(code="TH (กฎกระทรวง 1.4D+1.7L / วสท. USD, phi per CEDA)", phib=0.90, phiv=0.85)

def lam_s(cfg, d):
    return min(1.0, math.sqrt(2 / (1 + 0.004 * d * 10))) if cfg.get("size_effect") else 1.0

def ld_straight(cfg, db, fc, fy):
    """development length (cm) of bottom bar in tension"""
    if cfg.get("code", "TH").upper().startswith("ACI"):   # ACI 318-19 25.4.2.3 simplified, psi_t=psi_e=1
        fyM, fcM = fy * 0.0980665, fc * 0.0980665
        psig = 1.0 if fyM <= 420 else (1.15 if fyM <= 550 else 1.3)
        k = 1.7 if db >= 22 else 2.1
        return fyM * psig / (k * math.sqrt(fcM)) * db / 10
    Ab = math.pi * (db / 10) ** 2 / 4                       # CEDA/TH basic: 0.06 Ab fy/sqrt(fc') >= 0.0057 db fy
    return max(0.06 * Ab * fy / math.sqrt(fc), 0.0057 * db / 10 * fy, 30)

def ldh_hook(cfg, db, fc, fy):
    if cfg.get("code", "TH").upper().startswith("ACI"):   # ACI 318-19 25.4.3.1, psi_e=1, psi_r=1.6, psi_o=1.25
        fyM, fcM = fy * 0.0980665, min(fc * 0.0980665, 70)
        psic = min(1.0, fcM / 105 + 0.6)
        return max(fyM * 1.6 * 1.25 * psic / (23 * math.sqrt(fcM)) * db ** 1.5 / 10, 8 * db / 10, 15)
    return max(318.2 * db / 10 / math.sqrt(fc) * fy / 4220, 8 * db / 10, 15)   # ACI 318-89 lhb basis

def design_type(cfg, T, h):
    cp = code_par(cfg); fc, fy = cfg["fc"], cfg["fy"]; D = cfg["pile"]["D"]
    Qa = cfg["pile"]["Qa"]; fac = cfg.get("factor", 1.55)
    cx, cy = T.get("pedestal", cfg.get("pedestal", [80, 80]))
    e = cfg.get("e", 10); cov = cfg.get("cover", 7.5); emb = T.get("embed", cfg["embed"])        # per-type override (v2)
    s = T.get("s", C5(cfg.get("spacing_D", 2.5) * D)); edge = T.get("edge", cfg.get("edge_D", 1.0) * D)
    pts = [tuple(p) for p in T["coords"]] if "coords" in T else layout(T["n"], s)
    n = len(pts); poly = cap_outline(pts, edge, n, D)
    W = 2.4 * poly.area / 1e4 * h / 100
    wf = {"factored": 1.4, "service": 1.0, "none": 0.0}[cfg.get("cap_weight", "factored")]
    Pu = (fac * Qa + wf * W / n) * 1000                     # kg / pile
    bars = T.get("bars", cfg.get("bars", [20, 25, 28, 32]))
    beta1 = 0.85 if fc <= 280 else max(0.65, 0.85 - 0.05 * (fc - 280) / 70)
    out = dict(name=T["name"], n=n, s=s, edge=edge, h=h, embed=emb, pedestal=[cx, cy], coords=pts, Pu_t=Pu / 1000,
               W_t=W, outline=list(poly.exterior.coords), area_m2=poly.area / 1e4, code=cp["code"],
               size_effect=bool(cfg.get("size_effect")), checks={}, notes=[])
    ok = True; dbg = max(bars)
    sq = math.sqrt(fc)
    for axis, cface, idx in (("x", cx, 0), ("y", cy, 1)):
        # choose bar later; d with largest bar first (conservative), refined below
        res = None
        for db in bars:
            d = h - cov - emb - 1.5 * db / 10
            ls = lam_s(cfg, d)
            Mu = 0; Vu = 0; bsec = 0; side_rows = []
            for sgn in (1, -1):
                u = [sgn * p[idx] for p in pts]
                face = cface / 2
                m = sum(Pu * (ui - face + e) for ui in u if ui > face) / 100           # kg-m
                sec = face + d
                v = sum(Pu * clamp(0.5 + (ui - sec) / D) for ui in u)
                bs = cut_width(poly, axis, sgn * sec)
                ext = poly.bounds[2 + idx] if sgn > 0 else -poly.bounds[idx]
                if sec >= ext: v, bs = 0, 0
                side_rows.append((m, v, bs))
            Mu = max(r[0] for r in side_rows)
            if n == 1: Mu = Pu * e / 100                       # CEDA F1: Mu = Pu x e (pile tolerance)
            k = max(range(2), key=lambda i: (side_rows[i][1] / side_rows[i][2]) if side_rows[i][2] else 0)
            Vu, bsec = side_rows[k][1], side_rows[k][2]
            bf = cut_width(poly, axis, cface / 2)
            # flexure
            Ru = Mu * 100 / (cp["phib"] * bf * d * d)
            disc = 1 - 2 * Ru / (0.85 * fc)
            rho = 0.85 * fc / fy * (1 - math.sqrt(disc)) if disc > 0 else 9
            if cp["code"].startswith("ACI"):
                rmin_g = max(0.0018 * 4200 / fy, 0.0014) * h / d
                rmax = 0.85 * beta1 * fc / fy * 0.003 / (0.003 + 0.004)
            else:
                rmin_g = 0.0018 * 4000 / fy * h / d if fy > 4000 else 0.0018 * h / d
                rmax = 0.75 * (0.85 * beta1 * fc / fy) * 6120 / (6120 + fy)
            rmin = max(min(14 / fy, 1.33 * rho), rmin_g)
            rho_u = max(rho, rmin); As = rho_u * bf * d
            Ab = math.pi * (db / 10) ** 2 / 4
            nb = max(2, math.ceil(As / Ab - 1e-9))
            span = bf - 2 * cov
            nb = max(nb, math.ceil(span / cfg.get("s_max", 30)) + 1)
            sp = span / (nb - 1)
            # shear capacities
            if cp["code"].startswith("ACI") and cfg.get("size_effect"):
                rw = min(nb * Ab / (bf * d), 0.02)
                vc1 = min(2.12 * ls * rw ** (1 / 3) * sq, 1.33 * sq)    # 22.5.5.1(c), Av<Av,min
            else:
                vc1 = 0.53 * sq
            vu1 = Vu / (bsec * d) if bsec else 0
            # development
            avail = min((poly.bounds[2 + idx]), -poly.bounds[idx]) - cface / 2 - cov
            ld = ld_straight(cfg, db, fc, fy); ldh = ldh_hook(cfg, db, fc, fy)
            res = dict(db=db, d=d, Mu_tm=Mu / 1000, b_face=bf, Ru=Ru, rho_req=rho, rho_min=rmin, rho_use=rho_u,
                       rho_max=rmax, As_req=As, nbars=nb, As_prov=nb * Ab, spacing=sp,
                       Vu_t=Vu / 1000, b_sec=bsec, vu=vu1, phi_vc=cp["phiv"] * vc1, lam_s=ls,
                       beam_ok=vu1 <= cp["phiv"] * vc1 + 1e-9, flex_ok=rho <= rmax and sp >= cfg.get("s_min", 10),
                       ld=ld, ldh=ldh, l_avail=avail, anchorage=("n/a (Mu=0, min. steel)" if Mu <= 0 else "cage, hooked (1-pile)" if n == 1 else "straight" if ld <= avail else ("90deg hook" if ldh <= avail else "NOT OK")),
                       beam_na=Vu == 0)
            if res["flex_ok"]: break
        out["checks"]["dir_" + axis] = res
        ok &= res["beam_ok"] and res["flex_ok"] and res["anchorage"] != "NOT OK"
    # punching at pedestal  (d = average of the two directions)
    d = (out["checks"]["dir_x"]["d"] + out["checks"]["dir_y"]["d"]) / 2; ls = lam_s(cfg, d)
    hx, hy = (cx + d) / 2, (cy + d) / 2
    rect = box(-hx, -hy, hx, hy)
    b0 = rect.exterior.intersection(poly).length
    fr = [clamp(0.5 + max(abs(x) - hx, abs(y) - hy) / D) for x, y in pts]
    Vp = sum(Pu * f for f in fr)
    beta = max(cx, cy) / min(cx, cy); a_s = 40
    vcp = min(0.53 * (1 + 2 / beta), 0.265 * (a_s * d / b0 + 2), 1.06) * sq * ls if b0 > 0 else 1.06 * sq * ls
    vup = Vp / (b0 * d) if (n > 1 and b0 > 0) else 0
    out["checks"]["punch_col"] = dict(d=d, b0=b0, fractions=fr, Vu_t=Vp / 1000, vu=vup, phi_vc=cp["phiv"] * vcp,
                                      lam_s=ls, ok=vup <= cp["phiv"] * vcp + 1e-9, Vu_sheet_method_t=n * Pu / 1000 if n > 1 else 0)
    ok &= out["checks"]["punch_col"]["ok"]
    # punching around single piles (corner/edge), section at d/2 from pile face, clipped by cap edges
    pr = []
    if n > 1:
        for i, (x, y) in enumerate(pts):
            circ = Point(x, y).buffer((D + d) / 2, 128).exterior
            b0p = circ.intersection(poly).length
            ne = 0 if b0p > 0.99 * circ.length else (1 if b0p > 0.6 * circ.length else 2)
            asp = {0: 40, 1: 30, 2: 20}[ne]
            vcpp = min(0.265 * (asp * d / b0p + 2), 1.06) * sq * ls
            vpp = Pu / (b0p * d)
            pr.append(dict(pile=i + 1, b0=b0p, vu=vpp, phi_vc=cp["phiv"] * vcpp, ok=vpp <= cp["phiv"] * vcpp + 1e-9))
        worst = max(pr, key=lambda r: r["vu"] / r["phi_vc"])
        out["checks"]["punch_pile"] = worst; ok &= worst["ok"]
    # deep-cap flag (sectional shear vanishes -> strut-and-tie should be checked)
    amin = min(max(abs(x) - cx / 2, abs(y) - cy / 2) for x, y in pts) if n > 1 else 0
    if n > 1 and all(out["checks"][k]["beam_na"] for k in ("dir_x", "dir_y")):
        out["notes"].append("All piles within d of the pedestal face: one-way shear = 0 by dp/2 rule -> verify by STM (ACI 318-19 Ch.23) [Engineering judgment]")
    # temperature (top) steel, CEDA convention
    At = 0.0018 * 100 * min(h / 2, 50); tb = cfg.get("temp_bar", 16); Atb = math.pi * (tb / 10) ** 2 / 4
    st = min(30, math.floor(Atb / At * 100 / 2.5) * 2.5)
    out["checks"]["temp"] = dict(As_per_m=At, bar=tb, spacing=st, ok=st >= 10)
    if h > 90: out["notes"].append("h > 90 cm: provide side-face skin reinforcement (CEDA uses DB16@15-20)")
    if n == 1:
        out["notes"].append("1-pile cap: flexure from e only; bars as cage (ตะกร้อ) per CEDA F1")
    out["ok"] = bool(ok)
    return out

def design(cfg):
    res = []
    for T in cfg["types"]:
        if "h" in T: res.append(design_type(cfg, T, T["h"])); continue
        D = cfg["pile"]["D"]
        h = max(cfg.get("h_start", 60), C5(30 + cfg["cover"] + T.get("embed", cfg["embed"]) + 5)) if T.get("n", 2) > 1 else C5(D)
        while True:
            r = design_type(cfg, T, h)
            if r["ok"] or h > 400: break
            h += cfg.get("h_step", 5)
        res.append(r)
    return res

# ----------------------------------------------------------------- Excel (live formulas)
def to_excel(cfg, res, path):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
    from openpyxl.utils import get_column_letter as CL
    wb = Workbook(); sm = wb.active; sm.title = "Summary"
    B = Font(bold=True); INP = PatternFill("solid", fgColor="FFF2CC"); HD = PatternFill("solid", fgColor="DDEBF7")
    cp = code_par(cfg)
    sm.append([cfg.get("project", ""), "Pile cap design summary", cp["code"], "size effect λs: " + ("ON" if cfg.get("size_effect") else "OFF")])
    sm["A1"].font = B
    sm.append(["Type", "n", "Pile D (cm)", "Qa (t)", "Pu/pile (t)", "B x L (m)", "h (cm)", "Main X", "Main Y", "Top (temp)", "Punch col vu/φvc", "Beam X", "Beam Y", "Pile punch", "Status", "Notes"])
    for c in sm[2]: c.font = B; c.fill = HD
    for r in res:
        ws = wb.create_sheet(r["name"][:30]); _sheet(ws, cfg, r, cp, B, INP, HD)
        bx = r["outline"]; xs = [p[0] for p in bx]; ys = [p[1] for p in bx]
        X, Y = r["checks"]["dir_x"], r["checks"]["dir_y"]; P = r["checks"]["punch_col"]
        sm.append([r["name"], r["n"], cfg["pile"]["D"], cfg["pile"]["Qa"], round(r["Pu_t"], 1),
                   f"{(max(xs)-min(xs))/100:.2f} x {(max(ys)-min(ys))/100:.2f}", r["h"],
                   f"{X['nbars']}-DB{X['db']} ({X['anchorage']})", f"{Y['nbars']}-DB{Y['db']} ({Y['anchorage']})",
                   f"DB{r['checks']['temp']['bar']}@{r['checks']['temp']['spacing']/100:.3f}",
                   round(P["vu"] / P["phi_vc"], 2) if P["phi_vc"] else "-",
                   round(X["vu"] / X["phi_vc"], 2), round(Y["vu"] / Y["phi_vc"], 2),
                   round(r["checks"]["punch_pile"]["vu"] / r["checks"]["punch_pile"]["phi_vc"], 2) if "punch_pile" in r["checks"] else "-",
                   "O.K." if r["ok"] else "NOT O.K.", " | ".join(r["notes"])])
    for col in range(1, 17): sm.column_dimensions[CL(col)].width = 14
    wb.save(path)

def _sheet(ws, cfg, r, cp, B, INP, HD):
    from openpyxl.utils import get_column_letter as CL
    cell = {}; row = [1]
    def put(key, label, val, unit="", inp=False, fmt=None):
        i = row[0]; ws.cell(i, 1, label); c = ws.cell(i, 3, val); ws.cell(i, 4, unit)
        if inp: c.fill = INP
        if fmt: c.number_format = fmt
        cell[key] = f"$C${i}"; row[0] += 1; return c
    def head(t):
        ws.cell(row[0], 1, t).font = B; row[0] += 1
    X, Y = r["checks"]["dir_x"], r["checks"]["dir_y"]
    ws.cell(1, 1, f"{cfg.get('project','')}   —   {r['name']}  ({r['n']}-pile cap)").font = B; row[0] = 2
    ws.cell(2, 1, f"Basis: {cp['code']}; Pu/pile = factor × Qa (+ cap weight); shear by dp/2 rule (ACI 318 §13.4.2.5); λs {'ON' if cfg.get('size_effect') else 'OFF'}"); row[0] = 4
    head("1. Input (yellow = editable)")
    put("fc", "f'c (cylinder)", cfg["fc"], "ksc", True); put("fy", "fy", cfg["fy"], "ksc", True)
    put("D", "Pile diameter Dp", cfg["pile"]["D"], "cm", True); put("Qa", "Pile allowable Qa", cfg["pile"]["Qa"], "t/pile", True)
    put("fac", "Factor Pu = k·Qa (eng. judgment)", cfg.get("factor", 1.55), "", True)
    put("h", "Cap thickness h", r["h"], "cm", True); put("cov", "Cover", cfg["cover"], "cm", True)
    put("emb", "Pile embedment", r.get("embed", cfg["embed"]), "cm", True)
    put("cx", "Pedestal cx", r["pedestal"][0], "cm", True); put("cy", "Pedestal cy", r["pedestal"][1], "cm", True)
    put("e", "Pile eccentricity e (tolerance)", cfg.get("e", 10), "cm", True)
    put("dbx", "Main bar X  DB", X["db"], "mm", True); put("dby", "Main bar Y  DB", Y["db"], "mm", True)
    put("phib", "φ flexure", cp["phib"], "", True); put("phiv", "φ shear", cp["phiv"], "", True)
    put("area", "Cap plan area (geometry)", round(r["area_m2"], 4), "m²")
    wf = {"factored": 1.4, "service": 1.0, "none": 0.0}[cfg.get("cap_weight", "factored")]
    put("wf", "Cap weight factor", wf, "", True)
    put("W", "Cap weight", f"=2.4*{cell['area']}*{cell['h']}/100", "t", fmt="0.00")
    put("Pu", "Pu per pile", f"=({cell['fac']}*{cell['Qa']}+{cell['wf']}*{cell['W']}/{r['n']})*1000", "kg", fmt="#,##0")
    put("dx", "d (X bars) = h-cov-emb-1.5db", f"={cell['h']}-{cell['cov']}-{cell['emb']}-1.5*{cell['dbx']}/10", "cm", fmt="0.0")
    put("dy", "d (Y bars)", f"={cell['h']}-{cell['cov']}-{cell['emb']}-1.5*{cell['dby']}/10", "cm", fmt="0.0")
    put("dav", "d average (punching)", f"=({cell['dx']}+{cell['dy']})/2", "cm", fmt="0.0")
    put("ls", "λs (1.0 = not considered)", round(r["checks"]["punch_col"]["lam_s"], 4), "", True)
    row[0] += 1; head("2. Pile table  (frac = share of pile reaction acting on section, linear between ±Dp/2)")
    hdr = ["Pile", "x (cm)", "y (cm)", "lever +X", "lever -X", "lever +Y", "lever -Y", "Vfrac +X", "Vfrac -X", "Vfrac +Y", "Vfrac -Y", "Punch frac"]
    for j, t in enumerate(hdr): c = ws.cell(row[0], 1 + j, t); c.font = B; c.fill = HD
    r0 = row[0] + 1
    D, cx, cy, e, dx, dy, dv = cell["D"], cell["cx"], cell["cy"], cell["e"], cell["dx"], cell["dy"], cell["dav"]
    for k, (x, y) in enumerate(r["coords"]):
        i = r0 + k; ws.cell(i, 1, k + 1); ws.cell(i, 2, round(x, 4)).fill = INP; ws.cell(i, 3, round(y, 4)).fill = INP
        X_, Y_ = f"B{i}", f"C{i}"
        ws.cell(i, 4, f"=IF({X_}>{cx}/2,{X_}-{cx}/2+{e},0)"); ws.cell(i, 5, f"=IF(-{X_}>{cx}/2,-{X_}-{cx}/2+{e},0)")
        ws.cell(i, 6, f"=IF({Y_}>{cy}/2,{Y_}-{cy}/2+{e},0)"); ws.cell(i, 7, f"=IF(-{Y_}>{cy}/2,-{Y_}-{cy}/2+{e},0)")
        ws.cell(i, 8, f"=MIN(1,MAX(0,0.5+({X_}-({cx}/2+{dx}))/{D}))"); ws.cell(i, 9, f"=MIN(1,MAX(0,0.5+(-{X_}-({cx}/2+{dx}))/{D}))")
        ws.cell(i, 10, f"=MIN(1,MAX(0,0.5+({Y_}-({cy}/2+{dy}))/{D}))"); ws.cell(i, 11, f"=MIN(1,MAX(0,0.5+(-{Y_}-({cy}/2+{dy}))/{D}))")
        ws.cell(i, 12, f"=MIN(1,MAX(0,0.5+MAX(ABS({X_})-({cx}+{dv})/2,ABS({Y_})-({cy}+{dv})/2)/{D}))")
        for j in range(4, 13): ws.cell(i, j).number_format = "0.000"
    r1 = r0 + len(r["coords"]) - 1; row[0] = r1 + 2
    rng = lambda c: f"{c}{r0}:{c}{r1}"
    head("3. Flexure at pedestal face  (Mu = Σ Pu·(lever))")
    for ax, d_, lp, ln_, D_ in (("X", dx, "D", "E", X), ("Y", dy, "F", "G", Y)):
        if r["n"] == 1:
            put("Mu" + ax, f"Mu {ax} = Pu·e/100 (1-pile, CEDA F1)", f"={cell['Pu']}*{cell['e']}/100", "kg-m", fmt="#,##0")
        else:
            put("Mu" + ax, f"Mu {ax} = Pu·max(Σlever+,Σlever-)/100", f"={cell['Pu']}*MAX(SUM({rng(lp)}),SUM({rng(ln_)}))/100", "kg-m", fmt="#,##0")
        put("bf" + ax, f"b at face ({ax}-bars, geometry)", round(D_["b_face"], 2), "cm")
        put("Ru" + ax, "Ru = Mu/(φ b d²)", f"={cell['Mu'+ax]}*100/({cell['phib']}*{cell['bf'+ax]}*{d_}^2)", "ksc", fmt="0.000")
        put("rr" + ax, "ρ req", f"=0.85*{cell['fc']}/{cell['fy']}*(1-SQRT(1-2*{cell['Ru'+ax]}/(0.85*{cell['fc']})))", "", fmt="0.00000")
        rmg = (f"MAX(0.0018*4200/{cell['fy']},0.0014)*{cell['h']}/{d_}" if cp["code"].startswith("ACI")
               else f"0.0018*MIN(1,4000/{cell['fy']})*{cell['h']}/{d_}")
        put("rm" + ax, "ρ min = max(min(14/fy,1.33ρ), temp·h/d)", f"=MAX(MIN(14/{cell['fy']},1.33*{cell['rr'+ax]}),{rmg})", "", fmt="0.00000")
        put("As" + ax, "As req", f"=MAX({cell['rr'+ax]},{cell['rm'+ax]})*{cell['bf'+ax]}*{d_}", "cm²", fmt="0.00")
        put("nb" + ax, f"Use n bars DB{D_['db']}", D_["nbars"], "bars", True)
        db_ = cell["db" + ax.lower()]
        put("Ap" + ax, "As provided", f"={cell['nb'+ax]}*PI()*({db_}/10)^2/4", "cm²", fmt="0.00")
        put("ck" + ax, "As check", f"=IF({cell['Ap'+ax]}>={cell['As'+ax]},\"O.K.\",\"NOT O.K.\")")
        put("sp" + ax, "Spacing (10-30 cm)", f"=({cell['bf'+ax]}-2*{cell['cov']})/({cell['nb'+ax]}-1)", "cm", fmt="0.0")
        put("ld" + ax, "ld straight / avail. from face", f"{D_['ld']:.1f} / {D_['l_avail']:.1f}  -> {D_['anchorage']} (ldh={D_['ldh']:.1f})", "cm")
    row[0] += 1; head("4. One-way (beam) shear at d from pedestal face")
    sq = f"SQRT({cell['fc']})"
    vc1 = (f"MIN(2.12*{cell['ls']}*MIN(0.02,{{As}}/({{b}}*{{d}}))^(1/3)*{sq},1.33*{sq})"
           if cp["code"].startswith("ACI") and cfg.get("size_effect") else f"0.53*{sq}")
    for ax, d_, fp, fn, D_ in (("X", dx, "H", "I", X), ("Y", dy, "J", "K", Y)):
        put("bs" + ax, f"b at critical section ({ax}, geometry)", round(D_["b_sec"], 2), "cm")
        put("Vu" + ax, "Vu = Pu·max(Σfrac+,Σfrac-)", f"={cell['Pu']}*MAX(SUM({rng(fp)}),SUM({rng(fn)}))", "kg", fmt="#,##0")
        put("vu" + ax, "vu = Vu/(b d)", f"=IF({cell['bs'+ax]}>0,{cell['Vu'+ax]}/({cell['bs'+ax]}*{d_}),0)", "ksc", fmt="0.00")
        put("vc" + ax, "φvc", "=" + cell["phiv"] + "*" + vc1.format(As=cell["Ap" + ax], b=cell["bf" + ax], d=d_), "ksc", fmt="0.00")
        put("vk" + ax, "Beam shear", f"=IF({cell['vu'+ax]}<={cell['vc'+ax]},\"O.K.\",\"NOT O.K.\")")
    row[0] += 1; head("5. Two-way (punching) shear at d/2 from pedestal")
    put("b0", "b0 (clipped by cap edge, geometry)", round(r["checks"]["punch_col"]["b0"], 2), "cm")
    put("Vp", "Vu = Pu·Σ punch frac", f"={cell['Pu']}*SUM({rng('L')})", "kg", fmt="#,##0")
    put("Vps", "(old CEDA sheet: n·Pu, for comparison)", f"={r['n']}*{cell['Pu']}", "kg", fmt="#,##0")
    put("vp", "vu = Vu/(b0 d)", f"={cell['Vp']}/({cell['b0']}*{cell['dav']})", "ksc", fmt="0.00")
    put("bt", "β = long/short pedestal", f"=MAX({cell['cx']},{cell['cy']})/MIN({cell['cx']},{cell['cy']})", "", fmt="0.00")
    put("vcp", "φvc = φ·λs·min(0.53(1+2/β), 0.265(αs d/b0+2), 1.06)√fc'",
        f"={cell['phiv']}*{cell['ls']}*MIN(0.53*(1+2/{cell['bt']}),0.265*(40*{cell['dav']}/{cell['b0']}+2),1.06)*{sq}", "ksc", fmt="0.00")
    put("pk", "Punching (column)", f"=IF({cell['vp']}<={cell['vcp']},\"O.K.\",\"NOT O.K.\")")
    if "punch_pile" in r["checks"]:
        pp = r["checks"]["punch_pile"]
        put("pp", f"Punching around pile #{pp['pile']} (b0={pp['b0']:.1f} cm)",
            f"vu={pp['vu']:.2f} ≤ φvc={pp['phi_vc']:.2f} ksc -> {'O.K.' if pp['ok'] else 'NOT O.K.'}")
    row[0] += 1; head("6. Top (temperature) steel — CEDA: 0.0018·b·min(h/2,50)")
    t = r["checks"]["temp"]
    put("At", "As temp", f"=0.0018*100*MIN({cell['h']}/2,50)", "cm²/m", fmt="0.00")
    put("tb", f"Use DB{t['bar']} @", t["spacing"], "cm", True)
    put("tk", "Check", f"=IF(PI()*({t['bar']}/10)^2/4*100/{cell['tb']}>={cell['At']},\"O.K.\",\"NOT O.K.\")")
    row[0] += 1
    for nt in r["notes"]: ws.cell(row[0], 1, "Note: " + nt); row[0] += 1
    ws.column_dimensions["A"].width = 44; ws.column_dimensions["C"].width = 16
    for c in "BDEFGHIJKL": ws.column_dimensions[c].width = 10

if __name__ == "__main__":
    cfg = json.load(open(sys.argv[1])); res = design(cfg)
    json.dump(res, open(sys.argv[1].replace(".json", "_result.json"), "w"), indent=1, default=str, ensure_ascii=False)
    if len(sys.argv) > 2: to_excel(cfg, res, sys.argv[2])
    for r in res:
        X, Y, P = r["checks"]["dir_x"], r["checks"]["dir_y"], r["checks"]["punch_col"]
        print(f"{r['name']}: n={r['n']} h={r['h']} ok={r['ok']} | X {X['nbars']}DB{X['db']} vu/vc={X['vu']:.2f}/{X['phi_vc']:.2f} {X['anchorage']}"
              f" | Y {Y['nbars']}DB{Y['db']} vu/vc={Y['vu']:.2f}/{Y['phi_vc']:.2f} | punch {P['vu']:.2f}/{P['phi_vc']:.2f} (sheet n·Pu: {P['Vu_sheet_method_t']:.0f}t vs {P['Vu_t']:.0f}t)"
              + (f" | pile-punch {r['checks']['punch_pile']['vu']:.2f}/{r['checks']['punch_pile']['phi_vc']:.2f}" if 'punch_pile' in r['checks'] else ""))
        for nt in r["notes"]: print("   note:", nt)
