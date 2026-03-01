"""
Pipeline Configuration for Biomechanics System

Loads configuration from YAML files and provides typed access to settings.
"""

import os
from typing import Optional, Tuple, List
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


# =============================================================================
# SUB-CONFIGURATIONS
# =============================================================================

class PipelineConfig(BaseModel):
    """Top-level pipeline configuration."""
    target_fps: int = 30
    log_level: str = "INFO"
    single_camera_mode: bool = True


class CaptureConfig(BaseModel):
    """Camera capture configuration."""
    source: str = "webcam"
    device_id: int = 0
    resolution: Tuple[int, int] = (1280, 720)


class PoseConfig(BaseModel):
    """Pose estimation configuration."""
    backend: str = "mediapipe"  # mediapipe | rtmpose
    confidence_threshold: float = 0.3


class TriangulationConfig(BaseModel):
    """Stereo triangulation configuration."""
    enabled: bool = False


class KinematicsConfig(BaseModel):
    """Inverse kinematics configuration."""
    backend: str = "analytical"  # analytical | opensim


class DepthFaultConfig(BaseModel):
    """Squat depth fault thresholds."""
    parallel: float = 90.0
    below_parallel: float = 100.0


class BilateralAsymmetryConfig(BaseModel):
    """Bilateral asymmetry fault thresholds."""
    mild: float = 5.0
    moderate: float = 10.0
    severe: float = 15.0


class HeelRiseConfig(BaseModel):
    """Heel rise fault thresholds."""
    threshold_cm: float = 2.0


class ForwardLeanConfig(BaseModel):
    """Forward lean fault thresholds."""
    mild: float = 35.0
    moderate: float = 45.0
    severe: float = 55.0


class KneeValgusConfig(BaseModel):
    """Knee valgus fault thresholds."""
    mild: float = 5.0
    moderate: float = 10.0
    severe: float = 15.0


class FaultsConfig(BaseModel):
    """Fault detection configuration."""
    depth: DepthFaultConfig = Field(default_factory=DepthFaultConfig)
    bilateral_asymmetry: BilateralAsymmetryConfig = Field(default_factory=BilateralAsymmetryConfig)
    heel_rise: HeelRiseConfig = Field(default_factory=HeelRiseConfig)
    forward_lean: ForwardLeanConfig = Field(default_factory=ForwardLeanConfig)
    knee_valgus: KneeValgusConfig = Field(default_factory=KneeValgusConfig)


class RepDetectionConfig(BaseModel):
    """Rep detection configuration."""
    entry_threshold: float = 30.0
    min_rep_duration_frames: int = 20


class CoachingConfig(BaseModel):
    """Coaching integration configuration."""
    min_cue_gap_seconds: float = 2.0
    set_timeout_seconds: float = 30.0
    cache_cues_before_set: bool = True


class IPCConfig(BaseModel):
    """IPC communication configuration."""
    frame_send_interval: int = 10
    fault_cooldown_seconds: float = 3.0


# =============================================================================
# FULL CONFIGURATION
# =============================================================================

class BiomechanicsConfig(BaseModel):
    """Complete biomechanics pipeline configuration."""
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    capture: CaptureConfig = Field(default_factory=CaptureConfig)
    pose: PoseConfig = Field(default_factory=PoseConfig)
    triangulation: TriangulationConfig = Field(default_factory=TriangulationConfig)
    kinematics: KinematicsConfig = Field(default_factory=KinematicsConfig)
    faults: FaultsConfig = Field(default_factory=FaultsConfig)
    rep_detection: RepDetectionConfig = Field(default_factory=RepDetectionConfig)
    coaching: CoachingConfig = Field(default_factory=CoachingConfig)
    ipc: IPCConfig = Field(default_factory=IPCConfig)

    # Convenience properties
    @property
    def target_fps(self) -> int:
        return self.pipeline.target_fps

    @property
    def frame_time_ms(self) -> float:
        return 1000.0 / self.pipeline.target_fps


# =============================================================================
# LOADING FUNCTIONS
# =============================================================================

def _get_default_config_path() -> Path:
    """Get the default configuration file path."""
    # Try relative to this file first
    module_dir = Path(__file__).parent
    config_path = module_dir.parent.parent / "config" / "biomechanics.yaml"

    if config_path.exists():
        return config_path

    # Try relative to current working directory
    cwd_config = Path.cwd() / "config" / "biomechanics.yaml"
    if cwd_config.exists():
        return cwd_config

    return config_path


def load_pipeline_config(path: Optional[str] = None) -> BiomechanicsConfig:
    """
    Load pipeline configuration from a YAML file.

    Args:
        path: Path to config file. If None, uses default location.

    Returns:
        BiomechanicsConfig instance

    Raises:
        FileNotFoundError: If config file doesn't exist
        yaml.YAMLError: If YAML parsing fails
    """
    if path is None:
        config_path = _get_default_config_path()
    else:
        config_path = Path(path)

    if not config_path.exists():
        print(f"Warning: Config file not found at {config_path}, using defaults")
        return BiomechanicsConfig()

    with open(config_path, "r") as f:
        raw_config = yaml.safe_load(f)

    if raw_config is None:
        return BiomechanicsConfig()

    # Parse nested configs
    config_dict = {}

    if "pipeline" in raw_config:
        config_dict["pipeline"] = PipelineConfig(**raw_config["pipeline"])

    if "capture" in raw_config:
        capture_data = raw_config["capture"]
        # Handle resolution as list -> tuple
        if "resolution" in capture_data and isinstance(capture_data["resolution"], list):
            capture_data["resolution"] = tuple(capture_data["resolution"])
        config_dict["capture"] = CaptureConfig(**capture_data)

    if "pose" in raw_config:
        config_dict["pose"] = PoseConfig(**raw_config["pose"])

    if "triangulation" in raw_config:
        config_dict["triangulation"] = TriangulationConfig(**raw_config["triangulation"])

    if "kinematics" in raw_config:
        config_dict["kinematics"] = KinematicsConfig(**raw_config["kinematics"])

    if "faults" in raw_config:
        faults_data = raw_config["faults"]
        faults_config = FaultsConfig(
            depth=DepthFaultConfig(**faults_data.get("depth", {})),
            bilateral_asymmetry=BilateralAsymmetryConfig(**faults_data.get("bilateral_asymmetry", {})),
            heel_rise=HeelRiseConfig(**faults_data.get("heel_rise", {})),
            forward_lean=ForwardLeanConfig(**faults_data.get("forward_lean", {})),
            knee_valgus=KneeValgusConfig(**faults_data.get("knee_valgus", {})),
        )
        config_dict["faults"] = faults_config

    if "rep_detection" in raw_config:
        config_dict["rep_detection"] = RepDetectionConfig(**raw_config["rep_detection"])

    if "coaching" in raw_config:
        config_dict["coaching"] = CoachingConfig(**raw_config["coaching"])

    if "ipc" in raw_config:
        config_dict["ipc"] = IPCConfig(**raw_config["ipc"])

    return BiomechanicsConfig(**config_dict)


# Global config instance (lazy loaded)
_global_config: Optional[BiomechanicsConfig] = None


def get_config() -> BiomechanicsConfig:
    """Get the global configuration instance (loads on first call)."""
    global _global_config
    if _global_config is None:
        _global_config = load_pipeline_config()
    return _global_config


def reload_config(path: Optional[str] = None) -> BiomechanicsConfig:
    """Reload the global configuration from disk."""
    global _global_config
    _global_config = load_pipeline_config(path)
    return _global_config
