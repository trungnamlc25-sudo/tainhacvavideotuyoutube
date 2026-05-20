"""EZVIZ LAN Camera Viewer - Main Application."""

import json
import os
import platform
import signal
import subprocess
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

IS_WINDOWS = platform.system() == "Windows"

app = FastAPI(title="EZVIZ LAN Camera Viewer", version="1.0.0")

BASE_DIR = Path(__file__).parent
STREAMS_DIR = BASE_DIR / "streams"
CONFIG_FILE = BASE_DIR / "cameras.json"

STREAMS_DIR.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.mount("/streams", StaticFiles(directory=str(STREAMS_DIR)), name="streams")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Store active FFmpeg processes
ffmpeg_processes: dict[str, subprocess.Popen] = {}
process_lock = threading.Lock()


class CameraConfig(BaseModel):
    """Camera configuration model."""

    name: str
    ip: str
    port: int = 554
    username: str = "admin"
    password: str = ""
    channel: int = 1
    stream_type: int = 1  # 1 = main stream, 2 = sub stream


class CameraUpdate(BaseModel):
    """Camera update model."""

    name: str | None = None
    ip: str | None = None
    port: int | None = None
    username: str | None = None
    password: str | None = None
    channel: int | None = None
    stream_type: int | None = None


def load_cameras() -> list[dict]:
    """Load camera configurations from JSON file."""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return []


def save_cameras(cameras: list[dict]) -> None:
    """Save camera configurations to JSON file."""
    with open(CONFIG_FILE, "w") as f:
        json.dump(cameras, f, indent=2, ensure_ascii=False)


def get_rtsp_url(camera: dict) -> str:
    """Build RTSP URL for EZVIZ camera.

    EZVIZ cameras typically use this RTSP format:
    rtsp://username:password@ip:port/h264/chN/stream_type/av_stream
    """
    username = camera.get("username", "admin")
    password = camera.get("password", "")
    ip = camera["ip"]
    port = camera.get("port", 554)
    channel = camera.get("channel", 1)
    stream_type = camera.get("stream_type", 1)

    if password:
        auth = f"{username}:{password}@"
    else:
        auth = ""

    return f"rtsp://{auth}{ip}:{port}/h264/ch{channel}/{stream_type}/av_stream"


def start_ffmpeg_stream(camera_id: str, rtsp_url: str) -> bool:
    """Start FFmpeg process to convert RTSP to HLS."""
    output_dir = STREAMS_DIR / camera_id
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "stream.m3u8"

    # Kill existing process if any
    stop_ffmpeg_stream(camera_id)

    cmd = [
        "ffmpeg",
        "-y",
        "-fflags",
        "nobuffer",
        "-flags",
        "low_delay",
        "-rtsp_transport",
        "tcp",
        "-i",
        rtsp_url,
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-tune",
        "zerolatency",
        "-g",
        "30",
        "-vf",
        "scale=1280:720",
        "-c:a",
        "aac",
        "-ar",
        "44100",
        "-f",
        "hls",
        "-hls_time",
        "1",
        "-hls_list_size",
        "5",
        "-hls_flags",
        "delete_segments",
        "-hls_allow_cache",
        "0",
        str(output_path),
    ]

    try:
        kwargs: dict = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
        }
        if IS_WINDOWS:
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["preexec_fn"] = os.setsid

        process = subprocess.Popen(cmd, **kwargs)
        with process_lock:
            ffmpeg_processes[camera_id] = process
        return True
    except FileNotFoundError:
        return False


def stop_ffmpeg_stream(camera_id: str) -> None:
    """Stop FFmpeg process for a camera."""
    with process_lock:
        process = ffmpeg_processes.pop(camera_id, None)
    if process:
        try:
            if IS_WINDOWS:
                process.terminate()
            else:
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            process.wait(timeout=5)
        except (ProcessLookupError, subprocess.TimeoutExpired, OSError):
            try:
                if IS_WINDOWS:
                    process.kill()
                else:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except (ProcessLookupError, OSError):
                pass


def is_stream_active(camera_id: str) -> bool:
    """Check if a camera stream is currently active."""
    with process_lock:
        process = ffmpeg_processes.get(camera_id)
    if process is None:
        return False
    return process.poll() is None


# --- API Routes ---


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Render main page."""
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/api/cameras")
async def list_cameras():
    """List all configured cameras."""
    cameras = load_cameras()
    result = []
    for i, cam in enumerate(cameras):
        cam_id = f"cam_{i}"
        result.append(
            {
                "id": cam_id,
                "name": cam.get("name", f"Camera {i + 1}"),
                "ip": cam["ip"],
                "port": cam.get("port", 554),
                "username": cam.get("username", "admin"),
                "channel": cam.get("channel", 1),
                "stream_type": cam.get("stream_type", 1),
                "active": is_stream_active(cam_id),
                "stream_url": f"/streams/{cam_id}/stream.m3u8"
                if is_stream_active(cam_id)
                else None,
            }
        )
    return result


@app.post("/api/cameras")
async def add_camera(camera: CameraConfig):
    """Add a new camera."""
    cameras = load_cameras()
    cameras.append(camera.model_dump())
    save_cameras(cameras)
    return {"message": "Camera added", "id": f"cam_{len(cameras) - 1}"}


@app.put("/api/cameras/{camera_id}")
async def update_camera(camera_id: str, camera: CameraUpdate):
    """Update camera configuration."""
    cameras = load_cameras()
    idx = int(camera_id.replace("cam_", ""))
    if idx < 0 or idx >= len(cameras):
        raise HTTPException(status_code=404, detail="Camera not found")

    update_data = camera.model_dump(exclude_none=True)
    cameras[idx].update(update_data)
    save_cameras(cameras)

    # Restart stream if active
    if is_stream_active(camera_id):
        rtsp_url = get_rtsp_url(cameras[idx])
        start_ffmpeg_stream(camera_id, rtsp_url)

    return {"message": "Camera updated"}


@app.delete("/api/cameras/{camera_id}")
async def delete_camera(camera_id: str):
    """Delete a camera."""
    cameras = load_cameras()
    idx = int(camera_id.replace("cam_", ""))
    if idx < 0 or idx >= len(cameras):
        raise HTTPException(status_code=404, detail="Camera not found")

    stop_ffmpeg_stream(camera_id)
    cameras.pop(idx)
    save_cameras(cameras)
    return {"message": "Camera deleted"}


@app.post("/api/cameras/{camera_id}/start")
async def start_stream(camera_id: str):
    """Start streaming from a camera."""
    cameras = load_cameras()
    idx = int(camera_id.replace("cam_", ""))
    if idx < 0 or idx >= len(cameras):
        raise HTTPException(status_code=404, detail="Camera not found")

    camera = cameras[idx]
    rtsp_url = get_rtsp_url(camera)
    success = start_ffmpeg_stream(camera_id, rtsp_url)

    if not success:
        raise HTTPException(
            status_code=500,
            detail="Failed to start stream. Make sure FFmpeg is installed.",
        )

    # Wait until HLS playlist file is created (max 15 seconds)
    output_dir = STREAMS_DIR / camera_id
    m3u8_path = output_dir / "stream.m3u8"
    for _ in range(30):
        time.sleep(0.5)
        if m3u8_path.exists() and m3u8_path.stat().st_size > 0:
            # Wait a bit more for first segment
            time.sleep(1)
            break
        # Check if FFmpeg crashed
        if not is_stream_active(camera_id):
            raise HTTPException(
                status_code=500,
                detail="FFmpeg process died. Check camera IP/password and FFmpeg installation.",
            )
    else:
        raise HTTPException(
            status_code=500,
            detail="Timeout waiting for stream. FFmpeg may not be generating output.",
        )

    return {
        "message": "Stream started",
        "stream_url": f"/streams/{camera_id}/stream.m3u8",
    }


@app.post("/api/cameras/{camera_id}/stop")
async def stop_stream(camera_id: str):
    """Stop streaming from a camera."""
    stop_ffmpeg_stream(camera_id)
    return {"message": "Stream stopped"}


@app.get("/api/cameras/{camera_id}/status")
async def stream_status(camera_id: str):
    """Check stream status."""
    active = is_stream_active(camera_id)
    # Check if HLS files exist
    output_dir = STREAMS_DIR / camera_id
    m3u8_exists = (output_dir / "stream.m3u8").exists()
    ts_files = list(output_dir.glob("*.ts")) if output_dir.exists() else []
    return {
        "active": active,
        "stream_url": f"/streams/{camera_id}/stream.m3u8" if active else None,
        "m3u8_exists": m3u8_exists,
        "ts_segments": len(ts_files),
    }


@app.on_event("shutdown")
async def shutdown_event():
    """Stop all FFmpeg processes on shutdown."""
    with process_lock:
        camera_ids = list(ffmpeg_processes.keys())
    for cam_id in camera_ids:
        stop_ffmpeg_stream(cam_id)
