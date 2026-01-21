# GIS-Project
Repository for this particular project

Changes (01/21/2026):
  - iso25010.html is removed

 app.py:
  - its app also in app.py also remove (@app.get("/admin/iso25010))

 base_admin.html:
  - its nav bar also remobe in base_admin.html (href="/admin/iso25010")

(New Added/Changes for today)
app.py: (Added)
 - import csv
 - from flask import Response
 - from io import StringIO
 - def csv_response
 - def demo_raw_logs
 - def demo_validation
 - Added app routes (Raw Logs + Validation)
 - Added app routes (Actual vs Predicted)

Changes:
 - admin/logs.html
 - admin/validation.html
 - js/history.js
	- just add .reverse in the function renderTable(series)
            - const rows = series.slice(-24).reverse().map(s => { ..... etc
