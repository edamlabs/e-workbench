"""infra/config/services: which arm of the A/B the process runs — `full` unless told otherwise."""

from infra.config.base import BaseSettings
from models.arm import Arm


##### SETTINGS #####
class ServiceSettings(BaseSettings):
    """The arm the server and the CLI run; the bench builds every arm itself."""

    ### ARMS
    DEEPTRACK_LAB_ARM: Arm = Arm.FULL
