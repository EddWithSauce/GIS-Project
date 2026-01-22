# URSM Flood GIS (Prototype)

## Run
1) Create venv (optional)
- python -m venv .venv
- Windows: .venv\Scripts\activate
- macOS/Linux: source .venv/bin/activate

2) Install
- pip install -r requirements.txt

3) Start
- python app.py

Open: http://127.0.0.1:5000

## Notes
- Data is MOCK right now.
- ML is STANDBY:
  - /api/ml/status
  - /api/ml/predict (POST JSON)
Later you can replace these with your trained model inference.
