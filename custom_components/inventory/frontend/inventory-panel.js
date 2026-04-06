class InventoryPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._locations = [];
    this._selectedLocation = '';
  }

  set hass(hass) {
    this._hass = hass;
    this._loadLocations();
    this._render();
  }

  async _loadLocations() {
    if (!this._hass) return;

    const entities = Object.entries(this._hass.states)
      .filter(([entityId]) => entityId.startsWith('sensor.inventory_'))
      .map(([entityId, state]) => {
        const attrs = state.attributes || {};
        return {
          entityId,
          locationId: attrs.location_id,
          name: attrs.location_name || entityId,
          icon: attrs.icon || 'mdi:package-variant',
          items: attrs.items || [],
          count: Number(state.state || 0),
          expiredCount: attrs.expired_count || 0,
          expiringSoonCount: attrs.expiring_soon_count || 0,
        };
      })
      .sort((a, b) => a.name.localeCompare(b.name));

    this._locations = entities;
    if (!this._selectedLocation && entities.length > 0) {
      this._selectedLocation = entities[0].locationId;
    }
    this._render();
  }

  _getCurrentLocation() {
    return this._locations.find((loc) => loc.locationId === this._selectedLocation) || null;
  }

  async _callService(service, data) {
    await this._hass.callService('inventory', service, data);
  }

  _render() {
    const location = this._getCurrentLocation();

    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; padding: 16px; }
        .card { background: var(--card-background-color); border-radius: 12px; padding: 16px; margin-bottom: 16px; box-shadow: var(--ha-card-box-shadow, none); }
        .row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
        .stats { display: flex; gap: 16px; margin-top: 8px; color: var(--secondary-text-color); }
        .item { display: grid; grid-template-columns: 1fr auto auto; gap: 8px; align-items: center; padding: 8px 0; border-bottom: 1px solid var(--divider-color); }
        .muted { color: var(--secondary-text-color); }
        button { border: 1px solid var(--divider-color); background: transparent; color: var(--primary-text-color); border-radius: 8px; padding: 6px 10px; cursor: pointer; }
        input, select { padding: 8px; border-radius: 8px; border: 1px solid var(--divider-color); background: var(--card-background-color); color: var(--primary-text-color); }
      </style>

      <div class="card">
        <h2>Inventory</h2>
        <div class="row">
          <label for="location">Location</label>
          <select id="location">
            ${this._locations.map((loc) => `<option value="${loc.locationId}" ${loc.locationId === this._selectedLocation ? 'selected' : ''}>${loc.name}</option>`).join('')}
          </select>
          <button id="refresh">Refresh</button>
        </div>
        ${location ? `
          <div class="stats">
            <span>Items: <strong>${location.count}</strong></span>
            <span>Expired: <strong>${location.expiredCount}</strong></span>
            <span>Expiring soon: <strong>${location.expiringSoonCount}</strong></span>
          </div>
        ` : '<p class="muted">No locations found. Add one in integration options.</p>'}
      </div>

      ${location ? `
      <div class="card">
        <h3>Add item</h3>
        <div class="row">
          <input id="name" placeholder="Name" />
          <input id="qty" type="number" min="1" value="1" style="width:90px" />
          <input id="unit" placeholder="Unit" style="width:100px" />
          <input id="expiry" type="date" />
          <button id="add">Add</button>
        </div>
      </div>

      <div class="card">
        <h3>Items</h3>
        ${location.items.length === 0 ? '<p class="muted">No items yet.</p>' : location.items.map((item) => `
          <div class="item">
            <div>
              <strong>${item.name}</strong>
              <div class="muted">${item.quantity || 1}${item.unit ? ` ${item.unit}` : ''}${item.expiry ? ` • Expires ${item.expiry}` : ''}</div>
            </div>
            <button data-action="minus" data-name="${item.name}">-1</button>
            <button data-action="remove" data-name="${item.name}">Remove</button>
          </div>
        `).join('')}
      </div>
      ` : ''}
    `;

    const locationSelect = this.shadowRoot.getElementById('location');
    if (locationSelect) {
      locationSelect.addEventListener('change', (ev) => {
        this._selectedLocation = ev.target.value;
        this._render();
      });
    }

    const refreshButton = this.shadowRoot.getElementById('refresh');
    if (refreshButton) {
      refreshButton.addEventListener('click', () => this._loadLocations());
    }

    const addButton = this.shadowRoot.getElementById('add');
    if (addButton && location) {
      addButton.addEventListener('click', async () => {
        const name = this.shadowRoot.getElementById('name').value.trim();
        const quantity = Number(this.shadowRoot.getElementById('qty').value || 1);
        const unit = this.shadowRoot.getElementById('unit').value.trim();
        const expiry = this.shadowRoot.getElementById('expiry').value;
        if (!name) return;
        await this._callService('add_item', {
          location: location.locationId,
          name,
          quantity,
          ...(unit ? { unit } : {}),
          ...(expiry ? { expiry } : {}),
        });
        await this._loadLocations();
      });
    }

    this.shadowRoot.querySelectorAll('button[data-action]').forEach((button) => {
      button.addEventListener('click', async () => {
        const name = button.getAttribute('data-name');
        const action = button.getAttribute('data-action');
        if (!location || !name) return;
        if (action === 'minus') {
          await this._callService('remove_item', { location: location.locationId, name, quantity: 1 });
        } else {
          await this._callService('remove_item', { location: location.locationId, name });
        }
        await this._loadLocations();
      });
    });
  }
}

customElements.define('inventory-panel', InventoryPanel);
