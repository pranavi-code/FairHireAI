# Deployment boundary

`backend.Dockerfile` packages the public FastAPI request service. Configure all
`ROLEREADY_*` values through the hosting platform's secret/environment manager.
Never bake `.env` into the image.

The selected checkpoint is external to Git. Only the trusted worker must mount
or download the verified checkpoint and set:

```text
ROLEREADY_MODEL_CHECKPOINT_PATH
ROLEREADY_MODEL_RUN_NAME
ROLEREADY_MODEL_CHECKPOINT_SHA256
```

The GPU worker is intentionally not hidden inside this API image. It needs
CUDA, the Windows OpenFace 2.2.0 runtime presently installed at
`D:\FairHireAI-tools`, Whisper model files, FFmpeg, and the selected checkpoint.
Run `scripts/run_fairhire_worker.py` on that trusted host with the Supabase
server secret. The browser and public API use only the publishable key/user JWT.

Production completion requires:

1. an HTTPS backend hostname;
2. its hostname in `ROLEREADY_CORS_ALLOWED_ORIGINS`;
3. the frontend's `VITE_API_BASE_URL` set to `<https-backend>/api/v1`;
4. the final frontend URL in Supabase Auth redirect URLs;
5. a running GPU worker and queue/deletion monitoring.
