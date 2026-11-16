# Security Policy

## Supported versions

Only the latest release receives security fixes. Please update via HACS before reporting.

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Report vulnerabilities privately via GitHub:
**Security → Report a vulnerability** (or use
[this link](https://github.com/TiWe1998/ha-led-wall-bridge/security/advisories/new)).

Please include:
- affected version,
- a description of the problem and its impact,
- steps to reproduce (if possible).

You will receive a response as soon as possible. Once a fix is available, it is published as a
new release together with a security advisory.

🇩🇪 Sicherheitslücken bitte **nicht** als öffentliches Issue melden, sondern vertraulich über
**Security → Report a vulnerability**.

## Security design

- Communication with the controller uses HTTPS. Because NovaStar controllers use self-signed
  certificates, the certificate is **pinned** when the device is added: its SHA-256 fingerprint
  is stored and checked on every connection. If the certificate changes, Home Assistant stops
  communicating with the device and asks the user to confirm it again (re-authentication).
- Data received from the controller is size-limited (1 MB for API responses, 10 MB for
  screenshots).
- Cloud requests use HTTPS with full certificate validation and are signed with a per-request
  checksum; the AppSecret itself is never transmitted.
- Passwords, tokens and keys are redacted from logs and diagnostics.
- The integration has no third-party Python dependencies.

## Recommendations for users

- Change the default password of your controller.
- Ideally put LED controllers into a separate network segment (VLAN) that only Home Assistant can
  reach.
