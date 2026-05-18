# GramTrack — Home Assistant Integration

Companion Home Assistant integration for the **GramTrack** iOS app. It lets
you choose, from Home Assistant's native UI, which entities appear in the
app's Home-screen sensor strip — the same kind of multi-select entity
picker the HomeKit integration uses.

The integration publishes a single entity, `sensor.gramtrack`, whose
attributes list the entity IDs you selected. The GramTrack app reads that
through Home Assistant's normal `/api/states` endpoint and renders a chip
for each one (mixed domains are fine — weather, binary sensors, climate,
locks, switches, etc.).

## Install (HACS)

1. In HACS, open the menu (⋮) → **Custom repositories**.
2. Add `https://github.com/Lukejb14/ha-gramtrack` with category
   **Integration**, then **Add**.
3. Search HACS for **GramTrack**, **Download**, and **restart Home
   Assistant**.
4. Go to **Settings → Devices & Services → Add Integration → GramTrack**
   and pick the entities you want in the app.

To change the selection later: open the **GramTrack** integration →
**Configure**. No restart needed.

## Manual install

Copy `custom_components/gramtrack/` into your Home Assistant
`config/custom_components/` directory and restart Home Assistant, then add
the integration as in step 4 above.

## How it works

- `config_flow` / `options_flow` present a native
  `EntitySelector(multiple=True)` — any entities, any domains.
- The selection is stored on the config entry and exposed as
  `sensor.gramtrack`:
  - **state**: number of selected entities
  - **attributes.entities**: the chosen entity IDs (canonical)
  - **attributes.entity_id**: the same list (mirrored for app
    compatibility)
- The GramTrack iOS app reads `sensor.gramtrack` and builds the Home-screen
  sensor strip from it. If the entity is absent, the app falls back to its
  built-in default sensors.

## License

[MIT](LICENSE)
