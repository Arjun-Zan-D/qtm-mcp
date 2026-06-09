# Copyright (c) 2026 Xavier Gait Lab Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration settings for the QTM MCP server, loaded dynamically from environment variables."""

    # QTM REST API configuration
    qtm_rest_port: int = 7979
    qtm_rest_host: str = "localhost"

    # QTM RT (Real-Time) protocol configuration
    qtm_rt_port: int = 22223
    qtm_rt_host: str = "127.0.0.1"

    # Path configuration for patient biomechanics trials
    # Override these via environment variables or a .env file for your lab.
    projects_root: str = "~/QTM_Projects"
    default_project: str = "My_Gait_Lab"

    # External pipeline engine paths (used by tools/pipeline.py)
    # Override via MATLAB_SCRIPTS_PATH and OPENSIM_CONFIG_ROOT env vars.
    matlab_scripts_path: str = "~/QTM_Projects/My_Gait_Lab/Matlab_Scripts"
    opensim_config_root: str = "~/QTM_Projects/My_Gait_Lab/OpenSim"

    # Enable reading from .env files
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def qtm_rest_url(self) -> str:
        """Returns the fully qualified REST API endpoint URL."""
        return f"http://{self.qtm_rest_host}:{self.qtm_rest_port}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Returns a cached singleton Settings instance.

    Uses lru_cache to defer .env file parsing until first access
    and guarantee a single shared instance across the application.
    """
    return Settings()
