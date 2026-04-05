Design Overview: Home Assistant Inventory Integration

---

## Overview

A custom Home Assistant integration for tracking food inventory across configurable storage locations (freezer, cupboard, fridge, etc.).

### Core Features (v1)

1. **Configurable Locations** - Users add/remove storage locations via UI config flow
2. **List Entities** - Each location is a sensor with item count as state, full list in attributes
3. **HA Services** - `inventory.add_item`, `inventory.remove_item`, `inventory.update_item`, `inventory.clear_expired`
4. **Persistence** - Data stored in HA's storage layer (survives restarts)
5. **Expiry Tracking** - Each item has name, quantity, unit, expiry date, category, notes
6. **Categories** - Optional category field for filtering/grouping (dairy, meat, vegetables, etc.)
7. **Dashboard Ready** - Works with existing HA cards (markdown, entities, custom:auto-entities)

### Future Features (Phase 2+)

- Custom Lovelace card for rich inventory UI
- Native Assist/voice intents for hands-free management
- Barcode scanning webhook/service
- Shopping list integration

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    HOME ASSISTANT                        │
├─────────────────────────────────────────────────────────┤
│  custom_components/inventory/                            │
│  ├── __init__.py          # Integration setup             │
│  ├── config_flow.py       # UI setup + location mgmt      │
│  ├── const.py             # Constants                     │
│  ├── sensor.py            # Dynamic entities per location  │
│  ├── services.py          # add/remove/update/clear       │
│  ├── storage.py           # Data persistence               │
│  └── strings.json         # UI translations               │
├─────────────────────────────────────────────────────────┤
│  ENTITIES (dynamic, one per location)                    │
│  └── sensor.inventory_{location_id}                      │
│      # State: item count                                 │
│      # Attributes: items list, location name             │
├─────────────────────────────────────────────────────────┤
│  SERVICES                                                │
│  ├── inventory.add_item(location, name, qty, unit,       │
│  │                       expiry, category, notes)        │
│  ├── inventory.remove_item(location, name)               │
│  ├── inventory.update_item(location, name, **kwargs)     │
│  └── inventory.clear_expired(location)                   │
└─────────────────────────────────────────────────────────┘
```

---

## Data Model

### Location (stored in config entry)

```json
{
  "id": "freezer",
  "name": "Freezer",
  "icon": "mdi:fridge-top"
}
```

### Item

```json
{
  "name": "Milk",
  "quantity": 2,
  "unit": "litres",
  "expiry": "2026-04-15",
  "added": "2026-04-05",
  "category": "dairy",
  "notes": "Semi-skimmed"
}
```

### Storage Schema

```json
{
  "locations": {
    "freezer": {
      "items": [
        {"name": "Milk", "quantity": 2, ...}
      ]
    },
    "cupboard": {
      "items": [...]
    }
  }
}
```

---

## Config Flow

### Initial Setup

1. User adds integration via HA Settings → Devices & Services
2. User provides first location name (e.g., "Freezer")
3. Integration creates config entry + sensor entity

### Managing Locations

Via Options Flow (gear icon on integration):

1. View existing locations
2. Add new location (name + icon picker)
3. Delete location (with confirmation, clears all items)
4. Rename location (preserves items)

### Config Entry Structure

```python
# Config entry data (setup)
{
  "location_id": "freezer",  # unique slug
  "location_name": "Freezer",
  "icon": "mdi:fridge-top"
}

# Options (per-entry, for modifying)
# Note: Multiple locations = multiple config entries
# OR: Single config entry with options storing all locations
```

**Decision:** Use single config entry with options storing all locations. Simpler UX.

---

## Services

### inventory.add_item

```yaml
service: inventory.add_item
data:
  location: freezer          # required - location id
  name: Milk                 # required - item name
  quantity: 2                 # optional - default 1
  unit: litres                # optional
  expiry: "2026-04-15"        # optional - YYYY-MM-DD
  category: dairy             # optional
  notes: Semi-skimmed         # optional
```

### inventory.remove_item

```yaml
service: inventory.remove_item
data:
  location: freezer           # required
  name: Milk                  # required - exact match
  quantity: 1                 # optional - reduce by qty, remove if 0
```

**Behavior:**
- If quantity not specified or matches current qty: remove item entirely
- If quantity specified and < current qty: reduce quantity
- If quantity specified and >= current qty: remove item entirely

### inventory.update_item

```yaml
service: inventory.update_item
data:
  location: freezer           # required
  name: Milk                  # required - item to update
  quantity: 3                 # optional - new quantity
  unit: gallons               # optional - new unit
  expiry: "2026-04-20"        # optional - new expiry
  category: dairy             # optional
  notes: Whole milk           # optional
```

### inventory.clear_expired

```yaml
service: inventory.clear_expired
data:
  location: freezer           # optional - omit to clear all locations
```

Returns notification with count and list of removed items.

### inventory.clear_all

```yaml
service: inventory.clear_all
data:
  location: freezer           # required - safety, must be explicit
```

---

## Entity Attributes

```python
# sensor.inventory_freezer
state: 5  # item count

attributes:
  location_id: freezer
  location_name: Freezer
  items:
    - name: Milk
      quantity: 2
      unit: litres
      expiry: "2026-04-15"
      category: dairy
      added: "2026-04-05"
      notes: Semi-skimmed
    - ...
  expired_count: 1  # items past expiry
  expiring_soon_count: 2  # items expiring within 7 days
  categories:
    - dairy
    - meat
```

---

## Events

The integration fires events for automation triggers:

```yaml
# Event: inventory_item_added
event_type: inventory_item_added
data:
  location_id: freezer
  location_name: Freezer
  item:
    name: Milk
    quantity: 2
    ...

# Event: inventory_item_removed
event_type: inventory_item_removed
data:
  location_id: freezer
  item_name: Milk
  reason: user_action | expired | cleared

# Event: inventory_expired
event_type: inventory_expired
data:
  location_id: freezer
  items:
    - {name: Yogurt, quantity: 1, expiry: "2026-04-01"}
```

---

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Add duplicate item name | Update existing item (merge) |
| Remove non-existent item | Log warning, no error raised |
| Invalid location | Raise ServiceValidationError |
| Invalid expiry format | Raise ServiceValidationError |
| Negative quantity | Raise ServiceValidationError |

---

## File Structure

```
custom_components/inventory/
├── __init__.py          # async_setup_entry, async_unload_entry
├── config_flow.py       # Setup wizard + options flow
├── const.py             # DOMAIN, defaults, keys
├── sensor.py            # InventorySensor class
├── services.py          # Service handlers
├── storage.py           # InventoryStorage helper
├── manifest.json        # Integration metadata
└── strings.json         # UI strings (en)
```

---

## Storage Implementation

Use HA's built-in storage API (`homeassistant.helpers.storage`):

```python
from homeassistant.helpers.storage import Store

STORAGE_VERSION = 1
STORAGE_KEY = "inventory"

class InventoryStorage:
    def __init__(self, hass):
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._data = None

    async def async_load(self):
        self._data = await self._store.async_load() or {"locations": {}}
        return self._data

    async def async_save(self):
        await self._store.async_save(self._data)
```

---

## Manifest

```json
{
  "domain": "inventory",
  "name": "Inventory",
  "version": "1.0.0",
  "documentation": "https://github.com/user/pantry-ha",
  "requirements": [],
  "dependencies": [],
  "codeowners": ["@user"],
  "config_flow": true,
  "iot_class": "local_polling"
}
```

---

## Implementation Order

1. **Setup** - `manifest.json`, `const.py`, `__init__.py`
2. **Storage** - `storage.py` with load/save
3. **Config Flow** - `config_flow.py`, `strings.json` (minimal: just name entry)
4. **Sensor** - `sensor.py` (single location entity)
5. **Services** - `services.py` with add/remove
6. **Options Flow** - Add/remove locations in UI
7. **Events** - Fire events on changes
8. **Polish** - Error handling, validation, edge cases

---

## Testing Checklist

- [ ] Add integration via UI
- [ ] Add/remove locations via options
- [ ] Add item via service call
- [ ] Remove item (partial and full)
- [ ] Update item fields
- [ ] Clear expired items
- [ ] Verify persistence after HA restart
- [ ] Check entity attributes in developer tools
- [ ] Test automations on events
- [ ] Invalid inputs show proper errors

---

## Future Phases

### Phase 2: Custom Lovelace Card

- Table view with sorting/filtering
- Category filter dropdown
- Expiry highlighting (red/yellow/green)
- Quick add/remove buttons
- Per-location card or tabbed interface

### Phase 3: Assist Intents

```yaml
# Example voice commands
"Add milk to the freezer"
"What's in my freezer?"
"Remove yogurt from cupboard"
"What's expiring soon?"
```

Requires:
- `sentences/en/inventory.yaml` - Intent definitions
- Intent handlers in `__init__.py`

### Phase 4: Advanced Features

- Barcode lookup service
- Shopping list integration (add to shopping list when removed/expired)
- Import/export JSON
- Low stock threshold alerts
