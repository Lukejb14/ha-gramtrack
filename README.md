# GramTrack — Home Assistant Integration

Companion Home Assistant integration for the **GramTrack** iOS app. It lets
you choose, from Home Assistant's native UI, which entities appear in the
app's Home-screen sensor strip — the same kind of multi-select entity
picker the HomeKit integration uses.

The integration publishes `sensor.gramtrack`, whose attributes list the
entity IDs you selected (and, optionally, `sensor.gramtrack_home_layout`;
see [Home layout from a dashboard](#home-layout-from-a-dashboard)). The GramTrack app reads that
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

## Home layout from a dashboard

Optionally, the app's Home tiles can follow a Lovelace dashboard: arrange
tile cards in the dashboard editor (drag and drop) and the app shows those
tiles, in that order, in those buildings, on its next refresh.

- **Field:** *Home layout dashboard (url path)*, at setup or under
  **Configure**. Enter the dashboard's url path (the part of its address
  after the first slash). Leave it empty to turn the feature off.
- **Dashboard shape:** the first view, of type *sections*. Each section is
  a building, named by its title or, as the editor writes it, by the
  section's heading card. Only `tile` cards with an `entity` count; a
  card's `name` overrides the tile name. Other card types, and any card
  with a `visibility` condition, are skipped and listed under `ignored`.
- **Sensor:** `sensor.gramtrack_home_layout`
  - **state**: when the tiles last changed (ISO 8601, UTC)
  - **attributes.source**: the dashboard's url path
  - **attributes.version**: counts layout changes since Home Assistant
    started (informational)
  - **attributes.last_changed**: same as the state
  - **attributes.stale**: `true` when the latest read failed
  - **attributes.buildings**: `[{"id": "<section title, lowercased>",
    "tiles": [{"entity": "...", "name": "..."}]}]` (`name` only when the
    card sets one)
  - **attributes.ignored**: skipped cards, at most 20
- **Refresh:** on every save of that dashboard, every 5 minutes as a
  backstop, and at startup.
- **Never empty:** if a read fails (or finds no titled sections), the
  sensor keeps the last good layout and sets `stale: true`; the failure is
  logged once, not on every retry. Only a dashboard that doesn't exist
  clears the layout: the state is then `unknown` and the attributes are
  just `source`, `stale` and `missing: true`.

The dashboard is read in-process from Home Assistant's Lovelace storage
(no token, no websocket). That storage is internal to Home Assistant, so
an upgrade could change it; when that happens the sensor goes stale rather
than empty.

## License

[MIT](LICENSE)
