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

  _mapLocations(states) {
    return Object.entries(states)
      .filter(([entityId]) => entityId.startsWith('sensor.inventory_'))
      .map(([entityId, state]) => {
        const attrs = state.attributes || {};
        return {
          entityId,
          locationId: attrs.location_id,
          name: attrs.location_name || entityId,
          icon: attrs.icon || 'mdi:package-variant',
          items: Array.isArray(attrs.items) ? [...attrs.items] : [],
          count: Number(state.state || 0),
          expiredCount: attrs.expired_count || 0,
          expiringSoonCount: attrs.expiring_soon_count || 0,
        };
      })
      .sort((a, b) => a.name.localeCompare(b.name));
  }

  async _readStates(forceFetch = false) {
    if (!this._hass) return;

    if (!forceFetch) {
      return this._mapLocations(this._hass.states);
    }

    const states = await this._hass.callWS({ type: 'get_states' });
    const mappedStates = Object.fromEntries(
      states.map((state) => [state.entity_id, state])
    );
    return this._mapLocations(mappedStates);
  }

  async _loadLocations(forceFetch = false) {
    if (!this._hass) return;

    const entities = await this._readStates(forceFetch);
    if (!entities) return;

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

  _escapeHtml(value) {
    return String(value ?? '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#39;');
  }

  _formatMeta(item) {
    const parts = [];
    const quantity = item.quantity || 1;
    parts.push(`${quantity}${item.unit ? ` ${item.unit}` : ''}`);
    if (item.category) parts.push(item.category);
    if (item.expiry) parts.push(`Expires ${item.expiry}`);
    return parts.join(' • ');
  }

  _getExpiryTone(item) {
    if (!item.expiry) return 'normal';
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const expiry = new Date(`${item.expiry}T00:00:00`);
    if (Number.isNaN(expiry.getTime())) return 'normal';

    const diffDays = Math.round((expiry - today) / 86400000);
    if (diffDays < 0) return 'expired';
    if (diffDays <= 7) return 'soon';
    return 'normal';
  }

  _renderItems(location) {
    if (location.items.length === 0) {
      return `
        <div class="empty-state">
          <div class="empty-state__title">Nothing here yet</div>
          <div class="empty-state__body">Use Assist or the form above to add your first item.</div>
        </div>
      `;
    }

    return location.items.map((item) => {
      const tone = this._getExpiryTone(item);
      const toneLabel = tone === 'expired'
        ? 'Expired'
        : tone === 'soon'
          ? 'Soon'
          : 'Fresh';

      return `
        <div class="item-card item-card--${tone}">
          <div class="item-main">
            <div class="item-title-row">
              <strong class="item-title">${this._escapeHtml(item.name)}</strong>
              <span class="status-pill status-pill--${tone}">${toneLabel}</span>
            </div>
            <div class="item-meta">${this._escapeHtml(this._formatMeta(item))}</div>
            ${item.notes ? `<div class="item-notes">${this._escapeHtml(item.notes)}</div>` : ''}
          </div>
          <div class="item-actions">
            <button class="button button--soft" data-action="minus" data-name="${this._escapeHtml(item.name)}">Use 1</button>
            <button class="button button--danger" data-action="remove" data-name="${this._escapeHtml(item.name)}">Remove</button>
          </div>
        </div>
      `;
    }).join('');
  }

  _render() {
    const location = this._getCurrentLocation();

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          min-height: 100%;
          padding: 24px;
          color: var(--primary-text-color);
          background:
            radial-gradient(circle at top left, rgba(47, 128, 237, 0.12), transparent 30%),
            radial-gradient(circle at top right, rgba(39, 174, 96, 0.12), transparent 24%),
            linear-gradient(180deg, rgba(255,255,255,0.02), rgba(0,0,0,0.03));
          box-sizing: border-box;
        }
        * { box-sizing: border-box; }
        .shell {
          max-width: 1100px;
          margin: 0 auto;
          display: grid;
          gap: 18px;
        }
        .hero {
          display: grid;
          gap: 16px;
          padding: 24px;
          border-radius: 24px;
          background:
            linear-gradient(135deg, rgba(20, 90, 160, 0.92), rgba(18, 58, 92, 0.95)),
            var(--card-background-color);
          color: white;
          box-shadow: 0 18px 40px rgba(5, 23, 40, 0.22);
        }
        .hero-top {
          display: flex;
          gap: 12px;
          align-items: center;
          justify-content: space-between;
          flex-wrap: wrap;
        }
        .hero-copy h1 {
          margin: 0;
          font-size: 2rem;
          line-height: 1;
          letter-spacing: -0.04em;
        }
        .hero-copy p {
          margin: 6px 0 0;
          color: rgba(255, 255, 255, 0.78);
          max-width: 48rem;
        }
        .hero-actions {
          display: flex;
          gap: 10px;
          align-items: center;
          flex-wrap: wrap;
        }
        .select-wrap {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          padding: 10px 14px;
          border-radius: 999px;
          background: rgba(255, 255, 255, 0.12);
          backdrop-filter: blur(8px);
        }
        .select-wrap label {
          font-size: 0.82rem;
          text-transform: uppercase;
          letter-spacing: 0.08em;
          color: rgba(255, 255, 255, 0.75);
        }
        .select-wrap select {
          min-width: 160px;
          border: 0;
          outline: none;
          background: transparent;
          color: white;
          font: inherit;
        }
        .select-wrap option {
          color: var(--primary-text-color);
        }
        .stats-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
          gap: 12px;
        }
        .stat {
          padding: 16px;
          border-radius: 18px;
          background: rgba(255, 255, 255, 0.1);
          border: 1px solid rgba(255, 255, 255, 0.08);
        }
        .stat__label {
          display: block;
          font-size: 0.8rem;
          text-transform: uppercase;
          letter-spacing: 0.08em;
          color: rgba(255, 255, 255, 0.7);
        }
        .stat__value {
          display: block;
          margin-top: 8px;
          font-size: 2rem;
          font-weight: 700;
          letter-spacing: -0.04em;
        }
        .content-grid {
          display: grid;
          grid-template-columns: minmax(280px, 360px) minmax(0, 1fr);
          gap: 18px;
          align-items: start;
        }
        .card {
          background: var(--card-background-color);
          border: 1px solid color-mix(in srgb, var(--divider-color) 85%, transparent);
          border-radius: 22px;
          padding: 20px;
          box-shadow: 0 10px 24px rgba(15, 23, 42, 0.06);
        }
        .card h2, .card h3 {
          margin: 0 0 14px;
          letter-spacing: -0.03em;
        }
        .card-head {
          display: flex;
          justify-content: space-between;
          align-items: baseline;
          gap: 12px;
          margin-bottom: 14px;
        }
        .muted {
          color: var(--secondary-text-color);
        }
        .form-grid {
          display: grid;
          gap: 12px;
        }
        .field {
          display: grid;
          gap: 6px;
        }
        .field--split {
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 12px;
        }
        .field label {
          font-size: 0.82rem;
          font-weight: 600;
          color: var(--secondary-text-color);
        }
        input, select, button {
          font: inherit;
        }
        input, select {
          width: 100%;
          padding: 12px 14px;
          border-radius: 14px;
          border: 1px solid var(--divider-color);
          background: color-mix(in srgb, var(--card-background-color) 88%, black 2%);
          color: var(--primary-text-color);
        }
        input:focus, select:focus {
          outline: 2px solid rgba(47, 128, 237, 0.22);
          border-color: rgba(47, 128, 237, 0.48);
        }
        .button {
          border: 0;
          border-radius: 999px;
          padding: 10px 14px;
          cursor: pointer;
          transition: transform 120ms ease, opacity 120ms ease, background 120ms ease;
        }
        .button:hover {
          transform: translateY(-1px);
        }
        .button--primary {
          color: white;
          background: linear-gradient(135deg, #2f80ed, #1f6fd6);
        }
        .button--ghost {
          color: white;
          background: rgba(255, 255, 255, 0.14);
          border: 1px solid rgba(255, 255, 255, 0.1);
        }
        .button--soft {
          color: var(--primary-text-color);
          background: color-mix(in srgb, var(--primary-color) 10%, var(--card-background-color));
          border: 1px solid color-mix(in srgb, var(--primary-color) 18%, transparent);
        }
        .button--danger {
          color: #9b1c1c;
          background: rgba(217, 48, 37, 0.1);
          border: 1px solid rgba(217, 48, 37, 0.16);
        }
        .button--block {
          width: 100%;
          justify-content: center;
        }
        .item-list {
          display: grid;
          gap: 12px;
        }
        .item-card {
          display: grid;
          grid-template-columns: minmax(0, 1fr) auto;
          gap: 16px;
          align-items: center;
          padding: 16px;
          border-radius: 18px;
          border: 1px solid var(--divider-color);
          background: linear-gradient(180deg, rgba(255,255,255,0.04), rgba(255,255,255,0.01));
        }
        .item-card--soon {
          border-color: rgba(221, 107, 32, 0.28);
          background: linear-gradient(180deg, rgba(221, 107, 32, 0.08), rgba(255,255,255,0.01));
        }
        .item-card--expired {
          border-color: rgba(217, 48, 37, 0.26);
          background: linear-gradient(180deg, rgba(217, 48, 37, 0.08), rgba(255,255,255,0.01));
        }
        .item-title-row {
          display: flex;
          gap: 10px;
          align-items: center;
          flex-wrap: wrap;
        }
        .item-title {
          font-size: 1rem;
          letter-spacing: -0.02em;
        }
        .item-meta {
          margin-top: 6px;
          color: var(--secondary-text-color);
        }
        .item-notes {
          margin-top: 10px;
          font-size: 0.92rem;
          color: var(--primary-text-color);
        }
        .status-pill {
          display: inline-flex;
          align-items: center;
          padding: 4px 10px;
          border-radius: 999px;
          font-size: 0.78rem;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          background: rgba(39, 174, 96, 0.1);
          color: #1e7b43;
        }
        .status-pill--soon {
          background: rgba(221, 107, 32, 0.12);
          color: #b45309;
        }
        .status-pill--expired {
          background: rgba(217, 48, 37, 0.12);
          color: #b42318;
        }
        .item-actions {
          display: flex;
          gap: 8px;
          align-items: center;
          flex-wrap: wrap;
        }
        .empty-state {
          padding: 28px 18px;
          border-radius: 18px;
          border: 1px dashed var(--divider-color);
          text-align: center;
          background: linear-gradient(180deg, rgba(47, 128, 237, 0.04), transparent);
        }
        .empty-state__title {
          font-size: 1.05rem;
          font-weight: 700;
          letter-spacing: -0.02em;
        }
        .empty-state__body {
          margin-top: 8px;
          color: var(--secondary-text-color);
        }
        @media (max-width: 900px) {
          :host { padding: 16px; }
          .content-grid { grid-template-columns: 1fr; }
          .item-card { grid-template-columns: 1fr; }
        }
        @media (max-width: 640px) {
          .hero { padding: 18px; border-radius: 20px; }
          .hero-copy h1 { font-size: 1.6rem; }
          .field--split { grid-template-columns: 1fr; }
          .item-actions { width: 100%; }
          .item-actions .button { flex: 1; }
        }
      </style>

      <div class="shell">
        <section class="hero">
          <div class="hero-top">
            <div class="hero-copy">
              <h1>Inventory</h1>
              <p>${location ? `Track what is in ${this._escapeHtml(location.name)} and update it quickly from one place.` : 'Track pantry, fridge, and freezer stock in one place.'}</p>
            </div>
            <div class="hero-actions">
              <div class="select-wrap">
                <label for="location">Location</label>
                <select id="location">
                  ${this._locations.map((loc) => `<option value="${loc.locationId}" ${loc.locationId === this._selectedLocation ? 'selected' : ''}>${this._escapeHtml(loc.name)}</option>`).join('')}
                </select>
              </div>
              <button class="button button--ghost" id="refresh">Refresh</button>
            </div>
          </div>
          ${location ? `
            <div class="stats-grid">
              <div class="stat">
                <span class="stat__label">Items</span>
                <span class="stat__value">${location.count}</span>
              </div>
              <div class="stat">
                <span class="stat__label">Expired</span>
                <span class="stat__value">${location.expiredCount}</span>
              </div>
              <div class="stat">
                <span class="stat__label">Expiring Soon</span>
                <span class="stat__value">${location.expiringSoonCount}</span>
              </div>
            </div>
          ` : '<p class="muted">No locations found. Add one in integration options.</p>'}
        </section>

        <div class="content-grid">
          <section class="card">
            <h3>Quick Add</h3>
            ${location ? `
              <div class="form-grid">
                <div class="field">
                  <label for="name">Item name</label>
                  <input id="name" placeholder="Chicken breast" />
                </div>
                <div class="field field--split">
                  <div class="field">
                    <label for="qty">Quantity</label>
                    <input id="qty" type="number" min="1" value="1" />
                  </div>
                  <div class="field">
                    <label for="unit">Unit</label>
                    <input id="unit" placeholder="packs" />
                  </div>
                </div>
                <div class="field">
                  <label for="expiry">Expiry date</label>
                  <input id="expiry" type="date" />
                </div>
                <button class="button button--primary button--block" id="add">Add item</button>
              </div>
            ` : `
              <div class="empty-state">
                <div class="empty-state__title">No location selected</div>
                <div class="empty-state__body">Add a freezer, fridge, or cupboard in the integration settings first.</div>
              </div>
            `}
          </section>

          <section class="card">
            <div class="card-head">
              <h3>${location ? `${this._escapeHtml(location.name)} items` : 'Items'}</h3>
              ${location ? `<span class="muted">${location.items.length} visible</span>` : ''}
            </div>
            ${location ? `<div class="item-list">${this._renderItems(location)}</div>` : ''}
          </section>
        </div>
      </div>
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
      refreshButton.addEventListener('click', () => this._loadLocations(true));
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
        await this._loadLocations(true);
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
        await this._loadLocations(true);
      });
    });
  }
}

customElements.define('inventory-panel', InventoryPanel);
