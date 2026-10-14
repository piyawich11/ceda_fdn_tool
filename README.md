# CEDA Foundation Tool v0.1 (Step 01–02)

โปรแกรมช่วยคำนวณฐานรากเสาเข็มที่รันบนเครื่องของเราเอง (localhost) ไม่ต้องใช้อินเทอร์เน็ตและไม่ใช้ AI

- **Step 01:** Bored-pile capacity จาก boring log (Mode A) หรือบันทึกค่าที่ผู้ออกแบบกำหนด (Mode B)
- **Step 02:** Pile-cap design 1–9 ต้นหรือ layout พิเศษ ออก Excel แบบ live formula และ type library (`cap_result.json`) สำหรับ Step 03

## ติดตั้งและใช้งาน (Windows)
1. ติดตั้ง Python 3.10 ขึ้นไปจาก python.org และติ๊ก "Add to PATH"
2. ดับเบิลคลิก `install.bat` (ทำครั้งเดียว) ระบบจะรัน regression test และต้องขึ้น **ALL PASS**
3. ดับเบิลคลิก `run_app.bat` แล้วโปรแกรมจะเปิดในเบราว์เซอร์ที่ `http://localhost:8501`
   ทุกครั้งที่เปิด โปรแกรมจะรัน test ก่อน ถ้า test ไม่ผ่านจะไม่ยอมเปิด
4. ถ้าต้องการลองโปรแกรม ให้เปิดไฟล์ `examples/example_voco_bh01.ceda.json` จาก sidebar

## โครงสร้าง
| ไฟล์ | หน้าที่ |
|---|---|
| `ceda_fdn/pile_capacity.py` | Engine ของ Step 01 คัดลอกจาก skill `ceda-pile-capacity` โดย**ไม่แก้ไข** |
| `ceda_fdn/cap_design.py` | Engine ของ Step 02 คัดลอกจาก skill `ceda-pile-cap-design` โดย**ไม่แก้ไข** |
| `ceda_fdn/helpers.py` | ตรวจ input, เลือก option ของ Step 01, วาดรูป cap และตรวจ Excel ด้วย LibreOffice |
| `app.py` | หน้าจอ (Streamlit) ซึ่งไม่มีสูตรคำนวณอยู่ในไฟล์นี้ |
| `tests/test_engines.py` | Regression test: VOCO BH01 Qult = 159.69 t, F4 h135 Mu = 487,125 kg-m, punching 6.65/13.30 ksc และ per-type embed |

## กฎที่ถอดมาจาก skill
- **ไม่มีค่าใดถูกใส่ให้อัตโนมัติ** ช่องว่างหมายถึงยังไม่ได้ยืนยัน ปุ่ม "เติมค่าเสนอ CEDA" จะเติมเฉพาะช่องที่ว่าง และปุ่ม Run จะล็อกไว้จนกว่าจะกรอกครบและติ๊กยืนยันแล้ว
- **Code basis, λs และ pile embedment ไม่มีปุ่มเติมค่า** ผู้ออกแบบต้องเลือกเองทุกครั้ง
- ข้อเสนอเรื่อง D และ tip ใน Step 01 เป็น **[EJ]** ส่วนค่าที่จะส่งไป Step 02 ผู้ออกแบบต้องกรอกเอง

## ข้อจำกัดที่ทราบ
- **Size effect λs ON ในฐาน 2 ต้น:** engine หา h ไม่ได้ เพราะ punching รอบเข็มมี b0 ถูกขอบ cap ตัดจนค่า vu ไม่ลดลงตาม h ขณะที่ λs ทำให้ φvc ลดลง ผลคือโปรแกรมแสดง "NOT CONVERGED" และ Excel ของ type นั้นมี #DIV/0! พฤติกรรมนี้มาจาก engine เดิมและยังไม่ได้แก้ ต้องให้ผู้ออกแบบตัดสินวิธีตรวจก่อน
- ปุ่มตรวจ Excel ต้องติดตั้ง LibreOffice ในเครื่องก่อน
- Driven I-pile (Step 01) ยังไม่รองรับ
- หัวข้อที่ไม่ครอบคลุมใน Step 02 เป็นไปตาม skill ได้แก่ column moment, dowel, tension pile และฐานรวมหลายเสา

## การแก้ไข engine
หากแก้ไฟล์ใน `ceda_fdn/` ต้องรัน `python tests\test_engines.py` ให้ผ่านทุกครั้ง ถ้าการแก้เปลี่ยนผลลัพธ์โดยตั้งใจ ให้ปรับค่าอ้างอิงใน test พร้อมบันทึกเหตุผลไว้ใน change log ด้านล่าง

## Change log
- v0.1.0 (ต.ค. 2026): Step 01–02, engine จาก skill v2.1
