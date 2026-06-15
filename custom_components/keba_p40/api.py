"""Async client for the local KEBA P40 REST API."""

from __future__ import annotations

from typing import Any

from aiohttp import ClientError, ClientResponseError, ClientSession


class KebaApiError(Exception):
    """Base exception for KEBA API errors."""


class KebaAuthenticationError(KebaApiError):
    """Raised when authentication fails."""


class KebaConnectionError(KebaApiError):
    """Raised when the wallbox cannot be reached."""


class KebaApi:
    """Communicate with a KEBA P40."""

    def __init__(
        self,
        session: ClientSession,
        host: str,
        port: int,
        username: str,
        password: str,
    ) -> None:
        self._session = session
        self._base_url = f"https://{host}:{port}"
        self._username = username
        self._password = password
        self._access_token: str | None = None

    async def async_login(self) -> None:
        """Authenticate and store a JWT access token."""
        try:
            response = await self._session.post(
                f"{self._base_url}/v2/jwt/login",
                json={"username": self._username, "password": self._password},
                timeout=20,
            )
            response.raise_for_status()
            body = await response.json()
        except ClientResponseError as err:
            if err.status == 401:
                raise KebaAuthenticationError("Invalid username or password") from err
            raise KebaApiError(f"Login failed with HTTP {err.status}") from err
        except (ClientError, TimeoutError) as err:
            raise KebaConnectionError("Unable to connect to the KEBA P40") from err

        self._access_token = body.get("accessToken")
        if not self._access_token:
            raise KebaAuthenticationError("Login response did not contain an access token")

    async def async_request(
        self,
        method: str,
        path: str,
        *,
        retry_auth: bool = True,
        **kwargs: Any,
    ) -> Any:
        """Make an authenticated API request."""
        if self._access_token is None:
            await self.async_login()

        headers = dict(kwargs.pop("headers", {}))
        headers["Authorization"] = f"Bearer {self._access_token}"

        try:
            response = await self._session.request(
                method,
                f"{self._base_url}{path}",
                headers=headers,
                timeout=20,
                **kwargs,
            )

            if response.status == 401 and retry_auth:
                self._access_token = None
                await self.async_login()
                return await self.async_request(
                    method,
                    path,
                    retry_auth=False,
                    **kwargs,
                )

            response.raise_for_status()
            if response.content_length == 0:
                return None
            return await response.json()
        except ClientResponseError as err:
            if err.status == 401:
                raise KebaAuthenticationError("KEBA authentication failed") from err
            raise KebaApiError(
                f"{method} {path} failed with HTTP {err.status}"
            ) from err
        except (ClientError, TimeoutError) as err:
            raise KebaConnectionError("Unable to connect to the KEBA P40") from err

    async def async_get_wallboxes(self) -> list[dict[str, Any]]:
        """Return all configured wallboxes."""
        body = await self.async_request("GET", "/v2/wallboxes")
        if isinstance(body, dict) and isinstance(body.get("wallboxes"), list):
            return body["wallboxes"]
        if isinstance(body, list):
            return body
        raise KebaApiError("Unexpected response from /v2/wallboxes")

    async def async_get_wallbox(self, serial: str) -> dict[str, Any]:
        """Return status for one wallbox."""
        body = await self.async_request("GET", f"/v2/wallboxes/{serial}")
        if not isinstance(body, dict):
            raise KebaApiError("Unexpected wallbox status response")
        return body

    async def async_get_load_management(self) -> dict[str, Any]:
        """Return all load management values."""
        body = await self.async_request("GET", "/v2/configs/lmgmt")
        if not isinstance(body, dict):
            raise KebaApiError("Unexpected load management response")
        return body

    async def async_set_max_available_current(self, current_ma: int) -> None:
        """Set maximum available current in milliamperes."""
        await self.async_request(
            "PUT",
            "/v2/configs/lmgmt",
            json={
                "configs": [
                    {
                        "key": "max_available_current",
                        "value": current_ma,
                    }
                ]
            },
        )

    async def async_set_phases(self, serial: str, phases: int) -> None:
        """Switch the wallbox to one or three phases."""
        if phases not in (1, 3):
            raise ValueError("phases must be 1 or 3")
        await self.async_request(
            "POST",
            f"/v2/wallboxes/{serial}/phase-toggle?numberOfPhases={phases}",
            json={},
        )

    async def async_start_charging(self, serial: str) -> None:
        """Start charging on a wallbox."""
        await self.async_request(
            "POST",
            f"/v2/wallboxes/{serial}/start-charging",
        )

    async def async_stop_charging(self, serial: str) -> None:
        """Stop charging on a wallbox."""
        await self.async_request(
            "POST",
            f"/v2/wallboxes/{serial}/stop-charging",
        )
