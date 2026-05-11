#### Local API Server Setup
Follow these steps to host the API server on your local machine:
1. Install emmet-api in editable mode to ensure any local changes are reflected immediately:
```
pip install -e .
```
2. Configure Environment Variables
```
export MP_API_KEY=
export MPMATERIALS_MONGO_HOST=
export MPTASKS_MONGO_HOST=
export MPMOLECULES_MONGO_HOST=
export MPCONTRIBS_MONGO_HOST=
```
3. Launch the Server
You can start the application using either method:
```
python app.py
```
```
uvicorn app:app --host 0.0.0.0 --port 8000
```
