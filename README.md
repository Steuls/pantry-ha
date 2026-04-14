# Inventory - Home Assistant Custom Integration

A custom Home Assistant integration for tracking food inventory across configurable storage locations (freezer, cupboard, fridge, etc.) while using `pantry-server` as the source of truth.

## Features

- **Server-Backed State** - `pantry-server` owns locations and items
- **Configurable Locations** - Add/remove storage locations via UI
- **Item Tracking** - Track name, quantity, unit, expiry date, category, and notes
- **Expiry Monitoring** - Automatic expired/expiring-soon counts per location
- **Cached Read State** - Last known snapshot survives Home Assistant restarts and temporary backend outages
- **Automation Ready** - Events fired on all inventory changes
- **Native Sidebar UI** - Manage inventory directly in Home Assistant
- **Dashboard Compatible** - Works with existing HA cards

## Installation

### HACS (Recommended)

1. Add this repository as a custom repository in HACS
2. Search for "Inventory" and install
3. Restart Home Assistant

### Manual

1. Copy the `custom_components/inventory/` folder to your Home Assistant `custom_components/` directory
2. Restart Home Assistant

## Setup

1. Go to **Settings** → **Devices & Services**
2. Click **Add Integration** (bottom right)
3. Search for "Inventory" and select it
4. Enter:
   - your `pantry-server` base URL
   - a bearer token with `locations:read`, `locations:write`, `items:read`, and `items:write`
   - polling and timeout settings
5. Submit the form to validate `GET /api/v1/health` and `GET /api/v1/state`

## Managing Locations

After setup, click the **Configure** (gear) button on the integration card:

- **Add Location** - Create a new pantry-server location (e.g., "Freezer", "Cupboard")
- **Manage Location** - Rename or delete existing locations
- **Icon overrides** - The location name lives in `pantry-server`; the optional HA icon remains local

## Home Assistant UI

After installing the integration, a new **Inventory** item appears in the Home Assistant sidebar.

From this panel you can:
- View all configured locations
- See item counts, expired count, and expiring-soon count
- Add new items with quantity/unit/expiry
- Decrement or fully remove items

Location creation/rename/delete still lives under **Settings → Devices & Services → Inventory → Configure**.

## Services

### inventory.add_item

Add an item to a location. If an item with the same name exists, it will update the quantity on the server.

```yaml
service: inventory.add_item
data:
  location: freezer
  name: Milk
  quantity: 2
  unit: litres
  expiry: "2026-04-15"
  category: dairy
  notes: Semi-skimmed
```

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| location | Yes | string | Location ID |
| name | Yes | string | Item name |
| quantity | No | integer | Quantity (default: 1) |
| unit | No | string | Unit of measure |
| expiry | No | string | Expiry date (YYYY-MM-DD) |
| category | No | string | Category for filtering |
| notes | No | string | Additional notes |

### inventory.remove_item

Remove an item or reduce its quantity.

```yaml
service: inventory.remove_item
data:
  location: freezer
  name: Milk
  quantity: 1  # Optional - omit to remove entirely
```

### inventory.update_item

Update specific fields of an existing item.

```yaml
service: inventory.update_item
data:
  location: freezer
  name: Milk
  expiry: "2026-04-20"
  notes: Changed to whole milk
```

### inventory.clear_expired

Remove all expired items from one or all locations.

```yaml
# Clear from specific location
service: inventory.clear_expired
data:
  location: freezer

# Clear from all locations
service: inventory.clear_expired
```

Returns the count of removed items.

### inventory.clear_all

Remove all items from a specific location.

```yaml
service: inventory.clear_all
data:
  location: freezer
```

## Assist

The integration now includes intent handlers for Assist so it can understand:

- `Add chicken to the freezer`
- `Remove yogurt from the fridge`
- `What's in my freezer?`
- `What's expiring soon?`

On startup, the integration automatically writes its Assist sentence file into:

```text
/config/custom_sentences/en/inventory.yaml
```

After installing or upgrading through HACS, restart Home Assistant so Assist reloads the custom sentences. The `inventory.install_assist_sentences` service still exists as a manual fallback if you ever need to force a refresh.

Notes:
- Location matching is done against either the location ID or the location name.
- `add` and `remove` voice commands currently use the default quantity of `1`.
- `what's in ...` reads back up to 5 item names for the matched location.
- `what's expiring soon` works globally or for a specific location.

## Migration

If you previously used the local-only version of this integration, old `.storage` data is preserved for migration.

- Call `inventory.export_local_data` to retrieve the preserved legacy payload from Home Assistant.
- Import that payload into `pantry-server` with the server-side import tooling under `../pantry-server/scripts/`.
- Reconfigure Home Assistant to point at the server URL and token.
- Verify sensors, services, panel behavior, automations, and Assist after the first successful sync.

## Entities

Each location creates a sensor entity:

- **Entity ID**: `sensor.inventory_{location_id}`
- **State**: Number of items in the location
- **Attributes**:
  - `location_id` - Location identifier
  - `location_name` - Display name
  - `items` - Full list of items
  - `item_count` - Total items
  - `expired_count` - Items past expiry
  - `expiring_soon_count` - Items expiring within 7 days
  - `categories` - Unique categories in use

## Events

Events are fired for automation triggers:

| Event | Data |
|-------|------|
| `inventory_item_added` | `location_id`, `location_name`, `item` |
| `inventory_item_removed` | `location_id`, `location_name`, `item_name`, `item`, `reason` |
| `inventory_item_updated` | `location_id`, `location_name`, `item` |
| `inventory_expired_cleared` | `location_id`, `items`, `count` |
| `inventory_all_cleared` | `location_id`, `location_name`, `count` |

### Example Automation

```yaml
automation:
  - alias: "Notify on expired items cleared"
    trigger:
      - event: inventory_expired_cleared
        event_type: custom
        platform: event
    action:
      - service: notify.mobile_app
        data:
          message: "Cleared {{ trigger.event.data.count }} expired items"
```

## Roadmap

- [ ] Custom Lovelace card for rich inventory UI
- [x] Native Assist/voice intents
- [ ] Barcode scanning support
- [ ] Shopping list integration

## License

MIT
