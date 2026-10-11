(() => {
  const KEY = "abyssinianCart";
  const DELIVERY = 4;
  const TAX = 0.08;
  const DISCOUNT_MIN = 50;
  const DISCOUNT_RATE = 0.1;
  const TOAST_MS = 2200;

  let toastTimer = null;

  const $ = (id) => document.getElementById(id);

  const money = (number) => `ETB ${number.toFixed(2)}`;

  const getCart = () => {
    try {
      const cart = JSON.parse(localStorage.getItem(KEY));
      return Array.isArray(cart) ? cart : [];
    } catch {
      return [];
    }
  };

  const saveCart = (cart) => {
    localStorage.setItem(KEY, JSON.stringify(cart));
  };

  const totalQty = (cart) => {
    return cart.reduce((total, item) => total + item.qty, 0);
  };

  const setText = (id, text) => {
    const element = $(id);
    if (element) {
      element.textContent = text;
    }
  };

  const showToast = (message) => {
    let toast = $("cart-toast");

    if (!toast) {
      toast = document.createElement("div");
      toast.id = "cart-toast";
      toast.className = "toast";
      document.body.appendChild(toast);
    }

    toast.textContent = message;
    toast.classList.add("is-visible");

    clearTimeout(toastTimer);

    toastTimer = setTimeout(() => {
      toast.classList.remove("is-visible");
    }, TOAST_MS);
  };

  const updateBadge = (cart) => {
    const badge = $("cart-badge");

    if (!badge) return;

    const total = totalQty(cart);

    badge.textContent = total;
    badge.classList.toggle("is-hidden", total === 0);
  };

  const addToCart = (item) => {
    const cart = getCart();
    const existing = cart.find((cartItem) => cartItem.id === item.id);

    if (existing) {
      existing.qty++;
    } else {
      cart.push(item);
    }

    saveCart(cart);
    updateBadge(cart);
    showToast(`${item.name} added to cart`);
  };

  const renderCategory = (data, category, elementId) => {
    const container = document.getElementById(elementId);

    if (!container) return;

    const cards = data
      .filter((food) => food.category === category)
      .map((food) => {
        return `
          <article class="card">
            <div class="card-img-wrapper">
              <img
                src="/static/${escapeHtml(food.img)}"
                alt="${escapeHtml(food.name)}"
              />
            </div>

            <div class="card-body">
              <h3 class="card-name">${escapeHtml(food.name)}</h3>

              <p class="card-desc">
                ${escapeHtml(food.desc)}
              </p>

              <div class="card-actions">
                <span class="card-price">
                  ETB ${food.price.toFixed(2)}
                </span>

                <button
                  type="button"
                  class="btn-add"
                  data-id="${escapeHtml(food.id)}"
                  data-name="${escapeHtml(food.name)}"
                  data-desc="${escapeHtml(food.desc)}"
                  data-price="${food.price}"
                  data-img="${escapeHtml(food.img)}"
                >
                  Add to Cart
                </button>
              </div>
            </div>
          </article>
        `;
      })
      .join("");

    container.innerHTML = `
      <div class="menu-grid">
        ${cards}
      </div>
    `;

    const buttons = container.querySelectorAll(".btn-add");

    buttons.forEach((button) => {
      button.addEventListener("click", () => {
        const { id, name, desc, price, img } = button.dataset;

        addToCart({
          id,
          name,
          desc,
          price: parseFloat(price),
          img,
          qty: 1,
        });
      });
    });
  };

  const getFood = async () => {
    try {
      const response = await fetch("/api/menu");

      if (!response.ok) {
        throw new Error("Failed to load menu");
      }

      const data = await response.json();

      console.log("Menu received:", data);

      renderCategory(data, "ethiopian", "ethiopian");
      renderCategory(data, "starters", "starter");
      renderCategory(data, "main-course", "mains");
      renderCategory(data, "desserts", "dessert");
    } catch (error) {
      console.error("Error loading menu:", error);
    }
  };

  const cartItemTemplate = (item) => {
    return `
      <article class="cart-item" data-id="${escapeHtml(item.id)}">
        <img
          class="cart-item-img"
          src="/static/${escapeHtml(item.img)}"
          alt="${escapeHtml(item.name)}"
        />

        <div class="cart-item-body">
          <div class="cart-item-header">
            <div class="cart-item-heading">
              <h4 class="cart-item-name">${escapeHtml(item.name)}</h4>
              <p class="cart-item-desc">${escapeHtml(item.desc)}</p>
            </div>

            <span class="cart-item-unit">
              ${money(item.price)}
            </span>
          </div>

          <div class="cart-item-footer">
            <div class="qty-control">
              <button
                type="button"
                class="qty-btn"
                data-action="minus"
                ${item.qty <= 1 ? "disabled" : ""}
                aria-label="Decrease quantity"
              >
                &minus;
              </button>

              <span class="qty-value">${item.qty}</span>

              <button
                type="button"
                class="qty-btn"
                data-action="plus"
                aria-label="Increase quantity"
              >
                &plus;
              </button>
            </div>

            <div class="cart-item-subtotal">
              <span class="label">Item Total</span>
              <span class="value">
                ${money(item.price * item.qty)}
              </span>
            </div>

            <button
              type="button"
              class="btn-remove"
              data-action="remove"
            >
              Remove
            </button>
          </div>
        </div>
      </article>
    `;
  };

  const calculateDiscount = (subtotal) => {
    return subtotal >= DISCOUNT_MIN ? subtotal * DISCOUNT_RATE : 0;
  };

  const updateTotals = (cart) => {
    const subtotal = cart.reduce((sum, item) => sum + item.price * item.qty, 0);

    const delivery = subtotal > 0 ? DELIVERY : 0;
    const tax = subtotal * TAX;
    const discount = calculateDiscount(subtotal);
    const grand = subtotal + delivery + tax - discount;

    setText("summary-subtotal", money(subtotal));
    setText("summary-delivery", money(delivery));
    setText("summary-tax", money(tax));

    setText(
      "summary-discount",
      discount > 0 ? `-${money(discount)}` : money(discount),
    );

    $("summary-discount")?.classList.toggle("is-active", discount > 0);

    setText("summary-grand", money(grand));
  };

  const renderCart = () => {
    const cart = getCart();

    const list = $("cart-items");
    const empty = $("cart-empty");
    const summary = $("cart-summary");
    const countLine = $("cart-count-line");

    if (!list) return;

    setText("cart-count", totalQty(cart));

    countLine?.classList.toggle("is-hidden", cart.length === 0);

    if (cart.length === 0) {
      list.innerHTML = "";
      empty?.classList.remove("is-hidden");
      summary?.classList.add("is-hidden");
      updateBadge(cart);
      return;
    }

    empty?.classList.add("is-hidden");
    summary?.classList.remove("is-hidden");

    list.innerHTML = cart.map(cartItemTemplate).join("");

    updateTotals(cart);
    updateBadge(cart);
  };

  const changeQty = (id, delta) => {
    const cart = getCart();
    const item = cart.find((item) => item.id === id);

    if (!item || item.qty + delta < 1) {
      return;
    }

    item.qty += delta;

    saveCart(cart);

    const element = document.querySelector(`.cart-item[data-id="${id}"]`);

    if (element) {
      const qtyValue = element.querySelector(".qty-value");
      const subtotal = element.querySelector(".cart-item-subtotal .value");
      const minusButton = element.querySelector('[data-action="minus"]');

      if (qtyValue) {
        qtyValue.textContent = item.qty;
      }

      if (subtotal) {
        subtotal.textContent = money(item.price * item.qty);
      }

      if (minusButton) {
        minusButton.disabled = item.qty <= 1;
      }
    }

    updateTotals(cart);
    setText("cart-count", totalQty(cart));
    updateBadge(cart);

    showToast(`${item.name} quantity updated`);
  };

  const removeItem = (id) => {
    const cart = getCart();
    const item = cart.find((item) => item.id === id);

    if (!item) return;

    const confirmed = window.confirm(`Remove "${item.name}" from your cart?`);

    if (!confirmed) return;

    const updatedCart = cart.filter((item) => item.id !== id);

    saveCart(updatedCart);
    renderCart();

    showToast(`${item.name} removed from cart`);
  };

  const placeOrder = async () => {
    const cart = getCart();

    if (cart.length === 0) return;

    const customer = prompt("Enter your name:");

    if (!customer) return;

    // Only send item ids and quantities - the server looks up the real menu
    // price for each one and calculates the total itself.
    const items = cart.map((item) => ({ item_id: item.id, qty: item.qty }));

    try {
      const response = await fetch("/api/orders", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          customer,
          items,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || "Failed to place order");
      }

      console.log("Order created:", data);

      saveCart([]);
      renderCart();

      showToast("Order placed successfully");

      showOrderConfirmation(data.order, customer);
    } catch (error) {
      console.error("Order error:", error);
      showToast(error.message || "Failed to place order");
    }
  };

  const showOrderConfirmation = (order, customerName) => {
    if (order) {
      setText("order-modal-id", `#${order.id}`);

      const trackLink = $("order-modal-track");
      if (trackLink) {
        trackLink.href = `${trackLink.dataset.baseHref}?id=${order.id}&customer=${encodeURIComponent(customerName)}`;
      }
    }

    $("order-modal")?.classList.add("is-open");
  };

  const initCartPage = () => {
    const list = $("cart-items");

    if (!list) return false;

    renderCart();

    list.addEventListener("click", (event) => {
      const button = event.target.closest("[data-action]");
      const itemElement = button?.closest(".cart-item");

      if (!button || !itemElement) return;

      const { id } = itemElement.dataset;
      const action = button.dataset.action;

      if (action === "plus") {
        changeQty(id, 1);
      }

      if (action === "minus") {
        changeQty(id, -1);
      }

      if (action === "remove") {
        removeItem(id);
      }
    });

    const orderButton = $("place-order");

    if (orderButton) {
      orderButton.addEventListener("click", placeOrder);
    }

    const modal = $("order-modal");

    modal?.addEventListener("click", (event) => {
      if (event.target === modal) {
        modal.classList.remove("is-open");
      }
    });

    return true;
  };

  document.addEventListener("DOMContentLoaded", () => {
    updateBadge(getCart());

    if (initCartPage()) {
      return;
    }

    getFood();
  });
})();
