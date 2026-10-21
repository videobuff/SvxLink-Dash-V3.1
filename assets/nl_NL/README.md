# Nederlands SvxLink-geluidspakket

`assets/nl_NL.tar.xz` bevat de op de PI3TWE-installatie gebruikte Nederlandse
clips en `events.d/locale.tcl`. De checksum staat in `assets/SHA256SUMS`.
De installer gebruikt deze bestanden rechtstreeks; tijdens herstel is geen
spraak-API of lokale map buiten deze repository nodig.

De originele tekstlijst staat in `nl_NL.tsv`; `make_sounds.py` is de gebruikte
Edge TTS-generator. Dat script opnieuw uitvoeren vereist internet, edge-tts en
SoX en kan een andere stemuitkomst opleveren. Het is geen voorwaarde voor de
installatie. De meegeleverde gegenereerde WAV-bestanden zijn het herstelasset.

Dit pakket is voor de PI3TWE-toepassing samengesteld. Upstream SvxLink en de
bestaande auteursvermeldingen in de Tcl-bestanden behouden hun eigen licentie.
