# Changelog

🇬🇧 English · 🇩🇪 [Deutsch weiter unten](#deutsch)

## v1.2.2

### ⚠️ Breaking change: new integration ID
The technical ID (domain) of the integration changed from `novastar_terminal` to
**`led_wall_bridge`**, so that folder, ID and name match and the integration cannot be mistaken for
an official NovaStar product.

**If you installed an earlier version:**
1. Note your controller's IP address, serial number and password (and the AppKey/AppSecret of a
   VNNOX cloud account, if used).
2. Settings → Devices & services → *NovaStar LED Controller* / *LED Wall Bridge* → ⋮ →
   **Delete** (for every entry, including the cloud account).
3. Update via HACS (or copy the new folder `custom_components/led_wall_bridge`) and delete the old
   folder `custom_components/novastar_terminal`.
4. Restart Home Assistant and add **LED Wall Bridge** again.

Entity IDs stay the same as long as the old entries are deleted before adding the new ones, so
existing automations and dashboards keep working.

### Added
- Integration icon is now shipped with the integration (`brand/` folder) and shown on the
  integrations page and in HACS after installation (Home Assistant 2026.3 or newer).

## v1.2.1 – Security hardening

### Security
- **Certificate pinning:** NovaStar controllers use self-signed certificates. The certificate's
  SHA-256 fingerprint is now stored when the device is added and checked on every connection. If it
  changes, communication stops and Home Assistant asks for re-authentication – this protects the
  controller password against man-in-the-middle attacks. Existing installations pin the certificate
  automatically on the first start.
- **Size limits** for data received from the controller (1 MB per API response, 10 MB per
  screenshot).
- **Hardened GitHub workflow:** all third-party actions pinned to fixed versions, read-only
  permissions, Dependabot keeps them up to date.
- Added `SECURITY.md` with a private vulnerability reporting process.

### Fixed
- Short device hiccups ("appService is null") no longer make the wall unavailable – the last values
  are kept for up to 3 failed polls.
- Replaced a Home Assistant function that will be removed in Home Assistant 2027.8.

## v1.2.0
- One shared VNNOX cloud account for all walls; walls that only exist in the cloud appear as their
  own devices.
- "Store values permanently" is now a switch under *Controls*.
- Field explanations in the setup dialogs, link to the NovaCloud Open Platform.
- 12 languages, English log messages, bilingual README.

---

<a id="deutsch"></a>
# Änderungsprotokoll (Deutsch)

## v1.2.2

### ⚠️ Wichtige Änderung: neue Integrations-Kennung
Die technische Kennung (Domain) der Integration wurde von `novastar_terminal` in
**`led_wall_bridge`** geändert. So passen Ordner, Kennung und Name zusammen, und die Integration
kann nicht mit einem offiziellen NovaStar-Produkt verwechselt werden.

**Wenn du eine frühere Version installiert hast:**
1. IP-Adresse, Seriennummer und Passwort deines Controllers notieren (und AppKey/AppSecret des
   VNNOX-Cloud-Kontos, falls genutzt).
2. Einstellungen → Geräte & Dienste → *NovaStar LED Controller* / *LED Wall Bridge* → ⋮ →
   **Löschen** (jeden Eintrag, auch das Cloud-Konto).
3. Über HACS aktualisieren (oder den neuen Ordner `custom_components/led_wall_bridge` kopieren)
   und den alten Ordner `custom_components/novastar_terminal` löschen.
4. Home Assistant neu starten und **LED Wall Bridge** neu hinzufügen.

Die Entitäts-IDs bleiben gleich, sofern die alten Einträge vor dem Neuanlegen gelöscht werden.
Bestehende Automationen und Dashboards funktionieren also weiter.

### Neu
- Das Symbol der Integration wird jetzt mitgeliefert (Ordner `brand/`) und nach der Installation
  auf der Integrationsseite und in HACS angezeigt (ab Home Assistant 2026.3).

## v1.2.1 – Sicherheitsverbesserungen

### Sicherheit
- **Zertifikats-Pinning:** NovaStar-Controller nutzen selbst ausgestellte Zertifikate. Beim
  Hinzufügen wird jetzt der SHA-256-Fingerabdruck des Zertifikats gespeichert und bei jeder
  Verbindung geprüft. Ändert er sich, bricht die Kommunikation ab und Home Assistant fordert eine
  erneute Anmeldung an – das schützt das Controller-Passwort vor Man-in-the-Middle-Angriffen.
  Bestehende Installationen merken sich das Zertifikat beim ersten Start automatisch.
- **Größenlimits** für Daten vom Controller (1 MB pro API-Antwort, 10 MB pro Screenshot).
- **Abgesicherter GitHub-Workflow:** alle fremden Actions auf feste Versionen fixiert, nur
  Leserechte, Dependabot hält sie aktuell.
- `SECURITY.md` mit vertraulichem Meldeweg für Sicherheitslücken.

### Behoben
- Kurze Aussetzer des Geräts („appService is null“) machen die Wall nicht mehr „nicht
  verfügbar“ – bis zu 3 fehlgeschlagene Abfragen werden mit den letzten Werten überbrückt.
- Eine Home-Assistant-Funktion ersetzt, die mit Home Assistant 2027.8 entfernt wird.

## v1.2.0
- Ein gemeinsames VNNOX-Cloud-Konto für alle Walls; Walls, die nur in der Cloud existieren,
  erscheinen als eigene Geräte.
- „Werte dauerhaft speichern“ ist jetzt ein Schalter unter *Steuerung*.
- Erklärtexte in den Einrichtungsdialogen, Link zur NovaCloud Open Platform.
- 12 Sprachen, englische Log-Meldungen, zweisprachiges README.
