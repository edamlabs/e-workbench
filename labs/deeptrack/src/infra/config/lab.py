"""infra/config/lab: which arm of the A/B the process runs — `full` unless told otherwise."""

from pydantic_settings import SettingsConfigDict

from deeptrack.models.arm import Arm
from infra.config.base import BaseSettings


class LabSettings(BaseSettings):
    """`DEEPTRACK_LAB_ARM` picks the arm the server and the CLI run; the bench builds every arm itself."""

    model_config = SettingsConfigDict(env_prefix="DEEPTRACK_LAB_")

    arm: Arm = Arm.FULL
