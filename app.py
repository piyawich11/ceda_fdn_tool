"""CEDA Foundation Tool – Step 01 (pile capacity) and Step 02 (pile-cap design).
Run:  streamlit run app.py      (runs locally, no internet / no AI needed)
Calculation engines are the CEDA skill engines, kept verbatim in ceda_fdn/.
"""
import io, json, os, tempfile
import pandas as pd
import streamlit as st

from ceda_fdn import pile_capacity as pc, cap_design as cd, helpers as hp

APP_VERSION = "0.1.0"
st.set_page_config(page_title="CEDA Foundation Tool", page_icon="🏗️", layout="wide")
ss = st.session_state

# ------------------------------------------------------------------ default tables (structure only, no design values)
LAYER_COLS = ["BH", "name", "type", "top", "bot", "gamma", "N", "Su"]
if "bh_df" not in ss:
    ss.bh_df = pd.DataFrame([{"BH": "BH-1", "name": "", "type": "Clay", "top": 0.0, "bot": None,
                              "gamma": None, "N": 0.0, "Su": 0.0}], columns=LAYER_COLS)
if "gwl_df" not in ss:
    ss.gwl_df = pd.DataFrame([{"BH": "BH-1", "GWL (m)": None}])
if "types_df" not in ss:
    ss.types_df = pd.DataFrame([{"name": f"F{n}", "n": n, "h": None, "embed": None, "bars": "", "coords": ""}
                                for n in range(1, 10)])

# CEDA proposed values (Engineering judgment) – filled ONLY when the designer presses the button
S1_PROPOSED = {"s1_slurry": "polymer", "s1_cutoff": 1.0, "s1_fs": 2.5, "s1_fc": 280.0, "s1_qcoef": 0.29,
               "s1_diams": "0.8, 1.0, 1.2", "s1_from": 10.0, "s1_to": 60.0, "s1_step": 0.5}
S2_PROPOSED = {"s2_fc": 320.0, "s2_fy": 5000.0, "s2_cover": 7.5, "s2_D": 80.0, "s2_Qa": 215.0, "s2_factor": 1.55,
               "s2_spD": 2.5, "s2_edgeD": 1.0, "s2_cx": 80.0, "s2_cy": 80.0, "s2_e": 10.0, "s2_capw": "factored",
               "s2_bars": "20, 25, 28, 32", "s2_smin": 10.0, "s2_smax": 30.0, "s2_tbar": 16, "s2_h0": 60.0, "s2_hstep": 5.0}
# items with NO safe default – never auto-filled (skill rule): s2_code, s2_lams, s2_embed


def fill(d):
    for k, v in d.items():
        if ss.get(k) in (None, ""):
            ss[k] = v


def missing(keys):
    return [k for k in keys if ss.get(k) in (None, "")]


def floats(txt):
    return [float(x) for x in str(txt).replace(";", ",").split(",") if x.strip()]


# ------------------------------------------------------------------ sidebar: project file
with st.sidebar:
    st.markdown(f"### 🏗️ CEDA Foundation Tool\nv{APP_VERSION} · Step 01–02")
    st.text_input("ชื่อโปรเจกต์", key="project")
    st.caption("บันทึก/เปิดไฟล์โปรเจกต์ (.json) เก็บ input ทั้งหมดของ Step 01–02")
    keys = [k for k in list(S1_PROPOSED) + list(S2_PROPOSED) +
            ["project", "s1_mode", "s1_target", "s2_code", "s2_lams", "s2_embed",
             "s1b_D", "s1b_Qa", "s1b_tip", "s1b_type"]]
    proj = {"app_version": APP_VERSION, "state": {k: ss.get(k) for k in keys},
            "layers": ss.bh_df.to_dict("records"), "gwl": ss.gwl_df.to_dict("records"),
            "types": ss.types_df.to_dict("records")}
    st.download_button("💾 บันทึกโปรเจกต์", json.dumps(proj, ensure_ascii=False, indent=1, default=str),
                       file_name=f"{ss.get('project') or 'project'}.ceda.json", mime="application/json")

    def _load():
        f = ss.get("proj_upload")
        if not f: return
        p = json.load(f)
        for k, v in p.get("state", {}).items(): ss[k] = v
        ss.bh_df = pd.DataFrame(p["layers"], columns=LAYER_COLS); ss.gwl_df = pd.DataFrame(p["gwl"])
        ss.types_df = pd.DataFrame(p["types"])
        for k in ("ed_layers", "ed_gwl", "ed_types"): ss.pop(k, None)
    st.file_uploader("📂 เปิดโปรเจกต์", type=["json"], key="proj_upload", on_change=_load)
    st.divider()
    st.caption("Tag: **[Code]** code requirement · **[Practice]** common practice · "
               "**[EJ]** engineering judgment · **[Assume]** assumption")

tab1, tab2 = st.tabs(["Step 01 · Pile capacity", "Step 02 · Pile-cap design"])

# ================================================================== STEP 01
with tab1:
    st.subheader("Step 01 – Bored-pile capacity (CEDA friction + end-bearing)")
    mode = st.radio("Input mode", ["A – คำนวณจาก boring log", "B – ผู้ออกแบบกำหนด D / Qa / tip"],
                    index=None, key="s1_mode", horizontal=True)

    if mode and mode.startswith("B"):
        c = st.columns(4)
        c[0].number_input("D (cm)", value=None, key="s1b_D", step=5.0)
        c[1].number_input("Qa (t/pile)", value=None, key="s1b_Qa", step=5.0)
        c[2].number_input("Tip (m จากผิวดิน)", value=None, key="s1b_tip", step=0.5)
        c[3].text_input("Pile type", key="s1b_type", placeholder="เช่น bored polymer")
        miss = missing(["s1b_D", "s1b_Qa", "s1b_tip", "s1b_type"])
        if miss:
            st.info("กรอกให้ครบทั้ง 4 ค่า (ไม่ดึงจากโปรเจกต์อื่น)")
        else:
            spec = {"D": ss.s1b_D, "Qa": ss.s1b_Qa, "tip": ss.s1b_tip, "type": ss.s1b_type, "source": "Mode B"}
            st.json(spec)

            def _to_s2_b():
                ss.s2_D, ss.s2_Qa = float(ss.s1b_D), float(ss.s1b_Qa)
            st.button("➡️ ส่ง D, Qa ไป Step 02", on_click=_to_s2_b)
            st.download_button("pile_spec.json", json.dumps(spec, ensure_ascii=False), "pile_spec.json")

    elif mode:
        st.markdown("**1) Design criteria** — ช่องว่าง = ยังไม่ยืนยัน · ปุ่มด้านล่างเติมเฉพาะช่องที่ว่างด้วยค่าเสนอ CEDA **[EJ]**")
        st.button("เติมค่าเสนอ CEDA ในช่องที่ว่าง", on_click=fill, args=(S1_PROPOSED,), key="b_fill1")
        c = st.columns(5)
        c[0].selectbox("Slurry", ["polymer", "bentonite"], index=None, key="s1_slurry")
        c[1].number_input("Cut-off depth (m)", value=None, key="s1_cutoff", step=0.5)
        c[2].number_input("FS (soil)", value=None, key="s1_fs", step=0.1)
        c[3].number_input("f'c pile (ksc)", value=None, key="s1_fc", step=10.0)
        c[4].number_input("Qstr coef (×f'c·Ag) [Practice: CEDA sheet]", value=None, key="s1_qcoef", step=0.01, format="%.3f")
        c = st.columns(5)
        c[0].text_input("Diameters to try (m)", key="s1_diams", placeholder="0.8, 1.0, 1.2")
        c[1].number_input("Target Qa (t) – optional", value=None, key="s1_target", step=5.0)
        c[2].number_input("Scan from (m)", value=None, key="s1_from", step=0.5)
        c[3].number_input("Scan to (m)", value=None, key="s1_to", step=0.5)
        c[4].number_input("Scan step (m)", value=None, key="s1_step", step=0.5)

        st.markdown("**2) Boring log** — วาง (Ctrl+V) จาก Excel ได้ · หน่วย m, t/m³, blows/ft, t/m² · "
                    "ห้ามเดา Su/γt: Clay ที่มี N แต่ไม่มี Su ให้คงไว้ 0 แล้วโปรแกรมจะเตือน [C2]")
        cc = st.columns([4, 1])
        with cc[0]:
            ed_layers = st.data_editor(
                ss.bh_df, num_rows="dynamic", key="ed_layers", width="stretch",
                column_config={"type": st.column_config.SelectboxColumn("type", options=["Clay", "Sand"]),
                               "gamma": st.column_config.NumberColumn("γt (t/m³)"),
                               "Su": st.column_config.NumberColumn("Su (t/m²)")})
        with cc[1]:
            ed_gwl = st.data_editor(ss.gwl_df, num_rows="dynamic", key="ed_gwl", width="stretch")

        need = ["s1_slurry", "s1_cutoff", "s1_fs", "s1_fc", "s1_qcoef", "s1_diams", "s1_from", "s1_to", "s1_step"]
        miss = missing(need)
        if miss:
            st.warning("ยังไม่ยืนยัน: " + ", ".join(m.replace("s1_", "") for m in miss))
        gwl = {str(r["BH"]).strip(): (None if pd.isna(r["GWL (m)"]) else float(r["GWL (m)"]))
               for r in ed_gwl.to_dict("records") if r.get("BH")}
        rows = [{k: (None if (isinstance(v, float) and pd.isna(v)) else v) for k, v in r.items()}
                for r in ed_layers.to_dict("records")]
        bhs, errs = hp.layers_to_boreholes(rows, gwl)
        for e in errs:
            st.error(e)
        confirm = st.checkbox("ตรวจตาราง layer ของทุก BH และ criteria แล้ว", key="s1_confirm")

        if st.button("▶ Run Step 01", type="primary", disabled=bool(miss or errs or not confirm)):
            ss.bh_df, ss.gwl_df = ed_layers, ed_gwl
            cfg = {"project": ss.get("project", ""), "slurry": ss.s1_slurry, "cutoff": ss.s1_cutoff,
                   "fs_soil": ss.s1_fs, "fc": ss.s1_fc, "qstr_coef": ss.s1_qcoef, "diameters": floats(ss.s1_diams),
                   "scan": {"from": ss.s1_from, "to": ss.s1_to, "step": ss.s1_step}, "boreholes": bhs}
            if ss.get("s1_target"):
                cfg["target_qa"] = ss.s1_target
            ss.s1_cfg, ss.s1_res = cfg, pc.run(cfg)

        if "s1_res" in ss:
            cfg, res = ss.s1_cfg, ss.s1_res
            st.markdown("### ผลลัพธ์")
            if cfg.get("target_qa"):
                rec = hp.recommend(cfg, res)
                best = next((o for o in rec if o["recommended"]), None)
                if best:
                    st.success(f"**ข้อเสนอ [EJ]: D {best['D']:.2f} m, tip {best['tip']:.1f} m** "
                               f"(L = {best['L']:.1f} m, ปริมาตร {best['vol']:.2f} m³/ต้น) — ปริมาตรคอนกรีตน้อยสุดที่ "
                               f"ปลายอยู่ในชั้นแข็ง (Sand หรือ Su ≥ {hp.COMPETENT_SU:.0f} t/m²) ทุก BH และ soil governs")
                else:
                    st.warning("ไม่มีตัวเลือกที่ผ่านทุกเงื่อนไข (target / ชั้นแข็ง / soil governs) — ผู้ออกแบบพิจารณาเอง")
                st.markdown("**Governing tip (ลึกสุดของทุก BH) – ตรวจซ้ำที่ tip นี้ในทุก BH**")
                st.dataframe(pd.DataFrame([{
                    "D (m)": o["D"], "Tip (m)": o.get("tip"), "L (m)": o.get("L"),
                    "Vol (m³)": round(o["vol"], 2) if o.get("vol") else None,
                    "Qa min ทุก BH (t)": round(o["Qa_min"], 1) if o.get("Qa_min") else None,
                    "tip layer": o.get("tip_layers"), "ชั้นแข็ง": o.get("competent"),
                    "soil governs": o.get("soil_gov"), "≥ target": o.get("Qa_ok"),
                    "แนะนำ": "✅" if o["recommended"] else "", "หมายเหตุ": o.get("status", "")} for o in rec]),
                    hide_index=True, width="stretch")
                st.markdown("**Back-calculation แยกตาม BH (tip สั้นสุดที่ Qa ≥ target)**")
                st.dataframe(pd.DataFrame([{"BH": b["name"], "D": r["D"], "tip": r.get("tip"),
                                            "Qult": r.get("Qult"), "Qa": r.get("Qa"), "governs": r.get("governs"),
                                            "tip layer": r.get("tip_layer"), "note": r.get("note")}
                                           for b in res["boreholes"] for r in b["back_calc"]]).round(2),
                             hide_index=True, width="stretch")

            bsel = st.selectbox("กราฟ Qa – ความลึก", [b["name"] for b in res["boreholes"]])
            b = next(x for x in res["boreholes"] if x["name"] == bsel)
            df = pd.DataFrame(b["rows"]).pivot_table(index="tip", columns="D", values="Qa")
            df.columns = [f"D{c:g} m" for c in df.columns]
            st.line_chart(df, x_label="Tip depth (m)", y_label="Qa (t)")

            if res["warnings"]:
                with st.expander(f"⚠️ Engine warnings ({len(res['warnings'])})", expanded=True):
                    for w in res["warnings"]: st.write("•", w)
            st.info("**[EJ] ต้องระบุทุกครั้ง:** ไม่รวม negative skin friction ในดินเหนียวอ่อนกรุงเทพฯ · σ'v ที่กลางชั้น "
                    "ทั้ง fs และ qb (วิธี CEDA sheet) · qb ไม่มีค่าจำกัดบน · ควรอ้างแหล่งที่มาของ correlation φ–N', β, Nq "
                    "ในรายงาน · **[Practice]** ยืนยัน Qa ด้วย static / dynamic load test")

            with tempfile.TemporaryDirectory() as d:
                p = os.path.join(d, "pile_capacity.xlsx"); pc.to_excel(cfg, res, p)
                st.download_button("⬇️ pile_capacity.xlsx", open(p, "rb").read(), "pile_capacity.xlsx")

            st.markdown("**ส่งต่อ Step 02** – ผู้ออกแบบเลือกเอง")
            c = st.columns(3)
            Dsel = c[0].selectbox("D (m)", cfg["diameters"], key="s1_pickD")
            tip = c[1].number_input("Tip (m)", value=None, key="s1_picktip", step=0.5)
            qa = c[2].number_input("Qa ที่ใช้ (t/pile)", value=None, key="s1_pickQa", step=5.0)
            if tip is not None and qa is not None:
                spec = {"D": Dsel * 100, "Qa": qa, "tip": tip, "type": f"bored {cfg['slurry']}", "source": "Mode A"}

                def _to_s2_a():
                    ss.s2_D, ss.s2_Qa = float(spec["D"]), float(spec["Qa"])
                st.button("➡️ ส่ง D, Qa ไป Step 02", on_click=_to_s2_a, key="b_to2a")
                st.download_button("pile_spec.json", json.dumps(spec, ensure_ascii=False), "pile_spec.json", key="dl_spec_a")

# ================================================================== STEP 02
with tab2:
    st.subheader("Step 02 – Pile-cap design (dp/2 rule, live-formula Excel)")
    st.markdown("**1) ต้องเลือกเองทุกครั้ง (ไม่มีค่า default ที่ปลอดภัย)**")
    c = st.columns(3)
    c[0].selectbox("Code basis", ["TH", "ACI318-19"], index=None, key="s2_code",
                   help="TH: 1.4D+1.7L, φb 0.90 / φv 0.85 (CEDA) · ACI318-19: φv 0.75")
    c[1].selectbox("Size effect λs (ACI §22.5.5.1, §22.6.5.2)", ["OFF", "ON"], index=None, key="s2_lams")
    c[2].number_input("Pile embedment into cap (cm) – global", value=None, key="s2_embed", step=2.5,
                      help="แต่ละ type override ได้ในคอลัมน์ embed ของตาราง type")

    st.markdown("**2) Criteria อื่น** — ปุ่มเติมเฉพาะช่องว่างด้วยค่าเสนอ CEDA **[EJ]**")
    st.button("เติมค่าเสนอ CEDA ในช่องที่ว่าง", on_click=fill, args=(S2_PROPOSED,), key="b_fill2")
    c = st.columns(6)
    c[0].number_input("f'c (ksc)", value=None, key="s2_fc", step=10.0)
    c[1].number_input("fy (ksc)", value=None, key="s2_fy", step=100.0)
    c[2].number_input("Cover (cm)", value=None, key="s2_cover", step=0.5)
    c[3].number_input("Pile D (cm)", value=None, key="s2_D", step=5.0)
    c[4].number_input("Qa (t/pile)", value=None, key="s2_Qa", step=5.0)
    c[5].number_input("Pu factor k (Pu = k·Qa)", value=None, key="s2_factor", step=0.05)
    c = st.columns(6)
    c[0].number_input("Spacing (×D)", value=None, key="s2_spD", step=0.5)
    c[1].number_input("Edge (×D)", value=None, key="s2_edgeD", step=0.1)
    c[2].number_input("Pedestal cx (cm)", value=None, key="s2_cx", step=5.0)
    c[3].number_input("Pedestal cy (cm)", value=None, key="s2_cy", step=5.0)
    c[4].number_input("Pile eccentricity e (cm)", value=None, key="s2_e", step=2.5)
    c[5].selectbox("Cap weight", ["factored", "service", "none"], index=None, key="s2_capw")
    c = st.columns(6)
    c[0].text_input("Main bars DB (mm)", key="s2_bars", placeholder="20, 25, 28, 32")
    c[1].number_input("s min (cm)", value=None, key="s2_smin", step=1.0)
    c[2].number_input("s max (cm)", value=None, key="s2_smax", step=1.0)
    c[3].selectbox("Top bar DB", [12, 16, 20], index=None, key="s2_tbar")
    c[4].number_input("h start (cm)", value=None, key="s2_h0", step=5.0)
    c[5].number_input("h step (cm)", value=None, key="s2_hstep", step=5.0)

    st.markdown("**3) Type list** — h ว่าง = หา h เล็กสุดที่ผ่าน · h มีค่า = check only · bars เช่น `28` · "
                "coords (cm) สำหรับ layout พิเศษ เช่น `[[-100,0],[100,0],[0,170]]`")
    ed_types = st.data_editor(ss.types_df, num_rows="dynamic", key="ed_types", width="stretch",
                              column_config={"h": st.column_config.NumberColumn("h (cm)"),
                                             "embed": st.column_config.NumberColumn("embed (cm) override")})

    need2 = ["s2_code", "s2_lams", "s2_embed"] + list(S2_PROPOSED)
    miss2 = missing(need2)
    if miss2:
        st.warning("ยังไม่ยืนยัน: " + ", ".join(m.replace("s2_", "") for m in miss2))

    types, terr = [], []
    for i, r in enumerate(ed_types.to_dict("records"), 1):
        if not r.get("name"): continue
        T = {"name": str(r["name"]).strip()}
        try:
            if r.get("coords") and str(r["coords"]).strip():
                T["coords"] = json.loads(r["coords"])
            elif r.get("n") is not None and not pd.isna(r["n"]):
                T["n"] = int(r["n"])
            else:
                terr.append(f"{T['name']}: ต้องมี n หรือ coords"); continue
            if r.get("h") is not None and not pd.isna(r["h"]): T["h"] = float(r["h"])
            if r.get("embed") is not None and not pd.isna(r["embed"]): T["embed"] = float(r["embed"])
            if r.get("bars") and str(r["bars"]).strip(): T["bars"] = [int(x) for x in floats(r["bars"])]
        except Exception as e:
            terr.append(f"{T['name']}: {e}"); continue
        types.append(T)
    for e in terr: st.error(e)
    confirm2 = st.checkbox("ตรวจ criteria และ type list แล้ว", key="s2_confirm")

    if st.button("▶ Run Step 02", type="primary", disabled=bool(miss2 or terr or not types or not confirm2)):
        ss.types_df = ed_types
        cfg = {"project": ss.get("project", ""), "code": ss.s2_code, "size_effect": ss.s2_lams == "ON",
               "fc": ss.s2_fc, "fy": ss.s2_fy, "cover": ss.s2_cover, "embed": ss.s2_embed,
               "pile": {"D": ss.s2_D, "Qa": ss.s2_Qa}, "factor": ss.s2_factor, "spacing_D": ss.s2_spD,
               "edge_D": ss.s2_edgeD, "pedestal": [ss.s2_cx, ss.s2_cy], "e": ss.s2_e, "cap_weight": ss.s2_capw,
               "h_start": ss.s2_h0, "h_step": ss.s2_hstep, "bars": [int(x) for x in floats(ss.s2_bars)],
               "s_min": ss.s2_smin, "s_max": ss.s2_smax, "temp_bar": ss.s2_tbar, "types": types}
        with st.spinner("กำลังออกแบบ..."):
            ss.s2_cfg, ss.s2_res = cfg, cd.design(cfg)
        ss.pop("s2_verify", None)

    if "s2_res" in ss:
        cfg, res = ss.s2_cfg, ss.s2_res
        rows = []
        for r in res:
            X, Y, P = r["checks"]["dir_x"], r["checks"]["dir_y"], r["checks"]["punch_col"]
            xs, ys = zip(*r["outline"]); pp = r["checks"].get("punch_pile")
            util = {"Beam X": X["vu"] / X["phi_vc"], "Beam Y": Y["vu"] / Y["phi_vc"],
                    "Punch col": P["vu"] / P["phi_vc"] if P["phi_vc"] else 0,
                    "Punch pile": pp["vu"] / pp["phi_vc"] if pp else 0}
            gov = max(util, key=util.get) if max(util.values()) > 0 else "-"
            nonconv = (not r["ok"]) and r["h"] > 400
            rows.append({"Type": r["name"], "n": r["n"], "B×L (m)": f"{(max(xs)-min(xs))/100:.2f}×{(max(ys)-min(ys))/100:.2f}",
                         "h (cm)": r["h"], "embed": r["embed"], "Pu/pile (t)": round(r["Pu_t"], 1),
                         "Main X": f"{X['nbars']}-DB{X['db']} @{X['spacing']:.1f}", "Main Y": f"{Y['nbars']}-DB{Y['db']} @{Y['spacing']:.1f}",
                         "Anchor X/Y": f"{X['anchorage']} / {Y['anchorage']}",
                         "Top": f"DB{r['checks']['temp']['bar']}@{r['checks']['temp']['spacing']:g}",
                         **{k: round(v, 2) for k, v in util.items()}, "Governs": gov,
                         "Status": "O.K." if r["ok"] else ("NOT CONVERGED (h>400)" if nonconv else "NOT O.K.")})
        sdf = pd.DataFrame(rows)
        st.dataframe(sdf.style.map(lambda v: "color:#c00000;font-weight:bold" if str(v).startswith("NOT") else "",
                                   subset=["Status"]), hide_index=True, width="stretch")
        if any(r["Status"].startswith("NOT CONVERGED") for r in rows):
            st.error("มี type ที่หา h ไม่ได้ภายใน 400 cm — ตรวจ check ที่ governs ใน expander ด้านล่าง "
                     "(เช่น punching รอบเข็มของฐาน 2 ต้นเมื่อเปิด λs) และพิจารณาวิธีตรวจอื่น เช่น STM [EJ]")

        for r in res:
            with st.expander(f"{r['name']} – รายละเอียด"):
                c = st.columns([1, 2])
                c[0].pyplot(hp.cap_figure(r, cfg["pile"]["D"]))
                X, Y, P = r["checks"]["dir_x"], r["checks"]["dir_y"], r["checks"]["punch_col"]
                det = pd.DataFrame({
                    "X": [X["db"], X["d"], X["Mu_tm"], X["b_face"], X["rho_use"], X["As_req"], X["As_prov"], X["Vu_t"], X["b_sec"], X["vu"], X["phi_vc"], X["ld"], X["l_avail"]],
                    "Y": [Y["db"], Y["d"], Y["Mu_tm"], Y["b_face"], Y["rho_use"], Y["As_req"], Y["As_prov"], Y["Vu_t"], Y["b_sec"], Y["vu"], Y["phi_vc"], Y["ld"], Y["l_avail"]]},
                    index=["DB (mm)", "d (cm)", "Mu (t-m)", "b face (cm)", "ρ use", "As req (cm²)", "As prov (cm²)",
                           "Vu beam (t)", "b sec (cm)", "vu (ksc)", "φvc (ksc)", "ld (cm)", "l avail (cm)"])
                c[1].dataframe(det.round(4), width="stretch")
                c[1].write(f"Punching (column): b0 = {P['b0']:.1f} cm, Vu = {P['Vu_t']:.1f} t, vu = {P['vu']:.2f} ≤ φvc = {P['phi_vc']:.2f} ksc "
                           f"(old sheet n·Pu = {P['Vu_sheet_method_t']:.0f} t, for comparison)")
                if "punch_pile" in r["checks"]:
                    pp = r["checks"]["punch_pile"]
                    c[1].write(f"Punching around pile #{pp['pile']}: b0 = {pp['b0']:.1f} cm, vu = {pp['vu']:.2f} ≤ φvc = {pp['phi_vc']:.2f} ksc")
                for nt in r["notes"]: c[1].warning(nt)

        st.info("**ไม่ครอบคลุม:** column moment บน cap (ใช้ pile reaction จริงใน Step 03) · dowel ของ pedestal/เสา · "
                "tension/uplift pile · ฐานรวมหลายเสา (ทุก type ออกแบบสำหรับ pedestal กลางต้นเดียว) · "
                "Chebyshev distance ที่มุมใน punching เป็น [EJ]")

        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "cap_design.xlsx"); cd.to_excel(cfg, res, p); xbytes = open(p, "rb").read()
            if st.button("🔎 ตรวจ Excel (recalc ด้วย LibreOffice เทียบ engine ±0.1%)"):
                try:
                    ss.s2_verify = hp.verify_cap_excel(p, res)
                except Exception as e:
                    ss.s2_verify = str(e)
        if "s2_verify" in ss:
            v = ss.s2_verify
            if isinstance(v, str): st.warning(v)
            else:
                bad, errc = v
                (st.success("Excel ตรงกับ engine ทุกค่า, ไม่มี #REF!/#DIV/0!") if not bad and not errc
                 else st.error("ห้ามส่ง Excel นี้: " + "; ".join(bad + errc)))
        c = st.columns(2)
        c[0].download_button("⬇️ cap_design.xlsx (live formulas)", xbytes, "cap_design.xlsx")
        c[1].download_button("⬇️ cap_result.json (type library → Step 03)",
                             json.dumps(res, ensure_ascii=False, indent=1, default=str), "cap_result.json")
