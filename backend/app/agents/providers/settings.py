"""User-local provider settings with Windows-native secret protection.

The launcher owns the user-facing settings flow.  This module is deliberately
independent of the workflow database: it stores only provider metadata and a
DPAPI-protected API key in the current Windows user's local profile.
"""

from __future__ import annotations

import base64
import ctypes
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from .base import ProviderError
from .config import ProviderConfig, load_provider_config


SUPPORTED_REAL_PROVIDERS = ("openai-compatible",)
PROVIDER_ENVIRONMENT_KEYS = (
    "AGENTFORGE_LLM_PROVIDER",
    "AGENTFORGE_LLM_BASE_URL",
    "AGENTFORGE_LLM_MODEL",
    "AGENTFORGE_LLM_API_KEY",
    "AGENTFORGE_LLM_STRUCTURED_OUTPUT_MODE",
)
_CONFIG_VERSION = 1
_MAX_CONFIG_BYTES = 64 * 1024
_MAX_PROVIDER_LENGTH = 64
_MAX_BASE_URL_LENGTH = 2048
_MAX_MODEL_LENGTH = 256
_DPAPI_UI_FORBIDDEN = 0x1


class SecureStorageError(RuntimeError):
    """Safe failure raised when the user-local secret cannot be protected."""


class ProviderSettingsError(ValueError):
    """Safe validation failure for persisted or candidate settings."""


class SecretProtector(Protocol):
    def protect(self, value: bytes) -> bytes:
        """Protect one secret for the current user."""

    def unprotect(self, value: bytes) -> bytes:
        """Unprotect one secret for the current user."""


if os.name == "nt":

    class _DataBlob(ctypes.Structure):
        _fields_ = [
            ("cbData", ctypes.c_uint32),
            ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
        ]


class WindowsDPAPIProtector:
    """Use CryptProtectData/CryptUnprotectData; no application key is created."""

    def _crypt(self, value: bytes, *, protect: bool) -> bytes:
        if os.name != "nt":
            raise SecureStorageError("Windows secure storage is unavailable")
        if not value:
            raise SecureStorageError("Stored provider secret is unavailable")

        crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        function = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
        function.argtypes = [
            ctypes.POINTER(_DataBlob),
            ctypes.c_wchar_p,
            ctypes.POINTER(_DataBlob),
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(_DataBlob),
        ]
        function.restype = ctypes.c_int
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p

        source = ctypes.create_string_buffer(value)
        source_blob = _DataBlob(
            len(value), ctypes.cast(source, ctypes.POINTER(ctypes.c_ubyte))
        )
        target_blob = _DataBlob()
        description = "AgentForge provider secret" if protect else None
        flags = _DPAPI_UI_FORBIDDEN if protect else 0
        success = function(
            ctypes.byref(source_blob),
            description,
            None,
            None,
            None,
            flags,
            ctypes.byref(target_blob),
        )
        if not success or not target_blob.pbData:
            raise SecureStorageError("Windows secure storage operation failed")
        try:
            return ctypes.string_at(target_blob.pbData, target_blob.cbData)
        finally:
            kernel32.LocalFree(target_blob.pbData)

    def protect(self, value: bytes) -> bytes:
        return self._crypt(value, protect=True)

    def unprotect(self, value: bytes) -> bytes:
        return self._crypt(value, protect=False)


def default_provider_config_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return base / "AgentForge" / "config" / "provider.json"


@dataclass(frozen=True, slots=True)
class ProviderSettingsSnapshot:
    """Secret-free state suitable for a launcher label or diagnostics view."""

    provider: str = "unconfigured"
    base_url: str = ""
    model: str = ""
    structured_output_mode: str = "json_schema"
    configured: bool = False
    credential_configured: bool = False
    validation_error: str | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class _StoredSettings:
    provider: str
    base_url: str
    model: str
    structured_output_mode: str
    api_key: str = field(repr=False)


def _safe_text(value: object, *, limit: int) -> str:
    if not isinstance(value, str):
        raise ProviderSettingsError("Stored provider settings are invalid")
    value = value.strip()
    if len(value) > limit:
        raise ProviderSettingsError("Stored provider settings are invalid")
    return value


class ProviderSettingsStore:
    """Atomically persist non-secret metadata plus a DPAPI-protected secret."""

    def __init__(
        self,
        *,
        config_path: Path | None = None,
        protector: SecretProtector | None = None,
    ) -> None:
        self.config_path = Path(config_path or default_provider_config_path()).expanduser()
        self.protector = protector or WindowsDPAPIProtector()

    def _read_payload(self) -> dict[str, object] | None:
        if not self.config_path.is_file():
            return None
        try:
            if self.config_path.stat().st_size > _MAX_CONFIG_BYTES:
                raise ProviderSettingsError("Stored provider settings are invalid")
            payload = json.loads(self.config_path.read_text(encoding="utf-8"))
        except ProviderSettingsError:
            raise
        except (OSError, UnicodeError, ValueError) as exc:
            raise ProviderSettingsError("Stored provider settings are unavailable") from exc
        if not isinstance(payload, dict):
            raise ProviderSettingsError("Stored provider settings are invalid")
        return payload

    def _read_stored(self) -> _StoredSettings | None:
        payload = self._read_payload()
        if payload is None:
            return None
        if payload.get("version") != _CONFIG_VERSION:
            raise ProviderSettingsError("Stored provider settings are invalid")
        provider = _safe_text(payload.get("provider"), limit=_MAX_PROVIDER_LENGTH).lower()
        base_url = _safe_text(payload.get("base_url"), limit=_MAX_BASE_URL_LENGTH)
        model = _safe_text(payload.get("model"), limit=_MAX_MODEL_LENGTH)
        mode = _safe_text(payload.get("structured_output_mode", "json_schema"), limit=32).lower()
        encoded = payload.get("api_key_dpapi")
        if not isinstance(encoded, str) or not encoded:
            api_key = ""
        else:
            try:
                protected = base64.b64decode(encoded.encode("ascii"), validate=True)
                if not protected or len(protected) > _MAX_CONFIG_BYTES:
                    raise ValueError
                api_key = self.protector.unprotect(protected).decode("utf-8")
            except (ValueError, UnicodeError, SecureStorageError, OSError) as exc:
                raise SecureStorageError("Stored provider secret is unavailable") from exc
            if not api_key or len(api_key) > _MAX_CONFIG_BYTES:
                raise SecureStorageError("Stored provider secret is unavailable")
        return _StoredSettings(provider, base_url, model, mode, api_key)

    @staticmethod
    def _environment_for(stored: _StoredSettings) -> dict[str, str]:
        environment = {
            "AGENTFORGE_LLM_PROVIDER": stored.provider,
            "AGENTFORGE_LLM_BASE_URL": stored.base_url,
            "AGENTFORGE_LLM_MODEL": stored.model,
            "AGENTFORGE_LLM_STRUCTURED_OUTPUT_MODE": stored.structured_output_mode,
        }
        if stored.api_key:
            environment["AGENTFORGE_LLM_API_KEY"] = stored.api_key
        return environment

    @staticmethod
    def _config_from(stored: _StoredSettings) -> ProviderConfig:
        try:
            return load_provider_config(
                ProviderSettingsStore._environment_for(stored),
                allow_default_mock=False,
            )
        except ProviderError as exc:
            return ProviderConfig(
                provider="unconfigured",
                validation_error=f"Stored provider settings are invalid: {exc.category.value}",
            )

    def snapshot(self) -> ProviderSettingsSnapshot:
        try:
            stored = self._read_stored()
            if stored is None:
                return ProviderSettingsSnapshot()
            config = self._config_from(stored)
            return ProviderSettingsSnapshot(
                provider=stored.provider,
                base_url=stored.base_url,
                model=stored.model or "not-configured",
                structured_output_mode=stored.structured_output_mode,
                configured=config.configured,
                credential_configured=bool(stored.api_key),
                validation_error=config.validation_error,
            )
        except (ProviderSettingsError, SecureStorageError) as exc:
            return ProviderSettingsSnapshot(validation_error=str(exc))

    def load_provider_config(self) -> ProviderConfig:
        try:
            stored = self._read_stored()
        except (ProviderSettingsError, SecureStorageError) as exc:
            return ProviderConfig(provider="unconfigured", validation_error=str(exc))
        if stored is None:
            return ProviderConfig(
                provider="unconfigured",
                validation_error="Provider settings are not configured",
            )
        return self._config_from(stored)

    def environment(self) -> dict[str, str]:
        """Return a complete child environment only for valid saved settings."""

        try:
            stored = self._read_stored()
            if stored is None:
                return {}
            config = self._config_from(stored)
            if not config.configured:
                return {}
            return self._environment_for(stored)
        except (ProviderSettingsError, SecureStorageError):
            return {}

    def _existing_api_key(self) -> str:
        try:
            stored = self._read_stored()
        except (ProviderSettingsError, SecureStorageError) as exc:
            raise ProviderSettingsError("Saved provider secret is unavailable") from exc
        if stored is None or not stored.api_key:
            return ""
        return stored.api_key

    def validate_candidate(
        self,
        *,
        provider: str,
        base_url: str,
        model: str,
        api_key: str | None,
    ) -> ProviderConfig:
        provider = provider.strip().lower()
        if provider not in SUPPORTED_REAL_PROVIDERS:
            raise ProviderSettingsError("This provider is not supported for real connections")
        effective_key = self._existing_api_key() if api_key is None else api_key
        environment = {
            "AGENTFORGE_LLM_PROVIDER": provider,
            "AGENTFORGE_LLM_BASE_URL": base_url.strip(),
            "AGENTFORGE_LLM_MODEL": model.strip(),
            "AGENTFORGE_LLM_API_KEY": effective_key,
            "AGENTFORGE_LLM_STRUCTURED_OUTPUT_MODE": "json_schema",
        }
        config = load_provider_config(environment, allow_default_mock=False)
        if not config.configured:
            raise ProviderSettingsError(config.validation_error or "Provider settings are invalid")
        return config

    def save(
        self,
        *,
        provider: str,
        base_url: str,
        model: str,
        api_key: str | None,
    ) -> ProviderSettingsSnapshot:
        config = self.validate_candidate(
            provider=provider,
            base_url=base_url,
            model=model,
            api_key=api_key,
        )
        try:
            protected = self.protector.protect(config.api_key.encode("utf-8"))
        except (SecureStorageError, OSError) as exc:
            raise SecureStorageError("Windows secure storage operation failed") from exc
        payload = {
            "version": _CONFIG_VERSION,
            "provider": config.provider,
            "base_url": config.base_url,
            "model": config.model,
            "structured_output_mode": config.structured_output_mode.value,
            "api_key_dpapi": base64.b64encode(protected).decode("ascii"),
        }
        self._atomic_write(json.dumps(payload, ensure_ascii=True, separators=(",", ":")))
        return self.snapshot()

    def clear(self) -> None:
        try:
            self.config_path.unlink(missing_ok=True)
        except OSError as exc:
            raise SecureStorageError("Provider settings could not be cleared") from exc

    def _atomic_write(self, content: str) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.config_path.with_name(
            f".{self.config_path.name}.{os.getpid()}.{uuid4().hex}.tmp"
        )
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.config_path)
        except OSError as exc:
            raise SecureStorageError("Provider settings could not be saved") from exc
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
