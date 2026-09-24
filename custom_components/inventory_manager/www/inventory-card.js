/* Inventory Manager card
 * Vanilla custom element, no build step, no external deps.
 * Talks to the integration purely over hass.callWS().
 */

const DOMAIN = "inventory_manager";

class InventoryCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._data = { locations: [], items: [], expiry_warning_days: 7 };
    this._activeLocation = null;
    this._showAddForm = false;
    this._unsubEvents = null;
    this._initialized = false;
  }

  setConfig(config) {
    this._config = config || {};
  }

  getCardSize() {
    return 6;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._initialized) {
      this._initialized = true;
      this._init();
    }
  }

  async _init() {
    await this._fetchData();
    this._render();
    if (this._hass.connection && !this._unsubEvents) {
      this._unsubEvents = await this._hass.connection.subscribeEvents(
        () => this._fetchData().then(() => this._render()),
        `${DOMAIN}_item_updated`
      );
    }
  }

  disconnectedCallback() {
    if (this._unsubEvents) {
      this._unsubEvents();
      this._unsubEvents = null;
    }
  }

  async _fetchData() {
    try {
      this._data = await this._hass.callWS({ type: `${DOMAIN}/get_data` });
      if (!this._activeLocation && this._data.locations.length) {
        this._activeLocation = this._data.locations[0];
      }
    } catch (err) {
      console.error("inventory-card: failed to load data", err);
    }
  }

  async _call(type, payload) {
    await this._hass.callWS({ type: `${DOMAIN}/${type}`, ...payload });
    await this._fetchData();
    this._render();
  }

  _daysUntil(dateStr) {
    if (!dateStr) return null;
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const target = new Date(dateStr);
    return Math.round((target - today) / 86400000);
  }

  _itemStatus(item) {
    const days = this._daysUntil(item.expiration);
    const lowStock =
      item.threshold !== null &&
      item.threshold !== undefined &&
      item.quantity <= item.threshold;
    let expiryClass = "";
    if (days !== null) {
      if (days < 0) expiryClass = "expired";
      else if (days <= this._data.expiry_warning_days) expiryClass = "expiring";
    }
    return { lowStock, expiryClass, days };
  }

  _render() {
    const root = this.shadowRoot;
    root.innerHTML = "";

    const style = document.createElement("style");
    style.textContent = CSS;
    root.appendChild(style);

    const card = document.createElement("ha-card");
    card.header = this._config.title || "Inventár";

    const content = document.createElement("div");
    content.className = "card-content";

    content.appendChild(this._renderTabs());
    content.appendChild(this._renderSummary());
    content.appendChild(this._renderItemList());
    content.appendChild(this._renderAddForm());

    card.appendChild(content);
    root.appendChild(card);
  }

  _renderTabs() {
    const tabs = document.createElement("div");
    tabs.className = "tabs";

    this._data.locations.forEach((loc) => {
      const tab = document.createElement("button");
      tab.className = "tab" + (loc === this._activeLocation ? " active" : "");
      tab.textContent = loc;
      tab.addEventListener("click", () => {
        this._activeLocation = loc;
        this._render();
      });
      tabs.appendChild(tab);
    });

    const addLocBtn = document.createElement("button");
    addLocBtn.className = "tab add-location";
    addLocBtn.title = "Pridať miestnosť";
    addLocBtn.textContent = "+";
    addLocBtn.addEventListener("click", () => this._promptAddLocation());
    tabs.appendChild(addLocBtn);

    return tabs;
  }

  async _promptAddLocation() {
    const name = prompt("Názov novej miestnosti:");
    if (name && name.trim()) {
      await this._call("add_location", { name: name.trim() });
      this._activeLocation = name.trim();
      this._render();
    }
  }

  _renderSummary() {
    const wrap = document.createElement("div");
    wrap.className = "summary";

    const items = this._data.items.filter(
      (i) => i.location === this._activeLocation
    );
    const lowStock = items.filter((i) => this._itemStatus(i).lowStock).length;
    const expiring = items.filter(
      (i) => this._itemStatus(i).expiryClass !== ""
    ).length;

    wrap.innerHTML = `
      <span class="pill">${items.length} položiek</span>
      ${lowStock ? `<span class="pill warn">⚠ ${lowStock} nízky stav</span>` : ""}
      ${expiring ? `<span class="pill danger">⏰ ${expiring} exspirácia</span>` : ""}
    `;
    return wrap;
  }

  _renderItemList() {
    const list = document.createElement("div");
    list.className = "item-list";

    const items = this._data.items
      .filter((i) => i.location === this._activeLocation)
      .sort((a, b) => a.name.localeCompare(b.name));

    if (items.length === 0) {
      const empty = document.createElement("div");
      empty.className = "empty";
      empty.textContent = "Zatiaľ žiadne položky v tejto miestnosti.";
      list.appendChild(empty);
    }

    items.forEach((item) => {
      const { lowStock, expiryClass, days } = this._itemStatus(item);
      const row = document.createElement("div");
      row.className = "item-row" + (lowStock ? " low-stock" : "");

      const info = document.createElement("div");
      info.className = "item-info";
      let expiryLabel = "";
      if (days !== null) {
        if (days < 0) expiryLabel = `exspirovalo pred ${Math.abs(days)} d.`;
        else if (days === 0) expiryLabel = "exspiruje dnes";
        else expiryLabel = `exspiruje o ${days} d.`;
      }
      info.innerHTML = `
        <div class="item-name">${item.name}${
        item.category ? `<span class="category">${item.category}</span>` : ""
      }</div>
        <div class="item-meta">
          ${expiryLabel ? `<span class="badge ${expiryClass}">${expiryLabel}</span>` : ""}
          ${lowStock ? `<span class="badge low">nízky stav</span>` : ""}
        </div>
      `;

      const controls = document.createElement("div");
      controls.className = "item-controls";

      const minus = document.createElement("button");
      minus.className = "icon-btn";
      minus.textContent = "–";
      minus.addEventListener("click", () =>
        this._call("adjust_quantity", { item_id: item.item_id, delta: -1 })
      );

      const qty = document.createElement("span");
      qty.className = "qty";
      qty.textContent = `${item.quantity}${item.unit ? " " + item.unit : ""}`;

      const plus = document.createElement("button");
      plus.className = "icon-btn";
      plus.textContent = "+";
      plus.addEventListener("click", () =>
        this._call("adjust_quantity", { item_id: item.item_id, delta: 1 })
      );

      const del = document.createElement("button");
      del.className = "icon-btn delete";
      del.textContent = "✕";
      del.title = "Odstrániť";
      del.addEventListener("click", () => {
        if (confirm(`Odstrániť "${item.name}"?`)) {
          this._call("remove_item", { item_id: item.item_id });
        }
      });

      controls.append(minus, qty, plus, del);
      row.append(info, controls);
      list.appendChild(row);
    });

    return list;
  }

  _renderAddForm() {
    const wrap = document.createElement("div");
    wrap.className = "add-form-wrap";

    if (!this._showAddForm) {
      const btn = document.createElement("button");
      btn.className = "add-btn";
      btn.textContent = "+ Pridať položku";
      btn.addEventListener("click", () => {
        this._showAddForm = true;
        this._render();
      });
      wrap.appendChild(btn);
      return wrap;
    }

    const form = document.createElement("div");
    form.className = "add-form";
    form.innerHTML = `
      <input type="text" id="f-name" placeholder="Názov" />
      <div class="row">
        <input type="number" id="f-qty" placeholder="Počet" value="1" step="0.1" />
        <input type="text" id="f-unit" placeholder="Jednotka (ks, kg...)" />
      </div>
      <div class="row">
        <input type="date" id="f-expiration" />
        <input type="number" id="f-threshold" placeholder="Prah nízkeho stavu" step="0.1" />
      </div>
      <input type="text" id="f-category" placeholder="Kategória (voliteľné)" />
      <div class="row">
        <button id="f-cancel" class="secondary-btn">Zrušiť</button>
        <button id="f-submit" class="add-btn">Uložiť</button>
      </div>
    `;
    wrap.appendChild(form);

    form.querySelector("#f-cancel").addEventListener("click", () => {
      this._showAddForm = false;
      this._render();
    });

    form.querySelector("#f-submit").addEventListener("click", async () => {
      const name = form.querySelector("#f-name").value.trim();
      if (!name) return;
      const quantity = parseFloat(form.querySelector("#f-qty").value) || 1;
      const unit = form.querySelector("#f-unit").value.trim() || undefined;
      const expiration = form.querySelector("#f-expiration").value || undefined;
      const thresholdRaw = form.querySelector("#f-threshold").value;
      const threshold = thresholdRaw ? parseFloat(thresholdRaw) : undefined;
      const category = form.querySelector("#f-category").value.trim() || undefined;

      await this._call("add_item", {
        name,
        location: this._activeLocation,
        quantity,
        unit,
        expiration,
        threshold,
        category,
      });
      this._showAddForm = false;
      this._render();
    });

    return wrap;
  }
}

const CSS = `
  ha-card { padding-bottom: 8px; }
  .card-content { padding: 0 16px 16px; }
  .tabs { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
  .tab {
    background: var(--secondary-background-color, #eee);
    color: var(--primary-text-color);
    border: none; border-radius: 16px; padding: 6px 14px;
    font-size: 0.9em; cursor: pointer;
  }
  .tab.active { background: var(--primary-color); color: var(--text-primary-color, #fff); }
  .tab.add-location { font-weight: bold; padding: 6px 12px; }
  .summary { display: flex; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }
  .pill {
    background: var(--secondary-background-color, #eee);
    border-radius: 12px; padding: 3px 10px; font-size: 0.8em;
  }
  .pill.warn { background: rgba(255, 193, 7, 0.25); }
  .pill.danger { background: rgba(244, 67, 54, 0.25); }
  .item-list { display: flex; flex-direction: column; gap: 6px; }
  .empty { opacity: 0.6; padding: 12px 0; font-style: italic; }
  .item-row {
    display: flex; justify-content: space-between; align-items: center;
    background: var(--card-background-color);
    border: 1px solid var(--divider-color, #444);
    border-radius: 12px; padding: 8px 12px;
  }
  .item-row.low-stock { border-color: var(--warning-color, #ffa500); }
  .item-name { font-weight: 500; }
  .category {
    margin-left: 6px; font-size: 0.75em; opacity: 0.6;
    border: 1px solid var(--divider-color); border-radius: 8px; padding: 0 6px;
  }
  .item-meta { display: flex; gap: 6px; margin-top: 2px; }
  .badge { font-size: 0.72em; border-radius: 8px; padding: 1px 7px; background: var(--secondary-background-color); }
  .badge.expiring { background: rgba(255, 193, 7, 0.3); }
  .badge.expired { background: rgba(244, 67, 54, 0.3); }
  .badge.low { background: rgba(244, 67, 54, 0.2); }
  .item-controls { display: flex; align-items: center; gap: 6px; }
  .icon-btn {
    width: 28px; height: 28px; border-radius: 50%; border: none;
    background: var(--secondary-background-color, #eee); cursor: pointer; font-size: 1em;
    color: var(--primary-text-color);
  }
  .icon-btn.delete { color: var(--error-color, #f44336); }
  .qty { min-width: 48px; text-align: center; font-variant-numeric: tabular-nums; }
  .add-form-wrap { margin-top: 12px; }
  .add-btn {
    width: 100%; padding: 8px; border-radius: 10px; border: none;
    background: var(--primary-color); color: var(--text-primary-color, #fff);
    cursor: pointer; font-weight: 500;
  }
  .secondary-btn {
    width: 100%; padding: 8px; border-radius: 10px;
    border: 1px solid var(--divider-color); background: transparent;
    color: var(--primary-text-color); cursor: pointer;
  }
  .add-form { display: flex; flex-direction: column; gap: 8px; }
  .add-form .row { display: flex; gap: 8px; }
  .add-form input {
    flex: 1; padding: 8px; border-radius: 8px;
    border: 1px solid var(--divider-color, #444);
    background: var(--card-background-color); color: var(--primary-text-color);
  }
`;

customElements.define("inventory-card", InventoryCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "inventory-card",
  name: "Inventory Manager Card",
  description: "Spravuj zásoby v špajzi, chladničke a ďalších miestnostiach.",
});
