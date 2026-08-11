"""Durable answer and deletion workers for the complete student journey."""

from __future__ import annotations

import hashlib
import shutil
import socket
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch
import whisper_timestamped as whisper

from backend.app.config import Settings
from backend.app.domain.answer_evaluation import calculate_delivery_metrics
from backend.app.providers.gemini import GeminiClient
from backend.app.repositories.worker import SupabaseWorkerRepository
from backend.app.services.answer_evaluation import (
    EVALUATOR_PROMPT_VERSION,
    AnswerEvaluationService,
)
from backend.app.services.attempt_reporting import (
    build_attempt_output,
    interview_ready_for_report,
)
from ml_service.inference.runtime import CheckpointInferenceRuntime
from ml_service.preprocessing.alignment import align_sample
from ml_service.preprocessing.pipeline import (
    extract_openface,
    normalize_media,
    transcribe_audio,
)

VIDEO_BUCKET = "roleready-interview-video"
ARTIFACT_BUCKET = "roleready-processing-artifacts"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class FairHireWorker:
    def __init__(
        self,
        settings: Settings,
        *,
        repository: SupabaseWorkerRepository | None = None,
        worker_id: str | None = None,
    ) -> None:
        if not settings.worker_configured or settings.supabase_secret_key is None:
            raise RuntimeError(
                "ROLEREADY_SUPABASE_SECRET_KEY is required by the trusted worker."
            )
        checkpoint, run_name, checkpoint_sha = settings.selected_model
        if not checkpoint or not run_name or not checkpoint_sha or not settings.model_ready:
            raise RuntimeError("The selected-model manifest is missing or invalid.")
        if not settings.gemini_configured or settings.gemini_api_key is None:
            raise RuntimeError("Gemini is required for transcript-grounded rubric evaluation.")
        self.settings = settings
        self.worker_id = worker_id or f"{socket.gethostname()}:{id(self):x}"
        self.repository = repository or SupabaseWorkerRepository(
            base_url=settings.supabase_url or "",
            secret_key=settings.supabase_secret_key.get_secret_value(),
            timeout_seconds=max(30.0, settings.supabase_timeout_seconds),
        )
        self._owns_repository = repository is None
        self._checkpoint = checkpoint
        self._run_name = run_name
        self._checkpoint_sha = checkpoint_sha
        self._whisper_model: Any | None = None
        self._inference: CheckpointInferenceRuntime | None = None

    def close(self) -> None:
        if self._owns_repository:
            self.repository.close()

    def _models(self) -> tuple[Any, CheckpointInferenceRuntime]:
        if self._whisper_model is None:
            if not torch.cuda.is_available():
                raise RuntimeError("CUDA is required for the configured answer worker.")
            Path(self.settings.whisper_model_root).mkdir(parents=True, exist_ok=True)
            self._whisper_model = whisper.load_model(
                self.settings.whisper_model,
                device="cuda",
                download_root=self.settings.whisper_model_root,
            )
        if self._inference is None:
            self._inference = CheckpointInferenceRuntime(
                self._checkpoint,
                expected_sha256=self._checkpoint_sha,
                model_name_or_path=self.settings.bert_model_root,
                scaler_path=self.settings.scaler_path,
            )
        return self._whisper_model, self._inference

    def run_once(self) -> bool:
        job = self.repository.claim_processing_job(self.worker_id)
        if job is not None:
            self._process_job(job)
            return True
        deletion = self.repository.claim_deletion_request(self.worker_id)
        if deletion is not None:
            self._process_deletion(deletion)
            return True
        return False

    def _stage(self, job_id: str, stage: str) -> None:
        self.repository.update_job(job_id, stage=stage)

    def _process_job(self, job: dict[str, Any]) -> None:
        job_id = str(job["id"])
        answer_id = str(job["answer_id"])
        attempt_id = str(job["attempt_id"])
        work = Path(self.settings.worker_artifact_root) / "jobs" / job_id
        if work.is_dir():
            shutil.rmtree(work)
        work.mkdir(parents=True)
        try:
            context = self.repository.answer_context(answer_id)
            answer = context["answer"]
            question = context["question"]
            attempt = context["attempt"]
            if not self.repository.external_ai_consent(
                str(attempt["user_id"]),
                attempt_id,
            ):
                raise RuntimeError(
                    "Explicit external_ai_processing consent is required for Gemini evaluation."
                )

            source_video = work / "source.mp4"
            self._stage(job_id, "download_private_video")
            self.repository.download_object(
                VIDEO_BUCKET,
                str(answer["private_video_storage_key"]),
                source_video,
            )
            if _sha256(source_video) != str(answer["video_sha256"]):
                raise RuntimeError("Downloaded answer video checksum does not match.")

            whisper_model, inference = self._models()
            normalized_video = work / "normalized.mp4"
            normalized_audio = work / "normalized.wav"
            self._stage(job_id, "normalize_media")
            media = normalize_media(source_video, normalized_video, normalized_audio)

            self._stage(job_id, "transcribe_whisper")
            transcript = transcribe_audio(
                whisper_model,
                normalized_audio,
                video_id=str(answer["id"]),
                label=0.0,
                model_name=self.settings.whisper_model,
            )
            transcript_path = work / "transcript.json"
            from ml_service.preprocessing.pipeline import atomic_json

            atomic_json(transcript_path, transcript)

            self._stage(job_id, "extract_openface")
            openface_path, _visual_summary = extract_openface(
                normalized_video,
                work / "openface",
                openface_root=Path(self.settings.openface_root),
                expected_duration=media["video_duration_seconds"],
            )

            self._stage(job_id, "word_align_egemaps_openface")
            aligned_path = work / "aligned.npz"
            align_sample(
                transcript_path=transcript_path,
                audio_path=normalized_audio,
                visual_path=openface_path,
                output_path=aligned_path,
                label=0.0,
                video_id=str(answer["id"]),
            )

            self._stage(job_id, "selected_mag_bert_inference")
            prediction = inference.predict_aligned(aligned_path)
            delivery = calculate_delivery_metrics(
                transcript=transcript,
                audio_path=normalized_audio,
                openface_path=openface_path,
                duration_seconds=float(answer["duration_seconds"]),
            )

            self._stage(job_id, "gemini_rubric_evaluation")
            resume_claims = self.repository.resume_claims(attempt_id)
            with GeminiClient(
                api_key=self.settings.gemini_api_key.get_secret_value(),
                generation_model=self.settings.gemini_generation_model,
                embedding_model=self.settings.gemini_embedding_model,
                embedding_dimensions=self.settings.gemini_embedding_dimensions,
                timeout_seconds=self.settings.gemini_timeout_seconds,
                max_retries=self.settings.gemini_max_retries,
            ) as client:
                evaluation = AnswerEvaluationService(client).evaluate(
                    competency_id=str(question["competency_id"]),
                    prompt_snapshot=str(question["prompt_snapshot"]),
                    expected_concepts=[
                        str(item)
                        for item in question.get("expected_concepts_snapshot") or []
                    ],
                    rubric={
                        str(key): str(value)
                        for key, value in (
                            question.get("rubric_snapshot") or {}
                        ).items()
                    },
                    source_mapping={
                        str(key): [str(item) for item in values]
                        for key, values in (
                            question.get("source_mapping_snapshot") or {}
                        ).items()
                    },
                    transcript=transcript,
                    resume_claims=resume_claims,
                    is_follow_up=bool(question["is_follow_up"]),
                )

            artifact_key = (
                f"{attempt['user_id']}/attempts/{attempt_id}/answers/"
                f"{answer_id}/aligned.npz"
            )
            self._stage(job_id, "persist_private_artifact")
            self.repository.upload_object(
                ARTIFACT_BUCKET,
                artifact_key,
                aligned_path,
                content_type="application/octet-stream",
            )
            self.repository.upsert_answer_analysis(
                {
                    "answer_id": answer_id,
                    "attempt_id": attempt_id,
                    "transcript": transcript,
                    "transcript_text": transcript["text"],
                    "transcript_confidence": transcript["average_word_confidence"],
                    "delivery_metrics": delivery.model_dump(mode="json"),
                    "technical_evaluation": evaluation.model_dump(mode="json"),
                    "base_multimodal_interview_signal": (
                        prediction.base_multimodal_interview_signal
                    ),
                    "signal_quality": min(
                        prediction.signal_quality,
                        delivery.signal_quality,
                    ),
                    "model_run_name": prediction.model_run_name,
                    "model_checkpoint_sha256": prediction.checkpoint_sha256,
                    "aligned_artifact_storage_key": artifact_key,
                    "aligned_artifact_sha256": prediction.input_artifact_sha256,
                    "evaluator_model_id": self.settings.gemini_generation_model,
                    "evaluator_prompt_version": EVALUATOR_PROMPT_VERSION,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            self.repository.update_answer(
                answer_id,
                processing_status="complete",
                processed_at=datetime.now(timezone.utc).isoformat(),
            )
            self._finalize_or_continue(attempt)
            self.repository.update_job(
                job_id,
                status="succeeded",
                stage="complete",
                finished_at=datetime.now(timezone.utc).isoformat(),
                error_code=None,
                error_detail=None,
            )
        except Exception as exc:
            self.repository.update_answer(answer_id, processing_status="failed")
            self.repository.update_attempt(attempt_id, status="failed")
            self.repository.update_job(
                job_id,
                status="failed",
                stage="failed",
                finished_at=datetime.now(timezone.utc).isoformat(),
                error_code=type(exc).__name__[:100],
                error_detail=str(exc)[:4_000],
            )
            raise
        finally:
            if work.is_dir():
                shutil.rmtree(work)

    def _finalize_or_continue(self, attempt: dict[str, Any]) -> None:
        attempt_id = str(attempt["id"])
        material = self.repository.attempt_material(attempt_id)
        ready, _reason = interview_ready_for_report(
            role_id=str(attempt["role_id"]),
            questions=material["questions"],
            answers=material["answers"],
            analyses=material["analyses"],
        )
        if not ready:
            self.repository.update_attempt(attempt_id, status="interviewing")
            return
        parent_scorecard = (
            self.repository.scorecard(str(attempt["parent_attempt_id"]))
            if attempt.get("parent_attempt_id")
            else None
        )
        output = build_attempt_output(
            attempt=attempt,
            questions=material["questions"],
            answers=material["answers"],
            analyses=material["analyses"],
            resume_claims=material["resume_claims"],
            resources=self.repository.approved_resources(),
            parent_scorecard=parent_scorecard,
        )
        self.repository.replace_attempt_outputs(
            attempt_id=attempt_id,
            nodes=output.nodes,
            edges=output.edges,
            scorecard=output.scorecard,
            roadmap_items=output.roadmap_items,
            progress_metric=output.progress_metric,
        )
        self.repository.update_attempt(
            attempt_id,
            status="completed",
            completed_at=datetime.now(timezone.utc).isoformat(),
        )

    def _process_deletion(self, request: dict[str, Any]) -> None:
        try:
            for bucket, storage_key in self.repository.deletion_storage_keys(request):
                self.repository.delete_object(bucket, storage_key)
            self.repository.complete_deletion(request)
        except Exception as exc:
            self.repository.fail_deletion(str(request["id"]), type(exc).__name__)
            raise


def run_worker(settings: Settings, *, once: bool, poll_seconds: float) -> None:
    worker = FairHireWorker(settings)
    try:
        while True:
            try:
                handled = worker.run_once()
            except Exception:
                if once:
                    raise
                # The repository has already persisted a failed job/deletion
                # state. Keep the durable daemon alive so one malformed media
                # file cannot block every later job or privacy request.
                traceback.print_exc()
                time.sleep(poll_seconds)
                continue
            if once:
                return
            if not handled:
                time.sleep(poll_seconds)
    finally:
        worker.close()
