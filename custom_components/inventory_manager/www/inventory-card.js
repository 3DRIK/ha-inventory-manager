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
    this._editingItemId = null;
    this._locationMenuFor = null;
    this._longPressTimer = null;
    this._longPressTriggered = false;
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

  _esc(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
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
    card.appendChild(this._renderLocationMenu());
    root.appendChild(card);
  }

  _renderTabs() {
    const tabs = document.createElement("div");
    tabs.className = "tabs";

    this._data.locations.forEach((loc) => {
      const tab = document.createElement("button");
      tab.className = "tab" + (loc === this._activeLocation ? " active" : "");
      tab.textContent = loc;
      tab.title = "Podrž pre premenovanie/zmazanie";

      tab.addEventListener("pointerdown", () => {
        this._longPressTriggered = false;
        this._longPressTimer = setTimeout(() => {
          this._longPressTriggered = true;
          this._locationMenuFor = loc;
          this._render();
        }, 550);
      });
      const cancelLongPress = () => {
        clearTimeout(this._longPressTimer);
      };
      tab.addEventListener("pointerup", cancelLongPress);
      tab.addEventListener("pointerleave", cancelLongPress);
      tab.addEventListener("pointercancel", cancelLongPress);
      tab.addEventListener("contextmenu", (e) => e.preventDefault());

      tab.addEventListener("click", () => {
        if (this._longPressTriggered) {
          this._longPressTriggered = false;
          return;
        }
        this._activeLocation = loc;
        this._editingItemId = null;
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

  _renderLocationMenu() {
    if (!this._locationMenuFor) return document.createDocumentFragment();
    const loc = this._locationMenuFor;

    const overlay = document.createElement("div");
    overlay.className = "modal-overlay";
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) {
        this._locationMenuFor = null;
        this._render();
      }
    });

    const modal = document.createElement("div");
    modal.className = "modal";
    modal.innerHTML = `
      <div class="modal-title">Miestnosť: ${this._esc(loc)}</div>
      <input type="text" id="rename-input" value="${this._esc(loc)}" />
      <button id="rename-btn" class="add-btn">Premenovať</button>
      <button id="delete-btn" class="danger-btn">Zmazať miestnosť</button>
      <button id="close-btn" class="secondary-btn">Zavrieť</button>
    `;
    overlay.appendChild(modal);

    modal.querySelector("#rename-btn").addEventListener("click", async () => {
      const newName = modal.querySelector("#rename-input").value.trim();
      this._locationMenuFor = null;
      if (newName && newName !== loc) {
        if (this._activeLocation === loc) this._activeLocation = newName;
        await this._call("rename_location", { old_name: loc, new_name: newName });
      } else {
        this._render();
      }
    });

    modal.querySelector("#delete-btn").addEventListener("click", async () => {
      if (this._data.locations.length <= 1) {
        alert("Toto je jediná miestnosť, nedá sa zmazať.");
        return;
      }
      if (!confirm(`Naozaj zmazať miestnosť "${loc}"? Položky sa presunú do inej miestnosti.`)) {
        return;
      }
      this._locationMenuFor = null;
      if (this._activeLocation === loc) {
        this._activeLocation = this._data.locations.find((l) => l !== loc) || null;
      }
      await this._call("remove_location", { name: loc });
    });

    modal.querySelector("#close-btn").addEventListener("click", () => {
      this._locationMenuFor = null;
      this._render();
    });

    return overlay;
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
      const row = document.createElement("div");

      if (this._editingItemId === item.item_id) {
        row.className = "item-row editing";
        row.appendChild(this._renderEditForm(item));
        list.appendChild(row);
        return;
      }

      const { lowStock, expiryClass, days } = this._itemStatus(item);
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
        <div class="item-name">${this._esc(item.name)}${
        item.category ? `<span class="category">${this._esc(item.category)}</span>` : ""
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

      const edit = document.createElement("button");
      edit.className = "icon-btn edit";
      edit.textContent = "✎";
      edit.title = "Upraviť (názov, počet, exspirácia, prah...)";
      edit.addEventListener("click", () => {
        this._editingItemId = item.item_id;
        this._render();
      });

      const del = document.createElement("button");
      del.className = "icon-btn delete";
      del.textContent = "✕";
      del.title = "Odstrániť";
      del.addEventListener("click", () => {
        if (confirm(`Odstrániť "${item.name}"?`)) {
          this._call("remove_item", { item_id: item.item_id });
        }
      });

      controls.append(minus, qty, plus, edit, del);
      row.append(info, controls);
      list.appendChild(row);
    });

    return list;
  }

  _renderEditForm(item) {
    const wrap = document.createElement("div");
    wrap.className = "edit-form";
    wrap.innerHTML = `
      <input type="text" id="e-name" placeholder="Názov" value="${this._esc(item.name)}" />
      <div class="row">
        <input type="number" id="e-qty" placeholder="Počet" value="${item.quantity}" step="0.1" />
        <input type="text" id="e-unit" placeholder="Jednotka (ks, kg...)" value="${
          item.unit ? this._esc(item.unit) : ""
        }" />
      </div>
      <div class="row">
        <input type="date" id="e-expiration" value="${item.expiration || ""}" />
        <input type="number" id="e-threshold" placeholder="Prah nízkeho stavu" step="0.1" value="${
          item.threshold ?? ""
        }" />
      </div>
      <input type="text" id="e-category" placeholder="Kategória (voliteľné)" value="${
        item.category ? this._esc(item.category) : ""
      }" />
      <div class="hint">Prázdne pole exspirácie/prahu ponechá pôvodnú hodnotu (nevymaže ju).</div>
      <div class="row">
        <button id="e-cancel" class="secondary-btn">Zrušiť</button>
        <button id="e-submit" class="add-btn">Uložiť zmeny</button>
      </div>
    `;

    wrap.querySelector("#e-cancel").addEventListener("click", () => {
      this._editingItemId = null;
      this._render();
    });

    wrap.querySelector("#e-submit").addEventListener("click", async () => {
      const name = wrap.querySelector("#e-name").value.trim();
      const qtyRaw = wrap.querySelector("#e-qty").value;
      const unit = wrap.querySelector("#e-unit").value.trim();
      const expiration = wrap.querySelector("#e-expiration").value;
      const thresholdRaw = wrap.querySelector("#e-threshold").value;
      const category = wrap.querySelector("#e-category").value.trim();

      const payload = { item_id: item.item_id };
      if (name) payload.name = name;
      if (qtyRaw !== "" && !isNaN(parseFloat(qtyRaw))) payload.quantity = parseFloat(qtyRaw);
      if (unit) payload.unit = unit;
      if (expiration) payload.expiration = expiration;
      if (thresholdRaw !== "") payload.threshold = parseFloat(thresholdRaw);
      if (category) payload.category = category;

      await this._call("update_item", payload);
      this._editingItemId = null;
      this._render();
    });

    return wrap;
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
    user-select: none; -webkit-user-select: none; touch-action: manipulation;
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
  .item-row.editing { display: block; }
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
  .icon-btn.edit { font-size: 0.9em; }
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
  .add-form, .edit-form { display: flex; flex-direction: column; gap: 8px; }
  .add-form .row, .edit-form .row { display: flex; gap: 8px; }
  .add-form input, .edit-form input {
    flex: 1; padding: 8px; border-radius: 8px;
    border: 1px solid var(--divider-color, #444);
    background: var(--card-background-color); color: var(--primary-text-color);
  }
  .edit-form .hint { font-size: 0.75em; opacity: 0.6; }
  .modal-overlay {
    position: fixed; inset: 0; background: rgba(0, 0, 0, 0.5);
    display: flex; align-items: center; justify-content: center;
    z-index: 10; padding: 16px; box-sizing: border-box;
  }
  .modal {
    background: var(--card-background-color, #1e1e1e);
    border-radius: 16px; padding: 16px; width: 100%; max-width: 320px;
    display: flex; flex-direction: column; gap: 8px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
  }
  .modal-title { font-weight: 600; margin-bottom: 4px; }
  .modal input {
    padding: 8px; border-radius: 8px;
    border: 1px solid var(--divider-color, #444);
    background: var(--card-background-color); color: var(--primary-text-color);
  }
  .danger-btn {
    width: 100%; padding: 8px; border-radius: 10px; border: none;
    background: var(--error-color, #f44336); color: #fff;
    cursor: pointer; font-weight: 500;
  }
`;

customElements.define("inventory-card", InventoryCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "inventory-card",
  name: "Inventory Manager Card",
  description: "Spravuj zásoby v špajzi, chladničke a ďalších miestnostiach.",
});