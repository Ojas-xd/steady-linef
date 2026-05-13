"""
Replicate-hosted YOLOv8 — runs on Replicate's GPUs/servers, not on Render RAM.
Free tier: https://replicate.com account → API token (starter credits).
"""
from __future__ import annotations

import base64
import json
import logging
import time
from typing import Any

import cv2
import httpx
import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)

_version_id_cache: str | None = None


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Token {token.strip()}"}


def _bgr_to_data_uri_jpeg(img: np.ndarray, quality: int = 85) -> str:
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        raise ValueError("jpeg encode failed")
    b64 = base64.b64encode(buf.tobytes()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def get_replicate_model_version_id(token: str) -> str:
    global _version_id_cache
    if _version_id_cache:
        return _version_id_cache
    owner = settings.REPLICATE_MODEL_OWNER
    name = settings.REPLICATE_MODEL_NAME
    with httpx.Client(timeout=60.0) as client:
        r = client.get(
            f"https://api.replicate.com/v1/models/{owner}/{name}",
            headers=_auth_headers(token),
        )
        r.raise_for_status()
        data = r.json()
        vid = data["latest_version"]["id"]
        _version_id_cache = vid
        logger.info("[Replicate] Using model version %s", vid[:20])
        return vid


def _poll_until_done(client: httpx.Client, token: str, get_url: str, deadline: float) -> dict[str, Any]:
    while time.time() < deadline:
        r = client.get(get_url, headers=_auth_headers(token))
        r.raise_for_status()
        body = r.json()
        st = body.get("status")
        if st in ("succeeded", "failed", "canceled"):
            return body
        time.sleep(0.75)
    raise TimeoutError("Replicate prediction timed out")


def _parse_json_detections(raw: Any) -> list[tuple[int, int, int, int, float]]:
    """Extract (x1,y1,x2,y2,conf) for person class from assorted JSON shapes."""
    out: list[tuple[int, int, int, int, float]] = []

    if raw is None:
        return out
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return out
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("[Replicate] json_str is not valid JSON")
            return out

    def is_person(obj: dict) -> bool:
        name = str(obj.get("name") or obj.get("class_name") or obj.get("label") or "").lower()
        cid = obj.get("class_id", obj.get("cls", obj.get("category_id", obj.get("class"))))
        try:
            cid_int = int(cid) if cid is not None and str(cid).strip() != "" else None
        except (TypeError, ValueError):
            cid_int = None
        if cid_int == 0:
            return True
        if "person" in name:
            return True
        return False

    def add_row(obj: dict) -> None:
        if not is_person(obj):
            return
        conf = float(obj.get("confidence") or obj.get("score") or obj.get("conf") or 0.5)
        box = obj.get("bbox") or obj.get("box") or obj.get("xyxy")
        if not (isinstance(box, (list, tuple)) and len(box) >= 4):
            return
        x1, y1, x2, y2 = (int(float(box[0])), int(float(box[1])), int(float(box[2])), int(float(box[3])))
        out.append((x1, y1, x2, y2, min(0.99, max(0.05, conf))))

    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                add_row(item)
    elif isinstance(raw, dict):
        nested = False
        for key in ("detections", "predictions", "results", "objects", "data"):
            v = raw.get(key)
            if isinstance(v, list):
                nested = True
                for item in v:
                    if isinstance(item, dict):
                        add_row(item)
        if not nested:
            add_row(raw)
    return out


def _download_bgr(url: str, token: str) -> np.ndarray | None:
    try:
        with httpx.Client(timeout=90.0, follow_redirects=True) as client:
            r = client.get(url, headers=_auth_headers(token))
            r.raise_for_status()
            arr = np.frombuffer(r.content, dtype=np.uint8)
            return cv2.imdecode(arr, cv2.IMREAD_COLOR)
    except Exception as e:
        logger.warning("[Replicate] output image download failed: %s", e)
        return None


def run_replicate_yolov8(frame_bgr: np.ndarray, token: str) -> tuple[int, list[dict[str, object]], np.ndarray]:
    """
    Run remote YOLOv8 via Replicate; return (count, detections, annotated_bgr).
    """
    work = frame_bgr.copy()
    data_uri = _bgr_to_data_uri_jpeg(work)
    version_id = get_replicate_model_version_id(token)

    with httpx.Client(timeout=120.0) as client:
        r = client.post(
            "https://api.replicate.com/v1/predictions",
            headers={**_auth_headers(token), "Content-Type": "application/json"},
            json={
                "version": version_id,
                "input": {
                    "input_image": data_uri,
                    "model_name": settings.REPLICATE_YOLO_VARIANT,
                    "return_json": True,
                },
            },
        )
        r.raise_for_status()
        pred = r.json()
        get_url = pred.get("urls", {}).get("get")
        if not get_url:
            raise RuntimeError("Replicate response missing urls.get")

        body = _poll_until_done(client, token, get_url, time.time() + 120.0)
        if body.get("status") != "succeeded":
            raise RuntimeError(f"Replicate status={body.get('status')!r} error={body.get('error')!r}")

        output = body.get("output") or {}
        json_str = output.get("json_str")
        dets = _parse_json_detections(json_str)

        img_url = output.get("img")
        annotated_remote: np.ndarray | None = None
        if isinstance(img_url, str) and img_url.startswith("http"):
            annotated_remote = _download_bgr(img_url, token)

        if annotated_remote is not None and annotated_remote.size > 0:
            drawn = annotated_remote
        else:
            drawn = work
            for x1, y1, x2, y2, conf in dets:
                cv2.rectangle(drawn, (x1, y1), (x2, y2), (0, 255, 0), 2)
                label = f"Person {conf:.2f}"
                ls = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)[0]
                cv2.rectangle(drawn, (x1, y1 - ls[1] - 10), (x1 + ls[0], y1), (0, 255, 0), -1)
                cv2.putText(drawn, label, (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)

        detection_dicts: list[dict[str, object]] = [
            {"box": [x1, y1, x2, y2], "confidence": round(conf, 2)} for x1, y1, x2, y2, conf in dets
        ]
        return len(detection_dicts), detection_dicts, drawn
