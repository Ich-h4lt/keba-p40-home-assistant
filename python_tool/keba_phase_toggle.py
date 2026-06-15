#!/usr/bin/env python3
import argparse
import getpass
import json
import os
import sys
from typing import Any, Dict, List, Optional

import requests
import urllib3


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class KebaApi:
    def __init__(self, host: str, username: str, password: str):
        self.base_url = f"https://{host}:8443"
        self.username = username
        self.password = password
        self.access_token: Optional[str] = None

    def request(self, method: str, path: str, **kwargs) -> Any:
        headers = kwargs.pop("headers", {})

        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"

        response = requests.request(
            method,
            f"{self.base_url}{path}",
            headers=headers,
            verify=False,
            timeout=20,
            **kwargs,
        )

        try:
            body = response.json()
        except ValueError:
            body = response.text

        if not response.ok:
            print(f"\nFehler bei {method} {path}: HTTP {response.status_code}", file=sys.stderr)
            print(json.dumps(body, indent=2, ensure_ascii=False) if isinstance(body, dict) else body, file=sys.stderr)
            response.raise_for_status()

        return body

    def login(self) -> None:
        body = self.request(
            "POST",
            "/v2/jwt/login",
            headers={"Content-Type": "application/json"},
            json={
                "username": self.username,
                "password": self.password,
            },
        )

        self.access_token = body.get("accessToken")
        if not self.access_token:
            raise RuntimeError(f"Login hat keinen accessToken geliefert: {body}")

    def get_wallboxes(self) -> List[Dict[str, Any]]:
        body = self.request("GET", "/v2/wallboxes")

        # Laut API ist üblicherweise body["wallboxes"] vorhanden.
        # Fallbacks machen das Skript etwas robuster.
        if isinstance(body, dict) and isinstance(body.get("wallboxes"), list):
            return body["wallboxes"]

        if isinstance(body, list):
            return body

        raise RuntimeError(f"Unerwartete Antwort von /v2/wallboxes: {body}")

    def find_serial(self, wanted_serial: Optional[str] = None) -> str:
        wallboxes = self.get_wallboxes()

        if not wallboxes:
            raise RuntimeError("Keine Wallbox gefunden.")

        if wanted_serial:
            for wb in wallboxes:
                if str(wb.get("serialNumber")) == str(wanted_serial):
                    return str(wb["serialNumber"])
            raise RuntimeError(f"Seriennummer {wanted_serial} wurde nicht gefunden.")

        if len(wallboxes) == 1:
            return str(wallboxes[0]["serialNumber"])

        print("\nMehrere Wallboxen gefunden:")
        for wb in wallboxes:
            print(
                f"- serialNumber={wb.get('serialNumber')}, "
                f"alias={wb.get('alias')}, "
                f"state={wb.get('state')}, "
                f"phaseUsed={wb.get('phaseUsed')}"
            )

        raise RuntimeError("Bitte mit --serial die gewünschte Wallbox angeben.")

    def get_wallbox_status(self, serial: str) -> Dict[str, Any]:
        return self.request("GET", f"/v2/wallboxes/{serial}")

    def get_max_available_current(self) -> int:
        body = self.request("GET", "/v2/configs/lmgmt/max_available_current")
        configs = body.get("configs") if isinstance(body, dict) else None

        if isinstance(configs, list):
            for config in configs:
                if config.get("key") == "max_available_current":
                    return int(config["value"])

        raise RuntimeError(f"Unerwartete Antwort für max_available_current: {body}")

    def get_max_asymmetrical_phase_current(self) -> int:
        body = self.request("GET", "/v2/configs/lmgmt/max_asymmetrical_phase_current")
        configs = body.get("configs") if isinstance(body, dict) else None

        if isinstance(configs, list):
            for config in configs:
                if config.get("key") == "max_asymmetrical_phase_current":
                    return int(config["value"])

        raise RuntimeError(f"Unerwartete Antwort für max_asymmetrical_phase_current: {body}")

    def set_max_available_current(self, current_ma: int) -> Any:
        if current_ma <= 0:
            raise ValueError("--max-current muss größer als 0 A sein.")

        return self.request(
            "PUT",
            "/v2/configs/lmgmt",
            headers={"Content-Type": "application/json"},
            json={
                "configs": [
                    {
                        "key": "max_available_current",
                        "value": current_ma,
                    }
                ]
            },
        )

    def toggle_phases(self, serial: str, phases: int) -> Any:
        if phases not in (1, 3):
            raise ValueError("--phases darf nur 1 oder 3 sein.")

        return self.request(
            "POST",
            f"/v2/wallboxes/{serial}/phase-toggle?numberOfPhases={phases}",
            headers={"Content-Type": "application/json"},
            json={},
        )



def print_relevant_status(
    title: str,
    status: Dict[str, Any],
    max_available_current_ma: int,
    max_asymmetrical_phase_current_ma: int,
) -> None:
    meter = status.get("meter") or {}

    phase_used = status.get("phaseUsed")
    max_current_ma = status.get("maxCurrent")
    current_offered_ma = meter.get("currentOffered")
    total_active_power_mw = meter.get("totalActivePower")
    lines = meter.get("lines") or []

    print(f"\n=== {title} ===")
    print(f"phaseUsed:         {phase_used}")

    if isinstance(max_current_ma, int):
        max_current_a = max_current_ma / 1000
        max_power_kw = 3**0.5 * 400 * max_current_a / 1000
        print(
            f"maxCurrent:        {max_current_ma} mA ({max_current_a:g} A, "
            f"ca. {max_power_kw:.1f} kW dreiphasig)"
        )
    else:
        print(f"maxCurrent:        {max_current_ma}")

    print(
        f"maxAvailableCurrent: {max_available_current_ma} mA "
        f"({max_available_current_ma / 1000:g} A)"
    )
    print(
        f"maxAsymmetricalPhaseCurrent: {max_asymmetrical_phase_current_ma} mA "
        f"({max_asymmetrical_phase_current_ma / 1000:g} A)"
    )

    if isinstance(current_offered_ma, int):
        print(f"currentOffered:    {current_offered_ma} mA ({current_offered_ma / 1000:.2f} A)")
    else:
        print(f"currentOffered:    {current_offered_ma}")

    currents_by_phase = {
        line.get("socketPhase"): line.get("current")
        for line in lines
        if isinstance(line, dict)
    }
    for phase in ("L1", "L2", "L3"):
        current_ma = currents_by_phase.get(phase)
        if isinstance(current_ma, int):
            print(f"current{phase}:          {current_ma} mA ({current_ma / 1000:.2f} A)")
        else:
            print(f"current{phase}:          {current_ma}")

    if isinstance(total_active_power_mw, int):
        print(
            f"totalActivePower:  {total_active_power_mw} mW "
            f"({total_active_power_mw / 1_000:.0f} W / {total_active_power_mw / 1_000_000:.3f} kW)"
        )
    else:
        print(f"totalActivePower:  {total_active_power_mw}")


def main() -> int:
    parser = argparse.ArgumentParser(description="KEBA P40 Status abfragen und Einstellungen ändern.")
    parser.add_argument("--host", required=True, help="IP oder Hostname der Wallbox, z.B. 192.168.178.50")
    parser.add_argument("--user", default="admin", help="API-Benutzer, default: admin")
    parser.add_argument(
        "--password",
        help=(
            "API-Passwort; alternativ KEBA_PASSWORD setzen oder verdeckt "
            "eingeben"
        ),
    )
    parser.add_argument("--phases", type=int, choices=[1, 3], help="Optional: auf 1 oder 3 Phasen umschalten")
    parser.add_argument("--serial", help="Optional: Seriennummer, falls mehrere Wallboxen vorhanden sind")
    parser.add_argument(
        "--max-current",
        dest="max_current",
        type=float,
        help="Optional: max_available_current in Ampere setzen, z.B. 10",
    )
    args = parser.parse_args()

    if args.max_current is not None and args.max_current <= 0:
        parser.error("--max-current muss größer als 0 A sein.")

    password = args.password or os.environ.get("KEBA_PASSWORD")
    if not password:
        password = getpass.getpass("API-Passwort: ")

    api = KebaApi(args.host, args.user, password)

    print("1) Login")
    api.login()
    print("Login erfolgreich.")

    print("\n2) Seriennummer suchen")
    serial = api.find_serial(args.serial)
    print(f"Verwendete Seriennummer: {serial}")

    status_before = api.get_wallbox_status(serial)
    max_available_current_before_ma = api.get_max_available_current()
    max_asymmetrical_phase_current_before_ma = api.get_max_asymmetrical_phase_current()
    print_relevant_status(
        "Status vorher",
        status_before,
        max_available_current_before_ma,
        max_asymmetrical_phase_current_before_ma,
    )

    step = 3
    if args.max_current is not None:
        current_ma = round(args.max_current * 1000)
        print(
            f"\n{step}) max_available_current ändern: "
            f"{max_available_current_before_ma / 1000:g} A -> {current_ma / 1000:g} A"
        )
        result = api.set_max_available_current(current_ma)
        print("Antwort:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        step += 1

    if args.phases is not None:
        print(f"\n{step}) Toggle auf {args.phases} Phase(n)")
        result = api.toggle_phases(serial, args.phases)
        print("Toggle-Antwort:")
        print(json.dumps(result, indent=2, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"\nFehler: {exc}", file=sys.stderr)
        raise SystemExit(1)
