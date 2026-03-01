"""Pipeline configuration using Pydantic Settings.

Loads configuration from:
1. config/default.yaml (default)
2. BIOMECHANICS_CONFIG env var pointing to custom YAML
3. Individual env vars (e.g., BIOMECHANICS_POSE_BACKEND=rtmpose)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal, Optional

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class PipelineConfig(BaseModel):
    """Top-level pipeline settings."""
    target_fps: int = 30
    log_level: str = "INFO"


class CaptureConfig(BaseModel):
    """Camera capture settings."""
    source: Literal["webcam", "video_file", "multi_cam"] = "webcam"
    device_id: int = 0
    resolution: tuple[int, int] = (1280, 720)
    video_path: Optional[str] = None


class PoseConfig(BaseModel):
    """Pose estimation settings."""
    backend: Literal["rtmpose", "mediapipe"] = "mediapipe"
    model_path: str = "biomechanics/pose/models/rtmpose_m.onnx"
    confidence_threshold: float = 0.3


class TriangulationConfig(BaseModel):
    """3D triangulation settings."""
    enabled: bool = False
    camera_config: str = "config/camera_sim.yaml"


class KinematicsConfig(BaseModel):
    """Inverse kinematics settings."""
    backend: Literal["analytical", "opensim"] = "analytical"
    opensim_model_path: str = "config/models/rajagopal_2016/Rajagopal2016.osim"
    scaled_model_path: Optional[str] = None


class DepthFaultConfig(BaseModel):
    """Depth fault thresholds."""
    parallel: float = 90.0
    below_parallel: float = 100.0


class BilateralAsymmetryConfig(BaseModel):
    """Bilateral asymmetry thresholds."""
    mild: float = 5.0
    moderate: float = 10.0
    severe: float = 15.0


class HeelRiseConfig(BaseModel):
    """Heel rise thresholds."""
    threshold_cm: float = 2.0


class ForwardLeanConfig(BaseModel):
    """Forward lean thresholds."""
    mild: float = 35.0
    moderate: float = 45.0
    severe: float = 55.0


class KneeValgusConfig(BaseModel):
    """Knee valgus thresholds."""
    mild: float = 5.0
    moderate: float = 10.0
    severe: float = 15.0


class FaultsConfig(BaseModel):
    """Fault detection thresholds."""
    depth: DepthFaultConfig = Field(default_factory=DepthFaultConfig)
    bilateral_asymmetry: BilateralAsymmetryConfig = Field(
        default_factory=BilateralAsymmetryConfig
    )
    heel_rise: HeelRiseConfig = Field(default_factory=HeelRiseConfig)
    forward_lean: ForwardLeanConfig = Field(default_factory=ForwardLeanConfig)
    knee_valgus: KneeValgusConfig = Field(default_factory=KneeValgusConfig)


class RepDetectionConfig(BaseModel):
    """Rep detection settings."""
    entry_threshold: float = 30.0
    min_rep_duration_frames: int = 20


class CoachingConfig(BaseModel):
    """Coaching output settings."""
    audio_enabled: bool = True
    min_cue_gap_seconds: float = 2.0
    llm_enabled: bool = False
    llm_model: str = "claude-sonnet-4-20250514"


class VizConfig(BaseModel):
    """Visualization settings."""
    show_skeleton: bool = True
    show_angles: bool = True
    show_faults: bool = True
    dashboard: bool = False


class BiomechanicsSettings(BaseSettings):
    """Main settings class that loads from YAML and environment variables.

    Usage:
        settings = BiomechanicsSettings()
        print(settings.pose.backend)

    Environment variable overrides:
        BIOMECHANICS_CONFIG=/path/to/config.yaml  # Override entire config file
        BIOMECHANICS_POSE_BACKEND=rtmpose         # Override individual settings
        BIOMECHANICS_CAPTURE_DEVICE_ID=1
    """

    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    capture: CaptureConfig = Field(default_factory=CaptureConfig)
    pose: PoseConfig = Field(default_factory=PoseConfig)
    triangulation: TriangulationConfig = Field(default_factory=TriangulationConfig)
    kinematics: KinematicsConfig = Field(default_factory=KinematicsConfig)
    faults: FaultsConfig = Field(default_factory=FaultsConfig)
    rep_detection: RepDetectionConfig = Field(default_factory=RepDetectionConfig)
    coaching: CoachingConfig = Field(default_factory=CoachingConfig)
    visualization: VizConfig = Field(default_factory=VizConfig)

    model_config = {
        "env_prefix": "BIOMECHANICS_",
        "env_nested_delimiter": "_",
    }

    def __init__(self, config_path: Optional[Path | str] = None, **kwargs):
        # Determine config file path
        if config_path is None:
            config_path = os.environ.get("BIOMECHANICS_CONFIG")

        if config_path is None:
            # Look for default config relative to this file
            default_paths = [
                Path(__file__).parent.parent / "config" / "default.yaml",
                Path("config/default.yaml"),
                Path("biomechanics/config/default.yaml"),
            ]
            for path in default_paths:
                if path.exists():
                    config_path = path
                    break

        # Load YAML config if available
        yaml_config = {}
        if config_path and Path(config_path).exists():
            with open(config_path) as f:
                yaml_config = yaml.safe_load(f) or {}

        # Merge YAML config with any kwargs
        merged = {**yaml_config, **kwargs}

        # Handle resolution as tuple if it comes as list from YAML
        if "capture" in merged and isinstance(merged["capture"].get("resolution"), list):
            merged["capture"]["resolution"] = tuple(merged["capture"]["resolution"])

        super().__init__(**merged)

    @classmethod
    def from_yaml(cls, path: Path | str) -> "BiomechanicsSettings":
        """Load settings from a specific YAML file."""
        return cls(config_path=path)


# Convenience function to get settings singleton
_settings: Optional[BiomechanicsSettings] = None


def get_settings(config_path: Optional[Path | str] = None) -> BiomechanicsSettings:
    """Get the settings singleton, optionally with a custom config path."""
    global _settings
    if _settings is None or config_path is not None:
        _settings = BiomechanicsSettings(config_path=config_path)
    return _settings
