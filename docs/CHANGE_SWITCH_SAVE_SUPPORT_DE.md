# Change: Unterstützung für rohe Xbox-360-/nfsmw-nx-Spielstände

Stand: 6. Oktober 2026. Basis: Originalprojekt v1.5.0,
Commit `67cf6a0f85e7a244920d65863deab7b7163aaf72`.

## Ergebnis

Der Editor erhält Unterstützung für rohe Xbox-360-Spielstände,
wie sie `nfsmw-nx` auf der Switch speichert. Bearbeitet werden können
Profilwerte, Geld, Reward-Karten, Garage, Tuning, Auto-Builds und
Karrierevorlagen.

PC-Spielstände werden weiterhin mit dem bisherigen Code bearbeitet. Für das
bekannte native Format erkennt der Editor automatisch die andere Struktur
und liest bzw. schreibt die Werte in der passenden Byte-Reihenfolge.
Der vorhandene Apply-/Save-Ablauf einschließlich Sicherung bleibt erhalten.

## Codeänderung

| Datei | Zweck |
| --- | --- |
| `nfs_mw_save_editor/core/savefile.py` | Automatische Auswahl des Formatadapters |
| `nfs_mw_save_editor/core/switch_format.py` (neu) | Lesen, typedatenabhängige Umsetzung, Speichern und native Prüfsummen |
| `nfs_mw_save_editor/core/career_progress.py` | Originaler Karriereparser erhält normalisierte Daten |
| `nfs_mw_save_editor/core/career_transplant.py` | Blacklist-Stufe auch bei nativer Dateigröße auslesen |

Es wurden **drei bestehende Python-Dateien angepasst und ein Backend-Modul
ergänzt**. Zusätzlich kommen Tests, ein GUI-Prüfskript und diese Dokumentation
hinzu.

Die Fahrzeugtabellen liegen im nativen Format um **8 Bytes = 64 Bits**
versetzt. Hinzu kommen Big Endian statt Little Endian, andere Paddingwerte,
Bitfelder und eine andere Dateigröße. Deshalb genügt eine pauschale
Verschiebung oder ein blindes Umdrehen aller Bytes nicht.

Der Adapter stellt der vorhandenen Bearbeitungslogik intern eine PC-Ansicht
bereit. Nach außen bleibt der Puffer ein nativer Spielstand. Beim Speichern
werden nur geänderte bekannte Bereiche in die ursprünglichen nativen Daten
zurückgeschrieben. Unbekannte native Daten bleiben erhalten.

## Funktionen und Prüfungen

- Geld, Profilname und alle 21 bekannten Reward-/Junkman-Kartentypen.
- Garage, Career/My Cars, aktives Auto, Kopfgeld und Heat.
- Performance-Tuning und Junkman-Teile.
- Alle 34 mitgelieferten Auto-Builds in beiden Zielbereichen, einschließlich
  Speichern, erneutem Laden und JSON-Export.
- Alle 30 Karrierevorlagen in beiden Kopfgeld-Modi, einschließlich Speichern
  und erneutem Laden; Karriereübersicht und Blacklist-Stufe.
- Originaler Ablauf: Änderungen vormerken, `Apply (memory)`,
  `Save + backup`, von der Datei erneut laden.
- Äußere MD5, innere Gameplay-MD5 und alle drei EA-CRC-Prüfsummen.

**203 bestehende PC-Kerntests und 165 neue Formatprüfungen bestanden.**
Der Test der Originaloberfläche mit einer temporären Kopie des nativen Saves
bestand ebenfalls. Der bereitgestellte Originalspielstand blieb unverändert.

Unter Linux scheiterten bereits beim unveränderten Original zwei
Font-/Layouttests; 359 weitere Basistests bestanden. Diese beiden Prüfungen
werden ausdrücklich nicht als bestanden ausgegeben. Ein direkter Start der
Windows-EXE und ein Test des bearbeiteten Saves im Spiel auf einer echten
Switch stehen noch aus.

## Zu bearbeitende Spielstandsdatei

`saves/<Profil>/actual` und `saves/<Profil>/anterior` sind Ordner mit
automatisch erzeugten Kopien. Der Port lädt daraus keinen Spielstand. Beim
Schließen eines Spielstandscontainers ersetzt er diese Kopien: Das alte
`anterior` wird gelöscht, `actual` wird zu `anterior`, und eine neue Kopie des
echten Spielstands wird zu `actual`. Deshalb können Änderungen dort wieder
verschwinden und auch die dort abgelegte Editor-Sicherung gelöscht werden.
Beide Kopien zu ändern löst das Problem nicht.

Die tatsächlich zu bearbeitende Datei liegt bei der Standardinstallation in:

```text
<Portordner>\nfsmw\<XUID>\454107D9\00000001\<Profil>\<Profil>
```

Der letzte Bestandteil ist eine Datei ohne Endung. Die vorhandene XUID und
Profilstruktur verwenden; `Headers` und `<Profil>.header` erhalten.
Spiel vollständig schließen, Switch ausschalten, dann diese Datei im Editor
öffnen. Änderungen mit `Apply (memory)` übernehmen und mit `Save + backup`
schreiben. Vor dem nächsten Spielstart dieselbe Datei im Editor neu öffnen
und die Werte prüfen. Eine zusätzliche Sicherung kann auf dem PC liegen.

MD5/DATA = BAD nach einer Änderung im Speicher ist erwartbar, bis die
Prüfsummen neu berechnet sind. `Fix checksums` repariert sie im Speicher;
das Speichern erledigt dies automatisch. Dieser Ablauf erfordert für das
beschriebene Pfadproblem keine Änderung am Backend oder an der GUI.

Die Zuordnung und das Überschreiben der Kopien sind am Port-Quellcode geprüft:
[technischer Nachweis](SWITCH_SAVE_FORMAT.md#edit-the-authoritative-runtime-save).

## Umfang der Formatunterstützung

Unterstützt werden die bisherigen PC-v1.3-Spielstände mit 63.596 Bytes und
das dokumentierte rohe native MC02-Format mit 62.688 Bytes und Version
`0x10D`. Der Dateiname bzw. eine fehlende Erweiterung spielt keine Rolle.
Xbox-STFS-Container und beliebige andere Spielstandsversionen werden durch
diesen Change nicht neu unterstützt.

Zwei nicht verifizierte PC-Karrieresettings werden nicht auf native Felder
übertragen. Die entsprechende technische Grenze und das anhand bekannter
Fixtures geprüfte Parsing der gepackten Lua-Werte sind in
[SWITCH_SAVE_FORMAT.md](SWITCH_SAVE_FORMAT.md) beschrieben.

## Für das Originalprojekt einreichen

Projekt: <https://github.com/sprintstate/nfs-mw-save-editor>

Der beigefügte Git-Patch bezieht sich auf den bereitgestellten v1.5.0-Stand.
Im Repository-Hauptordner zuerst prüfen, dann anwenden:

```powershell
git apply --check .\nfsmw-original-ui-switch-support.patch
git apply .\nfsmw-original-ui-switch-support.patch
git diff --stat
```

Bei einem neueren Projektstand müssen Abweichungen vor dem Anwenden geprüft
werden. Eine englische Beschreibung zum Einfügen in den Originalthread bzw.
einen Pull Request liegt unter `docs/PR_SWITCH_SAVE_SUPPORT.md` bei.

## Portable Ausgabe

Die portable Ausgabe enthält den originalen Windows-Bootloader und den
originalen `_internal`-Ordner. Im eingebetteten Python-Archiv werden nur die
drei geänderten Backend-Module ersetzt und `core.switch_format` ergänzt.
Der Einstiegspunkt `main` und alle 18 eingebetteten GUI-Module bleiben
bytegleich erhalten; 430 bestehende PYZ-Einträge und alle 281 Laufzeitdateien
bleiben unverändert. Ein Prüfnachweis und das Repack-Skript liegen bei.

Es handelt sich um eine angepasste Ausgabe, nicht um eine bereits vom
Originalautor veröffentlichte neue Version. Die Versionsanzeige im Programm nennt weiterhin die Basisversion v1.5.0.
