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
    "tiles": [{"entity": "...", "name": "...", "device": {...}}]}]`
    (`name` only when the card sets one; `device` as below)
  - **attributes.ignored**: skipped cards, at most 20
- **Each tile's device** (since 1.2.0): when the tile's entity belongs to a
  device that has other entities, the tile carries them, so the app can
  show the whole appliance behind one tile:
  `"device": {"name": "Washer", "entities": [{"entity": "select.washer_cycle"},
  {"entity": "switch.washer_extra_rinse", "category": "config"}]}`.
  - `name` is the device's name (the one you gave it, else its own).
  - `entities` are in the entity registry's order, at most 40 (a device
    with more is logged once). `category` is present only on
    configuration entities, and is then `"config"`.
  - Left out: the tile's own entity, and every hidden, disabled or
    diagnostic entity.
  - A tile with no device, or whose device has nothing else to show, has
    no `device` key. Apps that predate it ignore the key.
  - `integration` (since 1.3.0): the domain of the device's config entry,
    e.g. `"integration": "acme_cloud"`; left out when it can't be found.
- **Twins** (since 1.3.0): some appliances appear twice in Home Assistant,
  once per integration (a cloud one and a local one, kept side by side so
  each checks the other). The tile's `device` then carries the other
  device as `twins`:
  `"twins": [{"name": "My range", "integration": "acme_cloud", "entities": [...]}]`.
  - A twin has the same model as the tile's device, under a different
    integration. It must be the only device of that model in its
    integration, and the tile's device the only one in its own: two door
    sensors of one model are two doors, and a camera model that a network
    integration lists several times can't be matched to one camera, so
    those give no twins rather than a guess.
  - Each twin's `entities` are filtered and capped like the device's (no
    hidden, disabled or diagnostic ones, `category` only on configuration
    ones, at most 40). A twin with nothing to show is left out; at most 3
    twins are kept, in the device registry's order.
  - No twins, no `twins` key. A device with nothing of its own to show but
    a twin still gives the tile a `device`, with `entities: []`. Apps that
    predate 1.3.0 ignore `integration` and `twins`.
- **Refresh:** on every save of that dashboard, every 5 minutes as a
  backstop, at startup, and when the entity or device registry changes
  (at most once every 10 seconds), so an entity added to, hidden on or
  removed from a device (or a twin) reaches the app.
- **Never empty:** if a read fails (or finds no titled sections), the
  sensor keeps the last good layout and sets `stale: true`; the failure is
  logged once, not on every retry. Only a dashboard that doesn't exist
  clears the layout: the state is then `unknown` and the attributes are
  just `source`, `stale` and `missing: true`.

The dashboard is read in-process from Home Assistant's Lovelace storage
(no token, no websocket). That storage is internal to Home Assistant, so
an upgrade could change it; when that happens the sensor goes stale rather
than empty.

The layout attributes aren't recorded in history, so a dashboard of many
devices (tens of KB) never meets the recorder's 16 KB attribute limit.

## Changelog

- **1.3.0**: a tile's `device` names its `integration` (the config entry's
  domain) and carries `twins`: the same appliance through another
  integration (same model, one device of it on each side), each with its
  name, integration and entities, filtered and capped like the device's,
  at most 3. Older app builds ignore the new keys.
- **1.2.0**: each tile of `sensor.gramtrack_home_layout` carries its
  device's other entities as `device` (name, and entities with
  `category: "config"` on configuration ones), leaving out the tile's own
  entity and hidden, disabled and diagnostic ones, at most 40 a device.
  The layout also refreshes when the entity or device registry changes.
  Older app builds ignore the new key.
- **1.1.0**: `sensor.gramtrack_home_layout`, the app's Home tiles from a
  dashboard named in Options.
- **1.0.0**: `sensor.gramtrack`, the entities picked for the app's sensor
  strip.

## License

[MIT](LICENSE)
