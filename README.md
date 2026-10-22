# AigoSmart HA

Native Home Assistant integration for AigoSmart kettles using the AigoSmart /
Alibaba IoT cloud API. Version **0.1.1**, development status.

Optional dashboard companion: [AigoSmart Premium Card](https://github.com/lovicub/aigosmart-premium-card).
The integration works independently; the card has its own installation and configuration.
<img width="1986" height="1242" alt="image" src="https://github.com/user-attachments/assets/41df2fe4-09f4-41ee-a909-ca9b675c9370" />

## Features

- UI account setup with email security-code verification and reauthentication.
- Heating ON/OFF using the `HeatingSwitch` switch.
- Target temperature: 0–100 °C using a number entity.
- Operating mode selection: 0, 1 or 2, with TSL labels in `mode_labels`.
- Heat preservation: 0–13 hours using a number entity.
- Monitoring: heating state, status, target temperature, time and heat preservation.
- Cloud polling every 15 seconds by default; configurable from 15 to 3600 seconds.
- Live TSL access/type/range/step validation before writes.
- One write attempt per action, no automatic retries, followed by confirmation reads.
- English, German and Polish setup translations.

Only Target_temperature, Mode, heatpreservation and HeatingSwitch are writable.
Status and Time remain read-only in this integration. Ranges and available controls
are derived from the device's live TSL, rather than assumed for every model.

The integration does **not** restore heating after a Home Assistant restart. Startup
reads the current state without issuing a command. A kettle already heating is not
automatically stopped either. Your own automations can still call entity services.

## Supported devices

| Device | Support |
| --- | --- |
| AigoSmart / Aigostar kettle exposing HeatingSwitch, Target_temperature, Mode, Time, status and heatpreservation | Development support for the documented six-property model |
| Other AigoSmart appliances, bulbs or non-EU accounts | Not supported or verified |

No exact retail model number was supplied; this project does not claim universal
Aigostar compatibility. The reviewed cloud endpoints support the EU region only.
Read access and a temperature write were verified during the original investigation;
the published release's control paths are covered by offline tests, not a new live
hardware certification. Confirm the TSL on your own model before relying on controls.

## Installation via HACS

After this repository is published:

1. Open HACS → Custom repositories.
2. Add `https://github.com/lovicub/aigosmart-ha`, category **Integration**.
3. Download AigoSmart HA and restart Home Assistant.
4. Follow Configuration below.

This is a custom repository; inclusion in HACS's default catalog is not claimed.
The repository targets Home Assistant 2026.10.2 or newer. Test results refer to
2026.10.2's classes; see [Validation](VALIDATION.md) for the exact environment.

## Manual installation

1. Download this repository, or build an archive with `python tools/build_zip.py`.
2. Copy `custom_components/aigosmart` into your HA configuration directory as
   `config/custom_components/aigosmart` (normally `/config/custom_components/aigosmart`).
3. Restart Home Assistant. Do not copy tests, scripts or your virtual environment
   into `custom_components`.

For updates, replace the complete `aigosmart` directory and restart HA.

## Configuration

1. Open **Settings → Devices & services → Add integration → AigoSmart HA**.
2. Enter your AigoSmart email address and password.
3. If verification is requested, select **Send verification email** and submit.
   Enter the code in the next submission. Sending is explicit, without automatic retry.
4. Select the kettle. Device choices use local sequence numbers instead of account
   or device identifiers. Add each kettle separately.
5. Use **Configure** on the integration entry to change the polling interval.

Home Assistant stores the email and IoT session token in the config entry. The
password and verification code are held in the setup flow, not persisted in the
entry. Protect your HA configuration and backups; `.storage` is not an encrypted
credential vault. This client reuses the session between polls but does not refresh
it automatically; an authentication failure requires reauthentication in HA.
No cryptography version is pinned by the integration: it uses HA's installed library.
The root `requirements.txt` is for the optional standalone scripts only.

Write results appear in the `last_write_result` attribute:

| Result | Meaning |
| --- | --- |
| confirmed | A subsequent read matches the requested value |
| accepted_unconfirmed | The API accepted the request, but confirmation reads did not match |
| outcome_unknown | The request failed or timed out, so its actual outcome is unknown |

Confirmation reads occur immediately, then after 2 and another 5 seconds. A matching
read is evidence of state, not proof that a particular request caused it. Writes
are never replayed automatically after a timeout.

## Troubleshooting

- **Unavailable:** check the kettle in the official app, internet connectivity and
  cloud availability. Polling errors mark entities unavailable.
- **Verification fails:** request a code explicitly, check expiration and complete
  any CAPTCHA in the official app. Avoid repeated requests when rate-limited.
- **Reauthentication required:** use the original account containing the same device.
- **A control is missing:** the live TSL must expose a writable property with supported
  type and constraints. Do not bypass validation with raw API calls.
- **Unconfirmed write:** inspect the actual device state before acting again. The
  integration will not resend the command.
- **Custom integration not found:** check directory nesting and restart HA.
- **Dependency conflict:** do not install standalone-script requirements into HA.

Before opening an issue, remove email addresses, tokens, passwords, iotId, Virtual ID,
MAC/IP addresses and personal device names from logs and screenshots. Never upload
HA `.storage`, full API responses or account exports.

## Development

```sh
python -m venv .venv
.venv/bin/python -m pip install homeassistant==2026.10.2
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tools/build_zip.py
```

Tests use mock transports and a synthetic TSL fixture. GitHub Actions includes
offline tests, hassfest and HACS validation. The original CLI tools are retained
under `scripts/`; they can access real devices when explicitly run interactively.
Do not run live CLI modes as part of CI. See [Validation](VALIDATION.md),
[Security review](SECURITY_REVIEW.md) and [license notes](THIRD_PARTY_NOTICES.md).

## Disclaimer

Unofficial community project, not affiliated with or endorsed by Aigostar, Alibaba,
Home Assistant or HACS. Cloud APIs may change without notice. Heating controls
operate a physical appliance: follow its manufacturer's instructions and do not
use this integration as a safety interlock. Distributed under the MIT License,
without warranty. Product names and trademarks belong to their respective owners.
